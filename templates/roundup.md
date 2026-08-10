# Roundup Template

> Format ID: `roundup`. Curated collection of resources / tools / examples on a topic.
> Differs from listicle: less ranking, more discovery; from buyers-guide: less decision framework.

## Default structure

```
{N} Best {Resource Type} for {Persona} ({Year})

## TL;DR (40-60w)
What's in the roundup + how we picked.

## How we curated (~200-300w)
Inclusion criteria. Be specific (not "we chose the best").

## The {N} {resources} (12-20 typically)

### Category A: Free / Open source
- Resource 1 — 1-2 sentences + link
- Resource 2 — same
- ...

### Category B: Paid premium
- Resource 1
- ...

### Category C: Hybrid / freemium
- Resource 1
- ...

## How to choose (~300-400w decision framework)

## What we left out + why (~200w)
Honest. Builds trust.

## FAQ (3-5)

## References (≤10)
```

## Word budget (3500w)

Each resource entry is 80-150w. 15 resources × 100w = 1500w. Plus framework + FAQ + curation explanation = 3500w total.

## Required modifiers
- `tldr-first`, `citation-capsules-per-h2`, `mandatory-toc`, `info-gain-prose` ≥1

## Hard rules
1. Group by meaningful category (NOT just alphabetical)
2. Each entry: link + 1-line summary + use case + pricing
3. Include "what we left out" section (transparency)
4. Affiliate disclosure if commercial

## Schema additions
- `Article` base
- `ItemList` with each resource
- `FAQPage`

## When to use vs listicle vs buyers-guide
- listicle (10-15 ranked items): "best products"
- buyers-guide: heavy decision-framework focus
- roundup (12-20 items, less ranked): "tools / resources / examples in this space"

## Common pitfalls
- ❌ Just an unannotated link list
- ❌ Too few items (<8) → reads like listicle
- ❌ Too many items (>25) → loses focus
- ❌ No grouping → hard to scan
- ❌ Missing pricing or context per entry
