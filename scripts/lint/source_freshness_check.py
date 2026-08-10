"""scripts/lint/source_freshness_check.py — Per-topic source-age check.

Compares cited source years against topic-specific freshness thresholds.

Used by `agents/fact-checker.md` during Phase 4 fact-checking.

Topic detection: keyword-based heuristic (override via --topic).

CLI:
    python -m scripts.lint.source_freshness_check --input draft.md --topic tech --json
    python -m scripts.lint.source_freshness_check --input draft.md  # auto-detect topic
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


# Topic → (max_age_years, hard_fail_age_years)
FRESHNESS_THRESHOLDS: dict[str, tuple[int, int]] = {
    "tech":             (2, 4),     # AI / software / SaaS
    "ai":               (2, 3),     # AI / ML / LLM
    "seo":              (2, 4),     # SEO + marketing
    "marketing":        (2, 4),
    "news":             (1, 1),     # Current events (max 12 months)
    "finance":          (1, 2),     # Markets, earnings
    "crypto":           (1, 2),     # ≤6mo ideal but 1y default
    "medical":          (5, 10),    # Health, research
    "pharma":           (3, 8),
    "mental-health":    (5, 10),
    "legal":            (5, 10),    # Mostly stable; some regulatory churn
    "demographics":     (5, 10),
    "industry-size":    (2, 4),     # Annual reports drive
    "education":        (5, 10),
    "historical":       (999, 999), # Unlimited
    "culture":          (10, 999),
    "real-estate":      (1, 3),
    "travel":           (2, 4),
    "food":             (5, 10),
    "climate":          (3, 8),
    "default":          (3, 6),
}

# Keyword → topic mapping for auto-detection
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "tech":      ["chatgpt", "gpt-4", "gpt-5", "llm", "claude", "anthropic", "openai", "saas", "software", "api", "developer"],
    "ai":        ["ai marketing", "ai writing", "ai content", "generative ai", "machine learning", "neural network"],
    "seo":       ["seo", "ranking", "google search", "serp", "keyword research", "backlink", "search engine"],
    "marketing": ["marketing automation", "lead gen", "conversion rate", "ctr", "email marketing", "social media"],
    "news":      ["breaking", "today", "just announced", "this week", "current events"],
    "finance":   ["stock", "earnings", "revenue", "investment", "investor", "ipo", "fed", "interest rate"],
    "crypto":    ["bitcoin", "ethereum", "blockchain", "cryptocurrency", "defi", "nft", "web3"],
    "medical":   ["health", "patient", "treatment", "diagnosis", "clinical", "fda", "trial"],
    "real-estate": ["mortgage", "real estate", "housing market", "property", "rent"],
    "travel":    ["hotel", "airfare", "destination", "tourism", "vacation"],
    "climate":   ["climate change", "emissions", "renewable", "carbon", "ipcc"],
}


@dataclass
class FreshnessIssue:
    claim_text: str
    source_year: int
    age_years: int
    severity: str           # fresh | stale | fail
    recommended_action: str
    citation_text: str = ""


@dataclass
class FreshnessReport:
    topic: str
    detected_via: str       # "auto" | "user"
    max_age_years: int
    hard_fail_age_years: int
    current_year: int
    sources_analyzed: int = 0
    fresh_count: int = 0
    stale_count: int = 0
    fail_count: int = 0
    sources: list[FreshnessIssue] = field(default_factory=list)
    overall_pass: bool = True
    summary: str = ""


# Match (Author, YYYY) or (YYYY) inline citations
INLINE_CITE_RE = re.compile(r"\(([^()]*?(?:19|20)\d{2}[^()]*?)\)")

# Match "in 2024" / "as of 2024"
YEAR_PROSE_RE = re.compile(r"\b(?:in|as\s+of|by|since|since|during|from)\s+(?:Q\d\s+)?(20[12]\d)\b", re.IGNORECASE)

# Reference list entry year (APA-style)
REFERENCE_YEAR_RE = re.compile(r"(?:^|\.\s*)((19|20)\d{2})(?:[a-z]?)\.\s")

# Topic auto-detection
def _detect_topic(text: str) -> tuple[str, str]:
    """Auto-detect topic from text. Returns (topic, detected_via)."""
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[topic] = scores.get(topic, 0) + 1
    if not scores:
        return "default", "auto-default"
    best = max(scores.items(), key=lambda x: x[1])
    return best[0], "auto"


def _extract_years(text: str) -> list[tuple[int, str]]:
    """Extract all cited years + their surrounding context."""
    results: list[tuple[int, str]] = []

    # 1. Inline citations like "(HubSpot, 2024)"
    for m in INLINE_CITE_RE.finditer(text):
        cite_text = m.group(1)
        year_match = re.search(r"\b(20\d{2})\b", cite_text)
        if year_match:
            year = int(year_match.group(1))
            # Context: the sentence containing this citation
            start = max(0, m.start() - 200)
            end = min(len(text), m.end() + 50)
            context = text[start:end].strip()
            results.append((year, context))

    # 2. Prose like "in 2024" or "as of 2024"
    for m in YEAR_PROSE_RE.finditer(text):
        year = int(m.group(1))
        start = max(0, m.start() - 100)
        end = min(len(text), m.end() + 100)
        context = text[start:end].strip()
        results.append((year, context))

    return results


def check_freshness(
    text: str, *,
    topic: str = "default",
    current_year: int | None = None,
) -> FreshnessReport:
    """Check source freshness against topic-specific thresholds."""
    if current_year is None:
        current_year = datetime.now().year

    detected_via = "user"
    if topic == "auto":
        topic, detected_via = _detect_topic(text)
    elif topic == "default":
        # See if we can do better than default
        better_topic, det_via = _detect_topic(text)
        if det_via == "auto":
            topic = better_topic
            detected_via = "auto"

    max_age, hard_fail = FRESHNESS_THRESHOLDS.get(topic, FRESHNESS_THRESHOLDS["default"])

    years = _extract_years(text)

    issues: list[FreshnessIssue] = []
    for year, context in years:
        age = current_year - year
        if age < 0:
            # Future date — odd, but skip
            continue
        if age <= max_age:
            severity = "fresh"
            action = ""
        elif age <= hard_fail:
            severity = "stale"
            action = f"Consider replacing — {age}y old, threshold is {max_age}y for {topic}"
        else:
            severity = "fail"
            action = f"REQUIRED replacement — {age}y old, way beyond {hard_fail}y hard limit for {topic}"

        # Try to extract the actual claim/citation text (short)
        claim = context[:120] + "..." if len(context) > 120 else context

        issues.append(FreshnessIssue(
            claim_text=claim,
            source_year=year,
            age_years=age,
            severity=severity,
            recommended_action=action,
            citation_text=claim,
        ))

    fresh = sum(1 for i in issues if i.severity == "fresh")
    stale = sum(1 for i in issues if i.severity == "stale")
    fail = sum(1 for i in issues if i.severity == "fail")

    overall_pass = fail == 0  # stale is warning, not fail

    summary = (f"Topic: {topic} (max: {max_age}y, fail: {hard_fail}y) — "
               f"{fresh} fresh, {stale} stale, {fail} fail")
    if not overall_pass:
        summary += f" → REQUIRES replacement of {fail} sources"

    # Only show stale/fail in the report
    surface_issues = [i for i in issues if i.severity != "fresh"]

    return FreshnessReport(
        topic=topic,
        detected_via=detected_via,
        max_age_years=max_age,
        hard_fail_age_years=hard_fail,
        current_year=current_year,
        sources_analyzed=len(issues),
        fresh_count=fresh,
        stale_count=stale,
        fail_count=fail,
        sources=surface_issues,
        overall_pass=overall_pass,
        summary=summary,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-topic source freshness check")
    ap.add_argument("--input", type=Path)
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--topic", default="auto", choices=list(FRESHNESS_THRESHOLDS) + ["auto"])
    ap.add_argument("--current-year", type=int)
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

    report = check_freshness(text, topic=args.topic, current_year=args.current_year)

    if args.json:
        print(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    else:
        icon = "✓" if report.overall_pass else "✗"
        print(f"{icon} {report.summary}")
        if report.sources:
            print()
            for s in report.sources[:10]:
                sev_icon = {"stale": "⚠", "fail": "🔴"}.get(s.severity, "•")
                print(f"  {sev_icon} [{s.severity}] year={s.source_year} age={s.age_years}y")
                print(f"        {s.recommended_action}")
                print(f"        ...{s.claim_text[:100]}...")
    return 0 if report.overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
