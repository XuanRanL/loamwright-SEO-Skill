---
name: local-state-pillar
description: State-level local-SEO pillar for "[keyword] [state]" queries. 3000-3200 words. Supports both Pattern A (service_area — true geographic service) and Pattern B (spatial_coverage — Wirecutter, national business writing about the state) via conditional schema. Enforces Sterling Sky 80/20 (≥20% unique-per-state content across 4 categories). Use when state.brief.local_mode=true AND location_anchor.type='state'. Industry-agnostic.
allowed-tools: []
disable-model-invocation: true
user-invocable: false
---

# Local State Pillar Template

> A pillar-page-class article that targets "[keyword] [state]" queries. Combines subject knowledge (~80% reusable across the cluster) with state-specific signals (~20% unique per state) per Sterling Sky's reverse-engineering of Google's 2025-12-10 doorway policy.

## When to use this template

The format-selector picks this when:
- `state.brief.local_mode == true`
- `state.brief.location_anchor.type == "state"`
- The query expresses informational/commercial intent (not pure transactional like "buy X in Y")
- The project has either Pattern A or Pattern B configured in `business-context.json :: location.local_article_pattern`

If the location anchor is a city (not state), use `local-city-page.md` instead.

> **Global scope (v3.40.0):** "state" means ANY first-order region — a US state,
> a Canadian province (Ontario), a Chinese province (Guangdong), an Australian
> state (Queensland) — and `location_anchor.type == "country"` routes here too
> (country-market pillar). Substitute the region's own institutions for the
> US-flavored examples below (utility rebates → provincial/national programs,
> state licensing → the local regulator), and write in the market's locale
> (`state.brief.target_market_locale`, e.g. en-CA for Ontario).
If the project archetype is A/B/C and the query is hyper-local single-city, prefer `local-city-page.md`.

## Word budget

3000-3200 words (excluding References). Below 3000 the pillar feels thin; above 3500 it dilutes AIO citation density. Citation-density target ≥1 citation per 350 words = ~8-9 citations.

## Schema pattern — chosen automatically by schema-generator

| Project archetype | local_article_pattern | Schema emitted |
|---|---|---|
| A / B / C | `service_area` | `Service.areaServed: <state>` + LocalBusiness parent |
| D / E | `spatial_coverage` | `Article.spatialCoverage + about + mentions` (Wirecutter) |

The writer does NOT decide this; the schema-generator subskill reads `business-context.json :: location.local_article_pattern` and emits the correct schema. Writer's job is to make the **content** consistent with the chosen pattern (see Sterling Sky 80/20 rules below).

---

## Sterling Sky 80/20 enforcement

