---
name: featured-snippet-optimizer
description: RETIRED v3.35 (2026-07-04) — merged into the wired citation-capsule-builder stage. Featured snippets fell 18%→8% of SERPs in 2025 (83% replaced by AI Overviews) and both select the same 40-60w extractive answer shape; a separate FS step would duplicate the capsule stage.
disable-model-invocation: true
user-invocable: false
---

# Featured Snippet Optimizer — RETIRED (merged)

**Status: retired 2026-07-04 (v3.35). Do not dispatch. Kept as a pointer.**

## Why retired

- Ahrefs (Jun 2025): FS prevalence 18% → 8% Jan–Jun 2025; 0.9 correlation with AIO
  growth; ~83% replacement in 8 months; FS and AIO rarely co-occur.
- The tactic this SKILL documented (40-60 word declarative answer block after a
  question H2, specific number, no hedging) is EXACTLY what the wired
  `citation-capsule-builder` stage produces and `scripts/lint/citation_capsule_lint`
  validates. Two stages writing the same block = duplicate/conflicting edits.
- Rule-6 history: this SKILL had pseudo-code and no executor since v5.0 — it never
  ran in production anyway.

## Where the behavior lives now

- **Executor:** `citation-capsule-builder` stage (`scripts/pipeline/orchestrator.py`),
  whose dispatch prompt PRIORITIZES sections `outline.json` marks
  `is_featured_snippet_target: true` (outline-architect still sets that flag from
  `research.serp_features`; since v3.35 it finally has a consumer).
- **Validation:** `python -m scripts.lint.citation_capsule_lint {ws}/draft.md --json`
- `outline.sections[].snippet_format` is deprecated orphan data — do not emit.

## Evidence base

`references/seo/serp-feature-value-2026.md` §1.
