# SEO Audit Scoring Weights & Priority Definitions

## 7-Category Scoring System

Total score = weighted sum of category scores. Each category is scored 0-100, then multiplied by its weight.

| # | Category | Weight | Description |
|---|----------|--------|-------------|
| 1 | Technical SEO | **22%** | Crawlability, indexability, security, URL structure, mobile readiness, JS rendering |
| 2 | Content Quality | **23%** | E-E-A-T signals, readability, thin content detection, AI citation readiness |
| 3 | On-Page SEO | **20%** | Title tags, meta descriptions, heading structure, internal linking, keyword optimization |
| 4 | Schema / Structured Data | **10%** | Implementation correctness, validation, rich result opportunities |
| 5 | Performance (CWV) | **10%** | LCP, INP, CLS, resource optimization, TTFB |
| 6 | AI Search Readiness | **10%** | Citability, llms.txt, brand entity signals, structural readability for LLMs |
| 7 | Images | **5%** | Alt text coverage, format optimization, lazy loading, sizing |

**Total: 100%**

---

## Category Breakdown

### 1. Technical SEO (22%)

| Subcategory | Points (of 100) | What Is Checked |
|-------------|-----------------|-----------------|
| Crawlability | 25 | robots.txt validity, XML sitemap presence/accuracy, crawl errors in GSC, noindex misuse, orphan pages |
| Indexability | 20 | Index coverage, canonical tag correctness, duplicate content, hreflang (if multilingual), pagination |
| Security | 15 | HTTPS on all pages, mixed content warnings, HSTS header, certificate validity, security headers (CSP, X-Frame-Options) |
| URL Structure | 15 | Clean URLs, no excessive parameters, consistent trailing slashes, no broken redirects, redirect chains <3 hops |
| Mobile Readiness | 15 | Mobile-friendly test pass, viewport meta tag, tap target sizing, font legibility, no horizontal scroll |
| JS Rendering | 10 | Critical content visible without JS, dynamic rendering for bots if needed, JS error console clean, hydration issues |

### 2. Content Quality (23%)

| Subcategory | Points (of 100) | What Is Checked |
|-------------|-----------------|-----------------|
| E-E-A-T Signals | 30 | Author bios, credentials, about page, contact info, trust signals (see `eeat-framework.md`) |
| Readability | 20 | Flesch-Kincaid appropriate to audience, paragraph length, heading frequency, scanability |
| Thin Content | 20 | Page word counts vs. minimums (see `quality-gates.md`), unique content percentage, content-to-code ratio |
| Topical Authority | 15 | Content clusters, internal topic linking, publication depth in niche |
| AI Citation Readiness | 15 | Structured claims with sources, APA-style references, clear attributable statements, FAQ blocks |

### 3. On-Page SEO (20%)

| Subcategory | Points (of 100) | What Is Checked |
|-------------|-----------------|-----------------|
| Title Tags | 25 | Length 30-60 chars, primary keyword near front, uniqueness across site, no truncation |
| Meta Descriptions | 20 | Length 120-160 chars, CTA present, keyword included, uniqueness |
| Heading Structure | 20 | Single H1 per page, logical H2-H6 hierarchy, keywords in H2s, no skipped levels |
| Internal Linking | 20 | Link count per page type (see `quality-gates.md`), descriptive anchors, no orphan pages, hub-spoke patterns |
| Keyword Optimization | 15 | Primary keyword density 0.5-1.0%, semantic variations present, no over-optimization (>1.5% = penalty risk) |

### 4. Schema / Structured Data (10%)

| Subcategory | Points (of 100) | What Is Checked |
|-------------|-----------------|-----------------|
| Implementation | 40 | JSON-LD present, correct @context/@type, required properties populated, no placeholder values |
| Validation | 30 | Passes Google Rich Results Test, no errors in Schema.org validator, dates ISO 8601, URLs absolute |
| Opportunities | 30 | Missing schema types for page type (see `schema-types.md`), competitor schema gap analysis, GEO-advantaged types |

### 5. Performance / CWV (10%)

| Subcategory | Points (of 100) | What Is Checked |
|-------------|-----------------|-----------------|
| LCP | 35 | Field data ≤2.5s (Good), hero image optimized, preload critical resources, TTFB <800ms |
| INP | 25 | Field data ≤200ms (Good), no long tasks >50ms on main thread, event handlers debounced |
| CLS | 20 | Field data ≤0.1 (Good), all images/iframes dimensioned, no late-injected content, font-display: swap |
| Resource Optimization | 20 | Image compression (WebP/AVIF), JS/CSS minified, gzip/brotli enabled, unused code eliminated |

### 6. AI Search Readiness (10%)

