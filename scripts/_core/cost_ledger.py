"""
scripts/_core/cost_ledger.py — Cost estimation, budget enforcement, logging.

Every LLM and external-API call in this plugin MUST flow through this module.

Lifecycle:
    1. estimate(model, in_tokens, out_tokens, **extras)  →  Decimal USD cost
    2. check(estimated_cost)  →  "approved" | "needs_approval" | "blocked"
    3. log(actual_cost, model, endpoint, task_id?)  →  written to JSONL ledger
    4. summary(period)  →  aggregate report

Ledger file:  ~/.xuanran-seo/cost-ledger.jsonl
Config file:  ~/.xuanran-seo/config.yaml (cost_limits section)

Pricing tables (verified 2026-05 via Web search):
    - Anthropic Claude Opus 4.7: $5/M input, $25/M output (cache 90% off, batch 50% off)
    - Anthropic Claude Sonnet 4.6: $3/M input, $15/M output (estimated)
    - Anthropic Claude Haiku 4.5: $1/M input, $5/M output (estimated)
    - OpenAI gpt-image-2: per-image cost by quality × size; Batch API 50% off.
      NOTE: relay providers (openclawroot, see image_provider.py) are token-billed,
      not per-image. Image cost is intentionally keyed to this official table
      regardless of the active provider — a conservative over-estimate so the cost
      guard never under-counts. It is NOT token-accurate for the relay.
    - OpenAI gpt-image-1-mini: cheaper
    - Google Gemini 3.1 Pro: $1.25/M input (<200k ctx), $10/M output
    - Google Gemini 2.5 Flash: $0.30/M input, $2.50/M output
    - Tavily Search: 1 credit basic, 2 credits advanced. 1 credit ≈ $0.008 PAYG

Usage (Python):
    from scripts._core import cost_ledger as cl
    from decimal import Decimal

    est = cl.estimate("claude-opus-4-7", in_tokens=5000, out_tokens=2000)
    if cl.check(est) == "blocked":
        raise BudgetExceededError()
    # ... call API ...
    cl.log(actual_cost=est, model="claude-opus-4-7", endpoint="messages", task_id="abc")

Usage (CLI):
    python -m scripts._core.cost_ledger --estimate --model claude-opus-4-7 --in 5000 --out 2000
    python -m scripts._core.cost_ledger --summary --period day --json
    python -m scripts._core.cost_ledger --reset-today    # admin only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Final, Literal

from scripts._core import file_lock


getcontext().prec = 10  # cost precision

XS_HOME: Final[Path] = Path.home() / ".xuanran-seo"
LEDGER_FILE: Final[Path] = XS_HOME / "cost-ledger.jsonl"
CONFIG_FILE: Final[Path] = XS_HOME / "config.yaml"


# ─── Pricing tables (verified 2026-05) ──────────────────────────────

# Anthropic per-million-token (input, output)
_ANTHROPIC: Final[dict[str, tuple[Decimal, Decimal]]] = {
    "claude-opus-4-7":    (Decimal("5.00"),  Decimal("25.00")),
    "claude-opus-4-6":    (Decimal("15.00"), Decimal("75.00")),    # legacy
    "claude-sonnet-4-6":  (Decimal("3.00"),  Decimal("15.00")),
    "claude-sonnet-4-5":  (Decimal("3.00"),  Decimal("15.00")),    # legacy
    "claude-haiku-4-5":   (Decimal("1.00"),  Decimal("5.00")),
}

# Google Gemini per-million-token (input, output)
# Note: 2.5 Pro has tiered pricing above 200k context; we use base tier
_GEMINI: Final[dict[str, tuple[Decimal, Decimal]]] = {
    "gemini-3.1-pro":         (Decimal("1.25"),  Decimal("10.00")),
    "gemini-2.5-pro":         (Decimal("1.25"),  Decimal("10.00")),
    "gemini-2.5-flash":       (Decimal("0.30"),  Decimal("2.50")),
    "gemini-2.5-flash-lite":  (Decimal("0.10"),  Decimal("0.40")),
}

# OpenAI image generation: per-image USD by (model, quality, size)
# Size is "WxH" string
_OPENAI_IMAGE: Final[dict[tuple[str, str, str], Decimal]] = {
    # gpt-image-2 (flagship, 2025 late)
    ("gpt-image-2", "low",    "1024x1024"): Decimal("0.006"),
    ("gpt-image-2", "medium", "1024x1024"): Decimal("0.053"),
    ("gpt-image-2", "high",   "1024x1024"): Decimal("0.211"),
    ("gpt-image-2", "low",    "1024x1536"): Decimal("0.005"),
    ("gpt-image-2", "medium", "1024x1536"): Decimal("0.041"),
    ("gpt-image-2", "high",   "1024x1536"): Decimal("0.165"),
    ("gpt-image-2", "low",    "1536x1024"): Decimal("0.005"),
    ("gpt-image-2", "medium", "1536x1024"): Decimal("0.041"),
    ("gpt-image-2", "high",   "1536x1024"): Decimal("0.165"),
    # gpt-image-1-mini (budget)
    ("gpt-image-1-mini", "low",    "1024x1024"): Decimal("0.005"),
    ("gpt-image-1-mini", "medium", "1024x1024"): Decimal("0.011"),
    ("gpt-image-1-mini", "high",   "1024x1024"): Decimal("0.040"),
}

# Tavily: cost per request (basic vs advanced search)
_TAVILY: Final[dict[str, Decimal]] = {
    "search.basic":     Decimal("0.008"),
    "search.advanced":  Decimal("0.016"),
    "extract.basic":    Decimal("0.0016"),  # 1 credit / 5 URLs
    "extract.advanced": Decimal("0.0032"),
}

# SerpApi: real cost is $0 on the pooled free tier (250 searches/key/month);
# the smallest paid plan is ~$0.015/search. Priced at $0 so the cost guard never
# blocks a free pooled call — per-key monthly quota is managed by key rotation
# (serpapi_pool), not by dollars. `inputs.searches` still records usage.
_SERPAPI: Final[Decimal] = Decimal("0.0")

# Discounts
_BATCH_DISCOUNT: Final[Decimal] = Decimal("0.5")        # 50% off (Anthropic & OpenAI)
_CACHE_DISCOUNT: Final[Decimal] = Decimal("0.1")        # 90% off cached input (Anthropic)


# ─── Exceptions ───────────────────────────────────────────────────

class CostLedgerError(Exception):
    """Base."""


class UnknownModelError(CostLedgerError):
    """Model not in pricing tables."""


class BudgetExceededError(CostLedgerError):
    """Cost exceeds configured daily budget."""


# ─── Data types ────────────────────────────────────────────────────

@dataclass(frozen=True)
class CostEstimate:
    model: str
    endpoint: str
    estimated_usd: Decimal
    inputs: dict  # the params used (in_tokens, out_tokens, size, etc.)


CheckResult = Literal["approved", "needs_approval", "blocked"]


# ─── Core API ──────────────────────────────────────────────────────

def estimate(
    model: str,
    *,
    in_tokens: int = 0,
    out_tokens: int = 0,
    cached_in_tokens: int = 0,
    batch_mode: bool = False,
    image_quality: str | None = None,
    image_size: str | None = None,
    image_count: int = 1,
    tavily_calls_basic: int = 0,
    tavily_calls_advanced: int = 0,
    tavily_extract_urls: int = 0,
    tavily_extract_advanced: bool = False,
    serpapi_searches: int = 0,
) -> CostEstimate:
    """Estimate USD cost for a planned API call.

    For LLMs (Anthropic / Gemini), use in_tokens / out_tokens / cached_in_tokens.
    For OpenAI images, use image_quality / image_size / image_count.
    For Tavily, use tavily_calls_basic / advanced / extract_urls.

    Returns CostEstimate with .estimated_usd.

    Raises UnknownModelError if model is unrecognized.
    """
    # ── Anthropic ──
    if model in _ANTHROPIC:
        in_rate, out_rate = _ANTHROPIC[model]
        in_cost = (Decimal(in_tokens) / Decimal(1_000_000)) * in_rate
        out_cost = (Decimal(out_tokens) / Decimal(1_000_000)) * out_rate
        cache_cost = (Decimal(cached_in_tokens) / Decimal(1_000_000)) * in_rate * _CACHE_DISCOUNT
        total = in_cost + out_cost + cache_cost
        if batch_mode:
            total *= _BATCH_DISCOUNT
        return CostEstimate(
            model=model, endpoint="messages",
            estimated_usd=total.quantize(Decimal("0.0001")),
            inputs={
                "in_tokens": in_tokens, "out_tokens": out_tokens,
                "cached_in_tokens": cached_in_tokens, "batch_mode": batch_mode,
            },
        )

    # ── Gemini ──
    if model in _GEMINI:
        in_rate, out_rate = _GEMINI[model]
        in_cost = (Decimal(in_tokens) / Decimal(1_000_000)) * in_rate
        out_cost = (Decimal(out_tokens) / Decimal(1_000_000)) * out_rate
        total = in_cost + out_cost
        if batch_mode:
            total *= _BATCH_DISCOUNT
        return CostEstimate(
            model=model, endpoint="generateContent",
            estimated_usd=total.quantize(Decimal("0.0001")),
            inputs={
                "in_tokens": in_tokens, "out_tokens": out_tokens,
                "batch_mode": batch_mode,
            },
        )

    # ── OpenAI images ──
    if model.startswith("gpt-image"):
        if not image_quality or not image_size:
            raise CostLedgerError("image_quality and image_size required for image models")
        # Normalize legacy quality names (DALL-E 3 "hd" → gpt-image "high")
        _quality_aliases = {"hd": "high", "standard": "medium"}
        image_quality = _quality_aliases.get(image_quality, image_quality)
        # Normalize non-standard sizes to nearest supported size
        _size_aliases = {"1792x1024": "1536x1024", "1024x1792": "1024x1536"}
        image_size = _size_aliases.get(image_size, image_size)
        key = (model, image_quality, image_size)
        if key not in _OPENAI_IMAGE:
            # Pixel-scaling fallback (2026-06-10): gpt-image-2 accepts arbitrary
            # WIDTHxHEIGHT (2K default tiers, up to 3840x2160). Token cost scales
            # ~linearly with pixel count, so scale the 1024x1024 baseline for the
            # same quality instead of hard-failing. The old UnknownModelError here
            # failed slots AFTER generation (double-billing across provider
            # fallbacks) — an estimator must never be the thing that breaks a run.
            base_key = (model, image_quality, "1024x1024")
            try:
                w, h = (int(p) for p in image_size.lower().split("x"))
                base = _OPENAI_IMAGE.get(base_key)
                if base is None or w <= 0 or h <= 0:
                    raise ValueError
                per_image = (base * Decimal(w * h) / Decimal(1024 * 1024)).quantize(
                    Decimal("0.0001"))
            except (ValueError, ArithmeticError):
                raise UnknownModelError(
                    f"No pricing for {key!r} and size not scalable. "
                    f"Known: {list(_OPENAI_IMAGE)[:5]}..."
                ) from None
        else:
            per_image = _OPENAI_IMAGE[key]
        total = per_image * Decimal(image_count)
        if batch_mode:
            total *= _BATCH_DISCOUNT
        return CostEstimate(
            model=model, endpoint="images/generations",
            estimated_usd=total.quantize(Decimal("0.0001")),
            inputs={
                "image_count": image_count, "image_quality": image_quality,
                "image_size": image_size, "batch_mode": batch_mode,
            },
        )

    # ── Tavily ──
    if model == "tavily":
        cost = (
            Decimal(tavily_calls_basic) * _TAVILY["search.basic"]
            + Decimal(tavily_calls_advanced) * _TAVILY["search.advanced"]
        )
        if tavily_extract_urls > 0:
            rate = _TAVILY["extract.advanced"] if tavily_extract_advanced else _TAVILY["extract.basic"]
            cost += Decimal(tavily_extract_urls) * rate
        return CostEstimate(
            model="tavily", endpoint="search/extract",
            estimated_usd=cost.quantize(Decimal("0.0001")),
            inputs={
                "search_basic": tavily_calls_basic, "search_advanced": tavily_calls_advanced,
                "extract_urls": tavily_extract_urls, "extract_advanced": tavily_extract_advanced,
            },
        )

    # ── SerpApi ──
    if model == "serpapi":
        cost = Decimal(serpapi_searches) * _SERPAPI
        return CostEstimate(
            model="serpapi", endpoint="search",
            estimated_usd=cost.quantize(Decimal("0.0001")),
            inputs={"searches": serpapi_searches},
        )

    raise UnknownModelError(f"Unknown model: {model!r}")


def check(estimated_cost: Decimal | CostEstimate, *, scope: str = "per_article") -> CheckResult:
    """Decide whether to approve, require approval, or block the cost.

    Compares against `~/.xuanran-seo/config.yaml` cost_limits.

    Args:
        estimated_cost: Decimal USD or CostEstimate.
        scope: One of "per_init" / "per_article" / "per_image_batch" / "daily_total".

    Returns:
        "approved" — cost within limits, proceed
        "needs_approval" — cost > 0.5 × limit (warn but allow)
        "blocked" — cost > limit OR daily total would exceed
    """
    if isinstance(estimated_cost, CostEstimate):
        cost = estimated_cost.estimated_usd
    else:
        cost = Decimal(estimated_cost)

    limits = _load_limits()

    # Per-scope limit
    scope_key = f"{scope}_usd"
    scope_limit = limits.get(scope_key, Decimal("1000"))  # huge default = unlimited
    if cost > scope_limit:
        return "blocked"
    if cost > scope_limit * Decimal("0.5"):
        return "needs_approval"

    # Daily total
    daily_used = summary("day")["total_usd"]
    daily_limit = limits.get("daily_total_usd", Decimal("100"))
    if daily_used + cost > daily_limit:
        return "blocked"
    if daily_used + cost > daily_limit * Decimal("0.8"):
        return "needs_approval"

    return "approved"


def log(
    actual_cost: Decimal | CostEstimate,
    *,
    model: str | None = None,
    endpoint: str | None = None,
    task_id: str | None = None,
    project_slug: str | None = None,
    extra: dict | None = None,
) -> None:
    """Append an entry to the ledger JSONL file."""
    if isinstance(actual_cost, CostEstimate):
        cost = actual_cost.estimated_usd
        model = model or actual_cost.model
        endpoint = endpoint or actual_cost.endpoint
    else:
        cost = Decimal(actual_cost)

    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model or "unknown",
        "endpoint": endpoint or "unknown",
        "cost_usd": str(cost),
        "task_id": task_id,
        "project_slug": project_slug,
        "extra": extra or {},
    }

    # Cross-process lock: 3 parallel sessions append concurrently. Without this
    # the JSONL interleaves/corrupts and the shared daily budget mis-counts.
    with file_lock.locked(LEDGER_FILE):
        with LEDGER_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def summary(period: Literal["day", "week", "month"] = "day") -> dict:
    """Aggregate ledger entries for the given period (ending now).

    Returns:
        {
          "period": "day",
          "total_usd": Decimal,
          "by_model": {model: usd, ...},
          "by_endpoint": {endpoint: usd, ...},
          "entry_count": int,
        }
    """
    if not LEDGER_FILE.exists():
        return {
            "period": period, "total_usd": Decimal("0"),
            "by_model": {}, "by_endpoint": {}, "entry_count": 0,
        }

    now = datetime.now(timezone.utc)
    cutoff = now - {
        "day":   timedelta(days=1),
        "week":  timedelta(days=7),
        "month": timedelta(days=30),
    }[period]

    total = Decimal("0")
    by_model: dict[str, Decimal] = {}
    by_endpoint: dict[str, Decimal] = {}
    n = 0

    with LEDGER_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
                ts = datetime.fromisoformat(e["timestamp"])
                if ts < cutoff:
                    continue
                cost = Decimal(e["cost_usd"])
                total += cost
                by_model[e["model"]] = by_model.get(e["model"], Decimal("0")) + cost
                by_endpoint[e["endpoint"]] = by_endpoint.get(e["endpoint"], Decimal("0")) + cost
                n += 1
            except (json.JSONDecodeError, KeyError, ValueError):
                continue

    return {
        "period": period,
        "total_usd": total,
        "by_model": by_model,
        "by_endpoint": by_endpoint,
        "entry_count": n,
    }


# ─── Helpers ──────────────────────────────────────────────────────

def _load_limits() -> dict[str, Decimal]:
    """Load cost_limits section from ~/.xuanran-seo/config.yaml."""
    defaults = {
        "daily_total_usd":    Decimal("50"),
        "per_init_usd":       Decimal("1.5"),
        "per_article_usd":    Decimal("3.0"),
        "per_image_batch_usd": Decimal("2.0"),
    }
    if not CONFIG_FILE.exists():
        return defaults
    try:
        import yaml
        data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
        cl = (data or {}).get("cost_limits", {}) if isinstance(data, dict) else {}
        return {k: Decimal(str(cl.get(k, defaults[k]))) for k in defaults}
    except Exception as e:
        # Audit 2026-05-22 P1 — log silent-fallback
        print(
            f"⚠ cost_limits load failed: {type(e).__name__}: {e} — "
            f"falling back to plugin defaults (daily=${defaults.get('daily_total_usd', 'n/a')})",
            file=sys.stderr,
        )
        return defaults


# ─── CLI ───────────────────────────────────────────────────────

def _to_jsonable(obj):
    """Convert Decimal → str for JSON serialization."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_jsonable(v) for v in obj]
    return obj


