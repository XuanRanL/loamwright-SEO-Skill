# Citation Capsules — Princeton GEO Pattern

> **Single highest-ROI structural pattern for AI-engine citation.** Each H2 section MUST contain one 40-60 word self-contained block that's directly quotable by ChatGPT/Perplexity/Claude/Gemini.

---

## Data

Princeton + Penn research on Generative Engine Optimization (2024-2025):

| Metric | Without capsules | With capsules | Delta |
|---|---|---|---|
| Cited by ChatGPT | 21% of pages | 49% of pages | **+133%** |
| Cited by Perplexity | 17% | 41% | **+141%** |
| Statistical claims in AI answers | 14% of citing pages | 19-23% | **+28-41%** |
| Authority source references | 8% | 17% | **+115%** |

**Source**: Princeton/Penn Generative Engine Optimization study (preprint 2024-12); replicated by Wix (2026.3) and AirOps (2026.4).

---

## What is a Citation Capsule?

A **40-60 word paragraph** with five properties:

1. **Self-contained** — Reader doesn't need prior context to understand
2. **Specific claim** — Contains a number, year, percentage, OR named entity
3. **Single subject** — One topic per capsule
4. **Quotable as-is** — No dangling references ("This shows...", "These results...")
5. **Verifiable** — Has citation or is original methodology

**NOT a Citation Capsule**:
- Vague summary ("This section covers...")
- Speculation ("Some experts believe...")
- Multi-topic paragraph
- Cliffhanger ("More on this below")

---

## Six structural patterns

### Pattern 1: Entity + Action + Specific Outcome

> The G.Loomis NRX+ rod (8'6", $549) outperformed nine competitors in ICAST 2026 sensitivity testing, registering a 12.8 newton-meter response gradient. Anglers using it report 23% improved bite detection across freshwater bass scenarios over 2023 baseline (G.Loomis Q1 2026 customer survey).

— 51 words. Entity (G.Loomis NRX+) + spec (price, length) + claim (sensitivity 12.8 Nm) + verification (ICAST + customer survey).

### Pattern 2: Method + Result + Year

> Topic-cluster architecture combining one pillar page (3,000+ words) with 6-12 spoke posts has been shown to capture 30-43% more organic traffic than disconnected blog posts, per HubSpot's 2024 analysis of 1.2M websites. The effect compounds when internal links exceed 7 per pillar.

— 49 words. Method (topic clusters) + measured result (+30-43% traffic) + year (2024) + sample size (1.2M sites).

### Pattern 3: Definition + Bounds + Application

> The Featured Snippet (Google's "Position 0") is a 40-60 word excerpt extracted from a page and displayed above all search results. It claims 8.6× the click-through rate of position #1, makes the page eligible for Google's AI Overview, and accounts for 19% of all SERP real estate as of January 2026 (Ahrefs 2026).

— 56 words. Definition + measurable bounds (8.6× CTR, 19% SERP) + application (AIO source).

### Pattern 4: Counter-Intuitive Finding

> Increasing keyword density above 1.3% reduces ranking position by an average of 4.2 places (Moz 2025 analysis of 100k queries). Yet 41% of marketers still target 2-3% density. The penalty applies even when keywords appear in heading tags — proximity matters less than overall body ratio.

— 49 words. Surprise + magnitude + sample size + nuance.

### Pattern 5: Comparison

> Shopify's checkout converts at 3.8% average across 1.7M stores (Shopify Q4 2025), while WooCommerce averages 2.1% across comparable verticals (WPEngine 2025). The 81% relative lift stems from one design choice: Shopify defaults to one-page checkout; WooCommerce defaults to three-step.

— 48 words. Two entities + measured outcomes + causal explanation.

### Pattern 6: Process + Time + Result

> A complete GEO audit takes 11-15 hours for a 50-page site, broken down as: 3 hours technical baseline, 4 hours content review against the CORE-EEAT 80-item rubric, 3 hours competitive AI citation probe, and 2 hours fixing schema and Author Person markup (RankScale 2026 internal benchmark).

— 51 words. Process + time + steps + benchmark source.

---

## Placement within H2 section

Three options, in order of effectiveness:

### Option A: Section-end summary (RECOMMENDED, best for AI extraction)

```
## How Wikipedia-style content earns AI citations

[Body paragraphs explaining the concept, examples, methodology — 400-800 words]

[Citation Capsule — final paragraph, 40-60 words, self-contained summary]
```

### Option B: Section-opening definition (good for Featured Snippet)

```
## What is keyword cannibalization?

[Citation Capsule — first paragraph, 40-60 words, defines the term clearly]

[Body paragraphs going deeper — 300-800 words]
```

### Option C: Mid-section pull quote (good for Perplexity)

```
## Strategy
[Body paragraphs 1-3]

[Citation Capsule — distinguished paragraph with specific claim]

[Body paragraphs 4-6]
```

---

## Linter rules (per `scripts/lint/citation_capsule_lint.py`)

A paragraph qualifies as a Citation Capsule if:
- ✓ Word count between 35 and 70 (40-60 ideal)
- ✓ Contains ≥1 specific data point (regex: `\d+%`, `\d{4}`, `\$\d+`, "et al")
- ✓ Self-contained: doesn't start with "This", "These", "Those", "They", "It", "That"
- ✓ Self-contained: doesn't end with "as we'll see", "more on this below", "see the next section"
- ✓ Is a paragraph (not a list / table / heading)

**Article passes if**: ≥80% of content H2s have at least one qualifying capsule. (References / TOC / Takeaways H2s don't count.)

---

## Anti-pattern: "Capsule sprinkling"

❌ Wrong: Adding `[CITATION CAPSULE]` markers visible to readers.

❌ Wrong: 3+ capsules per H2 (defeats the "one quotable chunk" purpose).

❌ Wrong: All capsules in opening paragraphs (AI engines extract from full content).

✅ Right: One capsule per H2, naturally embedded, indistinguishable from regular prose to human readers but loaded with extractable facts.

---

## See also

- `references/seo/information-gain-markers.md` (RETIRED — information gain is plain prose now)
- `references/seo/flow-evidence-triple.md` (year + cite + URL + retrieval-date pattern)
- `references/geo/cite-framework-40.md` (40-item AI-citation rubric)
- `scripts/lint/citation_capsule_lint.py` (enforcement)
