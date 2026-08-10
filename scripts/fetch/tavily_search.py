"""
scripts/fetch/tavily_search.py — Web search via Tavily API (advanced default).

v3.2 defaults (per user 2026-05 directive + Tavily official docs verification):
    - search_depth = "advanced" (2 credits/call; richer relevance)
    - chunks_per_source = 3 (max per official docs; 500 chars/chunk)
    - include_answer = "advanced"
    - include_raw_content = "markdown"
    - include_usage = True (visibility into credit consumption)
    - topic = "general" (or "news"/"finance" per query type)

Pricing (verified 2026-05 https://docs.tavily.com/documentation/api-reference/endpoint/search):
    basic       1 credit  — balanced relevance/latency, 1 NLP summary
    advanced    2 credits — highest relevance, multi-chunk per URL (v3.2 default)
    fast        1 credit  — lower latency, multi-chunk
    ultra-fast  1 credit  — minimum latency, 1 NLP summary

Free tier: 1000 credits/mo. PAYG: $0.008/credit.
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


CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "memory" / "research-cache"
CACHE_TTL_SECONDS = 72 * 3600


# v3.2 defaults
DEFAULT_DEPTH: Literal["basic", "advanced", "fast", "ultra-fast"] = "advanced"
DEFAULT_CHUNKS_PER_SOURCE: int = 3   # Official max per Tavily docs
DEFAULT_INCLUDE_ANSWER: Literal["basic", "advanced", False] = "advanced"
DEFAULT_INCLUDE_RAW_CONTENT: Literal["markdown", "text", False] = "markdown"
DEFAULT_MAX_RESULTS = 10
DEFAULT_INCLUDE_USAGE = True


@dataclass
class TavilyResult:
    title: str
    url: str
    content: str
    score: float = 0.0
    published_date: str | None = None
    raw_content: str | None = None
    favicon: str | None = None


@dataclass
class TavilySearchResponse:
    query: str
    answer: str | None
    results: list[TavilyResult]
    images: list = field(default_factory=list)
    response_time: float = 0
    cached: bool = False
    cost_credits: int = 0
    cost_usd: float = 0.0
    usage: dict | None = None
    request_id: str | None = None


def _cache_key(query: str, depth: str, max_results: int, **kwargs) -> str:
    h = hashlib.sha256()
    h.update(query.encode("utf-8"))
    h.update(depth.encode("utf-8"))
    h.update(str(max_results).encode("utf-8"))
    for k in sorted(kwargs):
        h.update(f"{k}={kwargs[k]}".encode("utf-8"))
    return h.hexdigest()[:32]


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


def search(
    query: str,
    *,
    depth: Literal["basic", "advanced", "fast", "ultra-fast"] = DEFAULT_DEPTH,
    max_results: int = DEFAULT_MAX_RESULTS,
    chunks_per_source: int = DEFAULT_CHUNKS_PER_SOURCE,
    topic: Literal["general", "news", "finance"] = "general",
    include_answer: bool | str = DEFAULT_INCLUDE_ANSWER,
    include_raw_content: bool | str = DEFAULT_INCLUDE_RAW_CONTENT,
    include_usage: bool = DEFAULT_INCLUDE_USAGE,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    include_images: bool = False,
    time_range: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    country: str | None = None,
    auto_parameters: bool = False,
    use_cache: bool = True,
    task_id: str | None = None,
) -> TavilySearchResponse:
    """Search Tavily — v3.2 defaults: advanced depth, chunks=3, answer=advanced."""
    if depth != "advanced":
        chunks_per_source = 3
    if chunks_per_source > 3:
        chunks_per_source = 3   # Official max per Tavily docs

    extra_keys = {
        "topic": topic, "include_domains": include_domains,
        "exclude_domains": exclude_domains, "include_answer": include_answer,
        "include_raw_content": include_raw_content,
        "chunks_per_source": chunks_per_source,
        "time_range": time_range, "start_date": start_date, "end_date": end_date,
        "country": country,
    }
    key = _cache_key(query, depth, max_results, **extra_keys)

    if use_cache:
        cached = _read_cache(key)
        if cached:
            return TavilySearchResponse(
                query=query, answer=cached.get("answer"),
                results=[TavilyResult(**r) for r in cached.get("results", [])],
                images=cached.get("images", []),
                response_time=cached.get("response_time", 0),
                cached=True, cost_credits=0, cost_usd=0.0,
                usage=cached.get("usage"), request_id=cached.get("request_id"),
            )

    advanced_call = (depth == "advanced")
    estimate = cost_ledger.estimate(
        "tavily",
        tavily_calls_basic=0 if advanced_call else 1,
        tavily_calls_advanced=1 if advanced_call else 0,
    )
    decision = cost_ledger.check(estimate, scope="per_article")
    if decision == "blocked":
        raise RuntimeError(f"Tavily call would exceed budget: ${estimate.estimated_usd}")

    try:
        from tavily import TavilyClient
    except ImportError as e:
        raise RuntimeError("tavily-python not installed: pip install tavily-python") from e

    from scripts._core.tavily_retry import with_retry

    t0 = time.time()

    # Tavily rejects queries >400 chars with HTTP 400 (BadRequestError) — a
    # non-transient fail-fast in tavily_retry, i.e. a guaranteed caller crash.
    # No legitimate >400 query exists, so cap here (single source of truth for
    # every caller) with an observable warning instead of an API error.
    if len(query) > 400:
        print(
            f"⚠ tavily.search: query {len(query)} chars > 400-char API cap — "
            "truncating at word boundary (fix the caller to pass a shorter query)",
            file=sys.stderr,
        )
        query = query[:397].rsplit(" ", 1)[0]

    params: dict = {
        "query": query, "search_depth": depth, "max_results": max_results,
        "topic": topic, "include_images": include_images,
    }
    if depth == "advanced":
        params["chunks_per_source"] = chunks_per_source
    if include_answer is not False:
        params["include_answer"] = include_answer
    if include_raw_content is not False:
        params["include_raw_content"] = include_raw_content
    if include_usage:
        params["include_usage"] = True
    if include_domains:
        params["include_domains"] = include_domains
    if exclude_domains:
        params["exclude_domains"] = exclude_domains
    if time_range:
        params["time_range"] = time_range
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    if country and topic == "general":
        params["country"] = country
    if auto_parameters:
        params["auto_parameters"] = True

    # Retry transient failures (429/quota/connection) with key rotation across the pool.
    try:
        raw = with_retry(
            lambda api_key: TavilyClient(api_key=api_key).search(**params),
            get_key=credential_hub.get_tavily_key,
            label="tavily.search",
        )
    except Exception as e:
        raise RuntimeError(f"Tavily search failed: {e}") from e

    elapsed = time.time() - t0
    credits = 2 if advanced_call else 1

    cost_ledger.log(
        estimate, endpoint="tavily.search", task_id=task_id,
        extra={
            "query": query[:120], "depth": depth, "credits": credits,
            "max_results": max_results,
        },
    )

    results = [
        TavilyResult(
            title=r.get("title", ""), url=r.get("url", ""),
            content=r.get("content", ""), score=float(r.get("score", 0.0)),
            published_date=r.get("published_date"),
            raw_content=r.get("raw_content") if include_raw_content else None,
            favicon=r.get("favicon"),
        )
        for r in raw.get("results", [])
    ]

    response = TavilySearchResponse(
        query=query, answer=raw.get("answer"),
        results=results, images=raw.get("images", []),
        response_time=round(elapsed, 3),
        cached=False, cost_credits=credits,
        cost_usd=float(estimate.estimated_usd),
        usage=raw.get("usage"), request_id=raw.get("request_id"),
    )

    if use_cache:
        _write_cache(key, {
            "query": query, "answer": response.answer,
            "results": [asdict(r) for r in response.results],
            "images": response.images,
            "response_time": response.response_time,
            "usage": response.usage, "request_id": response.request_id,
        })

    return response


def main() -> int:
    ap = argparse.ArgumentParser(description="Tavily web search (v3.2 defaults: advanced + chunks=3)")
    ap.add_argument("query")
    ap.add_argument("--depth", choices=["basic", "advanced", "fast", "ultra-fast"], default=DEFAULT_DEPTH)
    ap.add_argument("--max", type=int, default=DEFAULT_MAX_RESULTS)
    ap.add_argument("--chunks", type=int, default=DEFAULT_CHUNKS_PER_SOURCE)
    ap.add_argument("--topic", choices=["general", "news", "finance"], default="general")
    ap.add_argument("--answer", choices=["basic", "advanced", "false"], default="advanced")
    ap.add_argument("--raw", choices=["markdown", "text", "false"], default="markdown")
    ap.add_argument("--time-range", choices=["day", "week", "month", "year", "d", "w", "m", "y"])
    ap.add_argument("--start-date")
    ap.add_argument("--end-date")
    ap.add_argument("--country")
    ap.add_argument("--include", action="append", default=[])
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--images", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--task-id")
    args = ap.parse_args()

    answer_param: bool | str = args.answer if args.answer != "false" else False
    raw_param: bool | str = args.raw if args.raw != "false" else False

    try:
        r = search(
            args.query, depth=args.depth, max_results=args.max,
            chunks_per_source=args.chunks, topic=args.topic,
            include_answer=answer_param, include_raw_content=raw_param,
            time_range=args.time_range, start_date=args.start_date,
            end_date=args.end_date, country=args.country,
            include_domains=args.include, exclude_domains=args.exclude,
            include_images=args.images, auto_parameters=args.auto,
            use_cache=not args.no_cache, task_id=args.task_id,
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({
            "query": r.query, "answer": r.answer,
            "results": [asdict(x) for x in r.results], "images": r.images,
            "response_time": r.response_time, "cached": r.cached,
            "cost_credits": r.cost_credits, "cost_usd": r.cost_usd,
            "usage": r.usage, "request_id": r.request_id,
        }, indent=2, ensure_ascii=False))
    else:
        cache_note = " (cached)" if r.cached else ""
        print(f"Query: {r.query}  [{r.response_time}s, {r.cost_credits} credits, ${r.cost_usd:.4f}]{cache_note}")
        if r.usage:
            print(f"Usage: {r.usage}")
        if r.answer:
            print(f"\nAI Answer: {r.answer[:500]}{'...' if len(r.answer) > 500 else ''}")
        print(f"\nResults ({len(r.results)}):")
        for i, item in enumerate(r.results, 1):
            print(f"  [{i}] {item.title}")
            print(f"      {item.url}  (score {item.score:.2f})")
            print(f"      {item.content[:200]}...")
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
