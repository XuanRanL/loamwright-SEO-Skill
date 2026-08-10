---
name: phase-optimize
description: Run Phase Optimize — humanize, meta build, schema, internal link, GEO optimize, visual design, CTA module + deterministic lint gates (render / density / keyword / PAA alignment / locale spelling / local uniqueness) + 4 quality gates + repair escalation. Use when draft.md exists and needs polish + quality assurance. Triggered by /seo-blog optimize, /audit, "run quality checks", "make this ready to publish".
allowed-tools: [Read, Write, Edit, Bash, Task]
disable-model-invocation: false
---

# Phase Optimize Orchestrator

Polish + multi-gate quality verification + repair loop.

## Inputs

Required in `workspace/{task_id}/`:
- `draft.md` (from build phase or external)
- `state.json`, `research.json`, `outline.json`, `citations.json`

## Stage 1: Polish (matches the orchestrator STAGES table — v3.35 reality sync)

```
1.  humanizer                     → 43 patterns lint + 5×5 voice/purpose + 3-mode + iterate N≤3
2.  meta-builder                  → title/slug/excerpt/tags/categories/image_search_keywords
3.  category-selector             → BASH: signal-based multi-category from categories-config.json
4.  schema-generator              → JSON-LD blocks (FAQPage/HowTo/ItemList/Dataset for body)
5.  internal-linker               → resolve [INTERNAL-LINK] placeholders + brand link map
6.  geo-content-optimizer         → 6 GEO techniques + engine-specific weights + entity injection
7.  visual-designer               → native-markdown components (tables/stat grids/quotes/TL;DR)
8.  cta-injection                 → BASH: python -m scripts.optimize.cta_injector --task-id {task_id} --project-slug {project_slug} --json
                                     (deterministic .xr-cta-box module from business-context.cta; no-op if project has no config)
```

**Retired / relocated (v3.35 — do NOT dispatch as polish steps):**
- `featured-snippet-optimizer` → RETIRED, merged into the build-phase
  `citation-capsule-builder` stage (FS 83% replaced by AIO; same 40-60w shape).
- `paa-answer-writer` → contract enforced by the `paa-alignment-check` lint gate
  (Stage 2b below); writers follow the SKILL's wording rules at draft time.
- `voice-search-optimizer` → RETIRED (no voice-only tactic exists; zombie-stat
  discipline). Manual diagnostic CLI only.
- `localization-pass` Mode 1 → the `locale-spelling-check` lint gate (Stage 2b);
  Mode 2 `/locale-audit` stays a user-invocable portfolio tool.
- `ai-overview-recovery` → a MONITOR-phase playbook (churn-guarded NOT_IN_AI
  routing via refresh_decision_router), never a per-article polish step.
Evidence for all five: references/seo/serp-feature-value-2026.md.

## Stage 2: Quality Gates (parallel, all 4 must pass)

```
Gate 1: CORE-EEAT (80-item, 8 dimensions × 10 each)
        Vetoes: T04 (fabricated stat) / C01 (fabricated citation) / R10 (prompt injection)
        Cap: 1 veto → final = min(raw, 60); 2+ → BLOCKED
        Pass: verdict ∈ {SHIP, FIX}

Gate 2: CITE (40-item, 4 dimensions × 10 each)
        Vetoes: T03 (missing affiliate disclosure) / T05 (missing E-E-A-T) / T09 (schema missing)
        Pass: verdict ∈ {SHIP, FIX}

Gate 3: AI-Slop (reproducible formula)
        score = 4×patterns_hit + 25×(1-burstiness) + 15×vocab_ratio
        Pass: score < 20

Gate 4: Pillar 100-pt (Content 30 + SEO 25 + EEAT 15 + Tech 15 + AI-Citation 15)
        Pass: total ≥ 80 (Good tier)

+ Format-fit dimension (v3.2)
+ Reading-level dimension (v3.2, per-persona)
```

## Stage 2b: Lint Gates (mandatory, run BEFORE independent reviewer)

All lint gates are mandatory Bash invocations. Each writes a JSON report; any
defect = hard veto → route to repair-orchestrator Stage 4. Do NOT skip these
even if the 4 quality gates above all passed — lint catches mechanical text
defects the LLM-judge gates cannot detect.

