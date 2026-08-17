# How-to Guide Template

> Format ID: `how-to-guide`. Target: Google AIO + Featured Snippets.
> Used by `outline-architect` when `format_id == "how-to-guide"`.

## Default structure

```
{Action-verb title with time-frame and {persona} qualifier}

## TL;DR (40-60w)
{Action} in {N} steps; takes {time}; requires {prereq}.

## Abstract (120-150w)
What this guide covers + skill level + tools needed.

## Key Takeaways (4-6 bullets)
- The critical step most people skip: X
- Tool you need that costs $Y
- ...

## Table of Contents

## Before you start (~300w)
Prerequisites:
- Tools / equipment
- Skill level
- Time budget
- Common assumptions

Citation Capsule (data on how often this matters).

## Step 1: {action verb} (~400-500w)
### What this step does (1-line)
### How to do it (specific instructions)
- Sub-action 1
- Sub-action 2
- Sub-action 3

### Common mistakes
1. Mistake 1: why people do it, what to do instead
2. Mistake 2: ...

### Verification
How to know you did it right.

Citation Capsule.

## Step 2: ... Step N (same pattern, ~300-450w each)

## Troubleshooting (top 5 issues, ~500w total)
For each common problem:
- Symptom
- Likely cause
- Fix

## When to {alternative action} instead (~200w)
Edge cases / when this how-to doesn't apply.

## FAQ (5-10, ≥60% from research.paa)

## Conclusion (~150w)
Recap key steps. Encourage next action.

## References
APA 7, ≤10 entries.
```

## Word budget allocation (4500w target)

| Section | Words | % |
|---|---|---|
| TL;DR + Abstract + Takeaways | 300 | 7 |
| Before you start | 300 | 7 |
| 7 steps × 350w | 2450 | 54 |
| Troubleshooting | 500 | 11 |
| Alternative + FAQ | 700 | 16 |
| Conclusion + References | 250 | 5 |
| **Total** | **4500** | 100 |

## Required modifiers

- `tldr-first` ✓
- `citation-capsules-per-h2` ✓ (every step gets one)
- `mandatory-toc` ✓
- `featured-snippet-targets` ✓ (each step H2 is a snippet candidate)
- `info-gain-prose` ✓ (≥1 in Before you start OR Troubleshooting)

## Featured Snippet hunting

Each step H2 should be a question or action statement:
- ✅ "Step 3: Cast the rod at 10-11 o'clock angle" → step paragraph is FS candidate
- ✅ "How do I avoid the wind tangle?" → H3 question with 28-45w answer

Place a 40-60 word answer block IMMEDIATELY after each H2 that targets Featured Snippet.

## Schema additions

Despite "HowTo" schema being **deprecated** (per `references/geo/cite-framework-40.md` T09 risk):
- ✅ Use `Article` or `BlogPosting` as base
- ✅ Add `mainEntity: HowTo` (still valid in some contexts; deprecated for rich results)
- ✅ Definitely add `FAQPage` for FAQ section
- ✅ Each step's image gets `ImageObject`

DO NOT make `HowTo` the primary @type (will trigger T09 veto).

## Image slot allocation

- Cover: overview / hero (16:9)
- Section 1: Step 1 in progress (4:3)
- Section 2: middle step (most visual) (4:3)
- Section 3: result / final state (4:3)
- Slots 4-5 (the default `image_count` 6 → 5 inline slots; `scripts/_core/image_policy.py`): continue the subject pattern above with distinct, non-duplicative scenes for further key sections

## Common pitfalls

- ❌ Steps too granular (15 steps for a 5-step task)
- ❌ Steps too vague ("Do X correctly" with no specifics)
- ❌ No troubleshooting (people only google when stuck)
- ❌ "Let's begin" / "First, we'll..." openers (Comprehensive overview P29)
