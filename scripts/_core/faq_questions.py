r"""scripts/_core/faq_questions.py — ONE definition of "a FAQ question in a draft".

History (2026-08-12 release audit). v3.42.8 made the FAQ-question regex PAIRS in
``scripts/validate/core_eeat_scorer.py`` and ``scripts/lint/paa_alignment_check.py``
byte-identical, but left the COMPOSITION divergent: paa additionally filtered out
candidates that are not question-shaped (no ``?`` and no leading question word),
while the scorer's ``_count_faq_questions`` counted every standalone bold line.
Measured 6 vs 3 on one real FAQ — CORE-EEAT C10 flipped from unpassable (always 0,
the v3.42.8 bug) to too-easily-passable (>= 5 satisfied by bold lead-ins like
``**Bottom line:**`` that are not questions). Rule 12: two checkers reading the
same FAQ must not disagree; the only arrangement that stays agreed is both calling
the ONE extraction function below.

Contract (canonical = the established paa_alignment_check behavior):

* Two question forms, the ones this pipeline's writers emit: standalone
  bold-paragraph (``**Question?**``) or H3 heading (``### Question?``, tolerating
  the ``{#anchor}`` suffix assemble.py injects).
* Bold form WINS: the fallback to H3 happens only when the section has no
  standalone bold lines AT ALL — the form choice is made BEFORE the
  question-shape filter (an H3-form FAQ may legitimately contain bold lines
  inside its answers, and a bold-form FAQ may sit under statement H3s).
* The QUESTION-SHAPE filter is part of the contract: a candidate must contain
  ``?`` or start with a question word. That is what keeps bold lead-ins and
  statement-H3s (``### Overview of costs``) from counting as FAQ entries.

Guard: ``tests/test_v3428_scorer_and_media_title_cures.py::``
``test_c10_agrees_with_paa_alignment_check_on_the_same_faq`` drives BOTH callers'
production entry points on the same fixtures.
"""
from __future__ import annotations

import re
from typing import Any

from scripts._core.heading_anchor import ANCHOR_FRAGMENT

# FAQ question forms the pipeline emits: bold-paragraph (**Q?**) or H3 heading.
BOLD_Q_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*$", re.M)
H3_Q_RE = re.compile(r"^###\s+(.+?)\s*(" + ANCHOR_FRAGMENT + r")?\s*$", re.M)

_QWORD_RE = re.compile(
    r"^(how|what|why|when|where|which|who|can|do|does|is|are|should|will)\b", re.I
)


def is_question_shaped(text: str) -> bool:
    """True when a heading/bold candidate is actually a question.

    Must contain a ``?`` or start with a question word — this filter is what
    keeps bold lead-ins like ``**Bottom line:**`` out of the FAQ count.
    """
    return "?" in text or bool(_QWORD_RE.match(text))


def extract_faq_questions(faq_body: str) -> list[dict[str, Any]]:
    """Return ``[{question, answer_words}]`` in draft order.

    ``answer_words`` is the word count of the first non-empty paragraph between
    this question and the next candidate (paa_alignment_check's extraction-window
    advisory); 0 when no answer paragraph exists.
    """
    out: list[dict[str, Any]] = []
    matches = list(BOLD_Q_RE.finditer(faq_body)) or list(H3_Q_RE.finditer(faq_body))
    for i, m in enumerate(matches):
        q = m.group(1).strip()
        if not is_question_shaped(q):
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(faq_body)
        answer_block = faq_body[m.end():end].strip()
        first_para = next(
            (p.strip() for p in answer_block.split("\n\n") if p.strip()), ""
        )
        out.append(
            {
                "question": q,
                "answer_words": len(first_para.split()) if first_para else 0,
            }
        )
    return out


def count_faq_questions(faq_body: str) -> int:
    """Question count both C10 and the PAA lint must agree on."""
    return len(extract_faq_questions(faq_body))
