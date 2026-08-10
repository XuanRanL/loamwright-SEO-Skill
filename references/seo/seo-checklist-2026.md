# 2026 SEO + GEO Publishing Checklist

> The complete pre-publish gate. All items must pass for green-light. Per `subskills/optimize/quality-gate-*` skills.

---

## ✅ Structural (10 items)

| # | Check | Hard requirement | Script |
|---|---|---|---|
| S1 | TL;DR in first 540 words | yes (AI grounding zone) | markdown_structure_check.py |
| S2 | Unique Abstract section | exactly 1 | markdown_structure_check.py |
| S3 | Unique Key Takeaways (4-7 items) | yes | markdown_structure_check.py |
| S4 | Unique Table of Contents | yes | markdown_structure_check.py |
| S5 | Unique References section | yes | markdown_structure_check.py |
| S6 | Article ends at References | nothing after | markdown_structure_check.py |
| S7 | ≥2 markdown tables | yes | markdown_structure_check.py |
| S8 | ≥1 table in front 50% of article | yes | markdown_structure_check.py |
| S9 | All H2s have anchor `id="..."` | for ToC navigation | anchor_link_builder.py |
| S10 | Paragraph length ≤150 words | each paragraph | markdown_structure_check.py |

## ✅ On-Page SEO (10 items)

| # | Check | Hard requirement | Script |
|---|---|---|---|
| O1 | Title 50-65 characters | yes | title_validator.py |
| O2 | Title contains primary keyword exactly once | yes | title_validator.py |
| O3 | Title contains ≥1 Power Word | yes | title_validator.py |
| O4 | Title contains ≥1 digit | yes | title_validator.py |
| O5 | Slug ≤40 chars, contains keyword | yes | slug_generator.py |
| O6 | Meta description 120-160 chars | yes | (in meta-builder skill) |
| O7 | Primary keyword density 0.8-1.3% | yes | keyword_density.py |
| O8 | Secondary keywords density 0.3-0.7% each | yes | keyword_density.py |
| O9 | Featured image with alt text | yes | (in publisher) |
| O10 | Word count ≥ target × 0.95 | yes | word_count.py |

## ✅ E-E-A-T (15 items)

| # | Check | Required | Notes |
|---|---|---|---|
| E1 | Author byline visible | yes | Real name preferred |
| E2 | Author bio with credentials | yes | Person schema |
| E3 | Last updated date | yes | dateModified |
| E4 | ≥3 sources are Tier-1 (peer-reviewed / .gov / .edu) | yes | References section |
| E5 | All claims have inline citations | yes | (Author, Year) format |
| E6 | No fabricated statistics | yes | fact-checker verified |
| E7 | Methodology section if data-driven | conditional | data-research / case-study formats |
| E8 | Information gain expressed as plain prose (bracket markers RETIRED) | ≥2 signal types per article | core_eeat_scorer.py O01/O02 |
| E9 | Real first-hand experience in plain prose — only if it truly exists (never fabricate) | ≥1 if applicable | core_eeat_scorer.py O03/O04 |
| E10 | YMYL: affiliate disclosure present | only if commercial | (in body) |
| E11 | Affiliate / sponsored disclosure (FTC compliance) | only if commercial | conditional |
| E12 | About page link in header/footer | site-wide | not per-article |
| E13 | Contact info visible | site-wide | not per-article |
| E14 | HTTPS only | site-wide | tech-stack check |
| E15 | Privacy policy linked | site-wide | tech-stack check |

## ✅ AI Citation (GEO) (10 items)

