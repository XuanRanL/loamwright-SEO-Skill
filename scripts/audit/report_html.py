"""Self-contained HTML report generator for SEO Health Audits.

Produces a single, client-facing HTML file with all CSS inlined (no external
dependencies, no JavaScript required). Reads structured audit output from
scores.json, modules/*.json, crawl-results.json, and business-type.json.

Usage:
    python -m scripts.audit.report_html audit_output/ -o report.html
    python -m scripts.audit.report_html audit_output/ --title "Custom Audit Title"
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "technical_seo": "Technical SEO",
    "content_quality": "Content Quality",
    "on_page_seo": "On-Page SEO",
    "schema_structured_data": "Schema & Structured Data",
    "performance_cwv": "Performance & Core Web Vitals",
    "ai_search_readiness": "AI Search Readiness",
    "images": "Images & Visual Assets",
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

SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

EFFORT_MAP: dict[str, str] = {
    "critical": "Immediate",
    "high": "1-2 days",
    "medium": "3-5 days",
    "low": "1-2 weeks",
}

# Module file (stem) -> list of categories it contributes to.
# Duplicated from audit_scorer.py to avoid import coupling; keep in sync.
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
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any] | None:
    """Safely load a JSON file, returning None on failure."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return None


def load_audit_data(audit_dir: Path) -> dict[str, Any]:
    """Load all audit data from the output directory."""
    data: dict[str, Any] = {
        "scores": None,
        "modules": {},
        "crawl_results": None,
        "business_type": None,
    }

    # scores.json
    scores_path = audit_dir / "scores.json"
    data["scores"] = _load_json(scores_path)

    # modules/*.json
    modules_dir = audit_dir / "modules"
    if modules_dir.is_dir():
        for module_file in sorted(modules_dir.glob("*.json")):
            module_data = _load_json(module_file)
            if module_data is not None:
                data["modules"][module_file.stem] = module_data

    # crawl-results.json
    crawl_path = audit_dir / "crawl-results.json"
    data["crawl_results"] = _load_json(crawl_path)

    # business-type.json
    btype_path = audit_dir / "business-type.json"
    data["business_type"] = _load_json(btype_path)

    return data


# ---------------------------------------------------------------------------
# Score utilities
# ---------------------------------------------------------------------------


def score_badge(score: float) -> tuple[str, str, str]:
    """Return (label, bg_color, text_color) for a score."""
    rounded = round(score)
    if rounded >= 90:
        return "Excellent", "#2d6a4f", "#ffffff"
    elif rounded >= 70:
        return "Good", "#1e3a5f", "#ffffff"
    elif rounded >= 50:
        return "Needs Improvement", "#d4740e", "#ffffff"
    else:
        return "Poor", "#c53030", "#ffffff"


def score_bar_color(score: float) -> str:
    """Return progress bar fill color based on score."""
    rounded = round(score)
    if rounded >= 90:
        return "#2d6a4f"
    elif rounded >= 70:
        return "#1e3a5f"
    elif rounded >= 50:
        return "#d4740e"
    else:
        return "#c53030"


def severity_priority_label(severity: str) -> str:
    """Map severity to display priority label."""
    labels = {
        "critical": "Critical",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    }
    return labels.get(severity, "Low")


# ---------------------------------------------------------------------------
# HTML generation helpers
# ---------------------------------------------------------------------------


def _e(text: str) -> str:
    """HTML-escape user-supplied text."""
    return html.escape(str(text), quote=True)


