"""
scripts/audit/crawl_site.py — BFS website crawler for SEO auditing.

Crawls a site breadth-first from a seed URL, following internal links only.
Collects per-page SEO signals: status, title, word count, response time, etc.

Features:
    - Async BFS via httpx.AsyncClient + semaphore concurrency control
    - robots.txt respect (configurable)
    - SSRF protection via scripts._core.ssrf_guard
    - URL normalization (lowercase host, strip UTM, sort params)
    - Cost ledger integration (rate tracking, zero cost)
    - Graceful error handling (never crashes on bad pages)

Usage (CLI):
    python -m scripts.audit.crawl_site https://example.com --max-pages 100 --json
    python -m scripts.audit.crawl_site https://example.com -o crawl_results.json

Usage (Python):
    from scripts.audit.crawl_site import crawl_site, CrawlConfig
    import asyncio

    config = CrawlConfig(max_pages=100, concurrent=5, delay=1.0)
    results = asyncio.run(crawl_site("https://example.com", config))
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Final
from urllib.parse import (
    ParseResult,
    parse_qs,
    urlencode,
    urljoin,
    urlparse,
    urlunparse,
)
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from scripts._core.cost_ledger import log as cost_log
from scripts._core.ssrf_guard import SSRFError, validate_url

# ─── Constants ────────────────────────────────────────────────────────

_USER_AGENT: Final[str] = (
    "XuanranSEOBot/1.0 (+https://github.com/xuanran-seo; SEO audit crawler)"
)

# UTM and tracking params to strip during normalization
_STRIP_PARAMS: Final[set[str]] = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "gclsrc",
    "msclkid",
    "dclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "_ga",
    "_gl",
}

# Extensions to skip (non-HTML resources)
_SKIP_EXTENSIONS: Final[set[str]] = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".avif",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".css", ".js", ".map", ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".ico", ".xml", ".rss", ".atom", ".json", ".jsonld",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
}

# Default ports per scheme
_DEFAULT_PORTS: Final[dict[str, int]] = {"http": 80, "https": 443}


# ─── Data types ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class CrawlConfig:
    """Configuration for the site crawl."""

    max_pages: int = 500
    concurrent: int = 5
    delay: float = 1.0
    timeout: float = 30.0
    respect_robots: bool = True
    user_agent: str = _USER_AGENT
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class PageResult:
    """Crawl result for a single page."""

    url: str
    status_code: int
    content_type: str
    redirect_chain: list[str] = field(default_factory=list)
    word_count: int = 0
    title: str = ""
    response_time_ms: float = 0.0
    error: str | None = None
    crawled_at: str = ""

    def to_dict(self) -> dict[str, object]:
        """Convert to JSON-serializable dict."""
        d: dict[str, object] = {
            "url": self.url,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "redirect_chain": self.redirect_chain,
            "word_count": self.word_count,
            "title": self.title,
            "response_time_ms": round(self.response_time_ms, 2),
            "crawled_at": self.crawled_at,
        }
        if self.error:
            d["error"] = self.error
        return d


# ─── URL normalization ────────────────────────────────────────────────


def normalize_url(url: str, base_url: str | None = None) -> str | None:
    """Normalize a URL for deduplication.

    - Resolve relative URLs against base_url
    - Lowercase scheme and host
    - Strip default ports (80 for http, 443 for https)
    - Remove UTM/tracking params
    - Sort remaining query params
    - Strip fragments

    Returns None if the URL is invalid or non-HTTP(S).
    """
    if base_url:
        url = urljoin(base_url, url)

    try:
        parsed: ParseResult = urlparse(url)
    except Exception:
        return None

    scheme: str = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return None

    host: str | None = parsed.hostname
    if not host:
        return None
    host = host.lower()

    # Strip default port
    port: int | None = parsed.port
    if port == _DEFAULT_PORTS.get(scheme):
        port = None

    # Reconstruct netloc
    netloc: str = host
    if port is not None:
        netloc = f"{host}:{port}"
    if parsed.username:
        userinfo: str = parsed.username
        if parsed.password:
            userinfo = f"{userinfo}:{parsed.password}"
        netloc = f"{userinfo}@{netloc}"

    # Path: ensure at least "/"
    path: str = parsed.path or "/"
    # Remove trailing slash for non-root paths to deduplicate
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Query: strip tracking params, sort remainder
    query: str = ""
    if parsed.query:
        params: dict[str, list[str]] = parse_qs(
            parsed.query, keep_blank_values=True,
        )
        filtered: dict[str, list[str]] = {
            k: v for k, v in params.items() if k.lower() not in _STRIP_PARAMS
        }
        if filtered:
            query = urlencode(
                sorted(
                    ((k, vi) for k, vlist in filtered.items() for vi in vlist),
                    key=lambda kv: (kv[0].lower(), kv[1]),
                ),
            )

    # Strip fragment entirely
    return urlunparse((scheme, netloc, path, "", query, ""))


def is_internal_url(url: str, seed_host: str) -> bool:
    """Check whether a URL belongs to the same domain as the seed."""
    try:
        parsed: ParseResult = urlparse(url)
    except Exception:
        return False
    host: str | None = parsed.hostname
    if not host:
        return False
    return host.lower() == seed_host


def should_skip_extension(url: str) -> bool:
    """Return True if the URL path has a non-HTML extension."""
    try:
        path: str = urlparse(url).path.lower()
    except Exception:
        return True
    for ext in _SKIP_EXTENSIONS:
        if path.endswith(ext):
            return True
    return False


# ─── Robots.txt handling ──────────────────────────────────────────────


async def fetch_robots_txt(
    client: httpx.AsyncClient,
    seed_url: str,
) -> RobotFileParser:
    """Fetch and parse robots.txt for the seed domain."""
    parsed: ParseResult = urlparse(seed_url)
    robots_url: str = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    rp: RobotFileParser = RobotFileParser()
    rp.set_url(robots_url)

    try:
        resp: httpx.Response = await client.get(
            robots_url,
            follow_redirects=True,
            timeout=10.0,
        )
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        else:
            # If robots.txt is missing or errored, allow everything
            rp.allow_all = True  # type: ignore[attr-defined]
    except (httpx.HTTPError, Exception):
        # Network error fetching robots.txt — allow everything
        rp.allow_all = True  # type: ignore[attr-defined]

    return rp


def is_allowed_by_robots(
    rp: RobotFileParser,
    url: str,
    user_agent: str,
) -> bool:
    """Check if the given URL is allowed by robots.txt rules."""
    if getattr(rp, "allow_all", False):
        return True
    return rp.can_fetch(user_agent, url)


# ─── HTML parsing ─────────────────────────────────────────────────────


def extract_links(html: str, base_url: str) -> list[str]:
    """Extract all href links from <a> tags in HTML content."""
    soup: BeautifulSoup = BeautifulSoup(html, "html.parser")
    links: list[str] = []

    for anchor in soup.find_all("a", href=True):
        href: str = anchor["href"].strip()
        if not href:
            continue
        # Skip non-HTTP schemes and fragment-only anchors
        if re.match(r"^(javascript|mailto|tel|data|ftp):", href, re.IGNORECASE):
            continue
        if href.startswith("#"):
            continue

        normalized: str | None = normalize_url(href, base_url=base_url)
        if normalized:
            links.append(normalized)

    return links


def extract_title(html: str) -> str:
    """Extract the <title> text from HTML."""
    soup: BeautifulSoup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        return title_tag.string.strip()
    return ""


def count_words(html: str) -> int:
    """Count visible text words in the HTML body."""
    soup: BeautifulSoup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for element in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        element.decompose()

    text: str = soup.get_text(separator=" ", strip=True)
    words: list[str] = text.split()
    return len(words)


# ─── Core crawler ─────────────────────────────────────────────────────


async def _crawl_page(
    client: httpx.AsyncClient,
    url: str,
    config: CrawlConfig,
    seed_host: str,
) -> tuple[PageResult, list[str]]:
    """Fetch a single page and return the result plus discovered internal links.

    Args:
        client: Shared httpx async client.
        url: URL to crawl.
        config: Crawl configuration.
        seed_host: Hostname of the seed URL (for internal-link filtering).

    Returns:
        Tuple of (PageResult, list of discovered internal link URLs).
    """
    crawled_at: str = datetime.now(timezone.utc).isoformat()
    discovered_links: list[str] = []

    # SSRF gate
    try:
        validate_url(url, allow_http=True, resolve_dns=True)
    except SSRFError as e:
        return (
            PageResult(
                url=url,
                status_code=0,
                content_type="",
                error=f"SSRF blocked: {e}",
                crawled_at=crawled_at,
            ),
            [],
        )

    start_time: float = time.perf_counter()

    try:
        resp: httpx.Response = await client.get(
            url,
            follow_redirects=True,
            timeout=config.timeout,
        )
        elapsed_ms: float = (time.perf_counter() - start_time) * 1000.0

        # Build redirect chain
        redirect_chain: list[str] = []
        if resp.history:
            redirect_chain = [str(r.url) for r in resp.history]

        content_type: str = (
            resp.headers.get("content-type", "").split(";")[0].strip()
        )

        # Log to cost ledger (free, but rate-tracked)
        cost_log(
            actual_cost=Decimal("0"),
            model="crawl_site",
            endpoint="GET",
            extra={"url": url, "status": resp.status_code},
        )

        title: str = ""
        word_count: int = 0

        # Parse HTML content for metadata + link discovery
        if "html" in content_type.lower() and resp.status_code < 400:
            html_body: str = resp.text
            title = extract_title(html_body)
            word_count = count_words(html_body)

            # Discover internal links
            all_links: list[str] = extract_links(html_body, str(resp.url))
            for link in all_links:
                if is_internal_url(link, seed_host) and not should_skip_extension(link):
                    discovered_links.append(link)

        return (
            PageResult(
                url=str(resp.url),
                status_code=resp.status_code,
                content_type=content_type,
                redirect_chain=redirect_chain,
                word_count=word_count,
                title=title,
                response_time_ms=elapsed_ms,
                crawled_at=crawled_at,
            ),
            discovered_links,
        )

    except httpx.TimeoutException:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return (
            PageResult(
                url=url,
                status_code=0,
                content_type="",
                response_time_ms=elapsed_ms,
                error="Timeout",
                crawled_at=crawled_at,
            ),
            [],
        )
    except httpx.ConnectError as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return (
            PageResult(
                url=url,
                status_code=0,
                content_type="",
                response_time_ms=elapsed_ms,
                error=f"Connection error: {e}",
                crawled_at=crawled_at,
            ),
            [],
        )
    except httpx.HTTPError as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return (
            PageResult(
                url=url,
                status_code=0,
                content_type="",
                response_time_ms=elapsed_ms,
                error=f"HTTP error: {type(e).__name__}: {e}",
                crawled_at=crawled_at,
            ),
            [],
        )
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return (
            PageResult(
                url=url,
                status_code=0,
                content_type="",
                response_time_ms=elapsed_ms,
                error=f"Unexpected error: {type(e).__name__}: {e}",
                crawled_at=crawled_at,
            ),
            [],
        )


async def crawl_site(
    seed_url: str,
    config: CrawlConfig | None = None,
) -> list[PageResult]:
    """BFS crawl a website starting from seed_url.

    Crawls internal links breadth-first up to config.max_pages. Each page's
    metadata (status, title, word count, response time, redirect chain) is
    recorded. External links, non-HTML resources, and robots.txt-blocked
    paths are skipped.

    Args:
        seed_url: Starting URL (must be HTTP or HTTPS).
        config: Crawl configuration. Uses CrawlConfig defaults if None.

    Returns:
        List of PageResult for every page attempted.

    Raises:
        ValueError: If seed_url is invalid.
        SSRFError: If seed_url resolves to a blocked IP range.
    """
    if config is None:
        config = CrawlConfig()

    # Normalize seed
    normalized_seed: str | None = normalize_url(seed_url)
    if not normalized_seed:
        raise ValueError(f"Invalid seed URL: {seed_url}")

    parsed_seed: ParseResult = urlparse(normalized_seed)
    seed_host: str = (parsed_seed.hostname or "").lower()

    if not seed_host:
        raise ValueError(f"Cannot determine host from seed URL: {seed_url}")

    # SSRF validate the seed URL
    validate_url(seed_url, allow_http=True, resolve_dns=True)

    # BFS state
    queue: deque[str] = deque()
    visited: set[str] = set()
    results: list[PageResult] = []

    queue.append(normalized_seed)
    visited.add(normalized_seed)

    # Concurrency control
    semaphore: asyncio.Semaphore = asyncio.Semaphore(config.concurrent)

    headers: dict[str, str] = {
        "User-Agent": config.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        # Accept-Encoding intentionally NOT set: httpx advertises only codecs it
        # can decode (br requires the brotli package). Hardcoding "br" without
        # the decoder turns every Brotli response into mojibake — zero links,
        # empty titles (project-delta audit, 2026-07-18).
    }
    if config.extra_headers:
        headers.update(config.extra_headers)

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=False,  # per-request for redirect chain tracking
        timeout=config.timeout,
        limits=httpx.Limits(
            max_connections=config.concurrent * 2,
            max_keepalive_connections=config.concurrent,
        ),
    ) as client:
        # Fetch and parse robots.txt
        rp: RobotFileParser | None = None
        if config.respect_robots:
            rp = await fetch_robots_txt(client, seed_url)

        # BFS loop
        while queue and len(results) < config.max_pages:
            # Determine batch size
            remaining: int = config.max_pages - len(results)
            batch_size: int = min(config.concurrent, len(queue), remaining)

            batch_urls: list[str] = []
            for _ in range(batch_size):
                if not queue:
                    break
                batch_urls.append(queue.popleft())

            # Filter by robots.txt
            allowed_urls: list[str] = []
            for url in batch_urls:
                if rp and not is_allowed_by_robots(rp, url, config.user_agent):
                    results.append(PageResult(
                        url=url,
                        status_code=0,
                        content_type="",
                        error="Blocked by robots.txt",
                        crawled_at=datetime.now(timezone.utc).isoformat(),
                    ))
                else:
                    allowed_urls.append(url)

            if not allowed_urls:
                continue

            # Crawl batch concurrently with semaphore + delay
            async def _bounded_crawl(u: str) -> tuple[PageResult, list[str]]:
                async with semaphore:
                    result: tuple[PageResult, list[str]] = await _crawl_page(
                        client, u, config, seed_host,
                    )
                    # Politeness delay between requests
                    await asyncio.sleep(config.delay)
                    return result

            tasks: list[asyncio.Task[tuple[PageResult, list[str]]]] = [
                asyncio.create_task(_bounded_crawl(u))
                for u in allowed_urls
            ]
            batch_results: list[tuple[PageResult, list[str]]] = (
                await asyncio.gather(*tasks)
            )

            for page_result, links in batch_results:
                results.append(page_result)

                # Enqueue newly discovered internal links
                for link in links:
                    normalized_link: str | None = normalize_url(link)
                    if normalized_link and normalized_link not in visited:
                        visited.add(normalized_link)
                        queue.append(normalized_link)

            # Progress to stderr
            print(
                f"\r  Crawled: {len(results)}/{config.max_pages} | "
                f"Queue: {len(queue)} | Visited: {len(visited)}",
                end="",
                file=sys.stderr,
                flush=True,
            )

        # Final newline
        print("", file=sys.stderr)

    return results


# ─── CLI ──────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    ap: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="crawl_site",
        description=(
            "BFS website crawler for SEO auditing. Crawls internal links "
            "and collects per-page metadata (status, title, word count, "
            "response time, redirect chain)."
        ),
    )
    ap.add_argument(
        "url",
        help="Seed URL to start crawling from (must be HTTP or HTTPS)",
    )
    ap.add_argument(
        "--max-pages",
        type=int,
        default=500,
        help="Maximum number of pages to crawl (default: 500)",
    )
    ap.add_argument(
        "--concurrent",
        type=int,
        default=5,
        help="Maximum concurrent requests (default: 5)",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay in seconds between requests per slot (default: 1.0)",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout in seconds per page request (default: 30)",
    )
    ap.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output file path for JSON results",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print JSON results to stdout",
    )
    # Robots.txt control
    robots_group = ap.add_mutually_exclusive_group()
    robots_group.add_argument(
        "--respect-robots",
        action="store_true",
        default=True,
        dest="respect_robots",
        help="Respect robots.txt rules (default)",
    )
    robots_group.add_argument(
        "--ignore-robots",
        action="store_false",
        dest="respect_robots",
        help="Ignore robots.txt rules",
    )
    ap.add_argument(
        "--header", "-H",
        action="append",
        default=[],
        metavar="NAME:VALUE",
        help="Extra HTTP header (e.g. -H 'X-Token:abc'). Repeatable.",
    )

    return ap


def main() -> int:
    """CLI entry point."""
    parser: argparse.ArgumentParser = build_parser()
    args: argparse.Namespace = parser.parse_args()

    # Validate inputs
    if args.max_pages < 1:
        print("Error: --max-pages must be >= 1", file=sys.stderr)
        return 1
    if args.concurrent < 1:
        print("Error: --concurrent must be >= 1", file=sys.stderr)
        return 1
    if args.delay < 0:
        print("Error: --delay must be >= 0", file=sys.stderr)
        return 1
    if args.timeout <= 0:
        print("Error: --timeout must be > 0", file=sys.stderr)
        return 1

    # Must specify at least one output mode
    if not args.json_output and not args.output:
        print(
            "Error: specify --json (stdout) or --output/-o <file> for results",
            file=sys.stderr,
        )
        return 1

    extra_headers: dict[str, str] = {}
    for h in args.header:
        if ":" in h:
            k, v = h.split(":", 1)
            extra_headers[k.strip()] = v.strip()

    config: CrawlConfig = CrawlConfig(
        max_pages=args.max_pages,
        concurrent=args.concurrent,
        delay=args.delay,
        timeout=args.timeout,
        respect_robots=args.respect_robots,
        extra_headers=extra_headers,
    )

    print(
        f"Starting BFS crawl of {args.url}\n"
        f"  max_pages={config.max_pages}, concurrent={config.concurrent}, "
        f"delay={config.delay}s, timeout={config.timeout}s\n"
        f"  robots.txt: {'respect' if config.respect_robots else 'ignore'}",
        file=sys.stderr,
    )

    try:
        results: list[PageResult] = asyncio.run(crawl_site(args.url, config))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except SSRFError as e:
        print(f"SSRF Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCrawl interrupted by user.", file=sys.stderr)
        return 130

    # Build JSON output
    output_data: list[dict[str, object]] = [r.to_dict() for r in results]

    # Summary stats to stderr
    total: int = len(results)
    ok_count: int = sum(1 for r in results if 200 <= r.status_code < 300)
    redirect_count: int = sum(1 for r in results if 300 <= r.status_code < 400)
    client_err: int = sum(1 for r in results if 400 <= r.status_code < 500)
    server_err: int = sum(1 for r in results if r.status_code >= 500)
    failed: int = sum(1 for r in results if r.status_code == 0 and r.error)
    timed_pages: int = sum(1 for r in results if r.response_time_ms > 0)
    avg_time: float = (
        sum(r.response_time_ms for r in results if r.response_time_ms > 0)
        / max(1, timed_pages)
    )

    print(
        f"\n{'=' * 60}\n"
        f"Crawl complete: {total} pages\n"
        f"  2xx: {ok_count} | 3xx: {redirect_count} | "
        f"4xx: {client_err} | 5xx: {server_err} | errors: {failed}\n"
        f"  Avg response time: {avg_time:.0f}ms\n"
        f"{'=' * 60}",
        file=sys.stderr,
    )

    # Write output
    json_str: str = json.dumps(output_data, indent=2, ensure_ascii=False)

    if args.json_output:
        print(json_str)

    if args.output:
        output_path: Path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_str, encoding="utf-8")
        print(f"Results written to: {output_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
