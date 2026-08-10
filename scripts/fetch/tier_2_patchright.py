"""scripts/fetch/tier_2_patchright.py — Tier 2 of /init 5-tier fallback waterfall.

Uses patchright (Playwright fork with anti-detection patches) for JS-heavy sites
that Tier 1 (Tavily extract) can't render.

Patchright auto-handles:
  - navigator.webdriver hiding
  - User-Agent normalization (no "HeadlessChrome")
  - Chrome-runtime properties
  - Bot detection bypass (Cloudflare Turnstile won't always pass, but common cases work)

Installs:
  pip install patchright
  python -m patchright install chromium
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts._core.ssrf_guard import validate_url, SSRFError


# Anti-detection User-Agents (real browser strings)
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
]


@dataclass
class PatchrightResult:
    url: str
    final_url: str
    status: int
    html: str
    text_content: str
    title: str
    fetch_ms: int
    error: str | None = None


async def fetch_with_patchright(
    url: str,
    *,
    timeout_ms: int = 30_000,
    wait_for: str = "networkidle",
    headless: bool = True,
) -> PatchrightResult:
    """Fetch a URL using patchright (anti-detection Chromium).

    Args:
        url: Target URL.
        timeout_ms: Total page-load timeout.
        wait_for: 'networkidle' / 'domcontentloaded' / 'load'.
        headless: Run headless (default True).

    Returns:
        PatchrightResult with rendered HTML + text + metadata.
    """
    try:
        validate_url(url, allow_http=False, resolve_dns=True)
    except SSRFError as e:
        return PatchrightResult(url, url, 0, "", "", "", 0, error=f"SSRF: {e}")

    try:
        from patchright.async_api import async_playwright
    except ImportError as e:
        return PatchrightResult(url, url, 0, "", "", "", 0,
                                 error=f"patchright not installed: {e}")

    t0 = time.time()
    ua = random.choice(UA_POOL)
    viewport = random.choice(VIEWPORTS)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            context = await browser.new_context(
                user_agent=ua,
                viewport=viewport,
                locale="en-US",
                timezone_id="America/Los_Angeles",
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                },
            )
            page = await context.new_page()

            # NOTE: Patchright (vs vanilla Playwright) already patches
            # navigator.webdriver, Runtime.enable, headless detection, etc.
            # Adding a manual add_init_script for the same property breaks
            # Chromium's network stack on Windows (ERR_NAME_NOT_RESOLVED).
            # Trust patchright's built-in stealth — don't double-patch.

            try:
                response = await page.goto(url, wait_until=wait_for, timeout=timeout_ms)
                # Small randomized scroll to trigger lazy-load
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                await asyncio.sleep(random.uniform(0.5, 1.5))

                html = await page.content()
                title = await page.title()
                text = await page.inner_text("body")
                status = response.status if response else 0
                final_url = page.url

                fetch_ms = int((time.time() - t0) * 1000)
                await browser.close()

                return PatchrightResult(
                    url=url, final_url=final_url, status=status,
                    html=html, text_content=text, title=title,
                    fetch_ms=fetch_ms,
                )

            except Exception as e:
                await browser.close()
                return PatchrightResult(
                    url, url, 0, "", "", "",
                    int((time.time() - t0) * 1000),
                    error=f"Page error: {e}",
                )

    except Exception as e:
        return PatchrightResult(
            url, url, 0, "", "", "",
            int((time.time() - t0) * 1000),
            error=f"Patchright error: {e}",
        )


def fetch_sync(url: str, **kwargs) -> PatchrightResult:
    """Sync wrapper for fetch_with_patchright."""
    return asyncio.run(fetch_with_patchright(url, **kwargs))


def main() -> int:
    ap = argparse.ArgumentParser(description="Tier 2 patchright fetch (JS-heavy pages)")
    ap.add_argument("url")
    ap.add_argument("--timeout", type=int, default=30000, help="Total ms")
    ap.add_argument("--wait", choices=["networkidle", "domcontentloaded", "load"],
                    default="networkidle")
    ap.add_argument("--headed", action="store_true", help="Visible browser (debug)")
    ap.add_argument("--save-body", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = fetch_sync(args.url,
                   timeout_ms=args.timeout,
                   wait_for=args.wait,
                   headless=not args.headed)

    if args.save_body and r.html:
        args.save_body.write_text(r.html, encoding="utf-8")

    if args.json:
        out = asdict(r)
        if len(out["html"]) > 1000:
            out["html"] = out["html"][:1000] + "..."
        if len(out["text_content"]) > 1000:
            out["text_content"] = out["text_content"][:1000] + "..."
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"URL:       {r.url}")
        print(f"Final URL: {r.final_url}")
        print(f"Status:    {r.status}")
        print(f"Title:     {r.title}")
        print(f"HTML size: {len(r.html)} chars")
        print(f"Text size: {len(r.text_content)} chars")
        print(f"Time:      {r.fetch_ms} ms")
        if r.error:
            print(f"Error:     {r.error}")
        elif r.text_content:
            print(f"\n--- First 500 chars of text ---")
            print(r.text_content[:500])

    return 0 if r.status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