def _build_css() -> str:
    """Generate the complete embedded CSS."""
    return """
/* === Base Reset & Typography === */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 15px; line-height: 1.7; -webkit-text-size-adjust: 100%; }
body {
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
    background: #faf9f7;
    color: #2d3748;
    padding: 0;
    margin: 0;
}

/* === Layout === */
.container {
    max-width: 1100px;
    margin: 0 auto;
    padding: 0 24px 60px;
}

/* === Cover Section === */
.cover {
    background: linear-gradient(135deg, #1e3a5f 0%, #0f1f33 100%);
    color: #ffffff;
    text-align: center;
    padding: 60px 24px 50px;
    margin-bottom: 40px;
}
.cover h1 {
    font-size: 2.2rem;
    font-weight: 700;
    margin-bottom: 8px;
    letter-spacing: -0.5px;
}
.cover .subtitle {
    font-size: 1.1rem;
    opacity: 0.85;
    margin-bottom: 24px;
}
.cover .overall-score {
    display: inline-block;
    font-size: 3.5rem;
    font-weight: 800;
    color: #b8860b;
    line-height: 1;
}
.cover .score-label {
    display: block;
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-top: 8px;
    opacity: 0.7;
}
.cover .badge {
    display: inline-block;
    margin-top: 16px;
    padding: 6px 20px;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* === Score Banner Grid === */
.score-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 16px;
    margin-bottom: 40px;
}
.score-card {
    background: #ffffff;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    border-top: 4px solid #e2e8f0;
    transition: box-shadow 0.2s;
}
.score-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.10);
}
.score-card .card-title {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #718096;
    margin-bottom: 8px;
    font-weight: 600;
}
.score-card .card-score {
    font-size: 2.5rem;
    font-weight: 800;
    color: #1e3a5f;
    line-height: 1;
    margin-bottom: 6px;
}
.score-card .card-badge {
    font-size: 0.75rem;
    font-weight: 600;
    display: inline-block;
    padding: 2px 10px;
    border-radius: 10px;
    margin-bottom: 12px;
}
.progress-bar {
    width: 100%;
    height: 8px;
    background: #e2e8f0;
    border-radius: 4px;
    overflow: hidden;
}
.progress-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.4s ease;
}
.weight-label {
    font-size: 0.7rem;
    color: #a0aec0;
    margin-top: 6px;
}

/* === Section Headers === */
.section-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: 2px solid #e2e8f0;
}
.section-header h2 {
    font-size: 1.4rem;
    font-weight: 700;
    color: #1e3a5f;
    margin: 0;
}
.section-badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 700;
}

/* === Executive Summary === */
.exec-summary {
    background: #ffffff;
    border-radius: 12px;
    padding: 32px;
    margin-bottom: 40px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.exec-summary h2 {
    font-size: 1.3rem;
    color: #1e3a5f;
    margin-bottom: 20px;
    font-weight: 700;
}
.exec-meta {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}
.meta-item {
    text-align: center;
    padding: 12px;
    background: #f7fafc;
    border-radius: 8px;
}
.meta-item .meta-value {
    font-size: 1.4rem;
    font-weight: 700;
    color: #1e3a5f;
}
.meta-item .meta-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #718096;
    margin-top: 2px;
}
.exec-columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
}
.exec-columns h3 {
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 12px;
    font-weight: 700;
}
.exec-columns .critical-heading { color: #c53030; }
.exec-columns .wins-heading { color: #2d6a4f; }
.exec-list {
    list-style: none;
    padding: 0;
}
.exec-list li {
    padding: 8px 12px;
    margin-bottom: 6px;
    border-radius: 6px;
    font-size: 0.88rem;
    line-height: 1.5;
}
.exec-list.critical-list li {
    background: #fef2f2;
    border-left: 3px solid #c53030;
}
.exec-list.wins-list li {
    background: #f0fff4;
    border-left: 3px solid #2d6a4f;
}

/* === Category Sections === */
.category-section {
    background: #ffffff;
    border-radius: 12px;
    padding: 28px 32px;
    margin-bottom: 28px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

/* === Findings === */
.findings-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0 8px;
}
.finding {
    border-left: 4px solid #e2e8f0;
    background: #f7fafc;
    border-radius: 6px;
}
.finding td {
    padding: 12px 16px;
    vertical-align: top;
}
.finding.critical { border-left: 4px solid #c53030; background: #fef2f2; }
.finding.high { border-left: 4px solid #d4740e; background: #fffbeb; }
.finding.medium { border-left: 4px solid #b8860b; background: #fefce8; }
.finding.low { border-left: 4px solid #4a5568; background: #f7fafc; }
.finding .severity-tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #ffffff;
    white-space: nowrap;
}
.severity-tag.critical { background: #c53030; }
.severity-tag.high { background: #d4740e; }
.severity-tag.medium { background: #b8860b; }
.severity-tag.low { background: #4a5568; }
.finding .finding-message {
    font-weight: 600;
    color: #2d3748;
    margin-bottom: 4px;
}
.finding .finding-evidence {
    font-size: 0.82rem;
    color: #718096;
    font-style: italic;
}
.finding .finding-recommendation {
    font-size: 0.85rem;
    color: #2d6a4f;
    margin-top: 4px;
}

/* === Action Plan Table === */
.action-plan-section {
    background: #ffffff;
    border-radius: 12px;
    padding: 28px 32px;
    margin-bottom: 28px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.action-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
}
.action-table thead th {
    text-align: left;
    padding: 10px 12px;
    background: #1e3a5f;
    color: #ffffff;
    font-weight: 600;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.action-table thead th:first-child { border-radius: 8px 0 0 0; }
.action-table thead th:last-child { border-radius: 0 8px 0 0; }
.action-table tbody td {
    padding: 10px 12px;
    border-bottom: 1px solid #e2e8f0;
    vertical-align: top;
}
.action-table tbody tr:last-child td { border-bottom: none; }
.action-table .priority-cell {
    white-space: nowrap;
    font-weight: 700;
    font-size: 0.78rem;
    text-transform: uppercase;
}
.priority-critical { color: #c53030; }
.priority-high { color: #d4740e; }
.priority-medium { color: #b8860b; }
.priority-low { color: #4a5568; }

/* === Methodology Footer === */
.methodology {
    background: #ffffff;
    border-radius: 12px;
    padding: 24px 32px;
    margin-bottom: 40px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    font-size: 0.82rem;
    color: #718096;
}
.methodology h2 {
    font-size: 1.1rem;
    color: #1e3a5f;
    margin-bottom: 16px;
    font-weight: 700;
}
.methodology table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 16px;
}
.methodology th, .methodology td {
    padding: 6px 12px;
    text-align: left;
    border-bottom: 1px solid #e2e8f0;
}
.methodology th {
    font-weight: 600;
    color: #4a5568;
}
.methodology .footer-note {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid #e2e8f0;
    font-size: 0.78rem;
}

/* === No Findings Notice === */
.no-findings {
    text-align: center;
    padding: 20px;
    color: #a0aec0;
    font-style: italic;
}

/* === Responsive === */
@media (max-width: 768px) {
    .container { padding: 0 16px 40px; }
    .cover { padding: 40px 16px 36px; }
    .cover h1 { font-size: 1.6rem; }
    .cover .overall-score { font-size: 2.8rem; }
    .score-grid { grid-template-columns: 1fr; }
    .exec-columns { grid-template-columns: 1fr; }
    .exec-summary, .category-section, .action-plan-section, .methodology { padding: 20px 16px; }
    .action-table { font-size: 0.8rem; }
    .action-table thead th, .action-table tbody td { padding: 8px 6px; }
}

/* === Print styles === */
@media print {
    body { background: #fff; }
    .cover { break-after: page; }
    .category-section { break-inside: avoid; }
    .score-card { break-inside: avoid; }
}
"""


