# Surface Targeting (Phase 0 Strategy)

Before writing a single article, decide which **surface** the content is optimizing for. Different surfaces have different ranking signals, different reader expectations, different content formats.

## The 6 surfaces

| Surface | Reader | Ranking signal | Format that wins |
|---|---|---|---|
| 1. **Owned** | Direct site visitors | brand awareness + email signup | pillar-page / brand resource / template |
| 2. **Google organic SERP** | Search-intent visitors | E-E-A-T + technical SEO + backlinks | listicle / how-to-guide / definition |
| 3. **Google AIO (AI Overview)** | Generative AI snippet visitors | structured answer + freshness + entity richness | how-to / pillar / news-analysis with FAQ schema |
| 4. **ChatGPT / Perplexity / Claude / Gemini AI search** | LLM-search users | citations + structured data + 40-60w extractable blocks | shortlist-validation / encyclopedic / data-research |
| 5. **Reddit / Quora / niche community** | Community-search users | authentic voice + expert credentials | personal-story / opinion / interview |
| 6. **YouTube** | Video-search users | high view count + watch time | how-to / interview / review (NOT pure blog) |

## Pick BEFORE writing

The Phase 0 question — "which surfaces are we targeting?" — must be answered before format-selector runs.

```
brief.target_surfaces: ["owned", "google-organic", "google-aio", "chatgpt-search"]
                       │        │                │                  │
                       │        │                │                  └ format must be ChatGPT-citation-ready
                       │        │                └ FAQ schema mandatory; freshness ≤ 12mo
                       │        └ Tier-1 backlinks + E-E-A-T author
                       └ Brand voice ramps higher; less SEO compromise
```

## Surface decision matrix

For your brand, pick 2-4 surfaces (not all 6). Diluting attention across all 6 = mediocre on all 6.

| Brand type | Recommended surfaces |
|---|---|
| B2B SaaS | owned + chatgpt + perplexity + youtube |
| B2C ecom | google-organic + google-aio + reddit (niche) |
| Local service | google-organic + google-aio (local-pack) + reddit |
| Agency / consultancy | owned + chatgpt + youtube |
| Publisher / blog | google-organic + AIO + chatgpt + perplexity |
| Open source project | owned + chatgpt + youtube + community |

## Per-surface optimization (from `references/geo/ai-engine-matrix.md`)

### Google AI Overview (AIO)
- **Priority signals**: Freshness > Authority > Structure
- Update articles every 6-12 months
- Strong backlink profile (DA 30+)
- FAQ schema (often quoted directly in AIO)
- Recent dateModified visible in HTML
- Best formats: how-to-guide / news-analysis / faq-knowledge / pillar-page

### ChatGPT Search
- **Priority signals**: Authority > Citations
- Citation Capsules per H2 (40-60w self-contained)
- Tier-1 sources (peer-reviewed, .gov, .edu)
- ItemList schema for listicles
- Validation pages (8 list sections, ≤10 word sentences)
- Best formats: listicle / shortlist-validation / encyclopedic / pillar-page

### Perplexity
- **Priority signals**: Citations > Authority
- Highest dependency on inline (Author, Year) citations
- DOI links preferred over URLs
- "How we tested" methodology sections
- Original data (case-studies, data-research)
- Best formats: case-study / data-research / definition / pillar-page

### Claude (Anthropic chat)
- **Priority signals**: Authority > Structure
- Reviewers + Persons schema
- Higher word count tolerance (Claude reads deep)
- Opinion + reasoning > pure facts
- Personal voice / first-person experience valued
- Best formats: product-review / case-study / opinion / personal-story / pillar-page

### Gemini
- **Priority signals**: Balanced (no strong preference)
- Good schema implementation
- FAQ schema + Speakable
- Voice-friendly answers (Gemini powers Google Assistant)
- Multimodal-aware (images with good alt)
- Best formats: how-to-guide / faq-knowledge / definition / level-guide

### Reddit / Community
- **Priority signals**: Authenticity > Authority
- Personal voice (first-person)
- Expert credentials visible
- No marketing language
- Best formats: personal-story / opinion / interview (cross-posted as Reddit text post)

## Targeting impact on draft

Once surfaces are picked, they cascade into every downstream subskill:

```
brief.target_surfaces=["chatgpt", "google-aio"]
        ↓
format-selector: bias toward listicle + how-to (both surfaces favor)
        ↓
outline-architect: mandatory FAQ schema slot
                  mandatory citation capsules per H2
                  35-50w answer block after each H2
        ↓
section-drafter: ensure (Source, Year) citation pattern
        ↓
schema-generator: FAQPage + Article + BreadcrumbList
        ↓
quality-gate: 60-cap if no citation capsules
```

## Anti-pattern: targeting all 6

If `target_surfaces == "all"`:
- Article becomes generic
- E-E-A-T diluted (can't be expert at everything)
- Length explodes trying to satisfy all
- Schema bloated

Force pick 2-4 max.

## When to update target surfaces

- **Quarterly** review: which surfaces drove most traffic? Refresh targeting based on actual GSC + AI citation data
- **Per-cluster** override: a single cluster can have different targets than the project default
- **Per-article** override: edge cases (e.g., a YouTube-companion blog post should target `youtube + owned`)

## See also

- `references/geo/ai-engine-matrix.md` — per-engine signal weights
- `references/seo/blog-formats-2026.md` — 24 formats and their surface fit
- `subskills/research/surface-targeting/SKILL.md` — Phase 0 skill
- `subskills/plan/format-selector/SKILL.md` — format decision tree
