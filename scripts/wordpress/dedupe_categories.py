"""scripts/wordpress/dedupe_categories.py — Detect + repair duplicate WP blog categories.

WHY THIS EXISTS
───────────────
Before v3.19.2 (2026-06-21) the publisher's name→term matching was not HTML-entity
aware: WordPress returns term names entity-encoded (``Ash &amp; Fur Keepsake Ideas``)
while callers pass literal ``&``. Every ``&``-bearing category name therefore missed,
fell through to create(), and minted a parentless TOP-LEVEL duplicate with a
name-derived slug (project-kilo orphans 351/352/…, project-hotel pairs 298/322 etc.).
The matching bug is fixed, and wp_publisher no longer creates categories at publish
time at all — but already-minted duplicates persist on live sites until repaired.

This tool is the standing detector + repairer for that damage class:

    # Detect only (exit 1 when duplicates exist — usable as a CI/lint gate)
    python -m scripts.wordpress.dedupe_categories <site_slug> --check [--json]

    # Full repair: backup → reassign posts → delete dups → emit redirect rules
    python -m scripts.wordpress.dedupe_categories <site_slug> --apply [--json]

Repair semantics (per duplicate group, canonical = config-listed term, else lowest id):
  1. Every post in a duplicate term is PATCHed to the canonical term (order-preserving
     swap + dedupe; ``rank_math_primary_category`` fixed when it pointed at the dup).
  2. The duplicate term is deleted (``?force=true``; WP re-parents nothing — posts were
     already moved; deleting a term never deletes posts).
  3. A 301 redirect rule ``/category/{dup-slug}/ → /category/{canonical-slug}/`` is
     written to ``projects/{slug}/.seo/category-dedupe-redirects-{date}.json`` for
     RankMath Redirections import (term archives 404 after deletion otherwise).
  4. A full pre-change backup (terms + affected posts) is written to
     ``projects/{slug}/.seo/category-dedupe-backup-{date}.json``.
  5. The project's local snapshot (categories-live.json / wp-taxonomy-cache.json) is
     refreshed via scripts.wordpress.snapshot_categories so category_selector and the
     publisher fast path see the repaired taxonomy.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


# ─── Pure planning core (unit-tested; no I/O) ────────────────────────────────


def _norm_name(s: str) -> str:
    """HTML-unescape + collapse whitespace + lowercase (mirror wp_taxonomy._norm_name)."""
    return " ".join(html.unescape(s).split()).lower()


def find_duplicate_groups(terms: list[dict]) -> dict[str, list[dict]]:
    """Group raw REST term dicts by normalized name; keep only groups of 2+.

    Returns {normalized_name: [terms sorted by id ascending]}.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in terms:
        groups[_norm_name(t["name"])].append(t)
    return {
        k: sorted(v, key=lambda t: t["id"])
        for k, v in groups.items()
        if len(v) > 1
    }


def choose_canonical(group: list[dict], config_ids: set[int]) -> dict:
    """Pick the canonical term of a duplicate group.

    Preference: (1) term listed in the project's categories-config.json — the curated
    taxonomy is authoritative; (2) lowest id (created first). A stray duplicate is
    always the LATER, non-curated term.
    """
    in_config = [t for t in group if t["id"] in config_ids]
    pool = in_config or group
    return min(pool, key=lambda t: t["id"])


def build_mapping(groups: dict[str, list[dict]], config_ids: set[int]) -> dict[int, int]:
    """{duplicate_id: canonical_id} across all groups."""
    mapping: dict[int, int] = {}
    for group in groups.values():
        canonical = choose_canonical(group, config_ids)
        for t in group:
            if t["id"] != canonical["id"]:
                mapping[t["id"]] = canonical["id"]
    return mapping


def plan_post_updates(posts: list[dict], mapping: dict[int, int]) -> list[dict]:
    """Compute per-post category swaps. Only posts touching a duplicate get a plan.

    Swap preserves order, drops the id that would repeat after the swap (post already
    in the canonical term), and fixes rank_math_primary_category when it pointed at a
    duplicate. ``new_primary`` is None when no primary fix is needed.
    """
    plans: list[dict] = []
    for post in posts:
        old = list(post.get("categories") or [])
        if not any(cid in mapping for cid in old):
            continue
        new: list[int] = []
        for cid in old:
            target = mapping.get(cid, cid)
            if target not in new:
                new.append(target)
        meta = post.get("meta") or {}
        primary = meta.get("rank_math_primary_category")
        new_primary = mapping.get(primary) if isinstance(primary, int) and primary in mapping else None
        plans.append({
            "post_id": post["id"],
            "old_categories": old,
            "new_categories": new,
            "new_primary": new_primary,
        })
    return plans


def build_redirect_rules(
    groups: dict[str, list[dict]], mapping: dict[int, int], base_url: str,
) -> list[dict]:
    """301 rules for every deleted duplicate's term archive."""
    slug_by_id = {t["id"]: t["slug"] for g in groups.values() for t in g}
    base = base_url.rstrip("/")
    rules = []
    for dup_id, canon_id in sorted(mapping.items()):
        rules.append({
            "from_slug": slug_by_id[dup_id],
            "to_slug": slug_by_id[canon_id],
            "from_url": f"{base}/category/{slug_by_id[dup_id]}/",
            "to_url": f"{base}/category/{slug_by_id[canon_id]}/",
            "status": 301,
        })
    return rules


# ─── I/O shell ────────────────────────────────────────────────────────────────


