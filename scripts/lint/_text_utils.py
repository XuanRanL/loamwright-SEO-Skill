"""
scripts/lint/_text_utils.py — Shared text/markdown processing primitives.

Used by all lint scripts. No external dependencies (stdlib only).

Public functions:
    strip_markdown(text)                — remove code blocks, tables, links → plain text
    strip_frontmatter(text)             — drop --- ... --- block
    iter_lines(text)                    — (line_num_1_based, line_text)
    iter_sentences(text)                — best-effort sentence split
    iter_paragraphs(text)               — split on blank line
    count_words(text)                   — words excluding code blocks
    iter_h2_sections(text)              — yield (h2_text, section_body, start_line)
    extract_code_blocks(text)           — yield (start_line, end_line, lang, content)
    find_all_with_line(pattern, text)   — yield (line_no, match) for regex hits

Design notes:
    - All operations preserve original line numbers for error reporting
    - No NLP libs; pure regex + str
    - UTF-8 safe; handles Chinese / Japanese / Korean / RTL
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator


# ─── Regexes ──────────────────────────────────────────────────────

_CODE_FENCE_RE = re.compile(r"^```([^\n]*)\n(.*?)^```", re.DOTALL | re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_TABLE_ROW_RE = re.compile(r"^\|.*\|\s*$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+?)$", re.MULTILINE)
_H1_RE = re.compile(r"^#\s+(.+?)$", re.MULTILINE)
# Sentence delimiter heuristic (works for English-Latin scripts;
# Chinese/Japanese use 。！？)
_SENT_END_RE = re.compile(r"(?<=[.!?。！？])\s+(?=[A-ZÀ-Ÿ一-鿿])")
_WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)$", re.MULTILINE)


# ─── Data types ──────────────────────────────────────────────────

@dataclass(frozen=True)
class Match:
    """A single lint hit with line number."""
    line: int             # 1-based
    column: int           # 0-based
    text: str             # the matched substring
    context: str          # surrounding line (trimmed)


@dataclass(frozen=True)
class CodeBlock:
    start_line: int
    end_line: int
    lang: str
    content: str


@dataclass(frozen=True)
class H2Section:
    h2_text: str
    body: str
    start_line: int       # 1-based, line of the ## heading
    end_line: int         # 1-based, line BEFORE next H2 (or last line)


# ─── Markdown stripping ──────────────────────────────────────────

def strip_frontmatter(text: str) -> str:
    """Remove ---...--- YAML frontmatter block if present."""
    return _FRONTMATTER_RE.sub("", text, count=1)


def strip_markdown(text: str, *, keep_lists: bool = True) -> str:
    """Remove markdown syntax → plain prose for analysis.

    - Strips: frontmatter, code blocks, inline code, image syntax (keeps alt),
      link syntax (keeps anchor text), headings (#), bold/italic (*_), blockquotes,
      horizontal rules
    - Keeps: list markers if keep_lists=True (so sentence_variance can count them)
    """
    t = strip_frontmatter(text)
    # Strip fenced code blocks
    t = _CODE_FENCE_RE.sub("", t)
    # Strip inline code
    t = _INLINE_CODE_RE.sub("", t)
    # Replace images with alt text
    t = _MD_IMAGE_RE.sub(r"\1", t)
    # Replace links with anchor text
    t = _MD_LINK_RE.sub(r"\1", t)
    # Strip heading prefixes
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
    # Strip blockquote markers
    t = re.sub(r"^>\s?", "", t, flags=re.MULTILINE)
    # Strip horizontal rules
    t = re.sub(r"^---+\s*$", "", t, flags=re.MULTILINE)
    # Strip bold/italic markers (simple cases)
    t = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*\n]+)\*", r"\1", t)
    t = re.sub(r"__([^_\n]+)__", r"\1", t)
    t = re.sub(r"_([^_\n]+)_", r"\1", t)
    # Strip list markers if requested
    if not keep_lists:
        t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
        t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)
    # Strip table syntax
    t = re.sub(r"^\|.*\|\s*$", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\|?[\s:|-]+\|?\s*$", "", t, flags=re.MULTILINE)
    # Collapse multiple newlines
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


# ─── Code blocks ──────────────────────────────────────────────

def extract_code_blocks(text: str) -> Iterator[CodeBlock]:
    """Yield CodeBlock for each ```lang\n...\n``` fence."""
    text_no_fm = strip_frontmatter(text)
    offset = len(text) - len(text_no_fm)  # lines we skipped
    fm_lines = text[:offset].count("\n")

    for m in _CODE_FENCE_RE.finditer(text_no_fm):
        start_off = m.start()
        start_line = text_no_fm[:start_off].count("\n") + 1 + fm_lines
        content = m.group(2)
        end_line = start_line + content.count("\n") + 1
        yield CodeBlock(
            start_line=start_line,
            end_line=end_line,
            lang=m.group(1).strip() or "",
            content=content,
        )


# ─── H2 sections ──────────────────────────────────────────────

def iter_h2_sections(text: str) -> Iterator[H2Section]:
    """Yield H2Section for each `## Heading` block in the document.

    The 'body' field includes everything after the heading line up to
    (but not including) the next H2 heading or end of document.
    """
    lines = text.splitlines(keepends=True)
    matches = []
    for i, line in enumerate(lines, start=1):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            matches.append((i, m.group(1).strip()))

    for idx, (start_line, h2_text) in enumerate(matches):
        end_line = matches[idx + 1][0] - 1 if idx + 1 < len(matches) else len(lines)
        body = "".join(lines[start_line:end_line])
        yield H2Section(
            h2_text=h2_text, body=body,
            start_line=start_line, end_line=end_line,
        )


# ─── Lines / sentences / words ────────────────────────────────

def iter_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield (1-based line number, line text without trailing newline)."""
    for i, line in enumerate(text.splitlines(), start=1):
        yield i, line


def iter_sentences(text: str) -> Iterator[str]:
    """Best-effort sentence split. Strips markdown first."""
    plain = strip_markdown(text)
    # Split on . ! ? plus CJK ideographic punctuation
    parts = _SENT_END_RE.split(plain)
    for p in parts:
        p = p.strip()
        if p:
            yield p


def iter_paragraphs(text: str) -> Iterator[str]:
    """Split on blank line (one or more)."""
    for p in re.split(r"\n\s*\n+", text):
        p = p.strip()
        if p:
            yield p


def count_words(text: str, *, strip_md: bool = True) -> int:
    """Count words (Unicode-aware), optionally excluding markdown."""
    t = strip_markdown(text) if strip_md else text
    return len(_WORD_RE.findall(t))


def words_per_sentence(text: str) -> list[int]:
    """Return list of word counts per sentence."""
    return [len(_WORD_RE.findall(s)) for s in iter_sentences(text)]


# ─── Regex find with line numbers ─────────────────────────────

def find_all_with_line(
    pattern: re.Pattern[str] | str,
    text: str,
    *,
    flags: int = 0,
    skip_code_blocks: bool = True,
    skip_frontmatter: bool = True,
) -> Iterator[Match]:
    """Yield Match for each pattern hit, with 1-based line number.

    Args:
        pattern: regex pattern or compiled Pattern.
        text: input text.
        flags: regex flags (only if pattern is str).
        skip_code_blocks: don't report hits inside ```...``` blocks.
        skip_frontmatter: don't report hits in --- ... --- frontmatter.
    """
    if isinstance(pattern, str):
        pattern = re.compile(pattern, flags)

    # Determine excluded line ranges
    exclude_ranges: list[tuple[int, int]] = []
    if skip_frontmatter:
        m = _FRONTMATTER_RE.match(text)
        if m:
            n_lines = text[m.start():m.end()].count("\n")
            exclude_ranges.append((1, n_lines))
    if skip_code_blocks:
        for cb in extract_code_blocks(text):
            exclude_ranges.append((cb.start_line, cb.end_line))

    def excluded(line_no: int) -> bool:
        return any(lo <= line_no <= hi for lo, hi in exclude_ranges)

    # Walk through matches
    for m in pattern.finditer(text):
        start = m.start()
        line_no = text[:start].count("\n") + 1
        if excluded(line_no):
            continue
        # column within line
        last_nl = text.rfind("\n", 0, start)
        col = start - (last_nl + 1) if last_nl >= 0 else start
        # context line
        line_end = text.find("\n", start)
        if line_end < 0:
            line_end = len(text)
        line_start = last_nl + 1 if last_nl >= 0 else 0
        ctx = text[line_start:line_end].strip()
        yield Match(
            line=line_no, column=col,
            text=m.group(0),
            context=ctx[:200],
        )


# ─── Format helpers for reports ──────────────────────────────

def format_hits_table(hits: list[Match], *, max_rows: int = 50) -> str:
    """Format hits as a simple table for terminal output."""
    if not hits:
        return "  (no hits)"
    lines = []
    for h in hits[:max_rows]:
        lines.append(f"  line {h.line:4d}:{h.column:3d}  {h.text!r:20s}  …{h.context[:80]}…")
    if len(hits) > max_rows:
        lines.append(f"  ... and {len(hits) - max_rows} more")
    return "\n".join(lines)
