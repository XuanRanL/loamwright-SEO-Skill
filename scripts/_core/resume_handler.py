"""
scripts/_core/resume_handler.py — Resume interrupted /article pipeline.

Reads workspace/{task_id}/state.json + draft.md frontmatter to determine:
  - Which phase (research / plan / build / optimize / publish) owns current Stage
  - What's already done vs what's pending
  - Whether resumable or needs full restart

Outputs a dispatch plan (JSON or human-readable) that L1 or user can execute.

CLI:
    python -m scripts._core.resume_handler                  # most recent task
    python -m scripts._core.resume_handler --task-id abc123
    python -m scripts._core.resume_handler --task-id abc --dry-run --json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts._core.file_bus import PLUGIN_ROOT
from scripts._core.status_reporter import (
    STAGE_ORDER, STAGE_TO_INDEX,
    status_for_task,
    _read_state,
    _is_terminal_state,
)
from scripts.pipeline import orchestrator as _orch


# Which artifacts each stage produces — derived from the orchestrator's Stage
# definitions (single source of truth). The pre-v3.41.0 hand-written map here
# described a 27-stage v3.2 pipeline whose artifact names (`format.json`,
# `geo-optimized.md`, `wp-publish-log.json`, ...) no real stage has ever
# written, so /resume verified fictional artifacts against real workspaces.
STAGE_ARTIFACTS: dict[str, list[str]] = {
    s.name: list(s.expected_outputs) for s in _orch.STAGES
}


@dataclass
class ResumePlan:
    task_id: str
    current_stage: str
    current_phase: str
    next_phase: str             # which L2 to invoke next
    resume_from_stage: str      # stage to resume at
    artifacts_verified: list[str] = field(default_factory=list)
    artifacts_missing: list[str] = field(default_factory=list)
    resumable: bool = True
    reason_blocked: str | None = None
    estimated_remaining_seconds: int = 0
    estimated_remaining_usd: str = "0.00"
    suggested_command: str = ""


def _verify_artifacts(workspace: Path, stage: str) -> tuple[list[str], list[str]]:
    """Check which expected artifacts for `stage` actually exist."""
    expected = STAGE_ARTIFACTS.get(stage, [])
    found, missing = [], []
    for art in expected:
        if art.endswith("/"):
            d = workspace / art.rstrip("/")
            if d.is_dir() and any(d.iterdir()):
                found.append(art)
            else:
                missing.append(art)
        else:
            if (workspace / art).exists():
                found.append(art)
            else:
                missing.append(art)
    return found, missing


def _next_phase_after(stage: str) -> tuple[str, str]:
    """Given current stage, return (next_phase, resume_from_stage)."""
    idx = STAGE_TO_INDEX.get(stage, 0)
    # Resume from same stage (re-run it, since something failed mid-stage)
    # OR skip to next stage if all artifacts present
    if idx + 1 < len(STAGE_ORDER):
        next_phase, next_stage = STAGE_ORDER[idx + 1]
        return next_phase, next_stage
    return STAGE_ORDER[-1]


def plan_resume(task_id: str) -> ResumePlan | None:
    """Build a resume plan for the given task."""
    workspace = _orch.WS_ROOT / task_id
    if not workspace.is_dir():
        workspace = PLUGIN_ROOT / "workspace" / task_id
    if not workspace.is_dir():
        return None

    state = _read_state(workspace) or {}
    stage = (state.get("current_stage") or state.get("stage") or "brief-intake")
    pipeline_state = (state.get("status") or state.get("state") or "running")

    if _is_terminal_state(pipeline_state) and pipeline_state.lower() == "completed":
        return ResumePlan(
            task_id=task_id, current_stage=stage,
            current_phase=state.get("phase", ""),
            next_phase="", resume_from_stage="",
            resumable=False, reason_blocked="Task already completed",
        )

    if pipeline_state.lower() == "abandoned":
        return ResumePlan(
            task_id=task_id, current_stage=stage,
            current_phase=state.get("phase", ""),
            next_phase="", resume_from_stage="",
            resumable=False, reason_blocked="Task abandoned (manual tombstone)",
        )

    current_phase = state.get("phase", "")
    if not current_phase and stage in STAGE_TO_INDEX:
        current_phase = STAGE_ORDER[STAGE_TO_INDEX[stage]][0]

    found, missing = _verify_artifacts(workspace, stage)

    # If current stage's artifacts complete, jump forward
    if not missing:
        next_phase, resume_stage = _next_phase_after(stage)
    else:
        # Re-run current stage (it didn't finish)
        next_phase = current_phase
        resume_stage = stage

    # Estimate remaining
    from scripts._core.status_reporter import STAGE_TYPICAL_SECONDS
    idx = STAGE_TO_INDEX.get(resume_stage, 0)
    remaining_sec = sum(
        STAGE_TYPICAL_SECONDS.get(s, 60)
        for _, s in STAGE_ORDER[idx:]
    )

    # Estimate remaining cost — pull current spend, extrapolate
    s = status_for_task(task_id)
    if s and s.progress_pct > 0:
        from decimal import Decimal
        spent = Decimal(s.cost_so_far_usd)
        if s.progress_pct < 100:
            est_remaining = (spent / Decimal(str(s.progress_pct)) * Decimal("100")) - spent
            est_remaining_str = str(est_remaining.quantize(Decimal("0.01")))
        else:
            est_remaining_str = "0.00"
    else:
        est_remaining_str = "?"

    # The canonical resume is the deterministic runner itself: it re-derives the
    # next incomplete stage from state + artifacts and continues. Never hand-pick
    # an L2 phase — that duplicated (badly) what run_pipeline already does.
    suggested = (
        f"python -m scripts.pipeline.run_pipeline --workspace {task_id} --json"
        f"   # resumes at '{resume_stage}' ({next_phase} phase)"
    )

    return ResumePlan(
        task_id=task_id,
        current_stage=stage,
        current_phase=current_phase,
        next_phase=next_phase,
        resume_from_stage=resume_stage,
        artifacts_verified=found,
        artifacts_missing=missing,
        resumable=True,
        estimated_remaining_seconds=remaining_sec,
        estimated_remaining_usd=est_remaining_str,
        suggested_command=suggested,
    )


def find_most_recent_resumable() -> str | None:
    """Find latest non-terminal task across both workspace roots."""
    candidates: list[tuple[float, str]] = []
    seen: set[str] = set()
    for workspace_root in (_orch.WS_ROOT, PLUGIN_ROOT / "workspace"):
        if not workspace_root.is_dir():
            continue
        for task_dir in workspace_root.iterdir():
            if not task_dir.is_dir() or task_dir.name in seen or task_dir.name == "batches":
                continue
            state_file = task_dir / "state.json"
            if not state_file.exists():
                continue
            seen.add(task_dir.name)
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
                st = state.get("status") or state.get("state") or ""
                if not _is_terminal_state(st):
                    candidates.append((state_file.stat().st_mtime, task_dir.name))
            except (OSError, json.JSONDecodeError):
                continue
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _fmt_human(plan: ResumePlan) -> str:
    lines = [f"━━ Resume plan for {plan.task_id} ━━━━━━━━━━━━━━━━━"]
    if not plan.resumable:
        lines.append(f"  ❌ NOT RESUMABLE: {plan.reason_blocked}")
        return "\n".join(lines)

    lines.append(f"  Currently at:  {plan.current_phase} / {plan.current_stage}")
    lines.append(f"  Will resume:   {plan.next_phase} / {plan.resume_from_stage}")
    if plan.artifacts_verified:
        lines.append(f"  ✓ Verified ({len(plan.artifacts_verified)}):")
        for a in plan.artifacts_verified:
            lines.append(f"    • {a}")
    if plan.artifacts_missing:
        lines.append(f"  ⚠ Missing  ({len(plan.artifacts_missing)}):")
        for a in plan.artifacts_missing:
            lines.append(f"    • {a}")
        lines.append("  → Stage will re-run (artifacts incomplete)")
    else:
        lines.append("  → Stage complete; jumping to next stage")

    mins = plan.estimated_remaining_seconds // 60
    secs = plan.estimated_remaining_seconds % 60
    lines.append(f"  ETA:           {mins}m{secs}s")
    lines.append(f"  Cost left:     ~${plan.estimated_remaining_usd}")
    lines.append("")
    lines.append(f"  Next: {plan.suggested_command}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Resume an interrupted /article pipeline")
    ap.add_argument("--task-id", help="Specific task to resume (default: most recent)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print plan only, don't actually dispatch")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    task_id = args.task_id
    if not task_id:
        task_id = find_most_recent_resumable()
        if not task_id:
            print("No resumable task found.", file=sys.stderr)
            print("All workspaces are either completed, abandoned, or empty.", file=sys.stderr)
            return 1
        print(f"Using most recent task: {task_id}", file=sys.stderr)

    plan = plan_resume(task_id)
    if plan is None:
        print(f"Task {task_id} not found in workspace/.", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(asdict(plan), indent=2, ensure_ascii=False))
    else:
        print(_fmt_human(plan))

    if not plan.resumable:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
