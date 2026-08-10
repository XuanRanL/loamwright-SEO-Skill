"""scripts/wordpress/setup_categories.py — Create or update WordPress categories
from projects/{slug}/categories-config.json.

Idempotent: re-runnable safely. On each run:
  1. Read categories-config.json
  2. For each category in order (top-level first):
     - Look up by slug. If exists → PATCH name/description/parent.
       If not → POST new category.
     - PATCH the meta block (rank_math_*) if MU plugin v1.1+ is installed.
       Otherwise skip with a warning (description still set; other meta deferred).
  3. Print summary: created / updated / failed / meta-deferred.

Usage:
    python -m scripts.wordpress.setup_categories project-charlie
    python -m scripts.wordpress.setup_categories project-charlie --dry-run
    python -m scripts.wordpress.setup_categories project-charlie --skip-meta
    python -m scripts.wordpress.setup_categories project-charlie --only=lighting
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.wordpress.wp_client import WPClient


def load_config(site_slug: str) -> dict:
    path = ROOT / "projects" / site_slug / "categories-config.json"
    if not path.exists():
        raise FileNotFoundError(f"No categories config at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_existing_categories(wp: WPClient) -> dict[str, dict]:
    """Return slug -> category-dict map. Paginates if >100 categories."""
    out: dict[str, dict] = {}
    page = 1
    while True:
        r = wp.get("/wp/v2/categories", params={"per_page": 100, "page": page, "context": "edit"})
        data = r.json_data
        if not isinstance(data, list) or not data:
            break
        for c in data:
            out[c["slug"]] = c
        if len(data) < 100:
            break
        page += 1
        if page > 20:
            break
    return out


def check_term_meta_writable(wp: WPClient) -> bool:
    """Probe whether term meta is registered (MU plugin v1.1+)."""
    try:
        # Try to fetch the bridge health endpoint
        r = wp.get("/xuanran/v1/rank-math-bridge")
        data = r.json_data
        ver = (data or {}).get("bridge_version", "1.0.0")
        # Version 1.1.0+ has term meta support
        parts = ver.split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        return (major, minor) >= (1, 1)
    except Exception as e:
        # Audit 2026-05-22 P1 — log silent-fallback
        print(
            f"⚠ bridge_version check failed: {type(e).__name__}: {e} — "
            f"assuming term meta not supported (1.1.0+ required)",
            file=sys.stderr,
        )
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site_slug")
    ap.add_argument("--dry-run", action="store_true", help="Show planned changes without executing")
    ap.add_argument("--skip-meta", action="store_true", help="Don't attempt RankMath meta PATCH")
    ap.add_argument("--only", default=None, help="Only operate on this slug prefix (e.g. 'lighting' = lighting + lighting-*)")
    args = ap.parse_args()

    config = load_config(args.site_slug)
    cat_specs = config["categories"]
    if args.only:
        cat_specs = [c for c in cat_specs if c["slug"] == args.only or c["slug"].startswith(args.only + "-")]
        print(f"Filtered to {len(cat_specs)} categories matching '{args.only}*'")

    wp = WPClient(site_slug=args.site_slug)
    existing = get_existing_categories(wp)
    print(f"Existing categories on site: {len(existing)}")

    term_meta_writable = check_term_meta_writable(wp)
    if not args.skip_meta:
        print(f"MU plugin term-meta support: {'YES (v1.1+)' if term_meta_writable else 'NO (v1.0 — meta PATCH will silently no-op until plugin is upgraded)'}")

    slug_to_id: dict[str, int] = {c["slug"]: c["id"] for c in existing.values()}
    # Pre-fill with already-existing categories (e.g. "uncategorized")

    # Sort: top-level (parent=null) first, then subcategories
    cat_specs.sort(key=lambda c: (0 if c["parent"] is None else 1, c["slug"]))

    summary = {
        "created": [], "updated": [], "failed": [], "meta_set": [], "meta_deferred": [],
    }

    for spec in cat_specs:
        slug = spec["slug"]
        name = spec["name"]
        description = spec["description"]
        parent_slug = spec.get("parent")
        parent_id = 0 if parent_slug is None else slug_to_id.get(parent_slug, 0)
        if parent_slug and parent_id == 0:
            print(f"  WARN: parent '{parent_slug}' not yet known for '{slug}' — skip")
            summary["failed"].append((slug, "parent not found"))
            continue

        payload = {
            "name": name,
            "slug": slug,
            "description": description,
            "parent": parent_id,
        }

        if slug in slug_to_id:
            # Update existing
            cat_id = slug_to_id[slug]
            print(f"  UPDATE [{slug}] id={cat_id}  parent={parent_id}  desc={len(description)} chars")
            if not args.dry_run:
                try:
                    r = wp.post(f"/wp/v2/categories/{cat_id}", json_body=payload)
                    if r.status == 200:
                        summary["updated"].append(slug)
                    else:
                        summary["failed"].append((slug, f"status={r.status}"))
                except Exception as e:
                    print(f"    FAIL: {e}")
                    summary["failed"].append((slug, str(e)))
                    continue
        else:
            # Create new
            print(f"  CREATE [{slug}]  parent={parent_id}  desc={len(description)} chars")
            if not args.dry_run:
                try:
                    r = wp.post("/wp/v2/categories", json_body=payload)
                    cat_id = r.json_data["id"]
                    slug_to_id[slug] = cat_id
                    summary["created"].append((slug, cat_id))
                except Exception as e:
                    print(f"    FAIL: {e}")
                    summary["failed"].append((slug, str(e)))
                    continue

        # Set RankMath meta if supported
        if args.skip_meta:
            summary["meta_deferred"].append(slug)
            continue
        if not term_meta_writable:
            summary["meta_deferred"].append(slug)
            continue
        if args.dry_run:
            summary["meta_deferred"].append(slug)
            continue
        if slug not in slug_to_id:
            # Dry-run create or failed create; can't set meta
            summary["meta_deferred"].append(slug)
            continue

        cat_id = slug_to_id[slug]
        meta_payload = {
            k: spec[k] for k in [
                "rank_math_title", "rank_math_description", "rank_math_focus_keyword",
                "rank_math_robots", "rank_math_facebook_title", "rank_math_facebook_description",
                "rank_math_twitter_card_type", "rank_math_twitter_title", "rank_math_twitter_description",
            ] if k in spec
        }
        if not args.dry_run:
            try:
                rm = wp.post(f"/wp/v2/categories/{cat_id}", json_body={"meta": meta_payload})
                # Verify the meta actually persisted
                vr = wp.get(f"/wp/v2/categories/{cat_id}", params={"context": "edit"})
                stored_meta = vr.json_data.get("meta", {})
                if isinstance(stored_meta, dict) and stored_meta.get("rank_math_title") == meta_payload["rank_math_title"]:
                    summary["meta_set"].append(slug)
                else:
                    summary["meta_deferred"].append(slug)
                    print(f"    META silent-fail: returned meta={type(stored_meta).__name__}")
            except Exception as e:
                print(f"    META FAIL: {e}")
                summary["meta_deferred"].append(slug)

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Created   : {len(summary['created'])}  {[s for s, _ in summary['created']]}")
    print(f"  Updated   : {len(summary['updated'])}  {summary['updated']}")
    print(f"  Failed    : {len(summary['failed'])}  {summary['failed']}")
    print(f"  Meta set  : {len(summary['meta_set'])}  (RankMath term meta persisted)")
    print(f"  Meta deferred: {len(summary['meta_deferred'])}  (description set; rank_math_* meta NOT writable until MU plugin v1.1+ deployed)")
    if summary["meta_deferred"] and not term_meta_writable:
        print()
        print("⚠️  To enable RankMath term meta for category SEO titles, focus keywords,")
        print("    and OG/Twitter overrides, deploy the updated MU plugin:")
        print("    install/wordpress-mu-plugin/xuanran-rank-math-rest-bridge.php")
        print("    → wp-content/mu-plugins/ on the WordPress server.")
        print("    Then re-run: python -m scripts.wordpress.setup_categories project-charlie")


if __name__ == "__main__":
    main()
