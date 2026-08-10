"""scripts/_core/tech_detect.py — Detect CMS / framework / SEO plugin / CDN / analytics from HTML.

Used by /init Stage 1 (Discovery) to populate projects/{slug}/tech-stack.json.

Detection signals:
  - Generator meta tags
  - URL path patterns (/wp-content/, /shopify/, /static/squarespace/)
  - JS bundle signatures (__NEXT_DATA__, __NUXT__, etc.)
  - HTTP headers (Server, X-Powered-By, CF-Ray)
  - Cookie patterns
  - Inline configuration objects
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class TechStack:
    cms: str | None = None
    cms_version_hint: str | None = None
    frontend: str | None = None
    framework: str | None = None
    seo_plugin: str | None = None
    schema_plugin: str | None = None
    page_builder: str | None = None
    cdn: str | None = None
    analytics: list[str] = field(default_factory=list)
    ecommerce_platform: str | None = None
    ai_bot_policy_hint: str | None = None
    https: bool = True
    confidence: float = 0.0


def detect(html: str, headers: dict | None = None) -> TechStack:
    """Detect tech stack from HTML body + optional response headers."""
    stack = TechStack()
    headers = headers or {}

    # ─── CMS detection ────────────────────────────────────────
    # WordPress
    if "/wp-content/" in html or "/wp-includes/" in html or "wp-json" in html:
        stack.cms = "WordPress"
        m = re.search(r'name="generator"[^>]+content="WordPress\s+([\d.]+)"', html)
        if m:
            stack.cms_version_hint = m.group(1)

    # Shopify
    if "cdn.shopify.com" in html or "Shopify.shop" in html or "shopify" in html.lower()[:5000]:
        stack.cms = "Shopify"
        stack.ecommerce_platform = "Shopify"
        # Shopify Hydrogen detection
        if "data-flight" in html or "/_hydrogen/" in html:
            stack.frontend = "Shopify Hydrogen"

    # Squarespace
    if "static.squarespace.com" in html or "squarespace.com/static" in html:
        stack.cms = "Squarespace"

    # Wix
    if "static.wixstatic.com" in html or "wix.com/" in html.lower():
        stack.cms = "Wix"

    # Webflow
    if "webflow.io" in html.lower() or 'name="generator" content="Webflow"' in html:
        stack.cms = "Webflow"

    # Ghost
    if 'generator" content="Ghost' in html or "/ghost/" in html:
        stack.cms = "Ghost"

    # Drupal
    if "drupal-" in html.lower() or 'generator" content="Drupal' in html:
        stack.cms = "Drupal"

    # Magento
    if "/skin/frontend/" in html or "magento" in html.lower()[:5000]:
        stack.cms = "Magento"
        stack.ecommerce_platform = "Magento"

    # WooCommerce
    if "/woocommerce/" in html or "woocommerce-" in html.lower():
        stack.ecommerce_platform = "WooCommerce"

    # BigCommerce
    if "bigcommerce.com" in html.lower() or "/_cdn/shop/" in html:
        stack.ecommerce_platform = "BigCommerce"

    # ─── Framework detection ──────────────────────────────────
    if "__NEXT_DATA__" in html:
        stack.framework = "Next.js"
        stack.frontend = "Next.js"
    elif "window.__NUXT__" in html or "__NUXT__" in html:
        stack.framework = "Nuxt"
        stack.frontend = "Nuxt"
    elif "window.___INITIAL_DATA__" in html:
        stack.framework = "Gatsby"
        stack.frontend = "Gatsby"
    elif "__remixContext" in html:
        stack.framework = "Remix"
        stack.frontend = "Remix"
    elif "Astro" in html and "astro-" in html.lower():
        stack.framework = "Astro"
        stack.frontend = "Astro"

    # ─── SEO plugin (WordPress) ──────────────────────────────
    if stack.cms == "WordPress":
        if "yoast_wpseo" in html or "Yoast SEO" in html or "yoast.com" in html.lower():
            stack.seo_plugin = "Yoast"
        elif "rank-math" in html.lower() or "RankMath" in html:
            stack.seo_plugin = "Rank Math"
        elif "aioseop" in html.lower() or "all-in-one-seo" in html.lower():
            stack.seo_plugin = "AIOSEO"

    # Schema plugin
    if "schema-pro" in html.lower():
        stack.schema_plugin = "Schema Pro"
    elif stack.seo_plugin == "Yoast":
        stack.schema_plugin = "Yoast (built-in)"

    # Page builder (WordPress)
    if stack.cms == "WordPress":
        if "elementor" in html.lower():
            stack.page_builder = "Elementor"
        elif "wp-block-" in html:
            stack.page_builder = "Gutenberg"
        elif "fusion-builder" in html.lower() or "/avada-/" in html.lower():
            stack.page_builder = "Avada"
        elif "et_pb_" in html.lower():
            stack.page_builder = "Divi"

    # ─── CDN / Hosting ────────────────────────────────────────
    if headers:
        server = (headers.get("server") or "").lower()
        cf_ray = headers.get("cf-ray") or headers.get("CF-Ray")
        if cf_ray or "cloudflare" in server:
            stack.cdn = "Cloudflare"
        elif "fastly" in server or "x-fastly-request-id" in headers:
            stack.cdn = "Fastly"
        elif "vercel" in server or "x-vercel-id" in headers:
            stack.cdn = "Vercel"
        elif "netlify" in server or "x-nf-request-id" in headers:
            stack.cdn = "Netlify"
        elif "cloudfront" in server:
            stack.cdn = "AWS CloudFront"

    if not stack.cdn:
        # Detect via HTML signatures
        if "cloudflare" in html.lower()[:5000]:
            stack.cdn = "Cloudflare"

    # ─── Analytics ────────────────────────────────────────────
    if "googletagmanager.com" in html:
        stack.analytics.append("GTM")
    if "gtag(" in html or re.search(r"G-[A-Z0-9]{6,}", html):
        if "GA4" not in stack.analytics:
            stack.analytics.append("GA4")
    if "google-analytics.com/ga.js" in html:
        stack.analytics.append("UA (legacy)")
    if "plausible.io" in html or "data-domain" in html:
        if "plausible" in html.lower():
            stack.analytics.append("Plausible")
    if "matomo" in html.lower() and "tracker" in html.lower():
        stack.analytics.append("Matomo")
    if "fathom-client" in html.lower() or "usefathom" in html:
        stack.analytics.append("Fathom")
    if "amplitude" in html.lower() and ("api" in html.lower() or "tracking" in html.lower()):
        stack.analytics.append("Amplitude")
    if "mixpanel.com/track" in html or "mixpanel-" in html.lower():
        stack.analytics.append("Mixpanel")

    # ─── HTTPS / security ────────────────────────────────────
    stack.https = True  # we only fetch via https
    if headers and "strict-transport-security" in {k.lower() for k in headers}:
        pass  # HSTS confirmed (not stored but checked)

    # ─── Confidence (rough) ──────────────────────────────────
    detected_signals = sum([
        bool(stack.cms), bool(stack.framework), bool(stack.seo_plugin),
        bool(stack.cdn), len(stack.analytics) > 0,
    ])
    stack.confidence = detected_signals / 5

    return stack


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect tech stack from HTML")
    ap.add_argument("file", type=Path, help="HTML file (or - for stdin)")
    ap.add_argument("--headers", type=Path, help="JSON file with response headers")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if str(args.file) == "-":
        html = sys.stdin.read()
    else:
        if not args.file.exists():
            print(f"Not found: {args.file}", file=sys.stderr)
            return 2
        html = args.file.read_text(encoding="utf-8")

    headers = None
    if args.headers and args.headers.exists():
        headers = json.loads(args.headers.read_text(encoding="utf-8"))

    stack = detect(html, headers=headers)

    if args.json:
        print(json.dumps(asdict(stack), indent=2, ensure_ascii=False))
    else:
        print(f"CMS:              {stack.cms}  (v{stack.cms_version_hint})" if stack.cms_version_hint else f"CMS:              {stack.cms}")
        print(f"Framework:        {stack.framework}")
        print(f"Frontend:         {stack.frontend}")
        print(f"SEO plugin:       {stack.seo_plugin}")
        print(f"Schema plugin:    {stack.schema_plugin}")
        print(f"Page builder:     {stack.page_builder}")
        print(f"E-commerce:       {stack.ecommerce_platform}")
        print(f"CDN:              {stack.cdn}")
        print(f"Analytics:        {', '.join(stack.analytics) if stack.analytics else '(none detected)'}")
        print(f"Confidence:       {stack.confidence:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
