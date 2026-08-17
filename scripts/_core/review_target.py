"""scripts/_core/review_target.py — single source of truth for the reviewer score target.

Why this module exists (2026-08-17): the independent-reviewer pass/fail threshold was
spelled in FOUR places that disagreed — schemas/state.schema.json declared
``"default": 95`` (a documentation-only annotation nothing at runtime applies),
orchestrator.py and pre_publish_gate.py each carried their own ``or 80`` literal, and
skills/seo-blog/SKILL.md documented 80. A batch brief author consulted the schema (the
natural reference), copied 95 into ``brief.quality_target_score``, and burned six
reviewer/repair rounds against a bar the fleet never actually operates at. Same
disease as Rule 14's table: two places depend on one fact and disagree about how that
fact is spelled.

Contract:
- ``brief.quality_target_score`` absent / null / 0  →  DEFAULT_REVIEW_TARGET (80).
  (Falsy-means-default is deliberate and matches both historical call sites: a target
  of 0 must never silently disable the gate — "never silently downgrade quality
  target", skills/seo-blog/SKILL.md.)
- The returned target is always >= 1 (pre_publish_gate's historical ``max(t, 1)``).
- schemas/state.schema.json's declared default MUST equal DEFAULT_REVIEW_TARGET —
  pinned by tests/test_review_target_single_source.py.

Both consumers (scripts/pipeline/orchestrator.py :: _content_gate_reason and
scripts/pipeline/pre_publish_gate.py :: _reviewer_target) import from here; do not
reintroduce a local literal at a call site.
"""
from __future__ import annotations

from typing import Any, Final, Mapping

DEFAULT_REVIEW_TARGET: Final[int] = 80


def review_target(state: Mapping[str, Any]) -> int:
    """Resolve the reviewer score target from a loaded state.json dict."""
    brief = state.get("brief") or {}
    try:
        t = int(brief.get("quality_target_score") or DEFAULT_REVIEW_TARGET)
    except (TypeError, ValueError):
        return DEFAULT_REVIEW_TARGET
    return max(t, 1)
