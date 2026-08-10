---
name: citation-capsule-builder
description: After section-drafter, verifies each H2 has a Citation Capsule (40-60 word AI-quotable block). If missing, generates one. Princeton GEO requirement.
allowed-tools: [Read, Write, Edit]
---

# Citation Capsule Builder

Ensures Princeton GEO compliance: every content H2 has a 40-60 word self-contained quotable block.

## Featured-snippet duty (absorbed v3.35)

The standalone `featured-snippet-optimizer` subskill is RETIRED (Ahrefs 2025: FS fell
18%→8%, 83% replaced by AI Overviews — and both select the SAME 40-60w extractive
shape this stage already writes). This stage inherits its one distinct duty:
**sections `outline.json` marks `is_featured_snippet_target: true` get the most
answer-first capsule** — declarative first sentence, a specific number, no hedging.
Evidence: `references/seo/serp-feature-value-2026.md` §1.

## Workflow

```
1. Read all sections/*.json
2. For each section without citation_capsule field:
   - Read section markdown
   - Extract specific data point (number/year)
   - Generate 40-60 word self-contained paragraph
   - Insert at section end (preferred) or beginning
3. Run scripts.lint.citation_capsule_lint to verify ≥80% H2 coverage
4. Update section JSON with capsule field
```

## Validation
```bash
python -m scripts.lint.citation_capsule_lint workspace/{task}/draft.md --json
```

Pass = coverage ≥80% of content H2s (excludes References, ToC, Takeaways).

## See also
- `references/seo/citation-capsules-princeton.md` (design patterns)
- `scripts.lint.citation_capsule_lint`
