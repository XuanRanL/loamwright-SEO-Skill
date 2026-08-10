"""
scripts/fetch/crossref_lookup.py — Crossref DOI lookup (FREE, no API key).

Crossref REST API (https://api.crossref.org/works) is the primary source for
academic citation metadata. Free, no key, but uses "polite pool" via User-Agent.

Per `references/apa-citation-rules.md`:
  - Prefer Crossref-verified DOIs over Tavily web results
  - Always verify DOI is real (HEAD check via link_resolver.py)

Polite pool benefit: get notified of API changes + higher rate limits.
Requires User-Agent: `YourApp/Version (mailto:contact@email.com)`.

CLI:
    python -m scripts.fetch.crossref_lookup "lumbar support office chair RCT"
    python -m scripts.fetch.crossref_lookup --doi 10.1234/abc.2023
    python -m scripts.fetch.crossref_lookup "query" --rows 10 --json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts._core import credential_hub
from scripts._core.ssrf_guard import validate_url, SSRFError


CROSSREF_BASE = "https://api.crossref.org"
RATE_LIMIT_DELAY = 0.05  # 50ms between requests (polite pool ~20 req/s)


@dataclass
class CrossrefWork:
    doi: str
    doi_url: str           # https://doi.org/...
    title: str
    authors: list[str]
    year: int | None
    journal: str           # container-title
    volume: str
    issue: str
    page: str
    publisher: str
    type: str               # journal-article, book-chapter, ...
    is_referenced_by_count: int = 0
    score: float = 0.0      # Crossref relevance score


def _user_agent() -> str:
    return credential_hub.get_crossref_user_agent()


def _make_request(url: str, params: dict | None = None) -> dict:
    """Make a Crossref API request with retries."""
    try:
        validate_url(url, allow_http=False, resolve_dns=True)
    except SSRFError as e:
        raise RuntimeError(f"SSRF block: {e}")

    try:
        import httpx
    except ImportError as e:
        raise RuntimeError("httpx not installed") from e

    last_err = None
    for attempt in range(3):
        try:
            r = httpx.get(
                url,
                params=params or {},
                headers={"User-Agent": _user_agent()},
                timeout=15.0,
                follow_redirects=True,
            )
            if r.status_code == 429:
                # Rate limited; back off
                time.sleep(2.0 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            last_err = e
            time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"Crossref API failed after retries: {last_err}")


def _parse_work(item: dict) -> CrossrefWork:
    """Convert Crossref API response item to CrossrefWork."""
    doi = item.get("DOI", "")
    title_list = item.get("title", [])
    title = title_list[0] if title_list else ""
    container_list = item.get("container-title", [])
    journal = container_list[0] if container_list else ""

    authors = []
    for a in item.get("author", []):
        family = a.get("family", "")
        given = a.get("given", "")
        if family:
            initials = ". ".join(g[0] for g in given.split() if g) + "." if given else ""
            authors.append(f"{family}, {initials}".strip())

    # Year from various date fields
    year = None
    for date_key in ("published-print", "published-online", "issued", "created"):
        d = item.get(date_key, {})
        if isinstance(d, dict) and d.get("date-parts"):
            parts = d["date-parts"][0]
            if parts and isinstance(parts[0], int):
                year = parts[0]
                break

    return CrossrefWork(
        doi=doi,
        doi_url=f"https://doi.org/{doi}" if doi else "",
        title=title,
        authors=authors,
        year=year,
        journal=journal,
        volume=item.get("volume", ""),
        issue=item.get("issue", ""),
        page=item.get("page", ""),
        publisher=item.get("publisher", ""),
        type=item.get("type", ""),
        is_referenced_by_count=item.get("is-referenced-by-count", 0),
        score=float(item.get("score", 0.0)),
    )


def search(query: str, rows: int = 5, filter_type: str = "") -> list[CrossrefWork]:
    """Search Crossref by query string.

    Args:
        query: Free-text query (e.g. "lumbar support fishing rod RCT").
        rows: Max results (1-1000; we cap at 20 to be polite).
        filter_type: Crossref type filter (e.g. "journal-article").

    Returns:
        List of CrossrefWork sorted by relevance score.
    """
    params: dict = {"query": query, "rows": min(rows, 20)}
    if filter_type:
        params["filter"] = f"type:{filter_type}"

    data = _make_request(f"{CROSSREF_BASE}/works", params)
    items = data.get("message", {}).get("items", [])

    works = [_parse_work(item) for item in items]
    works.sort(key=lambda w: w.score, reverse=True)
    return works


def get_by_doi(doi: str) -> CrossrefWork | None:
    """Fetch a single work by DOI."""
    doi = doi.replace("https://doi.org/", "").strip()
    if not doi:
        return None
    try:
        data = _make_request(f"{CROSSREF_BASE}/works/{doi}")
        return _parse_work(data.get("message", {}))
    except RuntimeError:
        return None


def format_apa(work: CrossrefWork) -> str:
    """Format a CrossrefWork as APA 7 reference entry.

    Per references/apa-citation-rules.md.
    """
    if not work.authors:
        author_str = "Unknown"
    else:
        # Up to 20 authors; if 21+, list first 19, then "...", then last
        if len(work.authors) <= 20:
            author_str = ", ".join(work.authors[:-1])
            if len(work.authors) > 1:
                author_str += f", & {work.authors[-1]}"
            else:
                author_str = work.authors[0]
        else:
            author_str = ", ".join(work.authors[:19]) + f", ... {work.authors[-1]}"

    year_str = f"({work.year})" if work.year else "(n.d.)"
    parts = [f"{author_str} {year_str}.", f"{work.title}."]
    if work.journal:
        loc = work.journal
        if work.volume:
            loc += f", {work.volume}"
            if work.issue:
                loc += f"({work.issue})"
        if work.page:
            loc += f", {work.page}"
        loc += "."
        parts.append(loc)
    if work.doi_url:
        parts.append(work.doi_url)
    return " ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Crossref DOI lookup")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("query", nargs="?", help="Search query (free text)")
    g.add_argument("--doi", help="Fetch by DOI")
    ap.add_argument("--rows", type=int, default=5)
    ap.add_argument("--filter-type", help="Crossref type filter")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--apa", action="store_true", help="Output APA 7 formatted")
    args = ap.parse_args()

    if args.doi:
        work = get_by_doi(args.doi)
        if not work:
            print(f"DOI not found: {args.doi}", file=sys.stderr)
            return 1
        works = [work]
    else:
        try:
            works = search(args.query, rows=args.rows, filter_type=args.filter_type or "")
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        if not works:
            print("No results", file=sys.stderr)
            return 1

    if args.json:
        print(json.dumps([asdict(w) for w in works], indent=2, ensure_ascii=False))
    elif args.apa:
        for w in works:
            print(format_apa(w))
            print()
    else:
        for i, w in enumerate(works, 1):
            print(f"  [{i}]  {w.doi}  (score: {w.score:.1f})")
            print(f"        {w.title}")
            print(f"        {', '.join(w.authors[:3])}{'...' if len(w.authors) > 3 else ''}  ({w.year})")
            if w.journal:
                print(f"        {w.journal}")
            print(f"        cited: {w.is_referenced_by_count}")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
