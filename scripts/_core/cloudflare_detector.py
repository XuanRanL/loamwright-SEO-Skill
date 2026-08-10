"""
scripts/_core/cloudflare_detector.py — Detect + classify Cloudflare protection.

Identifies whether a fetch hit Cloudflare protection AND which layer:
  - L1: Bot Fight Mode (basic challenge page)
  - L2: Super Bot Fight Mode (JS challenge)
  - L3: Bot Management score-based block
  - L4: WAF custom rule block
  - L5: Managed Challenge (CAPTCHA / Turnstile)
  - L6: Rate limit (429)
  - L7: Country / IP block

Used by `multi_tier_fetch.py` to decide bypass strategy.

CLI:
    python -m scripts._core.cloudflare_detector --url https://example.com --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Final

import httpx


# CF response signature patterns
CF_HEADERS: Final[tuple[str, ...]] = (
    "cf-ray", "cf-cache-status", "cf-mitigated", "cf-chl-bypass",
    "server",  # often "cloudflare"
)

CF_BODY_PATTERNS: Final[dict[str, str]] = {
    # Layer → regex pattern
    "L1_bot_fight": r"<title>Just a moment\.\.\.</title>|cf-browser-verification|cf_chl_jschl_tk",
    "L2_super_bot_fight": r"<title>Attention Required! \| Cloudflare</title>|cf-error-details|/cdn-cgi/challenge-platform/h/[bg]/",
    "L3_managed_challenge": r"challenge-platform/h/[bg]/managed/.*|cf-turnstile-response|/cdn-cgi/challenge-platform/h/[bg]/managed/",
    "L4_waf_block": r"<title>Access denied</title>.*Cloudflare|<title>Cloudflare Browser Check</title>",
    "L5_country_block": r"Sorry, you have been blocked|<title>Forbidden</title>",
}

# CF challenge page signatures (more conservative)
CF_CHALLENGE_REGEX = re.compile(
    r"cf_chl_|cf-chl-|challenge-platform|cf-browser-verification|cf-error-details|"
    r"cf-mitigated|cf-ray-id|cf-turnstile|jschl_tk|jschl_answer",
    re.IGNORECASE,
)


@dataclass
class CloudflareDetection:
    url: str
    is_cloudflare: bool = False
    is_blocked: bool = False
    cf_layer: str = ""             # L1/L2/L3/L4/L5/L6/L7
    cf_layer_name: str = ""
    cf_ray: str = ""
    server_header: str = ""
    status_code: int = 0
    response_size: int = 0
    bypass_strategy_recommended: str = ""    # header_token | cookies | commercial | retry_later
    bypass_strategy_rationale: str = ""
    raw_signals: list[str] = field(default_factory=list)


def _layer_name(layer: str) -> str:
    return {
        "L1_bot_fight": "Bot Fight Mode (basic)",
        "L2_super_bot_fight": "Super Bot Fight Mode",
        "L3_managed_challenge": "Managed Challenge (CAPTCHA/Turnstile)",
        "L4_waf_block": "WAF custom rule block",
        "L5_country_block": "Country / IP block",
        "L6_rate_limit": "Rate limit (429)",
    }.get(layer, layer)


def _recommend_bypass(detection: CloudflareDetection) -> tuple[str, str]:
    """Recommend bypass strategy + rationale."""
    if not detection.is_blocked:
        return ("none", "Not blocked; no bypass needed")

    if detection.cf_layer == "L1_bot_fight":
        return ("header_token",
                "L1 BFM: simplest. Configure WAF Allow rule on your secret header.")

    if detection.cf_layer == "L2_super_bot_fight":
        return ("header_token",
                "L2: JS challenge. Header token bypass is cleanest; "
                "or use cookie injection from your authenticated session.")

    if detection.cf_layer == "L3_managed_challenge":
        return ("cookies",
                "L3 Managed Challenge: need cf_clearance + __cf_bm cookies "
                "from authenticated browser session. Header token works ONLY "
                "if WAF rule is configured to skip managed challenge.")

    if detection.cf_layer == "L4_waf_block":
        return ("waf_rule_update",
                "L4 WAF block: your WAF rule is explicitly denying. "
                "Update WAF custom rule to allow on header_token or IP.")

    if detection.cf_layer == "L5_country_block":
        return ("vpn_or_commercial",
                "L5 country block: cannot bypass from current IP. "
                "Use VPN endpoint OR commercial proxy service (ScraperAPI / Bright Data).")

    if detection.cf_layer == "L6_rate_limit":
        return ("retry_later",
                "L6 rate limit: too many requests. Wait 60s+ or use rotating IPs.")

    return ("commercial",
            "Unknown CF layer; recommend commercial bypass service "
            "(ScraperAPI / Bright Data / Scrapingbee)")


def detect_from_response(
    url: str, response: httpx.Response,
) -> CloudflareDetection:
    """Analyze an httpx response for Cloudflare protection signals."""
    detection = CloudflareDetection(
        url=url,
        status_code=response.status_code,
        response_size=len(response.content),
        cf_ray=response.headers.get("cf-ray", ""),
        server_header=response.headers.get("server", "").lower(),
    )

    has_cf_header = (
        "cloudflare" in detection.server_header
        or detection.cf_ray
        or any(h.lower() in {k.lower() for k in response.headers} for h in CF_HEADERS)
    )

    if has_cf_header:
        detection.is_cloudflare = True
        detection.raw_signals.append("CF response headers present")

    # Check status codes that indicate CF challenge / block
    if response.status_code == 429:
        detection.is_blocked = True
        detection.cf_layer = "L6_rate_limit"
        detection.cf_layer_name = "Rate limit (429)"
        detection.raw_signals.append("HTTP 429 from CF")

    if response.status_code in {403, 503}:
        # Could be CF challenge or block
        body = response.text[:5000]
        if CF_CHALLENGE_REGEX.search(body):
            detection.is_cloudflare = True
            detection.is_blocked = True
            detection.raw_signals.append("CF challenge signature in body")
            # Try to classify
            for layer, pattern in CF_BODY_PATTERNS.items():
                if re.search(pattern, body, re.IGNORECASE):
                    detection.cf_layer = layer
                    detection.cf_layer_name = _layer_name(layer)
                    detection.raw_signals.append(f"Matched: {layer}")
                    break
            if not detection.cf_layer:
                detection.cf_layer = "L1_bot_fight"
                detection.cf_layer_name = "Bot Fight Mode (basic)"

    # Even 200 responses may contain JS challenge
    if response.status_code == 200 and CF_CHALLENGE_REGEX.search(response.text[:5000]):
        # JS challenge served on 200; cookies pending
        detection.is_cloudflare = True
        detection.is_blocked = True
        detection.cf_layer = "L2_super_bot_fight"
        detection.cf_layer_name = _layer_name("L2_super_bot_fight")
        detection.raw_signals.append("CF JS challenge detected in 200 response")

    strategy, rationale = _recommend_bypass(detection)
    detection.bypass_strategy_recommended = strategy
    detection.bypass_strategy_rationale = rationale

    return detection


def detect_from_url(url: str, timeout: float = 15.0,
                    headers: dict | None = None) -> CloudflareDetection:
    """Make a GET request + detect CF."""
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_0) "
                      "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                      "Version/17.0 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        # Accept-Encoding intentionally NOT set: httpx advertises only codecs it
        # can decode (br requires the brotli package).
    }
    if headers:
        default_headers.update(headers)

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True,
                          headers=default_headers) as client:
            r = client.get(url)
            return detect_from_response(url, r)
    except httpx.HTTPError as e:
        return CloudflareDetection(
            url=url, is_blocked=True, cf_layer="UNREACHABLE",
            cf_layer_name=f"HTTP error: {e}",
            bypass_strategy_recommended="commercial",
            bypass_strategy_rationale=f"Network error: {e}",
            raw_signals=[f"httpx error: {e}"],
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect Cloudflare protection layer")
    ap.add_argument("--url", required=True)
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--header", action="append", default=[],
                    help="Key:Value pair (can repeat)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    custom_headers = {}
    for h in args.header:
        if ":" in h:
            k, _, v = h.partition(":")
            custom_headers[k.strip()] = v.strip()

    detection = detect_from_url(args.url, args.timeout, custom_headers)

    if args.json:
        print(json.dumps(asdict(detection), indent=2, ensure_ascii=False))
    else:
        icon = "🔴" if detection.is_blocked else ("🟡" if detection.is_cloudflare else "✓")
        print(f"{icon} {args.url}")
        print(f"  CF protection: {detection.is_cloudflare}")
        print(f"  CF blocked:    {detection.is_blocked}")
        if detection.cf_layer:
            print(f"  Layer:         {detection.cf_layer_name} ({detection.cf_layer})")
        print(f"  Status:        {detection.status_code}")
        print(f"  CF-Ray:        {detection.cf_ray}")
        print(f"  Bypass:        {detection.bypass_strategy_recommended}")
        print(f"  Rationale:     {detection.bypass_strategy_rationale}")
        if detection.raw_signals:
            print(f"  Signals:")
            for s in detection.raw_signals:
                print(f"    - {s}")
    return 0 if not detection.is_blocked else 1


if __name__ == "__main__":
    sys.exit(main())
