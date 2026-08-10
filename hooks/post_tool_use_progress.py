#!/usr/bin/env python3
"""
hooks/post_tool_use_progress.py — Real-time pipeline progress display.

Fires on every PostToolUse event. Detects state.json writes from L2 phase
orchestrators (research/plan/build/optimize/publish) and prints a single-line
progress beacon to the user, like:

  [11/27] section-drafting  →  build phase, 40% complete, $0.72 spent, ~14m to go

The hook does NOT block the pipeline. It silently no-ops if:
  - No active workspace
  - State unchanged since last invocation
  - Output is being captured by a non-interactive run

This addresses the v3.2 "user sees nothing during a 30 min run" problem.
"""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path


# Cache last-printed stage per task to avoid duplicate prints
_STAGE_CACHE_FILE = Path.home() / ".xuanran-seo" / ".progress-cache.json"


def _load_cache() -> dict:
    if not _STAGE_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_STAGE_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict) -> None:
    _STAGE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        _STAGE_CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass


def _read_hook_event() -> dict:
    """Hook events are delivered via stdin as JSON."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return {}


def _is_state_write(event: dict) -> tuple[bool, Path | None]:
    """Detect a Write tool call writing to workspace/{task_id}/state.json."""
    if event.get("tool_name") != "Write":
        return False, None
    args = event.get("tool_input") or event.get("arguments") or {}
    path = args.get("file_path") or args.get("path")
    if not path:
        return False, None
    p = Path(path)
    # Match: ..../workspace/<anything>/state.json
    if p.name != "state.json":
        return False, None
    if "workspace" not in p.parts:
        return False, None
    return True, p


def _format_progress(state: dict, prev_stage: str | None) -> str | None:
    """Format the single-line beacon or return None to suppress."""
    stage = state.get("stage")
    if not stage or stage == prev_stage:
        return None

    phase = state.get("phase", "")
    task_id = state.get("task_id", "?")[:8]

    # Try to use status_reporter for richer info; fall back to minimal
    try:
        # Lazy import to avoid hook startup cost when not needed
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from scripts._core.status_reporter import (  # noqa: E402
            status_for_task, STAGE_TO_INDEX, STAGE_ORDER, _fmt_duration,
        )
        s = status_for_task(state.get("task_id", ""))
        if s:
            idx = s.stage_index + 1
            total = s.total_stages
            cost = s.cost_so_far_usd
            eta = _fmt_duration(s.estimated_remaining_seconds)
            return (
                f"  ▸ [{idx:2d}/{total}] {stage:<28s}"
                f" {phase:<10s}  ${cost}  eta {eta}"
            )
    except (ImportError, Exception):
        pass

    # Minimal fallback
    return f"  ▸ [{task_id}] Stage: {stage} ({phase})"


def main() -> int:
    event = _read_hook_event()
    if not event:
        return 0

    matched, state_path = _is_state_write(event)
    if not matched or state_path is None:
        return 0

    # Load just-written state
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0

    task_id = state.get("task_id", state_path.parent.name)
    cache = _load_cache()
    prev_stage = cache.get(task_id, {}).get("last_stage")

    msg = _format_progress(state, prev_stage)
    if msg:
        print(msg, file=sys.stderr, flush=True)
        cache[task_id] = {"last_stage": state.get("stage")}
        _save_cache(cache)

    return 0


if __name__ == "__main__":
    sys.exit(main())
