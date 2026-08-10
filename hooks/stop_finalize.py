#!/usr/bin/env python3
"""
hooks/stop_finalize.py — Session-end housekeeping.

Fires when Claude Code session ends. Performs:
  1. Archive completed workspace tasks (those with Stage: final or published)
  2. Cleanup tombstoned projects older than 30 days (GDPR purge)
  3. Snapshot cost ledger summary to projects/{active}/_meta/

Non-blocking — exits 0 even if errors.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _plugin_root() -> Path | None:
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "VERSION").exists() and (p / ".claude-plugin").is_dir():
            return p
        p = p.parent
    return None


def _archive_completed_tasks(plugin: Path) -> int:
    """Move workspace tasks with frontmatter Stage: final/published to .archived/."""
    workspace = plugin / "memory" / "workspace"
    if not workspace.exists():
        return 0

    archive_root = workspace / ".archived" / datetime.now(timezone.utc).strftime("%Y-%m")
    archived = 0
    for task_dir in workspace.iterdir():
        if not task_dir.is_dir() or task_dir.name.startswith("."):
            continue
        # Check if "final" stage reached
        draft = task_dir / "final.md"
        if draft.exists():
            archive_root.mkdir(parents=True, exist_ok=True)
            dst = archive_root / task_dir.name
            if dst.exists():
                continue  # already archived
            try:
                shutil.move(str(task_dir), str(dst))
                archived += 1
            except Exception:
                continue
    return archived


def _purge_tombstoned_projects(plugin: Path) -> int:
    """Delete projects/.deleted/<slug>-<timestamp>/ older than 30 days."""
    deleted_dir = plugin / "projects" / ".deleted"
    if not deleted_dir.exists():
        return 0
    cutoff = time.time() - 30 * 86400
    purged = 0
    for d in deleted_dir.iterdir():
        if not d.is_dir():
            continue
        try:
            if d.stat().st_mtime < cutoff:
                shutil.rmtree(d)
                purged += 1
        except Exception:
            continue
    return purged


def main() -> int:
    plugin = _plugin_root()
    if not plugin:
        return 0

    try:
        archived = _archive_completed_tasks(plugin)
        purged = _purge_tombstoned_projects(plugin)
        if archived or purged:
            msgs = []
            if archived:
                msgs.append(f"archived {archived} task(s)")
            if purged:
                msgs.append(f"purged {purged} tombstoned project(s)")
            print(f"[stop-finalize] " + ", ".join(msgs))
    except Exception:
        pass  # never block on cleanup

    return 0


if __name__ == "__main__":
    sys.exit(main())
