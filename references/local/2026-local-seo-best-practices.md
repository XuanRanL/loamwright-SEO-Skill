# 2026 Local SEO Best Practices (Whitespark + Sterling Sky + Moz Consolidated)

> Synthesized 2026-05-22 from deep research at `memory/research/local_seo_deep_research_2026.json` + `memory/research/competitive_local_seo_tools_2026.json`. Industry-agnostic recommendations any project using this plugin should follow.

---

## 1. The 2026 SERP for "[keyword] + location" queries

Per Whitespark 2026 AIO study + Sterling Sky local-pack tracker:

| SERP element | Prevalence for "[keyword] [city]" B2B commercial queries | Strategic implication |
|---|---|---|
| **AI Overview (AIO)** | 15-25% (vs 40-68% for "near me" queries) | Optimize for AIO citation, not just blue links |
| **Local Pack (Maps 3-pack)** | 39% overall / 6% for long-tail informational | Critical for archetype A/B/C; irrelevant for D/E ecommerce |
| **Organic blue links** | Universal | Standard SEO still matters most for D/E archetypes |
| **Featured snippet** | 12-18% | High-yield target; design content for snippet eligibility |
| **People Also Ask** | 35-50% | Mine for FAQ section content (4-10 Q&A) |
| **Video carousel** | 8-15% | Out of scope for this plugin (no video gen) |

**AIO citation source distribution**: ~60% of AIO citations point to third-party publishers (Yelp, Reddit, Thumbtack, industry forums), only ~40% to first-party local-business sites. This means: optimizing your own content alone isn't enough — content also needs to appear ON third-party platforms (PR, guest posts, syndication) for max AIO citation.

## 2. Page-level structure that ranks

From Whitespark 2026 study of top-ranked "[keyword] [city]" pages:

| Element | Top-ranked sites have it (%) | Plugin implementation |
|---|---|---|
| City/state name in `<title>` + `<h1>` + URL | 95% | Template enforces; verify_post check 27 confirms |
| At least 3 H2s referencing the location | 88% | Template + check 27 (≥3 H2 mentions) |
| Embedded Google Maps iframe | 67% | NOT in plugin (deferred) |
| Business NAP block visible (archetype A/B/C) | 92% | `business-context.json :: location.nap` + schema-generator |
| LocalBusiness JSON-LD schema | 84% | Schema-generator subskill (archetype A/B/C) |
| Article schema (archetype D/E national writing local content) | 71% | Schema-generator (Wirecutter pattern) |
| FAQPage schema | 64% | Existing FAQ-extractor flow |
| At least 8 inline citations | 78% | Existing citation-capsules + APA references rules |
| Reviews/testimonials section | 56% | Out of scope (review schema is restrictive — see schema-mapping doc §7) |
| 2,400-3,200 words | 73% (state pillar) | Template word budget matches |
| 2,000-2,800 words | 65% (city page) | Template word budget matches |

## 3. The 60/40 AIO citation split — implications

Per Whitespark Q2 2026 AIO citation study (the source of the "first-party gets only 40%" stat):

- First-party site content (your blog post) gets cited ~40% of the time
- Third-party platform content (Yelp, Reddit, Thumbtack, industry directories) get cited ~60%
- Implication: to maximize AIO citation rate, your local content needs to ALSO appear (in syndicated/excerpted form) on industry platforms — not exclusively on your own site

This plugin doesn't automate third-party syndication. Recommended manual workflow:
1. Publish your article via /article + wp_publisher
2. Excerpt the most-citable 200-400 words and post as a related answer on Reddit (r/{industry}, r/{location}), Quora, or industry forums
3. If archetype A/B/C, ensure GBP "Updates" section gets a post linking to the article
4. Submit URL to industry-specific directories (BBB, Yelp business page, etc.) where applicable

## 4. The hub-and-spoke architecture (validated cautiously)

Per Whitespark + Yext studies (2024-2026):

- Pages that link UP to a "national hub" + DOWN to "city sub-pages" + SIDE to "sister state pages" tend to earn higher AI Overview citation rates than orphan pages
- The claimed lift is between 1.5× and 3× (per validation research — earlier "3.4×" claims trace to a single n=50 Backlinko study with confounded site-authority variables; the realistic range is 1.5-3× with significant variance)

Plugin implementation: NOT automated in v3.4.0. Manual workflow:
1. Create a national hub page first (e.g. "Best Solar Installers in the USA: 50-State Guide")
2. Each state article (`local-state-pillar`) links UP to the hub + SIDE to 2-3 sister state articles
3. Each city article (`local-city-page`) links UP to the state pillar + SIDE to 2-3 sister city articles in same state
4. Use the `linker` subagent (already in plugin) to handle anchor-text variation

## 5. The doorway page risk (Google 2025-12-10 update)

Google's spam policy was updated 2025-12-10 to add explicit language about region/city template pages:

