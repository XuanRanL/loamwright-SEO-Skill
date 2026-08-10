"""
scripts/wordpress/wp_media.py — WordPress Media Library upload.

Operations:
  - upload(file_path, alt, caption, title) → WPMedia (id + source_url)
  - upload_batch(items)                     → bulk with progress
  - set_featured_image(post_id, media_id)
  - delete(media_id)                        → for rollback / cleanup
  - search_by_filename(filename)             → find existing uploads

Features:
  - Multipart upload via wp_client
  - Auto-detect MIME (WebP, PNG, JPEG, AVIF supported)
  - Alt-text, caption, title, description all set in one call
  - Updates Yoast image meta (via MU-plugin) if available
  - srcset variants: WP auto-generates standard sizes;
    if you've pre-built variants, upload primary only
  - Idempotency: optional check_existing_by_filename to avoid duplicate uploads

Used by:
  - wp_publisher.py during image injection step
  - /init image-fetch step (for downloading WP-hosted images during baseline)

CLI:
    python -m scripts.wordpress.wp_media example-com upload image.webp --alt "..."
    python -m scripts.wordpress.wp_media example-com set-featured 123 456
    python -m scripts.wordpress.wp_media example-com search image.webp
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scripts.wordpress.wp_client import WPClient, WPApiError, WPNotFoundError


# Supported image types
SUPPORTED_MIMES = {
    "image/webp", "image/png", "image/jpeg", "image/jpg",
    "image/gif", "image/avif", "image/svg+xml",
}


# ─── Upload-format normalization (default WebP, LOSSLESS / 100% quality) ──────
# Every image is converted to WebP before upload BY DEFAULT. WordPress 5.8+ accepts
# image/webp (verified live on project-charlie 2026-06-03: POST /wp/v2/media of a .webp
# returned 201 with mime_type=image/webp).
#
# QUALITY POLICY (user directive 2026-06-03): WebP is LOSSLESS at full resolution —
# NO lossy compression, NO downscaling. PNG/JPEG sources are re-encoded into the WebP
# container with ZERO pixel loss (lossless=True). For the project's gpt-image PNG sources
# (themselves lossless) this is a pure container swap: bit-for-bit identical pixels, and
# lossless WebP is still typically smaller than the source PNG, so it also avoids the
# 2026-06-03 oversized-PNG upload reset (WinError 10054) WITHOUT sacrificing any quality.
#
# Resizing is OFF by default (max_dim=0). A caller may pass max_dim>0 to opt into a cap,
# but the default preserves 100% resolution. Override format per run with env
# XS_UPLOAD_IMAGE_FORMAT=original|png|jpeg, or per call via upload(..., upload_format=...).
# "original" disables conversion entirely.
DEFAULT_UPLOAD_FORMAT = (os.environ.get("XS_UPLOAD_IMAGE_FORMAT") or "webp").strip().lower()
DEFAULT_MAX_UPLOAD_DIM = int(os.environ.get("XS_UPLOAD_MAX_DIM") or "0")  # 0 = no downscale


def _normalize_image_for_upload(path: Path, *, fmt: str = "", max_dim: int = 0) -> Path:
    """Return an upload-ready image path, converting to `fmt` (default WebP) at 100% quality.

    WebP is written LOSSLESS (zero pixel loss). Downscaling happens ONLY if `max_dim` (or the
    env default) is > 0; by default resolution is preserved. SVG/GIF and anything already in
    the target format AND not being resized pass through untouched. ANY failure returns the
    ORIGINAL path — image normalization must never block a publish. Pillow is required for
    conversion; if it is unavailable the original file uploads unchanged.
    """
    fmt = (fmt or DEFAULT_UPLOAD_FORMAT or "webp").lstrip(".").lower()
    if max_dim <= 0:
        max_dim = DEFAULT_MAX_UPLOAD_DIM
    if fmt in ("original", "none", "keep"):
        return path
    if path.suffix.lower() in (".svg", ".gif"):  # vector / animated — leave as-is
        return path
    if fmt not in ("webp", "jpeg", "jpg", "png"):
        fmt = "webp"
    try:
        from PIL import Image, ImageOps
        img = Image.open(path)
        # Bake in EXIF orientation before re-encoding. WebP carries orientation
        # inconsistently across viewers, and phone-camera photos (other projects)
        # commonly rely on the EXIF tag; without this they could upload rotated.
        # No-op for the gpt-image PNGs this project uses (they carry no EXIF).
        img = ImageOps.exif_transpose(img) or img
        w, h = img.size
        src_ext = path.suffix.lower().lstrip(".")
        same_fmt = src_ext == fmt or {src_ext, fmt} <= {"jpg", "jpeg"}
        needs_resize = max_dim > 0 and max(w, h) > max_dim
        if same_fmt and not needs_resize:
            return path
        if needs_resize:
            img = img.copy()
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        ext = "webp" if fmt == "webp" else ("jpg" if fmt in ("jpg", "jpeg") else "png")
        out = path.with_suffix("." + ext)
        if out == path:  # same-extension resize → avoid clobbering by name collision
            out = path.with_name(path.stem + "-up." + ext)
        if fmt == "webp":
            # LOSSLESS = 100% quality, zero pixel loss. method=6 = max compression effort
            # (smallest lossless file; the `quality` arg is only an effort hint when lossless).
            save_img = img if img.mode in ("RGB", "RGBA", "P", "L") else img.convert("RGBA")
            save_img.save(out, "WEBP", lossless=True, quality=100, method=6)
        elif fmt in ("jpg", "jpeg"):
            # JPEG is inherently lossy; at user request use the maximum-fidelity setting
            # (quality=100, no chroma subsampling). Prefer WebP for true lossless.
            img.convert("RGB").save(out, "JPEG", quality=100, subsampling=0, optimize=True)
        else:  # png
            img.save(out, "PNG", optimize=True)
        return out if out.exists() else path
    except Exception:
        return path


@dataclass(frozen=True)
class WPMedia:
    """A media object from WordPress Media Library."""
    id: int
    source_url: str               # absolute URL to original file
    title: str
    alt_text: str
    caption: str
    description: str
    media_type: str               # "image" / "file"
    mime_type: str                # e.g. "image/webp"
    media_details_width: int      # px
    media_details_height: int
    sizes: dict                    # dict of named sizes (thumbnail/medium/large) with .source_url
    filename: str                  # without path
    post: int                      # 0 if unattached


# ─── Helpers ────────────────────────────────────────────

def _parse_media(d: dict) -> WPMedia:
    """Convert WP REST media JSON → WPMedia."""
    media_details = d.get("media_details", {}) or {}
    sizes = media_details.get("sizes", {}) or {}
    # Extract filename
    filename = ""
    if d.get("source_url"):
        filename = d["source_url"].rsplit("/", 1)[-1]

    return WPMedia(
        id=d["id"],
        source_url=d.get("source_url", ""),
        title=d.get("title", {}).get("rendered", "") if isinstance(d.get("title"), dict) else d.get("title", ""),
        alt_text=d.get("alt_text", ""),
        caption=d.get("caption", {}).get("rendered", "") if isinstance(d.get("caption"), dict) else d.get("caption", ""),
        description=d.get("description", {}).get("rendered", "") if isinstance(d.get("description"), dict) else d.get("description", ""),
        media_type=d.get("media_type", "file"),
        mime_type=d.get("mime_type", ""),
        media_details_width=media_details.get("width", 0),
        media_details_height=media_details.get("height", 0),
        sizes=sizes,
        filename=filename,
        post=d.get("post", 0) or 0,
    )


# ─── Upload ────────────────────────────────────────────

def upload(
    client: WPClient,
    file_path: Path,
    *,
    alt_text: str = "",
    caption: str = "",
    title: str = "",
    description: str = "",
    post_id: int | None = None,
    check_existing_by_filename: bool = True,
    upload_format: str = "",
    max_dim: int = 0,
) -> WPMedia:
    """Upload a single file to Media Library.

    Args:
        client: WPClient instance.
        file_path: Local path to image file.
        alt_text: Image alt attribute (REQUIRED for SEO; we'll warn if empty).
        caption: Visible caption.
        title: Internal title (defaults to filename).
        description: Long description.
        post_id: Attach to specific post (None = unattached, fine for inline images).
        check_existing_by_filename: If True, search for existing upload with same filename first.

    Returns:
        WPMedia.

    Raises:
        FileNotFoundError, WPApiError.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Image not found: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"Not a file: {file_path}")

    # Normalize to the configured upload format (default WebP) + cap longest side.
    # Done FIRST so the dedup search-by-filename and the multipart mime both see the
    # converted file. Returns the original path on any failure (never blocks publish).
    file_path = _normalize_image_for_upload(file_path, fmt=upload_format, max_dim=max_dim)

    # Validate MIME
    mime, _ = mimetypes.guess_type(str(file_path))
    if mime and mime not in SUPPORTED_MIMES:
        # WP may still accept; just warn
        pass

    # Sanity: alt_text for SEO
    if not alt_text:
        import warnings
        warnings.warn(f"Uploading {file_path.name} without alt_text — bad for SEO", stacklevel=2)

    # Check existing if requested
    if check_existing_by_filename:
        existing = search_by_filename(client, file_path.name)
        if existing:
            return existing[0]

    if not title:
        title = file_path.stem.replace("-", " ").replace("_", " ").title()

    raw = client.upload_file(
        file_path,
        alt_text=alt_text, caption=caption, title=title,
        description=description, post_id=post_id,
    )
    return _parse_media(raw)