# ---------------------------------------------------------------------------
# HTML section builders
# ---------------------------------------------------------------------------


def _build_cover(
    title: str,
    domain: str,
    audit_date: str,
    overall_score: float,
    badge_label: str,
    badge_bg: str,
    badge_text: str,
) -> str:
    """Build the cover/hero section."""
    return f"""<div class="cover">
    <h1>{_e(title)}</h1>
    <div class="subtitle">{_e(domain)} &mdash; {_e(audit_date)}</div>
    <div class="overall-score">{round(overall_score)}</div>
    <span class="score-label">Overall SEO Health Score</span>
    <div>
        <span class="badge" style="background:{badge_bg};color:{badge_text};">{_e(badge_label)}</span>
    </div>
</div>"""


def _build_score_grid(categories: dict[str, Any]) -> str:
    """Build the category score card grid."""
    cards: list[str] = []

    for cat_key in CATEGORY_WEIGHTS:
        display_name = CATEGORY_DISPLAY_NAMES.get(cat_key, cat_key.replace("_", " ").title())
        cat_data = categories.get(cat_key)

        if cat_data is None:
            score_val = 0.0
            weight_val = CATEGORY_WEIGHTS[cat_key]
        else:
            score_val = float(cat_data.get("score", 0))
            weight_val = float(cat_data.get("weight", CATEGORY_WEIGHTS[cat_key]))

        label, bg, text_col = score_badge(score_val)
        bar_color = score_bar_color(score_val)
        border_color = bar_color

        card = f"""<div class="score-card" style="border-top-color:{border_color};">
    <div class="card-title">{_e(display_name)}</div>
    <div class="card-score" style="color:{border_color};">{round(score_val)}</div>
    <span class="card-badge" style="background:{bg};color:{text_col};">{_e(label)}</span>
    <div class="progress-bar">
        <div class="progress-fill" style="width:{min(100, max(0, round(score_val)))}%;background:{bar_color};"></div>
    </div>
    <div class="weight-label">Weight: {weight_val:.0%}</div>
</div>"""
        cards.append(card)

    return f"""<div class="score-grid">
{"".join(cards)}
</div>"""


