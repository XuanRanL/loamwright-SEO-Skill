# Format × Image Style Mapping (24 × 12)

> Used by `image-prompt-designer` to auto-select visual style based on `format_id`.

| Format | Primary style | Secondary | Notes |
|---|---|---|---|
| listicle | editorial-photography | product-photography | National Geographic feel; varied subjects per item |
| how-to-guide | flat-illustration | isometric-illustration | Process clarity > photography |
| pillar-page | conceptual-photography | editorial-photography | Mix of overview + concept |
| comparison | product-photography | infographic-style | Side-by-side compositions |
| product-review | product-photography | lifestyle-photography | Hero + real-use shot |
| case-study | documentary-style | infographic-style | Behind-the-scenes + data |
| definition | flat-illustration | conceptual-photography | Concept clarity |
| checklist | minimalist | flat-illustration | Clean overview shots |
| news-analysis | dramatic-style | photojournalism | Topical impact |
| problem-solution | conceptual-photography | documentary-style | Problem visualization → resolution |
| roundup | editorial-photography | product-photography | Multi-subject grids |
| data-research | infographic-style | 3d-render | Data viz heavy |
| faq-knowledge | flat-illustration | minimalist | Clear, instructional |
| glossary-hub | flat-illustration | minimalist | Reference-book aesthetic |
| template-resource | minimalist | flat-illustration | Tool-focused |
| opinion | conceptual-photography | editorial-photography | Thought-provoking |
| personal-story | vintage-film | lifestyle-photography | Nostalgic, intimate |
| interview | lifestyle-photography | documentary-style | Portrait-focused |
| curated-roundup | minimalist | editorial-photography | Selection grid |
| level-guide | flat-illustration | isometric-illustration | Hierarchy visualization |
| shortlist-validation | minimalist | product-photography | Stripped-down picks |
| encyclopedic | conceptual-photography | flat-illustration | Wikipedia-meets-modern |
| multi-intent-hybrid | editorial-photography | conceptual-photography | Versatile |
| buyers-guide | product-photography | editorial-photography | Product + context |

## When multiple styles apply
- Cover image: use primary style
- Section image 1: primary or secondary
- Section image 2: secondary (variation)
- Section image 3: secondary or primary (back to primary if needed)
- Section images 4-5 (present at the default image_count of 6 — scripts/_core/image_policy.py): keep alternating secondary/primary; never two identical styles adjacent

## Industry adjustments

| Industry | Style adjustment |
|---|---|
| SaaS / B2B tech | Lean toward 3d-render, isometric-illustration, infographic |
| Fashion / lifestyle | Lean toward editorial, lifestyle, vintage-film |
| Food / hospitality | Lean toward lifestyle, editorial |
| Health / medical | Lean toward documentary, minimalist (less drama) |
| Finance | Lean toward minimalist, infographic, conceptual |
| Fitness / sports | Lean toward dramatic, lifestyle, documentary |
| Outdoor / adventure | Lean toward editorial (NatGeo), lifestyle |
| Education | Lean toward flat-illustration, isometric |
| News / journalism | Lean toward dramatic, documentary, photojournalism |