def upload_batch(
    client: WPClient,
    items: list[dict],
    *,
    on_progress: Any = None,
) -> list[WPMedia | Exception]:
    """Upload multiple files. Returns list of WPMedia OR Exception per item.

    items: list of {file_path, alt_text, caption?, title?, post_id?}
    on_progress: optional callable(i, total, item, result_or_error)
    """
    results: list[WPMedia | Exception] = []
    total = len(items)
    for i, item in enumerate(items, 1):
        try:
            m = upload(client, Path(item["file_path"]), **{
                k: v for k, v in item.items() if k != "file_path"
            })
            results.append(m)
            if on_progress:
                on_progress(i, total, item, m)
        except Exception as e:
            results.append(e)
            if on_progress:
                on_progress(i, total, item, e)
    return results


# ─── Search ────────────────────────────────────────────

def search_by_filename(client: WPClient, filename: str) -> list[WPMedia]:
    """Find media library items by filename (best-effort search).

    WP REST doesn't have a direct "by filename" endpoint, but the `search`
    parameter does substring match on title/content/excerpt + the filename
    is often in the title.
    """
    stem = Path(filename).stem
    try:
        r = client.get("/wp/v2/media", params={"search": stem, "per_page": 20})
    except WPApiError:
        return []

    if not isinstance(r.json_data, list):
        return []

    result = []
    for d in r.json_data:
        m = _parse_media(d)
        if m.filename == filename or stem in m.filename:
            result.append(m)
    return result


