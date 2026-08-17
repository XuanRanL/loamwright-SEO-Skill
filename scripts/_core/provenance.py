"""scripts/_core/provenance.py — SINGLE source of truth for `_generated_by` provenance.

v3.41.3 root cure (2026-07-19 contract-gap audit): the orchestrator's
``_PROVENANCE_REQUIRED`` and pre_publish_gate's ``PROVENANCE_REQUIREMENTS``
were two hand-maintained dicts that shared only 3 of 7 entries — the
orchestrator gated geo-audit/visual-design-report/cta-draft but not
image-qa-report; the gate did the reverse. Same Rule-12 disease as the
render-lint/check-06 split: two places checking "the same fact" drifted apart.
Both now import THIS dict. The linker's internal-link-report.json — whose
dispatch prompt demanded ``_generated_by`` that nothing enforced — is included
so the demand is real.

Rule 11: every artifact listed here MUST have its accepted value stated in the
owning ``agents/<name>.md`` (and the dispatching prompt). Pinned by
``tests/test_provenance_contract_fanout.py``.

v3.42.12 (2026-08-12) — ADVISORY provenance for script-PRE-WRITTEN artifacts.
``skills/weekly-digest/SKILL.md`` step 5 pre-writes 5 pipeline artifacts so the
orchestrator can skip research/plan.  Two of them (``outline.json``,
``image-prompts.json``) are owned by REAL LLM stages, and because neither was
listed here, ``_artifact_valid()`` waved them through on existence alone: on the
2026-08-12 run ``outline-architect`` and ``image-prompt-designer`` both recorded
``completed`` 3 MILLISECONDS apart without ever dispatching, and the deletion was
invisible in ``state.json``.  ``PROVENANCE_ADVISORY`` makes "a script wrote this,
not its owning agent" a CHECKABLE fact (``scan_workspace`` / ``--check``).

Why advisory and not ``PROVENANCE_REQUIRED``: the orchestrator EXACT-matches that
dict (``gen_by not in _PROVENANCE_REQUIRED[name]``), the outline-architect stamps
a free-form dispatch suffix (``"outline-architect (orchestrator dispatch, batch-…
entry 1/3)"``), and ``image-prompts.json`` has NEVER carried the field at all —
so hard-gating either one would block every non-digest article run.  The
classifier below is prefix-tolerant precisely so an agent-authored value keeps
validating.

CLI (Rule 14 — a check that cannot fail is not a check)::

    python -m scripts._core.provenance --task-id {tid} --check --json
    python -m scripts._core.provenance --workspace {dir} --check

    exit 0  every registered artifact present is agent-authored
    exit 1  an artifact is unreadable, or carries an unrecognized value
    exit 2  an artifact was script-PRE-WRITTEN (its LLM stage was skipped)
    exit 3  an artifact is present but unstamped (provenance unknowable)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# artifact filename -> accepted _generated_by values
PROVENANCE_REQUIRED: dict[str, list[str]] = {
    "fact-check.json": ["fact-checker-subagent", "fact-checker-agent-v2"],
    "humanizer-report.json": ["humanizer-subagent"],
    "review.json": ["reviewer-subagent", "independent-reviewer"],
    "geo-audit.json": ["geo-auditor-subagent", "geo-auditor"],
    "visual-design-report.json": ["visual-designer-subagent"],
    "cta-draft.json": ["cta-writer-subagent"],
    "image-qa-report.json": ["image-visual-qa-subagent"],
    "internal-link-report.json": ["linker-subagent"],
}

# artifact filename -> the agent definition file that owns producing it
# (used by the fan-out regression test; keep in sync when adding entries).
PROVENANCE_OWNING_AGENT: dict[str, str] = {
    "fact-check.json": "agents/fact-checker.md",
    "humanizer-report.json": "agents/humanizer.md",
    "review.json": "agents/reviewer.md",
    "geo-audit.json": "agents/geo-auditor.md",
    "visual-design-report.json": "agents/visual-designer.md",
    "cta-draft.json": "agents/cta-writer.md",
    "image-qa-report.json": "agents/image-visual-qa.md",
    "internal-link-report.json": "agents/linker.md",
}

# ---------------------------------------------------------------------------
# Advisory provenance — artifacts an LLM stage OWNS but a script may PRE-WRITE
# ---------------------------------------------------------------------------

#: value stamped by scripts/research/digest_artifacts.py :: write_artifacts
PREWRITER_WEEKLY_DIGEST: str = "weekly-digest-prewriter"

#: every recognized script pre-writer (a value here means "an LLM stage was skipped")
SCRIPT_PREWRITERS: frozenset[str] = frozenset({PREWRITER_WEEKLY_DIGEST})

# artifact filename -> accepted _generated_by values (owning agent FIRST)
PROVENANCE_ADVISORY: dict[str, list[str]] = {
    "outline.json": ["outline-architect", PREWRITER_WEEKLY_DIGEST],
    "image-prompts.json": ["image-prompt-designer", PREWRITER_WEEKLY_DIGEST],
}

# artifact filename -> the pipeline stage that is SKIPPED when a script pre-wrote it
PROVENANCE_ADVISORY_OWNING_STAGE: dict[str, str] = {
    "outline.json": "outline-architect",
    "image-prompts.json": "image-prompt-designer",
}

# classify() verdicts
AGENT_AUTHORED = "agent"
SCRIPT_PREWRITTEN = "prewriter"
UNKNOWN_VALUE = "unknown"
UNSTAMPED = "unstamped"
UNREGISTERED = "unregistered"

# scan/--check exit codes
EXIT_OK = 0
EXIT_DEFECT = 1        # unreadable file OR unrecognized _generated_by value
EXIT_PREWRITTEN = 2    # a script wrote an artifact its LLM stage owns
EXIT_UNSTAMPED = 3     # present, but provenance unknowable


def accepted_values(artifact: str) -> list[str]:
    """Accepted ``_generated_by`` values for *artifact* ([] when unregistered)."""
    return list(PROVENANCE_REQUIRED.get(artifact) or PROVENANCE_ADVISORY.get(artifact) or [])


def classify(artifact: str, value: str | None) -> str:
    """Classify a ``_generated_by`` value.

    Prefix-tolerant on purpose: the real outline-architect stamp is
    ``"outline-architect (orchestrator dispatch, batch-… entry 1/3)"`` and an
    exact-match rule would call the agent's own output invalid.
    """
    accepted = accepted_values(artifact)
    if not accepted:
        return UNREGISTERED
    text = str(value).strip() if value is not None else ""
    if not text:
        return UNSTAMPED
    low = text.lower()
    for acc in accepted:
        a = acc.lower()
        if low == a or low.startswith(a):
            return SCRIPT_PREWRITTEN if acc in SCRIPT_PREWRITERS else AGENT_AUTHORED
    return UNKNOWN_VALUE


def scan_workspace(ws_dir: Path | str) -> dict[str, Any]:
    """Read every registered artifact in *ws_dir* and report who authored it.

    A missing artifact is NOT a finding (the orchestrator's existence check owns
    that question); an artifact that exists but cannot be read IS one — "I could
    not read it" is never "it matches" (Rule 12/13).
    """
    ws = Path(ws_dir)
    artifacts: dict[str, dict[str, Any]] = {}
    prewritten: list[str] = []
    unknown: list[str] = []
    unstamped: list[str] = []
    unreadable: list[str] = []
    absent: list[str] = []

    for name in sorted(set(PROVENANCE_REQUIRED) | set(PROVENANCE_ADVISORY)):
        path = ws / name
        if not path.is_file():
            absent.append(name)
            artifacts[name] = {"status": "absent"}
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            unreadable.append(name)
            artifacts[name] = {"status": "unreadable", "error": str(exc)}
            continue
        value = data.get("_generated_by") if isinstance(data, dict) else None
        verdict = classify(name, value)
        artifacts[name] = {
            "status": verdict,
            "generated_by": value,
            "accepted": accepted_values(name),
        }
        if verdict == SCRIPT_PREWRITTEN:
            prewritten.append(name)
        elif verdict == UNKNOWN_VALUE:
            unknown.append(name)
        elif verdict == UNSTAMPED:
            unstamped.append(name)

    skipped_stages = sorted(
        {PROVENANCE_ADVISORY_OWNING_STAGE[n] for n in prewritten
         if n in PROVENANCE_ADVISORY_OWNING_STAGE}
    )
    return {
        "workspace": str(ws),
        "artifacts": artifacts,
        "prewritten": prewritten,
        "skipped_stages": skipped_stages,
        "unknown": unknown,
        "unstamped": unstamped,
        "unreadable": unreadable,
        "absent": absent,
    }


def exit_code(report: dict[str, Any]) -> int:
    """Severity of a :func:`scan_workspace` report (worst finding wins)."""
    if report.get("unreadable") or report.get("unknown"):
        return EXIT_DEFECT
    if report.get("prewritten"):
        return EXIT_PREWRITTEN
    if report.get("unstamped"):
        return EXIT_UNSTAMPED
    return EXIT_OK


def _default_workspace(task_id: str) -> Path:
    # scripts/_core/provenance.py -> parents[2] == plugin root
    return Path(__file__).resolve().parents[2] / "memory" / "workspace" / task_id


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Report which workspace artifacts an agent authored and which "
                    "a script pre-wrote (i.e. whose LLM stage was skipped)."
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--task-id", help="workspace under memory/workspace/{task_id}")
    src.add_argument("--workspace", help="explicit workspace directory")
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero on a finding (0 clean / 1 defect / 2 pre-written / 3 unstamped)")
    ap.add_argument("--json", action="store_true", dest="json_output")
    args = ap.parse_args(argv)

    ws = Path(args.workspace) if args.workspace else _default_workspace(args.task_id)
    if not ws.is_dir():
        # transport failure != content verdict
        msg = {"error": "workspace not found", "workspace": str(ws)}
        sys.stdout.write(json.dumps(msg) + "\n") if args.json_output else print(msg["error"], ws)
        return EXIT_DEFECT if args.check else 0

    report = scan_workspace(ws)
    code = exit_code(report)
    report["exit_code"] = code
    if args.json_output:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    else:
        for name, info in report["artifacts"].items():
            if info["status"] == "absent":
                continue
            print(f"{name:28} {info['status']:12} {info.get('generated_by')!r}")
        if report["prewritten"]:
            print("\nSCRIPT-PRE-WRITTEN (owning LLM stage skipped): "
                  + ", ".join(report["prewritten"]))
            print("skipped stages: " + ", ".join(report["skipped_stages"]))
    return code if args.check else 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
