# Product Review Template

> Format ID: `product-review`. Single-product deep evaluation with hands-on testing.
> Used by `outline-architect` when `format_id == "product-review"`.

## Default structure

```
{Product Name} Review {Year}: {Specific Verdict / Hook}

## TL;DR / Verdict (40-60w)
**Verdict**: {Brand} {Product} is {X-star rating}/5. Best for {persona}. Skip if {disqualifier}.

## Abstract (120-150w, 3rd person)
What was tested, by whom, over what period, against what alternatives.

## Key Takeaways (5-7 bullets)
- The single biggest pro: {data-backed}
- The single biggest con: {honest}
- Best for: {specific persona}
- Skip if: {disqualifier}
- Price: ${price} vs alternatives' ${range}

## Table of Contents

## How we tested (~400-500w) — E-E-A-T critical
- Test duration + conditions
- Test methodology (objective + subjective)
- Comparison set (X products tested in parallel)
- real first-hand experience (plain prose)
- Citation Capsule with test data

## What's in the box (~200w)
Photo + bulleted contents. Sets expectation for unboxing experience.

## Design + build quality (~400-500w)
- Materials, dimensions, weight
- Build quality observations
- Aesthetic verdict
- Photos
- Inline citation if quoting specs

## Performance / functionality (~600-800w)
The meat of the review. Test results with data:
- Metric 1: {actual measurement}
- Metric 2: {actual measurement}
- Comparison to {alternative}
- original data (plain prose)

## Pros (5-7 specific)
Each pro = 1 sentence claim + 1 sentence evidence.

## Cons (3-5 honest)
What didn't work + workarounds.
**Critical**: include cons. No-cons reviews look fake.

## Who should buy this (~250w)
Decision criteria — when this product is right.

## Who should NOT buy this (~200w)
Decision criteria — when to look elsewhere. Builds trust.

## Alternatives (~400-500w with 3 comparisons)
For each alt:
- 1-line summary
- Why pick this over our review subject (if at all)
- Link to our full review (if exists)

## Price + value (~250w)
- Price tracked over 3-6 months (if possible)
- Price vs alternatives
- Discount codes / sales calendar
- Verdict: worth full price OR wait for X% off

## FAQ (5-8 PAA questions)
- Common pre-purchase doubts

## Final verdict (~150w)
Rating + specific recommendation. No hedging.

## References
APA 7, ≤10 entries.
```

## Word budget (4500w target)

| Section | Words | % |
|---|---|---|
| TL;DR + Abstract + Takeaways | 400 | 9 |
| How we tested | 500 | 11 |
| What's in box | 200 | 4 |
| Design + build | 500 | 11 |
| Performance | 800 | 18 |
| Pros / Cons | 500 | 11 |
| Who should / shouldn't | 450 | 10 |
| Alternatives | 500 | 11 |
| Price + value | 250 | 6 |
| FAQ | 400 | 9 |
| Verdict + Refs | 200 | 4 |

## Required modifiers
- `tldr-first` ✓ — verdict in first 540w
- `citation-capsules-per-h2` ✓
- `mandatory-toc` ✓
- `strong-eeat-signals` ✓
- `info-gain-prose` ✓ ≥2 (testing methodology + first-hand use, plain prose — only if the testing truly happened)

## Hard rules
1. ≥1 piece(s) of real first-hand experience
2. ≥3 specific metrics with test data
3. ≥3 cons (honest)
4. Affiliate disclosure required (T03 veto)
5. Star rating consistent across reviews on same site
6. Photos of actual product (not stock)

## Schema additions
- `Article` base
- `Review` schema with `itemReviewed` + `reviewRating`
- `AggregateRating` if multiple reviews on site
- Optional: `Product` schema if also selling

## Image slots
- Cover: hero shot of product in use (16:9)
- Section 1: design / build detail (4:3)
- Section 2: in-use mid-test (4:3)
- Section 3: comparison or final result (4:3)

## Common pitfalls
- ❌ All-positive review (looks fake; bad for trust)
- ❌ No specific metrics (just "feels good")
- ❌ Hidden affiliate (T03 veto)
- ❌ "Game-changing", "revolutionary" hype (P4)
- ❌ Generic verdict (be specific)
