#!/usr/bin/env python3
"""scripts/build/render_data_charts.py — render data/diagram image slots as REAL
labeled charts (Pillow) instead of letting them go to the AI photo generator.

This is the wiring that closes the Rule-6 gap behind the "图表没字 / textless dull
charts" failure: a slot whose intent is a chart/comparison/coverage/table is rendered
locally with real titles, axes, units, value labels, and a brand footer — text the
AI image model garbles or omits entirely.

Flow position: runs as a foreground orchestrator stage RIGHT AFTER
image-prompt-designer and BEFORE image-pipeline-fork. It reads image-prompts.json,
renders every entry with kind=="chart" + a chart_spec via data_chart_png, and MERGES
the resulting entries into images.json (upsert by slot_id). The photo pipeline then
only generates kind!="chart" slots and merges its photos into the same images.json.

Cover/featured slots are ALWAYS treated as photos and skipped here (a charted hero
would break the OG card + theme hero).

Usage:
    python -m scripts.build.render_data_charts --task-id {tid} [--project-slug slug] --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts._core import competitor_domains, file_bus
from scripts.build import data_chart_png as dcp

# Rule 8 chart-source layer (v3.36.0, 2026-07-06). chart_spec.source renders into the
# PNG footer — it is a CITATION SURFACE, but none of the existing Rule-8 layers
# (fact-checker refs / assemble strip / linker / schema strip / L11 / COMP01 /
# verify check 28) ever scanned it. The 2026-07-06 batch shipped competitor vendor
# names (Dashclicks / Hustle Marketers / Admove) into two chart footers; only a
# vision-QA agent reading the pixels caught one of them, and the fix was manual.
# This deterministic layer neutralizes tainted sources at the ONE executor every
# chart flows through, writes the sanitized value back to image-prompts.json (so QA
# re-renders stay clean), and records every replacement in the stage result.
NEUTRAL_CHART_SOURCE = "Industry benchmark synthesis"


def _source_block_hits(source: str, policy: competitor_domains.CompetitorPolicy) -> list[str]:
    """Blocked domains OR competitor brand names appearing in a chart source line."""
    if not policy.enabled or not source:
        return []
    low = source.lower()
    hits = [d for d in policy.domains if d in low]
    for b in policy.brands:
        if b and re.search(r"(?<![\w])" + re.escape(b.lower()) + r"(?![\w])", low):
            hits.append(b)
    return hits


def _sanitize_sources_in_file(ws: Path, policy: competitor_domains.CompetitorPolicy) -> list[dict]:
    """Neutralize competitor-tainted chart_spec.source values in image-prompts.json.

    Mutates the file in place (tolerant of both the {prompts:[...]} dict shape and a
    bare list) and returns [{slot_id, original, matched}] for every sanitized entry.
    No-op when the project has no enabled citation_source_policy (backward compatible,
    same opt-in contract as every other Rule-8 layer)."""
    p = ws / "image-prompts.json"
    if not policy.enabled or not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    prompts = raw.get("prompts") if isinstance(raw, dict) else raw
    if isinstance(prompts, dict):
        iterable = list(prompts.values())
    elif isinstance(prompts, list):
        iterable = prompts
    else:
        return []
    sanitized: list[dict] = []
    for e in iterable:
        if not isinstance(e, dict):
            continue
        spec = e.get("chart_spec")
        if not isinstance(spec, dict):
            continue
        src = str(spec.get("source") or "")
        hits = _source_block_hits(src, policy)
        if hits:
            spec["source"] = NEUTRAL_CHART_SOURCE
            sanitized.append({"slot_id": e.get("slot_id", ""),
                              "original": src,
                              "matched": sorted(set(hits))})
    if sanitized:
        p.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        for s in sanitized:
            print(f"[render_data_charts] Rule-8 chart-source sanitized: slot "
                  f"{s['slot_id']!r} matched {s['matched']} -> '{NEUTRAL_CHART_SOURCE}'",
                  file=sys.stderr)
    return sanitized

_RENDERERS = {
    "vbar": dcp.render_vbar,
    "grouped_vbar": dcp.render_grouped_vbar,
    "rangebar": dcp.render_rangebar,
    "table": dcp.render_table,
}


def _load_prompt_entries(ws: Path) -> list[dict]:
    # Centralized shape normalization (handles list AND {prompts:{slot_id:...}}
    # dict) so a dict-shaped image-prompts.json can never again silently render
    # ZERO charts (2026-06-29).
    from scripts._core.image_prompts import load_image_prompts
    return load_image_prompts(ws / "image-prompts.json")


def _apply_project_brand(project_slug: str) -> None:
    """Set the chart palette/footer from the project's brand-config (portable)."""
    if not project_slug:
        return
    proj = _REPO_ROOT / "projects" / project_slug
    primary = secondary = accent = None
    bc = proj / "brand" / "brand-config.json"
    if bc.exists():
        try:
            data = json.loads(bc.read_text(encoding="utf-8")) or {}
            # Accept BOTH the canonical nested `colors:{primary,...}` (5/6 projects)
            # AND the flat `primary_color`/`secondary_color`/`accent_color` schema that
            # /init's setup_wizard writes (loamwright). That writer/reader split silently
            # left loamwright's charts in matplotlib slate defaults — the "grey/navy
            # instead of brand teal" C3 warning on every charted article (2026-06-29).
            colors = data.get("colors") or {}
            primary = colors.get("primary") or data.get("primary_color")
            secondary = colors.get("secondary") or data.get("secondary_color")
            accent = colors.get("accent") or data.get("accent_color")
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    footer = None
    bctx = proj / "business-context.json"
    if bctx.exists():
        try:
            url = (json.loads(bctx.read_text(encoding="utf-8")) or {}).get("site_url", "")
            footer = urlparse(url).netloc.replace("www.", "") if url else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            footer = None
    dcp.set_brand(
        primary=primary,
        secondary=secondary,
        accent=accent,
        footer=footer,
    )


