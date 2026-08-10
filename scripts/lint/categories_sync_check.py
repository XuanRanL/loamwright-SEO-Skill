#!/usr/bin/env python3
"""Check sync between categories-config.json and WordPress live categories.

Usage:
    python -m scripts.lint.categories_sync_check --project-slug {slug} [--json]

Compares categories-config.json (editorial config with auto_select_signals)
against live WP categories (fetched via REST API). Reports:
- Categories in WP but missing from config (new WP cats without signals)
- Categories in config but missing from WP (stale config entries)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent


def _flatten_config_ids(categories: list[dict]) -> set[int]:
    ids: set[int] = set()
    for cat in categories:
        ids.add(cat["id"])
        for child in cat.get("children", []):
            ids.add(child["id"])
    return ids


def _flatten_config_map(categories: list[dict]) -> dict[int, str]:
    m: dict[int, str] = {}
    for cat in categories:
        m[cat["id"]] = cat["name"]
        for child in cat.get("children", []):
            m[child["id"]] = child["name"]
    return m


def check(project_slug: str) -> dict:
    config_path = PLUGIN_ROOT / "projects" / project_slug / "categories-config.json"
    if not config_path.exists():
        return {"passed": False, "error": f"categories-config.json not found for {project_slug}"}

    config = json.loads(config_path.read_text(encoding="utf-8"))
    config_ids = _flatten_config_ids(config.get("current_categories", []))
    config_map = _flatten_config_map(config.get("current_categories", []))

    cred_path = Path.home() / ".xuanran-seo" / "credentials" / "wordpress" / f"{project_slug}.json"
    if not cred_path.exists():
        cred_path = PLUGIN_ROOT / "projects" / project_slug / "credentials" / "wordpress.json"
    if not cred_path.exists():
        return {"passed": False, "error": "WordPress credentials not found"}

    creds = json.loads(cred_path.read_text(encoding="utf-8"))
    url = creds.get("url", creds.get("site_url", "")).rstrip("/")
    auth = (creds["username"], creds["app_password"])

    try:
        r = httpx.get(f"{url}/wp-json/wp/v2/categories", params={"per_page": 100}, auth=auth, timeout=30)
        r.raise_for_status()
        wp_cats = r.json()
    except Exception as e:
        return {"passed": False, "error": f"WP API error: {e}"}

    wp_ids = {c["id"] for c in wp_cats if c["id"] != 1}
    wp_map = {c["id"]: c["name"] for c in wp_cats}

    if len(wp_cats) >= 100:
        print("WARNING: WP returned 100 categories (page limit). Some may be missing.", file=sys.stderr)

    in_wp_not_config = wp_ids - config_ids
    in_config_not_wp = config_ids - wp_ids - {1}

    passed = len(in_wp_not_config) == 0 and len(in_config_not_wp) == 0

    return {
        "passed": passed,
        "project_slug": project_slug,
        "config_count": len(config_ids),
        "wp_count": len(wp_ids),
        "in_wp_missing_from_config": [
            {"id": cid, "name": wp_map.get(cid, "?")} for cid in sorted(in_wp_not_config)
        ],
        "in_config_missing_from_wp": [
            {"id": cid, "name": config_map.get(cid, "?")} for cid in sorted(in_config_not_wp)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-slug", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = check(args.project_slug)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result.get("error"):
            print(f"ERROR: {result['error']}")
            sys.exit(2)
        if result["passed"]:
            print(f"  [OK] categories-config.json in sync with WP ({result['config_count']} categories)")
        else:
            print(f"  [DRIFT] categories-config.json out of sync with WP")
            if result["in_wp_missing_from_config"]:
                print(f"  In WP but not in config ({len(result['in_wp_missing_from_config'])}):")
                for c in result["in_wp_missing_from_config"]:
                    print(f"    - ID {c['id']}: {c['name']}")
            if result["in_config_missing_from_wp"]:
                print(f"  In config but not in WP ({len(result['in_config_missing_from_wp'])}):")
                for c in result["in_config_missing_from_wp"]:
                    print(f"    - ID {c['id']}: {c['name']}")

    if not result.get("passed", False):
        sys.exit(1)


if __name__ == "__main__":
    main()
