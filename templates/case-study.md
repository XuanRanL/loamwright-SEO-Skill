# Case Study Template

> Format ID: `case-study`. Princeton GEO: case studies with original data = +30-40% AI citation.
> Used by `outline-architect` when `format_id == "case-study"`.

## Default structure

```
{How {company/persona} achieved {specific result} with {method}: case study}

## TL;DR (40-60w)
Result: {specific number}. Method: {brief}. Time: {duration}. Cost: $X (or saved $X).

## Abstract (150w, third-person)
Who, what, when, where, why, how, result. All specifics.

## Key Takeaways (5-7 bullets)
- Result: {primary metric} jumped from X to Y (+N%)
- Key insight: {what surprised even us}
- Replicable: {yes/partially/no} — {why}
- ...

## Table of Contents

## Background / Company profile (~400w)
{Customer / persona} context: industry, size, when started.
original data (plain prose) — baseline metrics.

## The challenge (~500w)
Quantified problem:
- Metric was X before
- Pain points
- What they had tried that didn't work

Citation Capsule (the problem stated quotably).

## What we tried (approach) (~500w)
The strategy / framework we used.
Why this approach over alternatives.

## Implementation (~600-1000w)
### Phase 1 (~200w with date range)
What was done. Specific decisions.

### Phase 2 (~200w)
...

### Phase 3 (~200w)
...

Be honest about pivots. real first-hand experience (plain prose).

## Results (~600w with charts)
**THE moneymaker section.** Lots of specific numbers.

### Metric 1: {name}
Before: X
After: Y
Change: +N% over {duration}

Include chart (markdown table).

### Metric 2 ... Metric M
Same structure.

Citation Capsule with the top result.

## What worked (~400w)
3-5 specific learnings.

## What didn't work (~300w)
**Honest failures.** Builds massive trust.
2-3 things we tried that fell flat.
What we'd do differently.

## Lessons learned (~400w)
The transferable principles.

## Replicating this for your situation (~400w)
Decision framework: when this approach fits.
Adapted version of the playbook.

## Tools & resources used (~200w)
Bulleted list. Affiliate disclosures if any.

## FAQ (5-7 questions)
Including: "Would this work for {different vertical}?", "How long did it really take?", "What if I have less budget?"

## Conclusion (~200w)
Restate the result + the most important lesson.

## References
- Internal: original survey data, internal analytics
- External: peer-reviewed sources for methodology claims
- ≤10-15 entries
```

## Word budget allocation (5500w target)

| Section | Words | % |
|---|---|---|
| TL;DR + Abstract + Takeaways | 400 | 7 |
| Background | 400 | 7 |
| Challenge | 500 | 9 |
| Approach | 500 | 9 |
| Implementation (3 phases) | 800 | 15 |
| Results (charts) | 600 | 11 |
| What worked / didn't / lessons | 1100 | 20 |
| Replicating | 400 | 7 |
| Tools | 200 | 4 |
| FAQ | 400 | 7 |
| Conclusion + Refs | 200 | 4 |
| **Total** | **5500** | 100 |

## Required modifiers

- `tldr-first` ✓ (result in first 540w)
- `citation-capsules-per-h2` ✓
- `mandatory-toc` ✓
- `strong-eeat-signals` ✓ (case study is E-E-A-T showcase)
- `info-gain-prose` ✓ (REQUIRES ≥3 — case studies are about original data)

## Mandatory rules (case-study specific)

1. ≥3 specific numeric metrics with before/after
2. ≥1 chart/table showing results visually
3. Author byline must include credentials proving the experience is real
4. ≥1 piece of original data
5. ≥1 piece(s) of real first-hand experience
6. "What didn't work" section is NOT optional (honesty premium)
7. Customer permission documented if their name is used

## Veto risks

- **C01 (fabricated citation)** — Case studies tempt fabrication; HEAD-check every source
- **T04 (fabricated stat)** — Every number must be traceable
- **T03 (missing disclosure)** — Sponsored case studies need disclosure

## Schema additions

- `Article` base
- `Person` for the customer (if individual) OR `Organization`
- `Review` if it's a product case study
- `Dataset` if you published the dataset

## Image slot allocation

- Cover: outcome visualization (chart, before/after, hero photo of customer)
- Section 1: challenge / "before" state photo or chart
- Section 2: implementation moment / behind-the-scenes
- Section 3: result / "after" state visualization

## Common pitfalls

- ❌ Hagiography (only successes; readers don't believe perfect stories)
- ❌ Vague metrics ("significantly improved")
- ❌ No baseline (can't measure change without before)
- ❌ "Game-changing transformation" (P1 + P4 promo language)
- ❌ Reads like marketing copy (P4 promotional language pattern)
