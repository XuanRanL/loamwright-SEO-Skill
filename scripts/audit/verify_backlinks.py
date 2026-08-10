#!/usr/bin/env python3
"""Backlink verification crawler.

Crawls known backlink source URLs to verify that links to the target
domain still exist, checks anchor text match, and detects nofollow status.

Usage:
    python -m scripts.audit.verify_backlinks backlinks.json --json
    python -m scripts.audit.verify_backlinks backlinks.json --concurrency 5 --timeout 20 --json
    echo '[{"source_url":"...", "target_url":"...", "anchor_text":"..."}]' | \\
        python -m scripts.audit.verify_backlinks --stdin --json

Input format (JSON list):
    [
      {
        "source_url": "https://external-site.com/page",
        "target_url": "https://your-site.com/linked-page",
        "anchor_text": "expected anchor"   // optional
      }
    ]

Output:
    JSON list of verification results per backlink entry.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx

from scripts._core.ssrf_guard import SSRFError, validate_url


def _check_ssrf(url: str) -> str | None:
    """Return a human-readable refusal reason, or None when the URL is safe.

    ``ssrf_guard.validate_url`` signals success by RETURNING a truthy
    ``ValidatedURL`` and signals failure by RAISING ``SSRFError``. Reading its
    return value as an error indicator inverts the check — that bug shipped here
    and silently marked every valid backlink "blocked", so this function has
    never verified a link. Keep the raise/return contract encapsulated here so
    no caller has to remember it. See
    tests/test_audit_backlink_sources_are_live.py.
    """
    try:
        validate_url(url, allow_http=True)
    except SSRFError as exc:
        return str(exc)
    except Exception as exc:  # malformed URL etc. — refuse rather than fetch
        return f"{type(exc).__name__}: {exc}"
    return None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CONCURRENCY = 3       # Polite crawling of external sites
DEFAULT_TIMEOUT = 20          # Per-request timeout (seconds)
DEFAULT_DELAY = 1.0           # Seconds between requests to the same domain
MAX_REDIRECTS = 5

_USER_AGENT = (
    "Mozilla/5.0 (compatible; XuanranSEO/3.4; +https://xuanran.dev/bot) "
    "BacklinkVerifier/1.0"
)

_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BacklinkInput:
    """A single backlink to verify."""

    source_url: str
    target_url: str
    anchor_text: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BacklinkInput:
        return cls(
            source_url=d["source_url"],
            target_url=d["target_url"],
            anchor_text=d.get("anchor_text"),
        )


@dataclass
class VerificationResult:
    """Verification outcome for a single backlink."""

    source_url: str
    target_url: str
    expected_anchor: Optional[str] = None
    status: str = "pending"       # found | not_found | error | blocked | timeout
    http_status: Optional[int] = None
    link_present: bool = False
    anchor_match: bool = False
    actual_anchor: Optional[str] = None
    rel_nofollow: bool = False
    rel_ugc: bool = False
    rel_sponsored: bool = False
    link_in_content: bool = False  # True if link is in <main>/<article>, not nav/footer
    error_message: Optional[str] = None
    response_time_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "target_url": self.target_url,
            "expected_anchor": self.expected_anchor,
            "status": self.status,
            "http_status": self.http_status,
            "link_present": self.link_present,
            "anchor_match": self.anchor_match,
            "actual_anchor": self.actual_anchor,
            "rel_nofollow": self.rel_nofollow,
            "rel_ugc": self.rel_ugc,
            "rel_sponsored": self.rel_sponsored,
            "link_in_content": self.link_in_content,
            "error_message": self.error_message,
            "response_time_ms": self.response_time_ms,
        }


@dataclass
class VerificationSummary:
    """Aggregate summary across all verified backlinks."""

    total: int = 0
    found: int = 0
    not_found: int = 0
    errors: int = 0
    nofollow_count: int = 0
    anchor_matches: int = 0
    anchor_mismatches: int = 0
    results: list[VerificationResult] = field(default_factory=list)
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "found": self.found,
            "not_found": self.not_found,
            "errors": self.errors,
            "nofollow_count": self.nofollow_count,
            "anchor_matches": self.anchor_matches,
            "anchor_mismatches": self.anchor_mismatches,
            "found_pct": round(self.found / self.total * 100, 1) if self.total else 0.0,
            "results": [r.to_dict() for r in self.results],
            "elapsed_ms": self.elapsed_ms,
        }


# ---------------------------------------------------------------------------
# HTML link extraction (lightweight, no BS4 dependency for speed)
# ---------------------------------------------------------------------------

# Regex to find <a> tags with href attributes.  Intentionally permissive
# to handle real-world messy HTML.
_A_TAG_RE = re.compile(
    r"<a\s[^>]*?href\s*=\s*[\"']([^\"']*?)[\"'][^>]*?>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)

_REL_RE = re.compile(r"\brel\s*=\s*[\"']([^\"']*)[\"']", re.IGNORECASE)

# Content region detection: prefer <main>, fall back to <article>, then full body.
_MAIN_RE = re.compile(r"<main[\s>].*?</main>", re.IGNORECASE | re.DOTALL)
_ARTICLE_RE = re.compile(r"<article[\s>].*?</article>", re.IGNORECASE | re.DOTALL)


def _normalize_url(href: str, base_url: str) -> str:
    """Resolve a potentially relative href against a base URL and normalize."""
    resolved = urljoin(base_url, href)
    # Strip fragment
    parsed = urlparse(resolved)
    normalized = parsed._replace(fragment="").geturl()
    return normalized.rstrip("/")


def _normalize_for_compare(url: str) -> str:
    """Normalize a URL for comparison (lowercase, no trailing slash, no fragment)."""
    parsed = urlparse(url.lower())
    return parsed._replace(fragment="").geturl().rstrip("/")


def _extract_links(
    html: str,
    base_url: str,
    target_url: str,
) -> list[dict[str, Any]]:
    """Find all <a> tags whose href matches the target URL.

    Returns a list of dicts with: href, anchor_text, rel, in_content.
    """
    target_normalized = _normalize_for_compare(target_url)
    target_domain = urlparse(target_url).netloc.lower()

    # Determine content region
    main_match = _MAIN_RE.search(html)
    article_match = _ARTICLE_RE.search(html)
    content_region: Optional[str] = None
    if main_match:
        content_region = main_match.group()
    elif article_match:
        content_region = article_match.group()

    matches: list[dict[str, Any]] = []

    for m in _A_TAG_RE.finditer(html):
        href_raw = m.group(1)
        anchor_html = m.group(2)
        full_tag = m.group(0)

        # Resolve href
        try:
            href_resolved = _normalize_url(href_raw, base_url)
        except Exception:
            continue

        href_normalized = _normalize_for_compare(href_resolved)

        # Check if this link points to our target
        # Match exactly or match domain (for cases where target_url might differ slightly)
        is_match = False
        if href_normalized == target_normalized:
            is_match = True
        elif urlparse(href_resolved).netloc.lower() == target_domain:
            # Same domain -- partial match (path might differ due to trailing slash, etc.)
            target_path = urlparse(target_url).path.rstrip("/").lower()
            href_path = urlparse(href_resolved).path.rstrip("/").lower()
            if target_path and target_path == href_path:
                is_match = True
            elif not target_path and not href_path:
                # Both are root
                is_match = True

        if not is_match:
            continue

        # Extract anchor text (strip HTML tags)
        anchor_text = re.sub(r"<[^>]+>", "", anchor_html).strip()

        # Extract rel attribute from the full tag
        rel_match = _REL_RE.search(full_tag)
        rel_value = rel_match.group(1).lower() if rel_match else ""

        # Determine if link is in content region
        in_content = False
        if content_region and full_tag in content_region:
            in_content = True

        matches.append({
            "href": href_resolved,
            "anchor_text": anchor_text,
            "rel": rel_value,
            "in_content": in_content,
        })

    return matches


# ---------------------------------------------------------------------------
# Single-URL verification
# ---------------------------------------------------------------------------


async def _verify_single(
    backlink: BacklinkInput,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    domain_delays: dict[str, float],
    delay: float,
) -> VerificationResult:
    """Verify a single backlink entry."""
    result = VerificationResult(
        source_url=backlink.source_url,
        target_url=backlink.target_url,
        expected_anchor=backlink.anchor_text,
    )

    # SSRF guard
    ssrf_err = _check_ssrf(backlink.source_url)
    if ssrf_err is not None:
        result.status = "blocked"
        result.error_message = f"SSRF guard blocked: {ssrf_err}"
        return result

    source_domain = urlparse(backlink.source_url).netloc.lower()

    async with semaphore:
        # Per-domain politeness delay
        now = time.monotonic()
        last_hit = domain_delays.get(source_domain, 0.0)
        wait = max(0.0, delay - (now - last_hit))
        if wait > 0:
            await asyncio.sleep(wait)
        domain_delays[source_domain] = time.monotonic()

        start = time.perf_counter()
        try:
            response = await client.get(
                backlink.source_url,
                headers=_HEADERS,
                follow_redirects=True,
            )
            elapsed = int((time.perf_counter() - start) * 1000)
            result.response_time_ms = elapsed
            result.http_status = response.status_code

            if response.status_code >= 400:
                result.status = "error"
                result.error_message = f"HTTP {response.status_code}"
                return result

            html = response.text

        except httpx.TimeoutException:
            result.status = "timeout"
            result.error_message = "Request timed out"
            result.response_time_ms = int((time.perf_counter() - start) * 1000)
            return result
        except httpx.HTTPError as exc:
            result.status = "error"
            result.error_message = str(exc)[:200]
            result.response_time_ms = int((time.perf_counter() - start) * 1000)
            return result

    # Search for the target link in the HTML
    found_links = _extract_links(html, backlink.source_url, backlink.target_url)

    if not found_links:
        result.status = "not_found"
        result.link_present = False
        return result

    # Use the first match (or the one in content if available)
    best = found_links[0]
    for link in found_links:
        if link["in_content"]:
            best = link
            break

    result.status = "found"
    result.link_present = True
    result.actual_anchor = best["anchor_text"]
    result.link_in_content = best["in_content"]

    # Parse rel attributes
    rel_tokens = best["rel"].split()
    result.rel_nofollow = "nofollow" in rel_tokens
    result.rel_ugc = "ugc" in rel_tokens
    result.rel_sponsored = "sponsored" in rel_tokens

    # Anchor text comparison
    if backlink.anchor_text:
        expected_lower = backlink.anchor_text.strip().lower()
        actual_lower = (best["anchor_text"] or "").strip().lower()
        result.anchor_match = expected_lower == actual_lower
    else:
        # No expected anchor -- skip comparison, always "match"
        result.anchor_match = True

    return result


# ---------------------------------------------------------------------------
# Batch verification
# ---------------------------------------------------------------------------


async def _verify_batch(
    backlinks: list[BacklinkInput],
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout: int = DEFAULT_TIMEOUT,
    delay: float = DEFAULT_DELAY,
) -> list[VerificationResult]:
    """Verify a batch of backlinks with controlled concurrency."""
    semaphore = asyncio.Semaphore(concurrency)
    domain_delays: dict[str, float] = {}

    async with httpx.AsyncClient(
        timeout=timeout,
        max_redirects=MAX_REDIRECTS,
        follow_redirects=True,
    ) as client:
        tasks = [
            _verify_single(bl, client, semaphore, domain_delays, delay)
            for bl in backlinks
        ]
        results = await asyncio.gather(*tasks)

    return list(results)


def verify_backlinks(
    backlinks: list[BacklinkInput],
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout: int = DEFAULT_TIMEOUT,
    delay: float = DEFAULT_DELAY,
) -> VerificationSummary:
    """Verify a list of backlinks and produce a summary.

    This is the synchronous public API.  Internally uses asyncio for
    concurrent HTTP requests.
    """
    start = time.perf_counter()

    results = asyncio.run(
        _verify_batch(backlinks, concurrency, timeout, delay)
    )

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    summary = VerificationSummary(
        total=len(results),
        results=results,
        elapsed_ms=elapsed_ms,
    )

    for r in results:
        if r.status == "found":
            summary.found += 1
            if r.rel_nofollow:
                summary.nofollow_count += 1
            if r.anchor_match:
                summary.anchor_matches += 1
            elif r.expected_anchor:
                summary.anchor_mismatches += 1
        elif r.status == "not_found":
            summary.not_found += 1
        else:
            summary.errors += 1

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify_backlinks",
        description="Crawl known backlink URLs to verify link existence, anchor text, and nofollow status.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=None,
        help="JSON file with backlink entries (or use --stdin).",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        default=False,
        help="Read backlink JSON from stdin.",
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Max parallel requests (default: {DEFAULT_CONCURRENCY}).",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT}).",
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Min seconds between requests to the same domain (default: {DEFAULT_DELAY}).",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        default=False,
        help="Output JSON (default: human-readable text).",
    )
    return parser


def _load_input(file_path: Optional[Path], use_stdin: bool) -> list[BacklinkInput]:
    """Load and parse backlink input from file or stdin."""
    if use_stdin:
        raw = sys.stdin.read()
    elif file_path is not None:
        if not file_path.exists():
            raise SystemExit(f"Error: file not found: {file_path}")
        raw = file_path.read_text(encoding="utf-8")
    else:
        raise SystemExit("Error: provide a file path or use --stdin.")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Error: invalid JSON input: {exc}") from exc

    if not isinstance(data, list):
        raise SystemExit("Error: input must be a JSON array of backlink objects.")

    entries: list[BacklinkInput] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise SystemExit(f"Error: entry {i} is not an object.")
        if "source_url" not in item or "target_url" not in item:
            raise SystemExit(
                f"Error: entry {i} missing required fields 'source_url' and/or 'target_url'."
            )
        entries.append(BacklinkInput.from_dict(item))

    return entries


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    backlinks = _load_input(args.file, args.stdin)

    if not backlinks:
        if args.json:
            print(json.dumps({"total": 0, "results": [], "error": "No backlinks to verify."}))
        else:
            print("No backlinks to verify.")
        return 0

    print(f"Verifying {len(backlinks)} backlinks (concurrency={args.concurrency})...", file=sys.stderr)

    summary = verify_backlinks(
        backlinks,
        concurrency=args.concurrency,
        timeout=args.timeout,
        delay=args.delay,
    )

    if args.json:
        print(json.dumps(summary.to_dict(), indent=2, default=str))
    else:
        print(f"\n=== Backlink Verification Summary ===")
        print(f"  Total checked:     {summary.total}")
        print(f"  Found (live):      {summary.found}")
        print(f"  Not found:         {summary.not_found}")
        print(f"  Errors/timeouts:   {summary.errors}")
        print(f"  With nofollow:     {summary.nofollow_count}")
        if summary.anchor_matches or summary.anchor_mismatches:
            print(f"  Anchor matches:    {summary.anchor_matches}")
            print(f"  Anchor mismatches: {summary.anchor_mismatches}")
        print(f"  Elapsed:           {summary.elapsed_ms}ms")

        # Detail any issues
        issues = [r for r in summary.results if r.status != "found"]
        if issues:
            print(f"\n--- Issues ({len(issues)}) ---")
            for r in issues:
                label = r.status.upper()
                detail = r.error_message or "link not present on page"
                print(f"  [{label}] {r.source_url}")
                print(f"           target: {r.target_url}")
                print(f"           reason: {detail}")

        mismatches = [r for r in summary.results if r.status == "found" and not r.anchor_match and r.expected_anchor]
        if mismatches:
            print(f"\n--- Anchor Mismatches ({len(mismatches)}) ---")
            for r in mismatches:
                print(f"  {r.source_url}")
                print(f"    expected: {r.expected_anchor!r}")
                print(f"    actual:   {r.actual_anchor!r}")

        nofollows = [r for r in summary.results if r.status == "found" and r.rel_nofollow]
        if nofollows:
            print(f"\n--- Nofollow Links ({len(nofollows)}) ---")
            for r in nofollows:
                rel_parts: list[str] = []
                if r.rel_nofollow:
                    rel_parts.append("nofollow")
                if r.rel_ugc:
                    rel_parts.append("ugc")
                if r.rel_sponsored:
                    rel_parts.append("sponsored")
                print(f"  {r.source_url}  rel={','.join(rel_parts)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
