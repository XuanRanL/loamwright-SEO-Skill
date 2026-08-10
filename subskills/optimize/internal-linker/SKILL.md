---
name: internal-linker
description: Resolve [INTERNAL-LINK: anchor → target] placeholders, inject brand internal links from projects/{slug}/internal-links-map.md, manage internal link density per word count.
allowed-tools: [Read, Write, Edit, Task]
---

# Internal Linker

Injects internal links at brand-specified anchor positions.

## Density formula (per claude-blog)

| Word count | Internal links target |
|---|---|
| <1000 | 3-5 |
| 1000-2000 | 5-7 |
| 2000-3000 | 7-10 |
| Pillar (3000+) | 10-15 |

## Workflow

```
1. Read projects/{slug}/internal-links-map.md (curated)
   Format: anchor_text → target_url (with intent: nofollow / sponsored / dofollow)
2. Read draft.md, find [INTERNAL-LINK: anchor → target] placeholders
3. Replace each placeholder with proper [anchor](url) markdown
4. Add brand internal links based on map matches (LLM picks natural positions)
5. Verify density within target range
6. Run scripts.validate.link_resolver on all internal links (HEAD check)
7. Spawn linker agent for nuanced anchor-text decisions
```

## Anchor text rules
- Natural, descriptive (not "click here")
- Vary across links to same destination
- Mix branded + descriptive anchors
- No keyword stuffing
- No duplicates within same paragraph

## See also
- `agents/linker.md` (executes nuanced edits)
- `references/seo/internal-linking-formulas.md`
