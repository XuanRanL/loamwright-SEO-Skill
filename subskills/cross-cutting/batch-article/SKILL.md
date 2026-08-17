---
name: batch-article
description: Run /article end-to-end for a list of keywords. Each keyword goes through the FULL pipeline (research → plan → build → optimize → publish → monitor baseline). Use for agency-scale operations — drop 10-500 keywords, get 10-500 published articles. Resumable across sessions.
allowed-tools: [Bash, Read, Skill, Write, Edit]
disable-model-invocation: false
user-invocable: true
---

# /batch-article — Bulk full-pipeline content production

For agency-scale ops: give a list of keywords, get a list of published articles.
Each goes through the COMPLETE /article pipeline — no shortcuts, no quality
compromises.

## When to invoke

- `/batch-article --project my-site --file keywords.txt`
- `/batch-article --project my-site --keywords "kw1,kw2,kw3"`
- `/batch-article --resume <batch_id>` — pick up after interruption
- `/batch-article --status <batch_id>` — check progress
- `/batch-article --list` — all known batches

## Input file formats (auto-detected)

**Plain text (`.txt`)** — one keyword per line, optional comma-separated fields:
```
best fishing rods 2026, listicle
how to choose fishing rod, how-to-guide, professional, 4500
graphite vs fiberglass rods, comparison
```

**CSV (`.csv`)** — header with `keyword` column required:
```csv
keyword,format,voice,word_count
"best fishing rods 2026",listicle,professional,6000
"how to choose fishing rod",how-to-guide,casual,4500
```

**JSON (`.json`)** — array of objects:
```json
[
  {"keyword": "best fishing rods 2026", "format": "listicle"},
  {"keyword": "how to choose fishing rod", "format": "how-to-guide", "word_count": 4500}
]
```

## Workflow (Claude executes this)

### Phase 1: Enqueue

```bash
python -m scripts._core.batch_queue enqueue \
    --project {project_slug} \
    --file {keywords_file}
```

This creates `workspace/batches/{batch_id}/index.json` with all entries pending.
Output shows: batch_id + entry count + total estimated cost.

Contract notes (v3.41.0):
- Generated task_ids are underscore-form (`art_YYYYmmddHHMMSS_NNN_hex`) — they MUST
  satisfy `schemas/state.schema.json :: task_id` `^[a-z0-9_]{8,32}$`, because
  `assemble.py` validates the full state against it mid-pipeline. The pre-v3.41.0
  hyphenated ids passed the early stages then hard-failed at assembly
  (2026-07-17 project-lima batch). Pinned by `tests/test_batch_queue_taskid_schema.py`.
- `daily_cost_cap_usd` in the index comes from `~/.xuanran-seo/config.yaml ::
  cost_limits.daily_total_usd` — never a hardcode. A stale index with an empty cap
  is backfilled from config on load.
