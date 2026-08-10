# Stage Tracking Convention

> **Audit 2026-05-22 finding:** `schemas/state.schema.json::stage_history` was declared but no skill/agent/script wrote to it. 3/3 recent production workspaces had no stage history. Every "did X actually run?" question — including the image-curator silent-skip class that produced the 2026-05-22 image-placeholder drift — was unanswerable from forensics. **This reference exists to fix that.**

---

## ⛔ HARD RULE — NEVER write state.json with the `Write`/`Edit` tool (2026-07-05)

If you are an LLM agent (not a deterministic script) and you have Bash/Write tool access, this rule
is absolute: **never call `Write` (or hand-craft a full-file `Edit`) on
`memory/workspace/{task_id}/state.json`, for any reason.**

`Write` replaces the ENTIRE file. The helpers below (`record_stage_start`, `record_stage_complete`,
`update_state`) all do read-modify-write — they load the existing file, patch only the field(s) they
own, and save the whole thing back. A direct `Write` call can only construct state.json from fields
the agent can see (its own understanding of `brief`, its own view of `stage_history`), which **silently
deletes every field the agent doesn't know exists** — including `phase` / `current_stage` / `created_at`
(all `required` by `schemas/state.schema.json`, so the very next deterministic stage crashes with a
schema-validation error) and `project_constraints` (`wrapper_class`, `mandatory_sections`,
`differentiation_note` — orchestrator-populated fields no agent is ever given as input and has no way
to reconstruct).

**This happened in production on 2026-07-05:** a researcher subagent's direct `state.json` write during
a 3-article batch dropped `phase`/`current_stage`/`created_at`/`project_constraints`; the next stage
(`assembly`) crashed with `'phase' is a required property`, requiring a manual mid-pipeline recovery
that would have gone unnoticed in an unattended batch run. `scripts/_core/file_bus.py :: write_state()`
now refuses (raises `ValueError`) any write that would remove a previously-present required field or
`project_constraints` unless the caller explicitly passes `allow_field_removal=True` — this is defense
in depth, wired in code, not a prompt-only rule. But the instruction to you is simpler and has no
exceptions:

- ✅ `record_stage_start(task_id, stage, phase=...)` / `record_stage_complete(task_id, stage,
  status=...)` for anything stage-history-related.
- ✅ `update_state(task_id, **fields)` for any other single-field patch (it does read-merge-write).
- ❌ `Write` on `state.json`. Ever. If you believe a field needs setting that no helper covers, say so
  in your final report — that is a signal to add a helper, not to hand-author the file.

## Why stage_history matters

Without recorded stage execution, the orchestrator and post-hoc auditors cannot distinguish:

- **Stage skipped (legitimately)** — e.g. a project that doesn't need image generation
- **Stage skipped (bug)** — e.g. image-curator was supposed to run but the orchestrator forgot
- **Stage ran but failed silently** — a broad `except` swallowed the error

All three look identical in artifacts (no images.json present). They're different problems with different fixes. `stage_history` makes them distinguishable.

## When to call

Any phase-level skill or substantive subskill that performs an externally-observable side effect (writes a workspace artifact, calls an external API, modifies WordPress state) **must** record its execution in `stage_history`.

Examples that MUST record:
- phase-research running keyword research, SERP analysis, competitor analysis
- phase-build dispatching section-drafter, fact-check-and-citation, assembly
- phase-optimize running humanizer, schema-generator, the 4 quality gates
- phase-publish dispatching image-pipeline, wordpress-publisher, gbp post (when added)
- monitoring stages (T+7/14/30/90 callbacks)

Examples that DON'T need to record (would be noise):
- Pure read-only helpers (file_bus.read_artifact, regex helpers)
- Lints that are part of a quality-gate composite (the gate records once for the composite)
- Sub-steps within a single Python function (record the function entry, not every if-branch)

## How to call — Python script

The canonical helpers live in `scripts/_core/file_bus.py`:

