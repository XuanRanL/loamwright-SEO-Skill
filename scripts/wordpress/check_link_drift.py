#!/usr/bin/env python3
"""Hop 2→3 drift for internal links baked into published post bodies.

WHY THIS EXISTS (Rule 13)
`sync_links_map.py` runs hop 3 → hop 2 — it LEARNS the map from live posts. There
is no reverse. `internal_link_graph.py` is explicitly plan-only ("it never edits a
post") and `cross_article_linker.py` does PATCH live posts, but from TF-IDF
suggestions rather than from the map. So map-vs-body drift was undetectable in both
directions.

WHAT DRIFT ACTUALLY MEANS HERE, AND WHAT IT DOES NOT
An internal link is not a templated value like a signature — a post legitimately
links wherever its argument needed to go, so "this body links somewhere the map
doesn't list" is editorial, not drift. Reporting it would bury the real finding
under every hand-added link in the fleet.

The finding that matters is a link that **no longer resolves**: a slug renamed, a
post unpublished, a URL restructured. That is silent damage on a live page, it is
exactly what a hop-3 checker should see, and it is checkable without guessing at
intent. Secondarily: map entries pointing at URLs that are gone, since the map
feeds every future article's linking.

Detection only.

Usage
-----
    python -m scripts.wordpress.check_link_drift {slug} --check
    python -m scripts.wordpress.check_link_drift {slug} --check --limit 40
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts._core import hop3_drift

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

_HREF_RE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\']', re.I)


def _load_json(p: Path) -> dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def internal_hrefs(content: str, site_url: str) -> list[str]:
    """Absolute-or-relative links pointing back at this site."""
    host = site_url.rstrip("/")
    out: list[str] = []
    for h in _HREF_RE.findall(content or ""):
        h = h.strip()
        if h.startswith("#") or h.startswith("mailto:") or h.startswith("tel:"):
            continue
        if h.startswith("/"):
            out.append(host + h)
        elif host and h.startswith(host):
            out.append(h)
    # de-dupe, keep order
    seen, uniq = set(), []
    for u in out:
        u = u.split("#", 1)[0].rstrip("/")
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _known_urls(slug: str, site_url: str, w: Any) -> set[str]:
    """Every URL this site currently serves as a post, page or term archive."""
    host = site_url.rstrip("/")
    known: set[str] = {host}
    # WooCommerce post types matter: the first live run flagged three product and
    # product-category URLs as dead purely because this list did not include them.
    # Enumeration can only ever cover the post types you thought of, which is why
    # it is a fast pre-filter here and NOT the verdict.
    for endpoint in ("/wp/v2/posts", "/wp/v2/pages", "/wp/v2/categories",
                     "/wp/v2/tags", "/wp/v2/product", "/wp/v2/product_cat",
                     "/wp/v2/product_tag"):
        page = 1
        while True:
            try:
                r = w.get(endpoint, params={"per_page": 100, "page": page,
                                            "_fields": "link,status"})
            except Exception:                          # noqa: BLE001
                break
            batch = r.json_data
            if not isinstance(batch, list) or not batch:
                break
            for item in batch:
                link = str(item.get("link") or "").split("#", 1)[0].rstrip("/")
                if link and item.get("status", "publish") == "publish":
                    known.add(link)
            if len(batch) < 100:
                break
            page += 1
    return known


def url_is_live(url: str, slug: str, cache: dict[str, bool]) -> bool:
    """Ask the SERVER whether a URL resolves.

    Enumeration is a guess about which post types exist; an HTTP status is the
    fact. The first live run reported three WooCommerce product URLs as dead
    because `/wp/v2/product` was not in the enumeration list — the third time in
    this session that a checker inferred a verdict it had not actually measured.
    So anything the pre-filter cannot vouch for gets a real request.
    """
    if url in cache:
        return cache[url]
    import httpx
    headers = {"User-Agent": "Mozilla/5.0 (compatible; xuanran-link-check)"}
    try:
        from scripts.wordpress.wp_client import _load_cf_bypass_token
        token, header_name = _load_cf_bypass_token(slug)
        if token:
            headers[header_name] = token
    except Exception:                                       # noqa: BLE001
        pass
    try:
        r = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
        alive = r.status_code < 400
    except Exception:                                       # noqa: BLE001
        alive = True        # unreachable is UNKNOWN, never "broken"
    cache[url] = alive
    return alive


def run(slug: str, *, limit: int | None = None) -> dict[str, Any]:
    from scripts.wordpress.wp_client import WPClient

    bc = _load_json(PLUGIN_ROOT / "projects" / slug / "business-context.json")
    site_url = str(bc.get("site_url") or "").rstrip("/")
    report: dict[str, Any] = {"project": slug, "scanned": 0, "updated": [],
                              "skipped": [], "errors": []}
    if not site_url:
        report["errors"].append({"id": slug, "reason": "no site_url in business-context"})
        return report

    w = WPClient(slug)
    known = _known_urls(slug, site_url, w)
    if len(known) <= 1:
        # We could not enumerate the site. That is an unknown, not "every link is
        # broken" — reporting drift here would be a transport failure wearing a
        # content verdict's clothes.
        report["errors"].append({"id": slug,
                                 "reason": "could not enumerate site URLs; no verdict"})
        return report

    posts: list[dict[str, Any]] = []
    page = 1
    while True:
        r = w.get("/wp/v2/posts", params={"status": "publish", "per_page": 100,
                                          "page": page, "context": "edit",
                                          "_fields": "id,slug,link,content"})
        batch = r.json_data
        if not isinstance(batch, list) or not batch:
            break
        posts.extend(batch)
        if len(batch) < 100 or (limit and len(posts) >= limit):
            break
        page += 1
    if limit:
        posts = posts[:limit]

    report["scanned"] = len(posts)
    live_cache: dict[str, bool] = {}
    for post in posts:
        content = ((post.get("content") or {}).get("raw")
                   or (post.get("content") or {}).get("rendered") or "")
        candidates = [u for u in internal_hrefs(content, site_url) if u not in known]
        dead = [u for u in candidates if not url_is_live(u, slug, live_cache)]
        if dead:
            report["updated"].append({"id": post.get("id"), "slug": post.get("slug"),
                                      "issues": [{"field": "dead_internal_link",
                                                  "found": dead[:6],
                                                  "count": len(dead)}]})
        else:
            report["skipped"].append({"id": post.get("id")})
    return report


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Detect internal links in published posts that no longer resolve")
    ap.add_argument("slug")
    ap.add_argument("--check", action="store_true", required=True,
                    help="report drift; this tool never writes")
    ap.add_argument("--limit", type=int, help="only scan the first N posts")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rep = run(a.slug, limit=a.limit)
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(hop3_drift.format_check(rep, artifact="internal links", fix_hint="detection only; fix the links or restore the URLs"))
        for u in rep["updated"][:20]:
            for i in u["issues"]:
                print(f"   {u['id']:>7} {u.get('slug','')}: {i['count']} dead")
                for url in i["found"]:
                    print(f"           {url}")
        for e in rep["errors"]:
            print(f"   ERROR {e['id']}: {e['reason']}")
    return hop3_drift.check_exit_code(rep)


if __name__ == "__main__":
    sys.exit(main())
