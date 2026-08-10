---
name: resume
description: Resume an interrupted /article pipeline from its last checkpoint. Reads workspace state.json + verifies artifacts, decides whether to re-run the failing stage or jump forward. Use when /status shows a stuck task, network blip, OpenAI Batch wait, laptop sleep, etc.
allowed-tools: [Bash, Read, Skill]
disable-model-invocation: false
user-invocable: true
---

# Resume

The user got interrupted mid-/article (network blip, batch wait, laptop sleep, manual ctrl-C). This skill picks up where it left off.

## When to invoke

- `/resume` (defaults to most-recent in-progress task)
- `/resume <task_id>` (specific task)
- After `/status` shows a stuck or stale task
- Auto-suggest in error.json's recovery field

## How to invoke

Step 1: Plan the resume (dry-run first)

```bash
python -m scripts._core.resume_handler --task-id <id> --dry-run
```

This outputs:
```
━━ Resume plan for abc123 ━━━━━━━━━━━━━━━━━
  Currently at:  build / image-generation-queued
  Will resume:   build / images-injected
  ✓ Verified (2):
    • image_prompts.json
    • batch_id.json
  → Stage complete; jumping to next stage
  ETA:           18m42s
  Cost left:     ~$0.74

  Next: Re-invoke L2 phase 'build' for task abc123, resuming at stage 'images-injected'.
```

Step 2: Execute the resume

Invoke the L2 phase orchestrator named by `next_phase` in the plan, with the task workspace pointing at the existing one:

- `next_phase = research` → invoke `phase-research` SKILL with `--resume <task_id>`
- `next_phase = plan` → invoke `phase-build` SKILL with `--resume <task_id>`  
- `next_phase = build` → invoke `phase-build` SKILL with `--resume <task_id>`
- `next_phase = optimize` → invoke `phase-optimize` SKILL with `--resume <task_id>`
- `next_phase = publish` → invoke `phase-publish` SKILL with `--resume <task_id>`
- `next_phase = monitor` → invoke `phase-monitor` SKILL with `--resume <task_id>`

Each L2 reads existing artifacts and skips completed sub-steps (Stage-based guard).

## Decision logic (in resume_handler.py)

```
For task with Stage X:
  If all expected artifacts for Stage X exist:
    → jump forward to Stage X+1 (the stage that hadn't started)
  Else:
    → re-run Stage X (it didn't finish)
```

This is deterministic — same input always produces same plan.

## When resume is NOT possible

| Condition | Why |
|---|---|
| Task state = "completed" | Nothing to resume |
| Task state = "abandoned" | User explicitly tombstone'd it |
| state.json corrupted / unreadable | No checkpoint to resume from |
| Workspace directory deleted | Same — nothing to resume |

In these cases, `--dry-run` exits 1 with reason. User should /article fresh.

## Resume edge cases

### Image batch still pending
If Stage = `image-generation-queued` and batch_id exists but no images yet:
- Resume doesn't re-submit batch (costs $)
- It polls existing batch_id every 60s
- If batch failed → resubmit
- If batch succeeded → download images + jump to `images-injected`

### Cost budget exhausted mid-pipeline
If yesterday's budget exhausted and that's why task paused:
- Today's budget refreshed automatically (daily reset at UTC 00:00)
- Resume proceeds normally
- If budget still exhausted: error.json surfaces config.yaml edit path

### WP publish 5xx
If publish stage failed with 5xx:
- Resume re-tries with exponential backoff
- Each retry checks WP for partial state (post already created? media uploaded?)
- Uses wp_publisher's 7-step rollback if state is incoherent

## What this skill does NOT do

- ❌ Restart from scratch (use /article instead — workspace gets fresh task_id)
- ❌ Fix the underlying cause of failure (just resumes; doesn't debug)
- ❌ Edit artifacts (read-only diagnosis + dispatch)
- ❌ Skip mandatory quality gates (resume respects veto state)

## Composition with /status

```
/status                 → shows abc123 stuck at images-injected, idle 12m
↓
/resume abc123 --dry-run → confirms 2 artifacts ✓, ETA 18m
↓
/resume abc123           → actually picks up
```

## Cost guarantee

Resume never re-runs completed stages → no double-billing.
The cost-estimator delta = original estimate − cost-so-far ≈ what /resume will burn.
