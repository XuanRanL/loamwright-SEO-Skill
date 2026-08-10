"""scripts/lint/section_completeness_check.py — Detect writer-subagent silent dropouts.

Added 2026-05-23 per `feedback_writer_subagent_silent_dropout.md`. Writer subagents
sometimes enter self-correction loops (em-dash trim → keyword-density adjust →
re-check) and exhaust their token budget BEFORE writing their section file. The
dropout is silent: no error, no notification, the agent just returns. The
orchestrator gets nothing to act on. We caught 6/50 such dropouts in the
2026-05-22 5-article batch by manually `ls memory/workspace/{task}/sections/`
after each parallel dispatch. This lint automates that check.

Usage:
    python -m scripts.lint.section_completeness_check --workspace {task_id} [--json]

Exits 0 if all expected sections present. Exits 1 (and reports missing) if
sections/*.md count is less than outline.sections.length.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class SectionCompletenessResult:
    passed: bool
    workspace: str
    expected_count: int        # outline.sections.length
    actual_count: int          # count of sections/*.md
    expected_indices: list[int]  # outline.sections[].index verbatim — ZERO-based: [0, 1, ..., N-1]
    actual_indices: list[int]    # [0, 1, 3, ...] (missing 2 means outline-index-2 dropped)
    missing_indices: list[int]
    extra_indices: list[int]   # files present but not in outline
    detail: str
    # References outline entries exempt from the writer-completeness contract
    # (fact-checker/finalize own that section; assemble auto-appends its stub).
    exempt_indices: list[int] = field(default_factory=list)


def check_section_completeness(workspace_task_id: str) -> SectionCompletenessResult:
    ws = PLUGIN_ROOT / "memory" / "workspace" / workspace_task_id
    if not ws.exists():
        return SectionCompletenessResult(
            passed=False,
            workspace=workspace_task_id,
            expected_count=0, actual_count=0,
            expected_indices=[], actual_indices=[],
            missing_indices=[], extra_indices=[],
            detail=f"Workspace not found: {ws}",
        )

    # Read outline.json
    outline_path = ws / "outline.json"
    if not outline_path.exists():
        return SectionCompletenessResult(
            passed=False,
            workspace=workspace_task_id,
            expected_count=0, actual_count=0,
            expected_indices=[], actual_indices=[],
            missing_indices=[], extra_indices=[],
            detail=f"outline.json not found — cannot determine expected section count",
        )
    try:
        outline = json.loads(outline_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return SectionCompletenessResult(
            passed=False,
            workspace=workspace_task_id,
            expected_count=0, actual_count=0,
            expected_indices=[], actual_indices=[],
            missing_indices=[], extra_indices=[],
            detail=f"outline.json is malformed: {e}",
        )

    all_sections = [s for s in outline.get("sections", []) if isinstance(s, dict)]
    # References is fact-checker/finalize-owned (no writer is ever dispatched for
    # it): assemble.py auto-appends the "## References" stub when no section file
    # supplies one, and finalize-references-signature rebuilds its content from
    # citations.json. So its outline entry is EXEMPT from the writer-completeness
    # contract — before 2026-07-07 every batch operator had to rediscover and
    # hand-create a sections/NN_references.md placeholder just to satisfy this
    # check. A placeholder file, if present anyway, is likewise not "extra".
    exempt_indices = sorted(
        s.get("index", 0) for s in all_sections
        if str(s.get("h2", "")).strip().lower() == "references"
        or s.get("is_references_block")
    )
    expected_indices = sorted(
        s.get("index", 0) for s in all_sections
        if s.get("index", 0) not in set(exempt_indices)
    )
    expected_count = len(expected_indices)

    # Scan sections/*.md
    sections_dir = ws / "sections"
    actual_indices: list[int] = []
    if sections_dir.exists():
        for f in sections_dir.glob("*.md"):
            stem = f.stem
            # Accept both "3.md" (numeric) and "03_slug.md" (prefixed) patterns
            try:
                actual_indices.append(int(stem))
            except ValueError:
                # Try extracting leading digits from "03_slug" pattern
                import re as _re
                m = _re.match(r"^(\d+)", stem)
                if m:
                    actual_indices.append(int(m.group(1)))
    actual_indices = sorted(set(actual_indices))
    actual_count = len(actual_indices)

    missing = sorted(set(expected_indices) - set(actual_indices))
    extra = sorted(set(actual_indices) - set(expected_indices) - set(exempt_indices))

    if missing:
        detail = (
            f"Writer subagent dropped {len(missing)} section(s): {missing}. "
            f"Common cause: self-correction loop exhausted token budget before "
            f"final Write. Fix: re-dispatch the writer subagent(s) for the "
            f"missing indices with explicit FAILSAFE instruction (write current "
            f"best on budget exhaustion). See memory: "
            f"feedback_writer_subagent_silent_dropout.md"
        )
        passed = False
    elif extra:
        detail = (
            f"Extra section files not in outline: {extra}. "
            f"Probably stale from a prior outline revision. Either remove "
            f"the stray files or update outline.json to include them."
        )
        passed = False  # treat as defect — content not described by outline
    else:
        detail = f"All {expected_count} expected sections present."
        passed = True

    return SectionCompletenessResult(
        passed=passed,
        workspace=workspace_task_id,
        expected_count=expected_count,
        actual_count=actual_count,
        expected_indices=expected_indices,
        actual_indices=actual_indices,
        missing_indices=missing,
        extra_indices=extra,
        detail=detail,
        exempt_indices=exempt_indices,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", required=True, help="Workspace task_id (folder name under memory/workspace/)")
    ap.add_argument("--json", action="store_true", help="Emit JSON report to stdout")
    ap.add_argument("--out", type=Path, default=None, help="Write JSON to file (file-bus). Defaults to {workspace}/section-completeness.json when --workspace is set.")
    args = ap.parse_args()

    result = check_section_completeness(args.workspace)
    json_str = json.dumps(asdict(result), indent=2)

    out_path = args.out
    if out_path is None:
        ws_dir = Path(__file__).resolve().parent.parent.parent / "memory" / "workspace" / args.workspace
        out_path = ws_dir / "section-completeness.json"
    out_path.write_text(json_str, encoding="utf-8")

    if args.json:
        print(json_str)
    else:
        flag = "✓ COMPLETE" if result.passed else "✗ DROPOUT DETECTED"
        print(f"{flag} — workspace={result.workspace}")
        print(f"  expected: {result.expected_count} sections {result.expected_indices}")
        print(f"  actual:   {result.actual_count} sections {result.actual_indices}")
        if result.missing_indices:
            print(f"  MISSING: {result.missing_indices}")
        if result.extra_indices:
            print(f"  EXTRA:   {result.extra_indices}")
        print(f"  → {result.detail}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
