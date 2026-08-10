"""Fact-check verdict contract — the ONE classifier every gate shares.

History (2026-08-02 root cure). The pass whitelist was introduced consumer-side
in v3.9.0 (``pre_publish_gate``: closed-world, case-sensitive) and never
propagated to any producer layer (Rule 11): ``agents/fact-checker.md`` taught a
different enum, the dispatch prompt taught none, and no schema or hook checked
the field at write time. Meanwhile the orchestrator content gate (v3.35.3) used
an open-world exact-match denylist with ``.upper()``. The two gates disagreed in
BOTH directions (Rule 12):

- a benign novel string (``issues_fixed``) passed the orchestrator and failed
  pre-publish — hit live 2026-08-02; 7 of 338 historical fact-check artifacts
  (2.1%) carried out-of-enum verdicts, so this was a base rate, not a one-off;
- a hard veto phrased ``BLOCKED - DO NOT PUBLISH`` passed the orchestrator's
  exact-match denylist and was recordable as a COMPLETED stage.

Canonical producer enum (mirrored in ``agents/fact-checker.md``, the
orchestrator dispatch prompt, ``subskills/build/fact-check-and-citation``,
``skills/seo-blog/SKILL.md`` and ``schemas/fact-check.schema.json`` — Rule 11
fan-out):

    CLEAN | CLEAN_WITH_NOTES | FIX_REQUIRED | BLOCK_PUBLISH

Consumers additionally accept unambiguous legacy pass aliases seen in history.
Anything else FAILS CLOSED at every gate.
"""
from __future__ import annotations

CANONICAL_ENUM = "CLEAN | CLEAN_WITH_NOTES | FIX_REQUIRED | BLOCK_PUBLISH"

PASS_VERDICTS: frozenset[str] = frozenset({
    "CLEAN",
    "CLEAN_WITH_NOTES",
    # legacy consumer-side aliases (v3.9.0 whitelist) kept for old artifacts
    "PASS",
    "APPROVED",
    # unambiguous alias: problems were found and fixed in place (2026-08-02)
    "ISSUES_FIXED",
})

BLOCK_VERDICTS: frozenset[str] = frozenset({
    "FIX_REQUIRED",
    "BLOCK_PUBLISH",
    "CORRECTIONS_NEEDED",
    "REJECTED",
    "FAIL",
    "BLOCKED",
    "REVISE_BEFORE_PUBLISH",
})

# Substring tripwires: a verdict CONTAINING any of these is blocking even when
# the exact string is novel ("BLOCKED - DO NOT PUBLISH", "FAIL_HARD - ...").
# Checked AFTER the exact pass set, so e.g. a hypothetical "PASS" can never be
# demoted by a substring.
_BLOCK_SUBSTRINGS: tuple[str, ...] = (
    "BLOCK",
    "FAIL",
    "REJECT",
    "DO NOT PUBLISH",
    "FIX_REQUIRED",
    "CORRECTIONS",
)


def normalize(verdict: object) -> str:
    """Uppercase, stripped string form of any verdict value (None-safe)."""
    return str(verdict or "").strip().upper()


def classify(verdict: object) -> str:
    """Classify a fact-check verdict: ``'pass' | 'block' | 'unknown'``.

    ``'unknown'`` MUST fail closed at every consumer — an unrecognized verdict
    means the producer broke the contract, not that the article is clean.
    """
    v = normalize(verdict)
    if not v:
        return "unknown"
    if v in PASS_VERDICTS:
        return "pass"
    if v in BLOCK_VERDICTS or any(s in v for s in _BLOCK_SUBSTRINGS):
        return "block"
    return "unknown"
