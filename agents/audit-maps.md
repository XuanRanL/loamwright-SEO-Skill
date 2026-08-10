---
name: audit-maps
description: GBP 25-field completeness audit, review intelligence, competitor radius mapping, and geo-grid ranking analysis for local map pack optimization
tools: [Read, Bash, Write, Glob, Grep]
maxTurns: 60
---

# Audit Maps Agent

## Spawn Condition
Only run when `audit-local` was spawned AND at least one of: geoapify key, dataforseo key, or `{audit_dir}/gbp-data.json` exists.

## Inputs
- `{audit_dir}/modules/local.json`, `{audit_dir}/gbp-data.json`, `{audit_dir}/config.json`

## Scripts
- `python -m scripts.audit.geoapify_grid --lat {lat} --lng {lng} --radius {km} --keyword {kw} --json`
- `python -m scripts.audit.gbp_field_audit --profile {gbp_json_path} --json`
- `python -m scripts.audit.review_sentiment --reviews {reviews_path} --json`

## Checks

### 1. GBP 25-Field Audit
Verify each populated & optimized. Critical fields: business name (exact legal), primary category, phone (local preferred), website (HTTPS + UTM), address (NAP match). High: secondary categories (up to 9), description (750 chars, keyword + city first sentence), regular hours (all 7 days), photos (exterior 3+, interior 3+, product 5+), services list, posts (< 7 days). Medium: special hours, team photos 2+, cover 1332x750, attributes, Q&A (5+ seeded), booking link. Low: opening date, messaging, short name. Score = weighted populated / 25.

### 2. Review Intelligence
Total count vs top-3 local-pack competitors. Sentiment: top 5 positive + negative keywords. Owner response rate (target 80%+) and avg response time (< 24h optimal). Keyword mentions in reviews. Photo-reviews count. Source distribution (Google vs Yelp vs Facebook).

### 3. Competitor Radius
Identify top 10 competitors within service radius sharing primary category. Compare review count, rating, photo count, post recency, category overlap. Classify market position: leader / competitive / catching_up / trailing.

### 4. Geo-Grid Ranking (if API available)
5x5 or 7x7 grid across service area. Query primary keyword per point, record rank 1-20. Generate heatmap data: strong zones vs weak zones. If unavailable, redistribute weight.

### 5. Photo Audit
Benchmark: local pack median = 11+ photos. Recency < 30 days. Diversity: exterior/interior/team/products. Quality: resolution, geotagging. Delta vs top 3 competitors.

### 6. Post Analysis
Frequency (weekly optimal), recency (> 14d = stale), type variety (Update/Offer/Event/Product), CTA usage.

## Scoring
`(completeness*0.30) + (reviews*0.25) + (competitor*0.20) + (geo_grid*0.15) + (photos*0.10)` — if no geo-grid, use 0.35/0.30/0.25/0.10.

## Output → `{audit_dir}/modules/maps.json`
```json
{
  "module": "maps", "score": 0-100,
  "gbp_completeness": {"populated": N, "total": 25, "score": 0-100, "missing_critical": []},
  "review_intelligence": {"total_reviews": N, "avg_rating": N, "sentiment": {"positive_keywords": [], "negative_keywords": []}, "response_rate": 0.0, "velocity_monthly": N},
  "competitor_analysis": {"competitors_found": N, "market_position": "...", "gaps": []},
  "geo_grid": {"available": false, "grid_size": "5x5", "avg_rank": N, "coverage_pct": 0},
  "findings": [{"severity": "critical|high|medium|low", "category": "...", "message": "...", "evidence": "...", "recommendation": "..."}],
  "metadata": {"apis_used": [], "grid_center": {}, "radius_km": N}
}
```
