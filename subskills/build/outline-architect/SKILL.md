---
name: outline-architect
description: Designs H2/H3 outline with explicit per-section word budgets, table placements (≥2 with one in front 50%), image/video slot markers, FAQ count, abstract seed, takeaways seeds, Citation Capsule requirement per H2. Loads format-specific template. Critical pre-build step. Use whenever building an article — after format + angle picked, before section-drafter parallel dispatch.
allowed-tools: [Read, Write, Bash]
---

# Outline Architect

Converts (format + angle + research) into a structured outline that section-drafter can parallelize across.

## HARD REQUIREMENT — every outline ends with References

Every outline this skill produces MUST include, as the final `sections[]` entry (preceded by "Further Reading" if a Further Reading section is desired):

```jsonc
// ... earlier content sections ...
{
  "index": N-2,
  "h2": "Further Reading",                  // OPTIONAL; if present, MUST come BEFORE References
  "word_budget": 100,
  "section_intent": "Internal links to companion pillars + 1-3 narrative external pointers",
  "citation_capsule_required": false
},
{
  "index": N-1,
  "h2": "References",                       // MANDATORY for every format
  "word_budget": 200,                       // accommodates 8-10 APA-7 entries
  "section_intent": "APA-7 numbered list of every external source cited in body; link-resolvable URLs/DOIs; ≥1 peer-reviewed when available",
  "needs_table": false,
  "image_slot": false,
  "citation_capsule_required": false,
  "is_references_block": true
}
```

