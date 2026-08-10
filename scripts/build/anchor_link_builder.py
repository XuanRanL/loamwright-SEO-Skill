"""scripts/build/anchor_link_builder.py — Inject anchor IDs on H2/H3 and build ToC.

Used by assemble.py and meta-builder. Reads markdown, generates:
  - H2/H3 with anchor IDs (slug)
  - Markdown ToC with [Title](#anchor) links
  - Auto-rewrite source markdown to inject {#anchor} after each H2/H3
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts._core import heading_anchor


@dataclass
class Anchor:
    level: int           # 2 or 3
    text: str
    slug: str
    line_no: int


@dataclass
class ToC:
    anchors: list[Anchor] = field(default_factory=list)
    markdown: str = ""   # rendered ToC list


# ASCII transliteration for anchor slugs — kept identical to
# markdown_to_html._ANCHOR_TRANSLIT so the TOC href (built here) and the rendered
# heading id (built there) always agree. Non-ASCII (e.g. "µ") otherwise survives in
# the id but percent-encodes in the href → render_lint L10 mismatch.
_ANCHOR_TRANSLIT = str.maketrans({
    "µ": "u", "μ": "u", "²": "2", "³": "3", "°": "", "×": "x", "÷": "",
    "–": "-", "—": "-", "’": "", "‘": "", "“": "", "”": "",
})


def _slug(text: str, used: set[str]) -> str:
    """Generate an ASCII-only slug; ensure uniqueness within document."""
    s = text.lower().strip()
    s = re.sub(r"\*+|_+|`+|#+", "", s)
    s = s.translate(_ANCHOR_TRANSLIT)
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    # Cap length on a word (hyphen) boundary so anchors never slice mid-syllable
    # (e.g. '...-for-all-9-com'). The heading id and the TOC href both come from
    # this one function, so they stay byte-identical regardless of the cap.
    if len(s) > 80:
        cut = s[:80]
        s = cut.rsplit("-", 1)[0] if "-" in cut else cut
        s = s.strip("-")
    base = s or "section"
    candidate = base
    i = 2
    while candidate in used:
        candidate = f"{base}-{i}"
        i += 1
    used.add(candidate)
    return candidate


def collect_anchors(markdown: str) -> list[Anchor]:
    """Find all H2/H3 headings and assign anchor slugs."""
    anchors: list[Anchor] = []
    used: set[str] = set()
    for i, line in enumerate(markdown.splitlines(), 1):
        m2 = re.match(r"^(#{2,3})\s+(.+?)\s*(?:\{#[^}]+\})?\s*$", line)
        if m2:
            level = len(m2.group(1))
            text = m2.group(2).strip()
            anchors.append(Anchor(level=level, text=text,
                                  slug=_slug(text, used), line_no=i))
    return anchors


# Component ids (scripts/_core/component_headings.COMPONENTS keys) whose headings
# are visual boxes, never navigational sections. "checklist" is deliberately NOT
# here: real content sections are legitimately titled "...checklist" and must
# stay in the TOC (the checklist COMPONENT is realized as bold-led bullets, not
# as its own H2).
_TOC_EXCLUDED_COMPONENT_IDS = frozenset(
    {"tldr", "glossary", "stat_grid", "at_a_glance", "cta", "cta_quiet", "cta_banner"}
)

# classify_heading matches these as components, but the mandatory-sections
# contract also allows them as REAL section headings — keep them in the TOC.
# ("The Bottom Line" is a valid Conclusion H2 per business-context
# mandatory_sections conclusion pattern, yet aliases the tldr component.)
# Matched as an exact heading OR as a "{phrase}: {subtitle}" prefix — real
# conclusion H2s are written with subtitles ("The Bottom Line: Two Jobs, One
# Healthy Ear"), and the exact-only match silently dropped every one of them
# from the TOC (found 2026-08-08; the 2026-08-04 batch shipped the same hole).
_TOC_EXCLUSION_WHITELIST = frozenset({"the bottom line"})


def _is_whitelisted_section_heading(norm: str) -> bool:
    """True when `norm` is a whitelisted real-section heading, exact or with a
    ':'-separated subtitle (component boxes never carry subtitles)."""
    return any(
        norm == phrase or norm.startswith(phrase + ":")
        for phrase in _TOC_EXCLUSION_WHITELIST
    )


def _is_toc_excluded(text: str) -> bool:
    """True for headings that must NOT appear as TOC entries.

    v3.38.3 root cure (2026-07-10 batch audit): the regenerated TOC listed
    visual-design COMPONENT boxes (## TL;DR / ## Glossary / ## By the Numbers /
    ## At a Glance) and the "## Table of Contents" heading itself as if they were
    article sections — every article in the 2026-07-09 loamwright batch shipped
    with this and needed a hand-cleaned TOC (2 of 3 were reviewer-bounced for it).
    Component boxes are INTENTIONALLY H2s (the project CSS keys on
    ``h2[id^="tldr"]`` etc. — see article_css_generator), so the fix is here in
    the TOC builder, not a heading demotion: anchors are still injected on every
    heading (CSS unaffected); they are only excluded from the TOC list.

    The exclusion consults the scripts/_core/component_headings registry (the
    v3.31 single source of truth) restricted to _TOC_EXCLUDED_COMPONENT_IDS —
    add an alias THERE and the TOC learns it too.
    """
    from scripts._core.component_headings import classify_heading

    norm = " ".join(text.split()).strip().lower()
    if norm.rstrip(":") == "table of contents":
        return True  # never list the TOC inside itself
    if _is_whitelisted_section_heading(norm):
        return False
    return classify_heading(text) in _TOC_EXCLUDED_COMPONENT_IDS


def build_toc(anchors: list[Anchor], *, include_h3: bool = False, indent: str = "  ") -> str:
    """Render anchors as markdown bullet list.

    Component-box headings (TL;DR / Glossary / By the Numbers / At a Glance /
    checklist / CTA skins — per scripts/_core/component_headings) and the
    Table of Contents self-reference are skipped: they are visual components,
    not navigational sections. Their anchors are still injected (CSS depends
    on the heading ids); only the TOC listing excludes them.
    """
    lines = []
    for a in anchors:
        if _is_toc_excluded(a.text):
            continue
        if a.level == 2:
            lines.append(f"- [{a.text}](#{a.slug})")
        elif a.level == 3 and include_h3:
            lines.append(f"{indent}- [{a.text}](#{a.slug})")
    return "\n".join(lines)


def inject_anchors(markdown: str, anchors: list[Anchor]) -> str:
    """Rewrite markdown so every H2/H3 carries the CANONICAL computed anchor.

    v3.41.3 root cure (2026-07-19 loamwright batch): the old behavior SKIPPED
    headings that already carried a ``{#...}`` suffix, while ``build_toc``
    always links the freshly computed text-slug — so a writer-supplied anchor
    (e.g. the outline's hand-shortened ``anchor_id`` copied into the heading)
    left the heading id and the TOC href permanently disagreeing: 8 of 14 TOC
    links were dead on the rendered draft (``markdown_to_html._add_anchor_ids``
    honors an explicit anchor as the element id). The canonical text-slug now
    ALWAYS wins: any pre-existing anchor is stripped and replaced, making the
    pass idempotent and guaranteeing heading id == TOC slug by construction.
    This also closes the component-CSS hole where a custom anchor like
    ``## TL;DR {#summary}`` silently orphaned ``h2[id^="tldr"]`` styling.
    """
    lines = markdown.splitlines(keepends=True)
    by_line = {a.line_no: a for a in anchors}
    out = []
    for i, line in enumerate(lines, 1):
        if i in by_line:
            a = by_line[i]
            # Strip trailing newline for matching
            stripped = line.rstrip("\n\r")
            # Canonical slug always wins: drop any pre-existing anchor first.
            stripped = heading_anchor.ANCHOR_SUFFIX_RE.sub("", stripped)
            new = stripped + f" {{#{a.slug}}}"
            # Restore trailing newline
            if line.endswith("\r\n"):
                new += "\r\n"
            elif line.endswith("\n"):
                new += "\n"
            out.append(new)
        else:
            out.append(line)
    return "".join(out)


def process(markdown: str, *, include_h3_in_toc: bool = False) -> tuple[str, ToC]:
    """Full process: collect, build ToC, inject anchors.

    Returns (modified_markdown, toc).
    """
    anchors = collect_anchors(markdown)
    toc_md = build_toc(anchors, include_h3=include_h3_in_toc)
    modified = inject_anchors(markdown, anchors)
    return modified, ToC(anchors=anchors, markdown=toc_md)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--in-place", action="store_true", help="Rewrite source file")
    ap.add_argument("--include-h3", action="store_true")
    ap.add_argument("--toc-only", action="store_true", help="Output ToC only (no rewrite)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"Not found: {args.file}", file=sys.stderr)
        return 2
    text = args.file.read_text(encoding="utf-8")
    modified, toc = process(text, include_h3_in_toc=args.include_h3)

    if args.in_place:
        args.file.write_text(modified, encoding="utf-8")
        print(f"Updated {args.file} with {len(toc.anchors)} anchors injected", file=sys.stderr)

    if args.json:
        print(json.dumps({
            "anchors": [asdict(a) for a in toc.anchors],
            "toc_markdown": toc.markdown,
        }, indent=2, ensure_ascii=False))
    elif args.toc_only:
        print(toc.markdown)
    elif not args.in_place:
        print(modified)
    return 0


if __name__ == "__main__":
    sys.exit(main())
