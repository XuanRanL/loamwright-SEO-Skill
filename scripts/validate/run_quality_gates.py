#!/usr/bin/env python3
"""Wrapper that runs all 3 quality gate scorers and writes a combined quality.json.

Solves the CLI-mismatch bug: the orchestrator sends --workspace but the
individual scorers accept positional file paths. This wrapper resolves
workspace paths, runs all 3 scorers, and writes a single quality.json
to the workspace file-bus.

Usage:
    python -m scripts.validate.run_quality_gates --workspace {task_id} [--json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
WS_ROOT = PLUGIN_ROOT / "memory" / "workspace"


def _ws(task_id: str) -> Path:
    return WS_ROOT / task_id


def _run_scorer(cmd: list[str], name: str, extract_fn) -> dict:
    """Run a scorer subprocess. Parse stdout as JSON regardless of exit code.

    Scorers return exit 1 for FIX/FAIL verdicts (not errors). Only treat
    as ERROR if stdout is empty or not valid JSON.
    """
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(PLUGIN_ROOT)
        )
        if proc.stdout.strip():
            data = json.loads(proc.stdout)
            return extract_fn(data)
        else:
            return {"score": 0, "verdict": "ERROR", "error": f"{name} produced no stdout. stderr: {proc.stderr[:300]}"}
    except json.JSONDecodeError as e:
        return {"score": 0, "verdict": "ERROR", "error": f"{name} stdout not valid JSON: {e}"}
    except Exception as e:
        return {"score": 0, "verdict": "ERROR", "error": str(e)[:300]}


def main() -> int:
    ap = argparse.ArgumentParser(description="Combined quality gates runner")
    ap.add_argument("--workspace", required=True, help="Task ID")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ws = _ws(args.workspace)
    if not ws.exists():
        print(f"Workspace {args.workspace} not found", file=sys.stderr)
        return 2

    draft_path = ws / "draft.md"
    citations_path = ws / "citations.json"
    schema_path = ws / "schema.json"

    if not draft_path.exists():
        print(f"draft.md not found in {ws}", file=sys.stderr)
        return 2

    meta_path = ws / "meta.json"

    # Resolve project_slug so the CITE scorer can credit head-emitted schema types.
    project_slug = ""
    state_path = ws / "state.json"
    state_brief: dict = {}
    if state_path.exists():
        try:
            _state = json.loads(state_path.read_text(encoding="utf-8"))
            project_slug = _state.get("project_slug", "") or ""
            state_brief = _state.get("brief") or {}
        except Exception:
            project_slug = ""
            state_brief = {}

    # Resolve the primary keyword and write a sidecar brief for core_eeat_scorer.
    # WITHOUT this, core_eeat R01/R06 FAIL "no keyword provided" -> a fixed -2.5pt
    # on every article (same class as the O01/O02 -2.5pt bug). state.json already
    # carries brief.primary_keyword; meta.json's focus_keyphrase is the fallback.
    # (2026-07-17 seam fix — the v3.40.0 audit fixed core_eeat's own CLI but not
    # this run_quality_gates -> core_eeat_scorer seam. Rule 10.)
    brief_path = None
    primary_kw = (state_brief.get("primary_keyword") or "").strip()
    if not primary_kw and meta_path.exists():
        try:
            primary_kw = (json.loads(meta_path.read_text(encoding="utf-8"))
                          .get("focus_keyphrase") or "").strip()
        except Exception:
            primary_kw = ""
    if primary_kw:
        # Reuse the full state brief when it carries the keyword (word_target etc.),
        # else synthesize the minimal shape core_eeat_scorer expects.
        gate_brief = dict(state_brief) if state_brief.get("primary_keyword") else {}
        gate_brief["primary_keyword"] = primary_kw
        brief_path = ws / "_gate_brief.json"
        brief_path.write_text(json.dumps(gate_brief), encoding="utf-8")

    results: dict = {}

    # --- CORE-EEAT scorer ---
    cmd = [sys.executable, "-m", "scripts.validate.core_eeat_scorer",
           str(draft_path), "--json"]
    if brief_path is not None:
        cmd.extend(["--brief", str(brief_path)])
    if citations_path.exists():
        cmd.extend(["--citations", str(citations_path)])
    if schema_path.exists():
        cmd.extend(["--schema", str(schema_path)])
    # C09/C10 locate the Conclusion/FAQ sections via the PROJECT's mandatory_sections
    # h2_pattern. Without this, C10's legacy `^##\s+faq` regex never matched the plugin's
    # own default heading ("Frequently Asked Questions") and C09 failed on every project
    # that mandates a gentle conclusion label ("The Last Sip") — both unearnable, because
    # renaming the heading to satisfy the scorer trips the Format-Fit hard veto. (2026-07-14)
    if project_slug:
        cmd.extend(["--project-slug", project_slug])
    results["core_eeat"] = _run_scorer(cmd, "core_eeat_scorer", lambda d: {
        "score": d.get("final_overall_score", d.get("raw_overall_score", 0)),
        "verdict": d.get("verdict", "UNKNOWN"),
        "vetoes": d.get("vetoes_triggered", []),
    })

    # --- CITE scorer ---
    cmd = [sys.executable, "-m", "scripts.validate.cite_scorer",
           str(draft_path), "--json"]
    # --meta revives the T05 YMYL veto (cite_scorer gates it on meta.is_ymyl);
    # without it that hard veto is dead at this layer. (2026-07-17 seam fix.)
    if meta_path.exists():
        cmd.extend(["--meta", str(meta_path)])
    if citations_path.exists():
        cmd.extend(["--citations", str(citations_path)])
    if schema_path.exists():
        cmd.extend(["--schema", str(schema_path)])
    if project_slug:
        cmd.extend(["--project-slug", project_slug])
    results["cite"] = _run_scorer(cmd, "cite_scorer", lambda d: {
        "score": d.get("final_overall_score", d.get("raw_overall_score", 0)),
        "verdict": d.get("verdict", "UNKNOWN"),
        "vetoes": d.get("vetoes_triggered", []),
    })

    # --- AI-Slop scorer ---
    cmd = [sys.executable, "-m", "scripts.validate.ai_slop_score",
           str(draft_path), "--json"]
    results["ai_slop"] = _run_scorer(cmd, "ai_slop_score", lambda d: {
        "score": d.get("score", 100),
        "passes": d.get("passes", False),
        "band": d.get("band", "UNKNOWN"),
    })

    # --- Combined verdict ---
    eeat_ok = results.get("core_eeat", {}).get("verdict") in ("SHIP", "FIX")
    eeat_no_vetoes = len(results.get("core_eeat", {}).get("vetoes", [])) == 0
    cite_ok = results.get("cite", {}).get("verdict") in ("SHIP", "FIX")
    cite_no_hard_vetoes = not any(
        v in results.get("cite", {}).get("vetoes", [])
        for v in ["T03", "T05", "T09", "COMP01"]
    )
    slop_ok = results.get("ai_slop", {}).get("passes", False)

    if eeat_ok and eeat_no_vetoes and cite_ok and cite_no_hard_vetoes:
        combined_verdict = "SHIP" if slop_ok else "SHIP_WITH_NOTES"
    elif not eeat_ok or not cite_ok:
        combined_verdict = "FIX_REQUIRED"
    else:
        combined_verdict = "BLOCKED"

    all_pass = eeat_ok and cite_ok and slop_ok and eeat_no_vetoes and cite_no_hard_vetoes
    output = {
        **results,
        "combined_verdict": combined_verdict,
        "all_pass": all_pass,
        # v3.38.3: top-level gate flag so run_pipeline._GATE_STAGES /
        # orchestrator._PASS_FLAG_REQUIRED can gate this stage like every other
        # deterministic lint. Root cure for the 2026-07-09 gold-filament hole:
        # post-humanizer stages (linker/geo/visual/cta) regressed ai_slop to
        # 24.25; quality.json carried the FRESH failing measurement but nothing
        # read it as a gate — the runner sailed to the reviewer and pre-publish
        # adjudicated ai_slop from the STALE humanizer-report (16.13). Now a
        # failing fresh measurement stops the pipeline at this stage (route:
        # re-dispatch the humanizer, then re-run).
        "passed": all_pass,
    }

    out_path = ws / "quality.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"  CORE-EEAT: {results['core_eeat'].get('score', '?')}/100 — {results['core_eeat'].get('verdict', '?')}")
        print(f"  CITE:      {results['cite'].get('score', '?')}/100 — {results['cite'].get('verdict', '?')}")
        print(f"  AI-Slop:   {results['ai_slop'].get('score', '?')}/100 — {'PASS' if results['ai_slop'].get('passes') else 'FAIL'}")
        print(f"  Combined:  {combined_verdict}")
        print(f"  Written:   {out_path}")

    return 0 if combined_verdict != "BLOCKED" else 1


if __name__ == "__main__":
    sys.exit(main())
