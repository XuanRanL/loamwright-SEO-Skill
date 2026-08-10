#!/usr/bin/env python3
"""scripts/lint/cta_tone_check.py — CTA Gate 2 (v3.38.0).

Deterministic tone/hype/pressure lint on `cta-draft.json` blocks (heading +
text). This is the gate `subskills/optimize/cta-placement/SKILL.md` had
documented since v3.37 as "NOT YET IMPLEMENTED (honest gap)" — it is now
wired. It is a plain lexicon lint (v1), NOT an LLM judge: it catches
mechanical hype/pressure patterns, not subtler tone drift. Mirrors
`scripts/optimize/cta_diversity_check.py`'s structure (no-op PASS when no
cta-draft.json, {passed, violations[], _generated_by} contract, CLI shape,
--out writer) exactly, per CLAUDE.md Rule 11.

What it checks, per block (heading + text; a `shortcode` field, if present,
is read ONLY to be excluded — tone rules apply to prose, never to a
WooCommerce `[products ...]` shortcode string):

  1. Universal hype lexicon (revolutionary, game-changing, unbeatable, ...).
  2. Pressure phrases (act now, don't miss out, limited time, ...).
  3. Pressure punctuation/format: any `!`; ALL-CAPS words >=4 letters, minus
     a registered acronym allowlist (SEO, GEO, CTA, PLA, ... ).
  4. Per-project `cta-brief.json :: constraints.banned_phrases` (case-
     insensitive substring). A missing/unreadable brief just skips this
     constraint-based check (never a crash / never a false PASS gap).
  5. `constraints.tone == "grief_safe"` adds a grief-unsafe sublexicon (deal,
     bargain, sale, grab, snap up, ...) that reads as commerce-pushy against
     grief content.

Apostrophes are normalized (ASCII `'` and U+2019 both match) before lexicon
matching, since the pipeline sanitizes prose apostrophes to U+2019
(subskills/optimize/cta-placement/SKILL.md) but this lexicon is authored with
ASCII apostrophes for readability.

Usage:
    python -m scripts.lint.cta_tone_check --task-id {tid} --project-slug {slug} --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
WS_ROOT = PLUGIN_ROOT / "memory" / "workspace"

# Registered acronyms that are legitimately ALL-CAPS in this domain's prose —
# these must NEVER trip the ALL-CAPS pressure-punctuation rule.
ALLOWED_ACRONYMS = {
    "SEO", "GEO", "AEO", "PPC", "SERP", "CTA", "LED", "HPS", "PLA", "ABS",
    "PETG", "TPU", "ASA", "OEM", "MOQ", "FAQ", "USA", "B2B", "B2C",
    # v3.38.3 (2026-07-09 project-kilo batch): standards bodies + polymer names are
    # legitimate technical vocabulary, not shouting — "ASTM" tripped the gate twice
    # in one CTA and forced a hand-edit. 3-letter forms (ISO, COA, TDS, FDM, MJF,
    # DLS, RAL) never match the >=4 regex and need no entry here.
    "ASTM", "ANSI", "NIST", "PEBA", "PEEK", "PEKK", "CIELAB", "ROHS",
    "HDPE", "LDPE", "PVDF", "PCTG",
    # v3.39.1 (2026-07-16 project-echo regional-city batch): government-agency acronyms
    # are legitimate regulatory vocabulary, not shouting — "CBSA" (Canada Border
    # Services Agency) appears throughout every project-echo regional-city CTA and body
    # since the whole series cites CBSA personal-exemption rules.
    "CBSA", "CRA", "TVPA", "TPAPLR",
    # v3.42.3 (2026-08-04 project-alpha joint-supplement batch): veterinary and
    # animal-health regulatory acronyms. "NASC" (National Animal Supplement
    # Council) failed the gate on the very first CTA of this project — its
    # Quality Seal is the honest purchase criterion every project-alpha supplement
    # article points to, so it recurs in body and CTA copy across the vertical.
    # 3-letter forms (FDA, CVM, EPA, OFA, AKC, AVMA is 4) never match the >=4
    # regex except where noted.
    "NASC", "NAERS", "AAFCO", "AVMA", "ACVS", "AAHA", "WSAVA", "CAPC",
    "JAVMA", "VCPR", "USDA",
}

HYPE_LEXICON = [
    "revolutionary", "game-changing", "game changer", "unbeatable",
    "world-class", "best-in-class", "once-in-a-lifetime", "jaw-dropping",
    "mind-blowing", "guaranteed results", "#1", "number one",
]

PRESSURE_PHRASES = [
    "act now", "don't miss out", "don't wait", "limited time", "hurry",
    "last chance", "before it's too late", "only today", "while supplies last",
]

# grief_safe-only sublexicon: these read as commerce-pushy against grief
# content even though they are unremarkable in ordinary marketing copy.
GRIEF_UNSAFE_LEXICON = [
    "deal", "bargain", "sale", "discount", "grab", "snap up", "treat yourself",
    "don't miss", "buy now", "shop now", "order today", "perfect gift",
]

_ALL_CAPS_RE = re.compile(r"\b[A-Z]{4,}\b")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_apostrophes(text: str) -> str:
    """Collapse the pipeline's sanitized U+2019 apostrophe back to ASCII `'`
    so lexicon phrases authored with ASCII apostrophes (e.g. "don't miss
    out") match copy the CTA injector has already sanitized."""
    return text.replace("’", "'")


def _word_bounded_pattern(phrase: str) -> re.Pattern[str]:
    """Compile a case-insensitive pattern that matches `phrase` as a whole
    word/phrase — never as a substring of a longer word (so "sale" does not
    trip on "sales", "deal" does not trip on "dealer"). A plain `\\b` breaks
    on phrases that start/end with a non-alnum character (e.g. "#1", where
    the character right before the boundary is itself non-word), so the
    boundary is built from an explicit alnum lookaround only on the sides
    that actually start/end on an alnum character."""
    escaped = re.escape(phrase)
    prefix = r"(?<![A-Za-z0-9])" if phrase[:1].isalnum() else ""
    suffix = r"(?![A-Za-z0-9])" if phrase[-1:].isalnum() else ""
    return re.compile(prefix + escaped + suffix, re.IGNORECASE)


def _phrase_hits(text: str, lexicon: list[str]) -> list[str]:
    norm = _normalize_apostrophes(text)
    return [phrase for phrase in lexicon if _word_bounded_pattern(phrase).search(norm)]


def _all_caps_hits(text: str) -> list[str]:
    return [w for w in _ALL_CAPS_RE.findall(text) if w not in ALLOWED_ACRONYMS]


def _load_draft(task_id: str) -> dict[str, Any] | None:
    p = WS_ROOT / task_id / "cta-draft.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _load_brief(task_id: str) -> dict[str, Any] | None:
    p = WS_ROOT / task_id / "cta-brief.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _constraints(task_id: str) -> dict[str, Any]:
    """Read cta-brief.json :: constraints, tolerating a missing/unreadable/
    malformed brief by skipping constraint-based checks (banned_phrases,
    grief_safe) rather than crashing the gate — cta-draft.json, not
    cta-brief.json, is this gate's mandatory input."""
    brief = _load_brief(task_id)
    if not brief:
        return {}
    constraints = brief.get("constraints")
    return constraints if isinstance(constraints, dict) else {}


def _add_violation(result: dict[str, Any], *, rule: str, placement: str,
                    matched_text: str, detail: str) -> None:
    result["passed"] = False
    result["violations"].append({
        "rule": rule, "placement": placement,
        "matched_text": matched_text, "detail": detail,
    })


def check_tone(task_id: str, project_slug: str) -> dict[str, Any]:
    draft = _load_draft(task_id)
    result: dict[str, Any] = {
        "passed": True, "task_id": task_id, "project_slug": project_slug,
        "violations": [], "_generated_by": "cta-tone-check",
        "generated_at": _now_iso(),
    }
    if not draft:
        result["_note"] = "no cta-draft.json (legacy static path, gate is a no-op PASS)"
        return result

    constraints = _constraints(task_id)
    banned_phrases = constraints.get("banned_phrases") or []
    if not isinstance(banned_phrases, list):
        banned_phrases = []
    tone = constraints.get("tone")

    for placement, block in (draft.get("blocks") or {}).items():
        heading = str(block.get("heading", ""))
        text = str(block.get("text", ""))
        # shortcode (ecommerce blocks) is intentionally NEVER read here — tone
        # rules apply to prose the writer authored, not the WooCommerce
        # [products ...] shortcode string copied verbatim from the brief.
        content = f"{heading}\n{text}"

        for phrase in _phrase_hits(content, HYPE_LEXICON):
            _add_violation(result, rule="hype_lexicon", placement=placement,
                            matched_text=phrase,
                            detail=f"hype phrase '{phrase}' reads as an inflated marketing "
                                   f"claim rather than evidence-based CTA copy")

        for phrase in _phrase_hits(content, PRESSURE_PHRASES):
            _add_violation(result, rule="pressure_phrase", placement=placement,
                            matched_text=phrase,
                            detail=f"pressure phrase '{phrase}' manufactures urgency the "
                                   f"article content does not support")

        # Markdown image syntax `![alt](url)` carries a structural `!` that is
        # NOT hype punctuation — the cta-writer's avatar feature (v3.37,
        # cta-brief.json :: matched_team_member.photo_media_url) emits exactly
        # this. Without the exemption every avatar-bearing CTA hard-fails Gate 2
        # (caught live on the 2026-07-08 loamwright weekly digest). Strip image
        # syntax first; any REMAINING `!` is genuine pressure punctuation.
        content_sans_images = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", content)
        if "!" in content_sans_images:
            _add_violation(result, rule="pressure_punctuation", placement=placement,
                            matched_text="!",
                            detail="exclamation mark reads as pressure/hype punctuation; use a period")

        for word in _all_caps_hits(content):
            _add_violation(result, rule="all_caps", placement=placement,
                            matched_text=word,
                            detail=f"ALL-CAPS word '{word}' reads as shouting; use sentence case")

        norm_content_lower = _normalize_apostrophes(content).lower()
        for raw_phrase in banned_phrases:
            phrase = str(raw_phrase).strip()
            if phrase and _normalize_apostrophes(phrase).lower() in norm_content_lower:
                _add_violation(result, rule="banned_phrase", placement=placement,
                                matched_text=phrase,
                                detail=f"project-banned phrase '{phrase}' present in CTA copy")

        if tone == "grief_safe":
            for phrase in _phrase_hits(content, GRIEF_UNSAFE_LEXICON):
                _add_violation(result, rule="grief_unsafe", placement=placement,
                                matched_text=phrase,
                                detail=f"'{phrase}' reads as commerce-pushy against this "
                                       f"project's grief-safe tone")

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="CTA Gate 2 hype/pressure/tone lint")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--project-slug", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", help="also write the JSON result here")
    args = ap.parse_args()

    result = check_tone(args.task_id, args.project_slug)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"cta_tone_check: {'PASS' if result['passed'] else 'FAIL'} "
              f"({len(result['violations'])} violation(s))")
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
