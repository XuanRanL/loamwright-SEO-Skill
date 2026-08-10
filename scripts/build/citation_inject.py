#!/usr/bin/env python3
"""scripts/build/citation_inject.py — Replace [claim:cN] markers with (Author, Year).

Reads draft.md + citations.json, applies in_text_replacements, writes back.
Separate from assemble.py so the orchestrator can track it as an independent stage
with its own completion artifact (citation-inject-result.json).

Accepts BOTH key shapes:
  - {"from": "[claim:c1_abstract]", "to": "(Chandra et al., 2008)"}
  - {"marker": "[claim:c1_abstract]", "replace_with": "(Chandra et al., 2008)"}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts._core import file_bus
# Reuse the publisher's canonical 2-source parser so inject and publish produce
# IDENTICAL inline citations from one source of truth (avoids the case-sensitivity
# / format drift that bit us before). It derives (Author, Year) from BOTH explicit
# in_text_replacements[] AND citations[].claim_markers_resolved[]+apa_7.
from scripts.wordpress.wp_publisher import _build_in_text_replacement_map

_CLAIM_RE = re.compile(r"\[claim:[^\]]+\]", re.IGNORECASE)
# Bare marker IDs inside a [claim:...] bracket, e.g. c1_abstract, c5_s4_1, c1_S2.
_CLAIM_ID_RE = re.compile(r"c\d+_[a-z0-9_]+", re.IGNORECASE)


def inject(task_id: str) -> dict:
    ws = file_bus.get_workspace(task_id)
    draft_path = ws / "draft.md"

    if not draft_path.exists():
        return {"success": False, "error": "draft.md not found"}

    try:
        citations = file_bus.read_artifact(task_id, "citations.json")
    except FileNotFoundError:
        return {"success": False, "error": "citations.json not found"}

    text = draft_path.read_text(encoding="utf-8")
    markers_before = len(_CLAIM_RE.findall(text))

    # ── 2-source replacement map (the FIX) ────────────────────────────────
    # Build {bare_id: "(Author, Year)"} from explicit in_text_replacements[]
    # AND, when those are absent, derive from citations[].claim_markers_resolved[]
    # + apa_7. This is why the old single-source path silently deleted citations:
    # a fact-checker that populated claim_markers_resolved but left
    # in_text_replacements empty produced an empty map, and every marker fell
    # into a strip-with-no-replacement branch. We never strip anymore.
    marker_map = _build_in_text_replacement_map(citations)

    applied = 0
    left_unresolved: list[str] = []

    def _swap(match: "re.Match[str]") -> str:
        nonlocal applied
        bracket = match.group(0)
        ids = [s.lower() for s in _CLAIM_ID_RE.findall(bracket)]
        if not ids:
            left_unresolved.append(bracket)
            return bracket  # malformed marker → leave it for render_lint L5
        resolved, missing = [], []
        for mid in ids:
            (resolved if mid in marker_map else missing).append(mid)
        # SAFETY: if ANY id in the bracket can't be resolved, leave the WHOLE
        # marker in place. A left-in marker is a LOUD, recoverable gate failure
        # (render_lint L5 hard-vetoes it); a silently deleted marker is invisible
        # data loss. Never trade a visible failure for a corrupt artifact.
        if missing or not resolved:
            left_unresolved.extend(missing or ids)
            return bracket
        # Dedupe while preserving order (a bracket may map several ids to the
        # same citation, e.g. two claims from one source).
        seen, deduped = set(), []
        for r in resolved:
            cite = marker_map[r]
            if cite not in seen:
                seen.add(cite)
                deduped.append(cite)
        applied += 1
        if len(deduped) == 1:
            return deduped[0]
        # Multiple distinct citations on one claim → merge into one parenthesis.
        return "(" + "; ".join(c.strip("()") for c in deduped) + ")"

    text = _CLAIM_RE.sub(_swap, text)
    # Two ADJACENT markers resolving to the same source each emit their own
    # parenthetical — collapse identical neighbours (2026-07-01, draft-788
    # "(Reboot Online, 2025)(Reboot Online, 2025)" bug).
    from scripts._core.citation_text import collapse_adjacent_duplicate_citations
    text = collapse_adjacent_duplicate_citations(text)
    # Tidy whitespace artifacts from empty-string (deliberate-strip) replacements:
    # "word [claim:x]." -> "word." not "word ." (2026-06-29 fix; empty `to` means
    # the fact-checker marked the claim author-experience and wants it removed).
    text = re.sub(r"[ \t]+([.,;:)])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    markers_after = len(_CLAIM_RE.findall(text))

    draft_path.write_text(text, encoding="utf-8")

    result = {
        "success": True,
        "task_id": task_id,
        "markers_before": markers_before,
        "markers_after": markers_after,
        "replacements_applied": applied,
        "marker_map_size": len(marker_map),
        # Markers we deliberately LEFT in place (no derivable citation). These
        # are caught by render_lint L5 as a hard veto → repair, NOT silent loss.
        "markers_left_unresolved": sorted(set(left_unresolved)),
    }

    result_path = ws / "citation-inject-result.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Inject (Author, Year) citations into draft.md")
    ap.add_argument("task_id")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = inject(args.task_id)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["success"]:
            unresolved = result.get("markers_left_unresolved", [])
            print(f"  citation-inject: {result['replacements_applied']} applied, "
                  f"{result['markers_before']}→{result['markers_after']} markers"
                  + (f", {len(unresolved)} LEFT UNRESOLVED (render_lint L5 will veto): {unresolved}"
                     if unresolved else ""))
        else:
            print(f"  ERROR: {result['error']}", file=sys.stderr)

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
