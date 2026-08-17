#!/usr/bin/env python3
"""Pipeline stage checklist — DIAGNOSTIC audit CLI over pipeline-checklist.json.

HONESTY BANNER (2026-08-17 wiring audit — Rule 6/12/14). This module's docstring
used to claim "the pre_publish_gate reads this checklist to enforce that
mandatory stages were executed." That was FALSE: no production code path ever
imported this module or invoked its CLI — live enforcement is, and remains,
`orchestrator._PASS_FLAG_REQUIRED` + `run_pipeline._GATE_STAGES` +
`orchestrator._content_gate_reason` (the per-workspace pipeline-checklist.json
FILE is orchestrator-owned; the orchestrator reads/writes it directly, not
through this module). What this module actually is: a standalone diagnostic —
`--action audit` answers "which mandatory stages have no completion record in
this workspace?" for a human debugging a task, and start/complete exist for
manual hand-driven runs. It enforces nothing; treating it as an enforcement
layer is the exact Rule-12 disease (a gate that gates nothing).

The stage lists below are DERIVED from the orchestrator's Stage table — the
single source of truth — so they can no longer drift (before this fix the
hand-maintained copy was missing chart-render / chart-rerender /
stat-grid-check, all mandatory since v3.13/v3.39).

Usage:
    # Which mandatory stages have no completion record?
    python -m scripts.pipeline.pipeline_checklist --workspace {task_id} --action audit [--json]

    # Manual hand-driven-run bookkeeping (rare):
    python -m scripts.pipeline.pipeline_checklist --workspace {task_id} --stage {name} --action start|complete

Exit codes (for --action audit):
    0 = all mandatory stages completed
    1 = some mandatory stages missing
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

# Derived, not hand-maintained (2026-08-17): the orchestrator's Stage table is
# the single source of truth for what is mandatory. The old literal list here
# drifted (missing chart-render/chart-rerender/stat-grid-check) — harmless only
# because nothing consumed it, which is its own finding (see banner).
from scripts.pipeline.orchestrator import STAGES as _STAGES  # noqa: E402

MANDATORY_STAGES = [s.name for s in _STAGES if s.is_mandatory]
RECOMMENDED_STAGES = [s.name for s in _STAGES if not s.is_mandatory]


def _checklist_path(task_id: str) -> Path:
    return PLUGIN_ROOT / "memory" / "workspace" / task_id / "pipeline-checklist.json"


def _load(task_id: str) -> dict:
    path = _checklist_path(task_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"task_id": task_id, "stages": {}}


def _save(task_id: str, data: dict) -> None:
    path = _checklist_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def register_start(task_id: str, stage: str) -> None:
    data = _load(task_id)
    now = datetime.now(timezone.utc).isoformat()
    data["stages"][stage] = {"started_at": now, "completed_at": None, "status": "in_progress"}
    _save(task_id, data)
    print(f"  [CHECKLIST] {stage}: started at {now}")


def register_complete(task_id: str, stage: str) -> None:
    data = _load(task_id)
    now = datetime.now(timezone.utc).isoformat()
    if stage in data["stages"]:
        data["stages"][stage]["completed_at"] = now
        data["stages"][stage]["status"] = "completed"
    else:
        data["stages"][stage] = {"started_at": now, "completed_at": now, "status": "completed"}
    _save(task_id, data)
    print(f"  [CHECKLIST] {stage}: completed at {now}")


def audit(task_id: str) -> dict:
    data = _load(task_id)
    completed = {
        name for name, info in data.get("stages", {}).items()
        if info.get("status") == "completed"
    }

    mandatory_missing = [s for s in MANDATORY_STAGES if s not in completed]
    recommended_missing = [s for s in RECOMMENDED_STAGES if s not in completed]
    mandatory_completed = [s for s in MANDATORY_STAGES if s in completed]

    return {
        "all_mandatory_passed": len(mandatory_missing) == 0,
        "mandatory_completed": mandatory_completed,
        "mandatory_missing": mandatory_missing,
        "recommended_missing": recommended_missing,
        "total_stages_completed": len(completed),
        "total_mandatory": len(MANDATORY_STAGES),
        "completion_pct": round(len(mandatory_completed) / len(MANDATORY_STAGES) * 100, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline stage checklist")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--stage", default=None)
    parser.add_argument("--action", required=True, choices=["start", "complete", "audit"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.action == "start":
        if not args.stage:
            parser.error("--stage required for start action")
        register_start(args.workspace, args.stage)
    elif args.action == "complete":
        if not args.stage:
            parser.error("--stage required for complete action")
        register_complete(args.workspace, args.stage)
    elif args.action == "audit":
        report = audit(args.workspace)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"\n  Pipeline Checklist Audit: {args.workspace}")
            print(f"  Completion: {report['completion_pct']}% ({len(report['mandatory_completed'])}/{report['total_mandatory']})")
            if report["mandatory_missing"]:
                print(f"\n  MANDATORY MISSING ({len(report['mandatory_missing'])}):")
                for s in report["mandatory_missing"]:
                    print(f"    [XX] {s}")
            if report["recommended_missing"]:
                print(f"\n  RECOMMENDED MISSING ({len(report['recommended_missing'])}):")
                for s in report["recommended_missing"]:
                    print(f"    [!!] {s}")
            if report["all_mandatory_passed"]:
                print("\n  All mandatory stages PASSED.")
            else:
                print(f"\n  BLOCKED: {len(report['mandatory_missing'])} mandatory stage(s) not completed.")
        sys.exit(0 if report["all_mandatory_passed"] else 1)


if __name__ == "__main__":
    main()
