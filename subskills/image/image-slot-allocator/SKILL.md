---
name: image-slot-allocator
description: Decide the article's image slots (brief.image_count, default 6 = 1 cover + 5 section images, max 8). Reads outline.json + format_id. Picks H2s to image based on per-format mapping in references/image/format-style-mapping.md. Triggered as Stage 27a of phase-publish image sub-pipeline.
allowed-tools: [Read, Write]
---

# Image Slot Allocator

> ⚠️ **NOT WIRED into the deterministic pipeline (2026-07-17 audit).** There is no
> `image-slot-allocator` stage in `scripts/pipeline/orchestrator.py`'s Stage table,
> nothing produces its declared `image_slots.json`, and `_match_image_slot_to_section`
> exists only as pseudo-code in `section-drafter/SKILL.md`. In the live pipeline the
> **image contract is: the per-section `image_slot: true` booleans in `outline.json`
> sections[], and `image-prompts.json` (slot_id source of truth).** The designer names
> slots `cover` + sequential `section_1|section_2|section_3` (see `agents/image-prompt-designer.md`),
> and `scripts/build/assemble.py` auto-injects `[IMAGE-SLOT-cover]` after the Abstract
> for `no_inline` projects. Do NOT rely on this file describing a running stage; it is
> a design doc for a stage that was never enabled (Rule 6). Wire it before referencing
> it as live, and if you do, note that its own spec uses sequential `section_{i+1}` ids.

Decides WHERE images go. Doesn't generate them (that's image-prompt-designer + openai-image-generator).

## Inputs

- `workspace/{task_id}/outline.json` — section structure
- `workspace/{task_id}/angle.json` — format_id
- `state.brief.image_count` — default 6 (1 cover + 5 inline; scripts/_core/image_policy.py, raised from 4 on 2026-08-17)

## Output

`workspace/{task_id}/image_slots.json`:

```json
{
  "slots": [
    {
      "slot_id": "cover", "purpose": "hero / featured image / OG card",
      "aspect_ratio": "16:9", "size": "3840x2160", "is_featured_image": true,
      "body_render": false,
      "h2_anchor": null, "after_paragraph": 0
    },
    {
      "slot_id": "section_1", "h2_anchor": "1-gloomis-nrx",
      "purpose": "showcase top pick", "aspect_ratio": "4:3", "size": "3264x2448",
      "is_featured_image": false, "body_render": true
    },
    ...
  ]
}
```

**Critical:** the cover slot has `body_render: false`. The drafter MUST NOT emit
`[IMAGE-SLOT-cover]` or `![cover](images/cover.png)` in the markdown body — WordPress
themes render the featured image at the top of the post automatically, and inlining the
cover in the body produces a visible duplicate.

The publisher (`wp_publisher.py`) defensively filters out images flagged
`is_featured: true` from body placeholder substitution as a backstop, but the cleanest
fix is to allocate the cover with `body_render: false` and never emit a body placeholder
for it in the first place.

## Allocation by format

Per `references/image/format-style-mapping.md` — the table lists each format's first three PRIORITY subjects; at the default `image_count` 6 there are 5 inline slots (`scripts/_core/image_policy.py`), so continue each format's pattern for slots 4-5:

| Format | Cover | Section 1 | Section 2 | Section 3 |
|---|---|---|---|---|
| listicle | overview hero | top pick (#1) | mid-list (#5) | methodology |
| how-to | concept overview | step 1 | mid step | result |
| pillar | overview | subtype A | core concept | future trends |
| comparison | split-screen | X strengths | Y strengths | verdict viz |
| review | hero product | features close-up | use case | verdict |
| case-study | scene setter | challenge viz | results chart | lessons learned |
| definition | abstract concept | type A | example | application |
| ... | (per catalog) | | | |

## Logic

```python
def allocate(outline, format_id, image_count=6):
    slots = [
        # Cover always first
        Slot(slot_id="cover", aspect="16:9", size="3840x2160",
             is_featured=True, h2_anchor=None, position="before-abstract"),
    ]
    
    # Pick image_count-1 section H2s based on format
    section_h2s = pick_section_h2s_for_format(outline.sections, format_id, n=image_count - 1)
    for i, h2 in enumerate(section_h2s):
        slots.append(Slot(
            slot_id=f"section_{i+1}",
            aspect="4:3", size="3264x2448",
            is_featured=False,
            h2_anchor=slugify(h2.text),
            position="after-h2-paragraph-1",
        ))
    
    return slots[:image_count]
```

## Handoff

`recommended_next_skill`: `image-prompt-designer`