```bash
# 1. Render lint — catches L1-L8 leak classes (HTML escapes, Pandoc anchors,
#    unbalanced bold, srcset, claim markers, scaffold markers, BOM, JSON envelope)
python -m scripts.lint.render_lint --workspace {task_id} --json
# Output: workspace/{task_id}/render-lint.json
# Gate:   gates.render_lint.passed must be true

# 2. Image placeholder check — catches D1-D5 drift modes (local-path images,
#    count mismatch, unknown slot_id, zero placeholders, name mismatch)
python -m scripts.lint.image_placeholder_check --workspace {task_id} --json
# Output: workspace/{task_id}/image-placeholder-lint.json
# Gate:   gates.image_placeholder.passed must be true

# 3. Section completeness — catches writer subagent silent dropout
python -m scripts.lint.section_completeness_check --workspace {task_id} --json
# Output: workspace/{task_id}/section-completeness.json (auto file-bus)
# Gate:   gates.section_completeness.passed must be true

# 4. Local uniqueness (CONDITIONAL — only when state.brief.local_mode=true)
#    Skipped when local_mode=false.
# if state.brief.local_mode:
python -m scripts.lint.brand_fact_check --workspace {task_id} --json --out workspace/{task_id}/brand-fact-lint.json
# First-person company-fact consistency vs business-context.company (v3.36.0;
# no-op PASS for projects without a company block). Runs as the mandatory
# brand-fact-check stage right after locale-spelling-check.
python -m scripts.lint.local_uniqueness_check --workspace {task_id} --out workspace/{task_id}/local-uniqueness-lint.json
# Gate:   gates.local_uniqueness.passed must be true (when local_mode=true)

# 5. CTA module (v3.34) — mandatory stage; no-ops for projects without a cta config
python -m scripts.optimize.cta_injector --task-id {task_id} --project-slug {project_slug} --json
# Output: workspace/{task_id}/cta-injection-result.json
# Gate:   passed must be true (bad config / stripped module = hard veto)

# 6. PAA alignment (v3.35) — FAQ <-> research.paa >=60% contract, measured on the draft
python -m scripts.lint.paa_alignment_check --workspace {task_id} --json
# Output: workspace/{task_id}/paa-alignment-lint.json
# Gate:   passed must be true (no-ops PASS on thin PAA harvest / missing FAQ)

# 7. Locale spelling (v3.35) — dialect-drift AI-tell gate (en-GB leaking into en-US etc.)
python -m scripts.lint.spelling_dialect_check --workspace {task_id} --json
# Output: workspace/{task_id}/locale-spelling-lint.json
# Gate:   passed must be true (FAIL only at >=3 opposite-dialect hits; References/quotes/proper nouns exempt)
```

## Stage 3: Independent Reviewer (separate subagent, NO pipeline history)

```python
review = task({
    "subagent_type": "reviewer",
    "context": {"role": "Google E-E-A-T editor + Perplexity citation judge"},
    "input_files": ["draft.md", "state.json"],
    "references": ["seo/seo-checklist-2026.md", "geo/core-eeat-80.md"]
})
# Returns review.json: score, verdict, strengths, weaknesses, would_change
```

Required: `review.score >= state.brief.quality_target_score`

## Stage 4: Repair Escalation (only if any gate fails)

```
Round 1: SURGICAL
  - Edit only repairs[].instruction specified lines/segments
  - Cheapest, fastest
  - If score improves <3 or worse → escalate

Round 2: SECTION-REWRITE
  - Rewrite full section if any section's issues persist
  - New drafter agent with original section + repair instructions

Round 3: STAGE-REWRITE
  - Rerun a stage (e.g. outline-architect or fact-checker)
  - Previous quality.json as negative example

Round 4: FULL-REGEN
  - Rerun all of Phase Build (preserve research/angle/outline)

Round 5: FROM-SCRATCH
  - Rerun from Plan (new angle from alternative_titles_considered)
  
Hard cap: 4 rounds total. Round 5 → halt + return best-of-N + repair-report.
```

## Output

- `workspace/{task}/draft.md` (final, frontmatter `Stage: optimized`)
- `workspace/{task}/meta.json`
- `workspace/{task}/quality.json` (all gates' results)
- `workspace/{task}/review.json` (independent reviewer)

## Handoff

`recommended_next_skill: "phase-publish"` (only if all gates passed)

## See also

- Sub-skills under `subskills/optimize/` (see the Stage-1 table above for which are
  live stages vs retired pointers)
- `subskills/cross-cutting/repair-orchestrator/SKILL.md`
- `agents/reviewer.md`
- `agents/seo-auditor.md`
- `agents/geo-auditor.md`
