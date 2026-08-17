#!/usr/bin/env python3
"""scripts/pipeline/run_pipeline.py — deterministic pipeline DRIVER.

WHY THIS EXISTS (root cure, 2026-06-03)
=======================================
The orchestrator (orchestrator.py) is a PASSIVE state machine: it answers "what's next?"
and "did that verify?", but it never drives. Until now the LLM had to hand-drive all ~29
stages for every article — calling `--action next`, dispatching/running each stage, then
`--action verify` — between every single stage. Under long batch runs that manual ritual is
where steps got skipped or driven out of order (the 2026-05-26 "23/35 skipped", the 2026-06-02
"geo skipped", and the 2026-06-03 "3 stage records missed + lots of by-hand driving" incidents).
Enforcement made bad outcomes *detectable* at the gates, but execution was still only as
reliable as operator discipline.

This driver makes execution deterministic. It runs the loop in CODE:
  • BASH / BACKGROUND / CHECK stages → it runs/launches/checks them itself and records them.
  • LLM stages → a Python script cannot dispatch a Claude subagent, so the driver STOPS and
    hands back a precise, machine-readable dispatch spec (subagent_type + prompt + expected
    outputs). The caller dispatches that ONE subagent, makes sure the artifact landed, then
    re-invokes the driver with `--completed-llm <stage>`. The driver verifies it and auto-runs
    every following BASH stage until the next LLM stage or PIPELINE_COMPLETE.

Net effect: the LLM's surface area drops from "orchestrate 29 stages × N articles" to "service
the handful of LLM stages I'm explicitly handed." No skipped `next`/`verify` calls, no driving
from memory, no missed stage_history records — the driver does all the bookkeeping and ordering.

PROTOCOL FOR THE CALLER (the seo-blog skill)
============================================
  1. python -m scripts.pipeline.run_pipeline --workspace <tid> --json
  2. Read the JSON `action`:
       - "DISPATCH_LLM" → dispatch Agent(subagent_type=<subagent_type>, prompt=<dispatch_prompt>);
                          ensure every path in <expected_outputs> exists; then re-invoke with
                          `--completed-llm <stage>`.
       - "COMPLETE"     → pipeline done; proceed to the publish confirmation step.
       - "BLOCKED"      → a stage is missing inputs; fix them, then re-invoke.
       - "GATE_FAILED"  → a lint/gate found defects (details in `gate`); route to repair, then
                          re-invoke (the driver re-runs the failed stage).
       - "ERROR"        → a BASH stage crashed; inspect `detail`, fix, re-invoke.
       - "LOCKED"       → another driver is already active on this workspace (exit 30).
                          Wait for it to return, then re-invoke. NEVER delete the lock
                          sidecar or retry in a tight loop (2026-07-07 double-publish race).
  3. Repeat until "COMPLETE".

Usage:
    python -m scripts.pipeline.run_pipeline --workspace <tid> [--completed-llm <stage>] [--json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from scripts._core import file_bus, file_lock
from scripts.pipeline import orchestrator as orch

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

# How long a second driver waits for the workspace lock before reporting LOCKED.
# Short on purpose: the race we are killing is a second driver arriving while a
# minutes-long BASH stage (publish) is mid-flight — it should back off fast, not
# queue up and re-drive stages the first driver already ran.
_DRIVER_LOCK_TIMEOUT_S = 2.0

# Stages whose output JSON carries a top-level "passed" flag; if false, the work needs repair
# even though the artifact exists. We stop on these so a defect is fixed BEFORE we sail past it.
_GATE_STAGES = {
    "section-completeness-check": "section-completeness.json",
    "render-lint": "render-lint.json",
    "image-placeholder-check": "image-placeholder-lint.json",
    "visual-density-check": "visual-density.json",
    # Stat-grid contract (v3.39.0): mirrors orchestrator._PASS_FLAG_REQUIRED so a
    # broken stat value surfaces as GATE_FAILED (route back to visual-designer),
    # not a generic verify ERROR. Rule 11: change both layers together.
    "stat-grid-check": "stat-grid-lint.json",
    "local-uniqueness-check": "local-uniqueness-lint.json",
    # CTA brief resolution (2026-08-12 audit): the v3.42.4 resolution_failed
    # sentinel exits 1, but this driver swallowed any non-gate stage's exit code
    # — the pipeline reported COMPLETE with "exit": 1 buried in steps.
    # cta-brief.json carries no `passed` flag (see the cta-brief.json note in
    # orchestrator._PASS_FLAG_REQUIRED), so this entry's work is done by the
    # returncode branch below plus the cta-brief-builder content gate in
    # orchestrator._content_gate_reason — Rule 11: the two layers state the same
    # contract and must be changed together. The legitimate skipped_no_config
    # sentinel exits 0 and stays a quiet pass.
    "cta-brief-builder": "cta-brief.json",
    "cta-injection": "cta-injection-result.json",
    # CTA Gate 5 (v3.37): mirrors orchestrator._PASS_FLAG_REQUIRED so a repetitive
    # CTA draft surfaces as GATE_FAILED (route to re-dispatch cta-writer), not a
    # generic verify ERROR. Rule 11: this driver map and _PASS_FLAG_REQUIRED are
    # two layers stating the same gate contract and must be changed together.
    "cta-diversity-check": "cta-diversity.json",
    # CTA Gate 2 (v3.38.0): same contract as cta-diversity-check above — mirrors
    # orchestrator._PASS_FLAG_REQUIRED so a hype/pressure-laden CTA draft
    # surfaces as GATE_FAILED (route to re-dispatch cta-writer), not a generic
    # verify ERROR. Rule 11: this driver map and _PASS_FLAG_REQUIRED are two
    # layers stating the same gate contract and must be changed together.
    "cta-tone-check": "cta-tone.json",
    "paa-alignment-check": "paa-alignment-lint.json",
    "locale-spelling-check": "locale-spelling-lint.json",
    "brand-fact-check": "brand-fact-lint.json",
    # 2026-07-17 audit — Rule-12 completions; mirrors of
    # orchestrator._PASS_FLAG_REQUIRED (Rule 11: change together).
    "citation-capsule-builder": "citation-capsule-result.json",
    "finalize-references-signature": "finalize-result.json",
    # v3.38.3 — two gates that previously wrote a verdict nothing read (Rule 12):
    # keyword-density: passed=false ONLY above the documented 1.5% hard-stuffing
    # ceiling (under-band stays informational — the 2026-07-09 batch logged
    # scary-but-meaningless exit:1 on every "too_low" article while the actual
    # hard veto had NO enforcement layer at all).
    "keyword-density-check": "keyword-density.json",
    # quality-gates: quality.json now carries passed=all_pass. The FRESH ai_slop
    # measurement (this stage re-runs after every draft edit via
    # _FRESHNESS_VS_DRAFT) finally blocks here, instead of pre-publish reading
    # the stale humanizer-report (the 2026-07-09 gold-filament 24.25 hole).
    # Rule 11: mirror of orchestrator._PASS_FLAG_REQUIRED — change together.
    "quality-gates": "quality.json",
    "pre-publish-gate": "pre-publish-gate-result.json",
}


def _ws(task_id: str) -> Path:
    return PLUGIN_ROOT / "memory" / "workspace" / task_id


def _run_bash(command: str) -> subprocess.CompletedProcess:
    """Run a resolved BASH stage command from the plugin root.

    The stage commands are authored as shell strings (`python -m module ... --flag "value"`),
    the exact form the LLM would otherwise run via the Bash tool, so we execute them through the
    shell for parity. task_id/project_slug are schema-validated and the only free field
    (primary_keyword) is double-quoted in the template."""
    return subprocess.run(command, shell=True, cwd=str(PLUGIN_ROOT),
                          capture_output=True, text=True)


def _launch_background(command: str) -> None:
    """Launch a BACKGROUND stage detached so it survives this driver process exiting."""
    kwargs: dict = {"cwd": str(PLUGIN_ROOT), "shell": True,
                    "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)


def _gate_passed(ws: Path, stage_name: str) -> tuple[bool, str]:
    """For a gate stage, return (passed, reason) from its result artifact's `passed` flag."""
    fname = _GATE_STAGES.get(stage_name)
    if not fname:
        return True, ""
    p = ws / fname
    if not p.exists():
        return False, f"{fname} not produced"
    try:
        data = file_bus.tolerant_json_load(p)
    except Exception as e:
        return False, f"{fname} unreadable: {e}"
    if isinstance(data, dict) and data.get("passed") is False:
        defects = data.get("defects") or data.get("missing_indices") or data.get("results") or []
        return False, f"{stage_name} found defect(s): {str(defects)[:300]}"
    return True, ""


