"""scripts/wordpress/flip_post_live.py — THE executor for the draft→publish flip.

Why this exists (2026-08-17 audit): the flip procedure — PATCH status → re-verify
the PUBLIC live URL → re-run the indexing notifier (whose in-pipeline run correctly
recorded `skipped_draft` on the draft, Rule 5a) — existed only as a checklist
duplicated across THREE instruction layers (skills/phase-publish/SKILL.md step 9,
skills/weekly-digest/SKILL.md step 9, skills/seo-blog/SKILL.md pipeline sketch), and
nothing machine-verified that a flipped post's workspace ever reached
`indexing-result.json :: outcome == "submitted"`. That is the Rule 6/11/14 triple:
markdown-only wiring, a contract fanned out across layers with no single owner, and
a promise nothing can check. This script is the single owner; the three SKILL.md
checklists now just invoke it.

What it does, in order (each step's result lands in flip-result.json — Rule 12: the
artifact carries its own verdict, not just its existence):

1. PATCH  /wp/v2/posts/{id}  {"status": "publish"}   (refuses if already publish
   unless --force-reverify; refuses on any non-2xx)
2. Re-verify the PUBLIC live URL via scripts.wordpress.verify_post with
   --expected-status publish, written to verify-live-result.json (a DISTINCT file —
   the draft-phase verify-result.json is a completed gate record; overwriting it
   would rewrite pipeline history)
3. Re-run scripts.publish.indexing_notify (the post-flip run is the one that can
   actually submit) and read its outcome.

Exit codes (each failure mode distinguishable, Rule 13's transport-vs-content rule):
  0  flipped + live verification PASSED + indexing outcome == submitted
  2  flipped + live verification PASSED, but indexing did NOT submit
     (no_credentials / transport_error / submit_failed — the flip itself is good;
     the indexing gap is reported loudly, never silently)
  1  hard failure: PATCH failed, or live verification FAILED (overall_pass false),
     or verify/notify could not run at all

Rule 5a note: this script is the EXPLICIT publish action. It must only ever be run
after the user's publish confirmation (or a project-level publish_policy.default ==
"publish" pre-authorization). It never runs inside the draft-first pipeline.

Usage:
    python -m scripts.wordpress.flip_post_live {project_slug} --workspace {task_id} --json
    # post_id is read from the workspace's publish-result.json; or pass --post-id
    # explicitly for a post without a workspace (older articles).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
WS_ROOT = PLUGIN_ROOT / "memory" / "workspace"

RESULT_FILENAME = "flip-result.json"
LIVE_VERIFY_FILENAME = "verify-live-result.json"

EXIT_OK = 0
EXIT_HARD_FAIL = 1
EXIT_INDEXING_GAP = 2


def _patch_status(project_slug: str, post_id: int) -> tuple[str | None, str | None]:
    """PATCH the post to publish. Returns (live_link, error). error set on failure."""
    try:
        from scripts.wordpress.wp_client import WPClient

        with WPClient(project_slug) as wp:
            r = wp.post(f"/wp/v2/posts/{post_id}", json={"status": "publish"})
            data = r.json_data or {}
            if r.status >= 400:
                return None, f"HTTP {r.status} on status PATCH: {str(data)[:300]}"
            new_status = str(data.get("status") or "")
            if new_status != "publish":
                return None, f"PATCH returned status={new_status!r}, not 'publish'"
            return str(data.get("link") or ""), None
    except Exception as exc:  # transport/auth — a hard failure, never a silent pass
        return None, f"{type(exc).__name__}: {exc}"


def _read_status(project_slug: str, post_id: int) -> tuple[str | None, str | None]:
    from scripts.publish.indexing_notify import resolve_live_post

    status, _link, err = resolve_live_post(project_slug, str(post_id))
    return status, err


def _run_verify(project_slug: str, post_id: int, task_id: str | None) -> tuple[bool | None, str, Path | None]:
    """Run verify_post with --expected-status publish. Returns (overall_pass, detail, out_path)."""
    out_path: Path | None = None
    cmd = [sys.executable, "-m", "scripts.wordpress.verify_post",
           project_slug, str(post_id), "--expected-status", "publish", "--json"]
    if task_id:
        out_path = WS_ROOT / task_id / LIVE_VERIFY_FILENAME
        cmd += ["--workspace", task_id, "--out", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=PLUGIN_ROOT)
    if out_path and out_path.exists():
        try:
            vr = json.loads(out_path.read_text(encoding="utf-8"))
            return bool(vr.get("overall_pass")), f"exit={proc.returncode}", out_path
        except ValueError:
            return None, f"unreadable {out_path.name} (exit={proc.returncode})", out_path
    # no workspace: fall back to parsing stdout
    try:
        vr = json.loads(proc.stdout)
        return bool(vr.get("overall_pass")), f"exit={proc.returncode}", None
    except ValueError:
        return None, (f"verify_post produced no parseable result "
                      f"(exit={proc.returncode}): {proc.stderr[-300:]}"), None


def _run_indexing(project_slug: str, task_id: str | None) -> tuple[str, str]:
    """Re-run the indexing notifier. Returns (outcome, detail)."""
    if not task_id:
        return "skipped_no_workspace", ("no --workspace given; indexing_notify needs "
                                        "publish-result.json — submit manually if needed")
    from scripts.publish.indexing_notify import notify

    result = notify(project_slug, task_id)
    return str(result.get("outcome")), str(result.get("detail") or "")


def flip(project_slug: str, task_id: str | None, post_id: int | None,
         force_reverify: bool = False) -> dict[str, Any]:
    """The whole flip, as one auditable document."""
    doc: dict[str, Any] = {
        "_generated_by": "flip-post-live",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_slug": project_slug,
        "task_id": task_id,
        "post_id": post_id,
        "patched": False,
        "live_verify_pass": None,
        "indexing_outcome": None,
        "exit_code": EXIT_HARD_FAIL,
        "detail": None,
    }

    if post_id is None and task_id:
        try:
            pr = json.loads((WS_ROOT / task_id / "publish-result.json").read_text(encoding="utf-8"))
            post_id = int(pr.get("post_id"))
            doc["post_id"] = post_id
        except (OSError, ValueError, TypeError):
            doc["detail"] = f"no post_id: pass --post-id or provide a workspace with publish-result.json"
            return doc
    if post_id is None:
        doc["detail"] = "no post_id and no workspace"
        return doc

    status, err = _read_status(project_slug, post_id)
    if err:
        doc["detail"] = f"cannot read live post before PATCH (transport, not content): {err}"
        return doc

    if status == "publish":
        if not force_reverify:
            doc["detail"] = ("post is ALREADY publish — refusing the redundant PATCH. "
                            "Re-run with --force-reverify to run verification+indexing only.")
            return doc
        doc["patched"] = "already_publish"
    else:
        link, err = _patch_status(project_slug, post_id)
        if err:
            doc["detail"] = f"status PATCH failed: {err}"
            return doc
        doc["patched"] = True
        doc["live_url"] = link

    ok, detail, out_path = _run_verify(project_slug, post_id, task_id)
    doc["live_verify_pass"] = ok
    doc["live_verify_detail"] = detail
    if out_path:
        doc["live_verify_file"] = str(out_path)
    if ok is not True:
        doc["detail"] = ("post is LIVE but the live-URL verification did not pass — "
                        "fix the live post; do NOT treat this flip as complete "
                        f"({detail}; see {LIVE_VERIFY_FILENAME})")
        return doc

    outcome, idetail = _run_indexing(project_slug, task_id)
    doc["indexing_outcome"] = outcome
    doc["indexing_detail"] = idetail
    if outcome == "submitted":
        doc["exit_code"] = EXIT_OK
        doc["detail"] = "flipped, live-verified, submitted to IndexNow"
    else:
        doc["exit_code"] = EXIT_INDEXING_GAP
        doc["detail"] = (f"flipped and live-verified, but indexing outcome is "
                        f"{outcome!r} ({idetail}) — the URL was NOT submitted; "
                        f"resolve and re-run indexing_notify")
    return doc


def _record_stage(task_id: str | None, doc: dict[str, Any]) -> None:
    """Stage-tracking per references/orchestration/stage-tracking.md — tolerant:
    tracking failures warn on stderr, never block the flip (wp_publisher pattern)."""
    if not task_id:
        return
    try:
        from scripts._core import file_bus as fb

        fb.record_stage_start(task_id, "publish-flip", phase="publish")
        status = "completed" if doc.get("exit_code") in (EXIT_OK, EXIT_INDEXING_GAP) else "failed"
        fb.record_stage_complete(task_id, "publish-flip", status=status)
    except Exception as exc:
        print(f"[flip_post_live] stage-tracking failed (non-blocking): {exc}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Draft→publish flip: PATCH + live re-verify + indexing re-run")
    ap.add_argument("project_slug")
    ap.add_argument("--workspace", help="task_id under memory/workspace/ (post_id read from publish-result.json)")
    ap.add_argument("--post-id", type=int, help="explicit post id (for posts without a workspace)")
    ap.add_argument("--force-reverify", action="store_true",
                    help="post already publish: skip the PATCH, run verification+indexing anyway")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    doc = flip(args.project_slug, args.workspace, args.post_id, args.force_reverify)

    if args.workspace:
        try:
            out = WS_ROOT / args.workspace / RESULT_FILENAME
            out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            print(f"[flip_post_live] could not write {RESULT_FILENAME}: {exc}", file=sys.stderr)
        _record_stage(args.workspace, doc)

    if args.json:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        print(f"flip: patched={doc.get('patched')} verify={doc.get('live_verify_pass')} "
              f"indexing={doc.get('indexing_outcome')} → {doc.get('detail')}")
    return int(doc.get("exit_code", EXIT_HARD_FAIL))


if __name__ == "__main__":
    raise SystemExit(main())