Per `references/local/sterling-sky-80-20-rule.md` (and Google's 2025-12-10 doorway spam policy update), ≥20% of body content must be unique-per-state and fall into one of 4 categories:

| Category | Examples (industry-agnostic) | Where to embed |
|---|---|---|
| **Local programs / incentives** | State utility rebates, tax credits, state regulations, state licensing requirements | Body sections 3-5 (after the generic subject explainer) |
| **Local case studies / customer references** | "A [verticals] facility in {state} reported...", state-specific testimonials, local press coverage | Body sections 5-7 |
| **Local landmarks / regional signals** | State capital, top metros, regional language ("the I-25 corridor", "the Bay Area"), state nickname | Abstract + intro + transitions |
| **Local pricing / logistics / market data** | State-average pricing, lead time from warehouse to state, kWh prices, state-specific demographics, market size | Body sections 6-7 + FAQ |

**Floor**: at least 1 item from each of the 4 categories MUST appear in body. The `local_uniqueness_check.py` lint enforces this at the quality-gate stage.

**Genuine vs fake unique-per-state content**:
- ✅ "Colorado's Xcel Energy offers $0.80-$1.00/W rebates on DLC-listed LED fixtures via the One-Stop Trade Ally program (CO-program code 23-529)." — specific, citable, verifiable
- ❌ "Colorado has unique needs for LED lighting solutions." — generic, swappable with any state name, doorway-pattern

Anti-pattern: writing the same article 50 times with only the state name and a generic "the {state} market is unique" sentence changed. Google's 2025-08 + 2025-12 spam updates explicitly target this. The publisher's `local_doorway_uniqueness.py` lint will hard-veto.

---

## Required mandatory sections (project may override via business-context.json :: mandatory_sections)

Default for commercial / buyer-guide / YMYL projects (the canonical 6):

1. **`## Abstract`** (150-280w, two paragraphs: thesis + persona + how article is organized; state name in the thesis)
2. **`## Key Takeaways`** (4-7 bullets, each ≤20w, format `- **Lead clause** rest of sentence.`; at least 2 bullets must reference state-specific data)
3. **`## Table of Contents`** (anchored ordered list linking every H2 in document order)
4. **`## Frequently Asked Questions`** (6-10 PAA-aligned Q&A; ≥3 questions reference the state by name)
5. **`## Conclusion`** (100-250w; restates state thesis. On cta-enabled projects (business-context.cta.enabled) write NO prose CTA — the mandatory cta-injection stage appends the styled CTA module (v3.35.1, kills the double-CTA pressure pattern); only projects WITHOUT a cta config keep the legacy soft CTA to /contact/ or /shop/)
6. **`## References`** (8-10 APA-7 entries; ≥2 entries must be state-specific authoritative sources)

Plus the article signature (markdown italic, last paragraph in body) per `references/style/markdown-authoring-conventions.md` Rule 2.

---

## Canonical H2 skeleton (13 H2s)

Adjust per `outline-architect` decisions. The skeleton interleaves boilerplate (B) with unique-per-state (U) sections to satisfy 80/20.

| # | H2 | Block type | Word budget |
|---|---|---|---|
| 1 | Abstract | (mandatory) | 200 |
| 2 | Key Takeaways | (mandatory) | 130 |
| 3 | Table of Contents | (mandatory, auto) | 110 |
| 4 | What "[primary_keyword]" Actually Means | B (boilerplate; subject 101) | 350 |
| 5 | Why {STATE} Matters for [subject] | **U** (state intro + signals 3+4) | 350 |
| 6 | The Specs / Factors That Matter | B | 400 |
| 7 | {STATE} Incentives, Rebates, and Regulations | **U** (signals 1) | 500 |
| 8 | Real-World {STATE} Case Examples | **U** (signals 2) | 400 |
| 9 | Local Pricing, Lead Time, and Logistics | **U** (signals 4) | 350 |
| 10 | Vetting Checklist for {STATE} Buyers | B+U mix | 250 |
| 11 | Frequently Asked Questions | (mandatory) | 700 |
| 12 | Conclusion | (mandatory) | 200 |
| 13 | References | (mandatory) | 280 |

Total: ~4,220 words including References. Adjust ±15% per outline.

---

## Writer instructions

When dispatched with `local_mode=true` + `location_anchor.type=state`:

1. **Embed location_anchor.name_full prominently**: H1 title MUST include the state. ≥3 H2s should reference it directly. Body should mention it 10+ times naturally (not stuffed). The `geo_anchor_density` gate enforces this.

2. **Avoid sibling-territory framing**: Do NOT write content that would equally fit a different state. If you say "the local market is competitive", that sentence applies to any state and earns zero 80/20 credit. Replace with specifics: "the {state} cannabis cultivation market has 2,815 licensed cultivators (per state department records 2024) — 4× the per-capita rate of California."

3. **Cite state-specific sources**: ≥2 References entries must be state-government, state utility, state trade association, or peer-reviewed studies conducted in {state}. Generic federal sources (DOE, EPA) count for the boilerplate ≥6 entries but don't fulfill the state-specific minimum.

4. **Avoid Service.areaServed framing if archetype D/E**: For national-ecommerce / SaaS projects, never write "we serve {state}" or "our {state} customers" — this contradicts the schema-generator's spatial_coverage emission and creates an E-E-A-T misleading-data signal. Use Wirecutter framing instead: "the {state} market", "{state}'s buyer profile", "what {state} buyers need to know".

5. **Avoid spatial_coverage framing if archetype A/B/C**: For service-area businesses, DO write in service voice: "we serve {state} customers", "our {state} crew", "our {state} delivery zones". The schema-generator's areaServed declaration matches this content.

---

## File output

Write the draft to `memory/workspace/{task}/draft.md` with this frontmatter:

```yaml
---
title: "[primary_keyword] in [State]: [Angle]"
slug: <kebab-case>
stage: writer
task_id: <task_id>
project_slug: <slug>
primary_keyword: "[primary_keyword] [State]"
target_locale: en-US
word_count_target: 3200
format: local-state-pillar
local_mode: true
location_anchor_canonical: <STATE_ABBREV>
local_article_pattern: <service_area | spatial_coverage>
generated_at: <ISO_DATE>
---
```

The pipeline downstream reads `local_mode` + `location_anchor_canonical` + `local_article_pattern` from the frontmatter to choose the right verify_post checks and schema emission.

## See also

- `references/local/industry-to-schema-mapping.md` — schema decision tree
- `references/local/sterling-sky-80-20-rule.md` — 80/20 unique-per-locality rules
- `references/local/2026-local-seo-best-practices.md` — Whitespark / Sterling Sky / Moz 2026 consolidated
- `templates/local-city-page.md` — sibling template for city-level queries
- `scripts/research/_detect_local_intent.py` — keyword → location_anchor detection
- `scripts/lint/local_uniqueness_check.py` — Sterling Sky 80/20 enforcement (Stage D)
