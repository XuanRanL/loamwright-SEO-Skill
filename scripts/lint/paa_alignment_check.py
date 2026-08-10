#!/usr/bin/env python3
"""PAA alignment lint — the executor the paa-answer-writer SKILL never had (v3.35).

Rule-6 history: `subskills/optimize/paa-answer-writer/SKILL.md` documented a
">=60% of FAQ questions must come from research.paa" contract since v5.0, and
`outline.schema.json :: faq.paa_alignment_pct` carried a self-reported estimate —
but ZERO scripts ever validated either (same orphan-data class as the deprecated
`cta_placement`). This lint measures the alignment ON THE DRAFT (the artifact the
reader sees), not on the outline's self-report.

Evidence basis (2026-07-04 research): PAA prevalence GREW through 2025 (+34.7%
US mobile, seoClarity) and PAA co-occurs with AI Overviews on ~90% of AIO SERPs
(Semrush 10M-keyword study) — Q&A-formatted content aligned to real PAA phrasing
feeds both the PAA box and AI-search answers. See
references/seo/serp-feature-value-2026.md.

What it checks
--------------
1. ALIGNMENT (blocking): every FAQ question in the draft is matched against
   research.json :: paa[] by normalized token overlap. The contract is honest
   about supply: required_matches = min(ceil(0.6 * faq_count), paa_count) — a
   thin PAA harvest can never demand more matches than it offers.
   No-ops (PASS with note) when research.paa has < MIN_PAA_FOR_GATE entries or
   the draft has no FAQ section (mandatory_sections owns that failure).
2. ANSWER LENGTH (advisory): first answer paragraph per question should be
   20-60 words (PAA/AIO extraction window; SKILL target 28-45). Warnings only.

Usage:
    python -m scripts.lint.paa_alignment_check --workspace {task_id} --json
    python -m scripts.lint.paa_alignment_check --workspace {task_id} --json --out {ws}/paa-alignment-lint.json
Exit codes: 0 = passed, 1 = failed.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

MIN_PAA_FOR_GATE = 3          # fewer harvested PAA than this -> alignment not demandable
ALIGNMENT_TARGET = 0.60       # the SKILL/outline contract
ANSWER_WORDS_MIN, ANSWER_WORDS_MAX = 20, 60   # advisory extraction window
_JACCARD_MATCH = 0.5

_FAQ_H2_RE = re.compile(
    r"^##\s+(Frequently Asked Questions|FAQ|Common Questions)\b.*$", re.I | re.M)
_H2_RE = re.compile(r"^##\s+", re.M)
# FAQ question forms the pipeline emits: bold-paragraph (**Q?**) or H3 heading.
_BOLD_Q_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*$", re.M)
_H3_Q_RE = re.compile(r"^###\s+(.+?)\s*(\{#[^}]*\})?\s*$", re.M)
_STOPWORDS = frozenset(
    "a an the is are was were do does did can could should would will i you it "
    "my your our their of in on at to for with and or vs versus what which who "
    "how why when where much many there this that".split())


def _normalize_tokens(q: str) -> set[str]:
    q = re.sub(r"[^a-z0-9\s]", " ", q.lower())
    return {t for t in q.split() if t not in _STOPWORDS and len(t) > 1}


def _questions_match(a: str, b: str) -> bool:
    ta, tb = _normalize_tokens(a), _normalize_tokens(b)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    union = len(ta | tb)
    if union and inter / union >= _JACCARD_MATCH:
        return True
    # containment: a short PAA fully inside a longer FAQ phrasing (or vice versa)
    return inter == len(ta) or inter == len(tb)


def _extract_faq_section(body: str) -> str | None:
    m = _FAQ_H2_RE.search(body)
    if not m:
        return None
    rest = body[m.end():]
    nxt = _H2_RE.search(rest)
    return rest[: nxt.start()] if nxt else rest


def _extract_faq_questions(faq: str) -> list[dict[str, Any]]:
    """Return [{question, answer_words}] in order. Bold-paragraph form wins;
    falls back to H3 questions. A 'question' must contain a '?' or start with a
    question word (avoids counting bold lead-ins like '**Bottom line:**')."""
    out: list[dict[str, Any]] = []
    matches = list(_BOLD_Q_RE.finditer(faq)) or list(_H3_Q_RE.finditer(faq))
    qword = re.compile(r"^(how|what|why|when|where|which|who|can|do|does|is|are|should|will)\b", re.I)
    for i, m in enumerate(matches):
        q = m.group(1).strip()
        if "?" not in q and not qword.match(q):
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(faq)
        answer_block = faq[m.end():end].strip()
        first_para = next((p.strip() for p in answer_block.split("\n\n") if p.strip()), "")
        out.append({"question": q, "answer_words": len(first_para.split()) if first_para else 0})
    return out


def _load_paa(ws: Path) -> list[str]:
    p = ws / "research.json"
    if not p.exists():
        return []
    try:
        research = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    raw = research.get("paa") or research.get("people_also_ask") or []
    paa: list[str] = []
    for item in raw:
        if isinstance(item, str):
            paa.append(item)
        elif isinstance(item, dict):
            q = item.get("question") or item.get("q") or item.get("query")
            if q:
                paa.append(str(q))
    return paa


def check(task_id: str) -> dict[str, Any]:
    ws = PLUGIN_ROOT / "memory" / "workspace" / task_id
    result: dict[str, Any] = {
        "passed": True,
        "task_id": task_id,
        "faq_count": 0,
        "paa_count": 0,
        "matched": 0,
        "required": 0,
        "alignment_pct": None,
        "unmatched_questions": [],
        "answer_length_warnings": [],
        "notes": [],
        "_generated_by": "paa-alignment-check",
    }
    draft = ws / "draft.md"
    if not draft.exists():
        result["passed"] = False
        result["notes"].append("draft.md not found")
        return result
    body = draft.read_text(encoding="utf-8")

    paa = _load_paa(ws)
    result["paa_count"] = len(paa)

    faq = _extract_faq_section(body)
    if faq is None:
        result["notes"].append(
            "no FAQ H2 found — alignment not applicable (mandatory_sections gate "
            "owns FAQ presence)")
        return result

    questions = _extract_faq_questions(faq)
    result["faq_count"] = len(questions)
    if not questions:
        result["notes"].append("FAQ section has no parseable questions (bold-paragraph or H3 form)")
        return result

    # Advisory: answer extraction window
    for q in questions:
        w = q["answer_words"]
        if w and not (ANSWER_WORDS_MIN <= w <= ANSWER_WORDS_MAX):
            result["answer_length_warnings"].append(
                f"{q['question'][:70]!r}: first answer paragraph is {w} words "
                f"(extraction window {ANSWER_WORDS_MIN}-{ANSWER_WORDS_MAX})")

    if len(paa) < MIN_PAA_FOR_GATE:
        result["notes"].append(
            f"research.paa has only {len(paa)} entries (< {MIN_PAA_FOR_GATE}) — "
            "alignment not demandable from a thin harvest; PASS")
        return result

    matched = 0
    for q in questions:
        if any(_questions_match(q["question"], p) for p in paa):
            matched += 1
        else:
            result["unmatched_questions"].append(q["question"])
    required = min(math.ceil(ALIGNMENT_TARGET * len(questions)), len(paa))
    result.update(matched=matched, required=required,
                  alignment_pct=round(matched / len(questions), 2))

    if matched < required:
        result["passed"] = False
        result["notes"].append(
            f"only {matched}/{len(questions)} FAQ questions align with research.paa "
            f"(need >= {required}). Replace unmatched questions with real PAA phrasing "
            f"(keep the ORIGINAL wording — that is what the PAA box and AIO extract). "
            f"Harvested PAA available: {len(paa)}.")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="FAQ <-> research.paa alignment lint")
    ap.add_argument("--workspace", required=True, help="Task ID")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    result = check(args.workspace)
    out = args.out or (PLUGIN_ROOT / "memory" / "workspace" / args.workspace
                       / "paa-alignment-lint.json")
    try:
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        flag = "OK" if result["passed"] else "FAIL"
        print(f"  [{flag}] paa-alignment: {result['matched']}/{result['faq_count']} matched "
              f"(required {result['required']}, paa harvested {result['paa_count']})")
        for n in result["notes"]:
            print(f"    - {n}")
        for u in result["unmatched_questions"][:8]:
            print(f"    - unmatched: {u}")
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
