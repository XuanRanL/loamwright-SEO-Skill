"""
scripts/validate/link_resolver.py — HTTP HEAD check for URL list (citations / outbound links).

For each URL:
  - SSRF validate
  - HTTP HEAD (with GET fallback if HEAD blocked)
  - Track redirect chain
  - Identify problematic patterns:
      * 404 / 410 / 5xx
      * 302 chain length > 3
      * grounding-api-redirect (Google AI sourced)
      * cdn.openai.com / cdn.anthropic.com (LLM-cached, unreliable)
      * bit.ly / t.co / shortened (resolve canonical)

Per v3.2 / scripts/validate/cite_scorer.py:
  All citation URLs must return 200 OK, max redirect length ≤2, no grounding-redirect.

CLI:
    python -m scripts.validate.link_resolver https://example.com/page
    python -m scripts.validate.link_resolver url1 url2 url3 --json
    python -m scripts.validate.link_resolver --from-file references.txt --concurrent 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from scripts._core.ssrf_guard import validate_url, SSRFError


GROUNDING_PATTERNS = [
    "grounding-api-redirect",
    "google.com/url?",
    "googleweblight.com",
]

UNRELIABLE_HOSTS = {
    "cdn.openai.com",       # LLM-cached content; unreliable as primary source
    "files.anthropic.com",
    "cdn.cohere.ai",
}

SHORTENER_HOSTS = {
    "bit.ly", "t.co", "goo.gl", "tinyurl.com", "is.gd", "buff.ly",
    "ow.ly", "rebrand.ly", "tiny.cc", "shorturl.at",
}


@dataclass
class LinkCheckResult:
    url: str
    final_url: str
    status: int                            # 0 if network error
    is_resolvable: bool
    redirect_count: int
    redirect_chain: list[str] = field(default_factory=list)
    is_grounding_redirect: bool = False
    is_unreliable_host: bool = False
    is_shortener: bool = False
    elapsed_ms: int = 0
    error: str | None = None
    content_type: str = ""
    is_pdf: bool = False
    is_html: bool = False


async def _check_single(url: str, *, timeout: float = 10.0) -> LinkCheckResult:
    """Async single URL check."""
    result = LinkCheckResult(
        url=url, final_url=url, status=0, is_resolvable=False,
        redirect_count=0,
    )
    t0 = time.time()

    # SSRF
    try:
        validate_url(url, allow_http=False, resolve_dns=True)
    except SSRFError as e:
        result.error = f"SSRF: {e}"
        result.elapsed_ms = int((time.time() - t0) * 1000)
        return result

    try:
        import httpx
    except ImportError:
        result.error = "httpx not installed"
        return result

    # Patterns to check before fetch
    for p in GROUNDING_PATTERNS:
        if p in url:
            result.is_grounding_redirect = True
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    if host in UNRELIABLE_HOSTS:
        result.is_unreliable_host = True
    if host in SHORTENER_HOSTS:
        result.is_shortener = True

    headers = {
        "User-Agent": "XuanranSEO/3.2.0 LinkResolver",
        "Accept": "*/*",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            current_url = url
            chain = []
            status = 0
            content_type = ""

            for _ in range(10):  # max 10 redirects
                # Try HEAD first
                try:
                    r = await client.head(current_url, headers=headers)
                except httpx.HTTPError:
                    # HEAD might be blocked; fall back to GET
                    r = await client.get(current_url, headers=headers)

                status = r.status_code
                content_type = r.headers.get("content-type", "").lower()

                if 300 <= status < 400:
                    loc = r.headers.get("location", "")
                    if not loc:
                        break
                    from urllib.parse import urljoin
                    if loc.startswith("/"):
                        loc = urljoin(current_url, loc)
                    # SSRF on redirect target
                    try:
                        validate_url(loc, allow_http=False, resolve_dns=True)
                    except SSRFError:
                        result.error = "Redirect SSRF"
                        break
                    # Detect grounding-redirect mid-chain
                    for p in GROUNDING_PATTERNS:
                        if p in loc:
                            result.is_grounding_redirect = True
                    chain.append(current_url)
                    current_url = loc
                    continue
                break

            result.status = status
            result.final_url = current_url
            result.redirect_chain = chain
            result.redirect_count = len(chain)
            result.content_type = content_type
            result.is_html = "text/html" in content_type or "application/xhtml" in content_type
            result.is_pdf = "application/pdf" in content_type
            result.is_resolvable = 200 <= status < 400

    except httpx.TimeoutException:
        result.error = "Timeout"
    except httpx.HTTPError as e:
        result.error = f"HTTP error: {e}"
    except Exception as e:
        result.error = f"Unexpected: {e}"

    result.elapsed_ms = int((time.time() - t0) * 1000)
    return result


async def check_many_async(
    urls: list[str], *, concurrent: int = 10, timeout: float = 10.0
) -> list[LinkCheckResult]:
    """Check URLs concurrently with bounded parallelism."""
    semaphore = asyncio.Semaphore(concurrent)

    async def _bounded(u: str) -> LinkCheckResult:
        async with semaphore:
            return await _check_single(u, timeout=timeout)

    return await asyncio.gather(*[_bounded(u) for u in urls])


def check_many(urls: list[str], *, concurrent: int = 10, timeout: float = 10.0) -> list[LinkCheckResult]:
    """Sync wrapper."""
    return asyncio.run(check_many_async(urls, concurrent=concurrent, timeout=timeout))


def check_one(url: str, *, timeout: float = 10.0) -> LinkCheckResult:
    """Sync single-URL check."""
    return asyncio.run(_check_single(url, timeout=timeout))


def main() -> int:
    ap = argparse.ArgumentParser(description="HTTP link resolver / health checker")
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--from-file", type=Path, help="File with URLs (one per line)")
    ap.add_argument("--concurrent", type=int, default=10)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    urls = list(args.urls)
    if args.from_file and args.from_file.exists():
        urls.extend(args.from_file.read_text(encoding="utf-8").splitlines())
    urls = [u.strip() for u in urls if u.strip() and not u.startswith("#")]
    if not urls:
        print("No URLs to check", file=sys.stderr)
        return 2

    results = check_many(urls, concurrent=args.concurrent, timeout=args.timeout)

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))
    else:
        ok = sum(1 for r in results if r.is_resolvable and not r.is_grounding_redirect)
        total = len(results)
        print(f"Checked {total} URLs · {ok} OK / {total - ok} problematic")
        print()
        for r in results:
            if r.is_resolvable and not r.is_grounding_redirect:
                icon = "✓"
            elif r.is_grounding_redirect:
                icon = "⚠"
            else:
                icon = "✗"
            print(f"  {icon} [{r.status}] {r.url}")
            if r.redirect_chain:
                print(f"      → {len(r.redirect_chain)} redirect(s) → {r.final_url}")
            if r.is_grounding_redirect:
                print(f"      ⚠️ Grounding redirect detected (rejected for citations)")
            if r.is_unreliable_host:
                print(f"      ⚠️ Unreliable host (LLM-cached content)")
            if r.is_shortener:
                print(f"      ⚠️ URL shortener; resolved to {r.final_url}")
            if r.error:
                print(f"      ERROR: {r.error}")
    overall_ok = all(r.is_resolvable and not r.is_grounding_redirect for r in results)
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
