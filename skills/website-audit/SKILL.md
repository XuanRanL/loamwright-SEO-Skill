---
name: website-audit
description: "Full website SEO audit — crawls up to 500 pages, detects business type, spawns up to 15 parallel specialist agents (8 always + 7 conditional), generates SEO Health Score (0-100) with enterprise HTML report. Completely standalone — not connected to the blog-writer pipeline. Triggers on: audit my site, website audit, full SEO check, site health, analyze my website, SEO analysis, technical SEO audit, or any URL + audit intent. Use whenever user mentions 'audit', 'check my site', 'SEO health', 'website analysis', or provides a URL asking for SEO evaluation."
user-invocable: true
argument-hint: "<url> [--max-pages N] [--output dir]"
allowed-tools: [Read, Write, Bash, Glob, Grep, Agent, Task]
---

# Full Website SEO Audit

Standalone website auditing tool. URL in → crawl → analyze → report out.
No dependency on the blog-writer pipeline, project system, or article creation flow.

## Invocation

```
/website-audit https://example.com
/website-audit https://example.com --max-pages 100
```

## Process

### Phase 1: INITIALIZE

1. Validate URL:
```bash
python -c "from scripts._core.ssrf_guard import validate_url, SSRFError; import sys
try:
    validate_url('$URL', allow_http=True); print('OK')
except SSRFError as e:
    print(f'BLOCKED: {e}'); sys.exit(1)"
```
⚠️ `validate_url()` signals success by RETURNING a truthy `ValidatedURL` and failure by RAISING `SSRFError`. The old snippet here did `err = validate_url(...); print(err or 'OK')`, which prints the success object and can never print `OK` — and that inverted reading got copied into `verify_backlinks.py`, where it marked every valid backlink "blocked" and silently disabled link verification entirely. Never treat the return value as an error indicator.
2. Create output directory: **`./Website Audit/seo-audit-{domain}-{YYYY-MM-DD}/`**
   ⚠️ The `Website Audit/` parent already exists and holds every prior audit — write there, NOT in the repo root. This was violated on 2026-08-06 (audit-client.example) and cost a 149 MB directory move plus an artifact URL rescue. Create the full path before crawling, not after.
3. Show cost estimate to user (based on detected page count):
   - 8 core agents (Opus): ~$8
   - With conditional agents: ~$15 max
   - Await user confirmation if over $10

### Phase 2: CRAWL

```bash
python -m scripts.audit.crawl_site "$URL" --max-pages 500 --concurrent 5 --delay 1.0 --output ./"Website Audit"/seo-audit-{domain}-{date}/crawl-results.json
```

Configuration:
- Max pages: 500 (user-overridable via --max-pages)
- Respect robots.txt: Yes
- Follow redirects: Yes (max 3 hops)
- Timeout per page: 30 seconds
- Concurrent requests: 5
- Delay between requests: 1 second

### Phase 3: DETECT BUSINESS TYPE

```bash
python -m scripts.audit.business_type_detector ./"Website Audit"/seo-audit-{domain}-{date}/homepage.html --url "$URL" --json > ./"Website Audit"/seo-audit-{domain}-{date}/business-type.json
```

Business types: SaaS | E-commerce | Local (brick-and-mortar/SAB/hybrid) | Publisher | Agency | Other

### Phase 4: SPAWN SUBAGENTS (parallel)

**Always spawn (8 agents):**

| Agent | Responsibility | Key Scripts |
|-------|---------------|-------------|
| `audit-technical` | Crawlability, indexability, security, URL structure, JS rendering | crawl_site, fetch_page, parse_html |
| `audit-content` | E-E-A-T scoring (80 items), readability, thin content, YMYL detection | core_eeat_scorer |
| `audit-schema` | JSON-LD detection, validation, deprecated type veto (T09) | schema_validator |
| `audit-sitemap` | XML sitemap structure, coverage gaps, quality gates | fetch_page |
| `audit-performance` | LCP, INP, CLS via PageSpeed Insights + CrUX field data | pagespeed_check |
| `audit-visual` | Desktop + mobile screenshots, above-fold analysis, responsive check | capture_screenshot, **render_probe** |
| `audit-geo` | AI crawler access, llms.txt, citability (134-167w optimal), brand signals | fetch_page |
| `audit-sxo` | SERP backwards analysis, page-type mismatch detection, persona scoring | fetch_page, parse_html |

