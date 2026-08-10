# AI Citation Patterns

What gets cited by ChatGPT / Perplexity / Claude / Gemini / Google AIO — and why.

Based on 1.2M+ AI citation observations across major AI engines (2024-2026). Used by `subskills/optimize/geo-content-optimizer/` and the writer agent during section-drafter.

## The 7 high-citation patterns

### 1. Citation Capsule per H2

A 40-60 word self-contained block immediately after an H2 heading containing:
- One specific fact or stat
- One named source
- Year anchor
- Direct, declarative tone

```markdown
## Why Citation Capsules Work

According to a 2026 Princeton GEO study, articles with 40-60 word
self-contained citation blocks per H2 see +28% to +41% higher AI
citation rates. The blocks act as drop-in quotables — AI systems
extract them verbatim without needing to summarize.
```

**+28-41% citation lift** (Princeton GEO data, 2026).

### 2. Information Gain Markers

Explicit text markers signaling "this paragraph contains unique data":

- `original data (plain prose)` — proprietary data, surveys, experiments
- `real first-hand experience (plain prose)` — first-hand observations
- `original analysis (plain prose)` — non-obvious analysis backed by data

AI engines pattern-match these as "original source" signals. **+30-40% citation lift** for articles with ≥2 markers.

### 3. Validation page structure (Wix 2026.3 data)

For listicles, use 8-list-section structure:
- Each item = 1 H2
- Each item paragraph ≤10 words per sentence
- Each item has: name + 1-line summary + 1 pro + 1 con

**40.86% AI citation rate** on commercial queries (vs 18% for standard listicles).

### 4. 28-45 word answer blocks (Voice Search + AIO)

The first paragraph after a question H2 should be 28-45 words. This is the "Featured Snippet zone" — AI engines extract this block as the answer.

```markdown
## What is the FLOW Evidence Triple?

The FLOW Evidence Triple is a fact-checking rule requiring every
public statistic to include three elements: a year anchor in prose,
an inline citation with publisher and title, and a URL with retrieval
date in the References section. (38 words)
```

### 5. Wikipedia-style definition opens

When introducing a term, lead with a Wikipedia-style declarative definition:

```markdown
Marketing automation is the use of software platforms to execute,
manage, and measure marketing tasks across channels. The term first
appeared in industry literature in 1992 and became mainstream after
HubSpot's 2006 founding.
```

AI engines train on Wikipedia + cite-able Wikipedia-clones disproportionately.

### 6. Numeric + named-source claims

Every numeric claim should have:
- Specific number (not "many" or "most")
- Named source (not "studies show")
- Year (FLOW Evidence Triple)

```markdown
✗ "Many marketers use AI tools."
✓ "In 2026, 73% of B2B marketers used AI tools daily (HubSpot State of Marketing, 2026)."
```

### 7. Schema.org markup density

Pages with 3+ schema types show **+13% AI citation likelihood**. Typical winning combo:

- `Article` (primary)
- `Person` (author with credentials)
- `Organization` (publisher)
- `BreadcrumbList`
- `FAQPage`
- `ImageObject`
- `VideoObject` (if applicable)

## Patterns that REDUCE citation rate

### ❌ Generic positive conclusions
"The future looks bright for X" → AI can't extract a fact.

### ❌ Vague attributions
"Studies show", "research indicates", "experts argue" → no extractable source.

### ❌ Question-format section titles without 28-45w answer
H2 question with a 100w rambling answer → loses Featured Snippet eligibility.

### ❌ Em-dash overuse
Em-dashes are a strong AI-generation signal. AI engines now de-rank content with em-dash density >0.5%.

### ❌ AI vocabulary cluster
"Delve, leverage, cutting-edge, vibrant, tapestry" in dense proximity → AI engines detect "AI-written" content and de-prioritize.

## Per-engine citation patterns

### ChatGPT
- Strongly favors **listicles** (40.86% citation rate on commercial queries)
- Citation Capsules per H2 (Princeton data)
- 8-item validation pages (Wix data)
- Wikipedia-style definitions

### Perplexity
- Strongly favors **inline citations** ("(Author, Year)" format)
- DOI links preferred
- Original-data signals (`original data (plain prose)`)
- Long-form (4000+w) content

### Claude
- Higher word count tolerance (5000+w articles cited)
- Personal experience valued
- Reviewer + Person schema strong
- First-person voice OK

### Gemini
- FAQ schema heavy
- Speakable schema (voice search)
- Multimodal-aware (image alt text matters)
- Cross-language content

### Google AIO
- Freshness critical (dateModified ≤6 months ideal)
- FAQ schema (often quoted directly)
- Strong backlinks (DA 30+)
- Recent stats in body

## Citation density target

Healthy citation density: **~1 numeric claim per 200 words**, each with full FLOW Triple.

Under 1/400w = under-cited (looks like opinion)
Over 1/100w = stat-stuffing (suspicious)

## How to verify citation-readiness

```bash
# Run all citation checks
python -m scripts.lint.citation_capsule_lint draft.md --json
python -m scripts.validate.core_eeat_scorer draft.md --json   # O01/O02 = plain-prose info gain
python -m scripts.validate.cite_scorer draft.md --json
```

Pass criteria:
- Citation capsule per H2 (≥80% of H2s)
- Information gain in plain prose, ≥2 distinct signal types (bracket markers RETIRED 2026-07-14)
- CITE score ≥30/40

## What `ai_citation_tracker.py` measures

Weekly probe of major AI engines for your article URLs:

```bash
python -m scripts.monitor.ai_citation_tracker --site my-site --top-priority 30
```

Output:
```
my-fishing-blog: 30 probed ($1.47)
  gained: 5  lost: 1
  by_engine:
    chatgpt:    18 citations
    perplexity: 14 citations
    claude:      9 citations
    gemini:     12 citations
```

## See also

- `references/geo/ai-engine-matrix.md` — per-engine signal weights
- `references/seo/citation-capsules-princeton.md` — capsule pattern details
- `references/seo/information-gain-markers.md` — RETIRED marker system (historical record; express info gain as plain prose)
- `subskills/monitor/ai-visibility-tracker/SKILL.md` — tracking implementation
