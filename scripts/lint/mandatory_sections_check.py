"""scripts/lint/mandatory_sections_check.py — Per-project mandatory-H2 enforcement.

PROBLEM (Rule 6 violation found in 2026-05-27 portability audit)
─────────────────────────────────────────────────────────────────
`skills/seo-blog/SKILL.md` claims: "The Format-Fit quality gate runs the regex
matchers against the rendered HTML's <h2> text and fails closed (hard veto) if
any required section is missing." That gate was documented but NEVER existed as
code — there was no mandatory_sections checker anywhere in scripts/.

Consequence: each project declares its own `mandatory_sections` in
business-context.json (project-charlie wants 6: Abstract/Key Takeaways/TOC/FAQ/
Conclusion/References; another project might want 3 or 8). Nothing verified the
draft actually contained them. Enforcement relied entirely on the LLM remembering
— which is exactly the failure mode Rule 6 exists to prevent.

THIS FILE IS THE EXECUTOR. It is project-agnostic: it reads whatever
`mandatory_sections` the active project declares and verifies each one's
`h2_pattern` regex matches an actual H2 in the draft.

PROJECT-AGNOSTIC BY DESIGN
──────────────────────────
- Reads `projects/{slug}/business-context.json :: mandatory_sections.sections[]`
- Each section entry has `id` + `h2_pattern` (a regex matched against H2 text)
- If a project declares NO mandatory_sections, this check PASSES (the format
  template's own required sections apply instead — not this checker's concern)
- Works identically for project-charlie, project-juliet, or any future project

USAGE
──────
    python -m scripts.lint.mandatory_sections_check --workspace {task_id} --project-slug {slug} --json
    python -m scripts.lint.mandatory_sections_check --workspace {task_id} --project-slug {slug} --json --out {ws}/mandatory-sections-lint.json

    # project-slug optional — falls back to state.json :: project_slug
    python -m scripts.lint.mandatory_sections_check --workspace {task_id} --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from scripts._core import heading_anchor
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
_FORMAT_BASELINE = PLUGIN_ROOT / "references" / "seo" / "format-mandatory-sections.json"


def _extract_h2_texts(markdown: str) -> list[str]:
    """Return the text of every H2 heading in the markdown body.

    Handles both `## Heading` and `## Heading {#anchor}` (anchor stripped).
    Ignores fenced code blocks so `## ` inside a ``` block isn't counted.
    """
    h2s: list[str] = []
    in_fence = False
    for line in markdown.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # Match exactly H2 (##), not H1 (#) or H3 (###)
        m = re.match(r"^##\s+(.*)$", line)
        if m and not line.startswith("###"):
            text = m.group(1)
            # strip trailing Pandoc anchor {#id} if any survived
            text = heading_anchor.strip_heading_anchor(text)
            h2s.append(text)
    return h2s


def _load_format_baseline(format_id: str) -> list[dict[str, Any]] | None:
    """Return the skill-level sections list for *format_id*, or None if absent."""
    if not format_id or not _FORMAT_BASELINE.exists():
        return None
    try:
        data = json.loads(_FORMAT_BASELINE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠ mandatory_sections_check: bad {_FORMAT_BASELINE}: {e}", file=sys.stderr)
        return None
    secs = data.get(format_id)
    return secs if isinstance(secs, list) and secs else None


def _load_mandatory_sections(
    project_slug: str,
    format_id: str | None = None,
) -> list[dict[str, Any]] | None:
    """Return the mandatory sections list via 3-tier resolution.

    Tier 1 — project business-context.json::mandatory_sections.by_format[format_id]
    Tier 2 — references/seo/format-mandatory-sections.json[format_id]   (skill baseline)
    Tier 3 — project mandatory_sections.sections[]                       (legacy default)

    Returns None only when ALL tiers yield nothing (→ gate auto-passes).
    Backward-compatible: callers that omit format_id fall through to tier 3 exactly
    as before this change.
    """
    bc_ms: list[dict[str, Any]] | None = None
    if project_slug:
        bc_file = PLUGIN_ROOT / "projects" / project_slug / "business-context.json"
        if bc_file.exists():
            try:
                ms = json.loads(bc_file.read_text(encoding="utf-8")).get("mandatory_sections")
            except Exception as e:
                print(
                    f"⚠ mandatory_sections_check: could not parse {bc_file}: {e}",
                    file=sys.stderr,
                )
                ms = None
            if isinstance(ms, dict):
                # Tier 1: project per-format override
                if format_id and isinstance(ms.get("by_format"), dict):
                    ov = ms["by_format"].get(format_id)
                    if isinstance(ov, list) and ov:
                        return ov
                bc_ms = ms.get("sections") or None
            elif isinstance(ms, list):
                bc_ms = ms
    # Tier 2: skill-level format baseline
    fb = _load_format_baseline(format_id or "")
    if fb is not None:
        return fb
    # Tier 3: project legacy default
    return bc_ms


def check(
    workspace_dir: Path,
    project_slug: str,
    format_id: str | None = None,
) -> dict[str, Any]:
    draft = workspace_dir / "draft.md"
    if not draft.exists():
        return {
            "passed": False,
            "reason": f"draft.md not found in {workspace_dir}",
            "missing_sections": [],
            "project_slug": project_slug,
        }

    sections = _load_mandatory_sections(project_slug, format_id)
    if sections is None:
        # No mandatory_sections declared for this project → not this gate's job.
        return {
            "passed": True,
            "reason": f"project '{project_slug}' declares no mandatory_sections "
                      f"(format-template defaults apply instead)",
            "missing_sections": [],
            "checked_count": 0,
            "project_slug": project_slug,
        }

    md = draft.read_text(encoding="utf-8")
    h2_texts = _extract_h2_texts(md)

    missing: list[dict[str, Any]] = []
    matched: list[str] = []
    for sec in sections:
        sec_id = sec.get("id", "?")
        pattern = sec.get("h2_pattern")
        if not pattern:
            # No regex to match against — skip but note it
            continue
        try:
            # Case-insensitive: heading case (Title Case vs sentence case) is a
            # stylistic choice; the SEMANTIC role is what mandatory_sections enforces.
            # "Key Takeaways" and "Key takeaways" fill the same role.
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            missing.append({
                "id": sec_id,
                "h2_pattern": pattern,
                "error": f"invalid regex: {e}",
            })
            continue
        if any(rx.search(h) for h in h2_texts):
            matched.append(sec_id)
        else:
            missing.append({
                "id": sec_id,
                "h2_pattern": pattern,
                "hint": f"No H2 in the draft matches /{pattern}/. "
                        f"Found H2s: {h2_texts}",
            })

    passed = len(missing) == 0
    return {
        "passed": passed,
        "reason": (
            f"all {len(matched)} mandatory sections present"
            if passed
            else f"{len(missing)} mandatory section(s) missing: "
                 f"{[m['id'] for m in missing]}"
        ),
        "project_slug": project_slug,
        "checked_count": len(sections),
        "matched": matched,
        "missing_sections": missing,
        "h2_texts_found": h2_texts,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-project mandatory-H2 section enforcement")
    ap.add_argument("--workspace", required=True, help="task_id OR full workspace path")
    ap.add_argument("--project-slug", default="", help="project slug (falls back to state.json)")
    ap.add_argument("--out", help="write result JSON to this path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    # Resolve workspace dir (accept either a task_id or a full path)
    ws_arg = Path(args.workspace)
    if ws_arg.is_dir():
        ws = ws_arg
    else:
        ws = PLUGIN_ROOT / "memory" / "workspace" / args.workspace

    project_slug = args.project_slug
    if not project_slug:
        state = ws / "state.json"
        if state.exists():
            try:
                project_slug = json.loads(state.read_text(encoding="utf-8")).get("project_slug", "")
            except Exception:
                pass

    format_id: str | None = None
    angle = ws / "angle.json"
    if angle.exists():
        try:
            format_id = json.loads(angle.read_text(encoding="utf-8")).get("format_id")
        except Exception:
            pass

    result = check(ws, project_slug, format_id)

    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['reason']}")
        for m in result.get("missing_sections", []):
            print(f"  MISSING: {m['id']} (pattern: {m.get('h2_pattern')})")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
