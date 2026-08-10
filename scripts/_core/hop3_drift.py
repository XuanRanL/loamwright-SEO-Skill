"""scripts/_core/hop3_drift.py — one definition of "the deployed copy is stale".

Rule 13 says a 3-hop artifact needs a hop 2→3 executor with a `--check` mode, and
that "a `--check` that exits non-zero on drift is what turns 'we think it shipped'
into a fact". When that sentence was written, exactly one of the four tools in the
rule's own inventory table satisfied it: the three incumbent reinject tools exited
0 whether or not a dry run found stale posts, so drift was reported in prose that
no caller could act on. The rule was written from the newest tool and the
incumbents were never checked against it — Rule 11, committed the same day as the
rule.

So the mapping from a report to an exit code lives HERE, once, and every hop 2→3
tool calls it. A per-tool choice is how the four drifted apart in the first place.

The contract every reinject-style report already satisfies:
    report["updated"] — entries that WOULD change (in dry-run) or DID change
    report["errors"]  — entries that could not be processed

Under `--check` nothing is written, so a non-empty `updated` IS the drift.
"""
from __future__ import annotations

from typing import Any


def drift_count(report: dict[str, Any]) -> int:
    """How many deployed copies differ from what hop 2 would produce."""
    return len(report.get("updated") or [])


def check_exit_code(report: dict[str, Any]) -> int:
    """Exit code for a `--check` run: non-zero when stale OR unreadable.

    Errors count as non-zero deliberately. "I could not read the deployed copy"
    is not evidence that it matches — reporting success there is the same mistake
    as calling a transport failure a content verdict.
    """
    return 1 if (drift_count(report) or report.get("errors")) else 0


def format_check(report: dict[str, Any], *, artifact: str,
                 fix_hint: str = "run --apply to fix") -> str:
    """Human line for a `--check` run."""
    n = drift_count(report)
    errs = len(report.get("errors") or [])
    project = report.get("project", "?")
    if not n and not errs:
        return (f"[{project}] {artifact}: in sync "
                f"({report.get('scanned', 0)} checked)")
    parts = []
    if n:
        parts.append(f"{n} DRIFTED")
    if errs:
        parts.append(f"{errs} unreadable")
    return (f"[{project}] {artifact}: " + ", ".join(parts)
            + f" of {report.get('scanned', 0)} checked — {fix_hint}")
