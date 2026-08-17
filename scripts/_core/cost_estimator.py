"""
scripts/_core/cost_estimator.py — Pre-flight cost estimation for /article.

Estimates total USD cost for a planned /article run BEFORE the pipeline starts,
so users can see "Estimated $2.40 — proceed?" instead of finding out after.

Cost breakdown (typical /article run):
  - Research (Tavily search/extract):         ~$0.05-0.15
  - Brief / planning (Claude in-out tokens):  ~$0.10-0.20
  - Section drafting (Claude parallel):       ~$0.60-1.50
  - Humanizer + fact-checker + editor:        ~$0.30-0.60
  - Image generation (provider-dependent, 4 imgs): ~$0.66 (realtime high; relay primary
        is token-billed + cheaper but ledger over-estimates with the official table)
  - Schema + meta builders:                    ~$0.02
  - Lint/validate (no LLM):                    $0
  - Overhead buffer:                            +10%

Formats with different word_count_target produce different cost profiles:
  pillar (6000w):     ~$3.40
  case-study (5500w): ~$3.10
  comparison (4500w): ~$2.50
  how-to (4500w):     ~$2.40
  listicle (6000w):   ~$2.90
  definition (3500w): ~$2.00
  news-analysis (1500w): ~$1.40

CLI:
    python -m scripts._core.cost_estimator --format listicle --words 6000
    python -m scripts._core.cost_estimator --brief workspace/abc/brief.json --json
    python -m scripts._core.cost_estimator --format pillar --images 4 --batch
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path

from scripts._core import cost_ledger, format_registry, image_policy


# ── Per-format cost model parameters (calibrated against /article runs) ──

FORMAT_PARAMS: dict[str, dict] = {
    "listicle":       {"words": 6000, "research_calls_advanced": 8, "research_extracts": 12, "image_count": image_policy.DEFAULT_IMAGE_COUNT},
    "how-to-guide":   {"words": 4500, "research_calls_advanced": 5, "research_extracts": 8,  "image_count": image_policy.DEFAULT_IMAGE_COUNT},
    "pillar-page":    {"words": 6500, "research_calls_advanced": 10, "research_extracts": 15, "image_count": image_policy.DEFAULT_IMAGE_COUNT},
    "comparison":     {"words": 4500, "research_calls_advanced": 6, "research_extracts": 10, "image_count": image_policy.DEFAULT_IMAGE_COUNT},
    "case-study":     {"words": 5500, "research_calls_advanced": 4, "research_extracts": 6,  "image_count": image_policy.DEFAULT_IMAGE_COUNT},
    "definition":     {"words": 3500, "research_calls_advanced": 5, "research_extracts": 7,  "image_count": image_policy.DEFAULT_IMAGE_COUNT},
    # ⚠ the 2/3-image rows below are ESTIMATES for short formats — generation itself
    # follows brief.image_count (default image_policy.DEFAULT_IMAGE_COUNT) regardless
    # of format, so a short-format article that wants fewer images must SET
    # image_count in its brief; otherwise the real cost tracks the default row.
    "news-analysis":  {"words": 1500, "research_calls_advanced": 4, "research_extracts": 5,  "image_count": 2},
    "product-review": {"words": 4500, "research_calls_advanced": 4, "research_extracts": 6,  "image_count": image_policy.DEFAULT_IMAGE_COUNT},
    "shortlist-validation": {"words": 2200, "research_calls_advanced": 6, "research_extracts": 9, "image_count": 3},
    "faq-knowledge":  {"words": 3000, "research_calls_advanced": 4, "research_extracts": 6,  "image_count": 2},
    # Provisional row (2026-08-17): template targets 5500-6500w (templates/
    # buyers-guide.md), research load listicle-class. The 2026-08-17 project-hotel
    # batch ran ~$7.33/article ACTUAL vs $1.66 default-profile estimate — 40% of
    # the gap was the missing row (4500w baseline), the rest repair-round churn
    # (cured v3.42.16) + the then-unmodeled deep-research call (modeled below).
    # Recalibrate from ledger rows once task-id attribution (v3.42.18) has data.
    "buyers-guide":   {"words": 6000, "research_calls_advanced": 8, "research_extracts": 12, "image_count": image_policy.DEFAULT_IMAGE_COUNT},
    # default fallback
    "default":        {"words": 4500, "research_calls_advanced": 6, "research_extracts": 10, "image_count": image_policy.DEFAULT_IMAGE_COUNT},
}

# FORMAT_PARAMS is a COST-MODEL table — it holds calibration rows only for the formats
# whose real /article runs have been measured, and `estimate_article` falls back to
# "default" for the rest. It is NOT the list of legal formats: that is the schema enum,
# shared via format_registry. Using FORMAT_PARAMS.keys() as the CLI's `choices=` (the
# pre-v3.42.11 bug) promoted a deliberate soft fallback into a hard `invalid choice`
# rejection for 17 of 27 real formats, breaking the per-article cost guard that
# subskills/cross-cutting/batch-article documents. See
# tests/test_cost_estimator_format_enum_seam.py.
VALID_FORMATS: set[str] = format_registry.load_valid_formats(source="cost_estimator") | {"default"}

# Token consumption model (input/output per 100 words drafted)
# Calibrated: drafting 100w needs ~500 prompt tokens (refs+context+brief) + ~140 output tokens
TOKENS_PER_100W_DRAFT_INPUT  = 500
TOKENS_PER_100W_DRAFT_OUTPUT = 140

# One mandatory Tavily Deep Research pro call per article (~30 credits ≈ $0.24
# PAYG; scripts/fetch/tavily_research.py). Flat per-article, not a row field.
DEEP_RESEARCH_PRO_USD = Decimal("0.24")

# Per-pipeline-stage fixed token consumption (independent of word count)
PIPELINE_STAGES: list[tuple[str, int, int]] = [
    # (stage_label, in_tokens, out_tokens)
    ("brief-intake",       3000,  300),
    ("topic-angle",        8000,  600),
    ("format-selector",    4000,  300),
    ("outline-architect",  12000, 1500),
    ("research-gap-fill",  5000,  400),
    ("humanizer",          15000, 3000),
    ("fact-checker",       18000, 2000),
    ("linker",             8000,  800),
    # editor-in-chief row removed 2026-08-17: agent PARKED v3.42.12 (tombstoned,
    # never dispatched) — a cost row for a stage that never runs inflates every
    # estimate by a phantom ~$0.09.
    ("reviewer",           18000, 1200),
    ("geo-optimizer",      6000,  500),
    ("meta-builder",       4000,  400),
    ("schema-builder",     3000,  500),
]


@dataclass
class CostBreakdown:
    research_tavily_usd: Decimal      = Decimal("0")
    drafting_llm_usd:    Decimal      = Decimal("0")
    pipeline_llm_usd:    Decimal      = Decimal("0")
    image_generation_usd: Decimal     = Decimal("0")
    overhead_buffer_usd: Decimal      = Decimal("0")
    total_usd:           Decimal      = Decimal("0")
    confidence_band: tuple[Decimal, Decimal] = (Decimal("0"), Decimal("0"))
    breakdown_lines:     list[str]    = field(default_factory=list)
    assumptions:         list[str]    = field(default_factory=list)


def estimate_article(
    *,
    fmt: str = "listicle",
    words: int | None = None,
    image_count: int | None = None,
    image_quality: str = "high",
    batch_images: bool = True,
    model_drafter: str = "claude-opus-4-7",
    model_pipeline: str = "claude-opus-4-7",
    cache_hit_pct: float = 0.30,   # ~30% of prompt tokens cached on average
) -> CostBreakdown:
    """Compute estimated total cost for a planned /article run."""
    params = FORMAT_PARAMS.get(fmt)
    if params is None:
        params = FORMAT_PARAMS["default"]
        # Loud, not silent: a default-derived number must never read as
        # format-specific calibration (Rule 14 — a derived value must be
        # distinguishable from an unknown one).
        print(
            f"[cost_estimator] NOTE: '{fmt}' has no calibrated cost row; "
            f"estimating with the uncalibrated default profile "
            f"({FORMAT_PARAMS['default']['words']}w baseline).",
            file=sys.stderr,
        )
    w = words or params["words"]
    n_imgs = image_count if image_count is not None else params["image_count"]

    out = CostBreakdown()
    out.assumptions = [
        f"Format: {fmt} (target {w} words)",
        f"Images: {n_imgs} × {image_quality}-quality 1024² ({'batch' if batch_images else 'sync'})",
        f"Drafter / pipeline model: {model_drafter} / {model_pipeline}",
        f"Cache hit rate assumed: {int(cache_hit_pct * 100)}%",
    ]

    # 1. Research (Tavily)
    tavily_est = cost_ledger.estimate(
        "tavily",
        tavily_calls_advanced=params["research_calls_advanced"],
        tavily_extract_urls=params["research_extracts"],
        tavily_extract_advanced=True,
    )
    # Mandatory Stage-0 Deep Research pro call (~30 credits ≈ $0.24 at PAYG,
    # scripts/fetch/tavily_research.py) — appeared in NO row until 2026-08-17;
    # every format runs exactly one, so it is a flat term, not a row field.
    out.research_tavily_usd = tavily_est.estimated_usd + DEEP_RESEARCH_PRO_USD
    out.breakdown_lines.append(
        f"  Research (Tavily ×{params['research_calls_advanced']} adv search + "
        f"{params['research_extracts']} extracts + 1 deep-research pro): "
        f"${out.research_tavily_usd}"
    )

    # 2. Drafting (parallel section dispatch — same total tokens, just parallelized)
    in_tokens = (w * TOKENS_PER_100W_DRAFT_INPUT) // 100
    out_tokens = (w * TOKENS_PER_100W_DRAFT_OUTPUT) // 100
    cached_in = int(in_tokens * cache_hit_pct)
    fresh_in = in_tokens - cached_in
    draft_est = cost_ledger.estimate(
        model_drafter,
        in_tokens=fresh_in,
        out_tokens=out_tokens,
        cached_in_tokens=cached_in,
    )
    out.drafting_llm_usd = draft_est.estimated_usd
    out.breakdown_lines.append(
        f"  Drafting ({w}w via {model_drafter}, {fresh_in:,} in + {out_tokens:,} out + "
        f"{cached_in:,} cached): ${out.drafting_llm_usd}"
    )

    # 3. Pipeline stages (planning + humanizer + fact-check + editor + reviewer + etc.)
    pipeline_total = Decimal("0")
    pipeline_in_total = 0
    pipeline_out_total = 0
    for stage, t_in, t_out in PIPELINE_STAGES:
        # Apply ~50% cache hit on planning stages (high reuse)
        cached = int(t_in * 0.5)
        fresh = t_in - cached
        est = cost_ledger.estimate(
            model_pipeline,
            in_tokens=fresh, out_tokens=t_out, cached_in_tokens=cached,
        )
        pipeline_total += est.estimated_usd
        pipeline_in_total += t_in
        pipeline_out_total += t_out
    out.pipeline_llm_usd = pipeline_total.quantize(Decimal("0.0001"))
    out.breakdown_lines.append(
        f"  Pipeline stages (13 stages, {pipeline_in_total:,} in + "
        f"{pipeline_out_total:,} out via {model_pipeline}): ${out.pipeline_llm_usd}"
    )

    # 4. Image generation
    #    Cost is deliberately keyed to the official "gpt-image-2" per-image table
    #    regardless of the configured primary provider (the openclawroot relay is
    #    token-billed + cheaper; we over-estimate on purpose so the cost guard
    #    stays conservative). See scripts/_core/image_provider.py.
    if n_imgs > 0:
        img_est = cost_ledger.estimate(
            "gpt-image-2",
            image_quality=image_quality,
            image_size="1024x1024",
            image_count=n_imgs,
            batch_mode=batch_images,
        )
        out.image_generation_usd = img_est.estimated_usd
        out.breakdown_lines.append(
            f"  Images ({n_imgs} × {image_quality} 1024², provider chain"
            f"{', batch' if batch_images else ', realtime'}): ${out.image_generation_usd}"
        )

    # 5. Overhead (retries, repair-orchestrator passes, etc.)
    subtotal = (
        out.research_tavily_usd + out.drafting_llm_usd
        + out.pipeline_llm_usd + out.image_generation_usd
    )
    out.overhead_buffer_usd = (subtotal * Decimal("0.10")).quantize(Decimal("0.0001"))
    out.breakdown_lines.append(f"  Overhead buffer (10%): ${out.overhead_buffer_usd}")

    out.total_usd = (subtotal + out.overhead_buffer_usd).quantize(Decimal("0.01"))

    # Confidence band (±25% spread for the 80% case)
    lower = (out.total_usd * Decimal("0.75")).quantize(Decimal("0.01"))
    upper = (out.total_usd * Decimal("1.30")).quantize(Decimal("0.01"))
    out.confidence_band = (lower, upper)

    return out


def estimate_from_brief(brief_path: Path) -> CostBreakdown:
    """Load brief.json and extract relevant inputs."""
    if not brief_path.exists():
        raise FileNotFoundError(brief_path)
    data = json.loads(brief_path.read_text(encoding="utf-8"))
    return estimate_article(
        fmt=data.get("format", "listicle"),
        words=data.get("word_count_target") or data.get("words"),
        image_count=data.get("image_count", image_policy.DEFAULT_IMAGE_COUNT),
        image_quality=data.get("image_quality", "high"),
        batch_images=data.get("batch_images", True),
    )


def _to_jsonable(b: CostBreakdown) -> dict:
    d = asdict(b)
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = str(v)
        elif isinstance(v, tuple):
            d[k] = [str(x) for x in v]
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-flight cost estimator for /article")
    ap.add_argument("--format", default="listicle",
                    choices=sorted(VALID_FORMATS))
    ap.add_argument("--words", type=int)
    # default=None → estimate_article falls back to the FORMAT row (which
    # imports image_policy.DEFAULT_IMAGE_COUNT). A literal argparse default
    # here silently overrode every pinned row (found 2026-08-17, Rule 10).
    ap.add_argument("--images", type=int, default=None)
    ap.add_argument("--image-quality", default="high",
                    choices=["low", "medium", "high"])
    ap.add_argument("--batch", action="store_true", help="Use Batch API for images (50% off)")
    ap.add_argument("--no-batch", dest="batch", action="store_false")
    ap.set_defaults(batch=True)
    ap.add_argument("--drafter-model", default="claude-opus-4-7")
    ap.add_argument("--pipeline-model", default="claude-opus-4-7")
    ap.add_argument("--brief", type=Path, help="Load inputs from brief.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        if args.brief:
            br = estimate_from_brief(args.brief)
        else:
            br = estimate_article(
                fmt=args.format,
                words=args.words,
                image_count=args.images,
                image_quality=args.image_quality,
                batch_images=args.batch,
                model_drafter=args.drafter_model,
                model_pipeline=args.pipeline_model,
            )
    except (FileNotFoundError, cost_ledger.CostLedgerError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(_to_jsonable(br), indent=2, ensure_ascii=False))
    else:
        print("━━━ /article cost estimate ━━━━━━━━━━━━━━━━━━━━━━━━━")
        for a in br.assumptions:
            print(f"  {a}")
        print()
        print("Breakdown:")
        for line in br.breakdown_lines:
            print(line)
        print()
        print(f"  TOTAL:         ${br.total_usd}")
        lo, hi = br.confidence_band
        print(f"  80% range:    ${lo} – ${hi}")
        print()
        check_result = cost_ledger.check(br.total_usd, scope="per_article")
        if check_result == "blocked":
            print("  ⛔ BLOCKED — exceeds your per-article budget. Adjust ~/.xuanran-seo/config.yaml")
        elif check_result == "needs_approval":
            print("  ⚠ Above 50% of budget — proceed with caution.")
        else:
            print(f"  ✓ Within budget.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
