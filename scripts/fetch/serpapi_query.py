"""
scripts/fetch/serpapi_query.py — SerpApi unified query wrapper (pool + rotation + cache).

SerpApi exposes 100+ "engines" through ONE endpoint (https://serpapi.com/search.json)
selected by the `engine` param, so a single wrapper covers them all. The ones that fill
real gaps in this pipeline (Tavily gives generic web search but NOT structured SERP
features or AI-engine answers):

    engine=google                — organic positions, featured snippet, answer_box,
                                    related_questions (People Also Ask), related_searches
    engine=google_ai_overview    — Google AI Overview (AIO) block  ← core GEO signal
    engine=google_autocomplete   — keyword-expansion suggestions
    engine=google_trends         — interest-over-time / seasonality
    engine=google_news / google_scholar / google_local / google_patents / ...
    engine=bing / duckduckgo / baidu / naver (naver also has AI overview) ...

Mirrors the Tavily resilience stack:
  - key-pool round-robin   (serpapi_pool.get_serpapi_key — pools free 250/mo accounts)
  - retry + key rotation   (tavily_retry.with_retry — generic helper) on quota/429/timeout
  - short response cache    (6h; SERP is time-sensitive) in memory/research-cache/
  - cost-ledger logging     ($0 on the free pool; logged for usage visibility)
  - --json output           (cross-host contract)

A quota-exhausted key (250/mo used) makes SerpApi return an error → normalised to a
transient error so with_retry rotates to the next pooled account automatically.

CLI:
    python -m scripts.fetch.serpapi_query --engine google --q "best fishing rods 2026" --json
    python -m scripts.fetch.serpapi_query --engine ai_overview --q "is petg food safe" --json
    python -m scripts.fetch.serpapi_query --engine google_autocomplete --q "3d printer filament" --json

    Note: `ai_overview` is a convenience pseudo-engine — Google's AI Overview is returned
    inline in the `google` engine response, but is occasionally deferred behind a page_token;
    the `ai_overview` engine fetches it from google and auto-follows the token. The raw
    `google_ai_overview` engine needs a `page_token` (not a `q`).
    python -m scripts.fetch.serpapi_query --engine google --q "..." --param location="Austin, Texas" --gl us --hl en
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from scripts._core import cost_ledger, serpapi_engines, serpapi_pool
from scripts._core.tavily_retry import with_retry

SEARCH_URL = "https://serpapi.com/search.json"
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "memory" / "research-cache"
CACHE_TTL_SECONDS = 6 * 3600   # SERP data is time-sensitive; keep TTL short
DEFAULT_TIMEOUT = 30.0

# Per-engine query-param names (youtube=search_query, amazon=k, yahoo=p, …) live in the
# engine registry (scripts/_core/serpapi_engines.py) as the single source of truth, so the
# wrapper and the selector never disagree. Default is `q`.

# SerpApi error fragments meaning "this key is out of monthly searches / rate-limited"
# → rotate to the next pooled account (these are NOT a hard failure of the request).
_QUOTA_MARKERS = (
    "run out of searches", "ran out of searches", "exceeded", "monthly search",
    "plan limit", "429", "rate limit", "quota", "have reached", "no longer has",
)


class SerpApiError(RuntimeError):
    """Hard SerpApi error (bad engine, bad params) — retrying won't help."""


class SerpApiQuotaError(SerpApiError):
    """Quota/rate/connection error — message carries a transient marker so
    tavily_retry.with_retry classifies it as retryable and rotates the key."""


def _cache_key(engine: str, q: str, params: dict[str, Any]) -> str:
    h = hashlib.sha256()
    h.update(b"serpapi")
    h.update(engine.encode("utf-8"))
    h.update(q.encode("utf-8"))
    for k in sorted(params):
        h.update(f"{k}={params[k]}".encode("utf-8"))
    return "serpapi_" + h.hexdigest()[:30]


def _read_cache(key: str) -> dict[str, Any] | None:
    f = CACHE_DIR / f"{key}.json"
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if time.time() - data.get("cached_at", 0) > CACHE_TTL_SECONDS:
            return None
        payload: dict[str, Any] | None = data.get("payload")
        return payload
    except Exception:
        return None


