# Internal Linking Formulas

Internal link density rules. Used by `agents/linker.md` + `scripts/optimize/cross_article_linker.py`.

## Density by word count

| Word count | Internal links target | Min | Max |
|---|---|---|---|
| <1000 (short) | 3-5 | 2 | 6 |
| 1000-2000 | 5-7 | 4 | 9 |
| 2000-3000 | 7-10 | 5 | 12 |
| 3000-4000 | 10-15 | 8 | 18 |
| 4000-6000 (pillar) | 15-25 | 12 | 30 |
| 6000+ | 20-35 | 15 | 40 |

Above max = link spam (Google penalty risk). Below min = orphan article (no spoke-pillar benefit).

## Distribution

For an article with N internal links:

- 30% to **pillar pages** (broad authority transfer)
- 40% to **spoke / cluster siblings** (intra-cluster reinforcement)
- 20% to **adjacent cluster spokes** (semantic bridge)
- 10% to **glossary / definition pages** (entity reinforcement)

## Anchor text rules

### Vary anchor text (Google's spam detection)
- Same anchor text >3 times = anchor-text manipulation signal
- For target X, use 2-4 variant anchors:
  - Exact: "fishing rod"
  - Variant 1: "the fishing rod"
  - Variant 2: "rod for fishing"
  - Branded: "G.Loomis NRX+ rod"

### Avoid generic anchors
- ❌ "click here", "read more", "learn more"
- ❌ "this article", "this page"
- ✅ "fishing rod selection guide"
- ✅ "saltwater rod comparison"

### Anchor length
- 2-7 words ideal
- 1 word = too vague (often a single noun)
- 8+ words = looks like a sentence link

## Pillar-spoke linking pattern

### Pillar (hub) article
- Down-links to EVERY spoke in its cluster
- Anchor uses spoke's primary keyword
- Distributed across body (not all in conclusion)

### Spoke article
- Up-link to pillar (anchor: pillar's primary keyword)
- Cross-links to 2-3 cluster siblings (related spokes)
- Optional: 0-1 link to adjacent-cluster spoke

## Section placement

Distribute links across sections (don't bunch):

```
Article structure → Link distribution
─────────────────────────────────────
Intro (5%)         → 1-2 links (rare; only critical)
H2 #1 (15-20%)     → 2-3 links
H2 #2 (15-20%)     → 2-3 links
H2 #3 (15-20%)     → 2-3 links
H2 #4 (15-20%)     → 2-3 links
H2 #5 (10-15%)     → 1-2 links
FAQ section        → 1-2 links (to glossary)
Conclusion         → 0-1 link (avoid distracting CTA exit)
```

## Where NOT to link

- ❌ Headings (sacred — never)
- ❌ Citation Capsule self-contained blocks
- ❌ References section (those are EXTERNAL citations, not internal links)
- ❌ Author bio (already linked via Schema.org Person.url)
- ❌ Above-the-fold call-to-action area
- ❌ Image alt text (alt text is for accessibility, not SEO link juice)

## Frequency caps

- **Per-paragraph cap**: 1 internal link per sentence; 2 per paragraph max
- **Per-section cap**: 3-4 internal links per H2 section max
- **Density cap**: 1 internal link per 100 words avg (sustainable across 100-article portfolios)

## Anchor variety tracking

Across an entire portfolio, track anchor text frequency:

```
Target URL: /guide/fishing-rods
Anchors used (last 30 articles linking here):
  - "fishing rods" (8x)            ← exact-match dominant
  - "fishing rod guide" (4x)        ← good variant
  - "rod selection" (3x)            ← good variant
  - "G.Loomis NRX+" (2x)            ← branded
  - "this guide" (1x)               ← generic; minimize
```

If exact-match >40%, force variation in next article.

## Cross-article linker algorithm

`scripts/optimize/cross_article_linker.py` flow:

```
1. Read all published articles in portfolio
2. Build TF-IDF vectors per article
3. For each article pair, compute cosine similarity
4. Apply boosts:
   - +0.30 pillar-spoke relationship
   - +0.20 definition-target reference
5. Threshold filter (default ≥0.5)
6. For each candidate link, find natural anchor location in source body
7. Generate suggestions JSON (human reviews before applying)
```

## Tracking + maintenance

Update `internal-links-map.md` (at project root) whenever:
- New article publishes
- Existing article's slug changes
- Pillar-spoke relationship reorganizes

The map serves as a single source of truth for `agents/linker.md`.

## Quality signal: orphan rate

Healthy portfolio: 0-5% orphan articles (no incoming internal links).
Warning: 5-15% orphan rate.
Critical: >15% orphan rate.

Run `cross_article_linker.py` quarterly to identify orphans and suggest fixes.

## See also

- `agents/linker.md` — the per-article linker
- `scripts/optimize/cross_article_linker.py` — portfolio-scope orchestrator
- `subskills/optimize/internal-linker/SKILL.md` — per-article skill
