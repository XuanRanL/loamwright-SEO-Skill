"""
scripts/monitor/content_audit.py — mechanical content-quality scanner (optimization axis 2a).

The refresh decision router (refresh_decision_router.py) is SIGNAL-driven — it acts on GSC
performance (CTR / rank / AI-citation). It never reads the article body, so it cannot see a post
that ranks fine yet contains thin, stale, orphaned, or weakly-sourced content. This scanner is the
complementary CONTENT-driven axis: it reads every published post and flags quality issues
REGARDLESS of search performance.

It catches the mechanical signals only (cheap, no LLM):
  - THIN          body word count below the floor
  - STALE         not modified in a long time (content rot)
  - ORPHAN        too few internal links (poor topical interlinking / authority flow)
  - THIN_SOURCING too few distinct external citations (an E-E-A-T risk, esp. for YMYL)
  - YEAR_DRIFT    leans on old years and never mentions the current year (looks dated)

What it does NOT catch — factual errors, outdated specific claims, weak citation AUTHORITY —
needs an LLM to read + verify (route those posts to the `fact-checker` agent / `rewrite` audit,
using the authoritative-source MCPs). This scanner tells you WHICH posts to send there.

Output: projects/{slug}/audits/content-audit.json (+ report). Skill-level logic; project output.

    python -m scripts.monitor.content_audit --site project-juliet --json
    python -m scripts.monitor.content_audit --all
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts._core import credential_hub

THIN_WORDS = 1200
STALE_DAYS = 180
MIN_INTERNAL_LINKS = 3
MIN_EXTERNAL_DOMAINS = 2
_TAG_RE = re.compile(r"<[^>]+>")
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)   # ALL hrefs (relative + absolute)


@dataclass
class PostFlags:
    post_id: int
    slug: str
    words: int
    age_days: int
    internal_links: int        # distinct internal targets (not raw link count)
    external_sources: int      # distinct external URLs (doi.org x N papers -> N, not 1)
    flags: list[str] = field(default_factory=list)


@dataclass
class ContentAuditReport:
    site: str
    posts_scanned: int = 0
    flagged: int = 0
    by_flag: dict[str, int] = field(default_factory=dict)
    posts: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def analyze_post(post: dict[str, Any], *, domain: str, now: datetime, current_year: int) -> PostFlags:
    """Pure content-quality analysis of one WP post dict (no I/O)."""
    html = (post.get("content", {}) or {}).get("rendered", "") or ""
    text = _TAG_RE.sub(" ", html)
    words = len(text.split())

    mod_raw = post.get("modified_gmt") or post.get("modified") or ""
    try:
        mod = datetime.fromisoformat(mod_raw.replace("Z", "") + "+00:00")
        age = (now - mod).days
    except Exception:
        age = -1

    internal_targets: set[str] = set()
    ext_sources: set[str] = set()
    for href in _HREF_RE.findall(html):
        href = href.strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        base = href.split("#")[0]
        if base.startswith(("/", "./", "../")):
            internal_targets.add(base)                       # relative internal target
            continue
        parsed = urlparse(base)
        host = parsed.netloc.lower().lstrip("www.")
        if not host:
            continue
        if domain and host.endswith(domain):
            internal_targets.add(parsed.path or base)        # absolute same-domain target
        else:
            ext_sources.add(base)                            # distinct external source URL
    internal = len(internal_targets)
    external = len(ext_sources)

    yr = {str(current_year - k): len(re.findall(rf"\b{current_year - k}\b", text)) for k in range(0, 4)}
    old = yr[str(current_year - 2)] + yr[str(current_year - 3)]

    flags: list[str] = []
    if words < THIN_WORDS:
        flags.append("THIN")
    if age > STALE_DAYS:
        flags.append("STALE")
    if internal < MIN_INTERNAL_LINKS:
        flags.append("ORPHAN")
    if external < MIN_EXTERNAL_DOMAINS:
        flags.append("THIN_SOURCING")
    if old >= 4 and yr[str(current_year)] == 0:
        flags.append("YEAR_DRIFT")

    return PostFlags(
        post_id=int(post.get("id", 0)), slug=str(post.get("slug", "")),
        words=words, age_days=age, internal_links=internal,
        external_sources=external, flags=flags,
    )


def _wp_headers(slug: str) -> tuple[str, dict[str, str]]:
    creds = credential_hub.get_wordpress_creds(slug)
    headers = {"Authorization": creds.basic_auth_header()}
    try:
        bc = json.loads(Path(f"projects/{slug}/business-context.json").read_text(encoding="utf-8"))
        wp = bc.get("wordpress", {})
        cf_name = wp.get("bypass_header") or wp.get("header_name")
        cf_tok = wp.get("bypass_token") or wp.get("cloudflare_bypass_token") or wp.get("token")
        if cf_name and cf_tok:
            headers[cf_name] = cf_tok
    except Exception:
        pass
    return creds.url, headers


def audit_site(slug: str) -> ContentAuditReport:
    """Fetch all published posts for a project via WP REST and run the mechanical content audit."""
    import httpx

    rep = ContentAuditReport(site=slug)
    try:
        base_url, headers = _wp_headers(slug)
        bc = json.loads(Path(f"projects/{slug}/business-context.json").read_text(encoding="utf-8"))
        domain = urlparse(bc.get("site_url", "")).netloc.lower().lstrip("www.")
    except Exception as e:
        rep.error = f"creds/business-context: {e}"
        return rep

    now = datetime.now(timezone.utc)
    current_year = now.year
    posts: list[dict[str, Any]] = []
    page = 1
    try:
        while True:
            r = httpx.get(f"{base_url}/wp-json/wp/v2/posts", headers=headers,
                          params={"per_page": 100, "page": page, "context": "edit",
                                  "_fields": "id,slug,modified_gmt,content"}, timeout=60.0)
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

    by_flag: dict[str, int] = {}
    flagged: list[PostFlags] = []
    for p in posts:
        pf = analyze_post(p, domain=domain, now=now, current_year=current_year)
        if pf.flags:
            flagged.append(pf)
            for f in pf.flags:
                by_flag[f] = by_flag.get(f, 0) + 1
    flagged.sort(key=lambda x: (len(x.flags), -x.age_days), reverse=True)
    rep.posts_scanned = len(posts)
    rep.flagged = len(flagged)
    rep.by_flag = by_flag
    rep.posts = [asdict(pf) for pf in flagged]

    out = Path(f"projects/{slug}/audits/content-audit.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(rep), indent=2, ensure_ascii=False), encoding="utf-8")
    return rep


def _print_human(rep: ContentAuditReport) -> None:
    print(f"── content audit · {rep.site} ──")
    if rep.error:
        print(f"  ERROR: {rep.error}")
        return
    print(f"  scanned {rep.posts_scanned} posts · flagged {rep.flagged} · {rep.by_flag or 'all clean'}")
    for pf in rep.posts[:20]:
        print(f"  [{','.join(pf['flags']):28s}] /{pf['slug'][:40]:40s} "
              f"words={pf['words']:>5} age={pf['age_days']:>3}d int={pf['internal_links']:>2} ext={pf['external_sources']:>2}")
    if rep.flagged:
        print("  → send the LLM-needed ones (accuracy/citation authority) to fact-checker / rewrite.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Mechanical content-quality scanner (axis 2a)")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--site")
    grp.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    slugs = ([os.path.basename(os.path.dirname(p)) for p in sorted(glob.glob("projects/*/business-context.json"))]
             if args.all else [args.site])
    reports = [audit_site(s) for s in slugs]
    if args.json:
        print(json.dumps([asdict(r) for r in reports] if args.all else asdict(reports[0]),
                         indent=2, ensure_ascii=False))
    else:
        for r in reports:
            _print_human(r)
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
