"""scripts/wordpress/setup_tags.py — Apply projects/{slug}/tags-config.json
to a WordPress site's `post_tag` taxonomy.

Operations (in order):
  1. For each merge_from_slug → re-tag posts from legacy tag to canonical tag,
     then delete the legacy tag
  2. For each strategic_tag → create or update (name, slug, description) + RankMath meta
  3. For each noindex_tag → create or update (name, slug) + rank_math_robots=["noindex"]
  4. For each delete_tags entry → delete from live site (if it still has 0 posts)
  5. Print summary

Idempotent: re-runnable safely. Also called by wp_publisher.py on every article
publish to ensure newly-created tags get the right SEO meta.

Usage:
    python -m scripts.wordpress.setup_tags project-charlie
    python -m scripts.wordpress.setup_tags project-charlie --dry-run
    python -m scripts.wordpress.setup_tags project-charlie --skip-merges
    python -m scripts.wordpress.setup_tags project-charlie --skip-deletes
    python -m scripts.wordpress.setup_tags project-charlie --only-tag=1000w
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.wordpress.wp_client import WPClient


def load_config(site_slug: str) -> dict:
    path = ROOT / "projects" / site_slug / "tags-config.json"
    if not path.exists():
        raise FileNotFoundError(f"No tags config at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_all_tags(wp: WPClient) -> dict[str, dict]:
    out: dict[str, dict] = {}
    page = 1
    while True:
        r = wp.get("/wp/v2/tags", params={"per_page": 100, "page": page, "context": "edit"})
        if not isinstance(r.json_data, list) or not r.json_data:
            break
        for t in r.json_data:
            out[t["slug"]] = t
        if len(r.json_data) < 100:
            break
        page += 1
        if page > 20:
            break
    return out


def check_term_meta_writable(wp: WPClient) -> tuple[bool, str]:
    try:
        r = wp.get("/xuanran/v1/rank-math-bridge")
        ver = (r.json_data or {}).get("bridge_version", "1.0.0")
        parts = [int(x) for x in ver.split(".")]
        while len(parts) < 3:
            parts.append(0)
        return (tuple(parts) >= (1, 2, 0), ver)
    except Exception:
        return (False, "absent")


def posts_for_tag(wp: WPClient, tag_id: int) -> list[int]:
    """Return list of post IDs that have this tag."""
    out = []
    page = 1
    while True:
        r = wp.get("/wp/v2/posts", params={"tags": tag_id, "per_page": 100, "page": page, "context": "edit", "status": "any"})
        if not isinstance(r.json_data, list) or not r.json_data:
            break
        for p in r.json_data:
            out.append(p["id"])
        if len(r.json_data) < 100:
            break
        page += 1
        if page > 50:
            break
    return out


def retag_post(wp: WPClient, post_id: int, remove_tag_ids: list[int], add_tag_id: int) -> None:
    """Replace remove_tag_ids on a post with add_tag_id. Preserves all other tags.
    Pass add_tag_id=0 to drop the tag without replacement."""
    pr = wp.get(f"/wp/v2/posts/{post_id}", params={"context": "edit"})
    current = set(pr.json_data.get("tags", []) or [])
    new = current - set(remove_tag_ids)
    if add_tag_id:
        new = new | {add_tag_id}
    if new == current:
        return  # no change
    wp.post(f"/wp/v2/posts/{post_id}", json_body={"tags": sorted(new)})


def apply_meta(wp: WPClient, tag_id: int, spec: dict, term_meta_writable: bool) -> str:
    """Apply RankMath meta to a tag. Returns 'set' or 'deferred'."""
    if not term_meta_writable:
        return "deferred"
    meta_keys = [
        "rank_math_title", "rank_math_description", "rank_math_focus_keyword",
        "rank_math_robots", "rank_math_facebook_title", "rank_math_facebook_description",
        "rank_math_twitter_card_type", "rank_math_twitter_title", "rank_math_twitter_description",
    ]
    meta_payload = {k: spec[k] for k in meta_keys if k in spec}
    if not meta_payload:
        return "skipped"
    wp.post(f"/wp/v2/tags/{tag_id}", json_body={"meta": meta_payload})
    return "set"


def create_or_update_tag(
    wp: WPClient,
    spec: dict,
    existing_by_slug: dict[str, dict],
    term_meta_writable: bool,
    dry_run: bool,
) -> tuple[str, int | None, str]:
    slug = spec["slug"]
    payload = {
        "slug": slug,
        "name": spec["name"],
    }
    if "description" in spec:
        payload["description"] = spec["description"]

    if slug in existing_by_slug:
        tag_id = existing_by_slug[slug]["id"]
        action = "UPDATE"
        if not dry_run:
            wp.post(f"/wp/v2/tags/{tag_id}", json_body=payload)
    else:
        action = "CREATE"
        if dry_run:
            tag_id = None
        else:
            r = wp.post("/wp/v2/tags", json_body=payload)
            tag_id = r.json_data["id"]
            existing_by_slug[slug] = r.json_data

    if dry_run or tag_id is None:
        return (action, tag_id, "dry-run")

    meta_status = apply_meta(wp, tag_id, spec, term_meta_writable)
    return (action, tag_id, meta_status)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site_slug")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-merges", action="store_true")
    ap.add_argument("--skip-deletes", action="store_true")
    ap.add_argument("--only-tag", default=None)
    args = ap.parse_args()

    config = load_config(args.site_slug)
    wp = WPClient(site_slug=args.site_slug)

    term_meta_writable, mu_ver = check_term_meta_writable(wp)
    print(f"MU plugin: v{mu_ver}  term_meta_writable_for_post_tag={term_meta_writable}")
    if not term_meta_writable:
        print(f"  WARNING: MU plugin needs v1.2+ for tag meta to persist.")
        print(f"  Descriptions + slugs will still apply; rank_math_* will be deferred.")
        print(f"  After redeploying install/wordpress-mu-plugin/xuanran-rank-math-rest-bridge.php,")
        print(f"  re-run: python -m scripts.wordpress.setup_tags {args.site_slug}")
        print()

    existing = fetch_all_tags(wp)
    print(f"Existing tags on site: {len(existing)}")

    summary = {"created": [], "updated": [], "merged": [], "deleted": [], "meta_set": [], "meta_deferred": [], "errors": []}

    # ── 1. Process merges (strategic + noindex) ────────────────────
    if not args.skip_merges:
        all_with_merges = [t for t in config.get("strategic_tags", []) + config.get("baseline_tags", []) if "merge_from_slugs" in t]
        for spec in all_with_merges:
            target_slug = spec["slug"]
            if args.only_tag and target_slug != args.only_tag:
                continue
            # Ensure target exists first (create if needed)
            if target_slug not in existing:
                if args.dry_run:
                    print(f"  [merge-prep] would create target tag '{target_slug}' first")
                    continue
                action, tag_id, meta_status = create_or_update_tag(wp, spec, existing, term_meta_writable, args.dry_run)
                print(f"  [merge-prep] {action} target '{target_slug}' id={tag_id} meta={meta_status}")
                if action == "CREATE":
                    summary["created"].append(target_slug)
                elif action == "UPDATE":
                    summary["updated"].append(target_slug)
            target_id = existing[target_slug]["id"] if target_slug in existing else None
            if target_id is None:
                continue
            # For each legacy slug, retag posts then delete the legacy tag
            for legacy_slug in spec.get("merge_from_slugs", []):
                if legacy_slug not in existing:
                    continue
                legacy_id = existing[legacy_slug]["id"]
                posts = posts_for_tag(wp, legacy_id)
                print(f"  [merge] '{legacy_slug}' (id={legacy_id}) → '{target_slug}' (id={target_id}) — {len(posts)} posts to retag")
                if args.dry_run:
                    continue
                for pid in posts:
                    retag_post(wp, pid, remove_tag_ids=[legacy_id], add_tag_id=target_id)
                # Delete the legacy tag
                try:
                    wp.delete(f"/wp/v2/tags/{legacy_id}", params={"force": "true"})
                    del existing[legacy_slug]
                    summary["merged"].append((legacy_slug, target_slug, len(posts)))
                except Exception as e:
                    summary["errors"].append((legacy_slug, f"merge-delete failed: {e}"))

    # ── 2. Strategic tags (create + index + full meta) ────────────
    print()
    print("=== Strategic tags (indexed, full SEO meta) ===")
    for spec in config.get("strategic_tags", []):
        slug = spec["slug"]
        if args.only_tag and slug != args.only_tag:
            continue
        try:
            action, tag_id, meta_status = create_or_update_tag(wp, spec, existing, term_meta_writable, args.dry_run)
            desc_words = len(spec.get("description", "").split())
            print(f"  {action} [{tag_id or '???'}] {slug:30s}  desc={desc_words}w  meta={meta_status}")
            if action == "CREATE":
                summary["created"].append(slug)
            else:
                summary["updated"].append(slug)
            if meta_status == "set":
                summary["meta_set"].append(slug)
            elif meta_status == "deferred":
                summary["meta_deferred"].append(slug)
        except Exception as e:
            print(f"  ERROR [{slug}]: {e}")
            summary["errors"].append((slug, str(e)))

    # ── 3. Baseline tags (auto-create with minimal meta) ───────────
    print()
    print("=== Baseline tags (axis-classified, auto-templated description, indexed) ===")
    default_desc_template = config["policy"].get("auto_create_default_meta", {}).get("description_template", "{name} content on this site.")
    policy_robots = config["policy"].get("default_robots", ["index"])
    for spec in config.get("baseline_tags", []):
        slug = spec["slug"]
        if args.only_tag and slug != args.only_tag:
            continue
        # Per-tag curated description preferred; fall back to template only if absent.
        # The template should be rare — every baseline_tags entry should carry a
        # unique axis-aware description per the category-description-style-guide.md
        # pattern (avoid "Articles tagged X on..." tautology).
        description = spec.get("description") or default_desc_template.format(name=spec["name"])
        full_spec = {
            "slug": slug,
            "name": spec["name"],
            "description": description,
            "rank_math_robots": spec.get("rank_math_robots", policy_robots),
        }
        # Baseline entries MAY carry curated full RankMath meta (loamwright 2026-07-06
        # pattern) — the strategic/baseline split is editorial investment, not capability.
        # Without this pass-through the curated keys were silently dropped.
        for opt_key in (
            "rank_math_title", "rank_math_description", "rank_math_focus_keyword",
            "rank_math_twitter_card_type",
        ):
            if spec.get(opt_key):
                full_spec[opt_key] = spec[opt_key]
        if "merge_from_slugs" in spec:
            full_spec["merge_from_slugs"] = spec["merge_from_slugs"]
        try:
            action, tag_id, meta_status = create_or_update_tag(wp, full_spec, existing, term_meta_writable, args.dry_run)
            robots_str = ",".join(full_spec["rank_math_robots"])
            print(f"  {action} [{tag_id or '???'}] {slug:35s} ({robots_str}) meta={meta_status}")
            if action == "CREATE":
                summary["created"].append(slug)
            else:
                summary["updated"].append(slug)
        except Exception as e:
            print(f"  ERROR [{slug}]: {e}")
            summary["errors"].append((slug, str(e)))

    # ── 4. Delete orphan tags ──────────────────────────────────────
    if not args.skip_deletes:
        print()
        print("=== Delete orphan tags ===")
        for entry in config.get("delete_tags", []):
            slug = entry["slug"]
            if args.only_tag and slug != args.only_tag:
                continue
            if slug not in existing:
                print(f"  SKIP {slug} (not on site)")
                continue
            tag_id = existing[slug]["id"]
            count = existing[slug].get("count", 0)
            force_remove = entry.get("force_remove_from_posts", False)
            if count > 0 and not force_remove:
                print(f"  SKIP {slug} (count={count} — has posts; set force_remove_from_posts=true to retag and delete)")
                continue
            if args.dry_run:
                action = "would DELETE"
                if count > 0:
                    action += f" (after retagging {count} posts to remove this tag)"
                print(f"  {action} {slug} (id={tag_id}, count={count}) reason: {entry.get('reason','')}")
                continue
            # If has posts and force_remove, retag posts to drop this tag
            if count > 0 and force_remove:
                posts = posts_for_tag(wp, tag_id)
                print(f"  RETAG {len(posts)} posts to remove '{slug}' before deleting...")
                for pid in posts:
                    retag_post(wp, pid, remove_tag_ids=[tag_id], add_tag_id=0)  # add_tag_id=0 means "no replacement"
            try:
                wp.delete(f"/wp/v2/tags/{tag_id}", params={"force": "true"})
                summary["deleted"].append((slug, entry.get("reason", "")))
                print(f"  DELETED {slug} (id={tag_id})  reason: {entry.get('reason','')}")
            except Exception as e:
                print(f"  ERROR delete {slug}: {e}")
                summary["errors"].append((slug, f"delete failed: {e}"))

    # ── Summary ─────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Created   : {len(summary['created'])}  {summary['created']}")
    print(f"  Updated   : {len(summary['updated'])}")
    print(f"  Merged    : {len(summary['merged'])}  {summary['merged']}")
    print(f"  Deleted   : {len(summary['deleted'])}  {[s for s, _ in summary['deleted']]}")
    print(f"  Meta set  : {len(summary['meta_set'])}  (RankMath term meta persisted on strategic tags)")
    print(f"  Meta deferred: {len(summary['meta_deferred'])}  (description + slug set; rank_math_* requires MU plugin v1.2+)")
    if summary["errors"]:
        print(f"  Errors    : {len(summary['errors'])}  {summary['errors']}")


if __name__ == "__main__":
    main()
