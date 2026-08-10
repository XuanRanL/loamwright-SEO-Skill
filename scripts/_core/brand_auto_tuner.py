"""
scripts/_core/brand_auto_tuner.py — Winner-feature analysis → brand-guideline adjustments.

After enough articles have outcome tags (winner/mid/loser per outcome_tagger),
this script finds the features that statistically distinguish winners and
suggests brand-guideline.yaml updates.

Method:
  1. Load outcomes.json (needs ≥10 tagged articles, ideally ≥20)
  2. Group by outcome: winners, mid, losers
  3. For each numeric feature (word_count, first_person_pct, ai_slop_score, ...):
     - Compute mean per group
     - Compute Cohen's d (effect size) winner-vs-loser
     - If |d| > 0.5: medium effect; if > 0.8: large effect
  4. For categorical features (format, voice, purpose):
     - Compute winner-rate per category
     - Flag categories with significantly higher win-rate
  5. Generate brand-guideline.diff.yaml with concrete numeric targets
  6. Show summary + ask user to review (does not auto-apply)

Statistical caveat: with N<30 in any group, effects are noisy. We surface
"directional hint" rather than "statistical truth" and require human review.

CLI:
    python -m scripts._core.brand_auto_tuner --site my-site
    python -m scripts._core.brand_auto_tuner --site my-site --apply  # writes diff to apply
    python -m scripts._core.brand_auto_tuner --all-sites
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from scripts._core.file_bus import PLUGIN_ROOT


NUMERIC_FEATURES = [
    "word_count", "h2_count", "h3_count",
    "citation_count", "tier1_citation_count",
    "image_count", "table_count", "list_count",
    "info_gain_marker_count", "first_person_pct",
    "ai_slop_score", "core_eeat_score", "cite_score",
    "reviewer_score",
]

CATEGORICAL_FEATURES = ["format", "voice", "purpose"]

# Smaller-is-better features (lower ai_slop_score is better)
LOWER_IS_BETTER = {"ai_slop_score"}


@dataclass
class FeatureFinding:
    feature: str
    feature_type: str            # "numeric" | "categorical"
    winner_value: float | str
    loser_value: float | str
    effect_size: float            # Cohen's d for numeric; win-rate-delta for categorical
    significance: str            # "large" | "medium" | "small" | "negligible"
    suggestion: str
    sample_sizes: dict[str, int] = field(default_factory=dict)


@dataclass
class TunerReport:
    site_slug: str
    evaluated_at: str
    total_articles: int
    sample_sizes: dict[str, int] = field(default_factory=dict)
    findings: list[FeatureFinding] = field(default_factory=list)
    diff_yaml: str = ""
    output_path: str = ""
    diff_path: str = ""
    confidence: str = ""          # high / medium / low based on sample size
    too_few_data: bool = False


def _cohens_d(group1: list[float], group2: list[float]) -> float:
    """Standard pooled-SD Cohen's d. Returns 0 if either group <2 or pooled SD is 0."""
    if len(group1) < 2 or len(group2) < 2:
        return 0.0
    m1, m2 = statistics.mean(group1), statistics.mean(group2)
    s1, s2 = statistics.stdev(group1), statistics.stdev(group2)
    n1, n2 = len(group1), len(group2)
    pooled = math_sqrt((((n1 - 1) * s1**2) + ((n2 - 1) * s2**2)) / (n1 + n2 - 2))
    if pooled == 0:
        return 0.0
    return (m1 - m2) / pooled


def math_sqrt(x: float) -> float:
    """Small wrapper so we can import-free at module load."""
    import math
    return math.sqrt(max(x, 0))


def _significance_label(d: float) -> str:
    abs_d = abs(d)
    if abs_d >= 0.8:
        return "large"
    if abs_d >= 0.5:
        return "medium"
    if abs_d >= 0.2:
        return "small"
    return "negligible"


def _load_outcomes(site_slug: str) -> list[dict]:
    p = PLUGIN_ROOT / "projects" / site_slug / "audits" / "outcomes.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("outcomes", []) or []
    except (OSError, json.JSONDecodeError):
        return []


