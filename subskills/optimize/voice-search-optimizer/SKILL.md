---
name: voice-search-optimizer
description: RETIRED v3.35 (2026-07-04) — voice search optimization has no tactic that answer-first content, FAQ sections, and schema do not already cover; the founding "50% of searches by voice" statistic is a debunked zombie citation. scripts/lint/voice_search_check.py survives as a MANUAL diagnostic only.
disable-model-invocation: true
user-invocable: false
---

# Voice Search Optimizer — RETIRED

**Status: retired 2026-07-04 (v3.35). Do not dispatch. Not an orchestrator stage.**

## Why retired

- The "50% of searches will be voice by 2020" statistic that founded VSO is a
  mis-attributed zombie citation; it never materialized. 2026 posts still recycling
  it ("27% of queries are voice") trace to the same debunked lineage.
- Search Engine Land's own VSO guide (updated Nov 2025) lists question headings,
  conversational long-tail, FAQ blocks, snippet formatting, FAQPage/HowTo schema,
  and page speed — every item is standard SEO this pipeline already executes
  (FAQ mandatory section + paa-alignment-check, citation capsules, schema-generator,
  humanizer). **No voice-only tactic exists.**
- The genuine shift went to conversational AI (ChatGPT voice, Gemini Live), which
  consumes the same answer-first content the GEO stages already optimize for.

## What survives

- `scripts/lint/voice_search_check.py` — retained as a **manual diagnostic CLI**
  (never a stage; running it as a gate would block on a discipline with no evidence):

  ```bash
  python -m scripts.lint.voice_search_check --input memory/workspace/{task}/draft.md --json
  ```

## Evidence base

`references/seo/serp-feature-value-2026.md` §3.
