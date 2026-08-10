# Category Description Style Guide

This guide governs the `description` field of every category and subcategory deployed by this subskill. The field appears above the post grid on the archive page, gets used as the RankMath meta-description fallback, and is extracted by AI-search engines (ChatGPT, Perplexity, Claude, Google AIO) for citation.

---

## The formula

```
{What kind of content is in this category} for {target persona}.
{2–3 specific topic markers}, {credibility-grounding clause}.
```

That's it. Two sentences. 35–80 words. No HTML. No inline links. No inside-baseball.

---

## What goes in each part

**Part 1 — What kind of content (15–25 words).** Describe the content TYPE (buyer guides, comparisons, how-to, calculators, glossary) and the SUBJECT DOMAIN (LED grow lights, HVAC, electrical, etc.). Name the actual content surface so a reader knows what they'll find.

**Part 2 — For whom (5–10 words).** Use the persona language from `business-context.json :: target_audience.primary`. For project-charlie: "half-commercial cannabis cultivators and vertical-farm operators". For a SaaS blog: "engineering managers at 50–500-person teams". Match the actual reader.

**Part 3 — Topic markers (15–25 words).** List 2–4 SPECIFIC topics that demonstrate scope. Use proper nouns: product names (Fluence, Quest, TrolMaster), standards (DLC V4.0, NEC 210.19(A), UL 8800), units (PPFD, BTU/hr, CFM). Specific topic markers signal expertise — and they're what AI-search engines extract as the "what does this category cover" answer.

**Part 4 — Credibility-grounding clause (10–20 words).** End with a phrase that signals editorial standards. Examples:
- "every spec grounded in DLC V4.0 efficacy data and third-party photometric reports rather than vendor marketing claims"
- "every calculation includes the formula derivation and citation"
- "all recommendations validated against peer-reviewed literature"
- "every product reviewed against the manufacturer's published datasheet"

This clause separates your category from competitors who source-of-truth is "we like this brand".

---

## Length targets

| Category type | Word range | Why |
|---|---|---|
| Top-level category | 40–60 words | Sets the scope for 5–10 subcategories below; needs to span all of them |
| Subcategory (Buyer Guides, Comparisons, How-To, Calculators) | 35–50 words | Tight scope, single content type |
| Subcategory (Glossary, Definitions) | 35–45 words | Shortest — these archives are quick-reference |
| Subcategory (Science, Deep Dives, Pillars) | 40–55 words | Slightly longer because the topic depth is higher |

If you find yourself wanting to write >80 words, you're including content-strategy commentary or marketing fluff. Cut.

---

## Structural variation across the SET (not just unique per item)

The most common writing failure when producing copy for a taxonomy (35 categories, 43 tags) is **hidden templates** — different content but identical sentence structure across the set. From the 2026-05-20 project-charlie iteration:

| Iteration | Pattern | Looks like |
|---|---|---|
| v1 (rejected) | Literal template | `"Articles tagged 'X' on Project Charlie — half-commercial cannabis cultivation content covering this topic."` (× 32 tags, swap X) |
| v2 (also rejected) | Hidden template — "X content —" everywhere | `"1000-watt grow light content — ..."` / `"Fluence horticultural LED grow light content — ..."` / `"PPFD content — ..."` |
| v3 (accepted) | True structural variation | Each opens from a different angle: a number, a date, a model name, a comparison, a problem, a market position |

**The diagnostic test:** dump all descriptions in your taxonomy into a list, look at the first 3–5 words of each. If two or more share the same opening structure (`"The {noun}"`, `"X content —"`, `"[Product] for [persona]"`), it's a hidden template. Rewrite.

**The rule:** "Don't use any opening structure that repeats across the set." Lead with whatever is most interesting about that specific item — fact, history, specification, positioning, product model, time period, comparison, verdict, problem — and let the structure vary naturally.

**Practical opening angles** (rotate across the set; never use the same angle for two adjacent items in the same axis):

