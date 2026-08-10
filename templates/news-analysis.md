# News Analysis Template

> Format ID: `news-analysis`. Time-sensitive opinion + analysis on current events.
> Used by `outline-architect` when `format_id == "news-analysis"`.

## Default structure

```
{Subject}: What It Means for {Reader Persona}

## TL;DR (40-60w)
What happened + the take + so what (3 sentences).

## What happened (~200-300w)
Just the facts. Sources cited inline.

## Why it matters (~300-400w)
The "so what" — your interpretation backed by data.

## Context: how we got here (~300-400w)
Historical setup. Helps reader understand significance.

## What's likely next (~250-350w)
Forward-looking analysis. Uncertain claims labeled as such.

## What you can do about it (~250-300w)
Actionable takeaways for the reader.

## Counterargument / what could go differently (~200w)
Address strongest opposing view.

## FAQ (3-5 short)

## References (≤8 APA 7)
```

## Word budget (1500w target — short by design)

News content is shorter than evergreen:

| Section | Words | % |
|---|---|---|
| TL;DR | 60 | 4 |
| What happened | 250 | 17 |
| Why it matters | 350 | 23 |
| Context | 350 | 23 |
| What's next | 300 | 20 |
| What to do | 250 | 17 |
| Counterargument + FAQ | 200 | 13 |
| Refs | (count separate) | — |

## Required modifiers
- `tldr-first` ✓ — first 540w must answer "what happened?"
- `citation-capsules-per-h2` ✓
- `freshness-critical` ✓ — `dateModified` essential; ideally publish within 24h of event
- `info-gain-prose` ✓ ≥1 piece of original analysis (your interpretation)
- `surface-targeting` ✓ — Google AIO heavy (freshness wins)

## Hard rules
1. Publish within 24-72h of event (freshness decay is rapid)
2. Cite ≥3 Tier-1 sources for the news facts
3. Distinguish facts from your interpretation (use original analysis (plain prose) for opinion)
4. Update if facts change ("Last updated: {date}")
5. Avoid speculation without labeling
6. No clickbait headline patterns

## Schema additions
- `NewsArticle` (NOT BlogPosting — different SEO treatment)
- `Person` author with credentials
- `Organization` publisher
- `BreadcrumbList`

## Image slots
- Cover: relevant image (NOT generic stock)
- Section 1: data visualization OR contextual image

## Why "what's next" matters

AI engines especially Perplexity favor articles with forward-looking analysis. The "what's likely next" section is the AI-citation goldmine.

## Common pitfalls
- ❌ Pure reporting without interpretation (no value-add vs original source)
- ❌ Opinion without labeling as opinion
- ❌ Outdated within 48h ("recent" but published 2 weeks ago)
- ❌ Missing dateModified
- ❌ News not in NewsArticle schema (BlogPosting treats differently)
- ❌ Speculation as fact

## Time decay

News-analysis articles have rapid decay:
- T+1 day: 90% of traffic
- T+7 days: 30%
- T+30 days: <5%
- T+90 days: archive

Unless news has lasting significance, expect short-lifespan traffic.

## When to convert to pillar later

If a news topic becomes evergreen (e.g., "ChatGPT launches" → "How ChatGPT works"):
- Don't update news-analysis → write a new pillar-page
- Link news-analysis up to pillar
- Pillar gets long-term traffic; news-analysis serves freshness
