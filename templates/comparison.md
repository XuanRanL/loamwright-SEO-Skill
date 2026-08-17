# Comparison Template

> Format ID: `comparison`. AirOps 2026.4: 3 comparison tables = +25.7% ChatGPT citations.
> Used by `outline-architect` when `format_id == "comparison"`.

## Default structure

```
{X vs Y: {Authority Word} comparison in {year}}

## TL;DR (40-60w)
**Verdict**: Choose X if {use case A}. Choose Y if {use case B}. Tied if {use case C}.

## Abstract (120-150w)
Compared on N criteria. Tested for M weeks. Specific verdict per use case.

## Key Takeaways (5-7 bullets)
- X wins for {scenario 1} — specifically because {data point}
- Y wins for {scenario 2}
- {Surprising finding}
- {Cost angle}
- ...

## Table of Contents

## Quick comparison (Table 1, ≤25% mark) (~200w)
Side-by-side feature/benefit table. 8-12 rows.

| Feature | X | Y |
|---|---|---|
| Best for | ... | ... |
| Price | $A | $B |
| ...

This is THE table that wins Featured Snippet for "X vs Y".

## Pricing comparison (Table 2) (~400w)
Plans tier-by-tier. Total cost over 1 year / 3 years.

## Feature-by-feature (Table 3) (~600w)
The deep dive. 15-25 rows. Use ✓/✗/partial.

## {X}: strengths & weaknesses (~600w)
### Strengths (3-5)
### Weaknesses (3-4)
### Best for whom

Citation Capsule.

## {Y}: strengths & weaknesses (~600w)
### Strengths (3-5)
### Weaknesses (3-4)
### Best for whom

Citation Capsule.

## Real-world use cases (~500w)
3-4 scenarios where one clearly wins.

## Performance comparison (data-backed) (~400w)
Benchmarks, speed tests, conversion data.
original data (plain prose).

## When to choose {X} (~200w)
Decision criteria for X.

## When to choose {Y} (~200w)
Decision criteria for Y.

## Migration path (if applicable) (~300w)
How to switch from one to the other.

## FAQ (5-10, ≥60% from research.paa)

## Verdict (~150w)
Restate top-level recommendation per persona.

## References
APA 7, ≤10 entries.
```

## Word budget allocation (4500w target)

| Section | Words | % |
|---|---|---|
| TL;DR + Abstract + Takeaways | 350 | 8 |
| Quick comparison + pricing + features | 1200 | 27 |
| X strengths/weaknesses | 600 | 13 |
| Y strengths/weaknesses | 600 | 13 |
| Use cases + Performance | 900 | 20 |
| When to choose + Migration | 700 | 16 |
| FAQ | 400 | 9 |
| Verdict + References | 250 | 6 |
| **Total** | **4500** | 100 |

## Required modifiers

- `tldr-first` ✓ (verdict in first 540w)
- `citation-capsules-per-h2` ✓ (each subject's strengths/weaknesses gets a capsule)
- `mandatory-toc` ✓
- `featured-snippet-targets` ✓ (the table 1)
- `info-gain-prose` ✓ (≥2 — original data in performance section)

## The 3 tables rule (AirOps +25.7%)

Tables MUST be:
1. Quick comparison (top, simple, 8-12 rows) → wins FS
2. Pricing (tier-by-tier)
3. Feature-by-feature (deep, 15-25 rows)

If user is targeting ChatGPT specifically, ensure these 3 tables exist.

## Schema additions

- `Article` base
- `Review` schema with `itemReviewed: ProductGroup`
- `ItemList` listing both X and Y
- `FAQPage`
- Optionally: `SoftwareApplication` schema for each subject (if SaaS)

## Image slot allocation

- Cover: split-screen X vs Y (16:9, brand-consistent)
- Section 1: X in action
- Section 2: Y in action
- Section 3: verdict visualization (decision tree or 2×2 matrix)
- Slots 4-5 (the default `image_count` 6 → 5 inline slots; `scripts/_core/image_policy.py`): continue the subject pattern above with distinct, non-duplicative scenes for further key sections

## Common pitfalls

- ❌ Advocating one side (must be balanced even if conclusion favors one)
- ❌ Only 1 table (need 3 for ChatGPT lift)
- ❌ Generic feature comparison ("Both have integrations" — be SPECIFIC)
- ❌ "Both options have their pros and cons" (Generic positive conclusion P24)
- ❌ Affiliate disclosure missing (if commercial — T03 veto)
