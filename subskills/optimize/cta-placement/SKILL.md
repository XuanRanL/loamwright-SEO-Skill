---
name: cta-placement
description: Inject the project's designed CTA module (styled .xr-cta-box conversion card) into the draft. Config lives in business-context.json :: cta (legacy) or :: conversion_offers (v3.37 service-aware). Projects without either no-op.
allowed-tools: [Read, Bash]
---

# CTA Placement (v3.37 — three-stage, service-aware + composable design system)

> **History:** v3.34 added the executor with a single static config (9 total
> copy variants site-wide, one fixed heading, one generic offer). v3.37 splits
> generation into three stages so every article gets a genuinely unique,
> service-routed CTA — see `docs/superpowers/specs/2026-07-08-cta-system-redesign-design.md`.

## The orchestrator stages (this is what actually runs)

These are **orchestrator-wired stages** in `scripts/pipeline/orchestrator.py`,
NOT commands you run by hand — the `run_pipeline` driver dispatches them in
order during the `optimize` phase (after `visual-designer`). The command lines
below are the *exact* `Stage(...)` executors, shown for reference:

```bash
# Stage 1 "cta-brief-builder" - deterministic fact resolver. ALWAYS writes
# cta-brief.json: a real resolved brief when the project has conversion_offers
# config, otherwise a no-config sentinel (resolved_service:null,
# skipped_no_config:true) so the orchestrator never hard-halts the pipeline:
python -m scripts.optimize.cta_brief_builder --task-id {task_id} --project-slug {project_slug} --json

# Stage 2 "cta-writer" - LLM composer (orchestrator dispatches
# agents/cta-writer.md; auto-skipped when Step 1's brief is the no-config
# sentinel, i.e. cta_brief_present is false):
# (dispatched via the orchestrator's "cta-writer" Stage, never run directly)

# Stage 3 "cta-diversity-check" (Gate 5) - runs AFTER cta-writer and BEFORE
# cta-injection, so a repetitive draft is caught before it is placed:
python -m scripts.optimize.cta_diversity_check --task-id {task_id} --project-slug {project_slug} --json --out {ws}/cta-diversity.json

# Stage 4 "cta-tone-check" (Gate 2) - runs AFTER cta-diversity-check and
# BEFORE cta-injection, so a hype/pressure-laden draft is caught before it is
# placed:
python -m scripts.lint.cta_tone_check --task-id {task_id} --project-slug {project_slug} --json --out {ws}/cta-tone.json

# Stage 5 "cta-injection" - deterministic placement (consumes cta-draft.json
# when present, else falls back unchanged to the legacy static cta.variants):
python -m scripts.optimize.cta_injector --task-id {task_id} --project-slug {project_slug} --json
# verify-only (used by pre_publish_gate check "cta_module"):
python -m scripts.optimize.cta_injector --task-id {task_id} --project-slug {project_slug} --check --json

# Stage 6 "cta-record-history" - runs AFTER cta-injection; appends this
# article's CTA fingerprint to projects/{slug}/cta-history.json so FUTURE
# articles' Gate 5 has history to compare against. GUARDED: records only when
# cta-injection actually placed the LLM draft (passed AND draft_source=='llm');
# the static/no-op path writes recorded:false and never pollutes the window:
python -m scripts.optimize.cta_diversity_check --task-id {task_id} --project-slug {project_slug} --record --json --out {ws}/cta-history-record.json
```

Wired as orchestrator stages (`scripts/pipeline/orchestrator.py`), in this
order, all in the `optimize` phase, after `visual-designer` and before
`visual-density-check`/`render-lint`:

| Stage name | Executor | Mandatory? |
|---|---|---|
| `cta-brief-builder` | BASH | optional (`is_mandatory=False`) |
| `cta-writer` | LLM, `subagent_type="xuanran-seo-blog-writer:cta-writer"` | optional; conditional — dispatched only when `state.json :: cta_brief_present == true` |
| `cta-diversity-check` | BASH (Gate 5) | optional; conditional on `cta_brief_present`; **blocks on `passed:false`** (`_PASS_FLAG_REQUIRED`) → re-dispatch `cta-writer` |
| `cta-tone-check` | BASH (Gate 2) | optional; conditional on `cta_brief_present`; **blocks on `passed:false`** (`_PASS_FLAG_REQUIRED`) → re-dispatch `cta-writer` |
| `cta-injection` | BASH | mandatory |
| `cta-record-history` | BASH | optional; conditional on `cta_brief_present`; bookkeeping only (never a gate, never halts) |