**Conditionally spawn (7 agents):**

| Agent | Condition | Responsibility |
|-------|-----------|---------------|
| `audit-local` | business_type ∈ {local_*} | GBP signals, NAP consistency, reviews, local schema |
| `audit-maps` | local detected AND geoapify/dataforseo key available | Geo-grid, competitor radius |
| `audit-google` | Google API key configured | CrUX field data, GSC indexation, GA4 traffic |
| `audit-backlinks` | Always (CC free); enriched if Moz/Bing keys | DA/PA, referring domains, toxic links |
| `audit-cluster` | /blog detected OR pillar signals | Semantic clustering, cannibalization |
| `audit-drift` | Previous baseline exists for this domain | 17-rule drift comparison |
| `audit-ecommerce` | business_type == "ecommerce" | Product schema, marketplace intel |

Each agent writes results to: `./"Website Audit"/seo-audit-{domain}-{date}/modules/{name}.json`

#### A negative rendering claim needs a time-series, and a real browser to settle ties

**Never rate a "does not render / shows zero / is blank / is missing" finding above `medium` from a single screenshot.** On 2026-08-06 two such findings shipped as `critical` on audit-client.example and both were wrong — a headless capture had caught a slow `fadeInUp` animation before it started, and that frame was read as the final state.

Measured on that page: headless, 10s wait, 6 runs → 5 never started; headed, 10s wait, 3 runs → all animated, 1 still mid-flight. So the failure mode is **a single capture landing mid-animation**, not "headless is broken" — sampling over time is the fix, and the real browser is the tie-breaker.

```bash
python -m scripts.audit.render_probe "$URL" --selector "[data-to-value]" --selector ".hero h1" --check
```

It reports three columns that must never be collapsed into one claim:

| Column | Audience | If content is missing here |
|---|---|---|
| `static` (no JS) | text-extracting crawlers, AI fetchers, link previews | real finding — rate for **machine readability** |
| `headless` samples | some render services, screenshot bots | corroborating signal |
| `headed` samples | **human visitors** — the ground truth | only this justifies a UX/visual severity |

`--check` exits non-zero when headless and headed disagree, i.e. when any headless-derived finding would be unsafe to publish. A `static_unavailable` result (403/WAF/network) is reported as unavailable, never as empty — a transport failure is not a content verdict.

### Phase 5: SCORE

```bash
python -m scripts.audit.audit_scorer ./"Website Audit"/seo-audit-{domain}-{date}/modules/ --json > ./"Website Audit"/seo-audit-{domain}-{date}/scores.json
```

**Scoring Weights:**

| Category | Weight | Contributing Modules |
|----------|--------|---------------------|
| Technical SEO | 22% | technical, sitemap, backlinks (authority) |
| Content Quality | 23% | content, cluster (bonus) |
| On-Page SEO | 20% | sxo, visual (partial), local (bonus) |
| Schema / Structured Data | 10% | schema, ecommerce (if present) |
| Performance (CWV) | 10% | performance, google (field data) |
| AI Search Readiness | 10% | geo |
| Images | 5% | visual (image portion) |

### Phase 6: VALIDATE

```bash
python -m scripts.audit.validate_audit_report ./"Website Audit"/seo-audit-{domain}-{date}/ --json
```

Pre-delivery checks: all core modules reported, no empty sections, score math correct.

### Phase 7: REPORT

```bash
python -m scripts.audit.report_generator ./"Website Audit"/seo-audit-{domain}-{date}/ --output ./"Website Audit"/seo-audit-{domain}-{date}/FULL-AUDIT-REPORT.md
python -m scripts.audit.report_html ./"Website Audit"/seo-audit-{domain}-{date}/ --output ./"Website Audit"/seo-audit-{domain}-{date}/FULL-AUDIT-REPORT.html
```

Generate ACTION-PLAN.md from findings sorted by severity.

#### Branding — MANDATORY on every client-facing report

Audit reports are **Loamwright SEO (沃匠 SEO) lead-generation assets**, not neutral technical documents. Loamwright is the operator's OWN agency. Every HTML report ships with its branding.

