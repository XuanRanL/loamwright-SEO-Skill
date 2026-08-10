"""scripts/wordpress/audit_post_categories.py — Audit every WP post's categories vs category_selector recommendation.

For each post on the site:
  1. Fetch live body HTML + title from WP REST
  2. Strip HTML tags to plain text body
  3. Run category_selector signals against (title, body, slug-derived format hint)
  4. Compare recommendation vs current categories
  5. Optionally PATCH posts where categories differ

USAGE
──────
    # Audit only (no PATCH)
    python -m scripts.wordpress.audit_post_categories <site_slug> --json

    # Audit + auto-PATCH everything that differs
    python -m scripts.wordpress.audit_post_categories <site_slug> --apply

    # Audit a specific post by ID
    python -m scripts.wordpress.audit_post_categories <site_slug> --post-id 37368 --apply

The PATCH preserves post status (publish stays publish, draft stays draft).
Categories are SET (not appended) — the recommendation IS the final state.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html import unescape
from pathlib import Path

from scripts._core import file_bus
from scripts.wordpress.wp_client import WPClient
from scripts.build.category_selector import (
    _SIGNAL_WEIGHTS, _count_product_h3s, _normalize_body,
    _eval_format_id_match, _eval_product_h3_min,
    _eval_body_keywords_any, _eval_body_keywords_all,
    _eval_title_keywords_any,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def _strip_html(html: str) -> str:
    """Strip tags + decode entities → plain text body for keyword matching."""
    # Remove script/style blocks entirely
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    # Replace tags with space (so adjacent words don't merge)
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _infer_format_id_from_post(title: str, body: str, slug: str) -> str:
    """Reverse-engineer format_id from observable signals when no angle.json exists."""
    t = title.lower()
    if t.startswith("best ") or "best " in t.split(":")[0].lower():
        return "listicle"
    if "vs " in t.lower() or " vs. " in t.lower():
        return "comparison"
    if t.startswith("how to ") or " how to " in t.lower():
        return "how-to-guide"
    # Default for project-charlie long-form content
    if _count_product_h3s(body) >= 3:
        return "listicle"  # likely product roundup
    return "pillar-page"


def audit_post(
    site_slug: str,
    post_id: int,
    *,
    project_slug: str | None = None,
    apply: bool = False,
) -> dict:
    """Audit one post; optionally PATCH categories if recommendation differs."""
    c = WPClient(site_slug)
    project_slug = project_slug or site_slug

    # Fetch post
    r = c.get(f"/wp/v2/posts/{post_id}", params={
        "_fields": "id,title,slug,content,status,categories",
        "context": "edit",
    })
    post = r.json_data
    title = unescape(post["title"].get("rendered", "")) or unescape(post["title"].get("raw", ""))
    slug = post["slug"]
    body_html = post["content"].get("rendered") or post["content"].get("raw", "")
    body_text = _strip_html(body_html)
    current_cat_ids = post.get("categories", [])
    status = post.get("status", "unknown")

    # Load project's categories-config + name→ID map (live from WP)
    cc_path = PLUGIN_ROOT / "projects" / project_slug / "categories-config.json"
    bc_path = PLUGIN_ROOT / "projects" / project_slug / "business-context.json"
    categories_config = []
    default_categories = []
    project_max_categories = 3  # default
    if cc_path.exists():
        cc = json.loads(cc_path.read_text(encoding="utf-8"))
        categories_config = cc.get("categories", [])
    if bc_path.exists():
        bc = json.loads(bc_path.read_text(encoding="utf-8"))
        default_categories = bc.get("wordpress", {}).get("default_categories", [])
        cp = bc.get("category_policy", {})
        if isinstance(cp.get("max_per_article"), int):
            project_max_categories = cp["max_per_article"]

    # Live WP category map (id ↔ name)
    wp_cats = {}
    for page in range(1, 5):
        rr = c.get("/wp/v2/categories", params={
            "per_page": 100, "page": page, "_fields": "id,name,slug,parent",
        })
        if not rr.json_data:
            break
        for ct in rr.json_data:
            wp_cats[ct["id"]] = {"name": unescape(ct["name"]), "slug": ct["slug"]}
        if len(rr.json_data) < 100:
            break
    name_to_id = {v["name"]: cid for cid, v in wp_cats.items()}
    # Some WP names have HTML entities (& → &amp;) — normalize both ways
    name_to_id_normalized = {unescape(name): cid for name, cid in name_to_id.items()}
    name_to_id = {**name_to_id, **name_to_id_normalized}

    # Build pseudo-angle for the format_id_match signal
    fake_angle = {"format_id": _infer_format_id_from_post(title, body_text, slug)}
    body_lower = body_text.lower()
    title_lower = title.lower()

    # ── Evaluate signals (mirrors category_selector.select_categories Step 2)
    recommended: list[dict] = []
    seen_slugs: set[str] = set()
    rejected: list[dict] = []

    # Defaults always included
    for default_name in default_categories:
        cat_slug = None
        for c2 in categories_config:
            if c2.get("name") == default_name:
                cat_slug = c2.get("slug")
                break
        if cat_slug and cat_slug not in seen_slugs:
            recommended.append({"name": default_name, "slug": cat_slug, "reason": "project default", "score": 0.0})
            seen_slugs.add(cat_slug)

    # Signal-matched
    candidates: list[dict] = []
    for cat in categories_config:
        slug_c = cat.get("slug")
        name = cat.get("name")
        signals = cat.get("auto_select_signals")
        if not signals or not slug_c or not name:
            continue
        if slug_c in seen_slugs:
            continue
        trigger_logic = (signals.get("trigger_logic") or "any").lower()
        evals = [
            ("format_id_match", _eval_format_id_match(signals, fake_angle)),
            ("product_h3_min", _eval_product_h3_min(signals, body_lower, body_text)),
            ("body_keywords_any", _eval_body_keywords_any(signals, body_lower)),
            ("body_keywords_all", _eval_body_keywords_all(signals, body_lower)),
            ("title_keywords_any", _eval_title_keywords_any(signals, title_lower)),
        ]
        non_vacuous = [(sig, ok, msg, cnt) for sig, (ok, msg, cnt) in evals if msg]
        if not non_vacuous:
            continue
        matched = [(sig, msg, cnt) for sig, ok, msg, cnt in non_vacuous if ok]
        failed = [(sig, msg) for sig, ok, msg, _ in non_vacuous if not ok]
        if trigger_logic == "all":
            triggered = bool(matched) and not failed
        else:
            triggered = bool(matched)
        if triggered:
            score = sum(cnt * _SIGNAL_WEIGHTS.get(sig, 1.0) for sig, _, cnt in matched)
            candidates.append({
                "name": name, "slug": slug_c,
                "reason": "; ".join(m for _, m, _ in matched),
                "score": score,
            })
        else:
            rejected.append({"name": name, "slug": slug_c,
                             "reason": "; ".join(m for _, m in failed)})

    # Rank + cap (per project_policy, defaults to 3)
    candidates.sort(key=lambda d: d["score"], reverse=True)
    cap = project_max_categories
    slots = max(0, cap - len(recommended))
    for d in candidates[:slots]:
        recommended.append(d)
        seen_slugs.add(d["slug"])

    # Resolve recommended names → IDs
    rec_ids = []
    for r in recommended:
        cid = name_to_id.get(r["name"]) or name_to_id_normalized.get(r["name"])
        if cid:
            rec_ids.append(cid)

    # Diff
    current_set = set(current_cat_ids)
    recommended_set = set(rec_ids)
    needs_patch = current_set != recommended_set

    result = {
        "post_id": post_id,
        "status": status,
        "slug": slug,
        "title": title,
        "current_cat_ids": sorted(current_cat_ids),
        "current_cat_names": [wp_cats.get(cid, {}).get("name", f"?{cid}") for cid in current_cat_ids],
        "recommended_cat_ids": rec_ids,
        "recommended_cat_names": [r["name"] for r in recommended],
        "recommended_reasons": [r.get("reason", "") for r in recommended],
        "inferred_format_id": fake_angle["format_id"],
        "needs_patch": needs_patch,
        "patched": False,
    }

    if needs_patch and apply:
        rr = c.post(f"/wp/v2/posts/{post_id}", json_body={"categories": rec_ids})
        result["patched"] = True
        result["wp_confirmed_cat_ids"] = sorted(rr.json_data.get("categories", []))

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("site_slug")
    ap.add_argument("--post-id", type=int, help="Audit a single post; omit to audit all")
    ap.add_argument("--project-slug", help="Defaults to site_slug")
    ap.add_argument("--apply", action="store_true", help="PATCH posts where recommendation differs (default: dry-run)")
    ap.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    args = ap.parse_args()

    c = WPClient(args.site_slug)
    if args.post_id:
        post_ids = [args.post_id]
    else:
        post_ids = []
        for page in range(1, 5):
            r = c.get("/wp/v2/posts", params={
                "per_page": 100, "page": page, "status": "publish,draft",
                "_fields": "id", "orderby": "date", "order": "desc",
            })
            if not r.json_data: break
            post_ids.extend(p["id"] for p in r.json_data)
            if len(r.json_data) < 100: break

    results = []
    for pid in post_ids:
        try:
            results.append(audit_post(args.site_slug, pid, project_slug=args.project_slug, apply=args.apply))
        except Exception as e:
            results.append({"post_id": pid, "error": f"{type(e).__name__}: {e}"})

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        diff_count = sum(1 for r in results if r.get("needs_patch"))
        patched_count = sum(1 for r in results if r.get("patched"))
        flag = "APPLY" if args.apply else "DRY-RUN"
        print(f"audit_post_categories [{flag}] :: {len(results)} posts audited :: "
              f"{diff_count} need PATCH :: {patched_count} patched")
        for r in results:
            if r.get("error"):
                print(f"  ✗ {r['post_id']}: {r['error']}")
                continue
            mark = "PATCH" if r.get("needs_patch") else "OK  "
            print(f"  [{mark}] {r['post_id']} [{r['status']:7s}] {r['slug'][:40]:40s}")
            if r.get("needs_patch"):
                print(f"          current:     {r['current_cat_names']}")
                print(f"          recommended: {r['recommended_cat_names']}")
                if r.get("patched"):
                    print(f"          ✓ PATCHED → {r['wp_confirmed_cat_ids']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
