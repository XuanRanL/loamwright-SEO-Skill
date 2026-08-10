# Multi-Intent Hybrid Template

> Format ID: `multi-intent-hybrid`. Combines informational + commercial intent in one article.
> Use when keyword research shows mixed intent (e.g., "AI marketing tools" = info + commercial).

## When to use this format

Keyword analysis shows:
- Top 10 SERP has mix of how-to + listicle + product pages
- "People also ask" includes both "what is X" and "best X"
- Search intent is genuinely ambiguous

Pure listicle = misses informational users. Pure how-to = misses commercial intent.

## Default structure

```
{Topic}: {Definition + Comparison} ({Year})

## TL;DR (40-60w)
What X is + best X for {use case}.

## What is {topic} (~600-800w)
Definition + how it works + why it matters.
Serves informational intent.
real first-hand experience (plain prose).

## Why you might need {topic} (~400-500w)
Use cases. Decision: is this for me?

## Key features to look for (~500-600w)
Decision framework. Sets up comparison.

## Best {topic} for different use cases (~2000-2500w)
The commercial section. 5-7 picks with:
- 1-line summary
- Best for: {persona}
- Pros / cons / price
- Verdict

## How to choose (~400-500w)
Decision tree based on use case.

## How to get started (~300-400w)
After picking. Bridges to next step.

## FAQ (5-7 — mix info + commercial questions)

## References (≤10)
```

## Word budget (5500-6500w target)

Long-form by necessity (covering both intents):

| Section | Words | % |
|---|---|---|
| TL;DR + intro | 200 | 4 |
| What is X | 700 | 12 |
| Why need it | 450 | 8 |
| Key features | 550 | 10 |
| Best picks | 2250 | 39 |
| How to choose | 450 | 8 |
| Get started | 350 | 6 |
| FAQ | 500 | 9 |
| Transitions + hooks | 300 | 5 |

## Required modifiers
- `tldr-first`, `mandatory-toc`, `citation-capsules-per-h2`
- `info-gain-prose` ✓ ≥2
- `multi-intent` ✓ (this is the defining modifier)

## Hard rules
1. Definition section (~600w) MUST come before commercial picks
2. Picks section must reference definition (not standalone)
3. Conclusion serves BOTH intents (info summary + commercial verdict). On cta-enabled projects (business-context.cta.enabled) write NO prose CTA — the cta-injection stage appends the styled module; only no-cta projects keep prose CTAs here (v3.35.1)
4. Schema: combine Article + ItemList
5. ≥2 piece(s) of real first-hand experiences (you used the products)
6. Affiliate disclosure if commercial

## Schema additions
- `Article` base
- `ItemList` for picks
- `FAQPage` for Q&A
- `Review` per pick (optional)

## When to use vs listicle vs pillar
- listicle: pure commercial intent
- pillar: pure informational, links to listicle spokes
- multi-intent-hybrid: ambiguous SERP, single article covers both

## SEO benefits

Multi-intent articles often:
- Rank for both info + commercial keywords
- Capture readers at multiple funnel stages
- Higher dwell time (more content)
- Lower bounce (something for every reader)

But require more work to write well.

## Common pitfalls
- ❌ Definition too short (skipped) → loses info intent rankings
- ❌ Picks section dominates → just becomes a listicle
- ❌ No clear navigation between sections (use TOC heavily)
- ❌ Mixing informational tone with commercial selling
- ❌ Same Citation Capsule pattern dropped mid-article

## Voice + purpose
- Voice: `professional`
- Purpose: `general` (not `marketing` — too sales-y for info readers)
