# Buyers Guide Template

> Format ID: `buyers-guide`. Decision-framework heavy. More analytical than listicle.

## Default structure

```
The Complete {Year} Buyers Guide to {Category}

## TL;DR (40-60w)
Top recommendation by use case.

## Why this matters (~250-300w)
Why buyers need this guide.

## How to choose: the decision framework (~600-800w) — CORE SECTION
- Criterion 1: {weight}
- Criterion 2: {weight}
- Criterion 3: {weight}
- How to weight them for your situation

## What to ignore (~250-300w)
Marketing terms that don't matter. Builds trust.

## Best {category} by use case (~2000-2500w)

### Best for {use case 1} ({persona description})
- Top pick: X
- Runner-up: Y
- Why: {decision-framework-based reasoning}

### Best for {use case 2}
{Same structure}

### Best for {use case 3}
{Same structure}

### Best for {use case 4}
{Same structure}

## Detailed comparison table (~600-800w + table)

| Criterion | X | Y | Z | W |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

## How to test before buying (~250-300w)

## When to delay your purchase (~150-200w)

## FAQ (5-7)

## References (≤10)
```

## Word budget (5500-6500w target)

| Section | Words | % |
|---|---|---|
| TL;DR + why matters | 350 | 6 |
| Decision framework | 700 | 12 |
| What to ignore | 275 | 5 |
| 4 use cases × ~550w | 2200 | 38 |
| Comparison table | 700 | 12 |
| Test + delay | 425 | 7 |
| FAQ | 550 | 10 |
| Transitions | 600 | 10 |

## Required modifiers
- `tldr-first`, `mandatory-toc`, `citation-capsules-per-h2`
- `info-gain-prose` ✓ ≥2 (testing methodology + comparison data, plain prose)
- `featured-snippet-targets` ✓ (each "best for" = snippet candidate)

## Hard rules
1. Decision framework comes BEFORE picks (not after)
2. Picks organized by USE CASE (not arbitrary ranking)
3. "What to ignore" section mandatory (anti-marketing builds trust)
4. ≥1 detailed comparison table
5. Affiliate disclosure if commercial
6. ≥1 piece of real information gain, written as PLAIN PROSE (never a bracketed `[ORIGINAL DATA]` marker — those are render_lint L6 hard-vetoes and are stripped at publish). If genuine first-party testing exists, describe the methodology. **If it does not, do NOT invent one** — a criteria-led guide that teaches the reader to judge for themselves is legitimate information gain, and a fabricated "we tested N products" claim is a hard veto.

## Schema additions
- `Article` base
- `ItemList` for picks
- `Review` per pick
- `AggregateRating` (if rating each)
- `FAQPage`

## When to use vs listicle vs comparison
- listicle: ranked best-of (X is #1)
- comparison: 2-way deep (X vs Y)
- buyers-guide: multi-criteria decision framework for diverse buyers

## Image slots
- Cover: decision tree / matrix visualization
- Section 1: criterion-weighting diagram
- Section 2-3: per-use-case visualization
- Comparison table: itself counts as visual

## Tone notes

Buyer guides earn trust through:
- Quantified comparisons (not "X is great")
- Honest exclusions ("X is bad for Y use case")
- Anti-marketing transparency ("ignore claim Z")
- Specific decision criteria (not vague "consider your needs")

## Common pitfalls
- ❌ All-positive (no exclusions = looks fake)
- ❌ Vague criteria
- ❌ Hidden affiliate
- ❌ No comparison table
- ❌ Just a listicle in disguise (no framework)
- ❌ Marketing copy from manufacturers
