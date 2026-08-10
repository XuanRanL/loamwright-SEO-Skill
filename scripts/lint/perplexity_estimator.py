"""
scripts/lint/perplexity_estimator.py — Vocabulary diversity / surprise estimator.

Perplexity in the GPTZero sense = "how predictable is each next word given the
previous". Humans produce less-predictable word sequences; AI produces fluent
predictable streams.

Without a language model handy, we approximate perplexity-like surprise via:
  1. TYPE-TOKEN RATIO (TTR) — unique words / total words
  2. STOPWORD RATIO — common-word density (high = AI-fluent)
  3. REPETITION DETECTION — n-gram (3-5 grams) reuse rate
  4. RARE-WORD COUNT — words not in common-5000 list
  5. AVERAGE WORD LENGTH — shorter avg = simpler vocab

Combined heuristic score:
    surprise_score = 0.4 * TTR + 0.2 * rare_word_ratio
                   - 0.2 * stopword_ratio - 0.2 * ngram_repetition_rate
    (normalized to [0, 1])

This is a proxy, not real perplexity. But it correlates with what real detectors
see, and lets the AI-Slop pipeline catch "fluent but generic" text without an LM.

Used by:
  - AI-Slop score formula (vocab_blacklist_ratio inputs)
  - quality-gate content quality dimension
  - humanizer "is this prose interesting?" check
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from scripts.lint._text_utils import strip_markdown


_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]+\b")


# Top ~300 English stopwords (no NLTK dep)
STOPWORDS: Final[frozenset[str]] = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "did", "do", "does", "doing", "don",
    "down", "during", "each", "few", "for", "from", "further", "had", "has", "have",
    "having", "he", "her", "here", "hers", "herself", "him", "himself", "his", "how",
    "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more",
    "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same",
    "she", "should", "so", "some", "such", "than", "that", "the", "their", "theirs",
    "them", "themselves", "then", "there", "these", "they", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "we", "were", "what", "when",
    "where", "which", "while", "who", "whom", "why", "will", "with", "you", "your",
    "yours", "yourself", "yourselves",
})


# Roughly-common 5000 English words (compressed inline; this is a small "is-it-common" filter)
# For real corpus, expand from references/style/common-5000.txt
COMMON_WORDS: Final[frozenset[str]] = frozenset(STOPWORDS | {
    "people", "make", "good", "first", "want", "look", "use", "many", "say", "small",
    "find", "thing", "place", "case", "part", "right", "great", "way", "work", "also",
    "year", "back", "give", "day", "long", "another", "still", "much", "world", "high",
    "every", "old", "see", "feel", "try", "leave", "call", "young", "different", "ask",
    "next", "follow", "show", "important", "best", "early", "without", "around", "since",
    "tell", "hand", "head", "school", "yet", "today", "later", "though", "almost",
    # ... in production load full common-5000 list
})


@dataclass
class PerplexityReport:
    word_count: int
    unique_word_count: int
    ttr: float                    # type-token ratio
    stopword_ratio: float
    rare_word_ratio: float
    ngram_repetition_rate: float
    avg_word_length: float
    surprise_score: float          # 0-1 combined heuristic
    target_threshold: float = 0.30
    passes: bool = False


def analyze(text: str) -> PerplexityReport:
    plain = strip_markdown(text).lower()
    words = _WORD_RE.findall(plain)
    n = len(words)
    if n == 0:
        return PerplexityReport(
            word_count=0, unique_word_count=0, ttr=0.0,
            stopword_ratio=0.0, rare_word_ratio=0.0,
            ngram_repetition_rate=0.0, avg_word_length=0.0,
            surprise_score=0.0, passes=False,
        )

    unique = set(words)
    ttr = len(unique) / n if n > 0 else 0
    stopword_count = sum(1 for w in words if w in STOPWORDS)
    stopword_ratio = stopword_count / n
    rare_count = sum(1 for w in words if w not in COMMON_WORDS and len(w) >= 4)
    rare_ratio = rare_count / n
    avg_len = sum(len(w) for w in words) / n

    # 3-5 gram repetition rate
    ngram_repeats = 0
    ngram_total = 0
    for k in (3, 4, 5):
        if n < k:
            continue
        grams = [tuple(words[i:i+k]) for i in range(n - k + 1)]
        if not grams:
            continue
        counts = Counter(grams)
        ngram_total += len(grams)
        ngram_repeats += sum(c - 1 for c in counts.values() if c > 1)
    ngram_rep_rate = (ngram_repeats / ngram_total) if ngram_total else 0.0

    # Combined surprise heuristic (higher = more human-like)
    score = (
        0.4 * ttr
        + 0.2 * min(rare_ratio * 3, 1.0)   # rescale; rare typically 0-0.3
        - 0.2 * max(0, stopword_ratio - 0.4)  # penalty if stopwords > 40%
        - 0.2 * ngram_rep_rate
    )
    score = max(0.0, min(1.0, score))

    return PerplexityReport(
        word_count=n,
        unique_word_count=len(unique),
        ttr=round(ttr, 4),
        stopword_ratio=round(stopword_ratio, 4),
        rare_word_ratio=round(rare_ratio, 4),
        ngram_repetition_rate=round(ngram_rep_rate, 4),
        avg_word_length=round(avg_len, 2),
        surprise_score=round(score, 4),
        passes=score > 0.30,
    )


def surprise_score(text: str) -> float:
    """Used by AI-Slop / quality gates."""
    return analyze(text).surprise_score


def main() -> int:
    ap = argparse.ArgumentParser(description="Vocabulary diversity / surprise estimator")
    ap.add_argument("file", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.30)
    args = ap.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    text = args.file.read_text(encoding="utf-8")
    r = analyze(text)
    r.target_threshold = args.threshold
    r.passes = r.surprise_score > args.threshold

    if args.json:
        print(json.dumps(asdict(r), indent=2))
    else:
        verdict = "✓ PASS" if r.passes else "✗ FAIL"
        print(f"File: {args.file}")
        print(f"Words: {r.word_count} ({r.unique_word_count} unique)")
        print(f"  TTR (type-token ratio):   {r.ttr}")
        print(f"  Stopword ratio:           {r.stopword_ratio}")
        print(f"  Rare-word ratio:          {r.rare_word_ratio}")
        print(f"  3-5 gram repetition:      {r.ngram_repetition_rate}")
        print(f"  Avg word length:          {r.avg_word_length}")
        print(f"")
        print(f"Surprise score: {r.surprise_score}  (target > {args.threshold})  {verdict}")
    return 0 if r.passes else 1


if __name__ == "__main__":
    sys.exit(main())
