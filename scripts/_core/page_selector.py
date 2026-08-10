"""scripts/_core/page_selector.py — Pick 40 most info-dense pages from sitemap.

Per /init Stage 2 spec: prioritize info-density pages (homepage / about / FAQ /
resources / product / blog) over policy / category pages.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse


PageType = Literal[
    "homepage", "about", "contact", "info", "policy", "category",
    "product", "blog", "author", "tag", "search", "404", "tech", "other"
]


@dataclass
class PageCandidate:
    url: str
    path: str
    page_type: PageType = "other"
    priority: int = 0          # 0=highest
    lastmod: str | None = None
    parent_dir: str = ""


# URL path patterns → page type
PATH_PATTERNS: list[tuple[str, PageType, int]] = [
    # (regex, type, priority — lower = higher priority)
    (r"^/$|^/index\.html?$", "homepage", 0),
    (r"^/(about|about-us|company|team|story)/?$", "about", 1),
    (r"^/(contact|contact-us|locations|find-us)/?$", "contact", 1),
    (r"^/(faq|frequently-asked-questions|help|support|resources?|guides?)/?", "info", 2),
    (r"^/(knowledge|kb|info|learn|how-to|tips)/?", "info", 2),
    (r"^/(privacy|terms|tos|legal|policy|gdpr|returns|shipping|warranty)/?", "policy", 4),
    (r"^/(blog|news|articles|posts|insights|stories)/?$", "category", 3),
    (r"^/(blog|news|articles?|posts?)/[\w-]+/?$", "blog", 2),
    (r"^/(products?|shop|store|collections?|catalog)/?$", "category", 3),
    (r"^/(products?|shop|store)/[\w-]+/?$", "product", 1),
    (r"^/category/[\w-]+/?$", "category", 3),
    (r"^/categories?/[\w-]+/?$", "category", 3),
    (r"^/tag/[\w-]+/?$", "tag", 5),
    (r"^/author/[\w-]+/?$", "author", 4),
    (r"^/search\b", "search", 6),
    (r"^/404\b|^/error\b", "404", 7),
    (r"^/robots\.txt$|^/sitemap.*\.xml$|^/feed\b|^/rss\b", "tech", 7),
]


def classify(url: str) -> PageCandidate:
    """Classify a single URL."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    parent = path.rstrip("/").rsplit("/", 1)[0] or "/"

    for pattern, ptype, prio in PATH_PATTERNS:
        if re.match(pattern, path, re.IGNORECASE):
            return PageCandidate(url=url, path=path, page_type=ptype,
                                  priority=prio, parent_dir=parent)
    return PageCandidate(url=url, path=path, page_type="other",
                          priority=5, parent_dir=parent)


def select(
    urls: list[str] | list[tuple[str, str | None]],
    *,
    max_pages: int = 40,
    is_ecommerce: bool = False,
) -> list[PageCandidate]:
    """Pick the most info-dense N pages from a sitemap.

    Args:
        urls: list of URLs OR list of (url, lastmod) tuples.
        max_pages: cap (default 40 per /init spec).
        is_ecommerce: if True, weight product pages higher.

    Returns:
        Selected pages sorted by priority then lastmod.
    """
    candidates: list[PageCandidate] = []
    for item in urls:
        if isinstance(item, tuple):
            url, lastmod = item
        else:
            url, lastmod = item, None
        c = classify(url)
        c.lastmod = lastmod
        candidates.append(c)

    # Bucket by type
    buckets: dict[PageType, list[PageCandidate]] = {}
    for c in candidates:
        buckets.setdefault(c.page_type, []).append(c)

    # Target allocations per /init spec
    if is_ecommerce:
        allocations = {
            "homepage": 1,
            "about": 1,
            "contact": 1,
            "info": 6,
            "policy": 2,
            "category": 4,
            "product": 15,
            "blog": 7,
            "author": 1,
            "tech": 2,
        }
    else:
        allocations = {
            "homepage": 1,
            "about": 1,
            "contact": 1,
            "info": 7,
            "policy": 3,
            "category": 3,
            "product": 8,
            "blog": 12,
            "author": 2,
            "tech": 2,
        }

    selected: list[PageCandidate] = []
    for ptype, n in allocations.items():
        pool = buckets.get(ptype, [])
        # Sort within bucket: by lastmod desc, then path length asc
        pool.sort(key=lambda c: (-(int(c.lastmod or "0").__hash__()) if c.lastmod else 0,
                                   len(c.path)))
        selected.extend(pool[:n])

    # Fill remaining slots with highest-priority untaken pages
    taken_urls = {c.url for c in selected}
    remaining = [c for c in candidates if c.url not in taken_urls]
    remaining.sort(key=lambda c: c.priority)
    while len(selected) < max_pages and remaining:
        selected.append(remaining.pop(0))

    return selected[:max_pages]


def main() -> int:
    ap = argparse.ArgumentParser(description="Select 40 most info-dense pages from URL list")
    ap.add_argument("--sitemap", type=Path, help="XML sitemap file")
    ap.add_argument("--urls-file", type=Path, help="Newline-separated URLs")
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument("--ecommerce", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    urls: list[str | tuple[str, str | None]] = []
    if args.sitemap and args.sitemap.exists():
        # Parse XML sitemap
        text = args.sitemap.read_text(encoding="utf-8")
        for m in re.finditer(r"<url>(.+?)</url>", text, re.DOTALL):
            url_match = re.search(r"<loc>(.+?)</loc>", m.group(1))
            lastmod_match = re.search(r"<lastmod>(.+?)</lastmod>", m.group(1))
            if url_match:
                urls.append((url_match.group(1), lastmod_match.group(1) if lastmod_match else None))
    elif args.urls_file and args.urls_file.exists():
        urls = [u.strip() for u in args.urls_file.read_text(encoding="utf-8").splitlines() if u.strip()]
    else:
        urls = sys.stdin.read().splitlines()
        urls = [u.strip() for u in urls if u.strip() and not u.startswith("#")]

    if not urls:
        print("No URLs to select from", file=sys.stderr)
        return 2

    selected = select(urls, max_pages=args.max, is_ecommerce=args.ecommerce)

    if args.json:
        print(json.dumps([asdict(c) for c in selected], indent=2, ensure_ascii=False))
    else:
        print(f"Selected {len(selected)} of {len(urls)}:")
        by_type: dict[str, int] = {}
        for c in selected:
            by_type[c.page_type] = by_type.get(c.page_type, 0) + 1
        for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"  {n:3d}  {t}")
        print()
        for c in selected[:50]:
            print(f"  [{c.priority}] {c.page_type:10s} {c.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