```python
from scripts._core import file_bus as fb

# Pattern 1: explicit start + complete (preferred for long-running stages)
fb.record_stage_start(task_id, "wordpress-publisher", phase="publish")
try:
    # ... do the work
    fb.record_stage_complete(task_id, "wordpress-publisher", status="completed",
                             cost_usd=actual_cost_or_None)
except Exception as e:
    fb.record_stage_complete(task_id, "wordpress-publisher", status="failed")
    raise

# Pattern 2: context manager (preferred for short stages)
with fb.stage_context(task_id, "image-curator", phase="publish") as ctx:
    # ... do the work
    ctx.cost_usd = 0.05  # optional
# On exception: status="failed" recorded automatically, then exception re-raises
# On clean exit: status="completed" recorded
```

## How to call — SKILL.md / agent

SKILL.md and agent prompts don't directly execute Python. Instead, they instruct the orchestrator or the agent (when the agent is a code-running agent) to make the call. Standard prompt fragment:

```markdown
## Stage tracking

This stage MUST be recorded in state.json::stage_history. The orchestrator
calls (or the executing agent calls) at the start:

    fb.record_stage_start(task_id, "<this-stage-name>", phase="<phase>")

And at the end:

    fb.record_stage_complete(task_id, "<this-stage-name>",
                             status="completed" | "failed" | "skipped")

See references/orchestration/stage-tracking.md for the full convention.
```

## How to verify

Run after any task:

```bash
python -c "from scripts._core import file_bus as fb; \
           import json; \
           h = fb.list_stages_run('<task_id>'); \
           print(json.dumps(h, indent=2))"
```

Or programmatically check whether a specific stage ran:

```python
from scripts._core import file_bus as fb

if not fb.has_stage_run(task_id, "fact-check-and-citation"):
    # downstream stage may want to refuse to run (its inputs aren't ready)
    raise RuntimeError("fact-check-and-citation never ran for this task")
```

`verify_post.py` check 26 (added 2026-05-22) emits an informational warning if expected publish-phase stages have no recorded entry — defense-in-depth for the silent-skip class of bug.

## Failure-mode catalog

| Symptom in `stage_history` | Likely diagnosis |
|---|---|
| Entry missing entirely | Stage never invoked. Orchestrator bug, OR caller forgot to record. |
| Entry with `status: in_progress` and old timestamp | Stage crashed without finalizing. Look at logs around `started_at`. |
| Entry with `status: failed` | Stage ran but caught an exception. Look at logs for the error. |
| Entry with `status: completed` but expected artifact missing | Stage reported success but actually failed silently — classic broad-except bug. Open scripts/lint/silent_except_audit.py to scan the stage's code. |
| Same stage with multiple `completed` entries | Stage was re-run (repair-orchestrator). Expected during a repair iteration; suspicious otherwise. |

## When NOT to add stage_history recording

Don't record if:
- The "stage" is a pure helper called many times per article (would spam history)
- The stage runs in a tight loop (N writer agents in parallel — the dispatching subskill records ONCE; each writer doesn't record per-invocation)
- The artifact already exists from prior call to the same stage (idempotent re-runs — record on the FIRST run, not the no-op re-run)

In doubt: record. Noise in `stage_history` is far cheaper than silence.

---

## Reference implementations

These are the canonical examples of the convention applied correctly:

- `scripts/wordpress/wp_publisher.py` — Pattern 1 (start/complete with try/finally) around `publish()`. Records as stage `"wordpress-publisher"`, phase `"publish"`. Logs warnings on tracking failures via stderr; tracking failures must never block publish.
- `scripts/openai/openai_image_pipeline.py` — Pattern 1 around `generate_images()`. Records as stage `"image-pipeline"`, phase `"publish"`. Records `cost_usd` from the actual cost-ledger value. Sets `status="failed"` if partial slot success (success_count < total).

When adding tracking to a new stage, follow the wp_publisher pattern: lazy-import `file_bus` only when `task_id` is set, log tracking failures to stderr without raising, never block the actual work on tracking.
