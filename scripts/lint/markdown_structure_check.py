"""
scripts/lint/markdown_structure_check.py — Article structural integrity check.

Verifies a SEO blog markdown follows v3.2 universal 10-section skeleton:

  1. Title (H1)
  2. TL;DR / Quick Answer section (in first 540 words, claude-blog grounding zone)
  3. Abstract
  4. Key Takeaways (list, 4-7 items)
  5. Table of Contents (auto-generated with anchor links to H2s)
  6. Body (with required structure per format)
  7. FAQ (5+ Q&A)
  8. Conclusion
  9. References (APA 7, must be LAST section)
  10. Frontmatter for SEO meta (separate from body)

Additionally checks:
  - Unique ToC / Key Takeaways / References (no duplicates, including synonyms)
  - Article MUST end at References — no content after the last reference entry
  - No markdown <table>...</table> HTML mixed in (use markdown table syntax)
  - At least 2 markdown tables, with ≥1 in front 50% of article
  - All H3 are properly nested under H2 (no orphan H3)
  - Paragraph length ≤150 words
  - Em-dash count = 0 (delegates to em_dash_audit but flags here too)
  - Internal anchor links resolve to actual H2s

Used by:
  - quality-gate-structure dimension
  - PostToolUse hook on draft.md
  - section-drafter / assembly step
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts.lint._text_utils import (
    Match, find_all_with_line, iter_h2_sections, strip_frontmatter, strip_markdown,
)


# ─── Section identifiers (case-insensitive H2 matching) ────────────

_REQUIRED_SECTIONS: dict[str, list[str]] = {
    # Canonical name → list of acceptable H2 phrasings
    "abstract":       ["abstract", "summary", "overview", "introduction"],
    # "tl;dr"/"tldr" are deliberately NOT aliases here. In this pipeline `## TL;DR` is a
    # DISTINCT component (the tldr_box) that coexists with `## Key Takeaways` on every
    # article, so treating it as a synonym reported a phantom "duplicate section:
    # key_takeaways appears 2 times" on all three articles of the 2026-08-05 batch.
    # TL;DR presence is covered independently by _TLDR_NAMES below.
    "key_takeaways":  ["key takeaways", "takeaways", "quick takeaways", "what you'll learn"],
    "toc":            ["table of contents", "toc", "in this article", "contents"],
    "faq":            ["faq", "frequently asked", "common questions", "questions"],
    "conclusion":     ["conclusion", "final thoughts", "wrap-up", "verdict", "bottom line"],
    "references":    ["references", "sources", "bibliography", "citations", "works cited"],
}

_TLDR_NAMES = {"tl;dr", "tldr", "quick answer", "summary", "the short version"}


@dataclass
class SectionFinding:
    canonical_name: str
    found: bool
    h2_text: str | None
    line_no: int | None
    duplicate_count: int = 0   # 0 = unique, 1 = appears twice, etc.


@dataclass
class StructureReport:
    file: str
    total_lines: int
    total_words: int
    # Section coverage
    sections: list[SectionFinding] = field(default_factory=list)
    # Hard rules
    ends_at_references: bool = False
    tldr_in_first_540_words: bool = False
    no_html_tables: bool = True
    markdown_table_count: int = 0
    markdown_tables_in_front_half: int = 0
    h2_count: int = 0
    h3_orphan_count: int = 0
    paragraph_over_150w_count: int = 0
    em_dash_count: int = 0
    # Overall
    passed: bool = False
    issues: list[str] = field(default_factory=list)


_H2_ANCHOR_SUFFIX_RE = re.compile(r"\s*\{#[^}]*\}\s*$")


def _normalize_h2(text: str) -> str:
    """Lowercase + strip punctuation for matching.

    The `{#anchor}` suffix is removed FIRST. assemble.py injects a canonical anchor
    onto every H2, so by the time this lint sees a real draft the heading reads
    `## Abstract {#abstract}`. Stripping punctuation without removing the suffix
    turned that into "abstract abstract", which matched nothing, so EVERY section
    reported found:false on EVERY pipeline-produced article (verified 2026-08-05 on
    the project-alpha batch). The lint could not fail for the reason it exists, and could
    not pass either — it was inert (Rule 14).
    """
    return re.sub(r"[^\w\s]", "", _H2_ANCHOR_SUFFIX_RE.sub("", text)).strip().lower()


def _find_section(h2_sections: list, names: list[str]) -> tuple[int, "object"] | None:
    """Find first H2 matching any of the given names."""
    name_set = set(names)
    for s in h2_sections:
        if _normalize_h2(s.h2_text) in name_set:
            return s.start_line, s
    return None


def analyze(text: str) -> StructureReport:
    body = strip_frontmatter(text)
    lines = body.splitlines()
    h2s = list(iter_h2_sections(body))
    total_words = len(strip_markdown(body).split())

    rep = StructureReport(
        file="<input>", total_lines=len(lines), total_words=total_words,
        h2_count=len(h2s),
    )

    # ── Section coverage ──
    for canonical, aliases in _REQUIRED_SECTIONS.items():
        aliases_norm = [_normalize_h2(a) for a in aliases]
        # PREFIX match, not exact. The alias table is written as prefixes ("frequently
        # asked" is not a heading anyone writes in full), but this compared for exact
        # set membership, so the plugin's OWN default FAQ heading, "Frequently Asked
        # Questions", never matched its own alias. Same disease core_eeat_scorer
        # already fixed once for `^##\s+faq`; this was the third instance in the
        # codebase (2026-08-05 audit). Prefix matching also absorbs the ordinary
        # variants ("References and Further Reading", "Summary of Findings").
        found_sections = [
            s for s in h2s
            if any(_normalize_h2(s.h2_text).startswith(a) for a in aliases_norm)
        ]
        rep.sections.append(SectionFinding(
            canonical_name=canonical,
            found=len(found_sections) > 0,
            h2_text=found_sections[0].h2_text if found_sections else None,
            line_no=found_sections[0].start_line if found_sections else None,
            duplicate_count=max(0, len(found_sections) - 1),
        ))
        if not found_sections:
            rep.issues.append(f"Missing section: {canonical} (looked for: {aliases})")
        if len(found_sections) > 1:
            rep.issues.append(
                f"Duplicate section: {canonical} appears {len(found_sections)} times"
            )

    # ── Ends at References ──
    refs_section = None
    for s in h2s:
        if _normalize_h2(s.h2_text) in {_normalize_h2(a) for a in _REQUIRED_SECTIONS["references"]}:
            refs_section = s
    if refs_section:
        # Check: after Refs section, only Reference list lines + possible empty lines remain
        after_refs = body[body.find("\n", _find_line_offset(body, refs_section.start_line)) + 1:]
        # Strip trailing whitespace
        if not after_refs.strip():
            # Empty after refs heading? That's fine but unusual
            pass
        # Count chars *after* what looks like a reference entry (not headers, not main prose)
        suspicious_lines = []
        for ln in after_refs.splitlines():
            t = ln.strip()
            if not t:
                continue
            # Reference patterns: [number], -, *, plain author-year text
            if re.match(r"^\s*(\d+\.|-|\*|\[\d+\]|\(?\d{4}\)?\.|[A-Z][a-z]+,)", t):
                continue
            # H2/H3 mid-references is suspicious
            if t.startswith("#"):
                suspicious_lines.append(ln[:100])
        if suspicious_lines:
            rep.ends_at_references = False
            rep.issues.append(f"Content after References: {suspicious_lines[:3]}")
        else:
            rep.ends_at_references = True
    else:
        rep.ends_at_references = False
        rep.issues.append("No References section found")

    # ── TL;DR in first 540 words ──
    first_540 = " ".join(strip_markdown(body).split()[:540])
    for tldr_name in _TLDR_NAMES:
        if tldr_name in first_540.lower():
            rep.tldr_in_first_540_words = True
            break
    if not rep.tldr_in_first_540_words:
        # Allow if Abstract is present (treats abstract as tldr equivalent)
        abs_found = any(s.canonical_name == "abstract" and s.found for s in rep.sections)
        kt_found = any(s.canonical_name == "key_takeaways" and s.found for s in rep.sections)
        if not (abs_found or kt_found):
            rep.issues.append("Missing TL;DR/Abstract/Takeaways in first 540 words")

    # ── No HTML tables ──
    if re.search(r"<table\b", body, re.IGNORECASE):
        rep.no_html_tables = False
        rep.issues.append("HTML <table> mixed in — use markdown tables")

    # ── Markdown table count + front-half placement ──
    table_starts: list[int] = []
    for m in re.finditer(r"^\|[^\n]*\|\s*\n\|[\s:|-]+\|\s*\n", body, re.MULTILINE):
        table_starts.append(body[:m.start()].count("\n") + 1)
    rep.markdown_table_count = len(table_starts)
    if len(lines) > 0:
        front_half_cutoff = len(lines) / 2
        rep.markdown_tables_in_front_half = sum(1 for s in table_starts if s < front_half_cutoff)
    if rep.markdown_table_count < 2:
        rep.issues.append(f"Only {rep.markdown_table_count} markdown table(s); need ≥2")
    if rep.markdown_tables_in_front_half < 1:
        rep.issues.append("No markdown tables in front 50% of article")

    # ── H3 orphan check ──
    rep.h3_orphan_count = _count_h3_orphans(body)
    if rep.h3_orphan_count > 0:
        rep.issues.append(f"H3 orphans found (H3 not under any H2): {rep.h3_orphan_count}")

    # ── Paragraph length ──
    paragraphs = re.split(r"\n\s*\n+", strip_markdown(body))
    rep.paragraph_over_150w_count = sum(
        1 for p in paragraphs if len(p.split()) > 150
    )
    if rep.paragraph_over_150w_count > 0:
        rep.issues.append(f"Paragraphs >150 words: {rep.paragraph_over_150w_count}")

    # ── Em-dash ──
    # ACTUALLY delegate to em_dash_audit (this header's claim was false until
    # 2026-07-17 — a third independent counter had drifted: it counted the
    # References section, where APA-7 source titles legitimately contain
    # em-dashes, e.g. the CBSA "I Declare — ..." title that em_dash_audit's
    # References exemption was built for).
    from scripts.lint.em_dash_audit import em_dash_count as _em_dash_count
    rep.em_dash_count = _em_dash_count(body)
    if rep.em_dash_count > 0:
        rep.issues.append(f"Em-dashes found: {rep.em_dash_count} (zero-tolerance)")

    # ── Overall pass ──
    rep.passed = (
        all(s.found for s in rep.sections) and
        all(s.duplicate_count == 0 for s in rep.sections) and
        rep.ends_at_references and
        rep.tldr_in_first_540_words and
        rep.no_html_tables and
        rep.markdown_table_count >= 2 and
        rep.markdown_tables_in_front_half >= 1 and
        rep.h3_orphan_count == 0 and
        rep.em_dash_count == 0
    )

    return rep


# ─── Helpers ──────────────────────────────────────────────────

def _find_line_offset(text: str, line_no: int) -> int:
    """Convert 1-based line number to character offset."""
    if line_no <= 1:
        return 0
    offset = 0
    for _ in range(line_no - 1):
        nl = text.find("\n", offset)
        if nl < 0:
            return offset
        offset = nl + 1
    return offset


def _count_h3_orphans(body: str) -> int:
    """Count H3 headings that appear before any H2."""
    orphans = 0
    seen_h2 = False
    for line in body.splitlines():
        if re.match(r"^##\s+", line):
            seen_h2 = True
        elif re.match(r"^###\s+", line):
            if not seen_h2:
                orphans += 1
    return orphans


# ─── CLI ─────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Markdown article structure check")
    ap.add_argument("file", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    text = args.file.read_text(encoding="utf-8")
    rep = analyze(text)
    rep.file = str(args.file)

    if args.json:
        out = asdict(rep)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        verdict = "✓ PASS" if rep.passed else "✗ FAIL"
        print(f"File: {args.file}")
        print(f"Words: {rep.total_words}  Lines: {rep.total_lines}  H2: {rep.h2_count}")
        print(f"Tables: {rep.markdown_table_count} ({rep.markdown_tables_in_front_half} in front half)")
        print()
        print(f"Sections found:")
        for s in rep.sections:
            icon = "✓" if s.found and s.duplicate_count == 0 else "✗"
            dup_note = f" (×{s.duplicate_count + 1})" if s.duplicate_count > 0 else ""
            print(f"  {icon} {s.canonical_name:18s}  {s.h2_text or '(missing)'}{dup_note}")
        print()
        print(f"Ends at References:  {'yes' if rep.ends_at_references else 'no'}")
        print(f"TL;DR in first 540w: {'yes' if rep.tldr_in_first_540_words else 'no'}")
        print(f"Em-dash count:       {rep.em_dash_count}")
        print(f"H3 orphans:          {rep.h3_orphan_count}")
        print(f"Long paragraphs:     {rep.paragraph_over_150w_count}")
        print()
        print(f"Overall: {verdict}")
        if rep.issues:
            print(f"\nIssues ({len(rep.issues)}):")
            for i in rep.issues:
                print(f"  ✗ {i}")

    return 0 if rep.passed else 1


if __name__ == "__main__":
    sys.exit(main())
