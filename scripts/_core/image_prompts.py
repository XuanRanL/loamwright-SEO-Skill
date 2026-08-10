"""scripts/_core/image_prompts.py — single source of truth for parsing image-prompts.json.

The `image-prompt-designer` agent is a free-form LLM `Write`; it inconsistently emits
`prompts` as a JSON array (the documented shape) OR as an object keyed by slot_id
(`{"cover": {...}, "section_1": {...}}`). Before this module, six consumers each
hand-rolled their own unwrap and three of them mis-handled the dict shape SILENTLY
(render_data_charts rendered zero charts, real_brand_image_pipeline sourced zero
photos, image_placeholder_check + pre_publish_gate.check_images went blind and the
publish gate passed vacuously). The 2026-06-29 batch surfaced this because
assemble.py happened to CRASH on the dict shape (the loud one of the six).

This module collapses all of those parsers into one tested normalizer. EVERY consumer
of image-prompts.json MUST go through `normalize_image_prompts()` / `load_image_prompts()`
so a shape drift can never again be silently mishandled at one call-site but not another.

See: feedback_silent_no_op_through_exception_swallow.md (same disease — N call-sites,
each with its own ad-hoc discipline) and reference_loamwright_batch_2026_06_29.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Wrapper keys under which a list/dict of prompt entries may live. Order matters:
# the first key present wins.
_WRAPPER_KEYS = ("prompts", "image_prompts", "images", "requests", "slots", "image_slots")


def _dicts_only(seq: Any) -> list[dict[str, Any]]:
    return [x for x in seq if isinstance(x, dict)] if isinstance(seq, list) else []


def _mapping_to_list(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    """{slot_id: {spec...}} -> [{slot_id, spec...}], injecting slot_id from the key."""
    out: list[dict[str, Any]] = []
    for slot_id, spec in mapping.items():
        if isinstance(spec, dict):
            entry = dict(spec)
            entry.setdefault("slot_id", slot_id)
            out.append(entry)
    return out


def normalize_image_prompts(data: Any) -> list[dict[str, Any]]:
    """Normalize ANY image-prompts.json shape into a ``list[dict]`` where every entry
    carries a ``slot_id``.

    Handles: a bare list; ``{"prompts": [...]}`` / ``images`` / ``requests`` / etc.;
    ``{"prompts": {slot_id: {...}}}`` (the 2026-06-29 regression shape); and a bare
    top-level mapping ``{slot_id: {...}}`` with no metadata keys. Anything else -> ``[]``.
    """
    if data is None:
        return []
    if isinstance(data, list):
        return _dicts_only(data)
    if isinstance(data, dict):
        for key in _WRAPPER_KEYS:
            if key in data:
                value = data[key]
                if isinstance(value, list):
                    return _dicts_only(value)
                if isinstance(value, dict):
                    return _mapping_to_list(value)
                return []
        # No wrapper key. If EVERY value is a dict, treat the whole object as a bare
        # {slot_id: {...}} mapping (the pure dict-keyed shape an LLM sometimes emits).
        if data and all(isinstance(v, dict) for v in data.values()):
            return _mapping_to_list(data)
    return []


def is_cover_slot(slot_id: str | None) -> bool:
    """True when a slot_id denotes the cover/featured-image slot.

    Single source of truth (2026-07-01): real workspaces name the cover ``cover``,
    ``slot-cover`` or ``hero-cover`` — exact ``== "cover"`` checks missed the
    variants (the 2026-06-29 project-echo miss, previously fixed only inside
    real_brand_image_pipeline). Consumers: openai_image_pipeline (forces the cover
    entry featured in images.json), wp_publisher (featured_media fallback),
    real_brand_image_pipeline.
    """
    if not slot_id:
        return False
    s = str(slot_id).strip().lower()
    return s in ("cover", "slot-cover") or s.endswith("-cover")


def load_image_prompts(source: Any) -> list[dict[str, Any]]:
    """Load + normalize image prompts.

    ``source`` may be: already-loaded data (list/dict); a file path (str/Path) to
    image-prompts.json; or a workspace directory (str/Path) containing it. Missing /
    unreadable -> ``[]``. Never raises.
    """
    if isinstance(source, (list, dict)):
        return normalize_image_prompts(source)
    try:
        p = Path(source)
    except TypeError:
        return []
    if p.is_dir():
        p = p / "image-prompts.json"
    if not p.exists():
        return []
    try:
        return normalize_image_prompts(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []
