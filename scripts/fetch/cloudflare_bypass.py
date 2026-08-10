"""
scripts/fetch/cloudflare_bypass.py — 3-strategy CF bypass fetcher.

Strategy A: Header token (Allow via WAF custom rule)
Strategy B: Cookie injection (cf_clearance from authenticated browser)
Strategy C: Commercial proxy (ScraperAPI / Bright Data)

Used by `multi_tier_fetch.py` as Tier 2.5 (between Patchright + Firecrawl)
when `cloudflare_detector` reports a CF block.

CLI:
    # Strategy A: Header token
    python -m scripts.fetch.cloudflare_bypass --url https://example.com --strategy header_token

    # Strategy B: Cookies
    python -m scripts.fetch.cloudflare_bypass --url https://example.com --strategy cookies --slug my-site

    # Strategy C: Commercial
    python -m scripts.fetch.cloudflare_bypass --url https://example.com --strategy commercial
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import httpx

from scripts._core import credential_hub
from scripts._core.cloudflare_detector import detect_from_response


BypassStrategy = Literal["header_token", "cookies", "commercial", "auto"]


@dataclass
class BypassResult:
    url: str
    strategy: str
    success: bool = False
    status_code: int = 0
    content: str = ""
    content_length: int = 0
    final_url: str = ""
    cookies_used: list[str] = field(default_factory=list)
    response_time_ms: int = 0
    error: str = ""
    cost_usd: str = "0.00"


# Strategy A: Header token bypass

def bypass_header_token(
    url: str, site_slug: str | None = None,
    *, timeout: float = 30.0,
) -> BypassResult:
    """Use X-Xuanran-SEO-Token header. Requires user to configure CF WAF Allow rule."""
    result = BypassResult(url=url, strategy="header_token")
    t0 = time.time()

    token = _get_cf_token(site_slug)
    if not token:
        result.error = (
            "No CF bypass token configured. "
            "Set XUANRAN_CF_TOKEN env OR projects/{slug}/credentials/cloudflare.json "
            "with {\"bypass_token\": \"<32-hex>\"} AND configure CF WAF rule."
        )
        return result

    headers = {
        "User-Agent": "XuanranSEO-Init/3.2 (+xuanran-seo)",
        "X-Xuanran-SEO-Token": token,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as c:
            r = c.get(url)
            result.status_code = r.status_code
            result.content = r.text
            result.content_length = len(r.content)
            result.final_url = str(r.url)
            result.response_time_ms = int((time.time() - t0) * 1000)
            result.success = (
                r.status_code == 200
                and not _looks_like_cf_challenge(r.text)
            )
            if not result.success and r.status_code in {403, 503}:
                result.error = (
                    "CF still blocking. Verify your WAF Allow rule is active "
                    "AND token matches. Test via: curl -H 'X-Xuanran-SEO-Token: <token>' <url>"
                )
    except httpx.HTTPError as e:
        result.error = str(e)

    return result


# Strategy B: Cookie injection bypass

def bypass_cookies(
    url: str, site_slug: str,
    *, timeout: float = 30.0,
) -> BypassResult:
    """Use cf_clearance + __cf_bm cookies from authenticated browser session."""
    result = BypassResult(url=url, strategy="cookies")
    t0 = time.time()

    cookies = _load_cf_cookies(site_slug)
    if not cookies:
        result.error = (
            f"No CF cookies for {site_slug}. "
            "Export from browser DevTools (F12 → Application → Cookies) "
            "OR use a browser extension like EditThisCookie. "
            f"Save to projects/{site_slug}/credentials/cf-cookies.json"
        )
        return result

    # Check if cookies expired
    if _cookies_expired(cookies):
        result.error = (
            f"CF cookies for {site_slug} expired. "
            "Re-export from browser (typically 1-30 days TTL)."
        )
        return result

    headers = {
        "User-Agent": cookies.get("user_agent",
                                   "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_0) "
                                   "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                                   "Version/17.0 Safari/605.1.15"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": cookies.get("accept_language", "en-US,en;q=0.9"),
    }

    cookie_jar = {}
    for key in ("cf_clearance", "__cf_bm"):
        if key in cookies:
            cookie_jar[key] = cookies[key]

    if not cookie_jar:
        result.error = "Cookies file present but missing cf_clearance + __cf_bm"
        return result

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True,
                          headers=headers, cookies=cookie_jar) as c:
            r = c.get(url)
            result.status_code = r.status_code
            result.content = r.text
            result.content_length = len(r.content)
            result.final_url = str(r.url)
            result.response_time_ms = int((time.time() - t0) * 1000)
            result.cookies_used = list(cookie_jar.keys())
            result.success = (
                r.status_code == 200
                and not _looks_like_cf_challenge(r.text)
            )
            if not result.success:
                result.error = (
                    "CF cookies didn't pass. Likely expired OR site uses "
                    "Bot Management Enterprise (cookies alone insufficient). "
                    "Try Strategy C (commercial)."
                )
    except httpx.HTTPError as e:
        result.error = str(e)

    return result


# Strategy C: Commercial proxy

def bypass_commercial(
    url: str, *, timeout: float = 60.0,
) -> BypassResult:
    """Use ScraperAPI (or similar) commercial proxy with residential IPs + browser farms."""
    result = BypassResult(url=url, strategy="commercial")
    t0 = time.time()

    api_key = os.environ.get("SCRAPERAPI_KEY", "")
    if not api_key:
        # Try credential hub
        try:
            cred_path = Path.home() / ".xuanran-seo" / "credentials" / "scraperapi.key"
            if cred_path.exists():
                api_key = cred_path.read_text(encoding="utf-8").strip()
        except OSError:
            pass

    if not api_key:
        result.error = (
            "No ScraperAPI key. "
            "Set SCRAPERAPI_KEY env OR ~/.xuanran-seo/credentials/scraperapi.key. "
            "Sign up: https://scraperapi.com (free tier: 1000 calls/month)."
        )
        return result

    proxy_url = "http://api.scraperapi.com"
    params = {
        "api_key": api_key,
        "url": url,
        "render": "true",         # JS rendering enabled
        "country_code": "us",      # set as needed
        "premium": "true",          # use residential IPs for harder bypass
    }

    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(proxy_url, params=params)
            result.status_code = r.status_code
            result.content = r.text
            result.content_length = len(r.content)
            result.final_url = url
            result.response_time_ms = int((time.time() - t0) * 1000)
            result.success = (
                r.status_code == 200
                and not _looks_like_cf_challenge(r.text)
            )
            # Estimate cost (ScraperAPI: 5 credits per render+premium request, ~$0.005 each)
            result.cost_usd = "0.0050"
            if not result.success:
                result.error = (
                    "ScraperAPI returned status but content suggests still blocked. "
                    "Possible reasons: site has aggressive Bot Management; "
                    "try premium tier or Bright Data."
                )
    except httpx.HTTPError as e:
        result.error = str(e)

    return result


# Auto strategy: try in order

def bypass_auto(
    url: str, site_slug: str | None = None,
    *, timeout: float = 30.0,
) -> BypassResult:
    """Try strategies in order: header_token → cookies → commercial."""
    # Try header_token first (fastest, cheapest)
    r = bypass_header_token(url, site_slug, timeout=timeout)
    if r.success:
        return r

    # Try cookies
    if site_slug:
        r2 = bypass_cookies(url, site_slug, timeout=timeout)
        if r2.success:
            return r2

    # Try commercial
    r3 = bypass_commercial(url, timeout=timeout)
    if r3.success:
        return r3

    # All failed
    r3.error = (
        f"All CF bypass strategies failed:\n"
        f"  Header token: {r.error}\n"
        f"  Cookies: {r2.error if site_slug else 'no slug provided'}\n"
        f"  Commercial: {r3.error}"
    )
    return r3


# Helpers

def _get_cf_token(site_slug: str | None) -> str:
    """Get CF bypass token (Strategy A): env > project > global."""
    if site_slug:
        try:
            from scripts._core.project_paths import project_root
            p = project_root(site_slug) / "credentials" / "cloudflare.json"
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("bypass_token"):
                    return data["bypass_token"]
        except Exception:
            pass

    return os.environ.get("XUANRAN_CF_TOKEN", "").strip()


def _load_cf_cookies(site_slug: str) -> dict:
    """Load CF cookies file for a site."""
    try:
        from scripts._core.project_paths import project_root
        p = project_root(site_slug) / "credentials" / "cf-cookies.json"
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cookies_expired(cookies: dict) -> bool:
    """Check if cookies file declares an expiry that's passed."""
    exp = cookies.get("expires", "")
    if not exp:
        return False
    try:
        from datetime import datetime, timezone
        if "T" in exp:
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        else:
            exp_dt = datetime.fromisoformat(f"{exp}T00:00:00+00:00")
        return datetime.now(timezone.utc) > exp_dt
    except (ValueError, TypeError):
        return False


