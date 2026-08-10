---
name: seo-blog
description: Production-grade SEO + GEO content factory. Routes user intent to one of 5 phases (research / build / optimize / publish / monitor) or runs end-to-end. Use whenever the user wants to write a blog post, create SEO/GEO-optimized articles, refresh existing content, audit a page, or publish to WordPress. Always trigger when user mentions "blog", "article", "content", "SEO", "SERP", "AI search", "ChatGPT visibility", "Google AIO", "Perplexity", "rank", or supplies a topic + keyword combination. Also triggers on URL + write intent.
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, Task]
---

# SEO Blog Writer · Master Orchestrator (v3.7)

Production-grade content factory for the Google + AI search dual front.

## ⛔ STOP — READ THIS FIRST: Deterministic Runner-Driven Execution (v3.14)

**When the intent is `/article` (full pipeline), you DRIVE THE PIPELINE WITH THE RUNNER, not by hand.**
**DO NOT read the pipeline prose in this file and decide stages yourself.**
**DO NOT call `orchestrator --action next/verify` manually between stages — the RUNNER does that for you.**
**DO NOT write artifact JSON files (fact-check.json, humanizer-report.json, review.json) manually.**

### Why a runner now drives (v3.14, 2026-06-03)

Before v3.14 the orchestrator was a PASSIVE state machine and the LLM had to hand-drive all ~30
stages — calling `--action next`, running/dispatching each stage, then `--action verify` — between
EVERY stage, for EVERY article. That manual ritual is exactly where steps got skipped or driven
out of order (2026-05-26 "23/35 skipped"; 2026-06-02 "geo skipped"; 2026-06-03 "stage records
missed + heavy by-hand driving"). Enforcement made bad outcomes *detectable* at the gates, but
execution was only as reliable as operator discipline. **`scripts/pipeline/run_pipeline.py` now
drives the loop in CODE**: it runs/launches/checks every BASH/BACKGROUND/CHECK stage itself and
records it, and STOPS only to hand you the handful of LLM stages that genuinely need a subagent.
Your surface area drops from "orchestrate 30 stages" to "service the LLM stages I'm handed."

### The Loop (execute this after state.json is created)

```
REPEAT:
  1. result = Bash("python -m scripts.pipeline.run_pipeline --workspace {task_id} --json"
                   [+ " --completed-llm {last_llm_stage}" if you just finished one])

  2. Read result.action:
     "COMPLETE"      → DONE. Proceed to the publish-confirmation step.
     "DISPATCH_LLM"  → Dispatch Agent(subagent_type=result.subagent_type, prompt=result.dispatch_prompt).
                       If subagent_type is "", execute result.description inline (format-selector /
                       outline-architect / meta-builder are inline LLM stages).
                       After the subagent finishes, confirm every path in result.expected_outputs exists,
                       then GOTO 1 with --completed-llm {result.stage}.
                       ⚠ TRANSIENT NO-OP (v3.38.3): a dispatched subagent can occasionally return
                       with ZERO tool uses and no output files (harness init glitch — a 2026-07-09
                       humanizer did this, returning only a garbled system-reminder). expected_outputs
                       will be missing: simply RE-DISPATCH the same subagent once before investigating
                       anything else. Same rule when a subagent dies mid-run to an API/session error
                       (a geo-auditor was killed this way in the same batch): check whether its
                       evidence artifact landed on disk; if not, re-dispatch — the draft itself is
                       usually untouched.
     "GATE_FAILED"   → A lint/quality gate found defects (result.gate). Route to repair (fix the draft
                       or re-dispatch the responsible subagent per subskills/cross-cutting/repair-orchestrator),
                       then GOTO 1 (the runner re-runs the failed stage).
     "WAIT"          → A CHECK isn't ready (e.g. Fork B image gen still running). Wait briefly, GOTO 1.
     "BLOCKED"       → A stage is missing inputs (result.missing_inputs). Fix them, GOTO 1.
     "ERROR"         → A BASH stage crashed (result.detail). Inspect, fix, GOTO 1.
     "LOCKED"        → Another run_pipeline driver is ALREADY active on this workspace (exit 30).
                       Wait for it to return, then GOTO 1. NEVER delete the .pipeline-driver.lock
                       sidecar and NEVER launch a second driver call while one is still running —
                       the 2026-07-07 batch double-published 2 of 3 posts exactly this way (a bare
                       status-check invocation re-dispatched the in-flight wordpress-publisher).
```

⚠️ One driver per workspace at a time (v3.36.2). The runner holds an exclusive per-workspace
lock (`{workspace}/.pipeline-driver.lock`) for the whole invocation, so a concurrent call —
including an innocent-looking bare `run_pipeline --workspace X --json` "status check" while a
background invocation is still running — now returns LOCKED instead of double-driving. To check
progress while a driver runs, read `state.json :: stage_history` instead.

The runner handles ALL `--action next` / `--action verify` / stage-recording / ordering internally,
so a stage can no longer be silently skipped or left unrecorded. You only ever act on DISPATCH_LLM,
GATE_FAILED, WAIT, BLOCKED, ERROR. The underlying engine is still
`scripts/pipeline/orchestrator.py` (the deterministic artifact/evidence/provenance gatekeeper);
the runner is the loop on top of it.

### Three Rules That Are Not Negotiable

1. **Every DISPATCH_LLM with a `subagent_type` MUST be dispatched as an Agent call.** You are the driver, not the writer/fact-checker/humanizer/reviewer. The independent-subagent property is load-bearing for quality.
2. **Never write a provenance-gated artifact yourself.** The full set (single source of truth: `scripts/_core/provenance.py`, shared by orchestrator + pre_publish_gate since v3.41.3) is: fact-check.json, humanizer-report.json, review.json, geo-audit.json, visual-design-report.json, cta-draft.json, image-qa-report.json, internal-link-report.json. Each requires a `_generated_by` value only the real subagent produces.
3. **Always re-invoke the runner with `--completed-llm {stage}` after an LLM stage.** That is how the runner verifies + records it and advances. Do not skip it.

> Manual fallback (only if `run_pipeline` is unavailable): the legacy hand-driven loop is
> `orchestrator --action next` → execute → `orchestrator --action verify --stage X`, repeated
> between every stage. The runner exists precisely so you don't have to do this by hand.

### Execution-evidence enforcement (v3.12, 2026-06-02) — every stage must PROVE it ran

Root cause of the 2026-06-02 batch incident ("geo step silently skipped"): the optional
LLM stages `geo-content-optimizer`, `internal-linker`, and `citation-capsule-builder` had
NO required output artifact, so `--action verify` auto-passed them on the honour system. An
orchestrator under context pressure recorded them "completed" without ever dispatching the
subagent. Same failure class as the 2026-05-26 / 2026-05-27 incidents: enforcement was
artifact-gated, but some stages produced no artifact, so they were unenforceable.

**The cure — there is no longer an honour-system pass.** Every work stage now declares
execution evidence, and `verify` refuses to mark it complete without that evidence:

| Stage | Evidence the orchestrator now requires |
|---|---|
| `geo-content-optimizer` | `geo-audit.json` with `_generated_by:"geo-auditor-subagent"` |
| `internal-linker` | `internal-link-report.json` (links_added, anchors[]) |
| `citation-capsule-builder` | `citation-capsule-result.json` (from `citation_capsule_lint --out`) |
| `serp-analysis` / `competitor-analysis` | non-empty `serp_features` / `competitors` keys in `research.json` |
| (already enforced) `fact-check` / `humanizer` / `independent-reviewer` | provenance-stamped JSON |

`--action verify` on a stage whose evidence is missing now returns `passed:false` and exits 1.
The ONLY stage still recorded on trust is the BACKGROUND `image-pipeline-fork` launch, whose
real output (`images.json`) is checked later at the JOIN.

**If you genuinely want to skip an optional stage, you MUST do it explicitly — never fake completion:**

```
python -m scripts.pipeline.orchestrator --workspace {task_id} --action skip \
    --stage geo-content-optimizer --reason "client opted out of GEO pass for this batch"
```

This records `status:"skipped"` (NOT `"completed"`) with the reason in the audit trail, so a
later auditor can always tell what RAN from what was deliberately DROPPED. Skipping a
**mandatory** stage is refused (exit 1). The rule of thumb: a stage is either (a) run, with its
evidence artifact on disk, or (b) explicitly skipped with a logged reason. "Quietly recorded
complete" is no longer possible — and `tests/test_orchestrator_evidence_enforcement.py` pins it.

When `--action next` returns one of these optional stages, do the work and produce the evidence
artifact, OR skip it with a reason. Do not call `verify` expecting a free pass.

## Startup sequence (runs every invocation)

1. **Source `bin/preamble.md`** — version check + active project load
2. **Resolve active project** — `XS_ACTIVE_PROJECT` env var WINS, then the shared file.
   This is the contract that makes parallel multi-session work (see "Parallel
   multi-session" below). Resolve via the canonical helper, NOT a raw file read:
   ```bash
   # env-first resolution (XS_ACTIVE_PROJECT → ~/.xuanran-seo/active-project file):
   active_slug=$(python -c "from scripts._core import active_project as a; print(a.get_active_project() or '')")
   ```
   ```python
   # equivalent semantics:
   active_slug = os.environ.get("XS_ACTIVE_PROJECT") or read("~/.xuanran-seo/active-project")
   if active_slug:
       business_context = load(f"projects/{active_slug}/business-context.json")
       check_freshness(business_context)  # warn if >90d stale
   else:
       business_context = None
   ```
   ⚠️ Never read `~/.xuanran-seo/active-project` directly to decide a NEW task's
   `project_slug`. Always go env-first. In a parallel session, another session may
   have overwritten the shared file; the env var is this session's authoritative pin.
3. **Load shared context** (`@context/*.md` files exist in plugin context/)
4. **Initialize cost ledger** (read `~/.xuanran-seo/config.yaml`, check daily total)
5. **Detect local-intent (v3.4.0, 2026-05-22)** — **MANDATORY Bash invocation** of `scripts/_core/local_intent_runner.py` after state.json exists. The wrapper reads project's `business-context.json :: location.local_seo_mode`, calls `_detect_local_intent.py` if not "off", and writes `state.brief.local_mode` + `state.brief.location_anchor` into state.json. This is the ONLY way to set these fields — never inline-Python the detection elsewhere (wiring-audit 2026-05-22 P1 found inline-pseudocode drift).

   ```bash
   # In seo-blog orchestrator (Bash invocation, NOT pseudocode):
   python -m scripts._core.local_intent_runner \
       --task-id {state.task_id} \
       --project-slug {active_project_slug or ''} \
       --keyword "{state.brief.primary_keyword}" \
       --json
   # Parse JSON output to learn local_mode + location_anchor + ambiguous status.
   ```

   **Scope is WORLDWIDE (v3.40.0):** the gazetteer covers 252 countries (+ aliases like "uk"/"usa"), ~3.8k states/provinces (Ontario, Guangdong, Queensland, England, …) and ~34k world cities ≥15k population — a keyword like "chinese age-restricted products toronto", "tea wholesale guangdong" or "slope mower queensland" MUST set `local_mode=true` with the correct `location_anchor.country`. Cross-country duplicates (Vancouver BC/WA, London GB/ON) are resolved by in-keyword cue → the project's `location.target_markets` bias (derived inside the wrapper; override with `--countries CA,GB`) → population ≥2x → `ambiguous=true`.

   If output's `ambiguous=true`, present `disambiguation_options` to the user and re-run with their pick before invoking phase-research (province-vs-city twins like bare "ontario" flag ambiguous by design). If `local_seo_mode=off`, the wrapper logs "skipped" and writes `local_mode=false` (legacy behavior; downstream skills follow non-local path).

   Downstream effect: when local_mode=true, `subskills/plan/format-selector/SKILL.md` Step 0 routes to `templates/local-state-pillar.md` or `templates/local-city-page.md`; `subskills/build/section-drafter/SKILL.md` passes `local_mode` + `location_anchor` + `locality_signals_required` + `local_article_pattern` to each writer; `subskills/optimize/schema-generator/SKILL.md` + `scripts/build/schema_jsonld_builder.py` emits LocalBusiness leaf + Service.areaServed (archetype A/B/C) OR OnlineStore/Organization + Article.spatialCoverage (archetype D/E); quality gates include `gates.local_uniqueness.passed`; verify_post check 27 enforces geo-anchor density.

## HARD RULES — these override default behavior

These rules came from production failures. Violating them produced real costs (wasted draft work, unstyled live posts, missed traffic on legitimate keyword variants). Apply unconditionally.

### Rule 1 — Exact-keyword fidelity (never silently dedupe)

When a user supplies a search term — including typos, grammatical variants, plurals/singulars, alternate spellings, or terms "similar" to an existing article — that term IS the SEO target. Treat it as a distinct keyword regardless of perceived overlap with prior work. SERP and AI-search engines differentiate `1000 watt led grow light` from `1000 watt led grow lamps`, `seo content writer` from `seo content writter`, `chatgpt seo` from `chat gpt seo`. Users searching the variant are real traffic.

Forbidden behaviors:
- Silently substituting a similar existing article as "the same thing"
- Suggesting the variant is a typo and rewriting against the corrected form without asking
- Assuming a plural↔singular pair shares search intent
- Treating a "nearby" keyword in an existing article as already-served

Required behavior:
- Before reusing/canonicalizing/redirecting to existing content, **ask the user explicitly**. Default is: new keyword = new article.
- If there is a genuine cannibalization risk (same primary search intent), the answer is differentiation by angle/format/persona, not skipping the work.
- Per project, maintain an inventory of existing live articles (slug + focus_keyword + angle) in `projects/{slug}/articles/` so the differentiation analysis is informed, not guessed.

### Rule 2 — Project article CSS is mandatory at publish

If `projects/{slug}/brand/article-css.css` (or `.min.css`) exists, **every new post must be wrapped with the scoped CSS at publish time**. The wrapper class MUST equal the CSS scope selector — typically `{slug}-pillar` (e.g. `project-charlie-pillar`), but read the CSS file's leading selector to confirm. A wrapper-class/scope mismatch silently orphans every rule.

> **Style-token projects (v3.42.0+, all 13 projects today).** If `projects/{slug}/brand/style-tokens.json` exists, the PUBLISHED class names are per-project HMAC tokens, not the legacy names — `project-charlie-pillar` ships as `mwxiod-1ymm61`. `wp_publisher._apply_project_styling` rewrites body + CSS at the publish boundary; internal artifacts (draft.md, lints) keep the legacy names. **Never hand-write or grep for a published class name — resolve it:** `python -m scripts._core.style_tokens --show {slug}`. Verifying live HTML for `.{slug}-pillar` on a tokenized project is a check that can never pass.


The canonical wrapping pattern (Gutenberg-block compatible, matches the existing published posts on the site):

```html
<!-- wp:html -->
<style>{minified CSS contents}</style>
<!-- /wp:html -->

<!-- wp:html -->
<div class="{wrapper}">   <!-- resolve via style_tokens; NOT literally {slug}-pillar -->
<!-- /wp:html -->

{article body HTML}

<!-- wp:html -->
</div>
<!-- /wp:html -->
```

Inline `<script type="application/ld+json">` schema blocks should be appended OUTSIDE the closing wrapper so the schema is not styled.

The `phase-publish` skill MUST verify the wrapper class is present in the rendered front-end HTML before declaring publish complete.

## Batch-mode orchestration (multiple articles)

When the user requests N articles in one session, you MUST process them **one at a time through the FULL orchestrator loop**. Parallelism is allowed ONLY within a single article (e.g., parallel writer subagents for different sections, Fork B image pipeline). Cross-article parallelism of LLM stages causes context exhaustion and subagent stub shortcuts.

### Parallel multi-session (multiple projects at once) — v3.14.4

The one-at-a-time rule above is about a **single session**. A different, supported
axis is running **N separate Claude Code sessions** (separate OS processes), each
writing for a **different project**. To do this safely, each session pins its
project with the `XS_ACTIVE_PROJECT` env var:

```powershell
# 3 terminals, one project each:
.\bin\launch-session.ps1 project-charlie     # session A
.\bin\launch-session.ps1 project-juliet   # session B
.\bin\launch-session.ps1 project-kilo      # session C
```

Why this is safe (v3.14.4 isolation fixes):
- **Project identity** resolves env-first (`scripts/_core/active_project.py`), so a
  session never reads another session's project. The shared `active-project` file
  is never written by env-pinned sessions → zero contention, no wrong-site publish.
- **Shared global writes are locked** (`scripts/_core/file_lock.py`):
  `cost-ledger.jsonl` appends and the `.tavily-rr-counter` round-robin RMW are
  cross-process exclusive-locked, so concurrent sessions don't corrupt the ledger
  or collide on Tavily keys. The daily budget stays globally accurate (shared by
  design).

Rules for env-pinned sessions:
- Do **not** use `/switch` inside an env-pinned session — the env var wins and the
  file write only affects future non-pinned sessions (`set_active_project` warns).
- Each session still processes its own articles **one at a time** (the within-session
  rule is unchanged).

### Why batch shortcuts happen and how the code now prevents them

**Root cause (2026-05-27 3-article batch incident):** During batch runs, context pressure causes the LLM to write stub JSON files (fact-check.json, humanizer-report.json, review.json) directly instead of dispatching subagents. Articles 2+ progressively skip more stages. The pattern:
- Article 1: full pipeline with real subagents
- Article 2: humanizer + reviewer skipped (LLM writes stubs)
- Article 3: humanizer + reviewer + quality-gates all skipped

**6 code-level fixes now prevent this (v3.8.0):**

1. **Provenance validation on INPUTS** (orchestrator.py): `_artifact_valid()` now checks `_generated_by` at the INPUT check, not just output, for the full shared set in `scripts/_core/provenance.py` (fact-check / humanizer-report / review / geo-audit / visual-design-report / cta-draft / image-qa-report / internal-link-report — v3.41.3 unified the orchestrator's and pre_publish_gate's previously-drifted lists). Writing a stub without the correct `_generated_by` field causes the NEXT stage to report BLOCKED.

2. **Pre-publish-gate blocks wordpress-publisher** (orchestrator.py): wordpress-publisher now requires `pre-publish-gate-result.json` as an input. The gate cannot be bypassed by running the publisher directly.

3. **Pre-publish-gate writes result file** (pre_publish_gate.py): Gate now writes `pre-publish-gate-result.json` to workspace, making it trackable by the orchestrator.

4. **Subagent enforcement warnings** (orchestrator.py): Stages in `SUBAGENT_ENFORCED_STAGES` set return `subagent_enforced: true` + `enforcement_warning` in the orchestrator response. The LLM sees an explicit "MANDATORY: dispatch via Agent()" instruction for every quality-critical stage.

5. **quality.json required by pre-publish-gate** (orchestrator.py): quality.json is now a mandatory input for the pre-publish-gate, ensuring `run_quality_gates` actually executes.

6. **Orchestrator call is mandatory between EVERY stage** — The orchestrator tracks progress and refuses to advance. The LLM MUST call `--action next` to learn what to do.

**Required batch pattern (v3.14 — runner-driven):**
```
FOR EACH article in batch:
    1. Create workspace + state.json
    2. LOOP (drive THIS article with the runner; see "The Loop" at the top of this file):
       a. result = run_pipeline --workspace {task_id} [--completed-llm {last_llm_stage}]
       b. IF result.action == "COMPLETE" → move to next article
       c. IF result.action == "DISPATCH_LLM" → dispatch Agent(subagent_type=result.subagent_type)
          (writing the artifact yourself WILL fail provenance validation), then GOTO 2a with
          --completed-llm {result.stage}
       d. IF result.action in (GATE_FAILED / WAIT / BLOCKED / ERROR / LOCKED) → handle per "The Loop", then GOTO 2a
          ⚠ LOCKED (v3.36.2): another driver already holds this workspace's .pipeline-driver.lock.
          NEVER run a second run_pipeline call (even a bare "status check") while one is still in
          flight — that exact pattern double-published 2 of 3 posts in the 2026-07-07 batch. Read
          state.json :: stage_history to check progress instead.
    3. Only move to next article after result.action == "COMPLETE"
       ⚠ COMPLETE is returned only after verify-post. The runner will NOT report COMPLETE after
       wordpress-publisher alone — verify-post is the next mandatory stage. Publishing without
       verify-post is an incomplete pipeline.
       ⚠ Since v3.35.3, COMPLETE also re-reads the content verdicts (verify-result.json
       overall_pass, fact-check verdict, review score) via the shared _content_gate_reason()
       helper — a bare re-invocation after a gate ERROR can no longer flip the failed stage
       to completed (the 2026-07-06 COMPLETE-lie seam). If a gate ERRORs, FIX the underlying
       defect and re-run the stage; do not expect a fresh call to "clear" it.
```
Process articles ONE AT A TIME through the runner. Research MAY be parallelized across articles
(independent web search), but everything from fact-check onward is sequential per article. The
runner enforces ordering within each article; you only decide which article to drive next.

**Forbidden batch shortcuts (now code-enforced, not just prose):**
- Writing humanizer-report.json / review.json yourself → provenance check fails at pre-publish-gate input validation
- Skipping quality-gates → quality.json missing → pre-publish-gate BLOCKED
- Running wordpress-publisher before pre-publish-gate → missing pre-publish-gate-result.json input → BLOCKED
- Hand-editing review.json score → provenance check fails if _generated_by missing/wrong

The research phase CAN be parallelized across articles (independent web searches). Everything from fact-check onward MUST be sequential per article.

### Re-angling / re-running part of an article: use `--action reset`, NEVER hand-edit state (v3.38.3)

If an article must be re-planned mid-batch (e.g. a Rule-1 cannibalization catch forces a new
angle after research), do ONE of:

1. **Fresh task_id (preferred for a full re-angle):** create a new workspace, copy
   `research.json` + `research/` over, and drive it normally. Zero reset semantics to reason about.
2. **Sanctioned reset:** `python -m scripts.pipeline.orchestrator --workspace {task_id} --action reset
   --stage {stage_name} --reason "..."` — re-arms `{stage_name}` and everything after it by clearing
   ALL THREE completion stores (state.json stage_history, pipeline-checklist.json, and the
   expected_outputs/evidence artifacts, derived from the Stage table). Refuses under an active
   `.pipeline-driver.lock`. Resetting to a stage at-or-before `assembly` gives a clean rebuild;
   resetting later re-runs stages but cannot revert in-place draft.md edits. It cannot delete an
   already-created WP post (reported as a warning).

**NEVER hand-truncate `state.json::stage_history` or hand-delete a subset of artifacts to "reset".**
Completion state lives in three stores; a partial hand-reset leaves `_stage_complete()` satisfied by
the survivors (checklist records + `*-result.json` evidence files) and the runner SILENTLY JUMPS the
stages you thought you reset — the 2026-07-09 project-kilo batch lost 6 stages exactly this way
(citation-inject among them: 41 unresolved `[claim:]` markers reached the draft and had to be
repaired by hand-running the stages).

## Intent routing

Parse user request → exactly one of:

| User says | Route to |
|---|---|
| `/init <url>` or URL alone (not in projects/) | `subskills/init/website-project-init/` |
| `/setup-categories` or "design category architecture" | `subskills/init/wordpress-category-setup/` |
| `/article <topic>` or "write a blog about X" | **End-to-end pipeline** (this skill drives all 5 phases) |
| `/audit <url>` | `subskills/optimize/` (skip research/build/publish) |
| `/refresh <url>` | `subskills/monitor/content-refresher/` |
| `/cluster <pillar>` | `subskills/plan/topic-clustering/` |
| `/factcheck <url>` | `subskills/build/fact-check-and-citation/` |
| `/humanize <url>` | `subskills/optimize/humanizer/` |
| `/ai-visibility <url>` | `subskills/monitor/ai-visibility-tracker/` |
| `/aio-recovery <url>` | `subskills/optimize/ai-overview-recovery/` |
| Ambiguous | Ask user to pick 3 options |

## End-to-end pipeline (default for `/article`)

> **⛔ REMINDER: Use the orchestrator loop from section 1 above. The prose below is REFERENCE ONLY.**
> Do not use this prose to decide which stage to run next. Call `orchestrator.py --action next`.

The pipeline forks an **image-generation branch** immediately after the outline lands (Phase Plan), so image API time overlaps with Phase Build + Phase Optimize. By the time the wordpress-publisher needs the images, they are almost always ready. This saves 8–14 minutes per article on realtime mode and ~25 minutes on batch mode vs. the legacy serial ordering.

```
state.json initialized → ↓

Phase Research (skills/phase-research/SKILL.md)
  Stages: keyword-research → serp-analysis → competitor-analysis
          → content-gap-analysis → surface-targeting
  Output: workspace/{task}/research.json

Phase Plan (implicit, runs sub-skills directly)
  Stages: format-selector → topic-angle-selector → outline-architect
          → image-slot-allocator → image-prompt-designer
  Output: workspace/{task}/{angle.json, outline.json, image-prompts.json}
  ✋ Human approval gate (optional, configurable)
  ↓
  Category-selection (MANDATORY, 2026-05-23c). Runs AFTER assembly produces
  draft.md so the script can scan body content for signal keywords. Updates
  meta.json::categories[] with the multi-category recommendation.

  ```bash
  python -m scripts.build.category_selector \
      --task-id {task_id} \
      --project-slug {active_project_slug} \
      --max-categories 3
  ```

  Why mandatory: previously the orchestrator copied `business-context.json ::
  default_categories` directly into meta.json (single category, every article).
  This created the systemic "all articles → 144" bug confirmed across 13 posts
  on project-charlie. The selector reads body keywords + product H3 count +
  format_id + title and ranks signal-matched categories alongside the project
  default. Default is always preserved (backwards-compat); top N-1 signal
  matches added. See `feedback_publisher_category_systemic_bug.md`.

  PRESERVE-META semantics (v3.41.2): the meta-builder's live-resolvable
  `categories[]` are PRESERVED — they occupy cap slots first and the selector's
  scored candidates fill only the remaining slots. The scorer sees body keywords
  only; it cannot see format/intent, which is exactly what the meta-builder
  encodes. Pre-fix the selector REPLACED meta wholesale, which dropped the most
  apt category on 4 real articles (project-foxtrot 2026-07-14; all 3 project-lima
  2026-07-18 — a pricing article lost "Pricing & Cost" to parts-wear body
  keywords). `--replace-meta` restores the old behavior for deliberate
  re-categorization runs. Names that do not resolve on the live site are still
  dropped (stale/junk names cannot be preserved into a broken id pair).

  Per-project signals live in `projects/{slug}/categories-config.json ::
  categories[].auto_select_signals`. Projects without signals defined fall
  through to default-only (preserves existing behavior).

  Project cap override: `projects/{slug}/business-context.json ::
  category_policy.max_per_article` (default 3). project-charlie uses 4 because the
  content cross-cuts buyer-guide + comparison + retrofit + tech routinely.

  Performance: if `projects/{slug}/categories-live.json` exists (WP snapshot),
  the selector also writes `meta.category_ids[]` so wp_publisher skips the
  per-category GET /wp/v2/categories?slug=X round-trips at publish time
  (saves 3-6 REST calls per publish). Regenerate snapshot via:

  ```bash
  python -m scripts.wordpress.snapshot_categories {site_slug}
  ```

  Run after any WP-side category change (add / rename / delete / reparent) or
  quarterly. The snapshot is a hint, not source-of-truth — wp_publisher falls
  back to the slow name-resolution path if IDs aren't present.

  Audit existing posts: `python -m scripts.wordpress.audit_post_categories
  {site_slug} [--apply]` runs the same selection logic against every live post
  body and PATCHes any whose categories drift from the recommendation.
  Preserves publish/draft status (does NOT revert publish to draft).
  ↓
  ┌────────────────────────────────────────────────────────────────┐
  │ FORK A — main editorial pipeline (foreground, blocking)        │
  │                                                                │
  │ Phase Build → section-drafter (N parallel) →                   │
  │             fact-check-and-citation → assembly                 │
  │ Phase Optimize → humanizer → meta-builder → schema-generator → │
  │                  internal-linker → geo-content-optimizer →     │
  │                  4 Quality Gates → Independent Reviewer        │
  └────────────────────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────────────────────┐
  │ chart-render (foreground, runs BEFORE Fork B) — v3.13           │
  │                                                                │
  │ python -m scripts.build.render_data_charts                     │
  │   --task-id {task} --project-slug {slug} --json                │
  │                                                                │
  │ Renders every image slot with kind=="chart" as a REAL labeled  │
  │ chart (title/axes/units/value-labels, brand colors) via        │
  │ data_chart_png.py, and MERGES them into images.json. This is   │
  │ why data slots no longer ship as textless dull AI photos.      │
  └────────────────────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────────────────────┐
  │ FORK B — PHOTO image generation (background, non-blocking)      │
  │                                                                │
  │ python -m scripts.openai.openai_image_pipeline generate        │
  │   --requests-file workspace/{task}/image-prompts.json          │
  │   --workspace workspace/{task} --task-id {task}                │
  │   --mode realtime   # relay primary + official OpenAI fallback  │
  │   # provider chain: scripts/_core/image_provider.py. realtime   │
  │   # is forced (relays have no Batch API). Matches orchestrator. │
  │                                                                │
  │ Generates ONLY kind!="chart" slots (charts handled above), and │
  │ MERGES its photos into images.json (does not clobber charts).  │
  │ Output: workspace/{task}/images.json + workspace/{task}/images/│
  └────────────────────────────────────────────────────────────────┘

  IMAGE-SLOT kind contract (v3.13): every slot in outline.image_slots[] /
  image-prompts.json carries kind: "photo" | "chart". DATA/diagram slots
  (comparison, yield %, PPFD/DLI/CFM, coverage, checklist, verdict matrix,
  spectrum) MUST be kind:"chart" → rendered as real labeled charts, NEVER as
  AI photos (which garble axis/value text — the "图表没字" failure). The COVER /
  featured slot is ALWAYS kind:"photo". Chart numbers come from research.json /
  the article body and are fact-checkable. See agents/image-prompt-designer.md.
  ↓
JOIN: at Phase Publish entry, the orchestrator awaits Fork B if it has not
       finished. With realtime parallel=4 (~150s wall) and Build+Optimize
       (~15–20 min wall), Fork B is almost always done before Fork A.
  ↓
image-visual-qa (LLM stage, MANDATORY — dispatched via
  Agent(subagent_type='xuanran-seo-blog-writer:image-visual-qa')):
  the ONLY stage that actually LOOKS at generated images. Reads every PNG in
  images.json, scores 13 defect classes (P1-P10 photo / C1-C3 chart), rewrites
  prompts and runs targeted regeneration, max 2 rounds:

  ```bash
  # photo slots (QA agent invokes after writing image-qa-regen-requests.json):
  python -m scripts.openai.image_regen_slots \
      --workspace {ws} --requests-file {ws}/image-qa-regen-requests.json \
      --task-id {task_id} --json
  # chart slots (QA agent fixes chart_spec in image-prompts.json first):
  python -m scripts.build.render_data_charts --task-id {task_id} \
      --project-slug {project_slug} --json
  ```

  Output: image-qa-report.json (_generated_by: 'image-visual-qa-subagent').
  Verdict policy: accept_with_warning NEVER blocks publish; pre_publish_gate
  FAILS only on missing report / bad provenance / internally-inconsistent report.
  ↓
Phase Publish (skills/phase-publish/SKILL.md)
  MANDATORY PRE-CHECK (2026-05-26, hard-block):
  ```bash
  python -m scripts.pipeline.pre_publish_gate --workspace {task_id} --json
  # Exit 1 = BLOCKED. Do NOT proceed to wp_publisher.
  # Exit 0 = all mandatory artifacts present, safe to publish.
  ```
  If the gate fails, fix the missing artifacts BEFORE publishing.
  Common failures: images.json missing (Fork B skipped), image-qa-report.json
  missing (image-visual-qa subagent never dispatched), render-lint.json
  missing (render_lint.py never ran). The gate also warns on insufficient
  tables (<2) and missing schema.json.

  Stages: [image-visual-qa (vision QA + regen loop) → image-curator]
          → wordpress-publisher (creates as DRAFT — Rule 5a)
          → schema-injector → preview-URL verification
          ✋ Human checkpoint: confirm "publish" → status flip → live-URL re-verify
          → indexing-notifier (runs AFTER status=publish)
  Output: preview URL (default) OR live URL (if user confirmed publish)
          + change-log.json entry

Phase Monitor (skills/phase-monitor/SKILL.md)
  Register T+7/14/30/90 callbacks for:
    rank-tracker / ai-visibility-tracker / drift-detector /
    content-refresher / performance-reporter
```

### Repair-orchestrator handling under the forked pipeline

If quality gates fail (Phase Optimize) and the article enters the 5-level repair escalation, the image branch is **not** cancelled — its outputs remain valid because image prompts derive from the OUTLINE (which is stable across repair rounds), not from the prose. Only escalation level 5 ("from-scratch — new angle") invalidates images; in that case, kill the Fork B subprocess if still running and re-spawn after the new outline is approved. Levels 1–4 leave images untouched.

### Project-level override

Projects that want the legacy serial ordering (e.g. for deterministic cost-ledger ordering or for `--mode batch` overnight runs where there's no time pressure) can set:

```
projects/{slug}/business-context.json :: image_pipeline_policy.kickoff_timing = "publish"  // legacy
                                                                            | "post_plan"  // default
```

Default is `post_plan`. The project-charlie project as of 2026-05-21 uses `post_plan` + `mode=realtime` for the fastest operator turnaround.

### Rule 4 — Tag taxonomy: per-project policy, default is index-everything for niche / small-scale sites

The 2026 SEO consensus "noindex tags by default" applies to **large sites** (thousands of organically-grown tags, real crawl-budget concerns, empty auto-generated descriptions). It does NOT apply to niche sites at <500-tag scale where every URL is a potential ranking surface and tag descriptions are deliberately curated. The default policy in this plugin matches the niche-site reality: **all tags, categories, and subcategories default to `rank_math_robots: ["index"]`**.

**The policy lives in** `projects/{slug}/tags-config.json :: policy.default_robots`. A project may override this to `["noindex"]` if it grows to a scale where crawl budget matters (typically 500+ tags) — but the default is index for new projects.

**The config has three lists:**

- **`strategic_tags[]`** — tags with curated full-SEO meta: rich description (50–300 words), custom `rank_math_title`, focus keyword, OG/Twitter overrides, axis classification, optional `merge_from_slugs` for consolidating legacy variants. Always indexed. Target 8–15 strategic tags per site.
- **`baseline_tags[]`** — tags that get name + slug + axis + auto-templated description. Indexed by default per `policy.default_robots`. Brand mentions, technical synonyms, axis-fill tags. Distinguished from strategic by NOT having custom title or focus keyword — uses RankMath's global tag template for `<title>` and meta description. Target 20–40 per site.
- **`delete_tags[]`** — tags to remove. Setup script handles retag-then-delete via `force_remove_from_posts: true` if the tag still has posts.

**Tags vs Categories — distinction in this plugin:**

| | Categories | Tags |
|---|---|---|
| Designed when | Once, during `/setup-categories` or `/init` Step 14 | Evolves with each `/article` publish |
| Source of truth | `projects/{slug}/categories-config.json` | `projects/{slug}/tags-config.json` |
| Default robots | `index` (always — categories represent real content silos) | `noindex` (strategic exceptions only) |
| Auto-create on article publish | NO — articles must be assigned to existing categories | YES — new tags can be created from article frontmatter |
| Stability | Stable infrastructure; rarely changes | Grows organically; periodic audit + consolidation |

**Promotion criteria** for a baseline tag to be upgraded to a strategic tag (curated full-SEO):

1. Post count ≥ 3 articles using the tag (signals enough content depth to justify the editorial investment)
2. The tag has a distinct keyword target not already covered by a category or another strategic tag
3. The tag has an axis classification (wattage / technology / crop / stage / certification / scale / region / subsystem / content_angle / brand)
4. The promotion comes with concrete editorial work: write a 50–300 word description, draft a custom `rank_math_title` and focus keyword, define OG/Twitter overrides

Both strategic and baseline tags index; promotion is about content quality, not indexing.

**Article publish flow** (in `scripts/wordpress/wp_publisher.py`):

1. Article frontmatter declares `tags: ["1000W LED", "DLC certification", "Cannabis", ...]` as a list of human-readable tag names
2. `wp_taxonomy.get_or_create_terms()` resolves names → existing tag IDs OR creates new tags with bare name+slug
3. **NEW (post-create hook):** for each resolved tag, `scripts.wordpress.tag_seo_resolver.resolve_tag_seo_spec(slug, tag_name)` consults `tags-config.json`:
   - Match in `strategic_tags[]` (by slug, name, OR `merge_from_slugs[]`) → apply full SEO meta with `rank_math_robots: ["index"]`
   - Match in `baseline_tags[]` → apply description template + `rank_math_robots` per the tag's entry (typically `["index"]`)
   - No match (organic new tag) → apply policy default (`policy.default_robots`, typically `["index"]`) + auto-generated description from template
4. `apply_tag_seo(wp, tag_id, spec, meta_writable)` PATCHes the tag — description always, RankMath meta only if MU plugin v1.2+ is deployed (`bridge_version >= 1.2.0` via `/xuanran/v1/rank-math-bridge`)
5. Article publishes with `tags: [resolved_ids...]`

This ensures every tag a published article touches has correct SEO meta — strategic tags are auto-promoted to indexed, organic tags default to noindex, and the tag archives stay clean even as content scales.

**MU plugin requirement.** Term meta on tags requires `install/wordpress-mu-plugin/xuanran-rank-math-rest-bridge.php` v1.2+ deployed to `wp-content/mu-plugins/`. Without it, descriptions and slugs still apply, but `rank_math_*` meta silently no-ops (POST returns 200 but `meta: []`). The publisher reports `Tag SEO applied: {..., deferred: N}` to surface this state.

**One-time setup + ongoing maintenance.** `scripts/wordpress/setup_tags.py` is the bulk-apply / cleanup tool — run it once to deploy a fresh taxonomy, and re-run periodically (quarterly) to apply config changes and prune empty tags. The article publish flow handles per-article tag SEO automatically via the resolver, so the bulk script is only needed when the `tags-config.json` itself changes.

### Rule 3 — Per-project mandatory H2 sections (project policy overrides format defaults)

Every project may declare a `mandatory_sections` array in `projects/{slug}/business-context.json`. When present, every article published under that project MUST contain every named section as an `<h2>`, regardless of which format template (pillar, listicle, comparison-review, how-to, etc.) the article uses. This is a project-level structural rule that OVERRIDES per-format defaults — a listicle for a project with `mandatory_sections` must produce all of them; a pillar for a project without the policy still defaults to its template's required sections.

**Default 6-section set (the project-charlie pattern, recommended for commercial / buyer-guide / YMYL sites):**

| # | Section ID | H2 matcher (regex) | Position | Spec |
|---|---|---|---|---|
| 1 | `abstract` | `^Abstract($\|:)` | first body H2 | 150-280w, two paragraphs (thesis + persona+structure). NOT a TL;DR blockquote — must be `<h2>`. |
| 2 | `key_takeaways` | `^Key Takeaways$` | after abstract | 4-7 bullets, each ≤20w, each leading with `<strong>` bolded clause |
| 3 | `table_of_contents` | `^Table of Contents$` | after key takeaways | anchored `<ol>` linking every H2; abstract first, references last |
| 4 | `faq` | `^(Frequently Asked Questions\|FAQ\|Common Questions)$` | before conclusion | 6-10 Q&A, aligned to research PAA; feeds FAQPage JSON-LD |
| 5 | `conclusion` | `^(Conclusion\|Final Verdict\|The Bottom Line)( *:.*)?$` | before references | 100-250w synthesis. On cta-enabled projects (business-context.json :: cta.enabled) write NO prose CTA sentence — the mandatory cta-injection stage appends the styled CTA module (two adjacent CTAs read as pressure). Only projects WITHOUT a cta config keep the legacy soft prose CTA. |
| 6 | `references` | `^References$` (with `id="references"`) | last H2 | `<h2 id="references">` + `<ol>` of 8-10 APA-7 entries, link-resolvable |

**How this applies:**
- The outline architect reads `business-context.json :: mandatory_sections` BEFORE drafting the outline, and emits all named sections explicitly. The format template fills in the rest.
- The Format-Fit quality gate runs the regex matchers against the rendered HTML's `<h2>` text and fails closed (hard veto) if any required section is missing.
- The /init flow asks new projects what their mandatory_sections should be (Step 13 question 6). Default suggestion for commercial sites is the full 6.
- Projects without `mandatory_sections` set fall back to the per-format template's defaults (pillar-page.md requires Abstract+Key Takeaways+TOC+FAQ+Conclusion+References; listicle.md has lighter requirements).

**Why per-project rather than per-format:** real-world projects publish across multiple formats but want consistent structural standards across them. A project-charlie comparison-review (listicle format) without a Table of Contents reads differently from a project-charlie pillar with one — that inconsistency hurts the site's information architecture more than a per-format relaxation would help any single article. The 2026-05-20 audit of project-charlie's three live articles surfaced that Post 37090 (comparison-review) was missing TOC and Conclusion while Posts 37063 and 37103 had both — codified the rule project-wide as a result.

Auto-memory: `feedback_mandatory_sections_per_project.md`. Original pillar-only rule documented in `feedback_pillar_must_include_abstract_takeaways_toc.md` is now subsumed by this generalized rule.

### Rule 5 — Competitor/peer domains must never be a cited source (2026-06-20)

A competitor / peer ("同行") website must NEVER appear as a **cited source** — in-text
`(Author, Year)`, the References list, a body outbound link, or JSON-LD `citation`/`sameAs`.
Competitor brand NAMES in comparison prose are fine; only *citing/linking the domain* is blocked.

- Per-project blocklist: `projects/{slug}/business-context.json :: citation_source_policy.do_not_cite_domains`.
  Absent/`exclude_competitor_domains:false`/`enforcement:"off"` ⇒ full no-op (backward compatible).
- DIRECT competitors only — suppliers (Samsung, Mean Well) + standards bodies (DLC, ICNIRP) stay citable. No datasheet exception.
- Sole-source claim whose only source is a competitor ⇒ fact-checker re-sources to a neutral authority; drops the claim only if none exists.
- Enforced end-to-end (single executor `scripts/_core/competitor_domains.py`):
  `tavily_search --exclude` → fact-checker filter → `assemble.py` strip → `linker` →
  schema strip → **chart-source sanitizer** (`render_data_charts` neutralizes
  competitor domains/brands in `chart_spec.source` — the PNG footer is a citation
  surface; added v3.36.0 after two 2026-07-06 chart footers leaked vendor names) →
  render_lint **L11** → CITE **COMP01** hard veto (via `run_quality_gates`, which resolves the slug from `state.json` and forwards `--project-slug` to `cite_scorer`; the wrapper itself takes only `--workspace`) →
  `pre_publish_gate` → `verify_post` **check 28** (live URL). `COMP01` blocks publish.
- Quick check during a run: `python -m scripts._core.competitor_domains --task {tid} --check-url "{url}"` (exit 1 = blocked).

Full reasoning: root `CLAUDE.md` Rule 8 + `docs/superpowers/specs/2026-06-20-competitor-citation-exclusion-design.md`.

## ⚠ Mandatory subagent gate (2026-05-23+) — orthodox pipeline ≠ lint scripts

When intent is `/article` (full pipeline), the orchestrator MUST physically dispatch
the following subagents and write their JSON artifacts to the workspace BEFORE
declaring publish-ready. Lint scripts (render_lint / image_placeholder_check /
keyword_density / mandatory_sections / section_completeness) are necessary but
NOT sufficient. Lint catches mechanical text-pattern defects; it cannot catch:

| What lint cannot catch | Which subagent catches it |
|---|---|
| Broken citation URL (404, paywalled, fabricated path) | `fact-checker` |
| Source-to-claim mismatch (wrong APA title for real DOI) | `fact-checker` |
| Outdated industry spec (DLC v4.0 PPE 2.30 — actual is 2.5 µmol/J since Apr 2025) | `fact-checker` |
| Fabricated product SKUs (Carambola P200 doesn't exist; HLG 600 Diablo doesn't exist) | `fact-checker` |
| In-article spec contradiction (Phlizon FD6500 table says 3yr, narrative says 5yr) | `fact-checker` OR `reviewer` |
| AI-tells, breathless marketing prose, repetitive sentence patterns | `humanizer` |
| E-E-A-T weakness, Perplexity-extractability gaps, missing date stamps | `reviewer` |
| Math errors in tables (DLI lower bound: claimed 11, actual 6.5) | `reviewer` |

The 2026-05-22 5-article project-charlie batch ran lint-only ("orthodox pipeline" was
claimed but the 3 subagents were skipped). Post-hoc reviewer + fact-checker
caught: 1 cross-article DLC PPE error (touched 5 articles × 9 places), 1
Llewellyn Frankenstein citation (touched 5 articles), 4 fabricated products
(Carambola P200, Phlizon FD3000, HLG 600 Diablo, ChilLED X6 720W), 6+ broken
URLs (shared across articles), 12 scaffold-marker leaks, 1 Rodriguez-Morrison
saturation contradiction, multiple spec inconsistencies. None caught by lint.

**Required artifacts in workspace before publish:**
- `memory/workspace/{task}/fact-check.json` with `verdict == CLEAN` (or `CLEAN_WITH_NOTES`). **`FIX_REQUIRED` is an INTERMEDIATE state, NOT publish-ready** — both the orchestrator's fact-check verify-gate AND `pre_publish_gate` block on it (since v3.9.0). Resolve it the SANCTIONED way: fix the draft, then RE-DISPATCH the fact-checker so it re-verifies the edited draft and writes a fresh provenance-stamped `CLEAN`. NEVER hand-edit the verdict field (the provenance check exists to catch that).
- `memory/workspace/{task}/review.json` with `score >= state.brief.quality_target_score` (default 80)
- `memory/workspace/{task}/humanizer-report.json` with `ai_slop_score < 20` (when humanizer ran)

Absence of any of these artifacts when intent=`/article` is a HARD pipeline veto.
The orchestrator cannot self-substitute for these subagents — the fresh-editor
/ independent-fact-checker property is load-bearing. See memory:
`feedback_orchestrator_must_run_quality_gates.md`.

## Cannot proceed past Optimize unless

- `gates.core_eeat.verdict` ∈ {`SHIP`, `FIX`} AND `vetoes_triggered.empty`
- `gates.cite.verdict` ∈ {`SHIP`, `FIX`} AND no `T03/T05/T09`
- `gates.ai_slop.score < 20` — **machine-enforced at TWO layers since v3.38.3** (Rule 12 cure for the 2026-07-09 gold-filament hole where post-humanizer stages regressed ai_slop 16→24 and the stale humanizer-report let it sail): (1) the `quality-gates` runner stage now GATE_FAILs when `quality.json :: passed` is false (quality.json is freshness-enforced vs draft.md, so this is always the FRESH measurement); (2) `pre_publish_gate.check_humanizer` prefers quality.json's ai_slop over humanizer-report.json whenever quality.json is newer. Repair route in both cases: re-dispatch the humanizer on the CURRENT draft, then re-run.
- `gates.independent_review.score >= state.brief.quality_target_score`
- `gates.format_fit.score >= 70`
- `gates.reading_level.within_target`
- **`gates.keyword_density.primary_density_pct <= 1.5`** — soft-gate. Hard veto ONLY above 1.5% (clear over-optimization per Moz 2025 evidence: density above 1.3% costs 4.2 ranking positions on average; above 2% triggers stuffing-spam filters). Computed by `scripts/lint/keyword_density.py` against the assembled draft body. Under-optimization (below 0.4%) is reported as an informational warning, NOT a veto — modern SEO is semantic-driven and Google's BERT/MUM treats `1000W LED grow lamp` and `1000W LED grow light` as equivalent. The asymmetric policy reflects the asymmetric penalty curve: cost of being too low is small (lose 1-3 places); cost of being too high is large (lose 4-10+ places). Target band aimed for during drafting: **0.5-1.0%** (slightly below Moz's 0.8-1.3% optimal band to leave natural-prose headroom). Writers receive `primary_keyword_density_target` in `section_spec` so density is shaped during drafting, not post-fixed. **Machine-enforced since v3.38.3:** `keyword_density.py` writes `passed`/`hard_veto` fields and exits 1 ONLY above the `--hard-max` ceiling (default 1.5%); the runner's `keyword-density-check` stage is now in `_GATE_STAGES`/`_PASS_FLAG_REQUIRED`, so a stuffing case GATE_FAILs while under-band remains a warning (before v3.38.3 the script exited 1 on any out-of-band value and NOTHING read the verdict — the hard veto was Rule-6 dead prose).
- **`gates.mandatory_sections.all_present` is `true`** — for every entry in `projects/{slug}/business-context.json :: mandatory_sections`, the rendered HTML contains an `<h2>` whose text matches the entry's regex. Absence of any required section = hard veto (per Rule 3 above), not a scoring penalty. If `mandatory_sections` is unset for the project, fall back to the format template's per-format requirements (e.g. pillar-page.md requires Abstract + Key Takeaways + TOC + FAQ + Conclusion + References).
- **`gates.references_block.present` is `true`** — i.e. draft body contains an `<h2>References</h2>` (or `<h2 id="references">`) followed by an `<ol>` with ≥3 link-resolvable entries. Absence is a hard veto, not a scoring penalty (caught by `subskills/build/fact-check-and-citation/` if it ran, otherwise enforced by `subskills/publish/wordpress-publisher/` auto-append). The CITE gate's score must be recomputed AFTER the References block exists — scoring the draft without one and calling 84/SHIP is the 2026-05-20 bug.
- **`gates.article_signature.present` is `true` (project-dependent)** — draft body ends with `<p class="article-signature">` paragraph as defined in `projects/{slug}/CLAUDE.md`
- **`gates.render_lint.passed` is `true` (mandatory, 2026-05-21+)** — `scripts/lint/render_lint.py` is run against `memory/workspace/{task_id}/draft.md` after Optimize completes. The script runs the canonical publisher conversion (markdown-it-py with `html=False`) and scans the resulting HTML for FIVE generic leak classes — NOT a hand-curated incident list:
  - **L1** `&lt;tagname` HTML-escape leak inside any `<li> / <p> / <td> / <th> / <figcaption> / <blockquote>` (catches raw `<strong>` / `<em>` / `<span>` left in markdown body)
  - **L2** literal `{#anchor-id}` Pandoc anchor syntax inside any `<h1..h6>` text (catches author-side Pandoc convention drift)
  - **L3** unbalanced `**` markdown-bold markers (odd count → orphan token printed as literal `**`)
  - **L4** hand-rolled srcset variant pattern `<img srcset="...-NNNw.png NNNw">` (the 2026-05-21 Bug 3 family)
  - **L5** unresolved `[claim:cN_section_id]` writer-emitted markers (2026-05-22 — fact-check-and-citation + assembly skipped; should have been swapped to `(Author, Year)`). 2026-05-23 expanded to catch variants: `[claim:c1_1]` (no `s` prefix), `[claim:c5_s4_1]` (extra suffix), `[claim:c1_S2]` (uppercase section).
  - **L6** writer-side scaffold/annotation marker leak — `[ORIGINAL DATA]`, `[UNIQUE INSIGHT]`, `[PERSONAL EXPERIENCE]`, `[CAPSULE]`, etc. (2026-05-23 — caught 12 such leaks in 3/5 articles of the 2026-05-22 batch). These are writer-internal annotations meant to signal info-gain content to fact-checker/reviewer; must be stripped before publish.
  Output: `memory/workspace/{task_id}/render-lint.json` with `passed/defect_count/defects[]/leak_classes[]`. Any defect = hard veto, route to repair-orchestrator. This is a CLASSIFIER, not a pattern allowlist — the next previously-unseen markdown-it leak is caught by the L1/L3 generic detectors automatically.
- **`gates.image_placeholder.passed` is `true` (mandatory, 2026-05-22+)** — `scripts/lint/image_placeholder_check.py` is run against `memory/workspace/{task_id}/draft.md` + `outline.json` after Build. Detects three drift modes the 2026-05-22 audit surfaced from 3 published articles:
  - **D1** `![alt](images/X.png)` local-path markdown image instead of `[IMAGE-SLOT-X]` placeholder. The publisher's `_replace_image_placeholders()` only substitutes the bracket-token form; the markdown-image form ships as a broken-image reference.
  - **D2** count mismatch: outline.json declares N image_slots but body has M ≠ N `[IMAGE-SLOT-…]` placeholders. The 2026-05-22 articles 37252 + 37254 each declared 3 slots but only had the cover placeholder in body, requiring a repair PATCH.
  - **D3** unknown slot_id: body uses `[IMAGE-SLOT-foo]` where `foo` is not declared in outline.image_slots. The publisher cannot route the image and the literal token leaks into rendered body.
  Output: `memory/workspace/{task_id}/image-placeholder-lint.json`. Any defect = hard veto, route to repair-orchestrator.
- **`gates.section_completeness.passed` is `true` (mandatory, 2026-05-23+)** — `scripts/lint/section_completeness_check.py` verifies that `count(memory/workspace/{task}/sections/*.md) == len(outline.sections)`. Catches the writer-subagent silent-dropout class (see `feedback_writer_subagent_silent_dropout.md`): writer agents enter em-dash/density/AI-tells self-correction loops and exhaust token budget BEFORE writing their section file; no error surfaces. 6/50 sections dropped in the 2026-05-22 batch were caught only by manual `ls`. Now automated.
  ```bash
  python -m scripts.lint.section_completeness_check --workspace {task_id} --json
  # exit 0 = all sections present, exit 1 = missing or extra
  # Auto-writes to workspace/{task_id}/section-completeness.json (file-bus)
  ```
  Missing indices → re-dispatch writer subagent for each. Extra indices (files not in outline) → either remove or update outline.
- **`gates.brand_fact.passed` is `true` (mandatory, v3.36.0, 2026-07-06+, no-op for projects without `business-context.company`)** — `scripts/lint/brand_fact_check.py` scans SELF-referential sentences (first-person/brand-name guard) for tenure / team-size / clients-served numbers that contradict `business-context.json :: company` (years_operating / team_size / brands_served). Root cure for the 2026-07-06 batch that fabricated the agency's own tenure three ways in one run ("five years"/"ten years"/"a decade" vs the real 6y) — writer.md's red line covered EXTERNAL sources only, and GEO scoring actively rewards experience phrasing, so self-facts had NO enforcement layer. Runner stage `brand-fact-check` (between locale-spelling-check and local-uniqueness-check) + pre_publish_gate `brand_facts` check. Output: `memory/workspace/{task_id}/brand-fact-lint.json`. Any violation = hard veto, route to repair.
- **`gates.local_uniqueness.passed` is `true` (mandatory, 2026-05-22+, conditional on state.brief.local_mode=true)** — `scripts/lint/local_uniqueness_check.py` enforces Sterling Sky 80/20 anti-doorway uniqueness when local_mode=true. Skipped when local_mode=false. Algorithm: 4-factor composite scorer (entity density 35% + factual-claim density 30% + sibling-article Jaccard 25% + lexical TTR 10%) PLUS Sterling Sky 4-category enforcement (≥1 local programs/incentives + ≥1 case studies/references + ≥1 landmarks/regional + ≥1 pricing/logistics). Composite ≥70 = PASS; 50-69 = WARN (passes with warning); <50 OR missing category = FAIL (hard veto). See `references/local/sterling-sky-80-20-rule.md`. Output: `memory/workspace/{task_id}/local-uniqueness-lint.json`.
  **RUNNER-ENFORCED since 2026-07-01 (v3.33.0):** this gate is a conditional STAGE in the orchestrator table (`local-uniqueness-check`, between keyword-density-check and quality-gates; auto-skipped with a logged `skipped` status when local_mode=false) and a MANDATORY pre_publish_gate check (`local_uniqueness` — FAILs a local article whose lint artifact is missing or failing). Before that fix this paragraph was Rule-6 dead prose — the v3.7 runner migration dropped the stage and it had never executed in production. Manual invocation (the runner does this for you):
  ```bash
  # When state.brief.local_mode=true (bare task-id now resolves like every sibling lint):
  python -m scripts.lint.local_uniqueness_check --workspace {task_id} --json --out {workspace}/local-uniqueness-lint.json
  # Optional --siblings <dir> for cross-article Jaccard comparison against published siblings
  ```

If any fails → `subskills/cross-cutting/repair-orchestrator/` triggered.

## File-bus contract

All inter-stage communication via `memory/workspace/{task_id}/*.json` files conforming to `schemas/*.schema.json`. **No agent communicates via shared context.**

Each artifact validated against schema at write time. Hook `post_tool_use_schema_validate.py` blocks write if invalid.

### Canonical workspace artifact schemas (publisher-compatible)

These are the exact shapes downstream stages (especially `scripts/wordpress/wp_publisher.py`) expect. Produce them in these shapes the first time — the 2026-05-21 task 085fb1ba240c hit four separate publisher rejections because intermediate stages used nested/wrapped variants the publisher couldn't parse.

**`state.json`** — REQUIRED fields (per `schemas/state.schema.json`):

```jsonc
{
  "task_id": "abc123...",            // 8-32 chars, alphanumeric lowercase
  "project_slug": "project-charlie",
  "command": "article",              // ENUM: article|init|audit|refresh|...
  "created_at": "2026-05-21T01:30:00Z",  // ISO-8601 with timezone
  "updated_at": "2026-05-21T03:00:00Z",
  "phase": "publish",                // ENUM: init|research|plan|build|optimize|publish|monitor
  "current_stage": "wordpress-publisher",  // REQUIRED — free-form string per stage
  "brief": { ... },                  // see schema for inner shape
  "project_constraints": { ... }     // free-form per-project
}
```

Missing `current_stage` blocks the schema-validate hook AND blocks the publisher (it calls `file_bus.read_state()` which raises). Always set both `phase` and `current_stage` together.

**`meta.json`** — FLAT schema consumed by publisher. **Do NOT nest under `og:` / `twitter:` / `rank_math_payload:`** — the publisher reads top-level keys only:

```jsonc
{
  "title": "Long human display title — the H1 / WP post title; carries the full thesis + year",
  "slug": "post-slug-here",
  "excerpt": "Short summary (becomes WP excerpt)",

  "seo_title": "...51–60 chars, the indexed <title>...",  // → rank_math_title (+ og:title). MUST share
                                                          // the entity + primary keyword + EVERY number
                                                          // that is in `title` (h1). No (year) suffix here —
                                                          // year goes in `title`. Validated by
                                                          // `python -m scripts.validate.title_validator "{seo_title}" --primary "{kw}" --register {register} --h1 {title}`.
  "register": "b2b_technical",                            // title register: b2b_technical | b2b_procurement |
                                                          // dtc_celebration | dtc_grief | ecommerce | default
  "meta_description": "...max 160 chars...",     // → rank_math_description
  "focus_keyphrase": "primary keyword",          // → rank_math_focus_keyword
  "canonical_url": "https://...",                // → rank_math_canonical_url
  "breadcrumb_title": "Short title",             // → rank_math_breadcrumb_title (optional)
  "pillar_content": true,                        // → rank_math_pillar_content="on"
  "robots": ["index"],                           // → rank_math_robots (NEVER include "follow" — invalid enum)
  "advanced_robots": { "max-image-preview": "large", "max-snippet": "-1" },

  "categories": ["Cat Name 1", "Cat Name 2"],    // list[str] — publisher resolves names→IDs via taxonomy
  "tags": ["Tag 1", "Tag 2"],                    // list[str] — same

  "og_title": "...",                              // FLAT key, NOT og.title
  "og_description": "...",
  "og_image": "https://...",                     // optional (defaults to featured_media)
  "og_image_alt": "...",

  "twitter_card_type": "summary_large_image",     // FLAT key, NOT twitter.card_type
  "twitter_title": "...",
  "twitter_description": "...",
  "twitter_image": "https://...",                 // optional
  "twitter_use_facebook": false                  // if true, twitter inherits og_*
}
```

Fields the publisher does NOT consume directly (safe to include for documentation, but not required): `secondary_keywords`, `format`, `word_count_target`, `reading_time_minutes_est`, `_notes`.

**`citations.json`** — drives BOTH the auto-appended References block AND the in-text `(Author, Year)` citation swap. As of 2026-05-22 the publisher applies `[claim:cN_section]` → `(Author, Year)` replacements before markdown→HTML conversion (defense layer 1 of 3 for the claim-marker leak class; see `feedback_claim_marker_leak_systemic.md`).

Canonical shape (matches `subskills/build/fact-check-and-citation/` output):

```jsonc
{
  "citations": [                      // canonical key (also accepts: refs, items, or top-level list)
    {
      "id": 1,
      "apa_7": "Chandra, S., Lata, H., Khan, I. A., & ElSohly, M. A. (2008). Photosynthetic response of Cannabis sativa L. ... https://...",
      "url": "https://...",
      "url_verified": true,
      "type": "peer_reviewed|industry|standard|government|datasheet",
      "claim_markers_resolved": ["c1_abstract", "c1_ppfd_math", "c1_outgrew_upgrade"]
      //                       ↑ every section-marker the writer agents
      //                         emitted that points at THIS citation.
      //                         The publisher derives the inline-citation
      //                         (Author, Year) from `apa_7`'s leading author
      //                         + the `(YYYY)` parenthesis automatically.
    }
  ],
  "in_text_replacements": [            // optional explicit override; wins over derived
    {"marker": "[claim:c1_abstract]", "replace_with": "(Chandra et al., 2008)"}
  ]
}
```

**The `claim_markers_resolved[]` field is NOT documentation** — it is the field the publisher reads to perform `[claim:cN_S]` → `(Author, Year)` substitution. If writer agents emitted `[claim:c1_abstract]` in a section and the citation that supports that fact does NOT list `c1_abstract` in its `claim_markers_resolved[]`, the marker leaks to live. Either (a) populate `claim_markers_resolved[]` for every citation, or (b) provide an explicit `in_text_replacements[]` override.

The publisher's parser (`_extract_first_author_year`) handles three APA-7 head shapes:
- `'Chandra, S., Lata, H., Khan, I. A., & ElSohly, M. A. (2008).'` → `(Chandra et al., 2008)` (3+ authors)
- `'Mitchell, J. F., & Bugbee, B. (2021).'` → `(Mitchell & Bugbee, 2021)` (2 authors)
- `'DesignLights Consortium. (2023).'` → `(DesignLights Consortium, 2023)` (organization-as-author)

Both `apa` and `apa_7` keys are accepted. Both `refs` and `citations` keys are accepted. Top-level list also works.

**Defense-in-depth** for the claim-marker-leak class of bug — three independent layers, any one of which catches the leak:
- L1 (this stage): `wp_publisher._apply_in_text_citations` runs the marker → `(Author, Year)` swap before markdown→HTML
- L2 pre-publish lint: `scripts/lint/render_lint.py :: detect_L5_claim_marker_leak` — defect class L5 = hard veto
- L3 post-publish verify: `scripts/wordpress/verify_post.py :: check_no_claim_marker_leak` — check 22 = fail-status check on rendered live HTML

**`schema.json`** — custom JSON-LD blocks the publisher's schema-injector appends OUTSIDE the CSS wrapper:

```jsonc
{
  "blocks": [
    { "block_name": "ppf_equivalence_dataset",
      "ld_json": { "@context": "https://schema.org", "@type": "Dataset", ... }
    },
    { "block_name": "howto_electrical_retrofit",
      "ld_json": { "@context": "https://schema.org", "@type": "HowTo", ... }
    }
  ]
}
```

Alt accepted shapes: `{"schemas": [...]}`, `{"jsonld": [...]}`, or top-level list of bare `@context`/`@type` objects. The injector normalizes them all.

**`images.json`** — produced ONLY by the image executors (`render_data_charts` merge, `openai_image_pipeline.write_artifacts`, `real_brand_image_pipeline`, `image_regen_slots`); consumed by publisher + image-visual-qa. Schema-pinned since v3.41.3: `schemas/images.schema.json`. The NINE fields below are the whole contract — there is NO `local_path`/`status`/`kind` key and never was (a 2026-07-19 session read those absent keys via `.get()`, misdiagnosed healthy files as "unpopulated", and hand-patched three manifests). Never hand-author or "reconcile" entries: the `image-pipeline-join` stage now content-gates slot coverage + path existence, and the fix for a genuinely bad manifest is re-running the producing executor. Already in the right shape if you used the canonical pipeline:

```jsonc
[
  { "slot_id": "cover", "path": "...png", "filename": "seo-friendly-stem",
    "alt": "...", "caption": "...", "title": "...", "description": "...",
    "is_featured": true, "source": "realtime|batch" }
]
```

The `filename` field is critical: the publisher uploads with `check_existing_by_filename=True`, so a generic `cover.png` filename will dedup to a stale prior-article media. Always pass the SEO `filename_seed` from `image-prompts.json` through to the local-disk filename — the pipeline does this automatically as of the 2026-05-21 patch.

### Final-mile verification

After `wp_publisher.py` returns success, ALWAYS run:

```bash
python -m scripts.wordpress.verify_post {site_slug} {post_id} \
    --workspace {task_id} \
    --expected-status draft \
    --require-schema-type FAQPage \
    [--require-schema-type Dataset]  [--require-schema-type HowTo]
```

`verify_post.py` uses structural HTML parsing (not string matches) to catch the failure modes that the legacy inline 13-point script missed — including `[IMAGE-SLOT-…]` leaks, markdown-it-escaped References blocks, and stale-media-ID dedup. If `--workspace` is provided, it loads `publish-result.json` from the workspace to enable the stale-dedup cross-reference check (compares image IDs in body against the publisher's reported media_ids — flags any leftover from a prior article's dedup).

## Failure & repair

- Schema validation failure at any stage → halt + report (no silent corruption)
- Repair escalation exhausted (round 5 done) → return best-of-N + repair-report to user
- Never silently downgrade quality target

## Inheritance from active project

When active project exists, `state.brief` inherits defaults from `business-context.json`:
- `industry` ← business-context.industry.primary
- `usage` ← business-context.usage_type
- `target_market_locale` ← business-context.location.languages[0]
  - **Keyword-dialect override (v3.41.3, Rule 1):** when the user-supplied exact
    keyword uses an opposite-dialect spelling (e.g. "search engine optimisation
    consultants" under an en-US project), the keyword stays verbatim in
    title/H1/slug/meta ALWAYS. Set `target_market_locale` to the keyword's
    dialect ONLY when the audience genuinely is that market (UK/AU searcher);
    otherwise keep the project locale — `spelling_dialect_check` now auto-exempts
    inflections of the exact target keyword, so the body no longer needs a
    locale flip just to carry the keyword (the 2026-07-19 batch flipped a whole
    article to en-GB to clear 52 keyword-inflection false drifts).
- `voice_pair` ← business-context.voice_default.pair
- `anchor_links` ← business-context.anchor_links
- CTA module ← business-context.cta (NOT copied into state.brief — the mandatory
  `cta-injection` stage reads it per project at runtime; `brief.cta_target`/`cta_style`
  are deprecated dead fields, see schemas/state.schema.json)

User only needs to supply `keywords`. Everything else is auto-derived.

## See also

- `AGENTS.md` — host-agnostic intent routing
- **`references/style/markdown-authoring-conventions.md`** — global authoring rules every writer agent MUST follow (Rules 1-6: bold, signature, references, anchors, srcset, wp:html escape hatch). Replaces the older per-project drift on these conventions.
- `references/seo/seo-checklist-2026.md` — current best practices
- `references/seo/blog-formats-2026.md` — 24 format catalog
- `references/geo/ai-engine-matrix.md` — per-engine optimization weights
- `scripts/lint/render_lint.py` — pre-publish leak classifier (gates.render_lint.passed); enforces the conventions above
- `scripts/wordpress/verify_post.py` — post-publish 19-check structural verifier (checks 06, 19, 20, 21 mirror the lint classes)
- `../SKILL-ARCHITECTURE-V3.md` — full design doc
- `../EXECUTION-PLAN-V3.2.md` — build plan
