---
name: local-city-page
description: City-level local-SEO page for "[keyword] [city]" queries. 2400-3000 words (more focused than state pillar). Supports both Pattern A (service_area) and Pattern B (spatial_coverage). Sterling Sky 80/20 with 4 unique-per-city signal categories. Use when state.brief.local_mode=true AND location_anchor.type='city'. Industry-agnostic.
allowed-tools: []
disable-model-invocation: true
user-invocable: false
---

# Local City Page Template

> A focused page targeting "[keyword] [city]" queries. Sister to `local-state-pillar.md` — same dual-pattern (service_area / spatial_coverage) architecture, but tighter scope (single city + adjacent neighborhoods, not multi-city). 

## When to use this template

The format-selector picks this when:
- `state.brief.local_mode == true`
- `state.brief.location_anchor.type == "city"`
- The project has either Pattern A or Pattern B configured

If the location anchor is a state (not city), use `local-state-pillar.md` instead.

> **Global scope (v3.40.0):** the city may be ANYWHERE in the world (Toronto,
> Manchester, Shenzhen, Sydney — `location_anchor.country` carries the ISO2
> code). Swap the US-flavored data-source examples for the market's own
> (US Census ACS → Statistics Canada / ONS / local equivalents) and write in
> the market's locale (`state.brief.target_market_locale`, e.g. en-CA / en-GB).
If the location anchor is a region (PNW, DMV, Bay Area), use `local-state-pillar.md` with multi-state framing.

## Word budget

2400-3000 words (excluding References). Tighter than state pillar because the geographic scope is narrower — single city + adjacent metro, not statewide. Citation-density target ≥1 per 300 words = ~8 citations.

## Schema pattern — same dual choice as state pillar

| Project archetype | local_article_pattern | Schema emitted |
|---|---|---|
| A / B / C | `service_area` | `Service.areaServed: City + containedInPlace: State` + LocalBusiness parent |
| D / E | `spatial_coverage` | `Article.spatialCoverage: Place(city) + about + mentions(local entities)` (Wirecutter) |

**City-specific note**: When emitting `Service.areaServed` for a city, ALSO include `containedInPlace: <state>` per Schema.org best practice — Google's parser uses this to relate city schemas to state-level local pack results.

---

## Sterling Sky 80/20 — city version

≥20% of body content unique-per-city. Same 4 categories as state pillar, scoped to city granularity:

| Category | City-scoped examples |
|---|---|
| **Local programs / incentives** | City utility programs (e.g. Xcel Denver), city tax breaks, municipal regulations, county-level licensing |
| **Local case studies / references** | Named clients in {city} or its suburbs, local press coverage from city-level outlets (Westword for Denver, BostInno for Boston, etc.) |
| **Local landmarks / neighborhood signals** | Neighborhoods (Capitol Hill, Back Bay, Brickell), highway corridors (I-25, Mass Pike), nicknames (the Mile-High City, the Hub), local employers / institutions |
| **Local pricing / logistics / market data** | City-average pricing, lead time from warehouse to city, city demographics (US Census ACS), city-specific market size |

**Floor**: ≥1 from each category. `local_uniqueness_check.py` enforces.

**City-vs-state trap**: Don't pad city pages with state-level content. "Colorado has rebates" is for the state pillar; this city page needs "Denver buyers can stack the statewide Xcel rebate with the city's PACE-style energy-loan program" — city-level specifics.

---

## Canonical H2 skeleton (11 H2s)

Shorter than state pillar — focused on a single city's specifics.

| # | H2 | Block type | Word budget |
|---|---|---|---|
| 1 | Abstract | (mandatory) | 180 |
| 2 | Key Takeaways | (mandatory) | 110 |
| 3 | Table of Contents | (mandatory, auto) | 90 |
| 4 | What [primary_keyword] Means for {CITY} Buyers | U+B mix | 300 |
| 5 | {CITY} Market Snapshot | **U** (signals 3+4 — demographics, neighborhoods) | 350 |
| 6 | The Core Factors / Specs That Matter | B | 350 |
| 7 | {CITY}-Specific Incentives + Regulations | **U** (signals 1) | 400 |
| 8 | Real {CITY} Case Examples + Customer Voice | **U** (signals 2) | 300 |
| 9 | Vetting Checklist for {CITY} Buyers | B+U mix | 200 |
| 10 | Frequently Asked Questions | (mandatory) | 600 |
| 11 | Conclusion + References | (mandatory) | 200 + 280 |

Total: ~3,360 words including References. Adjust per outline.

---

## Writer instructions — city-specific overlays vs state pillar

Same general rules as state pillar (sibling-territory avoidance, schema-pattern matching) PLUS:

1. **Embed location_anchor.containing_state alongside the city**: H1 should read "[keyword] in {City}, {ST}" (e.g. "1000W LED grow lights in Denver, CO") — the state qualifier disambiguates against same-named cities (Portland OR vs ME) AND helps Google's local-pack parser tie the article to the state-level entity.

2. **Reference at least 2 neighborhoods or sub-areas**: Don't write only "Denver" — write "Denver Tech Center", "Boulder corridor", "north metro" — this signals local expertise and earns 80/20 credit.

3. **Cite city-level sources where available**: 
   - Local newspaper (Westword for Denver, Boston Globe Metro, AZCentral for Phoenix)
   - City government data (city department of public works, city utility commission)
   - Chamber of Commerce or city business association
   At least 2 References entries should be city-level sources. The remaining 6-8 entries can be national/federal authorities.

4. **Avoid state-level padding**: If 50%+ of your H2s are statewide content, you're writing the wrong template — switch to state pillar. City pages should be city-first.

5. **Wirecutter framing for archetype D/E**: Same as state pillar — never claim "we serve {city}" if you're national ecommerce. Use "the {city} market", "{city} buyers", "what {city} customers should know".

---

## File output frontmatter

```yaml
---
title: "[primary_keyword] in [City], [State]: [Angle]"
slug: <kebab-case>
stage: writer
task_id: <task_id>
project_slug: <slug>
primary_keyword: "[primary_keyword] [City]"
target_locale: en-US
word_count_target: 2700
format: local-city-page
local_mode: true
location_anchor_canonical: <CITY_NAME>
location_anchor_state: <STATE_ABBREV>
local_article_pattern: <service_area | spatial_coverage>
generated_at: <ISO_DATE>
---
```

## See also

- `templates/local-state-pillar.md` — sibling for state-level queries; share the 80/20 framework and schema-pattern choice
- `references/local/industry-to-schema-mapping.md` — schema decision tree
- `references/local/sterling-sky-80-20-rule.md` — 80/20 unique-per-locality rules
- `scripts/research/_detect_local_intent.py` — keyword → location_anchor detection (handles ambiguous city names like Portland OR vs ME)
- `scripts/lint/local_uniqueness_check.py` — Sterling Sky 80/20 enforcement (Stage D)
