#!/usr/bin/env python3
"""Targeted regeneration of failed PHOTO slots flagged by the image-visual-qa subagent.

Thin wrapper around openai_image_pipeline.generate_images(): that function already
handles cost-ledger estimate/check/log, brand watermarking, the dimension hard-gate,
provider fallback, and the upsert-merge into images.json (chart entries survive).

Chart-slot defects are NOT handled here — the QA agent patches chart_spec inside
image-prompts.json and re-runs scripts.build.render_data_charts (local, free).

Usage:
    python -m scripts.openai.image_regen_slots \
        --workspace memory/workspace/{task_id} \
        --requests-file memory/workspace/{task_id}/image-qa-regen-requests.json \
        --task-id {task_id} [--json]

Exit codes: 0 all regenerated / 1 partial / 2 total failure / 3 input error
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from scripts.openai.openai_image_pipeline import (
    ImagePromptSpec,
    generate_images,
)


class RegenInputError(ValueError):
    """Raised when the regen-requests file is missing, malformed, or photo-empty."""


def load_regen_specs(requests_file: Path) -> tuple[list[ImagePromptSpec], int]:
    """Parse image-qa-regen-requests.json into photo-only ImagePromptSpecs.

    Filenames get a -r{round} suffix so the regenerated upload can never be
    deduped to the round-0 WP media item or silently shadow the old local file.
    """
    if not requests_file.exists():
        raise RegenInputError(f"requests file not found: {requests_file}")
    try:
        data = json.loads(requests_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise RegenInputError(f"requests file is not valid JSON: {e}") from e

    task_id = data.get("task_id", "")
    round_n = int(data.get("round", 1))
    entries = data.get("requests", [])
    photo_entries = [e for e in entries
                     if isinstance(e, dict) and e.get("kind", "photo") != "chart"]
    if not photo_entries:
        raise RegenInputError(
            "no photo slots in requests file (chart slots are re-rendered via "
            "scripts.build.render_data_charts, not this script)")

    specs: list[ImagePromptSpec] = []
    for e in photo_entries:
        spec = ImagePromptSpec.from_dict({
            **e,
            "alt": e.get("alt") or e.get("alt_text_seed", ""),
        })
        base = (e.get("filename") or e.get("filename_seed")
                or (f"{task_id}-{spec.slot}" if task_id else spec.slot))
        spec.filename = f"{base}-r{round_n}"
        specs.append(spec)
    return specs, round_n


def _real_photo_project(workspace: Path) -> str:
    """Return the project_slug if this workspace's project sources REAL product photos.

    A real-photo project (e.g. project-echo) must NEVER regen via text-to-image: that
    re-hallucinates the branded pack as garbled pseudo-glyphs — the exact Rule-7
    failure this whole feature exists to prevent. Empty string => not a real-photo
    project => use the normal AI regen path.
    """
    try:
        state = json.loads((workspace / "state.json").read_text(encoding="utf-8"))
        slug = str(state.get("project_slug", "") or "")
    except Exception:
        return ""
    if not slug:
        return ""
    try:
        from scripts._core.image_brand_policy import load_image_brand_policy
        return slug if load_image_brand_policy(slug).source_real_photos else ""
    except Exception:
        return ""


def _run_real_photo_regen(workspace: Path, project_slug: str, round_n: int,
                          json_mode: bool) -> int:
    """Re-source REAL product photos for the workspace's flagged slots (no text-to-image).

    Delegates to real_brand_image_pipeline.run_for_workspace, which reads brand/scene
    from image-prompts.json, re-sources a real photo per product slot, re-scenes the
    background with the pack preserved, and merges into images.json.
    """
    from scripts.openai import real_brand_image_pipeline as rb
    merged = rb.run_for_workspace(str(workspace), project_slug)
    ok = [e for e in merged if e.get("source") not in ("failed", "skipped")]
    bad = [e for e in merged if e.get("source") in ("failed", "skipped")]
    exit_code = 0 if not bad else (1 if ok else 2)
    summary = {
        "ok": exit_code == 0,
        "round": round_n,
        "route": "real_brand",
        "project_slug": project_slug,
        "regenerated_slots": [e.get("slot_id") for e in ok],
        "failed_slots": [e.get("slot_id") for e in bad],
        "exit_code": exit_code,
    }
    (workspace / f"image-qa-regen-result-r{round_n}.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    if json_mode:
        print(json.dumps(summary, ensure_ascii=False))
    return exit_code


# Repo root = .../scripts/openai/image_regen_slots.py -> up 3
_REPO_ROOT = Path(__file__).resolve().parents[2]
_WS_ROOT = _REPO_ROOT / "memory" / "workspace"


def resolve_workspace(given: Path) -> Path:
    """Resolve --workspace, tolerating a BARE task_id.

    v3.41.4. The docstring at the top of this module shows the intended
    `--workspace memory/workspace/{task_id}` form, but agents/image-visual-qa.md
    and the orchestrator dispatch both hand this flag a bare `{task_id}`. A bare
    id resolved against CWD, so regenerated PNGs were written to
    `./{task_id}/images/...` -- OUTSIDE the real workspace. Nothing crashed:
    the images generated, the API was billed, `images.json` never saw them, and
    the watermark step (which runs against the true workspace) was skipped. The
    operator's only symptom was "it cost money and nothing changed."

    Found on the 2026-07-24 project-india batch, article 3, during a legitimate
    round-2 regeneration.

    Resolution order, first hit wins:
      1. the path as given, if it already exists
      2. memory/workspace/<given>, if that exists (the bare-task_id case)
      3. the path as given (unchanged), so a genuinely new path still works
         and any downstream error names the caller's own argument
    """
    if given.exists():
        return given
    candidate = _WS_ROOT / given.name
    if len(given.parts) == 1 and candidate.is_dir():
        return candidate
    return given


def run(*, workspace: Path, requests_file: Path, task_id: str | None,
        json_mode: bool = False) -> int:
    workspace = resolve_workspace(workspace)
    try:
        specs, round_n = load_regen_specs(requests_file)
    except RegenInputError as e:
        payload = {"ok": False, "error": str(e), "exit_code": 3}
        if json_mode:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"INPUT ERROR: {e}", file=sys.stderr)
        return 3

    # Rule-7 wiring: real-photo projects re-source a REAL photo instead of re-rendering
    # the pack via text-to-image (which garbles brand glyphs). See _real_photo_project.
    real_slug = _real_photo_project(workspace)
    if real_slug:
        return _run_real_photo_regen(workspace, real_slug, round_n, json_mode)

    result = generate_images(
        specs, workspace, task_id=task_id, mode="realtime", json_mode=json_mode,
    )

    if result.success_slots == result.total_slots:
        exit_code = 0
    elif result.success_slots > 0:
        exit_code = 1
    else:
        exit_code = 2

    summary = {
        "ok": exit_code == 0,
        "round": round_n,
        "regenerated_slots": [s.slot for s in result.slots if s.success],
        "failed_slots": [s.slot for s in result.slots if not s.success],
        "total_cost_usd": result.total_cost_usd,
        "exit_code": exit_code,
        "result": asdict(result),
    }
    out_path = workspace / f"image-qa-regen-result-r{round_n}.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    if json_mode:
        print(json.dumps({k: v for k, v in summary.items() if k != "result"},
                         ensure_ascii=False))
    return exit_code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--requests-file", required=True, type=Path)
    ap.add_argument("--task-id", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    return run(workspace=args.workspace, requests_file=args.requests_file,
               task_id=args.task_id, json_mode=args.json)


if __name__ == "__main__":
    sys.exit(main())
