"""scripts/lint/local_uniqueness_check.py — Sterling Sky 80/20 enforcement.

PURPOSE
─────────
For articles with state.brief.local_mode=true, verifies that ≥20% of body
content is genuinely unique-per-locality (not "doorway page" — same template
with city name swapped). Per Google's 2025-12-10 doorway-page spam policy
update + Sterling Sky's reverse-engineered 80/20 rule.

DESIGN
──────
Single-Jaccard similarity is too crude (validation research P1: "Keep ≥20%
as one input among four, not THE threshold"). This lint scores 4 independent
factors, then combines them into a composite uniqueness score:

  F1 — Local entity density
        Count of distinct named entities specific to the location_anchor
        (utility programs, city names, neighborhoods, state agencies, local
        trade associations, climate descriptors, local case-study subjects).
        Higher is better.

  F2 — Factual claim density
        Count of state/city-specific quantitative facts (kWh prices, rebate
        amounts, population numbers, cultivator counts, etc.) — distinguishes
        genuine local content from templated platitudes.

  F3 — Sentence similarity to sibling articles (1 - Jaccard)
        Tokenized sentence overlap with already-published articles in the
        same business_category that target a DIFFERENT location. High overlap
        = doorway pattern. Composite penalty.

  F4 — Lexical diversity (TTR — type-token ratio)
        Vocabulary richness relative to the article's length. Templated
        doorway pages have low TTR because they reuse the same phrases.

COMPOSITE SCORE (0-100):
    score = 0.35 * F1_norm + 0.30 * F2_norm + 0.25 * F3_norm + 0.10 * F4_norm

THRESHOLDS:
    score ≥ 70 → PASS (genuine local content)
    50 ≤ score < 70 → WARN (acceptable; consider strengthening)
    score < 50 → FAIL (doorway-pattern risk; repair required)

Also enforces 4 Sterling Sky CATEGORIES (per references/local/industry-to-schema-mapping.md):
  - At least 1 program/incentive mention (utility rebate, tax credit, license)
  - At least 1 case study / customer reference / local press citation
  - At least 1 landmark / neighborhood / regional-language signal
  - At least 1 pricing / logistics / market-data point

Missing ANY category → automatic FAIL regardless of composite score.

CLI
───
    python -m scripts.lint.local_uniqueness_check --draft path/to/draft.md
    python -m scripts.lint.local_uniqueness_check --workspace TASK_ID
    Add --siblings DIR to compare against published sibling articles.

EXIT
────
    0 = pass / informational
    1 = fail (composite < 50 OR missing category)
    2 = bad arguments
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


# ─── Category keyword signals (industry-agnostic; broad heuristic) ──

# Words that are STRONG indicators of each category in body text.
# This is intentionally generic — works for plumber, dentist, solar, cannabis,
# any vertical — because these patterns describe genuine local content
# regardless of industry.

_PROGRAM_INCENTIVE_PATTERNS = [
    r"\brebate\b", r"\bincentive\b", r"\btax\s+credit\b",
    r"\butility\b.*(\bprogram\b|\bdiscount\b|\brefund\b)",
    r"\bgovernment\b.*\bprogram\b", r"\bsubsid(?:y|ies)\b",
    r"\bgrant\b", r"\blicense\b", r"\bpermit\b", r"\bcertification\b",
    r"\bcompliance\b", r"\bregulation\b", r"\bcode\b",
    r"\$\d+(?:\.\d+)?(?:\s*(?:per|/)\s*(?:kWh|W|fixture|sq\s*ft))?",  # specific dollar amounts
    r"\b\d+\s*%\s*(?:rebate|discount|refund|credit|cashback)\b",
]

_CASE_STUDY_PATTERNS = [
    r"\bcase\s+study\b", r"\bcustomer\s+(?:in|from)\b",
    r"\bfacility\s+in\b", r"\boperator\s+in\b",
    r"\b[A-Z][a-z]+\s+(?:Co\.|Inc\.|LLC|LLP)\b",  # company names (caps + suffix)
    r"\baccording\s+to\b.*\b(?:report|study|data|analysis)\b",
    r"\bone\s+(?:client|customer|operator|installer)\b",
    r"\binterview\b", r"\btestimonial\b", r"\breview(?:ed|s)?\s+by\b",
    r"\b(?:Reuters|Bloomberg|AP|Forbes|TechCrunch|Wired)\b",  # press
    # Local press
    r"\b(?:Tribune|Herald|Globe|Times|Post|Journal|Gazette|Chronicle|Daily|Press|Inquirer)\b",
]

_LANDMARK_PATTERNS = [
    # Highway / corridor references
    r"\bI-\d+\b",  # I-25, I-95
    r"\b(?:Highway|Route|Hwy)\s+\d+\b",
    r"\bcorridor\b",
    # Neighborhood / district indicators
    r"\b(?:downtown|uptown|midtown|metro)\b",
    r"\b\w+(?:\s+\w+)?\s+District\b",
    r"\b\w+(?:\s+\w+)?\s+Heights\b",
    r"\b\w+(?:\s+\w+)?\s+(?:Park|Square|Plaza)\b",
    # Local region words
    r"\bsuburb(?:s|an)\b", r"\bmetropolitan\b", r"\bcounty\b",
    r"\b(?:north|south|east|west)\s+(?:side|metro|county)\b",
    # Common landmark nouns
    r"\b(?:stadium|university|college|hospital|airport|port|harbor|bay)\b",
]

_PRICING_LOGISTICS_PATTERNS = [
    r"\b(?:average|median)\s+(?:price|cost|salary|income|rent)\b",
    r"\b\d+\s+to\s+\d+\s+days?\b",  # lead times
    r"\bship(?:ping|ped|s)\b", r"\bfreight\b", r"\bdelivery\s+time\b",
    r"\bwarehouse\b", r"\bfulfillment\b", r"\bdistribution\b",
    r"\bkWh\b", r"\b\$/sq\s*ft\b", r"\bgallon\b", r"\bper\s+capita\b",
    r"\bpopulation\b", r"\bdemographic", r"\bmedian\s+income\b",
    r"\bgrowth\s+rate\b", r"\bmarket\s+size\b",
    # specific local-data verbs
    r"\baverage\b.*\$\d+", r"\b\d+%\s+of\s+\w+s?\b",
]


# ─── Stop words for lexical diversity (TTR) ───────────────────────

_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "this", "that",
    "these", "those", "it", "its", "they", "them", "their", "we", "us",
    "our", "you", "your", "i", "me", "my", "he", "she", "him", "her", "his",
}


# ─── Result type ─────────────────────────────────────────────────

@dataclass
class FactorScore:
    name: str
    raw_value: float          # Raw count or ratio
    normalized: float          # 0-100
    detail: str
    examples: list[str] = field(default_factory=list)


@dataclass
class UniquenessReport:
    passed: bool
    composite_score: float
    verdict: str               # PASS / WARN / FAIL
    factors: dict              # name → FactorScore
    categories_satisfied: dict  # name → bool
    missing_categories: list
    word_count: int
    source_path: str


# ─── Helpers ─────────────────────────────────────────────────────

def _strip_frontmatter_and_code(text: str) -> str:
    # Drop YAML frontmatter
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    # Strip code blocks (fenced + indented)
    text = re.sub(r"```[^\n]*\n.*?\n```", "", text, flags=re.DOTALL)
    # Strip inline code
    text = re.sub(r"`[^`]+`", "", text)
    # Strip markdown image syntax
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    # Strip raw HTML tags but keep their text content
    text = re.sub(r"<[^>]+>", "", text)
    return text


def _count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _match_patterns(text: str, patterns: list[str]) -> list[str]:
    """Find all matches across patterns; dedupe; return sample (max 5)."""
    found: list[str] = []
    seen: set[str] = set()
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            s = m.group(0).strip().lower()
            if s not in seen:
                seen.add(s)
                found.append(m.group(0).strip())
    return found


def _factor1_entity_density(body: str, location_anchor: dict | None) -> FactorScore:
    """F1 — count distinct local-entity-style references."""
    examples = []
    # Direct location mentions
    if location_anchor:
        canon = location_anchor.get("canonical", "")
        name_full = location_anchor.get("name_full", "")
        for ref in [canon, name_full, location_anchor.get("containing_state", "")]:
            if not ref:
                continue
            count = len(re.findall(rf"\b{re.escape(ref)}\b", body, re.IGNORECASE))
            if count:
                examples.append(f"{ref} ×{count}")

    # Capitalized phrases that look like entities (e.g. "Xcel Energy", "Boston Globe")
    # Match: 2+ capitalized words in a row, OR 1 cap word followed by Inc./LLC/Co./etc.
    entity_pattern = re.compile(
        r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+|"
        r"[A-Z][a-z]+\s+(?:Inc|LLC|Co|Group|Corporation|Energy|Hospital|University|Park))\b"
    )
    entities = set()
    for m in entity_pattern.finditer(body):
        # Skip if the entire phrase is just the location anchor repeated
        e = m.group(0)
        if location_anchor and e == location_anchor.get("name_full"):
            continue
        entities.add(e)

    raw = len(entities)
    # Normalize: 8+ unique entities = 100; 0 entities = 0; linear in between
    normalized = min(100, raw * 12.5)

    return FactorScore(
        name="F1_entity_density",
        raw_value=raw,
        normalized=normalized,
        detail=f"{raw} distinct named-entity-style phrases detected",
        examples=list(entities)[:5],
    )


def _factor2_factual_claim_density(body: str) -> FactorScore:
    """F2 — quantitative facts: dollar amounts, percentages, ratios, dates."""
    # Specific dollar amounts (any pattern with $X)
    dollar_pattern = re.compile(r"\$\d+(?:[\.,]\d+)?(?:\s*(?:/|per)\s*\w+)?")
    # Percentages with context
    pct_pattern = re.compile(r"\b\d+(?:\.\d+)?\s*%\b")
    # Numerical ranges
    range_pattern = re.compile(r"\b\d+\s*[-–to]+\s*\d+\b")
    # Years
    year_pattern = re.compile(r"\b(?:19|20)\d{2}\b")
    # kWh / W / sq ft / per capita
    unit_pattern = re.compile(r"\b\d+(?:\.\d+)?\s*(?:kWh|W|sq\s*ft|µmol|per\s*capita|miles?|hours?)\b", re.IGNORECASE)

    counts = {
        "dollar_amounts": len(dollar_pattern.findall(body)),
        "percentages": len(pct_pattern.findall(body)),
        "numerical_ranges": len(range_pattern.findall(body)),
        "years": len(year_pattern.findall(body)),
        "unit_measures": len(unit_pattern.findall(body)),
    }
    total = sum(counts.values())

    # Sample examples
    examples = []
    for pat, label in [(dollar_pattern, "$"), (pct_pattern, "%"), (unit_pattern, "unit")]:
        m = pat.search(body)
        if m:
            examples.append(f"{label}: {m.group(0)}")

    # Normalize: 15+ quantitative facts = 100; <3 = 0
    normalized = max(0, min(100, (total - 2) * 7.5))

    return FactorScore(
        name="F2_factual_claim_density",
        raw_value=total,
        normalized=normalized,
        detail=f"{total} quantitative facts: {counts}",
        examples=examples,
    )


def _tokenize_sentences(body: str) -> list[set[str]]:
    """Return a list of sentence-token-sets for Jaccard comparison."""
    body_clean = re.sub(r"\s+", " ", body).strip()
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", body_clean)
    out = []
    for s in sentences:
        toks = re.findall(r"\b\w+\b", s.lower())
        # Drop stop words
        toks = [t for t in toks if t not in _STOP_WORDS and len(t) >= 3]
        if len(toks) >= 4:  # Skip very short sentences
            out.append(set(toks))
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _factor3_sibling_similarity(body: str, sibling_drafts: list[Path]) -> FactorScore:
    """F3 — sentence-overlap with sibling articles. Lower overlap = more unique = higher score."""
    if not sibling_drafts:
        return FactorScore(
            name="F3_sibling_similarity",
            raw_value=0.0,
            normalized=70.0,  # Neutral score when no siblings — can't penalize
            detail="no sibling articles available for comparison (neutral score)",
        )

    own_sentences = _tokenize_sentences(body)
    if not own_sentences:
        return FactorScore(
            name="F3_sibling_similarity",
            raw_value=0.0,
            normalized=50.0,
            detail="article has no scorable sentences",
        )

    # For each own sentence, find the max Jaccard with any sibling sentence
    max_similarities = []
    for sib in sibling_drafts:
        try:
            sib_text = _strip_frontmatter_and_code(sib.read_text(encoding="utf-8"))
        except Exception:
            continue
        sib_sentences = _tokenize_sentences(sib_text)
        if not sib_sentences:
            continue
        for own_s in own_sentences:
            best = max((_jaccard(own_s, ss) for ss in sib_sentences), default=0.0)
            max_similarities.append(best)

    if not max_similarities:
        return FactorScore(
            name="F3_sibling_similarity",
            raw_value=0.0,
            normalized=70.0,
            detail="sibling files unreadable (neutral score)",
        )

    avg_max_sim = sum(max_similarities) / len(max_similarities)
    # avg_max_sim: 0.0 = totally unique vs siblings; 1.0 = identical
    # Composite score: 1 - avg = uniqueness
    uniqueness = 1.0 - avg_max_sim
    # Normalize: uniqueness=0.7+ → 100; uniqueness=0.5 → 50; uniqueness<0.4 → 0
    normalized = max(0, min(100, (uniqueness - 0.4) * 333))

    return FactorScore(
        name="F3_sibling_similarity",
        raw_value=avg_max_sim,
        normalized=normalized,
        detail=(
            f"avg max sentence-Jaccard vs {len(sibling_drafts)} siblings: "
            f"{avg_max_sim:.3f} (uniqueness={uniqueness:.3f})"
        ),
    )


def _factor4_lexical_diversity(body: str) -> FactorScore:
    """F4 — type-token ratio (vocabulary richness)."""
    tokens = [t.lower() for t in re.findall(r"\b\w+\b", body) if len(t) >= 3]
    # Remove very common stop words (TTR is meaningful on content words)
    tokens = [t for t in tokens if t not in _STOP_WORDS]
    if not tokens:
        return FactorScore(name="F4_lexical_diversity", raw_value=0.0, normalized=0.0, detail="empty body")

    ttr = len(set(tokens)) / len(tokens)
    # Articles of 2000-3000 words typically have TTR 0.30-0.45 for human-written
    # Doorway/templated content shows TTR < 0.25
    # Normalize: TTR=0.45+ → 100; 0.30 → 50; <0.20 → 0
    normalized = max(0, min(100, (ttr - 0.20) * 400))

    return FactorScore(
        name="F4_lexical_diversity",
        raw_value=ttr,
        normalized=normalized,
        detail=f"TTR={ttr:.3f} ({len(set(tokens))} unique / {len(tokens)} content tokens)",
    )


# ─── Category check (Sterling Sky 4 categories) ──────────────────

def _check_categories(body: str) -> tuple[dict, list]:
    """Check whether at least one example from each of 4 categories is present."""
    categories: dict[str, dict] = {}
    for name, patterns in [
        ("programs_incentives", _PROGRAM_INCENTIVE_PATTERNS),
        ("case_studies", _CASE_STUDY_PATTERNS),
        ("landmarks_regional", _LANDMARK_PATTERNS),
        ("pricing_logistics", _PRICING_LOGISTICS_PATTERNS),
    ]:
        matches = _match_patterns(body, patterns)
        categories[name] = {
            "satisfied": len(matches) >= 1,
            "match_count": len(matches),
            "examples": matches[:3],
        }
    missing = [k for k, v in categories.items() if not v["satisfied"]]
    return categories, missing


# ─── Main entry ──────────────────────────────────────────────────

def lint_uniqueness(
    draft_path: Path,
    *,
    sibling_drafts: list[Path] | None = None,
    location_anchor: dict | None = None,
) -> UniquenessReport:
    raw = draft_path.read_text(encoding="utf-8")
    body = _strip_frontmatter_and_code(raw)

    f1 = _factor1_entity_density(body, location_anchor)
    f2 = _factor2_factual_claim_density(body)
    f3 = _factor3_sibling_similarity(body, sibling_drafts or [])
    f4 = _factor4_lexical_diversity(body)

    composite = (
        0.35 * f1.normalized +
        0.30 * f2.normalized +
        0.25 * f3.normalized +
        0.10 * f4.normalized
    )

    categories, missing = _check_categories(body)
    word_count = _count_words(body)

    # Verdict
    if missing:
        verdict = "FAIL"
        passed = False
    elif composite < 50:
        verdict = "FAIL"
        passed = False
    elif composite < 70:
        verdict = "WARN"
        passed = True  # passes with warning
    else:
        verdict = "PASS"
        passed = True

    return UniquenessReport(
        passed=passed,
        composite_score=round(composite, 1),
        verdict=verdict,
        factors={f.name: asdict(f) for f in [f1, f2, f3, f4]},
        categories_satisfied={k: v["satisfied"] for k, v in categories.items()},
        missing_categories=missing,
        word_count=word_count,
        source_path=str(draft_path),
    )


def _load_location_anchor(workspace_dir: Path) -> dict | None:
    """Read state.json::brief.location_anchor (when available)."""
    state_path = workspace_dir / "state.json"
    if not state_path.exists():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return state.get("brief", {}).get("location_anchor")
    except Exception:
        return None


def main() -> int:
    p = argparse.ArgumentParser(description="Sterling Sky 80/20 uniqueness lint")
    p.add_argument("--draft", help="path to draft.md")
    p.add_argument("--workspace", help="task workspace dir (auto-finds draft.md + state.json)")
    p.add_argument(
        "--siblings",
        help="directory containing sibling published drafts (.md) for similarity comparison",
    )
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", help="write JSON report to this path")
    args = p.parse_args()

    if args.workspace:
        ws = Path(args.workspace)
        if not ws.exists() and not ws.is_absolute() and len(ws.parts) == 1:
            # Bare task-id (the canonical runner invocation `--workspace {task_id}`):
            # resolve under the plugin's memory/workspace like every sibling lint
            # (visual_density_check). 2026-07-01: the SKILL docs prescribed the
            # task-id form but this CLI only accepted a raw dir path — even a
            # diligent operator following the docs crashed with exit 2.
            ws = Path(__file__).resolve().parent.parent.parent / "memory" / "workspace" / args.workspace
        draft_path = ws / "draft.md"
        location_anchor = _load_location_anchor(ws)
    elif args.draft:
        draft_path = Path(args.draft)
        location_anchor = None
    else:
        print("--draft or --workspace required", file=sys.stderr)
        return 2

    if not draft_path.exists():
        print(f"draft not found: {draft_path}", file=sys.stderr)
        return 2

    siblings = []
    if args.siblings:
        sib_dir = Path(args.siblings)
        if sib_dir.is_dir():
            siblings = sorted(sib_dir.rglob("*.md"))

    report = lint_uniqueness(draft_path, sibling_drafts=siblings, location_anchor=location_anchor)

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(f"local_uniqueness_check: {report.verdict} (composite={report.composite_score})")
        print(f"  word_count: {report.word_count}")
        for fname, f in report.factors.items():
            print(f"  {fname}: {f['normalized']:.1f}/100 — {f['detail']}")
            if f.get("examples"):
                print(f"      examples: {f['examples'][:3]}")
        print(f"  categories:")
        for cname, ok in report.categories_satisfied.items():
            sym = "✓" if ok else "✗"
            print(f"    {sym} {cname}")
        if report.missing_categories:
            print(f"  MISSING: {report.missing_categories}")

    if args.out:
        Path(args.out).write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
