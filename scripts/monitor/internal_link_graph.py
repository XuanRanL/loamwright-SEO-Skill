"""
scripts/monitor/internal_link_graph.py — site-wide internal-link graph + orphan repair plan.

Root cause this fixes: the per-article `internal-linker` subskill only adds links OUT of a new
post — it pushes link equity forward and never updates the existing posts that should now point
AT the new one. So a portfolio accumulates ORPHANS (pages with too few INBOUND internal links),
which content_audit flags but cannot fix. (project-juliet: 88 orphans.)

This is the graph-level complement: read every published post, build the internal-link graph,
find pages with too few INBOUND links, and for each orphan suggest the best INBOUND links from
topically-related existing posts (title-token similarity) that do not already link to it — with a
ready anchor. Output is a PLAN (draft-first): projects/{slug}/audits/internal-link-plan.json. It
never edits a post; the `internal-linker` subskill / a human applies the suggestions.

Skill-level logic; project-level plan.

    python -m scripts.monitor.internal_link_graph --site project-juliet --json
    python -m scripts.monitor.internal_link_graph --site project-juliet --min-inbound 2 --suggest 3
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts._core import credential_hub

_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOP = frozenset("the a an and or of for to in on with your you best guide how what is are 2026 "
                  "2025 vs your top review reviews complete ultimate".split())
DEFAULT_MIN_INBOUND = 2
DEFAULT_SUGGEST = 3


@dataclass
class OrphanPlan:
    url: str
    title: str
    inbound: int
    outbound: int
    suggestions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LinkGraphReport:
    site: str
    posts: int = 0
    orphans: int = 0
    plans: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOP and len(w) > 2}


def _similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _norm_path(href: str, domain: str) -> str | None:
    """Return the on-site path a link points to, or None if external/non-content."""
    href = href.strip().split("#")[0]
    if href.startswith(("mailto:", "tel:", "javascript:")):
        return None
    if href.startswith(("/", "./", "../")):
        return "/" + href.lstrip("./").rstrip("/") + "/"
    p = urlparse(href)
    host = p.netloc.lower().lstrip("www.")
    if host and domain and host.endswith(domain):
        return (p.path.rstrip("/") + "/") or "/"
    return None


def build_plan(slug: str, *, min_inbound: int = DEFAULT_MIN_INBOUND,
               suggest: int = DEFAULT_SUGGEST) -> LinkGraphReport:
    import httpx

    rep = LinkGraphReport(site=slug)
    try:
        creds = credential_hub.get_wordpress_creds(slug)
        bc = json.loads(Path(f"projects/{slug}/business-context.json").read_text(encoding="utf-8"))
        domain = urlparse(bc.get("site_url", "")).netloc.lower().lstrip("www.")
        headers = {"Authorization": creds.basic_auth_header()}
        wp = bc.get("wordpress", {})
        cf_name = wp.get("bypass_header") or wp.get("header_name")
        cf_tok = wp.get("bypass_token") or wp.get("cloudflare_bypass_token") or wp.get("token")
        if cf_name and cf_tok:
            headers[cf_name] = cf_tok
    except Exception as e:
        rep.error = f"creds/business-context: {e}"
        return rep

    posts: list[dict[str, Any]] = []
    page = 1
    try:
        while True:
            r = httpx.get(f"{creds.url}/wp-json/wp/v2/posts", headers=headers,
                          params={"per_page": 100, "page": page, "context": "edit",
                                  "_fields": "id,slug,link,title,content"}, timeout=60.0)
            if r.status_code != 200 or not r.json():
                break
            batch = r.json()
            posts.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    except Exception as e:
        rep.error = f"WP fetch: {e}"
        return rep

    # index by path; build outbound link sets + inbound counts
    by_path: dict[str, dict[str, Any]] = {}
    for p in posts:
        path = (urlparse(p.get("link", "")).path.rstrip("/") + "/") or "/"
        p["_path"] = path
        p["_title"] = (p.get("title", {}) or {}).get("rendered", "")
        p["_tokens"] = _tokens(p["_title"] + " " + p.get("slug", ""))
        by_path[path] = p

    inbound: dict[str, set[str]] = {p["_path"]: set() for p in posts}
    for p in posts:
        out: set[str] = set()
        for href in _HREF_RE.findall((p.get("content", {}) or {}).get("rendered", "")):
            tp = _norm_path(href, domain)
            if tp and tp in by_path and tp != p["_path"]:
                out.add(tp)
        p["_outbound"] = out
        for tp in out:
            inbound[tp].add(p["_path"])

    orphans = [p for p in posts if len(inbound[p["_path"]]) < min_inbound]
    orphans.sort(key=lambda p: len(inbound[p["_path"]]))
    rep.posts = len(posts)
    rep.orphans = len(orphans)

    for o in orphans:
        # candidate inbound sources: other posts topically related that don't already link to o
        cands = []
        for c in posts:
            if c["_path"] == o["_path"] or o["_path"] in c["_outbound"]:
                continue
            sim = _similarity(o["_tokens"], c["_tokens"])
            if sim > 0:
                cands.append((sim, c))
        cands.sort(key=lambda x: x[0], reverse=True)
        anchor = " ".join(list(o["_tokens"])[:4]) or o.get("slug", "")
        op = OrphanPlan(url=o.get("link", ""), title=o["_title"][:80],
                        inbound=len(inbound[o["_path"]]), outbound=len(o["_outbound"]))
        for sim, c in cands[:suggest]:
            op.suggestions.append({"link_from": c.get("link", ""), "from_title": c["_title"][:60],
                                   "similarity": round(sim, 3), "suggested_anchor": anchor})
        rep.plans.append(asdict(op))

    out_path = Path(f"projects/{slug}/audits/internal-link-plan.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(asdict(rep), indent=2, ensure_ascii=False), encoding="utf-8")
    return rep


def _print_human(rep: LinkGraphReport) -> None:
    print(f"── internal-link graph · {rep.site} ──")
    if rep.error:
        print(f"  ERROR: {rep.error}")
        return
    print(f"  {rep.posts} posts · {rep.orphans} orphans (< min inbound)")
    for op in rep.plans[:15]:
        print(f"  ORPHAN inbound={op['inbound']} {op['url'][:58]}")
        for s in op["suggestions"]:
            print(f"      ← link from {s['link_from'][:52]}  (sim {s['similarity']}, anchor \"{s['suggested_anchor']}\")")


def main() -> int:
    ap = argparse.ArgumentParser(description="Site-wide internal-link graph + orphan repair plan")
    ap.add_argument("--site", required=True)
    ap.add_argument("--min-inbound", type=int, default=DEFAULT_MIN_INBOUND)
    ap.add_argument("--suggest", type=int, default=DEFAULT_SUGGEST)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rep = build_plan(args.site, min_inbound=args.min_inbound, suggest=args.suggest)
    print(json.dumps(asdict(rep), indent=2, ensure_ascii=False) if args.json else "")
    if not args.json:
        _print_human(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
