"""SEO Health Score aggregator.

Reads per-module audit results from a modules/ directory and produces
a weighted overall SEO Health Score with per-category breakdown,
severity-sorted findings, badge assignment, and quick-win suggestions.

Usage:
    python -m scripts.audit.audit_scorer modules/ --json -o report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

CATEGORY_WEIGHTS: dict[str, float] = {
    "technical_seo": 0.22,
    "content_quality": 0.23,
    "on_page_seo": 0.20,
    "schema_structured_data": 0.10,
    "performance_cwv": 0.10,
    "ai_search_readiness": 0.10,
    "images": 0.05,
}

# Module file (stem) -> list of (category, contribution_weight within that category)
# contribution_weight is relative; scores are averaged across contributors.
MODULE_CATEGORY_MAP: dict[str, list[str]] = {
    "technical": ["technical_seo"],
    "sitemap": ["technical_seo"],
    "backlinks": ["technical_seo"],
    "content": ["content_quality"],
    "cluster": ["content_quality"],
    "schema": ["schema_structured_data"],
    "performance": ["performance_cwv"],
    "visual": ["images", "on_page_seo"],
    "geo": ["ai_search_readiness"],
    "sxo": ["on_page_seo"],
    "local": ["on_page_seo"],
    "ecommerce": ["schema_structured_data", "on_page_seo"],
    # drift is informational only -- excluded from scoring
}

INFORMATIONAL_MODULES: set[str] = {"drift"}

BADGE_THRESHOLDS: list[tuple[int, str, str]] = [
    (90, "Excellent", "green"),
    (70, "Good", "blue"),
    (50, "Needs Improvement", "amber"),
    (0, "Poor", "red"),
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    severity: str
    category: str
    message: str
    evidence: str = ""
    recommendation: str = ""
    source_module: str = ""

    def to_dict(self) -> dict[str, str]:
        d: dict[str, str] = {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "source_module": self.source_module,
        }
        if self.evidence:
            d["evidence"] = self.evidence
        if self.recommendation:
            d["recommendation"] = self.recommendation
        return d


@dataclass
class ModuleResult:
    name: str
    score: float
    findings: list[Finding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CategoryScore:
    name: str
    score: float
    weight: float
    weighted_contribution: float
    modules: list[str]


@dataclass
class AuditReport:
    overall_score: float
    badge: str
    badge_color: str
    categories: dict[str, CategoryScore]
    findings_summary: dict[str, int]
    top_critical: list[dict[str, str]]
    top_quick_wins: list[dict[str, str]]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": round(self.overall_score),
            "badge": self.badge,
            "badge_color": self.badge_color,
            "categories": {
                k: {
                    "score": round(v.score, 2),
                    "weight": v.weight,
                    "weighted_contribution": round(v.weighted_contribution, 2),
                    "modules": v.modules,
                }
                for k, v in self.categories.items()
            },
            "findings_summary": self.findings_summary,
            "top_critical": self.top_critical,
            "top_quick_wins": self.top_quick_wins,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def load_module(path: Path) -> ModuleResult | None:
    """Load a single module JSON file. Returns None if file doesn't exist or is invalid."""
    if not path.is_file():
        return None
    try:
        # utf-8-sig handles optional BOM (common on Windows)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return None

    score = data.get("score")
    if score is None:
        return None

    findings: list[Finding] = []
    for f in data.get("findings", []):
        findings.append(
            Finding(
                severity=f.get("severity", "low"),
                category=f.get("category", ""),
                message=f.get("message", ""),
                evidence=f.get("evidence", ""),
                recommendation=f.get("recommendation", ""),
                source_module=path.stem,
            )
        )

    return ModuleResult(
        name=path.stem,
        score=float(score),
        findings=findings,
        metadata=data.get("metadata", {}),
    )


