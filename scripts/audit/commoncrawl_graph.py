#!/usr/bin/env python3
"""Common Crawl host-level web graph parser.

Fetches domain-level link metrics from the CC quarterly domain-ranks table:
harmonic centrality (value + rank), PageRank (value + rank), and n_hosts.
The table has no in/out-degree columns; the v3.42.10 rewrite deleted those
fields rather than fabricate them.

Completely FREE -- no API key required.

Usage:
    python -m scripts.audit.commoncrawl_graph example.com --json
    python -m scripts.audit.commoncrawl_graph example.com --crawl cc-main-2025-nov --json

Data source:
    https://data.commoncrawl.org/projects/hyperlinkgraph/
    Files are tab-separated, gzip-compressed.  We stream them to avoid
    loading multi-GB files into memory.

Caching:
    Downloaded ranking data is cached in ``{output_dir}/cc_cache/`` (or
    a caller-supplied directory) to avoid redundant multi-MB downloads.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CC_BASE = "https://data.commoncrawl.org/projects/hyperlinkgraph"

# Common Crawl publishes the webgraph QUARTERLY, at
#   {crawl_id}/domain/{crawl_id}-domain-ranks.txt.gz
# with tab-separated columns:
#   #harmonicc_pos  #harmonicc_val  #pr_pos  #pr_val  #host_rev  #n_hosts
# and the domain key REVERSED (example.com -> com.example), sorted by harmonic
# centrality rank ascending (rank 1 = most central).
#
# The previous per-month `{crawl}/host-level/vertices.txt.gz` path was retired
# upstream and returned 404 for EVERY domain — which this module reported
# indistinguishably from "domain not in the graph", so the whole tier-0 backlink
# source was silently dead. Found 2026-08-06; pinned by
# tests/test_audit_backlink_sources_are_live.py.
_RANKS_TEMPLATE = "{base}/{crawl_id}/domain/{crawl_id}-domain-ranks.txt.gz"

# Most recent quarter first. Every ID here is HTTP-verified by the test above —
# do not add one without checking it resolves.
_DEFAULT_CRAWL_IDS: list[str] = [
    "cc-main-2025-sep-oct-nov",
    "cc-main-2025-may-jun-jul",
    "cc-main-2025-jan-feb-mar",
    "cc-main-2024-sep-oct-nov",
    "cc-main-2024-may-jun-jul",
]


# How deep (by harmonic-centrality rank) the last scan of each crawl reached.
# Used to phrase "not found" honestly.
_LAST_SCAN_DEPTH: dict[str, int] = {}

# Above this download budget we stop building an in-memory index: a deep scan is
# a one-off lookup, and holding millions of rows to cache them costs more than
# re-scanning ever saves.
_MAX_CACHEABLE_BYTES = 64 * 1024 * 1024

# Reserved key inside a cached index recording how deep that cache actually went.
# A domain can never collide with it: real keys are reversed domains.
_CACHE_META_KEY = "#meta"


def _ranks_url(crawl_id: str) -> str:
    """Build the published domain-ranks URL for a crawl."""
    return _RANKS_TEMPLATE.format(base=CC_BASE, crawl_id=crawl_id)


def _reverse_domain(domain: str) -> str:
    """example.com -> com.example (the graph's sort key)."""
    return ".".join(reversed(domain.strip().strip(".").lower().split(".")))


def _parse_ranks_row(line: str) -> Optional[dict[str, Any]]:
    """Parse one domain-ranks row into a metrics dict, or None if not a data row.

    Columns: harmonicc_pos, harmonicc_val, pr_pos, pr_val, host_rev, n_hosts
    """
    if not line or line.startswith("#"):
        return None
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 6:
        return None
    try:
        return {
            "domain": ".".join(reversed(parts[4].split("."))),
            "domain_reversed": parts[4],
            "harmonic_centrality_rank": int(parts[0]),
            "harmonic_centrality": float(parts[1]),
            "pagerank_rank": int(parts[2]),
            "pagerank": float(parts[3]),
            "n_hosts": int(parts[5]),
        }
    except (ValueError, IndexError):
        return None

# Streaming download timeout (the full vertices file can be 1-3 GB compressed).
_STREAM_TIMEOUT = 300

# Default cache directory (relative to cwd or overridden by caller).
_DEFAULT_CACHE_DIR = Path("cc_cache")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class HostGraphMetrics:
    """Metrics for a single host extracted from the CC web graph."""

    domain: str
    harmonic_centrality: float = 0.0
    harmonic_centrality_rank: int = 0
    pagerank: float = 0.0
    pagerank_rank: int = 0
    n_hosts: int = 0
    crawl_id: str = ""
    error: Optional[str] = None
    #: Deepest harmonic-centrality rank the truncated scan reached. Lets a caller
    #: distinguish "absent from the graph" from "deeper than we read".
    scanned_to_rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "harmonic_centrality": self.harmonic_centrality,
            "harmonic_centrality_rank": self.harmonic_centrality_rank,
            "pagerank": self.pagerank,
            "pagerank_rank": self.pagerank_rank,
            "n_hosts": self.n_hosts,
            "crawl_id": self.crawl_id,
            "error": self.error,
            "scanned_to_rank": self.scanned_to_rank,
        }


