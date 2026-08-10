---
name: meta-builder
description: Builds final SEO meta package (title / slug / excerpt / focus_keyphrase / tags / categories / image_search_keywords / JSON-LD schema_jsonld). Conforms to WordPress + Yoast fields. Uses title from angle.json + content from final draft. Use after humanizer + before publish.
allowed-tools: [Read, Write, Bash]
---

# Meta Builder

Final assembly of SEO metadata for WordPress / any CMS.

## Inputs

- `angle.json` (title, slug_draft, persona)
- `draft.md` (final humanized + linked draft)
- `outline.json` (FAQ count, sections)
- `state.brief` (primary_keyword, secondary_keywords)
- `projects/{slug}/business-context.json` (brand, locale, industry)

## Output

`workspace/{task_id}/meta.json` per `schemas/meta.schema.json`.

## Build

```python
# Titles — both fields come pre-validated from topic-angle-selector (2026-06-16 split).
# See docs/title-optimization-plan-2026-06-16.md.
seo_title = angle.seo_title    # short <title> / rank_math_title / og:title (51–60 chars)
title     = angle.h1           # long human display title → WordPress post title (renders as <h1>)
register  = angle.register     # b2b_technical | b2b_procurement | dtc_celebration | dtc_grief | ecommerce | default
# Back-compat: if an older angle.json only has `title`, treat it as the h1 and derive a short
# seo_title from it (front-load the primary keyword, 51–60 chars, drop any (year) suffix).

# Slug
bash: python -m scripts.build.slug_generator --title "{title}" --primary "{primary_keyword}" --max 40

# Excerpt (120-160 chars, contains primary_keyword 1x)
# Generate via LLM from draft.md first paragraph + key takeaway
excerpt = llm_generate(draft.tldr + draft.first_paragraph, max_chars=160)

# Focus keyphrase = primary keyword
focus_keyphrase = state.brief.primary_keyword

# Meta description (Yoast) = excerpt or shorter variant
meta_description = excerpt[:155]

# Tags (5-10) — derived from secondary keywords + semantic clusters
tags = ", ".join(state.brief.secondary_keywords[:5] + research.semantic_clusters[:5])

# Categories (1-3)
# Pick from research.topic_clusters or business-context.default_categories
categories = business_context.default_categories or [derive_from_content]

# Image search keywords (3) — each contains primary_keyword
image_search_keywords = [
    f"{primary_keyword} 2026",
    f"best {primary_keyword}",
    f"{primary_keyword} {target_locale_phrase}"
]

# JSON-LD @graph
# Delegate to schema-generator skill (or use schema_jsonld_builder.py)
bash: python -m scripts.build.schema_jsonld_builder \
    --type Article \
    --title "{title}" \
    --url "{url}" \
    --published "{datetime_now}" \
    --modified "{datetime_now}" \
    --author "{author_name}" \
    --image-url "{cover_image_url}" \
    --primary-keyword "{primary_keyword}" \
    --format-id {angle.format_id} \
    --json
```

## Validation

Validate the **`seo_title`** (not the long `title`/h1), passing the register and the h1 so
alignment + number-preservation are checked:

```bash
python -m scripts.validate.title_validator "{seo_title}" \
    --primary "{primary_keyword}" --register "{register}" --h1 "{title}" --json
```

Must have `all_passed: true` (no hard issues). Hard fails: `seo_title` >65 / <30 chars, primary
keyword missing, a number in `seo_title` absent from the h1, a register-banned term (e.g. a power
word in `dtc_grief`, hype word in `b2b_*`). Title Case and `(year)`/`[year]` suffixes are advisory
`warnings[]`, NOT hard fails.
**Power word and digit are NO LONGER required** — do not regenerate just to add them.

## OG + Twitter

Generate alternative title/desc for social if longer/shorter formats work better:
```
og_title = title (or shortened to 95 chars)
og_description = excerpt
og_image_url = cover image URL (from image upload step)
twitter_card = "summary_large_image"
```

## Output example

```json
{
  "title": "The 7 best 1000 watt LED grow lamps for 2026: commercial picks tested on efficiency, coverage, and HPS-replacement cost",
  "seo_title": "7 best 1000 watt LED grow lamps: HPS-replacement tested",
  "register": "b2b_technical",
  "slug": "best-1000-watt-led-grow-lamps",
  "excerpt": "After testing 23 rods on 87 trips, here are 10 best fishing rods for 2026 with sensitivity ratings, prices, and our top picks for every budget.",
  "meta_description": "After testing 23 rods on 87 trips, here are 10 best fishing rods for 2026...",
  "focus_keyphrase": "best fishing rods 2026",
  "focus_keywords": "best fishing rods 2026, fishing rod 2026, saltwater fishing rod, fly fishing rod",
  "tags": "fishing rod, saltwater rod, fly fishing, gear review, 2026, beginner fishing",
  "categories": ["Buying Guides", "Fishing Gear"],
  "image_search_keywords": [
    "best fishing rods 2026",
    "fishing rod review 2026",
    "PNW fishing rod 2026"
  ],
  "schema_jsonld": {
    "@context": "https://schema.org",
    "@graph": [
      {"@type": "Article", ...},
      {"@type": "Organization", ...},
      {"@type": "Person", ...},
      {"@type": "BreadcrumbList", ...}
    ]
  },
  "og_title": "10 Best Fishing Rods for 2026",
  "og_description": "Data-backed tested picks for every budget.",
  "twitter_card": "summary_large_image"
}
```

## Handoff

`recommended_next_skill`: `schema-generator` (if not done inline) → then `quality-gate-core-eeat` + `quality-gate-cite` → ultimately `phase-publish`

## See also

- `scripts/build/slug_generator.py` (TODO M4)
- `scripts/build/schema_jsonld_builder.py` (TODO M4)
- `scripts/validate/title_validator.py`
- `schemas/meta.schema.json`