- Task workspaces live under `memory/workspace/{task_id}/` (the runner's WS_ROOT);
  the `workspace/` root holds only `batches/`.
- FORMAT IDS (v3.41.4): the per-row `format` column validates against
  `schemas/angle.schema.json :: format_id` enum — the single source of truth,
  mirrored 1:1 by `templates/*.md` basenames. An unknown format still soft-falls
  back to the default, but now WARNS on stderr; pre-v3.41.4 the check ran against
  a stale hand-maintained 10-item literal, so a REAL format like `buyers-guide`
  was silently rewritten to `listicle` and the whole article was planned in the
  wrong format with no error anywhere (2026-07-24 project-india batch). Pinned by
  `tests/test_batch_queue_format_enum_seam.py`. Watch the enqueue output's format
  column — it must echo the format you asked for.

**STOP & CONFIRM**: surface the estimate to user. Example:
> "Created batch-20260519-143201-7c2f8 with 25 entries. Estimated total cost: $58.40. Proceed?"

Wait for user approval before iteration.

### Phase 2: Iterate (one entry at a time, sequential)

For each pending entry (call `batch_queue next --batch-id X` until empty):

```
1. Get next entry:
   python -m scripts._core.batch_queue next --batch-id {batch_id} --json
   → returns {task_id, keyword, format, voice, ...}

2. Mark as running:
   python -m scripts._core.batch_queue mark --batch-id {batch_id} \
     --task-id {task_id} --status running

3. Create workspace + brief:
   - Create workspace/{task_id}/
   - Write brief.json with {keyword, format, voice, project_slug, ...}
   - Write initial state.json with stage=brief-intake
   - BRIEF ENUM DISCIPLINE (v3.41.3): `intent_override` accepts ONLY
     informational|commercial|transactional|navigational|null — the analyst
     label "commercial-investigation" is NOT a valid enum and now fails the
     fresh-task schema gate at the first runner advance (before any spend).
   - CTA PRODUCT ANGLE (2026-08-08): if the content-plan row names a CTA
     product angle (e.g. "Ear wash", "Gut probiotic"), set
     `brief.cta_category_hint` to that category's slug or name. The
     cta-brief-builder prefers the hint over content matching (which
     structurally cannot select one-token or long category names) while still
     enforcing `excluded_categories` + in-stock validation. Without the hint,
     short-named categories silently degrade to `default_category` and the
     operator's intended product angle is lost.
   - KEYWORD DIALECT (Rule 1): a keyword with opposite-dialect spelling
     ("optimisation" on an en-US project) stays VERBATIM in title/slug/meta;
     set `target_market_locale` to the keyword's dialect only if the audience
     really is that market — `spelling_dialect_check` auto-exempts the exact
     keyword's inflections either way (v3.41.3).
   - IMAGE COUNT (v3.42.17): OMIT `image_count` from the brief unless overriding —
     the enforced default is `scripts/_core/image_policy.py :: DEFAULT_IMAGE_COUNT`
     (6 = 1 cover + 5 section images; max 8), pinned to the schema annotation by
     `tests/test_image_count_policy.py`. Short formats (news-analysis,
     faq-knowledge, shortlist-validation) SHOULD set a lower explicit count —
     the cost estimator's per-format rows assume they do; generation itself
     always follows the brief, not the format.
   - QUALITY TARGET (v3.42.16): OMIT `quality_target_score` from the brief
     unless the operator explicitly requested a stricter bar. The enforced
     default is `scripts/_core/review_target.py :: DEFAULT_REVIEW_TARGET` (80);
     the schema annotation is pinned to that constant by
     `tests/test_review_target_single_source.py`. Do NOT copy a number out of
     the schema into the brief "to be safe" — a bootstrapped 95 (the schema's
     old, enforced-by-nothing annotation) burned six reviewer/repair rounds on
     2026-08-17 against content every review round called clean. Review scores
     are LLM judgments with ±4-point run-to-run variance; a target above ~90
     turns that variance into an unpassable gate. If a mis-set target is
     discovered mid-run, the sanctioned correction is
     `file_bus.update_state(task_id, brief=...)` plus a note in the batch-queue
     entry — never a silent edit, and NEVER an edit to review.json's score.

4. Invoke L1 seo-blog SKILL.md with this task_id:
   - This runs the FULL pipeline (research → plan → build → optimize → publish → monitor baseline)
   - L1 reads workspace/{task_id}/brief.json
   - L1 writes all artifacts back to workspace/{task_id}/
   - L1 ends with publish-complete + baseline

5. After L1 returns:
   - Read workspace/{task_id}/publish-log.json for post_url
   - Sum cost from filtered cost-ledger by task_id
   - Mark entry:
     python -m scripts._core.batch_queue mark --batch-id {batch_id} \
       --task-id {task_id} --status completed \
       --workspace-path workspace/{task_id} \
       --published-url <url> \
       --actual-cost-usd <cost>

6. If L1 fails (error.json present):
   - Mark entry as failed with error message
   - Continue to next entry (do NOT abort the batch)
```

### Phase 3: Summary

After the queue is exhausted:
```bash
python -m scripts._core.batch_queue status --batch-id {batch_id}
```

Report to user:
- N completed / M failed / K skipped
- Total actual cost vs estimate
- Failed entries list (with reasons)
- Suggest: `/refresh-queue` for failed entries OR manual review

## Safety guards

### Daily cost cap
Before each iteration, check daily total via cost-ledger summary:
```bash
python -m scripts._core.cost_ledger --summary --period day --json
```
If `total_usd > daily_total_usd × 0.95`:
- Pause batch (mark remaining entries still pending)
- Tell user: "Daily cap approached; pausing batch. Resume tomorrow with `/batch-article --resume {batch_id}`."

### Per-article cost cap
Before each L1 invocation, pre-flight:
```bash
python -m scripts._core.cost_estimator --format {fmt} --words {wc} --json
```
If `check == "blocked"`:
- Mark entry skipped with reason
- Continue to next

### Rate limit / API failure
If 3 consecutive entries fail with API errors (rate limit, network):
- Pause batch (wait 5 min)
- Re-probe with /status check
- Resume if cleared

### Parallelism
Default sequential (`parallelism: 1`). For agency use with `--parallelism 3`:
- Spawn 3 parallel L1 invocations
- Each writes to its own workspace/{task_id}/
- Image Batch API contention: keep ≤3 (OpenAI Batch concurrent limit)
- Cost guard remains active across all running tasks

## Resume protocol

```
/batch-article --resume {batch_id}
```

Does:
1. Read `workspace/batches/{batch_id}/index.json`
2. Find entries with status=pending OR status=running (interrupted mid-pipeline)
3. For status=running entries: invoke `/resume {task_id}` instead of fresh L1
4. For status=pending: standard new L1 invocation
5. Continue until queue exhausted

### One operator per task (2026-08-17)

The runner's `.pipeline-driver.lock` serializes `run_pipeline` INVOCATIONS, but no
lock can stop two OPERATORS — a resumed/background driver and the parent session —
from editing the same workspace's artifacts concurrently. On 2026-08-17 a parent
session hand-repaired a draft and dispatched its own reviewer while the background
driver it had earlier resumed was still running its own repair rounds on the same
task; the two interleaved without corruption only by luck, and the task ended up
marked `failed` in the batch queue while its artifacts said otherwise. The rule:

- A task has exactly ONE operator at a time. Before taking over a task you
  delegated, either (a) confirm the driver has terminated (its final report
  arrived and it holds no live children), or (b) explicitly order it to stand
  down and wait for the acknowledgment.
- Never repair artifacts of a task whose driver may still be live. To see where
  a possibly-live task really is, read `state.json :: stage_history` — never
  invoke the runner as a "status check" (that is the v3.36.2 double-publish
  pattern this file already bans).
- A batch-queue status set by a driver that was later overridden (e.g. `failed`
  on a task that then completed) must be corrected with a note explaining the
  override — the queue is the operator-facing record; a stale `error` field on a
  completed entry reads as an unresolved defect in the next audit.

## Cost transparency

Before starting:
- Show estimate per format breakdown
- Show daily budget remaining
- Show per-client cost attribution (if project has client metadata)

During iteration:
- After every 5 completed entries, print a mini-status:
  > "[12/25] last 5 cost $11.20; on track for $58 total"

After completion:
- Final summary with actual vs estimated
- Cost overrun analysis if >20% delta

## What this skill does NOT do

- ❌ Skip pipeline steps for speed (each article gets FULL treatment)
- ❌ Share research between entries (each is independent — different keywords)
- ❌ Auto-publish without per-article gate-checks (each L1 still hits all 4 quality gates)
- ❌ Continue past daily cap (safety)

## Composition

```
Daily agency workflow with /batch-article:

morning:  /batch-article --project client-a --file daily-keywords.txt
          (review estimate, approve)
          → batch runs, Claude iterates through

mid-day:  /status                          (check pipeline)
          /cost                            (track burn)

evening:  /batch-article --status {batch_id}
          (review failures, decide on /refresh-queue or manual)

next-day: /batch-article --resume {batch_id}
          (if paused by daily cap)
```

## Recommended sizing per session

| Articles | Session length | Daily budget needed |
|---|---|---|
| 1-5 | ~30 min | ~$10 |
| 10-25 | ~2-5 hr | ~$30-60 |
| 25-50 | use --resume across days | ~$60-120 |
| 50+ | multiple batches, multiple days | scale daily cap |

For 100+ articles, split into 4× 25-article batches across 4 days.
