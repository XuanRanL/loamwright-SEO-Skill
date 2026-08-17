# Pillar Page Template

> Format ID: `pillar-page`. Yext 680M citations data: 3.2× AI citation rate vs disconnected.
> Used by `outline-architect` when `format_id == "pillar-page"`. ≥3000 words required.

## Default structure

```
{Distinctive title — avoid SERP-clone patterns like "The Complete Guide to X for {year}".
 Lead with the article's actual thesis or a specific number. Must contain primary keyword
 exactly once, a power word, and a digit. See topic-angle-selector for anti-homogenization rules.}

## Abstract (150-280w)  ← ALWAYS the first body H2. Merges what older docs called "TL;DR" and "Abstract".
Paragraph 1 (≤120w): the article's thesis in one tight paragraph. State the central distinction or
finding. This is what AI search engines extract and what readers skim first.
Paragraph 2 (≤160w): who this guide is for, what they'll learn, how it's organized. Reference key
sections by name (e.g. "See §N for the buyer framework"). This paragraph anchors comprehension.

Do NOT emit a separate `> **TL;DR.** ...` blockquote above the Abstract. Older templates and
existing drafts may still show that pattern — it has been deprecated in favor of a single
`## Abstract` H2 because (a) AI search engines weight H2-structured content higher than
blockquotes, (b) the publisher's article CSS styles `h2#abstract + p` as a callout, and
(c) consolidating "summary at top" reduces redundancy with Key Takeaways immediately below.

## Key Takeaways (4-7 bullets, each ≤20w)
The most important conceptual points. Each bullet leads with a bolded clause that summarizes
the bullet's claim — the publisher's CSS treats `<strong>` at the start of each <li> as the
emphasis anchor.

## Table of Contents
Auto-gen; links to all 8-12 H2s. Must include Abstract as #1 and References as the last entry.

## What is {subject}? (~400w)
Definition + history + why it matters now.
Citation Capsule HERE (this is the most-cited section).

## How {subject} works (~600w)
Mechanism / process.
≥1 chart or diagram.

## Types of {subject} (~600w)
### Type A
### Type B
### Type C

Link each type to a SPOKE article: [INTERNAL-LINK: Type A → /spokes/type-a]

## Benefits and drawbacks (~500w)
### Benefits
3-5 specific, measurable benefits with data.

### Drawbacks
3-4 honest limitations.

Citation Capsule.

## Choosing the right {subject} (~700w)
Decision framework:
- Factor 1 (criteria + how to evaluate)
- Factor 2
- Factor 3

Comparison table (3+ items).

## How to get started (~400w)
Brief tutorial. Don't replicate a how-to-guide spoke; just enough to point them to the right next step.
[INTERNAL-LINK: detailed how-to → /how-to-guide/full-tutorial]

## Best {subject} for different use cases (~500w)
Tease the listicle spoke.
[INTERNAL-LINK: full ranking → /listicle/best-X]

## Common mistakes to avoid (~400w)
Top 5-7 mistakes, each ~50-70w.

## Future trends ({year} outlook) (~400w)
Forward-looking. Cite expert opinions / data.
original data or original analysis, in plain prose here.

## FAQ (10-15 questions, ≥60% from research.paa)

## Conclusion (~200w)
Synthesis. The 2-3 most important things to remember.

## Further reading (4-7 internal spoke links)
Curated list of related deep-dives. THIS IS THE PILLAR-SPOKE LINKAGE.

## References
APA 7, ≤10-15 entries.
```

## Word budget allocation (4500w minimum, 6000-8000w typical)

| Section | Words (6000w target) | % |
|---|---|---|
| TL;DR + Abstract + Takeaways | 400 | 7 |
| Definition + History | 400 | 7 |
| Mechanism | 600 | 10 |
| Types | 600 | 10 |
| Benefits + Drawbacks | 500 | 8 |
| Decision framework | 700 | 12 |
| Getting started + Use cases | 900 | 15 |
| Mistakes + Trends | 800 | 13 |
| FAQ | 800 | 13 |
| Conclusion + Further reading + Refs | 300 | 5 |
| **Total** | **6000** | 100 |

## Required modifiers

- `tldr-first` ✓
- `citation-capsules-per-h2` ✓ (5+ capsules, more than other formats)
- `mandatory-toc` ✓
- `info-gain-prose` ✓ (≥3, more than other formats — pillars need depth)
- `strong-eeat-signals` ✓ (pillars rank on E-E-A-T)

## Internal linking strategy (KEY for pillar)

Per claude-blog research (Yext data):
- 7+ internal links to spokes minimum (more if spokes exist)
- 12+ internal links if 3000-4000w
- 15+ if 5000+

Spoke types to link:
- Listicle: "Best X for {persona}"
- How-to: "How to {action}"
- Comparison: "X vs Y"
- Case study: "How {customer} achieved {result}"
- Definition: "What is {component}"

## Schema additions

- `Article` (NOT `BlogPosting` — pillar deserves Article)
- `mainEntity: {@type: "Thing", name: "X"}` (the central concept)
- `mentions: []` (linked spokes as Things)
- `FAQPage`
- `BreadcrumbList`
- `Organization` + `Person` (author)

## Image slot allocation

- **Cover (`body_render: false`)**: concept / overview hero (16:9, 1536×1024). Used as `featured_media` ONLY — WordPress themes render the featured image at the top of the post automatically, so the cover MUST NOT appear as an inline figure in the post body. Drafter must not emit `[IMAGE-SLOT-cover]` or `![cover](images/cover.png)` in the body. The publisher defensively filters out any `is_featured: true` image from the body, but the drafter should not require that fallback.
- Section 1 (4:3, 1024×1024): types diagram (infographic style) — appears inline after the relevant H2.
- Section 2 (4:3, 1024×1024): decision framework visual (table or chart) — inline.
- Section 3 (4:3, 1024×1024): case-study or trend visual — inline.
- Slots 4-5 (the default `image_count` 6 → 5 inline slots; `scripts/_core/image_policy.py`): continue the subject pattern above with distinct, non-duplicative scenes for further key sections

Section figures are rendered as Gutenberg `<!-- wp:image -->` blocks with `<figcaption>` populated from the image's caption metadata field. All four media-library fields (title, alt_text, caption, description) MUST be populated at upload time — the publisher reads these from `workspace/{task}/image_metadata.json`.

## Common pitfalls

- ❌ Pillar that's actually a listicle (no decision framework, no internal linking)
- ❌ Too few internal links to spokes (waste of pillar status)
- ❌ Overlap with spokes (pillar should overview; spokes should drill down)
- ❌ Stale data (pillars rank on freshness; update annually)
- ❌ <3000 words (Google ignores as pillar; treats as regular post)
