"""
scripts/lint/em_dash_audit.py — U+2014 zero-tolerance auditor.

Em-dashes (—, U+2014) are the **single highest-ROI AI tell**:
  - ChatGPT/Claude default to them; humans rarely do
  - One regex catches them; no false positives if used properly
  - Trivial to fix

Per v3.2 spec, em-dash count == 0 is a hard quality gate requirement.

Replacement strategy:
  - Most em-dashes → comma OR parentheses OR full stop
  - "X — Y" → "X, Y" or "X. Y" (if separating clauses)
  - "X—Y—Z" → "X (Y) Z" or rewrite

Also flags (informationally):
  - U+2013 EN DASH — softer AI tell but still flagged
  - Triple-hyphen --- used as em-dash substitute

CLI:
  python -m scripts.lint.em_dash_audit draft.md
  python -m scripts.lint.em_dash_audit draft.md --json
  python -m scripts.lint.em_dash_audit draft.md --include-en-dash
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.lint._text_utils import Match, find_all_with_line


EM_DASH = re.compile(r"—")     # U+2014
EN_DASH = re.compile(r"–")     # U+2013
HYPHEN_TRIPLE = re.compile(r"(?<![-])---(?![-])")  # exactly 3, not hr ---

# Matches a markdown "## References" (any heading depth, optional trailing
# {#anchor} / punctuation) heading. Mirrors render_lint.py's
# detect_L12_em_dash_in_prose scope guard (_REFERENCES_H2_RE there operates on
# rendered HTML; this operates on raw markdown, which is what this module's
# callers — ai_slop_score.py chief among them — read).
_REFERENCES_H2_RE = re.compile(r"^#{1,6}\s*References\b", re.IGNORECASE | re.MULTILINE)


def _scope_excluding_references(text: str) -> str:
    """Trim `text` to the portion BEFORE the "## References" heading.

    Added 2026-07-17: verbatim external text (an APA-7 source's own published
    title, e.g. a Statistics Canada or Government of Canada publication whose
    real title contains an em-dash) is not "our prose" and must not be flagged
    — exactly the reasoning render_lint.py's L12 already codifies ("everything
    from the References H2 onward is excluded ... APA titles of real papers may
    legitimately contain em-dashes"). Before this fix, `em_dash_count()` scanned
    the WHOLE file and had no such exemption, so a fully clean draft with zero
    em-dashes in body prose could still hard-fail the ai_slop quality gate
    (`passes = score < threshold and em_dashes == 0`) purely because a real,
    correctly-quoted citation title contains one — the two independent
    "no em-dash" implementations had drifted apart in scope (same disease as
    the render_lint L1 / verify_post check 06 drift documented in project
    memory). This function is the single shared fix point for every caller of
    `lint()` / `em_dash_count()` in this module.
    """
    m = _REFERENCES_H2_RE.search(text)
    return text[: m.start()] if m else text


@dataclass
class DashHit:
    char: str        # — or – or ---
    char_name: str   # "em-dash" / "en-dash" / "triple-hyphen"
    line: int
    column: int
    context: str


def lint(
    text: str,
    *,
    include_en_dash: bool = False,
    include_triple: bool = True,
    include_references: bool = False,
) -> list[DashHit]:
    """Find dash-like characters.

    By default (`include_references=False`) excludes the "## References"
    heading onward — see `_scope_excluding_references`. Pass
    `include_references=True` to scan the raw whole-file text (diagnostic use
    only; do not use this to gate a publish decision).
    """
    scope = text if include_references else _scope_excluding_references(text)
    hits: list[DashHit] = []

    for m in find_all_with_line(EM_DASH, scope):
        hits.append(DashHit("—", "em-dash (U+2014)",
                            m.line, m.column, m.context))

    if include_en_dash:
        for m in find_all_with_line(EN_DASH, scope):
            hits.append(DashHit("–", "en-dash (U+2013)",
                                m.line, m.column, m.context))

    if include_triple:
        for m in find_all_with_line(HYPHEN_TRIPLE, scope):
            # Skip if it's a markdown horizontal rule (--- on its own line)
            if m.context.strip() == "---":
                continue
            hits.append(DashHit("---", "triple-hyphen",
                                m.line, m.column, m.context))

    hits.sort(key=lambda h: (h.line, h.column))
    return hits


def em_dash_count(text: str, *, include_references: bool = False) -> int:
    """Used by AI-Slop and quality-gate-ai-slop. Counts ONLY U+2014.

    By default excludes the References section onward — see
    `_scope_excluding_references`. This is the enforced (gate-relevant) count.
    """
    scope = text if include_references else _scope_excluding_references(text)
    return len(EM_DASH.findall(scope))


def main() -> int:
    ap = argparse.ArgumentParser(description="Em-dash auditor (zero-tolerance)")
    ap.add_argument("file", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--include-en-dash", action="store_true",
                    help="Also flag U+2013 en-dashes")
    ap.add_argument("--no-triple", action="store_true",
                    help="Don't flag '---' triple-hyphen")
    ap.add_argument("--fix", action="store_true",
                    help="Auto-replace em-dashes with comma (caution: not always correct)")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    text = args.file.read_text(encoding="utf-8")

    if args.fix:
        # Conservative auto-fix: em-dash → comma
        new = text.replace("—", ", ")
        if new != text:
            args.file.write_text(new, encoding="utf-8")
            print(f"Replaced {text.count('—')} em-dashes with comma.")
        else:
            print("No em-dashes found.")
        return 0

    hits = lint(
        text,
        include_en_dash=args.include_en_dash,
        include_triple=not args.no_triple,
    )

    if args.json:
        out = {
            "file": str(args.file),
            "em_dash_count": em_dash_count(text),
            "em_dash_count_including_references": em_dash_count(text, include_references=True),
            "total_hits": len(hits),
            "passed": em_dash_count(text) == 0,
            "hits": [asdict(h) for h in hits],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        em = em_dash_count(text)
        em_total = em_dash_count(text, include_references=True)
        print(f"File: {args.file}")
        print(f"Em-dashes (U+2014), body prose (References-exempt): {em}  {'✓ PASS' if em == 0 else '✗ FAIL'}")
        if em_total != em:
            print(f"  (raw whole-file count including References: {em_total} — verbatim citation "
                  f"titles are not flagged, matching render_lint L12)")
        if hits:
            print(f"Total dash-like hits: {len(hits)}")
            for h in hits[:30]:
                print(f"  line {h.line:4d}:{h.column:3d}  {h.char_name}  …{h.context[:80]}…")
            if len(hits) > 30:
                print(f"  ... and {len(hits) - 30} more")

    return 0 if em_dash_count(text) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