def advance(task_id: str, completed_llm: str | None = None, max_bash: int = 60) -> dict:
    """Drive the pipeline forward until an LLM stage, completion, or a stop condition."""
    ws = _ws(task_id)
    if not ws.exists():
        return {"action": "ERROR", "detail": f"workspace {task_id} not found"}

    steps: list[dict] = []

    # If the caller just finished an LLM stage, verify (record) it before advancing.
    if completed_llm:
        v = orch.verify_stage(task_id, completed_llm)
        healed = False
        if not v.get("passed") and completed_llm == "research":
            # Self-heal (v3.36.0, root cure for the 2026-07-06 loamdmanearme incident):
            # researcher subagents write research.json via scripts (bypassing the
            # Write-hook schema validation) and occasionally improvise a variant shape
            # (intent-as-dict, competitor_content instead of competitor_titles, raw
            # SerpApi feature keys). The v3.35.3 floor correctly REJECTS that here —
            # but the only cure used to be manual JSON surgery. Run the deterministic
            # normalizer ONCE, then re-verify. Every applied mapping is recorded in
            # research.json::_normalizations[] so the heal is auditable, and a shape
            # the normalizer can't fix still returns the same hard ERROR as before.
            fix = _run_bash(
                f"python -m scripts.validate.research_contract --workspace {task_id} --fix --json"
            )
            if fix.returncode == 0:
                v = orch.verify_stage(task_id, completed_llm)
                healed = v.get("passed", False)
        if not v.get("passed"):
            return {"action": "ERROR", "stage": completed_llm,
                    "detail": f"LLM stage '{completed_llm}' did not produce valid outputs: "
                              f"{v.get('outputs_missing') or v.get('reason')}",
                    "verify": v}
        if healed:
            # Surfaced (not silent): the caller sees the heal in the response and
            # research.json carries _normalized_by/_normalizations for the audit trail.
            steps.append({"stage": "research", "executor": "SELF-HEAL",
                          "detail": "research_contract --fix normalized a variant "
                                    "research.json shape to the canonical contract"})

    bash_count = 0
    while True:
        r = orch.next_stage(task_id)
        status = r.get("status")

        if status == "PIPELINE_COMPLETE":
            return {"action": "COMPLETE", "steps_run": steps,
                    "progress": r.get("pipeline_progress")}
        if status == "BLOCKED":
            return {"action": "BLOCKED", "stage": r.get("stage"),
                    "reason": r.get("reason"), "missing_inputs": r.get("missing_inputs"),
                    "steps_run": steps}

        if status == "ERROR" or r.get("action") == "ERROR" or "executor" not in r:
            # v3.41.3: next_stage() can return an ERROR shape (workspace not
            # found; fresh-task brief schema gate). This driver previously fell
            # through to r["executor"] and died with a bare KeyError — the
            # latent crash existed for ANY next_stage error, my gate merely
            # exposed it.
            return {"action": "ERROR", "stage": r.get("stage"),
                    "detail": r.get("reason") or r.get("detail")
                    or f"next_stage returned unexpected shape: {sorted(r)}",
                    "steps_run": steps}

        stage = r["stage"]
        executor = r["executor"]  # BASH | BACKGROUND | CHECK | LLM

        if executor == "LLM":
            # Hand control back to the caller to dispatch exactly one subagent.
            return {
                "action": "DISPATCH_LLM",
                "stage": stage,
                "phase": r.get("phase"),
                "subagent_type": r.get("subagent_type", ""),
                "subagent_enforced": r.get("subagent_enforced", False),
                "dispatch_prompt": r.get("dispatch_prompt", ""),
                "description": r.get("description", ""),
                "expected_outputs": r.get("expected_outputs", []),
                "is_mandatory": r.get("is_mandatory", True),
                "steps_run": steps,
                "progress": r.get("pipeline_progress"),
                "next_call": f"--completed-llm {stage}",
            }

        if executor == "BACKGROUND":
            cmd = r.get("command")
            if not cmd:
                return {"action": "ERROR", "stage": stage, "detail": "no command resolved"}
            _launch_background(cmd)
            v = orch.verify_stage(task_id, stage)  # records the launch
            steps.append({"stage": stage, "executor": "BACKGROUND", "launched": True})
            continue

        if executor == "CHECK":
            v = orch.verify_stage(task_id, stage)
            if not v.get("passed"):
                # e.g. image-pipeline-join: Fork B not finished yet. Caller should wait + retry.
                return {"action": "WAIT", "stage": stage,
                        "reason": v.get("reason") or v.get("outputs_missing"),
                        "detail": "Expected artifact not ready yet (e.g. background image gen still running). "
                                  "Wait briefly, then re-invoke run_pipeline.",
                        "steps_run": steps}
            steps.append({"stage": stage, "executor": "CHECK", "passed": True})
            continue

        # executor == BASH
        bash_count += 1
        if bash_count > max_bash:
            return {"action": "ERROR", "stage": stage,
                    "detail": f"exceeded max_bash={max_bash} (possible loop)", "steps_run": steps}
        cmd = r.get("command")
        if not cmd:
            return {"action": "ERROR", "stage": stage, "detail": "no command resolved"}
        proc = _run_bash(cmd)

        # A gate stage may exit non-zero (e.g. pre_publish_gate) or write passed:false.
        gate_ok, gate_reason = _gate_passed(ws, stage)
        if proc.returncode != 0 and stage in _GATE_STAGES:
            gate_ok = gate_ok and False
            if not gate_reason:
                gate_reason = (proc.stdout or proc.stderr or "").strip()[-400:]
        if not gate_ok:
            return {"action": "GATE_FAILED", "stage": stage, "gate": gate_reason,
                    "stdout_tail": (proc.stdout or "")[-600:],
                    "detail": "A quality/lint gate found defects. Route to repair (fix the draft "
                              "or re-dispatch the responsible subagent), then re-invoke run_pipeline.",
                    "steps_run": steps}

        v = orch.verify_stage(task_id, stage)
        if not v.get("passed"):
            return {"action": "ERROR", "stage": stage,
                    "detail": f"BASH stage '{stage}' ran but verify failed: "
                              f"{v.get('outputs_missing') or v.get('reason')}",
                    "exit_code": proc.returncode,
                    "stdout_tail": (proc.stdout or "")[-600:],
                    "stderr_tail": (proc.stderr or "")[-400:],
                    "steps_run": steps}
        steps.append({"stage": stage, "executor": "BASH", "exit": proc.returncode})
        continue


