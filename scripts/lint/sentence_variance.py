"""
scripts/lint/sentence_variance.py — Burstiness (sentence-length variance) detector.

The "burstiness" metric is one of the two key features GPTZero-style detectors
use. Humans naturally vary sentence length: short fragments (3-8 words) mixed
with medium (12-20) and long (25-40+). AI clusters around 15-25 words.

We define burstiness as:
    burstiness_normalized = stddev(sentence_lengths) / mean(sentence_lengths)

Per humanizer-skill formula:
    Target: burstiness_normalized > 0.30
    Used by AI-Slop score: 4*P + 25*(1-B) + 15*V

Also produces a per-paragraph "uniformity score":
    A paragraph with 3+ consecutive sentences within ±3 words is flagged.

Why this matters: a paragraph with [18, 19, 21, 20, 18] words is robotic.
A natural paragraph might be [4, 23, 15, 31, 8]: varied burst rhythm.

Usage:
    python -m scripts.lint.sentence_variance draft.md
    python -m scripts.lint.sentence_variance draft.md --json
    python -m scripts.lint.sentence_variance draft.md --by-paragraph
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.lint._text_utils import iter_paragraphs, iter_sentences, words_per_sentence


@dataclass
class VarianceReport:
    sentence_count: int
    mean_length: float
    stddev_length: float
    burstiness_normalized: float       # stddev / mean
    target_threshold: float = 0.30
    passes: bool = False
    # Distribution
    min_length: int = 0
    max_length: int = 0
    median_length: float = 0
    quartiles: list[int] | None = None
    # Length buckets
    short_count: int = 0    # <=8 words
    medium_count: int = 0   # 9-20
    long_count: int = 0     # >20
    # Suspicious paragraphs
    uniform_paragraphs: list["UniformParagraph"] = None  # type: ignore


@dataclass
class UniformParagraph:
    paragraph_index: int
    sentence_lengths: list[int]
    paragraph_stddev: float
    para_preview: str       # first 100 chars


def short_sentence_ratio(text: str, max_words: int = 5) -> float:
    """Fraction of sentences with <= max_words words.

    Burstiness (stddev/mean) is gameable: stacking ultra-short fragment-closers
    ("Pure leakage.") mechanically inflates it. This ratio is the anti-gaming signal
    consumed by ai_slop_score's staccato penalty (2026-06-30). Uses the SAME sentence
    tokenizer as the burstiness metric so the two stay consistent.
    """
    lengths = words_per_sentence(text)
    if not lengths:
        return 0.0
    return sum(1 for x in lengths if x <= max_words) / len(lengths)


def analyze(text: str) -> VarianceReport:
    """Full burstiness analysis."""
    lengths = words_per_sentence(text)
    n = len(lengths)
    if n == 0:
        return VarianceReport(
            sentence_count=0, mean_length=0.0, stddev_length=0.0,
            burstiness_normalized=0.0, passes=False,
            uniform_paragraphs=[],
        )

    mean_l = statistics.mean(lengths)
    std_l = statistics.stdev(lengths) if n >= 2 else 0.0
    burstiness = (std_l / mean_l) if mean_l > 0 else 0.0

    # Distribution
    sorted_lens = sorted(lengths)
    med = statistics.median(lengths)
    if n >= 4:
        quartiles = statistics.quantiles(lengths, n=4)
        quartiles = [int(q) for q in quartiles]
    else:
        quartiles = sorted_lens

    # Buckets
    short = sum(1 for x in lengths if x <= 8)
    medium = sum(1 for x in lengths if 9 <= x <= 20)
    long_ = sum(1 for x in lengths if x > 20)

    # Per-paragraph uniformity check
    uniform = []
    for p_idx, para in enumerate(iter_paragraphs(text)):
        p_lens = [len(s.split()) for s in iter_sentences(para)]
        if len(p_lens) < 3:
            continue
        p_std = statistics.stdev(p_lens) if len(p_lens) >= 2 else 0.0
        # Flag if 3+ consecutive sentences within ±3 of each other
        for i in range(len(p_lens) - 2):
            window = p_lens[i:i + 3]
            if max(window) - min(window) <= 3:
                uniform.append(UniformParagraph(
                    paragraph_index=p_idx,
                    sentence_lengths=p_lens,
                    paragraph_stddev=round(p_std, 2),
                    para_preview=para[:100].replace("\n", " "),
                ))
                break  # one flag per paragraph

    return VarianceReport(
        sentence_count=n,
        mean_length=round(mean_l, 2),
        stddev_length=round(std_l, 2),
        burstiness_normalized=round(burstiness, 4),
        passes=burstiness > 0.30,
        min_length=min(lengths),
        max_length=max(lengths),
        median_length=med,
        quartiles=quartiles,
        short_count=short,
        medium_count=medium,
        long_count=long_,
        uniform_paragraphs=uniform,
    )


def burstiness_normalized(text: str) -> float:
    """Used by AI-Slop formula. Returns the (stddev/mean) ratio."""
    return analyze(text).burstiness_normalized


def main() -> int:
    ap = argparse.ArgumentParser(description="Sentence-length variance (burstiness) analyzer")
    ap.add_argument("file", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--by-paragraph", action="store_true",
                    help="Also report per-paragraph length distribution")
    ap.add_argument("--threshold", type=float, default=0.30,
                    help="Burstiness pass threshold (default 0.30)")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    text = args.file.read_text(encoding="utf-8")
    r = analyze(text)
    r.target_threshold = args.threshold
    r.passes = r.burstiness_normalized > args.threshold

    if args.json:
        out = asdict(r)
        out["uniform_paragraphs"] = [asdict(u) for u in r.uniform_paragraphs]
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"File: {args.file}")
        print(f"Sentences: {r.sentence_count}")
        print(f"  mean   = {r.mean_length} words")
        print(f"  stddev = {r.stddev_length} words")
        print(f"  median = {r.median_length}")
        print(f"  range  = [{r.min_length}, {r.max_length}]")
        print(f"  buckets: short(≤8)={r.short_count}, med(9-20)={r.medium_count}, long(>20)={r.long_count}")
        print()
        verdict = "✓ PASS" if r.passes else "✗ FAIL"
        print(f"Burstiness (stddev/mean): {r.burstiness_normalized:.4f}  (target > {args.threshold})  {verdict}")
        if r.uniform_paragraphs:
            print(f"\nUniform paragraphs flagged: {len(r.uniform_paragraphs)}")
            for u in r.uniform_paragraphs[:10]:
                print(f"  Para #{u.paragraph_index}  lengths={u.sentence_lengths}  σ={u.paragraph_stddev}")
                print(f"    …{u.para_preview}…")

        if args.by_paragraph:
            print("\nPer-paragraph sentence counts:")
            for i, para in enumerate(iter_paragraphs(text)):
                lens = [len(s.split()) for s in iter_sentences(para)]
                if not lens:
                    continue
                print(f"  P{i:3d}  n={len(lens):2d}  lens={lens[:10]}{' ...' if len(lens) > 10 else ''}")

    return 0 if r.passes else 1


if __name__ == "__main__":
    sys.exit(main())