Read the brand facts — never write them from memory:
```bash
python -c "import json;d=json.load(open('projects/loamwright/business-context.json',encoding='utf-8'));print(json.dumps({k:d[k] for k in ['brand_name_full','site_url','company','article_signature']},ensure_ascii=False,indent=1))"
grep -oE '\-\-xr-[a-z-]+:\s*#[0-9a-fA-F]{3,8}' projects/loamwright/brand/article-css.css
```

Required elements (the 2026-08-06 audit-client.example report is the reference implementation — copy its structure):
1. **Top brand bar** — wordmark + positioning line + CTA link to `https://loamwrightseo.com/contact-us/`
2. **Masthead** — "沃匠 SEO 出品" pill and an 审计方 field
3. **Brand palette** — primary `#138670`, accent `#12B76A`, link `#0B5143`. The brand's own `#B45309` / `#B42318` double as the warn/critical severity colors; don't invent a second palette.
4. **关于沃匠 SEO section** — real proof signals only: 6 years, 100+ brands (incl. publicly listed), 0 account managers, 5.0 rating, 8 disciplines
5. **CTA block** — free SEO audit offer (200+ checks, ranked by revenue impact)
6. **Branded footer** — site, email, contact URL, and the signature "沃匠 SEO 团队，Lewei Zhang 复核"

Two constraints: the Artifact CSP blocks font CDNs and CJK fonts can't be inlined, so use system font stacks (PingFang SC / Microsoft YaHei) — that is the correct call, not a compromise. And first-person IS on-brand for Loamwright (founder-led), but never fabricate client results or experiences that didn't happen.

## Output Files

```
./"Website Audit"/seo-audit-{domain}-{date}/
  crawl-results.json          # Crawled pages manifest
  business-type.json          # Detected industry + conditional agents
  modules/                    # Per-agent analysis results (JSON)
  scores.json                 # Aggregated 7-category health score
  FULL-AUDIT-REPORT.md        # Comprehensive findings (Markdown)
  FULL-AUDIT-REPORT.html      # Interactive report (self-contained HTML)
  ACTION-PLAN.md              # Prioritized recommendations
  screenshots/                # Desktop + mobile captures
```

## Report Structure

### Executive Summary
- Overall SEO Health Score: {score}/100 [{badge}]
- Business type detected
- Pages crawled
- Top 5 critical issues
- Top 5 quick wins

### Per-Category Sections (7 categories)
Each section includes:
- Category score with badge (Excellent/Good/Needs Improvement/Poor)
- Findings table: severity | issue | evidence | recommendation
- Sub-section detail per analyzed dimension

### Action Plan
- **Critical**: Blocks indexing or causes penalties (fix immediately)
- **High**: Significantly impacts rankings (fix within 1 week)
- **Medium**: Optimization opportunity (fix within 1 month)
- **Low**: Nice to have (backlog)

## Error Handling

| Scenario | Action |
|----------|--------|
| URL unreachable (DNS/connection) | Report error clearly; do not guess content |
| robots.txt blocks crawling | Analyze accessible pages; note limitation in report |
| Rate limiting (429) | Back off; report partial results |
| Timeout on large sites | Cap at limit; report findings for crawled pages |
| Subagent timeout/failure | Skip that module; note in report; redistribute weight |
| No Google API key | Skip audit-google; use lab-only CWV data from PSI |
| No backlink APIs | Use Common Crawl only (always available, free) |

## Reference Files (load on-demand)

- `references/audit/eeat-framework.md` — E-E-A-T scoring rubric
- `references/audit/cwv-thresholds.md` — Core Web Vitals thresholds
- `references/audit/quality-gates.md` — Content minimums per page type
- `references/audit/schema-types.md` — Recommended schema + deprecation status
- `references/audit/local-seo-signals.md` — Local ranking factors
- `references/audit/backlink-quality.md` — Toxic link patterns + anchor benchmarks
- `references/audit/scoring-weights.md` — Full scoring methodology
- `references/audit/business-types.md` — Detection signal matrix

## Cost & Model

- Default model: inherits from session (Opus)
- Override: user can say "use sonnet" to reduce cost ~6x
- Budget guard: cost_ledger enforces limits from `~/.xuanran-seo/config.yaml`
- Estimated cost: $8-15 per full audit (Opus), $1.50-2.50 (Sonnet)
