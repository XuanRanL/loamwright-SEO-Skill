"""
scripts/_core/status_reporter.py — Pipeline status reporter.

Scans `workspace/{task_id}/` directories and reports:
  - In-progress tasks (state != "completed", "blocked", "abandoned")
  - Current Stage per task (from state.json + draft.md frontmatter)
  - Elapsed time since start
  - Costs accrued so far (from cost-ledger filtered by task_id)
  - Estimated remaining time / cost
  - Last activity timestamp
  - Any veto / repair signals

Used by `/status` slash command. Read-only — does not modify pipeline state.

CLI:
    python -m scripts._core.status_reporter
    python -m scripts._core.status_reporter --task-id abc123 --json
    python -m scripts._core.status_reporter --all --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from scripts._core import cost_ledger
from scripts._core.file_bus import PLUGIN_ROOT
from scripts.pipeline import orchestrator as _orch


# ── Stage map — derived from the orchestrator, the single source of truth ────
#
# Pre-v3.41.0 this file carried its OWN hand-written 27-stage list from the v3.2
# architecture while the real pipeline grew to 45 stages, AND scanned
# `workspace/{task}` while real workspaces moved to `memory/workspace/{task}`,
# AND read state keys (`state`/`stage`/`started_at`) that the runner never
# writes (`status`/`current_stage`/`created_at`). Net effect: /status was blind
# to every real task and reported the `batches` directory as a phantom running
# task. Same Rule-11 disease as the L1/check-06 drift: a duplicated contract
# rots. Everything below now derives from `scripts.pipeline.orchestrator`.

STAGE_ORDER: list[tuple[str, str]] = [(s.phase, s.name) for s in _orch.STAGES]

STAGE_TO_INDEX: dict[str, int] = {stage: i for i, (_, stage) in enumerate(STAGE_ORDER)}

# Typical duration per stage in seconds (rough ETA weights for the SLOW stages;
# anything unlisted uses _DEFAULT_STAGE_SECONDS).
_DEFAULT_STAGE_SECONDS = 45
STAGE_TYPICAL_SECONDS: dict[str, int] = {
    "research": 600, "serp-analysis": 90, "competitor-analysis": 120,
    "outline-architect": 240, "section-drafter": 600,
    "image-pipeline-fork": 300, "image-pipeline-join": 120,
    "fact-check-and-citation": 600, "humanizer": 300,
    "geo-content-optimizer": 240, "visual-designer": 180,
    "independent-reviewer": 240, "image-visual-qa": 180,
    "wordpress-publisher": 120, "verify-post": 60,
}


@dataclass
class TaskStatus:
    task_id: str
    project_slug: str | None
    state: str                       # pipeline state (running/blocked/complete)
    phase: str                       # research / plan / build / optimize / publish / monitor
    stage: str
    stage_index: int                 # 0-based, into STAGE_ORDER
    total_stages: int
    progress_pct: float              # 0-100
    started_at: str | None
    elapsed_seconds: float
    last_activity_seconds_ago: float
    cost_so_far_usd: str             # Decimal as str
    estimated_remaining_seconds: int
    estimated_total_cost_usd: str    # str(Decimal)
    veto_flags: list[str] = field(default_factory=list)
    repair_level: int = 0
    blockers: list[str] = field(default_factory=list)
    workspace_path: str = ""


def _read_state(workspace_dir: Path) -> dict | None:
    state_file = workspace_dir / "state.json"
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _read_draft_frontmatter(workspace_dir: Path) -> dict:
    """Best-effort frontmatter parse from draft.md or final.md."""
    out: dict = {}
    for fname in ("final.md", "draft.md"):
        fp = workspace_dir / fname
        if not fp.exists():
            continue
        try:
            content = fp.read_text(encoding="utf-8", errors="ignore")
            m = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if m:
                for line in m.group(1).splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        out[k.strip()] = v.strip().strip('"').strip("'")
            return out
        except OSError:
            continue
    return out


def _filter_ledger_by_task(task_id: str) -> Decimal:
    """Sum costs from JSONL ledger for a specific task_id."""
    ledger = cost_ledger.LEDGER_FILE
    if not ledger.exists():
        return Decimal("0")
    total = Decimal("0")
    try:
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
                if e.get("task_id") == task_id:
                    total += Decimal(e.get("cost_usd", "0"))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    except OSError:
        return Decimal("0")
    return total


def _is_terminal_state(state: str) -> bool:
    return state.lower() in {"completed", "complete", "blocked", "abandoned", "failed"}


def _last_activity(workspace_dir: Path) -> float:
    """Return seconds since most recent file mtime in workspace."""
    latest = 0.0
    for p in workspace_dir.rglob("*"):
        if p.is_file():
            try:
                latest = max(latest, p.stat().st_mtime)
            except OSError:
                pass
    if latest == 0:
        return -1
    return time.time() - latest


def status_for_task(task_id: str) -> TaskStatus | None:
    """Build status report for one task_id."""
    # Canonical workspaces live under memory/workspace/ (orchestrator.WS_ROOT);
    # fall back to the legacy root for pre-v3.7 leftovers.
    workspace = _orch.WS_ROOT / task_id
    if not workspace.is_dir():
        workspace = PLUGIN_ROOT / "workspace" / task_id
    if not workspace.is_dir():
        return None

    state_data = _read_state(workspace) or {}
    frontmatter = _read_draft_frontmatter(workspace)

    # Real runner keys first (status/current_stage/created_at); legacy fallbacks.
    stage = (state_data.get("current_stage")
             or state_data.get("stage")
             or frontmatter.get("Stage")
             or "brief-intake")
    pipeline_state = (state_data.get("status")
                      or state_data.get("state")
                      or "running")
    phase = state_data.get("phase", "")
    if not phase and stage in STAGE_TO_INDEX:
        phase = STAGE_ORDER[STAGE_TO_INDEX[stage]][0]

    started_at_str = state_data.get("created_at") or state_data.get("started_at")
    elapsed_seconds = 0.0
    if started_at_str:
        try:
            started = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
            elapsed_seconds = (datetime.now(timezone.utc) - started).total_seconds()
        except (ValueError, TypeError):
            pass

    total = len(STAGE_ORDER)
    # Progress: prefer the stage_history ground truth (completed+skipped / total);
    # fall back to index-of-current-stage for workspaces without history.
    history = state_data.get("stage_history") or []
    done_in_history = sum(
        1 for h in history if h.get("status") in ("completed", "skipped"))
    stage_idx = STAGE_TO_INDEX.get(stage, 0)
    if done_in_history:
        stage_idx = max(stage_idx, min(done_in_history, total - 1))
        progress = (done_in_history / max(1, total)) * 100
    else:
        progress = (stage_idx / max(1, total - 1)) * 100
    if pipeline_state == "completed":
        progress = 100.0

    # ETA: sum typical duration of remaining stages
    remaining_seconds = sum(
        STAGE_TYPICAL_SECONDS.get(s, _DEFAULT_STAGE_SECONDS)
        for _, s in STAGE_ORDER[stage_idx + 1 :]
    )
    if pipeline_state == "completed":
        remaining_seconds = 0

    cost_so_far = _filter_ledger_by_task(task_id)
    # Rough total estimate: scale current cost to full pipeline
    if progress > 5:
        est_total = cost_so_far * Decimal(100) / Decimal(str(progress))
        est_total = est_total.quantize(Decimal("0.01"))
    else:
        # Pre-pipeline: use per_article default budget
        est_total = Decimal("2.50")

    return TaskStatus(
        task_id=task_id,
        project_slug=state_data.get("project_slug") or frontmatter.get("project_slug"),
        state=pipeline_state,
        phase=phase,
        stage=stage,
        stage_index=stage_idx,
        total_stages=total,
        progress_pct=round(progress, 1),
        started_at=started_at_str,
        elapsed_seconds=round(elapsed_seconds, 1),
        last_activity_seconds_ago=round(_last_activity(workspace), 1),
        cost_so_far_usd=str(cost_so_far.quantize(Decimal("0.0001"))),
        estimated_remaining_seconds=remaining_seconds,
        estimated_total_cost_usd=str(est_total),
        veto_flags=state_data.get("veto_flags") or [],
        repair_level=state_data.get("repair_level", 0),
        blockers=state_data.get("blockers") or [],
        workspace_path=str(workspace),
    )


def status_all() -> list[TaskStatus]:
    """Find all in-progress tasks (not terminal).

    Scans the canonical root (memory/workspace/) plus the legacy root
    (workspace/, minus the batches/ queue dir) and dedupes by task_id.
    """
    out: list[TaskStatus] = []
    seen: set[str] = set()
    for workspace_root in (_orch.WS_ROOT, PLUGIN_ROOT / "workspace"):
        if not workspace_root.is_dir():
            continue
        for task_dir in workspace_root.iterdir():
            if not task_dir.is_dir() or task_dir.name in ("batches",):
                continue
            if task_dir.name in seen or not any(task_dir.iterdir()):
                continue
            if not (task_dir / "state.json").exists():
                continue   # not a task workspace (misc dirs are not tasks)
            seen.add(task_dir.name)
            s = status_for_task(task_dir.name)
            if s and not _is_terminal_state(s.state):
                out.append(s)
    out.sort(key=lambda x: x.last_activity_seconds_ago)
    return out


def _fmt_duration(seconds: float) -> str:
    if seconds < 0:
        return "?"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m{int(seconds % 60)}s"
    return f"{int(seconds // 3600)}h{int((seconds % 3600) // 60)}m"


def _fmt_human(s: TaskStatus) -> str:
    lines = []
    bar_len = 20
    filled = int(s.progress_pct / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)

    lines.append(f"━━ Task {s.task_id} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"  Project:  {s.project_slug or '(none)'}")
    lines.append(f"  State:    {s.state.upper()}")
    lines.append(f"  Phase:    {s.phase}")
    lines.append(f"  Stage:    {s.stage}  ({s.stage_index + 1}/{s.total_stages})")
    lines.append(f"  Progress: [{bar}] {s.progress_pct}%")
    lines.append(f"  Elapsed:  {_fmt_duration(s.elapsed_seconds)}")
    lines.append(f"  Idle for: {_fmt_duration(s.last_activity_seconds_ago)}")
    lines.append(f"  Cost:     ${s.cost_so_far_usd}  (est. total ${s.estimated_total_cost_usd})")
    lines.append(f"  ETA:      ~{_fmt_duration(s.estimated_remaining_seconds)} remaining")
    if s.veto_flags:
        lines.append(f"  ⚠ Vetoes: {', '.join(s.veto_flags)}")
    if s.repair_level > 0:
        lines.append(f"  ⚙ Repair: level {s.repair_level}")
    if s.blockers:
        lines.append(f"  ⛔ Blockers:")
        for b in s.blockers:
            lines.append(f"    • {b}")
    if s.last_activity_seconds_ago > 300:
        lines.append(f"  ⚠ Idle >5min — pipeline may be stuck. Try /resume.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Pipeline status")
    ap.add_argument("--task-id")
    ap.add_argument("--all", action="store_true", help="Show all in-progress tasks")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.task_id:
        s = status_for_task(args.task_id)
        if not s:
            print(f"No task found: {args.task_id}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(asdict(s), indent=2, ensure_ascii=False))
        else:
            print(_fmt_human(s))
        return 0

    # Default: list all in-progress
    tasks = status_all()
    if args.json:
        print(json.dumps([asdict(t) for t in tasks], indent=2, ensure_ascii=False))
    else:
        if not tasks:
            print("No in-progress tasks. (All workspaces are completed/blocked/empty.)")
            print("Run /article to start a new article.")
            return 0
        print(f"Found {len(tasks)} in-progress task(s):\n")
        for t in tasks:
            print(_fmt_human(t))
    return 0


if __name__ == "__main__":
    sys.exit(main())
