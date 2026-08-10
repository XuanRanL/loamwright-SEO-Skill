# Glossary Hub Template

> Format ID: `glossary-hub`. Multi-term glossary on a topic. SEO + AI citation goldmine.

## Default structure

```
{Topic} Glossary: {N} Terms Defined ({Year})

## TL;DR (40-60w)
What's covered + how to use this glossary.

## Quick alphabetical index (A-Z linked)

## Terms grouped by sub-topic

### Sub-topic A
- **Term 1**: 40-80w definition + example
- **Term 2**: same
- ...

### Sub-topic B
- **Term N**: same
- ...

## Most commonly confused terms (~300w)
Side-by-side: "X vs Y — what's the difference?"

## Related concepts (~150w)
Pointers to other glossary-hubs OR pillar pages.

## How this glossary is maintained (~100w — E-E-A-T)

## References (≤10)
```

## Word budget (3500w target)

| Section | Words | % |
|---|---|---|
| Intro + index | 200 | 6 |
| 30 terms × 90w | 2700 | 77 |
| Commonly confused | 300 | 9 |
| Related + maintenance | 200 | 6 |
| FAQ | 100 | 3 |

## Why this format wins

- Each term is a mini-definition article (high citation extractability)
- AI engines love wiki-style content
- Internal-linking goldmine (link from any other article that uses a term)
- Long-tail traffic (each term = its own query)
- Authority signal (you're the glossary; readers trust you)

## Required modifiers
- `tldr-first`, `mandatory-toc`
- `alphabetical-index` ✓
- `info-gain-prose` ≥1
- `internal-link-hub` ✓

## Hard rules
1. ≥20 terms (else it's not a "glossary" — use definition format)
2. Each term: 40-80w definition + concrete example
3. Group by sub-topic AND provide A-Z index
4. Cross-link related terms within definitions
5. "Commonly confused" section mandatory
6. Maintenance date visible

## Schema additions
- `Article` base
- Each term: `DefinedTerm` schema
- `DefinedTermSet` wrapping all terms
- Optional: `FAQPage` for commonly confused

## Internal-linking strategy

Glossary-hub is the **hub** of internal linking:
- Every other article mentions a term → link to its glossary entry
- Glossary entries link to relevant pillar / how-to articles
- High internal-link density (15-30 links from glossary; 2-5 per term)

## Image slots
- Cover: word cloud / concept map (NOT photo)
- Optional: diagram per sub-topic group

## When to use vs definition vs faq-knowledge
- definition: ONE term, deep dive (3000w)
- faq-knowledge: questions about one topic (15 Q&A)
- glossary-hub: MANY terms, lighter coverage each (30 × 90w)

## Maintenance

Glossary-hubs need updates (new terms emerge):
- Quarterly: add 2-5 new emerging terms
- Annually: archive obsolete terms (with redirect note)
- Mark "last updated: {date}" visibly

## Common pitfalls
- ❌ Terms in random order (group by sub-topic)
- ❌ Definitions too short (<30w each looks lazy)
- ❌ Definitions too long (>120w → use definition template instead)
- ❌ No examples in definitions
- ❌ No internal links between terms
- ❌ Missing A-Z index
