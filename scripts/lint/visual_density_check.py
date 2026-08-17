#!/usr/bin/env python3
"""Visual density check — enforce a FLOOR and a CEILING of well-designed visual components.

Part of the visual-design system (2026-06-30). Supersedes the never-wired
`table_density_check.py` by counting the full component set, not just tables.

Evidence basis (Princeton GEO KDD'24; Nielsen Norman Group eye-tracking):
  - SUBSTANCE components (comparison tables, cited-stat grids, real quotations) are the
    high-value ones for readers AND AI citation. The floor therefore requires not just
    "some components" but at least one Tier-A substance component.
  - DECORATIVE components (callouts, and especially pull-quotes) over-used are a *measured*
    failure (banner blindness; decorative pull-quotes reduce reading and add nothing for AI).
    The ceiling caps decorative pull-quotes at 1.

Because components are authored as NATIVE markdown (the publisher renders html:False), this
scans the markdown draft for the structures the scoped CSS styles.

Usage:
    python -m scripts.lint.visual_density_check --workspace {task_id} [--min-components N] [--json] [--out PATH]

Exit codes: 0 = passed, 1 = failed (floor not met OR pull-quote ceiling breached).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from scripts._core.heading_anchor import ANCHOR_FRAGMENT

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
WS_ROOT = PLUGIN_ROOT / "memory" / "workspace"

# Tier weights: substance (A) counts double a decorative box (C).
_WEIGHTS = {
    "table": 2.0, "stat_grid": 2.0, "quotation": 2.0, "chart": 2.0,  # Tier A (substance)
    "tldr_box": 1.5, "glossary": 1.5, "checklist": 1.5,  # Tier B
    "callout": 1.0, "pull_quote": 1.0, "image": 1.0,     # Tier C / decorative visuals
}
# A rendered data CHART is substance too — this pipeline deliberately renders comparison/spec
# data as labeled chart PNGs instead of markdown tables (BUG 5), so a chart-rich article must
# not fail the floor as a "wall of text".
_TIER_A = ("table", "stat_grid", "quotation", "chart")


def _strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        end = content.find("\n---\n", 3)
        if end > 0:
            return content[end + 5:]
    return content


def _count_tables(body: str) -> int:
    lines = body.split("\n")
    n, i = 0, 0
    while i < len(lines):
        if re.match(r"^\s*\|.*\|.*\|\s*$", lines[i]):
            block = []
            while i < len(lines) and re.match(r"^\s*\|.*\|", lines[i]):
                block.append(lines[i])
                i += 1
            has_sep = any(re.match(r"^\s*\|[\s\-:|]+\|\s*$", b) for b in block)
            if has_sep and len(block) >= 3:
                n += 1
        else:
            i += 1
    return n


def _heading_ids(body: str) -> list[str]:
    """Slugged ids of the article's H2s (matches the publisher's slugify closely enough
    for the fixed component headings we care about)."""
    ids = []
    for m in re.finditer(r"^##\s+(.+?)\s*(" + ANCHOR_FRAGMENT + r")?\s*$", body, re.M):
        text = m.group(1)
        slug = re.sub(r"[^a-z0-9\s-]", "", text.lower()).strip()
        slug = re.sub(r"\s+", "-", slug)
        ids.append(slug)
    return ids


def _has_list_after(body: str, heading_regex: str) -> bool:
    """True only if the IMMEDIATE next non-blank line after the heading is a bullet — matching
    the CSS adjacent-sibling selector `h2#... + ul` (an intervening paragraph breaks the CSS,
    so the gate must not credit it either — BUG 7). `.*$` consumes the rest of the heading line
    (e.g. a `{#anchor}`)."""
    m = re.search(heading_regex + r".*$", body, re.M | re.I)
    if not m:
        return False
    for ln in body[m.end():].split("\n"):
        if ln.strip() == "":
            continue
        return bool(re.match(r"^\s*-\s+", ln))
    return False


def _classify_blockquotes(body: str) -> dict[str, int]:
    """Group consecutive `>` lines into blockquotes and classify each via the SHARED
    classifier (same source of truth the publisher uses — BUG 3)."""
    from scripts._core.blockquote_classify import classify
    counts = {"callout": 0, "pull_quote": 0, "quotation": 0}
    lines = body.split("\n")
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith(">"):
            block = []
            # A blank line (no leading '>') ends a blockquote in markdown, so group ONLY
            # consecutive '>'-prefixed lines — otherwise two adjacent callouts/pull-quotes
            # separated by a blank line merge into one and undercount.
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                block.append(lines[i])
                i += 1
            first = next((ln for ln in block if ln.lstrip().startswith(">")), "")
            inner = first.lstrip().lstrip(">").strip()
            kind = classify(inner)
            if kind.startswith("callout-"):
                counts["callout"] += 1
            elif kind == "pull_quote":
                counts["pull_quote"] += 1
            else:
                counts["quotation"] += 1
        else:
            i += 1
    return counts


# Per-format floors (completes the Phase-4 spec: "weekly-digest carve-out" + room
# for future per-format calibration). Used when no explicit --min-components is given.
_FORMAT_FLOORS = {
    "weekly-digest": 2.0,
}
_DEFAULT_FLOOR = 3.0

# component_headings ids -> by_type keys ("at_a_glance" is deliberately absent:
# its table is already counted by _count_tables; crediting it again would double-count).
_HEADING_COMPONENT_KEYS = {
    "stat_grid": "stat_grid",
    "glossary": "glossary",
    "tldr": "tldr_box",
    "checklist": "checklist",
}


def _count_component_headings(body: str) -> dict[str, int]:
    """Count component blocks via the SHARED heading classifier (2026-07-01).

    Same single source of truth the publisher's class-tagger uses
    (scripts/_core/component_headings) — so the gate can never again credit a
    component the CSS won't style, or miss one it will (the old English-exact
    regexes here missed topic-scoped, duplicated, variant and localized headings
    while the CSS failed on a DIFFERENT subset). H2 and H3 both qualify, and the
    sibling-structure requirement mirrors the tagger (list after list-components,
    paragraph after TL;DR).
    """
    from scripts._core.component_headings import classify_heading, sibling_tags_for
    counts = {v: 0 for v in _HEADING_COMPONENT_KEYS.values()}
    for m in re.finditer(r"^(#{2,3})\s+(.+?)\s*$", body, re.M):
        comp = classify_heading(m.group(2))
        key = _HEADING_COMPONENT_KEYS.get(comp or "")
        if not key:
            continue
        # sibling check: first non-blank line after the heading must open the
        # component's block type (mirrors the CSS adjacency — BUG 7).
        sib_ok = False
        for ln in body[m.end():].split("\n"):
            if ln.strip() == "":
                continue
            tags = sibling_tags_for(comp)
            if "ul" in tags and re.match(r"^\s*[-*]\s+", ln):
                sib_ok = True
            elif "ol" in tags and re.match(r"^\s*\d+[.)]\s+", ln):
                sib_ok = True
            elif "p" in tags and not re.match(r"^\s*(#{1,6}\s|\||>|\[IMAGE-SLOT)", ln):
                sib_ok = True
            break
        if sib_ok:
            counts[key] += 1
    return counts


def analyze(body: str, *, format_id: str | None = None, min_components: float | None = None,
            chart_count: int = 0) -> dict:
    body = _strip_frontmatter(body)
    if min_components is None:
        min_components = _FORMAT_FLOORS.get(str(format_id or ""), _DEFAULT_FLOOR)
    bq = _classify_blockquotes(body)
    total_image_slots = len(re.findall(r"\[IMAGE-SLOT-[^\]]+\]", body))
    heads = _count_component_headings(body)

    by_type = {
        "table": _count_tables(body),
        "stat_grid": heads["stat_grid"],
        "glossary": heads["glossary"],
        "tldr_box": heads["tldr_box"],
        "checklist": heads["checklist"],
        "quotation": bq["quotation"],
        "callout": bq["callout"],
        "pull_quote": bq["pull_quote"],
        "chart": chart_count,                                    # Tier-A data viz (BUG 5)
        "image": max(0, total_image_slots - chart_count),        # non-chart (decorative) images
    }

    weighted = sum(_WEIGHTS.get(k, 0) * v for k, v in by_type.items())
    component_count = sum(by_type.values())
    tier_a = sum(by_type[k] for k in _TIER_A)
    decorative = by_type["callout"] + by_type["pull_quote"]

    # FLOOR = blocking (a genuine wall of text). CEILING = advisory warnings (style
    # over-design should not halt a publish, and re-looping on it risks a stuck pipeline).
    defects: list[str] = []
    warnings: list[str] = []
    if weighted < min_components:
        defects.append(
            f"only {weighted:.1f} weighted visual components (minimum {min_components}); "
            f"article reads as a wall of text. Add a table, a By-the-Numbers stat block, or a quotation."
        )
    if tier_a < 1:
        defects.append(
            "no Tier-A substance component (comparison table / cited-stat grid / authoritative quotation). "
            "Decorative boxes alone do not count; add at least one substance component."
        )
    # Ceiling (evidence-based, advisory): decorative pull-quotes are the lowest-value element.
    if by_type["pull_quote"] > 1:
        warnings.append(
            f"{by_type['pull_quote']} decorative pull-quotes (recommend max 1). They disrupt reading "
            f"and add nothing for AI citation."
        )
    if by_type["callout"] > 4:
        warnings.append(
            f"{by_type['callout']} callout boxes; over-boxing triggers banner blindness. Keep it lean."
        )
    if decorative >= 5 and decorative > (tier_a + by_type["tldr_box"] + by_type["glossary"]):
        warnings.append(
            "decorative components (callouts + pull-quotes) outnumber substance; over-design risk."
        )

    passed = (weighted >= min_components) and (tier_a >= 1)   # FLOOR only

    return {
        "passed": passed,
        "weighted_score": round(weighted, 1),
        "component_count": component_count,
        "tier_a_count": tier_a,
        "by_type": by_type,
        "minimum_required": min_components,
        "format_id": format_id,
        "defects": defects,
        "warnings": warnings,
    }


def check(task_id: str, min_components: float | None = None) -> dict:
    # Resolve via WS_ROOT (not a hardcoded PLUGIN_ROOT/memory/workspace) so this
    # function and check_cta_block_ceiling() share ONE workspace root — identical
    # in production, and it lets the Gate-3 merge below be driven end-to-end in a
    # test that monkeypatches WS_ROOT (Rule 10: exercise the real invocation path).
    ws = WS_ROOT / task_id
    draft = ws / "draft.md"
    if not draft.exists():
        return {"passed": False, "error": "draft.md not found", "by_type": {}, "defects": ["draft.md not found"]}
    body = draft.read_text(encoding="utf-8")
    fmt = None
    angle = ws / "angle.json"
    if angle.exists():
        try:
            fmt = json.loads(angle.read_text(encoding="utf-8")).get("format_id")
        except Exception:
            fmt = None
    # Count CHART slots that actually render in the body (a chart is Tier-A substance — BUG 5).
    chart_count = 0
    ip = ws / "image-prompts.json"
    if ip.exists():
        try:
            for p in json.loads(ip.read_text(encoding="utf-8")).get("prompts", []):
                if str(p.get("kind", "")).lower() == "chart" and f"[IMAGE-SLOT-{p.get('slot_id')}]" in body:
                    chart_count += 1
        except Exception:
            pass
    result = analyze(body, format_id=fmt, min_components=min_components, chart_count=chart_count)

    # Project-level escape valve (BUG 4): a project may opt out of the mandatory floor via
    # business-context.json :: visual_density_required = false (mirrors references_required).
    # When opted out, never block — force passed=True and record why.
    if not result.get("passed", False) and _project_opts_out(ws):
        result["passed"] = True
        result["override"] = "visual_density_required:false"
        result.setdefault("warnings", []).append(
            "floor not met, but project opted out via visual_density_required:false")

    # Gate 3 (CTA v3.37) — MERGE the CTA over-decoration ceiling into the SAME
    # combined pass/fail this stage already reports (the whole point of Task 14:
    # check_cta_block_ceiling was built + unit-tested but nothing ever CALLED it,
    # so it gated no real article — Rule 6). It is a no-op PASS when no
    # cta-draft.json exists (the legacy static path AND the 5 projects without
    # conversion_offers), so non-adopting articles are never affected.
    # Applied AFTER the visual_density_required opt-out on purpose: that opt-out
    # suspends only the wall-of-text FLOOR; an over-decorated CTA that reads as an
    # ad banner is a distinct hard cap and must still block even when the floor is
    # waived.
    cta_ceiling = check_cta_block_ceiling(task_id)
    result["cta_block_ceiling"] = cta_ceiling
    if not cta_ceiling.get("passed", True):
        result["passed"] = False
        for v in cta_ceiling.get("violations", []):
            result.setdefault("defects", []).append(
                v.get("detail", "CTA block over-decorated (Gate 3 ceiling)"))
    return result


def _project_opts_out(ws: Path) -> bool:
    try:
        state = json.loads((ws / "state.json").read_text(encoding="utf-8"))
        slug = state.get("project_slug")
        if not slug:
            return False
        bc = json.loads((PLUGIN_ROOT / "projects" / slug / "business-context.json").read_text(encoding="utf-8"))
        return bc.get("visual_density_required") is False
    except Exception:
        return False


def check_cta_block_ceiling(task_id: str, max_blocks: int = 3) -> dict:
    """Gate 3 (CTA-specific): a CTA block should combine at most `max_blocks`
    building-block elements (avatar/stat/quote/button/etc.) — more than that is
    over-decorated for a component deliberately meant to read as calm, not an
    ad banner. No-op PASS when no cta-draft.json exists (legacy static path)."""
    draft_path = WS_ROOT / task_id / "cta-draft.json"
    result = {"passed": True, "task_id": task_id, "violations": [],
              "_generated_by": "visual-density-check-cta-ceiling"}
    if not draft_path.exists():
        result["_note"] = "no cta-draft.json (legacy static path, no-op PASS)"
        return result
    try:
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return result
    for placement, block in (draft.get("blocks") or {}).items():
        used = block.get("blocks_used") or []
        if len(used) > max_blocks:
            result["passed"] = False
            result["violations"].append({
                "placement": placement, "count": len(used), "max_blocks": max_blocks,
                "blocks_used": used,
                "detail": f"CTA '{placement}' combines {len(used)} building blocks "
                          f"({used}) — cap is {max_blocks}, over-decorated",
            })
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Visual density check (floor + ceiling)")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--min-components", type=float, default=None,
                    help="Minimum WEIGHTED component score (Tier-A counts 2x). Default: "
                         "per-format table (weekly-digest 2.0, else 3.0).")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", type=Path, default=None, help="Also write the JSON report to this path")
    args = ap.parse_args()

    result = check(args.workspace, min_components=args.min_components)
    out = args.out
    if out is None:
        out = WS_ROOT / args.workspace / "visual-density.json"
    try:
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except Exception:
        pass

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        flag = "OK" if result["passed"] else "FAIL"
        print(f"  [{flag}] visual density: score={result.get('weighted_score')} "
              f"tier_a={result.get('tier_a_count')} types={result.get('by_type')}")
        for d in result.get("defects", []):
            print(f"    - {d}")
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
