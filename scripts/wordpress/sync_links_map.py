"""Rebuild the "Published articles" section of internal-links-map.md from WP REST.

Root cure for the 2026-07-17 finding (Rule 6 dead wiring): every layer of
documentation said internal-links-map.md is "populated by the publisher as
articles go live", but NO code path ever wrote it — the file stayed frozen at
its /init value ("(none yet)") while sites accumulated dozens of live posts, so
agents/linker.md had ZERO blog-to-blog link targets. 8/10 projects carried the
stale marker; 2 were missing the file entirely.

Design: REGENERATE (not append) from the authoritative source — the live WP REST
inventory (feedback_site_inventory_authoritative_source). Idempotent; only the
"## Published articles" section is touched, everything else in the file is
preserved. Only status=publish posts are listed (a draft is not a link target).

Wired: wp_publisher calls this best-effort after every successful publish flow;
it is also a standalone CLI for backfills:

    python -m scripts.wordpress.sync_links_map {slug} [--dry-run] [--json]
"""
from __future__ import annotations

import argparse
import html
import json
import sys

from scripts._core.project_paths import internal_links_map_path

SECTION_HEADER = "## Published articles"


def _paginate(wp, path: str, params: dict) -> list[dict]:
    """Fetch every page of a WP collection.

    When the item count is an exact multiple of per_page, WP answers the
    one-past-the-end page with HTTP 400 `rest_post_invalid_page_number`
    ("page number ... larger than the number of pages available") — that is
    end-of-collection, not an error (hit live on project-charlie, exactly 100 posts).
    """
    from scripts.wordpress.wp_client import WPApiError

    items: list[dict] = []
    page = 1
    while True:
        try:
            r = wp.get(path, params={**params, "page": page})
        except WPApiError as e:
            if e.status == 400 and "number of pages" in str(e).lower():
                break
            raise
        batch = r.json_data
        if not isinstance(batch, list) or not batch:
            break
        items.extend(batch)
        if len(batch) < params.get("per_page", 100):
            break
        page += 1
    return items


def _fetch_published(wp) -> tuple[list[dict], dict[int, str]]:
    """Return (published posts, {category_id: name}) via paginated REST reads."""
    posts = _paginate(wp, "/wp/v2/posts", {
        "per_page": 100, "status": "publish",
        "_fields": "id,title,link,categories,date",
    })
    cats = {
        c["id"]: html.unescape(c.get("name", ""))
        for c in _paginate(wp, "/wp/v2/categories",
                           {"per_page": 100, "_fields": "id,name"})
    }
    return posts, cats


def _render_section(posts: list[dict], cats: dict[int, str], slug: str) -> str:
    lines = [
        SECTION_HEADER,
        "",
        f"_Auto-regenerated from WP REST (status=publish) — {len(posts)} live posts._",
        "_Do not hand-edit this section; run "
        f"`python -m scripts.wordpress.sync_links_map {slug}` to refresh._",
        "_Category names carry the content register — the linker must pick register-matched targets._",
        "",
    ]
    for p in sorted(posts, key=lambda x: x.get("date", ""), reverse=True):
        title = p.get("title")
        if isinstance(title, dict):
            title = title.get("rendered") or title.get("raw") or ""
        title = html.unescape(title or "").strip()
        # " · " not ", " — category names may themselves contain a comma
        # ("Porcelain, Explained"), and a comma separator made the list
        # unparseable for the linker's register matching.
        names = " · ".join(cats.get(cid, f"#{cid}") for cid in p.get("categories", []))
        lines.append(f"- [{p['id']}] {title}")
        lines.append(f"  - {p.get('link', '')}")
        if names:
            lines.append(f"  - categories: {names}")
    lines.append("")
    return "\n".join(lines)


def _splice(existing: str, new_section: str) -> str:
    """Replace the Published-articles section in-place; preserve everything else."""
    if SECTION_HEADER in existing:
        head, _, tail = existing.partition(SECTION_HEADER)
        rest = tail.split("\n## ", 1)
        trailer = ("## " + rest[1]) if len(rest) > 1 else ""
        joint = head.rstrip("\n") + "\n\n" + new_section
        if trailer:
            joint = joint.rstrip("\n") + "\n\n" + trailer
        return joint if joint.endswith("\n") else joint + "\n"
    base = existing.rstrip("\n") + "\n\n" if existing.strip() else ""
    return base + new_section


def sync_links_map(slug: str, *, dry_run: bool = False) -> dict:
    from scripts.wordpress.wp_client import WPClient

    map_path = internal_links_map_path(slug)
    with WPClient(slug) as wp:
        posts, cats = _fetch_published(wp)

    section = _render_section(posts, cats, slug)
    existing = map_path.read_text(encoding="utf-8") if map_path.exists() else (
        f"# {slug} — Internal Links Map\n"
    )
    merged = _splice(existing, section)

    if not dry_run:
        map_path.parent.mkdir(parents=True, exist_ok=True)
        map_path.write_text(merged, encoding="utf-8")

    return {
        "project": slug,
        "map_path": str(map_path),
        "published_posts": len(posts),
        "file_existed": map_path.exists(),
        "dry_run": dry_run,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Rebuild internal-links-map.md 'Published articles' from WP REST")
    ap.add_argument("slug")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        result = sync_links_map(args.slug, dry_run=args.dry_run)
    except Exception as e:  # credentials missing, site unreachable, ...
        print(f"sync_links_map failed for {args.slug}: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"✓ {args.slug}: {result['published_posts']} published posts → {result['map_path']}"
              + ("  (dry-run, not written)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
