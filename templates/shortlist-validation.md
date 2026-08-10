# Shortlist Validation Template

> Format ID: `shortlist-validation`. Per AirOps 2026.4: +25.7% AI citation lift vs standard listicle.
> Used by `outline-architect` when `format_id == "shortlist-validation"`.

## Why this format wins for ChatGPT citations

Wix 2026.3 + AirOps 2026.4 data:
- 8 list items (NOT 10-15) — better ChatGPT extractability
- Sentences ≤10 words each — direct quotability
- Strict validation structure — AI engines extract verbatim

## Default structure

```
{N} Best {Category} for {Persona} ({Year})

## TL;DR (40-60w)
Top pick: X. Runner-up: Y. Budget: Z.

## How we picked (~300-400w)
Criteria + methodology. Crisp.

## #1: {Product/Service Name}
**Best for**: {specific persona}
**Why**: {one stat-backed reason in ≤10 words}
**Pros**: 3 bullets, each ≤10 words
**Cons**: 2 bullets, each ≤10 words
**Price**: ${X} ({comparison vs avg})
**Verdict**: ≤25 words

## #2 ... #8 (same structure, ≤150w each)

## How to choose (~400w decision framework)

## FAQ (5-7 PAA, each answer ≤45w)

## References (≤10 APA 7)
```

## Word budget (2200w target — TIGHT)

| Section | Words | % |
|---|---|---|
| TL;DR | 60 | 3 |
| How we picked | 350 | 16 |
| 8 items × 150w | 1200 | 55 |
| How to choose | 400 | 18 |
| FAQ | 200 | 9 |

**Total: ~2200w** — much shorter than standard listicle. Density over length.

## Required modifiers
- `tldr-first` ✓
- `citation-capsules-per-h2` ✓ (each item is mini-capsule)
- `mandatory-toc` ✓
- `featured-snippet-targets` ✓
- `info-gain-prose` ✓ ≥1

## Hard rules
1. **EXACTLY 8 items** (not 10, not 15; 8 is the ChatGPT sweet spot)
2. **Sentences ≤10 words** in item sections
3. Each item has Pros/Cons/Price/Verdict block
4. Total word count 2000-2500w (TIGHT — over 2500 loses the advantage)
5. No prose-heavy intros within items
6. Each item: one stat with source

## Schema additions
- `Article` base
- `ItemList` with 8 ListItems
- `Review` schema per item (optional)
- `FAQPage`

## Image slots
- Cover: 8-up grid OR hero
- Section 1-3: top 3 items in use

## When NOT to use
- Long-form deep dive needed → use listicle (10-item, 6000w)
- Comparison-heavy → use comparison template
- Single product → use product-review

This format is specifically for FAST, AI-quotable shortlists.

## Validation checklist
- [ ] Exactly 8 items? (count headings)
- [ ] Each item ≤10w sentences in body?
- [ ] Total wc 2000-2500?
- [ ] Affiliate disclosure present (if commercial)?