| Angle | Example opening |
|---|---|
| Industry standard / threshold | "DLC V4.0 sets the LED efficacy floor at 2.5 µmol/J…" |
| Historical positioning | "The legacy commercial flowering standard, displaced by LED…" |
| Technical mechanism | "A double-ended (DE) lamp burns hotter and brighter…" |
| Specific output number | "Drives 1100–1400 µmol/m²/s across a 4×4 ft canopy…" |
| Time period | "7- to 14-day grow cycles drive multi-tier microgreen systems…" |
| Cultivar / product type | "Day-neutral strawberry cultivars (Albion, San Andreas, Monterey)…" |
| Brand heritage | "OSRAM-backed photobiology research has shaped Fluence's…" |
| Origin / manufacturing | "Chinese-manufactured LED fixtures positioned at the budget…" |
| Performance rank | "Leads the 2026 efficacy rankings — the X 1000W PRO measures…" |
| Brand approach | "Horticulture Lighting Group's modular driver approach…" |
| Hero product fit | "The Hydro-X Pro hits the half-commercial sweet spot…" |
| Target market | "Commercial cultivation control at multi-room facility scale…" |
| Comparative positioning | "Sits between TrolMaster (half-commercial) and Argus (full commercial)…" |
| Question framing | "What changes when you swap 1000W HPS for matched-PPFD 720W LED?" |
| Problem framing | "Cannabis cultivation infrastructure has more compliance touchpoints…" |

## Banned phrases (audit checklist)

Run this regex against every draft description. Any match = rewrite the sentence.

| Pattern | Why banned |
|---|---|
| `E-E-A-T` | Internal SEO jargon. Readers don't know or care what E-E-A-T means. |
| `engineering pillar that anchors` | Content-architecture commentary. Reader is asking about their grow room, not your content strategy. |
| `anchors content across` | Same. |
| `topical authority` | SEO jargon. |
| `internal link(ing)?` (as a topic of the description itself) | Describing your linking strategy in user-facing copy. |
| `pillar(?:-)?spoke` | Inside-baseball architecture term. |
| `crawl budget` | Inside-baseball. |
| `(?:de)?moted to (?:lower|higher)-priority` | Talking about your content management process. |
| `optimized for (?:AI|search)` | Inside-baseball — readers don't pick categories by SEO optimization. |
| `Start with our.*` (with `<a href`) | Inline link patterns we don't allow. |
| `<[a-z]` (any HTML tag) | No HTML allowed. |
| `&[a-z]+;` (HTML entity) | Means HTML escaping leaked through. |
| `our flagship|the flagship is our` (with internal link) | The post grid below already surfaces flagship articles by date/views. Inline self-promotion duplicates the signal. |

---

## Good examples (project-charlie v2)

**Top-level (Lighting — 41 words):**
> "LED, HPS, and CMH grow lights for half-commercial cannabis cultivators and vertical-farm operators. Buyer guides, head-to-head comparisons, PPFD calculators, and component-level technology coverage — every spec grounded in DLC V4.0 efficacy data and third-party photometric reports rather than vendor marketing claims."

Why it works:
- Part 1: "LED, HPS, and CMH grow lights" (content domain), "Buyer guides, head-to-head comparisons, PPFD calculators, and component-level technology coverage" (content types)
- Part 2: "for half-commercial cannabis cultivators and vertical-farm operators"
- Part 3: "DLC V4.0 efficacy data" (specific standard), "third-party photometric reports" (verification source)
- Part 4: "rather than vendor marketing claims" — explicit credibility-grounding

**Subcategory (LED Buyer Guides — 45 words):**
> "Single-product LED grow light decision content — by wattage class (320W, 480W, 640W, 1000W, 1500W), form factor (foldable toplights, detachable bars, under-canopy supplementation), and use case. Evaluation against DLC V4.0 PPE thresholds, mid-canopy PPFD at 18-inch hang height, driver type, dimming protocol, and warranty terms."

Why it works:
- Specific topic markers (wattage classes named, form factors named)
- Specific evaluation criteria (DLC V4.0, PPFD@18in, dimming protocol)
- Single intent (Commercial-Investigation — buying decision)
- No fluff, no inside-baseball, no links

