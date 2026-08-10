"""scripts/build/citation_capsule_compiler.py — Compile sections' citation_capsule fields into final draft.

Each section.schema.json may have a citation_capsule field (40-60 word AI-quotable block).
This script ensures every H2 section in the assembled draft contains its capsule.

Usage:
    python -m scripts.build.citation_capsule_compiler workspace/{task_id}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def compile_capsules(workspace_dir: Path) -> dict:
    """Read sections/*.json + draft.md; inject capsules; rewrite draft.md."""
    sections_dir = workspace_dir / "sections"
    draft_path = workspace_dir / "draft.md"
    if not sections_dir.exists() or not draft_path.exists():
        raise FileNotFoundError(f"Missing sections/ or draft.md in {workspace_dir}")

    section_files = sorted(sections_dir.glob("*.json"), key=lambda p: int(p.stem))
    capsules: dict[str, str] = {}
    for f in section_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            h2 = data.get("h2", "")
            cap = data.get("citation_capsule", {})
            if cap and cap.get("text"):
                capsules[h2] = cap["text"]
        except Exception:
            continue

    text = draft_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out_lines: list[str] = []
    i = 0
    injected = 0

    while i < len(lines):
        line = lines[i]
        out_lines.append(line)
        # Detect H2
        h2_match = line.lstrip().startswith("## ") and not line.lstrip().startswith("### ")
        if h2_match:
            h2_text = line.lstrip()[3:].strip()
            # Strip {#anchor} suffix if present
            h2_text = h2_text.split("{#")[0].strip()
            if h2_text in capsules:
                # Insert capsule right after heading (before next content)
                cap_text = capsules[h2_text]
                # Look ahead: only inject if not already present
                lookahead_window = "".join(lines[i + 1: i + 5])
                if cap_text[:50] not in lookahead_window:
                    out_lines.append("\n")
                    out_lines.append(cap_text + "\n\n")
                    injected += 1
        i += 1

    draft_path.write_text("".join(out_lines), encoding="utf-8")
    return {
        "draft_path": str(draft_path),
        "sections_processed": len(section_files),
        "capsules_found": len(capsules),
        "capsules_injected": injected,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        result = compile_capsules(args.workspace)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Compiled {result['capsules_injected']}/{result['capsules_found']} capsules into {result['draft_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
