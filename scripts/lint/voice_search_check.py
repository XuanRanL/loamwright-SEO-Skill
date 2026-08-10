"""scripts/lint/voice_search_check.py — Voice-search optimization check.

Used by `subskills/optimize/voice-search-optimizer/` when `state.brief.voice_search_targets`
includes google-assistant / chatgpt-voice / siri / alexa.

Voice search content patterns:
  1. Question-format H2/H3 headings (5W1H + How)
  2. 28-45 word direct answers immediately after question
  3. Conversational tone (contractions, "you", direct address)
  4. Featured Snippet-friendly structure
  5. Local intent markers ("near me", "in {city}")
  6. Time/duration mentions (how long, how often)

CLI:
    python -m scripts.lint.voice_search_check --input draft.md --json
    python -m scripts.lint.voice_search_check --stdin
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


# Question starters
QUESTION_STARTERS = [
    "what", "when", "where", "who", "why", "how",
    "can", "does", "is", "are", "should", "do", "did", "will", "would",
]
QUESTION_RE = re.compile(
    r"^(?:#{2,4}\s+)?(?:" + "|".join(QUESTION_STARTERS) + r")\b",
    re.IGNORECASE | re.MULTILINE,
)

# H2/H3 detection
H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
H3_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)

# Contractions (signal of conversational tone)
CONTRACTIONS_RE = re.compile(
    r"\b(?:it's|don't|won't|can't|isn't|aren't|wasn't|weren't|haven't|hasn't|"
    r"doesn't|didn't|wouldn't|shouldn't|you're|you've|you'll|we're|we've|"
    r"they're|that's|here's|there's|what's|where's|how's)\b",
    re.IGNORECASE,
)

# Direct address
DIRECT_ADDRESS_RE = re.compile(r"\byou(?:r|rs|rself)?\b", re.IGNORECASE)

# Local intent
LOCAL_INTENT_RE = re.compile(
    r"\b(?:near\s+me|in\s+(?:your\s+)?(?:city|town|area|neighborhood)|"
    r"close\s+by|nearby|local|in\s+\w+(?:burgh|town|ville|city))\b",
    re.IGNORECASE,
)

# Duration markers
DURATION_RE = re.compile(
    r"\b(?:how\s+long|how\s+often|how\s+much|how\s+many|"
    r"\d+\s*(?:seconds|minutes|hours|days|weeks|months|years)|"
    r"takes?\s+about|in\s+just\s+\d+)\b",
    re.IGNORECASE,
)


@dataclass
class VoiceSearchReport:
    total_h2_h3: int = 0
    question_headings: int = 0
    question_pct: float = 0.0
    h2_with_answer_block: int = 0
    answer_blocks_in_range: int = 0       # 28-45 words
    contractions_count: int = 0
    direct_address_count: int = 0
    local_intent_count: int = 0
    duration_markers: int = 0
    voice_search_score: int = 0           # 0-100
    verdict: str = ""                      # ready | partial | not-ready
    recommendations: list[str] = field(default_factory=list)


def _words(text: str) -> int:
    return len([w for w in re.split(r"\s+", text) if w])


def check_voice_search(text: str) -> VoiceSearchReport:
    h2_headings = H2_RE.findall(text)
    h3_headings = H3_RE.findall(text)
    all_headings = h2_headings + h3_headings

    question_headings = sum(
        1 for h in all_headings
        if any(h.strip().lower().startswith(s) for s in QUESTION_STARTERS)
    )

    # Find H2 + first paragraph after
    h2_with_answer = 0
    answer_in_range = 0
    h2_split = re.split(r"^##\s+", text, flags=re.MULTILINE)
    for section in h2_split[1:]:
        # First paragraph
        lines = section.split("\n", 1)
        if len(lines) < 2:
            continue
        body = lines[1].strip()
        first_para = body.split("\n\n", 1)[0]
        wc = _words(first_para)
        if wc > 0:
            h2_with_answer += 1
            if 28 <= wc <= 60:   # 28-45 ideal, ≤60 acceptable
                answer_in_range += 1

    contractions = len(CONTRACTIONS_RE.findall(text))
    direct_address = len(DIRECT_ADDRESS_RE.findall(text))
    local_intent = len(LOCAL_INTENT_RE.findall(text))
    duration = len(DURATION_RE.findall(text))

    total_words = _words(text)

    # Composite score
    qpct = question_headings / max(1, len(all_headings)) * 100
    answer_pct = answer_in_range / max(1, h2_with_answer) * 100 if h2_with_answer else 0
    contraction_rate = contractions / max(1, total_words) * 100
    address_rate = direct_address / max(1, total_words) * 100

    score = int(
        min(qpct, 60) * 0.30 +           # question headings 30%
        min(answer_pct, 80) * 0.30 +     # 28-45w answers 30%
        min(contraction_rate * 10, 20) * 0.20 +  # contractions 20%
        min(address_rate * 5, 30) * 0.10 +      # direct address 10%
        min(duration * 5, 10) * 0.05 +         # duration markers 5%
        min(local_intent * 5, 10) * 0.05         # local intent 5%
    )

    if score >= 70:
        verdict = "ready"
    elif score >= 40:
        verdict = "partial"
    else:
        verdict = "not-ready"

    recommendations = []
    if qpct < 40:
        recommendations.append(f"Only {qpct:.0f}% of headings are questions; convert 5W1H statements to questions")
    if answer_pct < 50 and h2_with_answer:
        recommendations.append(f"Only {answer_in_range}/{h2_with_answer} H2 have 28-60w answer blocks; tighten others")
    if contraction_rate < 0.3:
        recommendations.append("Few contractions; voice search content is conversational — use it's/don't/you're")
    if direct_address == 0:
        recommendations.append("No direct 'you' address; voice search assistants prefer second-person")
    if duration == 0:
        recommendations.append("No duration markers; voice queries often include 'how long', 'how often'")

    return VoiceSearchReport(
        total_h2_h3=len(all_headings),
        question_headings=question_headings,
        question_pct=round(qpct, 1),
        h2_with_answer_block=h2_with_answer,
        answer_blocks_in_range=answer_in_range,
        contractions_count=contractions,
        direct_address_count=direct_address,
        local_intent_count=local_intent,
        duration_markers=duration,
        voice_search_score=score,
        verdict=verdict,
        recommendations=recommendations,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Voice search optimization check")
    ap.add_argument("--input", type=Path)
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.stdin:
        text = sys.stdin.read()
    elif args.input:
        text = args.input.read_text(encoding="utf-8")
    else:
        print("Need --input or --stdin", file=sys.stderr)
        return 2

    report = check_voice_search(text)

    if args.json:
        print(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    else:
        print(f"Voice search score: {report.voice_search_score}/100 ({report.verdict.upper()})")
        print(f"  Headings:        {report.question_headings}/{report.total_h2_h3} are questions ({report.question_pct}%)")
        print(f"  Answer blocks:   {report.answer_blocks_in_range}/{report.h2_with_answer_block} in 28-60w range")
        print(f"  Contractions:    {report.contractions_count}")
        print(f"  Direct address:  {report.direct_address_count} 'you' mentions")
        print(f"  Local intent:    {report.local_intent_count}")
        print(f"  Duration:        {report.duration_markers}")
        if report.recommendations:
            print("\nRecommendations:")
            for r in report.recommendations:
                print(f"  • {r}")
    return 0 if report.voice_search_score >= 70 else 1


if __name__ == "__main__":
    sys.exit(main())
