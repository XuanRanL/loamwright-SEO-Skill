r"""scripts/_core/heading_anchor.py — one definition of the heading-anchor rules.

The regex ``\s*\{#[^}]+\}\s*$`` existed in three places: twice inside
``scripts/build/assemble.py`` and once in ``anchor_link_builder.py`` — plus a
FOURTH copy typed into a test, which asserted against its own copy and would have
stayed green if the production code were deleted outright. That test is what
`scripts/lint/test_quality_check.py` now catches mechanically.

Anchors are assembly-owned: whatever a writer types is dropped, and the canonical
slug is injected later by anchor_process. Every consumer of an H2 (conclusion
pattern-match, TOC/FAQ/References dedup) must compare against the clean text, so
there can only be one definition of "clean".

The pattern uses ``[^}]*`` rather than ``[^}]+``: two lint copies already used the
permissive form, so a degenerate ``{#}`` was stripped by some consumers and kept by
others. One character of divergence between four copies is exactly the drift this
module exists to end.
"""
from __future__ import annotations

import re

# A writer-supplied {#anchor} suffix on a heading line.
ANCHOR_SUFFIX_RE = re.compile(r"\s*\{#[^}]*\}\s*$")


def strip_heading_anchor(text: str) -> str:
    """Drop a trailing ``{#anchor}`` and surrounding whitespace."""
    return ANCHOR_SUFFIX_RE.sub("", str(text or "")).strip()


def h2_from_markdown(md_text: str) -> str:
    """Clean H2 text derived from a section .md file's first line.

    Returns "" when the first line is not a heading. Without this derivation the
    h2 stayed empty, dedup never matched, and duplicate seed sections shipped.
    """
    first_line = str(md_text or "").split("\n", 1)[0].lstrip()
    if not first_line.startswith("#"):
        return ""
    return strip_heading_anchor(first_line.lstrip("#").strip())
