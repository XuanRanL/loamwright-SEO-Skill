"""Canonical article-format enum — one reader, shared by every consumer.

The authoritative list of article formats is
``schemas/angle.schema.json :: properties.format_id.enum``, mirrored 1:1 by the
``templates/*.md`` basenames. Nothing else may hand-maintain a copy.

Why this module exists (Rule 11): `batch_queue` was root-cured in v3.41.4 after
its hand-written 10-item literal drifted a generation behind the schema and
silently rewrote real formats to `listicle`. The fix read the schema — but only
in that one file. `cost_estimator` still carried its own stale literal (as
argparse `choices=`), so the batch workflow's documented per-article cost guard
rejected 17 of 27 legal formats with `invalid choice`. Two readers of one
contract is exactly the fan-out Rule 11 warns about, so there is now one reader.

Adding a format = edit the schema and add the template. Never edit the fallback.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts._core.file_bus import PLUGIN_ROOT

FORMAT_ENUM_SCHEMA: Path = PLUGIN_ROOT / "schemas" / "angle.schema.json"

# Fallback ONLY for an unreadable schema file. Never edit this to add a format —
# it exists so a corrupt checkout degrades loudly instead of crashing.
_FORMAT_FALLBACK: frozenset[str] = frozenset({
    "listicle", "how-to-guide", "pillar-page", "comparison",
    "case-study", "definition", "news-analysis", "product-review",
    "shortlist-validation", "faq-knowledge",
})


def load_valid_formats(*, source: str = "format_registry") -> set[str]:
    """Return the canonical format_id enum, warning to stderr if unreadable."""
    try:
        schema = json.loads(FORMAT_ENUM_SCHEMA.read_text(encoding="utf-8"))
        enum = schema["properties"]["format_id"]["enum"]
        if isinstance(enum, list) and enum:
            return {str(f) for f in enum}
    except (OSError, ValueError, KeyError, TypeError) as exc:  # pragma: no cover
        print(
            f"[{source}] WARNING: could not read format enum from "
            f"{FORMAT_ENUM_SCHEMA} ({exc}); falling back to the built-in list.",
            file=sys.stderr,
        )
    return set(_FORMAT_FALLBACK)


VALID_FORMATS: set[str] = load_valid_formats()
