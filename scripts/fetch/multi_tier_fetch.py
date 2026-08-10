"""scripts/fetch/multi_tier_fetch.py — 5-tier fetch waterfall for /init.

Tries each tier in order; falls through on failure:
  Tier 1: tavily_extract       — fastest, server-side rendering
  Tier 2: patchright           — JS-heavy SPA / Shopify Hydrogen / Wix
  Tier 3: Firecrawl (MCP)      — anti-bot commercial scraper (if available)
  Tier 4: jina.ai/reader        — public readable mirror (no key needed)
  Tier 5: raw HTML + hydration  — last resort; extract embedded JSON

Each page records `tier_used` and `fallback_history` in result.

Acceptance criterion: body text >= 500 chars AND not a Cloudflare challenge / error page.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from scripts._core.ssrf_guard import validate_url, SSRFError


JINA_READER_BASE = "https://r.jina.ai/"

TIER_NAMES = {1: "tavily_extract", 2: "patchright", 3: "firecrawl",
              4: "jina_reader", 5: "hydration"}


@dataclass
class FetchAttempt:
    tier: int
    name: str
    success: bool
    error: str | None
    fetch_ms: int
    body_chars: int


@dataclass
class WaterfallResult:
    url: str
    final_url: str
    status: int
    title: str
    body_text: str
    body_markdown: str | None = None    # if tier supports markdown output
    tier_used: int = 0
    fallback_history: list[FetchAttempt] = field(default_factory=list)
    total_fetch_ms: int = 0
    framework_detected: str | None = None
    error: str | None = None


MIN_ACCEPTABLE_BODY_CHARS = 500


def _is_acceptable(body: str) -> bool:
    """Reject if too short OR Cloudflare challenge OR error page."""
    if len(body) < MIN_ACCEPTABLE_BODY_CHARS:
        return False
    body_lower = body.lower()
    challenge_markers = [
        "cloudflare", "checking your browser", "ddos protection",
        "captcha", "you have been blocked", "access denied",
    ]
    # Only reject if multiple challenge markers (avoid false positives)
    hits = sum(1 for m in challenge_markers if m in body_lower)
    if hits >= 2:
        return False
    return True


async def _try_tier_1_tavily(url: str) -> tuple[bool, str, str, str, str | None]:
    """Returns (success, body, title, final_url, error)."""
    try:
        from scripts.fetch.tavily_extract import extract
        results = extract([url], depth="advanced", format="markdown", use_cache=False)
        if not results or results[0].error:
            return False, "", "", url, results[0].error if results else "no result"
        r = results[0]
        body = r.content
        if not _is_acceptable(body):
            return False, body, r.title or "", url, "body too short or blocked"
        return True, body, r.title or "", url, None
    except Exception as e:
        return False, "", "", url, str(e)


async def _try_tier_2_patchright(url: str) -> tuple[bool, str, str, str, str | None]:
    try:
        from scripts.fetch.tier_2_patchright import fetch_with_patchright
        result = await fetch_with_patchright(url, timeout_ms=30000)
        if result.error:
            return False, "", "", result.final_url, result.error
        if not _is_acceptable(result.text_content):
            return False, result.text_content, result.title, result.final_url, "body too short"
        return True, result.text_content, result.title, result.final_url, None
    except Exception as e:
        return False, "", "", url, str(e)


async def _try_tier_2_5_cf_bypass(url: str, site_slug: str | None = None) -> tuple[bool, str, str, str, str | None]:
    """Cloudflare bypass tier — try header_token / cookies / commercial in order.

    Triggered when previous tiers failed AND the failure looks like CF.
    """
    try:
        from scripts.fetch.cloudflare_bypass import bypass_auto
        result = bypass_auto(url, site_slug)
        if not result.success:
            return False, result.content[:5000], "", url, result.error or "CF bypass failed"
        body = result.content
        if not _is_acceptable(body):
            return False, body, "", url, "body too short after CF bypass"
        # Try to extract title from HTML
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", body, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else ""
        return True, body, title, result.final_url or url, None
    except Exception as e:
        return False, "", "", url, str(e)


async def _try_tier_4_jina(url: str) -> tuple[bool, str, str, str, str | None]:
    """jina.ai/reader — free readable mirror, no key."""
    try:
        validate_url(url, allow_http=False)
    except SSRFError as e:
        return False, "", "", url, f"SSRF: {e}"

    try:
        import httpx
    except ImportError:
        return False, "", "", url, "httpx not installed"

    reader_url = JINA_READER_BASE + url
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(reader_url, headers={
                "User-Agent": "XuanranSEO/3.2.0",
                "Accept": "text/plain, text/markdown, text/html",
            })
            if r.status_code != 200:
                return False, "", "", url, f"jina returned {r.status_code}"
            body = r.text
            # First line is often the title
            title = ""
            if body.startswith("Title:"):
                first_line = body.split("\n", 1)[0]
                title = first_line.replace("Title:", "").strip()
            if not _is_acceptable(body):
                return False, body, title, url, "body too short"
            return True, body, title, url, None
    except Exception as e:
        return False, "", "", url, str(e)


async def _try_tier_5_hydration(url: str) -> tuple[bool, str, str, str, str | None]:
    """Raw HTML + hydration JSON extraction."""
    from scripts.fetch.fetch_page import fetch as fetch_raw
    from scripts.fetch.tier_5_hydration_miner import mine, extract_content_from_hydration

    result = fetch_raw(url, timeout=15.0)
    if result.status != 200 or not result.body:
        return False, "", "", result.url_final, result.error or "non-200"

    data = mine(result.body)
    title = data.metadata.get("title", "")
    content = extract_content_from_hydration(data)
    if not content:
        # Just strip tags from raw HTML as final fallback
        content = re.sub(r"<[^>]+>", " ", result.body)
        content = re.sub(r"\s+", " ", content).strip()

    if not _is_acceptable(content):
        return False, content, title, result.url_final, "body still too short after hydration"
    return True, content, title, result.url_final, None


async def fetch_url_waterfall(
    url: str,
    *,
    max_tier: int = 5,
    skip_tiers: list[int] | None = None,
    site_slug: str | None = None,
) -> WaterfallResult:
    """Run 5-tier fallback waterfall.

    Args:
        url: Target URL
        max_tier: Maximum tier to try (1-5)
        skip_tiers: e.g. [3] to skip Firecrawl if MCP not available

    Returns:
        WaterfallResult with tier_used + fallback_history.
    """
    skip_tiers = skip_tiers or []
    t0 = time.time()

    result = WaterfallResult(
        url=url, final_url=url, status=0, title="",
        body_text="", error=None,
    )

    # Tiers as ordered list of (tier_num, tier_func)
    tiers = [
        (1, _try_tier_1_tavily),
        (2, _try_tier_2_patchright),
        # Tier 2.5: CF bypass when previous tiers detect CF challenge
        (2, _try_tier_2_5_cf_bypass),
        # Tier 3 Firecrawl skipped if not MCP-configured (no built-in)
        (4, _try_tier_4_jina),
        (5, _try_tier_5_hydration),
    ]

    seen_tier2_5 = False
    for tier_num, tier_func in tiers:
        if tier_num > max_tier or tier_num in skip_tiers:
            continue

        # Tier 2.5 (CF bypass) is special — only triggers if prior tier saw CF challenge
        if tier_func is _try_tier_2_5_cf_bypass:
            # Did any prior attempt look like CF block?
            cf_signaled = any(
                a.error and ("cloudflare" in (a.error or "").lower() or "blocked" in (a.error or "").lower())
                for a in result.fallback_history
            )
            if not cf_signaled:
                continue
            if seen_tier2_5:
                continue
            seen_tier2_5 = True

        tier_t0 = time.time()
        if tier_func is _try_tier_2_5_cf_bypass:
            success, body, title, final_url, error = await tier_func(url, site_slug)
        else:
            success, body, title, final_url, error = await tier_func(url)
        elapsed = int((time.time() - tier_t0) * 1000)

        result.fallback_history.append(FetchAttempt(
            tier=tier_num, name=TIER_NAMES[tier_num],
            success=success, error=error, fetch_ms=elapsed,
            body_chars=len(body),
        ))

        if success:
            result.tier_used = tier_num
            result.body_text = body
            result.title = title
            result.final_url = final_url
            result.status = 200
            if tier_num in (1, 4):
                result.body_markdown = body  # these tiers return markdown
            break

    result.total_fetch_ms = int((time.time() - t0) * 1000)
    if result.tier_used == 0:
        result.error = "All tiers failed; URL unreachable"

    return result


def fetch_sync(url: str, **kwargs) -> WaterfallResult:
    return asyncio.run(fetch_url_waterfall(url, **kwargs))


def main() -> int:
    ap = argparse.ArgumentParser(description="5-tier fetch waterfall for /init")
    ap.add_argument("url")
    ap.add_argument("--max-tier", type=int, choices=[1, 2, 3, 4, 5], default=5)
    ap.add_argument("--skip", action="append", type=int, default=[], help="Skip tier N")
    ap.add_argument("--save-body", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = fetch_sync(args.url, max_tier=args.max_tier, skip_tiers=args.skip)

    if args.save_body and r.body_text:
        args.save_body.write_text(r.body_text, encoding="utf-8")

    if args.json:
        out = asdict(r)
        if len(out["body_text"]) > 1000:
            out["body_text"] = out["body_text"][:1000] + "..."
        if out.get("body_markdown") and len(out["body_markdown"]) > 1000:
            out["body_markdown"] = out["body_markdown"][:1000] + "..."
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"URL:         {r.url}")
        print(f"Final URL:   {r.final_url}")
        print(f"Tier used:   {r.tier_used} ({TIER_NAMES.get(r.tier_used, 'none')})")
        print(f"Title:       {r.title}")
        print(f"Body chars:  {len(r.body_text)}")
        print(f"Total time:  {r.total_fetch_ms} ms")
        print(f"\nFallback history:")
        for h in r.fallback_history:
            icon = "✓" if h.success else "✗"
            print(f"  {icon} Tier {h.tier} {h.name}: {h.body_chars} chars in {h.fetch_ms} ms")
            if h.error:
                print(f"      Error: {h.error}")
        if r.error:
            print(f"\n⚠ {r.error}")
    return 0 if r.tier_used > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
