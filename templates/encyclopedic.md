# Encyclopedic Template

> Format ID: `encyclopedic`. Wikipedia-style comprehensive coverage. Heavy AI citation magnet.

## Default structure

```
{Subject} ({Year})

## TL;DR (40-60w)
Wikipedia-style definition + key facts.

## Etymology / origin (~250-300w)
Where the term/concept came from. When first used. By whom.

## History (~500-700w)
Chronological development. Key milestones with dates.

## Definition + scope (~300-400w)
What is and isn't included. Boundaries.

## Types / classification (~500-700w)
Sub-categories with examples.

## Mechanism / how it works (~500-700w)
Process or principles. Diagrams.

## Applications (~400-500w)
Real-world uses across industries.

## Notable examples / instances (~400-500w)
Specific named cases.

## Controversies / debates (~300-400w)
Honest coverage of disagreements in the field.

## Future / current state (~300-400w)
Where it's headed.

## Cultural significance (~200-300w)
Beyond technical, why it matters.

## Related concepts (~300w with internal links)
Adjacent topics → other articles.

## See also
- {Related topic 1}: {1-line summary}
- {Related topic 2}: {1-line summary}

## References (≤15)
```

## Word budget (5000-7000w target)

This format is LONG by design. Comprehensive coverage signals authority.

## Required modifiers
- `tldr-first`, `mandatory-toc`
- `citation-capsules-per-h2` ✓
- `strong-eeat-signals` ✓ — encyclopedic = authority
- `info-gain-prose` ✓ ≥3
- `internal-link-hub` ✓

## Hard rules
1. Wikipedia-neutral tone (NOT promotional)
2. Multi-source citations (no single source dominance)
3. Etymology + history mandatory
4. Controversies honestly covered
5. Internal links to related topics
6. Author = subject-matter expert (E-E-A-T critical)
7. ≥10 distinct cited sources
8. No marketing language (P4)

## Schema additions
- `Article` base
- `DefinedTerm` as `mainEntity`
- `Person` author with credentials
- `Organization`

## When to use vs pillar vs definition
- definition (3500w): one term, deep
- pillar (4500-6500w): broad topic, mixed depth, with spokes
- encyclopedic (5000-7000w): comprehensive single-topic Wikipedia-style

## AI citation impact

Encyclopedic content is AI engines' favorite:
- ChatGPT trained on Wikipedia-style content
- Perplexity prefers comprehensive treatments
- Claude reads long-form well
- Gemini multimodal-friendly (diagrams)

Estimated AI citation rate: 60-80% on broad topical queries (vs 25-40% for standard articles).

## Tone notes

- Third-person throughout (no "I" or "we")
- Pass present-tense for current facts
- Past tense for history
- "While [X], some argue [Y]" pattern for controversies
- Definitive: "X is Y" (not "X may be Y")

## Image slots
- Cover: signature concept image (NOT photo of person unless biography)
- Section: timeline diagram for history
- Section: process diagram for mechanism
- Section: classification chart for types

## When to choose this format
- Topic deserves Wikipedia-style coverage
- Brand wants to own the "X" topic comprehensively
- Long-term SEO investment (15+ year content)
- Authority-building (vs traffic-getting)

## Common pitfalls
- ❌ Self-promotional (kills Wikipedia tone)
- ❌ Missing controversies (looks one-sided)
- ❌ Single-source overlap
- ❌ Too short (<3500w = use definition instead)
- ❌ Author without credentials
- ❌ Recent additions without historical context
