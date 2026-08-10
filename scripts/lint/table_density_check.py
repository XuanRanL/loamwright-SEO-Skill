#!/usr/bin/env python3
"""Table density check — verifies >=2 markdown tables with >=1 in front half.

Enforces the chart-generator spec: every article must contain at least 2
data tables (comparison, specification, stage-by-stage, etc.) with at
least one appearing in the first 50% of the article body.

Usage:
    python -m scripts.lint.table_density_check --workspace {task_id} [--json]

Exit codes:
    0 = passed (>=2 tables, >=1 in front half)
    1 = failed
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent


def _find_tables(content: str) -> list[dict]:
    """Find markdown tables in content, return their positions and row counts."""
    lines = content.split("\n")
    tables = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if re.match(r"^\|.*\|.*\|$", line):
            table_start = i
            table_lines = []
            while i < len(lines) and re.match(r"^\|.*\|", lines[i].strip()):
                table_lines.append(lines[i])
                i += 1
            has_separator = any(
                re.match(r"^\|[\s\-:|]+\|$", tl.strip())
                for tl in table_lines
            )
            if has_separator and len(table_lines) >= 3:
                char_pos = sum(len(lines[j]) + 1 for j in range(table_start))
                tables.append({
                    "line_start": table_start + 1,
                    "row_count": len(table_lines) - 1,
                    "char_position": char_pos,
                })
        else:
            i += 1
    return tables


def check(task_id: str) -> dict:
    ws = PLUGIN_ROOT / "memory" / "workspace" / task_id
    draft = ws / "draft.md"

    if not draft.exists():
        return {"passed": False, "error": "draft.md not found", "tables": []}

    content = draft.read_text(encoding="utf-8")
    body_start = content.find("\n---\n")
    if body_start > 0:
        body = content[body_start + 5:]
    else:
        body = content

    tables = _find_tables(body)
    total_len = len(body)
    midpoint = total_len // 2

    tables_in_front_half = [t for t in tables if t["char_position"] < midpoint]

    passed = len(tables) >= 2 and len(tables_in_front_half) >= 1

    return {
        "passed": passed,
        "table_count": len(tables),
        "tables_in_front_half": len(tables_in_front_half),
        "minimum_required": 2,
        "front_half_required": 1,
        "tables": tables,
        "defects": [] if passed else [
            *(
                [f"Only {len(tables)} table(s) found, minimum 2 required"]
                if len(tables) < 2 else []
            ),
            *(
                [f"No tables in front 50% of article body"]
                if len(tables_in_front_half) < 1 and len(tables) >= 2 else []
            ),
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Table density check")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = check(args.workspace)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["passed"]:
            print(f"  [OK] {result['table_count']} tables found, {result['tables_in_front_half']} in front half.")
        else:
            print(f"  [FAIL] Table density check failed:")
            for d in result.get("defects", []):
                print(f"    - {d}")

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
