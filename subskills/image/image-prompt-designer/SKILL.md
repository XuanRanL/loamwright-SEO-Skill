---
name: image-prompt-designer
description: Build shared Art Direction Prefix + per-slot 9-field prompts for 4 images. Uses Strategy A (shared prefix; per-slot variation). Reads brand-identity, brand-config, format_id. Produces image-prompts.json for openai-image-generator. Stage 27b.
allowed-tools: [Read, Write, Bash]
---

# Image Prompt Designer

Builds AI image prompts using Strategy A (shared Art Direction Prefix for visual consistency across 4 images).

## Inputs

- `workspace/{task_id}/image_slots.json`
- `projects/{slug}/brand-identity.json` (colors, founded, mission)
- `projects/{slug}/brand-config.json` (voice_pair, industry, target_locale)
- `workspace/{task_id}/angle.json` (format_id, hook)
- `references/image/style-presets.md` — 12 visual styles
- `references/image/format-style-mapping.md` — 24 format × style mapping
- `references/image/negative-prompts.md` — universal + category negatives

## Output

`workspace/{task_id}/image-prompts.json` — ⛔ `prompts` MUST be a JSON **array** of
objects (each with a `slot_id`), NEVER an object keyed by slot_id. The dict-keyed shape
silently broke chart-render, real-photo sourcing, the placeholder lint, and the publish
gate on 2026-06-29; the schema-validate hook now blocks a dict-shaped write.

```json
{
  "art_direction": {
    "visual_style": "editorial documentary photography, National Geographic 2026 aesthetic",
    "color_signature": "primary #FF8C00, secondary #2E5B7A, accent natural earth tones",
    "lighting": "golden hour or soft natural daylight",
    "mood": "competent, focused, aspirational",
    "camera_specs": "35mm lens, f/4-f/5.6",
    "universal_negatives": "no text overlays, no watermarks, no AI face tells..."
  },
  "prompts": [
    {
      "slot_id": "cover",
      "subject": "Single male angler casting a fly fishing rod over a Pacific Northwest river",
      "composition": "medium-wide shot, rule of thirds, river leading line from right",
      "lighting_note": "golden hour backlight from camera right, soft fill from river reflection",
      "mood_note": "contemplative, peaceful, aspirational",
      "aspect_ratio": "16:9",
      "size": "3840x2160",
      "negative_prompt": "no logos, no stock-photo poses",
      "alt_text_seed": "Expert angler demonstrating proper fly fishing technique at golden hour",
      "filename_seed": "best-fishing-rods-2026-pnw-angler-cover",
      "compiled_prompt": "[ART DIRECTION — applies to all images...]\n[THIS IMAGE]\nSubject: ..."
    },
    ...
  ]
}
```

## Workflow

```python
# Load inputs
brand = read("projects/{slug}/brand-identity.json")
config = read("projects/{slug}/brand-config.json")
slots = read("image_slots.json")
angle = read("angle.json")

# Build shared Art Direction (Strategy A)
art_direction = build_art_direction(
    primary_color_hex=config.primary_color,
    secondary_color_hex=config.secondary_color,
    accent_color_hex=config.accent_color,
    format_id=angle.format_id,
    voice_pair=config.voice_pair,
    industry=config.industry,
)

# For each slot, ask LLM to design subject + composition + mood
prompts = []
for slot in slots:
    spec = llm_design_per_slot(
        slot=slot,
        article_title=angle.title,
        section_context=outline.sections[slot.h2_anchor],
        art_direction=art_direction,
    )
    
    # Compile final prompt with shared prefix
    compiled = compile_prompt(spec, art_direction)
    spec["compiled_prompt"] = compiled
    prompts.append(spec)

# Save
write("image-prompts.json", {"art_direction": art_direction, "prompts": prompts})
```

## Use script

```bash
python -m scripts.openai.art_direction_compiler \
    --primary-color "{brand.primary_color}" \
    --secondary-color "{brand.secondary_color}" \
    --format-id "{angle.format_id}" \
    --voice-pair "{config.voice_pair}" \
    --industry "{config.industry}" \
    --prompts-file image_slots_with_specs.json \
    --json
```

## Cost

1 LLM call (Claude Opus) ~$0.05 to design all 4 prompts together.

## Handoff

`recommended_next_skill`: `openai-image-generator` (submits Batch API)