def _merge_into_images_json(ws: Path, new_entries: list[dict]) -> int:
    """Upsert chart entries into images.json by slot_id, preserving any existing
    (photo) entries. Returns the total slot count after merge."""
    p = ws / "images.json"
    existing: list[dict] = []
    container_is_list = True
    container: object = []
    if p.exists():
        try:
            container = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(container, list):
                existing = container
            elif isinstance(container, dict) and isinstance(container.get("images"), list):
                existing = container["images"]
                container_is_list = False
        except (json.JSONDecodeError, UnicodeDecodeError):
            existing = []
    by_slot = {e["slot_id"]: e for e in existing if isinstance(e, dict) and e.get("slot_id")}
    for e in new_entries:
        by_slot[e["slot_id"]] = e  # chart entry wins for its slot
    merged = list(by_slot.values())
    if container_is_list:
        out: object = merged
    else:
        container["images"] = merged
        out = container
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(merged)


def render(task_id: str, project_slug: str = "",
           result_filename: str = "chart-render-result.json") -> dict:
    ws = file_bus.get_workspace(task_id)
    (ws / "images").mkdir(parents=True, exist_ok=True)
    _apply_project_brand(project_slug)

    # Rule-8 chart-source sanitize BEFORE loading entries, so both the file and this
    # render see the neutralized values (load_policy_for_task resolves the project
    # from the workspace state — no reliance on the optional --project-slug flag).
    try:
        _policy = competitor_domains.load_policy_for_task(task_id)
    except Exception:  # noqa: BLE001 — a policy-load hiccup must not kill chart render
        _policy = competitor_domains.CompetitorPolicy()
    sources_sanitized = _sanitize_sources_in_file(ws, _policy)

    entries = _load_prompt_entries(ws)
    rendered: list[dict] = []
    skipped_featured: list[str] = []
    errors: list[dict] = []
    new_image_entries: list[dict] = []

    for e in entries:
        if not isinstance(e, dict):
            continue
        if str(e.get("kind", "photo")).lower() != "chart":
            continue
        slot_id = e.get("slot_id", "")
        # Guard: cover / featured is ALWAYS a photo, never a chart.
        if e.get("is_featured") or slot_id == "cover":
            skipped_featured.append(slot_id)
            continue
        spec = e.get("chart_spec")
        if not isinstance(spec, dict) or not spec:
            errors.append({"slot_id": slot_id, "error": "kind=chart but no chart_spec object"})
            continue
        ctype = str(spec.get("type", "vbar")).lower()
        renderer = _RENDERERS.get(ctype)
        if renderer is None:
            errors.append({"slot_id": slot_id, "error": f"unknown chart type '{ctype}' (use vbar|grouped_vbar|rangebar|table)"})
            continue
        seed = e.get("filename_seed") or f"{task_id}-{slot_id}-chart"
        out_path = ws / "images" / f"{seed}.png"
        try:
            img = renderer(spec)
            img.save(out_path, "PNG")
        except Exception as ex:  # noqa: BLE001 — report, don't crash the stage
            errors.append({"slot_id": slot_id, "error": f"{type(ex).__name__}: {ex}"})
            continue
        alt = e.get("alt_text_seed") or e.get("alt") or spec.get("title", "")
        caption = e.get("caption") or spec.get("subtitle") or spec.get("title", "")
        new_image_entries.append({
            "slot_id": slot_id,
            # v3.41.3: absolute by contract (schemas/images.schema.json)
            "path": str(out_path.resolve()),
            "filename": seed,
            "alt": alt,
            "caption": caption,
            "title": spec.get("title", ""),
            "description": caption,
            "is_featured": False,
            "source": "chart_render",
        })
        rendered.append({"slot_id": slot_id, "type": ctype, "path": str(out_path)})

    total_slots = _merge_into_images_json(ws, new_image_entries) if new_image_entries else None

    result = {
        "success": len(errors) == 0,
        "task_id": task_id,
        "charts_rendered": len(rendered),
        "rendered": rendered,
        "skipped_featured": skipped_featured,
        "errors": errors,
        "images_json_slot_count": total_slots,
        # Rule-8 chart-source layer: every competitor-tainted source that was
        # neutralized this run (empty list = nothing tainted / policy disabled).
        "sources_sanitized": sources_sanitized,
    }
    (ws / result_filename).write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Render data/chart image slots as real labeled charts")
    ap.add_argument("--task-id", "--workspace", dest="task_id", required=True)
    ap.add_argument("--project-slug", default="")
    ap.add_argument("--result-file", default="chart-render-result.json",
                    help="result artifact filename inside the workspace. The post-fact-check "
                         "chart-rerender stage passes a DISTINCT name (chart-rerender-result.json) "
                         "so the plan-phase artifact cannot auto-satisfy that stage.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    result = render(args.task_id, args.project_slug, result_filename=args.result_file)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"  chart-render: {result['charts_rendered']} chart(s) rendered, "
              f"{len(result['errors'])} error(s); images.json slots={result['images_json_slot_count']}")
        for e in result["errors"]:
            print(f"  ERROR {e['slot_id']}: {e['error']}", file=sys.stderr)
    # A chart slot with a malformed spec is a real defect → non-zero exit so the
    # orchestrator verify catches it rather than silently shipping a missing image.
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
