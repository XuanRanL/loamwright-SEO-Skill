#!/usr/bin/env python3
"""Stat-grid ("By the Numbers") contract lint.

WHY THIS EXISTS (2026-07-14 root cure)
--------------------------------------
The `## By the Numbers` H2 + bold-led `<ul>` is rendered by the project article
CSS as a grid of stat CARDS: the leading `<strong>` of each `<li>` becomes a
large display number, and the rest of the `<li>` becomes a small muted label.

The component only works if the bold lead is a SHORT NUMERIC VALUE. Nothing
enforced that. `references/style/visual-design-components.md` said "the bold
leading run becomes the big number" but set no length limit, forbade no
descriptive words, and had no executor (a Rule-6 violation: documentation is not
an executor). So writers shipped things like:

    - **30% more chlorophyll** in shaded tencha, ...      <- number + noun phrase
    - **$12,000 to $25,000+ per month** enterprise ...    <- range + unit + period
    - **Notched Izod verdict:** ...                       <- not a number at all
    - **Conquesting only pays** when ...                  <- a whole clause

A 2026-07-14 survey of 591 published/draft posts across 10 projects found 57
posts carrying a stat grid, and **40 of them (70%) contained at least one value
that broke the layout** -- 107 of 365 values (29%) outright, another 86 (24%)
sitting on the wrap boundary. project-foxtrot shipped "chlorophyll" rendered as
"chloroph / yll".

The CSS side is hardened separately (article_css_generator.py: wider columns,
clamp()-ed value, and an explicit cancel of the inherited `word-wrap:break-word`
so a value can never chop mid-word). That makes a bad value degrade gracefully.
THIS lint is the other half: it keeps the value short and numeric so the card
looks designed rather than merely survivable.

DEFECT CLASSES
--------------
  S1  value too long            (> MAX_VALUE_CHARS characters)
  S2  long word inside value    (a single word > MAX_WORD_CHARS chars)
  S3  value is not a number     (does not start with a digit / currency / ~ / +/- / #)
  S4  value ends with a colon   (a label masquerading as a value)
  S5  grid item count out of band (WARN only; 3-6 cards read best)

S1-S4 are hard defects (exit 1). S5 is a warning.

USAGE
-----
    python -m scripts.lint.stat_grid_check --workspace {task_id} --json
    python -m scripts.lint.stat_grid_check --input path/to/draft.md --json
Writes {workspace}/stat-grid-lint.json in workspace mode (file-bus).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[2]

# A well-formed value: "85°C", "2 g", "44.65 mg", "$12k/mo", "30%", "20-30 days".
# The label ("of shading before harvest") belongs in the UNBOLDED remainder.
MAX_VALUE_CHARS = 16          # generous: "44.65 mg per gram" (17) already wraps
MAX_WORD_CHARS = 10           # "chlorophyll" (11) is exactly what shattered
MIN_ITEMS = 3
MAX_ITEMS = 6

# A value must LEAD with something numeric. Currency/approx/sign/hash allowed.
_NUMERIC_LEAD = re.compile(r"^\s*[~≈±+\-<>#]?\s*[$£€¥]?\s*\d")

# `## By the Numbers` / `## Key Stats` (tolerates a numbered prefix + {#anchor})
_STAT_H2 = re.compile(
    r"^##\s+(?:\d+\.\s*)?(By the Numbers|Key Stats)\b.*$", re.I | re.M)
_ANY_H2 = re.compile(r"^##\s+", re.M)
# a bold-led markdown bullet: "- **value** label"
_BOLD_LI = re.compile(r"^\s*[-*]\s+\*\*(.+?)\*\*\s*(.*)$", re.M)


def _strip_md(s: str) -> str:
    """Drop inline markdown/HTML so length is measured on what a reader sees."""
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)   # links
    s = re.sub(r"<[^>]+>", "", s)                    # stray html
    s = re.sub(r"[*_`]", "", s)                      # emphasis marks
    return s.strip()


def _sections(body: str) -> list[tuple[int, str]]:
    """Return [(line_no_of_h2, section_text)] for each stat-grid H2."""
    out: list[tuple[int, str]] = []
    for m in _STAT_H2.finditer(body):
        rest = body[m.end():]
        nxt = _ANY_H2.search(rest)
        seg = rest[: nxt.start()] if nxt else rest
        out.append((body[: m.start()].count("\n") + 1, seg))
    return out


def check_text(body: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "passed": True,
        "grids_found": 0,
        "items_checked": 0,
        "defects": [],
        "warnings": [],
        "_generated_by": "stat-grid-check",
    }

    for h2_line, seg in _sections(body):
        result["grids_found"] += 1
        items = _BOLD_LI.findall(seg)

        if not items:
            # A stat H2 with no bold-led list is not a stat grid; the CSS would
            # still card-ify a plain <ul>, so surface it rather than pass silently.
            result["warnings"].append({
                "code": "S5", "h2_line": h2_line,
                "message": "'By the Numbers' heading has no bold-led list items; "
                           "the CSS will still render the following <ul> as cards.",
            })
            continue

        if not (MIN_ITEMS <= len(items) <= MAX_ITEMS):
            result["warnings"].append({
                "code": "S5", "h2_line": h2_line, "count": len(items),
                "message": f"{len(items)} stat cards; {MIN_ITEMS}-{MAX_ITEMS} read best "
                           f"(a lone card belongs in prose; >6 stops being scannable).",
            })

        for raw_value, _label in items:
            value = _strip_md(raw_value)
            result["items_checked"] += 1
            words = value.split()
            longest = max((w for w in words), key=len, default="")

            def defect(code: str, message: str) -> None:
                result["passed"] = False
                result["defects"].append({
                    "code": code, "h2_line": h2_line, "value": value, "message": message,
                })

            if len(value) > MAX_VALUE_CHARS:
                defect("S1", f"value is {len(value)} chars (max {MAX_VALUE_CHARS}). "
                             f"Bold ONLY the number and its unit; move the description "
                             f"into the unbolded label after the closing **.")
            if len(longest) > MAX_WORD_CHARS:
                defect("S2", f"the word '{longest}' is {len(longest)} chars "
                             f"(max {MAX_WORD_CHARS}) and will dominate the card. "
                             f"Move it into the unbolded label.")
            if not _NUMERIC_LEAD.match(value):
                defect("S3", "value does not start with a number. The bold lead is the "
                             "big display FIGURE, not a title. If this item has no "
                             "number, it does not belong in a stat grid (use a "
                             "checklist or prose).")
            if value.endswith(":"):
                defect("S4", "value ends with ':' -- that is a label, not a figure. "
                             "Drop the colon and bold only the number.")

    return result


def check_workspace(task_id: str) -> dict[str, Any]:
    ws = PLUGIN_ROOT / "memory" / "workspace" / task_id
    draft = ws / "draft.md"
    if not draft.exists():
        return {"passed": True, "grids_found": 0, "items_checked": 0,
                "defects": [], "warnings": [],
                "notes": [f"no draft.md at {draft}"],
                "_generated_by": "stat-grid-check"}
    res = check_text(draft.read_text(encoding="utf-8"))
    res["task_id"] = task_id
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="Stat-grid (By the Numbers) contract lint")
    ap.add_argument("--workspace", help="task id; reads memory/workspace/{id}/draft.md")
    ap.add_argument("--input", help="path to a markdown file")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", help="write the report here (defaults to the workspace)")
    a = ap.parse_args()

    if a.workspace:
        res = check_workspace(a.workspace)
        out = Path(a.out) if a.out else (
            PLUGIN_ROOT / "memory" / "workspace" / a.workspace / "stat-grid-lint.json")
    elif a.input:
        res = check_text(Path(a.input).read_text(encoding="utf-8"))
        out = Path(a.out) if a.out else None
    else:
        ap.error("need --workspace or --input")
        return 2

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if res["passed"] else "FAIL"
        print(f"[stat-grid] {status} — {res['grids_found']} grid(s), "
              f"{res['items_checked']} item(s), {len(res['defects'])} defect(s)")
        for d in res["defects"]:
            print(f"  ✗ {d['code']} {d['value']!r}: {d['message']}")
        for w in res["warnings"]:
            print(f"  ⚠ {w['code']}: {w['message']}")

    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
