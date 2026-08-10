# Curated Roundup Template

> Format ID: `curated-roundup`. "Best of {Year}" — selections from broader catalog with strong opinion.
> Different from roundup (broader, less ranking): curated-roundup is opinionated.

## Default structure

```
The {N} Best {Things} of {Year}: Our Top Picks

## TL;DR (40-60w)
Our top pick + 2 honorable mentions.

## How we picked (~300-400w)
Criteria, time period reviewed, comparison universe.
original data (plain prose) if testing methodology.

## #1: {Top pick} (~400-500w)
The flagship. Most space, most justification.
Why this won. What runner-ups didn't have.

## #2-7: Top picks (each ~250-300w)
Each has: name + 2-3 reasons + 1 stat + photo.

## #8-10: Honorable mentions (each ~150-200w)
Shorter; why they almost made the top.

## What didn't make the list + why (~200-250w)
Honest exclusions. Builds trust.

## How to choose for your use case (~300w)
Decision framework.

## FAQ (3-5)

## References (≤10)
```

## Word budget (4000w target)

| Section | Words | % |
|---|---|---|
| TL;DR + criteria | 400 | 10 |
| #1 in-depth | 450 | 11 |
| #2-7 (6 × 275w) | 1650 | 41 |
| #8-10 (3 × 175w) | 525 | 13 |
| Honest exclusions | 225 | 6 |
| Decision framework | 300 | 8 |
| FAQ + transitions | 450 | 11 |

## Required modifiers
- `tldr-first`, `citation-capsules-per-h2`, `mandatory-toc`
- `info-gain-prose` ✓ ≥1 (curation methodology stated in plain prose)

## Hard rules
1. Explicit criteria (not vague "best")
2. Top pick gets 1.5-2× space vs runners
3. Honorable mentions distinguished from top picks
4. Affiliate disclosure if commercial
5. Updated annually (year in title)
6. "What didn't make it" section mandatory

## Schema additions
- `Article` base
- `ItemList` with ranked items
- `Review` per item (optional)
- `FAQPage`

## When to use vs roundup vs listicle
- roundup: broader, less ranked (12-20 items)
- curated-roundup: opinionated picks (10 items, big delta between #1 and #10)
- listicle: traditional ranking (10 items, mostly equal weight)

## Annual update strategy

"Best X of 2026" needs annual refresh:
- Keep URL stable ("best-x-current-year" slug)
- Update title + content yearly
- Note changes from previous year
- Old version archived to "best-x-{previous-year}"

## Common pitfalls
- ❌ All picks equally weighted (defeats purpose of curation)
- ❌ Top pick justification too short
- ❌ No honest exclusions
- ❌ Year not in title (loses freshness signal)
- ❌ Generic criteria ("best overall")
