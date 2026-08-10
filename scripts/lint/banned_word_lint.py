"""
scripts/lint/banned_word_lint.py — Detect banned words with substitution suggestions.

Banned word source (priority order):
  1. CLI --words-file argument (one word per line)
  2. references/style/banned-words.md in plugin root (markdown list parsing)
  3. Inline DEFAULT_BANNED_WORDS fallback

Why ban each word:
  - Empty intensifiers (crucial, critical, vital) → use specific magnitudes instead
  - AI vocabulary tells (delve, leverage, multifaceted) → too obviously LLM
  - Promotional clichés (unleash, unlock, revolutionary) → low-credibility
  - Transition tics (furthermore, moreover, additionally) → AI rhythm
  - Conclusion tics (in conclusion, in summary, ultimately) → robotic close
  - Hedging stacks (it's important to note, it's worth mentioning) → padding

Each hit reports:
  - line number / column
  - matched word
  - suggested replacement(s)
  - context line

CLI:
  python -m scripts.lint.banned_word_lint draft.md
  python -m scripts.lint.banned_word_lint draft.md --json
  python -m scripts.lint.banned_word_lint draft.md --words-file my-list.md

Exit codes:
  0  No hits
  1  Hits found
  2  IO / config error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from scripts.lint._text_utils import Match, find_all_with_line


# ─── Default banned words (fallback if no references file) ──────────

# Format: word → list of suggested replacements
DEFAULT_BANNED_WORDS: Final[dict[str, list[str]]] = {
    # Empty intensifiers
    "crucial":      ["important", "central", "necessary for X to work"],
    "critical":     ["central", "load-bearing", "necessary for X"],
    "essential":    ["needed", "required", "core to X"],
    "vital":        ["needed", "core", "load-bearing"],
    "imperative":   ["needed", "important", "necessary"],
    "pivotal":      ["central", "decisive"],
    # AI vocabulary tells
    "delve":        ["explore", "examine", "look at"],
    "delves":       ["explores", "examines"],
    "leverage":     ["use", "apply", "draw on"],
    "leverages":    ["uses", "applies"],
    "multifaceted": ["many-sided", "complex"],
    "tapestry":     ["pattern", "mix", "set"],
    "landscape":    ["scene", "field", "industry"],
    "intricate":    ["complex", "detailed"],
    "robust":       ["strong", "reliable"],
    "seamless":     ["smooth", "uninterrupted"],
    "foster":       ["build", "grow", "encourage"],
    "harness":      ["use", "apply"],
    "paradigm":     ["model", "framework"],
    "dynamic":      ["active", "changing"],
    "vibrant":      ["active", "lively"],
    "nestled":      ["located", "set"],
    "cutting-edge": ["latest", "advanced"],
    "testament":    ["proof", "evidence", "example"],
    "realm":        ["field", "area"],
    "navigate":     ["work through", "handle"],
    "navigating":   ["working through"],
    "comprehensive":["complete", "thorough"],
    # Promotional clichés
    "unleash":      ["release", "let loose", "use"],
    "unleashed":    ["released"],
    "unlock":       ["enable", "open up"],
    "unlocks":      ["enables"],
    "unveil":       ["reveal", "introduce", "show"],
    "unveiled":     ["revealed"],
    "unravel":      ["explain", "untangle"],
    "uncover":      ["find", "discover"],
    "revolutionary":["new", "different"],
    # Transition tics
    "furthermore":  ["also", "and", "plus"],
    "moreover":     ["also", "and"],
    "additionally": ["also", "plus", "and"],
    "in addition":  ["also", "plus"],
    # Conclusion tics
    "in conclusion": ["so", "all told", "(just stop)"],
    "in summary":    ["so", "in short", "(just stop)"],
    "ultimately":    ["in the end", "finally", "(omit)"],
    "to wrap up":    ["(omit)"],
    "remember that": ["(omit)", "note:"],
    # Hedging / padding
    "it's important to note":   ["(omit)", "note:"],
    "it's worth mentioning":    ["(omit)"],
    "it's important to":        ["(omit)"],
    "it should be noted":       ["(omit)"],
    "needless to say":          ["(omit)"],
    "as previously mentioned":  ["(omit)"],
    "as mentioned earlier":     ["(omit)"],
    "as we discussed":          ["(omit)"],
    # Filler openers (AI tells)
    "in today's world":             ["in 2026", "(specific year)"],
    "in the world of":              ["in", "for"],
    "in today's era":               ["today", "in 2026"],
    "in today's digital era":       ["today", "online"],
    "in today's fast-paced world":  ["today"],
    # Filler verbs
    "take a dive into":     ["explore"],
    "embark on a journey":  ["start", "begin"],
    "pave the way":         ["enable", "lead to"],
    # Generic empty
    "this":   ["(specify what 'this' refers to)"],
    "and":    [],  # only flag if line starts with And
}


# ─── Load banned list from references/style/banned-words.md ────────

def _plugin_root() -> Path:
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "VERSION").exists() and (p / ".claude-plugin").is_dir():
            return p
        p = p.parent
    raise RuntimeError("Cannot find plugin root")


def load_banned_words(custom_file: Path | None = None) -> dict[str, list[str]]:
    """Load banned words map from custom file, references, or default.

    Markdown reference file format (simple):
        # Banned Words
        - **crucial** → important, central, necessary for X to work
        - **delve** → explore, examine
        ...
    """
    sources_tried = []
    if custom_file:
        sources_tried.append(custom_file)
        if custom_file.exists():
            return _parse_banned_md(custom_file.read_text(encoding="utf-8"))

    # Try plugin reference
    try:
        ref = _plugin_root() / "references" / "style" / "banned-words.md"
        sources_tried.append(ref)
        if ref.exists():
            parsed = _parse_banned_md(ref.read_text(encoding="utf-8"))
            if parsed:
                return parsed
    except RuntimeError:
        pass

    return dict(DEFAULT_BANNED_WORDS)


def _parse_banned_md(text: str) -> dict[str, list[str]]:
    """Parse markdown list of `- **word** → suggestion1, suggestion2`."""
    result: dict[str, list[str]] = {}
    pattern = re.compile(r"^\s*-\s+\*\*([^*]+)\*\*\s*(?:→|->|—)\s*(.+?)$", re.MULTILINE)
    for m in pattern.finditer(text):
        word = m.group(1).strip().lower()
        suggestions = [s.strip() for s in re.split(r"[,;]", m.group(2)) if s.strip()]
        result[word] = suggestions
    return result


# ─── Lint ──────────────────────────────────────────────────────

@dataclass
class BannedWordHit:
    word: str
    line: int
    column: int
    context: str
    suggestions: list[str]


def lint(text: str, words: dict[str, list[str]] | None = None) -> list[BannedWordHit]:
    """Find all banned-word hits in text.

    Returns sorted list (by line, then column).
    """
    if words is None:
        words = load_banned_words()

    # Sort by length descending to match multi-word phrases first
    sorted_words = sorted(words.keys(), key=lambda w: -len(w))
    # Build a single big alternation, with case-insensitive word boundaries.
    # Multi-word phrases use space boundary; single words use \b
    parts = []
    for w in sorted_words:
        if not w:
            continue
        if " " in w:
            parts.append(re.escape(w))
        else:
            parts.append(rf"\b{re.escape(w)}\b")
    if not parts:
        return []
    pattern = re.compile("|".join(parts), re.IGNORECASE)

    hits: list[BannedWordHit] = []
    for m in find_all_with_line(pattern, text):
        canonical = m.text.lower()
        # Look up in original (case-sensitive) dict
        suggestions = words.get(canonical, [])
        if not suggestions:
            # Try case variants
            for w in words:
                if w.lower() == canonical:
                    suggestions = words[w]
                    break
        hits.append(BannedWordHit(
            word=m.text, line=m.line, column=m.column,
            context=m.context, suggestions=suggestions,
        ))
    return hits


# ─── CLI ─────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Banned-word linter")
    ap.add_argument("file", type=Path, help="Markdown file to lint")
    ap.add_argument("--words-file", type=Path, help="Custom banned-words.md")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-display", type=int, default=50)
    args = ap.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    text = args.file.read_text(encoding="utf-8")
    words_map = load_banned_words(args.words_file)
    hits = lint(text, words_map)

    if args.json:
        out = {
            "file": str(args.file),
            "hits_count": len(hits),
            "passed": len(hits) == 0,
            "banned_words_loaded": len(words_map),
            "hits": [asdict(h) for h in hits[:args.max_display]],
            "truncated": len(hits) > args.max_display,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"File: {args.file}")
        print(f"Banned words loaded: {len(words_map)}")
        print(f"Hits: {len(hits)}")
        if hits:
            print()
            for h in hits[:args.max_display]:
                sugg = " | ".join(h.suggestions[:3]) if h.suggestions else "(no suggestion)"
                print(f"  line {h.line:4d}:{h.column:3d}  '{h.word}'  → {sugg}")
                print(f"      …{h.context[:100]}…")
            if len(hits) > args.max_display:
                print(f"  ... and {len(hits) - args.max_display} more")

    return 0 if not hits else 1


if __name__ == "__main__":
    sys.exit(main())
