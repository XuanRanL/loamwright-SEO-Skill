"""scripts/_core/citation_text.py — shared post-processing for in-text citations.

Single source of truth for collapsing ADJACENT DUPLICATE inline citations
(2026-07-01). All three claim-marker substitution executors (assemble.py's
``_replace_claims``, citation_inject.py, wp_publisher's ``_apply_in_text_citations``)
resolve each ``[claim:...]`` bracket independently, so two adjacent markers that
map to the SAME source each emit their own parenthetical:

    "... links come from DR 70-79 news sites [claim:c4_2][claim:c4_3]."
    → "... (Reboot Online, 2025)(Reboot Online, 2025)."   ← shipped in draft 788

No executor deduped ACROSS brackets (each deduped only within one bracket), so the
duplicate reads as a copy-paste error on the live page. Every executor MUST call
``collapse_adjacent_duplicate_citations()`` after its substitution pass.
"""
from __future__ import annotations

import re

# One inline citation: "(Author, 2025)" / "(Author & Co, 2025a)" / "(Org, n.d.)" /
# "(Google Search Central, 2025, 2026)". Bounded, no nested parens, must end in a
# year-like token so ordinary parentheticals ("(see below)") are never touched.
_CITATION_RE = (
    r"\((?:[^()\n]{1,90}?, )+(?:(?:19|20)\d{2}[a-z]?|n\.d\.)\)"
)

# The SAME citation repeated back-to-back (optionally whitespace-separated),
# captured once then matched again via backreference.
_ADJACENT_DUP_RE = re.compile(r"(" + _CITATION_RE + r")(?:\s*\1)+")


def collapse_adjacent_duplicate_citations(text: str) -> str:
    """Collapse ``(X, 2025)(X, 2025)`` / ``(X, 2025) (X, 2025)`` → ``(X, 2025)``.

    Only IDENTICAL, ADJACENT parentheticals are collapsed — two different sources
    cited side by side (``(A, 2024) (B, 2025)``) are left untouched, as are
    repeated citations separated by any prose.
    """
    return _ADJACENT_DUP_RE.sub(r"\1", text)