| Subcategory | Points (of 100) | What Is Checked |
|-------------|-----------------|-----------------|
| Citability | 30 | Clear factual claims with inline citations, structured data supporting claims, quotable passages |
| llms.txt / AI Crawl Policy | 15 | llms.txt present and correctly formatted, robots.txt AI bot directives, RSL 1.0 licensing if applicable |
| Brand Entity Signals | 25 | Organization schema, consistent NAP, sameAs to social profiles, Knowledge Panel presence, Wikipedia/Wikidata |
| Structural Readability | 30 | Clean heading hierarchy, definition lists for key terms, table data for comparisons, FAQ blocks, concise paragraphs |

### 7. Images (5%)

| Subcategory | Points (of 100) | What Is Checked |
|-------------|-----------------|-----------------|
| Alt Text Coverage | 35 | All non-decorative images have alt text 10-125 chars, descriptive (not filename), keyword where natural |
| Format Optimization | 25 | WebP or AVIF for photos, SVG for icons/logos, appropriate quality settings, no BMP/TIFF |
| Lazy Loading | 20 | Below-fold images use loading="lazy", above-fold LCP image NOT lazy-loaded, native or JS-based |
| Sizing & Responsiveness | 20 | Explicit width/height attributes (CLS prevention), srcset for responsive images, max-width: 100% |

---

## Priority Definitions

Every finding in the audit report is assigned one of four priority levels:

| Priority | Label | Definition | Expected Action |
|----------|-------|------------|-----------------|
| **P0** | Critical | Directly blocks indexing, causes ranking loss, or creates security/legal risk. Examples: site-wide noindex, HTTPS failure, manual penalty, all pages returning 5xx, Google penalty notification. | Fix immediately (within 24-48 hours). Stop other work if necessary. |
| **P1** | High | Significantly degrades ranking potential or user experience. Will cause measurable traffic loss if left unfixed for 2+ weeks. Examples: missing canonical tags causing duplicate indexing, broken internal links on key pages, CWV all "Poor", no schema on primary pages. | Fix within 1-2 weeks. Include in next sprint/deployment. |
| **P2** | Medium | Limits ranking ceiling or misses optimization opportunities. Not causing active harm but preventing full potential. Examples: title tags too long, missing meta descriptions, suboptimal heading hierarchy, images missing alt text. | Fix within 1 month. Batch with related work. |
| **P3** | Low | Minor optimization opportunities or best-practice recommendations. Diminishing returns. Examples: adding breadcrumb schema, optimizing already-passing CWV further, alt text on decorative images, minor anchor text diversification. | Address when convenient. Backlog for quarterly review. |

### Priority Escalation Rules

- Any finding affecting >50% of indexed pages escalates by one level (P2 becomes P1)
- Any finding on the homepage or top-5 traffic pages escalates by one level
- YMYL sites escalate all E-E-A-T and trust findings by one level
- Findings with active Google Search Console warnings are automatically P0

---

## Overall Score Interpretation

| Score Range | Rating | Summary |
|-------------|--------|---------|
| 90-100 | Excellent | Best-in-class SEO. Focus on maintenance and monitoring. |
| 75-89 | Good | Strong foundation with optimization opportunities. P2/P3 items only. |
| 60-74 | Needs Work | Meaningful gaps limiting ranking potential. Multiple P1 findings likely. |
| 40-59 | Poor | Significant technical and content issues. P0/P1 findings present. |
| 0-39 | Critical | Fundamental SEO problems. Site may be partially or fully deindexed. Immediate remediation required. |

---

## Score Calculation Example

```
Technical SEO:         78/100 x 0.22 = 17.16
Content Quality:       65/100 x 0.23 = 14.95
On-Page SEO:           82/100 x 0.20 = 16.40
Schema/Structured:     45/100 x 0.10 =  4.50
Performance (CWV):     71/100 x 0.10 =  7.10
AI Search Readiness:   30/100 x 0.10 =  3.00
Images:                60/100 x 0.05 =  3.00
                                      ------
Overall Score:                         66.11 → "Needs Work"
```

---

## Weight Adjustment by Business Type

The default weights above suit most sites. Adjust for specific business types:

| Business Type | Increase | Decrease | Rationale |
|---------------|----------|----------|-----------|
| E-commerce | Performance +5%, Images +3% | AI Readiness -5%, Schema -3% | Page speed and product images directly impact conversion |
| Local Business | On-Page +3%, Content +2% | AI Readiness -3%, Schema -2% | Local content signals and GBP alignment matter most |
| SaaS | AI Readiness +5%, Content +3% | Images -3%, Performance -5% | AI search visibility drives high-value demo/trial traffic |
| Publisher | Content +5%, AI Readiness +5% | Technical -5%, Images -5% | Content quality and citability are the primary ranking levers |
| Agency | Content +3%, Schema +2% | Performance -3%, Images -2% | Thought leadership content and service schema drive leads |