def load_all_modules(modules_dir: Path) -> dict[str, ModuleResult]:
    """Load all recognized module files from the directory."""
    results: dict[str, ModuleResult] = {}
    for module_name in MODULE_CATEGORY_MAP:
        path = modules_dir / f"{module_name}.json"
        result = load_module(path)
        if result is not None:
            results[module_name] = result
    return results


def compute_category_scores(
    modules: dict[str, ModuleResult],
) -> dict[str, CategoryScore]:
    """Compute per-category scores by averaging contributing module scores."""
    # Build category -> list of (module_name, score)
    category_contributions: dict[str, list[tuple[str, float]]] = {
        cat: [] for cat in CATEGORY_WEIGHTS
    }

    for module_name, result in modules.items():
        if module_name in INFORMATIONAL_MODULES:
            continue
        categories = MODULE_CATEGORY_MAP.get(module_name, [])
        for cat in categories:
            if cat in category_contributions:
                category_contributions[cat].append((module_name, result.score))

    category_scores: dict[str, CategoryScore] = {}
    for cat, weight in CATEGORY_WEIGHTS.items():
        contributions = category_contributions[cat]
        if not contributions:
            # No modules contributed -- category is excluded
            continue
        avg_score = sum(s for _, s in contributions) / len(contributions)
        avg_score = max(0.0, min(100.0, avg_score))
        category_scores[cat] = CategoryScore(
            name=cat,
            score=avg_score,
            weight=weight,
            weighted_contribution=avg_score * weight,
            modules=[name for name, _ in contributions],
        )

    return category_scores


def compute_overall_score(category_scores: dict[str, CategoryScore]) -> float:
    """Compute weighted overall score, redistributing weight from missing categories."""
    if not category_scores:
        return 0.0

    total_active_weight = sum(cs.weight for cs in category_scores.values())
    if total_active_weight <= 0:
        return 0.0

    # Redistribute: scale each category's contribution so active weights sum to 1.0
    scale_factor = 1.0 / total_active_weight
    overall = sum(
        cs.score * cs.weight * scale_factor for cs in category_scores.values()
    )
    return max(0.0, min(100.0, overall))


def assign_badge(score: float) -> tuple[str, str]:
    """Assign badge label and color based on overall score."""
    rounded = round(score)
    for threshold, label, color in BADGE_THRESHOLDS:
        if rounded >= threshold:
            return label, color
    return "Poor", "red"


def aggregate_findings(modules: dict[str, ModuleResult]) -> list[Finding]:
    """Collect all findings from all modules, sorted by severity."""
    all_findings: list[Finding] = []
    for result in modules.values():
        all_findings.extend(result.findings)

    all_findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 99))
    return all_findings


def summarize_findings(findings: list[Finding]) -> dict[str, int]:
    """Count findings by severity level."""
    summary: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = f.severity if f.severity in summary else "low"
        summary[sev] += 1
    return summary


def extract_top_critical(findings: list[Finding], limit: int = 10) -> list[dict[str, str]]:
    """Extract top critical findings."""
    critical = [f for f in findings if f.severity == "critical"]
    return [f.to_dict() for f in critical[:limit]]


def extract_quick_wins(findings: list[Finding], limit: int = 5) -> list[dict[str, str]]:
    """Extract quick wins: medium/low severity findings with recommendations.

    Quick wins are issues that are relatively easy to fix (lower severity)
    but still provide meaningful improvement when addressed.
    """
    candidates = [
        f
        for f in findings
        if f.severity in ("medium", "low") and f.recommendation
    ]
    return [f.to_dict() for f in candidates[:limit]]


