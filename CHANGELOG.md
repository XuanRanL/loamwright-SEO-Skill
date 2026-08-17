# Changelog

## [3.42.17] - 2026-08-17 (default images per article 4 → 6, ceiling → 8, count owned by one module)

Operator decision: raise the per-article image default to 6 (1 cover + 5 section
images ≈ one visual anchor per ~900 words on a 5,000-word piece; ≈$1.67/image at 4K,
so image cost moves ≈$6.7 → ≈$10/article) and the ceiling to 8 for briefs that
explicitly want more. Applying it surfaced the same disease as the same-day
review-target fix: "4" was spelled independently in the schema annotation, the
image-prompt-designer dispatch_prompt ("design 4 image prompts"), both designer
instruction layers, the slot-allocator doc, phase-publish, the generator's cost
math, and the cost estimator's per-format rows.

### Changed

- **`scripts/_core/image_policy.py` (new)** owns `DEFAULT_IMAGE_COUNT = 6` /
  `MAX_IMAGE_COUNT = 8` / `resolve_image_count()` (absent/garbage → default;
  **0 stays a real value** — a text-only article is an explicit choice; above-max
  clamps). Schema annotation corrected and PINNED (`tests/test_image_count_policy.py`,
  watched RED against a reverted default).
- **Dispatch prompts are now count-parameterized:** `_render_dispatch_prompt` gains
  `{image_count}` / `{inline_image_count}` placeholders; the image-prompt-designer
  Stage template uses them, and a wiring pin fails if a literal "design N image
  prompts" ever reappears. The count-consuming layers that were already
  count-agnostic (outline-architect's `image_count − 1` rule, verify_post's
  adapt-from-images.json, image-visual-qa, the pipelines) needed no change.
- **Cost estimator rows that mirrored the old default now import the constant**
  (pinned); the deliberate short-format rows (news-analysis 2 / faq-knowledge 2 /
  shortlist-validation 3) stay, with a new caveat comment + batch-article SKILL
  note: generation follows the BRIEF, not the format — short formats should set an
  explicit lower `image_count` or their real cost tracks the default.
- Doc fan-out updated in the same pass (Rule 11): agents/image-prompt-designer.md,
  agents/image-curator.md, both image subskills, outline-architect example,
  phase-publish stage sketch + cost line, openai-image-generator cost math,
  batch-article brief guidance.
- The agent-frontmatter YAML guard (v3.42.12) caught a colon this pass introduced
  into an unquoted description mid-edit — fixed before commit; the guard fired
  exactly as designed.

## [3.42.16] - 2026-08-17 (the duplicated-CTA incident, the reviewer target with four spellings, and the flip that had no executor)

Everything here came out of one real 3-article batch (all 46 stages ran, all gates green,
all three posts verified 24/24) plus a three-agent deep audit of the run, the last five
releases, and the wiring. The batch's one live defect and the audit's structural findings
are each root-cured with a regression test driven RED on the unfixed code where feasible.

### Fixed

- **A live draft shipped with the same CTA twice, and every gate stayed green.** Chain: a
  reviewer would-change proposed renaming the injected CTA H3 (it only knew example
  headings, not the registered `cta-draft.json` heading); an operator executed the rename
  mid-repair; the driver's re-run then found no cta-classified heading (the injector's
  idempotency is classification-based — the v3.38.0 skin-miss cure could not see a heading
  that classifies as NOTHING) and injected a second identical paragraph + `[products]`
  shortcode; check 29 and visual-density count only tagged/classified blocks, so the
  duplicate was invisible to both. Three-layer cure, each direction tested
  (`tests/test_cta_duplicate_content_guard.py`, the injector test watched RED via stash):
  (1) `cta_injector` gains a CONTENT-IDENTITY idempotency layer — a renamed copy blocks
  injection and fails the stage with the sanctioned repair path, in inject AND `--check`
  modes; (2) `verify_post` check 30 detects duplicated CTA copy on the rendered page;
  (3) `pre_publish_gate.check_gate_freshness` now FAILS (was WARN) when draft.md is newer
  than review.json — the reviewer is the last content stage, so a draft newer than its
  review is by definition unreviewed; fact-check/humanizer/quality staleness stays WARN
  (later optimize stages legitimately edit after them). The shipped duplicate itself was
  repaired, re-published, re-verified (25 checks incl. the new 30), and freshly re-reviewed.
- **The reviewer score target had four spellings and the wrong one was load-bearing.**
  `schemas/state.schema.json` annotated `default: 95` (nothing applies schema defaults at
  runtime — a pure lie), both gates carried their own `or 80` literal, SKILL.md said 80,
  and a batch bootstrap trusted the schema: six reviewer/repair rounds burned against a bar
  no code enforces, on content every round called clean. Now `scripts/_core/review_target.py`
  owns `DEFAULT_REVIEW_TARGET = 80`; both gates import it; the schema annotation is
  corrected and PINNED to the constant by `tests/test_review_target_single_source.py`
  (watched RED against the drift), with seam tests driving `next_stage()` on an
  absent-field brief. batch-article SKILL.md now says: omit the field unless the operator
  explicitly wants a stricter bar, and correct a mis-set target via `update_state` + a
  batch-queue note — never silently, never via review.json.
- **The draft→publish flip had three duplicated checklists and zero executors.** The
  PATCH → live re-verify → indexing re-run procedure lived as prose in phase-publish,
  weekly-digest, and seo-blog SKILL.md, and nothing could verify the post-flip indexing
  re-run ever happened (the wired v3.42.12 notifier correctly records `skipped_draft`
  in-pipeline, so on a draft-first project the SUBMITTING run only exists post-flip).
  `scripts/wordpress/flip_post_live.py` now owns the sequence with a pinned exit-code
  contract (0 flipped+verified+submitted / 2 flipped+verified but NOT submitted / 1 not
  done), writes `flip-result.json` + `verify-live-result.json` (draft-phase
  `verify-result.json` is pipeline history, deliberately preserved), and the three
  checklists now invoke it (`tests/test_flip_post_live.py`).
- **`pipeline_checklist.py` claimed to be an enforcement layer; it enforces nothing.** No
  production path ever imported it or ran its CLI (live enforcement is
  `_PASS_FLAG_REQUIRED` + `_GATE_STAGES` + `_content_gate_reason`), and its hand-maintained
  `MANDATORY_STAGES` had drifted (missing chart-render / chart-rerender / stat-grid-check).
  Its stage lists are now DERIVED from the orchestrator's Stage table and its docstring
  states honestly what it is: a standalone diagnostic audit CLI.
- **Reviewer CTA guard now names the source of truth, not examples.** Both layers
  (dispatch_prompt + `agents/reviewer.md`, Rule 11) instruct reading
  `cta-draft.json :: blocks[*].heading` for THIS draft's machine-owned headings — the
  example-list guard is what let "One more thing" get a rename proposal.
- **`AGENTS.md` routed `/rewrite` to a nonexistent skill** (`optimize/content-refresher` —
  the real one is `cross-cutting/rewrite`) **and advertised three phantom features**
  (`/context`, `/alerts`, `/skillify` → subskill dirs that never existed). Repointed / removed.
- **fact-checker agent file lacked the dispatch_prompt's References/signature guard**
  (Rule 11 point 2): out-of-band invocations could hand-build a draft References block that
  `finalize-references-signature` exists to own. The counter-rule now lives in the agent file.
- **`check_mu_plugin_drift`'s `requires=None` branch is now red-watched**
  (`test_always_applicable_bridge_absence_is_not_deployed_never_not_applicable`): an
  always-applicable bridge (page-schema) whose file is missing must surface as
  `not_deployed` drift, never `not_applicable` — the pre-`requires` bug filed exactly that
  as "in sync" (project-juliet, day one of page-schema).
- **`provenance.exit_code()`'s severity ladder is pinned** (`tests/test_provenance_exit_codes.py`)
  — it had one live run and zero tests.
- Cosmetics with teeth: parked editor-in-chief's phantom cost row removed from
  `cost_estimator` (inflated every estimate); verify-post stage description no longer
  hardcodes a check count (went stale twice); `file_bus` docstring stops implying
  `.history/` snapshots happen automatically (nothing calls `snapshot_history()` — the
  dual-repair forensics had no trail for exactly that reason).

### Added

- **`install/wordpress-mu-plugin/xuanran-page-schema.php` (v1.0.2)** — page-level schema
  correction on the free RankMath tier via the `rank_math/json_ld` filter: drops the
  Article/#richSnippet node on pages, refines WebPage → AboutPage/ContactPage/etc. from a
  filterable slug map, exposes `/xuanran/v1/page-schema` health endpoint so
  `check_mu_plugin_drift` can see the deployed version (Rule 13 by design). Deployed
  fleet-wide 08-15 (12 of 13 hosts; project-juliet has no file-write channel and now
  honestly reports `not_deployed`). The drift checker's `BRIDGES` gained the fourth
  `requires` element this plugin needed.

### Process notes (from the batch + audit, recorded for the next operator)

- One batch, one operator per task: the duplicated CTA was minted by a parent session and a
  resumed background driver repairing the same workspace concurrently — codified in
  batch-article SKILL.md ("One operator per task").
- The IndexNow key remains unminted: every `indexing-notifier` run fleet-wide records
  `no_credentials`. The wiring is honest; the feature submits nothing until the key is
  minted and hosted per site. Operator action, tracked as the one open infra item.

## [3.42.15] - 2026-08-12 (two more checks that could not fail, found by running a real batch through them)

Both were found producing a 3-article project-alpha batch, not by reading code and not against
fixtures. Both are the 3.42.14 disease one layer over: a rule whose enforcement lived in one
place while a second place kept the old shape (Rule 11). Each fix has a regression test
watched RED on the unfixed code, and the second fix's own guard test caught the first attempt
at it over-matching.

### Fixed

- **The batch per-article cost guard could not run for 17 of 27 formats.** The batch-article
  workflow documents `cost_estimator --format {fmt}` as its pre-flight cap check, but the
  CLI's `choices=` was `FORMAT_PARAMS.keys()` — a hand-maintained COST-MODEL table, not the
  format list — so a real format (`problem-solution`, `buyers-guide`, `multi-intent-hybrid`,
  ...) exited 2 with `invalid choice`. This is the v3.41.4 batch_queue bug in a second file,
  and it survived because that fix read the schema in ONE place only. Both readers now share
  `scripts/_core/format_registry.py`. `estimate_article` still falls back to the default cost
  profile for an uncalibrated format, but now says so on stderr instead of presenting a
  default-derived number as calibration.
- **`markdown_structure_check` could not find a conclusion written the way this plugin
  mandates.** Every project CLAUDE.md instructs writers to open the conclusion with
  `Conclusion:`, `The Bottom Line:` or `Final Verdict:`, and section coverage prefix-matched
  the alias `bottom line` — so the leading article in "The Bottom Line: ..." made two of the
  three mandated forms unmatchable, and the lint reported a missing conclusion on drafts that
  had followed the rule exactly. Third instance of this matcher disease in this one file
  (after the `{#anchor}` suffix bug and the exact-set-vs-prefix bug), and
  `anchor_link_builder._TOC_EXCLUSION_WHITELIST` already whitelisted "the bottom line", so two
  layers disagreed about the same fact. Matching now strips a leading article, but only for
  multi-word aliases or an exact whole-heading match, so the generic single-word alias
  `verdict` still cannot swallow "A Verdict Is Not a Diagnosis Yet". The first attempt DID
  over-match on exactly that string and its own guard test failed it.

Suite: 1925 passed, 1 skipped. Executors: test_quality_check 196 files OK,
contract_fanout_check OK, hop3 registry 80 passed.

## [3.42.14] - 2026-08-12 (the ten inert checks, cleared: every verifier can now fail for the reason it exists)

Clears the full inert-check backlog from the 2026-08-12 release audit (items ranked by
blast radius in that audit; three had already shipped in 3.42.11/12). Every behavioural
fix carries a regression test watched RED on the unfixed code, and each new gate was
driven in BOTH directions (a check hardwired to pass fails one scenario, hardwired to
fail fails another).

### Fixed

- **`deploy_blog_sidebars --check` exited 0 on `not_deployed`** — the mu-plugin absent on
  the host with transport verified, its own motivating scenario, plus `manual`,
  `not_generated`, and ANY unanticipated status. Root cause: a BLOCKLIST of bad states,
  so every state it did not enumerate read as success. Inverted to an allowlist
  (`resolve_exit`): 0 only when every result is verified `in_sync`. The hop3 registry
  gate now pins all formerly-green statuses plus an `unknown` probe.
- **The CTA `resolution_failed` sentinel finally has readers.** A failing brief (project
  SELLS things, catalog unreachable) let `next_stage()` report PIPELINE_COMPLETE, masking
  the failure as "nothing to do". Now a content-gate failure in the shared
  `_content_gate_reason` helper (both completion paths see it — the v3.35.3 lesson) and a
  `run_pipeline._GATE_STAGES` entry (GATE_FAILED, route-to-repair). `skipped_no_config`
  still auto-skips for the 5 no-CTA projects. The old regression test imported the
  orchestrator and never used it; replaced with 5 real seam tests including the happy path.
- **`tavily_pool` unreadable payloads no longer read as exhaustion.** `int(raw or 0)`
  turned `''`/`[]`/`False` into balance 0 → persistent "exhausted" marking (the exact
  v3.42.5 bug class surviving its own fix). New `_coerce_credit()`: bools and non-numeric
  values are UNKNOWN (no balance write); numeric strings, including a real `"0"`, still
  count. 20 tests either direction.
- **Common Crawl trio**: a 404'd crawl-id no longer reports a stale `scanned_to_rank`
  from a prior scan ("source unavailable" and "not in scanned ranks" are now distinct
  verdicts — Rule 12/13); `main()` no longer crashes on its own success path printing
  three deleted dataclass fields; `agents/audit-backlinks.md` now documents the REAL
  CLIs (its previous `--domain`/`--urls` flags never existed, so both "revived" tier-0
  backlink sources were dead in production — the sole caller could not invoke them).
- **`render_probe --check` can now fail.** "No headed samples" was reported as "headless
  agrees with headed"; unmeasured is now a distinct tri-state (`None`), `--check` refuses
  to certify unmeasured selectors, and the module went from zero tests to a
  three-direction gate.
- **`restyle_posts` leak signal is visible and covers the right family.** The detector
  matched only `xr-*` classes while the motivating incident was the
  `{slug}-pillar`/`article-signature` family (`style_tokens.LEGACY_SPECIAL`); the count
  was invisible in default output and an absent key read as clean. Now: full family +
  wrapper detection, `wrapper_check` tri-state (`checked` / `not_tokenized` /
  `skipped_no_slug` — unknown never folds into 0), printed in default output, `--check`
  exits non-zero on leaks.
- **`check_post_drift._norm_sig` is pinned.** Reverting it to `t.lower()` previously left
  all 27 tests green; now 5 new/rewritten tests (including the `audit .` artifact INSIDE
  the compared clause, and a permanent revert-trap) go red on exactly that revert.
- **C10 and `paa_alignment_check` count the same questions.** paa filtered non-questions;
  C10 did not (measured 6 vs 3 on one FAQ — bold lead-ins counted as questions), and the
  guard test re-typed paa's expression instead of calling it. One shared
  `scripts/_core/faq_questions.py :: extract_faq_questions()`, both callers delegate, the
  guard drives both production entry points on 4 fixture shapes, and both counters return
  5 on the real 2026-08-12 digest draft.
- **`heading_anchor` is now actually the one source.** 10 private copies of the anchor
  regex (4 on a divergent variant) replaced with compositions of exported fragments; a
  registry test greps `scripts/**` and fails on any new private copy outside the
  allowlist, with a stale-entry trap. One copy remains in `markdown_structure_check.py`
  (held by a concurrent session; its allowlist entry self-expires on consolidation).
- **Ghost executors exorcised.** 12 audit agent files invoked 8 modules that do not exist
  (or exist under other names/flags): each now documents either the REAL module + REAL
  argparse (verified by parsing) or the honest absence of an executor with the manual
  procedure. `hooks/post_tool_use_progress.py` deleted — never registered in hooks.json,
  its trigger cannot fire under the v3.7+ runner, its role is served by `/status`. New
  `tests/test_audit_doc_invocations.py` walks the audit instruction layer and fails on
  any future ghost module, ghost flag, or unregistered hook.

Suite: 1925 passed, 1 skipped. Executors: test_quality_check 196 files OK,
contract_fanout_check OK, hop3 registry 84 passed.

## [3.42.13] - 2026-08-12 (self-audit of 3.42.11/12: the follow-up close was a silent no-op — the fix's own test used the imagined shape)

Adversarial re-audit of this session's own two releases, applying the same standard they
were shipped under. One real defect found, one Rule 11 fan-out miss, both cured.

### Fixed

- **`close_published_followups` never closed anything in production.** It read
  `fu["head"]["url"]` — the CLUSTER shape — while `_emit_followups` emits digest-item shape
  (`canonical_source.url`, no `head` key at all). `closed` was always empty, the function
  returned rows unchanged, and the v3.42.11 "published follow-ups can no longer recycle"
  guarantee was a silent no-op. Its test passed because the fixture hand-built the imagined
  shape — the exact "fixtures prove shape, production proves contract" failure, in a commit
  that quoted that rule. `dedup_followups`, five lines above, had been reading the correct
  key all along. Proven live: 0 rows changed before, 3 after, on the real loamwright
  ledger. The `_followup` test fixture now DRIVES `_emit_followups` itself (a future shape
  change breaks the tests instead of no-opping), and a new lifecycle seam test covers
  emit → budget → close → next-week-emit end-to-end. No ledger repair needed: the 08-12
  issue published zero follow-ups (hand-curated all-fresh), so its `developing` rows are
  legitimately still eligible.
- **Rule 11 fan-out miss from v3.42.11:** `subskills/research/industry-news-monitor/
  SKILL.md` still taught `project_terms = content_strategy.primary_clusters` — the exact
  retired contract. Now documents `_digest_relevance_terms` (relevance_terms-first), the
  follow-up cap, and the close.

### Verified (no change needed)

- Cost attribution works at the live seam: production rows written after the v3.42.11 fix
  carry `project_slug` (a concurrent project-alpha pipeline's calls attribute correctly via the
  env-pin), and `fleet_view._site_cost_30d("project-alpha")` reads non-zero for the first time.
  Historical rows stay unattributed (most lack a mappable task_id; partial backfill is a
  separate data-migration decision).
- `_drop_excluded` receives the FULL catalog category list (parents included), so the
  ancestor walk has its tree; `digest_artifacts.main()` loads and passes `bc`;
  `max_followups_per_issue` reads from the `weekly_digest` block; skill/project separation
  holds (zero slug-conditionals in any file this session touched);
  `business-context.schema.json` is permissive, so the new project keys cannot be rejected
  (the `weekly_digest` block having no schema at all is a pre-existing known gap).

## [3.42.12] - 2026-08-12 (indexing-notifier wired after months as doc-only; digest pre-write made visible; the verifiers that could not fail, fixed)

Second half of the 2026-08-12 audit (first half shipped as 3.42.11). Theme: Rule 6/14 —
executors that existed only as documentation, and checks that could not fail for the
reason they exist. Every behavioural fix carries a regression test watched RED first.

### Added

- **`indexing-notifier` is now a real pipeline stage** (`scripts/publish/indexing_notify.py`,
  runs after `verify-post`). The subskill claimed "triggered as final step of phase-publish"
  for months while the STAGES table ended at `verify-post`; the only caller of the
  fully-implemented `indexnow_submit.py` was the dead `agents/publisher.md`, so no article
  this pipeline published was ever submitted to IndexNow. Contract: NOTIFIER, not gate —
  drafts record `skipped_draft` (Rule 5a; the post-flip re-run in the publish-confirmation
  flows is the one that submits), and submit/transport failures record distinct honest
  outcomes (`no_credentials` / `transport_error` / `submit_failed` — Rule 13) without
  blocking a pipeline whose article already verified. GSC URL-inspection stays a documented
  manual step (per-site OAuth, strict quotas, 13-site fleet). The first live run caught its
  own classifier matching an imagined error message instead of the real one; fixed and
  pinned to the message credential_hub actually produces. NOTE: no IndexNow key is
  configured yet — every run records `no_credentials` until one is minted and hosted.
- **`scripts/_core/provenance.py --check`**: workspace provenance scan with distinct exit
  codes (clean / unknown / script-prewritten / unstamped). The weekly-digest pre-writer's
  artifacts auto-satisfied `outline-architect` and `image-prompt-designer` in 3 ms without
  either agent running — invisible until now.

### Fixed

- **The digest `## Abstract` stub**: `digest_artifacts.compose_abstract()` composes a real
  60-90-word paragraph from the items' extract-verified summaries (ranked order, sentence-
  splitter tolerant of abbreviations, L12-safe). Previously `abstract_seed` was the raw
  `theme_of_week` headline, shipped verbatim by assemble — the published 2026-08-12 Abstract
  was six words, flagged by the reviewer as its #1 defect.
- **The digest cover's missing negative prompt** (root cause of a third-party logo rendering
  into the cover 3 consecutive weeks, ~$1.67 regen each): `build_image_prompts` now accepts
  the project config and layers `brand-guideline.yaml :: negative_prompt_baseline` verbatim
  + a format-level third-party-marks ban (incl. reflections/shadows) + the platforms this
  issue actually names, derived from `items[].entities` — no hardcoded list to go stale.
  Verified live: `openai_image_pipeline._adapt_entry` appends it as `AVOID:`.
- **Agent tool-isolation test regexed raw text instead of parsing YAML**: an agent whose
  frontmatter failed `yaml.safe_load` ran with ALL TOOLS while the test stayed green —
  `agents/visual-designer.md` (which edits draft.md in place) was live in exactly that
  state, and `agents/humanizer.md` carried the same defect. Both frontmatters fixed (quoted
  description scalar); the test now parses like the runtime and is proven able to fail.
- **`contract_fanout_check` scope**: now scans `projects/**/*.md` + recursive
  `references/**` (advisory bucket; `--include-projects` gates on it) with a usage-anchored
  `{slug}-pillar` pattern — 25 true positives it was blind to, 0 false positives. The one
  shipped-layer hit (`references/style/markdown-authoring-conventions.md` still teaching the
  pre-token wrapper class) is cured in this release.
- **hop3 registry gate was a grep** (`'"--check"' in src` passes on a no-op flag): it now
  drives all 8 executors' real `main()` with synthetic in-sync/drifted/unreadable reports
  and asserts exit codes in both directions; sabotage runs prove the old gate passed a
  no-op check the new one catches. The permanently-skipped "unguarded surfaces state why"
  test is now live.
- Canonical-stage fixture updated for the new stage; the stale `verify_backlinks`-era
  claim "CI: GitHub Actions on every commit" in CLAUDE.md corrected — there is no `.github/`
  directory; the real enforcement is the documented hand-run suite + Rule-14 executors.

### Changed

- **Dead agents tombstoned, not wired** (operator decision): `editor-in-chief` and
  `seo-auditor` PARKED — `reviewer` + the deterministic gates absorbed their roles, and a
  5th overlapping LLM gate adds cost without a distinct catch-rate; `publisher`,
  `image-curator`, `schema-validator` marked SUPERSEDED with what absorbed them and which
  gaps remain real (`alt_text_polisher` and `image_metadata.json` have no callers; the
  `/validate-schema` command never existed). Two false "used by" claims in the reference
  layer corrected. Leftover: the stale `editor-in-chief` cost row in `cost_estimator.py`
  (file held by a concurrent session; remove on next touch).

## [3.42.11] - 2026-08-12 (digest ranker fed the wrong vocabulary; CTA exclusion now inherits; cost attribution restored)

Post-publish audit of the 2026-08-12 loamwright weekly digest. The issue itself shipped
clean (reviewer 90/100, CORE-EEAT 81.25 — a series best, 24/24 live verification), but the
audit found four defects behind it, three of which had been silently degrading every prior
issue. Every fix below carries a regression test that was watched RED on the pre-fix code
(`tests/test_audit_fixes_2026_08_12.py` — Rule 14); 16 of the 21 failed before the fixes.

### Fixed

- **Digest relevance was scored against service-line labels, not news vocabulary.**
  `industry_news_runner` fed `content_strategy.primary_clusters` — what an agency *sells*
  ("Technical SEO", "Local SEO") — into the news-relevance scorer. On the seven
  hand-curated items of the 2026-08-12 issue, **6 of 7 scored 0.0**, the "definitely
  off-topic, worse than unknown" verdict, making the 0.20 relevance weight
  *anti-correlated* rather than merely dead and leaving recency the only live signal.
  That is the root cause of five consecutive issues needing full hand-curation.
  The scorer's arithmetic is unchanged and still correct — a lone common word must not
  match a two-word term. New `_digest_relevance_terms()` prefers
  `weekly_digest.relevance_terms` and falls back to `primary_clusters`. With loamwright's
  new 35-term news vocabulary the same items score 1.000 (6 of 7) while an off-topic
  bakery story still scores 0.0.

- **Continuing stories had first claim on the whole issue budget.** `resolve_issue_budget`
  capped follow-ups only at `items_per_issue`, and they were never ranked against a fresh
  item (`_emit_followups` hardcodes an empty summary and 0.5 significance). Three stale
  entries took 3 of 7 slots on 2026-08-12. Now capped by
  `weekly_digest.max_followups_per_issue` (default 2), with at least one fresh slot always
  reserved — which also closes the `keep == 0` hole that let a follow-up own
  `theme_of_week` despite both SKILL layers promising it cannot.

- **A published follow-up was never closed.** `build_covered_update` records only fresh
  clusters, so a story published *as* a continuing story kept `status: "developing"` and
  was re-emitted every week until it aged out. The same three entries ran on 08-06 and
  08-12 and would have run again on 08-19. New `close_published_followups()` flips them to
  `reported`; genuinely new developments re-enter via `resolve_recurrences` on a fresh URL.

- **CTA category exclusion did not inherit down the category tree (compliance).**
  `_drop_excluded` matched a category's own slug/name only, so excluding a parent excluded
  nothing and Rx children had to be enumerated by hand. That enumeration went stale:
  `spot-on-systemic` (a child of Prescription, holding a prescription-only product) was
  excluded in `blog_sidebars.excluded_product_categories` but not in
  `conversion_offers.excluded_categories`, leaving it CTA-merchandisable from editorial
  content — the site's own audit CRIT-1 defect. Exclusion now walks ancestors, so a future
  Rx child is blocked the day it is added, with no config edit.

- **`/fleet` reported $0.00 spend for every site.** `cost_ledger.log()` has always accepted
  `project_slug`, and all eight production call sites omitted it, so 7,108 of 7,112 ledger
  rows carried `project_slug: null` while `fleet_view._site_cost_30d` filters on exactly
  that field. Three months and $873.99 of real logged spend were attributed to nothing, and
  the "High spend (>$100)" health alert could never fire. `log()` now defaults the field to
  the active project (env-first, Rule 7), so parallel sessions attribute to their own
  project. The only prior test set it in a fixture — proving the plumbing while production
  never populated it (Rule 10: the helper was tested, the seam was not).

### Changed

- `projects/loamwright/business-context.json`: added `weekly_digest.relevance_terms` (35
  news-topic phrases) and `max_followups_per_issue: 2`.
- `skills/weekly-digest/SKILL.md`: Step 4b now documents the term-source contract and the
  follow-up cap. Hand-curation remains mandatory — these fixes improve the ranking inputs,
  they do not replace editorial judgment.

## [3.42.10] - 2026-08-10 (backlink data sources revived: inverted SSRF guard, retired Common Crawl path, single-frame render verdicts)

The 2026-08-06 website audit surfaced that BOTH free tier-0 backlink data sources had
been inert since the day they were written, and that single-screenshot visual audits
can ship false "critical" findings. Every fix below carries a regression test that
fails on the pre-fix code (tests/test_audit_backlink_sources_are_live.py — Rule 14).

### Fixed — verify_backlinks marked every valid URL "blocked" (SSRF-guard contract read inverted)

`ssrf_guard.validate_url()` returns a truthy `ValidatedURL` on success and RAISES
`SSRFError` on failure. `verify_backlinks.py` read the return value as an error
indicator (`err = validate_url(...); if err: blocked`), which inverts the check
completely: every valid backlink was refused, so the module had never verified a
single link — and genuinely unsafe URLs escaped as uncaught exceptions instead of
being blocked. The raise/return contract is now encapsulated in `_check_ssrf()`, and
the website-audit SKILL.md snippet that seeded the inverted reading is corrected with
an explicit warning.

### Fixed — commoncrawl_graph built URLs that 404 for every domain on earth

Common Crawl retired the per-month `{crawl}/host-level/vertices.txt.gz` layout; the
webgraph is published QUARTERLY at `{crawl}/domain/{crawl}-domain-ranks.txt.gz`, keyed
by REVERSED domain (`example.com` → `com.example`), so the module reported "not found"
for every domain — indistinguishable from a real miss (Rule 12's shape: a dead source
must never read as a content verdict). The rewrite also cures four secondary defects
found on the way in:

- **O(n²) decompression**: the old loop re-inflated the whole accumulated buffer on
  every 64 KB chunk and never completed on a multi-GB file; now a single incremental
  `zlib.decompressobj` streams line-by-line and stops the moment the target is found.
- **Shallow-cache poisoning**: a cache built from a 1 MB scan answered "not found" to
  every later request regardless of its budget. Cache entries now record their scan
  depth, and a deeper request re-scans instead of trusting a shallower cache.
- **`--max-download-mb` had no reader** (Rule 14.4): the flag now genuinely bounds the
  scan, and a not-found result reports `scanned_to_rank` so "not in the portion
  scanned" is never phrased as "not in the graph".
- **`_estimate_pagerank` deleted**: it assumed harmonic centrality in 0.0001–1.0; the
  quarterly table reports HC in the ~1e5–3e7 range, so the estimate saturated at 100
  for every domain. The table publishes real PageRank values and ranks — no estimate
  needed.

### Added — render_probe: what a crawler sees vs what a human sees, over time

Two "critical" findings on the 2026-08-06 audit were wrong the same way: a single
headless screenshot caught the frame BEFORE a slow entrance animation and was read as
the page's final state. `scripts/audit/render_probe.py` samples selector text at
0.5/1/2/4/8s across three passes — static (no JS: the text-extraction/AI-crawler
audience), headless, and headed (the human ground truth) — and `--check` exits
non-zero when headless and headed disagree, i.e. when any headless-derived finding
would be unsafe to publish. A static fetch that cannot be read (403/WAF) is reported
as `static_unavailable`, never as empty. The website-audit SKILL.md now forbids rating
any "does not render / shows zero / is blank" finding above `medium` from a single
screenshot.

### Changed — website-audit SKILL.md operational contracts

- All audit outputs go under `Website Audit/seo-audit-{domain}-{date}/`, not the repo
  root (violated once on 2026-08-06; cost a 149 MB directory move).
- Client-facing HTML reports carry mandatory Loamwright SEO (沃匠 SEO) branding — brand
  facts read from `projects/loamwright/business-context.json` at generation time, never
  from memory.

### Release hygiene

- `OPENSOURCE-SANITIZE-MAP.json` gains a domain alias + verify term for the 2026-08-06
  audit target, and the two incidental docstring examples that named it now use
  `example.com`. `cc_cache/` (Common Crawl quarterly downloads, ~75 MB each) is
  gitignored.
- The release secret scan excludes trufflehog's Lob detector (and nothing else): Lob
  keys are `test_` + 35 chars, so pytest filenames in CHANGELOG prose match the
  pattern, and Lob's test API "verifies" them — a permanent false positive blocking
  every future release. Detector-scoped, not path-scoped, so CHANGELOG stays covered
  by every other detector.

## [3.42.9] - 2026-08-08 (three executors caught by their own outputs: tagger swallow, TOC whitelist, restyle token-blindness)

A 3-article project-alpha batch (bulldog-health: 38031/38037/38044, all drafts) ran the full
45-stage pipeline; every stage executed, all gates passed with real verdicts, all three
verified 24/24. Along the way three latent defects surfaced, each caught by a check doing
its job against REAL output rather than fixtures, and each root-cured with a
red-then-green regression test.

### Fixed — component tagger's regex backtracked across the document and swallowed headings

`tag_component_blocks` (scripts/_core/component_headings.py) used a bare DOTALL `(.*?)`
for heading inner text. When a heading's immediate sibling was not in (ul|ol|p|table) —
e.g. `<h2>Red Flags…</h2><blockquote>` — the engine backtracked the "heading text" past
the heading's own closing tag to the NEXT same-level close, and that giant span consumed
every heading inside it. Any registered component inside such a span shipped untagged.

Caught by live verify check 29 on the batch's article 2: its CTA `<p>` reached WordPress
with no class at all. The conclusion boxes ("The Bottom Line: …" deliberately aliases the
tldr component) had been silently swallowed on EVERY project-alpha post to date. Cure: the
heading text is now tempered — `((?:(?!</h[23]).)*?)` cannot cross a heading close, so a
failed sibling match fails locally instead of eating the document.
Test: tests/test_component_tagger_no_backtrack_swallow.py (red on the old regex).
Hop-3 cleanup: 38031/38037 re-published (drafts); 37791/37797/37803 re-published live —
all now carry the tokenized conclusion box class.

### Fixed — TOC exclusion whitelist matched "the bottom line" exactly, so every real conclusion vanished from the TOC

The v3.38.3 component-exclusion work whitelisted "The Bottom Line" as a legitimate
Conclusion H2 — but only as an EXACT string. Real conclusions carry subtitles
("The Bottom Line: Two Jobs, One Healthy Ear"), classify as the tldr component, and were
silently dropped from every regenerated TOC, including all three live 2026-08-04 posts.
An independent reviewer flagged the missing nav entry; the whitelist now accepts
"{phrase}: {subtitle}". Test added to tests/test_toc_component_exclusion_v3383.py.
The three live posts' TOCs were repaired at re-publish.

### Fixed — restyle_posts shipped legacy-flavor CSS onto tokenized live bodies (caught by readback)

scripts/wordpress/restyle_posts.py predates the v3.42.0 style-token system: it loaded the
LEGACY generated CSS (`.{slug}-pillar` / `.xr-*` selectors) and re-tagged with legacy
class names. Applied to a token project, the fresh stylesheet matches nothing in the
already-tokenized body — three live project-alpha posts briefly rendered completely unstyled
during this session's retrofit before the mandatory READBACK check caught the mismatch
(Rule 13: verify by readback, not exit code). This is the same two-implementations-drift
disease as Rules 11/12: restyle re-implemented the publisher's styling application and
never received the token transform. `restyle_content` now routes its output through
`style_tokens.transform` (a no-op on non-token projects) and a dry-run reports
`legacy_class_leaks` so the defect is visible instead of silent.
Test: tests/test_restyle_posts_token_aware.py. The three live posts were restored through
the canonical wp_publisher boundary and re-verified 24/24.

### Added — brief.cta_category_hint: the operator's CTA product angle, as a supported channel

Batch content plans name a CTA product angle per keyword ("Ear wash", "Gut probiotic"),
but the v3.42.3 core-hit rule means token matching structurally cannot select a one-token
category ('digestion': overlap 1.0, no core hit) or a long-named one ('Ear, Eye & Skin
Care': 0.25 on one core token) — both degrade to `default_category`, and this batch needed
two hand-edited cta-brief.json overrides. New `state.brief.cta_category_hint` (slug or
human name) is preferred over content matching, STILL validated against
`excluded_categories` + in-stock status (a hint can never reach an Rx category; refusals
warn with distinct EXCLUDED vs unknown messages per Rule 12), and records provenance as
`resolved_products.category_from_hint`. The DEPRECATED `cta_target` tombstone (v3.34) is
untouched. Docs: subskills/optimize/cta-placement/SKILL.md +
subskills/cross-cutting/batch-article/SKILL.md.
Tests: tests/test_cta_brief_builder_category_hint.py (5, drive build_brief — Rule 10).

### Fixed — projects/project-alpha: excluded_categories had gone stale against a recategorized catalog

The 2026-08-04 exclusion listed `prescription`; the catalog has since been recategorized
into rx-eye-ear / antibiotics / oral-dewormers / flea-tick-chews, so the exclusion matched
NOTHING (Rule 14's shape: a control whose referent was renamed). All four current Rx slugs
are now excluded. Project-level config, recorded here because the failure mode is
portfolio-generic: an excluded_categories list is only as alive as its slugs.

## [3.42.8] - 2026-08-05 (four inert checks: the audit found the checkers, not the content)

A 3-article project-alpha batch ran end to end. Every pipeline stage executed, all four
quality gates passed, and all three posts verified 24/24 on their live URLs. The audit
that followed found no content defect. It found **four checks that could not do their
job**, and they share one shape:

> **two places depend on one fact and disagree about how that fact is spelled**

That is Rule 12's disease at the checker layer, and it is invisible precisely because
nothing fails. A scorer that counts zero questions in an 8-question FAQ does not raise
an error, it just quietly marks the article down forever.

### Fixed — CORE-EEAT C10 counted FAQ questions that this pipeline never emits

C10 counted `^###`. Every writer agent in this project emits FAQ questions as bold
paragraphs (`**Question?**`) — that is what the paa-answer-writer contract produces and
what schema-generator extracts into FAQPage. Measured on the batch: **scorer counted 0,
reality was 7, 8 and 8**. C10 therefore failed on three articles that fully satisfied it,
and had been failing fleet-wide.

`scripts/lint/paa_alignment_check.py` already accepted BOTH forms. Two checkers, one FAQ,
opposite answers. Counting now lives in `_count_faq_questions()` whose regexes are kept
deliberately identical to that lint's.

This is the SECOND time C10's FAQ detection has been wrong in the same file: the earlier
fix made the section-LOCATING regex project-aware and left the question-COUNTING regex
untouched. Fixing half a matcher is how a bug survives its own bugfix.

### Fixed — media titles fell through to the slot id, costing every image its SEO slug

`_adapt_entry` renames the designer's `filename_seed` to `filename`. The title fallback in
`ImagePromptSpec.from_dict` still read `filename_seed`, which by then does not exist, so it
degraded to the slot id: `"Cover"`, `"Section 7"`. WordPress derives the attachment slug
from the title, so the fleet shipped media as `cover-4` and `section-6` — zero keyword
value on an asset class that is a ranking signal. Confirmed live on posts 37894 and 37908
before hand-correction. The fallback now reads `filename_seed` OR `filename`; the slot id
remains the honest last resort.

A field renamed in one function and read by its old name in another, same file.

### Fixed — markdown_structure_check was inert on every draft this pipeline produces

Three stacked bugs meant it could neither pass nor fail for the reasons it exists:

1. `_normalize_h2` stripped punctuation without removing the `{#anchor}` suffix that
   assemble.py injects onto every H2, so `## Abstract {#abstract}` became
   `"abstract abstract"` and matched nothing. **Every section of every article reported
   `found: false`.**
2. The alias table is written as prefixes (`"frequently asked"` is not a heading anyone
   writes in full) but matching was exact-set, so the plugin's own default FAQ heading
   never matched its own alias. Third instance of the same disease as C10.
3. `tl;dr` was listed as a synonym of Key Takeaways, but in this pipeline TL;DR is a
   distinct component that coexists with Key Takeaways on every article, producing a
   phantom `duplicate section` on all three.

With all three fixed it reports `passed: true, 6/6 sections` on real drafts.

### Changed — phase-build SKILL.md no longer claims assembly runs it

The SKILL said "Run markdown_structure_check.py immediately"; nothing did (Rule 6). It is
also the wrong checker for that job: it carries a HARDCODED section table, while
`mandatory_sections_check.py` reads the PROJECT's declared `mandatory_sections` and is what
assemble.py actually imports. Wiring the hardcoded one as a gate would have overridden the
project contract. The SKILL now points at the real enforcer and says why.

### Not changed, deliberately

- **Claim-marker convention drift** (`cS_N` vs `cN_S`). Real, and it recurred three times
  in this batch. But `assemble.py::_resolve_marker_collisions` is convention-AGNOSTIC by
  design and auto-renames any cross-section collision into a reserved `c9NN_` namespace, so
  correctness was never at risk. Hand-fixing markers is wasted work. The churn comes from
  `agents/writer.md` declaring a canonical order that the section-drafter dispatch never
  repeats, so each operator invents one. That is a documentation gap, not a missing gate;
  adding an enforcement lint would be a check with nothing to protect.
- **`WPClient` retrying non-idempotent POSTs on timeout.** This is what minted duplicate
  media attachments during the batch. The fix changes shared retry semantics for every
  WordPress call across ~13 projects and needs an operator decision, not a drive-by patch.
- **Wiring markdown_structure_check as a pipeline gate.** Superseded by the project-aware
  `mandatory_sections_check`; adding it would duplicate a correct gate with a worse one.

## [3.42.7] - 2026-08-05 (Rule 13 inventory closed: 10 of 10 hop-3 surfaces guarded)

The last three surfaces that had no drift detection now have it. Every one shipped with the
same defect on its first live run, which is the finding worth keeping:

> **absence is not drift, and inference is not measurement**

Three occurrences in one session — a missing JSON-LD org node, an absent Yoast bridge, three
WooCommerce product URLs — where a checker reported a verdict it had never actually measured.
A detector that cries wolf gets muted, and a muted detector is worse than none.

### Added — `check_term_drift`: term meta beyond term IDs

`setup_categories` / `setup_tags` already pushed hop 2 → hop 3; the gap was detection. The only
sync check compared term **IDs**, so a description or `rank_math_*` value hand-edited in WP
admin was invisible — on an indexed archive page carrying customer-facing copy. Tags had no
live diff at all. HTML-escaping and curly quotes are normalised away, so ordinary
round-tripping is not reported as drift. Live: loamwright 229 terms in sync.

### Added — `check_mu_plugin_drift`: fleet staleness for the REST bridges

Deployment is a human file copy to ~13 hosts, and detection existed only as a per-call side
effect — which answers "can this one call proceed", never "is the fleet current". A host on an
old bridge degrades quietly: RankMath meta writes are skipped rather than failing, so articles
publish without SEO meta and the pipeline reports success. Reads `bridge_version` over REST, so
it needs no shell access and covers all 13. Live: rank-math in sync everywhere.

A bridge for an SEO plugin the site does not run is `not_applicable`, **not** `not_deployed` —
the first run reported the Yoast bridge missing on all 13 projects, which is pure noise, because
the fleet runs RankMath.

### Added — `check_link_drift`: internal links that no longer resolve

Scope is deliberately narrow. A body linking somewhere the map does not list is **editorial**,
not drift; reporting it would bury the real finding under every hand-added link in the fleet.
What matters is a link that 404s — silent damage on a live page.

Enumeration is a pre-filter only; the verdict comes from an actual HTTP status. The first run
called three WooCommerce product URLs dead purely because `/wp/v2/product` was not in the
enumeration list. An unreachable host is UNKNOWN, never "broken". Live: project-alpha and
loamwright in sync.

### Changed — `hop3_drift.format_check` takes the fix hint from the caller

It hardcoded "run --apply to fix", which is wrong for the five detection-only checkers.


## [3.42.6] - 2026-08-05 (three more 3-hop surfaces guarded; the install itself gets an executor)

### Added — `scripts/wordpress/check_post_drift.py`: drift in facts frozen into post bodies

Three of the six unguarded 3-hop surfaces are the same shape — a value resolved from project
config at publish time and then frozen verbatim into every post, where nothing could see it
change. One detector covers all three: article signature, CTA `[products ids=...]` SKUs, and
the JSON-LD org node. Detection only; it never writes.

**First live sweep found real drift the fleet could not previously see:** loamwright 44/56,
project-hotel 21/32, project-charlie 12/106 published posts carry signature wording that no longer
matches the configured template. project-alpha 3/3 in sync. This is the damage
`scripts/wordpress/fix_founder_name.py` — a hardcoded one-off regex — was written to repair
after the fact on one project.

**The audit's premise for the JSON-LD surface was wrong, and correcting it mattered more than
shipping it.** It was ranked highest-blast-radius on the belief that org identity is frozen
into every post body. Verified false: where RankMath emits `Organization` in the document
HEAD, the pipeline deliberately skips that type and the head node renders **live** from WP
options — not a 3-hop artifact at all. project-alpha's bodies carry FAQPage + ItemList only.
Treating an absent org node as drift would have fired on every post of every such project, so
absence is now "not applicable" and only present values are compared.

**Fixtures proved the shape; only production proved the contract.** The checker passed 27
fixtures and was still wrong three times against real posts: it grepped the legacy
`article-signature` class on tokenized projects (the exact trap
`references/retired-contracts.json` exists to catch, walked into in brand-new code); it
compared against the human-readable `author` descriptor instead of the `markdown_template`
that actually ships; and tag-stripping left `audit .` where the template says `audit.` — one
space that marked all 56 loamwright posts stale. It also now matches on the attribution
clause rather than the longest fragment, so varying CTA wording is not reported as signature
drift.

### Added — `scripts/_core/prune_workspaces.py`: the install has a cost, and now it is visible

This marketplace is registered as a **directory** source, so `/plugin install` and
`/plugin update` copy the local tree verbatim. `.gitignore` is not consulted — which is
load-bearing, since `projects/*/` is gitignored and a github-source install would produce a
cache with no client config at all. It also means the 4.2 GB tree comes along, of which
~3.7 GB (88%) is disposable runtime state, and each install mints a new versioned cache dir
rather than replacing the old one. Three stale dirs already hold ~7 GB.

CLAUDE.md already said "don't sync historical task dirs" — but only to a human doing a manual
sync. `/plugin update` has no human in the loop, so the instruction could never fire (Rule 6).
The prune tool is the executor: `--preflight` shows what an install would copy and how much is
junk; `--apply` removes only task dirs that are demonstrably finished, never the newest 20,
and never one whose pipeline did not finish. Age is not permission to delete — `/resume`
reads those.

### Changed — Rule 13's inventory is 7 guarded / 3 disclosed

`internal-links`, `term-meta` and `mu-plugin-bridges` remain without executors, each recorded
with its blast radius. The registry gate keeps them honest: a guarded surface must expose a
working `--check`, an unguarded one must say why.


## [3.42.5] - 2026-08-05 (Rule 14: the verification is the part that silently no-ops)

Closes the remaining findings of the 3.41.x–3.42.3 release audit. Every one of them was
the same shape, and it is not the shape the earlier rules describe: the FIXES were largely
correct and the **verification of the fixes** did nothing. A green check is read as proof,
so a vacuous check is worse than an unfixed bug.

New HARD RULE 14 in `CLAUDE.md` states it, lists all seven instances found, and — because a
rule with no executor is the thing it warns about — ships three:

```
python -m scripts.lint.test_quality_check      # tests that cannot fail
python -m scripts.lint.contract_fanout_check   # instruction layers stating a retired contract
pytest tests/test_hop3_surface_registry.py     # 3-hop surfaces with no --check
```

### Fixed — the weekly-digest relevance ranker actually ranks now (audit C3, HIGH)

v3.42.2 claimed to cure "configured projects rank strictly below unconfigured ones". It did
not. Measured on loamwright's real config, an on-topic headline scored **0.045** against the
0.5 no-terms baseline — the named pathology, intact. Two root causes, and the second is the
one the earlier fix missed entirely:

- the denominator was the UNION of every configured term's tokens, so **adding a topic
  cluster lowered every item's score** — a ranking signal that degrades the more you tell it
- a coverage FRACTION was being compared against a 0.5 constant. Different scales. Real
  cluster lines read "Generative Engine Optimization (GEO) — flagship differentiator", so a
  perfectly on-topic headline covers a third of one term and still lands under 0.5.

Terms are now scored independently (monotone by construction) and the configured path spans
the full range around the neutral point: nothing matched → 0.0, no terms → 0.5, anything
matched → 0.5–1.0. A multi-token term also needs **two** overlapping tokens, because the
two-token cluster "Local SEO" was otherwise half-covered by the single common word "local"
and scored a bakery story 0.75 on an SEO agency's digest — the same one-token defect cured
in the CTA category matcher, found here only by driving the real project config.

Measured after: on-topic 0.75–1.00, off-topic 0.00, unconfigured 0.50.

### Fixed — an unreadable Tavily `/usage` body is an error, not a balance of zero (audit C4)

The mechanism that drained 53 keys was untouched by v3.42.2: any unrecognized payload made
every `.get()` return None, `or 0` made it 0, and healthy keys were persist-marked exhausted.
The balance decision lived inline in `main()` where nothing could test it; it is now
`resolve_remaining()`, returning either a balance or a reason, and an HTTP 200 whose body
cannot be read leaves the stored value alone.

### Fixed — `--check` is a shared contract, not a per-tool choice (audit C5/C6)

When Rule 13 was written it required a `--check` that exits non-zero on drift, and exactly
one of the four tools in its own table did that. `scripts/_core/hop3_drift.py` now owns the
drift→exit-code mapping and all four call it.

The inventory table was also hand-written and incomplete — six further 3-hop surfaces had no
executor and no mention. `references/hop3-surfaces.json` is now the source of truth and
`tests/test_hop3_surface_registry.py` gates it: a guarded surface must expose a working
`--check`, an unguarded one must record why and with what blast radius. Silence is the one
thing it cannot be.

### Fixed — `wordpress.host_access` is declared and asked for (audit C7)

The sidebar deployer read a config key that no schema declared and no wizard asked for, so
its drift detection was inert on 12 of 13 projects. `/init` now asks for it alongside the
other WordPress access questions. It holds no credentials — `ssh` is an ssh-config alias.

### Fixed — one source of truth for per-format table floors (audit C8)

There were two maps: a live one-entry literal in `pre_publish_gate`, and the full
`FORMAT_RULES` table in a module nothing invokes — with the live one's comment naming the
dead one as authoritative. v3.42.2 edited the dead map and changed nothing that runs. The
gate now derives its floors from `FORMAT_RULES`. This tightens the floor for 14 further
formats; safe because that gate WARNs and never blocks a publish.

### Fixed — tests that could not fail (audit C9)

`test_md_derived_h2_is_anchor_free` re-typed assemble's anchor regex into the test body and
asserted against its own copy, so deleting the production code left it green. The regex had
three production copies besides; all now come from `scripts/_core/heading_anchor.py`, and the
test calls it.

`scripts/lint/test_quality_check.py` catches both shapes mechanically across 175 files. Its
own two false positives are pinned as tests, because a lint that fires on correct code gets
muted and a muted lint is worse than none: `False == 0` in Python made boolean verdicts look
like vacuous zero-thresholds, and a test that DRIVES production code while using a shared
pattern to validate its output is asserting, not re-implementing.


## [3.42.4] - 2026-08-05 (Rule 11 gets an executor; blog sidebars get a hop 2→3 deployer; two silent-skip cures)

A release audit of 3.41.x–3.42.3 found the same disease behind every finding: the fixes
were correct and the *verification* of the fixes silently did nothing. A check that greps
for a class name the publisher no longer emits, a kill switch no executor reads, an empty
list that falls back to the full default, a sentinel that encodes two opposite facts in
one flag — each looks like enforcement and enforces nothing.

### Added — `scripts/lint/contract_fanout_check.py`: Rule 11 stops being a request to remember

Rule 11 (a contract change is a fan-out edit across seven instruction layers) prescribed a
grep and then asked a human to run it. It was the only rule in `CLAUDE.md` with no
executor — Rule 6 has the wiring audit, Rule 12 has `_content_gate_reason`, Rule 13 has
`--check`, Rule 8 has nine layers — and consequently the only rule that demonstrably did
not fire.

Contracts are now registered in `references/retired-contracts.json`. A rule does not ban a
phrase (legacy names stay correct for internal artifacts, and a lint that fires on correct
usage gets muted, which is worse than no lint). It says: *a file mentioning the old form
must also mention what replaced it.* Add the entry in the same commit as the contract
change.

Its first run found two stale layers beyond the ones already known, one of which the manual
sweep had missed.

### Fixed — the style-token contract reaches the publish layers (audit C10, HIGH)

v3.42.0 made published class names per-project HMAC tokens; the code was right and the
instructions were not. Nine files still told operators to verify live HTML for
`.{slug}-pillar` — a check that cannot pass on any of the 13 tokenized projects, since
`project-charlie-pillar` ships as `mwxiod-1ymm61`. `skills/seo-blog/SKILL.md` (the main entry
point) also handed out a literal `{slug}-pillar` wrapper, the exact thing the root
`CLAUDE.md` forbids. Every layer now points at `scripts/_core/style_tokens.py` instead of
naming a class.

### Added — `scripts/wordpress/deploy_blog_sidebars.py`: the missing hop 2→3

Blog sidebars ship as a mu-plugin file plus a WPCode CSS snippet on the host — a third hop
this repo cannot see. Without a deployer the drift was not merely unfixed but
*undetectable*, and it appeared within hours of the first deploy. `--check` hashes both
halves and exits non-zero on drift; `--apply` lints on the host before installing, fixes
the root-owned ownership `docker cp` leaves behind, and verifies by readback.

Two properties learned from the deploy that prompted it:

- **A transport failure is never reported as a content verdict.** "Cannot connect" and "the
  file is absent" are different findings; conflating them tells an operator to redeploy
  over a file they never read. On Windows this fires immediately — only PowerShell's ssh
  reaches the agent key.
- **An orphan guard.** A mu-plugin swap verifies by reading the file back, and the file is
  always fine; what breaks is the DATA. WordPress keys widget assignments by `id_base`, so
  a renamed widget silently empties the sidebar while every check passes. The deployer now
  refuses such a deploy and names the widgets that would vanish. Caught for real: the
  generated file registered `..._products` while the live site had `..._shop` assigned.
  The template's `id_base` now matches the `-shop` markup it renders.

Rule 13 in `CLAUDE.md` is generalized from "article CSS" to the shape, with an inventory of
all four known 3-hop artifacts and the requirement that a hop 2→3 executor with `--check`
ships in the same change as its generator.

### Fixed — CTA brief: "sells nothing" and "cannot reach what it sells" are no longer one flag (audit C1, HIGH)

A configured ecommerce project whose catalog had synced empty wrote the *no-config*
sentinel and printed "no conversion_offers config" — false, and the orchestrator read it as
a legitimate skip, dropped four CTA stages, and reported COMPLETE. Articles shipped with no
CTA and nothing said so. The failure path now writes `resolution_failed` with a concrete
cause (missing catalog / empty catalog with its sync date / no category matched) and exits
non-zero. The artifact is still written, because its absence hard-halts the pipeline.

### Fixed — the sidebar feature's own kill switch and empty-list contract (audit C11/C12)

`blog_sidebars.enabled` was required by the schema, documented as the on/off switch, and
read by no executor — Rule 6 inside the feature that shipped alongside it. And
`post_modules: []`, which is exactly how `/init`'s "index sidebar only" answer is encoded,
was falsy and restored the full promotional default.

### Changed — WooCommerce category counts roll up to parents

`count` is products assigned *directly* to a term, never a subtree total — the same
misreading cured in the sidebar PHP in v3.42.3 and left in the Python CTA resolver. Stated
plainly: measured against all 12 catalogs this changes no current match. The audit read
project-hotel's four zero-count top-level categories as miscounted parents; in truth that
site has six products and those subtrees are empty all the way down. The rollup is kept
because the semantics are right, not because it fixed something today.


## [3.42.3] - 2026-08-04 (blog sidebars become an /init capability + two silent-failure root cures)

### Added — per-project blog sidebars, asked for at /init and generated from project config

`scripts/build/blog_sidebar_generator.py` + `templates/blog-sidebars.{php,css}.tpl` render two
deployable artifacts per project into `projects/{slug}/brand/`: an mu-plugin registering two
widget areas with three widgets, and a stylesheet built from the project's brand palette.

Two DIFFERENT sidebars by design. The blog index helps a reader **find** (its own Categories
widget first); the single post **promotes** (image-led CTA card, products, other pages). They are
never the same, and the theme's shared widget area is never touched, so pages and shop keep
whatever they had.

- `/init` **Step 0b** asks whether the site wants custom sidebars — in the opening wizard, before
  any crawling, and it may not be silently defaulted. A sidebar shapes every blog template, so
  discovering the answer at the end is a rebuild rather than a tweak.
- `/init` **Step 12c** builds what Step 0b agreed to, with no second question. It runs late because
  the sidebar needs the brand palette (11.7), the product catalog (4) and the tool/landing pages
  (11) to exist first.
- New `business-context.json :: blog_sidebars` block (schema updated). Absent or `enabled:false`
  is a full no-op.
- Regulated product categories are hard-blocked in the product widget, merging
  `conversion_offers.excluded_categories` with the sidebar's own list, so a sidebar cannot become a
  second route to a prescription line.
- Everything is namespaced by a configurable `class_prefix`, so several projects can deploy on one
  host without colliding.

### Fixed — `cta_brief_builder` resolved the wrong product category (two independent defects)

A CTA subagent refused to write a block because the brief had resolved a prescription-drug
category into a joint-supplement article. It was right to refuse, and there were two separate bugs
behind it:

1. **Single-token categories structurally won.** `_match_category` scores
   `|overlap| / |category tokens|`, so a category whose name and slug reduce to ONE token scored a
   perfect 1.0 off a single incidental word in a subheading, beating multi-token categories that
   were far more relevant. Matching now requires the overlap to touch the article's core signal
   (primary keyword or title); a near miss degrades to the configured `default_category` instead of
   to a wrong category.
2. **Compliance needed its own control.** New `conversion_offers.excluded_categories` suppresses
   categories on every resolution path — content match and default fallback alike — independent of
   how good the matcher is.

Also: `get_term_by()` reports `count=0` for top-level WooCommerce product categories, which made
two sidebar modules silently render nothing. Product lookups now go through `get_terms()`, which
applies WooCommerce's own counting.

### Fixed — veterinary acronyms failed the CTA tone gate

`cta_tone_check.ALLOWED_ACRONYMS` gained the animal-health regulatory set (NASC, NAERS, AAFCO,
AVMA, ACVS, AAHA, WSAVA, CAPC, JAVMA, VCPR, USDA). NASC failed the all-caps "shouting" rule on a
pet-supplement CTA, and its Quality Seal recurs across that whole vertical.

### Documented — four deployment rules that each produced a silent failure

Recorded in the `/init` Step 12c prose and pinned by a test, because every one of them looked like
working code:

1. Sidebar/widget registration belongs in an **mu-plugin**, never a snippet manager. The identical
   PHP as a WPCode Lite snippet never executed — published, correctly typed, parse-clean, nothing
   logged. Registration must beat `widgets_init`.
2. **Safelist the class prefix** in any Remove-Unused-CSS layer. An empty safelist strips the whole
   stylesheet in production while a logged-in admin sees it working.
3. **Never `delete_option()` a plugin's cache option.** WPCode's own `delete_cache()` empties the
   row rather than removing it; removing it stopped every snippet on the site from outputting,
   sitewide and self-perpetuating. Recovery is `wpcode()->cache->cache_all_loaded_snippets()`.
4. **Respect OPcache** (`validate_timestamps=On, revalidate_freq=60`) before concluding a fix
   failed — purging the page cache too early regenerates pages against the old compiled file.

Plus a verification rule: grepping rendered HTML for a class name proves nothing, since the
attribute is present whether or not the CSS that styles it was delivered. Screenshot instead, and
cache-bust every verification fetch.

### Research

`memory/research/sidebar-{evidence-ux-seo,practitioner-forums,competitive-teardown}.md` — the
evidence base behind the module set: NN/g eyetracking and banner-blindness findings, Google QRG
treatment of sidebars as Supplementary Content, practitioner reports, and a 20-site teardown of
DTC, veterinary-authority and publisher templates.

### Tests

`tests/test_blog_sidebar_generator.py` (17) and `tests/test_cta_brief_builder_category_precision.py`
(9), both driving the seam rather than helpers in isolation. Suite: 1487 passed.

## [3.42.2] - 2026-08-02 (weekly-digest root cures: ranker assembly, series conventions, verdict contract)

Deep audit triggered by loamwright issue #5 (the third consecutive digest whose
theme/H1 was last-month's story). Every fix below is skill-level; per-project
data stays under `projects/{slug}/` untouched.

- **fix(runner): follow-ups APPEND after fresh items; theme_of_week = first
  `kind:"new"` item** — new pure seam `industry_news_runner.finalize_issue()`.
  Pre-cure, `main()` prepended follow-ups and re-derived the theme from
  `items[0]`, so ANY surviving follow-up made a stale story the H1 —
  mathematically guaranteed, and exactly what shipped in issues #3/#4/#5.
- **feat(runner): evergreen/how-to title filter for Tier-A** — the Tier-B
  researcher prompt's "news EVENTS only" rule finally has an executor (Rule 6);
  high-precision anchored patterns; drops surfaced in the CLI JSON
  (`evergreen_dropped[]`), never silent.
- **fix(core): headline hygiene at the `make_item` choke point** — trailing
  RSS social-attribution suffixes ("… via @sejournal, @Author") stripped for
  every connector; the dirty form had been published verbatim AND persisted
  into covered.json where it could become a future follow-up headline → H1.
- **fix(runner): `_relevance` is token-based** — whole-phrase substring
  matching scored 0.0 for every real item when project terms are
  sentence-shaped, while the no-terms fallback returned 0.5: projects that
  CONFIGURED terms ranked strictly below ones that configured none.
- **fix(digest-artifacts): series conventions encoded** — title
  `{IND} Weekly, {Month D YYYY}: {hook}`, slug `{ind}-weekly-YYYY-MM-DD`, both
  from the ISSUE date parsed out of the task id (never harvest wall-clock; the
  07-22 issue slugged itself 07-23 by crossing UTC midnight — that off-by-one
  was still live in code, only ever hand-patched in artifacts). Emits BOTH
  `slug` (orchestrator contract) and `slug_draft` (assemble reader).
- **fix(digest-artifacts): claim markers are positional (`c{n}_src`)** — no
  longer derived from `cluster_id`, so hand-curated ids (`hc1`) can't mint
  schema-illegal `[claim:hc1_src]` markers that `citation_inject` rescued only
  by silent truncation, and follow-up ids (`fu_c3`) can't truncate-collide
  with their parent story's marker.
- **fix(assemble): Conclusion stub honors 3-tier mandatory-sections
  resolution** — `_format_wants_conclusion()` delegates to the SAME resolver
  the Format-Fit gate uses (Rule 12). Weekly-digest's tier-2 baseline excludes
  a conclusion, so the phantom `## Conclusion` + literal `_(See verdict in
  main body sections.)_` placeholder no longer ships (it satisfied CORE-EEAT
  C09 by heading-presence and no lint reads stub prose — only the human
  reviewer ever caught it).
- **fix(lint): render-lint L5 catches ANY `[claim:...]` id** — the old
  `c\d+`-anchored regex was blind to non-c-prefixed leaks, so the loud safety
  net `citation_inject` documents relying on didn't exist for them.
- **feat(gates): ONE fact-check verdict classifier** —
  `scripts/pipeline/fc_verdict.py` shared by `pre_publish_gate` and the
  orchestrator content gate. Pre-cure the two disagreed in BOTH directions
  (Rule 12): a benign novel string (`issues_fixed`, invented live 2026-08-02;
  2.1% base rate across 338 historical artifacts) passed the orchestrator and
  failed pre-publish, while `BLOCKED - DO NOT PUBLISH` passed the
  orchestrator's exact-match denylist and was recordable as completed. Unknown
  verdicts now FAIL CLOSED at both gates. Producer fan-out (Rule 11):
  `agents/fact-checker.md`, the dispatch prompt, and
  `subskills/build/fact-check-and-citation` all teach the canonical enum
  (`CLEAN | CLEAN_WITH_NOTES | FIX_REQUIRED | BLOCK_PUBLISH`); new
  `schemas/fact-check.schema.json` + PostToolUse hook rule reject an
  out-of-enum verdict at write time, when the agent can still self-correct.
- **fix(gates): `tables` gate is format-aware** — weekly-digest floor is 1
  markdown table (its second evidence block is a stat-grid LIST, invisible to
  pipe-table counting); `evidence_density_check.FORMAT_RULES` gains the
  `weekly-digest` entry. Known gap, documented: `evidence_density_check` is
  not wired into the pipeline as a stage (Rule 6) — wiring deferred.
- **docs(weekly-digest): SKILL.md gains Step 4b** (mandatory curation review of
  `news-digest.json`, with the two ranking limitations that REMAIN by decision:
  the authority boost structurally favors the project's own Tier-A source
  domains, and corroboration is constant because clusters key on canonical
  URL — no eval harness exists to validate a re-tune, so hand-curation stays
  the quality backstop) **+ publisher timeout discipline** (≥600s for the
  run_pipeline call that services wordpress-publisher; ghost-check procedure
  before any re-run). Stale "prepended" wording swept from
  `subskills/research/industry-news-monitor` and runner docstrings (Rule 11).
- **tests: 45 new** across `test_fc_verdict_contract`,
  `test_digest_ranker_root_cures`, `test_digest_artifacts_root_cures`,
  `test_assemble_conclusion_format_aware`, `test_render_lint_l5_generic_leak`,
  `test_tables_gate_format_aware` — each written failing-first against the
  seam that lied (Rule 10). Full suite: 1460 passed, 1 skipped.
- **fix(core): `tavily_pool._fetch_usage` parses the NEW nested `/usage`
  shape** — Tavily moved `plan_limit`/`plan_usage` under `account` (observed
  2026-07-25); the flat parse read 0/0, derived remaining=0, and
  `set_tavily_key_balance` then falsely marked healthy keys exhausted (53
  keys hit live — the rotation pool drained on a phantom signal). The values
  are normalised back to the flat shape; the regression test asserts against
  the REAL captured payload (Rule 9: parse against real provider shapes,
  never reverse-engineered fictions).

## [3.42.1] - 2026-08-02 (mandatory secret scanning in the release flow + explicit support scope)

- **feat(release): gitleaks + trufflehog are now a required export stage** —
  four scans per release (each scanner over the export TREE and over the export
  repo's git HISTORY); any finding fails the export (exit 1) and blocks
  `--git-init`. `--require-secret-scan` (the release flow) turns missing
  scanner binaries into a hard failure instead of a warning; `--no-secret-scan`
  exists only for local iteration. The named-term privacy scan cannot catch
  entropy-shaped credentials — this closes that gap.
- **fix(docs): a realistic-looking 32-hex example token** in
  `references/init/cloudflare-handling.md` replaced with an explicit
  `REPLACE-WITH-…` placeholder (it was synthetic, but indistinguishable from a
  real bypass token to any scanner or reader). Found by the new stage on its
  first real run, in already-published history.
- **`.gitleaks.toml`** — allowlist restricted, by policy, to self-evidently fake
  documentation placeholders; anything realistic gets fixed in the doc instead.
- **tests: `tests/test_secret_scan_stage.py`** — plants a fake credential and
  asserts the stage fails on it, asserts a clean tree passes, and pins the
  missing-binary policy (soft vs required).
- **docs(SUPPORT.md): explicit scope + burden boundaries** — supported
  versions/host/runtime/publish target, an out-of-scope list (other CMSs, older
  releases, project-config tuning, model behavior and API costs, done-for-you
  work, ranking guarantees), reproduction requirements for bug reports, and the
  security-report path. English + 中文.

## [3.42.0] - 2026-08-01 (per-project style tokens — published output de-fingerprinted)

Every install used to publish the same class vocabulary (`xr-*`,
`article-signature`, `{slug}-pillar`), making the plugin's output a cross-site
fingerprint. Published markup is now project-unique.

- **feat(core): `scripts/_core/style_tokens.py`** — per-(operator, project)
  class names derived as `HMAC(salt, slug:legacy)` → `{prefix}-{suffix}`
  (base36, CSS-identifier-safe, 6+6 chars). The salt is a per-operator secret
  created once outside the repo (locked, Rule 7), so open mechanism +
  private salt = unpredictable names; every install gets its own vocabulary.
  `--generate {slug}` materializes `projects/{slug}/brand/style-tokens.json`
  (the single source of truth; also scans the project CSS so stray classes are
  covered — 49 mapped classes per project vs the 20-name manual registry).
- **boundary model**: internal artifacts (draft.md, lints, agent contracts)
  keep the legacy names; the mapping applies ONLY where content meets the
  world: `wp_publisher._apply_project_styling` (body + inline CSS at publish),
  `verify_post` (checks 02/03/11/29 resolve expected names; a legacy-named
  live post fails with a pointer to the migration tool), the reinject fleet
  tools, and `attach_images_to_draft`'s pending-figure lookup. Projects
  without a tokens file behave exactly as before (legacy fallback,
  suite-pinned).
- **feat(wp): `scripts/wordpress/reinject_style_tokens.py`** — hop-3 migration
  (Rule 13): renames classes in live post bodies + inline `<style>` via the
  same pure transform, with a reader-visible-words safety gate (style block
  stripped before comparison), automatic pre-flight that aborts if any
  NON-article stylesheet on a rendered page targets the legacy names
  (identified by content match, not wrapper heuristics), per-post write-back
  verification, and `--revert`.
- **fleet migration executed**: 366 published posts across 12 sites renamed
  and individually verified (0 errors, 0 pre-flight aborts); fresh-render spot
  checks show token classes and zero legacy residue.
- **guard(reinject_article_css)**: refuses to inject token-named CSS into a
  legacy-named body (would orphan every rule — Rule 2's disease one hop up).
- **/init Step 12b**: token generation is now a standard, unconditional init
  step; CLAUDE.md Rule 2 documents the token-aware wrapper contract.
- **tests**: `tests/test_style_tokens.py` — derivation determinism,
  word-boundary safety (`xr-card` vs `xr-card-kt`), legacy no-op, reverse
  transform, and the REAL publisher/verifier seams (Rule 10).

## [3.41.8] - 2026-08-01 (first public release)

First release published to github.com/XuanRanL/loamwright-SEO-Skill.

- **license: Apache-2.0** (canonical text + `NOTICE`).
- **feat(release): `scripts/release/opensource_export.py`** — builds the
  publishable tree under `dist/opensource-export/` from git-tracked files,
  generates the public `.gitignore` + `projects/README.md`, and runs a
  mandatory pre-publish scan that fails the export (exit 1) if anything that
  should not ship is still present. `--git-init` prepares a release repo.
  Per-client archives, the maintainer's regression suite, and internal docs
  remain in the development tree.
- **docs(readme): complete redesign** — accurate v3.41.x component counts
  (8 skills / 67 subskills / 34 agents / 45 pipeline stages / L1–L13 render
  lint / 29 live-URL checks / 14 hard rules) — plus a full **Simplified
  Chinese translation (`README.zh-CN.md`)** with cross-links, a Loamwright
  （沃匠）byline, and an "About Loamwright" section.
- **fix(security): `google_oauth_setup.py` no longer hardcodes the Google
  OAuth client credentials** — they now resolve from
  `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` env vars or
  `~/.xuanran-seo/credentials/google-oauth-client.json`, with a clear setup
  message when absent; module also made `mypy --strict` clean.
- **fix(guard): `manifest_consistency_check` now validates and repairs
  `marketplace.json :: plugins[].version`** — the field `/plugin install`
  actually registers. Only the outer `version` key was checked before, so
  `plugins[0].version` had silently sat at 3.14.1 while the checker reported
  all-consistent (the exact drift its own `_version_note` warns about).
- **chore(gitignore): root-level stray media/audit artifacts anchored out**
  (`/*.png`, `/Website Audit/`) so ad-hoc session outputs can never be staged.

## [3.41.7] - 2026-07-25 (the LAST end exception retired: weekly-digest goes mid too)

Operator retired the v3.35.1 weekly-digest end exception, making mid placement
truly universal. Now zero configs, zero format rules, and zero live posts carry
an end CTA.

- **fix(projects): `cta.format_rules {"weekly-digest": ["end"]}` REMOVED** from
  loamwright + project-india — digests inherit the global `["mid"]`.
- **fix(wp): `reinject_cta_placement` digest skip removed** — digest posts
  migrate like any other; docstring updated.
- **live migration: loamwright's 3 weekly-digest posts (1628 / 2105 / 2331)
  converted** — each carried an end BANNER with no mid sibling, and a full-width
  dark end strip must not be auto-moved into the body, so each was converted to
  a mid CARD: banner heading → a registered card-skin heading ("Work with us" /
  "Your next step" / "Where we can help"), `xr-cta-banner` class modifier
  dropped, original copy + link preserved verbatim, inserted at the ~35% host
  section. All 3 PATCHed, re-read, re-classified mid, banner heading absent.
  The 3 digest workspaces' draft.md headings synced to match.
- **enforcement tightened:** the fleet test now fails on 'end' ANYWHERE —
  global placements or any format rule ("the last exception was retired
  2026-07-25"); digest exemption test inverted to expect normal migration;
  schema + /init + injector-comment wording updated so no layer still
  documents the retired exception (Rule 11 fan-out).

## [3.41.6] - 2026-07-25 (hop 3 closed: 113 LIVE posts migrated end→mid + the permanent relocation tool)

v3.41.5 fixed the default (skill) and the configs (project); this release closes
the third hop — the CTA already baked into published bodies — with operator
approval to edit live posts in place rather than creating new ones.

- **feat(wp): `scripts/wordpress/reinject_cta_placement.py`** — the CTA analog of
  `reinject_article_css` (same 3-hop rationale, same discipline): touches ONLY the
  CTA cluster (`<h3>{registered heading}</h3>` + `<p class="xr-cta-box…">` +
  optional `<p>[products …]</p>`), never the stylesheet/body/JSON-LD. Actions
  mirror the injector: end-only → MOVE to the ~35% mid host section; legacy
  mid-card + end-banner (loamwright's v3.37 pattern) → REMOVE the end banner,
  keep the mid card; end-banner with NO mid sibling → flag, never auto-move a
  full-width end strip into the body; digest posts and <3-content-H2 posts
  skipped. A MOVE must preserve the exact word multiset or the tool refuses.
  Applied post is re-read and re-classified for verification.
- **fleet migration executed 2026-07-25: 662 posts scanned across all 12 sites,
  113 updated and 113 verified, 0 flagged, 0 errors** (project-bravo 15, project-echo
  12, project-foxtrot 12, loamwright 39, project-hotel 14, project-india 6, project-juliet 3,
  project-kilo 3, project-lima 9; project-charlie 106 + project-delta 3 + project-mike 153
  confirmed module-free — pre-v3.34 bodies). Front-end render spot-checks
  (project-india + loamwright, CF-bypassed, cache-busted): mid CTA before the
  References H2, product grid rendering, retired banner absent.
- **workspace sync sweep: 116 task workspaces** had their `draft.md` +
  `cta-draft.json` blocks moved end→mid with the ORIGINAL per-article heading
  and copy preserved (no injector re-resolution) — a future
  republish-from-workspace can no longer regress the placement decision.
- **dry-run caught two tool bugs before any live edit** (why dry-run is
  mandatory): the relocation safety check compared word SEQUENCES, so every
  legitimate move refused itself (the paired test compared multisets — the test
  was right, the tool was wrong); and mixed mid-card+end-banner posts were
  flagged wholesale when the correct action was banner removal. Both fixed,
  `tests/test_reinject_cta_placement_seam.py` grew to 12 cases. Also fixed:
  `--all` enumerated projects by a project-tree credentials file and silently
  missed the two whose creds are user-level only (project-charlie, project-delta) —
  enumeration now keys on business-context.json and leaves credential
  resolution to WPClient/credential_hub.

## [3.41.5] - 2026-07-24 (CTA + product grid move to the FRONT-MIDDLE — a skill-level default error wearing project-level clothes)

Operator decision 2026-07-24: the conversion card (heading + copy + WooCommerce
`[products]` grid) belongs in the article's **front-middle** (after the content
section at the ~35% word mark), not at the end. Investigation found the "end
everywhere" state was NOT twelve independent project choices but ONE skill-level
default propagated three ways: `/init`'s interview prescribed "end … (default)"
and told operators to "reserve `mid` for lead-gen sites"; `cta_injector.py`'s
code fallback was `["end"]`; and the v3.37/v3.38 rollout stamped `["end"]` into
11 of 12 project configs, which each project CLAUDE.md then documented as if
bespoke (Rule-11 duplication of a default). The mid capability itself was always
present, precisely specified (~35% word mark, structural-H2-safe, ≥3-section
guard), and battle-tested by loamwright — only the default was wrong.

- **fix(cta): injector default placement `["end"]` → `["mid"]`** (docstring
  example updated; `end` stays fully supported as an explicit opt-in).
- **fix(projects): all 12 fleet configs migrated to `placements: ["mid"]`**
  (loamwright's `["mid","end"]` collapses to `["mid"]`), with `variants.mid`
  seeded from `variants.end` wherever missing — the injector HARD-fails a
  requested placement with no usable static variant when the LLM draft is
  absent, so the migration must not dead-end the fallback path. The deliberate
  `format_rules: {"weekly-digest": ["end"]}` exception (v3.35.1: no mid card
  inside a news roundup) is preserved on loamwright + project-india.
- **docs(Rule 11 fan-out): `/init` 6d now prescribes mid as THE default** (and
  records why the old wording was the root cause); `cta-placement` SKILL example
  + `agents/cta-writer.md` updated (mid blocks must bridge from the surrounding
  topic, never open like a closing pitch); business-context schema documents the
  default; all 12 project CLAUDE.md placement lines rewritten.
- **tests: `test_cta_placement_mid_default_seam.py`** drives `inject()` through
  the real workspace seam (default-resolution + ~35% host-section position) and
  PINS the fleet: every enabled project config must be `["mid"]`, `end` may
  survive only inside the weekly-digest format rule, and every static-variant
  project must carry `variants.mid`. Skips gracefully on checkouts without the
  (untracked) `projects/` fleet.
- **hop-3 (Rule 13's lesson): the three 2026-07-24 chinoiserie DRAFTS
  (37176/37182/37188) were re-injected and re-published in place** — each
  `cta-draft.json` block moved end→mid so the bespoke LLM copy + verbatim
  products shortcode survived (a naive re-run would have regressed them to
  generic static variants), end blocks stripped via the injector's sanctioned
  repair path, republished as drafts, verify-post 24/24 ×3 including check 29.
  LIVE posts across the fleet still carry end-placement CTAs and need a
  confirmed migration pass (same 3-hop reality as the article-CSS rule).

## [3.41.4] - 2026-07-24 (5 root cures from the project-india 3-batch day: silent-fallback and gate-severity class)

Nine project-india articles ran end-to-end today (3 published AM, 6 verified drafts:
37158/37164/37170 midday, 37176/37182/37188 chinoiserie evening batch). The
post-batch deep audit found all 12 tasks 45/45 stages, every enforced subagent
stamped `_generated_by`, every content gate `passed:true`, verify-post 24/24,
and gates re-scored the draft AFTER every post-reviewer manual edit (mtime-
verified) — the v3.35.3/v3.41.x gate seams all held. Five defects root-cured,
all in the silent-no-op / gate-severity family (Rules 6/11/12):

- **fix(batch): `batch_queue.VALID_FORMATS` is now READ FROM `schemas/angle.schema.json ::
  format_id` enum — the hand-maintained 10-item literal had drifted a generation behind
  the 27 templates.** A CSV row naming a real-but-unlisted format (`buyers-guide`,
  `encyclopedic`, `roundup`, ...) was silently rewritten to `listicle`, so the whole
  article was planned and written in the wrong format with no error anywhere (caught
  live enqueueing the 2026-07-24 chinoiserie batch). Fallback for a genuinely unknown
  format still soft-degrades but now WARNS on stderr. Seam-tested by
  `tests/test_batch_queue_format_enum_seam.py` (CSV → `enqueue()` → index.json, per
  Rule 10), which pins enum == schema AND templates ⊆ enum.
- **fix(schemas): `angle.schema.json` format_id enum gains `local-state-pillar` +
  `local-city-page` (25 → 27).** `format-selector` Step 0 has routed local-mode
  articles to these templates since v3.40.0, but the enum never accepted them — real
  local runs (project-echo Barrie 2026-07-17) had to record `pillar-page` and document the
  workaround in `format_selection_rationale`. Found by the new templates ⊆ enum test.
- **fix(hooks): `post_tool_use_schema_validate` now BLOCKS (exit 2) a watched artifact
  that is not parseable JSON** — the strictly-worse failure used to take the softer
  warn-only branch (exit 1, "could be partial write" — wrong: PostToolUse runs after
  the Write/Edit completed, so what it reads IS the final file). Real cost 2026-07-24:
  an Edit split a JSON string in outline.json, nothing blocked, and the defect
  surfaced two stages later as the reason-less "LLM stage did not produce valid
  outputs". `tests/test_schema_validate_hook_blocks_bad_json.py` drives `main()`
  through the real stdin seam.
- **fix(images): `image_regen_slots --workspace` now resolves a BARE task_id to
  `memory/workspace/{task_id}`.** `agents/image-visual-qa.md` and the orchestrator
  dispatch both pass a bare id, which resolved against CWD — regenerated PNGs landed
  in `./{task_id}/images/` OUTSIDE the real workspace: API billed, `images.json`
  unchanged, watermark skipped, zero errors ("it cost money and nothing changed",
  2026-07-24 midday batch round-2 regen). `tests/test_image_regen_slots_workspace_resolution.py`.
- **fix(wp): `sync_links_map` renders category names with " · " separator, not ", "**
  — a category whose NAME contains a comma ("Porcelain, Explained") made the
  per-post category list unparseable for the linker's register matching.
- **docs(Rule 11 fan-out): the format COUNT is no longer hand-stated anywhere.** Four
  layers disagreed (orchestrator dispatch "24 templates", format-selector SKILL "25",
  blog-formats catalog "24", schema "27" post-fix) while `templates/` held 27. All
  four now point at the schema enum as the single source of truth; the seam test is
  the enforcement, so the count cannot silently drift again. Also added the v3.41.4
  format-id contract note to `subskills/cross-cutting/batch-article/SKILL.md`.

## [3.41.3] - 2026-07-19 (7 root cures from the loamwright 3-article batch deep audit)

The 2026-07-19 loamwright batch (search-engine-optimisation-consultants 2122 /
bigcommerce-seo-agency 2128 / seo-content-writing-agency 2134 — all 3 published as
verified drafts, reviewer 87/88/91) took 5.10h wall (115+93+93 min sequential; ~85
min/article is inherent LLM-stage time, repairs ~25 min total). Every v3.41.x cure
held (deep-research `_rule8` stamped 3/3, COMPLETE/verify content gates 3/3, 0
em-dashes 3/3). The post-batch audit root-cured 7 defect clusters:

- **fix(assemble): duplicate-Conclusion stub was a v3.40.0 REGRESSION.** 5eb52c2
  switched conclusion detection from tolerant substring tokens to the project
  `h2_pattern` FULL-match on the raw h2 — which still carried the writer's
  `{#conclusion}` anchor, so `^Conclusion$` failed and a `_(See verdict...)_` stub
  was appended beside the real Conclusion. h2 is now normalized (anchor suffix
  stripped) at BOTH the .md derivation seam and inside `_has_conclusion_section`.
  (`tests/test_anchor_canonical_and_conclusion_v3413.py`)
- **fix(anchor_link_builder): canonical slug ALWAYS wins.** `inject_anchors` used to
  SKIP pre-anchored headings while `build_toc` linked fresh text-slugs — a writer
  copying the outline's `anchor_id` into a heading left 8 of 14 TOC links dead on
  the rendered page (latent since v3.13.0). Pre-existing anchors are now stripped
  and replaced with the computed text-slug: heading id == TOC slug by construction,
  idempotent, and a custom `## TL;DR {#summary}` can no longer orphan component CSS.
  Writer contract fanned out per Rule 11 (agents/writer.md, section-drafter
  SKILL + dispatch_prompt, markdown-authoring-conventions scope note): PLAIN
  headings, `anchor_id` is assembly metadata; plus the zero-BASED `NN_` filename
  convention stated at all three layers (art1's writers were dispatched 1-based).
- **fix(provenance): ONE source of truth for `_generated_by`.**
  `scripts/_core/provenance.py` now feeds BOTH `orchestrator._PROVENANCE_REQUIRED`
  and `pre_publish_gate.PROVENANCE_REQUIREMENTS` — the two hand-maintained dicts
  had drifted to 3-of-7 overlap (Rule 12). geo-content-optimizer / visual-designer /
  internal-linker joined SUBAGENT_ENFORCED_STAGES (their artifacts were gated but
  their dispatches never carried the warning — geo-audit.json failed exactly that
  way live); agents/geo-auditor.md's Step-6 template now INCLUDES the field it
  omitted, agents/linker.md states its (previously dead) demand.
  (`tests/test_provenance_contract_fanout_v3413.py` pins doc<->code agreement.)
- **fix(ai_tells_detector + cta_injector): the pipeline no longer manufactures its
  own quality-gate deadlock.** cta_injector deliberately curls apostrophes to
  U+2019 (project-charlie-class WAF); P17 then fired on the machine-curled CTA copy and
  ai_slop crossed the <20 gate with the ONLY repair agent (humanizer) forbidden
  from touching CTA blocks (live on art1: 21.1, hand-fix required). CTA extents
  (identified via the SAME component_headings registry the injector uses — no
  duplicated phrase list) now suppress `_FORMAT_PATTERNS ∪ {P13, P17}`;
  sanitize_copy additionally normalizes curly DOUBLE quotes to ASCII;
  agents/cta-writer.md drops the em-dash from its own stat-line example and
  mandates straight ASCII quotes in authored copy.
- **fix(orchestrator): fresh-task brief schema gate + run_pipeline ERROR handling.**
  `intent_override: "commercial-investigation"` (an analyst label, not a schema
  enum — keyword-research SKILL.md even TAUGHT it) burned ~10 stages before
  assemble's validation caught it. `next_stage()` now validates the brief
  sub-schema on genuinely fresh tasks (no history AND no checklist records —
  legacy workspaces exempt) and errors before any spend; keyword-research SKILL.md
  corrected. Fixing this exposed a LATENT crash: `run_pipeline.advance` had no
  handler for ANY next_stage ERROR shape (bare KeyError on `executor`) — now
  returns a proper `{"action": "ERROR"}`.
  (`tests/test_fresh_task_schema_and_images_join_gate_v3413.py`)
- **fix(images.json): schema + content gate close the Rule-12 vacuum.** The
  2026-07-19 operator incident was self-inflicted (absent keys read via `.get()`
  were misdiagnosed as "unpopulated" and three HEALTHY manifests were
  hand-"reconciled") — possible only because images.json had no schema and the
  join was a bare existence check. `schemas/images.schema.json` pins the 9-field
  contract; `image-pipeline-join` now content-gates slot coverage + path
  existence via `_content_gate_reason` (both decision paths, v3.35.3 pattern);
  `write_artifacts` + `render_data_charts` resolve paths to ABSOLUTE (a real
  relative-path defect found in art1's cover entry); agents/image-visual-qa.md +
  seo-blog SKILL.md document "nine fields, nothing else, never hand-reconcile".
- **fix(brand_fact_check): proof-point check now honors its own documented
  self-referential scope.** The `_is_self_sentence` guard existed for
  tenure/team/count checks but was missing from the proof-point branch, so any
  ecommerce-TOPIC sentence sharing a case-study subject word plus ANY number
  (citation years, an HTTP 301, a References title) fired — 5 false positives on
  art2, operator had to code-fix mid-batch. Real self-referential fabrications
  still fire. (`tests/test_brand_fact_self_sentence_guard_v3413.py`)
- **fix(spelling_dialect_check): the exact target keyword is exempt (Rule 1
  executor half).** "search engine optimisation consultants" under an en-US
  project counted 52 keyword-inflection "drifts" and forced a whole-article
  locale flip. Inflections of the exact user keyword (shared >=6-char prefix)
  are now exempt; brief-construction guidance added to seo-blog +
  batch-article SKILLs. (`tests/test_cta_and_dialect_lint_exemptions_v3413.py`)

## [3.41.2] - 2026-07-18 (off-core image sourcing + category-selector root cures from the project-lima 3-article batch)

The 2026-07-18 project-lima batch (senix push mowers 37226 / solar mower 37232 / bad boy
mowers prices 37238 — all three OFF-CORE adjacent-traffic articles) ran 45/45 stages
clean but surfaced three recurring skill-level defects, each caught and hand-fixed
mid-batch, now root-cured:

- **fix(real-photo images): the ARTICLE's per-slot subject now wins over the PROJECT's
  category policy.** `real_brand_image_pipeline` sourced every photo slot with the
  project-level `image_sourcing_policy.product_noun` + `search_terms` (project-lima:
  "remote control slope mower on steep grass bank"), ignoring the per-slot
  `product_noun` the designer already emits. On off-core articles that queried the
  WRONG subject — and shipped a competitor-branded Farmry VLF57 (a Rule-8 blocked
  brand) onto a Senix push-mower cover, twice more on the bad-boy article.
  `parse_photo_slot` now captures the slot noun; `run_for_workspace` sources with it
  and drops the project search_terms whenever the slot noun differs (domain-neutral
  "{brand} {noun}" templates take over — the exact `--smoke` behavior that recovered
  the batch by hand).
- **feat(real-photo images): plain-scene AI fallback for brand:null slots.** A photo
  slot with no real brand (the correct design for a generic unbranded subject — a
  robotic mower, a PV array, a landmark) previously VANISHED: `parse_photo_slot`
  returned None, no entry, no log, no image ("No fallback plain-scene generator
  exists yet"); the solar-mower article reached publish-time with every photo slot
  missing. Empty-brand slots now parse as `no_product` and route through the new
  `_generate_plain_scene_ai` — the normal openai_image_pipeline provider chain
  (mikuapi → vertex → openai) driven by the SLOT's own fields only (the project
  art_direction_prefix is deliberately excluded: its category language overrode the
  subject on the bad-boy cover regen). The source:"skipped" record survives only as
  the last resort when the fallback itself fails.
- **fix(alt text): `build_alt_text` no longer hardcodes an em-dash or the project
  noun.** The old template `"A real {brand} {noun} — {scene}"` put a U+2014 (render
  lint L12's exact veto target) into every real-photo alt attribute AND produced
  factually wrong alts on off-core articles ("A real Senix remote control slope
  mower"). Comma joiner; slot-derived noun; brand-less form supported.
- **fix(category-selector): preserve-meta merge replaces the wholesale overwrite.**
  The selector's body-keyword scoring REPLACED the meta-builder's format/intent
  -derived categories on every run — the 4th recurrence dropped "Pricing & Cost"
  from a PRICING article in favor of parts-wear body keywords (project-foxtrot 07-14, all
  3 project-lima 07-18). Meta-builder picks that resolve on the live site now occupy
  cap slots FIRST and scored candidates fill the remainder; `--replace-meta`
  restores the old behavior for deliberate re-categorization. Unresolvable names
  still fall away (the 2026-07-01 hand-authored-names safety is intact).
- **fix(category-selector): `_normalize_live_snapshot` also derives name_to_id /
  categories_by_id from the wp/v2 `terms` snapshot shape** (project-lima-style
  `{captured_at, slug_to_id, terms}`). Pre-fix that shape kept slug_to_id only, so
  every NAME-based consumer (the weekly-digest name/slug pin, the new preserve-meta
  step) silently no-opped on those projects — found by the new seam test, not by
  inspection (Rule 10 vindicated).
- **fix(active_project): `python -m scripts._core.active_project` is no longer a
  silent no-op.** The module had no `__main__`; `--set X` exited 0 having done
  nothing (observed live: a session believed it had switched projects). Minimal
  `--get`/`--set` CLI added; env-pin semantics unchanged.
- **tests:** `test_offcore_image_slot_seam.py` (7) + `test_category_selector_preserve_meta_seam.py`
  (4) drive the REAL seams (`run_for_workspace` with real image-prompts.json shapes;
  `select_categories` end-to-end against an on-disk workspace+project layout);
  `test_parse_photo_slot_skips_when_no_brand` re-pinned to the new contract (the old
  assertion pinned the vanishing-slot bug itself).
- **docs fan-out (Rule 11):** orchestrator image-prompt-designer dispatch + image-fork
  + category-selector stage descriptions, `agents/image-prompt-designer.md` real-photo
  contract (per-slot product_noun MANDATORY; brand:null legal + falls back to AI),
  `skills/seo-blog/SKILL.md` preserve-meta semantics.

## [3.41.1] - 2026-07-18 (audit-tooling root cures from the project-delta audit-first init)

Found live while auditing project-delta.example.com (Cloudflare-fronted WooCommerce site):

- **fix(crawl+fetch+cf-detector): never advertise a codec you can't decode.** `crawl_site.py`,
  `scripts/fetch/fetch_page.py`, and `_core/cloudflare_detector.py` hardcoded
  `Accept-Encoding: gzip, deflate, br` while the environment had no `brotli` package —
  any Brotli-serving origin (all Cloudflare sites) returned bytes httpx could not decode,
  so `resp.text` was mojibake: the crawler saw 0 links + empty titles and "completed" a
  1-page crawl with a green exit code. Root cure: the hardcoded header is REMOVED in all
  three (httpx negotiates only codecs it can actually decode) and `brotli` is installed.
  Same disease family as Rule 9 (a layer silently does the wrong thing because the real
  input never matched the assumed shape).
- **fix(capture_screenshot): per-page filenames + CF bypass headers.** Screenshot filenames
  were `{netloc}_{viewport}.png` — every page of the same domain overwrote the previous
  one (home/shop/blog collided; the "6 captures" were 1 page). Filenames now include a
  path slug. Also added repeatable `--header/-H NAME:VALUE` passthrough (patchright
  `extra_http_headers`) — without it, WAF-protected sites screenshot as the Cloudflare
  "Performing security verification" challenge page, which is exactly what the first run
  captured, silently.
- **projects/project-delta initialized** (audit-first: full 11-module website audit → 67/100
  baseline → init derived from measured artifacts). Fleet CF bypass token confirmed working
  on the new site; RankMath bridge MU-plugin pre-installed by ops.

## [3.41.0] - 2026-07-17 (deep audit: /status and /resume were blind to real workspaces; PIPELINE_COMPLETE never stamped; batch_queue ids broke assembly; links-map was never populated; deep-research Rule-8 gap)

A full-pipeline + release-regression audit (project-hotel 3-article batch as the live
probe, plus two parallel investigators over the 12 most recent workspaces and every
v3.38.3→v3.40.1 cure). The 12 recent runs were CLEAN — all 45 stages, every gate
reading real verdicts, drafts only. Every audited release cure verified ACHIEVED in
code with a live executor + seam test. The defects found were all in the SUPPORT
tooling around the pipeline, several of them generation-old dead-drifted contracts:

### 1. `/status` + `/resume` read a workspace layout and state contract that has not existed for months (Rule 6/11)

`status_reporter.py` scanned `workspace/{task}` (real tasks live in
`memory/workspace/`), read keys `state`/`stage`/`started_at` (the runner writes
`status`/`current_stage`/`created_at`), and carried a hand-written 27-stage v3.2
stage list (the pipeline has 45). Net effect, proven live: `/status` reported the
`batches` DIRECTORY as a phantom running task and was blind to every real
workspace. `resume_handler.py` had the same wrong root + keys PLUS a 27-stage
STAGE_ARTIFACTS map full of artifact names no real stage has ever written
(`format.json`, `geo-optimized.md`, `wp-publish-log.json`, ...), while its header
claimed it "delegates". Cures: both now derive stage order and artifacts from
`scripts.pipeline.orchestrator` (single source of truth), scan
`orchestrator.WS_ROOT` first with legacy fallback, read real keys with legacy
fallbacks, compute progress from `stage_history`, and `/resume`'s suggested
command is the canonical `run_pipeline` invocation instead of a hand-picked L2.

### 2. PIPELINE_COMPLETE was returned but never WRITTEN — every finished task stayed "running" forever (Rule 12 family)

`orchestrator.next_stage()`'s PIPELINE_COMPLETE branch only returned a dict; no
code path stamped `state.json`. All 3 project-hotel tasks (and, it turns out, every
finished task ever) sat at `status: running / current_stage: wordpress-publisher`
with a fully-completed stage_history. Cure: `_stamp_pipeline_complete()` (idempotent)
called from the PIPELINE_COMPLETE branch — the single shared path both the direct
CLI and run_pipeline funnel through — plus a new maintenance action
`--action backfill-complete` that stamped the **324** historically finished
workspaces (finished = completed `verify-post` in history OR `publish-result.json`
on disk; genuinely abandoned workspaces stay `running`, which is their true state).
`/status` went from 325 phantom in-flight tasks to 1 genuinely-stuck smoke leftover.
Seam test: `tests/test_pipeline_complete_stamp.py` (drives `next_stage()` on disk).

### 3. batch_queue task_ids violated the state schema and its daily cap was a hardcode

`_generate_task_id` emitted hyphenated ids (`art-...-001-ab`) that fail
`state.schema.json`'s `^[a-z0-9_]{8,32}$`; the runner's lenient writes let the
batch run until **assembly**, which validates the full state and hard-fails
(2026-07-17 project-lima batch — every workspace needed a manual copytree + in-place
id rewrite). And `daily_cost_cap_usd: "50.00"` ignored the operator's configured
$100, stalling batches on days already past $50. Cures: underscore id form
validated against the REAL schema pattern in
`tests/test_batch_queue_taskid_schema.py` (Rule 10: the test loads
state.schema.json, no copied regex), and the cap now comes from
`cost_ledger._load_limits()` at enqueue AND on load-backfill.

### 4. internal-links-map.md was documented as "populated by the publisher" — nothing ever wrote it (Rule 6)

`agents/linker.md` reads it for internal-link targets; `wp_publisher.py` never
touched it; `project_paths.internal_links_map_path()` was used only for an
existence check. 8/10 projects carried the frozen "(none yet)" init value —
project-juliet had **168** live posts the linker could not see — and 2 projects
were missing the file entirely. Cure: new `scripts/wordpress/sync_links_map.py`
REGENERATES the `## Published articles` section from the live WP REST inventory
(authoritative; status=publish only; splice preserves the rest of the file;
handles WP's 400-on-exact-multiple-of-per_page pagination edge, hit live on
project-charlie's exactly-100 posts). Wired best-effort into `wp_publisher` step 8
after every successful publish; all 10 projects backfilled this session
(project-bravo 6 / project-charlie 100 / project-echo 42 / project-foxtrot 6 / loamwright 44 /
project-hotel 21 / project-juliet 168 / project-kilo 34 / project-lima 3 / project-mike 152).

### 5. Tavily Deep Research ignores caller-side excludes — Rule 8 layer-1 gap

The pro/deep-research endpoint selects sources server-side; blocklisted
competitor domains leaked into `deep-research.json` on 2 of 3 project-hotel runs
even though every `tavily_search` honored `--exclude`, and each researcher had to
rediscover + quarantine the leak by hand. Cure: `tavily_research.py` now stamps a
`_rule8` block (`blocked_domains_found[]` / `citation_safe` / guidance) into its
own JSON output using the task's/active project's competitor policy, and warns on
stderr. `agents/researcher.md` + root CLAUDE.md Rule 8 enforcement-layers updated
to treat flagged material as CONTAMINATED_FOR_CITATION.

### 6. Cross-section claim-marker collisions are now auto-resolved at assembly

Parallel writers mixing the two documented marker orders (`cS_K` in
agents/writer.md vs `cK_S` in batch playbooks — a Rule 11 contradiction now
reconciled in writer.md, canonical = `c{section_index}_{seq}`) produced the same
literal marker labeling DIFFERENT claims in different sections every batch since
2026-06-18 (4 hand-fixes in the 2026-07-17 nose-print article alone); the
fact-checker then verified only one of the claims. Cure:
`assemble._resolve_marker_collisions()` renames a later section's colliding
markers into a reserved `c9NN_{idx}` namespace (intra-section repeats of the same
claim are preserved), with a stderr notice. Test:
`tests/test_assemble_marker_collision.py`.

### 7. Third em-dash counter converged + suite hygiene

Adopted the parallel session's `em_dash_audit.py` References-exemption (verified:
6/6 tests, correctly narrow — APA-7 source titles legitimately contain em-dashes,
e.g. the CBSA "I Declare — ..." reference on project-echo_barrie) and fixed
`markdown_structure_check.py`, whose header claimed it "delegates to
em_dash_audit" while actually running a third independent whole-body count — it
now really delegates. New `pytest.ini` (`testpaths=tests`) stops bare-`pytest`
collection from crashing on runtime diagnostic scripts inside
`memory/workspace/`. `schemas/angle.schema.json`'s title description no longer
demands the retired "+ Power Word + digit" contract that `title_validator.py`
dropped in the 2026-06 revision.

## [3.40.2] - 2026-07-17 (assemble: the slot-rename fallback could hijack a body orphan into the cover)

Closes the one latent hazard flagged (not fixed) in 3.40.1's investigation.
`assemble._fix_slot_id_names` maps body `[IMAGE-SLOT-X]` tokens that don't match
`image-prompts.json` onto the unplaced prompt slot_ids via `sorted(unplaced)[0]`.
Writers never emit `[IMAGE-SLOT-cover]` (it is injected after the Abstract by
`_inject_missing_image_placeholders` in a later step), so at rename time the cover
is almost always "unplaced" — and `"cover"` sorts FIRST alphabetically. Under any
body/prompt slot-id mismatch a mid-article orphan (e.g. `[IMAGE-SLOT-section_5]`)
was therefore renamed to `[IMAGE-SLOT-cover]`, planting the COVER image mid-article
and suppressing the after-Abstract injection.
- **Fix** (`scripts/build/assemble.py`): exclude cover/featured slots
  (`is_featured` OR `slot_id == "cover"`) from the positional-fallback target pool.
  The explicit alias branch (`hero`/`cover_image`/`featured`/`main` → the featured
  prompt) remains the only sanctioned orphan→cover mapping. Also dropped one dead
  local (`body_text_lower`).
- Test: `tests/test_assemble_slot_rename_never_hijacks_cover_2026_07_17.py` (drives
  the real `_fix_slot_id_names`, red-then-green on the exact hijack).

## [3.40.1] - 2026-07-17 (project-bravo 3-article batch: 3 root cures found by a 4-agent post-batch investigation)

The project-bravo batch (best hibiscus tea / loose leaf jasmine tea / flowering
tea set — all shipped as drafts 37016/37022/37028, verify-post 24/24) ran the full
45-stage pipeline cleanly with zero silent skips. A post-batch root-cause audit
(four parallel investigators) found three defects — none in stage *ordering*, all
in *contracts and scoring* — plus doc drift. Each is fixed at the skill level with
a seam test (Rule 10). A parallel dev session's in-flight `em_dash_audit.py`
References-exemption (same "style lint false-positives on correct typography"
family) is NOT included here and was kept out of this commit.

### 1. CORE-EEAT under-scored every article by −2.5 pt (the twin of the v3.40.0 O01/O02 bug)

`run_quality_gates.py` already opened `state.json` for `project_slug` but never
extracted `brief.primary_keyword` nor passed `--brief` to `core_eeat_scorer`, so
R01/R06 FAILED "no keyword provided" — a fixed −2.5 pt on EVERY article. Measured
on camelhibiscus0717: **76.25 → 78.75** after the fix (matches the geo-auditor's
manual re-score). Mis-verdicts any article whose true raw score is [80, 82.5) as
FIX instead of SHIP — the same near-SHIP band the v3.40.0 audit had just cleared of
the O01/O02 depressor. It survived that audit because the audit tested
`core_eeat_scorer`'s own CLI but not the `run_quality_gates → core_eeat_scorer`
seam (Rule 10).
- **Fix** (`scripts/validate/run_quality_gates.py`): resolve the primary keyword
  (state `brief.primary_keyword`, fallback `meta.focus_keyphrase`), write a sidecar
  `_gate_brief.json`, pass `--brief`. Also pass `--meta` to `cite_scorer` — without
  it the `T05` YMYL veto was dead at this layer.
- ✅ Rule-8 `COMP01` was VERIFIED alive (the wrapper forwards `--project-slug` to
  cite_scorer; probed with a blocklisted domain → `Vetoes: ['COMP01']`, BLOCKED,
  cap 50). But `agents/geo-auditor.md` documented BARE scorer commands that skip it
  — corrected.
- Test: `tests/test_quality_gates_brief_seam_2026_07_17.py` (drives `main()`,
  asserts the argv it hands each scorer).

### 2. category-selector wrote a category NAME without its matching ID (4th+ recurrence)

The selector overwrote `meta.categories` from its signal scan while leaving
`meta.category_ids` untouched → a self-contradictory meta.json (name "Teaware &
Care" / id 143), on 3/3 articles, masked only because `wp_publisher` prefers the id.
Three compounding causes: (a) name-write unconditional, id-write best-effort and
resolved BY NAME against a `name_to_id` map most projects' snapshot never exposes;
(b) `categories-live.json` exists in ~6 hand-authored schemas (canonical, applied,
`{generated_at,slug_to_id}`, project-lima's, a bare `{slug:int}` map, and
project-foxtrot/project-mike's `{slug:{id,parent,...}}`), several of which `_normalize_live_snapshot`
passed through with no `slug_to_id`; (c) the scorer had no depth awareness, so a
top-level parent with a broad keyword list out-scored its own child (flowerset:
parent "Teaware & Care" beat child "Teaware Guides").
- **Fix** (`scripts/build/category_selector.py`): `_derive_slug_to_id_any` +
  normalizer fallback expose `slug_to_id` for EVERY shape; the meta-write resolves
  ids BY SLUG and applies name+id **atomically, or defers** (leaves meta untouched)
  when it cannot resolve every pick — a name is never written without its id; and a
  matched parent **descends to its deepest matched child** within its own branch
  (never dropping a parent to let an unrelated childless top-level bubble up).
- Test: `tests/test_category_selector_name_id_invariant_2026_07_17.py` (drives the
  real `select_categories()` against a tmp project in all 6 snapshot shapes).
- NOTE (skill vs project separation): the *contradiction* is a skill bug, now cured.
  The remaining *topical* mis-pick (a buyer's-guide landing in a teaware category)
  is project-bravo's over-broad keyword config (`storage`/`care`/`clean` match any
  tea guide) — a PROJECT-level fix, per-project.

### 3. P28 "markdown bleeding" penalized correct scientific-binomial italics (perverse incentive)

P28's regex `(?:^|\s)\*{1,3}\w` matches the opener of ANY emphasis run, so
`*Hibiscus sabdariffa*` counted as a hit; P28 feeds `ai_slop_score` (4 × distinct
patterns), so STRIPPING correct ICN italics bought exactly −4.00. Two humanizer
runs on sibling articles diverged on identical input (one kept 15 binomial italics,
one stripped all 22) because `agents/humanizer.md` orders both "write italics as
`*text*`" and "apply the P28 fix = remove" with no arbitration; the score reward
decided it. Third instance in one week of "a style lint makes correct output the
expensive option."
- **Fix** (`scripts/lint/ai_tells_detector.py`): drop P28 hits on
  italic-only-balanced lines. Scoped to ITALIC (single `*`) deliberately —
  mid-sentence `**bold**` overuse is the trio's real target and still fires
  (pinned by `test_ai_tells_bold_led_exemption.py`); genuine orphan markers still
  fire (render_lint L3 backs it on rendered HTML).
- Test: `tests/test_p28_balanced_emphasis_exemption_2026_07_17.py`.

### Docs (Rule-11 fan-out)

- `agents/geo-auditor.md`: Step 1/2 now show the wrapper (or fully-argved scorer)
  commands so a geo-auditor cannot silently skip COMP01/T05/R01/R06.
- `CLAUDE.md` + `skills/seo-blog/SKILL.md`: corrected the "`run_quality_gates
  --project-slug`" phrasing (the wrapper takes only `--workspace` and resolves the
  slug internally).
- `references/style/ai-tells-43.md`: P28 now states binomial italics are NOT a defect.
- `subskills/image/image-slot-allocator/SKILL.md`: banner — this stage is **NOT
  wired** into the orchestrator Stage table (Rule-6 dead code described as live in
  5 layers); the live image contract is the per-section `image_slot` booleans +
  `image-prompts.json`, and `assemble.py` auto-injects `[IMAGE-SLOT-cover]`.

## [3.40.0] - 2026-07-16 (local mode goes GLOBAL — any world city / province / country now triggers; three active US-gazetteer mis-anchors cured)

Operator asked why local mode only triggered on US cities — it should trigger for cities and provinces worldwide.
Correct on both counts — and the investigation found it was WORSE than
US-only. The 2026-05-22 design research
(`memory/research/location_intent_detection_2026.json`) had already specified the
international layer (country_default, CA/AU/GB ISO codes, GeoNames worldwide),
but v5.0 shipped ONLY the US subset — the same Rule-6 disease family: a designed
contract with no executor. Live evidence: every project-echo regional-city article
(six regional cities) ran with
`local_intent=false`.

### What was actually broken (measured, pre-fix)

| Keyword | Old result | Disease |
|---|---|---|
| `chinese age-restricted products toronto` (and london/sydney/markham/hamilton/guangdong/canada/uk…) | `local_mode=false` | non-US never triggers |
| `premium tea shop ontario` | **Ontario, CA — the Californian city** | wrong country |
| `matcha vancouver` | **Vancouver, WA** | wrong country |
| `grow lights british columbia` | **Columbia, SC** | substring mis-match |

Tier 3 (spaCy) was no help even when installed: it resolved GPEs back through
the US-only Tier 2 gazetteer, and the runner defaults `allow_spacy=False`.

### Root cure

- **NEW `scripts/research/build_world_gazetteer.py`** (Rule 6: data ships with its
  executor) — downloads GeoNames dumps (CC-BY, attribution embedded) and emits:
  - `world_countries.json` — 252 countries + curated aliases (uk/usa/uae/…)
  - `world_admin1.json` — 3,814 states/provinces worldwide (Ontario, Guangdong,
    Queensland, England, …) with a **member-city-population size proxy**
  - `world_cities.json` — 33,961 cities ≥15k population
- **`_detect_local_intent.py` Tier 2 rewritten**: n-gram hash lookup (0.06 ms/call
  warm; replaces the per-name regex scan), match order regions → countries →
  US states + world admin1 → cities → trailing state/province codes (CA `ON QC
  BC…` + AU `NSW QLD…` with the same ALL-CAPS discipline as US collision codes).
  - **Longest-span rule** kills the `british columbia`→Columbia,SC class.
  - **Province-vs-city twins** ("ontario" = CA province AND Ontario, CA city):
    in-keyword cue → project target-market bias → size proxy (≥2x auto-pick;
    Bermuda's Hamilton parish no longer outranks Hamilton, ON) → `ambiguous=true`
    for the orchestrator to surface. Same-country containment twins (tokyo/
    dubai/quebec city-in-own-province) resolve to the city, no fake ambiguity.
  - **Collision gate**: curated English-word names (nice/china/turkey/sale/…) +
    single-token world cities <50k population require a COUNTRY-CONSISTENT
    second geo cue ("tea shop nice france" ✓; "for sale in Texas" must not
    anchor Salé, Morocco; "How to set up a yoga studio" must not anchor "To",
    Burkina Faso).
  - **`_NON_PLACE_PHRASES` brand mask** — the v5.0 xfail class (Indiana Jones,
    Maine Coon, New York Times, Manchester United) is now FIXED, tests un-xfailed.
  - US behavior preserved: full-state-name-over-city precedence, `--service-area-states`
    contract, all 24 pre-existing detector tests pass unchanged.
- **`local_intent_runner.py`**: derives `project_countries` from
  `business-context.json :: location.target_markets` (worldwide/global ⇒ NO bias;
  `UK`→GB; `EU` contributes nothing; fallback `location.country`) and passes it
  to the detector; `--countries CA,GB` CLI override; result JSON now carries
  `project_countries` + gate `notes`.
- **`verify_post.py` check 27**: short code forms now match case-sensitively —
  with global anchors, `containing_state="ON"` under IGNORECASE matched every
  English "on" and made the density check a fake gate (Rule 12; the same latent
  bug existed for US collision codes IN/OR).

### Rule-11 fan-out (all layers updated)

`skills/seo-blog/SKILL.md` step 5 (worldwide contract + ambiguity handling) ·
`docs/local-seo-quickstart.md` (tier table, YAGNI deferral overturned, limitation
№1 marked fixed) · `schemas/state.schema.json` (canonical/country/containing_state
descriptions) · `templates/local-state-pillar.md` + `local-city-page.md` (global-scope
notes: "state" = any admin1; swap US-flavored institutions/locale) ·
detector/runner docstrings.

### Tests

`tests/test_local_intent_global.py` NEW — 65 tests: world cities (incl. every
project-echo regional batch target), provinces/countries, cross-country disambiguation
+ project bias, collision gating, brand mask, US regressions, and a Rule-10 SEAM
test driving `local_intent_runner.run()` against real business-context.json +
state.json round-trips. `test_v5_local_pipeline_integration.py` xfail block
converted to hard negatives.

### 2026-07-17 full-pipeline audit hardening (ships in this release)

A four-track audit (15 recent task runs · subskill/subagent wiring · uncommitted
diff coherence · release-goal verification) confirmed all 15 recent articles ran
the complete 45-stage flow with genuinely-passing gates and draft-only posts —
and surfaced the following defects, all root-cured here:

- **CORE-EEAT O01/O02 still scored the RETIRED bracket markers** (Rule 6: the
  revised `core-eeat-80.md` contract had no executor). Markers are forbidden and
  stripped upstream, so both items were PERMANENTLY false — a fixed −2.5-pt
  depression that held 13 of 15 recent articles at 75–78.75, just under the SHIP
  threshold of 80. `core_eeat_scorer._check_O` now detects plain-prose
  information-gain signals (corrected-common-error / trade-off / comparison-
  synthesis incl. data tables / number-in-context); O01 = ≥2 distinct types,
  O02 = ≥1. All three spot-checked recent drafts earn both honestly.
  `tests/test_core_eeat_o_dimension_plain_prose.py` (7 tests).
- **`core_eeat_scorer` CLI dropped `--project-slug`** — main() parsed it but
  never passed it to `score()`, so the C09/C10 project-pattern cure (v3.39.1)
  was dead at the exact seam `run_quality_gates.py` drives (Rule 10). Fixed +
  CLI-seam regression test.
- **Marker-retirement fan-out completed (Rule 11 residue):** the format-system
  modifier is renamed `information-gain-markers` → **`info-gain-prose`** across
  format-selector, 25 templates, digest_artifacts.py; `agents/seo-auditor.md` no
  longer orders the retired lint (weight-8 row now reads core_eeat O01/O02);
  seo-checklist-2026 rows E8/E9/G4 restated; ai-citation-patterns verify block
  updated; section-drafter no longer loads the retired reference into writer
  context; garbled sed artifacts ("original datas", "(plain prose)s", a mangled
  casual.md sample) repaired. Guard test extended: no layer may invoke the
  retired lint or use the retired modifier id.
- **16 of 34 agent files used `allowed-tools:` — a SKILL.md key that agent files
  IGNORE — so those agents silently ran with ALL tools.** Least-tool isolation
  (writer "physically offline", head-of-research "no Bash/Web", publisher "only
  WP-REST-mutating agent") was dead the whole time; confirmed live in the session
  agent registry. All 16 flipped to `tools:`; linker's stale list reconciled to
  its real needs (`+Write` for linker-log.json, `+Bash` for the Rule-8
  competitor check) with the required Bash+WebFetch rationale note;
  schema-validator got the same rationale note; entity-extractor lost WebFetch
  while parked. `tests/test_agent_frontmatter_tools_key.py` pins the key, the
  writer/head-of-research isolation, and the rationale rule.
- **Two Rule-12 existence-only gates closed:** `citation-capsule-result.json`
  carries `passed` (coverage ≥ target) that nothing read; `finalize-result.json`
  could carry an `{"error": ...}` payload and still auto-satisfy its stage. Both
  now sit in `_PASS_FLAG_REQUIRED` + `_GATE_STAGES` (both completion layers), and
  finalize stamps `passed` on every path.
  `tests/test_rule12_capsule_and_finalize_gates.py` (6 tests, drives the
  artifact-validity seam with real failing payloads).
- **ZERO subskills were discoverable at runtime**: plugin.json registered
  `"./subskills"`, but discovery scans a registered path for IMMEDIATE
  `<name>/SKILL.md` children and subskills live two levels deep — so every
  user-invocable subskill command (/batch, /status, /switch, /cost, …) was
  silently unreachable. Each category dir is now registered individually.
  `tests/test_plugin_manifest_skill_paths.py`.
- **Orphans parked honestly (wire-vs-retire):** `agents/entity-extractor.md` +
  `subskills/cross-cutting/entity-optimizer` (the Wiki-Phase pair — nothing
  routes to either) and `subskills/build/youtube-embed` (its trigger
  `brief.embed_youtube` is set/read by nothing) now carry PARKED banners +
  `disable-model-invocation`. Wiring or deleting them is a product decision.
- **Repo hygiene:** session debris (`probe_*.txt`, `scratchpad/`,
  `scripts/_local/`) deleted/gitignored.
- **Erratum for [3.39.0] below:** its headline says "188 posts repaired across 7
  projects" while its own per-project breakdown lists 8 projects summing to 191.
  The reinject CLI prints its report to stdout without persisting an artifact,
  so the true count is unrecoverable — treat the breakdown (191/8) as the better
  source. Follow-up: teach `reinject_article_css.py` to write a report JSON.

Known gaps recorded, deliberately NOT changed here: `local_intent_runner` has no
deterministic orchestrator backstop (SKILL.md step-5 bash block is the only
executor — it did run in all 15 audited tasks); reviewer score is not re-run
after post-review image-QA regen touches draft.md (lints do re-run; images are
not review content by design); geo-audit.json remains schema-unpinned
(informational only — quality.json re-derives its facts deterministically). The
five project-echo regional-city drafts (Burlington/Oakville/Richmond Hill/Kitchener/
Vaughan) were built pre-v3.40.0 with `local_mode=false` and are refresh
candidates now that the detector resolves them correctly.

## [3.39.1] - 2026-07-16 (reconstructed entry — eight batch-session cures from 2026-07-14..16 that shipped without documentation; the version jumped 3.39.0 → 3.40.0 over them)

These cures were built during the project-bravo/project-foxtrot/project-echo batch sessions
and are committed together with v3.40.0. Documented here retroactively so the
paper trail matches the code (found by the 2026-07-17 audit).

1. **Info-gain-marker RETIREMENT** (the big one): bracketed scaffold markers
   (`[ORIGINAL DATA]` family) are forbidden — render_lint L6 already hard-vetoed
   what ~30 instruction-layer files still ORDERED writers to emit. Every layer
   (agents/editor-in-chief, head-of-research, humanizer, writer; subskills
   rewrite + section-drafter; ~12 references; ~16 templates) now says the same
   thing: information gain is PLAIN PROSE, and absence of first-party experience
   is an honest 0, never a fabrication. `references/seo/information-gain-markers.md`
   survives only under a RETIRED banner.
   `tests/test_no_layer_demands_banned_scaffold_markers.py`.
2. **CORE-EEAT C09/C10 read the PROJECT's mandatory_sections h2_pattern**
   (project-bravo "The Last Sip" / default "Frequently Asked Questions" never
   matched the old hardcoded regexes — C10 failed on essentially every article
   ever scored); `run_quality_gates.py` passes `--project-slug`.
   `tests/test_core_eeat_mandatory_section_detection.py`.
3. **assemble.py conclusion-stub detector** uses that same project h2_pattern
   (duplicate "The Last Sip" stub bug). `tests/test_assemble_conclusion_gentle_label.py`.
4. **ai_tells P7 no longer fires inside References/Further Reading** — verbatim
   cited titles containing "comprehensive" imposed an uncleable +4 ai_slop
   floor. `tests/test_ai_tells_citation_title_false_positive.py`.
5. **cta_tone_check**: CBSA/CRA/TVPA/TPAPLR government/regulatory acronyms
   allowlisted (project-echo Ontario series cites CBSA personal-exemption rules; the
   all-caps rule read them as shouting).
6. **`file_lock.is_locked()` — OS-lock liveness instead of sidecar existence**
   (⚠️ completes v3.39.0: the orchestrator hunk calling `is_locked` was swept
   into commit 9cc674b by the parallel-DEV axis (Rule 7 §4), so HEAD@3.39.0
   alone raises AttributeError on `--action reset`; this half MUST ship with
   it). Reset also preserves check-stage inputs. `tests/test_reset_lock_liveness.py`,
   `tests/test_reset_preserves_check_stage_inputs.py`, rewritten
   `tests/test_reset_and_history_selfheal_seam.py`.
7. **real_brand_image_pipeline no-product sentinel**: a brand of
   `"none (landmark ...)"` is no longer formatted into a product-photo search
   query (which had shipped a box literally reading "NONE" plus an Unsplash+
   watermark); the slot records `skipped`. +2 tests in
   `tests/test_real_brand_image_pipeline.py`.
8. **Category-cap policy seam test** pinning orchestrator behavior:
   `tests/test_orchestrator_category_cap_respects_project_policy.py`.

## [3.39.0] - 2026-07-14 (stat-card root cure: the "By the Numbers" grid shattered its values mid-word — CSS hardened, value contract now machine-enforced, 188 live posts repaired)

project-foxtrot shipped `chlorophyll` rendered as **`chloroph / yll`**. That was not a
one-off: a survey of **591 published/draft posts across all 10 projects** found
**57 posts carrying a stat grid and 40 of them (70%) containing at least one value
that breaks the layout** — **107 of 365 stat values (29%) outright, plus 86 (24%)
sitting on the wrap boundary**. Most were already live.

### Root cause (two independent layers, both fixed)

**1. CSS could not survive a real value.** `minmax(150px, 1fr)` + a flat
`font-size: 2em` left the value **~110px of content box at ~34px type: about 5-6
characters**. Anything longer overflowed, and because the pillar wrapper sets
`word-wrap: break-word` (a deliberate long-URL guard) the overflow **inherited into
the value and chopped the word in half**. Every project's CSS carried the same
`minmax(150px, 1fr)` — the defect was generated identically 10 times.

**2. The content contract was under-specified and had no executor (Rule 6).**
`references/style/visual-design-components.md` said "the bold leading run becomes the
big number" but set **no length limit, forbade no descriptive words, and nothing
enforced it**. Its own third example (`**30 to 75 percent**`) was already too long.
Writers therefore emitted, in descending frequency:
  - range + unit + period — `$3,000 to $12,000 per month` (~45 cases)
  - number + glued-on noun phrase — `30% more chlorophyll` (~30)
  - **a bold that is not a number at all** — `Notched Izod verdict:` (~25; the grid
    was being used as a generic bold-led checklist)
  - colon-terminated label (~12)

### Fixes

- **`scripts/build/article_css_generator.py`** — the value can no longer chop mid-word
  at ANY width: column floor `150px -> 210px`; value `font-size` now `clamp()`s DOWN
  instead of overflowing; **`overflow-wrap/word-break/word-wrap: normal` + `hyphens: manual`
  explicitly CANCEL the inherited `break-word`**; `min-width: 0` grid blow-out guard;
  `text-wrap: balance`. The mobile block no longer re-sets a flat `1.7em` (which would
  have overridden the clamp). A bad value now degrades gracefully instead of shattering.
- **`scripts/lint/stat_grid_check.py`** (NEW) — the executor the contract never had.
  S1 value >16 chars · S2 any word >10 chars · S3 value does not start with a number
  · S4 colon-terminated label · S5 item count outside 3-6 (warn). S1-S4 are hard defects.
- **Wired as a real gate** (Rule 11: both layers changed together) — `stat-grid-check`
  stage in `orchestrator.STAGES`, `stat-grid-lint.json: passed` in `_PASS_FLAG_REQUIRED`,
  `stat-grid-check` in `run_pipeline._GATE_STAGES`, `stat-grid-lint.json` in
  `_FRESHNESS_VS_DRAFT` (a repair edit cannot ride a stale pass), and a
  `check_stat_grid` hard check in `pre_publish_gate` (a MISSING artifact fails: the
  producer must have run — Rule 12).
- **Contract fan-out (Rule 11)** — the value contract is now stated in
  `references/style/visual-design-components.md`, `agents/visual-designer.md`,
  `agents/writer.md`, `subskills/optimize/visual-designer/SKILL.md`, and the
  orchestrator's visual-designer `dispatch_prompt`. A guard in only one layer
  re-creates the bug at the untouched source.
- **`scripts/wordpress/reinject_article_css.py`** (NEW) — closes the **3-hop
  distribution problem**, which is why a CSS bug "appears in other projects" and does
  not go away when the generator is patched. The stylesheet exists at three levels:
  *skill* (the generator, 1 copy) → *project* (`projects/{slug}/brand/article-css.css`,
  10 copies) → ***post* (inlined into every published body, N copies)**. Hop 2→3 only
  ever happened at publish time, so **every live post keeps the stylesheet that was
  current the day it shipped, forever**. This tool re-injects a project's current CSS
  into existing posts, touching ONLY the `<style>` block (it refuses to run if the body
  would change) and verifying each write.
- **`tests/test_stat_grid_contract.py`** (NEW, 21 tests) — every real-world breaker from
  the survey, the CSS rules (asserted through the REAL `generate()` entrypoint, not a
  hand-built dict), and the gate SEAM (Rule 10): both registries, the freshness set, and
  pre_publish_gate blocking on both a failing verdict and a missing artifact.

### Repair

All 10 project stylesheets regenerated; **188 existing posts re-injected with the fixed
CSS across 7 projects** (loamwright 44, project-juliet 44, project-kilo 41, project-echo 33,
project-hotel 21, project-lima 3, project-bravo 2, project-foxtrot 3), 0 errors, every write verified.
A published loamwright post that previously chopped now measures **0 mid-word breaks**.
Content repair (rewriting the 107 offending bold values into value+label form) is a
separate follow-up — the CSS fix makes them render correctly in the meantime.

## [3.38.4] - 2026-07-11 (category-duplication root cure: publish is resolve-only + dedupe repair tool — project-hotel 8 live dup pairs repaired)

Deep re-audit of the &-entity category-duplication class (the v3.19.2 / 2026-06-21
fix cured the *matching* bug; this release closes the four residual holes found by
the 2026-07-11 project-hotel investigation). All-projects live scan (10 sites,
categories + tags): only project-hotel carried damage — 8 duplicate pairs minted
2026-06-16→20, now repaired and live-verified clean. New regression suite:
`tests/test_category_dup_root_cure_2026_07_11.py` (11 tests). Full suite green.

### Fixed (skill level — the pipeline, benefits every project)
- **Publish-time category creation is now FORBIDDEN by default** (the structural
  root: even with perfect matching, any typo'd/stale category name minted a
  parentless top-level term at publish). `wp_publisher` Step 2 runs
  `create_missing=False`; an unresolvable name ABORTS the publish before any WP
  write with a fix-it message (Rule 12: fail loudly, never mutate the curated
  taxonomy silently). Explicit opt-in: `--allow-create-categories` /
  `PublishInput.allow_create_categories`. Tags stay create-on-the-fly.
- **`wp_taxonomy.get_or_create_terms` post-create `missing` recompute was not
  entity-aware** (`c.name.lower()` on WP's entity-encoded echo) — freshly created
  `&`-names were re-reported missing. Now uses `_norm_name` on both sides.
- **Legacy `scripts/analysis/wordpress_publisher.py` still carried the raw
  `.lower()` name match** (the exact pre-v3.19.2 bug; unwired but importable).
  Now entity-aware via `_norm_term_name` + module docstring marks it deprecated
  for pipeline use (canonical: `scripts/wordpress/wp_publisher.py`).
- **`category_selector` partial ID-resolution is now loud**: when a name can't be
  resolved against the live snapshot, it warns that `meta.categories` and
  `meta.category_ids` will carry different lengths and the unresolved name will
  never be assigned (stale-snapshot hint). Previously a silent drop.
- **`snapshot_categories.snapshot()` return-only trap**: new `write_snapshot()`
  actually persists `categories-live.json`; callers that "refreshed" via
  `snapshot()` wrote nothing (Rule-12 class: the report said refreshed, the disk
  said otherwise).
- **Doc-rot / Rule-11 fan-out**: `skills/phase-publish/SKILL.md` pointed at
  nonexistent `scripts/publish/wordpress_publisher.py`; `agents/publisher.md`
  Step 3 still instructed `--create-missing` for categories. Both now state the
  resolve-only contract; `subskills/publish/wordpress-publisher/SKILL.md` and
  `subskills/init/wordpress-category-setup/SKILL.md` document detection/repair.

### Added
- **`scripts/wordpress/dedupe_categories.py`** — standing detector + repairer for
  already-minted duplicate categories. `--check` (exit 1 on dups; CI-gate-able) /
  `--apply` (backup → reassign every affected post to the canonical config-listed
  term → fix `rank_math_primary_category` → delete strays → write 301 rules to
  `projects/{slug}/.seo/category-dedupe-redirects-{date}.json` → refresh
  categories-live.json). Pure planning core (find_duplicate_groups /
  choose_canonical / plan_post_updates / build_redirect_rules) is unit-tested on
  real REST shapes (entity-encoded names).

### Repaired (project level — project-hotel live site)
- 8 duplicate pairs (253/316, 256/304, 266/370, 279/350, 288/380, 289/323,
  291/328, 298/322): 11 posts reassigned to canonical terms, 8 strays deleted,
  62 categories remain (= curated 8 hubs × 53 subs + Uncategorized), /blog/
  front-end verified clean, local snapshots refreshed. Backup + redirect rules in
  `projects/project-hotel/.seo/`. Outstanding manual step: import the 8 redirect
  rules in Rank Math → Redirections (REST route for redirections doesn't accept
  URL-source rules). project-kilo's 2026-06-21 orphans confirmed already cleaned;
  all other 8 sites scanned clean (categories AND tags).

## [3.38.3] - 2026-07-10 (parallel-batch root cures: sanctioned workspace reset + record-store self-heal, CTA heading-diversity contract, fabricated-experience red line, keyword-density/quality Rule-12 gates, TOC component-heading exclusion, proof-point any-match, table-chart autofit, image-qa write-time schema)

Root cures from TWO parallel audit sessions run over the 2026-07-09 batches
(project-kilo: posts 37905/37911/37899 — project-juliet: posts 31972/31978/31984 —
loamwright: posts 1714/1720/1726; all drafts, verify 24/24, reviewers 87-91).
Combined release from one shared working tree. New regression suites:
`tests/test_reset_and_history_selfheal_seam.py` (8 seam tests) + acronym cases
in `tests/test_cta_tone_check.py` + `tests/test_toc_component_exclusion_v3383.py`
+ `tests/test_brand_fact_proof_point_any_match_v3383.py` +
`tests/test_chart_table_autofit_v3383.py` + `tests/test_gate_contracts_v3383.py`.
Full suite green: **1112 passed**.

### Fixed (project-kilo re-angle incident — the stage-skip class)
- **Hand-rolled workspace resets silently skip stages (6 skipped live).** A
  mid-batch re-angle (Rule-1 cannibalization catch) was hand-reset by truncating
  `state.json::stage_history` + deleting primary artifacts — but completion
  state lives in THREE stores (stage_history, `pipeline-checklist.json`, and
  expected_outputs/evidence artifacts). `_stage_complete()` stayed satisfied by
  the surviving checklist + `*-result.json` files, so the runner jumped
  chart-render, image-pipeline-fork, citation-inject,
  finalize-references-signature, chart-rerender, and category-selector: 41
  unresolved `[claim:]` markers reached the draft and References stayed a stub
  (repaired by hand-running the stage scripts). Root cure:
  **`orchestrator --action reset --stage X --reason "..."`** — the sanctioned
  reset clears ALL THREE stores for the target stage and everything after it,
  deriving the deletion set from the STAGES table (Rule 6: single source of
  truth; new stages are covered automatically). Refuses under an active
  `.pipeline-driver.lock`; warns (never deletes) an already-created WP post;
  prunes this task's fingerprints from the project `cta-history.json` when
  cta-record-history is re-armed. Documented in `skills/seo-blog/SKILL.md`
  ("Re-angling: use reset, NEVER hand-edit state"; fresh task_id preferred for
  full re-angles).
- **RC-A stamp guard read only ONE record store → permanently desynced audit
  trail.** `next_stage()`'s auto-satisfy stamp (and the conditional-skip stamp)
  checked only the checklist, so stages jumped by the partial reset were never
  re-stamped into stage_history (38 records vs 44 on sibling articles). Both
  guards now ask BOTH stores (`_history_status()` added as the mirror of
  `_checklist_status()`) and re-stamp whichever is missing, preserving explicit
  `skipped` status — the audit trail self-heals. Seam-tested per Rule 10
  (`next_stage()` driven with real desynced stores, not helpers in isolation).
- **CTA heading diversity was undocumented at the writer layers (Rule 11
  fan-out miss).** `cta-diversity-check` hard-fails a heading used by the
  project's last 5 articles, but `agents/cta-writer.md` said "pick freely
  within the lists" and the dispatch_prompt only said "read cta-history.json"
  — so a single-configured-heading project (project-kilo: "Talk to the factory")
  failed the gate on every 2nd+ batch article. Both layers now state the
  rotate-per-history contract explicitly.
- **`cta_tone_check` all_caps false-positived on technical acronyms.** "ASTM"
  tripped the shouting rule twice in one correct CTA and forced a hand-edit.
  ALLOWED_ACRONYMS extended with standards bodies + polymer names (ASTM, ANSI,
  NIST, PEBA, PEEK, PEKK, CIELAB, ROHS, HDPE, LDPE, PVDF, PCTG); regression
  tests pin both directions (acronyms pass, genuine shouting still flagged).
- **Writers fabricate first-person EXPERIENCE anecdotes on greenfield brands.**
  Three invented anecdotes ("40 skeleton minis for a client's demo table in Q1
  2026", "complaint spools returned by buyers", "two years of sampling") were
  hand-stripped across the project-kilo batch. The existing red lines covered
  fake sources/statistics and self-fact NUMBERS (brand-fact-check), but a
  fabricated anecdote carries NO number to contradict `business-context.company`
  — no deterministic gate can catch it, and
  `references/seo/information-gain-markers.md`'s `[PERSONAL EXPERIENCE]`
  template ("specific time/place + what you did") is exactly the fabrication
  shape. Rule-11 fan-out: `agents/writer.md` (new "Never fabricate an anecdote"
  red line + marker precondition), `references/seo/information-gain-markers.md`
  (hard precondition on the marker), `subskills/build/section-drafter/SKILL.md`
  (company_facts gates experience too). Greenfield brands legitimately score
  lower on the E-E-A-T experience dimension; fabricating past it is a T04.
- Investigated, NO fix needed: em-dashes inside References entries (official
  ASTM/ISO titles) are **exempt by design** — `render_lint` L12 excludes
  everything from the References H2 onward; the hand-fixes applied mid-batch
  were unnecessary.

### Fixed (parallel project-juliet audit session, same release)
- **keyword-density-check wrote a verdict nothing read (Rule 12).**
  `keyword-density.json` now carries `passed` (false ONLY above the documented
  1.5% hard-stuffing ceiling; the under-band "too_low" stays informational),
  and the gate is wired into `run_pipeline._GATE_STAGES` +
  `orchestrator._PASS_FLAG_REQUIRED` — before this, every legitimately-sparse
  long-tail article logged a scary exit:1 while a real >1.5% stuffing case had
  NO enforcement layer at all.
- **quality-gates verdict now blocks with FRESH ai_slop.** `quality.json`
  carries `passed=all_pass` and is gated in both layers; because quality.json
  is freshness-checked vs draft.md, a post-humanizer ai-slop regression
  (gold-filament 2026-07-09: 16.13 → 24.25 after linker/geo/cta) can no longer
  sail to publish on the stale humanizer-report verdict.
- **pre_publish_gate.check_humanizer prefers the fresher ai_slop measurement.**
  Companion to the gate above (defense in depth): the humanizer runs EARLY in
  optimize and linker/geo/visual/cta all edit the draft after it, so the gate
  now compares mtimes and reads `quality.json :: ai_slop.score` whenever it is
  newer than humanizer-report.json (and the humanizer report when the operator
  just re-humanized and has not re-run quality gates yet). Before this, the
  publish-blocking ai_slop adjudication ALWAYS read the stale early report.
- **C01 fabricated-citation veto fired on encoding, not semantics (Rule 9).**
  `cite_scorer._is_broken_ref` ignored `url_verified: true` when a status int
  was present, so the SAME bot-walled-but-Crossref-verified DOI produced
  opposite gate verdicts depending on the fact-checker's encoding: int `403` →
  false C01 veto (tpu-vs-pla core-EEAT BLOCKED at 50, manual citations.json
  surgery to clear), string `"bot-403"` → pass. An explicit `url_verified: true`
  is now authoritative over any status encoding; the recording contract
  (url_verified:true + resolved_status:"bot-403" STRING + resolution_note, and
  url_verified:false for genuinely unverifiable refs) is fanned out per Rule 11
  across `agents/fact-checker.md`, the orchestrator fact-check dispatch_prompt,
  and `subskills/build/fact-check-and-citation/SKILL.md`.
- **Citation-capsule lint attributed capsules to component H2s (false
  "missing capsule" on 4 sections across 2 articles).** Writers legitimately
  render a stat_grid as a real `## By the Numbers` H2 and often place the
  section's capsule after it; `iter_h2_sections` treated the component heading
  as a section boundary, so the capsule was credited to the (structurally
  skipped) component section and the PARENT content H2 false-failed — forcing
  redundant capsule insertions the independent reviewer then flagged as
  duplication. `citation_capsule_lint` now folds component sections
  (stat_grid / glossary / at_a_glance / checklist, classified via the
  `scripts/_core/component_headings` single source) back into their parent
  before detection; TL;DR / conclusion-class / CTA headings remain boundaries.
- New seam suite `tests/test_v3383_gate_cures_seam.py` (14 tests): the three
  C01 recording shapes through the real core-EEAT veto path, capsule-after-
  stat-grid attribution, the real keyword-density CLI at both bands, the
  Rule-11 mirror-map sync assertion, `_gate_passed` on failing/legacy
  quality.json, and check_humanizer mtime preference in both directions.
### Fixed (loamwright 2026-07-09 commercial-service batch — 4 root cures)

- **TOC listed visual-component H2s as sections (100% of articles).**
  `anchor_link_builder.build_toc` blindly listed EVERY H2 — including the
  component boxes (`## TL;DR` / `## Glossary` / `## By the Numbers` /
  `## At a Glance`) and the `## Table of Contents` heading itself. All 3
  loamwright articles shipped the leak; 2 were reviewer-bounced and every TOC
  was hand-cleaned. The TOC builder now consults the
  `scripts/_core/component_headings` registry (restricted to the box ids;
  `checklist`-titled real sections and the mandatory-sections-legal
  `The Bottom Line` conclusion are whitelisted) — anchors are STILL injected
  on component headings (the CSS keys on `h2[id^="tldr"]` etc.), only the TOC
  listing excludes them. Companion contract fix: `tldr_box` on a SECTION spec
  now means "answer-first opening paragraph", never a nested `## TL;DR` H2
  (fan-out per Rule 11: `references/style/visual-design-components.md`,
  `subskills/build/outline-architect/SKILL.md`, `agents/writer.md`).
- **brand-fact proof-point false positive: any-match across candidates.** The
  proof-point check compared a sentence against EACH case study independently;
  loamwright documents TWO ecommerce case studies, so a CTA citing the first
  one's numbers verbatim (128K clicks/11.3M impressions/16 months) was flagged
  against the second (0→14.3K/7 months) and blocked the pipeline. The check now
  collects every subject-anchored candidate and flags ONLY when the numbers
  match NONE of them (violation reports `candidates_checked[]` + the closest
  candidate).
- **table-chart C1 overflow made physically impossible (autofit).** The table
  renderer used a FIXED row height and wrapped cells with no line clamp, so
  150-200 char cells drew past their row into neighbours (2 QA regen rounds in
  this batch alone; same class 2026-07-06). `data_chart_png._fit_table_layout`
  now computes the layout BEFORE drawing: per-row heights sized to the tallest
  wrapped cell, font stepping 19→13 when needed, ellipsis-clamp as the physical
  last resort; column HEADERS wrap to ≤2 lines inside their own column. Input
  side: table text budget (cells ≤~90 chars, headers 1-3 words) pinned in
  `agents/image-prompt-designer.md` + the orchestrator dispatch prompt.
- **image-qa-report schema drift now caught at WRITE time.** The QA subagent
  nondeterministically serialized per-slot `verdict` instead of the schema's
  `final_verdict` (+ missing `final_score`/`round_history`) and
  `pre_publish_gate` hard-failed an all-pass report at the very END of the
  pipeline. `image-qa-report.json` is now in the schema-validate hook's watch
  map (drift surfaces to the agent immediately), and the exact per-slot
  contract is pinned in `agents/image-visual-qa.md` + the orchestrator
  dispatch prompt (Rule 11 both layers).
- Minor: `pre_publish_gate.check_meta` no longer warns "selector may not have
  run" on a legitimate single-category article carrying resolved
  `category_ids` (one-primary-category is loamwright's documented convention);
  `cta_injector` docstring documents the sanctioned CTA-repair path (edit
  cta-draft.json → delete the stale block → re-inject; idempotency is
  heading-detection and will otherwise no-op); `skills/seo-blog/SKILL.md` loop
  documents transient subagent no-op/API-kill re-dispatch.

## [3.38.2] - 2026-07-09 (agency-service batch wiring root-cures: schema-generator contract inversion, agent workspace-path fan-out, schema.json shape guard, brand-fact URL digits, cta-writer anti-override)

Five root-cures for real incidents found LIVE while writing 3 loamwright
agency-service articles (posts 1638 / 1645 / 1651, all drafts, verify 24/24).
Two subagents misbehaved and were hand-corrected mid-run; both are now cured at
the source. Regression suites: `tests/test_schema_generator_wiring_2026_07_09.py`
(5 tests) + the URL-digit cases added to
`tests/test_brand_fact_check_team_proof_points.py`. Full suite green: 1065 passed.

### Fixed
- **schema-generator STAGE dispatched the read-only `schema-validator` agent to
  GENERATE (contract inversion).** `orchestrator.py` stage `schema-generator`
  set `subagent_type=schema-validator`, but `agents/schema-validator.md` is a
  haiku-model, read-only *validation* role ("Forbidden: Write", "❌ Generate
  schema"). Dispatched to generate, it returned a fabricated summary (FAQ
  questions NOT in the draft) and wrote no `schema.json`. Root cure: new
  `agents/schema-generator.md` (opus, `tools: [Read, Write, Bash]`, builds
  FAQPage VERBATIM from the draft) + stage repointed to it + dispatch prompt
  hardened with exact `memory/workspace/{task_id}/` paths and a "you MUST write
  the file" clause.
- **16 agent defs documented the WRONG workspace path `workspace/{task}` instead
  of `memory/workspace/{task_id}` (Rule 11 fan-out).** With cwd = plugin root,
  the `linker` resolved that to a bogus `<root>/workspace/<task>/`, wrote an
  8.7KB partial draft + its report there, and the real draft got ZERO links.
  Only `cta-writer`/`visual-designer` had been fixed previously. Root cure:
  fan-out corrected the path in all 16 agent files (88 occurrences) and the
  stale `schema_graph.json` filename → canonical `schema.json` (16 occurrences
  across agents + 3 subskills/references; the publisher only ever read
  `schema.json`).
- **`schema.json` had NO pre-publish shape guard.** It is a hard
  `wordpress-publisher` input yet `_artifact_valid` only checked JSON-parseable,
  so a fabricated / 1-block / empty schema passed and failed only LIVE at
  `verify_post` check 17 (head schema isn't fetchable pre-publish, so the
  ≥2-body-block minimum falls entirely on this file). Added a shape guard
  (blocks is a list, ≥2 entries, each `ld_json.@type` present) so the failure
  surfaces at the schema-generator stage, not as a late manual patch.
- **`brand_fact_check.py` false-fired on a founder-avatar CTA image URL's date
  digits.** `![Lewei Zhang](https://.../uploads/2026/06/x.jpg)` leaked `2026`/`06`
  into the proof-point digit scan, hard-vetoing a CORRECT metric ("2 to 45 daily
  clicks in 90 days"). This hit every loamwright article with the avatar CTA
  banner. Root cure: `_URL_NOISE_RE` strips markdown image/link markup + bare
  URLs before the digit scan (orthogonal to the v3.38.1 word-boundary fix). +2
  regression tests.
- **`cta-writer` had no anti-override clause.** Article 1 failed `verify_post`
  check 29 because the dispatch prompt named `/contact-us/` while the brief
  resolved `/seo-consulting/` (the service-routing target check 29 enforces).
  Added a red line to `agents/cta-writer.md`: `cta-brief.json :: target_url`
  is the single source of truth and OVERRIDES any conflicting URL in the
  dispatch prompt / from the operator. (Note: the injector is idempotent-SKIP,
  so a wrong-URL CTA cannot be self-healed by re-running — a deterministic
  pre-publish URL-match + a replace/force path in `cta_injector` remain
  recommended follow-ups.)

### Known / deferred (documented, not fixed this release)
- `allowed-tools:` vs `tools:` frontmatter: 16 agents use `allowed-tools:` (the
  SKILL key), which agent frontmatter IGNORES → they run with ALL tools, so the
  designed isolation (e.g. writer "PHYSICALLY OFFLINE") is unenforced. Deferred:
  needs a per-agent tool-list audit first (e.g. `linker`'s declared list is
  missing `Write`), else enforcing restrictions would break agents.
- No proactive shared-canonical-facts channel across the N parallel writers, so
  time-sensitive facts (GBP Q&A removal, a canonical pricing band, an anchor mix)
  can drift between sections and are only caught reactively by the reviewer's
  numeric sweep. Recommended enhancement: outline-architect emits `canonical_facts`,
  section-drafter passes it to every writer.

## [3.38.1] - 2026-07-09 (weekly-digest run audit: 6 root cures — CTA skin idempotency, check-29/check-04 silent gaps, digest title hygiene, tone-gate avatar clash, brand-fact substring)

All six defects were found LIVE on the 2026-07-08 loamwright weekly digest
(task `loamwright_wk_20260708`, post 1628) and root-cured the same day.
Regression suite: `tests/test_weekly_digest_run_fixes_2026_07_08.py` (14
tests, incl. the inject-twice seam). Full suite green: 1058 passed.

### Fixed
- **CTA duplicate on pipeline re-invoke (Rule 11 fan-out miss from v3.38.0
  Task 2).** `cta_injector._scan_existing_cta` tested
  `classify_heading(...) == "cta"` exactly, but Task 2 split the registry
  into `cta` / `cta_quiet` / `cta_banner`. A quiet/banner-skin heading (e.g.
  "Let us make this the last audit you need") was invisible to the
  idempotency scan, so a `run_pipeline` re-invoke after any downstream gate
  failure re-injected a DUPLICATE CTA (shipped live to draft post 1628 before
  being caught by hand), and `placements_applied` stayed `[]`. Now matches
  any `cta*` component id.
- **verify_post check 29 silently skipped when `placements_applied` was
  empty** — the exact Rule-12 "gate that no-ops on a valid input" disease:
  the duplicated CTA above sailed through a 24/24 PASS verification. Check 29
  now unions `newly_injected` (written unconditionally at injection time) so
  an injected-but-unverifiable CTA can never skip.
- **verify_post check 04 could never pass on a `no_inline` cover-only
  digest.** It counted only BODY `wp-content/uploads` images from REST
  `content.rendered`; a digest whose sole image is the theme-rendered
  featured cover is a legitimate body-count 0, so even `--min-images 1`
  failed. The featured image now counts toward the total ONLY when the body
  carries zero images (never inflates inline-image articles).
- **digest_artifacts shipped a mid-clause-truncated, em-dash-bearing H1**
  ("SEO Weekly: … 42% (Pew) — while"). Three root cures: `_clean_theme()`
  strips em/en dashes from `theme_of_week` before it reaches
  title/abstract/tldr seeds (render_lint L12 hard-vetoes U+2014);
  `_fit_title()` now strips dangling connectives/punctuation after
  truncation (never ends on "while/and/with/…"); `_PADDING_SUFFIX` itself
  carried an em-dash and is now `" | Weekly Industry Brief"`.
- **cta_tone_check flagged the structural `!` in markdown image syntax** —
  every avatar-bearing CTA (`![name](photo)`, the v3.37
  `matched_team_member.photo_media_url` feature) hard-failed Gate 2, making
  the avatar feature structurally unusable. Image syntax is stripped before
  the pressure-punctuation scan; a real `!` still fails.
- **brand_fact_check proof-point anchor matched generic subject words as
  substrings.** Case-study subject "Ecommerce site" → "site" matched inside
  "publisher web**site**s" in third-party NEWS sentences, flagging the Define
  Media 42%/64 stats against the company's own 128K-clicks case study on
  every digest. Anchors are now word-boundary matches on DISTINCTIVE subject
  words only (generic tokens like site/page/store/company are skipped);
  distinctive-word overclaim detection (filament, manufacturer, …) is
  unchanged.

### Changed
- `skills/weekly-digest/SKILL.md` Step 3 researcher prompt hardened: every
  Tier-B item's headline/summary/stat must be EXTRACT-VERIFIED against the
  URL's actual content (the 2026-07-08 run's Tier-B researcher attributed a
  fabricated "Pew 69,000-search study" to a URL that actually hosts a Define
  Media Group analysis — caught by the fact-checker, Gate held); promo/CFP/
  webinar/conference-pitch items are explicitly out of scope.

## [3.38.0] - 2026-07-09 (CTA completion: ecommerce conversion-offer resolver + Gate 2 wired + all 5 projects populated)

Closes out the two gaps v3.37.0 honestly left open: the ecommerce
`business_model` branch (previously "designed and deferred to
project-launch") and Gate 2 (tone/voice, previously "NOT YET IMPLEMENTED").
Implementation plan (8 tasks, TDD):
`docs/superpowers/plans/2026-07-09-cta-completion-plan.md`.

### Added
- **Ecommerce conversion-offer resolver** (`scripts/wordpress/wc_catalog_sync.py`
  + `cta_brief_builder.py`'s new `business_model == "ecommerce"` branch):
  read-only `/wc/v3` catalog sync (products + categories, paginated, WP's
  400-past-last-page tolerated) writes `projects/{slug}/product-catalog.json`;
  the resolver matches the article's real content against the cached catalog
  via three ordered strategies — SKU-verbatim name match (cap 3), category
  token-overlap (≥50% + ≥1 non-generic token), configured `default_category`
  fallback — and emits a WooCommerce `[products ...]` shortcode. Root-caused a
  markdown-it quote-escaping bug (`"` → `&quot;` broke
  `shortcode_parse_atts()`) by emitting all shortcode attributes **unquoted**
  by construction (every value is guaranteed quote/space-free); live-reproved
  on a real project-hotel draft (37283, deleted after proof) confirming the
  quote-less form expands to real WooCommerce product-grid markup with zero
  literal `[products` text. `agents/cta-writer.md`, `cta_injector.py`, and
  `verify_post.py` check 29 all extended for the shortcode-bearing case
  (waived markdown-link requirement, WooCommerce grid-markup verification).
- **Gate 2 (tone/voice) — WIRED.** New `scripts/lint/cta_tone_check.py`: a
  deterministic hype/pressure lexicon lint on `cta-draft.json` (universal
  hype words, pressure phrases, `!`/ALL-CAPS with acronym allowlist,
  per-project `constraints.banned_phrases`, and — when
  `constraints.tone == "grief_safe"` — a grief-unsafe sublexicon). Wired as
  the `cta-tone-check` orchestrator stage between `cta-diversity-check` and
  `cta-injection`, gated exactly like Gate 5 (`passed:false` blocks and
  routes back to re-dispatch `cta-writer`).
- **All 5 remaining projects populated** with `conversion_offers` (3
  ecommerce: project-echo `no_person_blocks`, project-hotel `tone: grief_safe` +
  `banned_phrases`, project-charlie; 2 b2b-pattern: project-juliet, project-kilo).
  Cross-project contract test (`tests/test_all_projects_conversion_offers.py`)
  asserts schema validity, the ecommerce `default_category` resolves to an
  in-stock catalog category, b2b routing maps reference only real service
  slugs, and the `cta.enabled` AND-gate holds wherever `conversion_offers`
  exists.
- **`/init` Step 13.5 ecommerce branch flipped to ENABLED by default**
  (archetype D): runs `wc_catalog_sync` at init, presents synced categories
  with counts to recommend `default_category`, collects `fallback_url` +
  `constraints` (citing project-echo/project-hotel as the worked person-blocks/
  grief-safe examples), and documents the resolver's real 3-strategy
  matching behavior + periodic re-sync guidance. `cta-placement/SKILL.md`'s
  Config section documents the ecommerce shape alongside the existing
  b2b_services one.

### Fixed
- **CTA-1** (`brand_fact_check.py`): `_TEAM_MEMBER_MENTION_RE`'s blanket
  case-insensitivity let the NAME group match a lowercase phrase like "our
  agency" as a fake person name, masking a real fabricated team-member role
  later in the same sentence (`finditer` never re-examines consumed text).
  Scoped case-insensitivity to only the spans that need it; NAME now
  strictly requires capitalization.
- **RC-A generalization** (`orchestrator.py`): `next_stage()`'s RC-A
  auto-satisfy branch special-cased `stage.name == "cta-brief-builder"` to
  resync one in-memory state field post-`_record_stage()`. Replaced with a
  general `state = _read_state(task_id)` reload so ANY future stage whose
  completion writes a new condition field is immune by construction, not by
  a per-stage name check (Rule 10 class fix).
- **verify_post.py check 29 grid-scoping**: the WooCommerce-grid-markup
  requirement searched the WHOLE rendered page, but every real WooCommerce
  site carries `woocommerce` tokens site-wide (body class, cart widget,
  stylesheet id) — an EMPTY product grid (shortcode expanded to nothing)
  false-PASSED. Scoped the grid search and the literal-`[products` sub-check
  to content at/after the `xr-cta-box` CTA paragraph; tightened the grid
  regex to real grid markers.
- **cta_injector.py shortcode shape gate**: any non-empty string in an
  LLM-draft block's `shortcode` field was emitted verbatim and waived the
  markdown-link requirement — an injected `<script>` or unrelated shortcode
  would have shipped through. Added a strict shape gate matching only the
  quote-less `[products ...]` form the resolver actually emits; anything
  else is dropped with a warning and the link requirement re-applies.
- Ruff-clean on 2 files (`visual_density_check.py` E702/E741,
  `verify_post.py` F401 dead imports + a stale BeautifulSoup docstring claim
  that no longer matched the regex-anchored implementation).
- `schemas/business-context.schema.json`: `voice_default.pair` loosened from
  array-only to string-or-array (`oneOf`) — `title_validator.infer_register()`
  already handled both shapes; the over-strict schema was failing 3 real
  projects on a field the code supports.

### Live-verified (non-code)
- **Team Member media title** (`wp/v2/media/597` on loamwright): corrected
  the stale "Digital PR & Outreach Lead" to the canonical "SEM/Paid Search
  Lead" per official-pages authority, GET-verified post-PATCH.
- **GA4 `cta_click` snippet auto-install investigated** on loamwright: no
  REST-manageable code-snippet plugin exists (WPCode Lite is active but
  registers zero REST namespace in this install); made no WP changes,
  documented the investigation in `projects/loamwright/CLAUDE.md` — the
  manual wp-admin paste step stands.

## [3.37.0] - 2026-07-08 (CTA system redesign: service-aware routing + LLM-authored per-article CTAs + composable design system)

Full redesign of the site-wide CTA module — from a single static config
(9 total copy variants, one fixed heading, one generic offer for every
article) to a skill-level, business-model-aware capability where every
article gets a genuinely unique, LLM-authored CTA routed to the article's
matched service, backed by real team members and case-study proof points.
Design spec: `docs/superpowers/specs/2026-07-08-cta-system-redesign-design.md`;
implementation plan (17 tasks, TDD): `docs/superpowers/plans/2026-07-08-cta-system-redesign-plan.md`.

### Added
- **Three-stage CTA pipeline** replacing the single static `cta-injection`
  stage: `cta-brief-builder` (deterministic fact resolver — blog category →
  `service-routing-map.json` → matched service/team-member/proof-points from
  `business-context.json :: conversion_offers`; falls back to `meta.json ::
  categories` slugified when `state.brief.category` is unset, which is every
  real pipeline run today) → `cta-writer` (new LLM subagent
  `agents/cta-writer.md`, `xuanran-seo-blog-writer:cta-writer`, Read+Write
  only — composes per-article copy from a fixed building-block palette using
  ONLY facts in `cta-brief.json`) → reworked `cta_injector.py` (consumes
  `cta-draft.json` when present; byte-identical legacy static-variant path
  when absent).
- **Composable design-system building blocks** (native-markdown-only):
  circular avatar (real team photos), stat/proof line, quote-hook, real
  filled/outline buttons, card/quiet/banner visual skins.
  `component_headings.py` CTA registry expanded 6 → 21 phrases across 3
  component ids (`cta`/`cta_quiet`/`cta_banner`); all original phrases
  preserved. New CSS in `article_css_generator.py` (+ loamwright regenerated).
- **Quality gates, all WIRED and verified at the orchestrator seam:**
  Gate 1 fact-accuracy (`brand_fact_check.py` + new `team_member`/
  `proof_point` categories, token-set role matching to avoid false positives
  on natural title paraphrases); Gate 3 density ceiling
  (`check_cta_block_ceiling`, merged into the `visual-density-check` stage);
  Gate 4 routing correctness (per-block heading-registry validation in
  `cta_injector.py` + `verify_post.py` check 29 URL sub-check reading
  `cta-brief.json`); Gate 5 cross-article diversity (new
  `cta_diversity_check.py` + `cta-diversity-check` stage between cta-writer
  and cta-injection + `cta-record-history` stage after injection, recording
  only when `passed AND draft_source=="llm"`, file-locked per Rule 7).
  Gate 2 (tone) is honestly documented as NOT YET IMPLEMENTED — the
  humanizer stage runs before CTA text exists in the draft, so the
  originally-planned reuse was structurally impossible.
- **loamwright data:** full `conversion_offers` (13 services extracted from
  the live service pages), `company.team` (4 named specialists with real WP
  media-library photos), `company.proof_points` (3 real case studies + 3
  stats), `service-routing-map.json` (11 category pillars → service slugs).
- **`/init` Step 13.5 (Conversion Offer Strategy)** — every future project
  init collects this data automatically; b2b_services fully implemented,
  ecommerce branch designed and deferred to project-launch time (spec §7).
- **Retroactive founder-name audit** (`scripts/wordpress/fix_founder_name.py`):
  corrected stale "James" → canonical "Lewei Zhang" across 13 published +
  15 draft loamwright posts, live-verified; config/docs updated to match.

### Fixed
- **Backward compatibility hardening found during review:** projects without
  `conversion_offers` (5 of 6) were initially hard-halted by the new
  cta-brief-builder stage — root-cured with an always-written sentinel
  `cta-brief.json` + content-derived `cta_brief_present` condition + RC-A
  in-memory state re-sync in `next_stage()` (the v3.35.3 bare-reinvoke
  disease class), all proven at the real `run_pipeline.advance()` seam.
- Silent-styling-failure risk closed: an LLM-authored CTA heading not in the
  component registry now hard-fails the cta-injection stage per block
  (previously only the single static config value was validated).
- `verify_post.py` check 29: guarded against non-string `target_url` in
  malformed briefs (was an uncaught AttributeError crashing the whole
  live-verification run).
- `fix_founder_name.py`: WPClient kwarg (`json_body=`) and WP pagination
  (HTTP 400 past last page, not an empty list) — both found on first real run.

## [3.36.5] - 2026-07-08 (post-batch audit: schema-generator forbidden-types hardcoded across projects, loamwright missing wordpress schema config, manifest version drift)

Full audit of the 2026-07-08 3-article loamwright batch (posts 1535/1529/1541 —
`enterprise-seo-audit`, `google-seo-agency`, `top-web-design-firms`; all stages
completed or explicitly skipped with logged reasons, all provenance-stamped
artifacts present, verify 24/24 x3, one live hallucination incident caught and
corrected mid-run — see below). Two root cures + one manifest-hygiene fix.

### Fixed
- **schema-generator "Forbidden body types" hardcoded across ALL projects
  (Rule 9/12 disease):** `orchestrator.py`'s `schema-generator` Stage
  dispatch_prompt hardcoded the project-charlie project's exact
  `wordpress.seo_plugin_schema_provided` list ("Article, BlogPosting,
  Organization, Person, WebPage, WebSite, ImageObject, BreadcrumbList") as a
  UNIVERSAL constant, applied to every project regardless of that project's
  actual config or its absence. This silently disagreed with
  `scripts/validate/cite_scorer.py`, which reads the SAME config key directly
  and correctly credits nothing when it's absent. loamwright's
  `business-context.json` had no `wordpress` key at all (the only project of 6
  missing it) -- so cite_scorer.py assumed RankMath provided nothing in
  `<head>` and dinged CITE I01-I10 identity/trust items on every article
  (all 3 batch articles scored CITE=FIX, 72.5-75/100, instead of SHIP), while
  the SAME dispatch_prompt simultaneously told the schema-generator agent
  those exact types WERE already covered and forbidden from the body -- two
  code paths disagreeing about one fact. Root cure: `_schema_forbidden_types_text()`
  computes the clause per-project at dispatch time (extracted templating seam
  `_render_dispatch_prompt()`, called from `next_stage()`), reading the
  project's real config and falling back to an explicit "no policy declared"
  instruction (matching `subskills/optimize/schema-generator/SKILL.md`'s
  already-documented but previously-unenforced fallback) when absent. Also
  fixed the underlying loamwright data gap: a live `<head>` fetch (CF-bypass,
  no cache) on a published post found RankMath emits `Organization, WebSite,
  ImageObject, BreadcrumbList, WebPage, Person, NewsArticle` -- note
  `NewsArticle`, not `Article`/`BlogPosting`, so the old hardcoded list was
  wrong on 2 of 8 entries for this project even where it happened to overlap.
  Config now recorded in `projects/loamwright/business-context.json ::
  wordpress.seo_plugin_schema_provided`; the project's stale init-time
  "RankMath appears inactive" note in `CLAUDE.md` corrected accordingly.
  Seam tests: `tests/test_schema_forbidden_types_project_aware_2026_07_08.py`
  (6 tests, exercises `_render_dispatch_prompt` directly rather than assembling
  a full ~19-stage fixture, per Rule 10). Suite 785 passed.
- **Live hallucination caught mid-batch (process finding, not a code bug):**
  the `schema-validator` subagent, dispatched for the `top-web-design-firms`
  article's schema-generator stage, fabricated content for a DIFFERENT
  (nonexistent) article -- wrong slug, wrong FAQ questions, wrong platform
  list -- and never actually wrote `schema.json` to disk, despite its final
  report claiming success. Caught by verifying the file existed and its
  content matched the real draft before advancing the pipeline (the file
  didn't exist at all); re-dispatched with an explicit "you MUST use Read/Write
  on the real files, do not describe hypothetical actions" instruction, which
  produced correct output. All other subagent artifacts across the 3-article
  batch were spot-checked for the same failure mode (slug/keyword cross-match
  on every `schema.json`/`citations.json`) -- no other instance found. No code
  change; documented here as the "never trust a subagent's summary over the
  actual file" operating discipline this project's CLAUDE.md already states.
- **wp_publisher.py stale docstring example:** `_set_rankmath_meta()`'s
  docstring still listed `rank_math_robots` example values as
  `["index","follow",...]`, directly contradicting root CLAUDE.md Rule 3's
  warning that `"follow"` is not a valid enum value and 400s the POST. The
  enforcement code two lines below was always correct (filters against the
  real 6-value enum); this was a doc-only drift a future ad-hoc script could
  copy verbatim and reintroduce the bug. Corrected the docstring and the
  adjacent inline comment.
- **Manifest version drift:** `VERSION` file was stuck at `3.36.3` while
  `plugin.json`/`marketplace.json`/`CHANGELOG.md`/`scripts/__init__.py` already
  read `3.36.4` (the previous commit updated those but not the bare `VERSION`
  marker), and separately `install/claude-code/install.sh`,
  `install/claude-code/install.ps1`, and
  `install/wordpress-mu-plugin/seo-machine-yoast-rest.php` were still at
  `3.36.3`. `manifest_consistency_check.py --apply` resynced all 8 tracked
  files before this bump.

### Audit method (2026-07-08, in response to a direct user request)

Full CHANGELOG re-verification, v3.30.0 through v3.36.4: for each entry, the
1-3 most load-bearing claims were checked against CURRENT source (not
changelog text) via Read/Grep, plus a sweep for the old/bad pattern each fix
was supposed to eliminate. Result: every previously-shipped fix in that window
still holds -- no reverted fixes, no Rule-6-class dead documentation, no new
Rule-11 fan-out gaps. This is itself now the project's Nth independent
self-audit pass; see `memory/research/batch_audit_2026_07_08_v3365.json` for
the structured findings summary (batch execution audit, both root causes,
manifest drift, and the project-level-vs-skill-level separation answer).

## [3.36.4] - 2026-07-07 (live PHP-log audit: draft-create slug deferred past core's REST uniquifier warning)

Live loamwrightseo.com error-stream audit traced the recurring
`class-wp-rest-posts-controller.php:769/772 "Undefined property:
stdClass::$id/$post_parent"` warnings (31× in the docker-log retention window,
~6/day tracking the publish cadence, UA `XuanranSEO/3.2.0`) to WP core's
`create_item()`: a draft/pending create that carries a `slug` runs
`wp_unique_post_slug( $prepared_post->id, …, $prepared_post->post_parent )`
on two properties that never exist during a create. The REST *update* path has
no such block — verified by live A/B (create+slug → 2 warnings;
create-then-update-slug → 0 warnings, identical stored slug/status).

### Fixed
- **wp_publisher.py:** fresh CREATE posts without `slug`; the slug is applied
  in an immediate follow-up update inside the same try/rollback envelope. The
  idempotent re-publish PATCH path keeps its inline slug (update never warns).
- **hub_page_publisher.py `upsert_hub_page`:** draft/pending page creates defer
  the slug to a follow-up PATCH; explicit `status="publish"` creates keep the
  inline slug (that path never warned, and renaming a just-published URL would
  bait RankMath's redirect monitor). The PATCH response is adopted only when it
  echoes the created page id.
- Seam tests: `tests/test_rest_draft_slug_defer_2026_07_07.py` (5 tests — hub
  call-sequence contract ×3, wp_publisher create-payload AST tripwire,
  follow-up-update presence). Suite 779 passed.

## [3.36.3] - 2026-07-07 (second 2026-07-07 batch audit: assemble cover-mapping contract drift, duplicate join stage records, GFM-checkbox prevention layer, fact-checker em-dash red line)

Full audit of the second 2026-07-07 loamwright batch (posts 1508/1514/1520 —
all stages ran or were explicitly skipped with logged reasons for all 3, all
provenance-stamped artifacts present, verify 24/24 ×3, zero silent skips, one
`wordpress-publisher` record per workspace confirming the v3.36.2 driver-lock
cure held). Four residual defect classes root-cured; code fixes carry Rule-10
seam tests (`tests/test_batch_audit_fixes_2026_07_07b.py`, 8 tests; suite 774
passed).

### Fixed
- **assemble.py cover-mapping contract drift (Rule-11 class, live mis-placement
  ×2):** `_inject_missing_image_placeholders`'s fallback zip identified the
  cover by `is_featured` alone — but the CANONICAL image-prompts contract (the
  D5 slot-id fix) has the designer OMIT `is_featured` (the pipeline forces it
  later). Result: the cover joined the non-cover zip, `[IMAGE-SLOT-cover]` was
  injected inside the FIRST image section (observed in 2 of 3 drafts; harmless
  under `no_inline` because the publisher strips it, WRONG under inline mode)
  and every chart mapping was off-by-one-shifted (masked only because writers
  embedded their own placeholders). Root cure: cover identified by
  `slot_id == "cover"` OR truthy `is_featured`; maps to section 0 (after
  Abstract) in both shapes; chart zip no longer shifted.
- **Duplicate `image-pipeline-join` stage_history records:**
  `generate_images()` self-records the canonical join stage on EVERY invocation
  — and it is also the engine under `image_regen_slots.py` (the image-visual-qa
  regen path), so a cover regen appended a SECOND completed pair
  (`file_bus.record_stage_start` dedups only OPEN in_progress entries).
  Duplicate audit-trail entries are exactly the signal operators were told to
  trust after the v3.36.2 double-publish postmortem, so benign duplicates are
  not acceptable noise. Root cure: `_join_stage_already_completed()` guard —
  the first full run owns the record; regen/re-run invocations skip it
  (fail-open so a corrupt state file never blocks image generation).
- **GFM task-list checkbox prevention layer (Rule-11 fan-out of the v3.36.2 L13
  gate):** the DETECTOR existed (render_lint L13) but no writer-facing doc
  forbade the syntax, so a writer emitted `- [ ]` from habit when realizing a
  `checklist` design component (caught pre-assembly in the live batch; would
  have been an L13 repair round-trip). Prevention added where writers actually
  read: `references/style/markdown-authoring-conventions.md` NEW Rule 7 +
  L12/L13 validation row + quick-reference "Checklist" row, and
  `references/style/visual-design-components.md` Component 5
  checklist-realization note.
- **Fact-checker em-dash red line (Rule-11 gap in the em-dash contract):** the
  zero-em-dash contract covered writer/humanizer/linker/geo/visual-designer but
  NOT the fact-checker, whose draft corrections introduced em-dashes in 2 of 3
  articles (one propagated into four sections alongside a corrected stat). The
  humanizer backstop cleans them when it runs after, but the contract hole
  guaranteed churn. Added the red line to BOTH loading paths per Rule 11:
  `agents/fact-checker.md` ("Style red lines for text YOU write into the
  draft") + the orchestrator `fact-check-and-citation` dispatch_prompt.
- **Brittle tag-config count pin:** `test_tag_seo_baseline_meta_passthrough`
  hardcoded `len(entries) == 122`, failing on every HEALTHY config growth (the
  2026-07-07 curated pass grew loamwright to 132). The invariant that matters —
  every entry resolves with full curated meta — is per-entry; the count is now
  a truncation floor (`>= 122`).

### Audit notes (verified working, no change needed)
- v3.36.0 research-contract normalizer: all 3 researchers passed `passed:true,
  fixed:false` on first write. Chart-source sanitizer: nothing to sanitize (the
  upstream Rule-8 instruction layer produced clean sources). Brand-fact lint:
  ran and passed ×3 with `company_facts` wiring live. v3.36.1 baseline-tag
  pass-through: intact. v3.36.2 driver lock: exactly one publisher record per
  workspace; `LOCKED` never needed. Soft/hard keyword-density asymmetry works
  as documented (0.43% under-density passed as warning; the >1.5% hard veto
  lives in `pre_publish_gate.py:351`). Capsule-coverage re-check after
  fact-check edits caught a real coverage drop (75%→100% after repair) — the
  stage ordering worked as designed.

## [3.36.2] - 2026-07-07 (batch-audit root cures: per-workspace driver lock kills the double-publish race; L12/L13 render gates; References-placeholder ownership fix; detector + chart-label fixes)

Full audit of the 2026-07-07 loamwright 3-article batch (posts 1488/1494/1500 —
all 39 stages ran for all 3, all gates passed, verify 24/24 ×3) plus a 3-agent
root-cause investigation. Six defect classes root-cured; every fix carries a
Rule-10 seam test (`tests/test_batch_fixes_2026_07_07.py`, 9 tests + 4 detector
tests; suite 766 passed).

### Fixed
- **Double-publish race (Rule-7 class, the batch's one process defect):**
  `run_pipeline.py` had NO per-workspace execution lock, so a second invocation
  arriving while the first was mid-way through a minutes-long BASH stage
  re-dispatched the same READY stage. Live evidence: `wordpress-publisher`
  executed TWICE concurrently on 2 of 3 articles (double `create-draft`
  change-log entries for posts 1488/1500), and verify-post snapshotted the post
  BEFORE the second run's final PATCH — the last mutation shipped unverified.
  Idempotent draft PATCHes contained the damage; the same race on a
  non-idempotent stage would not be benign. Root cure: `drive()` wraps
  `advance()` in an exclusive per-workspace `file_lock`
  (`{workspace}/.pipeline-driver.lock`, OS-released on process death — no stale
  locks); a concurrent caller gets `action="LOCKED"` / exit 30. Fan-out (Rule
  11): protocol docs in run_pipeline docstring + skills/seo-blog/SKILL.md Loop +
  batch pattern + root CLAUDE.md Rule 7.
- **Post-humanizer em-dash gate hole → render_lint L12.** The zero-em-dash rule
  was enforced at write time and by the humanizer, but humanizer runs BEFORE
  meta/schema/linker/geo/visual/cta, and the only BLOCKING downstream ai-slop
  adjudication (`pre_publish_gate.check_humanizer`) reads the STALE
  humanizer-report (the fresh `run_quality_gates` recompute only downgrades
  SHIP→SHIP_WITH_NOTES). The geo-auditor introduced a U+2014 into a batch draft
  post-humanizer; caught only by hand. L12 now hard-vetoes em-dashes in editable
  prose (blockquotes/code/References exempt — verbatim external text), running
  inside the already-hard-enforced render-lint gate. Fan-out: zero-em-dash rule
  added to geo-auditor + linker agent files AND geo/linker/visual-designer/
  citation-capsule dispatch_prompts (visual-designer had the agent-file half
  only — the exact asymmetric state Rule 11 forbids).
- **GFM checkbox render leak → render_lint L13 + template fix.** The publisher's
  markdown-it ("gfm-like" + table/strikethrough) has NO tasklists plugin, so
  `- [ ] **Step 1**` ships a literal reader-visible "[ ]" (`<li>[ ] <strong>…`,
  confirmed against the canonical converter) — and `templates/checklist.md`
  PRESCRIBED that syntax (latent leak on every checklist article; the 2026-07-07
  batch avoided it only because the humanizer stripped the checkboxes for
  unrelated AI-tell reasons). Template + `references/seo/blog-formats-2026.md`
  now prescribe plain bold-led items; `markdown_to_html.py`'s false "task lists"
  docstring claim corrected; L13 vetoes any leak writers still emit from habit.
- **ai_tells detector false positives (2 gaps, live on this batch):**
  (a) `- [ ] **Step N:**` checklist items fell through `_BOLD_LED_LINE` (the
  checkbox token sat between list marker and bold run) — 27 of 43 hits on one
  article; (b) `### By the Numbers` H3 stat grids hit P15 because the structural
  allowlist keyed off H2s only. Regex now accepts the checkbox token; heading
  scan widened to H2–H4 with level-aware extents (a child H3 ends at the next
  H2/H3; a parent H2's extent — e.g. FAQ across its `###` questions — is NOT
  truncated by children; nested extents union).
- **Geo-auditor numeric drift (new hard rule 6c + dispatch clause).** The agent
  added "N = 8 sampled pages" precision in ONE location while 4 others said
  "top-10" — cross-section drift the reviewer then bounced back as repair. New
  contract (agent file + dispatch_prompt + capsule/visual dispatch clauses): a
  number added/sharpened/changed in one place must be aligned in EVERY
  restatement in the same pass, recorded in `edits_applied[]`.
- **Chart x-axis label / footer collision (image-QA C1 on this batch):**
  `_wrap()` had no line clamp, so a vbar label wrapping to 4 lines walked into
  the source footer (label line 3 at H−72px vs 2-line footer at H−84px —
  collision guaranteed at ≥3 lines). vbar + grouped_vbar labels now clamp to 2
  lines with ellipsis (rangebar already did); `_footer` reuses the same clamp.
- **References placeholder rediscovered every batch → ownership root cure.**
  No writer is ever dispatched for the References outline entry (fact-checker/
  finalize own it), yet `section_completeness_check` demanded a file per outline
  index and NOTHING auto-created one — `assemble` only appended References when
  citations existed (they never do at assembly time; fact-check runs after) and
  `finalize_refs_signature` only REPLACES an existing block. Every batch
  operator hand-created `sections/NN_references.md` from folklore. Now:
  `assemble.py` unconditionally appends the `## References` stub when absent;
  `section_completeness_check` exempts the References entry (new
  `exempt_indices[]` field, a leftover placeholder is not "extra" either);
  section-drafter dispatch_prompt + SKILL.md document the ownership split.

### Audit verdicts (recorded for the trail)
- v3.35.1→v3.36.1 goals ALL verified delivered against this batch's live
  artifacts (research contract canonical-on-first-write ×3, chart-source
  sanitizer wired, brand-fact lint passed ×3, SEO filenames on every slot,
  `_content_gate_reason` seam test 5/5, no-prose-CTA ×3, verify check 29 ×3).
- Operator follow-ups (project level, not code): 10 new organic tags from this
  batch (IDs 253-262: dental-seo, schema-markup, review-management, crawl-budget,
  google-search-console, log-file-analysis, robots-txt, xml-sitemap,
  freelance-seo, seo-consultant) ship bare by design and owe the curated
  tags-config pass; decide whether DigitalApplied (pricing-chart footer source,
  freelance article) belongs on loamwright's `do_not_cite_domains`.


## [3.36.1] - 2026-07-06 (loamwright full tag-SEO pass: 122 curated tag specs + baseline rank_math meta pass-through; 5 seam tests, all live-verified)

User request: full SEO text / descriptions / RankMath config for every post tag on
loamwrightseo.com. Audit found all 122 live tags bare (empty description +
rank_math_title/description/focus_keyword; only robots=["index"] set) — the exact
gap class `feedback_new_tags_need_full_seo` documents, at full-site scale because
`tags-config.json` had never been specced for loamwright.

### Added
- **`projects/loamwright/tags-config.json` v1.0** — 122 curated tag specs
  (15 strategic + 107 baseline). Every tag (both tiers) carries a tag-centric
  3-sentence description with set-level opening-structure variation
  (programmatically audited: zero first-4-word collisions across 122 entries, per
  `feedback_no_hidden_template_in_taxonomy_copy`), a curated `rank_math_title`
  (≤60 chars, `| Loamwright` suffix), `rank_math_description` (all 120-160 chars),
  `rank_math_focus_keyword` (zero duplicates), `rank_math_robots=["index"]`.
  Copy grounded in the site's own published-article claims (HARO/Connectively
  timeline, $509 avg link cost, citations ≈6-7% local-pack weight, Whitespark
  review-signal trend, white-label 40-60% margin band). U+2019 apostrophes
  throughout (CF WAF, OWASP CRS 942100). Near-duplicate tag families recorded in
  `_merge_recommendations` (observed, NOT merged — Rule-1 exact-keyword-fidelity
  spirit: consolidation needs user approval).
- **`projects/loamwright/tags-live.json`** — live snapshot; `meta_verified: true`
  on all 122 after authenticated `context=edit` re-read matched config exactly.
- **`tests/test_tag_seo_baseline_meta_passthrough.py`** — 5 Rule-10 seam tests
  driving `resolve_tag_seo_spec()` against the REAL on-disk configs (loamwright
  curated-baseline pattern + project-charlie legacy-baseline regression guard).

### Fixed
- **Baseline tags silently dropped curated RankMath meta.** The strategic/baseline
  split is editorial investment, not capability — but both executors stripped
  optional `rank_math_title/description/focus_keyword/twitter_card_type` from
  baseline entries: `setup_tags.py` rebuilt `full_spec` from a fixed key list, and
  `tag_seo_resolver._materialize_baseline()` returned a fixed-shape dict (so
  publish-time re-resolution would also never apply curated baseline meta). Both
  now pass the keys through when present; absence keeps the RankMath
  global-template behavior (project-charlie unchanged, covered by regression test).
- **`schemas/tags-config.schema.json` contradicted canonical practice** (Rule 11
  fan-out): `policy.auto_create_default_meta.description_template` typed `string`
  but the post-2026-05-23 canonical value is `null` (project-charlie's live config was
  failing its own `$schema`); baseline_tag now declares the optional curated
  rank_math_* properties; stale "noindex-by-default" top-level description and
  "baseline = no custom title" doc-contract updated. Both project configs validate.

### Verified (live, 2026-07-06)
- `setup_tags.py loamwright`: 122 UPDATE / 0 CREATE / 0 DELETE / 0 errors, meta=set on all.
- DB re-read (`context=edit`): 122/122 exact match on description + name + all four
  rank_math fields (WP entity-encodes `&` on read-back; verifier normalizes).
- Rendered archives (CF-bypass header + cache-bust): custom `<title>` + meta
  description render on every sampled tag; robots `follow, index,
  max-image-preview:large` on count>0 archives; count=0 (draft-only) archives
  correctly show RankMath's empty-archive `noindex` (auto-lifts at first publish);
  term-description prose + CollectionPage JSON-LD present.
- 55 display names normalized to Title Case (slugs untouched).

## [3.36.0] - 2026-07-06 (Agency-keyword batch audit: research-contract normalizer + self-heal, Rule-8 chart-source sanitizer, brand-fact lint stage, SEO filename fallback; 30 tests added, suite 730 green)

Audit of the 2026-07-06 loamwright agency-keyword batch (white-label-ppc 1474 /
best-local-seo-agency 1468 / digital-marketing-agency-near-me 1480 — all 3 shipped
as drafts, 24/24 verify checks each, reviews 87/88/89, all 38 stages ran or were
explicitly skipped with logged reasons; the recent v3.34–v3.35.3 updates all held:
89/89 targeted seam tests green, and the v3.35.3 research shape floor correctly
REJECTED a drifted research.json at the research stage — the gap was that the only
cure was manual surgery). Four root cures + doc-reality alignments below.

### Added
- **research.json contract normalizer + runner self-heal**
  (`scripts/validate/research_contract.py`). Researchers write research.json via
  scripts (bypassing the Write-hook schema validation) and occasionally improvise a
  variant shape — observed live: intent-as-dict, `competitor_content` instead of
  `competitor_titles`, `keyword_expansion.from_paa` instead of `paa`, raw SerpApi
  feature keys in `serp_features`. `--fix` deterministically normalizes every known
  variant family (all mappings recorded in `_normalizations[]`);
  `run_pipeline.advance()` now self-heals ONCE at the exact seam that used to
  return a dead-end ERROR. The `serp_features` schema enum was extended
  (paid_ads / related_searches / discussions_and_forums / directory_results /
  reddit_top_results / video_carousel / shopping_results / knowledge_graph /
  top_stories / inline_images) — the old 10-value enum could not express honest
  SerpApi ground truth while the orchestrator's OWN serp-analysis dispatch prompt
  instructed subagents to emit exactly those names (an intra-repo Rule-11/12
  contract contradiction that forced a sanctioned skip on a feature-bearing SERP).
  Researcher agent doc + both dispatch prompts now pin the canonical vocabulary +
  the mandatory `--fix --json` final consolidation step.
- **Rule 8 chart-source sanitizer** (`render_data_charts._sanitize_sources_in_file`).
  `chart_spec.source` renders into the chart PNG footer — a citation surface no
  Rule-8 layer scanned; two batch charts shipped competitor vendor names
  (Dashclicks / Hustle Marketers / Admove) in their footers and only a vision-QA
  agent noticed one. The sanitizer neutralizes any source matching the project's
  `citation_source_policy` (domains + competitor_brands) to "Industry benchmark
  synthesis" at the ONE executor every chart flows through, writes the sanitized
  spec back to image-prompts.json, and records `sources_sanitized[]` in the stage
  result. loamwright's blocklist gained the white-label-PPC vendor domains/brands
  (project-editable; see `_vendor_note_2026_07_06`).
- **`brand-fact-check` mandatory stage** (`scripts/lint/brand_fact_check.py`, wired
  into STAGES + `_PASS_FLAG_REQUIRED` + `_FRESHNESS_VS_DRAFT` + run_pipeline
  `_GATE_STAGES` + pipeline_checklist + pre_publish_gate `brand_facts`). The batch
  fabricated the agency's OWN tenure three ways in one run ("five years" /
  "ten years" / "a decade" — real: 6y) and one shipped into draft post 1474:
  writer.md's red line covered EXTERNAL sources only, no layer supplied
  `business-context.company` facts, and GEO scoring actively rewards experience
  phrasing. The lint checks SELF-referential sentences only (first-person /
  brand-name guard, so "the named owner should have five plus years…" third-party
  advice can never false-fire) for tenure / team-size / clients-served numbers vs
  `business-context.company`; projects without a company block no-op PASS.
  section-drafter now passes `company_facts` to every writer; writer/geo/humanizer
  agent docs carry the matching contract (Rule 11 fan-out).
- **SEO-stem media filename fallback** (`openai_image_pipeline._seo_filename_fallback`).
  A cover shipped to the WP media library as `{task_id}_cover.png` because the
  designer omitted `filename_seed` — misled by the dispatch wording "use slot_id
  NOT filename_seed" (meant as an identifier note, read as "don't emit the field").
  Fallback order is now meta.json::slug → angle.json::slug_draft → legacy task_id;
  the dispatch prompt wording was fixed and filename_seed is REQUIRED on every slot.

### Fixed
- Live-draft repairs from the audit: post 1474 "After five years running
  Loamwright" → "six years" (the third tenure instance, caught by the new lint's
  regression run); post 1480 "the ten questions I ask" → "the six-check vetting
  scorecard" (the rubric has 6 checks). Both republished (idempotent PATCH) and
  re-verified 24/24.
- Reviewer contract: explicit CROSS-SECTION NUMERIC CONSISTENCY sweep (one batch
  article stated its pricing band four different ways across TL;DR/table/stats/FAQ;
  the reviewer caught 2 of 3 numeric-drift defects — now a named checklist item)
  and a note that `### Your next step` CTA blocks are config-authored +
  machine-verified (all three reviewers burned a would_change slot proposing CTA
  edits). outline-architect gained the numeric single-source rule (seed numbers are
  copied verbatim from their owning section, never re-derived). Decision recorded:
  NO deterministic cross-restatement checker (high false-positive risk, low ROI vs
  the reviewer sweep).
- Doc-reality alignments (Rule 6/11): outline-architect constraint 7 clarified
  (inline `image_slot: true` sections = `image_count − 1`; the old wording produced
  a 4-boolean outline for a 4-image article), constraint 9 rewritten to the real
  contract (kinds live in image-prompts.json; top-level `image_slots[]` is legacy —
  `image_placeholder_check` D2/D3 documented as legacy no-ops, D4/D5 are the
  operative both-direction checks against image-prompts.json, so no coverage hole);
  `head-of-research` documented as OUT-OF-BAND (not a runner stage;
  `research-brief.json` optional — section-drafter reads research.json directly).

## [3.35.3] - 2026-07-06 (Live loamwright 3-article batch audit: COMPLETE-lie seam root-cured, schema @graph split, research shape floor; 8 tests added, suite 719 green)

Audit of the 2026-07-06 loamwright batch (google-maps-seo-services 1456 /
wordpress-seo-agency 1449 / local-seo-ranking-factors 1462 — all 3 shipped as drafts,
all verify-post checks passing, review 89/89/89). All 38 stages ran or were
explicitly skipped with logged reasons on every article; the four defects below were
found DURING the run, root-caused, and cured at the source.

### Fixed
- **[CRITICAL] The v3.35.2 content gates could be bypassed by a bare re-invocation —
  the COMPLETE signal lied again, one layer deeper.** v3.35.2 added the
  verify-post/fact-check/review gates ONLY to `verify_stage()`. But `next_stage()`
  answers "is this stage already done?" through a SECOND path (`_stage_complete()` /
  `_artifact_valid()`) that still checked existence/provenance only. Live repro
  (loamwpseo0706): verify-post failed check 17 → gate correctly ERRORed → a
  subsequent bare `run_pipeline` call hit the RC-A auto-satisfy branch, recorded the
  FAILED verify-post as `completed`, and reported the pipeline COMPLETE with
  `overall_pass: false` sitting on disk. Same bypass applied to FIX_REQUIRED
  fact-check verdicts and below-target review scores. Root cure: all three gates now
  live in ONE shared helper, `_content_gate_reason()`, called by BOTH
  `verify_stage()` (rich ERROR messaging) and `_stage_complete()` (RC-A can never
  auto-complete a failed gate). Rule 10 seam tests drive `next_stage()` with real
  failing artifacts — not the helper in isolation
  (`tests/test_content_gate_next_stage_seam.py`, 5 tests). Root CLAUDE.md Rule 12
  extended with the v3.35.3 addendum: every completion-deciding path must share the
  gate, and audits must enumerate ALL such paths.
- **[HIGH] Publisher merged a multi-member `@graph` schema.json into ONE
  `<script>` tag, under-counting at live verification (WP post 1449 check-17
  failure).** Two layers defined "block" differently (Rule 11): the schema
  agent/validator counted `@graph` members; `verify_post` check 17 counts rendered
  script TAGS. `wp_publisher._append_custom_schema_blocks`'s fallback deliberately
  wrapped a bare `{"@context", "@graph": [...]}` as one tag ("Google accepts it" —
  true, but the pipeline's own ≥2-body-blocks contract doesn't count it that way).
  Fixed: the fallback now splits each `@graph` member into its own tag (inheriting
  the parent `@context`), matching the canonical `blocks[]` path
  (`tests/test_schema_graph_split_publisher.py`, 3 tests). Contract reconciled
  across all instruction layers: `agents/schema-validator.md` check #11 now defines
  block = script tag; `subskills/optimize/schema-generator/SKILL.md` Step 11 now
  separates head-graph (@graph pattern, meta.json) from body blocks (blocks[]
  shape, schema.json) — its old text taught "single script tag combining all
  schemas" for everything, which is what seeded the drift.
- **[MED] Researcher output-shape drift stalled a pipeline 3 stages late.** One of
  three researcher subagents wrote `research.json` in a fully custom envelope
  (`serp_ground_truth`/`competitor_analysis`/`key_themes`) instead of the canonical
  schema keys; it passed the existence check and only surfaced as a confusing
  serp-analysis evidence failure requiring hand-normalization. Fixed at both
  layers: `_artifact_valid()` now enforces `schemas/research.schema.json`'s required
  keys (`primary_keyword`, `intent`, `competitor_titles`) via the new
  `_REQUIRED_KEYS` floor — key PRESENCE, not richness, so the weekly-digest
  prewrite's intentional `competitor_titles: []` stays valid — and
  `agents/researcher.md` now states the canonical-envelope contract explicitly.
- **[LOW] Conditional stages were never recorded, contradicting the documented
  audit-trail contract.** Root CLAUDE.md describes `local-uniqueness-check` as
  "auto-skipped with a LOGGED skipped status when local_mode=false", but
  `next_stage()`'s condition branch just `continue`d — all 3 batch articles shipped
  with the stage absent from `stage_history` entirely. Now recorded once
  (idempotent) as `skipped` with reason `auto-skipped: condition brief.local_mode=True
  not met`.

### Changed
- `serp-analysis` dispatch prompt: documents the sanctioned `--action skip` path for
  SERPs that GENUINELY have <3 features (live case: 'local seo ranking factors' had
  only ai_overview + related_searches) — inventing a third feature to satisfy the
  heuristic is the forbidden path, skipping with the ground-truth list is correct.
- `references/style/markdown-authoring-conventions.md` Rule 4: scope clarification —
  post-assembly `draft.md` H2s carrying `{#anchor-id}` are the intentional file-bus
  contract (consumed by `_add_anchor_ids` at conversion), NOT a violation; two
  humanizers false-positived on this in the batch and wasted review cycles.
- `agents/writer.md`: gated/paywalled-survey fabrication trap documented — three
  writers invented percentage splits for an email-gated survey despite the research
  brief's explicit prohibition; all were caught by the fact-checker sweep, but the
  no-reconstruction rule is now stated at the writer layer too (defense in depth).
- `skills/seo-blog/SKILL.md` batch loop: COMPLETE now documented as
  content-verdict-backed (v3.35.3), not just stage-order-backed.

## [3.35.2] - 2026-07-05 (Live 3-article batch post-mortem: 2 critical silent-pass gaps + 2 contract-drift gaps found and root-caused; 14 tests added, suite 711 green)

Root-cause audit of a real 3-article `/batch-article` run against loamwright (corporate
seo / manufacturing seo company / best seo ecommerce platform — all 3 shipped as drafts,
all 24-point live-verify checks now passing). Two of the four findings were caught only
because the operator manually inspected artifact files instead of trusting the runner's
own "COMPLETE" signal — the same disease class as Rules 6/9/10 (a layer of indirection
silently does the wrong thing because nobody checks its actual output, only that it ran).

### Fixed
- **[CRITICAL] `verify_stage()` never gated `verify-post`'s own pass/fail result.**
  `scripts/pipeline/orchestrator.py` had explicit content-based gates for
  `fact-check.json` (blocking verdict) and `review.json` (score threshold) but NONE
  for `verify-result.json` — it only checked the file existed. `verify_post.py` always
  writes its result file (pass or fail) so a human can debug, so "file exists" and
  "the live post is actually clean" are different questions. In production, 2 of 3
  batch articles had `overall_pass: false` in their real `verify-result.json` (a raw
  HTML-escape leak; a missing 2nd JSON-LD body block) yet `run_pipeline.py` reported
  the WHOLE pipeline `"COMPLETE"` for both — defeating root CLAUDE.md Rule 4 ("always
  verify the live URL after publish") at the code level. Fixed with a gate mirroring
  the existing fact-check/review pattern: `overall_pass is False` (or absent with a
  truthy `fail_count`, defensive) now fails the stage with the specific failed check
  IDs surfaced in `result["reason"]`, routing back to fix-and-re-dispatch instead of
  silently completing. 4 tests (`tests/test_verify_post_gate.py`).
- **[CRITICAL] Agent-direct `state.json` writes could silently destroy required +
  project-specific fields, with no defense in code.** Every deterministic script
  (`file_bus.py`'s `write_state`/`record_stage_complete`, `orchestrator.py`'s
  `_record_stage`) correctly does read-modify-write; the corruption came from an LLM
  subagent's own `Write` tool call reconstructing state.json from a partial view. In
  production this dropped `phase`/`current_stage`/`created_at` (all schema-`required`)
  and `project_constraints` (`wrapper_class`/`mandatory_sections`/
  `differentiation_note` — orchestrator-populated, no agent is ever given these as
  input) mid-batch, crashing the next stage (`assembly`) with `'phase' is a required
  property` and requiring a manual mid-pipeline recovery. Fixed in two layers: (1)
  `file_bus.write_state()` now refuses (`ValueError`) any write that would remove a
  previously-present required field or `project_constraints` unless the caller passes
  `allow_field_removal=True` — code-level defense, not prompt-only; (2) the shared
  `references/orchestration/stage-tracking.md` convention doc gained a prominent
  "NEVER write state.json with the `Write` tool" hard rule, referenced (not
  re-duplicated — avoids the next Rule-11 drift) from `agents/researcher.md`,
  `agents/head-of-research.md`, `agents/image-prompt-designer.md`, and
  `agents/publisher.md` — the 4 agent docs whose existing "update state.json: X"
  wording carried the same ambiguity risk.
- **[MEDIUM, Rule 11 fan-out] `render_lint.py` L1 and `verify_post.py` check 06
  implemented the same "no escaped-HTML-tag leak" contract with independently-drifted
  logic.** `render_lint.py` was patched 2026-07-01 to excise `<code>/<pre>` spans
  before scanning (a markdown backtick code span like `` `<link rel="alternate"
  hreflang>` `` legitimately renders as escaped display text, not a leak); `verify_post.py`
  check 06 never got that fix, so a pre-publish gate correctly passed content that the
  live post's own check then failed, forcing an unnecessary manual rewrite of
  legitimate prose. Additionally, check 06's own tag-boundary regex required a RAW
  boundary character right after the tag name, so it could not detect a real,
  fully-escaped leak like `&lt;strong&gt;` (a genuine false negative, independent of
  the code-span issue). Fixed by importing render_lint's `_CODE_SPAN_RE` and
  `_ESCAPED_TAG_RE` directly into `verify_post.py` instead of maintaining a second
  copy — the two checks now share one source of truth and cannot drift apart again.
  6 parametrized tests (`tests/test_verify_post_l1_parity.py`) run identical HTML
  samples through both detectors and assert they agree.
- **[MEDIUM, Rule 11 fan-out + self-contradicting pipeline] schema-generator's
  discretion over a 2nd JSON-LD body block collided with verify_post's hard >=2-block
  minimum, AND the dispatch contract told it to reach for a type its own downstream
  veto rejects.** For a DRAFT post (Rule 5a default), `<head>` isn't fetchable, so
  `check_jsonld_schemas(min_total_blocks=2)` falls entirely on body blocks — but
  `subskills/optimize/schema-generator/SKILL.md` never stated a hard minimum, so the
  dispatched subagent could reasonably ship only `FAQPage` ("ItemList doesn't fit"),
  which is what happened in production, forcing a manual patch. Separately,
  `orchestrator.py`'s dispatch_prompt listed `HowTo`/`Dataset` as "allowed body types"
  while `agents/schema-validator.md`'s own T09 veto scan HARD-REJECTS `HowTo` as a
  primary `@type` (Google deprecated HowTo rich results Sept 2023) — a
  self-contradicting instruction where following it could trip this same pipeline's
  quality gate. Fixed: orchestrator.py's dispatch_prompt now says FAQPage + ItemList
  only (no HowTo/Dataset as standalone types), and states the >=2-block minimum as
  mandatory with ItemList's always-available source (outline-architect guarantees
  >=2 tables per article). Mirrored into `subskills/optimize/schema-generator/SKILL.md`
  (new Hard Rule 6 + corrected the "✅ HowTo/Dataset" bullet list that contradicted its
  own Step 10 deprecated-type table) and `agents/schema-validator.md` (new check 11,
  catching a 1-block schema at validation time instead of only at live verification).
  4 tests (`tests/test_schema_block_count_gate.py`) pin the draft-vs-live asymmetry
  (head uncountable pre-publish → body alone must hit 2) plus the head-counts-on-live
  case.

### Verified unaffected
- Ran the full 3-article batch's actual artifacts back through the fixed
  `verify_stage()` — both previously-false-"COMPLETE" articles (loamcorpseo0705,
  loamecomplat0705) are already live-verified clean (manually fixed and re-verified
  during the same session, before this code fix landed); loammanufseo0705 (always
  genuinely clean) is unaffected either way.
- Full suite: 711 passed (was 697 before this batch's 14 new tests per the 3.35.1
  baseline; no regressions), 1 skipped, 4 xfailed — identical skip/xfail set to the
  pre-change baseline.

## [3.35.1] - 2026-07-05 (Re-audit of v3.34/v3.35: 1 HIGH + 3 MED + 4 LOW seam defects fixed; 2 hypotheses checked and dismissed)

Adversarial re-audit of the two same-day releases (the v3.30.1 "audit the audit"
pattern — Rule 10). Every fix at skill level; suite 697 green.

### Fixed
- **[HIGH H1] Template→writer double-CTA seam.** The v3.34 conclusion-spec change
  landed in skills/seo-blog/SKILL.md but NOT in the format templates or the writer
  agent: `templates/local-state-pillar.md` ("soft CTA to /contact/") and
  `templates/multi-intent-hybrid.md` ("CTAs in conclusion") still ordered prose CTAs
  that would ship NEXT TO the injected `.xr-cta-box` module — the exact pressure
  pattern v3.34 set out to kill. Both templates + `agents/writer.md` (explicit
  "write NO CTA" red line) fixed at the instruction SOURCE.
- **[MED M1] AGENTS.md (universal host router) still routed "featured snippet" /
  "PAA" / "localize" intents to retired/relocated subskills**; repointed to
  citation-capsule-builder / the machine-enforced gates; footer bumped from the
  fossilized "3.2.0 · 2026-05-19".
- **[MED M3] The ai_tells bold-led-line exemption (P14/P28/P42 shape suppression)
  had shipped UNCOMMITTED, UNSYNCED (cache still ran the old detector), and UNTESTED**
  from an earlier session. Now: 3 tests incl. the negative case (mid-sentence bold in
  prose must still fire), committed, cache-synced. Root cause: a session edited the
  working tree without completing the after-edit sync/commit workflow — the
  triple-state (tree ≠ cache ≠ git) is exactly what the CLAUDE.md sync section exists
  to prevent.
- **[MED M4] geo-content-optimizer could flip the new paa-alignment gate**: its Q&A
  technique runs before the gate and nothing forbade adding off-PAA FAQ questions
  (each one raises faq_count without raising matches). Dispatch prompt +
  agents/geo-auditor.md now require FAQ additions to be VERBATIM from research.paa.
- **[MED, follow-on] Weekly digests would have received a mid-article CTA card
  between news stories.** cta_injector gains `cta.format_rules` ({format_id:
  [placements]}, read from angle.json); loamwright sets {"weekly-digest": ["end"]};
  schema + test added.
- **[LOW L2] CTA-module red lines added to the agent DEFINITION files**
  (humanizer/geo-auditor/visual-designer .md) — v3.34 had only covered the
  orchestrator dispatch prompts, leaving out-of-band invocations (/humanize)
  unguarded. Plus linker.md: never link inside the CTA block.
- **[LOW L3/L4/L5] Doc-drift sweep**: phase-optimize "11 sub-skills" count;
  writer/linker "cta-placement" naming → cta-injection; format-selector no longer
  emits speakable-schema/voice-search-friendly modifiers (no consumer);
  surface-targeting + serp-analysis + reference headers pruned of retired names.

### Checked and DISMISSED (no change — recorded so the next audit doesn't re-litigate)
- **Scaffold-marker "contradiction" (humanizer preserves / templates prescribe /
  L6 flags):** machinery is coherent — render_lint pre-strips markers in memory
  (mirroring wp_publisher), C10 credits marker AND prose forms pre-strip; v3.33 only
  forbade the geo-auditor INJECTING markers post-hoc. Writers' markers are valid
  author-internal annotations.
- **Digest double tail CTA (end module + signature link):** same coexistence every
  article has by design (Rule 5 signature is a footer); accepted.
- **Freshness ordering / verify_post leniency / digest PAA no-op:** verified correct
  (no re-run loop possible; pre-v3.35 workspaces re-verify cleanly; digest
  research.json has no paa[] so the gate no-ops).

## [3.35.0] - 2026-07-04 (Wire-vs-retire pass over the 5 remaining Rule-6-dead optimize subskills)

Deep audit (repo dissection + 2024-2026 external evidence sweep) of the 5 subskills
documented since v5.0 with no executor/stage: featured-snippet-optimizer,
paa-answer-writer, voice-search-optimizer, localization-pass, ai-overview-recovery.
Verdicts are evidence-based — blindly wiring all 5 would be as fake as leaving them
dead. Evidence base: NEW `references/seo/serp-feature-value-2026.md`.

### Wired (2 new mandatory lint stages, full chain)
- **`paa-alignment-check`** — NEW `scripts/lint/paa_alignment_check.py` measures the
  ">=60% of FAQ from research.paa" contract ON THE DRAFT (the outline's
  `paa_alignment_pct` was a self-report validated by NOTHING — same orphan class as
  cta_placement). Honest-supply rule: required = min(ceil(0.6×faq_count), paa_count);
  no-ops on thin harvests (<3 PAA) / missing FAQ. Answer-length 20-60w advisory.
  Basis: PAA GREW through 2025 (+34.7% US mobile, seoClarity) and co-occurs with AIO
  on ~90% of AIO SERPs (Semrush) — one of the few features AIO does not displace.
  Real-draft smoke: loamauditconsult0704 measured 10/10 aligned; loamintlagency 5/6.
- **`locale-spelling-check`** — `scripts/lint/spelling_dialect_check.py` gains a
  workspace mode and is FINALLY wired (executor existed since v5.0, zero invocations).
  Resolves dialect from brief.target_market_locale (en-US default — its production
  value is catching en-GB training-data leakage, an AI-tell); exempts
  References/Further Reading, blockquotes, code, link URLs, and Capitalized
  mid-sentence proper nouns; FAILs only at >=3 hits (systemic drift). Non-English +
  en-CA no-op. **Wiring immediately exposed 3 latent word-list bugs** (the lesson of
  testing against real inputs): `analys(is|es)` matched the dialect-neutral
  "analysis/analyses" (6 phantom hits on a real draft), "dialogue" is standard US
  (pair removed), `tire(d)` matched the universal "tired" (suffix removed).
  Both stages: orchestrator STAGES + `_PASS_FLAG_REQUIRED` + `_FRESHNESS_VS_DRAFT` +
  `run_pipeline._GATE_STAGES` + `pipeline_checklist.MANDATORY_STAGES` + fresh-compute
  pre-publish gates (`paa_alignment`, `locale_spelling`).

### Retired (evidence-backed, with paper trail)
- **featured-snippet-optimizer → merged into `citation-capsule-builder`.** Ahrefs
  2025: FS fell 18%→8% of SERPs (83% replaced by AIO; 0.9 correlation) and both
  select the same 40-60w extractive shape the capsule stage already writes. The
  capsule dispatch now PRIORITIZES `outline.sections[].is_featured_snippet_target`
  (the orphan flag finally has a consumer); `snippet_format` deprecated.
- **voice-search-optimizer → retired.** The founding "50% voice by 2020" stat is a
  debunked zombie citation; SEL's own guide (Nov 2025) lists zero voice-only tactics —
  everything is already covered by FAQ/capsules/schema/humanizer.
  `scripts/lint/voice_search_check.py` survives as a MANUAL diagnostic CLI only.
  Both retired SKILL.md files rewritten as retirement pointers
  (disable-model-invocation: true).

### Monitor-side hardening (ai-overview-recovery)
- **AIO churn guard** in `refresh_decision_router`: NOT_IN_AI now requires the domain
  uncited in 2 consecutive probes >=48h apart (observations persisted per query in
  `projects/{slug}/audits/aio-observations.json`; a cited probe in between resets the
  clock). Basis: Ahrefs 2025 — consecutive AIO renders share only ~54.5% of cited
  URLs, so a single uncited snapshot is churn, not loss. Unconfirmed losses surface
  in `SitePlan.notes` for visibility. New Phase 0 in the recovery SKILL; the rest of
  the playbook was already the most-wired of the 5 (probe + journal --record/--verify
  test-enforced) and correctly stays a monitor-triggered playbook, not a polish stage.

### Docs reality-sync
- `skills/phase-optimize/SKILL.md` Stage-1 list now matches the orchestrator STAGES
  table exactly (the old 11-step list promised 5 stages that never ran) + a
  "Retired / relocated" table; description frontmatter updated.
- localization-pass SKILL: false claim that "the humanizer handles the locale layer"
  corrected (humanizer has no locale code); Mode 1 rewritten around the wired stage;
  Mode 2 `/locale-audit` stays a user-invocable portfolio tool.
- outline-architect: constraint 8 extended to ai_overview SERPs + snippet_format
  ban; PAA note (outline pct is an estimate; the draft is measured).

### Tests
- NEW `tests/test_subskill_wiring_2026_07_04.py` — 20 tests: paa matcher/honest-supply/
  no-ops, locale zones/proper-nouns/threshold/locale-resolution/UK-target, AIO churn
  guard (2-probe confirmation, cited-reset, observation cap), and Rule-10 seams
  (stages in STAGES + all 4 enforcement maps, retired names NOT stages, FS flag
  consumed by capsule dispatch, retired SKILLs declare retirement, gates compute
  fresh). Full suite: 693 passed.

## [3.34.0] - 2026-07-04 (Designed CTA module: cta-placement finally has an executor — Rule 6 third offense root-cured)

Deep audit ("does the pipeline promote the project's own products + is there a CTA
module?") found: self-promotion existed only at the edges (linker internal links, one
prose sentence in the conclusion, the signature), and the entire CTA feature was
Rule-6 dead for the third time — `subskills/optimize/cta-placement/SKILL.md` documented
behavior with NO executor and NO stage since v5.0; outline-architect emitted
`cta_placement` data NOTHING consumed; `state.brief.cta_target/cta_style` had no reader;
the referenced `references/seo/cta-placement-data.md` did not exist; the visual design
system had no CTA component. Skill-level feature, executed per-project (all 6).

### New executor + stage (the wiring)
- **NEW `scripts/optimize/cta_injector.py`** — deterministic, idempotent CTA-module
  injection from `business-context.json :: cta`: `end` placement (before Further
  Reading/References; BOFU slot — AI-referral visitors convert 6-9x organic) and opt-in
  `mid` (~35% word mark, never after the first content section). Copy variants rotate
  by task_id (no-hidden-templates); em-dash→comma + ASCII-apostrophe→U+2019 sanitize;
  no numbers / no UTM by policy (see references/seo/cta-placement-data.md). `--check`
  mode re-scans the CURRENT draft and tolerates legitimately-skipped placements.
- **NEW mandatory `cta-injection` stage** (orchestrator, after visual-designer, before
  render-lint) + `_PASS_FLAG_REQUIRED` + `_FRESHNESS_VS_DRAFT` (post-repair draft edits
  re-run it — a stripped CTA is re-injected, not silently lost) +
  `pipeline_checklist.MANDATORY_STAGES` + `run_pipeline._GATE_STAGES`. No-config
  projects no-op but still write the evidence artifact.
- **NEW `pre_publish_gate.check_cta_module`** (mandatory gate 16) — re-scans the draft
  via the injector's --check; catches repair loops stripping the block.
- **NEW `verify_post` check 29** — `<p class="xr-cta-box">` must render on the LIVE page
  when placements were applied (same silent-failure family as Rule 2's unwrapped CSS).
- humanizer / geo-content-optimizer / visual-designer dispatch prompts now hard-forbid
  editing or removing the injected CTA block (repair-loop protection).

### Visual design system
- **NEW component id `cta`** in `scripts/_core/component_headings.py` (phrases: "Your
  next step", "Where we can help", "Work with us", "Ready when you are", "Talk to the
  factory", "下一步") → publisher class-tags the sibling `<p>` as `xr-cta-box`.
  Deliberately EXCLUDED from `visual_density_check` weights (promo is not substance).
- **`article_css_generator.py` emits `.xr-cta-box` conversion-card rules** (light + dark
  palettes, `:has()` heading coupling with graceful degradation, mobile padding).
  Regenerated all 6 projects' `brand/article-css.css` (+.min.css) — diff-verified purely
  additive. Component 9 documented in `references/style/visual-design-components.md`.

### Per-project execution (all 6)
- `business-context.json :: cta` written for loamwright (mid+end, "Your next step",
  free-audit funnel), project-charlie ("Where we can help"), project-echo ("Your next step",
  21+ line, no urgency), project-juliet ("Work with us"), project-kilo ("Talk to the
  factory"), project-hotel ("Ready when you are", grief-safe) — each in project voice,
  2-3 variants per placement. Project CLAUDE.md files updated.
- Writer contract change: on cta-enabled projects the conclusion is synthesis ONLY (no
  prose CTA sentence — the card replaces it); seo-blog SKILL.md conclusion spec updated.

### Dead code / orphan data cured
- `outline.schema.json :: cta_placement` + outline-architect emission removed/deprecated
  (produced-but-never-consumed orphan). `state.brief.cta_target/cta_style` marked
  deprecated in state.schema.json. `references/seo/cta-placement-data.md` now EXISTS
  (evidence base: HubSpot anchor-text 47-93% vs end-banner ~6%; +32% mid contextual;
  +202% personalized; Princeton GEO — promo styling does NOT help citation; Dec 2025
  core update hit self-ranking listicles). cta-placement SKILL.md rewritten around the
  executor. `/init` Step 13 gains question 6d (CTA module config for new projects).
- Known remaining dead code (out of scope, documented): `scripts/analysis/cta_analyzer.py`
  + `cro_checker.py` (landing-page CRO analyzers, imported by nothing).

### Tests
- `tests/test_cta_injector.py` — 16 tests: unit (placement math, idempotency, variant
  rotation, sanitizer, config validation, strip detection) + Rule-10 seam (stage in
  STAGES between visual-designer and render-lint, checklist/gate maps, classifier +
  publisher tagging for all 6 shipped headings, markdown-it→tagger end-to-end, all real
  project configs injectable, CSS emission light+dark, density-gate non-crediting).
  Full suite: 673 passed.

### Retrofit (production, 2026-07-04)
- The 3 pre-v3.34 loamwright drafts awaiting publish (posts 1062/1049/1056) were
  patched in place: CTA modules injected (mid+end, variants rotated per task), the
  now-redundant prose CTA sentence removed from each conclusion, re-published via the
  idempotent wp_publisher PATCH path (same post_ids, media deduped by filename), and
  re-verified — check 29 PASS on all 3, zero new defects vs the pre-patch verify results
  (the draft-state check-17 "head not fetched" and the loamintlagency code-sample
  check-06 false-positive predate the patch and are unchanged).

## [3.33.0] - 2026-07-01 (Batch-07-01b audit: local-uniqueness gate finally wired + freshness invalidation + Tavily poll/pool root cures)

Full audit of the 07-01b 3-article batch (drafts 812/818/824 — all 33 stages ran, zero
skips, provenance clean) via 3 parallel source investigations. Every fix at skill level
(scripts/agents/skills — zero project-specific code touched), each with Rule-9/10 seam
tests (`tests/test_root_cause_fixes_2026_07_01b.py`, 19 tests; full suite 657 passing).
Recurring disease across all findings: completion inferred from artifact existence, and
behavior asserted in markdown with no executor.

### Pipeline enforcement (the big ones)
- **[CRITICAL] `local_uniqueness` gate had NEVER executed in production (Rule 6, second
  offense for the same feature).** Documented as mandatory-when-local since v3.4.0, wired
  into phase-optimize prose, then dropped by the v3.7 runner migration — zero
  `local-uniqueness-lint.json` in ~60 historical workspaces; the 07-01b Phoenix article
  (local_mode=true) shipped ungated (retro-lint: PASS 86.7, 4/4 Sterling categories — writer
  discipline, not enforcement). NOW: a conditional STAGE in the orchestrator table
  (first user of the `is_conditional` machinery; auto-skip logged for non-local tasks),
  `_PASS_FLAG_REQUIRED` + `run_pipeline._GATE_STAGES` entries (a failing lint routes
  GATE_FAILED), a MANDATORY `pre_publish_gate.check_local_uniqueness`, and the lint CLI
  now resolves bare task-ids like every sibling (the documented invocation used to exit 2).
- **[HIGH] Stale-artifact auto-satisfy (RC-A) — quality-gates for the Phoenix article was
  never executed by the runner.** The geo-auditor subagent ran `run_quality_gates` itself
  mid-stage; the runner later auto-stamped quality-gates COMPLETE off that file — which
  scored a draft 11 minutes older than the one that shipped. NOW: `_FRESHNESS_VS_DRAFT`
  in `_artifact_valid` — deterministic draft-derived gate artifacts (quality.json +
  the 5 lint artifacts) older than draft.md are invalid and the cheap stage re-executes;
  plus an ADVISORY `pre_publish_gate.check_gate_freshness` WARN for the LLM artifacts
  (fact-check/humanizer/review) whose re-dispatch is the operator's cost call. Verified
  against the real batch: re-driving the runner re-executed exactly the stale gates on
  all 3 tasks; all fresh verdicts SHIP/all_pass.
- **[HIGH] cite_scorer C10 rewarded the exact tokens render_lint strips (perverse
  incentive).** C10 passed only on literal `[ORIGINAL DATA]`-style markers — which the
  publisher/render-lint unconditionally strip as L6 leaks — so the geo-auditor rationally
  injected markers into a finished draft to score the point (loamphxseo0701, 2 markers).
  NOW: C10 credits PROSE-level info-gain signals ("we measured/tested N ...") directly
  (markers still count pre-strip); geo-auditor dispatch prompt + agents/geo-auditor.md
  hard-forbid scaffold-marker injection, heading renames, and fabricated experience.
- **[MED] NEW `chart-rerender` BASH stage after fact-check** + fact-checker CHART SYNC
  mandate (agents/fact-checker.md step 5b + dispatch prompt): a number corrected by the
  fact-checker now updates `image-prompts.json :: chart_spec` and the idempotent, $0
  local re-render pushes it into the PNGs (07-01b: corrected Census figures shipped in
  the table while the chart kept stale values — needed a manual patch). Distinct result
  artifact (`chart-rerender-result.json` via new `--result-file` arg) because reusing the
  plan-phase artifact would be instantly auto-satisfied. Both chart result files added to
  `_PASS_FLAG_REQUIRED` ("success").

### Tavily research reliability (v3.31.1 follow-through — both "fixed" bugs recurred)
- **[HIGH] `tavily_research` poll fix was half a state machine.** v3.31.1 added the poll
  loop but hardcoded non-terminal={"pending"}; the real lifecycle is
  `pending → in_progress → completed|failed`, so the first poll seeing `in_progress`
  returned it as FINAL (9-16s early exits; all 3 researchers lost the pro job to MCP
  fallback AGAIN). NOW: `_NON_TERMINAL_STATUSES = {pending, in_progress}` at BOTH the
  poll-loop exit and the poll-entry gate; tests replay the real recorded status sequence.
- **[HIGH] Community research crashed on any >400-char claim.** Full Reddit post bodies
  were passed verbatim as Tavily queries (hard API cap 400 → BadRequestError →
  fail-fast → the whole community pass died, every batch). NOW capped at 3 layers:
  word-boundary truncation in `community_claim_verifier._lookup`, a warn+cap single
  source of truth in `tavily_search.search()`, and the runner degrades a failing
  `verify_claim` to skip-this-claim instead of crashing the pass.
- **[MED] Invalid-key rotations no longer consume the retry budget.** The 06-30 key
  import added a contiguous tranche of 42 dead (deactivated) accounts un-probed; v3.31.1's
  persist-marking worked, but each rotation burned one of max 12 attempts, so first-touch
  calls failed on corpses while 58 healthy keys sat unused. NOW: dead-key skips get their
  own bound (pool size, terminates on an all-dead pool with an actionable error);
  researcher.md documents the real refresh CLI (`python -m scripts._core.tavily_pool
  --refresh` — scripts._core, not scripts.fetch).

### Verification correctness
- **[HIGH] verify_post check 27's H1 sub-check was structurally dead for every pipeline
  post.** The publisher converts with `drop_h1=True` (WP renders the TITLE as the H1),
  but the check scanned only `content.rendered` for an `<h1>` — so every local-mode
  article failed 22/23 forever (draft 818: "Phoenix" in the title, "H1 missing location"
  verdict). NOW: the REST `title.rendered` is passed in and preferred as the H1 source
  (body `<h1>` remains the fallback for ad-hoc content).

### Ground-truth + docs
- research/serp-analysis dispatch prompts now MANDATE `serpapi_query --engine google`
  structured output as the source for `serp_features[]`/`_serp_features_detail`/
  `ai_overview_present` (07-01b: Tavily inference under-detected 2 of 5 live features,
  including a live AI Overview); agents/researcher.md stage 10d hardened to match.
- `skills/seo-blog/SKILL.md`: local_uniqueness gate paragraph now records the runner
  enforcement (no more dead prose); title_validator invocation qualified to
  `scripts.validate.title_validator` (the one pathless reference that seeded a wrong guess).

Tests: 19 new seam tests; 2 assertions in test_record_and_gate_fixes_2026_06_04.py
updated to the corrected contract (strengthened — condition-skipped stages must appear in
skipped_stages). Full suite: 657 passed / 1 skipped / 4 xfailed.

## [3.32.0] - 2026-07-01 (Weekly-digest + visual-design audits: root-cause fixes & Phase-4 completion)

Two full audits (4 parallel investigations: digest code + digest live-state + visual-design
code + visual-design live-effect measurement) verified the v3.31 design system WORKS —
old→new cohort words-per-visual improved 41% (688→407) at equal length — and surfaced the
defects below. All fixed at source with seam tests (`test_digest_and_visual_fixes_2026_07_01.py`;
suite 638 passing).

### Visual design — the component-binding root cure
- **[CRITICAL] All 4 "By the Numbers" stat grids in the 07-01 batch shipped UNSTYLED.** An
  earlier in-section `### By the Numbers` claimed the base anchor, the component H2 deduped to
  `#by-the-numbers-2`, and the CSS's exact-id adjacency selector went dead — while the density
  gate (its own separate English regexes) still credited the component, so nothing warned.
  ROOT CURE (the blockquote_classify pattern): new single source of truth
  `scripts/_core/component_headings.py` (heading→component classifier: exact + topic-scoped
  "By the Numbers: 2026 Costs" + variant "This Week at a Glance" + localized 数据速览; h2 AND
  h3); wp_publisher tags rendered blocks with stable classes (`xr-stat-grid`, `xr-tldr-box`,
  `xr-glance-table`, `xr-glossary-list`, `xr-checklist`); the CSS targets classes with widened
  `[id^=]`/`[id$=]` attribute selectors as no-retag fallback; the density gate counts with the
  SAME classifier — gate and CSS can no longer diverge.
- **Phase-4 completed:** per-format density floors (`weekly-digest: 2.0` carve-out, orchestrator
  no longer hardcodes `--min-components 3`); NEW retrofit executor
  `scripts/wordpress/restyle_posts.py` (re-injects current CSS + re-tags components on stored
  raw content, status-preserving, dry-run default) — **applied to all 10 loamwright posts**:
  6 pre-v3.31 posts jumped 9,044B→15,025B CSS with TL;DR boxes lighting up; digest 773's
  At-a-Glance table + stat grid now bind; the 3 batch drafts' stat grids restored.
- `checklist` de-phantomed (classifier + CSS card treatment + density counter — was weighted
  and playbooked but detected/styled by nothing). A11y: `:focus-visible` rings +
  `prefers-reduced-motion` guard in generated CSS. All 6 projects' CSS regenerated.

### Weekly digest — series capability completed
- **[HIGH] The follow-up state machine was inert**: only "reported" was ever written; the
  active statuses gating the entire cross-week machinery were read but never set — no digest
  could EVER emit a follow-up without hand-editing covered.json. New
  `resolve_recurrences()` auto-marks a previously-reported story "developing" when it recurs
  with fresh coverage (headline-token overlap coefficient ≥0.5, ≥3 shared tokens, different
  URL, inside the window), wired into the runner before cross_week_filter.
- **[HIGH] `/seo-news/` hub was never created** (Step 10 never ran after 773 went live) —
  now LIVE (page 806) with project-configured `hub_title`/`intro` (were falling back to
  generic "Weekly Digest"), real issue link, CollectionPage+ItemList schema. Plus a CLI
  hard-error on PARTIAL issue args (silently dropping --issue-title without --task-id is what
  produced the first "Untitled Issue → #" hub render).
- **Week-level idempotency**: `find_issue_in_week()` guard — a second run in the same ISO week
  now exits 3 with the existing task id (`--force` to override). Previously two runs in one
  week produced two drafts/two issues rows/two hub rows.
- **Ledger hygiene**: `expire_and_prune_covered()` — aged-out active entries auto-close
  (zombie "watch" rows could never be emitted yet lived forever), entries beyond
  `covered_retention_weeks` (default 12) pruned; covered.json is now bounded.
- NewsAPI runs ALL configured `queries[]` (only `[0]` was used); verify-post image target is
  format-aware (len(images.json), floor 1 — the flat ≥4 false-warned the 1-chart digest);
  rank-formula doc synced to the real 5-term weights (authority 0.15 was undocumented);
  SKILL's phantom "image-curator" stage renamed; `connectors.mcp` explicitly documented as
  Tier-B (researcher-agent) only.

## [3.31.1] - 2026-07-01 (Root-cause fixes from the loamwright 3-article batch audit)

A full audit of the 2026-07-01 batch (drafts 782/788/794 — all 33 stages ran, zero skips)
plus the last-10-commit review surfaced 13 defects, each traced to root cause and fixed at
the source with Rule-10 seam tests (`tests/test_root_cause_fixes_2026_07_01.py`, 28 tests;
full suite 628 passing). Same disease class throughout the HARD RULES catalog: a contract
split across two implementations that misbehaves on inputs the other never exercised.

### Gate / scorer correctness
- **[HIGH] Reviewer threshold had NO executor (Rule 6).** The SKILL contract says
  `review.json.score >= state.brief.quality_target_score`, but `pre_publish_gate` hardcoded
  80 and the orchestrator enforced nothing — an 84 sailed past an 85-target brief
  (loamdentallocal0701; caught only by operator diligence). Now enforced at BOTH layers:
  `orchestrator.verify_stage` refuses to record `independent-reviewer` complete below the
  brief target (runner routes to repair at review time), and `pre_publish_gate.check_reviewer`
  reads the brief target (fallback 80).
- **[HIGH] CORE-EEAT C01 veto fired on every canonically-shaped citations.json.** It read the
  legacy `refs` key only, ignored `url_verified`, and defaulted a missing `resolved_status`
  to 0 → bot-walled REAL sources (CourtListener 202, Search Engine Land 403-to-bots) produced
  a false fabricated-citation veto + a pre-publish block (loambidkw0701). Ported the
  cite_scorer C09 hardening that was never applied here: canonical `citations` key, broken
  only on EXPLICIT non-resolution.
- **[MED] quality.schema.json described a contract that was never implemented** (total
  producer/consumer drift, invisible because `run_quality_gates` writes via `write_text`
  where the schema hook can't fire; surfaced by hook-blocking a legitimate `override_note`
  edit). Rewritten to the REAL contract incl. the sanctioned `override_note` escape.

### Publish correctness
- **[HIGH] Category name→term resolution was slug-first**, so
  `slugify("Link Building & Digital PR")` (= the CHILD term's real slug) resolved to
  subcategory 90 before the HTML-entity-aware name match for pillar 66 ever ran (post 788).
  `wp_taxonomy.get_or_create_terms` is now NAME-first with slug fallback.
- **[HIGH] categories-live.json has two producer schemas** (snapshot_categories vs
  setup_categories "applied" format); consumers expected only the first → loamwright's
  `category_ids` attach was a permanent silent no-op. `category_selector` now normalizes
  either shape (`_normalize_live_snapshot`), the name lookup is entity/case-tolerant, and
  the ID-attach also runs for hand-authored meta categories (previously skipped when the
  selector recommended nothing). loamwright's snapshot regenerated in canonical format.
- **[HIGH] Cover `is_featured` is one field with two meanings** (placeholder-lint exclusion
  hint in image-prompts.json vs featured_media selector in images.json). An explicit
  `false` propagated into images.json and shipped post 788 with `featured_media=0`; an
  explicit `true` false-fired the D5 orphan check. Cured at all three layers: shared
  `is_cover_slot()` (cover / slot-cover / *-cover) in `scripts/_core/image_prompts`;
  `openai_image_pipeline` forces the cover featured in images.json regardless of the
  prompts flag; `wp_publisher` falls back to the cover slot when nothing is flagged;
  D5's orphan direction now checks the FULL declared slot set. real_brand pipeline
  delegates to the shared helper. Designer contract: OMIT the key.
- **[MED] Adjacent duplicate inline citations** — two neighbouring claim markers resolving
  to the same source rendered `(Reboot Online, 2025)(Reboot Online, 2025)` (shipped in
  draft 788). All three substitution executors (assemble, citation_inject, wp_publisher)
  now collapse identical adjacent parentheticals via shared
  `scripts/_core/citation_text.collapse_adjacent_duplicate_citations`.
- **[LOW] Stale image-QA guard**: an image re-rendered AFTER the QA pass shipped unseen
  (loamdentallocal0701's re-numbered chart). `pre_publish_gate.check_image_qa` now WARNs
  when any images.json file mtime postdates image-qa-report.json.

### Lint false-positive classes (v3.31 follow-through the visual-design release missed)
- **[MED] render_lint L1 flagged legitimate inline code** — `` `<a href>` `` renders as
  `<code>&lt;a href&gt;</code>`, which is intentional display, not a leak. L1 now excises
  `<code>/<pre>` spans before scanning (a real raw-tag leak elsewhere in the element still
  fires). Authoring conventions updated.
- **[MED] AI-tells `_STRUCTURAL_SUPPRESS` didn't know the v3.31 visual blocks** — By the
  Numbers / Glossary / TL;DR / At a Glance PRESCRIBE bold-led list formatting, so every
  designed article carried a false P10/P14/P15/P26/P28/P42 floor (~20 raw score) the
  humanizer could not clear without de-designing frozen blocks. Suppress entries added.
- **[MED] Capsule-lint denominator counted the visual blocks** (observed 63.6% / 40%
  coverage while every real content H2 was covered). `Glossary` / `By the Numbers` /
  `At a Glance` added to the structural exclusions.

### Tavily (research reliability)
- **[HIGH] `tavily_research` never polled the async job.** `/research` answers
  `200 {status:"pending", request_id}` when a job outlives the sync window; the script
  returned that pending payload as the final "answer" (all 3 researchers lost their pro
  deep-research to MCP fallback). Now polls `GET /research/{request_id}` (default 900s
  deadline, `--poll-timeout/--poll-interval` CLI), reusing the submitting key.
- **[MED] Dead keys (401 / account deactivated) were never marked (Rule 9 gap).**
  `InvalidAPIKeyError` was neither transient nor quota → fail-fast, unmarked, re-selected
  by round-robin forever. New persistent `status:"invalid"`: classification by exception
  TYPE (`is_invalid_key_error`), `with_retry` persist-marks + rotates past dead keys,
  `get_tavily_key` skips them (and never falls back to them), `tavily_pool --refresh`
  marks a 401 /usage answer invalid (and auto-recovers if the account is reactivated).

Tests: `test_root_cause_fixes_2026_07_01.py` (28 seam tests, each reproducing the real
batch failure shape). Full suite 628 passed / 4 xfailed.

## [3.31.0] - 2026-06-30 (Visual Design System — every article is scannable + well-designed)

A dedicated design layer so articles are not walls of text, grounded in evidence (Princeton
GEO KDD'24; Nielsen Norman Group eye-tracking). Substance over ornament: the components that
raise AI-citation (quotations +41%, statistics +30.6%, cite-sources +27.5%, comparison tables)
are prioritized, and over-design (banner-blinded boxes, decorative pull-quotes) is capped.
Design spec: `docs/superpowers/specs/2026-06-30-visual-design-system-design.md`.

**Phase 1 — universal CSS components** (`scripts/build/article_css_generator.py`): every project
now inherits a By-the-Numbers stat-card grid, TL;DR box, At-a-Glance table treatment, Glossary
cards, typed callouts (note/info/tip/warning/danger), and a pull-quote — all from NATIVE markdown
(body renders `html:False`), dark-mode-safe (never `--xr-primary` for foreground), plus new
`--xr-warn-*`/`--xr-danger-*` status tokens in both palettes. Font-reader now accepts `fonts:`
block + `heading_family` (fixes silent wrong-font regen for project-kilo/project-hotel/project-juliet).
The DARK palette's link/strong are now brand-parameterized (were hardcoded project-echo gold), so any
dark project renders on-brand (project-echo stays gold via its own accent). **All 6 projects migrated**
to the `--xr-*` component CSS: loamwright (stale `#0F3D2E` corrected to real teal `#138670`),
project-echo (dark), project-charlie, project-kilo + project-hotel (added `colors.secondary` to fix wrong
default-magenta links), and project-juliet (a live probe showed its posts render on WHITE, not the
dark config palette — migrated as light: navy `#1a1a2e` headings, navy `#0f3460` links, cyan
`#00b4d8` accent). Every project now inherits the components on regeneration.

**Phase 2 — author-side wiring**: new `references/style/visual-design-components.md` catalog;
`design_components[]` added to `schemas/outline.schema.json`; outline-architect assigns components
per format; section-drafter loads the ref + validates requested components appear; writer gains a
hard constraint.

**Phase 3 — the dedicated design pass**: new `visual-designer` optimize-phase agent + subskill
(restructures prose into components, idempotent, never invents facts / edits headings / touches
citations), inserted after geo-optimize and before render-lint so all gates re-run on the designed
draft. New `scripts/lint/visual_density_check.py` enforces a FLOOR (>=1 Tier-A substance component +
weighted min) that BLOCKS publish (MANDATORY gate — wired in `run_pipeline._GATE_STAGES` +
`orchestrator._PASS_FLAG_REQUIRED` + `pre_publish_gate.MANDATORY_GATES`; a failing draft routes
GATE_FAILED back to the visual-designer), and a CEILING (over-used pull-quotes/callouts) as advisory
WARNINGS that never block. The visual-designer runs immediately before the gate and clears the floor
for legitimate articles, so it fires only on a genuine wall-of-text. Publisher hook
`_tag_callouts_and_pullquotes` tags typed callouts/pull-quotes on rendered HTML (mirrors the
faq-question seam). Provenance enforced. Weekly digests get the design pass automatically.

**Audit hardening (2026-07-01, root-cause fixes from a 3-agent adversarial audit — verified
running real code).** The audit confirmed skill/project separation is intact (no leaks) and
fixed 7 real bugs + 1 dead reference, all of the same class the HARD RULES name (a behavior
split across two implementations that misbehaves on inputs the other never exercised):
- **[HIGH] At-a-Glance header illegible** (white on light accent, WCAG fail on 5/6 projects):
  added a luminance-computed `--xr-on-accent` token; the header now uses contrast-safe text.
- **[HIGH] font stack double-quoted** — a project storing a full `heading_family` stack got
  `font-family: ''Inter',…'` (invalid → no brand font). New `_css_font()` emits a stack verbatim,
  a bare name quoted; also reads bare `typography.heading/body`. project-juliet now fonts correctly.
- **[MED] gate vs publisher blockquote classifiers had drifted** → one shared source of truth
  `scripts/_core/blockquote_classify.py` (adds `danger`; a curly/straight quotation is substance,
  NOT a decorative pull-quote — which had silently defeated the pull-quote ceiling).
- **[MED] mandatory gate had no escape** → per-project `visual_density_required:false` opt-out;
  corrected the stale "advisory" stage description; ceiling downgraded to advisory warnings.
- **[MED] data charts weren't Tier-A** → a chart-rich article no longer false-fails the floor
  (charts counted as substance from `image-prompts.json`, not double-counted as decorative images).
- **[MED/latent] dark link/strong failed contrast for deep accents** → luminance-clamped derivation.
- **[LOW] stat-grid over-credited vs CSS `+ ul` adjacency** → detection now matches the selector.
- **Rule-6 dead reference** `references/style/em-dash-prohibition.md` (Read-referenced by 4 files)
  — created. **Rule-10:** added a dynamic `run_pipeline`/`next_stage` seam test + a gate↔publisher
  cross-check test. All 6 projects regenerated. Full suite 600 passing.

Tests: `test_article_css_components`, `test_visual_density_check`, `test_callout_tagging`,
`test_visual_designer_seam` (Rule-10 seam), `test_blockquote_classify`.

## [3.30.2] - 2026-06-30 (Project/skill separation hardening of the weekly-digest fixes)

A separation audit of the v3.30.1 fixes (project-level config vs client-agnostic skill code):
confirmed the digest engine derives `authority_domains`, competitor `do_not_cite`,
`series_keyword`, and `hub_page` from project config (the `_AGGREGATOR_DOMAINS`
reddit/HN/x/twitter list is a correct universal skill-level constant). Two leaks fixed:

- **The digest category NAME was hardcoded `"Weekly Digest"` in skill code** (`category_selector`).
  The category is PROJECT state — now derived from the project's WP live snapshot
  (`categories-live.json :: categories_by_id[id].name/.slug`) so `meta['categories']` matches the
  ACTUAL WordPress category the pinned ID points to (e.g. "SEO News"), with the generic
  `"Weekly Digest"` only as a no-snapshot fallback. (+2 tests)
- **Skill docs referenced the SEO-specific `/seo-news/` hub path** as if it were the default. The
  real default is the generic `/weekly-digest/` (`weekly_digest.hub_page` is per-project). Fixed in
  `skills/weekly-digest/SKILL.md` (Step 10), `subskills/init/website-project-init/SKILL.md`, and the
  `hub_page_publisher` docstring — `/seo-news/` is now shown only as an example project override.

Full suite 551 passed / 4 xfailed.

## [3.30.1] - 2026-06-30 (Re-audit of the v3.30.0 fixes — 8 holes the 11-bug audit left or itself created; new HARD RULE 10)

The v3.30.0 audit's 11 fixes were verified correct at the right layer (T1 confirmed against the
*real installed* `tavily-python` SDK source; H1–H8 confirmed genuinely wired). But two of its OWN
fixes introduced regressions and several left gaps — all of the same class: **the unit tests
exercised the helpers in isolation and never the `main()` wiring that connects them.** Every fix
below is TDD-first (failing test → fix); full suite green (549 passed, 4 xfailed).

### Fixed — weekly-digest runner (`industry_news_runner.py`)
- **D1 (regression introduced by v3.30.0's D2): a recurring "developing" story was silently
  dropped from the digest.** The D2 fix de-duplicated follow-ups against *all* of `ranked`, but
  only `ranked[:keep]` is actually published — a story sitting in `ranked[keep:]` was removed from
  the follow-ups (assumed it would appear as a fresh item), yet never published and never promoted:
  it vanished. Root cause: the dedup exclude-set ≠ what's published, and `keep` itself depends on
  the dedup (circular). Extracted the budget logic into a pure, testable **`resolve_issue_budget`**
  fixpoint: a recurring story now appears exactly once (promoted to fresh when it makes the cut,
  else kept as a follow-up) and is never dropped.
- **D2: follow-ups bypassed the `items_per_issue` cap, and `theme_of_week` could name a story not
  in the issue.** `resolve_issue_budget` now counts follow-ups against the cap; `theme_of_week` is
  recomputed from the final assembled `items[0]` after follow-ups are prepended.
- **D3: one bad connector *import* crashed the whole runner** (the opposite of D4's continue-on-
  failure). The shared `from scripts.fetch import …` was unwrapped; now guarded — an ImportError
  degrades each affected connector to `status:"error"` and the runner continues.

### Fixed — weekly-digest hub / category
- **H1 (gap left by v3.30.0's H5): the series hub page could NEVER be published** — H5 stopped a
  refresh from clobbering status but added no path to ever transition the hub live, so
  `/weekly-digest/` stayed a permanent draft (404). Added **`resolve_hub_status`** (explicit
  `--status` > project `publish_policy.default=="publish"` opt-in > draft-first/H5), wired into
  `hub_page_publisher.main()`, and fixed SKILL.md Step 10 to pass `--status publish` in the live
  flow (it previously instructed to always omit it).
- **H2: the digest category pin set `category_ids` but not `meta["categories"]`**, so the MANDATORY
  `pre_publish_gate.check_meta` (requires non-empty `categories`) could hard-block the digest
  publish even though the ID was correct. The short-circuit now also sets the name list.
- **H3: `find_page_id` treated a 200-with-non-JSON body (CF interstitial) as "not found"** → would
  POST a duplicate hub page. Now raises on any non-list lookup body; only an empty list = "create".
- **H4: `isinstance(category_id, int)` accepted `true`** (bool is an int subclass; `int(True)==1`)
  → would pin Uncategorized. Now excludes `bool`.
- **H5: no warning when `weekly_digest.enabled` but `category_id` is missing/invalid** — silent
  fall-through to Uncategorized. Now warns to stderr.

### Fixed — Tavily pool coverage
- **`cross_reference_check.py` did a raw one-key `httpx.post` to Tavily with no rotation/retry** —
  a 429 under parallel-session bursts (Rule 7) silently degraded fact-check corroboration. Migrated
  to `tavily_retry.with_retry` so every Tavily call site shares the pool's resilience, not just the
  `fetch/` scripts. (`real_photo_sourcer.py` already rotates via its own loop — left as-is.)

### Cleanup
- `category_selector.py`: removed 2 ruff `F541` f-strings and a mypy variable-reuse false-positive
  (distinct loop var for the `rejected_categories` list[dict]).
- `.gitignore`: `memory/metrics-index.json` (runtime, holds absolute paths) and
  `public-health-articles/` (generated articles) — runtime artifacts, never part of the plugin.

### Added
- **HARD RULE 10** (`CLAUDE.md`): test the END-TO-END wiring, not just helpers in isolation. A fix
  verified only by isolated-helper tests can still regress or leave a gap at the `main()` seam that
  connects them — exactly how D1 (regression) and H1 (gap) slipped past the v3.30.0 audit.

## [3.30.0] - 2026-06-30 (Deep audit of recent Tavily-pool + weekly-digest commits — 11 bugs root-caused & fixed; new HARD RULE 9)

A focused audit of the most recent updates (the balance-aware Tavily key pool and the
weekly-industry-digest feature) found that several "fixes" were patching the wrong layer and
that the digest's hub half was documented-but-unwired. All fixed at source with TDD against the
REAL conditions; full suite green (536 passed).

### Fixed — Tavily balance pool
- **T1 (critical): error classification was dead against the real SDK.** `tavily_retry.py`
  matched message substrings (`"429"`/`"432"`/`"rate limit"`), but `tavily-python` raises
  `UsageLimitExceededError` (HTTP 429) and `ForbiddenError` (403/432/433) with the status code
  NOT in `str(exc)`. A real per-minute 429 was therefore classified `is_transient=False` —
  `with_retry` never rotated keys, so the entire pool-rotation feature died on the first
  rate-limit blip. Rewrote to classify by **exception type**; 429 rate-limit is transient-only
  (never persist-marks a key — that drains healthy keys under Rule 7 parallel bursts), 432/433
  is transient + persist-mark. Reverses the mis-aimed b67d5eb "rate limit → quota" change.
- **T2:** added `file_lock.atomic_write_text` (temp + `os.replace`); the pool ledger and
  digest state files now write atomically so lock-free readers never see a torn file.

### Fixed — weekly-digest runner (`industry_news_runner.py`)
- **D1 (data loss):** covered.json recorded `ranked[:items_per_issue]` but only published
  `followups + ranked[:keep]` → ranked-but-unpublished stories were recorded "reported" and
  suppressed forever. Now records only the items actually published (`build_covered_update`).
- **D2:** a developing story recurring in the harvest was emitted twice (new + follow-up) and
  never promoted; added `dedup_followups` + developing→reported promotion.
- **D3:** covered.json read-modify-write now happens inside the lock (`_update_covered`) — no
  lost update under concurrent same-project runs.
- **D4:** connector exceptions are logged and surfaced as status `error` (was swallowed +
  mislabeled `degraded`); all Tier-A connectors wrapped uniformly.

### Fixed — weekly-digest hub/category (was Rule-6 dead code)
- **H1:** `weekly_digest.category_id` now pinned into `meta.category_ids` by `category_selector`
  (digests were silently landing in Uncategorized — the SKILL.md claim had no executor).
- **H2:** `hub_page_publisher` is now actually invoked (weekly-digest SKILL.md Step 10).
- **H3/H7:** issues.json carries the published title+url and is idempotent by `task_id`.
- **H4:** digest verification now passes `--min-images 1` (was failing OVERALL on every run).
- **H5:** hub refresh no longer flips an already-published hub back to draft.
- **H6:** `find_page_id` raises on lookup failure instead of silently creating a duplicate page.
- **H8:** JSON-LD block escapes `<` so a harvested `</script>` cannot break out (stored-XSS).

### Added
- **HARD RULE 9** (`CLAUDE.md`): classify external SDK/API errors by exception TYPE, and test
  against REAL SDK error objects — not hand-built `Exception("429 ...")` strings.

## [3.29.2] - 2026-06-30 (Completes Fix #4 from the 3.29.1 audit: un-gameable AI-slop burstiness)

The 3.29.1 humanizer fix capped fragment insertion via instructions; this hardens the SCORER
itself so the gaming is mechanically impossible, not just discouraged.

### Fixed — staccato penalty makes burstiness un-gameable (calibrated, zero-impact on good content)
- `ai_slop_score` burstiness is σ/μ of sentence lengths with no floor on short sentences, so
  stacking ≤5-word fragment-closers ("Pure leakage.") inflated the CV, dropped the burstiness
  penalty, and slid the score under the `<20` gate — exactly the staccato a reviewer flags as the
  top AI tell. Added a **one-sided, capped staccato penalty** on the ≤5-word sentence ratio
  (`scripts/lint/sentence_variance.short_sentence_ratio` + `STACCATO_THRESHOLD=0.15`,
  `WEIGHT=100`, `CAP=15`). **Empirically calibrated** against a 15-draft shipped corpus whose
  ratio maxed at ~0.134: normal/format content (bullets, table cells, terse-but-real prose) gets
  **ZERO penalty** (verified 0/15 corpus drafts penalized), while clear fragment-gaming (the
  reviewer-flagged article sat at 0.18) is caught and stacking fragments now RAISES the score
  instead of lowering it. Exposed `staccato_component` + `short_sentence_ratio` in the report.

## [3.29.1] - 2026-06-30 (Pipeline-hardening: 7 root fixes from the loamwright 3-article batch audit)

Root-cause audit of a 3-article batch (loamwright). All 3 published correctly, but the run needed
~8 manual interventions — each a latent bug/gap exposed by the batch (none were recent regressions).
Fixed at the source, each with a regression test (24 new tests; full suite 414 passed).

### Fixed — image-prompts.json shape (HIGH; silent-failure class)
- The `image-prompt-designer` LLM inconsistently emits `prompts` as a list OR a dict keyed by slot_id.
  Six consumers each hand-rolled their own unwrap; **three failed SILENTLY** on the dict shape
  (`render_data_charts` → 0 charts, `real_brand_image_pipeline` → 0 photos, and
  `pre_publish_gate.check_images` iterated dict keys so its "every declared slot has an image" check
  **passed vacuously** — an article could ship with missing images + a green gate). New shared
  normalizer `scripts/_core/image_prompts.py` (`normalize_image_prompts`/`load_image_prompts`); all 6
  consumers refactored to it. Added `schemas/image-prompts.schema.json` + hook registration so a
  dict-shaped write is **blocked loudly at the source**. Pinned the array contract in the agent +
  subskill docs; fixed the stale `image_prompts.json`→`image-prompts.json` filename.

### Fixed — claim-marker leak + fake L5 hard-veto (HIGH)
- `_build_in_text_replacement_map` dropped empty-`to` entries (`if marker and repl:`), so the
  fact-checker's author-experience strips (`{from,to:""}`) were treated as unresolved and **leaked**
  ~12 markers/article. Now an explicit empty `to` records as a clean strip (+ whitespace cleanup in
  `citation_inject`). Critically, render_lint **L5 was a fake hard-veto** — it applied citations
  in-memory (stripping markers) *before* linting, so it could only fire when `citations.json` was
  absent. Added a RAW-body claim-marker scan (gated on `citation-inject-result.json`) so L5 genuinely
  vetoes a leaked marker. Documented the `to:""`=strip contract in the fact-checker agent + subskill.

### Fixed — fact-check `FIX_REQUIRED` gate had no resolution path (HIGH)
- `pre_publish_gate` has blocked `FIX_REQUIRED` since v3.9.0, but `seo-blog/SKILL.md` still advertised
  it as publish-acceptable and no re-fact-check loop was wired — forcing a provenance-tampering manual
  verdict flip. `orchestrator.verify_stage` now blocks `FIX_REQUIRED` at the build stage (so the runner
  re-yields fact-check → re-dispatch the fact-checker → fresh provenance-stamped `CLEAN`). Aligned the
  docs: `FIX_REQUIRED` is an INTERMEDIATE state resolved by re-running the fact-checker, never by hand.

### Fixed — humanizer gamed the AI-slop burstiness metric (MED)
- Burstiness is σ/μ with no floor on short sentences, and the instructions said "Use fragments." with
  no cap — so the humanizer stacked terse fragment-closers ("Pure leakage.") to clear `<20`, which a
  reviewer flags as the most visible AI tell. Capped fragment insertion (~1 / 150-200 words, never a
  repeated para-closer) in the humanizer agent + subskill. (Scorer-side hardening shipped in 3.29.2 —
  a calibrated, one-sided staccato penalty that makes the gaming mechanically impossible.)

### Fixed — data charts + article CSS ignored the brand palette (MED)
- `/init`'s `setup_wizard` writes FLAT `primary_color` keys; `render_data_charts` and
  `article_css_generator` read NESTED `colors.{primary,…}`. loamwright (first flat-schema chart
  project) fell back to matplotlib slate / the `#0F3D2E` CSS default. Both readers now accept BOTH
  shapes; `setup_wizard` now also emits the canonical nested `colors` block.

### Fixed — minor: angle-title bound + serp_features under-population (LOW)
- `angle.title` must be 50-65 chars (`angle.schema.json`) but that was undocumented; added it to the
  format-selector skill + the orchestrator dispatch_prompt. serp-analysis auto-completes at ≥3
  `serp_features`; instructed the researcher/serp-analysis to mirror every observed feature from
  `_serp_features_detail` so it doesn't stall the runner.

## [Unreleased] - 2026-06-27 (Real-brand image executor: generalized to skill-level + monitor record-loop closed)

Two architectural-debt fixes from a deep audit of the 2026-06-23 project-echo real-brand image executor.

### Changed — real-photo executor is now domain-neutral (skill-level clean; project customizes)
- The real-photo sourcer/editor/pipeline no longer hardcode vertical wording. Five concerns moved to
  project config (`business-context.json :: image_sourcing_policy`): `product_noun`, `search_terms`
  (with `{brand}` placeholder), `negative_terms`, `editing_real_photos.ymyl_clause`, `style_clause`.
  Resolved by `image_brand_policy.ImageBrandPolicy` (new fields, all with generic defaults:
  `product_noun="product"`, empty terms/clauses) and threaded through `real_photo_sourcer`
  (`build_search_queries`/`score_candidate`/`source_real_photo`), `product_photo_editor`
  (`build_edit_prompt`/`rescene_product`), and `real_brand_image_pipeline` (`generate_slot`,
  new pure `build_alt_text`). `_LIFESTYLE_TERMS` lost `smoking`/`smoker` (now project-echo `negative_terms`).
- **Effect:** project-echo behaviour is byte-identical (its config reproduces the old strings); a future
  NON-vertical real-brand project (e.g. a watch/sneaker site) plugs in via config with zero code edit.
  project-echo vertical wording now lives in `projects/project-echo/business-context.json`, not in `scripts/`.

### Fixed — monitor verification loop actually closes (Rule 6)
- `optimization_journal --record` was implemented + documented but no fixer skill called it (prose-only
  "should call --record"). Wired a concrete `python -m scripts.monitor.optimization_journal --record`
  invocation into the post-publish fixers: `subskills/cross-cutting/rewrite` (Phase 7) and
  `subskills/optimize/ai-overview-recovery` (Phase 3.5). Enforced by `tests/test_optimization_journal_wiring.py`.

### Tests
- +18 unit/wiring tests (generalization defaults/overrides for policy, sourcer, editor, pipeline;
  the live-project-echo-config preservation check; the --record wiring audit). Full suite 368 passed / 4 xfailed.

## [3.29.0] - 2026-06-26 (Community Research Surface — Reddit/X, always-on, verified, never-cited)

Makes Reddit + X professional insights a real, always-on research input. Replaces the long-standing
Rule 6 dead-code scaffold in `scripts/analysis/social_research_aggregator.py` (dataclasses + query
templates that NOTHING executed) with a real executor + real orchestration call + integration tests.
Skill-level (reusable across every project); per-project subreddits/handles are project-level config.

### Added
- **`scripts/fetch/community_search.py`** — fetch Reddit/X posts via Tavily `include_domains`
  (reddit.com / x.com,twitter.com). NOT the official Reddit/X API (approval-gated + commercially
  priced); reuses the existing Tavily key-pool, 72h cache, and cost_ledger. `search_community(query,
  *, source, max_results, task_id)`.
- **`scripts/research/community_claim_verifier.py`** — two-tier model. SIGNAL (real language / pain
  points / questions / opinions) passes freely; CLAIM (numeric/causal/experimental assertion) is
  quarantined and scored on 4 dimensions (authoritative corroboration / community consensus / author
  credibility / engagement). Verdict drives writer usage. Rule 8: the authoritative-source lookup
  excludes the project competitor blocklist.
- **`scripts/research/community_research_runner.py`** — the real executor (kills the Rule 6 dead code):
  fetch → classify → verify → emit `community-research.json`, merged into `research.json ::
  community_insights`. Reuses `InsightType`/`categorize_insight` from the former scaffold.
- **`subskills/research/community-research/SKILL.md`** — always-on subskill with the concrete
  `python -m` invocation (Rule 6 compliant — not pseudo-code).
- Tests: test_community_search (3) + test_community_claim_verifier (4) +
  test_community_research_runner_integration (2) + **test_community_never_cited (iron rule)** +
  test_community_wiring_audit (Rule 6). 12 green; 3 new modules mypy --strict clean.

### Changed
- **`skills/phase-research/SKILL.md`** — adds always-on Stage 6 (community-research) with the real
  runner invocation; orchestrator now runs 6 sub-skills.
- **`agents/researcher.md`** — whitelists the community fetch script + runner.
- **`schemas/research.schema.json`** — additive `community_insights` property (signals + verified claims).

### Iron rule
- Reddit/X URLs (`reddit.com` / `x.com` / `twitter.com`) NEVER enter References, in-text citations,
  body outbound links, or JSON-LD `citation`/`sameAs`. A verified claim cites the authoritative
  corroborating source; the community URL is `source_url` provenance only. Enforced by
  `tests/test_community_never_cited.py`.

## [3.28.0] - 2026-06-26 (Close the lifecycle: verification loop + internal-link graph + prune/consolidate planner)

Implements the three highest-ROI gaps the pipeline gap-audit surfaced. All skill-level (reusable
across every project); all write project-level plans/journals and NEVER auto-mutate a live site
(Rule 5a).

### Added
- **`scripts/monitor/optimization_journal.py`** — the missing "did the optimization work?" loop.
  `record_change()` logs each fix (before/after) with a baseline GSC snapshot; `verify_due()`
  re-pulls GSC at T+14/T+30 and returns a verdict (improved/flat/worse) per change. Without this,
  every title/citation/rewrite was fire-and-forget. Journal: projects/{slug}/audits/optimization-journal.jsonl.
  (Retro-recorded the 6 real project-juliet edits made this session, with live baselines.)
- **`scripts/monitor/internal_link_graph.py`** — site-wide internal-link graph + ORPHAN repair plan.
  The per-post linker only links FORWARD; this finds pages with too few INBOUND links and suggests
  inbound links from topically-related posts (title-token similarity) + an anchor. Live: project-juliet
  160 posts → 116 orphans with suggestions. Plan: projects/{slug}/audits/internal-link-plan.json.
- **`scripts/monitor/prune_consolidate_planner.py`** — the "act" half of content cleanup (content_audit
  only detects). From GSC, finds same-query page competition → consolidation plan (keep the stronger
  by clicks/impressions, 301 the weaker); prune candidates = content_audit THIN/STALE + near-zero
  traffic. Live: 2 real cannibalization merges after filtering GSC brand/content-blob "query" noise.
  DESTRUCTIVE output — never auto-executed; human signs off.
- Tests: test_optimization_journal (4) + test_internal_link_graph (3) + test_prune_consolidate_planner
  (3). 58 monitor/serpapi/google tests green; all 3 modules mypy --strict clean.

### Changed
- **`skills/phase-monitor/SKILL.md`** — "Closing the loop" section wiring all three as concrete
  commands; the lifecycle is now create→publish→monitor→diagnose→fix→**record**→**T+14/30 verify**→learn.


## [3.27.1] - 2026-06-26 (CRITICAL: grant the authoritative MCPs to researcher + fact-checker)

A Rule-6 wiring audit found that the authoritative-source MCPs wired in v3.20.0 were DEAD: the
researcher + fact-checker agent prompts instruct calling `mcp__us-gov__*` / `mcp__pubmed__*` / etc.
(STAGE 9 + grounding section), but the agents' `allowed-tools` excluded all MCPs
(`[Read, Write, Bash, WebFetch(, WebSearch)]`) — so the agents could never actually invoke them, and
every "Tier-1 primary source" grounding silently fell back to Tavily/secondary sources.

### Fixed
- **`agents/researcher.md`** + **`agents/fact-checker.md`** — added the MCP servers to `allowed-tools`
  (mcp__tavily, mcp__us-gov, mcp__pubmed, mcp__courtlistener, mcp__wikidata, mcp__semantic-scholar,
  mcp__chembl, mcp__pophive, mcp__biorxiv; researcher also context7/ms-learn). The STAGE 9 / grounding
  wiring + the YMYL fact-check workflow now actually function. (This is also what the THIN_SOURCING
  remediation in v3.27.0 depends on.)

EOF: known remaining wiring gaps (tracked, not yet fixed): keyword-research + serp-analysis subskills
still mark SerpApi as FUTURE/TODO; refresh_decision_router + content_audit are in phase-monitor
feedback-loop prose but not the STAGES list; no scheduler/verification-loop (all monitoring manual).


## [3.27.0] - 2026-06-26 (content-quality axis: mechanical scanner + YMYL deep-audit loop)

Adds the SECOND optimization axis the refresh router was missing. The router is SIGNAL-driven
(CTR/rank/AI) and never reads the body, so it cannot see a post that ranks fine yet is thin,
stale, orphaned, or weakly-sourced. This adds the CONTENT-driven axis.

### Added (skill-level)
- **`scripts/monitor/content_audit.py`** — mechanical content scanner: reads every published post
  via WP REST and flags THIN (low words), STALE (long unmodified), ORPHAN (<3 distinct internal
  links — counts relative AND absolute, dedups targets), THIN_SOURCING (<2 distinct external
  citations — E-E-A-T risk on YMYL), YEAR_DRIFT. Writes projects/{slug}/audits/content-audit.json.
  Pure `analyze_post()` + `audit_site()`; `--site`/`--all`/`--json`.
- **`tests/test_content_audit.py`** — 6 tests (each flag, relative-link counting, healthy). 48
  monitor/serpapi/google tests green; mypy --strict clean.
- **`skills/phase-monitor/SKILL.md`** — "Second axis — content quality" section: run the scanner;
  fix ORPHAN -> internal-linker, THIN_SOURCING -> authoritative citations (us-gov/pubmed MCPs),
  THIN/STALE -> rewrite /update; route accuracy/citation-authority (LLM-only) to fact-checker.

### Notes
- Live (project-juliet, 160 posts): 88 ORPHAN, 59 THIN_SOURCING — the deep pillar posts under-link
  and under-cite. Building the scanner also surfaced + fixed two accuracy bugs in it (relative
  internal links were missed; duplicate links / same-DOI double-counted -> now distinct counts).
- What the scanner CANNOT catch (factual errors, outdated specifics, citation AUTHORITY) needs an
  LLM read. Demonstrated the 2b deep loop on the YMYL post is-petg-food-safe: replaced a commercial
  -blog citation (inplexllc) used for a food-safety claim with FDA 21 CFR 177.1630 (ecfr.gov) inline
  + a peer-reviewed emissions study (PubMed PMID 40953477, J Occup Environ Hyg 2026) in References.
  (Project-level live-post edit; not a code change.)


## [3.26.1] - 2026-06-26 (router: collapse GSC anchor fragments -> one article = one opportunity)

Found while auditing project-juliet's published posts: GSC reports table-of-contents anchors
(`/post/#section`) as separate "pages", so the router double-counted the same article as many
opportunities (project-juliet looked like 81 optimizable posts; the true count is ~39).

### Fixed
- **`scripts/monitor/refresh_decision_router.py`** — `_base_url()` strips the `#anchor`; rows are
  now aggregated by `(query, base-URL)` with impression-weighted position before the impressions
  threshold + classification, so one article is one opportunity (impressions summed across its
  anchors). +2 tests (fragment strip, anchor collapse → single action w/ summed impressions).

Live re-check (project-juliet): plan now has zero `#`-fragment targets; distinct articles, not
anchor duplicates.


## [3.26.0] - 2026-06-26 (Refresh Decision Router: close the monitor -> action loop)

Implements the missing dispatcher in the post-publish feedback loop. Root cause (confirmed by a
3-stream investigation): the loop existed only as PROSE in phase-monitor + content-refresher with
NO code — monitoring surfaced opportunities but a human had to manually full-rewrite everything.
The architecture review concluded: do NOT build a new optimization subskill (the ~14 optimize/*
actions already exist); build a thin router that DIAGNOSES + ROUTES to the minimal sufficient
existing skill. Spec: docs/superpowers/specs/2026-06-26-refresh-decision-router-design.md

### Added (skill-level — reusable across every project, synced to cache)
- **`scripts/monitor/refresh_decision_router.py`** — reads first-party GSC (query+page) +
  serpapi AI-citation, classifies each opportunity by signal using 2026 CTR/GEO thresholds, and
  writes a prioritized plan to `projects/{slug}/audits/refresh-plan.json` naming the minimal skill:
  CONTENT_GAP -> `/article`; PAGE2_DEPTH (pos 11-20) -> rewrite(depth); LOW_CTR (top-10, CTR < ½
  position benchmark) -> meta-builder(title/meta); DEEP_WEAK (pos>20) -> rewrite; NOT_IN_AI ->
  ai-overview-recovery; CANNIBALIZE (2+ pages, same query) -> consolidate. DRAFT-FIRST: writes a
  plan only, never mutates/republishes a live post. `--site`/`--all`/`--no-ai`/`--json`.
- **`tests/test_refresh_decision_router.py`** — 5 tests (page-kind, CTR benchmark, signal
  classification, prioritized plan, cannibalization). 40 monitor/serpapi/google tests green; mypy clean.

### Changed (Rule 6 wiring)
- **`skills/phase-monitor/SKILL.md`** — "Feedback loop" prose table replaced with the router as an
  executable dispatcher + the signal->skill routing table + draft-first guarantee.
- **`subskills/monitor/content-refresher/SKILL.md`** — "Action routing" step: run the router first,
  don't always full-rewrite (top-10 under-click -> cheap meta-builder; tag-page gap -> new article).

### Deliberately NOT built (avoided duplication / non-needs)
- IndexNow — RankMath (auto IndexNow) + Cloudflare already handle indexing for the operator.
- A new optimizer subskill — actions already exist. Auto-publish of fixes — intentionally gated.

Live-validated: project-charlie CONTENT_GAP (hvac tag page) + NOT_IN_AI; project-juliet LOW_CTR
(filament-type-guide pos 9 / 744 impr / 0 clicks -> meta-builder), PAGE2_DEPTH, CANNIBALIZE.


## [3.25.1] - 2026-06-26 (Bing Webmaster: unify site resolution + add to monitor_smoke)

Bing Webmaster Tools was already running (key live, 35 verified sites incl. all 6 projects;
`bing_webmaster_ingest.py` pulls real rank/traffic/query stats). Two consistency/coverage fixes:

### Fixed
- **`scripts/monitor/bing_webmaster_ingest.py`** — `_resolve_site_url` now reads
  `business-context.json :: site_url` first (the canonical source, shared with the GSC ingest),
  normalized to Bing's trailing-slash form; legacy project.yaml + bare-domain kept as fallbacks.
  Previously it depended on project.yaml existing — the bare-domain fallback breaks for any slug
  != registered domain (project-echo -> project-echo.example.com). Now both engines resolve sites from
  one source of truth.

### Added
- **`scripts/monitor/monitor_smoke.py`** — new Bing stage: first-party Bing query_count / clicks /
  impressions alongside GSC + GA4, so the health check covers BOTH engines. Test updated (Bing
  mocked; 35 tests green; monitor_smoke mypy --strict clean).

Live: project-juliet shows **Bing 2029 queries / 1210 clicks / 7544 impr** vs Google GSC 124 clicks
— Bing is its dominant traffic source, invisible until now. project-echo (slug != domain) verified to
resolve correctly via business-context.


## [3.25.0] - 2026-06-26 (monitor_smoke: one-command end-to-end monitoring health check)

Productizes the first-party-data verification into a reusable tool, so any project can be
health-checked across the full monitoring chain in one command.

### Added
- **`scripts/monitor/monitor_smoke.py`** — `--site {slug}` / `--all` runs GSC (clicks/impr/position),
  GA4 (channel breakdown incl. the "AI Assistant" channel), SerpApi live whole-SERP rank for the
  project's top GSC query, and GEO citation checks (AI Overview + AI Mode) — each stage isolated so
  one failure (e.g. brand-new GA4 with no rows) doesn't fail the rest. Surfaces **ranking-opportunity**
  queries (>=50 impressions, position >=20, 0 clicks) — the content-refresher's prime candidates.
  `--no-serp` skips the paid stages; `--json` for machine use.
- **`tests/test_monitor_smoke.py`** — 3 tests (chain assembly + opportunity flag, --no-serp skip,
  per-stage failure isolation). 35 serpapi/google/monitor tests total green; mypy --strict clean.

Live across all 6 projects: chain_ok=True everywhere. Surfaced real signals — project-juliet leads
(9373 impr / 124 clicks, top "is petg food safe"); project-charlie has two high-impression page-4
opportunities ("commercial grow room hvac design" pos 34.6, "grow room hvac design" pos 40.5) with
zero clicks and no AI-answer citation.


## [3.24.1] - 2026-06-26 (Wire the LIVE monitor consumers to the connected GSC/GA4)

After v3.24.0 connected GSC + GA4, this routes the actual pipeline consumers at the working
credential — the root-cause fix that makes phase-monitor run on real first-party data. (All 6
projects now verified end-to-end: GSC + GA4 both return 200; GA4 for the 4 RankMath-created
properties matched by data-stream domain.)

### Fixed (root cause)
- **`scripts/monitor/gsc_api_ingest.py`** — the LIVE GSC ingest (referenced by 3 orchestration
  files) authenticated ONLY via `gsc-oauth/{slug}.json` → service account (both absent here), so
  it never used the connected token; and `_resolve_site_url` read `project.yaml` (these projects
  use `business-context.json`), falling through to a broken bare-domain guess. Now: `_get_access_token`
  uses `google_creds` first (legacy paths kept as fallback); `_resolve_site_url` reads
  `business-context.json :: analytics.gsc_property` first. **Live-verified**: project-charlie pulled
  475 rows / 86 URLs of real GSC data. (The analysis/ GSC+GA4 clients have 0 orchestration
  consumers — dead code — and were intentionally left untouched.)

### Added (Rule 6 wiring)
- **`subskills/monitor/content-refresher/SKILL.md`** — the decay formula (0.30×traffic +
  0.25×rank + 0.15×ctr + …) had no executors for its inputs. Added concrete data sources:
  traffic_drop ← `ga4_fetch`, rank/ctr ← `gsc_api_ingest`, replacement_pressure ← `serpapi_query`,
  all keyed off `business-context.analytics`; empty new-GA4 → traffic_drop=0 (not a crash).

## [3.24.0] - 2026-06-26 (First-party Google data: unified GSC/GA4 resolver + per-project wiring)

Fixes a Rule-6 gap: the user had connected GSC + GA4 (an OAuth token at
`credentials/google-oauth-token.json`, scopes webmasters.readonly + analytics.readonly), but
NO consumer script read it — the audit-google agent called `scripts.audit.gsc_fetch` /
`ga4_fetch` which **did not exist**, and the analysis/monitor scripts looked for env vars /
service-account / per-site oauth that were never set. So the most valuable first-party SEO data
was authenticated yet orphaned. Discovery (live, read-only): all 6 projects have GSC; only
project-charlie + project-echo have GA4 (4 missing).

### Added
- **`scripts/_core/google_creds.py`** — single source of truth for Google auth: reads
  `google-oauth-token.json`, refreshes the access token (in-process cache), exposes
  `get_access_token()` / `auth_header()` / `scopes()`.
- **`scripts/audit/gsc_fetch.py`** — the missing GSC executor the audit-google agent references:
  `--property "sc-domain:…" --days N --json` → Search Analytics rows. **Live-verified** against
  project-charlie (real query/impression/position data).
- **`scripts/audit/ga4_fetch.py`** — the missing GA4 executor: `--property-id N --days N` →
  runReport channel-group breakdown (organic sessions visible).
- **`tests/test_google_creds.py`** — 3 tests (token refresh + cache, refresh-failure raise, GA4
  row parsing). mypy --strict clean.
- **`projects/*/business-context.json`** — new `analytics` block per project with the resolved
  `gsc_property` (all 6) + `ga4_property_id` (project-charlie 538840772, project-echo 539743114; the other
  4 are null pending GA4 property creation) + `bing_webmaster: true`.

### Notes
- GSC works end-to-end now. GA4 read returns 403 until the **Google Analytics Data API** is
  enabled in the OAuth project — one click in the Cloud console; the Admin API was
  already enabled. Creating the 4 missing GA4 properties additionally needs an `analytics.edit`
  re-auth (current token is read-only) — tracked as a follow-up.

## [3.23.1] - 2026-06-26 (phase-monitor: google_ai_mode as a 2nd Google GEO signal)

- **`skills/phase-monitor/SKILL.md`** — ai-visibility-tracker now tracks BOTH distinct Google GEO
  surfaces independently: `ai_overview` (inline AI Overview) AND `google_ai_mode` (the dedicated AI
  tab). Live-verified that `google_ai_mode` returns a rich `references[]` (e.g. 26 entries for a
  product query) of `{title, link, source, snippet}` — the citation check matches the project domain
  against every `references[].link` and records cited?/rank per engine + per query. Corrected the
  earlier non-US line (dropped the unverified `naver_ai_overview` engine id → `naver`/`baidu` are
  callable for non-US markets). No code change; wiring + accuracy only.

## [3.23.0] - 2026-06-26 (SerpApi engine registry + vertical-aware on-demand selector)

Answers "should we add all ~110 SerpApi engines and load them on demand?" with the right
architecture: **don't** bloat agent prompts with a 110-engine list (context blow-up + decision
paralysis + most engines irrelevant to content SEO). Instead, a data-driven registry + a
deterministic selector pick the right 2-4 engines for an article's vertical/intent/surfaces. All
~110 engines remain directly callable via the generic wrapper; the registry governs *routing*.

### Added
- **`scripts/_core/serpapi_engines.py`** — curated registry of ~33 SEO-relevant engines (core,
  GEO, authority, freshness, video, ecommerce, local, visual, qa, niche, intl), each with its
  REAL query param (verified live — youtube=`search_query`, amazon=`k`, yahoo=`p`, walmart=`query`,
  ebay=`_nkw`, apple_app_store=`term`, naver=`query`, yelp=`find_desc`+`find_loc`, …), category,
  SEO use, and triggering verticals. `query_param_for()` is now the single source of truth for
  per-engine params (serpapi_query imports it). `suggest(vertical, intent, surfaces)` deterministically
  shortlists engines: universal core/GEO always + vertical/intent/surface-specific on top. CLI:
  `--list [--category]` / `--suggest --vertical … --intent … --surfaces …`.
- **`tests/test_serpapi_engines.py`** — 8 tests (param mapping incl. defaults; suggest gating for
  universal/ecommerce/local/surface/freshness/authority; metadata completeness). 29 serpapi tests
  total green; mypy --strict clean.

### Changed
- **`scripts/fetch/serpapi_query.py`** — per-engine query-param map moved into the registry (one
  source of truth; wrapper + selector can't disagree).
- **`skills/phase-research/SKILL.md`** — replaced the static engine table with a registry-driven
  selection step: shortlist via `serpapi_engines --suggest`, run the 2-4 returned. Discipline
  note: always run core 3-4, add only the 1-3 vertical/surface engines surfaced.
- **`agents/researcher.md`** — STAGE 10e calls `--suggest` to shortlist before querying.

### Notes
- Notable engine surfaced: `google_ai_mode` returns `text_blocks` + `references` + `reconstructed_markdown`
  — a second GEO citation signal alongside `ai_overview`. Both are in the GEO category (universal).
- Uncurated engines (flights, hotels, app reviews, ads, finance markets, …) are deliberately not in
  routing — still callable with `--engine X`, just don't auto-fire for content SEO. Add a registry
  entry to bring one into routing.

## [3.22.0] - 2026-06-26 (SerpApi multi-engine on-demand routing + youtube param fix)

Extends the v3.21.0 SerpApi integration so the pipeline calls the right engine ON DEMAND
(not just the 3 hard-wired ones), and fixes a per-engine query-param bug that live testing
against the 21-key pool surfaced.

### Fixed
- **`scripts/fetch/serpapi_query.py`** — per-engine query-param mapping. SerpApi engines do
  not all take `q`: the `youtube` engine needs `search_query` (a bare `q` 400s with
  "Missing `search_query`"), `walmart` needs `query`, `ebay` needs `_nkw`. Added
  `_ENGINE_QUERY_PARAM` (default `q`) applied in `_do_request`. Verified live: youtube now
  returns 19 video_results.

### Added (on-demand engine routing — Rule 6 concrete commands)
- **`skills/phase-research/SKILL.md`** — "Other SerpApi engines" routing table: when to reach
  for `google_trends` (seasonality / rising queries → topic timing), `google_scholar`
  (academic ranking + cited-by counts), `youtube` (video-surface analysis), `google_news`
  (freshness), `google_patents` (IP). Each notes overlap with existing sources so the agent
  picks one, not all.
- **`agents/researcher.md`** — STAGE 10e: call trends/scholar/youtube/news on demand per the
  routing table (explicitly "don't call them all").
- **`skills/phase-monitor/SKILL.md`** — content-refresher now reads `google_trends` interest
  trajectory: a declining search-interest trend is an early decay signal (topic cooling),
  feeding the freshness component beyond rank loss.
- Tests: +5 parametrized cases asserting the query-param mapping (google/scholar/trends → `q`,
  youtube → `search_query`, walmart → `query`). 21 serpapi tests green; mypy --strict clean.

Live-verified through the pool: google_trends (interest_over_time), google_scholar
(organic_results + cite data), google_news (news_results), google_patents (organic_results),
youtube (19 video_results).

## [3.21.0] - 2026-06-26 (SerpApi key-pool + structured-SERP / AI-Overview wiring)

Adds a **SerpApi integration with a Tavily-style free-account key pool**, filling the
pipeline's biggest data gap: Tavily gives generic web search/extract but NOT Google's ranked
positions, People-Also-Ask, featured snippets, or the AI Overview. SerpApi's free tier is 250
searches/account/month, so — exactly like the 100-key Tavily pool — multiple free accounts are
pooled and round-robined to combine quota.

### Added
- **`scripts/_core/serpapi_pool.py`** — self-contained key pool: `get_serpapi_key()` (round-robin
  across `~/.xuanran-seo/credentials/serpapi-pool.json`, single-key + `SERPAPI_KEY` fallbacks),
  `pool_size()`, `add_key()`, `account_status()`. The RR counter and pool file are written under
  `file_lock.locked()` (Rule 7 — parallel sessions must not pick the same key). CLI:
  `--status` / `--add KEY` / `--validate` (uses SerpApi `/account`, which does NOT consume a search).
- **`scripts/fetch/serpapi_query.py`** — unified wrapper over SerpApi's single endpoint (one
  `--engine` param covers google / google_ai_overview / google_autocomplete / google_trends /
  google_news / scholar / patents / bing / naver …). Mirrors the Tavily resilience stack:
  pool round-robin + retry/rotation on quota-429-timeout (reuses `tavily_retry.with_retry`), 6h
  response cache, cost-ledger logging, `--json`. A quota-exhausted key is normalised to a transient
  error so rotation moves to the next pooled account automatically.
- **`tests/test_serpapi_pool.py` + `tests/test_serpapi_query.py`** — 13 tests: round-robin cycling,
  counter persistence, env/file fallback, dedup, quota-rotation, caching, hard-error-not-retried.
- **`scripts/_core/cost_ledger.py`** — `serpapi` pricing branch (free pool = $0; logged for usage
  visibility via `serpapi_searches`).

### Wiring (Rule 6 — concrete executors, not prose)
- **`agents/researcher.md`** — STAGE 10 (keyword-research): real organic positions, true PAA
  (`related_questions`), autocomplete, and AI-Overview presence via `serpapi_query`, overriding
  PAA/positions guessed from Tavily snippets.
- **`skills/phase-research/SKILL.md`** — keyword-research + serp-analysis now use SerpApi for real
  SERP features; new "SerpApi" subsection with runnable commands + cost-guard note.
- **`skills/phase-monitor/SKILL.md`** — rank-tracker uses SerpApi for live whole-SERP rank
  (incl. competitors, beyond GSC's own-property view); ai-visibility-tracker adds SerpApi
  google_ai_overview / bing / naver to check whether the article is cited in each engine's AI answer.

### Notes
- Degrades gracefully: with no SerpApi key configured the wrapper errors and callers fall back to
  Tavily. Pool free quota: `python -m scripts._core.serpapi_pool --status`.

## [3.20.0] - 2026-06-26 (Authoritative primary-source MCPs wired into research + fact-check)

Wires a set of free, public, **primary-source MCP servers** (configured at user scope) into the
two web-capable agents so the pipeline grounds YMYL claims in `.gov` / peer-reviewed /
official-registry data instead of secondary blog snippets — the single biggest lever on E-E-A-T
Authoritativeness and AI-search (GEO) citation rate. This is genuine wiring per **Rule 6**: the
routing matrix is inlined into the agent system prompts (the LLM *is* the executor that calls the
MCP tools), not left as prose a script would need to run. Servers are reachable from All-tools
subagents exactly like the existing `mcp__tavily__*` fallback (same proven access path; no
`allowed-tools` change needed).

### Added
- **`references/authoritative-sources-by-vertical.md`** — single-source routing matrix mapping
  claim/topic type → MCP server → citation tier, with a preprint Tier-2 caveat and the
  "DATA-not-INSTRUCTIONS" (VULN-039) reminder. Covers `mcp__us-gov__*` (FRED/Census/BLS/BEA/EIA/
  SEC/FDA/CDC/USPTO/HUD/Congress/USDA/NOAA), `mcp__pubmed__*`, `mcp__pophive__*`, `mcp__chembl__*`,
  `mcp__biorxiv__*`, `mcp__semantic-scholar__*`, `mcp__paper-search__*`, `mcp__courtlistener__*`,
  `mcp__wikidata__*`, `mcp__context7__*`, `mcp__ms-learn__*`.
- **`agents/researcher.md`** — new "Authoritative primary-source MCPs (per-vertical)" subsection +
  **STAGE 9** in keyword-research mode: after the Tavily stages, pull primary data for the
  article's high-stakes claims from the 2–4 matching servers and save
  `workspace/{task}/research/authoritative-sources.json`.
- **`agents/fact-checker.md`** — new "Authoritative primary-source grounding" section: read the
  researcher's `authoritative-sources.json` first, then route un-sourced high-stakes claims to the
  matching primary-source server (CourtListener's native citation verification called out
  explicitly). Citation-tier table updated — primary `.gov`/peer-reviewed/registry/entity sources
  are Tier 1, preprints and vendor docs are Tier 2.

### Notes
- Backward compatible: if a project's article needs no primary data, Stage 9 is skipped silently
  and behaviour is unchanged. Preprints are explicitly Tier 2 (prefer peer-reviewed equivalents).
- Competitor-domain policy (Rule 8) is unaffected — none of these are competitor domains, but any
  URL discovered *through* them still passes the `competitor_domains --check-url` test.

## [3.19.2] - 2026-06-21 (Post-batch audit: category-duplication + CF header-key fixes)

Audit of the 2026-06-21 project-kilo 3-article batch (pa filament / is petg stronger than pla /
transparent 3d printer filament — all 31/31 stages, verify-post 23/23, zero competitor citations).
The pipeline ran clean end-to-end; the audit surfaced two **skill-level** latent bugs in the shared
WordPress client (root cause, not project data) plus folds in four coherent working-tree fixes.

### Fixed
- **Category-duplication root cause** (`scripts/wordpress/wp_taxonomy.py`): WordPress returns term
  names HTML-entity-encoded (`Drying, Storage &amp; Handling`), but callers query with a literal `&`.
  `find_by_name` did an exact match, so every `&`-bearing category name missed and the publisher
  minted a **duplicate top-level category** (project-kilo orphans 351/352/367/440/507/529). Added
  `_norm_name()` (HTML-unescape + collapse whitespace + lowercase) applied on both sides in
  `find_by_name` and in `create()`'s term-exists handler. `find_by_name` now also prefers the lowest
  id on a tie so a stray duplicate cannot shadow the canonical hierarchical term. Affects every
  project with hierarchical taxonomies. Verified live against project-kilo: all 7 `&`-names now resolve
  to their canonical IDs (283/289/260/264/290/285/286), not orphans.
- **Cloudflare header-key drift** (`scripts/wordpress/wp_client.py`): `_load_cf_bypass_token` read
  only `header_name`, but project-kilo / project-hotel declare the key as `bypass_header` (project-echo uses
  `header_name`). Those projects worked only by coincidence (their header equalled the default). Now
  accepts both `header_name` and `bypass_header`, plus token aliases (`bypass_token` /
  `cloudflare_bypass_token` / `token`). Verified: project-kilo->`x-xuanran-seo-token`,
  project-echo->`x-project-echo-bypass`, both with token.
- `hooks/hooks.json`: events nested under the top-level `hooks` key per the plugin hooks schema
  (the prior flat layout was silently ignored by the loader).
- `scripts/build/data_chart_png.py`: corrected inverted yes/no `STATUS_COLORS` (green=yes, rose=no)
  and added `_destar()` to transliterate star rating cells to `k/total` (the bundled font has no
  star glyph -> tofu boxes).
- `scripts/lint/ai_tells_detector.py`: suppress P10/P14/P15/P26/P28/P42 inside the mandatory FAQ
  section (its prescribed bold-question format is structural, not an AI tell — same treatment as Key
  Takeaways).
- `scripts/wordpress/wp_publisher.py`: `_append_custom_schema_blocks` now also accepts a single
  combined `@graph` JSON-LD dict (the schema-validator subagent's common output form), which the
  key-based loop previously missed and dropped.
- `.gitignore`: added `_*_audit.json` / `_competitor_audit.json` / `pk_posts.json` so one-off
  cross-project audit/REST-dump scratch files are never committed.

### Added
- `tests/test_taxonomy_and_cf_header_fixes_2026_06_21.py` — 8 tests pinning both fixes (entity-name
  matching incl. duplicate-shadowing tie-break; CF header read from either key convention + token
  aliases). Full suite collects 248 tests; new + adjacent WP/publish tests green.

### Notes (no code change)
- **Keyword-density gate behaved as designed**: the 3 articles measured 0.13% / 0.06% / 0.03% exact-
  phrase density (all "too_low"), which is the asymmetric soft-gate's informational, NON-blocking case
  (hard veto only >1.5%); the exact phrase anchors each title/H1/slug/meta + semantic variants carry
  the body. Latent footgun flagged for a future pass: `scripts/lint/keyword_density.py` still returns
  exit 1 on `too_low`, disagreeing with the gate policy — harmless because the orchestrator reads the
  JSON band, not `$?`.
- Pre-existing project-kilo orphan duplicate categories (351/352/367/440/507/529) remain on the live
  site; the code fix prevents NEW ones. Merging/deleting the orphans is project-level live-site
  cleanup (requires reassigning the posts that use them) and was left for an explicit pass.

## [3.19.1] - 2026-06-20 (WPClient respects per-project Cloudflare header_name)

`scripts/wordpress/wp_client.py` hardcoded the Cloudflare bypass header as `X-Xuanran-SEO-Token`,
so any project whose `cloudflare.json` declares a different `header_name` (e.g. project-echo →
`x-project-echo-bypass`) got HTTP 403 "Just a moment…" on every authed REST call — the WAF Allow rule
never matched. Surfaced during the project-echo `/init` publish-readiness verification.

### Fixed
- `_load_cf_bypass_token(site_slug)` now returns `(token, header_name)`, reading `header_name` from
  the project's `cloudflare.json` (defaults to `X-Xuanran-SEO-Token` → existing projects unaffected).
- Both callers updated to inject the resolved header: `WPClient._ensure_client` and
  `verify_post._fetch_live_head`. Verified: `WPClient("project-echo")` authed read returns 200 through
  Cloudflare with `x-project-echo-bypass`. 236 tests pass.

## [3.19.0] - 2026-06-20 (Competitor/peer-domain citation exclusion — 同行 sites never cited)

A competitor / peer ("同行") website could flow into a published article as a **cited source** —
in-text `(Author, Year)`, the References `<ol>`, a body outbound link, or JSON-LD `citation`/`sameAs`.
From the fact-checker onward NOTHING filtered by domain origin (only HTTP health, IP safety, source
tier). `agents/fact-checker.md` literally said `❌ Cite competitor articles directly` — but with **no
executor**: no list, no filter, no veto, no check. A textbook Rule-6 ghost rule. Now machine-enforced
end-to-end. This is **skill-level** (every project benefits automatically); the blocklist is
**project-level** data. See root CLAUDE.md **Rule 8** + `docs/superpowers/specs/2026-06-20-competitor-citation-exclusion-design.md`.

### Added
- `scripts/_core/competitor_domains.py` — single source of truth. `CompetitorPolicy` +
  `load_policy(slug)` / `load_policy_for_task(task_id)` (env-first project resolution, Rule 7 safe),
  suffix domain match (subdomains blocked, false-positive-safe), `find_blocked_in_html()` (anchors +
  bare URLs). CLI `--check-url` / `--scan-file --json`. Disabled no-op when a project has no policy.
- `business-context.json :: citation_source_policy` block (schema-validated): `enforcement`,
  `exclude_competitor_domains`, `scope[]`, `do_not_cite_domains[]`, `competitor_brands[]`,
  `allow_brand_mention_in_prose`, `datasheet_exception`, `sole_source_behavior`. Added to project-charlie
  with 24 verified competitor domains (manufacturers + competing e-commerce). config_version → 1.5.
- `render_lint.py` **L11** (project-aware competitor-domain-cited detector; skips when no policy).
- `cite_scorer.py` **COMP01** out-of-band block-level veto (does NOT alter the 40-item rubric or
  C/I/T/E dimension scores). Wired into `run_quality_gates.py` (already passes `--project-slug`) and
  the combined-verdict hard-veto list.
- `verify_post.py` **check 28** — scans the LIVE page for competitor-domain links.
- `assemble.py` backstop strip (drops surviving competitor refs + their in-text citations).
- `tests/test_competitor_domains.py` (10) + `tests/test_competitor_citation_e2e.py` (8) — prove the
  guard ACTUALLY blocks at every layer (the silent-no-op lesson).

### Changed
- `pre_publish_gate.py` hard-veto filter now includes `COMP01`.
- `agents/fact-checker.md` ghost rule upgraded to real steps: load blocklist, filter sources,
  re-source sole-source competitor claims, record `rejected_competitor_domains[]`.
- `agents/linker.md` (Step 4b outbound-link competitor guard), `agents/geo-auditor.md` (COMP01),
  `subskills/research/competitor-analysis/SKILL.md` (SERP candidate review →
  `competitor-candidates.json`), `subskills/optimize/schema-generator/SKILL.md` (URL-field note).
- `schemas/citations.schema.json`: optional `refs[].domain` + `rejected_competitor_domains[]`.
- Root `CLAUDE.md` **Rule 8**; per-skill copies in `skills/seo-blog/SKILL.md` (Rule 5) +
  `skills/phase-publish/SKILL.md`; `references/seo/authoritative-sources-catalog.md` NEVER-cite list.
- `/init` (website-project-init) now asks every new project for its competitor domains.

## [3.18.0] - 2026-06-18 (Patient Vertex-Gemini retry + serialization — image gen stays on the free 4K primary)

The 2026-06-18 project-hotel batch had 1 of 6 photos fall back from the free Vertex Gemini 3 Pro Image
primary to the paid OpenAI `gpt-image-2` ($1.67) because two photo slots fired in **parallel** and
burst **Vertex AI Express mode**'s **dynamic-shared-quota (DSQ)** per-minute capacity → HTTP 429
`RESOURCE_EXHAUSTED`. The old logic did ONE 60s retry, then leaked the slot to the paid fallback.

Empirical probe on the live key (2026-06-18): a **serial** request → `200 OK`; a **burst of 3
concurrent** → `1×200 + 2×429`. The 429 body carries empty `details[]` (no `RetryInfo`, no
`Retry-After` header) → pure truncated-exponential backoff is required. Google's own guidance for
DSQ 429 (preview models): **serialize + honor `RetryInfo.retryDelay` + truncated-exp backoff + jitter
+ retry to a wall-clock deadline**. Since the pipeline window is hours, we retry patiently and
(almost) never fall back. This is skill-level infra — it applies to **every** project's image gen.

### Added
- `_TransientImageError` (carries a server-advised `retry_after`) + `_parse_retry_delay()` — parses
  `google.rpc.RetryInfo.retryDelay` from the 429 body (with a regex fallback on the message). Defensive
  for keys that DO return it; this Express key returns empty `details[]` → falls through to backoff.
- `_RetryPolicy` + per-provider **patient retry**: Vertex gets a patient policy (10 attempts / 900s
  wall-clock deadline / 20s→90s truncated-exponential backoff + jitter); OpenAI/relays keep a light
  policy. A transient 429/5xx retries the SAME provider until its policy is exhausted, ONLY THEN
  falling over to the next provider.
- **Vertex request throttle** (`_vertex_throttle`): serializes Vertex calls (concurrency `1` by
  default) with an 8s minimum interval between starts — the single biggest lever (serial→200,
  burst→429). Other providers (the OpenAI fallback) are unaffected and still run in parallel. The
  throttle is released during the backoff sleep so a sibling slot can use Vertex meanwhile.
- All knobs env-overridable for ops without a code change: `XS_VERTEX_CONCURRENCY`,
  `XS_VERTEX_MIN_INTERVAL_S`, `XS_VERTEX_RETRY_MAX_ATTEMPTS/DEADLINE_S/BASE_S/MAX_BACKOFF_S`,
  `XS_IMAGE_RETRY_MAX_ATTEMPTS/DEADLINE_S/BASE_S`.
- 6 new tests in `tests/test_image_provider_fallback_2026_06_06.py`: `_parse_retry_delay`, transient
  classification, backoff cap + `retry_after` precedence, patient-retry **stays-on-Vertex** (no
  fallback), exhaust-then-fallback (safety net), and throttle serialization.

### Changed
- `generate_realtime_one` retry loop rewritten: per-provider patient retry (was a single 60s retry
  then immediate fall-over). The slot stays on the cheap free primary through a transient 429 burst.
- `_generate_vertex_gemini` now raises `_TransientImageError` on 429/5xx (was a generic `RuntimeError`).

### Verified
- Live re-run of the 2 concurrent photo slots that previously fell back: **2/2 served by
  `vertex-gemini`, $0.00, fallback_triggered=false** — `process-figures` hit 429 twice, the patient
  retry waited, and it succeeded on attempt 3 on the same Gemini provider (was $1.67 on OpenAI).

## [3.17.1] - 2026-06-18 (Scaffold-marker auto-strip — optimize-phase re-leak never needs a manual fix)

The optimize-phase subagents (humanizer / geo-auditor) edit `draft.md` **after** `assemble.py`'s
normalize pass, re-introducing writer-side scaffold annotation tokens (`[ORIGINAL DATA]`,
`[UNIQUE INSIGHT]`, `[PERSONAL EXPERIENCE]`, `[CAPSULE]`, `[EXAMPLE]`, `[CITATION CAPSULE]`,
`[INFO GAIN]`). This hard-failed the render-lint **L6** gate on nearly every article and forced a
manual strip + re-run (observed twice in the 2026-06-17 project-charlie batch). Root cause was the same
class as before: a strip that ran only at one point in the pipeline, plus a token-set drift
(`assemble._SCAFFOLD_RE` covered 4 tokens, case-insensitive; `render_lint` L6 detected 7,
case-sensitive).

Fix (3 layers, mirroring how `[claim:…]` citations are handled — strip at publish + pre-apply in
the lint check):

### Added
- `markdown_to_html.strip_scaffold_markers(text) -> (cleaned, count)` and `SCAFFOLD_MARKER_RE` — the
  **single canonical source of truth** for the scaffold token set (7 tokens, case-sensitive, upper-case
  so legit lowercase `[example]` prose is never false-stripped). Imported by the publisher, render_lint,
  and assemble so the 4-vs-7 / case drift can't recur.
- `render_lint` CLI flag `--no-apply-scaffold-strip` (parity with `--no-apply-citations`) and
  `LintResult.scaffold_markers_autostripped` (observable signal in `render-lint.json`).
- `tests/test_scaffold_marker_autostrip.py` (7 tests): canonical strip, publisher uses canonical,
  render_lint auto-strips + passes, detector still fires when disabled, assemble strips all 7.

### Changed
- `wp_publisher` strips scaffold markers in the publish path (Step 5e, before markdown→HTML) so they can
  never reach live HTML — even when re-introduced after assembly.
- `render_lint.lint_draft_file` pre-strips scaffold markers **in memory** before linting (default on), so
  a post-optimize re-leak no longer hard-fails the gate; the L6 detector remains a real safety net when
  the strip is disabled.
- `assemble._normalize_markdown` now delegates to the canonical strip (was a private 4-token regex).

## [3.17.0] - 2026-06-17 (Vertex Gemini 3 Pro Image = default 4K provider — relays degraded, Vertex is true 4K ~10x cheaper)

Live deep-research (probed 6 newapi gateways) found that **every relay gpt-image-2 endpoint now
silently degrades 4K to ~1.5MP** (1536×1024 / 1672×941 / 1254×1254) with HTTP 200 — chatgpt-code,
openclawroot, llmtoken, yunxiangpnv all share one `GPT-Image-2-4k (distributor)` upstream that is
actually 1.5MP-capped; aichat199 is 521-down; coze is key-gated. The pipeline's exact-match dimension
gate correctly rejected the degraded output and fell every 4K photo through to **official OpenAI at
~$1.67/image** (verified: 9/9 articles on 2026-06-16 served by the official fallback at $3.3–6.7 each).

Fix: **Google Vertex AI express mode serving Gemini 3 Pro Image (Nano Banana Pro)** is now the default
primary image provider. Verified live: true 4K (16:9 → 5504×3072, 1:1 → 4096×4096, ~16MP), ~10x
cheaper than OpenAI, with markedly better in-image text rendering. Authenticated with an `AQ.`-prefix
API key via the `x-goog-api-key` header (the AQ format only works on Vertex express, NOT AI Studio
`generativelanguage`). Applies to **every project** (provider config + pipeline are skill/global level;
per-project business-context only sets target sizes, already 4K). Evidence + recipe:
`reference_vertex_gemini_4k_image_recipe.md`.

### Added
- `image_provider.ImageProvider.protocol` field (`"openai"` default | `"vertex_gemini"`), parsed from
  `config.yaml :: image.providers[].protocol`.
- `openai_image_pipeline._generate_vertex_gemini()` — Vertex express `generateContent` + `imageConfig`
  adapter (httpx, `x-goog-api-key`, `inlineData` response), plus `_size_to_gemini_imageconfig()`
  (pixel size → nearest aspectRatio @ 4K tier) and `_downscale_to_size()` (center-crop to target
  aspect + Lanczos resize to EXACT requested pixels, so the dimension gate passes).
- `credential_hub` `vertex-gemini` provider (`VERTEX_GEMINI_API_KEY` / `vertex-gemini.key`).
- `tests/test_vertex_gemini_provider_2026_06_17.py` (protocol parsing + size mapping + downscale; 8 tests).

### Changed
- `~/.xuanran-seo/config.yaml :: image.providers` reordered: `vertex-gemini` primary →
  `openai-official` fallback. The degraded relays (chatgpt-code / openclawroot) are commented out.
- Vertex generations record `$0` in the OpenAI cost ledger (billed to the Google account, not OpenAI).
- `openai-image-generator` SKILL.md + `setup_wizard` provider catalog updated to reflect the new primary.

## [3.16.0] - 2026-06-16 (evidence-based, register-aware title engine — SERP + AI-citation decoupled)

Deep-research (run wf_adbc50a2-331; 23 sources, 25 claims adversarially verified, 19 confirmed /
6 killed) showed the title hard-gate was built on **2024 folklore** and applied **one B2B formula
to every register**. Real shipped project-charlie titles ran 66–127 chars (the validator's own 65 cap
was unenforced) and were jargon-dense. Two facts reframed the engine: (1) Google **rewrites ~76% of
title tags** (Q1-2025; >65 chars → ~99.9%) — so we were over-tuning a field users often never see;
(2) titles **barely matter for AI citation** (GEO paper, KDD 2024 — content-enrichment drives it).
Full plan: `docs/title-optimization-plan-2026-06-16.md`. Evidence memo:
`reference_title_optimization_evidence_2026_06_16.md`. **Research + plan + implementation only — no
title rewrites were published to any live site.**

### Changed
- **`scripts/validate/title_validator.py` fully rewritten.** Validates the short `seo_title`
  (target 51–60 chars; hard-fail >65 / <30). **Power word and digit are NO LONGER mandatory**
  (the "+36% digit / +13.8% power-word CTR" claims did not survive verification; Nature 2023 RCTs
  show positive power words can slightly *lower* CTR). Kept: primary keyword present, sentence
  case, ≤2-power-word anti-spam ceiling.
- **Register-aware.** New `REGISTER_PROFILES` (`default`, `b2b_technical`, `b2b_procurement`,
  `dtc_celebration`, `dtc_grief`, `ecommerce`) gate power-word / digit policy + banned terms.
  `dtc_grief` HARD-BANS power words, commercial superlatives (best/top/proven/ranked/#1), urgency
  — fixing the tonal hazard before project-hotel's grief-content launch. `infer_register()` maps
  `business-context.json :: voice_default`.
- **Reference docs** (`power-words.md`, `micro-copy-tactics.md`, `angle-catalog.md`) reframed:
  power words optional/register-gated, refuted 2024 data points removed, F1–F6 specificity-first
  title formulas replace the power-word formulas, retired-pattern list added, per-angle register-fit.

### Added
- **Three-field title model.** `seo_title` (short, indexed `<title>`/`rank_math_title`/`og:title`)
  vs `h1`/`title` (long human display title). NEW hard gate: every number in `seo_title` must also
  be in the `h1` (Google preserves a number 97.3% only when in both) + H1↔keyword alignment +
  parenthesized/bracketed-year rewrite-risk flag. Wired into `topic-angle-selector` + `meta-builder`
  (CLI now takes `--register` + `--h1`). `meta.schema.json` gains a `register` enum.
- `tests/test_title_validator_2026_06_16.py` (21 tests). mypy --strict clean; full suite 188 passed.

### Notes
- AEO/AI-citation is explicitly DECOUPLED from the title gate — it is owned by the References +
  inline-APA / content-enrichment rules, not headline wordcraft.
- Register adaptation + anti-homogenization rest on principled inference (no register-level RCT
  exists); flagged as such in the plan.

## [3.15.1] - 2026-06-15 (photo 4K floor + 2× crisp charts + grouped_vbar/precision/linear-scale)

Audit finding: although v3.14.8 set 4K image defaults, **most articles were still
shipping 1024/1536 photos**. Empirical check of 6-14 runs found only ~2/6 at 4K. Root
cause: the orchestrator's `image-prompt-designer` dispatch_prompt still hardcoded
`size must be '1024x1024'/'1024x1536'/'1536x1024'` (never updated for the 4K change),
and the pipeline's 4K default only applies when `size` is **absent** — an explicit
legacy size always won and silently downgraded the photo. Charts were a second gap:
rendered at a fixed 1024×1024 regardless, which the 6-14 visual-QA itself blamed for
label collisions ("9 bars in a 1024px canvas ≈ 90px/slot → overlap").

### Changed
- **Photos now ship at 4K reliably.** `orchestrator.py` designer dispatch_prompt no
  longer forces legacy sizes — it instructs `aspect_ratio` (mapped to 4K tiers) for
  photo slots. NEW `_enforce_4k_floor()` in `openai_image_pipeline.py` snaps any
  sub-4K photo size up to its nearest 4K tier, so an explicit 1024/1536 `size` can no
  longer downgrade the image. Charts are unaffected (filtered out before the floor).
- **Charts render at 2048×2048 (2× supersample).** `data_chart_png.py` rewritten
  around a `SCALE`/`px()` system (logical 1024 layout drawn at 2×) so text is
  retina-crisp and many-bar labels stop colliding. All geometry/fonts scale from one
  `SCALE` constant.

### Added
- **`grouped_vbar` chart type** — two+ series per category with a legend (e.g. density
  AND moisture per material), so two metrics no longer get crammed into one vbar.
- **Auto axis-tick precision** (`_fmt_num`) — sub-2 spans show decimals (fixes the
  "0,1,1,1,2" degraded ticks) while wide integer charts stay clean.
- **`x_scale:"linear"` honored** in `rangebar` — force-disables the auto-log that was
  compressing wide ranges (e.g. DLI 1–30) against an explicit linear request.
- `tests/test_image_4k_and_chart_upgrade_2026_06_15.py` (12 tests). Docs updated:
  `image-prompt-designer.md`, `image-visual-qa.md`, orchestrator dispatch prompt.

### Notes
- The chart-review mechanism itself was verified healthy: 18/18 recent articles had a
  valid `image-qa-report.json` (provenance + pre-publish-gate hard-enforced). This
  release removes the resolution root cause behind its recurring legibility warnings.

## [3.15.0] - 2026-06-10 (image visual-QA subagent + targeted regeneration loop)

The pipeline finally LOOKS at the images it generates. New mandatory publish-phase
stage `image-visual-qa` between image-pipeline-join and pre-publish-gate.

- NEW `agents/image-visual-qa.md` (Opus vision): reads every generated PNG, scores
  13 defect classes (composition collapse / anatomy deformity / garbled text /
  empty label chips / third-party brands / content mismatch / brand-color drift /
  low contrast / AI-look / style inconsistency + chart C1-C3 legibility), max 2
  regeneration rounds, `accept_with_warning` never blocks publish (draft-first
  preview is the human backstop).
- NEW `scripts/openai/image_regen_slots.py`: targeted photo-slot regeneration
  reusing `generate_images()` (cost-ledger, watermark, dimension hard-gate,
  upsert merge preserved). `-r{round}` filename suffix prevents WP media dedup
  to the round-0 upload. Chart defects re-render free via render_data_charts.
- NEW mandatory `image_qa` gate in pre_publish_gate.py: report existence +
  `_generated_by: image-visual-qa-subagent` provenance + internal-consistency
  check (a "pass" verdict carrying an unresolved error defect FAILS — fabrication
  smell).
- NEW `schemas/image-qa-report.schema.json` report contract.
- Orchestrator: stage registered + SUBAGENT_ENFORCED_STAGES; pipeline_checklist
  updated; skills/seo-blog/SKILL.md documents the Bash invocations (Rule 6).
- Designer hardening from gpt-image-2 community corpus: validated negative
  baseline (AI-look/plastic-skin/oversmoothed/cheap-ecommerce/overexposed/
  distorted-grid), field-separated text-overlay specs, quality-words-last
  prompt ordering.
- Applies to ALL projects unconditionally.

## [3.14.8] - 2026-06-10 (4K image default + WebP q85 + drop the always-on <200KB cap)

Follow-up to v3.14.7 after measured 3-way compression comparisons at 2K and 4K: the
chatgpt-code relay bills 2K and 4K at the same credit price, and 4K q85 WebP beats 2K q90
on BOTH size-efficiency and per-pixel fidelity (mean-abs-diff 1.01/255 @ 268KB vs
1.27/255 @ 193KB) — resolution dilutes quantization error.

### Changed
- **Default image output is now 4K high** — `size_cover: 3840x2160`,
  `size_section: 2880x2880`; `ar_to_size` upgraded to 4K tiers; `DEFAULT_SIZE`
  2048x2048→2880x2880. NOTE: gpt-image-2 caps total pixels at 8,294,400 (= 3840x2160
  exactly), so the max square is **2880x2880, not 3840x3840** — 16:9 and 1:1 tiers sit
  exactly at the cap.
- **WebP default quality 90→85** (`webp_converter.py`, `srcset_generator.py`,
  image-post-processor SKILL.md) — at 4K, q85 lands ~268KB with better per-pixel
  fidelity than 2K q90.
- **Removed the always-on "compress to <200KB" post-processing step** — re-compressing
  2K/4K sources to a hard KB cap pushed them back to ~q75 and undid the quality upgrade.
  `--target-kb` survives as an explicit opt-in flag on `webp_converter.py`.
- srcset derivative widths stay 480/1024/2048; the full-size 4K original is the largest
  srcset entry.
- Cost caps raised again (per-article 8→15, daily 30→60, weekly 90→180, monthly
  250→600): every 4K tier is ~8.29M px → ledger over-estimates ~$1.67/image
  (~$6.7/article) at official rates; real relay billing is credit-based and far lower.
- 4K sizes propagated to image-slot-allocator / image-prompt-designer /
  openai-image-generator / image-post-processor SKILL.md docs (Rule 6).

### Added
- **Same-provider retry on transient failures** (`generate_realtime_one`): Cloudflare
  524/5xx/429/timeouts get ONE retry on the same provider (60s backoff) before falling
  over. 4K generations regularly brush relay 120s proxy windows — without this, a
  retryable blip on the cheap primary leaked the slot to the paid official fallback.
  Dimension-mismatch errors deliberately don't retry (degradation is deterministic).

### Validated
- E2E smoke (smoke4k): cover exact 3840x2160 via chatgpt-code (54s); square slot
  exercised the FULL defense chain in production — chatgpt-code 524 → openclawroot
  served 1254x1254 and was **caught by the v3.14.7 dimension hard-gate** (first
  real-world firing) → openai-official delivered exact 2880x2880. 2/2 slots correct.

## [3.14.7] - 2026-06-10 (2K image default: chatgpt-code primary provider + dimension hard-gate + WebP q90)

Image-quality migration validated by live capability probes (artifacts in
`memory/workspace/_diag_2k4k/`): the chatgpt-code newapi gateway is the only tested relay that
returns pixel-exact output at 1024/2048x1152/3840x2160 (openclawroot silently degrades ANY
custom size to 1672x941 with HTTP 200). E2E smoke passed: 2/2 slots, exact 2048x1152 cover +
2048x2048 section, zero fallback.

### Changed
- **Default image output is now 2K high** — config `size_cover: 2048x1152`, `size_section:
  2048x2048`; pipeline `ar_to_size` upgraded to 2K tiers (4:3→2048x1536, 3:2→2048x1360, etc.,
  all 16-multiples within gpt-image-2 constraints); `DEFAULT_SIZE` 1024x1024→2048x2048.
- **Provider chain reordered** — `chatgpt-code` (newapi, sync b64_json) is primary;
  `openclawroot` and `openai-official` are fallbacks. New `chatgpt-code` entry in
  `credential_hub._PROVIDERS`.
- **WebP default quality 80→90** (`webp_converter.py`, `srcset_generator.py`,
  image-post-processor SKILL.md): at 2K, q90 ≈ 193KB (inside the 200KB budget) with
  mean-abs pixel deviation 1.27/255 vs source; q80's savings no longer justify the texture loss.
- **srcset width tiers 480/768·1024/1536 → 480/1024/2048** for the 2K source tier.
- Cost caps raised (per-article 2→8, daily 10→30, weekly 30→90, monthly 50→250): ledger
  deliberately over-estimates relay images at official rates and 2K carries 2-4x the 1K estimate.
- 2K sizes propagated to image-slot-allocator / image-prompt-designer / openai-image-generator
  / image-post-processor SKILL.md docs (Rule 6: docs must match executors).

### Added
- **`_verify_saved_dimensions()` hard gate** in `openai_image_pipeline.py` (realtime AND batch
  paths): saved pixels must equal the requested size, else the slot fails over to the next
  provider. Kills the silent-degradation class (relay returns HTTP 200 with wrong-size image).
- **Pixel-scaling price fallback** in `cost_ledger.estimate()` for unknown gpt-image sizes
  (scales the 1024x1024 baseline by pixel count) — eliminates the `UnknownModelError`-after-
  generation class entirely.

### Fixed
- **`webp_converter.convert()` dropped `lossless` for RGB images** — the flag only reached the
  RGBA branch, so `--lossless` on a plain RGB PNG silently produced lossy q80. Both branches now
  honor it (verified pixel-identical on real 2K and 4K sources).
- **Cost-estimate double-billing** — `cost_ledger.estimate()` was called inside the provider
  try-block AFTER a successful generation, so an estimator gap failed the slot and re-billed it
  through the fallback chain. Estimates are now isolated try/except (realtime + batch) and an
  estimator failure records $0 instead of failing the slot.

## [3.14.6] - 2026-06-09 (batch RCA: scoped TOC fill + claim-prefix normalization + HTML-signature idempotency)

Root-cause fixes from the 2026-06-09 project-juliet 3-article batch (`3d filament deals` /
`best pla filament brands` / `different filament types`). The batch itself validated the v3.14
runner end-to-end: all 3 articles ran 30/30 stages in order with zero skips, full artifact +
provenance trail, and 22/22 post-publish verification each — and the enforcement layer worked as
designed (the one silent defect that slipped through a subagent was caught by `pre_publish_gate`,
not by luck). These patches close the three defects so the next batch runs them right the first time.

### Fixed
- **`scripts/build/assemble.py`** — the `_(auto-generated)_` placeholder replacement was a GLOBAL
  `.replace()`, so the References section's placeholder (rebuilt later by
  `finalize_refs_signature`) was filled with a **duplicate Table of Contents** in all three
  articles. Fact-checkers then "helpfully" hand-patched the broken-looking intermediate state,
  causing knock-on drift. Extracted `_fill_toc_placeholder()`: TOC fill is now scoped to the
  Table of Contents section; leftover placeholders are blanked for finalize to rebuild.
- **`scripts/wordpress/wp_publisher.py::_build_in_text_replacement_map`** — fact-checker
  subagents sometimes emit `claim:cN_x` instead of the bare `cN_x` contract in
  `claim_markers_resolved[]`. Draft-side IDs are always bare, so the prefixed form produced a
  **silent zero-replacement citation-inject** (47 markers leaked in plabrands_0609; caught by
  `pre_publish_gate`'s citation_inject gate). The map builder (single source for BOTH
  `citation_inject` and the publisher L1 defense) now normalizes the `claim:` prefix away.
- **`scripts/build/finalize_refs_signature.py`** — signature idempotency only recognized the
  markdown-italic form, so a fact-checker-authored raw-HTML
  `<p class="article-signature">…</p>` variant survived and produced a **duplicate signature**
  (and would have entity-escaped into visible text under markdown-it `html=False` — render_lint
  L1 class). Raw-HTML signature variants are now stripped before the single canonical markdown
  signature is placed.

### Changed
- **`scripts/pipeline/orchestrator.py`** — the `fact-check-and-citation` dispatch_prompt now
  states the artifact contract explicitly: `claim_markers_resolved[]` entries are BARE slugs
  without the `claim:` prefix, and the fact-checker must NOT hand-build the References section
  or any signature (the finalize stage owns both).
- **`tests/test_v314_runner_and_finalize.py`** — 3 new regression tests pin all three fixes
  (scoped TOC fill / prefix normalization / HTML-signature strip). Suite: 145 passed, 4 xfailed.

## [3.14.5] - 2026-06-07 (parallel-isolation follow-up: lock the last shared write + image-brand init step + chart log-scale)

Follow-up patch to the v3.14.4 parallel multi-session work, from a full audit of the v3.14.1→v3.14.4
updates. Confirms v3.14.4 is structurally sound (env-first project resolution wired in all read sites;
`file_lock` on the two genuinely-shared mutable files; 142 passed / 4 xfailed; cache fully synced).
Closes the **one remaining** Rule-7 gap the audit found, plus lands two complete-but-uncommitted
skill-level improvements.

### Fixed
- **`scripts/publish/change_log.py`** — the cross-project audit log `memory/change-log-global.json`
  was written with an **unlocked read-modify-write**. It is a single file shared by every parallel
  session (all projects publish into it), so two concurrent publishes could clobber one audit entry.
  Now wrapped in `file_lock.locked(global_log)` (same primitive as cost-ledger / tavily counter).
  The per-project log is scoped by `site_slug` and correctly needs no lock. This was the last
  unlocked shared user/plugin-level mutable write — Rule 7 is now fully satisfied.

### Changed
- **`subskills/init/website-project-init/SKILL.md`** — adds Step 11.7 (image brand identity: visual
  style + cover text overlay + brand watermark + in-scene packaging label), writing the authoritative
  `projects/{slug}/brand-guideline.yaml`. Closes the 2026-06-06 project-kilo gap where covers shipped
  unbranded with no watermark because the project had no brand-guideline.yaml.
- **`scripts/build/data_chart_png.py`** — rangebar charts auto-switch to a log x-scale for wide
  dynamic ranges (e.g. `$15..$700`) so cheap rows stay visible instead of collapsing to slivers;
  footer source text now wraps/ellipsizes to ≤2 lines instead of overflowing.

## [3.14.4] - 2026-06-06 (parallel multi-session isolation: env-pinned project + cross-process locks)

Enables running **N separate Claude Code sessions in parallel, one project each** (e.g.
`project-charlie` + `project-juliet` + `project-kilo` simultaneously). Closes a whole **class** of
bug — *user-level global mutable state with no concurrency discipline* — that was invisible
while the plugin was only ever run one session at a time. Three concrete instances fixed at
root, plus two reusable primitives so the class cannot recur. Full suite: 142 passed, 4 xfailed
(incl. 14 new concurrency/isolation tests). New modules `mypy --strict` clean.

**Root causes (see `docs/superpowers/specs/2026-06-06-parallel-sessions-isolation-design.md`):**
1. `~/.xuanran-seo/active-project` was a single global pointer with no per-session scoping →
   parallel sessions overwrite each other → wrong `project_slug` burned into `state.json` at
   task-creation → article published to the **wrong WordPress site**. (HIGH)
2. `cost-ledger.jsonl` appends were unlocked → concurrent writes interleave/corrupt the JSONL
   and skew the shared daily budget. (MEDIUM)
3. `.tavily-rr-counter` round-robin was an unlocked read-modify-write → parallel sessions pick
   the same key, defeating the 10-key pool and burning quota. (MEDIUM)

### Added
- **`scripts/_core/file_lock.py`** — cross-platform (`msvcrt`/`fcntl`) advisory file lock as a
  `with file_lock.locked(path):` context manager. Locks a sidecar `{path}.lock`; OS auto-releases
  on process death (no stale-lock deadlock on Ctrl-C); non-blocking + polled with a `LockTimeout`.
  Zero new dependencies.
- **`scripts/_core/active_project.py`** — single source of truth for the active project slug.
  `get_active_project()` resolves **`XS_ACTIVE_PROJECT` env var first, then the shared file**.
  `set_active_project()` writes the file and warns when an env override is active.
- **`bin/launch-session.ps1` / `bin/launch-session.sh`** — launch a session pinned to one project
  via `XS_ACTIVE_PROJECT=<slug>`. Run one terminal per project for safe parallel work.
- Tests: `test_file_lock.py`, `test_active_project.py`, `test_cost_ledger_concurrency.py`,
  `test_tavily_counter_concurrency.py`.

### Changed
- **`cost_ledger.py`** — `log()` append and `--reset-today` rewrite now hold `file_lock.locked(LEDGER_FILE)`.
- **`credential_hub.py`** — the Tavily round-robin counter RMW now holds `file_lock.locked(counter_file)`.
- **`hooks/session_start_load_project.py`** — resolves the active project env-first via
  `active_project.get_active_project()`; status line shows `📌 pinned via XS_ACTIVE_PROJECT`.
- **`bin/preamble.md`** — Step 2 no longer overwrites `XS_ACTIVE_PROJECT` from the file; env wins.
- **`scripts/_core/local_intent_runner.py`** — empty `--project-slug` falls back to env-first
  resolution (defense-in-depth at the one LLM-invoked, file-derived call site).
- **Docs**: `skills/seo-blog/SKILL.md` (env-first resolution in startup + new "Parallel multi-session"
  section), `subskills/init/project-switch/SKILL.md` + `project-show/SKILL.md` (env-first + warning),
  root `CLAUDE.md` (new HARD RULE 7: parallel multi-session isolation).

### Verified
- `XS_ACTIVE_PROJECT` set ⇒ `get_active_project()` returns it regardless of the shared file
  (cross-session contamination structurally impossible); env unset ⇒ identical pre-change behavior.
- Lock serializes concurrent RMW with zero lost updates; Tavily rotation stays perfectly balanced
  under 100 concurrent calls across 8 threads; concurrent `log()` produces no torn/missing lines.

## [3.14.3] - 2026-06-06 (pluggable image provider: openclawroot relay primary + official OpenAI fallback)

Image generation became provider-pluggable. Previously the realtime path was hardcoded to
official OpenAI with a hardcoded `model="gpt-image-2"` and an un-overridable `base_url`
(a CLAUDE.md "don't hardcode model IDs" violation). Now a configurable PRIMARY provider
(a third-party OpenAI-compatible relay, openclawroot, validated 2026-06-06: drop-in via the
`openai` SDK, 4 high-quality images in 67.5s at concurrency 4) with an automatic per-slot
FALLBACK to official OpenAI. Realtime is forced because relays have no Batch API. Cost ledger
deliberately keeps the official per-image table (over-estimates the relay's token billing —
conservative cost guard). Pinned by `tests/test_image_provider_fallback_2026_06_06.py` (11 tests).
Full suite: 128 passed, 4 xfailed.

### Added
- **`scripts/_core/image_provider.py`** — `resolve_providers()` returns an ordered chain
  (primary first, fallbacks after) from `config.yaml :: image.providers`; each entry resolves
  its credential via `credential_hub`, missing-credential entries are skipped (logged to stderr,
  never silently). `default_mode()` reads `image.default_mode` then the previously-unread legacy
  `image.pipeline_mode` (fixing a latent wiring gap), defaulting to `realtime`. Backward-compatible:
  no `image.providers` block ⇒ single official-OpenAI provider (pre-change behavior).
- **`credential_hub`** registers the `openclawroot` provider (`OPENCLAWROOT_API_KEY` / `openclawroot.key`).

### Changed
- **`openai_image_pipeline.py`** — `generate_realtime_one` now loops the provider chain with
  automatic fallback; `generate_realtime_all` builds the client list from `resolve_providers()`;
  model id is read per-provider (no longer hardcoded); default mode `auto` → `realtime`; CLI
  `--mode` default now reads config. Batch path (`openai_batch_image_api.py`) is unchanged and
  documented as official-OpenAI-only (relays have no Batch API).
- **Docs synced to the new model**: `skills/seo-blog/SKILL.md` (Fork B `--mode realtime`, fixing a
  broken `{project.image_pipeline_policy.mode}` placeholder that referenced a non-existent config key),
  `skills/phase-publish/SKILL.md`, `subskills/image/{openai-image-generator,batch-job-poller,image-post-processor}/SKILL.md`,
  plus docstrings in `cost_ledger.py`, `cost_estimator.py`, `setup_wizard.py`, `scripts/openai/__init__.py`,
  `openai_batch_image_api.py`.

### Verified
- Canonical path traced end-to-end: `run_pipeline.py` → `orchestrator.py` image-pipeline-fork
  (`--mode realtime`) → `generate_realtime_all` → `resolve_providers()` → relay primary + official
  fallback. No bypass paths (all image gen routes through `openai_image_pipeline.py`).

## [3.14.2] - 2026-06-04 (batch-run RCA #2: 6 robustness bugs found running the seed-starting / t5-fixtures / ferns batch)

Found while running a second 3-article project-charlie batch on the v3.14 runner. All fixes are
**skill/plugin-level** (`scripts/`), so every project benefits. Pinned by
`tests/test_batch_fixes_2026_06_04b.py` (15 tests). Full suite: 117 passed, 4 xfailed.

### Fixed
- **Chart renderer crashed on hex-string colors.** The `image-prompt-designer` emits `chart_spec`
  bar/row `color` as hex strings (`"#0F3D2E"`), but `data_chart_png.render_vbar/render_rangebar` did
  `tuple(b["color"])` → `TypeError: color must be int, or tuple` → `chart-render` exit 1, leaving the
  data slot un-rendered. Both call sites now use the existing `_hex_to_rgb()` helper (accepts hex OR rgb).
- **`pre_publish_gate.check_humanizer` crashed on the humanizer's dict score.** The humanizer writes
  `ai_slop_score` as a structured `{before, after, threshold}` dict; the gate did `dict >= 20` →
  `TypeError` → the WHOLE gate produced no result file → runner reported `GATE_FAILED` with an empty
  reason. The gate now unwraps `.get("after")` when the score is a dict.
- **Stale `citation-inject-result.json` failed the gate even when the draft was clean.** When a
  downstream stage (e.g. the geo-auditor) resolves leaked `[claim:cN_*]` markers in the draft without
  refreshing the result file, the recorded `markers_after>0` hard-failed `check_citation_inject`. The
  gate is now AUTHORITATIVE ON THE LIVE DRAFT — it re-scans `draft.md` and only fails if markers truly
  remain.
- **`wordpress-publisher` recorded TWICE in `stage_history`.** `wp_publisher.py` self-records via
  `file_bus.record_stage_start/complete` AND the runner's `verify_stage` records the same stage →
  duplicate audit entry (cosmetic, but it pollutes post-hoc audits). `record_stage_start` now reuses an
  already-open `in_progress` entry instead of appending a second. (Verified: the published drafts had
  exactly one post per slug — never a double-publish.)
- **Non-ASCII heading anchors desynced the TOC (render_lint L10).** A `µ` in a heading survived as the
  literal char in the rendered `<h2 id="…µ…">` but percent-encoded to `%C2%B5` inside the TOC `<a href>`.
  Both `markdown_to_html.slugify` and `anchor_link_builder._slug` now ASCII-fold (µ→u, ²→2, …) and drop
  remaining non-ASCII, so the heading id and TOC href are always identical ASCII.
- **`finalize_refs_signature` left a misplaced signature in place (render_lint L9).** It only
  *added* a signature when absent; a signature a writer slipped into the Conclusion (before References)
  stayed misplaced. It now strips any existing signature and re-appends a single one AFTER References
  (idempotent), guaranteeing signature-last ordering.
- **Tavily research key-rotation capped at 3 keys** despite a 10-key pool, so when most keys were `432`
  (quota) on the expensive `/research` endpoint the pro deep-research gave up before reaching the one
  working key (failed on 2 of 3 articles, forcing the MCP fallback path). `with_retry()` now rotates
  through the ENTIRE pool by default with bounded backoff; non-transient errors still fail fast. Pinned
  by `tests/test_tavily_retry_pool_rotation.py`.

### Changed
- `references/style/markdown-authoring-conventions.md` validation table now explicitly documents that
  L1 catches raw `<table>`/`<hr>` and adds the L5/L6/L9/L10 rows, so writers know the full ruleset.

## [3.14.1] - 2026-06-03 (batch-run RCA fixes: 4 pipeline bugs + lossless-WebP default image uploads)

Found while running a 3-article project-charlie batch on the v3.14 runner. All fixes are **skill/plugin-level**
(in `scripts/`), so every project benefits. Pinned by `tests/test_pipeline_fixes_2026_06_03.py` (6 tests).

### Fixed
- **`assemble.py` rejected `--task-id`** (the runner's command form), erroring "unrecognized arguments"
  and failing the assembly stage for every article. Now accepts both the positional `task_id` and the
  `--task-id` flag its sibling BASH stages use. (Committed earlier as `e0c4129`.)
- **`category-selector` was silently skipped** → the "every article lands in the single default category
  (144)" bug. Root cause: the orchestrator's `_stage_complete()` treats a stage as done when its
  `expected_outputs` exist, but this stage mutates `meta.json` IN PLACE (created by meta-builder one stage
  earlier), so it false-positived. Fix: `category_selector.py` now writes a distinct evidence artifact
  `category-selection-result.json`, and the orchestrator's `category-selector` Stage declares it via
  `evidence_artifact`. (Confirmed: categories now multi-valued, e.g. 144/146/148/136.)
- **`citation_inject` leaked `[claim:cN_M]` markers** to `render_lint` L5 when a citation used a non-bare
  APA year. `_extract_first_author_year` (wp_publisher.py) now parses `(YYYY)`, `(YYYY, Month)`,
  `(YYYY, Month Day)`, `(YYYYa)`, and `(n.d.)`; unparseable forms still return `None` (caught loudly by L5,
  never fabricated).

### Changed
- **Image uploads default to LOSSLESS WebP at full resolution (100% quality, no downscale).**
  `wp_media.upload()` now re-encodes every image to WebP via `_normalize_image_for_upload()` with
  `lossless=True` and no resizing; EXIF orientation is baked in first (safe for phone photos in other
  projects). For the project's gpt-image PNG sources this is a pixel-identical container swap that is
  ~36% smaller than the PNG — which also cures the >2.5MB `WinError 10054` upload connection reset
  *without* sacrificing any quality. WordPress 5.8+ acceptance verified live. Override with env
  `XS_UPLOAD_IMAGE_FORMAT=original|png|jpeg` or per-image `images.json:"upload_format"`.

## [3.14.0] - 2026-06-03 (root-cure: deterministic pipeline runner + 5 source-fixes for recurring manual-patching)

### Why (root cause from the 2026-06-03 batch RCA)

A deep audit of a 3-article project-charlie batch found that, although v3.7/v3.12 enforcement made
silently-skipped mandatory stages *detectable* at the gates, the pipeline was still **LLM-driven**:
the orchestrator (`orchestrator.py`) is a PASSIVE state machine, and the operator had to hand-drive
all ~30 stages — `--action next` → execute → `--action verify` — between EVERY stage for EVERY
article. That manual ritual is exactly where steps got skipped or driven out of order (2026-05-26
"23/35 skipped", 2026-06-02 "geo skipped", 2026-06-03 "stage records missed + heavy by-hand
driving"). Separately, five known-recurring content defects had no source-level fix, so every run
required manual patching (a Rule-6 class problem — documented behaviour with no executable
implementation).

### Prong A — execution is now deterministic (no more "missed steps")

- **NEW `scripts/pipeline/run_pipeline.py`** — a real driver that runs the loop in CODE. It
  runs/launches/checks every BASH/BACKGROUND/CHECK stage itself and records it, and STOPS only to
  hand the caller the handful of LLM stages that genuinely need a subagent (returning a
  machine-readable dispatch spec). The caller dispatches that one subagent, then re-invokes with
  `--completed-llm <stage>`; the driver verifies + advances through the next BASH stages. Operator
  surface drops from "orchestrate 30 stages × N articles" to "service the LLM stages I'm handed."
- **`skills/seo-blog/SKILL.md`** — "The Loop" and the batch pattern now drive via `run_pipeline`
  instead of hand-calling the orchestrator between stages (legacy hand-loop kept as fallback).

### Prong B — 5 recurring content defects fixed at the source

- **JSON tool-tag self-heal** — `file_bus.tolerant_json_load` strips BOM / trailing subagent
  tool-call wrappers (`</content></invoke>`) and rewrites the file clean. Wired into the
  orchestrator artifact validator + `pre_publish_gate` so a leak self-heals instead of failing a
  gate. (Broke A1 citations.json / fact-check.json in the batch.)
- **NEW `finalize-references-signature` stage** (`scripts/build/finalize_refs_signature.py`) —
  rebuilds the draft's References block from the VERIFIED `citations.json` (assemble builds it
  BEFORE fact-check, so it can carry hallucinated authors the fact-checker only fixed in
  citations.json) AND auto-generates the article signature when missing (writers are barred from
  writing it; the publisher only tags an existing one). Codifies the manual finalizer.
- **assemble normalizer** (`assemble._normalize_markdown`) — strips writer scaffold tokens
  ([ORIGINAL DATA] etc., render_lint L6) and unglues heading/body glued onto one line (render_lint
  L2), deterministically at assembly. Implements the strip the render_lint docstring always
  promised but nobody had implemented.
- **CITE scorer measurement fix** (`cite_scorer.py`) — credits schema @types emitted in the
  `<head>` by the SEO plugin (`business-context.wordpress.seo_plugin_schema_provided`) instead of
  failing ~9/10 Identity items for Org/Person schema that is intentionally absent from the body;
  and accepts the canonical `citations[]` key (C07/C09 were reading only `refs`). CITE rose from a
  misleading ~67-70 to its true ~85+ on real articles, removing spurious manual quality overrides.
- **Quality-gate de-double-jeopardy** (`pre_publish_gate.check_quality_gates`) — SHIP_WITH_NOTES is
  now pass-with-warning, not a hard block. It only ever fires when CORE-EEAT + CITE passed and just
  the heuristic ai-slop is borderline (~20) — which `check_humanizer` and the independent reviewer
  already adjudicate. Hard CITE/EEAT vetoes and FIX_REQUIRED/BLOCKED still block.

### Prong C — regression tests (so it can't silently reopen)

- **NEW `tests/test_v314_runner_and_finalize.py`** — 18 tests pinning all of the above (JSON
  self-heal, normalizer L2/L6, finalize refs+signature idempotency, CITE head-schema + citations[]
  key, SHIP_WITH_NOTES-is-warn, and the runner's stop-at-LLM / record-and-advance behaviour). Full
  suite: 80 passed, 4 xfailed.

## [3.13.1] - 2026-06-03 (post-review fixes to the v3.13.0 chart wiring — found by adversarial verification)

An independent adversarial review of 3.13.0 surfaced real defects, all now fixed +
regression-tested (62 tests pass):

- **Project-agnostic charts (HIGH):** `data_chart_png.py` defaults were project-charlie
  green + a `project-charlie.example.com` footer. A project without brand-config (e.g. project-echo)
  would get a competitor's brand on its charts. Defaults are now NEUTRAL slate with
  NO footer; each project's real palette + footer is applied via `set_brand()` from
  its own `brand-config.json` + `business-context.json::site_url`. Skill-level code
  no longer bleeds any one project's brand onto another.
- **Negative-value charts (HIGH):** `render_vbar` crashed on negative values, but the
  designer is explicitly told to put signed `%`-change data in vbar. Rewrote it with a
  zero baseline (bars extend up for positive, down for negative).
- **Missing-image gate (HIGH):** a chart that failed to render left its slot absent
  from images.json with nothing blocking publish → the `[IMAGE-SLOT-x]` placeholder
  would leak. `pre_publish_gate.check_images` now FAILS if any declared image-prompts
  slot has no entry in images.json (catches failed charts AND failed photos).
- **Light-brand contrast (MED):** table header / range-bar in-bar text was hardcoded
  white → invisible on a light brand `primary`. Now luminance-adaptive (`_ink_on`).
- **Renderer crash-safety (MED):** `render_rangebar` guards missing/zero `x_max`;
  both renderers guard empty `bars`/`rows`.
- **Merge safety (LOW):** images.json merges skip entries without a `slot_id`
  (no more `None`-key collapse).

## [3.13.0] - 2026-06-03 (pipeline-hardening pass — data charts, TOC anchors, citation integrity, maxTurns, richness floor)

### Why (root causes from the 3-article project-charlie batch)
Six failure classes, all tracing to one theme: **quality was enforced terminally (the
pre-publish gate checks artifacts exist) but not procedurally**, and three real capabilities
were built yet never wired (Rule-6 dead code).

1. **Dull textless charts** — `data_chart_png.py` + `chart_svg_builder.py`
   existed but had ZERO call sites; every image slot (incl. data charts) went to the AI
   photo model, which garbles/omits axis & value text.
2. **Broken TOC anchors** — `assemble.py` only injected the correct auto-TOC when the
   `_(auto-generated)_` placeholder was present, which it skipped whenever a writer TOC
   section existed; the writer's short outline-anchors shipped verbatim against full-text-slug
   heading ids.
3. **Inline citations stripped** — `citation_inject.py` read only `in_text_replacements[]`
   and, when empty, stripped `[claim:...]` markers with NO replacement, deleting every
   inline citation — even though the publisher already had a 2-source parser.
4. **Dropped sections** — `writer` maxTurns=50 (the documented 6/50-dropout victim).
5. **Folded steps** — serp/competitor auto-completed on a non-empty key with no richness floor.
6. **Misleading capsule coverage** — the lint counted structural H2s (Abstract/TOC/References)
   in the denominator.

### Fixed
- **Chart wiring (Rule-6 cure):** new `scripts/build/render_data_charts.py` renders
  `kind=="chart"` slots as REAL labeled charts (title/axes/units/value-labels, brand colors)
  via `data_chart_png.py` and merges them into `images.json`. New `chart-render` orchestrator
  stage (runs before the photo fork). `openai_image_pipeline` now skips `kind=="chart"` slots
  and MERGES (not overwrites) `images.json`. The cover/featured slot is always a photo.
  `data_chart_png.py` is now brand-config-driven (palette/footer/font) for portability.
  image-prompt-designer + outline-architect emit/`kind`-tag chart slots + a `chart_spec`.
- **`assemble.py`:** always regenerates a writer-supplied TOC from real heading anchors
  (swaps the writer TOC body for the auto-gen placeholder) → no more broken jump links.
- **`render_lint.py` L10:** new hard veto — any in-page `href="#x"` with no matching `id="x"`.
- **`citation_inject.py`:** derives `(Author, Year)` from `claim_markers_resolved[]`+`apa_7`
  (reuses the publisher's canonical parser); NEVER silent-strips — unresolvable markers are
  left in place so render_lint L5 vetoes them (loud + recoverable, not invisible data loss).
- **maxTurns maxed:** writer 50→150, fact-checker 120→200, humanizer 90→150, reviewer 60→120,
  geo-auditor 60→120, linker 60→90, image-curator 40→90, schema-validator 40→60,
  image-prompt-designer 40→60, head-of-research 50→90.
- **Richness floor:** serp-analysis / competitor-analysis require `evidence_min_count=3`
  (a 1-2 item stub no longer satisfies the stage).
- **`citation_capsule_lint.py`:** content-H2-only coverage denominator (excludes
  Abstract/Key Takeaways/TOC/FAQ/Conclusion/References, incl. `{#anchor}`/numeric/`:`-subtitle
  variants) → honest coverage; stops redundant-capsule churn.
- **Tests:** `tests/test_v313_pipeline_hardening.py` (4 regression tests) + richness-floor test.

## [3.12.0] - 2026-06-02 (orchestrator execution-evidence enforcement — pipeline steps can no longer be silently skipped)

### Why (root cause)
A 3-article batch silently skipped the `geo-content-optimizer` stage: it was recorded
"completed" without the geo-auditor subagent ever running. Root cause — the orchestrator's
enforcement was **artifact-gated**, but the optional LLM stages (`geo-content-optimizer`,
`internal-linker`, `citation-capsule-builder`) declared `expected_outputs=[]`, so
`verify_stage` auto-passed them on the honour system:

```python
if not stage.expected_outputs:
    _record_stage(task_id, stage_name, "completed")   # no proof of execution
    return {"passed": True, ...}
```

An LLM orchestrator under context/budget pressure could (and did) call `--action verify` to
mark these stages done without dispatching the subagent. Same failure class as the 2026-05-26
(23/35 stages skipped) and 2026-05-27 (stub quality artifacts) incidents: **a stage with no
verifiable, provenance-stamped output artifact is unenforceable.** Optional + no-artifact =
silently skippable.

### Fix (skill-level — all projects)
- **scripts/pipeline/orchestrator.py — execution-evidence model.** Every work stage now
  declares evidence: a unique provenance-stamped `evidence_artifact` (geo-content-optimizer →
  `geo-audit.json` w/ `_generated_by:"geo-auditor-subagent"`; internal-linker →
  `internal-link-report.json`; citation-capsule-builder → `citation-capsule-result.json`) OR
  `evidence_keys` proving work landed in a shared artifact (serp-analysis → `serp_features`,
  competitor-analysis → `competitors`/`competitor_titles` in research.json).
- **`verify_stage` no longer auto-passes no-output stages.** It requires the evidence and exits
  1 if missing. The only stage still recorded on trust is the BACKGROUND `image-pipeline-fork`
  launch (its real output `images.json` is checked at the JOIN).
- **New `--action skip --stage X --reason "..."`** is the sanctioned alternative to faking
  completion. Records `status:"skipped"` (NOT `"completed"`) with the reason logged in
  `stage_history` + `pipeline-checklist.json`, so the audit trail never conflates "ran" with
  "deliberately dropped". Skipping a **mandatory** stage is refused.
- **`geo-audit.json` added to the provenance map** (`_generated_by` must be the real geo-auditor).
- **scripts/lint/citation_capsule_lint.py:** added `--out` so the capsule stage writes its
  evidence artifact.
- **skills/seo-blog/SKILL.md:** documents the evidence-enforcement contract + the skip command.
- **tests/test_orchestrator_evidence_enforcement.py (NEW):** 9 regression tests pinning every
  guarantee (no-evidence verify fails, provenance enforced, skip records "skipped", mandatory
  stages unskippable, shared-key evidence). The exact bug now breaks a test if it ever reopens.

### Result
The honour-system hole is closed: a stage is either run (evidence on disk) or explicitly
skipped (reason logged) — "quietly recorded complete" is impossible. The 3 batch articles
backfilled to 100% (28/28) under the new model. 53 tests pass.

## [3.11.3] - 2026-05-28 (brand watermark on all images + fixed empty-label inline diagrams)

### Why
(1) Brand watermark needed on every image, not just covers. (2) Some inline diagram images showed empty text boxes / blank callout chips — root cause: the original ad-hoc dispatch literally asked for "blank callout chips (no rendered text)", and AI-rendered text is unreliable anyway.

### Fixes (skill-level — all projects)
- **scripts/openai/image_watermark.py (NEW):** PIL post-process watermark overlay — crisp, correctly-spelled, consistently-placed brand mark stamped onto images (not AI-rendered, so it never garbles). Reads `brand-guideline.yaml :: watermark` (text/position/opacity/color/shadow/apply_to). Portable bold-font fallback (Windows/Linux/macOS) + PIL default last resort. Importable + CLI.
- **scripts/openai/openai_image_pipeline.py:** auto-applies the project watermark after every realtime image save (`_watermark_after_save`, fail-safe — derives project_slug from workspace state.json, never fatal).
- (3.11.2, reinforced) the image-prompt-designer + brand-guideline already steer toward real legible labels instead of empty callout chips.

### Project-level (project-juliet, stays in project folder)
- `brand-guideline.yaml` gained a `watermark` block (Project Juliet, bottom-right, opacity 0.55, apply_to: all).

### Result
Regenerated all 9 inline images photorealistic with REAL legible labels (anatomy callouts, the six family names PLA/PETG/ABS·ASA/Nylon/TPU/PC·PEEK, packaging-format names) — the empty boxes are gone. Every image (covers + inline) now carries a crisp "Project Juliet" watermark. All 3 drafts re-published idempotently (no ghost posts); 22/22 structural checks pass.

## [3.11.2] - 2026-05-28 (brand-guideline.yaml is now authoritative for imagery)

### Why
After dialing in project-juliet's realistic image recipe, the goal is that EVERY future article for that project (and any project) automatically uses its saved image style with no manual prompting. The agent previously read only `visual_style` from `brand-guideline.yaml` and then compiled its own generic prefix — so the tuned art direction, packaging branding, and realism rules could be lost on the next run.

### Fixes (skill-level — all projects)
- **agents/image-prompt-designer.md:** `brand-guideline.yaml` is now AUTHORITATIVE. The agent honors every field — `visual_style`, `art_direction_prefix` (used VERBATIM, no recompile), `featured_image` (cover text overlay), `packaging_branding` (brand labels = project's label_text; competitors forbidden), `realism`, and `negative_prompt_baseline`. Explicit reminder not to mirror a dark website theme into imagery.
- **scripts/pipeline/orchestrator.py:** the image-prompt-designer dispatch now instructs the agent to read `projects/{slug}/brand-guideline.yaml` FIRST and follow it as authoritative.

### Result
A project's image style is set once in its `brand-guideline.yaml` (project-level, stays in the project folder) and is applied consistently on every subsequent article. project-juliet will keep producing bright photorealistic, SIGMA-branded covers with hook text automatically.

## [3.11.1] - 2026-05-28 (realistic imagery + featured-image text overlay)

### Root Cause
The first project-juliet image batch came out as dark, moody 3D-CGI renders with empty/unlabeled callout chips and no text — they looked fake. The image-prompt-designer agent is actually flexible (defaults to photo-realistic), but: (a) project-juliet had no image art-direction file, so generation followed an ad-hoc dispatch that mirrored the DARK WEBSITE THEME into the imagery; (b) a skill-level default negative ("no text overlay") blanket-banned text even on covers; (c) nothing steered away from the empty-label-template anti-pattern.

### Fixes
- **agents/image-prompt-designer.md (SKILL-LEVEL — all projects benefit):** added a "Featured-image text overlay (project-configurable)" section — when a project's brand-guideline sets `featured_image.text_overlay: true`, the COVER prompt renders a short legible hook headline and the "no text overlay" negative is dropped from the cover only (kept on inline section images). Notes that modern gpt-image-class models render short text well (the DALL-E-era no-text caution is obsolete). Added a "Realism over template-art" section: never design a labeled diagram with empty callout chips (use real legible labels or a clean photo); prefer photorealistic photography for product/manufacturing topics (match a dark UI theme in the article CSS, not in the imagery).
- **projects/project-juliet/brand-guideline.yaml (PROJECT-LEVEL — project-juliet only):** new file the agent reads. `visual_style: photo-realistic-editorial`; bright real product/manufacturing photography art-direction; `featured_image.text_overlay: true` with short-hook style; `packaging_branding.label_text: "Project Juliet"` + forbid third-party competitor brand names (the first batch accidentally rendered a competitor logo); negatives against dark CGI, empty labels, sci-fi glow.

### Result
Regenerated the 3 article covers as bright photorealistic product shots with clean SIGMA-branded packaging and short hook headlines ("FILAMENT SPOOL DIMENSIONS", "FILAMENT TYPES EXPLAINED", "BULK FILAMENT · BUYER'S GUIDE"), swapped onto the 3 drafts as featured images. The skill capability is reusable: any project can opt into realistic imagery + cover text via its own brand-guideline.yaml; the per-project style choice stays in the project folder.

## [3.11.0] - 2026-05-28 (3 root causes of batch-run friction: turn-exhaustion, AI-slop false positives, writer fabrication)

### Root Cause
A 3-article project-juliet batch (filament spool dimensions / types of filament / bulk 3d printer filament) completed successfully but required heavy manual orchestrator intervention. Deep audit found the friction was NOT in the orchestrator or batch design (those worked and enforced every stage) — it was three specific tuning/tooling bugs:
1. **Subagent `maxTurns` set too low for the actual task scope.** fact-checker(25)/humanizer(25)/writer(8) routinely needed 30-50+ turns (verifying ~50 claims, rewriting+rescoring 5,000 words). They hit the ceiling mid-task and died before writing their output artifacts, forcing a second "finisher" dispatch for nearly every quality-critical stage (~2× the agent count).
2. **The AI-slop detector was not structure-aware.** Patterns P15 (structured-list), P26 (perfect list), P28 (markdown italics), P14/P42 (bold), P10 (rule-of-three) fire on the MANDATORY structural sections every article requires (Key Takeaways bold leads, Table of Contents list, References ordered list + APA-7 italic titles). These false positives (score = 4 × distinct pattern types) pushed otherwise-clean articles to 21-33, over the <20 gate — forcing manual repair on every article (stripping the required Key Takeaways bold, swapping a citation whose URL contained "comprehensive", de-Oxford-comma'ing lists).
3. **Writer prompts permitted fabrication and silent dropout.** Writers invented sources ("Mordor Intelligence, 2026", "SSSRAY, 2026"), a fake "internal pallet study" with invented percentages, and wrote their own `(Author, Year)` parentheticals; one writer ran a self-correction loop and exhausted its turns before writing the file (section silently dropped).
4. **(bug) P27 question-heading regex spanned newlines** — `[^?]*` matched `\n`, so a `## How to ...` heading with no "?" matched a "?" anywhere later in the doc (e.g. an FAQ question), a false positive.

### Code Fixes
- **agents/*.md (30 agents): `maxTurns` maxed out.** writer 8→50, fact-checker 25→120, humanizer 25→90, reviewer 12→60, researcher 35→150, linker 10→60, image-prompt-designer 8→40, schema-validator 5→40, geo-auditor/head-of-research/image-curator/publisher/seo-auditor/editor-in-chief/entity-extractor and all 15 audit-* agents raised to 40-90. Turn-exhaustion mid-task can no longer occur for any realistic task.
- **scripts/lint/ai_tells_detector.py: structure-aware suppression.** New `_structural_suppression_map()` identifies the mandatory sections (Key Takeaways / Table of Contents / References / Further Reading) by H2 heading and suppresses the "format-driven" pattern set {P10, P14, P15, P26, P28, P42} ONLY within them. Body prose is fully unaffected — a real pattern in a content section still fires. This eliminates the per-article AI-slop repair loop AND lets articles keep their REQUIRED Key Takeaways bold leads instead of stripping them to pass the gate. Verified: a structural test doc dropped from 5 flagged pattern-types (RAW) to 1 (only the genuine body rule-of-three).
- **scripts/lint/ai_tells_detector.py: P27 count threshold + regex fix.** `[^?]` → `[^?\n]` (heading must end with "?" on its own line). Added `_COUNT_THRESHOLDS = {"P27": 3}` so 1-2 question headings (good for SEO/featured snippets) don't trigger the tell; only the AI habit of making 3+ headings questions counts. `lint()` gained an `apply_structural_suppression=True` kwarg (default on; pass False for raw debugging).
- **agents/writer.md: write-first discipline + hard anti-fabrication rule.** New "Write-first discipline" section (draft → save → refine in place; never leave the section unsaved while polishing — prevents silent dropout). New "Never fabricate a source or a statistic" red-line section (never invent a source/study/org/report/number; never write your own `(Name, Year)` parenthetical — use `[claim:cN]` markers only and let the fact-checker attach verified sources). Citation-capsule + claims-marker constraints clarified accordingly.
- **agents/fact-checker.md: output-first + stale-turn-reference fix.** Removed hardcoded "turn 23 of 25" failsafe (stale after maxTurns→120). Reframed to write citations.json + fact-check.json EARLY then refine, and to lean on the researcher's already-link-checked sources in research.json rather than re-fetching everything.

### Impact
The orchestrator/batch architecture was never the problem and is unchanged. These fixes target the three tuning/tooling root causes so the next batch runs without the manual rescue work:
- No subagent dies mid-task → no double-dispatching.
- Clean articles pass the AI-slop gate on the first try, keep their required formatting, and need no manual pattern-chasing.
- Writers cannot reach the page with invented sources/stats, and cannot silently drop a section.
- 19 detector/scorer unit tests still pass; no regressions.

## [3.9.0] - 2026-05-27 (9 pipeline gate + tracking bugs from 3-article batch audit)

### Root Cause
Deep audit of 3-article batch run revealed 9 code-level bugs: orchestrator never wrote state_history (read-only state machine), pre_publish_gate had 4 logic defects (fact-check only blocked on exact "BLOCK_PUBLISH", reviewer ignored verdict field, keyword density field name mismatch, quality gates passed SHIP_WITH_NOTES), writer agent spec contradicted orchestrator on output format (.json vs .md), pipeline_checklist was missing 3 mandatory stages.

### Code Fixes
- **orchestrator.py: State tracking now writes to both state_history AND pipeline-checklist.json** — `next_stage()` records `in_progress`, `verify_stage()` records `completed`. Previously the entire file was read-only; 26/28 stages had zero forensic trail.
- **orchestrator.py: Empty template variable validation** — `_resolve_command()` returns None if `{post_id}` resolves to empty string. Prevents verify-post from silently running with no post ID (root cause of verify-post being skipped for articles 2+3).
- **pre_publish_gate.py: Fact-check gate blocks on FIX_REQUIRED** — Previously only exact string "BLOCK_PUBLISH" failed. Now blocks on FIX_REQUIRED, CORRECTIONS_NEEDED, rejected, FAIL. Also rejects unknown verdict strings (whitelist: CLEAN, PASS, APPROVED, CLEAN_WITH_NOTES).
- **pre_publish_gate.py: Reviewer gate checks verdict field + hardcoded target** — Previously checked only score, ignored verdict="rejected". Now checks verdict first (blocks on rejected/FAIL/FIX_REQUIRED), then score >= 80 (hardcoded, no longer read from untrusted artifact).
- **pre_publish_gate.py: Keyword density field name fix** — Consumer read top-level `primary_density_pct` (doesn't exist); producer wrote `primary.density_pct` (nested). Fixed to read `data.get("primary", {}).get("density_pct", 0)`. Gate was reporting 0% density for every article.
- **pre_publish_gate.py: Quality gates block on SHIP_WITH_NOTES + check all_pass** — Previously only `BLOCKED` failed. Now also fails on `FIX_REQUIRED` and `SHIP_WITH_NOTES`, and checks `all_pass=false` directly. AI-slop scores 31-41 will now actually block publish.
- **agents/writer.md: Output format unified to .md** — Agent spec said .json with JSON envelope; orchestrator dispatch_prompt said .md. Unified to .md. JSON envelope output is now documented as deprecated. Prevents format-conversion failures in articles 2+3 of batch runs.
- **pipeline_checklist.py: 3 stages moved to MANDATORY** — `citation-inject`, `keyword-density-check`, `quality-gates` moved from RECOMMENDED to MANDATORY_STAGES. Pipeline audit now correctly flags them as missing.

### Impact
All 9 bugs were found by deep-auditing a 3-article batch run (growing seeds with grow lights / what color light is best for flowering / what color light is best for seeds). The fixes ensure:
- Full forensic trail for every pipeline stage execution
- Fact-check corrections are enforced before publish (no more FIX_REQUIRED passthrough)
- Independent reviewer rejections actually block publish
- Keyword density is correctly measured and reported
- AI-slop threshold is enforced, not advisory
- Writer agents produce consistent .md output format across batch runs

## [3.8.0] - 2026-05-27 (Batch-pipeline provenance enforcement — 6 systemic fixes)

### Root Cause
LLM under context pressure during batch article runs writes stub JSON files (fact-check.json, humanizer-report.json, review.json) directly instead of dispatching subagents. Real independent reviewers scored 64/62 for articles where stubs claimed 82/81 — proving the independent-subagent property is load-bearing for quality.

### Code Fixes
- **orchestrator.py: Input provenance validation** — `_artifact_valid()` (provenance check via `_generated_by` field) now used for inputs in `_PROVENANCE_REQUIRED`, not just `_artifact_exists()` (file existence). Writing a stub without correct `_generated_by` causes the NEXT stage to report BLOCKED.
- **orchestrator.py: Pre-publish-gate blocks publisher** — wordpress-publisher now requires `pre-publish-gate-result.json` as input dependency. Cannot bypass the gate by running publisher directly.
- **pre_publish_gate.py: Writes result file** — Gate now writes `pre-publish-gate-result.json` to workspace, making it trackable by the orchestrator.
- **orchestrator.py: Subagent enforcement signals** — New `SUBAGENT_ENFORCED_STAGES` set. `next_stage()` returns `subagent_enforced: true` + `enforcement_warning` for fact-check, humanizer, reviewer stages.
- **orchestrator.py: quality.json dependency** — Added `quality.json` to pre-publish-gate required inputs. Skipping `run_quality_gates` now blocks publish.
- **SKILL.md: Batch-mode rewrite** — Root-cause explanation + code-level guarantee descriptions replace prose-only instructions.

### Validation Evidence
| Metric | Stub (LLM-written) | Real Subagent |
|---|---|---|
| Article 2 reviewer | 82 (SHIP) | 64 (REJECTED) |
| Article 3 reviewer | 81 (SHIP) | 62 (REJECTED) |

## [3.7.0] - 2026-05-27 (Deep audit + pipeline hardening + cache sync + version manifest alignment)

### Pipeline Bug Fixes (2026-05-27)
- **Quality gates CLI mismatch** — scorers accept positional args but orchestrator sent `--workspace`; NEW `scripts/validate/run_quality_gates.py` wrapper unifies all 3 scorers (CORE-EEAT + CITE + AI-Slop) with consistent `--workspace` flag
- **5 stdout-only scripts** — `keyword_density.py`, `section_completeness_check.py` and 3 others wrote results to stdout only, never to file-bus; added `--out` flags and auto-write behavior
- **Pre-publish gate `quality.json` check** — `pre_publish_gate.py` now includes `check_quality_gates()` in MANDATORY_GATES; blocks publish when quality.json missing or combined_verdict == BLOCKED
- **Image filename dedup** — 3 articles sharing `cover.png` got same WP media ID; `openai_image_pipeline.py` now prefixes `task_id` to filenames + reads `filename_seed` as fallback
- **Keyword density defaults** — function signature aligned to 0.005/0.010 (was 0.008/0.013), matching SKILL.md target band 0.5-1.0%
- **Orchestrator `image-pipeline-fork`** — now reads from `image-prompts.json` (was stale `image_batch_requests.json`)
- **Orchestrator `image-prompt-designer` dispatch** — removed stale `image_batch_requests.json` from dispatch prompt

### Skill Documentation Fixes (2026-05-27)
- **`skills/seo-blog/SKILL.md`** — 2x `image_batch_requests.json` → `image-prompts.json`; section_completeness invocation fixed to `python -m` form + documented auto file-bus write
- **`skills/phase-build/SKILL.md`** — section_completeness invocation fixed to `python -m` form + file-bus note
- **`skills/phase-optimize/SKILL.md`** — section_completeness invocation fixed to `python -m` form
- **`README.md`** — version badge + tree + changelog highlights updated to v3.7.0; added v3.6.0/v3.7.0 entries
- **`install/claude-code/install.sh` + `install.ps1`** — version comments updated from 3.2.0 to 3.7.0

### Prior Bug Fixes
- **`scripts/_core/cost_ledger.py:396`** — typo `daily_usd` → `daily_total_usd` in fallback error message. Key didn't match `defaults` dict, caused `n/a` in cost-limit warnings instead of the actual default value.
- **`scripts/pipeline/pre_publish_gate.py:78-84`** — table detection used fragile `content.count("\n|")` which miscounted pipe characters in code blocks and blockquotes. Replaced with proper header-separator-only detection using character-set analysis on pipe-starting lines.
- **`scripts/lint/categories_sync_check.py:68-72`** — asymmetric ID 1 (Uncategorized) filtering: was excluded from `wp_ids` at line 68 AND again subtracted from `in_wp_not_config` at line 71, but NOT excluded from `in_config_not_wp` at line 72. Fixed: ID 1 excluded only once from `wp_ids`, then `in_config_not_wp` properly excludes it. Added pagination warning when WP returns 100 categories (page limit).
- **`agents/humanizer.md:3`** — description said "Edit-only (cannot Write whole files)" but tool whitelist includes Write (needed for humanizer-report.json output). Fixed description to accurately reflect: Edit for draft.md, Write only for report output.

### Version Manifest Alignment
- **`.claude-plugin/marketplace.json`** — plugin entry had version 3.5.0 while root had 3.6.0 (drift from prior release). Both now aligned at 3.7.0.
- All 5 version manifests synced: VERSION, plugin.json, marketplace.json, install.sh, install.ps1.

### .gitignore Hardening
- Added `audit_output/` and `audits/` (were leaking to git status as untracked)
- Added `memory/research/project-charlie_*.json` and `memory/research/project-juliet_*.json` (per-project research data, not plugin code)

### Plugin Cache Sync
- Full source → cache sync for all modified files (12 modified + 1 new)
- Cache directory restructured to match source at version 3.7.0

## [3.6.0] - 2026-05-26 (Pipeline orchestrator + quality gate enforcement)

### Pipeline Orchestrator (Root Cause Fix)
- **NEW** `scripts/pipeline/orchestrator.py` — deterministic Python state machine with 25 stages. Replaces LLM-as-orchestrator advisory guidance with artifact-based stage sequencing. `--action next` returns the first mandatory stage whose inputs exist but outputs don't. LLM cannot skip stages because the orchestrator keeps returning the same stage until its artifacts appear.
  - CLI: `--action next|verify|status`, all JSON output
  - Covers all 5 phases: research (3) → plan (4) → build (3) → optimize (12) → publish (3)
  - Fork-join pattern for image pipeline (background launch + artifact-based join)
  - Conditional stages (localization-pass when locale != en-US, local-uniqueness when local_mode=true)
- **NEW** `scripts/pipeline/pre_publish_gate.py` — 9 mandatory artifact gates that hard-block wp_publisher:
  1. draft (>=1000 words)
  2. meta (required SEO fields)
  3. citations (>=3 APA-7 entries)
  4. images (images.json from Fork B)
  5. render_lint (L1-L9 passed)
  6. image_placeholder (D1-D5 passed)
  7. fact_check (fact-check.json exists, verdict != BLOCK_PUBLISH)
  8. humanizer (humanizer-report.json exists, ai_slop_score < 20)
  9. reviewer (review.json exists, score >= target)
- **NEW** `scripts/pipeline/pipeline_checklist.py` — stage completion tracker, 17 mandatory + 5 recommended stages
- **NEW** `scripts/lint/table_density_check.py` — enforces >=2 markdown tables with >=1 in front 50%
- **FIXED** `scripts/wordpress/wp_publisher.py` — pre-publish gate failure now returns `result` (hard-block) instead of printing warning and continuing. `success=false, post_id=null` when gate fails.
- **UPDATED** `skills/seo-blog/SKILL.md` — mandatory orchestrator invocation at every stage transition. LLM must call `python -m scripts.pipeline.orchestrator --action next` instead of reading prose pipeline description.

### Root Cause Analysis
- Identified 5 root causes for 53-83% pipeline stage skip rate across 2 production runs:
  - A: No pipeline engine (LLM reads markdown as advisory) — **FIXED by orchestrator.py**
  - B: Stage gate warn-only (publisher continues on failure) — **FIXED by return result**
  - C: Subskills not auto-invoked — **MITIGATED by orchestrator returning stage + command**
  - D: Artifact checks are documentation not code — **FIXED by pre_publish_gate 9 gates**
  - E: Fork-join not implemented — **FIXED by orchestrator fork/join stages**

### Quality Gate Scripts Wired
- `scripts/validate/core_eeat_scorer.py` — now referenced in orchestrator stage list
- `scripts/validate/cite_scorer.py` — now referenced in orchestrator stage list
- `scripts/validate/ai_slop_score.py` — now referenced in orchestrator stage list
- `scripts/lint/citation_capsule_lint.py` — now referenced in orchestrator stage list

## [3.5.0] - 2026-05-25 (Website audit system + security hardening + pipeline wiring fixes)

### Full Website SEO Audit (standalone)
- 15 specialist audit agents (8 core + 7 conditional: technical, content, schema, sitemap, performance, visual, GEO, SXO, local, maps, Google, backlinks, cluster, drift, e-commerce)
- 15 production audit scripts: `crawl_site.py`, `parse_html.py`, `audit_scorer.py`, `business_type_detector.py`, `pagespeed_check.py`, `capture_screenshot.py`, `report_generator.py`, `report_html.py`, `validate_audit_report.py`, `verify_backlinks.py`, `commoncrawl_graph.py`, `moz_api.py`, `google_oauth_setup.py`, `fetch_page.py`
- 8 audit reference docs (`references/audit/`): E-E-A-T framework, CWV thresholds, quality gates, schema types, local SEO signals, backlink quality, scoring weights, business types
- JSON schema for audit report validation (`schemas/audit-site-report.schema.json`)
- 7-category weighted scoring (Technical 22%, Content 23%, On-Page 20%, Schema 10%, Performance 10%, AI Search 10%, Images 5%)
- Enterprise HTML report + ACTION-PLAN.md generation
- Invocation: `/website-audit https://example.com [--max-pages N]`

### Security Hardening
- Removed all hardcoded WP credentials and Cloudflare tokens from 11 source files
- `media_metadata_backfill.py` and `visual_metadata_patch.py` now use `credential_hub.py`
- Debug scripts (`_debug_*.py`, `_run_*.py`, `_check_*.py`, `_count_*.py`) excluded from git via `.gitignore` patterns
- Audit output directories (`seo-audit-*/`), temp images (`_tmp_images/`), runtime data (`_audit_*.json`, `_media_inventory.json`) excluded from git
- Memory archive directory excluded from git

### Pipeline Wiring Fixes (Rule 6 compliance)
- `phase-optimize/SKILL.md` — added Stage 2b with mandatory Bash invocations for `render_lint.py`, `image_placeholder_check.py`, `section_completeness_check.py`, `local_uniqueness_check.py` (conditional on `local_mode`). These lint gates were documented in `seo-blog/SKILL.md` but never invoked by the phase orchestrator (dead code).
- `phase-build/SKILL.md` — added post-build `section_completeness_check.py` invocation to catch writer subagent silent dropout before proceeding to fact-check.
- `audit-cluster.md` and `audit-ecommerce.md` — added fallback instructions for missing `serp_overlap.py` and `schema_validate.py` scripts.

### Code Fixes
- `image_placeholder_check.py:236` — dead assignment before for-loop overwrite (initialized to `None`)
- `openai_image_pipeline.py:535` — redundant ternary with identical branches (`"batch_only" if mode == "batch" else "batch_only"` → direct assignment)

### New WordPress Utilities
- `audit_post_categories.py` — audit + PATCH post categories using signal-based category_selector
- `snapshot_categories.py` — snapshot live WP taxonomy to local JSON
- `media_metadata_overrides.py` — visually-verified metadata for 58 images

### Version Manifest
- VERSION, plugin.json, marketplace.json all synced to 3.5.0
- Plugin cache synced (marketplace + 3 temp_local caches, zero drift verified)
- GitHub repository URL corrected in plugin.json and marketplace.json

## [3.4.0] - 2026-05-22 (v5.0 plan — Local SEO as first-class plugin capability + 10 audit-driven bug fixes)

This is a minor-version bump introducing the plugin's first complete local-SEO capability. Industry-agnostic — works for plumbers, dentists, ecommerce, SaaS, cannabis B2B, any vertical. Built per the v5.0 plan after 5 deep-research streams + critical-validation audit found that v4.0's original plan would have over-engineered (32 new files for hypothetical generalization) while leaving 10 real production-pipeline bugs unfixed.

### Stage A — Real bug fixes (audit-prioritized, 10 items)

These came out of the 2026-05-22 internal code audit (`memory/research/internal_code_audit_2026.json`) which surfaced 42 findings (4 CRITICAL + 14 HIGH) — patterns identical to the bugs that produced 3.3.0 → 3.3.3 incident waves.

- **A0** — `state.json::stage_history` wired into orchestration. `scripts/_core/file_bus.py` gains `record_stage_start / record_stage_complete / has_stage_run / list_stages_run / stage_context` (context manager). `wp_publisher.publish()` + `openai_image_pipeline.generate_images()` now record execution. `verify_post.py` check 26 (new) warns when expected stages have no record. `state.schema.json` accepts `in_progress` status. Reference: `references/orchestration/stage-tracking.md`.
- **A1** — 10 silent-fallback broad-except instances fixed (`wp_publisher.py:865`, `attach_images_to_draft.py:80`, `cost_ledger.py:386`, `setup_categories.py:72`, `tag_seo_resolver.py:189`, `credential_hub.py:220+421`, `wp_client.py:58`, `wp_taxonomy.py:97`, `assemble.py:88`). Each fallback now logs to stderr; the 3.3.3 NameError pattern cannot recur silently.
- **A2** — `agents/writer.md`, `agents/humanizer.md`, `subskills/build/section-drafter/SKILL.md` now load `references/style/markdown-authoring-conventions.md` (the canonical doc for image-slot syntax, no raw `<strong>`, etc.). 80% of past writer-drift incidents traced to this doc not being read by writers.
- **A3** — `wp_publisher.py:220` References gate switched from string-match `"## References" not in body` to robust `_has_existing_references_block()` detector (handles markdown / raw HTML / escaped HTML forms).
- **A4** — `citations.json` top-level key drift fixed. Publisher's `_load_citation_entries` now accepts `refs / citations / references / items / list`. `subskills/build/fact-check-and-citation/SKILL.md` documents `citations` as canonical.
- **A5** — `schemas/meta.schema.json` drift fixed. `tags` now accepts `array | string`, `image_search_keywords` no longer required, `og_image / og_image_url` and `twitter_card_type / twitter_card` both accepted as aliases. Production meta.json now validates cleanly.
- **A6** — `post_tool_use_schema_validate.py` hook verified working (exit 2 on invalid, exit 0 on valid). Hook itself was fine; bug was the schema being too strict.
- **A7** — `scripts/lint/image_placeholder_check.py` NEW. Detects three drift modes: `![alt](images/X.png)` instead of `[IMAGE-SLOT-X]` (caught all 3 2026-05-22 articles), count mismatch with outline.image_slots, unknown slot_id. Wired into `skills/seo-blog/SKILL.md` as `gates.image_placeholder.passed`.
- **A8** — `scripts/lint/silent_except_audit.py` NEW. AST-based static scanner finds broad-except + silent-fallback patterns across `scripts/`. CI-runnable (`--strict` exits non-zero on findings).
- **A9** — `tests/test_claim_marker_case_insensitive.py` NEW. 19 pytest cases pin the case-insensitive `_CLAIM_MARKER_RE` behavior. Prevents regression of the 2026-05-22 Post 37187 leak.

### Stage B — 5 archetypes + 3-tier industry-to-schema resolution

- **B1** — `references/local/industry-to-schema-mapping.md` NEW (~250 lines). Source of truth for `schema-generator` auto-selection. Documents 5 business archetypes (A local brick-and-mortar / B service-area / C multi-location chain / D national ecommerce / E pure SaaS), Tier 1 closed-enum (15 industries → Schema.org leaf), Tier 2 soft-warning (10 industries), Tier 3 open fallback. Covers edge cases (Attorney→LegalService DEPRECATED, cannabis dispensary→Store+additionalType, no native cannabis B2B leaf, etc.).
- **B2** — `schemas/business-context.schema.json` NEW (was referenced by projects but never existed). Adds 12 new `location.*` fields: `business_archetype` (A-E enum), `business_category`, `schema_org_type`, `additional_type`, `local_article_pattern` (service_area | spatial_coverage), `ymyl_flag`, `service_areas`, `nap`, `gbp`, `shipping`, `local_seo_mode`, `local_authority_links_by_state`. All optional — projects without `location.*` get legacy behavior.
- **B3** — `subskills/optimize/schema-generator/SKILL.md` extended with "Local-aware schema generation" section. Reads `location.*` and emits per archetype: A/B/C → LocalBusiness leaf + Service.areaServed (Pattern A); D/E → `OnlineStore` / `Organization` + Article.spatialCoverage (Pattern B / "Wirecutter pattern"). Schema-generator NEVER emits `Service.areaServed` for archetype D/E — that's an E-E-A-T misleading-data signal per Google's 2025-12-10 doorway policy update.
- **B4** — `subskills/init/website-project-init/SKILL.md` Q7-Q12: 6 new local-SEO questions in the init flow (archetype, business category, local article pattern, local_seo_mode, NAP, GBP).

### Stage C — Minimum viable local SEO (detection + templates + routing)

- **C1+C2** — `scripts/research/_detect_local_intent.py` NEW (4-tier cascade: regex → bundled US gazetteer → spaCy NER fallback → geopy opt-in). Bundled data: `scripts/research/data/us_states.json` (50 + DC + 12 regions) + `scripts/research/data/us_cities_top500.json` (top 500 US cities by population). Handles 12 English-word collision state abbreviations + 4-step ambiguity policy (project service-area bias → context cues → population gap → flag ambiguous). 10/10 hand-tested edge cases pass + 25 pytest cases in integration suite.
- **C3** — `templates/local-state-pillar.md` NEW. 3000-3200w state-level pillar with 13-H2 skeleton, Sterling Sky 80/20 enforcement (4 categories of unique-per-locality content), dual-pattern schema support, industry-agnostic.
- **C4** — `templates/local-city-page.md` NEW. 2400-3000w city-level template with 11-H2 skeleton, neighborhood specificity rules, dual-pattern schema support.
- **C5** — `schemas/state.schema.json::brief` extended with `local_mode` (bool) + `location_anchor` (12-field object: type / canonical / fips / geonameid / name_full / containing_state / population / ambiguous / disambiguation_options / detection_tier / confidence / country).
- **C7** — `skills/seo-blog/SKILL.md` startup sequence step 5: runs `_detect_local_intent.py` on user keyword when `business-context.json::location.local_seo_mode != "off"`, writes `brief.local_mode` + `brief.location_anchor` to state.json, handles ambiguity disambiguation.
- **C8** — `agents/writer.md` accepts `local_mode` + `location_anchor` + `locality_signals_required` + `local_article_pattern` from section-drafter. Enforces service-voice vs Wirecutter-voice content consistency with the schema-generator's emission decision.

### Stage D — Pilot validation + 4-factor uniqueness lint

- **D1** — `scripts/lint/local_uniqueness_check.py` NEW. 4-factor composite scorer (F1 entity density / F2 factual-claim density / F3 sibling-article Jaccard / F4 lexical TTR diversity) + Sterling Sky 4-category enforcement (programs / case-studies / landmarks / pricing-logistics). NOT a single-Jaccard hard veto (validation research P1 found Sterling Sky 80/20 is heuristic, not Google's official threshold). Composite ≥70 = PASS, 50-69 = WARN, <50 OR missing category = FAIL.
- **D2** — `tests/test_v5_local_pipeline_integration.py` NEW. 25 passing pytest cases + 4 xfail (documented limitations) prove end-to-end integration: detector → schema validation → uniqueness lint → image-placeholder lint. Industry-agnostic test fixtures (solar Texas, dentist Boston, EV charger Oklahoma).
- **D3** — `scripts/wordpress/verify_post.py` check 27 (new): `geo_anchor_density`. Verifies `location_anchor` appears in H1 + ≥3 H2 + ≥10 body mentions when local_mode=true. Skips with informational warn for `near_me` type.
- **D4** — `docs/local-seo-quickstart.md` NEW. End-user guide.

### Memory updates

- New: `memory/research/v5_critical_validation_2026.json` (red-team verdict)
- New: `memory/research/internal_code_audit_2026.json` (42 findings)
- New: `memory/research/local_seo_deep_research_2026.json` (Whitespark / Sterling Sky 2026)
- New: `memory/research/competitive_local_seo_tools_2026.json` (13-tool capability matrix)
- New: `memory/research/local_schema_industry_mapping_2026.json` (Schema.org deep dive)
- New: `memory/research/location_intent_detection_2026.json` (4-tier architecture)
- New: `memory/research/project-charlie_final_schema_decision_2026.json` (canonical schema example)
- New: `memory/research/project-charlie_local_seo_state_intel.json` (US cannabis state data — for future project-charlie content runs, not plugin behavior)

### Backward compatibility

100% backward compatible. Projects without `location.*` in business-context.json behave exactly as in 3.3.x. The detector only runs when `location.local_seo_mode != "off"`; the schema-generator's new local emission only fires when archetype is set.

### What's deliberately NOT in 3.4.0 (deferred per YAGNI)

- Public-data API pipeline (DSIRE / NOAA / Census / Google Places auto-fetch) — wait for proven user demand
- Hub-and-spoke architecture automation
- GBP post auto-push
- Multi-location chain (archetype C) per-location schema auto-generation
- International detection beyond US/UK/CA postcodes

See `docs/local-seo-quickstart.md` for the user-facing quickstart.

## [3.3.3] - 2026-05-21 (HowTo schemas + policy-loader bug fix + per-post schema cleanup, task 7w0gl0260521 finalized)

### Fixed — critical: `_load_seo_plugin_provided_types` was silently returning empty

- **`scripts/wordpress/wp_publisher.py :: _load_seo_plugin_provided_types()`** — the 3.3.2 implementation referenced `PLUGIN_ROOT` without importing it; the resulting `NameError` was caught by the function's `except Exception: return set()` and silently swallowed. Net effect: the policy filter was a no-op — the publisher's defense-in-depth wasn't actually defending. Fixed to use `file_bus.PLUGIN_ROOT` (which is the canonical source). Now the policy properly loads the 8-type provided list. End-to-end simulation: 6/6 filter decisions match expectation (FAQPage KEPT, BreadcrumbList SKIPPED, mixed @graph KEPT, fully-provided @graph SKIPPED, etc.). Surfaced by deep-research verification — pre-3.3.3 the per-project policy was declared but not enforced.

### Added — HowTo schemas extracted from prose

- **Post 37063 — HowTo "7-Step Buyer Framework Before You Commit Capital"**: extracted all 7 steps directly from rendered HTML using `<strong>Step N — title.</strong> body` pattern. Each step has accurate `name` + `text` from source (no auto-generation). `totalTime: PT12W` (the 12-week pilot cycle in Step 7). Body schemas now: FAQPage + HowTo.
- **Post 37126 — HowTo "9-Item Pre-Purchase Vetting Checklist"**: extracted all 9 items from rendered HTML using `<strong>N. title.</strong> body` pattern. Body schemas now: FAQPage + ItemList + HowTo.
- Method: extract steps from THE ACTUAL article content, not auto-summarize. Each step's `text` is the verbatim article paragraph (HTML stripped, entities decoded, whitespace collapsed). No hallucinated or paraphrased steps.

### Diagnostics — deep-research verification pass

- DV1 — re-verified all 6 posts (regression check): 5/6 19/19 PASS, 1/6 18/19 (draft, expected for check 07 on a draft)
- DV2 — Dataset JSON-LD on 37090 + 37103: full Schema.org + Google Rich Results validation — all required fields present, `@id` stable, `variableMeasured` shape correct, dates ISO-8601, license URL resolvable
- DV3 — Schema-coordination policy end-to-end: caught the `PLUGIN_ROOT` import bug (see Fixed above); after fix, 6/6 filter cases match expectation
- DV4 — Source ↔ cache drift: zero drift on runtime code after fix sync; runtime artifacts (.seo/change-log.json, wp-taxonomy-cache.json) intentionally drift as the publisher updates them

### Final post-schema distribution (project-charlie, post-cleanup)

| Post | Body schemas |
|---|---|
| 37063 | FAQPage + HowTo |
| 37090 | FAQPage + ItemList + Dataset |
| 37103 | FAQPage + ItemList + Dataset |
| 37126 | FAQPage + ItemList + HowTo |
| 37146 | Dataset + HowTo×2 + FAQPage *(unchanged — gold standard)* |
| 37163 | FAQPage + Dataset *(draft)* |

Each post head still has the 7-type RankMath @graph (Organization + WebSite + ImageObject + BreadcrumbList + WebPage + Person + BlogPosting). No duplicates anywhere.

## [3.3.2] - 2026-05-21 (SEO-plugin schema coordination, task 7w0gl0260521 continued)

### Added — SEO-plugin coordination layer

- **`projects/{slug}/business-context.json :: wordpress.seo_plugin_schema_provided`** — NEW field. Explicit list of `@type` values the project's SEO plugin (RankMath / Yoast / AIOSEO) emits natively in `<head>`. The schema-generator subskill reads this list and skips those types when building `schema.json`; the wp_publisher then defense-in-depths the filter so even if `schema.json` contains a forbidden type, it's not emitted in body. Result: no duplicate BlogPosting / BreadcrumbList / Organization / Person / etc. across head and body. project-charlie list (RankMath Pro + global Breadcrumb JSON-LD enabled): 8 types — Article, BlogPosting, Organization, Person, WebPage, WebSite, ImageObject, BreadcrumbList.
- **`scripts/wordpress/wp_publisher.py :: _load_seo_plugin_provided_types()`** — NEW helper. Reads `business-context.json` for the per-site policy. Returns empty set if not configured (preserves legacy behavior for projects without the policy).
- **`scripts/wordpress/wp_publisher.py :: _ld_block_types()`** — NEW helper. Extracts all `@type` values from a single JSON-LD block, handling `@graph` wrappers correctly.
- **`scripts/wordpress/wp_publisher.py :: _append_custom_schema_blocks(site_slug=...)`** — accepts `site_slug` and filters `ld_list` against the SEO-plugin-provided types. Logs each skipped block_name for audit. Heuristic: skip only when EVERY type in a block is provided by the plugin (preserves mixed-type blocks).
- **`subskills/optimize/schema-generator/SKILL.md`** — added a prominent "SEO-plugin coordination (READ THIS FIRST)" section. Documents the policy + lists which types schema-generator SHOULD emit vs SHOULD skip for project-charlie specifically. Defines verification semantics (verify_post check 17 satisfies required types from head OR body).

### Changed — verify_post check 17 scans head + body together

- **`scripts/wordpress/verify_post.py :: check_jsonld_schemas()`** — refactored. Pre-2026-05-21 it only scanned `content.rendered` (body); false-alarmed on posts where RankMath head schema was the dominant contributor and the publisher's body schema was supplemental only. New signature: `check_jsonld_schemas(body_html, *, head_html=None, min_total_blocks=2, require_types=...)`. The check now:
  - Reports head and body schema types SEPARATELY in `detail` for diagnostic clarity
  - Counts blocks across both contexts
  - Satisfies `require_types` if a type appears in EITHER context
- **`scripts/wordpress/verify_post.py :: _fetch_live_head()`** — NEW helper. Fetches the live URL via httpx + cache-busting query string + Cloudflare bypass token (from `projects/{slug}/credentials/cloudflare.json`). Returns the `<head>` section as a string. Skips for draft posts (live URL requires auth). 30-second timeout.
- **`scripts/wordpress/verify_post.py :: _extract_jsonld_types()`** — NEW shared helper. Handles three common JSON-LD shapes: single object, `@graph` array (RankMath / Yoast pattern), bare list.

### Fixed — backfilled live articles

- **Post 37063 (`1000-watt-led-grow-light-buyers-guide`)** — was the only published post with zero supplemental schema in body. Repaired via REST PATCH: extracted 10 Q&A pairs from FAQ section, built FAQPage JSON-LD, injected via `<!-- wp:html -->` block. BreadcrumbList no longer needed in body since RankMath now provides it in head.
- **All 5 published posts** — RankMath global Breadcrumb JSON-LD setting was enabled by user. FlyingPress cache was holding stale HTML; per-post REST touch (PATCH modified field) busted per-page cache and the new 7-type head @graph (with BreadcrumbList) is now serving to all visitors.

### Diagnostics — what we learned

- **FlyingPress + Cloudflare cache stack masks RankMath setting changes** until per-page touch or full cache purge. `x-flying-press-cache: HIT` will keep serving stale HTML indefinitely after a RankMath setting toggle. For future RankMath setting changes affecting head schema, plan a cache-purge step.
- **Plugin audit** for project-charlie (21 active plugins, Woodmart 8.4.1 theme):
  - **AI Engine v3.5.1**: zero frontend footprint (0 JS/CSS assets, 0 chatbots configured, REST endpoints 404). Safe to deactivate if not actively used in WP-admin.
  - **Contact Form 7 + WPForms Lite**: redundant pair (two form plugins). Recommend keeping WPForms, deactivating CF7.
  - **WPvivid Backup + WPvivid Pro**: Pro likely supersedes free; verify Pro standalone before disabling free.
  - All other 17 plugins: provide real value, no redundancy.

### Memory updates

- New: `reference_rankmath_seo_plugin_schema_provided.md` (the canonical list + diagnosis)
- Extended: `feedback_render_lint_classifier_landed.md` (linked from check 17 refactor)

## [3.3.1] - 2026-05-21 (markdown-render leak hardening, task 7w0gl0260521)

### Added — failure-class classifier replaces incident allowlist

- **`scripts/lint/render_lint.py`** — NEW pre-publish leak detector (260 LOC). Runs `markdown_to_html.convert()` against `draft.md` and scans the rendered HTML for FOUR generic leak classes: L1 (`&lt;tagname` HTML-escape inside any reader-visible body element), L2 (literal `{#anchor-id}` Pandoc syntax inside any `<h1..h6>`), L3 (unbalanced `**` markdown-bold markers — odd count = orphan), L4 (`<img srcset="...-NNNw.{ext}">` hand-rolled variant pattern referencing files that don't exist). Output: console summary + machine-readable `render-lint.json` artifact + exit 0/1/2. Wired into `skills/seo-blog/SKILL.md` as mandatory gate `gates.render_lint.passed`. Defects route to repair-orchestrator.
- **`references/style/markdown-authoring-conventions.md`** — NEW global authoring-rules doc. Replaces the per-project drift on these conventions with one canonical reference loaded by every writer agent. Six rules: markdown bold not raw `<strong>`, signature as markdown italic, References as numbered list, no Pandoc `{#xxx}` syntax, no custom `<img srcset>`, `<!-- wp:html -->` escape hatch for legitimate raw-HTML cases. Each rule has the production incident behind it documented.
- **`scripts/wordpress/verify_post.py`** — 3 new post-publish checks (defense in depth alongside the new pre-publish lint):
  - `check_no_pandoc_anchor_leak` (id 19) — L2 family
  - `check_no_hand_rolled_srcset` (id 20) — L4 family
  - `check_no_orphan_markdown_bold` (id 21) — L3 family

### Changed — source-level fixes neutralize bug families at the toolchain layer

- **`scripts/build/markdown_to_html.py` :: `ConvertOptions.image_srcset` default `True` → `False`**. The previous default emitted srcset URLs for `-480w/-768w/-1024w` derivative files that no upstream code generates — every variant 404'd on mobile/tablet viewports, leaving readers with broken-image placeholders or empty space. With the default flipped, WordPress's native `wp_image_add_srcset_and_sizes()` filter regenerates srcset at render time from registered sizes (300x300, 768x768, 1024x1024, etc.) that actually exist as derivative files on disk. Re-enable only when an image-post-processor is built that creates the variants.
- **`scripts/build/markdown_to_html.py` :: `_add_anchor_ids()`** — added `_PANDOC_TRAILING_ANCHOR_RE` constant; rewrote to strip Pandoc `## Title {#anchor-id}` trailing syntax BEFORE slug generation, and use the explicit author-provided slug as the id when present. Previously the `{#xxx}` literal leaked into the rendered heading text AND was slugified into the id producing garbage like `id="electrical-budget-120v-and-277v-circuit-planning-electrical-budget"`. Now writers can use Pandoc syntax and it just works.
- **`scripts/wordpress/wp_publisher.py:229`** — production call site flipped `image_srcset=True` → `False` (belt-and-suspenders alongside the dataclass default flip).
- **`scripts/wordpress/verify_post.py` :: `check_no_escaped_html_leak`** (check id 06) — generalized from a 2-pattern allowlist (`&lt;h2`, `&lt;p class=article-signature`) to a class-based detector. Scans every reader-visible body element (`<li>/<p>/<td>/<th>/<figcaption>/<blockquote>/<dd>`) for any escaped tag opener `&lt;tagname(&gt;|\s|/>)`. Excludes mathematical `&lt; 5` false positives by requiring the `&gt;` close or whitespace boundary. Forward-compatible with conventions we haven't met yet.
- **`projects/project-charlie/business-context.json :: mandatory_sections.key_takeaways.spec`** — rewrote the ambiguous "leading with a bolded <strong> clause" wording (which produced the 2026-05-21 task 7w0gl0260521 incident). Now explicitly documents the canonical `- **Lead clause** rest` form and forbids mixing markdown `**` with raw `<strong>`.
- **`projects/project-charlie/CLAUDE.md` :: Rule 3 step 4 (article signature)** — rewrote the signature template from raw `<p class="article-signature"><em>...</em></p>` HTML to canonical markdown italic `*Last reviewed... [contact](url).*`. Documents that the publisher's `wp_publisher.py:1150-1167` auto-tagger adds the `article-signature` class to the last `<p><em>X</em></p>` in body.
- **`subskills/init/website-project-init/SKILL.md` :: article_signature config template** — rewrote to make the markdown form canonical (`markdown_template` field) and the rendered HTML form documentation-only (`wording_template_rendered`). Future projects scaffolded via /init now inherit the safe convention. Adds `_authoring_note` referencing the global conventions doc.
- **`skills/seo-blog/SKILL.md`** — added `gates.render_lint.passed` to the "Cannot proceed past Optimize unless" hard-gate list (4 leak classes documented inline). Added the global conventions doc to "See also" with elevated prominence.

### Fixed — backfilled prior live articles

- **Post 37126 (`1000-watt-grow-light-kit`)** — repaired via REST PATCH. Was shipped 2026-05-21 with the entire References block + signature paragraph as escaped raw HTML (literal `&lt;ol&gt;&lt;li&gt;...`), broken `<hr />` separator, and empty `rank_math_robots` meta. Now passes 19/19 verify_post checks.
- **Post 37163 (`700-watt-led-grow-light`)** — repaired during the original incident. Now passes 19/19.
- Posts 37063 + 37090 — found to have missing/incomplete supplemental JSON-LD blocks (schema-injector pipeline bug from an older publisher version). Documented; out of scope for this thread.

### Sync notes

- All 9 modified files synced source → `~/.claude/plugins/cache/.../3.3.0/` for immediate effect in the installed plugin (alongside this version bump to 3.3.1).
- Cache snapshot now matches source. Future `/plugin install` against this source dir produces an artifact at 3.3.1.

### Memory updates

- New: `feedback_render_lint_classifier_landed.md` (the full architecture + philosophy shift writeup)
- Extended: `feedback_markdown_pitfalls_publisher_three_bugs.md` (original incident diagnosis)
- Linked from `MEMORY.md` index.

## [3.3.0+post20260521b] - 2026-05-21 (in-place dev patch, task 085fb1ba240c)

### Added — root-cause repairs surfaced by the 1000w-led-grow-lamp article run

- **`scripts/wordpress/wp_publisher.py` :: `_append_custom_schema_blocks()`** — NEW. Reads `workspace/{task}/schema.json` (auto-detects multiple top-level shapes) and appends each `ld_json` as an inline `<script type="application/ld+json">` block OUTSIDE the project CSS wrapper. Wired in as Step 6.8 of the publish() flow. Eliminates the manual post-publish PATCH that was required this run to inject the 4 custom schema blocks (Dataset, HowTo×2, FAQPage).
- **`scripts/wordpress/wp_publisher.py` :: `_resolve_featured_inline_policy_mode()`** — NEW helper. Reads `projects/{slug}/business-context.json :: featured_image_inline_policy.mode`. The `_replace_image_placeholders()` step now consults this — projects with `mode: "inline"` (project-charlie post-2026-05-21) include the `is_featured` cover image in body placement. Eliminates the `[IMAGE-SLOT-cover]` literal-text leak.
- **`scripts/wordpress/wp_publisher.py` :: `_has_existing_references_block()`** — NEW. Detects an existing References section in markdown form, raw HTML form, OR escaped HTML form (`&lt;h2 id=references&gt;`). Replaces the legacy string-match for `## References` which silently failed when upstream had embedded HTML that markdown-it then escaped.
- **`scripts/wordpress/wp_publisher.py` :: `_load_citation_entries()`** — NEW. Normalizes `citations.json` from multiple shapes: `{refs: [...]}`, `{citations: [...]}` (the fact-checker subagent's canonical output), `{items: [...]}`, or top-level list. Also accepts both `apa` and `apa_7` keys. Fixes the silent skip where the auto-append read `data.get("refs")` but the fact-checker writes `data["citations"]`.
- **`scripts/wordpress/verify_post.py`** — NEW standalone post-verification script. Structural HTML parsing (not string match) for 15 checks: REST OK, wrapper class on an ACTUAL body element (not CSS selector match), scoped CSS in inline style, image count, NO `[IMAGE-SLOT-…]` literal leak, NO markdown-it `&lt;h2`/`&lt;p class=` escape leak, RankMath meta completeness, References H2 + OL element presence (≥N `<li>`), article-signature element presence, status check, categories ≠ Uncategorized, JSON-LD blocks + required types, featured_media set, AND the new stale-media-dedup cross-check (when `publish-result.json` is passed). Invoke via `python -m scripts.wordpress.verify_post {slug} {post_id} --workspace {task_id} --expected-status draft [--require-schema-type X ...]`. Returns exit 0/1 + `--json` output.
- **`scripts/openai/openai_image_pipeline.py`** CLI loader — auto-detects 5 top-level input shapes (bare list, `{"prompts": [...]}`, `{"requests": [...]}`, `{"items": [...]}`, single-spec dict). Adapts the designer's richer schema (`slot_id`, `full_prompt`, `negative_prompt`, `aspect_ratio`, `filename_seed`, `alt_text_seed`) into the flat `ImagePromptSpec` shape automatically. Eliminates the manual converter step required this run.
- **`skills/seo-blog/SKILL.md` :: "Canonical workspace artifact schemas"** — NEW section documenting the exact shapes downstream stages expect: `state.json` (required `current_stage`), `meta.json` (FLAT, not nested under `og:`/`twitter:`), `citations.json`, `schema.json`, `images.json`. Plus a "Final-mile verification" note pointing to `verify_post.py`.

### Changed — pipeline orchestration (effects ALL projects)

- **`skills/seo-blog/SKILL.md` :: End-to-end pipeline diagram** — pipeline now forks an **image-generation branch** immediately after Phase Plan, so image API time overlaps with Phase Build + Phase Optimize. By the time wordpress-publisher needs the images, they're almost always ready. Saves 10-14 minutes per article on operator-driven runs.
- **`scripts/openai/openai_image_pipeline.py` :: `generate_realtime_all()`** — was sequential (`# Sequential (image API is slow + concurrent-limit risk)`). Patched to `ThreadPoolExecutor(max_workers=4)` with order-preserving result reassembly. 5× speedup on realtime (14 min → ~3 min for 4 images). Tier-3+ OpenAI image-API accounts permit 5+ concurrent.
- **`scripts/openai/openai_image_pipeline.py` :: file save (both realtime + batch paths)** — both paths now write the local file as `{filename_seed}.png` instead of `{slot}.png`. Prevents `wp_media.upload(check_existing_by_filename=True)` from deduping a new cover to a stale prior-article media (the wrong-cover-leak failure mode hit this run).
- **`projects/project-charlie/business-context.json :: image_pipeline_policy`** — bumped to v1.3. Added `kickoff_timing: "post_plan"` (forks image gen as background task right after outline) and `realtime_parallel_workers: 4`. Mode stays `realtime`.
- **`~/.xuanran-seo/config.yaml :: image`** — global defaults updated: `prefer_batch_api: false`, `pipeline_mode: realtime`, `pipeline_kickoff_timing: post_plan`, `realtime_parallel_workers: 4`. Applies to all projects without per-project override.
- **`subskills/init/website-project-init/SKILL.md`** — NEW Step 11.6 added: bake `image_pipeline_policy` defaults into new projects' `business-context.json` during /init.

### Fixed — recurring failure modes turned into compile-time-stable defaults

- **`scripts/wordpress/wp_publisher.py` :: line 163** — `result = apply_tag_seo(...)` was overwriting the outer `PublishResult` instance with a dict, then crashing at next media-upload line with `'dict' object has no attribute 'media_ids'`. Renamed to `tag_seo_result` to scope-isolate. Caused the full publish to abort during this run.

### Memory updates (auto-memory layer, ~/.claude/projects/.../memory/)

- New: `feedback_image_gen_forks_post_plan.md` (orchestration rationale + code touchpoints + override mechanism)
- New: `feedback_publisher_cover_dedup_and_inline_skip.md` (cover-dedup + inline-skip root causes + manual repair playbook)
- Rewritten: `feedback_batch_image_default_and_polling.md` (realtime is now the right default, batch only for overnight bulk)

### Wall-time impact for a typical 4-image / 6000-word `/article` run

| Phase | Pre-fix | Post-fix |
|---|---|---|
| Research → Plan → Build → Optimize → Quality gates | 15-20 min | 15-20 min (unchanged) |
| Image generation | +14 min serial (blocks publish) | 0 min visible (forked at Plan, parallel max=4) |
| Publish | + manual REST PATCH for schema + cover + references + signature | 0 manual repairs (all auto-injected; verify_post.py confirms) |
| **Total operator wall time** | **30-45 min + manual repair loop** | **15-20 min, fully automated** |

## [3.3.0+post20260521] - 2026-05-21 (in-place dev patch)

### Added

- **`scripts/openai/openai_image_pipeline.py`** — NEW canonical image-generation entrypoint. Submits a Batch API job (50% off), polls patiently for up to 25 minutes (configurable), falls back to realtime `images.generate` on terminal batch failure or timeout. Per-slot partial-failure fallback: if batch returns 3/4 success, only the failed slot runs realtime. Writes `images.json` (wp_publisher input) + `images_manifest.json` (audit) + `image_pipeline.log`. CLI flags: `--mode auto|batch|realtime`, `--max-wait-minutes N`, `--poll-interval-seconds N`, `--no-fallback`, `--allow-partial`, `--dry-run`, `--json`.
- **`projects/project-charlie/business-context.json :: featured_image_inline_policy`** — new per-project field. `mode: inline | no_inline | manual` controls whether the cover image is embedded in the post body. Set to `inline` for project-charlie after user updated theme to suppress featured-media auto-render.
- **`projects/project-charlie/business-context.json :: image_pipeline_policy`** — new per-project field. Codifies which image-pipeline mode + timeout the project wants by default.
- **`subskills/init/website-project-init/SKILL.md`** — Step 11.5 added: interactive featured-image-inline question. Asks new projects whether their theme auto-renders featured_media, sets `featured_image_inline_policy` in `business-context.json` accordingly.

### Changed

- **`scripts/openai/openai_batch_image_api.py`** — fixed `cost_ledger.log(None, ...)` TypeError on submit. Was crashing scripts after successful batch submission. Pass `0` (cost is incurred at download, not submit) + wrapped in try/except.
- **`subskills/image/openai-image-generator/SKILL.md`** — rewritten to invoke `openai_image_pipeline.py generate` as a single call. Replaces the prior submit → `awaiting-images` state → scheduled poller flow with synchronous pipeline that handles polling + fallback internally.
- **`subskills/image/batch-job-poller/SKILL.md`** — repositioned as supplemental recovery tool only. The unified pipeline does inline polling, so the scheduled-hook auto-poll is no longer required. Kept for orphan-batch recovery + diagnose-stuck-batch scenarios.
- **`projects/project-charlie/business-context.json :: publish_policy.default`** — reverted from `"publish"` to `"draft"`. The 2026-05-20 direct-to-live override is superseded. User reasserted draft-first as the canonical workflow.
- **`projects/project-charlie/business-context.json :: wordpress.default_categories`** — updated from `["Buyer Guides"]` to `["LED Buyer Guides"]` after project-charlie.example.com site taxonomy was overhauled from flat to hierarchical structure. Old IDs 89 + 97 no longer exist.
- **`projects/project-charlie/tags-config.json`** — added 4 new strategic_tags: `1000w-grow-light-kit`, `led-grow-light-kit`, `hps-grow-light-kit`, `grow-tent-complete-kit`. Added 1 new baseline brand tag: `spider-farmer`. Added `hps-to-led-retrofit` slug to `retrofit-strategy`'s `merge_from_slugs[]` for future setup_tags.py consolidation.
- **`projects/project-charlie/CLAUDE.md`** — HARD RULE 0 reverted to draft-first with explicit-confirmation requirement. Articles inventory updated with post 37126 (1000-watt-grow-light-kit). Existing articles 37063 + 37090 + 37103 + 37126 patched to include featured image inline (between Abstract and Key Takeaways H2) per new design.
- **`~/.xuanran-seo/config.yaml :: image`** — added `pipeline_mode: auto`, `batch_max_wait_minutes: 25`, `batch_poll_interval_seconds: 60` settings for the new pipeline.

### Fixed

- Tag SEO completeness on project-charlie post 37126 — 7 brand-new tags had been created with empty rank_math_title/description/focus_keyword (publisher's tag_seo_resolver only applies policy-default for tags not pre-declared in tags-config.json). Manually applied full SEO meta to all 11 post-attached tags + 5 promoted to strategic_tags.
- Categories on project-charlie post 37126 — initially fell to `[1]` Uncategorized because meta referenced names that no longer existed in the overhauled site taxonomy. Patched to `[144 LED Buyer Guides, 146 LED & HPS Comparisons]`.

### Memory updates (auto-memory layer, not in cache)

- New: `feedback_new_tags_need_full_seo.md`, `feedback_categories_must_be_verified_before_publish.md`, `feedback_batch_image_default_and_polling.md`, `reference_openai_image_pipeline.md`.
- Superseded: `feedback_project-charlie_publish_direct_to_live.md` (the 2026-05-20 direct-publish override is reverted), `feedback_no_inline_featured_image.md` (still default for other projects; project-charlie overrides per new design).
- MEMORY.md index updated.

### Notes

This is an in-place dev patch — no formal version bump. The cache was kept at 3.3.0 and 8 affected files were file-by-file synced from source → cache. The proper canonical sync mechanism is `/plugin update`, which the user may run at any time to formalize a 3.3.1+ release.

## [3.3.0] - 2026-05-20

### Added
- **`scripts/build/article_css_generator.py`** — new script that reads `projects/{slug}/brand/brand-config.json` and generates a scoped article CSS stylesheet (`projects/{slug}/brand/article-css.css` + `.min.css`). Scoped to `.{slug}-pillar` wrapper. Styles H2/H3, abstract callout, key takeaways, TOC, tables, figures + figcaptions, blockquotes, references, FAQ, links, lists, plus mobile + print breakpoints. Token-driven via CSS custom properties + `color-mix()`.
- **`subskills/image/image-curator/SKILL.md`** — new subskill that produces `image_metadata.json` with all 4 WordPress media fields per slot (title, alt_text, caption, description). Required before publish.
- **`subskills/init/website-project-init/SKILL.md`** — Step 12 added: interactive "Design article CSS?" prompt. On yes, runs `article_css_generator.py` for the new project.
- **`subskills/build/topic-angle-selector/SKILL.md`** — Stage 3.5 added: SERP-clone rejection. Rejects titles that match top-10 competitor patterns (≥60% token overlap), forces regeneration with a distinctive frame (contrarian disambiguation / number-as-thesis / decision-framework label / persona-narrowed).
- **`subskills/image/image-slot-allocator/SKILL.md`** — cover slot now allocated with `body_render: false`. Drafter must not emit `[IMAGE-SLOT-cover]` in body; theme renders featured image at post top.

### Changed
- **`scripts/wordpress/wp_publisher.py`** — six durable behaviors added to `publish()`:
  - All 4 image metadata fields (`title`, `alt_text`, `caption`, `description`) are passed to `wp_media.upload()`.
  - Images flagged `is_featured: true` are filtered from body placeholder substitution (defense-in-depth on top of slot-allocator's `body_render: false`).
  - `## References` section auto-appended from `workspace/{task}/citations.json` if not already present.
  - Each `<img>` tag wrapped in Gutenberg `<!-- wp:image -->` block with `<figcaption class="wp-element-caption">` populated from image metadata.
  - Project article CSS (`projects/{slug}/brand/article-css.min.css`) injected as inline `<style>` and body wrapped in `<div class="{slug}-pillar">`.
  - Whole post content wrapped in single `<!-- wp:html -->...<!-- /wp:html -->` block so WordPress preserves `<p>` tags, `<style>`, and `<figure>` verbatim (classic-content sanitization no longer strips them).
- **`subskills/publish/wordpress-publisher/SKILL.md`** — documented the new auto-behaviors with a behavior matrix.
- **`templates/pillar-page.md`** — TL;DR blockquote pattern deprecated; Abstract is now always the first body H2 (merges legacy "TL;DR + Abstract" into one section). Cover slot documented as `body_render: false`.

### Fixed
- **`scripts/openai/openai_batch_image_api.py:60`** — removed deprecated `response_format: "b64_json"` parameter that `gpt-image-2` no longer accepts. Without this fix, every batch image request fails with HTTP 400.
- Image captions and descriptions are no longer empty on WordPress media library uploads.
- Cover/featured image no longer renders as a duplicate at the top of the post body.
- **CSS `:only-child` layout bug** — removed `p > em:only-child { display: block }` and `h2#faq ~ p strong:only-child` from the CSS generator. The `:only-child` pseudo-class only counts ELEMENT siblings (text nodes are invisible to it), so the rule intended for the signature line (`<p><em>...</em></p>`) was also firing on every inline italic (`<p>Text <em>also</em> more</p>`) and breaking text onto its own line. Replaced with class-based `.faq-question` and `.article-signature` selectors that the publisher applies via `_tag_structural_paragraphs()` only when a `<p>` truly contains a single element with no surrounding text. Also splits FAQ Q+A pairs that were collapsed into a single `<p>` by markdown-it's default `breaks: false` setting (questions get `<p class="faq-question">`, answers get their own `<p>`).

## [3.2.0] - 2026-05-19

### Added
- `/init <url>` website project deep initialization with 5-tier JS rendering fallback waterfall
- `projects/{slug}/` per-client project archive (business-context / brand-voice / competitors / baselines)
- Single active-project pointer (`~/.xuanran-seo/active-project`) + `/switch /list-projects /show-project /forget-project`
- 24 evidence-backed blog format catalog (`references/seo/blog-formats-2026.md`)
- `format-selector` skill with 5-step decision tree (intent × funnel × AI engine × data × cluster)
- Image generation sub-pipeline: `image-slot-allocator` / `image-prompt-designer` / `openai-image-generator` / `batch-job-poller` / `image-post-processor`
- OpenAI gpt-image-2 + Batch API integration (50% cost off, 24h max)
- Strategy A shared Art Direction Prefix for visual consistency across 4 images per article
- `featured-snippet-optimizer` skill for Position 0 抢位（H2 后 40-60w answer block）
- `paa-answer-writer` skill (FAQ ≥60% from research.paa)
- `cta-placement` skill (single CTA / centered / 30-40% mark)
- `voice-search-optimizer` skill (Google Assistant + ChatGPT Voice targets)
- Spelling dialect localization (en-US/UK/AU/CA/NZ)
- Reading level control by persona inference (NNGroup 4-tone)
- WordPress wait-for-all-images publish flow

### Changed
- Total skills: 37 → 48
- Total agents: 14 → 15 (+ image-prompt-designer)
- Total scripts: 38 → 57
- Total references: 31 → 45
- Memory topology: `projects/{slug}/` + `memory/` (global) replaces single-tier `memory/`
- Quality gates: + Reading Level dimension in content gate
- Localization-pass: 6 → 7 dimensions (+ spelling dialect)

### Verified APIs (2026-05)
- Anthropic Claude Opus 4.7 (`claude-opus-4-7`)
- OpenAI gpt-image-2 + Batch API (50% off)
- Tavily Search & Extract API
- Crossref REST API (polite pool)
- Google Gemini 3.1 Pro (`gemini-3.1-pro`)
- WordPress REST API + Application Password
- YouTube Data API v3
- IndexNow protocol (Bing + ChatGPT)
- Patchright (Playwright anti-detection fork)
- Claude Code Plugin v2.1.142+

## [3.1.0] - 2026-05-19

### Added
- `/init` command and projects/{slug}/ archive system
- 24-format blog catalog with Wix/Yext/AirOps/Princeton GEO research data
- `format-selector` skill

## [3.0.0] - 2026-05-19

### Added
- Initial v3 architecture: 35 skills, 14 agents, 38 scripts
- 5-phase pipeline (Research → Build → Optimize → Publish → Monitor)
- 3-pillar input model (Brief / Research Brief / Brand Guideline)
- CORE-EEAT 80-item + CITE 40-item + AI-Slop quality gates
- 5-Voice × 5-Purpose humanization matrix
- HOT/WARM/COLD memory model
- Cross-host adapters (Claude Code / Gemini API / Codex)

### Migrated from v2.0
- `default-beta-v1.5.ts` monolithic prompt → 11-stage pipeline
- `default-beta-youtube.ts` → folded into v1.5 + `embed_youtube` flag