def _build_executive_summary(
    scores: dict[str, Any],
    business_type: dict[str, Any] | None,
    pages_crawled: int,
) -> str:
    """Build the executive summary section."""
    overall = round(scores.get("overall_score", 0))
    badge_label = scores.get("badge", "N/A")
    badge_label_e, badge_bg, badge_text = score_badge(float(overall))

    btype = "General"
    if business_type:
        btype = business_type.get("type", business_type.get("business_type", "General"))

    findings_summary = scores.get("findings_summary", {})
    total_findings = sum(findings_summary.values()) if findings_summary else 0
    critical_count = findings_summary.get("critical", 0)

    # Top critical issues
    top_critical = scores.get("top_critical", [])[:5]
    critical_items = ""
    if top_critical:
        items = []
        for f in top_critical:
            msg = f.get("message", "")
            items.append(f'<li>{_e(msg)}</li>')
        critical_items = "\n".join(items)
    else:
        critical_items = '<li style="color:#a0aec0;font-style:italic;">No critical issues found</li>'

    # Top quick wins
    top_wins = scores.get("top_quick_wins", [])[:5]
    wins_items = ""
    if top_wins:
        items = []
        for f in top_wins:
            rec = f.get("recommendation", f.get("message", ""))
            items.append(f'<li>{_e(rec)}</li>')
        wins_items = "\n".join(items)
    else:
        wins_items = '<li style="color:#a0aec0;font-style:italic;">No quick wins identified</li>'

    return f"""<div class="exec-summary">
    <h2>Executive Summary</h2>
    <div class="exec-meta">
        <div class="meta-item">
            <div class="meta-value" style="color:{badge_bg};">{overall}/100</div>
            <div class="meta-label">Overall Score</div>
        </div>
        <div class="meta-item">
            <div class="meta-value">{_e(str(btype).title())}</div>
            <div class="meta-label">Business Type</div>
        </div>
        <div class="meta-item">
            <div class="meta-value">{pages_crawled}</div>
            <div class="meta-label">Pages Crawled</div>
        </div>
        <div class="meta-item">
            <div class="meta-value">{total_findings}</div>
            <div class="meta-label">Total Findings</div>
        </div>
        <div class="meta-item">
            <div class="meta-value" style="color:#c53030;">{critical_count}</div>
            <div class="meta-label">Critical Issues</div>
        </div>
    </div>
    <div class="exec-columns">
        <div>
            <h3 class="critical-heading">Top Critical Issues</h3>
            <ul class="exec-list critical-list">
                {critical_items}
            </ul>
        </div>
        <div>
            <h3 class="wins-heading">Quick Wins</h3>
            <ul class="exec-list wins-list">
                {wins_items}
            </ul>
        </div>
    </div>
</div>"""


def _build_category_section(
    cat_key: str,
    cat_score: float,
    findings: list[dict[str, Any]],
) -> str:
    """Build a per-category detail section."""
    display_name = CATEGORY_DISPLAY_NAMES.get(cat_key, cat_key.replace("_", " ").title())
    label, bg, text_col = score_badge(cat_score)

    # Build findings rows
    rows: list[str] = []
    sorted_findings = sorted(
        findings, key=lambda f: SEVERITY_ORDER.get(f.get("severity", "low"), 99)
    )

    for f in sorted_findings:
        severity = f.get("severity", "low")
        message = f.get("message", "")
        evidence = f.get("evidence", "")
        recommendation = f.get("recommendation", "")

        evidence_html = ""
        if evidence:
            evidence_html = f'<div class="finding-evidence">{_e(evidence)}</div>'

        rec_html = ""
        if recommendation:
            rec_html = f'<div class="finding-recommendation">&rarr; {_e(recommendation)}</div>'

        row = f"""<tr class="finding {_e(severity)}">
    <td style="width:90px;"><span class="severity-tag {_e(severity)}">{_e(severity_priority_label(severity))}</span></td>
    <td>
        <div class="finding-message">{_e(message)}</div>
        {evidence_html}
        {rec_html}
    </td>
</tr>"""
        rows.append(row)

    findings_html = ""
    if rows:
        findings_html = f"""<table class="findings-table">
    <tbody>
        {"".join(rows)}
    </tbody>
</table>"""
    else:
        findings_html = '<div class="no-findings">No findings in this category.</div>'

    return f"""<div class="category-section">
    <div class="section-header">
        <h2>{_e(display_name)}</h2>
        <span class="section-badge" style="background:{bg};color:{text_col};">{round(cat_score)} &mdash; {_e(label)}</span>
    </div>
    {findings_html}
</div>"""