def drive(task_id: str, completed_llm: str | None = None, max_bash: int = 60) -> dict:
    """advance() under an exclusive per-workspace driver lock.

    ROOT CURE (2026-07-07 double-publish race): two run_pipeline invocations on the
    SAME workspace could overlap — the second bare invocation, arriving while the
    first was mid-way through a minutes-long BASH stage (wordpress-publisher),
    re-dispatched the same READY stage. In the 2026-07-07 batch this executed the
    publisher TWICE concurrently on 2 of 3 articles (double change-log entries for
    posts 1488/1500) and verify-post snapshotted the post BEFORE the second run's
    final PATCH. Idempotent draft PATCHes contained the damage, but the same race
    on a non-idempotent stage would not be benign. Rule 7's locks cover shared
    ~/.xuanran-seo files only — workspace state.json had no execution lock.

    The lock sidecar lives at {workspace}/.pipeline-driver.lock; the OS releases
    it automatically if the driver dies (no stale-lock deadlock). A second caller
    gets action="LOCKED" (exit 30): wait for the running driver to finish, then
    re-invoke — do NOT retry in a tight loop and do NOT delete the lock file.
    """
    ws = _ws(task_id)
    if not ws.exists():
        # Let advance() produce its canonical missing-workspace error; taking the
        # lock first would create a junk workspace dir for a typo'd task id.
        return advance(task_id, completed_llm=completed_llm, max_bash=max_bash)
    try:
        with file_lock.locked(ws / ".pipeline-driver", timeout=_DRIVER_LOCK_TIMEOUT_S):
            return advance(task_id, completed_llm=completed_llm, max_bash=max_bash)
    except file_lock.LockTimeout:
        return {
            "action": "LOCKED",
            "stage": None,
            "detail": (
                f"Another run_pipeline driver is already active on workspace "
                f"'{task_id}' (lock: {ws / '.pipeline-driver.lock'}). Double-driving "
                f"re-dispatches in-flight stages (2026-07-07 double-publish race). "
                f"Wait for the running driver to return, then re-invoke."
            ),
        }


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic pipeline driver")
    ap.add_argument("--workspace", required=True, help="Task ID")
    ap.add_argument("--completed-llm", default=None,
                    help="Name of the LLM stage the caller just finished (verify + advance).")
    ap.add_argument("--max-bash", type=int, default=60)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = drive(args.workspace, completed_llm=args.completed_llm, max_bash=args.max_bash)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        action = result.get("action")
        print(f"  ACTION: {action}")
        if action == "DISPATCH_LLM":
            print(f"  → dispatch subagent '{result.get('subagent_type') or '(inline)'}' for stage '{result['stage']}'")
            print(f"    expected outputs: {result.get('expected_outputs')}")
            print(f"    then re-invoke: run_pipeline --workspace {args.workspace} {result.get('next_call')}")
        elif action == "COMPLETE":
            print("  Pipeline COMPLETE.")
        elif action in ("BLOCKED", "GATE_FAILED", "ERROR", "WAIT", "LOCKED"):
            print(f"  stage: {result.get('stage')} | {result.get('reason') or result.get('gate') or result.get('detail')}")

    # Exit codes: 0 = complete, 10 = needs LLM dispatch, 20 = wait,
    # 30 = another driver holds the workspace lock, 1 = blocked/gate/error
    action = result.get("action")
    if action == "COMPLETE":
        return 0
    if action == "DISPATCH_LLM":
        return 10
    if action == "WAIT":
        return 20
    if action == "LOCKED":
        return 30
    return 1


if __name__ == "__main__":
    sys.exit(main())
