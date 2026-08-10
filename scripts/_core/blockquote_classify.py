"""Single source of truth for classifying a blockquote as a typed callout, a decorative
pull-quote, or a plain quotation.

Root cause of BUG 3 (2026-07-01 audit): the density gate (`visual_density_check`) and the
publisher (`wp_publisher._tag_callouts_and_pullquotes`) each had their OWN classifier, and
they had drifted — different callout-label sets (the gate was missing "danger") and different
quote-mark triggers (one treated a normal curly/straight quotation as a decorative pull-quote,
which both mis-credited substance AND silently defeated the pull-quote ceiling). Both now call
`classify()` here, so the component the gate counts is exactly the component the CSS styles.

Rule: a decorative pull-quote is signalled ONLY by the heavy quote mark `❝` (or its entity).
A blockquote that merely starts with a normal straight/curly quote is a QUOTATION, not a
pull-quote — so `> "authority said X"` counts as substance and the publisher does not strip it
into a centered pull-quote.
"""
from __future__ import annotations

import re

# keyword -> callout kind (the CSS class suffix). caution folds to warning, important to info.
CALLOUT_KIND: dict[str, str] = {
    "note": "callout-note",
    "info": "callout-info",
    "tip": "callout-tip",
    "warning": "callout-warning",
    "caution": "callout-warning",
    "important": "callout-info",
    "danger": "callout-danger",
}

# Matches a leading bold label in EITHER markdown (**Label:**) or rendered HTML (<strong>Label:</strong>).
_LABEL_RE = re.compile(r"^\s*(?:<strong>|\*\*)\s*([A-Za-z]+)\s*:?\s*(?:</strong>|\*\*)", re.I)
# A decorative pull-quote is signalled ONLY by the heavy left quote mark (or its HTML entity).
_PULL_RE = re.compile(r"^\s*(?:❝|&#10077;|&#x275D;)")


def classify(head: str) -> str:
    """Classify the LEADING content of a blockquote's first line/paragraph.

    `head` may be markdown (`**Warning:** ...`) or rendered-HTML inner (`<strong>Warning:</strong> ...`).
    Returns one of:
      'callout-note' | 'callout-info' | 'callout-tip' | 'callout-warning' | 'callout-danger'
      | 'pull_quote' | 'quotation'.
    """
    m = _LABEL_RE.match(head)
    if m:
        kind = CALLOUT_KIND.get(m.group(1).lower())
        if kind:
            return kind
    if _PULL_RE.match(head):
        return "pull_quote"
    return "quotation"