def _build_action_plan(all_findings: list[dict[str, Any]]) -> str:
    """Build the prioritized action plan table."""
    sorted_findings = sorted(
        all_findings, key=lambda f: SEVERITY_ORDER.get(f.get("severity", "low"), 99)
    )

    # Limit to top 30 actionable items (ones with recommendations)
    actionable = [f for f in sorted_findings if f.get("recommendation")][:30]

    if not actionable:
        return ""

    rows: list[str] = []
    for f in actionable:
        severity = f.get("severity", "low")
        priority_cls = f"priority-{_e(severity)}"
        message = f.get("message", "")
        recommendation = f.get("recommendation", "")
        effort = EFFORT_MAP.get(severity, "TBD")
        source = f.get("source_module", "")

        row = f"""<tr>
    <td class="priority-cell {priority_cls}">{_e(severity_priority_label(severity))}</td>
    <td>{_e(message)}</td>
    <td>{_e(recommendation)}</td>
    <td style="white-space:nowrap;">{_e(effort)}</td>
    <td style="color:#a0aec0;font-size:0.78rem;">{_e(source)}</td>
</tr>"""
        rows.append(row)

    return f"""<div class="action-plan-section">
    <div class="section-header">
        <h2>Action Plan</h2>
    </div>
    <table class="action-table">
        <thead>
            <tr>
                <th>Priority</th>
                <th>Issue</th>
                <th>Recommendation</th>
                <th>Effort</th>
                <th>Source</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows)}
        </tbody>
    </table>
</div>"""


def _build_methodology(timestamp: str) -> str:
    """Build the methodology footer."""
    weight_rows: list[str] = []
    for cat_key, weight in CATEGORY_WEIGHTS.items():
        display_name = CATEGORY_DISPLAY_NAMES.get(cat_key, cat_key.replace("_", " ").title())
        weight_rows.append(
            f"<tr><td>{_e(display_name)}</td><td>{weight:.0%}</td></tr>"
        )

    return f"""<div class="methodology">
    <h2>Methodology</h2>
    <p style="margin-bottom:12px;">
        This audit evaluates 7 SEO health dimensions using automated crawling, content analysis,
        structured data validation, and performance measurement. Each category is scored 0-100
        and weighted to produce the overall health score.
    </p>
    <table>
        <thead><tr><th>Category</th><th>Weight</th></tr></thead>
        <tbody>{"".join(weight_rows)}</tbody>
    </table>
    <p><strong>Data Sources:</strong> Site crawl (Patchright/Chromium), Google PageSpeed Insights API,
    schema.org validation, content NLP analysis, backlink profile sampling.</p>
    <p><strong>Scoring:</strong> 90-100 Excellent | 70-89 Good | 50-69 Needs Improvement | 0-49 Poor</p>
    <div class="footer-note">
        Report generated: {_e(timestamp)} &bull; Engine: Xuanran SEO Audit v3.4 &bull;
        This report is a point-in-time snapshot and should be re-run periodically.
    </div>
</div>"""


# ---------------------------------------------------------------------------
# Main report assembly
# ---------------------------------------------------------------------------


