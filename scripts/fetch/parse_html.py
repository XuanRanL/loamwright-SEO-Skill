"""
scripts/fetch/parse_html.py — Extract structured data from HTML.

Extracts:
  - Page metadata (title, meta description, meta keywords, canonical, hreflang)
  - Open Graph + Twitter Card
  - JSON-LD schema (parsed)
  - Heading structure (H1, H2, H3)
  - Article body (text content, word count)
  - All anchor links (with text + href)
  - All images (with alt + src + size hints)
  - Tech stack signals (WordPress / Yoast / Shopify / Next.js / etc.)

CLI:
    python -m scripts.fetch.parse_html /path/to/file.html
    python -m scripts.fetch.parse_html /path/to/file.html --json --extract meta,links,schema
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class PageMeta:
    title: str = ""
    description: str = ""
    keywords: str = ""
    canonical: str = ""
    robots: str = ""
    author: str = ""
    lang: str = ""
    hreflang: dict[str, str] = field(default_factory=dict)  # locale → URL


@dataclass
class OpenGraph:
    title: str = ""
    description: str = ""
    type: str = ""
    url: str = ""
    image: str = ""
    site_name: str = ""


@dataclass
class TwitterCard:
    card: str = ""
    title: str = ""
    description: str = ""
    image: str = ""
    site: str = ""


@dataclass
class ImageInfo:
    src: str
    alt: str = ""
    width: str = ""
    height: str = ""
    loading: str = ""


@dataclass
class LinkInfo:
    href: str
    text: str
    rel: str = ""
    is_external: bool = False
    is_nofollow: bool = False


@dataclass
class TechStack:
    cms: str | None = None             # WordPress / Shopify / Squarespace / etc.
    framework: str | None = None        # Next.js / Nuxt / Gatsby / etc.
    seo_plugin: str | None = None       # Yoast / RankMath / AIO SEO / etc.
    analytics: list[str] = field(default_factory=list)  # GA4 / GTM
    cdn: str | None = None              # Cloudflare / Fastly / etc.
    has_jsonld: bool = False
    has_amp: bool = False


@dataclass
class ParsedPage:
    meta: PageMeta = field(default_factory=PageMeta)
    og: OpenGraph = field(default_factory=OpenGraph)
    twitter: TwitterCard = field(default_factory=TwitterCard)
    h1: list[str] = field(default_factory=list)
    h2: list[str] = field(default_factory=list)
    h3: list[str] = field(default_factory=list)
    body_text: str = ""
    word_count: int = 0
    images: list[ImageInfo] = field(default_factory=list)
    links: list[LinkInfo] = field(default_factory=list)
    json_ld: list[dict] = field(default_factory=list)
    schema_types: list[str] = field(default_factory=list)
    tech_stack: TechStack = field(default_factory=TechStack)


def parse(html: str, *, base_url: str = "") -> ParsedPage:
    """Parse HTML and return structured data.

    Args:
        html: Raw HTML string.
        base_url: Used to classify links as internal/external.

    Returns:
        ParsedPage.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise RuntimeError("beautifulsoup4 not installed: pip install beautifulsoup4 lxml") from e

    soup = BeautifulSoup(html, "lxml" if _lxml_available() else "html.parser")
    page = ParsedPage()

    # ── Meta ─────────────────────────────────────────
    if soup.title:
        page.meta.title = soup.title.get_text(strip=True)

    for meta in soup.find_all("meta"):
        name = (meta.get("name") or meta.get("property") or "").lower()
        content = meta.get("content", "")
        if not content:
            continue
        if name == "description":
            page.meta.description = content
        elif name == "keywords":
            page.meta.keywords = content
        elif name == "robots":
            page.meta.robots = content
        elif name == "author":
            page.meta.author = content
        elif name == "og:title":
            page.og.title = content
        elif name == "og:description":
            page.og.description = content
        elif name == "og:type":
            page.og.type = content
        elif name == "og:url":
            page.og.url = content
        elif name == "og:image":
            page.og.image = content
        elif name == "og:site_name":
            page.og.site_name = content
        elif name == "twitter:card":
            page.twitter.card = content
        elif name == "twitter:title":
            page.twitter.title = content
        elif name == "twitter:description":
            page.twitter.description = content
        elif name == "twitter:image":
            page.twitter.image = content
        elif name == "twitter:site":
            page.twitter.site = content
        elif name == "generator":
            # Detect CMS via generator meta
            gen = content.lower()
            if "wordpress" in gen:
                page.tech_stack.cms = "WordPress"
                # Try to extract version
                m = re.search(r"(\d+\.\d+(?:\.\d+)?)", content)
                if m:
                    page.tech_stack.cms = f"WordPress {m.group(1)}"

    # ── Canonical + hreflang ─────────────────────────
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel") or []).lower()
        href = link.get("href", "")
        if rel == "canonical":
            page.meta.canonical = href
        elif rel == "alternate" and link.get("hreflang"):
            page.meta.hreflang[link["hreflang"]] = href

    # ── Lang ─────────────────────────────────────────
    if soup.html and soup.html.get("lang"):
        page.meta.lang = soup.html["lang"]

    # ── Headings ─────────────────────────────────────
    page.h1 = [h.get_text(strip=True) for h in soup.find_all("h1")]
    page.h2 = [h.get_text(strip=True) for h in soup.find_all("h2")]
    page.h3 = [h.get_text(strip=True) for h in soup.find_all("h3")]

    # ── Body text ────────────────────────────────────
    main_el = soup.find("main") or soup.find("article") or soup.body
    if main_el:
        # Remove nav / footer / aside / script / style
        for tag in main_el.find_all(["nav", "footer", "aside", "script", "style", "noscript"]):
            tag.decompose()
        body_text = main_el.get_text(" ", strip=True)
        body_text = re.sub(r"\s+", " ", body_text)
        page.body_text = body_text
        page.word_count = len(re.findall(r"\b\w+\b", body_text))

    # ── Images ────────────────────────────────────────
    for img in soup.find_all("img"):
        page.images.append(ImageInfo(
            src=img.get("src", ""),
            alt=img.get("alt", ""),
            width=str(img.get("width", "")),
            height=str(img.get("height", "")),
            loading=img.get("loading", ""),
        ))

    # ── Links ────────────────────────────────────────
    from urllib.parse import urlparse
    base_host = ""
    if base_url:
        base_host = urlparse(base_url).hostname or ""

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)[:100]
        rel = " ".join(a.get("rel") or [])
        is_external = False
        if href.startswith("http://") or href.startswith("https://"):
            host = urlparse(href).hostname or ""
            is_external = bool(base_host and host != base_host)
        is_nofollow = "nofollow" in rel.lower()
        page.links.append(LinkInfo(
            href=href, text=text, rel=rel,
            is_external=is_external, is_nofollow=is_nofollow,
        ))

    # ── JSON-LD schemas ──────────────────────────────
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            if isinstance(data, list):
                for item in data:
                    page.json_ld.append(item)
                    if "@type" in item:
                        types = item["@type"] if isinstance(item["@type"], list) else [item["@type"]]
                        page.schema_types.extend(types)
            elif isinstance(data, dict):
                page.json_ld.append(data)
                if "@graph" in data and isinstance(data["@graph"], list):
                    for graph_item in data["@graph"]:
                        if "@type" in graph_item:
                            types = graph_item["@type"] if isinstance(graph_item["@type"], list) else [graph_item["@type"]]
                            page.schema_types.extend(types)
                elif "@type" in data:
                    types = data["@type"] if isinstance(data["@type"], list) else [data["@type"]]
                    page.schema_types.extend(types)
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
    page.tech_stack.has_jsonld = bool(page.json_ld)
    # Dedup schema_types
    page.schema_types = sorted(set(page.schema_types))

    # ── Tech stack heuristics ─────────────────────────
    # WordPress
    if not page.tech_stack.cms:
        if "/wp-content/" in html or "/wp-includes/" in html:
            page.tech_stack.cms = "WordPress"
    # Yoast
    if "yoast_wpseo" in html or "Yoast SEO" in html:
        page.tech_stack.seo_plugin = "Yoast"
    elif "rank-math" in html.lower():
        page.tech_stack.seo_plugin = "Rank Math"
    elif "aioseop" in html.lower() or "all-in-one-seo" in html.lower():
        page.tech_stack.seo_plugin = "AIOSEO"
    # Shopify
    if "cdn.shopify.com" in html or "Shopify.shop" in html:
        page.tech_stack.cms = "Shopify"
    # Next.js
    if "__NEXT_DATA__" in html:
        page.tech_stack.framework = "Next.js"
    # Nuxt
    if "__NUXT__" in html:
        page.tech_stack.framework = "Nuxt"
    # Gatsby
    if "___INITIAL_DATA__" in html:
        page.tech_stack.framework = "Gatsby"
    # Squarespace / Wix / Webflow
    if "static.squarespace.com" in html:
        page.tech_stack.cms = "Squarespace"
    elif "static.wixstatic.com" in html:
        page.tech_stack.cms = "Wix"
    elif "webflow.io" in html.lower():
        page.tech_stack.cms = "Webflow"
    # Analytics
    if "gtag(" in html or "google-analytics.com" in html or "googletagmanager.com" in html:
        if "googletagmanager.com" in html:
            page.tech_stack.analytics.append("GTM")
        if "gtag(" in html or "G-" in html:
            page.tech_stack.analytics.append("GA4")
    # CDN signals
    if "cloudflare" in html.lower():
        page.tech_stack.cdn = "Cloudflare"
    # AMP
    if "<html amp" in html or '⚡' in html[:1000]:
        page.tech_stack.has_amp = True

    return page


