---
name: geo-content-optimizer
description: Apply 6 GEO techniques + per-engine weighted optimization. Citation Capsules, Information Gain Markers, entity richness, Q&A structure, fact density, FAQPage schema.
allowed-tools: [Read, Write, Edit, Bash]
---

# GEO Content Optimizer

Per `references/geo/ai-engine-matrix.md` (TODO), apply per-engine optimization:

| Engine | Weight emphasis |
|---|---|
| Google AIO | freshness 30%, authority 25%, structure 20% |
| ChatGPT | authority 30%, citations 25%, fact-density 15% |
| Perplexity | citations 35%, authority 20%, structure 20% |
| Claude | authority 30%, structure 25%, fact-density 15% |
| Gemini | freshness 25%, authority 25%, structure 20% |

## 6 GEO techniques (always applied)
1. 25-50 word definitions per entity
2. Citation Capsules per H2 (already in citation-capsule-builder)
3. Authority signals (external schema/Wikipedia links)
4. Q&A structure (FAQ section)
5. Fact density (≥1 stat per 200 words)
6. FAQPage schema (in schema-generator)

## Workflow
1. Verify each technique applied via lints
2. Per `state.brief.target_surfaces`, emphasize matching engine's weights
3. Run `scripts.validate.cite_scorer` to confirm GEO compliance
4. If score <80, repair via targeted Edit

## See also
- `references/geo/cite-framework-40.md`
- `references/seo/citation-capsules-princeton.md`