def analyze_site(
    site_slug: str,
    *,
    min_per_group: int = 5,
    min_total_articles: int = 10,
) -> TunerReport:
    outcomes = _load_outcomes(site_slug)
    if not outcomes:
        return TunerReport(
            site_slug=site_slug,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            total_articles=0,
            too_few_data=True,
        )

    # Partition by outcome
    winners = [o for o in outcomes if o.get("outcome") == "winner"]
    mid = [o for o in outcomes if o.get("outcome") == "mid"]
    losers = [o for o in outcomes if o.get("outcome") == "loser"]

    sample_sizes = {"winner": len(winners), "mid": len(mid), "loser": len(losers)}

    report = TunerReport(
        site_slug=site_slug,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        total_articles=len(outcomes),
        sample_sizes=sample_sizes,
    )

    if len(outcomes) < min_total_articles:
        report.too_few_data = True
        report.confidence = "low"
        return report

    if len(winners) < min_per_group or len(losers) < min_per_group:
        report.too_few_data = True
        report.confidence = "low"
        return report

    # Numeric features: winners vs losers Cohen's d
    for feat in NUMERIC_FEATURES:
        w_vals = [
            float(o.get("features", {}).get(feat, 0))
            for o in winners if feat in o.get("features", {})
        ]
        l_vals = [
            float(o.get("features", {}).get(feat, 0))
            for o in losers if feat in o.get("features", {})
        ]
        if len(w_vals) < min_per_group or len(l_vals) < min_per_group:
            continue
        d = _cohens_d(w_vals, l_vals)
        sig = _significance_label(d)
        if sig in ("negligible", "small"):
            continue

        w_mean = round(statistics.mean(w_vals), 2)
        l_mean = round(statistics.mean(l_vals), 2)
        delta = round(w_mean - l_mean, 2)

        is_lower_better = feat in LOWER_IS_BETTER
        wins_with = "lower" if is_lower_better else "higher"
        suggestion = (
            f"winners have {wins_with} {feat} (mean {w_mean} vs losers {l_mean}). "
            f"Consider targeting around {w_mean} (band ±15%)."
        )

        report.findings.append(FeatureFinding(
            feature=feat,
            feature_type="numeric",
            winner_value=w_mean,
            loser_value=l_mean,
            effect_size=round(d, 3),
            significance=sig,
            suggestion=suggestion,
            sample_sizes={"winner_n": len(w_vals), "loser_n": len(l_vals)},
        ))

    # Categorical features: per-category win rate
    for feat in CATEGORICAL_FEATURES:
        win_rate_by_cat: dict[str, dict] = defaultdict(lambda: {"wins": 0, "total": 0})
        for o in outcomes:
            val = o.get("features", {}).get(feat)
            if not val:
                continue
            win_rate_by_cat[val]["total"] += 1
            if o.get("outcome") == "winner":
                win_rate_by_cat[val]["wins"] += 1

        if len(win_rate_by_cat) < 2:
            continue

        # Compute overall win rate
        overall_win = len(winners) / len(outcomes)

        for cat, counts in win_rate_by_cat.items():
            if counts["total"] < min_per_group:
                continue
            rate = counts["wins"] / counts["total"]
            delta = rate - overall_win
            if abs(delta) < 0.10:   # need ≥10 pts above baseline to flag
                continue
            sig = "large" if abs(delta) >= 0.20 else "medium" if abs(delta) >= 0.10 else "small"
            direction = "more often" if delta > 0 else "less often"
            suggestion = (
                f"{feat}={cat!r} wins {direction} (rate {rate:.0%} vs portfolio avg {overall_win:.0%}). "
                f"{'Bias towards' if delta > 0 else 'Avoid'} this {feat}."
            )
            report.findings.append(FeatureFinding(
                feature=f"{feat}={cat}",
                feature_type="categorical",
                winner_value=f"{rate:.0%}",
                loser_value=f"{overall_win:.0%}",
                effect_size=round(delta, 3),
                significance=sig,
                suggestion=suggestion,
                sample_sizes={"category_n": counts["total"], "category_wins": counts["wins"]},
            ))

    # Confidence based on sample sizes
    n_winners = len(winners)
    if n_winners >= 20:
        report.confidence = "high"
    elif n_winners >= 10:
        report.confidence = "medium"
    else:
        report.confidence = "low"

    # Generate diff YAML for review
    report.diff_yaml = _generate_diff_yaml(report)

    # Persist
    out_dir = PLUGIN_ROOT / "projects" / site_slug / "audits"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    out_path = out_dir / f"brand-tuner-report-{today}.json"
    out_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False),
                        encoding="utf-8")
    report.output_path = str(out_path)

    diff_path = out_dir / f"brand-guideline.diff.{today}.yaml"
    diff_path.write_text(report.diff_yaml, encoding="utf-8")
    report.diff_path = str(diff_path)

    return report


