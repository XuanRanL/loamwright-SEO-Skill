---
name: status-reporter
description: Show current pipeline state — in-progress tasks, current stage, elapsed time, accrued cost, ETA. Use when user runs /status or asks "what's the pipeline doing right now" or "is anything still running". Read-only — does not modify state.
allowed-tools: [Bash, Read]
disable-model-invocation: false
user-invocable: true
---

# Status Reporter

The user can't see what's happening during a 30-minute /article run. This skill
gives them visibility on demand.

## When to invoke

- `/status` — show all in-progress tasks (default)
- `/status <task_id>` — show specific task detail
- User asks: "is the pipeline still running?", "where are we?", "what's happening?"
- After any "looks stuck" complaint

## How to invoke

```bash
# All in-progress tasks
python -m scripts._core.status_reporter

# Specific task
python -m scripts._core.status_reporter --task-id <id>

# Machine-readable
python -m scripts._core.status_reporter --all --json
```

## Output format (human-readable)

```
━━ Task abc123 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Project:  my-fishing-site
  State:    RUNNING
  Phase:    build
  Stage:    section-drafting  (11/27)
  Progress: [████████░░░░░░░░░░░░] 40.7%
  Elapsed:  12m32s
  Idle for: 18s
  Cost:     $0.7234  (est. total $1.78)
  ETA:      ~14m remaining
```

## What gets surfaced

- **Stuck pipelines** — `Idle for >5min` → suggest `/resume`
- **Veto flags** — T04 fabricated stat, C01 fabricated citation, etc.
- **Repair level** — if escalating, surface (level 3+ means problems)
- **Cost trajectory** — alerts if track will exceed per-article budget

## What this skill does NOT do

- ❌ Restart/resume the pipeline (that's `/resume`)
- ❌ Kill stuck tasks (no destructive ops via /status)
- ❌ Show historical completed task details (use task workspace directly)

## Common output interpretations

| Pattern | Meaning | Action |
|---|---|---|
| Progress 0% + Idle 0s | Just started | Wait |
| Progress 30-90% + Idle 1-3min | Healthy progress | Wait |
| Progress unchanged + Idle 5+min | Probably stuck | Run /resume |
| State = BLOCKED + veto_flags non-empty | Quality gate vetoed | Manually review draft |
| Cost > est. total × 1.3 | Pipeline burning | Investigate; possible loop |

## Composition with other commands

- After `/status` shows stuck → `/resume`
- After `/status` shows complete → `/cost` for full breakdown
- Before /article → `/cost-estimate <format>` to preview cost
