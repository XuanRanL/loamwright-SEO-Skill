# Definition / Glossary Template

> Format ID: `definition`. ChatGPT training preference: Wikipedia-style content.
> Used by `outline-architect` when `format_id == "definition"`.

## Default structure

```
{What is {term}? Definition, types & examples ({year})}

## TL;DR / Definition (40-60w in first 540w)
{Term} is {essential definition in 1-2 sentences}. It's used for {primary use}. Also called {aliases}.

THIS IS THE PRIMARY FEATURED SNIPPET TARGET. Direct, factual, no hedging.

## Abstract (100-130w)
Brief: what term is, when it emerged, why it matters now.

## Key Takeaways (4-6 bullets)
- Definition: ...
- Types: A / B / C
- Used for: ...
- Most common misconception: ...
- ...

## Table of Contents

## Definition (~150-200w — Featured Snippet target)
The core, expanded definition. Wikipedia-style: neutral, factual, citable.

> {Term} is {category} that {differentiator}. It {core function}. The term was first used by {who} in {when} to describe {what}.

Citation Capsule HERE — the definitive 40-60w quotable block.

## Etymology / History (~300w)
When was the term coined? By whom? How has its meaning evolved?
This section is high-value for ChatGPT/Perplexity citations.

## Types of {term} (~500w)
### Type A
Description + when used + example.

### Type B
...

### Type C
...

Each type ~150w.

## How {term} works (~400w)
Mechanism / process / principle.
Diagram or table here.

## Examples (~400w with 5-8 specific instances)
Real-world examples, named:
- Example 1: {context} — {role of term}
- Example 2: ...

real first-hand experience or original data, in plain prose if author has worked with these.

## Use cases / Applications (~400w)
Where this term is applicable. 3-5 industries / scenarios.

## Advantages (~250w)
Benefits of using/understanding this concept.

## Disadvantages / Limitations (~200w)
Honest constraints. What this concept doesn't cover.

## Related concepts (~300w)
Adjacent terms with brief definitions + [INTERNAL-LINK: → /glossary/term-X] to each.
**THIS DRIVES GLOSSARY HUB INTERLINKING.**

## Common misconceptions (~300w)
Top 3 myths about this term, debunked with sources.

## FAQ (4-7 questions, ≥60% from research.paa)
Including: "What's the difference between X and Y?"

## Conclusion (~150w)
Brief synthesis. Don't summarize the definition — point to next steps.

## References
APA 7. Wikipedia-style: ≥3 academic OR authoritative sources. ≤10 entries.
```

## Word budget allocation (3000-3500w target — shorter than other formats)

| Section | Words | % |
|---|---|---|
| TL;DR / Definition + Abstract + Takeaways | 350 | 10 |
| Expanded Definition | 200 | 6 |
| Etymology / History | 300 | 9 |
| Types | 500 | 14 |
| How it works | 400 | 11 |
| Examples | 400 | 11 |
| Use cases | 400 | 11 |
| Advantages + Disadvantages | 450 | 13 |
| Related concepts | 300 | 9 |
| Misconceptions | 300 | 9 |
| FAQ | 200 | 6 |
| Conclusion + References | 200 | 6 |
| **Total** | **3500** | 100 |

## Required modifiers

- `tldr-first` ✓ (DEFINITION is the TL;DR for this format)
- `citation-capsules-per-h2` ✓
- `mandatory-toc` ✓
- `featured-snippet-targets` ✓ (the Definition section)
- `strong-eeat-signals` ✓ (especially if YMYL term like medical / legal)
- `info-gain-prose` ✓ (≥2)

## Wikipedia-style guidance

- Neutral tone (no "amazing", no "powerful")
- 3rd person throughout (no 1st person — exception in examples section)
- Cite sources for non-obvious claims
- Avoid promotional language
- Avoid speculation ("might" / "could" sparingly)

## Schema additions

- `Article` (NOT BlogPosting — this is reference-style)
- `mainEntity: DefinedTerm` (Schema.org)
- `description` = the TL;DR
- `definedTermDefinition` = the expanded definition
- `partOfSet: {@type: "DefinedTermSet", name: "{Brand} Glossary"}`
- `FAQPage` for FAQ block

## Image slot allocation

- Cover: conceptual visualization (NOT a photo of a thing; an abstract concept)
- Section 1: diagram of how it works
- Section 2: 3-up examples panel
- Section 3: misconception illustration OR types diagram
- Slots 4-5 (the default `image_count` 6 → 5 inline slots; `scripts/_core/image_policy.py`): continue the subject pattern above with distinct, non-duplicative scenes for further key sections

## Common pitfalls

- ❌ Promotional tone ("X is the most important concept in...")
- ❌ Vague definition ("X is a thing that does stuff")
- ❌ No etymology (this is where ChatGPT/Wikipedia thrives)
- ❌ Inconsistent terminology (define once, stick with it)
- ❌ Listing 20 examples without context (curated 5-8 beats unfocused 20)
