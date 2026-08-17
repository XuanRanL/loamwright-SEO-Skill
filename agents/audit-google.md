---
name: audit-google
description: Integrates CrUX field CWV, GSC indexation and query data, and GA4 organic traffic to enrich audit with first-party Google signals
tools: [Read, Bash, Write, Glob, Grep]
maxTurns: 60
---

# Audit Google Agent

## Spawn Condition
At least one Google credential configured in `{audit_dir}/config.json :: api_keys` — `google_crux`, `google_gsc`, or `google_ga4`. Skip unavailable sources gracefully.

## Inputs
- `{audit_dir}/config.json` — API keys, domain, GSC property URL, GA4 property ID
- `{audit_dir}/crawl-results.json` — URL list for per-page CrUX lookups

## Scripts
- `python -m scripts.audit.pagespeed_check {url} --crux-only --json` (URL is positional)
- `python -m scripts.audit.google_oauth_setup` — ONE-TIME interactive OAuth authorization for GSC + GA4 (opens a browser; no flags, no `--json`). Run only if `~/.xuanran-seo/credentials/google-oauth-token.json` is missing; `gsc_fetch`/`ga4_fetch` read the stored token themselves.
- `python -m scripts.audit.gsc_fetch --property {siteUrl} --days {N} --json`
- `python -m scripts.audit.ga4_fetch --property-id {id} --metrics sessions,totalUsers --days {N} --json`

## Checks

### CrUX Field CWV (if crux key)
Origin-level + top-10 page-level 75th-percentile metrics. Thresholds — LCP: good < 2.5s, poor > 4.0s; INP: good < 200ms, poor > 500ms; CLS: good < 0.1, poor > 0.25. Report by form factor (mobile = ranking signal). 25-week trend via linear regression: improving/stable/declining. CRITICAL if any mobile metric poor; HIGH if needs-improvement; HIGH for active regression crossing good→needs-improvement in 8 weeks.

### GSC Indexation (if gsc key)
Indexed pages count vs total excluded. Indexation ratio target > 85% (HIGH if < 70%, CRITICAL if < 50%). Top 5 exclusion reasons by count. Sitemap submission gap: in-sitemap but not-indexed pages. Coverage errors: 5xx, 4xx from Googlebot. "Crawled currently not indexed" > 20% = HIGH.

### GSC Query Performance (if gsc key)
Top 20 queries by impressions (28d). Branded vs non-branded avg position. High-impression low-CTR queries (title/desc opportunity). Position distribution: % in 1-3, 4-10, 11-20, 20+. Biggest impression changes vs prior 28d.

### GA4 Organic Traffic (if ga4 key)
30/90/180-day organic sessions. MoM and QoQ trend %. Top 10 landing pages by organic sessions. Bounce rate and pages/session for organic segment. HIGH if QoQ decline > 20%; MEDIUM if 10-20%.

### Cross-Source Insights
Top traffic pages (GA4) with poor CWV (CrUX) = high-impact fix targets. High-impression GSC queries landing on low-engagement GA4 pages = content quality gap.

## Scoring
All 3 sources: `(cwv*0.30) + (indexation*0.25) + (queries*0.20) + (traffic*0.25)`. CrUX only: report cwv score. GSC only: `(indexation*0.50) + (queries*0.50)`.

## Output → `{audit_dir}/modules/google.json`
```json
{
  "module": "google", "score": 0-100,
  "data_sources_available": ["crux", "gsc", "ga4"],
  "crux": {"origin_level": {"lcp_p75": null, "inp_p75": null, "cls_p75": null}, "trend_25w": {}, "per_page": []},
  "gsc": {"indexation_ratio": null, "indexed_pages": null, "top_queries": [], "coverage_issues": []},
  "ga4": {"organic_sessions_30d": null, "trend_qoq_pct": null, "top_landing_pages": []},
  "findings": [{"severity": "critical|high|medium|low", "category": "...", "message": "...", "evidence": "...", "recommendation": "..."}],
  "metadata": {"property_url": "...", "date_range": "...", "confidence": "full|partial|limited"}
}
```
