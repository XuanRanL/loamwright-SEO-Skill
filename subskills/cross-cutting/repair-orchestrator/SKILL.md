---
name: repair-orchestrator
description: 5-level repair escalation when quality gates fail. Surgical → Section-rewrite → Stage-rewrite → Full-regen → From-scratch. Hard cap 4 rounds total. Use when quality.json reports overall_passed=false OR reviewer rejects. Last line of defense before declaring an article unsalvageable.
allowed-tools: [Read, Write, Edit, Bash, Task]
---

# Repair Orchestrator

The escalating repair pipeline. Driven by quality.json findings.

## Inputs

- `workspace/{task_id}/quality.json` (one or more gates failed)
- `workspace/{task_id}/review.json` (if independent-reviewer ran)
- `state.repair_iteration` (current attempt count; cap = 4)

## 5 escalation levels

```
Level 1 — SURGICAL (cheapest, fastest)
  Edit specific lines indicated by quality.json.repairs[].instruction
  Use Edit tool only (preserve everything else)
  If quality improves ≥3 score → progress; loop back at Level 1 again
  If improvement <3 → escalate to Level 2

Level 2 — SECTION-REWRITE
  Identify which section(s) most contribute to failures
  Spawn writer agent for that section with:
    - original section spec
    - failures list as "things to fix"
    - stronger constraints
  Re-run quality gates
  If still failing → escalate to Level 3

Level 3 — STAGE-REWRITE
  Rerun one whole stage of build phase:
    - If structural issues: outline-architect (revise outline)
    - If reference issues: fact-check-and-citation (verify everything again)
    - If voice issues: humanizer (with stricter settings)
  Re-run quality gates
  If still failing → escalate to Level 4

Level 4 — FULL-REGEN
  Rerun all of Phase Build (preserve research.json + angle.json + outline.json)
  Re-run quality gates
  If still failing → escalate to Level 5

Level 5 — FROM-SCRATCH
  Rerun from Plan phase:
    - Pick alternative title from angle.alternative_titles_considered
    - New outline from scratch
    - New writer agents
  Re-run quality gates
  If still failing → HALT, return best-of-N to user
```

**Hard cap: 4 total rounds** across all levels. After round 4, return whatever artifact had highest quality.json score with a documented "could not converge" message.

## Decision tree

Read `quality.json.repairs[]` and `quality.gates`:

```python
def pick_level(quality, prior_iterations, prior_level):
    # First iteration after gate fail
    if prior_iterations == 0:
        return 1  # Always start surgical
    
    # Surgical didn't improve enough
    if prior_level == 1:
        # Was improvement small?
        delta = current_score - prior_score
        if delta < 3:
            return 2  # Escalate
        return 1  # Continue surgical
    
    # Section rewrite didn't help
    if prior_level == 2:
        # How many sections needed rewrite?
        problem_sections = [s for s in sections if has_issues(s)]
        if len(problem_sections) > 3:
            return 3  # Stage-level fix
        return 2  # Try again
    
    # Stage rewrite didn't help → full regen
    if prior_level == 3:
        return 4
    
    # Full regen didn't help → from scratch
    if prior_level == 4:
        return 5
```

## What each level fixes

### Level 1: Surgical — best for
- Banned word hits
- Em-dash hits
- Citation marker → APA replacement
- Minor wording polish

### Level 2: Section-rewrite — best for
- One H2 missing Citation Capsule
- One section badly off voice
- Word count outside band in 1-2 sections
- Format doesn't match for 1-2 sections

### Level 3: Stage-rewrite — best for
- Structural: H2 hierarchy wrong → outline-architect
- Multiple unverified citations → fact-check-and-citation
- Voice inconsistent across most sections → humanizer (rewrite mode)

### Level 4: Full-regen — best for
- AI-Slop score consistently high
- Many sections fail quality
- Multiple gates failing

### Level 5: From-scratch — last resort
- Article topic just doesn't work in current angle
- Try alternative title from `angle.alternative_titles_considered`
- Completely new outline

## Cost

Each level has roughly cumulative cost (worst case 4 rounds):
- Level 1 × 4 iterations: ~$0.10 (cheap edits)
- Level 1 + 1 × Level 2: ~$0.25 (one section rewrite)
- Up to Level 3: ~$0.50 (one stage rerun)
- Up to Level 4: ~$1.50 (full build rerun)
- Up to Level 5: ~$2.50 (mostly full pipeline rerun)

Cap is set so total repair never exceeds ~$2.50 over baseline article cost.

## Output

After each escalation, write `workspace/{task}/repair-log.json` (append):

```json
{
  "iterations": [
    {
      "iteration": 1,
      "level": 1,
      "trigger": "AI-Slop score 24 > 20 threshold",
      "actions": [
        {"type": "edit", "line": 47, "before": "crucial", "after": "central"}
      ],
      "score_before": 24, "score_after": 18,
      "duration_seconds": 12,
      "verdict": "improved, but still failing other gates"
    },
    {
      "iteration": 2,
      "level": 1,
      "trigger": "Em-dash count 1 > 0",
      "actions": [...],
      "score_before": 18, "score_after": 16,
      "verdict": "ship"
    }
  ],
  "final_level": 1,
  "total_iterations": 2,
  "outcome": "passed"
}
```

## Handoff

If passed:
- `recommended_next_skill`: `independent-reviewer` (final blessing)
- → `phase-publish` if reviewer approves

If exhausted (4 rounds done, still failing):
- `completion_status`: BLOCKED
- Return `workspace/{task}/repair-log.json` + best-of-N draft to user
- User decides: accept with caveats, abort, or take over manually

## See also

- `schemas/quality.schema.json` (input format)
- `agents/editor-in-chief.md` (tombstoned 2026-08-12 — Level 2 dispatches agents/writer.md below)
- `agents/writer.md` (Level 2 dispatched agent)
- `subskills/build/section-drafter/SKILL.md` (Level 3/4 dispatched skill)
