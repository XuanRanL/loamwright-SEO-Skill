---
name: paa-answer-writer
description: FAQ <-> research.paa alignment contract, machine-enforced since v3.35 by the mandatory paa-alignment-check stage. Writers keep original PAA wording (Google's phrasing wins) with 20-60w extractive answers; the lint measures alignment on the DRAFT.
allowed-tools: [Read, Write, Edit, Bash]
---

# PAA Answer Writer (v3.35 — validator-backed)

> **History (Rule 6):** from v5.0 to v3.34 the ">=60% from research.paa" contract
> lived only in prose, and `outline.faq.paa_alignment_pct` was a self-reported
> estimate validated by NOTHING. The contract is now measured on the draft.

## Why this still matters in 2026

PAA prevalence GREW through 2025 (+34.7% US mobile, seoClarity) and PAA co-occurs
with AI Overviews on ~90% of AIO SERPs (Semrush) — one of the few features AIO does
not displace. PAA-aligned Q&A feeds both the PAA box and AI-search answers. Full
evidence: `references/seo/serp-feature-value-2026.md` §2.

## The executor (this is what actually runs)

```bash
python -m scripts.lint.paa_alignment_check --workspace {task_id} --json
```

Wired as the mandatory **`paa-alignment-check`** stage (after keyword-density-check)
+ a mandatory `paa_alignment` pre-publish gate (computed FRESH on the current draft).

**Gate contract (honest about supply):**
- `required_matches = min(ceil(0.60 × faq_count), paa_count)` — a thin harvest can
  never demand more matches than it offers.
- No-op PASS when `research.paa` has < 3 entries or the draft has no FAQ section
  (mandatory_sections owns FAQ presence).
- Matching = normalized token overlap (Jaccard ≥ 0.5) or containment — tolerant of
  minor rephrasing, so keeping ORIGINAL PAA wording always matches.

## Writer rules (unchanged, now enforceable)

- ✅ Keep original PAA wording (Google's own phrasing wins ranking + extraction)
- ❌ Don't paraphrase / rewrite / change capitalization / add "?" PAA didn't have
- Answers: direct answer in the first sentence, 28-45 words target (lint warns
  outside the 20-60 extraction window — advisory, not blocking)
- Each answer: ≥1 specific data point OR clear direct claim, `[claim:*]`-marked

## Repair route on FAIL

The lint's `unmatched_questions[]` lists exactly which FAQ items to swap; replace
them with entries from `research.json :: paa[]` verbatim, then re-run the lint.

## See also
- `references/seo/serp-feature-value-2026.md` §2 (evidence)
- `references/seo/seo-checklist-2026.md` (G5)
