"""scripts/wordpress/snapshot_categories.py — Cache live WP category structure to disk.

Pulls the project's WP category tree (id, name, slug, parent_id, description summary,
post count) and writes `projects/{slug}/categories-live.json`. This cache lets
category_selector + wp_publisher resolve name→ID lookups WITHOUT a WP round-trip per
publish (was: 1 GET per category per publish; now: 0).

Re-run quarterly OR after any category-config change OR when adding/removing categories
in WP admin.

USAGE
──────
    # Snapshot project-charlie → projects/project-charlie/categories-live.json
    python -m scripts.wordpress.snapshot_categories project-charlie

    # Dry-run (print only)
    python -m scripts.wordpress.snapshot_categories project-charlie --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

from scripts.wordpress.wp_client import WPClient

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def snapshot(site_slug: str, *, project_slug: str | None = None) -> dict:
    project_slug = project_slug or site_slug
    c = WPClient(site_slug)

    # Pull all categories
    cats: list[dict] = []
    for page in range(1, 10):
        r = c.get("/wp/v2/categories", params={
            "per_page": 100, "page": page,
            "_fields": "id,name,slug,parent,description,count",
            "orderby": "id", "order": "asc",
        })
        if not r.json_data:
            break
        cats.extend(r.json_data)
        if len(r.json_data) < 100:
            break

    # Build parent → children index for hierarchy navigation
    by_id: dict[int, dict] = {}
    for ct in cats:
        # Truncate description for snapshot (full text lives in WP)
        desc = (ct.get("description") or "").strip()
        if len(desc) > 280:
            desc = desc[:277] + "..."
        by_id[ct["id"]] = {
            "id": ct["id"],
            "name": unescape(ct["name"]),
            "slug": ct["slug"],
            "parent_id": ct.get("parent", 0),
            "description_summary": desc,
            "post_count": ct.get("count", 0),
        }
    # Backfill parent_slug for convenience
    for ct in by_id.values():
        pid = ct["parent_id"]
        ct["parent_slug"] = by_id[pid]["slug"] if pid in by_id else None

    # Build name → id and slug → id maps (the hot path for category_selector resolution)
    name_to_id = {ct["name"]: ct["id"] for ct in by_id.values()}
    slug_to_id = {ct["slug"]: ct["id"] for ct in by_id.values()}

    snapshot = {
        "$schema": "../../schemas/categories-live.schema.json",
        "project_slug": project_slug,
        "site_slug": site_slug,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "category_count": len(by_id),
        "categories_by_id": by_id,
        "name_to_id": name_to_id,
        "slug_to_id": slug_to_id,
        "_note": (
            "Cached snapshot of WP category taxonomy. Read by scripts/build/category_selector.py "
            "and scripts/wordpress/wp_publisher.py to resolve category names → WP IDs without "
            "a WP round-trip per publish. Regenerate via "
            "`python -m scripts.wordpress.snapshot_categories {site_slug}` after any WP-side "
            "category changes (rename, parent reassign, add, delete) or quarterly maintenance."
        ),
    }
    return snapshot


def write_snapshot(site_slug: str, *, project_slug: str | None = None) -> Path:
    """Fetch + PERSIST the snapshot to projects/{slug}/categories-live.json.

    ``snapshot()`` only *returns* the dict; callers that need the on-disk cache
    refreshed (dedupe_categories after a repair, ad-hoc maintenance) must use this —
    calling snapshot() alone silently refreshes nothing (2026-07-11 Rule-12 lesson).
    """
    snap = snapshot(site_slug, project_slug=project_slug)
    resolved_project = project_slug or site_slug
    out_path = PLUGIN_ROOT / "projects" / resolved_project / "categories-live.json"
    if not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("site_slug")
    ap.add_argument("--project-slug", help="Defaults to site_slug")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    snap = snapshot(args.site_slug, project_slug=args.project_slug)
    project_slug = args.project_slug or args.site_slug
    out_path = PLUGIN_ROOT / "projects" / project_slug / "categories-live.json"

    if args.dry_run:
        print(f"DRY-RUN: would write {out_path}")
        print(f"  {snap['category_count']} categories")
        print(f"  snapshot_at: {snap['snapshot_at']}")
        return 0

    if not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps({
            "snapshot_path": str(out_path),
            "category_count": snap["category_count"],
            "snapshot_at": snap["snapshot_at"],
        }, indent=2))
    else:
        print(f"✓ Wrote {out_path}")
        print(f"  {snap['category_count']} categories cached")
        print(f"  snapshot_at: {snap['snapshot_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
