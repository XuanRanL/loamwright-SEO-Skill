# FAQ Knowledge Template

> Format ID: `faq-knowledge`. Q&A-format article. Optimized for AIO + voice search.

## Default structure

```
{Topic}: {N} Questions Answered ({Year})

## TL;DR (40-60w)
What this article covers.

## Q1: {Question (5W1H or yes/no)}
**Answer**: 28-45 word direct answer with statistic.
Then 1-2 paragraphs of detail.

## Q2 ... Q15 (same structure)

## Related questions (3-5 more — drives PAA optimization)

## References (≤8)
```

## Word budget (3000w target)

| Section | Words | % |
|---|---|---|
| TL;DR + intro | 100 | 3 |
| 15 Q&As × ~180w | 2700 | 90 |
| Related questions | 200 | 7 |

## Why this format wins for AI engines

AI engines + Google AIO extract Q&A pairs verbatim. FAQ-format content has the highest extractability:
- Question structure matches voice queries
- 28-45w answer = Featured Snippet sweet spot
- FAQPage schema doubles citation probability

## Required modifiers
- `tldr-first`, `featured-snippet-targets`, `mandatory-toc`
- `info-gain-prose` ≥1
- `voice-search-friendly` ✓ — questions ARE the headings

## Hard rules
1. Each Q is a real PAA question (verify via Tavily SERP probe)
2. Each Answer: 28-45w direct answer + optional expansion
3. ≥10 Q&A pairs (FAQPage schema needs ≥2; we want ≥10 for substance)
4. No yes/no questions without nuance
5. Questions varied (not all "what is" — mix what/why/how/when)
6. FAQPage schema mandatory

## Schema additions
- `Article` or `FAQPage` as primary (depends on usage)
- `FAQPage` with all Q&A pairs in `mainEntity`

## Common question types (mix all)

- **Definition**: "What is X?"
- **Process**: "How does X work?"
- **Decision**: "Should I do X?"
- **Comparison**: "X vs Y — which is better?"
- **Timing**: "When should I X?"
- **Cost**: "How much does X cost?"
- **Alternative**: "What's an alternative to X?"
- **Mistakes**: "What are common X mistakes?"
- **Future**: "Will X still matter in {year}?"

## Image slots
- Cover: topic hero
- Section 1-2: optional visual breaks every 5-7 questions

## When to use vs glossary-hub vs pillar
- pillar (4000+ w): broad coverage of a topic
- glossary-hub: definition-only, multiple terms
- faq-knowledge: questions about ONE topic (this format)

## Common pitfalls
- ❌ Made-up questions (use real PAA)
- ❌ All "what is" type questions
- ❌ Answers >100w (loses Featured Snippet)
- ❌ Hidden FAQPage schema
- ❌ Random question order (group by sub-topic)
