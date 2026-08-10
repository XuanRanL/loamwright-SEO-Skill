"""
scripts/fetch/tavily_extract.py — Extract structured content from URLs via Tavily.

v3.2 defaults (per user 2026-05 directive):
    - extract_depth = "advanced" (better for difficult pages, tables, embedded elements)
    - format = "markdown" (cleaner than HTML for LLM consumption)
    - include_favicon = True

Pricing (verified 2026-05):
    basic     1 credit / 5 URLs
    advanced  2 credits / 5 URLs (v3.2 default)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from scripts._core import credential_hub, cost_ledger
from scripts._core.ssrf_guard import validate_url, SSRFError


CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "memory" / "research-cache" / "extract"
CACHE_TTL_SECONDS = 72 * 3600

DEFAULT_DEPTH: Literal["basic", "advanced"] = "advanced"
DEFAULT_FORMAT: Literal["markdown", "text"] = "markdown"


@dataclass
class ExtractedPage:
    url: str
    title: str | None
    content: str
    raw_content: str | None = None
    images: list = field(default_factory=list)
    favicon: str | None = None
    error: str | None = None
    cached: bool = False


def _cache_key(url: str, depth: str, fmt: str) -> str:
    return hashlib.sha256(f"{depth}|{fmt}|{url}".encode("utf-8")).hexdigest()[:32]


def _read_cache(key: str) -> dict | None:
    f = CACHE_DIR / f"{key}.json"
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if time.time() - data.get("cached_at", 0) > CACHE_TTL_SECONDS:
            return None
        return data
    except Exception:
        return None


def _write_cache(key: str, payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload["cached_at"] = time.time()
    (CACHE_DIR / f"{key}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def extract(
    urls: list[str] | str,
    *,
    depth: Literal["basic", "advanced"] = DEFAULT_DEPTH,
    format: Literal["markdown", "text"] = DEFAULT_FORMAT,
    include_images: bool = False,
    include_favicon: bool = True,
    use_cache: bool = True,
    task_id: str | None = None,
) -> list[ExtractedPage]:
    """Extract URL content via Tavily. v3.2 default depth=advanced (2 credits / 5 URLs)."""
    if isinstance(urls, str):
        urls = [urls]

    safe_urls = []
    for u in urls:
        try:
            validate_url(u)
            safe_urls.append(u)
        except SSRFError as e:
            print(f"SSRF reject: {u}: {e}", file=sys.stderr)
    if not safe_urls:
        return []

    cached_results: dict[str, ExtractedPage] = {}
    to_fetch: list[str] = []
    if use_cache:
        for u in safe_urls:
            key = _cache_key(u, depth, format)
            data = _read_cache(key)
            if data:
                cached_results[u] = ExtractedPage(
                    url=u, title=data.get("title"),
                    content=data.get("content", ""),
                    raw_content=data.get("raw_content"),
                    images=data.get("images", []),
                    favicon=data.get("favicon"),
                    error=None, cached=True,
                )
            else:
                to_fetch.append(u)
    else:
        to_fetch = safe_urls[:]

    fetched: dict[str, ExtractedPage] = {}
    if to_fetch:
        try:
            from tavily import TavilyClient
        except ImportError as e:
            raise RuntimeError("tavily-python not installed") from e

        from scripts._core.tavily_retry import with_retry

        estimate = cost_ledger.estimate(
            "tavily",
            tavily_extract_urls=len(to_fetch),
            tavily_extract_advanced=(depth == "advanced"),
        )
        decision = cost_ledger.check(estimate, scope="per_article")
        if decision == "blocked":
            raise RuntimeError(f"Tavily extract would exceed budget: ${estimate.estimated_usd}")

        # Retry transient failures with key rotation across the pool.
        try:
            raw = with_retry(
                lambda api_key: TavilyClient(api_key=api_key).extract(
                    urls=to_fetch, extract_depth=depth, format=format,
                    include_images=include_images, include_favicon=include_favicon,
                ),
                get_key=credential_hub.get_tavily_key,
                label="tavily.extract",
            )
        except Exception as e:
            raise RuntimeError(f"Tavily extract failed: {e}") from e

        cost_ledger.log(
            estimate, endpoint="tavily.extract", task_id=task_id,
            extra={"url_count": len(to_fetch), "depth": depth, "format": format},
        )

        for item in raw.get("results", []):
            url = item.get("url", "")
            ep = ExtractedPage(
                url=url, title=item.get("title"),
                content=item.get("raw_content") or item.get("content", ""),
                raw_content=item.get("raw_content"),
                images=item.get("images", []),
                favicon=item.get("favicon"),
                error=None, cached=False,
            )
            fetched[url] = ep
            if use_cache:
                _write_cache(_cache_key(url, depth, format), {
                    "title": ep.title, "content": ep.content,
                    "raw_content": ep.raw_content, "images": ep.images,
                    "favicon": ep.favicon,
                })

        for fail in raw.get("failed_results", []):
            fetched[fail.get("url", "")] = ExtractedPage(
                url=fail.get("url", ""), title=None, content="",
                error=fail.get("error", "unknown"),
            )

    out: list[ExtractedPage] = []
    for u in safe_urls:
        if u in cached_results:
            out.append(cached_results[u])
        elif u in fetched:
            out.append(fetched[u])
        else:
            out.append(ExtractedPage(url=u, title=None, content="", error="not returned"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Tavily URL extractor (v3.2 advanced default)")
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--depth", choices=["basic", "advanced"], default=DEFAULT_DEPTH)
    ap.add_argument("--format", choices=["markdown", "text"], default=DEFAULT_FORMAT)
    ap.add_argument("--images", action="store_true")
    ap.add_argument("--no-favicon", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--task-id")
    args = ap.parse_args()

    try:
        results = extract(
            args.urls, depth=args.depth, format=args.format,
            include_images=args.images, include_favicon=not args.no_favicon,
            use_cache=not args.no_cache, task_id=args.task_id,
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))
    else:
        for r in results:
            cache_note = " (cached)" if r.cached else ""
            if r.error:
                print(f"  ✗ {r.url}: {r.error}{cache_note}")
            else:
                print(f"  ✓ {r.url}{cache_note}")
                print(f"      title: {r.title}")
                print(f"      content: {r.content[:200]}...")
                if r.images:
                    print(f"      images: {len(r.images)}")
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