def main() -> int:
    ap = argparse.ArgumentParser(description="Cost ledger CLI")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--estimate", action="store_true")
    g.add_argument("--summary", action="store_true")
    g.add_argument("--reset-today", action="store_true",
                   help="Delete ledger entries from last 24h (admin)")
    ap.add_argument("--model")
    ap.add_argument("--in", dest="in_tokens", type=int, default=0)
    ap.add_argument("--out", dest="out_tokens", type=int, default=0)
    ap.add_argument("--cached", dest="cached_in_tokens", type=int, default=0)
    ap.add_argument("--batch", action="store_true")
    ap.add_argument("--quality", choices=["low", "medium", "high"])
    ap.add_argument("--size")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--period", choices=["day", "week", "month"], default="day")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.estimate:
        if not args.model:
            print("--model required for --estimate", file=sys.stderr)
            return 1
        try:
            est = estimate(
                args.model,
                in_tokens=args.in_tokens, out_tokens=args.out_tokens,
                cached_in_tokens=args.cached_in_tokens, batch_mode=args.batch,
                image_quality=args.quality, image_size=args.size,
                image_count=args.count,
            )
        except CostLedgerError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        out = {
            "model": est.model, "endpoint": est.endpoint,
            "estimated_usd": str(est.estimated_usd),
            "inputs": est.inputs,
            "check": check(est),
        }
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(f"Model:    {est.model}")
            print(f"Endpoint: {est.endpoint}")
            print(f"Cost:     ${est.estimated_usd}")
            print(f"Check:    {out['check']}")
        return 0

    if args.summary:
        s = summary(args.period)
        if args.json:
            print(json.dumps(_to_jsonable(s), indent=2))
        else:
            print(f"Period:  {s['period']}")
            print(f"Total:   ${s['total_usd']}")
            print(f"Entries: {s['entry_count']}")
            print("By model:")
            for m, c in sorted(s["by_model"].items(), key=lambda x: -x[1]):
                print(f"  ${c}  {m}")
        return 0

    if args.reset_today:
        if not LEDGER_FILE.exists():
            print("No ledger to reset.")
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        kept = []
        # Lock the whole read-modify-rewrite so a concurrent log() append from
        # another session is not silently dropped by the rewrite.
        with file_lock.locked(LEDGER_FILE):
            with LEDGER_FILE.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                        if datetime.fromisoformat(e["timestamp"]) < cutoff:
                            kept.append(line)
                    except Exception:
                        kept.append(line)
            LEDGER_FILE.write_text("".join(kept), encoding="utf-8")
        print(f"Removed today's entries. Kept {len(kept)} older entries.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