def _load_config_ids(project_slug: str) -> set[int]:
    cfg = PLUGIN_ROOT / "projects" / project_slug / "categories-config.json"
    if not cfg.exists():
        return set()
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except Exception:
        return set()
    ids: set[int] = set()

    def _walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("id"), int):
                ids.add(node["id"])
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(data)
    return ids


def _fetch_all(client, path: str, extra: str = "") -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        r = client.get(f"{path}?per_page=100&page={page}&orderby=id&order=asc{extra}")
        if r.status != 200 or not isinstance(r.json_data, list):
            break
        items.extend(r.json_data)
        if len(r.json_data) < 100:
            break
        page += 1
    return items


def run(site_slug: str, *, apply: bool = False, as_json: bool = False) -> int:
    from scripts.wordpress.wp_client import WPClient

    report: dict = {"site_slug": site_slug, "apply": apply}
    with WPClient(site_slug) as wp:
        terms = _fetch_all(wp, "/wp/v2/categories")
        groups = find_duplicate_groups(terms)
        config_ids = _load_config_ids(site_slug)
        mapping = build_mapping(groups, config_ids)
        report["total_categories"] = len(terms)
        report["duplicate_groups"] = {
            name: [{k: t.get(k) for k in ("id", "slug", "parent", "count")} for t in g]
            for name, g in groups.items()
        }
        report["mapping"] = {str(k): v for k, v in mapping.items()}

        if not groups:
            report["result"] = "clean"
            _emit(report, as_json, "✓ No duplicate categories found "
                                   f"({len(terms)} categories scanned).")
            return 0

        # Affected posts: every post assigned to any duplicate term (all statuses).
        dup_ids_csv = ",".join(str(i) for i in mapping)
        posts = _fetch_all(
            wp, "/wp/v2/posts",
            extra=f"&categories={dup_ids_csv}&status=publish,draft,future,pending,private"
                  f"&context=edit&_fields=id,slug,status,categories,meta",
        )
        plans = plan_post_updates(posts, mapping)
        base_url = getattr(wp, "site_url", "") or ""
        if not base_url:
            creds = PLUGIN_ROOT / "projects" / site_slug / "credentials" / "wordpress.json"
            if creds.exists():
                base_url = json.loads(creds.read_text(encoding="utf-8")).get("site_url", "")
        redirects = build_redirect_rules(groups, mapping, base_url)
        report["affected_posts"] = plans
        report["redirects"] = redirects

        if not apply:
            report["result"] = "duplicates_found"
            _emit(report, as_json,
                  f"✗ {len(groups)} duplicate group(s), {len(mapping)} stray term(s), "
                  f"{len(plans)} post(s) to reassign. Run with --apply to repair.")
            return 1

        # ── APPLY ────────────────────────────────────────────
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        seo_dir = PLUGIN_ROOT / "projects" / site_slug / ".seo"
        seo_dir.mkdir(parents=True, exist_ok=True)
        backup_path = seo_dir / f"category-dedupe-backup-{stamp}.json"
        backup_path.write_text(json.dumps({
            "terms": terms, "posts": posts, "mapping": report["mapping"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        report["backup"] = str(backup_path)

        patched, patch_fails = [], []
        for plan in plans:
            body: dict = {"categories": plan["new_categories"]}
            if plan["new_primary"] is not None:
                body["meta"] = {"rank_math_primary_category": plan["new_primary"]}
            r = wp.post(f"/wp/v2/posts/{plan['post_id']}", json_body=body)
            (patched if r.status == 200 else patch_fails).append(plan["post_id"])
        report["posts_patched"] = patched
        report["posts_failed"] = patch_fails

        deleted, delete_fails = [], []
        if not patch_fails:
            for dup_id in sorted(mapping):
                r = wp.delete(f"/wp/v2/categories/{dup_id}?force=true")
                (deleted if r.status in (200, 410) else delete_fails).append(dup_id)
        else:
            report["note"] = "term deletion skipped — post reassignment had failures"
        report["terms_deleted"] = deleted
        report["terms_failed"] = delete_fails

        redirects_path = seo_dir / f"category-dedupe-redirects-{stamp}.json"
        redirects_path.write_text(
            json.dumps(redirects, indent=2, ensure_ascii=False), encoding="utf-8")
        report["redirects_file"] = str(redirects_path)

        try:
            from scripts.wordpress.snapshot_categories import write_snapshot
            snap_path = write_snapshot(site_slug)
            report["snapshot_refreshed"] = True
            report["snapshot_path"] = str(snap_path)
        except Exception as e:  # snapshot refresh is best-effort, never blocks repair
            report["snapshot_refreshed"] = False
            report["snapshot_error"] = str(e)[:200]

        ok = not patch_fails and not delete_fails
        report["result"] = "repaired" if ok else "partial"
        _emit(report, as_json,
              f"{'✓' if ok else '⚠'} Repair {'complete' if ok else 'PARTIAL'}: "
              f"{len(patched)} post(s) reassigned, {len(deleted)} duplicate term(s) deleted, "
              f"{len(redirects)} redirect rule(s) → {redirects_path.name}. Backup: {backup_path.name}")
        return 0 if ok else 1


def _emit(report: dict, as_json: bool, human_line: str) -> None:
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(human_line)
        for name, g in (report.get("duplicate_groups") or {}).items():
            ts = "  ".join(f"[{t['id']} {t['slug']} p={t['parent']} n={t['count']}]" for t in g)
            print(f"  {name!r}: {ts}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("site_slug")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="detect only; exit 1 if duplicates exist")
    mode.add_argument("--apply", action="store_true", help="backup + reassign posts + delete dups + emit redirects")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    return run(args.site_slug, apply=args.apply, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