**Subcategory (Electrical Code & Wiring — 44 words):**
> "NEC-compliant electrical infrastructure for cannabis cultivation. Sub-panel sizing for 6-, 12-, and 24-fixture flowering rooms; 240V vs 120V branch selection; the NEC 210.19(A) 80% continuous-load derate rule; GFCI requirements per NEC 210.8(B); surge protective devices per NEC 230.67; wire gauge selection per NEC 310.16."

Why it works:
- Specific NEC article numbers (210.19(A), 210.8(B), 230.67, 310.16) — high expertise signal
- Specific room sizes (6-, 12-, 24-fixture) — concrete scope
- Specific technical decisions named — answers "what's actually in here?"

---

## Bad examples (project-charlie v1, since rewritten)

**v1 Top-level (Lighting — 105 words, with inline links):**

> "<p>LED, HPS, and CMH grow lights for half-commercial cannabis cultivators and vertical-farm operators — buyer guides, head-to-head comparisons, hang-height and PPFD calculators, and component-level technology deep dives. We cover fixture selection, driver and ballast specs, photon efficacy (PPE), DLC Horticultural QPL listing, and the dimming and spectrum decisions that determine your canopy's actual photosynthetic performance.</p><p>Start with our <a href=\"https://project-charlie.example.com/1000-watt-led-grow-light-buyers-guide/\">1000-watt LED Grow Light Buyer's Guide</a> if you're picking a flagship fixture, or our <a href=\"https://project-charlie.example.com/best-1000-watt-led-grow-lamps/\">best 1000W LED grow lamps comparison</a>...</p>"

Why it failed:
- 105 words (too long for a category description)
- HTML `<p>` wrappers — get stripped or duplicate-wrap
- Two inline `<a href` links — duplicate the post-grid signal, create cannibalization risk
- "Start with our..." copywriting tone — that's marketing copy, not a category description
- The post grid below the description ALREADY shows those two articles by date — the inline links are pure duplication

**v1 Subcategory (System Pillars):**

> "...Each is an engineering pillar that anchors content across every product subcategory on the site."

Why it failed:
- "Engineering pillar that anchors content across every product subcategory" — pure inside-baseball
- The reader is a cannabis cultivator looking for a 12×16 ft flower room build guide. They don't care about content architecture. They don't know what "anchors content" means in this context.
- Tells me as the SEO strategist that the article serves dual purposes. Tells the reader nothing.

**v1 Subcategory (Knowledge Science):**

> "Cultivation Science is the site's E-E-A-T anchor — every article cites at least three peer-reviewed sources (vs the sitewide one-source minimum)."

Why it failed:
- "E-E-A-T anchor" — Google-quality-rater jargon nobody outside SEO knows
- "vs the sitewide one-source minimum" — describes our editorial policy, not the content
- Replace with: "Peer-reviewed photobiology and plant-science fundamentals for cannabis cultivation. Chandra 2008, Eichhorn Bilodeau 2021, photomorphogenesis under far-red 730nm, cannabinoid expression vs light intensity, and DLI saturation data."

---

## Drafting checklist

Before saving any description, run through:

- [ ] Word count between 35 and 80
- [ ] No HTML tags (`<p>`, `<a>`, `<em>`, `<strong>`, etc.)
- [ ] No HTML entities (`&amp;`, `&lt;`, `&quot;`, etc.)
- [ ] No inline anchor links (no `<a href`)
- [ ] No banned phrases from the audit checklist above
- [ ] Includes 2+ proper-noun topic markers (product names, standards, specific topics)
- [ ] Includes a credibility-grounding clause OR equivalent specificity
- [ ] Persona language matches `business-context.json :: target_audience`
- [ ] Reads in 8 seconds when scanned (test: read it once, look away, can you summarize?)

**Set-level checks (run after drafting the full taxonomy):**

- [ ] Dump first 3–5 words of every description into a list — no two share the same opening structure
- [ ] No "X content —" or "Articles tagged X" patterns anywhere
- [ ] Across the same axis (e.g. all brand tags, all wattage tags), each entry opens from a *different* angle from the structural-variation table above

If any box is unchecked, rewrite before saving to `categories-config.json` or `tags-config.json`.