> "Pages built from a template where only the location name varies, with the goal of capturing traffic for many cities/regions, may be classified as doorway pages."

The plugin's `local_uniqueness_check.py` is the defense against this. Per Sterling Sky 80/20 rule (`references/local/sterling-sky-80-20-rule.md`): ≥20% of body must be genuinely unique-per-locality across 4 categories.

**Note**: Per validation research, no site has been DOCUMENTED to lose rankings specifically from template-only city pages in the August 2025 or December 2025 spam updates. Sterling Sky's August 2025 case study attributes their client's drop to backlink spam, NOT template pages. The doorway-page risk is real and longstanding, but not "imminent moat" framing.

## 6. YMYL × local intersection

Per Google's Quality Rater Guidelines + Search Central docs (2026):

- Medical (dentist, MedicalClinic, Chiropractic) — REQUIRES: named author, `Person.hasCredential.MedicalDoctor` (or RegisteredHealthProfessional), `Article.reviewedBy: Person`, `lastReviewed` date
- Legal (LegalService — Attorney is DEPRECATED in Schema.org) — REQUIRES: `Person.hasCredential` (state bar membership)
- Financial (FinancialService, AccountingService) — REQUIRES: `Person.hasCredential` (CPA, CFP, CFA)
- General non-YMYL — author byline sufficient

Plugin's schema-generator reads `business-context.json :: location.ymyl_flag` and emits the required extras for YMYL categories per `references/local/industry-to-schema-mapping.md` §5.

## 7. AI Overview optimization signals (Stanford CITE 2025 + Anthropic 2025)

Per the Stanford CITE study and Anthropic's transparency reports:

- **Inline (Author, Year) citations have ~3× the AIO extraction rate vs end-of-list-only references** — this plugin's `_apply_in_text_citations` already enforces this (claim-marker → APA inline swap)
- **Schema completeness** — LocalBusiness + Service + Place graph (archetype A/B/C) OR Article + spatialCoverage + about + mentions (archetype D/E) both correlate with higher citation rate vs minimal schema
- **Author authority** — named author with `hasCredential` increases trust signal weight
- **Recency signal** — `lastReviewed` field within 6 months improves citation likelihood

## 8. Tooling landscape — what to use, what NOT to use

Per `memory/research/competitive_local_seo_tools_2026.json`:

| Need | Recommended | Avoid |
|---|---|---|
| Article generation w/ local awareness | This plugin (v3.4.0+) | Frase ("create 50 city pages from template" anti-pattern), Yext Pages (thin content) |
| Local pack tracking | Local Falcon, BrightLocal | Whitespark's product is fine but fragmented |
| GBP management | Whitespark, BrightLocal, native GBP | Yext (enterprise contracts) |
| Citation building | Whitespark, BrightLocal | Avoid pure-spam citation builders |
| AIO citation tracking | Newer tools emerging (Perplexity dashboards, ChatGPT visibility tools) | Most generic SEO tools don't yet measure AIO |

## 9. Measurement KPIs in 2026

What to track for local SEO success:

- **Local pack rank** (for archetype A/B/C) — measured via Local Falcon or Whitespark
- **GBP impressions + clicks** — native GBP insights
- **Organic clicks from local geography** — Google Search Console (filter by country/region)
- **AIO citation rate** for "[keyword] [city]" queries — manual probing of ChatGPT / Perplexity / Gemini / Google AIO
- **Direct conversions** — your CRM/analytics; ultimately what matters

## 10. Common pitfalls to avoid

1. **Service.areaServed for national ecommerce** — Misleading-data signal. Use Wirecutter pattern instead.
2. **AggregateRating self-attestation** — Google silently drops these (Sept 2019 update). Use real third-party reviews only.
3. **LocalBusiness without address** — Required field per Google docs; missing it tanks rich-results eligibility.
4. **GeoCoordinates with <5 decimal precision** — Signals "fake business" location.
5. **GeoCircle.geoRadius without unit** — Defaults to METERS (not miles). Easy gotcha.
6. **Reusing same hero image across 50 city pages** — Image hash detection flags this; use city-specific OG images or generic-but-different.
7. **Hardcoded boilerplate without per-city editorial review** — Sterling Sky 80/20 violation. Always review per-city output.

---

## Sources

- Whitespark 2026 Q1+Q2 AIO Citation Study — https://www.whitespark.ca/blog/
- Sterling Sky local-pack research — https://www.sterlingsky.ca/
- Stanford CITE 2025 — citation-extraction-rate study
- Google Search Central — https://developers.google.com/search/docs/
- Google spam policies (updated 2025-12-10) — https://developers.google.com/search/docs/essentials/spam-policies
- Moz Local SEO guide (2026 update) — https://moz.com/local-search-ranking-factors
- Schema.org canonical docs — https://schema.org/
