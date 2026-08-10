#!/usr/bin/env python3
"""scripts/optimize/cta_diversity_check.py — CTA Gate 5 (v3.37).

Cross-article diversity: compares the current article's cta-draft.json
against the project's rolling cta-history.json (last ~20 entries) to catch
CREATIVE repetition (same heading reused too soon, near-duplicate hook
opening) — but explicitly does NOT flag reusing the same correct specialist
or offer, since that is often the right answer, not laziness.

Usage:
    python -m scripts.optimize.cta_diversity_check --task-id {tid} --project-slug {slug} --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts._core import file_lock

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
WS_ROOT = PLUGIN_ROOT / "memory" / "workspace"

_HEADING_REPEAT_WINDOW = 5   # last N entries checked for an exact heading repeat
_HOOK_PREFIX_WORDS = 6
_MAX_HISTORY = 20


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hook_prefix(text: str) -> str:
    words = re.findall(r"[A-Za-z']+", text.lower())
    return " ".join(words[:_HOOK_PREFIX_WORDS])


def _load_draft(task_id: str) -> dict[str, Any] | None:
    p = WS_ROOT / task_id / "cta-draft.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _history_path(project_slug: str) -> Path:
    return PLUGIN_ROOT / "projects" / project_slug / "cta-history.json"


def _load_history(project_slug: str) -> list[dict[str, Any]]:
    p = _history_path(project_slug)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(data, dict):
        # A hand-edited or corrupted history file that parses to a bare list/
        # string/number must not crash the gate — treat it as an empty window
        # rather than raising AttributeError on the missing .get().
        return []
    return data.get("entries", [])


def check_diversity(task_id: str, project_slug: str) -> dict[str, Any]:
    draft = _load_draft(task_id)
    result: dict[str, Any] = {
        "passed": True, "task_id": task_id, "project_slug": project_slug,
        "violations": [], "_generated_by": "cta-diversity-check",
        "generated_at": _now_iso(),
    }
    if not draft:
        result["_note"] = "no cta-draft.json (legacy static path, gate is a no-op PASS)"
        return result

    history = _load_history(project_slug)
    recent = history[-_HEADING_REPEAT_WINDOW:]

    for placement, block in (draft.get("blocks") or {}).items():
        heading = str(block.get("heading", ""))
        hook = _hook_prefix(str(block.get("text", "")))
        for entry in recent:
            if entry.get("heading") == heading:
                result["passed"] = False
                result["violations"].append({
                    "type": "heading_repeat", "placement": placement,
                    "heading": heading, "conflicts_with": entry.get("task_id", "?"),
                    "detail": f"heading '{heading}' was already used by {entry.get('task_id', '?')} "
                              f"within the last {_HEADING_REPEAT_WINDOW} articles",
                })
            if hook and entry.get("hook_prefix") == hook:
                result["passed"] = False
                result["violations"].append({
                    "type": "hook_near_duplicate", "placement": placement,
                    "hook_prefix": hook, "conflicts_with": entry.get("task_id", "?"),
                    "detail": f"hook opening '{hook}...' matches {entry.get('task_id', '?')} "
                              f"— vary the creative execution, not necessarily the offer",
                })
    return result


def record_history(task_id: str, project_slug: str) -> None:
    """Append this article's CTA fingerprint(s) to the project's rolling history.

    Called by the orchestrator's cta-record-history stage, which runs in the
    OPTIMIZE phase (pre-publish) immediately after cta-injection succeeds with
    draft_source=='llm' — see record_history_if_eligible(), the eligibility
    guard the stage actually drives. It does NOT wait for the article to
    publish. Tradeoff accepted: an optimized-but-never-published article (the
    draft is abandoned, or publish fails downstream) still leaves a fingerprint
    in the rolling _MAX_HISTORY=20 window. This is bounded and harmless — the
    CTA copy WAS genuinely authored, so a future article avoiding its heading/
    hook phrasing is, at worst, needless variety, never a false diversity
    violation against content that was never real."""
    draft = _load_draft(task_id)
    if not draft:
        return
    path = _history_path(project_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Cross-process lock (Rule 7): same-project parallel batches can reach this
    # stage concurrently, and this whole block is a read-modify-write on the
    # SHARED projects/{slug}/cta-history.json — unlocked, a second writer reads
    # a stale list and clobbers the first writer's fingerprint on save.
    with file_lock.locked(path):
        history = _load_history(project_slug)
        for placement, block in (draft.get("blocks") or {}).items():
            history.append({
                "task_id": task_id, "placement": placement,
                "heading": str(block.get("heading", "")),
                "hook_prefix": _hook_prefix(str(block.get("text", ""))),
                "blocks_used": block.get("blocks_used", []),
                "recorded_at": _now_iso(),
            })
        history = history[-_MAX_HISTORY:]
        path.write_text(json.dumps({"entries": history}, indent=2, ensure_ascii=False), encoding="utf-8")


_INJECTION_RESULT = "cta-injection-result.json"


def _injection_used_llm(task_id: str) -> tuple[bool, str]:
    """Was the CTA actually placed from the LLM-authored cta-draft.json — not the
    legacy static config, and not a no-op? Reads the cta-injection stage's own
    result artifact. Only a successful, LLM-sourced injection PARTICIPATES in the
    cross-article diversity system, so only that path should leave a fingerprint in
    history: recording a static/no-op article would poison the diversity window with
    copy this gate never authored or checked (the exact failure the Task-14 review
    warned about)."""
    p = WS_ROOT / task_id / _INJECTION_RESULT
    if not p.exists():
        return False, f"{_INJECTION_RESULT} not found (cta-injection has not run)"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return False, f"{_INJECTION_RESULT} unreadable"
    if not isinstance(data, dict):
        return False, f"{_INJECTION_RESULT} malformed"
    if data.get("passed") is not True:
        return False, "cta-injection did not pass — nothing to record"
    if data.get("draft_source") != "llm":
        return False, (f"cta-injection used draft_source={data.get('draft_source')!r}, "
                       f"not 'llm' — the legacy static path does not participate in the "
                       f"diversity system")
    return True, "eligible"


def record_history_if_eligible(task_id: str, project_slug: str) -> dict[str, Any]:
    """Guarded recorder for the orchestrator's cta-record-history stage.

    Appends this article's CTA fingerprint to projects/{slug}/cta-history.json ONLY
    when the cta-injection stage actually placed the LLM-authored draft
    (draft_source=='llm' AND passed). This is the SEAM the record stage drives; the
    eligibility check lives HERE, in Python (testable per Rule 10), never in a
    fragile shell conditional. A non-eligible article is NOT an error — it is the
    correct no-op for the legacy static path and the no-config projects, so the
    caller (and the stage) treat recorded=false as success."""
    eligible, reason = _injection_used_llm(task_id)
    result: dict[str, Any] = {
        "task_id": task_id, "project_slug": project_slug,
        "recorded": False, "reason": reason,
        "_generated_by": "cta-diversity-check-record",
        "generated_at": _now_iso(),
    }
    if not eligible:
        return result
    record_history(task_id, project_slug)
    result["recorded"] = True
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="CTA cross-article diversity gate")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--project-slug", required=True)
    ap.add_argument("--record", action="store_true",
                     help="append this article's fingerprint to history instead of checking")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", help="also write the JSON result here")
    args = ap.parse_args()

    if args.record:
        rec = record_history_if_eligible(args.task_id, args.project_slug)
        if args.out:
            Path(args.out).write_text(
                json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
        if args.json:
            print(json.dumps(rec, indent=2, ensure_ascii=False))
        else:
            print("cta_diversity_check --record: "
                  + ("recorded" if rec["recorded"] else f"skipped ({rec['reason']})"))
        # Recording is best-effort bookkeeping: a non-eligible article (static path
        # / no-op / injection not yet run) is the CORRECT outcome, never a failure.
        return 0

    result = check_diversity(args.task_id, args.project_slug)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"cta_diversity_check: {'PASS' if result['passed'] else 'FAIL'} "
              f"({len(result['violations'])} violation(s))")
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