def _generate_diff_yaml(report: TunerReport) -> str:
    """Render findings as a YAML diff overlay for brand-guideline.yaml."""
    lines = [
        f"# Brand-guideline tuner suggestions ({report.site_slug})",
        f"# Generated: {report.evaluated_at}",
        f"# Confidence: {report.confidence} (winners n={report.sample_sizes.get('winner', 0)}, "
        f"losers n={report.sample_sizes.get('loser', 0)})",
        "#",
        "# Apply selectively. Edit brand-guideline.yaml manually after review.",
        "# This file is suggestions, NOT auto-applied.",
        "",
    ]

    numeric = [f for f in report.findings if f.feature_type == "numeric"]
    categorical = [f for f in report.findings if f.feature_type == "categorical"]

    if numeric:
        lines.append("# Numeric targets — derived from winners' mean")
        lines.append("content_targets:")
        for f in numeric:
            lines.append(f"  {f.feature}:")
            lines.append(f"    target: {f.winner_value}     # winners' mean")
            lines.append(f"    band_pct: 15")
            lines.append(f"    rationale: \"effect {f.effect_size} ({f.significance}); "
                         f"loser mean was {f.loser_value}\"")
        lines.append("")

    if categorical:
        lines.append("# Categorical biases — favor or avoid")
        lines.append("category_bias:")
        for f in categorical:
            feat_name, _, val = f.feature.partition("=")
            direction = "prefer" if f.effect_size > 0 else "avoid"
            lines.append(f"  {feat_name}:")
            lines.append(f"    {direction}: [{val!r}]")
            lines.append(f"    rationale: \"win rate {f.winner_value} vs portfolio {f.loser_value}\"")
        lines.append("")

    if not numeric and not categorical:
        lines.append("# No significant patterns detected yet.")
        lines.append("# Publish more articles + run outcome_tagger to gather data.")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Brand-guideline auto-tuner")
    ap.add_argument("--site")
    ap.add_argument("--all-sites", action="store_true")
    ap.add_argument("--min-per-group", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.site and not args.all_sites:
        print("Need --site or --all-sites", file=sys.stderr)
        return 2

    sites = (
        sorted(p.name for p in (PLUGIN_ROOT / "projects").iterdir() if p.is_dir())
        if args.all_sites else [args.site]
    )

    reports = []
    for slug in sites:
        r = analyze_site(slug, min_per_group=args.min_per_group)
        reports.append(r)
        if args.json:
            continue

        print(f"━━ Brand tuner: {slug} ━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  Articles:    {r.total_articles} (winners {r.sample_sizes.get('winner', 0)}, "
              f"mid {r.sample_sizes.get('mid', 0)}, losers {r.sample_sizes.get('loser', 0)})")
        print(f"  Confidence:  {r.confidence}")
        if r.too_few_data:
            print(f"  ⚠ Not enough data (need ≥10 articles, ≥5 each in winner+loser groups)")
            print(f"  Publish more articles and run outcome_tagger.")
            continue
        print(f"  Findings:    {len(r.findings)}")
        print(f"  Output:      {r.output_path}")
        print(f"  Diff:        {r.diff_path}")
        print()

        if r.findings:
            print("  Significant patterns:")
            for f in sorted(r.findings, key=lambda x: -abs(x.effect_size))[:8]:
                icon = {"large": "🔴", "medium": "🟡"}.get(f.significance, "•")
                print(f"    {icon} [{f.significance:<6s}] {f.feature}")
                print(f"        {f.suggestion}")
        print()

    if args.json:
        print(json.dumps([asdict(r) for r in reports], indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