def _looks_like_cf_challenge(body: str) -> bool:
    """Quick check if response body looks like CF challenge page."""
    if not body:
        return False
    sample = body[:3000].lower()
    cf_markers = [
        "cf-browser-verification", "cf-chl", "jschl-vc", "jschl_tk",
        "cf-error-details", "cloudflare ray id", "cf-mitigated",
        "challenge-platform/h/", "cf-turnstile", "managed_challenge",
    ]
    return any(marker in sample for marker in cf_markers)


def main() -> int:
    ap = argparse.ArgumentParser(description="Cloudflare bypass fetcher (3 strategies)")
    ap.add_argument("--url", required=True)
    ap.add_argument("--strategy", required=True,
                    choices=["header_token", "cookies", "commercial", "auto"])
    ap.add_argument("--slug", help="Project slug (for cookies + project-level token)")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--save-to", type=Path, help="Save content to file")
    args = ap.parse_args()

    if args.strategy == "header_token":
        result = bypass_header_token(args.url, args.slug, timeout=args.timeout)
    elif args.strategy == "cookies":
        if not args.slug:
            print("--slug required for cookies strategy", file=sys.stderr)
            return 2
        result = bypass_cookies(args.url, args.slug, timeout=args.timeout)
    elif args.strategy == "commercial":
        result = bypass_commercial(args.url, timeout=args.timeout)
    elif args.strategy == "auto":
        result = bypass_auto(args.url, args.slug, timeout=args.timeout)
    else:
        print(f"Unknown strategy: {args.strategy}", file=sys.stderr)
        return 2

    if args.save_to and result.success:
        args.save_to.write_text(result.content, encoding="utf-8")

    if args.json:
        # Don't dump huge content in JSON; truncate
        d = asdict(result)
        if len(d.get("content", "")) > 500:
            d["content"] = d["content"][:500] + "..."
        print(json.dumps(d, indent=2, ensure_ascii=False))
    else:
        icon = "✓" if result.success else "✗"
        print(f"{icon} {args.strategy}  status={result.status_code}  "
              f"size={result.content_length}  time={result.response_time_ms}ms  "
              f"cost=${result.cost_usd}")
        if not result.success and result.error:
            print(f"  Error: {result.error}")
        if result.success:
            print(f"  Final URL: {result.final_url}")
            if result.cookies_used:
                print(f"  Cookies: {result.cookies_used}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
