# Level Guide Template

> Format ID: `level-guide`. Beginner / Intermediate / Advanced structured tutorial.
> Strong for AI engines: clear progression hierarchy + 28-45w answer blocks.

## Default structure

```
{Topic}: Complete Guide from Beginner to Advanced ({Year})

## TL;DR (40-60w)
Path overview: Start at Level 1; Level 5 = expert.

## Who this guide is for (~150w)
- Level 1: complete beginners (no prior knowledge)
- Level 3: intermediate (has basics)
- Level 5: advanced (looking to refine)
Choose your starting level.

## Prerequisites (~150-200w)
What you need before starting Level 1.

## Level 1: Foundations (~500-700w)
**Goal**: {specific outcome}
**Time investment**: ~2 hours
**You'll learn**: {3 bullet points}

Steps + concepts + 1 worked example.

## Level 2: Building blocks (~500-700w)
Same structure. Builds on Level 1.

## Level 3: Real applications (~600-800w)
Same structure. First real-world use.

## Level 4: Advanced techniques (~600-800w)
Same structure. Less-common methods.

## Level 5: Mastery (~500-700w)
Same structure. Edge cases + optimization.

## How to know you've mastered each level (~250w)
Self-assessment criteria.

## Common pitfalls at each level (~300w)
What gets people stuck.

## Where to go next (~200w)
Pointers to deeper resources after this guide.

## FAQ (5-7)

## References (≤10)
```

## Word budget (5000-6000w target)

Each level ~600-700w × 5 levels = 3000-3500w + framework + FAQ + extras.

## Required modifiers
- `tldr-first`, `mandatory-toc` (jump to your level)
- `citation-capsules-per-h2` ✓ (each level intro = capsule)
- `info-gain-prose` ✓ ≥2
- `featured-snippet-targets` ✓ (each "Level X" intro = snippet candidate)

## Hard rules
1. Each level has explicit prerequisites
2. Each level has measurable outcome
3. Each level has time estimate
4. Progressive difficulty (don't repeat Level 1 concepts in Level 3)
5. Self-assessment included
6. Common pitfalls section mandatory

## Schema additions
- `Article` base
- `Course` schema (Google supports for educational content)
- `HowTo` as mainEntity (NEVER as primary @type)
- `FAQPage`

## When to use vs how-to-guide vs pillar
- how-to-guide: single task, neutral instruction
- level-guide: progression-oriented multi-task
- pillar: broad coverage of a topic (no progression)

## Image slots
- Cover: progression diagram (Level 1 → 5)
- Section per level: concept illustration OR screenshot

## Best for verticals
- Coding / programming
- Skill-based crafts (woodworking, photography)
- Software platforms (Salesforce, AutoCAD)
- Languages (English learning)
- Cooking technique mastery

## Common pitfalls
- ❌ Levels not distinct (Level 2 = repeat of Level 1)
- ❌ Wildly variable time investments (Level 1 = 1hr; Level 5 = 100hrs)
- ❌ Missing self-assessment criteria
- ❌ No pitfalls section
- ❌ Too many levels (>5 = use pillar instead)
