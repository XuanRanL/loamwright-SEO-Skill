"""scripts/_core/image_policy.py — single source of truth for per-article image count.

Why this module exists (2026-08-17, operator decision): the default was raised
4 → 6 (1 cover + 5 section images; ≈$1.67/image at 4K, so ≈$10/article) to hit
one visual anchor per ~900 words on a 5,000-word article, and the ceiling was
raised 4 → 8 for briefs that explicitly want more. "4" had been spelled as a
literal in the schema, the image-prompt-designer dispatch_prompt, both designer
instruction layers, the cost estimator's per-format rows, and five more doc
layers — the review-target lesson (scripts/_core/review_target.py) one contract
over. All of them now resolve through here; the schema annotation is pinned by
tests/test_image_count_policy.py.

Contract:
- ``brief.image_count`` absent / null / unparseable → DEFAULT_IMAGE_COUNT.
- 0 is a REAL value (a no-image article is a legitimate explicit choice, e.g.
  text-only refreshes) — unlike review_target, falsy does NOT mean default here;
  only absence/garbage does.
- Values above MAX_IMAGE_COUNT clamp to MAX_IMAGE_COUNT (schema validation
  rejects them at write_state time anyway; the clamp is defense in depth for
  hand-built states).
- The count includes the cover: image_count 6 = 1 featured cover (never inlined
  on no_inline projects) + 5 inline section images. inline_image_count() is the
  "how many sections get image_slot: true" number the outline-architect uses.
"""
from __future__ import annotations

from typing import Any, Final, Mapping

DEFAULT_IMAGE_COUNT: Final[int] = 6
MAX_IMAGE_COUNT: Final[int] = 8


def resolve_image_count(state: Mapping[str, Any]) -> int:
    """Resolve the article's total image count (cover included) from state.json."""
    brief = state.get("brief") or {}
    raw = brief.get("image_count")
    if raw is None:
        return DEFAULT_IMAGE_COUNT
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_IMAGE_COUNT
    if n < 0:
        return DEFAULT_IMAGE_COUNT
    return min(n, MAX_IMAGE_COUNT)


def inline_image_count(state: Mapping[str, Any]) -> int:
    """Section images only (total minus the cover, floor 0)."""
    return max(0, resolve_image_count(state) - 1)
