"""
scripts/lint/citation_capsule_lint.py — Per-H2 Citation Capsule presence + length check.

Per Princeton GEO research (claude-blog reference data), each H2 should contain
ONE 40-60 word self-contained AI-quotable block. This drives:
  - +28-41% AI citation rate (ChatGPT/Perplexity)
  - +115% authority-source attribution

A Citation Capsule:
  - One paragraph (no list/table/heading)
  - 40-60 words
  - Self-contained (doesn't depend on surrounding context)
  - Contains a specific factual claim with a quantifier (number/year/percent)
  - Reads naturally; not labeled "[CITATION CAPSULE]"

How we detect:
  For each H2 section:
    1. Split into paragraphs
    2. For each paragraph, check word count in [35, 70] (tolerance ±5 on 40-60)
    3. Of those, look for one with at least 1 specific numeric/year claim
    4. If found, that's the Capsule — pass
    5. Otherwise — fail

Self-containment heuristic:
  - Doesn't start with pronouns referring back ("This", "These", "It", "They")
  - Doesn't end with cliff-hanger continuation ("as we'll see", "more on this below")
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts._core import heading_anchor

from scripts._core.component_headings import classify_heading
from scripts.lint._text_utils import iter_h2_sections, iter_paragraphs, strip_markdown


@dataclass
class CapsuleFinding:
    h2_text: str
    h2_line: int
    has_capsule: bool
    candidate_count: int
    best_candidate_words: int | None
    capsule_text: str | None
    issues: list[str] = field(default_factory=list)


@dataclass
class CapsuleReport:
    total_h2s: int
    h2s_with_capsule: int
    coverage_pct: float
    findings: list[CapsuleFinding] = field(default_factory=list)
    passed: bool = False


_NUMERIC_CLAIM_RE = re.compile(
    r"\b(?:\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?)\s*(?:%|percent|x|times|million|billion|hours|days|years|months|weeks|degrees|kg|lbs|miles|km)?",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_PRONOUN_START_RE = re.compile(r"^\s*(this|these|those|they|it|that)\b", re.IGNORECASE)
_CONTINUATION_END_RE = re.compile(r"\b(as we['']?ll see|more on this|see below|to be discussed|see (?:the )?next section)\b[.\s]*$", re.IGNORECASE)


def _has_specific_claim(text: str) -> bool:
    """Does the paragraph contain at least one number or year?"""
    return bool(_NUMERIC_CLAIM_RE.search(text) or _YEAR_RE.search(text))


def _is_self_contained(text: str) -> bool:
    """Heuristic: doesn't start with anaphoric pronoun, doesn't promise more later."""
    if _PRONOUN_START_RE.match(text):
        return False
    if _CONTINUATION_END_RE.search(text):
        return False
    return True


def _is_capsule_candidate(text: str) -> tuple[bool, int]:
    """Check if a paragraph could be a Citation Capsule.

    Returns (is_candidate, word_count).
    """
    # Skip list-like / table-like content
    if re.search(r"^\s*[-*+]\s|^\s*\d+\.\s|^\s*\|", text, re.MULTILINE):
        return False, 0
    # Skip headings
    if re.match(r"^#{1,6}\s", text):
        return False, 0
    plain = strip_markdown(text)
    w = len(plain.split())
    return (35 <= w <= 70), w


# Structural H2s legitimately have NO citation capsule. They must be excluded
# from BOTH the per-section check AND the coverage denominator, otherwise the
# coverage_pct is misleading (e.g. 6/12 = 50% reads as "half uncovered" when in
# fact all 6 CONTENT sections are covered and the other 6 are structural). An
# honest denominator is content-H2s only — this also stops capsule-builder runs
# from trying to "hit 100%" by adding redundant capsules to Abstract/FAQ/Conclusion.
_STRUCTURAL_EXACT = {
    "references", "sources", "bibliography", "table of contents", "toc",
    "key takeaways", "tl;dr", "tldr", "abstract",
    "faq", "frequently asked questions", "common questions", "further reading",
    # v3.31 visual-design blocks (2026-07-01): stat grids / glossary cards / the
    # At-a-Glance table are structural components, not content H2s — they carry no
    # 40-60w citation capsule by design. Counting them deflated coverage_pct on
    # every designed article (observed 63.6% / 40% on the 2026-07-01 batch while
    # every real content H2 was covered).
    "by the numbers", "glossary", "at a glance",
}
_STRUCTURAL_PREFIX = ("conclusion", "final verdict", "the bottom line")


def _is_structural_h2(h2_text: str) -> bool:
    """True if an H2 is a structural section that should not carry a capsule.

    Normalizes a leading numeric prefix ('14. ') and a trailing ': subtitle'
    (e.g. 'Conclusion: Engineer the Room' → 'conclusion') before matching.
    """
    n = h2_text.strip()
    n = heading_anchor.ANCHOR_SUFFIX_RE.sub("", n)   # strip trailing {#anchor-id}
    n = re.sub(r"^\s*\d+\.\s*", "", n).lower()  # strip leading numeric prefix
    n = n.split(":", 1)[0].strip()              # drop ': subtitle'
    if n in _STRUCTURAL_EXACT:
        return True
    return any(n.startswith(p) for p in _STRUCTURAL_PREFIX)


# Visual-component H2s that are BLOCKS INSIDE their parent content section, not
# sections of their own. Classified via scripts/_core/component_headings (the
# single source of truth for heading→component, incl. topic-scoped variants like
# "By the Numbers: 2026 Costs"). Deliberately EXCLUDES the tldr id ("the bottom
# line" is a conclusion-class H2, a real boundary) and the cta ids (the CTA
# module sits after the conclusion and must never lend a content section its
# capsule).
_MERGE_INTO_PARENT_COMPONENT_IDS = frozenset({"stat_grid", "glossary", "at_a_glance", "checklist"})


def _is_mergeable_component_h2(h2_text: str) -> bool:
    return classify_heading(h2_text) in _MERGE_INTO_PARENT_COMPONENT_IDS


def _merged_sections(text: str) -> list[tuple[str, int, str]]:
    """H2 sections with visual-component sections folded into their parent.

    v3.38.3 root cure (2026-07-09 batch): writers legitimately render a
    stat_grid as `## By the Numbers` and often place the section's citation
    capsule AFTER that block. iter_h2_sections treats the component heading as a
    section boundary, so the capsule was attributed to the (structurally
    skipped) component section and the parent content H2 reported "no capsule"
    — false-failing gold-filament §4/§7 and painting-pla §8/§9 and forcing
    redundant capsule insertions that the independent reviewer then flagged as
    duplication. Folding component bodies back into the nearest preceding
    section makes a capsule on EITHER side of the component block count for the
    parent, matching how a reader (and an AI extractor) sees the page.
    """
    merged: list[tuple[str, int, list[str]]] = []
    for s in iter_h2_sections(text):
        if merged and _is_mergeable_component_h2(s.h2_text):
            merged[-1][2].append(s.body)
            continue
        merged.append((s.h2_text, s.start_line, [s.body]))
    return [(h2, line, "\n\n".join(parts)) for h2, line, parts in merged]


def analyze(text: str) -> CapsuleReport:
    h2s = _merged_sections(text)
    findings: list[CapsuleFinding] = []
    found_count = 0

    for h2_text, start_line, body in h2s:
        # Skip structural sections (boilerplate that never carries a capsule)
        if _is_structural_h2(h2_text):
            continue

        finding = CapsuleFinding(
            h2_text=h2_text, h2_line=start_line,
            has_capsule=False, candidate_count=0,
            best_candidate_words=None, capsule_text=None,
        )
        paragraphs = list(iter_paragraphs(body))
        candidates: list[tuple[str, int]] = []
        for para in paragraphs:
            is_cand, w = _is_capsule_candidate(para)
            if is_cand:
                candidates.append((para, w))

        finding.candidate_count = len(candidates)

        # Filter: must have specific claim
        with_claims = [(p, w) for p, w in candidates if _has_specific_claim(p)]
        if not with_claims:
            finding.issues.append("No paragraph in [35,70] words has a specific number/year claim")
            findings.append(finding)
            continue

        # Filter: must be self-contained
        self_contained = [(p, w) for p, w in with_claims if _is_self_contained(p)]
        if not self_contained:
            finding.issues.append("Candidate paragraphs not self-contained (anaphoric or cliff-hanger)")
            findings.append(finding)
            continue

        # Pick best (closest to 50 words)
        best = min(self_contained, key=lambda pw: abs(pw[1] - 50))
        finding.has_capsule = True
        finding.best_candidate_words = best[1]
        finding.capsule_text = best[0][:300]
        found_count += 1
        findings.append(finding)

    total = len([h2_text for h2_text, _line, _body in h2s if not _is_structural_h2(h2_text)])
    coverage = (found_count / total * 100) if total > 0 else 0

    return CapsuleReport(
        total_h2s=total,
        h2s_with_capsule=found_count,
        coverage_pct=round(coverage, 1),
        findings=findings,
        passed=(coverage >= 80.0),   # at least 80% of content H2s have a capsule
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Citation Capsule presence checker")
    ap.add_argument("file", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", type=Path, default=None,
                    help="Write the JSON report to this path (the citation-capsule-builder "
                         "stage evidence artifact the orchestrator requires).")
    ap.add_argument("--target-coverage", type=float, default=80.0)
    args = ap.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    text = args.file.read_text(encoding="utf-8")
    r = analyze(text)
    r.passed = r.coverage_pct >= args.target_coverage

    out = {
        "file": str(args.file),
        "_generated_by": "citation-capsule-lint",
        "total_h2s": r.total_h2s,
        "h2s_with_capsule": r.h2s_with_capsule,
        "coverage_pct": r.coverage_pct,
        "target_coverage_pct": args.target_coverage,
        "passed": r.passed,
        "findings": [asdict(f) for f in r.findings],
    }
    if args.out:
        args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        verdict = "✓ PASS" if r.passed else "✗ FAIL"
        print(f"File: {args.file}")
        print(f"H2 sections (content): {r.total_h2s}")
        print(f"H2s with Citation Capsule: {r.h2s_with_capsule}")
        print(f"Coverage: {r.coverage_pct}% (target: {args.target_coverage}%)  {verdict}")
        print()
        for f in r.findings:
            icon = "✓" if f.has_capsule else "✗"
            print(f"  {icon} line {f.h2_line}  '{f.h2_text}'  ({f.candidate_count} candidates)")
            if f.has_capsule:
                print(f"      Capsule ({f.best_candidate_words}w): {f.capsule_text[:120]}...")
            else:
                for i in f.issues:
                    print(f"      issue: {i}")

    return 0 if r.passed else 1


if __name__ == "__main__":
    sys.exit(main())