def _write_cache(key: str, payload: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(
        json.dumps({"cached_at": time.time(), "payload": payload}, ensure_ascii=False),
        encoding="utf-8",
    )


def _do_request(api_key: str, engine: str, q: str, params: dict[str, Any]) -> dict[str, Any]:
    """Single SerpApi request. Raises SerpApiQuotaError on quota/rate/connection
    (retryable) and SerpApiError on hard errors (not retryable)."""
    full: dict[str, Any] = {"engine": engine, "api_key": api_key, "output": "json"}
    if q:
        full[serpapi_engines.query_param_for(engine)] = q
    full.update(params)
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.get(SEARCH_URL, params=full)
    except httpx.HTTPError as e:
        raise SerpApiQuotaError(f"serpapi connection/timeout error: {e}") from e

    if resp.status_code == 429:
        raise SerpApiQuotaError("serpapi 429 rate limit / quota")

    try:
        data: dict[str, Any] = resp.json()
    except Exception as e:
        raise SerpApiError(f"serpapi non-JSON response (status {resp.status_code})") from e

    err = data.get("error")
    if err:
        low = str(err).lower()
        if any(m in low for m in _QUOTA_MARKERS):
            raise SerpApiQuotaError(f"serpapi quota/limit: {err}")
        raise SerpApiError(f"serpapi error: {err}")
    if resp.status_code != 200:
        raise SerpApiError(f"serpapi http {resp.status_code}")
    return data


def query(
    engine: str = "google",
    q: str = "",
    *,
    params: dict[str, Any] | None = None,
    use_cache: bool = True,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Run a SerpApi query through the pool with rotation + retry + cache.

    Returns the parsed SerpApi JSON (with an added `_cached` bool). For engine=google
    the useful keys are: organic_results, answer_box, related_questions (PAA),
    related_searches, ai_overview. For google_ai_overview: ai_overview. For
    google_autocomplete: suggestions. For google_trends: interest_over_time.
    """
    params = dict(params or {})
    ckey = _cache_key(engine, q, params)
    if use_cache:
        cached = _read_cache(ckey)
        if cached is not None:
            cached["_cached"] = True
            return cached

    # Cost guard — free pool is $0, but every external API call still flows through
    # the ledger (project rule). Never let a ledger hiccup kill a free call.
    est = None
    try:
        est = cost_ledger.estimate("serpapi", serpapi_searches=1)
        if cost_ledger.check(est, scope="per_article") == "blocked":
            raise SerpApiError("serpapi call would exceed configured budget")
    except SerpApiError:
        raise
    except Exception:
        est = None

    data = with_retry(
        lambda api_key: _do_request(api_key, engine, q, params),
        get_key=serpapi_pool.get_serpapi_key,
        max_attempts=min(max(4, serpapi_pool.pool_size()), 40),
        base_delay=0.3,
        max_delay=3.0,
        label=f"serpapi.{engine}",
    )

    if est is not None:
        try:
            cost_ledger.log(
                est, endpoint=f"serpapi.{engine}", task_id=task_id,
                extra={"engine": engine, "q": q[:120]},
            )
        except Exception:
            pass

    data["_cached"] = False
    if use_cache:
        _write_cache(ckey, data)
    return data


def ai_overview(
    q: str,
    *,
    params: dict[str, Any] | None = None,
    use_cache: bool = True,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Get Google's AI Overview (AIO) for a query — the core GEO signal.

    SerpApi returns the AIO inline in the `google` engine response most of the time;
    occasionally it returns a deferred reference carrying only a `page_token`, which must
    be fetched via the `google_ai_overview` engine. This helper handles both so callers
    never have to think about page tokens. Returns:
        {"ai_overview": <block-or-None>, "_source": "inline"|"page_token"|"none", "_cached": bool}
    """
    base = query("google", q, params=params, use_cache=use_cache, task_id=task_id)
    aio = base.get("ai_overview")
    if not aio:
        return {"ai_overview": None, "_source": "none", "_cached": base.get("_cached", False)}
    # Deferred AIO: only a page_token, no rendered content yet → follow it.
    if isinstance(aio, dict) and aio.get("page_token") and not aio.get("text_blocks"):
        follow = query("google_ai_overview", "", params={"page_token": aio["page_token"]},
                       use_cache=use_cache, task_id=task_id)
        return {"ai_overview": follow.get("ai_overview", follow),
                "_source": "page_token", "_cached": follow.get("_cached", False)}
    return {"ai_overview": aio, "_source": "inline", "_cached": base.get("_cached", False)}


def _summary(engine: str, data: dict[str, Any]) -> str:
    """Short human summary of the most SEO-relevant fields."""
    parts = [f"engine={engine}  cached={data.get('_cached')}"]
    if data.get("organic_results"):
        parts.append(f"organic={len(data['organic_results'])}")
    if data.get("related_questions"):
        parts.append(f"PAA={len(data['related_questions'])}")
    if data.get("related_searches"):
        parts.append(f"related={len(data['related_searches'])}")
    if data.get("ai_overview"):
        parts.append("ai_overview=YES")
    if data.get("answer_box"):
        parts.append("answer_box=YES")
    if data.get("suggestions"):
        parts.append(f"autocomplete={len(data['suggestions'])}")
    return "  ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="SerpApi unified query (pool + rotation + cache)")
    ap.add_argument("--engine", default="google", help="SerpApi engine (google, google_ai_overview, google_autocomplete, google_trends, ...)")
    ap.add_argument("--q", default="", help="Query string")
    ap.add_argument("--param", action="append", default=[], metavar="K=V",
                    help="Passthrough SerpApi param (repeatable), e.g. --param location=\"Austin, Texas\"")
    ap.add_argument("--gl", help="Country code (e.g. us)")
    ap.add_argument("--hl", help="UI language (e.g. en)")
    ap.add_argument("--location", help="Geographic location for the search")
    ap.add_argument("--num", type=int, help="Number of results")
    ap.add_argument("--google-domain", help="e.g. google.com")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--task-id")
    args = ap.parse_args()

    params: dict[str, Any] = {}
    for kv in args.param:
        if "=" in kv:
            k, v = kv.split("=", 1)
            params[k.strip()] = v
    if args.gl:
        params["gl"] = args.gl
    if args.hl:
        params["hl"] = args.hl
    if args.location:
        params["location"] = args.location
    if args.num is not None:
        params["num"] = args.num
    if args.google_domain:
        params["google_domain"] = args.google_domain

    try:
        if args.engine == "ai_overview":
            # Convenience pseudo-engine: get AIO inline from google, auto-following a
            # page_token if SerpApi defers it (the raw google_ai_overview engine needs
            # a page_token, NOT a q).
            data = ai_overview(args.q, params=params,
                               use_cache=not args.no_cache, task_id=args.task_id)
        else:
            data = query(args.engine, args.q, params=params,
                         use_cache=not args.no_cache, task_id=args.task_id)
    except SerpApiError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(_summary(args.engine, data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
