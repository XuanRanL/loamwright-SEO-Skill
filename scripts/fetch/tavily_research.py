"""
scripts/fetch/tavily_research.py — Tavily Deep Research API (new in v3.2).

NEW endpoint (verified 2026-05 https://docs.tavily.com/documentation/api-reference/endpoint/research):
    POST https://api.tavily.com/research

The Research endpoint performs end-to-end deep research via a single API call:
  - Multi-step iterative searches
  - Multi-angle reasoning
  - Multi-agent coordination
  - Deduplication + synthesis
  - Structured JSON output with citations

v3.2 default: model="pro" (comprehensive, multi-angle research)

Model options (per official docs):
    "mini"  — Targeted, efficient. Best for narrow / well-scoped questions.
    "pro"   — Comprehensive. Multi-angle for complex topics across multiple subtopics. (v3.2 default)
    "auto"  — Tavily decides

Citation formats:
    "numbered" (default per docs)
    "mla"
    "apa"      ← v3.2 default for our APA workflow
    "chicago"

Use cases in v3.2 pipeline:
  - /init Stage 3 (Brand Identity) — research a company comprehensively
  - /init Stage 8 (Competitor ID) — find true competitors via deep research
  - /article Phase Research advanced mode — replace shallow tavily_search
  - GEO probing — comprehensive AI engine analysis

Cost (TBD per official docs — not yet published; budget guard):
  - Single research call likely 10-30+ credits per docs implications
  - cost_guard config has per_init_usd and per_article_usd to cap

Pricing safety: we estimate 30 credits per research call as conservative default.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import httpx

from scripts._core import credential_hub, cost_ledger
from scripts._core.ssrf_guard import validate_url


CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "memory" / "research-cache" / "deep-research"
CACHE_TTL_SECONDS = 7 * 24 * 3600  # 1 week (deep research is expensive; cache longer)

TAVILY_RESEARCH_URL = "https://api.tavily.com/research"

DEFAULT_MODEL: Literal["mini", "pro", "auto"] = "pro"   # v3.2 default
DEFAULT_CITATION_FORMAT: Literal["numbered", "mla", "apa", "chicago"] = "apa"
DEFAULT_TIMEOUT = 300  # seconds; bounded (2026-06-04) so a stuck/async-pending
#                        research job fails over to the advanced-search fallback in
#                        5 min instead of hanging for 10. Pro research that needs
#                        longer is async anyway and returns status="pending".

# Conservative cost estimate (Tavily doesn't publish exact research credit cost)
ESTIMATED_CREDITS_PER_CALL = {"mini": 10, "pro": 30, "auto": 20}


@dataclass
class ResearchResponse:
    request_id: str
    status: str                 # "pending" / "completed" / "failed"
    input: str
    model: str
    response_time_seconds: float
    output: dict | None = None   # structured JSON output
    citations: list = field(default_factory=list)
    cached: bool = False
    cost_credits_estimated: int = 30
    cost_usd_estimated: float = 0.24


def _cache_key(input_str: str, model: str, schema: dict | None) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(input_str.encode("utf-8"))
    h.update(model.encode("utf-8"))
    if schema:
        h.update(json.dumps(schema, sort_keys=True).encode("utf-8"))
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


# Real /research job lifecycle (observed 2026-07-01, recorded in the batch
# deep-research.stderr artifacts): pending -> in_progress -> completed|failed.
# v3.31.1's poll fix hardcoded the non-terminal set to {"pending"} only, so the
# first poll that saw "in_progress" returned it as FINAL (9-16s early exit; all
# three researchers of the 07-01b batch lost the pro job to MCP fallback again).
# Keep polling while the status is any known non-terminal value.
_NON_TERMINAL_STATUSES = frozenset({"pending", "in_progress"})


def _poll_research_job(
    initial: dict,
    api_key: str | None,
    *,
    deadline_seconds: int,
    interval_seconds: int,
) -> dict:
    """Poll GET /research/{request_id} until the async job reaches a terminal state.

    2026-07-01: the /research endpoint answers ``200 {status:"pending",
    request_id}`` when a job outlives the synchronous window — the report must be
    RETRIEVED by id. Long jobs then report ``status:"in_progress"`` while running
    (2026-07-01b: treating that as terminal was the poll fix's residual bug).
    Returns the last payload seen (the non-terminal one if the deadline expires,
    the endpoint 404s, or no api_key is available), never raises: the caller
    decides how to surface a still-running result.
    """
    req_id = initial.get("request_id")
    if not (req_id and api_key):
        return initial
    url = f"{TAVILY_RESEARCH_URL.rstrip('/')}/{req_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    t0 = time.time()
    last = initial
    while time.time() - t0 < deadline_seconds:
        time.sleep(max(1, interval_seconds))
        try:
            with httpx.Client(timeout=60) as client:
                r = client.get(url, headers=headers)
            if r.status_code == 404:
                print(
                    f"⚠ tavily.research: retrieve endpoint 404 for request_id={req_id} — "
                    "cannot poll this job (API contract change?); returning last payload",
                    file=sys.stderr,
                )
                return last
            r.raise_for_status()
            last = r.json()
        except Exception as e:  # noqa: BLE001 — poll errors are retried until deadline
            print(
                f"⚠ tavily.research poll error ({type(e).__name__}: {str(e)[:100]}) — retrying",
                file=sys.stderr,
            )
            continue
        status = last.get("status", "completed")
        if status not in _NON_TERMINAL_STATUSES:
            print(
                f"✓ tavily.research job {req_id} finished (status={status}) after "
                f"{time.time() - t0:.0f}s of polling",
                file=sys.stderr,
            )
            return last
    return last


def research(
    input_query: str,
    *,
    model: Literal["mini", "pro", "auto"] = DEFAULT_MODEL,
    output_schema: dict | None = None,
    citation_format: Literal["numbered", "mla", "apa", "chicago"] = DEFAULT_CITATION_FORMAT,
    stream: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT,
    use_cache: bool = True,
    task_id: str | None = None,
    poll_timeout_seconds: int = 900,
    poll_interval_seconds: int = 15,
) -> ResearchResponse:
    """Submit a deep research task via Tavily /research endpoint.

    Args:
        input_query: The research question (can be long, multi-faceted).
        model: "mini" for narrow / "pro" for comprehensive (v3.2 default) / "auto".
        output_schema: Optional JSON Schema defining the structured output you want.
        citation_format: How references are formatted in the response.
        stream: If True, request SSE stream (returns incrementally; not yet wrapped here).
        timeout_seconds: HTTP timeout of the initial synchronous window.
        use_cache: Check 1-week cache first.
        poll_timeout_seconds: /research is ASYNC — when the job outlives the sync
            window the API replies ``200 {status:"pending", request_id}``. We then
            poll ``GET /research/{request_id}`` up to this deadline (2026-07-01 fix:
            previously there was NO poll loop at all — the pending payload was
            returned as the final "answer" and every long pro job was lost).
        poll_interval_seconds: seconds between polls.

    Returns:
        ResearchResponse with output + citations.

    Raises:
        RuntimeError on API errors.
    """
    if not input_query.strip():
        raise ValueError("input_query cannot be empty")

    # Cache key
    cache_key = _cache_key(input_query, model, output_schema)
    if use_cache:
        cached = _read_cache(cache_key)
        if cached:
            return ResearchResponse(
                request_id=cached.get("request_id", "cached"),
                status="completed",
                input=input_query,
                model=model,
                response_time_seconds=cached.get("response_time_seconds", 0),
                output=cached.get("output"),
                citations=cached.get("citations", []),
                cached=True,
                cost_credits_estimated=0,
                cost_usd_estimated=0.0,
            )

    # Pre-flight cost check
    estimated_credits = ESTIMATED_CREDITS_PER_CALL.get(model, 30)
    estimate = cost_ledger.estimate(
        "tavily",
        tavily_calls_advanced=estimated_credits // 2,  # rough mapping for budget
    )
    decision = cost_ledger.check(estimate, scope="per_article")
    if decision == "blocked":
        raise RuntimeError(
            f"Tavily research would exceed budget: ~{estimated_credits} credits "
            f"(~${estimated_credits * 0.008:.3f}). Lower model to 'mini' or split task."
        )
    if decision == "needs_approval":
        print(f"[cost-guard] ⚠️ Research call estimated ~{estimated_credits} credits",
              file=sys.stderr)

    # Validate API URL (SSRF safety)
    try:
        validate_url(TAVILY_RESEARCH_URL, allow_http=False)
    except Exception as e:
        raise RuntimeError(f"Tavily URL SSRF check failed: {e}") from e

    payload: dict = {
        "input": input_query,
        "model": model,
        "citation_format": citation_format,
    }
    if output_schema:
        payload["output_schema"] = output_schema
    if stream:
        payload["stream"] = True

    from scripts._core.tavily_retry import with_retry

    # The poll below must reuse the SAME account's key the job was submitted with
    # (a research job is account-scoped); with_retry rotates keys, so capture it.
    _used_key: dict[str, str] = {}

    def _do_research(api_key: str) -> dict:
        _used_key["k"] = api_key
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=timeout_seconds) as client:
            r = client.post(TAVILY_RESEARCH_URL, headers=headers, json=payload)
            r.raise_for_status()
            return r.json()

    t0 = time.time()
    # Deep research is the most expensive + failure-prone call (long-running, rate-limited).
    # Rotate across the WHOLE key pool on transient errors: a 432 "plan/quota limit" on the
    # /research endpoint is rejected with NO credit charge, so probing every key to find the
    # one that still has research credits is free — only a successful call costs ~30 credits.
    # (2026-06-04 fix: previously capped at max_attempts=3, so a 10-key pool gave up before
    # reaching its working key and pro research silently fell back. Omitting max_attempts now
    # lets with_retry derive it from credential_hub.tavily_pool_size().) Bad schema fails fast.
    try:
        data = with_retry(
            _do_research,
            get_key=credential_hub.get_tavily_key,
            base_delay=3.0,
            label="tavily.research",
        )
    except Exception as e:
        raise RuntimeError(f"Tavily research failed: {e}") from e

    # /research is ASYNC: a job that outlives the sync window answers
    # 200 {status:"pending"|"in_progress", request_id}. Poll GET
    # /research/{request_id} until the report is ready (2026-07-01 — previously no
    # poll existed; 2026-07-01b — the poll treated "in_progress" as terminal.
    # Both lost every long pro job to MCP fallback).
    _status = data.get("status", "completed")
    _req_id = data.get("request_id")
    if _status in _NON_TERMINAL_STATUSES and _req_id and poll_timeout_seconds > 0:
        data = _poll_research_job(
            data, _used_key.get("k"),
            deadline_seconds=poll_timeout_seconds,
            interval_seconds=poll_interval_seconds,
        )
        _status = data.get("status", "completed")

    elapsed = time.time() - t0

    if _status in _NON_TERMINAL_STATUSES:
        print(
            f"⚠ tavily.research still status={_status} (request_id={data.get('request_id')}) "
            f"after the sync window ({timeout_seconds}s) + poll deadline "
            f"({poll_timeout_seconds}s). Output may be partial — do NOT cache as final.",
            file=sys.stderr,
        )

    # Log cost (estimated; Tavily may include actual usage in response)
    cost_ledger.log(
        estimate, endpoint="tavily.research",
        task_id=task_id,
        extra={
            "model": model,
            "input_len": len(input_query),
            "elapsed_s": elapsed,
            "request_id": data.get("request_id"),
        },
    )

    response = ResearchResponse(
        request_id=data.get("request_id", ""),
        status=data.get("status", "completed"),
        input=input_query,
        model=model,
        response_time_seconds=round(elapsed, 2),
        output=data.get("output") or data.get("result") or data,
        citations=data.get("citations", []),
        cached=False,
        cost_credits_estimated=estimated_credits,
        cost_usd_estimated=estimated_credits * 0.008,
    )

    # Cache
    if use_cache and response.status == "completed":
        _write_cache(cache_key, {
            "request_id": response.request_id,
            "input": input_query,
            "model": model,
            "response_time_seconds": response.response_time_seconds,
            "output": response.output,
            "citations": response.citations,
        })

    return response


def main() -> int:
    ap = argparse.ArgumentParser(description="Tavily Deep Research API (v3.2 default model=pro)")
    ap.add_argument("input", help="Research question / task")
    ap.add_argument("--model", choices=["mini", "pro", "auto"], default=DEFAULT_MODEL)
    ap.add_argument("--citation-format", choices=["numbered", "mla", "apa", "chicago"],
                    default=DEFAULT_CITATION_FORMAT)
    ap.add_argument("--output-schema", type=Path,
                    help="Path to JSON Schema file defining structured output")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--poll-timeout", type=int, default=900,
                    help="Max seconds to poll GET /research/{request_id} when the job "
                         "returns status=pending (async). 0 disables polling.")
    ap.add_argument("--poll-interval", type=int, default=15)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--task-id")
    args = ap.parse_args()

    schema = None
    if args.output_schema and args.output_schema.exists():
        schema = json.loads(args.output_schema.read_text(encoding="utf-8"))

    try:
        r = research(
            args.input,
            model=args.model,
            output_schema=schema,
            citation_format=args.citation_format,
            timeout_seconds=args.timeout,
            use_cache=not args.no_cache,
            task_id=args.task_id,
            poll_timeout_seconds=args.poll_timeout,
            poll_interval_seconds=args.poll_interval,
        )
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Rule 8 quarantine annotation (2026-07-17): the Deep Research endpoint
    # selects sources SERVER-SIDE and honors no caller-side exclude list, so a
    # blocklisted competitor domain can appear in output/citations even though
    # every tavily_search call passed --exclude (leaked on 2 of 3 project-hotel
    # runs). We cannot prevent it; we CAN stamp the artifact so downstream
    # consumers treat those sources as citation-unsafe instead of each
    # researcher rediscovering the leak by hand.
    rule8: dict | None = None
    try:
        from scripts._core.competitor_domains import load_policy, load_policy_for_task
        policy = (load_policy_for_task(args.task_id) if args.task_id
                  else load_policy())
        if policy.enabled:
            haystack = json.dumps(
                {"output": r.output, "citations": r.citations}, ensure_ascii=False)
            hits = sorted({d for d, _ in policy.find_blocked_in_html(haystack)})
            rule8 = {
                "policy_enabled": True,
                "blocked_domains_found": hits,
                "citation_safe": not hits,
                "note": ("Deep Research selects sources server-side and ignores "
                         "caller-side excludes. Any domain listed here must NOT be "
                         "cited/linked; re-verify its facts against a "
                         "non-competitor primary source (Rule 8)."),
            }
    except Exception as _r8_e:  # annotation must never break research output
        rule8 = {"policy_enabled": None, "error": str(_r8_e)}

    if args.json:
        payload = {
            "request_id": r.request_id,
            "status": r.status,
            "model": r.model,
            "response_time_seconds": r.response_time_seconds,
            "output": r.output,
            "citations": r.citations,
            "cached": r.cached,
            "cost_credits_estimated": r.cost_credits_estimated,
            "cost_usd_estimated": r.cost_usd_estimated,
        }
        if rule8 is not None:
            payload["_rule8"] = rule8
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        cache_note = " (cached)" if r.cached else ""
        print(f"Request ID: {r.request_id}")
        print(f"Status:     {r.status}{cache_note}")
        print(f"Model:      {r.model}")
        print(f"Duration:   {r.response_time_seconds}s")
        print(f"Cost est:   ~{r.cost_credits_estimated} credits (~${r.cost_usd_estimated:.3f})")
        print()
        print(f"Output:")
        if isinstance(r.output, dict):
            print(json.dumps(r.output, indent=2, ensure_ascii=False)[:2000] + "...")
        else:
            print(str(r.output)[:2000])
        if r.citations:
            print(f"\nCitations ({len(r.citations)}):")
            for i, c in enumerate(r.citations[:10], 1):
                print(f"  [{i}] {c}")

    if rule8 and rule8.get("blocked_domains_found"):
        print(
            f"\n⚠ RULE 8: deep-research output contains blocklisted competitor "
            f"domain(s): {', '.join(rule8['blocked_domains_found'])}. "
            f"Citation-UNSAFE — re-source these facts before citing.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