@dataclass
class CCGraphResult:
    """Full result payload."""

    domain: str
    metrics: Optional[HostGraphMetrics] = None
    neighbours: list[dict[str, Any]] = field(default_factory=list)
    source: str = "commoncrawl"
    cache_hit: bool = False
    response_time_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "neighbours": self.neighbours,
            "source": self.source,
            "cache_hit": self.cache_hit,
            "response_time_ms": self.response_time_ms,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_domain(domain_or_url: str) -> str:
    """Strip scheme, www prefix, path, and trailing slash."""
    raw = domain_or_url.strip().rstrip("/")
    if "://" in raw:
        from urllib.parse import urlparse
        parsed = urlparse(raw)
        raw = parsed.netloc or parsed.path.split("/")[0]
    # Remove www. for matching (CC graph stores with and without; we check both)
    return raw.lower()


def _cache_path(cache_dir: Path, crawl_id: str) -> Path:
    """Return the local cache file for a crawl's per-domain JSON index."""
    return cache_dir / f"{crawl_id}_domain_index.json.gz"


def _load_cache(cache_dir: Path, crawl_id: str) -> Optional[dict[str, dict[str, Any]]]:
    """Load a previously built per-domain index from cache."""
    path = _cache_path(cache_dir, crawl_id)
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)  # type: ignore[no-any-return]
    except Exception:
        return None


