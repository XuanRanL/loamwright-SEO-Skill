#!/usr/bin/env python3
"""
hooks/post_tool_use_artifact_gate.py — Enforce auditor-output frontmatter.

Fires after Edit/Write. If the file is at memory/audits/*.md or
projects/{slug}/audits/*.md, the YAML frontmatter MUST contain `class: auditor-output`
plus the required fields (verdict, vetoes_triggered, ready_verdict_allowed).

This prevents silently shipping audit results without the structural commitment.
Borrowed from seo-geo-claude-skills pattern.

Exit codes:
  0  Passed (or file not in audits/)
  1  Warning
  2  BLOCK
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


_AUDIT_PATH_RE = re.compile(
    r"(memory/audits/[^/]+\.md|projects/[^/]+/audits/[^/]+\.md)$"
)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

REQUIRED_FIELDS = {"class", "verdict", "raw_overall_score", "final_overall_score"}


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0

    tool_name = data.get("tool_name", "")
    if tool_name not in {"Edit", "Write"}:
        return 0

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return 0

    fp = file_path.replace("\\", "/")
    if not _AUDIT_PATH_RE.search(fp):
        return 0  # not an audit file

    p = Path(file_path)
    if not p.exists():
        return 0

    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return 1

    m = _FRONTMATTER_RE.match(text)
    if not m:
        print(f"[artifact-gate] ✗ {file_path}: missing YAML frontmatter.",
              file=sys.stderr)
        print(f"[artifact-gate]   Audit files require: class: auditor-output, verdict, scores",
              file=sys.stderr)
        return 2

    fm_text = m.group(1)
    # Simple key extraction (no need for full YAML parser)
    found_keys: set[str] = set()
    class_value = None
    for line in fm_text.splitlines():
        s = line.strip()
        if ":" in s and not s.startswith("#"):
            k, _, v = s.partition(":")
            k = k.strip()
            found_keys.add(k)
            if k == "class":
                class_value = v.strip().strip('"').strip("'")

    if class_value != "auditor-output":
        print(f"[artifact-gate] ✗ {file_path}: frontmatter `class` is {class_value!r}, "
              f"expected 'auditor-output'.", file=sys.stderr)
        return 2

    missing = REQUIRED_FIELDS - found_keys
    if missing:
        print(f"[artifact-gate] ✗ {file_path}: missing required fields: {sorted(missing)}",
              file=sys.stderr)
        return 2

    # Optional: parse verdict
    verdict_value = None
    for line in fm_text.splitlines():
        s = line.strip()
        if s.startswith("verdict:"):
            verdict_value = s.split(":", 1)[1].strip().strip('"').strip("'")
            break

    if verdict_value not in {"SHIP", "FIX", "BLOCKED"}:
        print(f"[artifact-gate] ⚠ {file_path}: verdict {verdict_value!r} not in standard set",
              file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