def score_audit(modules_dir: Path) -> AuditReport:
    """Main scoring pipeline: load modules, compute scores, build report."""
    modules = load_all_modules(modules_dir)

    if not modules:
        badge_label, badge_color = assign_badge(0)
        return AuditReport(
            overall_score=0.0,
            badge=badge_label,
            badge_color=badge_color,
            categories={},
            findings_summary={"critical": 0, "high": 0, "medium": 0, "low": 0},
            top_critical=[],
            top_quick_wins=[],
            metadata={"modules_loaded": 0, "modules_dir": str(modules_dir)},
        )

    category_scores = compute_category_scores(modules)
    overall = compute_overall_score(category_scores)
    badge_label, badge_color = assign_badge(overall)

    all_findings = aggregate_findings(modules)
    findings_summary = summarize_findings(all_findings)
    top_critical = extract_top_critical(all_findings)
    top_quick_wins = extract_quick_wins(all_findings)

    # Update weighted_contribution after redistribution
    total_active_weight = sum(cs.weight for cs in category_scores.values())
    if total_active_weight > 0:
        scale_factor = 1.0 / total_active_weight
        for cs in category_scores.values():
            cs.weighted_contribution = cs.score * cs.weight * scale_factor

    metadata: dict[str, Any] = {
        "modules_loaded": len(modules),
        "modules_missing": [
            m
            for m in MODULE_CATEGORY_MAP
            if m not in modules and m not in INFORMATIONAL_MODULES
        ],
        "modules_dir": str(modules_dir),
        "total_findings": len(all_findings),
    }

    return AuditReport(
        overall_score=overall,
        badge=badge_label,
        badge_color=badge_color,
        categories=category_scores,
        findings_summary=findings_summary,
        top_critical=top_critical,
        top_quick_wins=top_quick_wins,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audit_scorer",
        description="Aggregate per-module SEO audit results into a weighted health score.",
    )
    parser.add_argument(
        "modules_dir",
        type=Path,
        help="Path to the modules/ directory containing per-module JSON files.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output file path. Defaults to stdout.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output as JSON (default when --output is specified).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    modules_dir: Path = args.modules_dir
    if not modules_dir.is_dir():
        print(f"Error: '{modules_dir}' is not a directory.", file=sys.stderr)
        return 1

    report = score_audit(modules_dir)
    output_data = report.to_dict()

    use_json = args.json or args.output is not None
    if use_json:
        formatted = json.dumps(output_data, indent=2, ensure_ascii=False)
    else:
        formatted = _format_text_report(output_data)

    if args.output:
        args.output.write_text(formatted, encoding="utf-8")
    else:
        print(formatted)

    return 0


def _format_text_report(data: dict[str, Any]) -> str:
    """Format a human-readable text report."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"  SEO HEALTH SCORE: {data['overall_score']}/100  [{data['badge']}]")
    lines.append("=" * 60)
    lines.append("")

    lines.append("Category Breakdown:")
    lines.append("-" * 40)
    for cat_key, cat_data in data["categories"].items():
        label = cat_key.replace("_", " ").title()
        lines.append(
            f"  {label:<30} {cat_data['score']:>5.1f}  "
            f"(weight: {cat_data['weight']:.0%}, "
            f"contribution: {cat_data['weighted_contribution']:.2f})"
        )
    lines.append("")

    lines.append("Findings Summary:")
    lines.append("-" * 40)
    for sev in ("critical", "high", "medium", "low"):
        count = data["findings_summary"].get(sev, 0)
        lines.append(f"  {sev.capitalize():<12} {count}")
    lines.append("")

    if data["top_critical"]:
        lines.append("Top Critical Issues:")
        lines.append("-" * 40)
        for i, finding in enumerate(data["top_critical"], 1):
            lines.append(f"  {i}. [{finding.get('source_module', '?')}] {finding['message']}")
            if finding.get("recommendation"):
                lines.append(f"     -> {finding['recommendation']}")
        lines.append("")

    if data["top_quick_wins"]:
        lines.append("Quick Wins:")
        lines.append("-" * 40)
        for i, finding in enumerate(data["top_quick_wins"], 1):
            lines.append(f"  {i}. [{finding.get('source_module', '?')}] {finding['message']}")
            if finding.get("recommendation"):
                lines.append(f"     -> {finding['recommendation']}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
