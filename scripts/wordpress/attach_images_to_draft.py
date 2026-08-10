"""
scripts/wordpress/attach_images_to_draft.py — Phase 2 of B-flow publish.

Pairs with `wp_publisher.py --defer-images`:

  Phase 1 (wp_publisher --defer-images):
    - Creates WP draft with HTML placeholder figures
    - Writes projects/{slug}/.seo/pending-images.json sidecar tracking what's pending

  Phase 2 (THIS SCRIPT):
    - For each pending entry, when images on disk are ready:
      1. Upload each image to WP Media Library (with alt/caption/title)
      2. Fetch current draft body from WP
      3. Replace <figure class="xuanran-pending-image" data-slot="X"> blocks
         with proper <figure><img></figure>
      4. PATCH draft body back to WP
      5. Set featured image (first slot marked is_featured, or by config)
      6. Mark sidecar entry status='attached'
      7. Optionally notify (stdout JSON; can be piped to webhook)

The script is idempotent — re-running on an already-attached entry is a no-op.

CLI:
    # Attach for one specific post
    python -m scripts.wordpress.attach_images_to_draft <slug> --post-id 123

    # Process all pending entries that have images on disk
    python -m scripts.wordpress.attach_images_to_draft <slug> --all

    # Watch mode: poll every N seconds, attach as images become available
    python -m scripts.wordpress.attach_images_to_draft <slug> --watch --interval 60

    # Dry run
    python -m scripts.wordpress.attach_images_to_draft <slug> --all --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.wordpress import wp_media
from scripts.wordpress.wp_client import WPClient, WPApiError


SIDECAR_REL_PATH = ".seo/pending-images.json"


@dataclass
class AttachResult:
    post_id: int
    success: bool
    attached_slot_ids: list[str] = field(default_factory=list)
    failed_slot_ids: list[str] = field(default_factory=list)
    media_ids: list[int] = field(default_factory=list)
    featured_media_id: int | None = None
    error: str | None = None
    duration_seconds: float = 0


# ─── Sidecar I/O ──────────────────────────────────────────

def _sidecar_path(site_slug: str) -> Path:
    from scripts._core.file_bus import PLUGIN_ROOT
    return PLUGIN_ROOT / "projects" / site_slug / SIDECAR_REL_PATH


def _load_sidecar(site_slug: str) -> dict:
    p = _sidecar_path(site_slug)
    if not p.exists():
        return {"pending": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        # Audit 2026-05-22 P1 — log silent-fallback (was: bare pass)
        print(
            f"⚠ _load_sidecar({site_slug!r}): {p.name} unreadable "
            f"({type(e).__name__}: {e}) — using empty pending list",
            file=sys.stderr,
        )
        return {"pending": []}


def _save_sidecar(site_slug: str, data: dict) -> None:
    p = _sidecar_path(site_slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _entry_ready_to_attach(entry: dict) -> tuple[bool, list[str]]:
    """Returns (all_ready, missing_slot_ids)."""
    if entry.get("status") != "awaiting_images":
        return (False, [])
    missing = []
    for slot in entry.get("slots", []):
        path = slot.get("image_path")
        if not path or not Path(path).exists():
            missing.append(slot.get("slot_id", ""))
    return (len(missing) == 0, missing)


# ─── Body manipulation ────────────────────────────────────

def pending_figure_re(site_slug: str = "") -> re.Pattern[str]:
    """Placeholder-figure matcher. Tokenized projects publish the figure with a
    per-project token class (style_tokens transform at the publish boundary),
    so match legacy OR token form (2026-08-01 de-fingerprint)."""
    from scripts._core import style_tokens

    cls_pat = (style_tokens.match_alternation(site_slug, "xuanran-pending-image")
               if site_slug else "xuanran-pending-image")
    return re.compile(
        rf'<figure\s+class="{cls_pat}"\s+'
        r'data-slot="([^"]+)"'
        r'(?:\s+data-alt="([^"]*)")?'
        r'\s*>.*?</figure>',
        re.DOTALL | re.IGNORECASE,
    )


def _build_real_figure(media: wp_media.WPMedia, alt: str, caption: str = "") -> str:
    """Build <figure><img></figure> with srcset + lazy loading."""
    import html as _html
    alt_escaped = _html.escape(alt or media.alt_text or "")
    sizes_attr = ""
    srcset_parts = []
    for size_name in ("medium", "large", "full"):
        size_info = (media.sizes or {}).get(size_name)
        if size_info and isinstance(size_info, dict):
            url = size_info.get("source_url")
            width = size_info.get("width")
            if url and width:
                srcset_parts.append(f"{url} {width}w")
    srcset_attr = f' srcset="{", ".join(srcset_parts)}"' if srcset_parts else ""
    if srcset_parts:
        sizes_attr = ' sizes="(max-width: 768px) 100vw, 768px"'

    caption_html = ""
    if caption:
        caption_html = f'\n  <figcaption>{_html.escape(caption)}</figcaption>'

    return (
        f'<figure class="wp-block-image size-large">\n'
        f'  <img src="{media.source_url}"{srcset_attr}{sizes_attr} '
        f'alt="{alt_escaped}" loading="lazy" '
        f'width="{media.media_details_width or ""}" '
        f'height="{media.media_details_height or ""}" />'
        f'{caption_html}\n'
        f'</figure>'
    )


def _replace_placeholders_in_body(
    body: str,
    slot_to_media: dict[str, wp_media.WPMedia],
    slot_to_alt: dict[str, str],
    slot_to_caption: dict[str, str],
    site_slug: str = "",
) -> tuple[str, list[str]]:
    """Replace pending-image figures with real figures. Returns (new_body, attached_slot_ids)."""
    attached: list[str] = []

    def _repl(m: re.Match) -> str:
        slot = m.group(1)
        if slot in slot_to_media:
            attached.append(slot)
            return _build_real_figure(
                slot_to_media[slot],
                slot_to_alt.get(slot, ""),
                slot_to_caption.get(slot, ""),
            )
        # Keep placeholder if media unavailable (partial attach)
        return m.group(0)

    new_body = pending_figure_re(site_slug).sub(_repl, body)
    return new_body, attached


# ─── Core attach ──────────────────────────────────────────

def attach_one(
    wp: WPClient, site_slug: str, entry: dict, *, dry_run: bool = False,
) -> AttachResult:
    t_start = time.time()
    post_id = entry["post_id"]
    result = AttachResult(post_id=post_id, success=False)

    ready, missing = _entry_ready_to_attach(entry)
    if not ready:
        result.error = f"Not ready: missing image files for slots {missing}"
        return result

    if dry_run:
        result.success = True
        result.attached_slot_ids = [s["slot_id"] for s in entry["slots"]]
        print(f"[DRY] Would attach {len(entry['slots'])} images to post {post_id}")
        return result

    # ── Step 1: Upload all images to Media Library ─────────
    slot_to_media: dict[str, wp_media.WPMedia] = {}
    slot_to_alt: dict[str, str] = {}
    slot_to_caption: dict[str, str] = {}
    featured_media_id: int | None = None

    for slot in entry["slots"]:
        slot_id = slot["slot_id"]
        path = Path(slot["image_path"])
        try:
            m = wp_media.upload(
                wp, path,
                alt_text=slot.get("alt", ""),
                caption=slot.get("caption", ""),
                title=slot.get("title", ""),
                check_existing_by_filename=True,
            )
        except Exception as e:
            result.failed_slot_ids.append(slot_id)
            result.error = f"Upload failed for slot {slot_id}: {e}"
            # Don't abort — try remaining slots so we get partial success
            continue
        slot_to_media[slot_id] = m
        slot_to_alt[slot_id] = slot.get("alt", "")
        slot_to_caption[slot_id] = slot.get("caption", "")
        result.media_ids.append(m.id)
        if slot.get("is_featured"):
            featured_media_id = m.id

    if not slot_to_media:
        return result  # nothing uploaded; error already set

    # ── Step 2: Fetch current draft body from WP ────────
    try:
        r = wp.get(f"/wp/v2/posts/{post_id}", params={"context": "edit"})
        post = r.json_data
        # `content.raw` is editable; `content.rendered` is filtered
        current_body = (post.get("content") or {}).get("raw", "")
        if not current_body:
            current_body = (post.get("content") or {}).get("rendered", "")
    except WPApiError as e:
        result.error = f"Failed to fetch post {post_id}: {e}"
        return result

    # ── Step 3: Replace placeholders ─────────────────────
    new_body, attached = _replace_placeholders_in_body(
        current_body, slot_to_media, slot_to_alt, slot_to_caption,
        site_slug=site_slug,
    )
    result.attached_slot_ids = attached

    if new_body == current_body:
        result.error = "No placeholders found in draft body — nothing patched"
        return result

    # ── Step 4: PATCH body back to WP ──────────────────
    patch_payload: dict[str, Any] = {"content": new_body}
    if featured_media_id is not None:
        patch_payload["featured_media"] = featured_media_id
        result.featured_media_id = featured_media_id

    try:
        wp.patch(f"/wp/v2/posts/{post_id}", json_body=patch_payload)
    except WPApiError as e:
        result.error = f"Failed to patch post body: {e}"
        return result

    # ── Step 5: Mark sidecar entry as attached ───────────
    # (caller updates the sidecar)

    result.success = True
    result.duration_seconds = round(time.time() - t_start, 2)
    return result


def attach_all_ready(
    site_slug: str,
    *,
    post_id_filter: int | None = None,
    dry_run: bool = False,
    allow_http: bool = False,
) -> list[AttachResult]:
    """Process all sidecar entries whose images are ready."""
    sidecar = _load_sidecar(site_slug)
    pending = sidecar.get("pending", [])
    if not pending:
        return []

    wp = WPClient(site_slug, allow_http_for_testing=allow_http)
    results: list[AttachResult] = []

    with wp:
        for entry in pending:
            if entry.get("status") != "awaiting_images":
                continue
            if post_id_filter is not None and entry.get("post_id") != post_id_filter:
                continue
            ready, _ = _entry_ready_to_attach(entry)
            if not ready:
                continue

            res = attach_one(wp, site_slug, entry, dry_run=dry_run)
            results.append(res)
            if res.success and not dry_run:
                entry["status"] = "attached"
                entry["attached_at"] = datetime.now(timezone.utc).isoformat()
                entry["media_ids"] = res.media_ids
                entry["featured_media_id"] = res.featured_media_id

    if not dry_run:
        _save_sidecar(site_slug, sidecar)

    return results


# ─── CLI ──────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Attach generated images to deferred WordPress draft(s)"
    )
    ap.add_argument("site_slug")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--post-id", type=int, help="Process only this specific draft")
    g.add_argument("--all", action="store_true", help="Process all pending entries ready to attach")
    g.add_argument("--watch", action="store_true",
                   help="Poll the sidecar and attach as soon as images become available")
    ap.add_argument("--interval", type=int, default=60, help="Poll interval (s) in --watch mode")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-http", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.watch:
        print(f"Watching {_sidecar_path(args.site_slug)} every {args.interval}s. Ctrl+C to stop.",
              file=sys.stderr)
        try:
            while True:
                results = attach_all_ready(
                    args.site_slug, dry_run=args.dry_run, allow_http=args.allow_http,
                )
                for r in results:
                    icon = "✓" if r.success else "✗"
                    print(f"{icon} post {r.post_id}: attached={r.attached_slot_ids} "
                          f"failed={r.failed_slot_ids} duration={r.duration_seconds}s",
                          file=sys.stderr)
                    if r.error:
                        print(f"  error: {r.error}", file=sys.stderr)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.", file=sys.stderr)
            return 0

    pid = args.post_id if args.post_id else None
    results = attach_all_ready(
        args.site_slug,
        post_id_filter=pid,
        dry_run=args.dry_run,
        allow_http=args.allow_http,
    )

    if not results:
        if args.post_id:
            print(f"No pending entry found for post {args.post_id} or not yet ready", file=sys.stderr)
        else:
            print("Nothing to attach (no entries ready)", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))
    else:
        for r in results:
            icon = "✓" if r.success else "✗"
            print(f"{icon} Post {r.post_id}")
            print(f"   Attached slots: {r.attached_slot_ids}")
            if r.failed_slot_ids:
                print(f"   Failed slots:   {r.failed_slot_ids}")
            print(f"   Media IDs:      {r.media_ids}")
            print(f"   Featured:       {r.featured_media_id}")
            print(f"   Duration:       {r.duration_seconds}s")
            if r.error:
                print(f"   ERROR: {r.error}")

    return 0 if all(r.success for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
