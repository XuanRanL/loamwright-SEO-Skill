"""scripts/publish/indexing_notify.py — post-publish indexing ping (IndexNow).

The hop that was documented for months and never wired (Rule 6, found by the
2026-08-12 wiring audit): `subskills/publish/indexing-notifier/SKILL.md` claimed
"Triggered as final step of phase-publish" while the orchestrator's STAGES table
ended at `verify-post`, and the only caller of `indexnow_submit` was the dead
`agents/publisher.md`. No article this pipeline published was ever submitted.

Wired as the `indexing-notifier` stage (after `verify-post`) as of v3.42.12.

Contract — this is a NOTIFIER, not a gate:

- The pipeline's terminal state is a DRAFT (Rule 5a). A draft URL must never be
  submitted to an index, so on a draft post the outcome is ``skipped_draft`` and
  the stage completes. After the operator flips the post live, re-run this
  script directly (the publish-confirmation flows in `skills/weekly-digest` and
  `skills/phase-publish` document the exact command).
- Submission is a best-effort accelerator. A Bing hiccup or missing key must
  not block a pipeline whose article already published and verified — the same
  never-blocks contract as image-visual-qa. Failures are therefore recorded
  HONESTLY in ``indexing-result.json :: outcome`` (``submit_failed`` /
  ``no_credentials`` / ``transport_error`` — each distinct, Rule 13: a transport
  failure is never a content verdict) but exit 0. Exit 2 is reserved for
  invocation errors (no workspace / no publish-result.json), which mean the
  stage was dispatched wrongly and SHOULD fail loudly.
- GSC URL-inspection submission stays a documented manual step
  (`scripts/publish/gsc_submit.py`): it needs per-site OAuth and has strict
  quotas, so pinging it unconditionally from every pipeline run would burn
  quota on the 13-site fleet. IndexNow covers Bing + ChatGPT-via-Bing + Yandex.

Usage:
    python -m scripts.publish.indexing_notify {project_slug} --workspace {task_id} --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
WS_ROOT = PLUGIN_ROOT / "memory" / "workspace"

RESULT_FILENAME = "indexing-result.json"

#: outcome enum — every value states what actually happened (Rule 12/14: the
#: artifact carries a verdict, and each failure mode is distinguishable).
OUTCOME_SUBMITTED = "submitted"
OUTCOME_SKIPPED_DRAFT = "skipped_draft"
OUTCOME_NO_CREDENTIALS = "no_credentials"
OUTCOME_TRANSPORT_ERROR = "transport_error"
OUTCOME_SUBMIT_FAILED = "submit_failed"


def resolve_live_post(project_slug: str, post_id: str) -> tuple[str | None, str | None, str | None]:
    """Return (status, link, error). error is set ONLY on transport failure.

    Reads the REST object rather than trusting workspace state: the operator may
    have flipped the post live (or trashed it) since publish-result.json was
    written, and `verify_post`'s expected_status field has been observed to be
    unreliable — the live object is the truth.
    """
    try:
        from scripts.wordpress.wp_client import WPClient

        wp = WPClient(project_slug)
        r = wp.get(f"/wp/v2/posts/{post_id}", params={"context": "edit"})
        data = r.json_data or {}
        if r.status >= 400:
            return None, None, f"HTTP {r.status} reading post {post_id}"
        return str(data.get("status") or ""), str(data.get("link") or ""), None
    except Exception as exc:  # transport, credentials, DNS — NOT a content verdict
        return None, None, f"{type(exc).__name__}: {exc}"


def notify(project_slug: str, task_id: str) -> dict[str, Any]:
    """Run the notification decision tree; return the result document (pure-ish:
    all I/O behind small seams so tests can drive every outcome)."""
    ws = WS_ROOT / task_id
    result: dict[str, Any] = {
        "_generated_by": "indexing-notify",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_slug": project_slug,
        "task_id": task_id,
        "outcome": None,
        "post_id": None,
        "url": None,
        "detail": None,
    }

    pr_path = ws / "publish-result.json"
    try:
        post_id = str(json.loads(pr_path.read_text(encoding="utf-8")).get("post_id") or "")
    except (OSError, ValueError):
        post_id = ""
    if not post_id:
        result["outcome"] = "invocation_error"
        result["detail"] = f"no post_id in {pr_path}"
        return result
    result["post_id"] = post_id

    status, link, transport_err = resolve_live_post(project_slug, post_id)
    if transport_err:
        result["outcome"] = OUTCOME_TRANSPORT_ERROR
        result["detail"] = transport_err
        return result

    if status != "publish":
        result["outcome"] = OUTCOME_SKIPPED_DRAFT
        result["detail"] = (
            f"post status is '{status}' — drafts are never submitted (Rule 5a). "
            "Re-run this script after flipping the post live."
        )
        return result

    result["url"] = link
    try:
        from scripts.publish.indexnow_submit import submit

        sub = submit([link], project_slug=project_slug)
    except Exception as exc:
        result["outcome"] = OUTCOME_SUBMIT_FAILED
        result["detail"] = f"{type(exc).__name__}: {exc}"
        return result

    if sub.success:
        result["outcome"] = OUTCOME_SUBMITTED
        result["detail"] = f"IndexNow {sub.status_code}, {len(sub.submitted_urls)} URL(s)"
        return result

    # `submit()` collapses its exceptions into a string error field, so type
    # information is gone at this boundary and message matching is the only
    # classifier available (Rule 9's fallback clause). Verified against the real
    # message credential_hub produces ("Bing IndexNow not configured. Set
    # credentials/bing-indexnow/{slug}.json … or BING_INDEXNOW_… env vars.",
    # pinned by test) — the first live run of
    # this module classified that as submit_failed because it only looked for
    # the word "credential", which the real message does not contain.
    err = str(sub.error or "")
    if "not configured" in err.lower() or "bing_indexnow" in err.lower() or "credential" in err.lower():
        result["outcome"] = OUTCOME_NO_CREDENTIALS
        result["detail"] = err
    else:
        result["outcome"] = OUTCOME_SUBMIT_FAILED
        result["detail"] = err or f"IndexNow returned {sub.status_code}"
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Submit a published post's URL to IndexNow")
    ap.add_argument("project_slug")
    ap.add_argument("--workspace", required=True, help="task_id under memory/workspace/")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ws = WS_ROOT / args.workspace
    if not ws.exists():
        print(f"workspace not found: {ws}", file=sys.stderr)
        return 2

    result = notify(args.project_slug, args.workspace)

    out = ws / RESULT_FILENAME
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[indexing-notify] {result['outcome']}: {result.get('detail')}")

    # Invocation errors fail loudly; everything else completes with an honest
    # outcome on record (notifier contract — see module docstring).
    return 2 if result["outcome"] == "invocation_error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