Do NOT hand-author CTA blocks in drafts — writers and optimize subagents must
never add or remove `### {cta heading}` blocks; the injector is idempotent
and the pre-publish gate re-scans for stripped blocks.

## What it injects

`### {heading}` + ONE paragraph (bold lead/avatar/quote + link), which the
publisher class-tags as `<p class="xr-cta-box">` (+ `xr-cta-quiet` or
`xr-cta-banner` skin modifier) via `scripts/_core/component_headings`
(component ids `cta`/`cta_quiet`/`cta_banner`) and the project's generated
article CSS renders as a conversion card with a real button.

For **ecommerce** projects (v3.38.0), the LLM block may instead carry a
`shortcode` field (a WooCommerce `[products ...]` shortcode copied verbatim from
`cta-brief.json :: resolved_products.shortcode`). The injector places it on its
own blank-line-separated line after the intro paragraph so WordPress expands it
into a live product grid — the grid is the conversion element, so the
markdown-link requirement (`_validate_variant`) is waived for shortcode-bearing
blocks (a fallback block with a null shortcode but a `target_url` keeps the
link). The shortcode is written verbatim; `sanitize_copy` touches the prose
only.

- `end` placement: before `## Further Reading` / `## References` (BOFU slot)
- `mid` placement (opt-in): after the content section at the ~35% word mark,
  never after the first content section
- Service-aware routing (v3.37): if the project has
  `business-context.json :: conversion_offers` configured, the CTA routes to
  the specific service page matching the article's blog category (via the
  project's `category_routing_map` file, e.g. `projects/{slug}/service-routing-map.json`),
  cites a real team member and proof point, and the copy is freshly LLM-authored
  per article — NOT a fixed variant. Projects without `conversion_offers` keep
  the legacy static `cta.variants` rotation unchanged.
- em-dashes sanitized to commas; ASCII apostrophes to U+2019; **no UTM on
  internal links** (GA4 self-referral anti-pattern)

## Config (per project)

Legacy: `projects/{slug}/business-context.json :: cta` — see
`schemas/business-context.schema.json`. `enabled:false` or absent = full
no-op (the stage still writes its evidence artifact).

Service-aware (v3.37, opt-in): `projects/{slug}/business-context.json ::
conversion_offers` (`business_model: "b2b_services"`, `services[]`, each with
`slug`/`url`/`positioning` required plus optional `persona`/`distinct_value_prop`/
`own_page_cta_copy`) + `company.team[]` (`name`/`role` required, plus
`photo_media_url`/`specialty_services[]`) / `company.proof_points[]`
(`type: "case_study"|"stat"` plus `subject`/`metric`/`period`/`url`/`claim`) +
the project's `category_routing_map` file (e.g. `projects/{slug}/service-routing-map.json`).
Set up interactively during `/init` Step 13.5, or backfilled manually — see
`subskills/init/website-project-init/SKILL.md`.

Ecommerce-aware (v3.38.0, opt-in, default ON at `/init` for archetype D):
`business-context.json :: conversion_offers` (`business_model: "ecommerce"`,
`default_category` slug/name fallback, `fallback_url` shop URL,
`catalog_path` optional override) + `constraints` (`no_person_blocks: bool`,
`tone: "grief_safe"`, `banned_phrases[]` — see `project-echo` and `project-hotel`
`business-context.json` for worked examples). The resolver reads
`projects/{slug}/product-catalog.json`, synced offline (never live at
build-time) via `python -m scripts.wordpress.wc_catalog_sync --project-slug
{slug} --json`; re-run that sync whenever the catalog changes materially. Set
up interactively during `/init` Step 13.5 (`subskills/init/website-project-init/SKILL.md`).