def generate_report(
    audit_dir: Path,
    output_path: Path | None = None,
    title: str | None = None,
) -> str:
    """Generate the complete HTML report and optionally write to file.

    Args:
        audit_dir: Path to the audit output directory.
        output_path: If provided, write the HTML to this file.
        title: Custom report title override.

    Returns:
        The generated HTML string.
    """
    data = load_audit_data(audit_dir)
    scores = data["scores"] or {}
    modules = data["modules"] or {}
    crawl_results = data["crawl_results"]
    business_type = data["business_type"]

    # Derive domain
    domain = "Unknown Domain"
    # crawl_results may be a list (flat page array) or dict (with metadata)
    if isinstance(crawl_results, list):
        # Flat list of page dicts — extract domain from first URL
        if crawl_results:
            first_url = crawl_results[0].get("url", "")
            domain = urlparse(first_url).netloc or "Unknown Domain"
    elif isinstance(crawl_results, dict):
        if crawl_results.get("domain"):
            domain = crawl_results["domain"]
        elif crawl_results.get("start_url"):
            domain = urlparse(crawl_results["start_url"]).netloc or "Unknown Domain"
    if domain == "Unknown Domain" and scores.get("metadata", {}).get("domain"):
        domain = scores["metadata"]["domain"]

    # Derive page count
    pages_crawled = 0
    if isinstance(crawl_results, list):
        pages_crawled = len(crawl_results)
    elif isinstance(crawl_results, dict):
        pages_crawled = crawl_results.get("pages_crawled", 0)
        if not pages_crawled and crawl_results.get("pages"):
            pages_crawled = len(crawl_results["pages"])

    # Timestamps
    audit_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Title
    if not title:
        title = f"SEO Health Audit: {domain}"

    # Overall score
    overall_score = float(scores.get("overall_score", 0))
    badge_label, badge_bg, badge_text = score_badge(overall_score)

    # Categories
    categories = scores.get("categories", {})

    # Collect all findings grouped by category
    category_findings: dict[str, list[dict[str, Any]]] = {
        cat: [] for cat in CATEGORY_WEIGHTS
    }
    all_findings: list[dict[str, Any]] = []

    for module_name, module_data in modules.items():
        for finding in module_data.get("findings", []):
            finding_with_source = dict(finding)
            finding_with_source.setdefault("source_module", module_name)
            all_findings.append(finding_with_source)

            # Map to category
            cat = finding.get("category", "")
            if cat in category_findings:
                category_findings[cat].append(finding_with_source)
            else:
                # Infer category from the module-category map
                mapped_cats = MODULE_CATEGORY_MAP.get(module_name, [])
                for mc in mapped_cats:
                    if mc in category_findings:
                        category_findings[mc].append(finding_with_source)
                        break
                else:
                    # Fallback: assign to first available category
                    if mapped_cats:
                        first_cat = mapped_cats[0]
                        if first_cat not in category_findings:
                            category_findings[first_cat] = []
                        category_findings[first_cat].append(finding_with_source)

    # Build HTML sections
    css = _build_css()
    cover = _build_cover(title, domain, audit_date, overall_score, badge_label, badge_bg, badge_text)
    score_grid = _build_score_grid(categories)
    exec_summary = _build_executive_summary(scores, business_type, pages_crawled)

    # Per-category sections
    category_sections: list[str] = []
    for cat_key in CATEGORY_WEIGHTS:
        cat_data = categories.get(cat_key)
        cat_score = float(cat_data["score"]) if cat_data else 0.0
        findings = category_findings.get(cat_key, [])
        section = _build_category_section(cat_key, cat_score, findings)
        category_sections.append(section)

    action_plan = _build_action_plan(all_findings)
    methodology = _build_methodology(timestamp)

    # Assemble full HTML
    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_e(title)}</title>
    <style>{css}</style>
</head>
<body>
{cover}
<div class="container">
{score_grid}
{exec_summary}
{"".join(category_sections)}
{action_plan}
{methodology}
</div>
</body>
</html>"""

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_html, encoding="utf-8")

    return report_html


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="report_html",
        description=(
            "Generate a self-contained, professional HTML report from SEO audit results. "
            "Reads scores.json, modules/*.json, crawl-results.json, and business-type.json "
            "from the specified audit output directory."
        ),
    )
    parser.add_argument(
        "audit_dir",
        type=Path,
        help="Path to the audit output directory.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=(
            "Output HTML file path. "
            "Default: {audit_dir}/FULL-AUDIT-REPORT.html"
        ),
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help='Custom report title. Default: "SEO Health Audit: {domain}"',
    )
    parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output JSON metadata (path, file size) instead of status message",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    audit_dir: Path = args.audit_dir.resolve()
    if not audit_dir.is_dir():
        print(f"Error: '{audit_dir}' is not a directory.", file=sys.stderr)
        return 1

    # Validate that at least scores.json or modules/ exists
    scores_exists = (audit_dir / "scores.json").is_file()
    modules_exists = (audit_dir / "modules").is_dir()
    if not scores_exists and not modules_exists:
        print(
            f"Error: Neither 'scores.json' nor 'modules/' found in '{audit_dir}'. "
            "Is this a valid audit output directory?",
            file=sys.stderr,
        )
        return 1

    # Determine output path
    output_path: Path = args.output if args.output else audit_dir / "FULL-AUDIT-REPORT.html"
    output_path = output_path.resolve()

    # Generate
    generate_report(audit_dir, output_path=output_path, title=args.title)

    if args.json:
        import json as _json
        print(_json.dumps({
            "output_path": str(output_path),
            "file_size_bytes": output_path.stat().st_size,
        }, indent=2))
    else:
        print(f"Report generated: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
