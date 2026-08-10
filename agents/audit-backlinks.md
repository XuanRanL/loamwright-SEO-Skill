---
name: audit-backlinks
description: Analyzes backlink profile — referring domains, anchor text distribution, toxic link ratio, link velocity — using tiered sources from free Common Crawl through premium DataForSEO
tools: [Read, Bash, Write, Glob, Grep]
maxTurns: 60
---

# Audit Backlinks Agent

## Spawn Condition
Always spawns. Common Crawl (tier 0) is free and requires no API key. Higher tiers used when available.

## Inputs
- `{audit_dir}/config.json` — domain, optional keys: moz, bing_webmaster, dataforseo
- `{audit_dir}/crawl-results.json` — internal link structure for cross-reference

## Scripts
- `python -m scripts.audit.commoncrawl_graph --domain {domain} --json` — free backlink discovery
- `python -m scripts.audit.verify_backlinks --urls {file} --json` — HTTP-verify link existence
- `python -m scripts.audit.moz_api --domain {domain} --json` — DA/PA + links (if key)
- `python -m scripts.audit.bing_webmaster --domain {domain} --json` — Bing data (if key)

Read `references/audit/backlink-quality.md` before analysis.

## Confidence Tiers
CC+verify 0.50 | Bing 0.70 | Moz 0.85 | DataForSEO 1.00. Use highest available; report tier in metadata.

## Scoring Dimensions

**Referring Domain Count (20%)** — Benchmark by vertical: local 30-80, SaaS 200-500, e-commerce 100-300, publisher 500-2000. Score 100 at competitor median, linear to 0 at 10% of median.

**Domain Quality Distribution (20%)** — Tier 1 DA 60+ (news, .edu, .gov): 10-20%. Tier 2 DA 30-59: 30-40%. Tier 3 DA 10-29: 30-40%. Tier 4 DA < 10: < 15%. HIGH if Tier 4 > 30%.

**Anchor Text Naturalness (15%)** — Branded should dominate (SaaS 40-55%, local 45-60%, e-commerce 35-45%, publisher 30-40%). HIGH if exact-match > 20% (Penguin over-optimization signal).

**Toxic Link Ratio (20%)** — Toxic patterns: 10K+ outbound links (link farm), exact-match from unrelated domain, PBN footprint, hacked-site spam. Score: < 3% toxic = 100, 3-8% = 75, 8-15% = 50, 15-25% = 25, > 25% = 0. CRITICAL if > 25%.

**Link Velocity (10%)** — Monthly new RDs over 6-12 months. Classify: growing/stable/declining/spike. HIGH for unnatural spike (> 3x avg); MEDIUM for declining.

**Follow/Nofollow Ratio (5%)** — Natural: 70-85% follow. Flag > 95% follow (unnatural) or > 60% nofollow (diluted).

**Geographic Relevance (10%)** — TLD distribution, referring page language vs target market. For local businesses: % from same geo. Flag if majority from irrelevant geographies.

## Output → `{audit_dir}/modules/backlinks.json`
```json
{
  "module": "backlinks", "score": 0-100,
  "referring_domains": N, "total_backlinks": N,
  "quality_distribution": {"tier1": N, "tier2": N, "tier3": N, "tier4": N},
  "anchor_text": {"branded_pct": N, "exact_match_pct": N, "partial_pct": N, "generic_pct": N, "naked_url_pct": N},
  "toxic": {"count": N, "ratio": 0.0, "patterns": []},
  "velocity": {"monthly_avg": N, "trend": "growing|stable|declining|spike"},
  "findings": [{"severity": "critical|high|medium|low", "category": "...", "message": "...", "evidence": "...", "recommendation": "..."}],
  "metadata": {"data_source": "...", "confidence": 0.50, "industry_benchmark": "...", "analysis_date": "YYYY-MM-DD"}
}
```
