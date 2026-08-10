# AI Engine Optimization Matrix

> Different AI engines weight different signals. This matrix drives `subskills/optimize/geo-content-optimizer/` per-engine targeting.

---

## The 5 AI engines (2026)

1. **Google AI Overview (AIO)** — replaces SGE; appears in 19-31% of SERPs
2. **ChatGPT Search** — OpenAI's native search + browsing
3. **Perplexity** — purpose-built AI search engine
4. **Claude** — Anthropic's chat with search capability
5. **Gemini** — Google's chat (separate from AIO)

---

## Per-engine signal weighting

Higher weight = engine cares more about this signal.

| Signal | AIO | ChatGPT | Perplexity | Claude | Gemini |
|---|---|---|---|---|---|
| **Freshness** (dateModified <12mo) | 0.30 | 0.10 | 0.10 | 0.10 | 0.25 |
| **Authority** (backlinks, domain rating) | 0.25 | 0.30 | 0.20 | 0.30 | 0.25 |
| **Structure** (H2/H3, schema) | 0.20 | 0.20 | 0.20 | 0.25 | 0.20 |
| **Citations** (inline + References quality) | 0.15 | 0.25 | 0.35 | 0.20 | 0.20 |
| **Fact density** (numbers/200w) | 0.10 | 0.15 | 0.15 | 0.15 | 0.10 |

---

## Per-engine optimization tactics

### Google AI Overview (AIO)
**Priority**: Freshness > Authority > Structure
- Update articles every 6-12 months minimum
- Strong backlink profile (DA 30+)
- FAQ schema heavy (often quoted directly in AIO)
- HowTo schema (in fallback role; not primary citation source)
- Recent dateModified visible in HTML

**Format-fit**: how-to-guide / news-analysis / faq-knowledge / pillar-page

### ChatGPT Search
**Priority**: Authority > Citations
- Citation Capsules per H2 (Princeton GEO data)
- Tier-1 sources (peer-reviewed, .gov, .edu)
- ItemList schema for listicles (Wix 2026.3: 40.86% commercial citation)
- Validation pages (8 list sections, ≤10 word sentences — AirOps +26.9%)
- Entity-rich (Wikipedia-style content)

**Format-fit**: listicle / shortlist-validation / encyclopedic / pillar-page

### Perplexity
**Priority**: Citations > Authority
- Highest dependency on inline citations
- (Author, Year) format in body, not just References
- DOI links preferred over URLs
- "How we tested" methodology sections
- Original data (case studies, data research)

**Format-fit**: case-study / data-research / definition / pillar-page

### Claude
**Priority**: Authority > Structure
- Reviewers + Persons schema strong
- Higher word count tolerance (Claude reads deep)
- Opinion + reasoning > pure facts
- Personal voice / first-person experience valued
- Sources from established publications (NYT, Bloomberg)

**Format-fit**: product-review / case-study / opinion / personal-story / pillar-page

### Gemini
**Priority**: Balanced (no strong preference)
- Good schema implementation
- FAQ schema + Speakable
- Voice-friendly answers (Gemini powers Google Assistant)
- Multimodal-aware (images with good alt)
- Cross-language content benefits

**Format-fit**: how-to-guide / faq-knowledge / definition / level-guide

---

## Multi-engine targeting

When `state.brief.target_surfaces` contains multiple engines:

### chatgpt + AIO (most common)
- Citation Capsules + FAQ schema
- Tier-1 citations + fresh dateModified
- Listicle / pillar / how-to formats win both

### perplexity + claude (E-E-A-T heavy)
- Original data + first-person experience
- Documented methodology
- Case-study / data-research / opinion formats

### All 5 (broad coverage; most articles)
- Hit minimum viable for each signal
- Don't over-optimize for one engine
- Pillar pages naturally fit all

---

## Engine recognition status (per `ai_search_probe.py`)

For each (entity, engine) pair, track:
- `recognized`: engine knows the entity accurately
- `partial`: engine mentions but has factual gaps
- `unrecognized`: engine doesn't mention
- `confused`: engine mixes with another entity (HIGH RISK)

Target: progress from unrecognized → partial → recognized over 90-180 days.

Status improvements come from:
- More citations from authoritative pages
- Wikidata QID + Wikipedia entry
- Consistent entity naming across the web
- Original research that gets cited externally

---

## Failure mode: "AIO removed from query"

If `drift-detector` reports AIO citation lost for a query that previously cited our article:
1. Trigger `ai-overview-recovery` skill (4-phase playbook)
2. Diagnose: freshness / authority / structure / entity confusion
3. Surgical rewrite + re-publish
4. Re-probe at T+7/14/28

---

## How to use this matrix

In `subskills/optimize/geo-content-optimizer/`:
```python
target_engines = state.brief.target_surfaces  # e.g. ["chatgpt", "google-aio"]
weights = combine_weights(target_engines)  # blend matrix rows
optimizations = []
if weights["freshness"] > 0.20:
    optimizations.append("ensure dateModified within 6 months")
if weights["citations"] > 0.20:
    optimizations.append("add 2+ Tier-1 citations per H2")
if weights["structure"] > 0.20:
    optimizations.append("verify all schemas present")
...
```

This produces a prioritized to-do for the geo-content-optimizer to apply.