| # | Check | Required | Notes |
|---|---|---|---|
| G1 | Citation Capsule in ≥80% of H2 sections | yes | citation_capsule_lint.py |
| G2 | Each Capsule is 40-60 words | yes | same lint |
| G3 | Each Capsule has specific data point | yes | same lint |
| G4 | Information gain as plain prose ≥2 distinct signal types (markers RETIRED) | yes | core_eeat_scorer.py O01/O02 |
| G5 | FAQ section with ≥5 questions from research.paa | yes | (in section-drafter) |
| G6 | FAQPage schema in JSON-LD | yes | schema-generator |
| G7 | Article schema with author Person | yes | schema-generator |
| G8 | Specific factual statements (≥1 per 200w) | yes | (in section-drafter) |
| G9 | No "in today's fast-paced world" openers | enforce zero | ai_tells_detector.py |
| G10 | LLM crawler robots.txt allows GPTBot/ClaudeBot/PerplexityBot | site-wide | (configurable) |

## ✅ Technical (10 items)

| # | Check | Required | Notes |
|---|---|---|---|
| T1 | JSON-LD @graph in <head> | yes | schema-generator |
| T2 | Article OR BlogPosting type | yes | schema-generator |
| T3 | Organization schema present | site-wide | schema-generator |
| T4 | Person schema for author | yes | schema-generator |
| T5 | BreadcrumbList schema | yes | schema-generator |
| T6 | No deprecated schema types (HowTo, SpecialAnnouncement, etc.) | enforce | schema_validator.py |
| T7 | Canonical URL set | yes | (in meta + publisher) |
| T8 | Open Graph title + description + image | yes | meta-builder |
| T9 | Twitter Card markup | yes | meta-builder |
| T10 | All external links target=_blank rel=noopener nofollow | yes | markdown_to_html.py |

## ✅ Style (5 items)

| # | Check | Required | Notes |
|---|---|---|---|
| ST1 | Banned word hits = 0 | enforce | banned_word_lint.py |
| ST2 | AI Tells (43 patterns) ≤5 distinct | yes | ai_tells_detector.py |
| ST3 | Em-dash count (U+2014) = 0 | enforce | em_dash_audit.py |
| ST4 | Curly quotes = 0 | enforce | curly_quote_audit.py |
| ST5 | AI-Slop score < 20 | yes | ai_slop_score.py |

## ✅ Images (8 items)

| # | Check | Required | Notes |
|---|---|---|---|
| I1 | Cover image 16:9 (1536×1024 or 1792×1024) | yes | (image-slot-allocator) |
| I2 | 3 section images at planned slots | yes | (per format) |
| I3 | All images have alt text ≤125 chars | yes | image-curator |
| I4 | SEO filenames (kebab-case + keyword) | yes | image_seo_filename.py |
| I5 | WebP format with PNG fallback | yes | webp_converter.py |
| I6 | Srcset variants (480w/768w/1024w or 1536w) | yes | srcset_generator.py |
| I7 | File size <200KB per variant | yes | image_compressor.py |
| I8 | EXIF stripped | yes | exif_stripper.py |

---

## How to use this checklist

1. **During drafting**: section-drafter agent self-checks S/O/E/G/ST items
2. **At quality gate**: parallel run of all linters + scorers → quality.json
3. **Pre-publish**: humans (or independent-reviewer agent) confirm I and T items
4. **Post-publish**: monitor phase tracks E14/E15 site-wide health

## Veto rules (cap or block)

Per `references/geo/core-eeat-80.md` Vetoes:
- **T04 (fabricated statistic)** → cap final score at 60, suggest manual review
- **C01 (fabricated citation)** → BLOCKED, cannot publish
- **R10 (prompt injection / unsafe HTML)** → BLOCKED
- **T03 (missing affiliate disclosure on commercial)** → BLOCKED for FTC compliance
- **T05 (missing E-E-A-T)** → cap at 60
- **T09 (broken schema)** → cap at 70

Cap algorithm: 1 veto → `final = min(raw, cap_value)`; 2+ vetoes → verdict `BLOCKED`.

---

## See also

- `references/geo/core-eeat-80.md` (E-E-A-T 80-item detail)
- `references/geo/cite-framework-40.md` (CITE 40-item detail)
- `references/seo/citation-capsules-princeton.md` (Capsule design)
- `scripts/validate/core_eeat_scorer.py` (automated scoring)
- `scripts/validate/cite_scorer.py` (automated scoring)
