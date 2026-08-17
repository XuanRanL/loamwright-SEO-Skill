# Listicle Template

> Format ID: `listicle`. Wix 2026.3 data: 40.86% AI citation rate on commercial queries.
> Used by `outline-architect` as the H2 skeleton when `format_id == "listicle"`.

## Default structure

```
{Title with number + Power Word + primary keyword}

## TL;DR (40-60w in first 540 words)
Quick answer: top pick is X, runner-up Y, budget pick Z. Methodology: tested N items.

## Abstract (120-180w)
3rd-person framing. What was tested, when, by whom, why.

## Key Takeaways (5-7 bullets)
- The #1 winner is X (specific reason)
- For under $Y, Z is the clear choice
- Most overrated category leader: K
- Common mistake: M
- ... (each <20 words, actionable)

## Table of Contents
Auto-generated from H2 anchors.

## Why these {item} matter / Selection criteria (~400w)
Establish stakes. Cite SERP/industry data. Define what we tested.
Include 1 markdown table here (the criteria + weights).

## How we tested {item} / Methodology (~500w)
E-E-A-T signal. Tools used, test conditions, time period.
Include real first-hand experience (plain prose).
Citation Capsule per H2 here.

## #1 {Top Pick Name} (~350-400w)
### Best for: {persona}
### Why it made the list (~100w with specific data)
### Pros (3-5 bullets) / Cons (2-3 bullets)
### Specs (markdown table)
### Bottom line (Citation Capsule here)

## #2 ... #N (same pattern, 250-350w each)

## How {item} have evolved in 2026 (~250w)
original data or original analysis, in plain prose.
Trend analysis. What's different vs 2024-25.

## Who shouldn't use {category} at all (~150w)
Anti-pattern section. Counterintuitive but boosts trust.

## FAQ (5-10 Q&A, ≥60% from research.paa)
### {PAA question 1}
{28-45 word direct answer, then 1 sentence context}

### {PAA question 2}
...

## Conclusion / Verdict (~200w)
Restate top pick + why. No "in conclusion". End with specific action.

## References
APA 7, ≤10 entries, all link-resolvable.
```

## Word budget allocation (6000w target)

| Section | Words | % |
|---|---|---|
| TL;DR + Abstract + Takeaways | 350 | 6 |
| Why matters + Methodology | 900 | 15 |
| 10 items × 350w | 3500 | 58 |
| Evolution / anti-pattern | 400 | 7 |
| FAQ | 600 | 10 |
| Conclusion + References | 250 | 4 |
| **Total** | **6000** | 100 |

## Required modifiers (auto-applied)

- `tldr-first` ✓ (always for listicle)
- `citation-capsules-per-h2` ✓ (each item + Why matters + Methodology = 12 H2s with capsules)
- `mandatory-toc` ✓ (10+ H2s)
- `info-gain-prose` ✓ (≥2: original data in the methodology + real first-hand experience elsewhere, both in plain prose)

## Variant specifics

### Shortlist variant (8 list-section + each ≤10 word/sentence)
- Use when target = ChatGPT (AirOps +26.9% data)
- Replace 10-item structure with 8 ultra-concise sections
- Each item: 100-150 words max
- See `templates/shortlist-validation.md`

### Buyer's guide variant (more decision framework)
- Use when target_surfaces = ["google-aio", "shopping"]
- Add "Decision criteria worksheet" section
- More tables (5+ vs 3+)
- Closer to product-review for top picks
- See `templates/buyers-guide.md`

## Image slot allocation

- Cover: hero shot of category (16:9, top of article)
- Section 1: top product (#1, in real use)
- Section 2: methodology / behind-the-scenes
- Section 3: comparison shot OR closing roundup
- Slots 4-5 (the default `image_count` 6 → 5 inline slots; `scripts/_core/image_policy.py`): continue the subject pattern above with distinct, non-duplicative scenes for further key sections

## Common pitfalls (auto-rejected by quality gates)

- ❌ All 10 items same length (perfect/error alternation P26 — vary 200-400w)
- ❌ Each item starts "Best X for Y" (rule-of-three P10 — vary openings)
- ❌ No data in "Why matters" (Vague attributions P5)
- ❌ Generic conclusion (Generic positive conclusion P24)
- ❌ Em-dashes in any section
- ❌ "In today's fast-paced world" opener (Formulaic challenges P6)

## Schema additions

In addition to base Article schema, add:
- `ItemList` with each ranked item
- `Review` schema if products are reviewed (with AggregateRating)
- `FAQPage` schema for the FAQ block
