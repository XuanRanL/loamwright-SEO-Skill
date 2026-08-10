# MECE 8 Content Lanes

Every blog article fits one of 8 mutually-exclusive, collectively-exhaustive lanes. Used by `subskills/research/content-gap-analysis/` to ensure portfolio coverage and avoid cannibalization.

## The 8 lanes

| Lane | Intent | Formats that fit | Typical word range |
|---|---|---|---|
| 1. **Informational-broad** | "What is X?" general education | definition / pillar-page / encyclopedic / faq-knowledge | 1,500-6,500 |
| 2. **Informational-specific** | "How does X work?" deep mechanism | how-to-guide / data-research / opinion / multi-intent-hybrid | 2,000-5,000 |
| 3. **Commercial-investigation** | "Best X?" / "X vs Y" / "X for Y" buyer research | listicle / comparison / shortlist-validation / buyers-guide / product-review | 3,000-6,000 |
| 4. **Commercial-transactional** | "Buy X" / "X near me" purchase intent | product-page / template-resource / curated-roundup | 800-2,500 |
| 5. **Navigational-branded** | "Acme login" / "Acme pricing" brand lookup | brand-page / about-page (not blog content per se) | N/A |
| 6. **Local-geographic** | "X in Tokyo" / "Best X near me" location-specific | local-listicle / location-guide | 1,500-3,500 |
| 7. **Case-study / personal-story** | "How {company} achieved Y" / "I tried X" experiential | case-study / personal-story / interview | 2,000-5,500 |
| 8. **News-analytic / opinion** | "X just happened, here's what it means" current events | news-analysis / opinion / data-research | 800-3,500 |

## MECE properties

**Mutually exclusive**: each article must fit ONE lane, not two. If an article spans lanes, split it into two articles OR use the `multi-intent-hybrid` format explicitly.

**Collectively exhaustive**: every blog topic is coverable by one of these 8 lanes. There is no 9th lane (and adding one means we're re-architecting).

## Why this matters

- **Anti-cannibalization**: two articles in the same lane targeting the same keyword = cannibalization. Two articles in different lanes targeting the same keyword = synergy (different search intent).
- **Pillar-spoke structure**: pillar = lane 1; spokes = lanes 2-3 and sometimes 6-7
- **Portfolio balance**: healthy portfolios have all 8 lanes represented; bias toward lane 3 (commercial) without lane 7 (case-study) = low E-E-A-T signal

## Lane → format mapping (from blog-formats-2026.md)

```
Lane 1 (info-broad):     pillar-page / definition / encyclopedic / faq-knowledge / glossary-hub
Lane 2 (info-specific):  how-to-guide / data-research / opinion / problem-solution
Lane 3 (commercial-inv): listicle / comparison / shortlist-validation / buyers-guide / product-review / roundup
Lane 4 (commercial-tx):  template-resource / curated-roundup / level-guide / checklist
Lane 5 (navigational):   N/A (not blog content)
Lane 6 (local):          local listicle variant / location-aware how-to variant
Lane 7 (case-study):     case-study / personal-story / interview
Lane 8 (news-analytic):  news-analysis / opinion / data-research
```

## Detection algorithm

When given a keyword, classify into a lane:

```
1. Has "best" / "top" / "vs" / "review" / "comparison" → Lane 3
2. Starts with "what is" / "what are" → Lane 1
3. Starts with "how to" / "how do I" → Lane 2
4. Has "near me" / city/region name → Lane 6
5. Has "how {company} did X" / "X case study" → Lane 7
6. Has current year + topical keyword → Lane 8
7. Brand name dominant (>50% of phrase) → Lane 5
8. Default → Lane 2 (informational-specific)
```

## Portfolio audit thresholds

For a healthy site, lane distribution should look approximately:

| Lane | % of total articles (healthy) |
|---|---|
| 1 | 8-15% (pillars are infrequent but high-value) |
| 2 | 25-35% (how-to dominates info) |
| 3 | 25-35% (commercial is the commercial engine) |
| 4 | 5-10% (transactional rarely needs blog format) |
| 5 | (excluded from blog metrics) |
| 6 | 0-15% (location-dependent) |
| 7 | 5-15% (case-studies are scarce but high-trust) |
| 8 | 5-15% (news / opinion adds freshness) |

**Imbalanced signals**:
- Lane 3 >50% → over-commercial; add lane 1 + 7 for trust
- Lane 1 + 2 = 100% → no commercial content; conversion gap
- Lane 7 = 0% → no E-E-A-T showcase; hire / interview experts

## Anti-cannibalization rule

Two articles can target similar keywords IF they're in different lanes:

- `[lane 1] "What is content marketing"` + `[lane 3] "Best content marketing tools"` = OK
- `[lane 1] "What is SEO"` + `[lane 1] "Define SEO for beginners"` = CANNIBALIZATION (same lane, same intent)

`subskills/plan/topic-clustering/SKILL.md` enforces this via SERP overlap analysis (5+ shared top-10 URLs = same lane).

## Application in content gap analysis

When auditing portfolio gaps:

```bash
# Identify lanes with <5 articles
python -m scripts.research.research_competitor_gaps --site X --lane-breakdown
```

Then:
- If lane 1 has <3 pillars → build pillars
- If lane 7 has 0 case-studies → solicit interviews
- If lane 3 has 50% concentration → diversify

## See also

- `references/seo/blog-formats-2026.md` — 24 formats catalog
- `subskills/research/content-gap-analysis/SKILL.md`
- `subskills/plan/topic-clustering/SKILL.md` — cannibalization prevention
