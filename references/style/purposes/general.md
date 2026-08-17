# Purpose: General Blog Article

> Default purpose for SEO blog posts. Pair with voice from `references/style/voices/`.

## Goal hierarchy

1. **Primary**: Satisfy search intent — reader's question answered fully within the article
2. **Secondary**: Earn AI engine citation (ChatGPT, Perplexity, Google AIO, Claude, Gemini)
3. **Tertiary**: Convert reader to next action (subscribe, click, buy) — soft, not pushy

## Structural template (overrides format-specific templates if conflict)

```
Title (H1)
TL;DR (40-60 words, in first 540 words — AI grounding zone)
Abstract (120-180 words)
Key Takeaways (4-7 bullet items, ≤20 words each)
Table of Contents (auto-generated, links to H2)
[Body — format-specific structure goes here]
FAQ (5-10 questions, ≥60% from research.paa)
Conclusion (no "In conclusion"; end with action recommendation)
References (APA 7, ≤10 entries, all link-resolvable)
```

## Per-H2 requirements

Each H2 section must contain:
- ≥1 **Citation Capsule** (40-60 words AI-quotable self-contained block)
- ≥0.95% primary keyword density (sectional)
- ≤150-word paragraphs (split if longer)
- At least one specific data point (year, number, %, $, source)

Every 2,000-word article must contain ≥2:
- **Information Gain Markers**: `original data (plain prose)` / `real first-hand experience (plain prose)` / `original analysis (plain prose)`

## What this purpose AVOIDS

- ❌ Long product pitches in body (relegate to single CTA)
- ❌ Affiliate spam (one CTA max in middle, one at end)
- ❌ Self-referential text ("In this article, we will explore...")
- ❌ Comprehensive overview openings
- ❌ Question-format every H2

## CTA placement

Per claude-blog research data:
- **Single CTA**: +266% conversion vs multiple
- **Centered (middle of article)**: +682% vs sidebar
- Place ONE primary CTA at 30-40% article mark
- Place secondary CTA in conclusion (optional, soft)
- Never above the fold (looks like ad)

## Visual elements

- **Tables**: ≥2 per article, at least one in front 50%
- **Images**: 1 cover (16:9) + `image_count − 1` inline (default 6 total → 5 inline; scripts/_core/image_policy.py; varies by format/brief)
- **Charts**: Optional, use for comparison data
- **Video embed**: Optional, only if relevant + adds value (don't embed for engagement metrics)

## Output format priority

For users who pasteboard to CMS:
- Primary output: `final.html` (plain HTML, WP-friendly)
- Secondary: `final.md` (markdown, for editing)
- Both saved to `workspace/{task_id}/`

## Reading level

- Default: Grade 10 (Flesch 60)
- Override per persona (from `projects/{slug}/personas/`)
- Use `scripts/lint/reading_level.py` (planned; for now `flesch_score()` in word_count.py)

## Voice modulation

- 10-15% first-person (default voice = professional × general)
- Override for case-study (more 1st person), how-to (more 2nd person)
- Avoid: exclamation points, "Whether you're a beginner or pro..."

## See also

- `references/style/voices/professional.md` (default voice pair)
- `references/seo/blog-formats-2026.md` (format-specific Body structure)
- `references/seo/cta-placement-data.md` (CTA placement evidence)
- `references/seo/seo-checklist-2026.md` (publishing checklist)