# ─── Featured image ───────────────────────────────────

def set_featured_image(client: WPClient, post_id: int, media_id: int) -> None:
    """Set a media item as the post's featured image."""
    r = client.patch(f"/wp/v2/posts/{post_id}", json_body={"featured_media": media_id})
    if r.status not in (200, 201):
        raise WPApiError(r.status, "Failed to set featured image")


# ─── Update metadata after upload ─────────────────────

def update_media(
    client: WPClient,
    media_id: int,
    *,
    alt_text: str | None = None,
    caption: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> WPMedia:
    """Update existing media item's metadata."""
    payload: dict = {}
    if alt_text is not None:
        payload["alt_text"] = alt_text
    if caption is not None:
        payload["caption"] = caption
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if not payload:
        raise ValueError("Nothing to update")
    r = client.post(f"/wp/v2/media/{media_id}", json_body=payload)
    return _parse_media(r.json_data)


# ─── Delete ───────────────────────────────────────────

def delete_media(client: WPClient, media_id: int, *, force: bool = True) -> None:
    """Delete a media item (and remove file from server if force=True)."""
    r = client.delete(f"/wp/v2/media/{media_id}", params={"force": "true" if force else "false"})
    if r.status not in (200, 204):
        raise WPApiError(r.status, f"Failed to delete media {media_id}")


# ─── CLI ──────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="WP Media Library operations")
    ap.add_argument("site_slug")
    sub = ap.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("upload", help="Upload a file")
    up.add_argument("file", type=Path)
    up.add_argument("--alt", default="", help="Alt text (REQUIRED for SEO)")
    up.add_argument("--caption", default="")
    up.add_argument("--title", default="")
    up.add_argument("--description", default="")
    up.add_argument("--post-id", type=int)
    up.add_argument("--no-dedup", action="store_true")
    up.add_argument("--json", action="store_true")

    fea = sub.add_parser("set-featured", help="Set featured image on a post")
    fea.add_argument("post_id", type=int)
    fea.add_argument("media_id", type=int)

    sea = sub.add_parser("search", help="Search media by filename")
    sea.add_argument("filename")
    sea.add_argument("--json", action="store_true")

    de = sub.add_parser("delete", help="Delete a media item")
    de.add_argument("media_id", type=int)

    ap.add_argument("--allow-http", action="store_true")
    args = ap.parse_args()

    try:
        wp = WPClient(args.site_slug, allow_http_for_testing=args.allow_http)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    with wp:
        if args.cmd == "upload":
            try:
                m = upload(
                    wp, args.file,
                    alt_text=args.alt, caption=args.caption,
                    title=args.title, description=args.description,
                    post_id=args.post_id,
                    check_existing_by_filename=not args.no_dedup,
                )
            except (FileNotFoundError, WPApiError) as e:
                print(f"Upload failed: {e}", file=sys.stderr)
                return 1
            if args.json:
                print(json.dumps(asdict(m), indent=2, ensure_ascii=False))
            else:
                print(f"Uploaded:")
                print(f"  ID:         {m.id}")
                print(f"  URL:        {m.source_url}")
                print(f"  Dimensions: {m.media_details_width}x{m.media_details_height}")
                print(f"  Sizes:      {list(m.sizes.keys())}")
            return 0

        if args.cmd == "set-featured":
            try:
                set_featured_image(wp, args.post_id, args.media_id)
                print(f"Set media {args.media_id} as featured image of post {args.post_id}")
            except WPApiError as e:
                print(f"Failed: {e}", file=sys.stderr)
                return 1
            return 0

        if args.cmd == "search":
            results = search_by_filename(wp, args.filename)
            if args.json:
                print(json.dumps([asdict(m) for m in results], indent=2, ensure_ascii=False))
            else:
                print(f"Found {len(results)} media item(s):")
                for m in results:
                    print(f"  [{m.id}]  {m.filename}  {m.source_url}")
            return 0

        if args.cmd == "delete":
            try:
                delete_media(wp, args.media_id)
                print(f"Deleted media {args.media_id}")
            except WPApiError as e:
                print(f"Failed: {e}", file=sys.stderr)
                return 1
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
