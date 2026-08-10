#!/usr/bin/env python3
"""Prune finished task workspaces — and make the install cost visible first.

WHY THIS EXISTS
This plugin's marketplace source is a **directory**, so `/plugin install` and
`/plugin update` copy the source tree verbatim into a new versioned cache dir.
Verbatim means *everything*, including the runtime artifacts that live inside the
tree:

    memory/workspace/     2.7 GB   466 finished task dirs (gitignored)
    memory/research-cache/1.1 GB   regenerable API-response cache
    ------------------------------------------------------------------
    ~3.8 GB of a 4.2 GB tree is disposable state that gets copied every install

Three stale caches (3.41.2 / 3.41.3 / 3.41.7) already hold ~7 GB between them, and
each update mints another copy rather than replacing them.

CLAUDE.md already says "don't sync historical task dirs" — but that instruction is
addressed to a *human* doing a manual file-by-file sync. `/plugin update` has no
human in the loop and no exclusion mechanism, so the instruction cannot fire. That
is Rule 6 exactly: a documented behaviour with no executor. This is the executor.

WHAT IS SAFE TO PRUNE
A task workspace is the file-bus for ONE article. Once that article is published
and verified, the workspace is history — the artifacts that matter (draft, images,
publish log) are on WordPress. It is NOT safe to prune a workspace whose pipeline
never finished: `/resume` and `--resume` read it. So this tool prunes only tasks
that are demonstrably complete, and keeps a recent tail regardless.

Usage
-----
    python -m scripts._core.prune_workspaces --report
    python -m scripts._core.prune_workspaces --preflight     # before /plugin update
    python -m scripts._core.prune_workspaces --apply --older-than 30
    python -m scripts._core.prune_workspaces --apply --older-than 30 --include-research-cache
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
WS_ROOT = PLUGIN_ROOT / "memory" / "workspace"
RESEARCH_CACHE = PLUGIN_ROOT / "memory" / "research-cache"

# Never prune the most recent N task dirs, whatever their age or status. Cheap
# insurance against "it said complete but I still wanted to look at it".
KEEP_RECENT = 20

# A task is finished when its own record says so — not when it merely looks old.
DONE_STATUSES = {"complete", "completed", "published", "done"}


def _dir_size(p: Path) -> int:
    total = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            continue
    return total


def _task_state(task_dir: Path) -> dict[str, Any]:
    """What this workspace says about itself."""
    out: dict[str, Any] = {"status": None, "published": False}
    try:
        st = json.loads((task_dir / "state.json").read_text(encoding="utf-8"))
        out["status"] = str(st.get("status") or "").lower()
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    # A publish log with a post id is the strongest evidence the work landed.
    for name in ("publish-log.json", "verify-result.json"):
        p = task_dir / name
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                if d.get("post_id") or d.get("post_url") or d.get("overall_pass"):
                    out["published"] = True
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                pass
    return out


def survey(older_than_days: int = 30) -> dict[str, Any]:
    """Classify every task workspace without touching anything."""
    if not WS_ROOT.is_dir():
        return {"tasks": [], "prunable": [], "kept": [], "ws_root_missing": True}

    cutoff = time.time() - older_than_days * 86400
    dirs = sorted((d for d in WS_ROOT.iterdir() if d.is_dir()),
                  key=lambda d: d.stat().st_mtime, reverse=True)
    recent_guard = {d.name for d in dirs[:KEEP_RECENT]}

    tasks, prunable, kept = [], [], []
    for d in dirs:
        st = _task_state(d)
        mtime = d.stat().st_mtime
        rec = {
            "task": d.name,
            "bytes": _dir_size(d),
            "age_days": round((time.time() - mtime) / 86400, 1),
            "status": st["status"],
            "published": st["published"],
        }
        tasks.append(rec)

        if d.name in recent_guard:
            rec["keep_reason"] = f"within the newest {KEEP_RECENT}"
            kept.append(rec)
        elif mtime > cutoff:
            rec["keep_reason"] = f"newer than {older_than_days}d"
            kept.append(rec)
        elif not (st["published"] or (st["status"] in DONE_STATUSES)):
            # Unfinished work is what /resume reads. Age is not permission.
            rec["keep_reason"] = "pipeline never finished — /resume needs it"
            kept.append(rec)
        else:
            prunable.append(rec)

    return {"tasks": tasks, "prunable": prunable, "kept": kept,
            "ws_root_missing": False}


def preflight() -> dict[str, Any]:
    """What would `/plugin update` copy right now, and how much of it is junk?"""
    tree = _dir_size(PLUGIN_ROOT) if PLUGIN_ROOT.is_dir() else 0
    ws = _dir_size(WS_ROOT) if WS_ROOT.is_dir() else 0
    rc = _dir_size(RESEARCH_CACHE) if RESEARCH_CACHE.is_dir() else 0
    s = survey()
    return {
        "tree_bytes": tree,
        "workspace_bytes": ws,
        "research_cache_bytes": rc,
        "disposable_bytes": ws + rc,
        "disposable_pct": round(100 * (ws + rc) / tree, 1) if tree else 0.0,
        "prunable_bytes": sum(t["bytes"] for t in s["prunable"]),
        "prunable_tasks": len(s["prunable"]),
        "kept_tasks": len(s["kept"]),
    }


def prune(older_than_days: int, *, apply: bool,
          include_research_cache: bool = False) -> dict[str, Any]:
    s = survey(older_than_days)
    removed, freed = [], 0
    if apply:
        for rec in s["prunable"]:
            target = WS_ROOT / rec["task"]
            try:
                shutil.rmtree(target)
                removed.append(rec["task"])
                freed += rec["bytes"]
            except OSError as e:
                rec["error"] = str(e)
    if include_research_cache and RESEARCH_CACHE.is_dir():
        rc_bytes = _dir_size(RESEARCH_CACHE)
        if apply:
            try:
                shutil.rmtree(RESEARCH_CACHE)
                RESEARCH_CACHE.mkdir(parents=True, exist_ok=True)
                freed += rc_bytes
            except OSError:
                pass
        s["research_cache_bytes"] = rc_bytes
    return {**s, "removed": removed, "freed_bytes": freed, "applied": apply}


def _gb(n: int) -> str:
    return f"{n / 1024 ** 3:.2f} GB" if n >= 1024 ** 3 else f"{n / 1024 ** 2:.0f} MB"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Prune finished task workspaces; show install cost")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--report", action="store_true", help="classify, change nothing")
    g.add_argument("--preflight", action="store_true",
                   help="what /plugin update would copy right now")
    g.add_argument("--apply", action="store_true", help="delete prunable workspaces")
    ap.add_argument("--older-than", type=int, default=30,
                    help="only prune tasks older than N days (default 30)")
    ap.add_argument("--include-research-cache", action="store_true",
                    help="also clear memory/research-cache (regenerable)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.preflight:
        pf = preflight()
        if a.json:
            print(json.dumps(pf, indent=2))
            return 0
        print("Install preflight — the marketplace source is a DIRECTORY, so "
              "/plugin update copies the tree verbatim.\n")
        print(f"  tree that would be copied : {_gb(pf['tree_bytes'])}")
        print(f"  memory/workspace/         : {_gb(pf['workspace_bytes'])}")
        print(f"  memory/research-cache/    : {_gb(pf['research_cache_bytes'])}")
        print(f"  disposable share          : {_gb(pf['disposable_bytes'])} "
              f"({pf['disposable_pct']}%)")
        print(f"\n  prunable now: {pf['prunable_tasks']} finished task(s), "
              f"{_gb(pf['prunable_bytes'])}   (kept: {pf['kept_tasks']})")
        print("\n  Run --apply first, then /plugin update, or every future install "
              "carries this again.")
        return 0

    res = prune(a.older_than, apply=a.apply,
                include_research_cache=a.include_research_cache)
    if a.json:
        print(json.dumps(res, indent=2))
        return 0

    verb = "REMOVED" if res["applied"] else "WOULD REMOVE"
    print(f"{verb} {len(res['prunable'])} finished task workspace(s), "
          f"{_gb(sum(t['bytes'] for t in res['prunable']))}")
    print(f"kept {len(res['kept'])} (newest {KEEP_RECENT}, "
          f"newer than {a.older_than}d, or pipeline unfinished)")
    unfinished = [t for t in res["kept"] if "never finished" in (t.get("keep_reason") or "")]
    if unfinished:
        print(f"\n  {len(unfinished)} unfinished task(s) kept — /resume reads these:")
        for t in unfinished[:8]:
            print(f"    {t['task']}  {t['age_days']}d  status={t['status']}")
    if res["applied"]:
        print(f"\nfreed {_gb(res['freed_bytes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
