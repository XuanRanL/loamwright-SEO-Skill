"""
scripts/lint/curly_quote_audit.py — Typographic AI fingerprint detector.

Different AIs have different default typographic habits:
  - ChatGPT/GPT-4: curly quotes ('smart' "quotes") U+2018-201D
  - Claude: usually straight ASCII quotes
  - Gemini: mixed
  - Most humans typing in editors: straight quotes (')

So curly quotes in long-form web content = high probability of AI authorship.

Other tells detected:
  - Ellipsis character U+2026 …
  - Non-breaking space U+00A0 (between words; LLM output artifact)
  - Various Unicode minus / hyphens beyond standard ASCII

Why fix: ① consistency ② removes AI fingerprint ③ avoids smart-quote
mismatches in code blocks and HTML attributes.

Detection categories (severity):
  - HIGH:    Curly single/double quotes
  - MEDIUM:  Ellipsis (rare in genuine typing)
  - LOW:     Non-breaking spaces, hyphenation variants
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from scripts.lint._text_utils import find_all_with_line


# Detection patterns
_CURLY_SINGLE = re.compile(r"[‘’]")   # ' '
_CURLY_DOUBLE = re.compile(r"[“”]")   # " "
_ELLIPSIS_CHAR = re.compile(r"…")           # …
_NBSP = re.compile(r" ")                    # non-breaking space
_LOW_QUOTE = re.compile(r"[‚„]")       # ‚ „
_PRIME = re.compile(r"[′″]")           # ′ ″ (prime / double prime)
_MIDDLE_DOT = re.compile(r"·")              # · (when not in CJK context)
_BULLET = re.compile(r"•")                  # • (vs - or *)


@dataclass(frozen=True)
class TypoHit:
    char: str
    name: str
    severity: str
    line: int
    column: int
    context: str
    suggestion: str


_RULES: Final = [
    (_CURLY_SINGLE,  "Curly single quote",  "high",   "Replace with straight ASCII '"),
    (_CURLY_DOUBLE,  "Curly double quote",  "high",   "Replace with straight ASCII \""),
    (_ELLIPSIS_CHAR, "Ellipsis char (U+2026)", "medium", "Replace with three dots ..."),
    (_NBSP,          "Non-breaking space",   "low",    "Replace with regular space"),
    (_LOW_QUOTE,     "Low quote (German-style)", "high", "Replace with straight ASCII"),
    (_PRIME,         "Prime / double-prime",  "medium", "Use straight quotes for inches/seconds, or rephrase"),
    (_BULLET,        "Bullet char (U+2022)",  "low",    "Use markdown - or * for lists"),
]


def lint(text: str, *, severity_filter: str | None = None) -> list[TypoHit]:
    hits: list[TypoHit] = []
    for pattern, name, sev, suggestion in _RULES:
        if severity_filter and sev != severity_filter:
            continue
        for m in find_all_with_line(pattern, text):
            hits.append(TypoHit(
                char=m.text, name=name, severity=sev,
                line=m.line, column=m.column,
                context=m.context, suggestion=suggestion,
            ))
    hits.sort(key=lambda h: (h.line, h.column))
    return hits


def curly_quote_count(text: str) -> int:
    """Quick count for AI-Slop / quality gates."""
    return len(_CURLY_SINGLE.findall(text)) + len(_CURLY_DOUBLE.findall(text))


def auto_fix(text: str) -> str:
    """Replace common typographic chars with ASCII equivalents."""
    t = text
    # Curly singles → '
    t = re.sub(r"[‘’]", "'", t)
    # Curly doubles → "
    t = re.sub(r"[“”]", '"', t)
    # Ellipsis → ...
    t = re.sub(r"…", "...", t)
    # NBSP → space
    t = re.sub(r" ", " ", t)
    # Low quotes → straight
    t = re.sub(r"[‚„]", "'", t)
    return t


def main() -> int:
    ap = argparse.ArgumentParser(description="Typographic AI fingerprint auditor")
    ap.add_argument("file", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--severity", choices=["high", "medium", "low"])
    ap.add_argument("--fix", action="store_true", help="Auto-replace curly chars in-place")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    text = args.file.read_text(encoding="utf-8")

    if args.fix:
        new = auto_fix(text)
        if new != text:
            args.file.write_text(new, encoding="utf-8")
            print(f"Auto-fixed {curly_quote_count(text)} curly quotes and other typographic chars.")
        else:
            print("Nothing to fix.")
        return 0

    hits = lint(text, severity_filter=args.severity)

    if args.json:
        out = {
            "file": str(args.file),
            "total_hits": len(hits),
            "curly_quote_count": curly_quote_count(text),
            "passed": curly_quote_count(text) == 0,
            "by_severity": {
                "high":   sum(1 for h in hits if h.severity == "high"),
                "medium": sum(1 for h in hits if h.severity == "medium"),
                "low":    sum(1 for h in hits if h.severity == "low"),
            },
            "hits": [asdict(h) for h in hits[:80]],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"File: {args.file}")
        print(f"Total hits: {len(hits)}  (curly quotes: {curly_quote_count(text)})")
        if hits:
            sev_count = {s: sum(1 for h in hits if h.severity == s) for s in ["high", "medium", "low"]}
            print(f"  By severity: {sev_count}")
            for h in hits[:50]:
                print(f"  line {h.line:4d}:{h.column:3d}  [{h.severity}] {h.name}  '{h.char}'")
                print(f"    → {h.suggestion}")

    return 0 if curly_quote_count(text) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