def _lxml_available() -> bool:
    try:
        import lxml  # noqa
        return True
    except ImportError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse HTML into structured data")
    ap.add_argument("file", type=Path, help="HTML file path (or - for stdin)")
    ap.add_argument("--base-url", default="", help="Base URL (for internal/external link classification)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--extract", help="Comma-separated subset: meta,og,headings,images,links,schema,tech")
    args = ap.parse_args()

    if args.file == Path("-"):
        html = sys.stdin.read()
    else:
        if not args.file.exists():
            print(f"Not found: {args.file}", file=sys.stderr)
            return 2
        html = args.file.read_text(encoding="utf-8")

    try:
        page = parse(html, base_url=args.base_url)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        out = asdict(page)
        # Optional subset filter
        if args.extract:
            keep = set(s.strip() for s in args.extract.split(","))
            section_map = {
                "meta": ["meta"], "og": ["og"], "twitter": ["twitter"],
                "headings": ["h1", "h2", "h3"], "images": ["images"],
                "links": ["links"], "schema": ["json_ld", "schema_types"],
                "tech": ["tech_stack"], "body": ["body_text", "word_count"],
            }
            kept_keys = set()
            for sec in keep:
                kept_keys.update(section_map.get(sec, [sec]))
            out = {k: out[k] for k in kept_keys if k in out}
        # Truncate body_text to avoid massive output
        if "body_text" in out and len(out["body_text"]) > 2000:
            out["body_text"] = out["body_text"][:2000] + "..."
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"Title:       {page.meta.title}")
        print(f"Description: {page.meta.description[:120]}")
        print(f"Canonical:   {page.meta.canonical}")
        print(f"Lang:        {page.meta.lang}")
        print(f"Word count:  {page.word_count}")
        print(f"H1s:         {len(page.h1)}  H2s: {len(page.h2)}  H3s: {len(page.h3)}")
        print(f"Images:      {len(page.images)}  (w/ alt: {sum(1 for i in page.images if i.alt)})")
        print(f"Links:       {len(page.links)}  (external: {sum(1 for l in page.links if l.is_external)})")
        print(f"Schema:      {', '.join(page.schema_types) if page.schema_types else '(none)'}")
        print(f"Tech:        CMS={page.tech_stack.cms}  Framework={page.tech_stack.framework}  SEO={page.tech_stack.seo_plugin}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
