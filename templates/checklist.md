# Checklist Template

> Format ID: `checklist`. Action-oriented numbered list. Strong for Featured Snippets + AIO.

## Default structure

```
{Action} Checklist: {N} Steps ({Year})

## TL;DR (40-60w)
N-step process. Time estimate.

## Before you start (~200-300w)
Prerequisites + tools + time investment.

## The checklist

- **Step 1: {Action verb + specific outcome}**
      Brief context (≤30 words).
      How to know it's done ("Done when ...").

- **Step 2: {Action verb + specific outcome}**
      ...

(8-15 items)

⚠️ Plain bold-led list items ONLY — NEVER GFM task-list checkboxes (`- [ ]`).
The publisher's markdown-it has no tasklists plugin, so `- [ ]` ships a literal
"[ ]" to readers (render_lint **L13** hard-vetoes it, 2026-07-07).

## Pro tips for each step (~600-800w)
Expanded guidance per step.

## Common mistakes (~300-400w)
What goes wrong + how to avoid.

## What to do if you miss a step (~200w)

## Downloadable version (~100w)
Link to PDF/printable version.

## FAQ (3-5)

## References (≤6)
```

## Word budget (2500-3000w target)

| Section | Words | % |
|---|---|---|
| TL;DR + before | 350 | 12 |
| Checklist items | 600 | 22 |
| Pro tips per step | 700 | 25 |
| Common mistakes | 350 | 13 |
| Recovery | 200 | 7 |
| Downloadable + FAQ + transitions | 600 | 22 |

## Required modifiers
- `tldr-first`, `mandatory-toc`, `featured-snippet-targets`
- `info-gain-prose` ≥1 (your test of the checklist — only if it really happened)

## Hard rules
1. Each item starts with action verb
2. Each item has measurable completion criterion
3. 8-15 items (under 8 = use mini-guide; over 15 = split)
4. Pro tips section adds depth
5. Common mistakes section mandatory
6. Downloadable version offered (boosts engagement)

## Schema additions
- `Article` base
- `HowTo` as `mainEntity` (NEVER as primary @type)
- `ItemList` for checklist items

## When to use vs how-to-guide vs problem-solution
- how-to: prose-heavy tutorial
- checklist: list-format actionable items
- problem-solution: starts with pain point

## Image slots
- Cover: checklist visualization (clipboard, checkmarks)
- Optional: screenshot of completed checklist

## Downloadable bonus

Checklist articles benefit hugely from a free PDF download:
- Email gate (lead gen)
- Or open access (link building)

## Voice + purpose
- Voice: `professional` or `casual` depending on audience
- Purpose: `general` (not marketing)

## Common pitfalls
- ❌ Items too vague ("Do good work")
- ❌ Items not measurable
- ❌ Random order (should be sequential)
- ❌ Missing pro tips depth
- ❌ No printable version
- ❌ Items overlapping or redundant
