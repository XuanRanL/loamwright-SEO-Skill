# 47 Entity Signals

> DESIGN REFERENCE ONLY (2026-08-12 wiring audit): its named consumers — the `entity-extractor` agent and `subskills/cross-cutting/entity-optimizer/` — are both PARKED/not wired, so nothing currently maintains `memory/entities/{id}.md` from this spec.
>
> Each entity has up to 47 signals across 5 categories. Progressive sedimentation (Wiki Phase 1/2/3) per mention count.

---

## Categories overview

| Category | Signals | Phase introduced |
|---|---|---|
| 1. Identity | 7 | Phase 1 (first mention) |
| 2. Description | 6 | Phase 1-2 |
| 3. Relationships | 8 | Phase 2 |
| 4. Authority | 10 | Phase 2 |
| 5. Recognition status | 9 | Phase 3 |
| 6. Tracking | 7 | Phase 3 |
| **Total** | **47** | |

---

## Category 1: Identity (Phase 1 — 7 signals)

Captured on first mention.

1. **entity_id** — kebab-case slug (e.g., `gloomis`, `openai`, `featured-snippet`)
2. **name** — canonical name as it appears in our content
3. **aliases** — alternative spellings, abbreviations, former names
4. **type** — Organization / Person / Product / Place / Concept / Event
5. **canonical_url** — official homepage / Wikipedia / Wikidata
6. **first_seen** — ISO date of first mention in our content
7. **first_seen_article** — URL of article where first mentioned

---

## Category 2: Description (Phase 1-2 — 6 signals)

8. **description** — 1-2 sentence definitive statement
9. **founded_year** — for Organizations; can be N/A for Concepts
10. **headquarters** — for Organizations; geographic
11. **industry** — for Organizations / Products
12. **etymology** — for Concepts; when/how the term emerged
13. **first_mainstream_use** — for Concepts; when it went mainstream

---

## Category 3: Relationships (Phase 2 — 8 signals)

14. **sameAs** — Wikipedia, Wikidata, LinkedIn, Crunchbase URLs
15. **parent_entity** — for Products (parent company); for Subsidiaries (parent org)
16. **subsidiaries** — for parent companies
17. **related_entities** — IDs of competing or complementary entities
18. **competitors** — direct competitors (for competitive analysis)
19. **partnerships** — known partnerships
20. **acquisitions** — for companies that have acquired or been acquired
21. **person_associations** — key people associated (founders, executives)

---

## Category 4: Authority (Phase 2 — 10 signals)

22. **wikipedia_url** — if Wikipedia entry exists
23. **wikidata_qid** — Wikidata identifier (e.g., Q1234567)
24. **schema_org_type** — formal Schema.org type
25. **domain_rating** — Ahrefs DR or similar (for Organizations)
26. **referring_domains_count** — backlink profile size
27. **funding_total** — for startups (signal of authority/trust)
28. **employee_count** — Organization size
29. **awards** — recognized industry awards / mentions
30. **media_mentions** — references in Tier-1 publications
31. **conferences_spoken** — for Persons; speaker history

---

## Category 5: AI Engine Recognition Status (Phase 3 — 9 signals)

Per `ai_search_probe.py`, tracked per engine:

32. **chatgpt_resolution** — recognized / partial / unrecognized / confused
33. **chatgpt_last_probed** — ISO date
34. **perplexity_resolution** — recognized / partial / unrecognized / confused
35. **perplexity_last_probed** — ISO date
36. **claude_resolution** — recognized / partial / unrecognized / confused
37. **claude_last_probed** — ISO date
38. **gemini_resolution** — recognized / partial / unrecognized / confused
39. **gemini_last_probed** — ISO date
40. **overall_resolution_score** — weighted average across engines

---

## Category 6: Tracking (Phase 3 — 7 signals)

41. **mention_count** — total mentions across all our content
42. **citation_count_30d** — backlink citations / mentions in last 30 days
43. **citation_count_90d** — last 90 days
44. **content_articles** — array of our article URLs mentioning this entity
45. **last_mentioned** — ISO date of most recent mention
46. **factual_errors_log** — array of error events (when AI engines got facts wrong)
47. **last_updated** — when this entity record was last updated

---

## Phase progression rules

### Phase 1 (1-2 mentions)
Required signals: 1-7 (Identity)
Optional: 8 (Description)
Storage: 200-500 words

### Phase 2 (3-9 mentions)
Required signals: 1-21 (Identity + Description + Relationships)
Optional: 22-31 (Authority partial)
Trigger AI probe: NO (still too sparse to justify cost)
Storage: 500-1500 words

### Phase 3 (10+ mentions)
Required signals: 1-47 (all)
Trigger AI probe: YES (weekly for Phase 3 entities)
Storage: 1500-3000 words
Wiki-style detail expected

---

## Example: Phase 3 entity record

```markdown
---
entity_id: gloomis
entity_type: Organization
name: G.Loomis
aliases: ["G. Loomis", "GLoomis", "G-Loomis"]
canonical_url: https://www.gloomis.com/
first_seen: 2025-12-03
first_seen_article: https://example.com/post-1
mention_count: 27
phase: 3
last_updated: 2026-05-19
---

# G.Loomis (Organization)

## Identity

**Founded**: 1982
**Headquarters**: Woodland, Washington, USA
**Industry**: Fishing rod manufacturing
**Parent**: Shimano Inc. (acquired 1997)

## Description

G.Loomis is an American fishing rod manufacturer specializing in
high-end graphite composite rods. The company was founded by Gary Loomis
in 1982 and acquired by Shimano in 1997. G.Loomis is recognized for
proprietary materials and craftsmanship, particularly in their NRX
and NRX+ series.

## Relationships

- **sameAs**:
  - https://en.wikipedia.org/wiki/G.Loomis
  - https://www.wikidata.org/wiki/Q5519028 (Q5519028)
  - https://www.crunchbase.com/organization/g-loomis
- **parent_entity**: Shimano Inc. (entity_id: shimano)
- **competitors**:
  - St. Croix Rods (entity_id: st-croix-rods)
  - Sage Manufacturing (entity_id: sage)
  - Orvis Company (entity_id: orvis)
- **person_associations**: Gary Loomis (founder)

## Authority

- Wikipedia: Yes (medium-quality article)
- Wikidata QID: Q5519028
- Schema.org type: Organization
- Domain rating: 67 (Ahrefs)
- Referring domains: 4,200
- Employee count: 100-500 estimated
- Awards: ICAST Awards 2018, 2021, 2024

## AI Engine Recognition Status

| Engine | Status | Last Probed |
|---|---|---|
| ChatGPT | recognized | 2026-05-19 |
| Perplexity | recognized | 2026-05-19 |
| Claude | partial (mixed Q&A) | 2026-05-12 |
| Gemini | recognized | 2026-05-19 |

**Overall resolution score**: 0.85 / 1.0

## Tracking

- mention_count: 27
- citation_count_30d: 156 (mentions across web)
- last_mentioned: 2026-05-18 (article: ...)
- factual_errors_log:
  - 2026-04-02: ChatGPT confused G.Loomis with St. Croix Rods on "founded year" query
```

---

## How entities are used downstream

1. **schema-generator** uses entity data to build accurate Schema.org markup
2. **fact-checker** verifies claims against entity facts
3. **internal-linker** suggests links to entity-pages (if we have them)
4. **ai-visibility-tracker** uses Phase 3 entities for weekly probes
5. **entity-optimizer** drives Wikipedia/Wikidata submission campaigns
