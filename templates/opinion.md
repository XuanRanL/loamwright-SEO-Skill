# Opinion Template

> Format ID: `opinion`. Strong take + reasoning. Best for industry critique, contrarian positions, leadership voice.

## Default structure

```
{Provocative Thesis Statement}

## TL;DR (40-60w)
The thesis + 1-line reason.

## The claim (~200-300w)
State the position clearly + name the opposing view.

## Why this matters (~250-300w)
Stake. What's at risk if this isn't acknowledged.

## The evidence (~600-800w)
Data + experience + reasoning supporting the claim.
- Stat 1 with source
- Stat 2 with source
- real first-hand experience (plain prose)
- original analysis (plain prose)

## Steel-manning the opposing view (~300-400w)
What people who disagree believe + why their position has merit.
This builds credibility.

## Where they go wrong (~400-500w)
Specific counter-arguments to the opposing view.

## What the right answer is (~300-400w)
Your synthesis.

## What this means for {audience} (~250w)
Actionable implication.

## Where I could be wrong (~150w)
Intellectual honesty. Identify your own blind spots.

## References (≤10)
```

## Word budget (3500w target)

| Section | Words | % |
|---|---|---|
| TL;DR + claim | 300 | 9 |
| Why it matters | 300 | 9 |
| Evidence | 700 | 20 |
| Steel-man opposing | 350 | 10 |
| Counter-arguments | 450 | 13 |
| Right answer | 350 | 10 |
| What to do | 250 | 7 |
| Where wrong | 150 | 4 |
| Hooks + transitions | 650 | 18 |

## Required modifiers
- `tldr-first`, `citation-capsules-per-h2`
- `info-gain-prose` ✓ ≥1 piece of real first-hand experience + ≥1 piece of original analysis
- `strong-eeat-signals` ✓ — author credentials critical

## Hard rules
1. CLEAR thesis (not "it's complicated")
2. Name the opposing view explicitly
3. Steel-man (don't strawman) the opposition
4. Acknowledge where you could be wrong
5. Author credentials prominent (op-ed = byline + bio matters)
6. ≥3 data points supporting claim
7. Avoid ad hominem (attack ideas, not people)

## Schema additions
- `Article` or `OpinionNewsArticle` (newer schema)
- `Person` author with credentials
- `Organization`

## When to use vs essay vs personal-story
- essay: argument-driven long-form (3000-4000w)
- opinion: shorter, sharper take with explicit position
- personal-story: experience-first; takeaways are softer

## Voice + purpose
- Voice: `blunt` or `professional`
- Purpose: `essay`
- Avoid `marketing` purpose (opinion ≠ marketing)

## Common pitfalls
- ❌ Hedging (defeats the purpose of opinion)
- ❌ "Many would agree" (cop-out — name names)
- ❌ Strawman (attacking weakest opposing argument)
- ❌ Personal attacks (ad hominem)
- ❌ No data backing claim (pure rant)
- ❌ "What do you think?" ending (lazy)

## Image slots
- Cover: thought-provoking, NOT generic stock
- Section 1: data visualization supporting claim
- Optional: portrait of author (E-E-A-T)

## Tone tips

- State claims as facts when you have evidence
- Use "I think" sparingly — once or twice for emphasis
- Specific examples > abstract claims
- One sharp 3-word sentence + one nuanced 30-word sentence > all medium length