Operator category hint (2026-08-08): when the content plan names the CTA
product angle for a keyword (a batch row's "Ear wash" / "Gut probiotic"
column), set `state.brief.cta_category_hint` to the category slug or human
name at task creation. `build_brief` prefers the hint over content-based
category matching — token matching structurally cannot select a one-token
category name ('digestion' has no core-hit) or a long one ('Ear, Eye & Skin
Care' scores 0.25 on a single core token) — but the hint is STILL validated
against `excluded_categories` and in-stock status, so it can never reach an
Rx/forbidden category; an invalid hint degrades to the normal matcher with an
explicit warning. Provenance lands in `resolved_products.category_from_hint`.
Do NOT hand-edit cta-brief.json to redirect a category; the hint is the
supported channel. (`brief.cta_target` is a different, DEPRECATED v3.34 field
— never consumed; do not resurrect it.)
See "What it injects" above and `agents/cta-writer.md` for the shortcode
contract this config resolves into.

> **⚠️ The two config blocks are an AND-gate, not an either/or.** `conversion_offers`
> only powers Steps 1-2 (brief-builder resolves facts → cta-writer authors copy →
> `cta-draft.json`). Step 3, `cta_injector.py :: inject()`, is still gated on the
> **legacy** `cta` block: it unconditionally no-ops (`return` before placing
> anything) unless `business-context.json :: cta.enabled` is `true`. So a project
> that configures ONLY the new `conversion_offers` and forgets `cta: {"enabled":
> true, "placements": ["mid"]}` gets a `cta-draft.json` authored but **zero CTAs
> injected** — cta-writer runs successfully, then the injector silently skips.
> (Placement default is `["mid"]` since v3.41.5 — front-middle, ~35% word mark;
> `end` is an explicit opt-in.)
> A v3.37 service-aware project needs BOTH: `conversion_offers` (for the LLM path)
> AND `cta.enabled: true` (+ `cta.placements`) to actually place the block. The
> block heading then comes from the LLM draft, not `cta.heading`; `cta.variants`
> is only the static fallback.

The `heading` for EVERY CTA block (legacy static OR v3.37 LLM-authored) MUST
be a phrase `component_headings.classify_heading` maps to `cta`, `cta_quiet`,
or `cta_banner` (shipped: 21 phrases total across the 3 skins — 12 card +
5 quiet + 4 banner; see `scripts/_core/component_headings.py :: COMPONENTS`
for the exact list) — an unrecognized heading is a stage-blocking error, not
a silent style miss.

## Writer-side contract

On cta-enabled projects the conclusion is **synthesis only — no prose CTA
sentence** (the card replaces it; two adjacent CTAs read as pressure). The
article signature keeps its own contact link (Rule 5) — that is a footer, not
this module.

## Quality gates

Status of each gate is stated honestly — all 5 are wired into the orchestrator
and gate real articles (this whole system exists to demonstrate root CLAUDE.md
Rule 6: a documented behavior with no executor is a lie).

1. **Fact accuracy — WIRED (active).** `scripts/lint/brand_fact_check.py`
   (extended, v3.37), run as the `brand-fact-check` orchestrator stage. It scans
   the whole draft body — which by that stage includes the injected CTA text —
   for any named team member's claimed role or any case-study number, and flags
   a mismatch against `business-context.json :: company.team[]` /
   `company.proof_points[]`. Applies to both the legacy and service-aware paths.
2. **Voice/tone — WIRED (active, v3.38.0).**
   The original design proposed "reuse the humanizer's scoring on the CTA text,"
   but that is **structurally impossible**: the `humanizer` orchestrator stage
   runs during `optimize` BEFORE `cta-injection` ever writes CTA copy into
   `draft.md`, so there is no CTA text in the draft for the humanizer to score.
   The gate that actually shipped is `scripts/lint/cta_tone_check.py`, run as
   the `cta-tone-check` orchestrator stage (AFTER `cta-diversity-check`, BEFORE
   `cta-injection`) — it reads `cta-draft.json` directly rather than waiting for
   injection. Be honest about what this is: **a deterministic hype/pressure
   lexicon lint (v1), not an LLM judge.** It flags (a) a universal hype lexicon
   (revolutionary, game-changing, unbeatable, world-class, ...), (b) pressure
   phrases (act now, don't miss out, limited time, ...), (c) pressure
   punctuation/format (any `!`; ALL-CAPS words >=4 letters, minus a registered
   acronym allowlist), (d) per-project `cta-brief.json :: constraints.banned_
   phrases` (case-insensitive substring), and (e) — only when
   `constraints.tone == "grief_safe"` — a grief-unsafe sublexicon (deal,
   bargain, sale, grab, snap up, ...). `passed:false` blocks the stage
   (`_PASS_FLAG_REQUIRED`) and routes back to re-dispatch `cta-writer`, exactly
   like Gate 5. No-op PASS when no `cta-draft.json` exists. A subtler tone
   drift a human editor would catch (e.g. a technically hype-free sentence that
   still reads pushy) is NOT caught by this lint — that would need an LLM
   judge, which is out of scope for v1.
3. **Visual density ceiling — WIRED (active).**
   `scripts/lint/visual_density_check.py :: check_cta_block_ceiling()` caps
   building blocks per CTA block at 3. As of Task 14 it is **merged into the
   `visual-density-check` orchestrator stage's combined pass/fail** (that stage's
   `check()` now calls it and fails the whole stage if the ceiling is breached).
   No-op PASS when no `cta-draft.json` exists (the legacy static path + the 5
   projects without `conversion_offers`).
4. **Routing correctness — WIRED (active).** `cta_injector.py`'s per-block
   heading validation (inside the mandatory `cta-injection` stage) hard-fails an
   unregistered heading, and `verify_post.py` check 29's URL-correctness
   sub-check compares the live page's CTA link against `cta-brief.json ::
   target_url` when present. For ecommerce briefs with a non-null
   `resolved_products.shortcode` (v3.38.0), check 29 additionally fails if the
   literal `[products` survives to the live page (unexpanded shortcode) or if no
   WooCommerce product-grid markup is present (the shortcode expanded to
   nothing).
5. **Cross-article diversity — WIRED (active).**
   `scripts/optimize/cta_diversity_check.py`, run as the `cta-diversity-check`
   orchestrator stage (AFTER `cta-writer`, BEFORE `cta-injection`). Flags a
   heading reused within the last 5 history entries, or a hook opening sharing
   its first 6 words with a recent entry; `passed:false` blocks the stage
   (`_PASS_FLAG_REQUIRED`) and routes back to re-dispatch `cta-writer`. Does NOT
   flag reusing the same correct service/offer — that can be the right answer.
   The comparison window is populated by the `cta-record-history` stage, which
   runs after `cta-injection` and records a fingerprint ONLY when the LLM draft
   was actually placed (`draft_source=='llm'`) — so the legacy static path never
   pollutes the window. No-op PASS when no `cta-draft.json` exists.

> **Operator note — a GATE_FAILED gate does not fix itself.** `cta-diversity-check`
> and `cta-tone-check` (both WIRED — see item 2 above) both score `cta-draft.json`
> and block on `passed:false`, but neither one regenerates that file. A bare
> `run_pipeline`/`next_stage` re-run just
> re-scores the SAME failing draft and reports `GATE_FAILED` again — forever.
> The fix always lives one stage upstream: explicitly RE-DISPATCH the
> `cta-writer` subagent (Stage 2) so it authors a fresh, provenance-stamped
> `cta-draft.json`, THEN re-run the failing gate. This is the same "artifact
> exists is not the same question as artifact says pass" discipline root
> CLAUDE.md Rule 12 requires of every gate in this pipeline — see
> `scripts/pipeline/orchestrator.py :: _content_gate_reason()` for the
> analogous fact-check/review/verify-post gates, which all route back to
> RE-DISPATCH the upstream subagent rather than being hand-edited to pass.

## Verification chain

1. Stage evidence: `cta-injection-result.json` (`passed` flag enforced by orchestrator)
2. `pre_publish_gate` gate `cta_module` — re-scans the CURRENT draft via `--check`
3. `verify_post` check 29 (`29_cta_module_rendered`) — `<p class="xr-cta-box">`
   present on the LIVE page, AND (v3.37) its href matches `cta-brief.json`'s
   resolved `target_url` when present, AND (v3.38.0) for an ecommerce brief with
   a `resolved_products.shortcode`: no literal `[products` on the live page +
   WooCommerce product-grid markup present

## See also

- `references/seo/cta-placement-data.md` — evidence base + design-decision table
- `references/style/visual-design-components.md` — Component 9 (CTA module)
- `docs/superpowers/specs/2026-07-08-cta-system-redesign-design.md` — full design rationale
- `agents/cta-writer.md` — Step 2 subagent contract
