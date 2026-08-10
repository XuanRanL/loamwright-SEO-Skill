"""
scripts/validate/word_count.py — Accurate word count excluding markdown.

Strips frontmatter, code blocks, inline code, image syntax, link URLs (keep
anchor text), heading prefixes, list markers, table syntax — then counts words.

Per v3.2 spec: word count must be within [target × 0.95, target × 1.10].

Also reports:
  - words per H2 section
  - paragraph count
  - sentence count (best-effort)
  - avg words per paragraph
  - avg words per sentence
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts.lint._text_utils import (
    count_words, iter_h2_sections, iter_paragraphs,
    iter_sentences, strip_markdown,
)


@dataclass
class WordCountReport:
    total_words: int
    paragraph_count: int
    sentence_count: int
    avg_words_per_paragraph: float
    avg_words_per_sentence: float
    by_h2_section: list[tuple[str, int]] = field(default_factory=list)
    target_min: int = 0
    target_max: int = 0
    within_band: bool = True


def analyze(text: str, target: int = 0) -> WordCountReport:
    total = count_words(text)
    paras = list(iter_paragraphs(text))
    n_para = len(paras)
    sents = list(iter_sentences(text))
    n_sent = len(sents)

    avg_pp = total / n_para if n_para else 0
    avg_ps = total / n_sent if n_sent else 0

    by_section: list[tuple[str, int]] = []
    for section in iter_h2_sections(text):
        body_words = count_words(section.body)
        by_section.append((section.h2_text, body_words))

    if target > 0:
        target_min = int(target * 0.95)
        target_max = int(target * 1.10)
        within = target_min <= total <= target_max
    else:
        target_min = target_max = 0
        within = True

    return WordCountReport(
        total_words=total,
        paragraph_count=n_para,
        sentence_count=n_sent,
        avg_words_per_paragraph=round(avg_pp, 1),
        avg_words_per_sentence=round(avg_ps, 1),
        by_h2_section=by_section,
        target_min=target_min,
        target_max=target_max,
        within_band=within,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Markdown word count + structure")
    ap.add_argument("file", type=Path)
    ap.add_argument("--target", type=int, default=0, help="Target word count (±5%/+10% bands)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"Not found: {args.file}", file=sys.stderr)
        return 2
    text = args.file.read_text(encoding="utf-8")
    r = analyze(text, args.target)

    if args.json:
        print(json.dumps(asdict(r), indent=2, ensure_ascii=False))
    else:
        print(f"File: {args.file}")
        print(f"Total words:        {r.total_words}")
        print(f"Paragraphs:         {r.paragraph_count}")
        print(f"Sentences:          {r.sentence_count}")
        print(f"Words/paragraph:    {r.avg_words_per_paragraph}")
        print(f"Words/sentence:     {r.avg_words_per_sentence}")
        if args.target:
            verdict = "✓ PASS" if r.within_band else "✗ FAIL"
            print(f"Target:             {args.target} (band {r.target_min}-{r.target_max})  {verdict}")
        print(f"\nBy H2 section ({len(r.by_h2_section)}):")
        for h2, n in r.by_h2_section:
            print(f"  {n:4d} words  {h2[:80]}")
    return 0 if r.within_band else 1


if __name__ == "__main__":
    sys.exit(main())
