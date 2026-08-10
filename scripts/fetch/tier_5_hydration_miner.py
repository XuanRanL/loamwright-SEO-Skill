"""scripts/fetch/tier_5_hydration_miner.py — Tier 5 fallback: extract embedded JSON from SSR pages.

Modern SSR frameworks embed page data as JSON inside the initial HTML:
  - Next.js:    <script id="__NEXT_DATA__" type="application/json">...
  - Nuxt:       window.__NUXT__ = {...}
  - Gatsby:     window.___INITIAL_DATA__ = {...}
  - Remix:      window.__remixContext = {...}
  - Shopify Hydrogen: data-flight payload
  - Generic:    <script type="application/json">...

When Tiers 1-4 fail (Tavily, patchright, Firecrawl, jina.ai/reader), this miner
parses raw HTML to extract whatever JSON the framework leaked.

Always works as last resort because we just need the bytes of the response.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class HydrationData:
    framework_detected: str | None = None
    next_data: dict | None = None
    nuxt_data: dict | None = None
    gatsby_data: dict | None = None
    remix_data: dict | None = None
    json_scripts: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)  # title / description / etc
    word_count_estimate: int = 0


def mine(html: str) -> HydrationData:
    """Extract all hydration data from raw HTML."""
    data = HydrationData()

    # Detect framework
    if "__NEXT_DATA__" in html:
        data.framework_detected = "Next.js"
    elif "__NUXT__" in html or "window.__nuxt__" in html.lower():
        data.framework_detected = "Nuxt"
    elif "___INITIAL_DATA__" in html or "window.___gatsby" in html.lower():
        data.framework_detected = "Gatsby"
    elif "__remixContext" in html:
        data.framework_detected = "Remix"
    elif "data-flight" in html and "shopify" in html.lower():
        data.framework_detected = "Shopify Hydrogen"
    elif "<script type=\"application/json\"" in html:
        data.framework_detected = "Generic SSR"

    # Next.js
    m = re.search(
        r'<script[^>]+id="__NEXT_DATA__"[^>]+type="application/json"[^>]*>(.*?)</script>',
        html, re.DOTALL,
    )
    if m:
        try:
            data.next_data = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Nuxt
    m = re.search(r"window\.__NUXT__\s*=\s*(\{.+?\})\s*;?\s*</script>", html, re.DOTALL)
    if m:
        try:
            data.nuxt_data = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Gatsby
    m = re.search(r"window\.___INITIAL_DATA__\s*=\s*(\{.+?\})\s*;?\s*</script>", html, re.DOTALL)
    if m:
        try:
            data.gatsby_data = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Remix
    m = re.search(r"window\.__remixContext\s*=\s*(\{.+?\})\s*;?\s*</script>", html, re.DOTALL)
    if m:
        try:
            data.remix_data = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Generic application/json scripts (e.g. JSON-LD, custom config)
    for m in re.finditer(
        r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>(.*?)</script>',
        html, re.DOTALL,
    ):
        try:
            obj = json.loads(m.group(1))
            data.json_scripts.append(obj)
        except json.JSONDecodeError:
            continue

    # Basic metadata from HTML
    title_m = re.search(r"<title[^>]*>(.+?)</title>", html, re.DOTALL | re.IGNORECASE)
    if title_m:
        data.metadata["title"] = title_m.group(1).strip()
    desc_m = re.search(
        r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html, re.IGNORECASE,
    )
    if desc_m:
        data.metadata["description"] = desc_m.group(1).strip()

    # Word count estimate (strip tags)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    data.word_count_estimate = len(text.split())

    return data


def extract_content_from_hydration(data: HydrationData) -> str:
    """Best-effort: pull readable text content from hydration JSON.

    Each framework has different structure. We do a generic recursive walk
    looking for text fields ("content", "body", "text", "html", "raw").
    """
    candidates = [
        data.next_data, data.nuxt_data, data.gatsby_data,
        data.remix_data,
    ]
    candidates = [c for c in candidates if c]
    if not candidates:
        return ""

    def walk(obj, parts: list, depth: int = 0):
        if depth > 8:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and len(v) > 50 and k.lower() in {
                    "content", "body", "text", "description", "html", "raw",
                    "markdown", "richtext", "excerpt",
                }:
                    parts.append(v)
                else:
                    walk(v, parts, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, parts, depth + 1)

    parts: list[str] = []
    for c in candidates:
        walk(c, parts)
    return "\n\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Mine hydration JSON from HTML (Tier 5 fallback)")
    ap.add_argument("file", type=Path, help="HTML file or - for stdin")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--extract-content", action="store_true",
                    help="Try to pull readable text content from hydration data")
    args = ap.parse_args()

    if str(args.file) == "-":
        html = sys.stdin.read()
    else:
        if not args.file.exists():
            print(f"Not found: {args.file}", file=sys.stderr)
            return 2
        html = args.file.read_text(encoding="utf-8")

    data = mine(html)

    if args.extract_content:
        text = extract_content_from_hydration(data)
        if args.json:
            print(json.dumps({
                "framework_detected": data.framework_detected,
                "extracted_content": text[:3000] + "..." if len(text) > 3000 else text,
                "extracted_word_count": len(text.split()),
            }, indent=2, ensure_ascii=False))
        else:
            print(f"Framework: {data.framework_detected}")
            print(f"Extracted: {len(text.split())} words")
            print("---")
            print(text[:2000])
        return 0

    if args.json:
        # Trim huge JSON for output
        out = {
            "framework_detected": data.framework_detected,
            "has_next_data": data.next_data is not None,
            "has_nuxt_data": data.nuxt_data is not None,
            "has_gatsby_data": data.gatsby_data is not None,
            "has_remix_data": data.remix_data is not None,
            "json_scripts_count": len(data.json_scripts),
            "metadata": data.metadata,
            "word_count_estimate": data.word_count_estimate,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"Framework detected: {data.framework_detected}")
        for fw_name, fw_data in [
            ("Next.js", data.next_data),
            ("Nuxt", data.nuxt_data),
            ("Gatsby", data.gatsby_data),
            ("Remix", data.remix_data),
        ]:
            print(f"  {fw_name}: {'✓ found' if fw_data else '—'}")
        print(f"  JSON-LD scripts: {len(data.json_scripts)}")
        print(f"  Title: {data.metadata.get('title', '')}")
        print(f"  Description: {data.metadata.get('description', '')[:100]}")
        print(f"  Word count estimate: {data.word_count_estimate}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
