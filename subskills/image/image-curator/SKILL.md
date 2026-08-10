---
name: image-curator
description: Produces image_metadata.json with all 4 WordPress media fields (title, alt_text, caption, description) per image slot. Runs AFTER image generation and BEFORE WordPress upload. Without this, captions and descriptions are empty in the media library and figcaptions never render in posts. Stage 27f of phase-publish image sub-pipeline.
allowed-tools: [Read, Write]
---

# Image Curator

Generates the 4-field metadata that the WordPress publisher requires on every image upload.
This is non-optional: without curated metadata, the publisher uploads images with empty
caption + description fields, and the media library record is SEO-incomplete.

## Inputs

- `workspace/{task_id}/outline.json` — section context for each slot
- `workspace/{task_id}/image_slots.json` — slot allocation (cover + sections)
- `workspace/{task_id}/image_prompts.json` — the prompts used to generate each image
- `workspace/{task_id}/research.json` — entity intelligence, primary keyword
- `projects/{slug}/brand/brand-config.json` — brand voice, banned competitor mentions

## Output

`workspace/{task_id}/image_metadata.json`:

```json
[
  {
    "media_id": null,
    "slot": "cover",
    "title": "{primary_keyword} {short_context}",
    "alt_text": "{accessibility-first description, ~120-180 chars, contains primary keyword naturally}",
    "caption": "{one short sentence visible under image, ~120-160 chars, reader-facing context}",
    "description": "{paragraph-length 400-1000 chars, includes technical entities + primary keyword + image's significance — populates the attachment page body}"
  },
  ...
]
```

`media_id` is null at this stage; the publisher populates it after the upload returns the WP media ID.

## The four-field discipline

All four fields are required on every image. Each serves a distinct SEO + accessibility purpose:

| Field | Length | Renders where | Purpose |
|---|---|---|---|
| **title** | ≤80 chars, kebab-case-derived | Media library list, attachment page `<title>` | Internal identification + AI image search |
| **alt_text** | 100–180 chars | `<img alt="">` | Screen readers + image SEO (primary keyword woven naturally) |
| **caption** | 100–180 chars | `<figcaption>` under image in post | Reader-facing context; also `ImageObject.caption` schema |
| **description** | 400–1000 chars | Attachment page body | Long-tail image-related queries; full technical context |

The publisher will refuse to publish if any image has empty caption or empty description
(blocking gate added in wp_publisher.py post-Stage 4).

## Tone & voice

All four fields must match `brand/brand-config.json` voice:
- Use brand-approved voice (NN-Group formality/humor/respectfulness/enthusiasm tuple)
- Reference primary keyword naturally (not stuffed)
- Include 1–2 technical entities from `research.json` in description (PPFD, DLC, OSRAM, etc.)
- Respect `ymyl_banned_phrases` (no health claims, no yield guarantees, etc.)
- Don't name `banned_competitors` in alt/caption/description

## Handoff

`recommended_next_skill`: `wordpress-publisher`. The publisher reads `image_metadata.json`
and passes all four fields to `wp_media.upload()` on each image upload.

## See also

- `scripts/wordpress/wp_publisher.py` (auto-loads image_metadata.json)
- `scripts/wordpress/wp_media.py:upload()` (accepts all 4 fields)
- `subskills/image/image-prompt-designer/SKILL.md` (preceding stage)
