#!/usr/bin/env python3
"""
hooks/post_tool_use_schema_validate.py — Validate JSON writes against schemas.

Fires after Edit/Write tool calls. If the written file matches a pattern like
`workspace/{task}/state.json` or `projects/{slug}/business-context.json`, we
validate it against the corresponding schema in schemas/.

Exit codes:
  0  Validation passed (or file not under schema-watched paths)
  1  Validation warnings (non-blocking)
  2  BLOCK — schema violation (the user should fix before continuing)

Schema-to-path mapping:
  workspace/*/state.json                 → state.schema.json
  workspace/*/research.json              → research.schema.json
  workspace/*/angle.json                 → angle.schema.json
  workspace/*/outline.json               → outline.schema.json
  workspace/*/sections/*.json            → section.schema.json
  workspace/*/citations.json             → citations.schema.json
  workspace/*/meta.json                  → meta.schema.json
  workspace/*/quality.json               → quality.schema.json
  workspace/*/review.json                → (no schema yet; skip)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


SCHEMA_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"workspace/[^/]+/state\.json$"),       "state"),
    (re.compile(r"workspace/[^/]+/research\.json$"),    "research"),
    (re.compile(r"workspace/[^/]+/angle\.json$"),       "angle"),
    (re.compile(r"workspace/[^/]+/outline\.json$"),     "outline"),
    (re.compile(r"workspace/[^/]+/sections/[^/]+\.json$"), "section"),
    (re.compile(r"workspace/[^/]+/citations\.json$"),   "citations"),
    (re.compile(r"workspace/[^/]+/meta\.json$"),        "meta"),
    (re.compile(r"workspace/[^/]+/quality\.json$"),     "quality"),
    # `prompts` MUST be an array; a dict-keyed-by-slot_id write fails here loudly
    # at the source (2026-06-29). Hyphen is canonical; underscore tolerated because
    # the designer docs historically named the file image_prompts.json.
    (re.compile(r"workspace/[^/]+/image[-_]prompts\.json$"), "image-prompts"),
    # v3.38.3 (2026-07-10): the image-visual-qa subagent nondeterministically
    # serialized per-slot `verdict` instead of the schema's `final_verdict`
    # (+ missing final_score/round_history) — pre_publish_gate then hard-failed
    # at the very END of the pipeline. Validating at write time surfaces the
    # drift to the agent immediately, when it can still fix its own output.
    (re.compile(r"workspace/[^/]+/image-qa-report\.json$"), "image-qa-report"),
    # 2026-08-02: the fact-checker invented verdict strings ('issues_fixed';
    # 2.1% base rate across 338 historical artifacts) because nothing checked
    # the field at write time — the closed-world pre_publish_gate then failed a
    # substantively clean article at the very end. Same v3.38.3 lesson: catch
    # the contract break at the Write, when the agent can still self-correct.
    (re.compile(r"workspace/[^/]+/fact-check\.json$"), "fact-check"),
]


def _plugin_root() -> Path | None:
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "VERSION").exists() and (p / ".claude-plugin").is_dir():
            return p
        p = p.parent
    return None


def _identify_schema(file_path: str) -> str | None:
    """Match file path against SCHEMA_RULES, return schema name or None."""
    fp = file_path.replace("\\", "/")
    for pattern, schema_name in SCHEMA_RULES:
        if pattern.search(fp):
            return schema_name
    return None


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0

    tool_name = data.get("tool_name", "")
    if tool_name not in {"Edit", "Write", "NotebookEdit"}:
        return 0

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return 0

    schema_name = _identify_schema(file_path)
    if not schema_name:
        return 0   # not watched

    plugin = _plugin_root()
    if not plugin:
        return 0

    schema_file = plugin / "schemas" / f"{schema_name}.schema.json"
    if not schema_file.exists():
        return 0

    # Skip 10MB+ files (per claude-seo pattern)
    try:
        if Path(file_path).stat().st_size > 10 * 1024 * 1024:
            return 0
    except OSError:
        return 0

    # Try to load + validate
    try:
        target_data = json.loads(Path(file_path).read_text(encoding="utf-8"))
    except Exception as e:
        # BLOCK (v3.41.4). This branch used to `return 1` ("warn but don't block —
        # could be partial write"), which was backwards: a watched artifact that is
        # not parseable JSON is strictly WORSE than one that parses but violates its
        # schema (which already blocks with 2). The partial-write rationale does not
        # apply in a PostToolUse hook — the Write/Edit has already fully completed by
        # the time we run, so what we read IS the final file.
        #
        # Rule-12 class defect: the gate ran, printed, and let the bad artifact
        # through. Cost on 2026-07-24: an Edit split a JSON string in outline.json,
        # the hook said nothing blocking, and the failure surfaced two stages later
        # inside run_pipeline as the far less obvious "LLM stage 'outline-architect'
        # did not produce valid outputs" (orchestrator._artifact_valid swallows
        # JSONDecodeError and just returns False, naming no reason).
        print(f"[schema-validate] ✗ {file_path}: not parseable JSON: {e}", file=sys.stderr)
        print("    A watched artifact must be valid JSON. Re-read the file around the "
              "reported line/column — a split string or a stray quote from a partial "
              "Edit is the usual cause.", file=sys.stderr)
        return 2   # BLOCK the write

    try:
        from jsonschema import Draft202012Validator
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        errors = list(validator.iter_errors(target_data))
    except ImportError:
        return 0   # jsonschema not installed; skip
    except Exception as e:
        print(f"[schema-validate] schema load error: {e}", file=sys.stderr)
        return 1

    if errors:
        print(f"[schema-validate] ✗ {file_path} fails schema '{schema_name}':", file=sys.stderr)
        for err in errors[:5]:
            path = " / ".join(str(p) for p in err.absolute_path)
            print(f"    {path}: {err.message}", file=sys.stderr)
        if len(errors) > 5:
            print(f"    ... and {len(errors) - 5} more", file=sys.stderr)
        return 2   # BLOCK the write

    return 0


if __name__ == "__main__":
    sys.exit(main())
