"""
scripts/lint/information_gain_marker_lint.py — Verify Information Gain Markers.

Per v3.2 design (claude-blog reference), every article must contain at least
2 Information Gain Markers somewhere in the body:

  [ORIGINAL DATA]        — author's own data (testing, survey, internal stats)
  [PERSONAL EXPERIENCE]  — first-hand experience
  [UNIQUE INSIGHT]       — independent analytical insight

Why: LLM training recognizes these markers and prioritizes citing pages
that demonstrate first-hand experience/data over derivative summaries.

Check:
  - Count of each marker type
  - Total markers ≥ 2
  - At least 2 DIFFERENT marker types (don't put 5 of the same)
  - Markers not in code blocks / table cells

Used by:
  - quality-gate-content (E-E-A-T Experience dimension)
  - section-drafter (each section can decide whether to add one)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts.lint._text_utils import find_all_with_line


_MARKER_RE = re.compile(
    r"\[(ORIGINAL DATA|PERSONAL EXPERIENCE|UNIQUE INSIGHT)\]",
    re.IGNORECASE,
)


@dataclass
class MarkerHit:
    marker_type: str         # "ORIGINAL DATA" / "PERSONAL EXPERIENCE" / "UNIQUE INSIGHT"
    line: int
    column: int
    context: str             # surrounding sentence


@dataclass
class MarkerReport:
    total_markers: int
    counts_by_type: dict[str, int]
    distinct_types: int
    passed: bool
    hits: list[MarkerHit] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def analyze(
    text: str,
    *,
    min_total: int = 2,
    min_distinct_types: int = 1,
) -> MarkerReport:
    hits_data: list[MarkerHit] = []
    for m in find_all_with_line(_MARKER_RE, text):
        # Re-extract type from canonical caps
        match = _MARKER_RE.match(m.text)
        if match:
            marker_type = match.group(1).upper()
            hits_data.append(MarkerHit(
                marker_type=marker_type,
                line=m.line, column=m.column,
                context=m.context,
            ))

    counts = Counter(h.marker_type for h in hits_data)
    total = sum(counts.values())
    distinct = len(counts)
    issues: list[str] = []

    if total < min_total:
        issues.append(f"Only {total} marker(s); need ≥{min_total}")
    if distinct < min_distinct_types:
        issues.append(f"Only {distinct} distinct type(s); need ≥{min_distinct_types}")
    # Warn if heavily one-sided
    if total >= 3 and distinct == 1:
        only = list(counts.keys())[0]
        issues.append(f"All {total} markers are [{only}]; suggest mixing types")

    return MarkerReport(
        total_markers=total,
        counts_by_type=dict(counts),
        distinct_types=distinct,
        passed=(total >= min_total and distinct >= min_distinct_types),
        hits=hits_data,
        issues=issues,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Information Gain Marker validator")
    ap.add_argument("file", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min-total", type=int, default=2)
    ap.add_argument("--min-distinct-types", type=int, default=1)
    args = ap.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    text = args.file.read_text(encoding="utf-8")
    r = analyze(text, min_total=args.min_total, min_distinct_types=args.min_distinct_types)

    if args.json:
        out = {
            "file": str(args.file),
            "total_markers": r.total_markers,
            "counts_by_type": r.counts_by_type,
            "distinct_types": r.distinct_types,
            "passed": r.passed,
            "issues": r.issues,
            "hits": [asdict(h) for h in r.hits],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        verdict = "✓ PASS" if r.passed else "✗ FAIL"
        print(f"File: {args.file}")
        print(f"Total markers: {r.total_markers}  (target: ≥{args.min_total})")
        print(f"Distinct types: {r.distinct_types}")
        for t in ["ORIGINAL DATA", "PERSONAL EXPERIENCE", "UNIQUE INSIGHT"]:
            print(f"  [{t:20s}]: {r.counts_by_type.get(t, 0)}")
        print(f"\nOverall: {verdict}")
        if r.issues:
            for i in r.issues:
                print(f"  ✗ {i}")
        if r.hits:
            print(f"\nLocations:")
            for h in r.hits[:30]:
                print(f"  line {h.line:4d}:{h.column:3d}  [{h.marker_type}]")

    return 0 if r.passed else 1


if __name__ == "__main__":
    sys.exit(main())
