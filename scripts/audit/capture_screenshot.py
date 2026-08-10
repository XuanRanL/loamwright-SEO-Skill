#!/usr/bin/env python3
"""Capture web page screenshots using patchright (Playwright fork).

Usage:
    python -m scripts.audit.capture_screenshot https://example.com
    python -m scripts.audit.capture_screenshot https://example.com --all --output screenshots/
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from patchright.sync_api import sync_playwright, TimeoutError as PatchrightTimeout

from scripts._core.ssrf_guard import validate_url, SSRFError

VIEWPORTS = {
    "desktop": {"width": 1920, "height": 1080},
    "laptop": {"width": 1366, "height": 768},
    "tablet": {"width": 768, "height": 1024},
    "mobile": {"width": 375, "height": 812},
}


def capture_screenshot(
    url: str,
    output_path: str,
    viewport: str = "desktop",
    full_page: bool = False,
    timeout: int = 30000,
    extra_headers: dict[str, str] | None = None,
) -> dict:
    """Capture a screenshot. Returns dict with success, error, output, viewport."""
    result: dict = {
        "url": url,
        "output": output_path,
        "viewport": viewport,
        "success": False,
        "error": None,
    }

    if viewport not in VIEWPORTS:
        result["error"] = f"Invalid viewport: {viewport}. Choose from: {list(VIEWPORTS.keys())}"
        return result

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

    result["url"] = url
    vp = VIEWPORTS[viewport]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": vp["width"], "height": vp["height"]},
                device_scale_factor=2 if viewport == "mobile" else 1,
                extra_http_headers=extra_headers or {},
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout)
            page.wait_for_timeout(1000)
            page.screenshot(path=output_path, full_page=full_page)
            result["success"] = True
            browser.close()

    except PatchrightTimeout:
        result["error"] = f"Page load timed out after {timeout}ms"
    except Exception as e:
        result["error"] = str(e)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture web page screenshots for audit")
    parser.add_argument("url", help="URL to capture")
    parser.add_argument("--output", "-o", default="screenshots", help="Output directory")
    parser.add_argument("--viewport", "-v", default="desktop", choices=VIEWPORTS.keys())
    parser.add_argument("--all", "-a", action="store_true", help="Capture all viewports")
    parser.add_argument("--full", "-f", action="store_true", help="Capture full page")
    parser.add_argument("--timeout", "-t", type=int, default=30000, help="Timeout in ms")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output with metadata")
    parser.add_argument(
        "--header", "-H", action="append", default=[], metavar="NAME:VALUE",
        help="Extra HTTP header (e.g. -H 'X-Token:abc'). Repeatable. "
             "Needed for Cloudflare-bypass tokens on WAF-protected sites.",
    )

    args = parser.parse_args()

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    parsed = urlparse(args.url)
    url = args.url if parsed.scheme else f"https://{args.url}"
    parsed = urlparse(url)
    base_name = (parsed.netloc or "unknown").replace(".", "_")
    # Include the URL path so different pages of the same domain don't
    # overwrite each other's screenshots (found 2026-07-18: home/shop/blog
    # captures all collided on {netloc}_{viewport}.png).
    path_slug = re.sub(r"[^a-z0-9]+", "-", (parsed.path or "/").strip("/").lower()).strip("-")
    if path_slug:
        base_name = f"{base_name}_{path_slug[:60]}"

    viewports = list(VIEWPORTS.keys()) if args.all else [args.viewport]

    import json as _json

    results = []
    for vp_name in viewports:
        filename = f"{base_name}_{vp_name}.png"
        out_path = str(output_dir / filename)

        extra_headers: dict[str, str] = {}
        for h in args.header:
            name, _, value = h.partition(":")
            if name.strip() and value.strip():
                extra_headers[name.strip()] = value.strip()

        print(f"Capturing {vp_name} screenshot...", file=sys.stderr)
        result = capture_screenshot(
            url, out_path, viewport=vp_name, full_page=args.full,
            timeout=args.timeout, extra_headers=extra_headers or None,
        )
        results.append(result)

        if result["success"]:
            print(f"  Saved to {out_path}", file=sys.stderr)
        else:
            print(f"  Failed: {result['error']}", file=sys.stderr)

    if args.json:
        print(_json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
