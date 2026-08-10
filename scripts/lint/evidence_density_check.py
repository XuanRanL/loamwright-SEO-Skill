"""scripts/lint/evidence_density_check.py — Evidence-density rule enforcement.

Enforces the 4 evidence-density rules (per references/seo/evidence-density-requirements.md):

  Rule 1: ≥N markdown tables (N varies by format)
  Rule 2: ≥M statistics with FLOW Evidence Triple (year + citation + URL)
  Rule 3: ≥1 Tier-1 source (peer-reviewed / .gov / .edu / authoritative research)
  Rule 4: ≥2 Information Gain Markers ([ORIGINAL DATA] / [PERSONAL EXPERIENCE] / [UNIQUE INSIGHT])

Used by seo-auditor + geo-auditor + cite_scorer.

CLI:
    python -m scripts.lint.evidence_density_check --input draft.md --format listicle --json
    python -m scripts.lint.evidence_density_check --stdin --format pillar-page --ymyl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


# Per-format minimum requirements
FORMAT_RULES: dict[str, dict] = {
    # format → {min_tables, min_stats, min_tier1, min_markers, min_markers_ymyl}
    "default":             {"min_tables": 2, "min_stats": 3, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "listicle":            {"min_tables": 2, "min_stats": 4, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "pillar-page":         {"min_tables": 3, "min_stats": 5, "min_tier1": 2, "min_markers": 3, "min_markers_ymyl": 5},
    "comparison":          {"min_tables": 3, "min_stats": 4, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "case-study":          {"min_tables": 2, "min_stats": 5, "min_tier1": 1, "min_markers": 3, "min_markers_ymyl": 5},
    "how-to-guide":        {"min_tables": 2, "min_stats": 3, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "product-review":      {"min_tables": 2, "min_stats": 5, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "definition":          {"min_tables": 2, "min_stats": 3, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "encyclopedic":        {"min_tables": 3, "min_stats": 5, "min_tier1": 3, "min_markers": 3, "min_markers_ymyl": 7},
    "data-research":       {"min_tables": 4, "min_stats": 10, "min_tier1": 2, "min_markers": 4, "min_markers_ymyl": 5},
    "buyers-guide":        {"min_tables": 3, "min_stats": 4, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "faq-knowledge":       {"min_tables": 2, "min_stats": 3, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "roundup":             {"min_tables": 2, "min_stats": 3, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "shortlist-validation":{"min_tables": 1, "min_stats": 3, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "news-analysis":       {"min_tables": 1, "min_stats": 3, "min_tier1": 0, "min_markers": 2, "min_markers_ymyl": 4},
    "opinion":             {"min_tables": 1, "min_stats": 3, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "personal-story":      {"min_tables": 1, "min_stats": 2, "min_tier1": 0, "min_markers": 2, "min_markers_ymyl": 3},
    "interview":           {"min_tables": 1, "min_stats": 2, "min_tier1": 0, "min_markers": 1, "min_markers_ymyl": 3},
    "problem-solution":    {"min_tables": 2, "min_stats": 3, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "glossary-hub":        {"min_tables": 2, "min_stats": 3, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "curated-roundup":     {"min_tables": 3, "min_stats": 3, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "level-guide":         {"min_tables": 2, "min_stats": 3, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "multi-intent-hybrid": {"min_tables": 3, "min_stats": 4, "min_tier1": 1, "min_markers": 2, "min_markers_ymyl": 4},
    "template-resource":   {"min_tables": 1, "min_stats": 2, "min_tier1": 0, "min_markers": 1, "min_markers_ymyl": 2},
    "checklist":           {"min_tables": 1, "min_stats": 2, "min_tier1": 0, "min_markers": 1, "min_markers_ymyl": 2},
    # 2026-08-02: digest layout = 1 At-a-Glance table + a By-the-Numbers
    # stat-grid LIST (invisible to table counters); the "default" 2-table
    # floor mislabeled every correctly-built digest.
    "weekly-digest":       {"min_tables": 1, "min_stats": 3, "min_tier1": 0, "min_markers": 2, "min_markers_ymyl": 4},
}


# Tier-1 source indicators
TIER1_PATTERNS = [
    # DOI links (peer-reviewed)
    r"https?://(?:dx\.)?doi\.org/10\.",
    # .gov / .edu
    r"https?://[^\s]+\.gov(?:/|\s|$)",
    r"https?://[^\s]+\.edu(?:/|\s|$)",
    # Wikipedia (cross-reference)
    r"https?://[^.]+\.wikipedia\.org/",
    # Authoritative orgs (top global)
    r"https?://(?:www\.)?nature\.com/",
    r"https?://(?:www\.)?science\.org/",
    r"https?://(?:www\.)?nih\.gov/",
    r"https?://(?:www\.)?who\.int/",
    r"https?://(?:www\.)?cdc\.gov/",
    r"https?://(?:www\.)?un\.org/",
    r"https?://(?:www\.)?worldbank\.org/",
    r"https?://(?:www\.)?imf\.org/",
    r"https?://(?:www\.)?oecd\.org/",
    r"https?://(?:www\.)?harvard\.edu/",
    r"https?://(?:www\.)?stanford\.edu/",
    r"https?://(?:www\.)?mit\.edu/",
    r"https?://(?:www\.)?princeton\.edu/",
    # Government statistical agencies
    r"https?://(?:www\.)?bls\.gov/",         # US Bureau of Labor Statistics
    r"https?://(?:www\.)?census\.gov/",      # US Census
    r"https?://(?:www\.)?ons\.gov\.uk/",     # UK Office for National Statistics
    r"https?://(?:www\.)?eurostat\.ec\.europa\.eu/",
    # Major research orgs
    r"https?://(?:www\.)?gartner\.com/",
    r"https?://(?:www\.)?forrester\.com/",
    r"https?://(?:www\.)?mckinsey\.com/",
    r"https?://(?:www\.)?pewresearch\.org/",
    r"https?://(?:www\.)?nielsen\.com/",
]


@dataclass
class EvidenceDensityReport:
    format: str
    is_ymyl: bool = False
    table_count: int = 0
    stat_with_citation_count: int = 0
    stat_with_year_count: int = 0
    tier1_source_count: int = 0
    info_gain_marker_count: int = 0
    marker_breakdown: dict[str, int] = field(default_factory=dict)
    table_locations: list[str] = field(default_factory=list)
    tier1_source_urls: list[str] = field(default_factory=list)
    rule_results: dict[str, bool] = field(default_factory=dict)
    overall_pass: bool = False
    recommendations: list[str] = field(default_factory=list)
    score: int = 0   # 0-100 composite


def _count_tables(text: str) -> tuple[int, list[str]]:
    """Count markdown tables. A table = ≥2 rows of `|...|` with header separator `|---|`."""
    locations = []
    count = 0
    lines = text.split("\n")
    in_table = False
    table_start_heading = ""
    last_h2 = ""
    for i, line in enumerate(lines):
        h2_match = re.match(r"^##\s+(.+)$", line)
        if h2_match:
            last_h2 = h2_match.group(1).strip()
            in_table = False
            continue

        # Table row: starts and ends with |
        if re.match(r"^\s*\|.+\|\s*$", line):
            if not in_table:
                # Look ahead for separator
                if i + 1 < len(lines) and re.match(r"^\s*\|[\s\-:|]+\|\s*$", lines[i + 1]):
                    in_table = True
                    table_start_heading = last_h2 or "(intro)"
                    count += 1
                    locations.append(table_start_heading)
        else:
            in_table = False

    return count, locations


def _count_stats_with_citation(text: str) -> tuple[int, int]:
    """Count statistics with full FLOW Triple."""
    # Stats: percentages, multipliers, currency
    stat_re = re.compile(r"\b(\d+(?:\.\d+)?%|\d+x|\d+×|\$\d+(?:,\d{3})*(?:\.\d+)?|\d+ (?:hours?|minutes?|days?|years?|weeks?))\b")
    # Year anchor (2020-2030)
    year_re = re.compile(r"\b20[2-3]\d\b")
    # Inline citation: (Author, Year) or [Text](URL) markdown link near a stat
    citation_re = re.compile(r"\(([^()]+, 20\d\d)\)|\[[^\]]+\]\(https?://[^\)]+\)")

    sentences = re.split(r"(?<=[.!?])\s+", text)
    with_citation = 0
    with_year = 0
    for s in sentences:
        if not stat_re.search(s):
            continue
        if citation_re.search(s):
            with_citation += 1
        if year_re.search(s):
            with_year += 1
    return with_citation, with_year


def _count_tier1_sources(text: str) -> tuple[int, list[str]]:
    """Count Tier-1 source URLs in the text."""
    urls = set()
    for pattern in TIER1_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            urls.add(m.group(0).rstrip(".,;)\""))
    return len(urls), sorted(urls)[:10]


def _count_info_gain_markers(text: str) -> tuple[int, dict[str, int]]:
    """Count [ORIGINAL DATA], [PERSONAL EXPERIENCE], [UNIQUE INSIGHT] markers."""
    breakdown = {
        "ORIGINAL DATA": len(re.findall(r"\[ORIGINAL DATA\]", text)),
        "PERSONAL EXPERIENCE": len(re.findall(r"\[PERSONAL EXPERIENCE\]", text)),
        "UNIQUE INSIGHT": len(re.findall(r"\[UNIQUE INSIGHT\]", text)),
    }
    total = sum(breakdown.values())
    return total, breakdown


def check_evidence_density(
    text: str, *, format: str = "default", is_ymyl: bool = False,
) -> EvidenceDensityReport:
    """Run all 4 evidence-density rules on the text."""
    rules = FORMAT_RULES.get(format, FORMAT_RULES["default"])

    table_count, table_locations = _count_tables(text)
    stat_with_cite, stat_with_year = _count_stats_with_citation(text)
    tier1_count, tier1_urls = _count_tier1_sources(text)
    marker_count, marker_breakdown = _count_info_gain_markers(text)

    min_markers = rules["min_markers_ymyl"] if is_ymyl else rules["min_markers"]

    report = EvidenceDensityReport(
        format=format,
        is_ymyl=is_ymyl,
        table_count=table_count,
        stat_with_citation_count=stat_with_cite,
        stat_with_year_count=stat_with_year,
        tier1_source_count=tier1_count,
        info_gain_marker_count=marker_count,
        marker_breakdown=marker_breakdown,
        table_locations=table_locations,
        tier1_source_urls=tier1_urls,
    )

    # Rule checks
    report.rule_results = {
        "rule_1_tables_min": table_count >= rules["min_tables"],
        "rule_2_stats_with_citation_min": stat_with_cite >= rules["min_stats"],
        "rule_3_tier1_source_min": tier1_count >= rules["min_tier1"],
        "rule_4_markers_min": marker_count >= min_markers,
    }
    report.overall_pass = all(report.rule_results.values())

    # Recommendations
    if not report.rule_results["rule_1_tables_min"]:
        diff = rules["min_tables"] - table_count
        report.recommendations.append(
            f"Add {diff} more table(s) — {format} format requires ≥{rules['min_tables']} tables"
            f" (have: {table_count})"
        )
    if not report.rule_results["rule_2_stats_with_citation_min"]:
        diff = rules["min_stats"] - stat_with_cite
        report.recommendations.append(
            f"Add {diff} more statistic(s) with FLOW Triple (year + citation + URL) — "
            f"format requires ≥{rules['min_stats']} (have: {stat_with_cite})"
        )
    if not report.rule_results["rule_3_tier1_source_min"]:
        diff = rules["min_tier1"] - tier1_count
        report.recommendations.append(
            f"Add {diff} more Tier-1 source(s) — peer-reviewed DOI / .gov / .edu / authoritative org"
            f" (have: {tier1_count})"
        )
    if not report.rule_results["rule_4_markers_min"]:
        diff = min_markers - marker_count
        report.recommendations.append(
            f"Add {diff} more Information Gain Marker(s) ([ORIGINAL DATA] / [PERSONAL EXPERIENCE] / "
            f"[UNIQUE INSIGHT]) — need ≥{min_markers} (have: {marker_count})"
        )

    # Composite score (0-100)
    score = 0
    score += min(table_count / max(rules["min_tables"], 1), 1.5) * 25
    score += min(stat_with_cite / max(rules["min_stats"], 1), 1.5) * 30
    score += min(tier1_count / max(rules["min_tier1"], 1), 1.5) * 25 if rules["min_tier1"] > 0 else 25
    score += min(marker_count / max(min_markers, 1), 1.5) * 20
    report.score = min(int(score / 1.5), 100)   # normalize to 100

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Evidence-density rule checker")
    ap.add_argument("--input", type=Path)
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--format", default="default",
                    choices=list(FORMAT_RULES.keys()))
    ap.add_argument("--ymyl", action="store_true",
                    help="Apply YMYL thresholds (stricter)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.stdin:
        text = sys.stdin.read()
    elif args.input:
        if not args.input.exists():
            print(f"File not found: {args.input}", file=sys.stderr)
            return 1
        text = args.input.read_text(encoding="utf-8")
    else:
        print("Need --input or --stdin", file=sys.stderr)
        return 2

    report = check_evidence_density(text, format=args.format, is_ymyl=args.ymyl)

    if args.json:
        print(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    else:
        icon = "✓" if report.overall_pass else "✗"
        print(f"{icon} Evidence density score: {report.score}/100  (format={report.format}, ymyl={report.is_ymyl})")
        print()
        print(f"  Rule 1 Tables          {report.table_count} {('✓' if report.rule_results['rule_1_tables_min'] else '✗')}")
        if report.table_locations:
            for loc in report.table_locations[:5]:
                print(f"    @ {loc}")
        print(f"  Rule 2 Stats+citation  {report.stat_with_citation_count} {('✓' if report.rule_results['rule_2_stats_with_citation_min'] else '✗')}")
        print(f"  Rule 3 Tier-1 sources  {report.tier1_source_count} {('✓' if report.rule_results['rule_3_tier1_source_min'] else '✗')}")
        if report.tier1_source_urls:
            for u in report.tier1_source_urls[:3]:
                print(f"    {u[:80]}")
        print(f"  Rule 4 Info Gain       {report.info_gain_marker_count} {('✓' if report.rule_results['rule_4_markers_min'] else '✗')}")
        for k, v in report.marker_breakdown.items():
            if v:
                print(f"    {k}: {v}")
        if report.recommendations:
            print()
            print("Recommendations:")
            for r in report.recommendations:
                print(f"  • {r}")
    return 0 if report.overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
