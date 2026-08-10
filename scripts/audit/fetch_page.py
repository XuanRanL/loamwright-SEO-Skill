#!/usr/bin/env python3
"""Fetch a web page with SSRF protection and redirect tracking.

Usage:
    python -m scripts.audit.fetch_page https://example.com
    python -m scripts.audit.fetch_page https://example.com --output page.html --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Optional
from urllib.parse import urlparse

import httpx

from scripts._core.ssrf_guard import validate_url, SSRFError

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 XuanranSEO/3.4"
)

GOOGLEBOT_USER_AGENT = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)

DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


def fetch_page(
    url: str,
    timeout: int = 30,
    follow_redirects: bool = True,
    max_redirects: int = 5,
    user_agent: Optional[str] = None,
) -> dict:
    """Fetch a web page and return response details.

    Returns dict with: url, status_code, content, headers, content_type,
    redirect_chain, redirect_details, response_time_ms, error.
    """
    result: dict = {
        "url": url,
        "status_code": None,
        "content": None,
        "content_type": None,
        "headers": {},
        "redirect_chain": [],
        "redirect_details": [],
        "response_time_ms": None,
        "error": None,
    }

    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"
        parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        result["error"] = f"Invalid URL scheme: {parsed.scheme}"
        return result

    try:
        validate_url(url, allow_http=True)
    except SSRFError as e:
        result["error"] = f"SSRF blocked: {e}"
        return result

    headers = dict(DEFAULT_HEADERS)
    if user_agent:
        headers["User-Agent"] = user_agent

    start = time.perf_counter()
    try:
        with httpx.Client(
            follow_redirects=follow_redirects,
            max_redirects=max_redirects,
            timeout=timeout,
        ) as client:
            response = client.get(url, headers=headers)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        result["url"] = str(response.url)
        result["status_code"] = response.status_code
        result["content"] = response.text
        result["content_type"] = response.headers.get("content-type", "")
        result["headers"] = dict(response.headers)
        result["response_time_ms"] = elapsed_ms

        if response.history:
            result["redirect_chain"] = [str(r.url) for r in response.history]
            result["redirect_details"] = [
                {"url": str(r.url), "status_code": r.status_code}
                for r in response.history
            ]

    except httpx.TimeoutException:
        result["error"] = f"Request timed out after {timeout} seconds"
    except httpx.TooManyRedirects:
        result["error"] = f"Too many redirects (max {max_redirects})"
    except httpx.ConnectError as e:
        result["error"] = f"Connection error: {e}"
    except httpx.HTTPError as e:
        result["error"] = f"HTTP error: {e}"

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a web page for SEO audit")
    parser.add_argument("url", help="URL to fetch")
    parser.add_argument("--output", "-o", help="Save HTML to file")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Timeout seconds")
    parser.add_argument("--no-redirects", action="store_true", help="Don't follow redirects")
    parser.add_argument("--user-agent", help="Custom User-Agent")
    parser.add_argument("--googlebot", action="store_true", help="Use Googlebot UA")
    parser.add_argument("--json", "-j", action="store_true", help="Output full result as JSON")

    args = parser.parse_args()

    ua = args.user_agent
    if args.googlebot:
        ua = GOOGLEBOT_USER_AGENT

    result = fetch_page(
        args.url,
        timeout=args.timeout,
        follow_redirects=not args.no_redirects,
        user_agent=ua,
    )

    if result["error"]:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        output = {k: v for k, v in result.items() if k != "content"}
        output["content_length"] = len(result["content"] or "")
        print(json.dumps(output, indent=2))
    elif args.output:
        from pathlib import Path
        Path(args.output).write_text(result["content"], encoding="utf-8")
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(result["content"])

    print(f"\nURL: {result['url']}", file=sys.stderr)
    print(f"Status: {result['status_code']}", file=sys.stderr)
    print(f"Time: {result['response_time_ms']}ms", file=sys.stderr)
    if result["redirect_details"]:
        for rd in result["redirect_details"]:
            print(f"  {rd['status_code']} -> {rd['url']}", file=sys.stderr)


if __name__ == "__main__":
    main()
