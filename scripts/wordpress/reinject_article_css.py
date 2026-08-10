#!/usr/bin/env python3
"""Re-inject a project's CURRENT article CSS into already-published posts.

WHY THIS EXISTS (the 3-hop distribution problem, 2026-07-14)
-----------------------------------------------------------
The article CSS lives at three levels, and they are NOT the same artifact:

  1. SKILL level    scripts/build/article_css_generator.py     (the template — 1 copy)
  2. PROJECT level  projects/{slug}/brand/article-css.css      (generated — 10 copies)
  3. POST level     the <style> block INLINED in each post body (N copies, one per post)

Hop 1 -> 2 is `python -m scripts.build.article_css_generator {slug}`.
Hop 2 -> 3 happens only at PUBLISH TIME, inside wp_publisher's 3-block wp:html wrap.

So fixing a CSS bug in the generator does NOT fix a single already-published post.
Every live post keeps whatever stylesheet was current on the day it shipped, forever.
That is why a component defect (e.g. the 2026-07-14 stat-card mid-word chop) appears
"in other projects too" and why it does not go away when the generator is patched.

This tool closes hop 3: it replaces the inline <style> block of existing posts with
the project's current CSS. It touches ONLY the stylesheet — never the article body,
never the wrapper <div>, never the JSON-LD.

USAGE
-----
    # always dry-run first
    python -m scripts.wordpress.reinject_article_css project-foxtrot --dry-run
    python -m scripts.wordpress.reinject_article_css project-foxtrot --apply
    python -m scripts.wordpress.reinject_article_css project-foxtrot --apply --post-ids 37026,37035
    python -m scripts.wordpress.reinject_article_css project-foxtrot --apply --only-if-stale
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from scripts._core import hop3_drift
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[2]

# The publisher emits exactly one leading <style>…</style> inside the first wp:html
# block. Non-greedy, DOTALL, first match only.
_STYLE_RE = re.compile(r"<style>.*?</style>", re.S)


def _project_css(slug: str) -> str:
    """Prefer the minified stylesheet (that is what the publisher inlines).

    Tokenized projects (2026-08-01 de-fingerprint) publish token class names,
    so the reinjected stylesheet gets the same style_tokens.transform the
    publisher applies — otherwise a reinject would silently orphan every rule
    on migrated posts (the exact Rule 2 disease, one level up).
    """
    from scripts._core import style_tokens

    base = PLUGIN_ROOT / "projects" / slug / "brand"
    for name in ("article-css.min.css", "article-css.css"):
        p = base / name
        if p.exists():
            return style_tokens.transform(p.read_text(encoding="utf-8").strip(), slug)
    raise SystemExit(f"no article CSS found for project {slug!r} under {base}")


def run(slug: str, apply: bool, post_ids: list[int] | None,
        only_if_stale: bool) -> dict[str, Any]:
    from scripts.wordpress.wp_client import WPClient

    css = _project_css(slug)
    new_style = f"<style>{css}</style>"
    w = WPClient(slug)

    targets: list[dict[str, Any]] = []
    if post_ids:
        for pid in post_ids:
            targets.append(w.get(f"/wp/v2/posts/{pid}",
                                 params={"context": "edit"}).json_data)
    else:
        for status in ("publish", "draft"):
            page = 1
            while True:
                r = w.get("/wp/v2/posts", params={
                    "status": status, "per_page": 100, "page": page,
                    "context": "edit", "_fields": "id,slug,status,content"})
                batch = r.json_data
                if not isinstance(batch, list) or not batch:
                    break
                targets.extend(batch)
                if len(batch) < 100:
                    break
                page += 1

    report: dict[str, Any] = {
        "project": slug, "applied": apply, "css_bytes": len(css),
        "scanned": len(targets), "updated": [], "skipped": [], "errors": [],
    }

    from scripts._core import style_tokens

    legacy_wrapper = style_tokens.legacy_wrapper_class(slug)
    tokenized = style_tokens.enabled(slug)

    for p in targets:
        pid = p["id"]
        body = (p.get("content") or {}).get("raw") or ""
        m = _STYLE_RE.search(body)
        if not m:
            report["skipped"].append({"id": pid, "slug": p.get("slug"),
                                      "reason": "no inline <style> block"})
            continue
        # Token-safety gate (2026-08-01): a tokenized project's CSS carries token
        # class names. Injecting it into a body that still uses LEGACY names would
        # orphan every rule (Rule 2's disease). Migrate the post first.
        if tokenized and legacy_wrapper in body[m.end():]:
            report["skipped"].append({"id": pid, "slug": p.get("slug"),
                                      "reason": "legacy-named body — run reinject_style_tokens first"})
            continue
        if m.group(0) == new_style:
            report["skipped"].append({"id": pid, "slug": p.get("slug"),
                                      "reason": "already current"})
            continue
        if only_if_stale and "minmax(210px" in m.group(0):
            report["skipped"].append({"id": pid, "slug": p.get("slug"),
                                      "reason": "already has the fixed stat grid"})
            continue

        updated = body[: m.start()] + new_style + body[m.end():]
        # Safety: only the stylesheet may change. The body after </style> is byte-identical.
        if body[m.end():] != updated[m.start() + len(new_style):]:
            report["errors"].append({"id": pid, "reason": "body would change; refusing"})
            continue

        entry = {"id": pid, "slug": p.get("slug"), "status": p.get("status"),
                 "old_bytes": len(m.group(0)), "new_bytes": len(new_style)}
        if apply:
            try:
                r = w.post(f"/wp/v2/posts/{pid}", json_body={"content": updated})
                entry["http"] = r.status
                back = w.get(f"/wp/v2/posts/{pid}",
                             params={"context": "edit"}).json_data
                entry["verified"] = new_style in ((back.get("content") or {}).get("raw") or "")
                entry["status_after"] = back.get("status")
            except Exception as e:  # surface, never swallow
                report["errors"].append({"id": pid, "reason": f"{type(e).__name__}: {e}"})
                continue
        report["updated"].append(entry)

    return report


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Re-inject a project's current article CSS into existing posts")
    ap.add_argument("slug")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true",
                   help="report drift, change nothing; exit 1 if any post is stale")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--post-ids", help="comma-separated ids; default = all posts")
    ap.add_argument("--only-if-stale", action="store_true",
                    help="skip posts whose CSS already has the fixed stat grid")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    ids = [int(x) for x in a.post_ids.split(",")] if a.post_ids else None
    rep = run(a.slug, apply=a.apply, post_ids=ids, only_if_stale=a.only_if_stale)

    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        verb = "UPDATED" if a.apply else "WOULD UPDATE"
        print(f"[{rep['project']}] scanned {rep['scanned']} · {verb} {len(rep['updated'])} "
              f"· skipped {len(rep['skipped'])} · errors {len(rep['errors'])}")
        for u in rep["updated"]:
            ok = u.get("verified")
            mark = "" if ok is None else (" ✓" if ok else " ✗ NOT VERIFIED")
            print(f"   {u['id']:>7} [{u.get('status','?'):<7}] {u.get('slug','')}{mark}")
        for e in rep["errors"]:
            print(f"   ERROR {e['id']}: {e['reason']}")

    if a.check:
        print(hop3_drift.format_check(rep, artifact="article CSS"))
        return hop3_drift.check_exit_code(rep)
    return 1 if rep["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
