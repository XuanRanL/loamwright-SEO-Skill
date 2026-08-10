"""
scripts/validate/ai_slop_score.py — AI-Slop composite score.

Formula (per humanizer-skill / references/style/ai-tells-43.md):

    score = 4 × patterns_hit              # 43 AI patterns count
          + 25 × (1 − burstiness_norm)    # sentence-length variance (0 → +25)
          + 15 × vocab_blacklist_ratio    # banned-word density
    clamped [0, 100]

Bands:
    0-20   Pristine (pass v3.2 quality gate)
    21-40  Mostly human
    41-60  Mixed
    61-80  AI-leaning
    81-100 Pure AI smell

Pass condition: score < 20

Used by:
  - quality-gate-ai-slop skill (one of 4 quality gates)
  - section-drafter self-check
  - humanizer convergence loop
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.lint.ai_tells_detector import lint as ai_tells_lint, patterns_hit_count
from scripts.lint.banned_word_lint import lint as banned_lint, load_banned_words
from scripts.lint.em_dash_audit import em_dash_count
from scripts.lint.sentence_variance import burstiness_normalized, short_sentence_ratio
from scripts.lint._text_utils import count_words


@dataclass
class AISlopReport:
    score: float                            # 0-100
    patterns_hit: int                       # distinct pattern types (P1..P43)
    burstiness_normalized: float            # stddev/mean of sentence lengths
    vocab_blacklist_ratio: float            # banned words / total words
    em_dash_count: int                      # zero-tolerance check
    band: str                                # Pristine / Mostly human / Mixed / AI-leaning / Pure AI smell
    passes: bool                             # True if score < 20 AND em_dash == 0
    formula_breakdown: dict


# Staccato penalty calibration (2026-06-30). Empirically tuned against a shipped-draft
# corpus whose <=5-word sentence ratio maxed at ~0.134; 0.15 leaves headroom so normal /
# format-mandated content (bullets, table cells, terse-but-real prose) gets ZERO penalty.
STACCATO_THRESHOLD = 0.15
STACCATO_WEIGHT = 100.0
STACCATO_CAP = 15.0


def compute(text: str, *, threshold: float = 20.0) -> AISlopReport:
    # Component 1: distinct AI patterns hit
    patterns = patterns_hit_count(text)

    # Component 2: burstiness (humanizer formula expects >0.30)
    bn = burstiness_normalized(text)

    # Component 3: banned-word density
    banned_words = load_banned_words()
    banned_hits = banned_lint(text, banned_words)
    total_words = count_words(text)
    vocab_ratio = (len(banned_hits) / total_words) if total_words else 0

    em_dashes = em_dash_count(text)

    # Compute score (weights reduced from v3.7: burstiness 25→15, vocab 15→10)
    # SEO articles have format-mandated uniform structures (Key Takeaways bullets,
    # FAQ answers, table rows) that inflate burstiness penalty without indicating AI
    p_component = 4 * patterns
    b_component = 15 * (1 - min(bn, 1.0))   # reduced from 25 — uniform FAQ/bullets are format, not AI
    v_component = 10 * min(vocab_ratio, 1.0) # reduced from 15 — "comprehensive" is sometimes needed

    # Component 4: staccato penalty (2026-06-30). b_component is gameable — stacking
    # ultra-short fragment-closers ("Pure leakage.") inflates the CV and drops b_component,
    # while a reviewer reads that staccato as the top AI tell. Re-add points when the
    # <=5-word sentence ratio exceeds the natural rate. One-sided + capped, so it is ZERO for
    # normal content and can never destabilize a legitimately-terse draft by > STACCATO_CAP.
    frag_ratio = short_sentence_ratio(text, max_words=5)
    s_component = min(STACCATO_CAP, STACCATO_WEIGHT * max(0.0, frag_ratio - STACCATO_THRESHOLD))

    score = p_component + b_component + v_component + s_component
    score = max(0.0, min(100.0, score))

    # Determine band
    if score <= 20:
        band = "Pristine"
    elif score <= 40:
        band = "Mostly human"
    elif score <= 60:
        band = "Mixed"
    elif score <= 80:
        band = "AI-leaning"
    else:
        band = "Pure AI smell"

    passes = score < threshold and em_dashes == 0

    return AISlopReport(
        score=round(score, 2),
        patterns_hit=patterns,
        burstiness_normalized=round(bn, 4),
        vocab_blacklist_ratio=round(vocab_ratio, 5),
        em_dash_count=em_dashes,
        band=band,
        passes=passes,
        formula_breakdown={
            "patterns_component": round(p_component, 2),
            "burstiness_component": round(b_component, 2),
            "vocab_component": round(v_component, 2),
            "staccato_component": round(s_component, 2),
            "short_sentence_ratio": round(frag_ratio, 4),
        },
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="AI-Slop composite score")
    ap.add_argument("file", type=Path)
    ap.add_argument("--threshold", type=float, default=20.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"Not found: {args.file}", file=sys.stderr)
        return 2
    text = args.file.read_text(encoding="utf-8")
    r = compute(text, threshold=args.threshold)

    if args.json:
        print(json.dumps(asdict(r), indent=2, ensure_ascii=False))
    else:
        verdict = "✓ PASS" if r.passes else "✗ FAIL"
        print(f"File: {args.file}")
        print(f"AI-Slop score: {r.score} / 100  ({r.band})")
        print(f"Threshold: {args.threshold}")
        print()
        print(f"Breakdown:")
        print(f"  patterns_hit ({r.patterns_hit} × 4):                    +{r.formula_breakdown['patterns_component']}")
        print(f"  burstiness penalty (15 × (1 - {r.burstiness_normalized})):   +{r.formula_breakdown['burstiness_component']}")
        print(f"  vocab penalty (10 × {r.vocab_blacklist_ratio}):          +{r.formula_breakdown['vocab_component']}")
        print(f"                                          = {r.score}")
        print()
        print(f"Em-dash count: {r.em_dash_count}  (zero-tolerance)")
        print(f"\nVerdict: {verdict}")

    return 0 if r.passes else 1


if __name__ == "__main__":
    sys.exit(main())