The article signature paragraph is appended at publish time by `subskills/publish/wordpress-publisher/` from `projects/{slug}/CLAUDE.md` — it is NOT a section in the outline (it's a single `<hr />` + `<p class="article-signature">` after the References block).

The "Further Reading" prose paragraph is OPTIONAL. The "References" `<ol>` block is MANDATORY for every format — all 24 `templates/*.md` declare `## References` as the closer. An outline that omits References will fail downstream verification at the publish phase and trigger a forced rebuild — emit the section even if `citations.json` is empty at outline time (the build phase populates it).

## Inputs

- `state.brief.word_count_target`
- `angle.json` (format_id + title + persona + modifiers)
- `research.json` (paa, semantic_clusters, competitor_titles, content_gaps)
- `templates/{format_id}.md` (24 formats, each with skeleton structure)
- `references/seo/blog-formats-2026.md` (format-specific Body structure)

## Output

`workspace/{task_id}/outline.json` per `schemas/outline.schema.json`:

```json
{
  "abstract_seed": "After testing 23 rods over 87 trips, we ranked the top 10 fishing rods for 2026.",
  "tldr_seed": "The G.Loomis NRX+ is our top pick at $549. For tight budgets, Ugly Stik Elite at $35 punches above its weight.",
  "takeaways_seeds": [
    "Choose action based on lure weight, not species (saves $100 misbuy)",
    "Graphite vs fiberglass: 70/30 rule by use case",
    "Best Fishing Rods 2026: G.Loomis NRX+ overall winner",
    "Ugly Stik Elite wins under $50",
    "Avoid these 3 marketing tricks rod brands use"
  ],
  "sections": [
    {
      "index": 0,
      "h2": "Why fishing rod selection matters more than gear cost",
      "h3s": ["What changed in 2025-26", "How rod quality affects catch rate"],
      "word_budget": 450,
      "needs_table": false,
      "image_slot": true,
      "youtube_slot": false,
      "section_intent": "Establish stakes; hook reader; introduce testing methodology",
      "primary_keyword_density_target": 0.012,
      "is_featured_snippet_target": false,
      "citation_capsule_required": true
    },
    {
      "index": 1,
      "h2": "How we tested 23 rods (methodology)",
      "h3s": ["Test conditions", "Rating criteria", "Disqualifications"],
      "word_budget": 500,
      "needs_table": true,
      "image_slot": false,
      "section_intent": "E-E-A-T Experience signal; tabulate test criteria",
      "primary_keyword_density_target": 0.005,
      "citation_capsule_required": true
    },
    {
      "index": 2,
      "h2": "10 Best Fishing Rods for 2026 (ranked)",
      "h3s": ["#1 G.Loomis NRX+", "#2 St. Croix...", "#3...", "#10..."],
      "word_budget": 3500,
      "needs_table": true,
      "image_slot": true,
      "youtube_slot": false,
      "section_intent": "Core listicle body; product evaluation per item",
      "primary_keyword_density_target": 0.010
    },
    ... (more sections)
  ],
  "faq": {
    "count": 7,
    "seed_questions": [
      "What's the best fishing rod under $100?",
      "How do I choose between graphite and fiberglass?",
      "Is the G.Loomis NRX+ worth the price?",
      "What rod action should beginners use?",
      "How often should I replace my fishing rod?",
      "Does rod length matter for kayak fishing?",
      "Are budget rods (under $50) usable for saltwater?"
    ],
    "paa_alignment_pct": 0.71
  },
  "total_word_budget": 6200,
  "expected_h2_count": 8,
  "expected_table_count": 3,
  "expected_image_count": 6
}
```

> **PAA contract (v3.35):** `faq.paa_alignment_pct` is the outline's ESTIMATE only.
> The real ">=60% of FAQ from research.paa" contract is MEASURED ON THE DRAFT by the
> mandatory `paa-alignment-check` stage (`scripts/lint/paa_alignment_check.py`).
> Keep `seed_questions` in ORIGINAL PAA wording so the draft passes.

## Hard constraints

1. **Word budgets sum** to `[word_count_target × 0.95, word_count_target × 1.05]`
2. **Section count** between 4 and 15
3. **≥2 sections with `needs_table: true`**, with at least 1 in the FIRST HALF (sections[index] < total/2)
4. **FAQ count 5-15**, and **≥60% must come from research.paa**
5. **Per-section word_budget**: each between 150 and 2500
6. **citation_capsule_required: true** on every content section (excludes Abstract / ToC / References)
7. **image_slot: true** on exactly `state.brief.image_count − 1` sections (the cover is
   NOT an inline slot: `image_count` counts cover + inline images, so `image_count: 6`
   means exactly **5** sections carry `image_slot: true`). When the brief OMITS
   `image_count` (batch briefs are told to), the count is NOT a guess: it resolves to
   the default **6** via `scripts/_core/image_policy.py` — the dispatch prompt hands you
   the resolved number. Clarified 2026-07-06 after the old wording ("exactly image_count
   sections … cover doesn't count") read two ways and produced a 4-boolean outline for a
   4-image article that had to be hand-corrected; the worked example above was itself
   half-updated on 2026-08-17 (said 6 → **3**), proving the arithmetic must be spelled
   once, not per-layer.
8. **Featured Snippet target sections**: if `research.serp_features` contains `featured_snippet` OR `ai_overview`, mark 1-2 H2s with `is_featured_snippet_target: true` — consumed (v3.35) by the citation-capsule-builder stage, which gives those sections the most answer-first extractive capsule (FS and AIO select the same shape; the standalone featured-snippet-optimizer is retired). Do NOT emit `snippet_format` (deprecated orphan field).
9. **image slot kinds — decided in image-prompts.json, not here (contract updated
   2026-07-06 to match the executors)**: the per-section `image_slot: true` booleans in
   `sections[]` are the outline's ONLY required image contract; the image-prompt-designer
   assigns each slot `kind: "chart"` or `kind: "photo"` in `image-prompts.json`, which is
   the slot source of truth for chart-render, the photo pipeline, and the D4/D5
   placeholder lint. A top-level `image_slots[]` array is OPTIONAL legacy detail (no
   current producer emits it; the D2/D3 checks that read it are legacy no-ops kept for
   backward compatibility). Guidance for the designer handoff still applies: a slot whose
   section carries DATA (comparison, %, ranges, matrix, checklist) should become
   `kind: "chart"`; the cover is ALWAYS `kind: "photo"`. Use `kind: "chart"` when the slot illustrates DATA (a comparison, yield/uplift %, PPFD/DLI/CFM/efficacy numbers, a coverage map, a checklist, a verdict matrix, a spectrum) — these are rendered as real labeled charts (titles/axes/units) by `render_data_charts.py`, NOT as AI photos (which garble chart text). Use `kind: "photo"` for scenes. **The cover slot is ALWAYS `kind: "photo"`.** Prefer making a slot a chart when its section has `needs_table: true` and the data is genuinely chartable — a labeled chart out-informs a generic stock photo.
10. **Visual design components (v3.31)**: assign a `design_components: []` array to each CONTENT section per the format policy below, so no article ships as a wall of text. Evidence (Princeton GEO, NNG) says SUBSTANCE components (tables, cited-stat blocks, real quotations) out-perform decorative boxes, and over-design (many colored boxes, decorative pull-quotes) measurably hurts — so plan Tier-A first and use Tier-C sparingly. Rules:
   - Every content section gets ≥1 component appropriate to its role; the ARTICLE overall must plan **≥3 distinct component types**.
   - Any section assigned `comparison_table` MUST also have `needs_table: true` (keep them consistent with constraint 3).
   - Allowed values: `comparison_table | stat_grid | quotation | tldr_box | checklist | glossary | callout | pull_quote`. Full catalog + when-NOT-to: `references/style/visual-design-components.md`.
   - ⚠️ `tldr_box` on a SECTION means "answer-first opening paragraph", NOT a nested
     `## TL;DR` H2 — the article-level TL;DR box is auto-emitted by assemble.py from
     `tldr_seed`, and a section-level `## TL;DR` H2 empties the parent section and
     ships a duplicate `#tldr-2` anchor (v3.38.3; 2026-07-09 reviewer bounce). If a
     section is a featured-snippet/AIO target, prefer `is_featured_snippet_target: true`
     + a plain answer-first first paragraph over assigning `tldr_box` at all. Any other
     H2 component box a section carries (`## Glossary` / `## By the Numbers`) belongs at
     the section BOUNDARY (after all its H3s), never between H3s.
   - **Format policy:**
     - *pillar*: `comparison_table` on Types/Choosing (first-half), `stat_grid` on the mechanism/data section, `quotation` once, `glossary` on the "What is X" section, `checklist` on "How to get started".
     - *comparison/review*: 3 `comparison_table` (quick/pricing/feature), `quotation` on the Verdict.
     - *how-to/buyers-guide*: `checklist` as the spine, ≤2 `callout` (warnings) on failure-mode steps, 1 `comparison_table` spec.
     - *listicle/roundup*: a `comparison_table` or `stat_grid` per item cluster, ≤1 `callout` per top pick.
     - *weekly-digest*: `comparison_table` ("At a Glance"), `stat_grid` ("By the Numbers"), `callout` for opinion blocks.
     - *opinion*: 1 `quotation`, minimal boxes (highest over-design risk — do NOT stack callouts).

### Numeric single-source rule (v3.36.0, 2026-07-06)

Every NUMBER that appears in `abstract_seed` / `tldr_seed` / `takeaways_seeds` MUST be
copied verbatim from the section that owns it (the pricing table's ranges, the stat
section's percentages) — never re-derived or re-rounded while writing the seeds. The
2026-07-06 batch shipped one article whose pricing band was stated four different ways
(TL;DR $1,500-$10,000 vs table $1,000-$3,000-start vs FAQ $3,000-$50,000) because seeds
and sections each invented their own restatement. Parallel section writers receive the
seeds as context, so a seed-level drift REPLICATES into sections. Pick the owning
section, write its numbers once, and copy them character-for-character everywhere else
(the independent reviewer now runs an explicit cross-section numeric-consistency sweep
and will bounce drift back as repair work).

## Format-specific skeleton

Read `templates/{format_id}.md` (e.g. `templates/listicle.md`) for the structural skeleton:
- Listicle: Why these matter → Methodology → #1...#N → How we tested → FAQ → Conclusion
- How-to: Before you start → Step 1 → Step 2 → ... → Troubleshooting → FAQ
- Pillar: What is X → Types → How it works → Benefits/Drawbacks → Choosing → Future Trends → FAQ
- Comparison: Quick Comparison Table → Pricing → Feature-by-Feature → X strengths → Y strengths → Use Cases → When to Choose → Verdict
- (etc., per 24 formats)

The skeleton is the SCAFFOLD. Customize H2 titles based on `angle.title` and `research.competitor_titles` (avoid duplicating competitor H2s; find gaps).

## Allocation strategy

Given `word_count_target` and section count, distribute budgets per format:

For listicle (10 items, 6000w target):
- Intro/Why matters: ~450w (~7.5%)
- Methodology: ~500w (~8.3%)
- 10 items × ~350w = 3500w (~58%)
- Wrap-up/Verdict: ~400w (~6.7%)
- FAQ: ~700w (~11.7%)
- Conclusion: ~250w (~4.2%)
- Buffer: ~200w (~3.3%)

For pillar (8000w target):
- Each H2 700-1100w
- More H3s per H2
- Heavier FAQ section (10-15 questions)

For comparison (4000w target):
- Quick Comparison Table (~300w + table)
- Per-option deep sections ~600-800w each
- Feature comparison sections ~400w
- FAQ ~600w
- Verdict ~300w

## Handoff

`recommended_next_skill`: `section-drafter` (parallel N agents, one per H2)

## See also

- `templates/*.md` (24 format skeletons)
- `references/seo/blog-formats-2026.md` (catalog with structural recommendations)
- `schemas/outline.schema.json`
- `subskills/build/section-drafter/SKILL.md` (downstream)