def _save_cache(
    cache_dir: Path,
    crawl_id: str,
    index: dict[str, dict[str, Any]],
) -> None:
    """Persist a per-domain index to compressed JSON."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, crawl_id)
    try:
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(index, f)
    except Exception as exc:
        print(f"Warning: failed to save CC cache: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Targeted streaming search (avoids downloading the full file)
# ---------------------------------------------------------------------------


def _search_domain_in_stream(
    domain: str,
    crawl_id: str,
    timeout: int = _STREAM_TIMEOUT,
) -> Optional[dict[str, Any]]:
    """Stream the vertices file and search for a specific domain.

    Returns a ``_parse_ranks_row`` dict (harmonic centrality + PageRank values
    and ranks, ``n_hosts``) if found, or ``None``.

    The CC vertices file is sorted alphabetically by domain, so we can
    bail early once we pass the target domain lexicographically.
    """
    url = _ranks_url(crawl_id)
    bare = domain.lower().removeprefix("www.")
    targets = {_reverse_domain(bare), _reverse_domain(f"www.{bare}")}

    # Decompress INCREMENTALLY. The previous implementation re-inflated the whole
    # accumulated buffer on every 64 KB chunk, which is O(n^2) over a multi-GB
    # file and never completed in practice.
    decomp = zlib.decompressobj(zlib.MAX_WBITS | 16)
    tail = ""

    try:
        with httpx.stream(
            "GET",
            url,
            timeout=httpx.Timeout(connect=30, read=timeout, write=30, pool=30),
            follow_redirects=True,
        ) as response:
            if response.status_code == 404:
                return None
            response.raise_for_status()

            for chunk in response.iter_bytes(chunk_size=1 << 18):
                try:
                    text = decomp.decompress(chunk).decode("utf-8", errors="replace")
                except zlib.error:
                    return None
                if not text:
                    continue

                text, tail = tail + text, ""
                lines = text.split("\n")
                tail = lines.pop()  # last element is a partial line

                for line in lines:
                    row = _parse_ranks_row(line)
                    if row is None:
                        continue
                    if row["domain_reversed"] in targets:
                        return row

    except httpx.TimeoutException:
        return None
    except httpx.HTTPError:
        return None

    return None


def _search_domain_via_ranked_download(
    domain: str,
    crawl_id: str,
    cache_dir: Path,
    max_download_bytes: int = 50 * 1024 * 1024,  # 50 MB max
) -> Optional[dict[str, Any]]:
    """Download the beginning of the vertices file and build a partial index.

    The CC host-level vertices file is sorted by harmonic centrality
    (descending).  For most SEO-relevant domains the entry is within the
    first 10-50 million rows (~50 MB compressed = ~200 MB decompressed).
    We download up to ``max_download_bytes`` of the gzip stream, build a
    domain -> metrics index, cache it, and look up the target domain.
    """
    # Try cache first
    # Build the lookup keys ONCE, up front, so the cache path and the fresh path
    # cannot drift apart on how a domain is keyed.
    bare = domain.lower().removeprefix("www.")
    lookup_keys = (_reverse_domain(bare), _reverse_domain(f"www.{bare}"))

    cached = _load_cache(cache_dir, crawl_id)
    if cached is not None:
        for key in lookup_keys:
            if key in cached:
                return cached[key]
        # A MISS in the cache is only meaningful if that cache was built from a
        # scan at least as deep as the one being asked for now. Otherwise a
        # shallow earlier run permanently answers "not found" for every deeper
        # request — which is how a 50 MB cache silently defeated a 500 MB scan.
        cached_budget = int(cached.get(_CACHE_META_KEY, {}).get("max_download_bytes", 0))
        if cached_budget >= max_download_bytes:
            _LAST_SCAN_DEPTH[crawl_id] = int(
                cached.get(_CACHE_META_KEY, {}).get("deepest_rank", 0)
            )
            return None
        # else: fall through and rescan deeper.

    url = _ranks_url(crawl_id)

    # Stream, decompress and match INCREMENTALLY, stopping the moment we hit the
    # target. Accumulating the whole range in memory and inflating it in one shot
    # cost ~3.5x the download in RAM (a 450 MB budget became a ~1.5 GB string and
    # simply failed), and it kept downloading long after the answer was in hand.
    #
    # Only crawls small enough to be worth caching get an index built; beyond that
    # the memory belongs to the scan, not to a cache nobody reuses.
    build_index = max_download_bytes <= _MAX_CACHEABLE_BYTES
    index: dict[str, dict[str, Any]] = {}
    dec = zlib.decompressobj(zlib.MAX_WBITS | 16)
    tail = ""
    deepest_rank = 0
    downloaded = 0
    hit: Optional[dict[str, Any]] = None

    try:
        with httpx.stream(
            "GET",
            url,
            timeout=httpx.Timeout(connect=30, read=_STREAM_TIMEOUT, write=30, pool=30),
            follow_redirects=True,
            headers={"Range": f"bytes=0-{max_download_bytes}"},
        ) as response:
            if response.status_code not in (200, 206):
                # The ranks file itself is unreachable (404 = retired/moved
                # upstream). Record THIS attempt's depth — zero — instead of
                # leaving a previous scan's depth in the module global, which
                # would let the not-found report quote a stale scanned_to_rank
                # and advise scanning deeper into a file that cannot be fetched
                # at all. "Source unavailable" and "not in the portion scanned"
                # are different verdicts (Rule 12); the HTTPError path below
                # already records its depth the same way.
                _LAST_SCAN_DEPTH[crawl_id] = deepest_rank
                return None

            for chunk in response.iter_bytes(chunk_size=1 << 18):
                downloaded += len(chunk)
                try:
                    text = dec.decompress(chunk).decode("utf-8", errors="replace")
                except zlib.error:
                    break
                if text:
                    parts = (tail + text).split("\n")
                    tail = parts.pop()
                    for line in parts:
                        row = _parse_ranks_row(line)
                        if row is None:
                            continue
                        if row["harmonic_centrality_rank"] > deepest_rank:
                            deepest_rank = row["harmonic_centrality_rank"]
                        if build_index:
                            index[row["domain_reversed"]] = row
                        if hit is None and row["domain_reversed"] in lookup_keys:
                            hit = row
                    if hit is not None and not build_index:
                        break  # answer in hand; no reason to keep downloading
                if downloaded >= max_download_bytes:
                    break

    except httpx.HTTPError:
        # Keep whatever depth we established; a partial scan is still information.
        pass

    # Record how far we actually got. Absence within a truncated scan is NOT
    # evidence of absence from the graph, and callers must be able to tell the
    # difference (Rule 12: a coverage limit is not a content verdict).
    _LAST_SCAN_DEPTH[crawl_id] = deepest_rank

    if build_index and index:
        index[_CACHE_META_KEY] = {  # type: ignore[assignment]
            "max_download_bytes": max_download_bytes,
            "deepest_rank": deepest_rank,
        }
        _save_cache(cache_dir, crawl_id, index)
        index.pop(_CACHE_META_KEY, None)
        # Look up in the index, keyed by REVERSED domain — the graph's own sort
        # key, and the same keys the cache path above uses.
        for key in lookup_keys:
            if key in index:
                return index[key]
        return None

    return hit


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_domain_metrics(
    domain: str,
    crawl_id: Optional[str] = None,
    cache_dir: Optional[Path] = None,
    max_download_bytes: int = 50 * 1024 * 1024,
) -> HostGraphMetrics:
    """Fetch domain-level graph metrics for a domain from Common Crawl.

    Tries crawl IDs from most recent to oldest until data is found.

    ``max_download_bytes`` bounds how much of each (multi-GB) ranks file is read.
    It is a genuine coverage limit: a domain ranked deeper than the scan reaches
    returns an error that says so, rather than claiming the domain is absent.
    """
    normalized = _normalize_domain(domain)
    effective_cache = cache_dir or _DEFAULT_CACHE_DIR

    crawl_ids = [crawl_id] if crawl_id else _DEFAULT_CRAWL_IDS

    for cid in crawl_ids:
        # Try ranked download (more reliable, cacheable)
        data = _search_domain_via_ranked_download(
            normalized, cid, effective_cache, max_download_bytes=max_download_bytes
        )
        if data:
            # The quarterly domain-ranks table publishes real harmonic-centrality
            # and PageRank RANKS. It has no in/out degree columns — n_hosts (the
            # number of hosts under the domain) is the only degree-ish figure, so
            # report it as itself rather than mislabelling it as in_degree.
            return HostGraphMetrics(
                domain=data.get("domain", normalized),
                harmonic_centrality=data.get("harmonic_centrality", 0.0),
                harmonic_centrality_rank=data.get("harmonic_centrality_rank", 0),
                pagerank=data.get("pagerank", 0.0),
                pagerank_rank=data.get("pagerank_rank", 0),
                n_hosts=data.get("n_hosts", 0),
                crawl_id=cid,
                scanned_to_rank=_LAST_SCAN_DEPTH.get(cid, 0),
            )

    # Say what was actually established. The scan is truncated by design (we read
    # the head of a multi-GB file), so "not in the part we read" must never be
    # reported as "not in the graph" — audit-client.example, for example, IS in the graph at
    # harmonic rank ~13.3M, far below any practical download cap.
    depths = [_LAST_SCAN_DEPTH.get(cid, 0) for cid in crawl_ids]
    scanned_to = max(depths) if depths else 0
    if scanned_to:
        reason = (
            f"Domain '{normalized}' was NOT FOUND IN THE PORTION SCANNED. "
            f"Tried crawl IDs: {', '.join(crawl_ids)}; the deepest scan reached "
            f"harmonic-centrality rank ~{scanned_to:,} of ~100M ranked domains. "
            "This is a coverage limit, NOT evidence the domain is absent from the "
            "graph — most real sites rank far deeper than a head-of-file scan "
            "reaches. Raise --max-download-mb to scan deeper."
        )
    else:
        reason = (
            f"Domain '{normalized}' could not be looked up: no crawl returned "
            f"readable data. Tried crawl IDs: {', '.join(crawl_ids)}. "
            "This is a fetch failure, not a verdict about the domain."
        )
    return HostGraphMetrics(domain=normalized, error=reason, scanned_to_rank=scanned_to)


# NOTE: a former `_estimate_pagerank()` helper mapped harmonic centrality onto a
# 0-100 "PageRank estimate" by assuming HC ranged 0.0001-1.0. The quarterly
# domain-ranks table reports HC in the ~1e5-3e7 range, so that mapping saturated
# at 100 for every domain on earth. It is deleted rather than rescaled: the table
# publishes a real PageRank value AND a real rank, so an estimate is no longer
# needed and a rescaled version would only invite the same units confusion.


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="commoncrawl_graph",
        description=(
            "Common Crawl host-level web graph parser. "
            "FREE, no API key required."
        ),
    )
    parser.add_argument(
        "domain",
        help="Domain to look up (e.g. example.com)",
    )
    parser.add_argument(
        "--crawl",
        default=None,
        help=(
            "Specific CC crawl ID (e.g. cc-main-2025-nov). "
            "Default: tries most recent crawls."
        ),
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Directory for caching CC graph data (default: ./cc_cache/).",
    )
    parser.add_argument(
        "--max-download-mb",
        type=int,
        default=50,
        help="Max MB to download from CC per crawl (default: 50).",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        default=False,
        help="Output JSON (default: human-readable text).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    start = time.perf_counter()

    metrics = get_domain_metrics(
        domain=args.domain,
        crawl_id=args.crawl,
        cache_dir=args.cache_dir,
        max_download_bytes=args.max_download_mb * 1024 * 1024,
    )

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    result = CCGraphResult(
        domain=_normalize_domain(args.domain),
        metrics=metrics,
        response_time_ms=elapsed_ms,
        error=metrics.error,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        if metrics.error:
            print(f"Error: {metrics.error}", file=sys.stderr)
            return 1

        # Print the fields the v3.42.10 dataclass actually carries. The old
        # in_degree / out_degree / pagerank_estimate fields were deleted in that
        # rewrite (the quarterly domain-ranks table has no degree columns), and
        # printing them made every SUCCESSFUL lookup die with AttributeError.
        print(f"\n=== Common Crawl Host Graph: {metrics.domain} ===")
        print(f"  Crawl:                     {metrics.crawl_id}")
        print(f"  Harmonic centrality:       {metrics.harmonic_centrality:,.1f}")
        print(f"  Harmonic centrality rank:  {metrics.harmonic_centrality_rank:,}")
        print(f"  PageRank:                  {metrics.pagerank:.3e}")
        print(f"  PageRank rank:             {metrics.pagerank_rank:,}")
        print(f"  Hosts under domain:        {metrics.n_hosts:,}")
        if metrics.scanned_to_rank:
            print(f"  Scanned to rank:           {metrics.scanned_to_rank:,}")
        print(f"\n  Response time: {elapsed_ms}ms")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
