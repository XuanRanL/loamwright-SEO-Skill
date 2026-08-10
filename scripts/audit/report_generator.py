#!/usr/bin/env python3
"""Generate Markdown audit report from per-module JSON results.

Usage:
    python -m scripts.audit.report_generator ./seo-audit-example-2026-05-25/
    python -m scripts.audit.report_generator ./audit/ --output ./audit/FULL-AUDIT-REPORT.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


BADGE_MAP = {
    "Excellent": "🟢",
    "Good": "🔵",
    "Needs Improvement": "🟡",
    "Poor": "🔴",
}

CATEGORY_LABELS = {
    "technical_seo": "Technical SEO",
    "content_quality": "Content Quality",
    "on_page_seo": "On-Page SEO",
    "schema_structured_data": "Schema & Structured Data",
    "performance_cwv": "Performance (Core Web Vitals)",
    "ai_search_readiness": "AI Search Readiness",
    "images": "Images",
}

SEVERITY_ORDER = ["critical", "high", "medium", "low"]


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8-sig")
    return json.loads(text)


def _severity_icon(severity: str) -> str:
    icons = {"critical": "🚨", "high": "⚠️", "medium": "💡", "low": "ℹ️"}
    return icons.get(severity, "•")


def generate_report(audit_dir: Path) -> str:
    scores_data = _load_json(audit_dir / "scores.json")
    business_data = _load_json(audit_dir / "business-type.json")
    crawl_data = _load_json(audit_dir / "crawl-results.json")

    if not scores_data:
        return "# Error\n\nNo scores.json found in audit directory."

    overall = scores_data.get("overall_score", 0)
    badge = scores_data.get("badge", "Unknown")
    badge_icon = BADGE_MAP.get(badge, "⚪")
    categories = scores_data.get("categories", {})
    findings_summary = scores_data.get("findings_summary", {})

    biz_type = "Unknown"
    if business_data:
        biz_type = (business_data.get("primary_type") or "unknown").replace("_", " ").title()

    pages_crawled = 0
    if isinstance(crawl_data, list):
        pages_crawled = len(crawl_data)

    domain = audit_dir.name.replace("seo-audit-", "").rsplit("-", 3)[0] if "seo-audit-" in audit_dir.name else "website"

    lines: list[str] = []

    # Header
    lines.append(f"# SEO Health Audit: {domain}")
    lines.append("")
    lines.append(f"**Date**: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"**Business Type**: {biz_type}")
    lines.append(f"**Pages Crawled**: {pages_crawled}")
    lines.append("")

    # Overall Score
    lines.append("---")
    lines.append("")
    lines.append(f"## Overall SEO Health Score: {overall}/100 {badge_icon} {badge}")
    lines.append("")

    # Findings Summary
    lines.append(f"| Severity | Count |")
    lines.append(f"|----------|-------|")
    for sev in SEVERITY_ORDER:
        count = findings_summary.get(sev, 0)
        lines.append(f"| {_severity_icon(sev)} {sev.capitalize()} | {count} |")
    lines.append("")

    # Top Critical Issues
    top_critical = scores_data.get("top_critical", [])
    if top_critical:
        lines.append("### Top Critical Issues")
        lines.append("")
        for issue in top_critical[:5]:
            msg = issue.get("message", "")
            lines.append(f"1. **{msg}**")
        lines.append("")

    # Top Quick Wins
    top_wins = scores_data.get("top_quick_wins", [])
    if top_wins:
        lines.append("### Quick Wins")
        lines.append("")
        for win in top_wins[:5]:
            msg = win.get("message", "") if isinstance(win, dict) else str(win)
            lines.append(f"1. {msg}")
        lines.append("")

    # Per-Category Sections
    lines.append("---")
    lines.append("")

    for cat_key, cat_label in CATEGORY_LABELS.items():
        cat_data = categories.get(cat_key)
        if not cat_data:
            continue

        cat_score = cat_data.get("score", 0)
        cat_weight = cat_data.get("weight", 0)
        modules = cat_data.get("modules", [])

        cat_badge = "Excellent" if cat_score >= 90 else "Good" if cat_score >= 70 else "Needs Improvement" if cat_score >= 50 else "Poor"
        cat_icon = BADGE_MAP.get(cat_badge, "⚪")

        lines.append(f"## {cat_label}: {cat_score}/100 {cat_icon}")
        lines.append("")
        lines.append(f"*Weight: {int(cat_weight * 100)}% | Modules: {', '.join(modules)}*")
        lines.append("")

        # Load findings from contributing modules
        all_findings: list[dict[str, Any]] = []
        for mod_name in modules:
            mod_data = _load_json(audit_dir / "modules" / f"{mod_name}.json")
            if mod_data and isinstance(mod_data, dict):
                all_findings.extend(mod_data.get("findings", []))

        if all_findings:
            # Sort by severity
            sev_rank = {s: i for i, s in enumerate(SEVERITY_ORDER)}
            all_findings.sort(key=lambda f: sev_rank.get(f.get("severity", "low"), 99))

            lines.append("| Severity | Issue | Recommendation |")
            lines.append("|----------|-------|----------------|")
            for finding in all_findings[:15]:
                sev = finding.get("severity", "low")
                msg = finding.get("message", "").replace("|", "\\|")[:80]
                rec = finding.get("recommendation", "").replace("|", "\\|")[:80]
                lines.append(f"| {_severity_icon(sev)} {sev.capitalize()} | {msg} | {rec} |")
            lines.append("")

            if len(all_findings) > 15:
                lines.append(f"*... and {len(all_findings) - 15} more findings*")
                lines.append("")
        else:
            lines.append("*No issues found in this category.*")
            lines.append("")

    # Action Plan
    lines.append("---")
    lines.append("")
    lines.append("## Action Plan")
    lines.append("")

    # Collect ALL findings across all modules
    all_module_findings: list[dict[str, Any]] = []
    modules_dir = audit_dir / "modules"
    if modules_dir.exists():
        for mod_file in modules_dir.glob("*.json"):
            mod_data = _load_json(mod_file)
            if mod_data and isinstance(mod_data, dict):
                for f in mod_data.get("findings", []):
                    f["_module"] = mod_file.stem
                    all_module_findings.append(f)

    sev_rank = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    all_module_findings.sort(key=lambda f: sev_rank.get(f.get("severity", "low"), 99))

    for severity in SEVERITY_ORDER:
        sev_findings = [f for f in all_module_findings if f.get("severity") == severity]
        if not sev_findings:
            continue

        priority_label = {
            "critical": "Critical (Fix Immediately)",
            "high": "High (Fix Within 1 Week)",
            "medium": "Medium (Fix Within 1 Month)",
            "low": "Low (Backlog)",
        }

        lines.append(f"### {_severity_icon(severity)} {priority_label.get(severity, severity)}")
        lines.append("")
        for f in sev_findings[:10]:
            msg = f.get("message", "")
            rec = f.get("recommendation", "")
            mod = f.get("_module", "")
            lines.append(f"- **{msg}** [{mod}]")
            if rec:
                lines.append(f"  - *Fix*: {rec}")
        lines.append("")

    # Methodology
    lines.append("---")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append("| Category | Weight |")
    lines.append("|----------|--------|")
    lines.append("| Technical SEO | 22% |")
    lines.append("| Content Quality | 23% |")
    lines.append("| On-Page SEO | 20% |")
    lines.append("| Schema / Structured Data | 10% |")
    lines.append("| Performance (CWV) | 10% |")
    lines.append("| AI Search Readiness | 10% |")
    lines.append("| Images | 5% |")
    lines.append("")
    lines.append(f"*Generated by xuanran-seo-blog-writer website-audit • {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Markdown audit report")
    parser.add_argument("audit_dir", help="Path to audit output directory")
    parser.add_argument("--output", "-o", help="Output file (default: {audit_dir}/FULL-AUDIT-REPORT.md)")
    parser.add_argument("--json", "-j", action="store_true", help="JSON metadata output")

    args = parser.parse_args()
    audit_dir = Path(args.audit_dir).resolve()

    if not audit_dir.is_dir():
        print(f"Error: Not a directory: {audit_dir}", file=sys.stderr)
        sys.exit(1)

    report = generate_report(audit_dir)

    output_path = Path(args.output) if args.output else audit_dir / "FULL-AUDIT-REPORT.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"Report written to: {output_path}", file=sys.stderr)

    if args.json:
        print(json.dumps({
            "output_path": str(output_path),
            "line_count": report.count("\n") + 1,
            "char_count": len(report),
        }, indent=2))


if __name__ == "__main__":
    main()
