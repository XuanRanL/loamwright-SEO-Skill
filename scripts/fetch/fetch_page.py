"""
scripts/fetch/fetch_page.py — Direct HTTP GET with UA rotation + redirect tracking + SSRF.

For when we need raw HTML (and don't want to spend Tavily credits OR Tavily can't
render the page). This is Tier-1 of the 5-tier waterfall used by /init.

Features:
  - UA rotation (10 real browser UAs)
  - Follow redirects (max 10)
  - Track redirect chain (for SEO baseline)
  - SSRF validation
  - Optional Playwright/patchright fallback when JS rendering needed (separate script)
  - Content-Type sniffing

Output:
  FetchResult { url_final, status, body, headers, redirect_chain, fetch_ms }

CLI:
    python -m scripts.fetch.fetch_page https://example.com
    python -m scripts.fetch.fetch_page url --json
    python -m scripts.fetch.fetch_page url --save-body /tmp/page.html
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts._core.ssrf_guard import validate_url, SSRFError


USER_AGENTS = [
    # Chrome (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Chrome (macOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Firefox (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    # Firefox (Linux)
    "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
    # Safari (macOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    # Edge (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    # Mobile Safari (iPhone)
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1",
    # Mobile Chrome (Android)
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
]


@dataclass
class RedirectStep:
    from_url: str
    to_url: str
    status: int


@dataclass
class FetchResult:
    url_requested: str
    url_final: str
    status: int
    body: str
    body_truncated: bool
    headers: dict[str, str]
    redirect_chain: list[RedirectStep] = field(default_factory=list)
    fetch_ms: int = 0
    content_type: str = ""
    is_html: bool = False
    error: str | None = None
    grounding_redirect_detected: bool = False  # Google AI redirect path detected


GROUNDING_INDICATORS = [
    "grounding-api-redirect",
    "google.com/url?",
    "googleweblight.com",
]


def fetch(
    url: str,
    *,
    max_body_size: int = 2_000_000,    # 2 MB max
    timeout: float = 15.0,
    ua: str | None = None,
    follow_redirects: bool = True,
    custom_headers: dict | None = None,
) -> FetchResult:
    """Fetch a URL with SSRF guard, UA rotation, redirect tracking.

    Args:
        url: Target URL.
        max_body_size: Max bytes of body to load.
        timeout: Per-request timeout in seconds.
        ua: Override User-Agent (otherwise randomized).
        follow_redirects: Default True.
        custom_headers: Extra headers.

    Returns:
        FetchResult with all metadata.
    """
    # SSRF
    try:
        validate_url(url, allow_http=True, resolve_dns=True)
    except SSRFError as e:
        return FetchResult(
            url_requested=url, url_final=url,
            status=0, body="", body_truncated=False, headers={},
            error=f"SSRF: {e}", fetch_ms=0,
        )

    try:
        import httpx
    except ImportError as e:
        return FetchResult(
            url_requested=url, url_final=url,
            status=0, body="", body_truncated=False, headers={},
            error=f"httpx not installed: {e}",
        )

    if not ua:
        ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        # Accept-Encoding intentionally NOT set: httpx advertises only codecs it
        # can decode (br requires the brotli package).
    }
    if custom_headers:
        headers.update(custom_headers)

    t0 = time.time()
    redirect_chain: list[RedirectStep] = []
    grounding_detected = False

    try:
        # Manual redirect handling (so we record the chain)
        if follow_redirects:
            client = httpx.Client(timeout=timeout, follow_redirects=False)
        else:
            client = httpx.Client(timeout=timeout, follow_redirects=False)

        current_url = url
        max_redirects = 10 if follow_redirects else 0
        response = None

        for _ in range(max_redirects + 1):
            try:
                response = client.get(current_url, headers=headers)
            except httpx.TimeoutException:
                client.close()
                return FetchResult(
                    url_requested=url, url_final=current_url,
                    status=0, body="", body_truncated=False, headers={},
                    redirect_chain=redirect_chain,
                    error="Timeout", fetch_ms=int((time.time() - t0) * 1000),
                )

            if any(ind in current_url for ind in GROUNDING_INDICATORS):
                grounding_detected = True

            if 300 <= response.status_code < 400 and follow_redirects:
                loc = response.headers.get("location", "")
                if not loc:
                    break
                # Resolve relative
                if loc.startswith("/"):
                    from urllib.parse import urlparse, urljoin
                    loc = urljoin(current_url, loc)
                # SSRF check redirect target
                try:
                    validate_url(loc, allow_http=True, resolve_dns=True)
                except SSRFError as e:
                    client.close()
                    return FetchResult(
                        url_requested=url, url_final=current_url,
                        status=response.status_code, body="", body_truncated=False,
                        headers=dict(response.headers),
                        redirect_chain=redirect_chain,
                        error=f"Redirect SSRF: {e}",
                        fetch_ms=int((time.time() - t0) * 1000),
                        grounding_redirect_detected=grounding_detected,
                    )
                redirect_chain.append(RedirectStep(
                    from_url=current_url, to_url=loc, status=response.status_code
                ))
                current_url = loc
                continue
            break

        client.close()
    except httpx.HTTPError as e:
        return FetchResult(
            url_requested=url, url_final=current_url,
            status=0, body="", body_truncated=False, headers={},
            redirect_chain=redirect_chain,
            error=str(e), fetch_ms=int((time.time() - t0) * 1000),
        )

    if response is None:
        return FetchResult(
            url_requested=url, url_final=current_url,
            status=0, body="", body_truncated=False, headers={},
            redirect_chain=redirect_chain,
            error="No response", fetch_ms=int((time.time() - t0) * 1000),
        )

    content_type = response.headers.get("content-type", "").lower()
    is_html = "text/html" in content_type or "application/xhtml" in content_type

    # Body (limit by size)
    raw_body = response.content[:max_body_size]
    body_truncated = len(response.content) > max_body_size

    try:
        body = raw_body.decode(response.encoding or "utf-8", errors="replace")
    except (LookupError, UnicodeDecodeError):
        body = raw_body.decode("utf-8", errors="replace")

    return FetchResult(
        url_requested=url,
        url_final=current_url,
        status=response.status_code,
        body=body,
        body_truncated=body_truncated,
        headers=dict(response.headers),
        redirect_chain=redirect_chain,
        fetch_ms=int((time.time() - t0) * 1000),
        content_type=content_type,
        is_html=is_html,
        grounding_redirect_detected=grounding_detected,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Direct HTTP fetch with SSRF + redirects")
    ap.add_argument("url")
    ap.add_argument("--max-size", type=int, default=2_000_000, help="Max body bytes")
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--no-follow", action="store_true", help="Don't follow redirects")
    ap.add_argument("--save-body", type=Path, help="Save body to file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = fetch(
        args.url, max_body_size=args.max_size, timeout=args.timeout,
        follow_redirects=not args.no_follow,
    )

    if args.save_body and r.body:
        args.save_body.write_text(r.body, encoding="utf-8")

    if args.json:
        out = asdict(r)
        if args.save_body or r.body_truncated:
            out["body"] = out["body"][:1000] + "..." if len(out["body"]) > 1000 else out["body"]
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"URL:       {r.url_requested}")
        print(f"Final URL: {r.url_final}")
        print(f"Status:    {r.status}")
        print(f"Time:      {r.fetch_ms} ms")
        print(f"Body size: {len(r.body)} chars{' (truncated)' if r.body_truncated else ''}")
        print(f"Type:      {r.content_type}  HTML: {r.is_html}")
        if r.grounding_redirect_detected:
            print(f"⚠️  Grounding redirect detected (Google AI redirect path)")
        if r.redirect_chain:
            print(f"Redirects ({len(r.redirect_chain)}):")
            for step in r.redirect_chain:
                print(f"  [{step.status}] {step.from_url} → {step.to_url}")
        if r.error:
            print(f"Error: {r.error}")
        elif r.body:
            print(f"\n--- First 500 chars of body ---")
            print(r.body[:500])

    return 0 if r.status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
