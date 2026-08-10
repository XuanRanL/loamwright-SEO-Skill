#!/usr/bin/env python3
"""Parse HTML and extract SEO-relevant elements for site audit.

Usage:
    python -m scripts.audit.parse_html page.html --url https://example.com --json
    cat page.html | python -m scripts.audit.parse_html --url https://example.com
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

try:
    import lxml  # noqa: F401
    _HTML_PARSER = "lxml"
except ImportError:
    _HTML_PARSER = "html.parser"

_PERFMATTERS_ATTRS = ("data-perfmatters-src", "data-perfmatters-srcset")
_EWWW_ATTRS = ("data-ewww-src", "data-eio")
_GENERIC_LAZY_ATTRS = ("data-src", "data-lazy-src", "data-original", "data-srcset")
_PERFMATTERS_CLASSES = {"perfmatters-lazy", "perfmatters-lazy-loaded"}
_EWWW_CLASSES = {"lazyload-eio", "lazyloaded-eio"}
_GENERIC_LAZY_CLASSES = {"lazyload", "lazyloaded", "lazy", "lazy-loaded"}


def _detect_lazy_method(img: Tag) -> str:
    """Classify image lazy-loading: native|perfmatters|ewww|js-generic|none."""
    if img.get("loading", "").lower() == "lazy":
        return "native"

    class_list = set(img.get("class", []) or [])

    if any(img.get(a) for a in _PERFMATTERS_ATTRS) or class_list & _PERFMATTERS_CLASSES:
        return "perfmatters"
    if any(img.get(a) for a in _EWWW_ATTRS) or class_list & _EWWW_CLASSES:
        return "ewww"
    if any(img.get(a) for a in _GENERIC_LAZY_ATTRS) or class_list & _GENERIC_LAZY_CLASSES:
        return "js-generic"

    return "none"


def parse_html(html: str, base_url: Optional[str] = None) -> dict[str, Any]:
    """Parse HTML and extract SEO elements.

    Returns dict with: title, meta_description, meta_robots, canonical,
    h1-h3 lists, images, links (internal/external), schema, open_graph,
    twitter_card, word_count, hreflang, security_headers_hints.
    """
    soup = BeautifulSoup(html, _HTML_PARSER)

    result: dict[str, Any] = {
        "title": None,
        "meta_description": None,
        "meta_robots": None,
        "canonical": None,
        "h1": [],
        "h2": [],
        "h3": [],
        "h1_suspicious": [],
        "h2_suspicious": [],
        "h3_suspicious": [],
        "images": [],
        "links": {"internal": [], "external": []},
        "schema": [],
        "open_graph": {},
        "twitter_card": {},
        "word_count": 0,
        "hreflang": [],
        "viewport": None,
        "charset": None,
        "lang": None,
    }

    html_tag = soup.find("html")
    if html_tag and isinstance(html_tag, Tag):
        result["lang"] = html_tag.get("lang")

    title_tag = soup.find("title")
    if title_tag:
        result["title"] = title_tag.get_text(strip=True)

    for meta in soup.find_all("meta"):
        name = (meta.get("name") or "").lower()
        property_attr = (meta.get("property") or "").lower()
        content = meta.get("content", "")
        charset = meta.get("charset")

        if charset:
            result["charset"] = charset
        if name == "description":
            result["meta_description"] = content
        elif name == "robots":
            result["meta_robots"] = content
        elif name == "viewport":
            result["viewport"] = content

        if property_attr.startswith("og:"):
            result["open_graph"][property_attr] = content
        if name.startswith("twitter:"):
            result["twitter_card"][name] = content

    canonical = soup.find("link", rel="canonical")
    if canonical and isinstance(canonical, Tag):
        result["canonical"] = canonical.get("href")

    for link in soup.find_all("link", rel="alternate"):
        hreflang = link.get("hreflang")
        if hreflang:
            result["hreflang"].append({"lang": hreflang, "href": link.get("href")})

    for tag in ("h1", "h2", "h3"):
        for heading in soup.find_all(tag):
            text = heading.get_text(strip=True)
            if text:
                result[tag].append(text)
                stripped = text.strip()
                is_suspicious = (
                    len(stripped) <= 3
                    or stripped.replace(",", "").replace(".", "").replace("+", "")
                    .replace("-", "").replace("%", "").replace(" ", "").isdigit()
                )
                if is_suspicious:
                    result[f"{tag}_suspicious"].append(text)

    for img in soup.find_all("img"):
        src = img.get("src", "")
        if base_url and src:
            src = urljoin(base_url, src)
        result["images"].append({
            "src": src,
            "alt": img.get("alt"),
            "width": img.get("width"),
            "height": img.get("height"),
            "loading": img.get("loading"),
            "lazy_method": _detect_lazy_method(img),
        })

    if base_url:
        base_domain = urlparse(base_url).netloc
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            link_data = {
                "href": full_url,
                "text": a.get_text(strip=True)[:100],
                "rel": a.get("rel", []),
                "nofollow": "nofollow" in (a.get("rel") or []),
            }
            if parsed.netloc == base_domain:
                result["links"]["internal"].append(link_data)
            else:
                result["links"]["external"].append(link_data)

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            schema_data = json.loads(script.string or "")
            if isinstance(schema_data, dict) and "@graph" in schema_data:
                for item in schema_data["@graph"]:
                    if isinstance(item, dict):
                        result["schema"].append(item)
            elif isinstance(schema_data, list):
                for item in schema_data:
                    if isinstance(item, dict):
                        result["schema"].append(item)
            else:
                result["schema"].append(schema_data)
        except (json.JSONDecodeError, TypeError):
            pass

    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()
    text = soup.get_text(separator=" ", strip=True)
    words = re.findall(r"\b\w+\b", text)
    result["word_count"] = len(words)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse HTML for SEO audit")
    parser.add_argument("file", nargs="?", help="HTML file (stdin if omitted)")
    parser.add_argument("--url", "-u", help="Base URL for resolving links")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()

    if args.file:
        path = Path(args.file).resolve()
        if not path.is_file():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        html = path.read_text(encoding="utf-8")
    else:
        html = sys.stdin.read()

    result = parse_html(html, args.url)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Title: {result['title']}")
        print(f"Meta Description: {result['meta_description']}")
        print(f"Canonical: {result['canonical']}")
        print(f"H1: {len(result['h1'])} | H2: {len(result['h2'])} | H3: {len(result['h3'])}")
        print(f"Images: {len(result['images'])}")
        print(f"Internal Links: {len(result['links']['internal'])}")
        print(f"External Links: {len(result['links']['external'])}")
        print(f"Schema Blocks: {len(result['schema'])}")
        print(f"Word Count: {result['word_count']}")


if __name__ == "__main__":
    main()
