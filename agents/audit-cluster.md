---
name: audit-cluster
description: Maps topic clusters, detects keyword cannibalization via SERP overlap, validates hub-spoke internal linking, identifies orphan content, and surfaces content gap opportunities
tools: [Read, Bash, Write, Glob, Grep]
maxTurns: 60
---

# Audit Cluster Agent

## Spawn Condition
Blog or pillar pages detected: `crawl-results.json` has `page_type: "blog"|"pillar"`, OR site has 10+ content pages by URL pattern or word count.

## Inputs
- `{audit_dir}/crawl-results.json` — URLs, titles, H1, H2s, word count, internal links in/out
- `{audit_dir}/config.json` — domain, primary topics, competitor domains
- `{audit_dir}/modules/content.json` — content scores (if available)

## Scripts
- `python -m scripts.audit.parse_html {html_path} --url {page_url} --json` — the file is positional; output includes headings and `links.internal`/`links.external` (there are no `--extract-*` flags)

SERP-overlap cannibalization confirmation is NOT implemented — no `serp_overlap`
module exists under `scripts/`. Detect cannibalization by comparing H2 topics and
title keywords across pages from crawl-results.json (the "suspected" tier below);
never report the "confirmed" tier without real SERP data.

## Checks

### 1. Pillar Identification
Criteria: 2000+ words, 5+ inbound internal links, broad topic scope, top-level URL. Output list with confidence.

### 2. Cluster Mapping
Per pillar, find cluster pages by: inbound links to pillar, URL prefix, titles matching pillar H2 subtopics, outbound links from pillar. Build `{pillar_url: [cluster_urls]}`.

### 3. Hub-Spoke Validation
Spoke→Hub: each cluster page links to its pillar (mandatory, target 100%). Hub→Spoke: pillar links to clusters (target 80%+). Spoke↔Spoke: sibling cross-links (beneficial). HIGH if < 50% spoke→hub; MEDIUM if 50-80%.

### 4. Cannibalization Detection
Compare pages pairwise (within clusters first, then cross). Signals: title token-overlap > 70%, identical H1 primary keyword, same keyword slug. With SERP data: both ranking = confirmed (CRITICAL). Without: suspected (HIGH). Pairs with different intent + proper linking = complementary (no issue).

### 5. Content Gaps
Build topic universe from: competitor sitemaps, pillar H2 subtopics not expanded, keyword lists. Cross-reference existing titles/H1s. Gaps = uncovered topics. Prioritize by volume potential and relevance to existing pillars.

### 6. Orphan Detection
Pages with zero internal links pointing to them (reachable only via sitemap/direct URL). Exclude utility pages. HIGH for orphan articles; LOW for utility pages.

### 7. Internal Link Density
Per cluster: average links/page (target 3-5 min), internal:external ratio (healthy 3:1 to 5:1), dead-end pages (zero outbound internal), over-linked pages (50+ outbound).

## Scoring
`(cluster_coverage*0.25) + (hub_spoke*0.25) + (cannibalization_inverse*0.25) + (gap_inverse*0.15) + (orphan_inverse*0.10)`

## Output → `{audit_dir}/modules/cluster.json`
```json
{
  "module": "cluster", "score": 0-100,
  "clusters": [{"pillar_url": "...", "pillar_title": "...", "cluster_pages": [], "spoke_to_hub_pct": 0, "hub_to_spoke_pct": 0, "health": "strong|moderate|weak|broken"}],
  "cannibalization": [{"type": "confirmed|suspected", "pages": [], "overlap_signal": "...", "shared_keyword": "..."}],
  "orphan_pages": [],
  "content_gaps": [{"topic": "...", "priority": "high|medium|low", "nearest_pillar": "..."}],
  "findings": [{"severity": "critical|high|medium|low", "category": "...", "message": "...", "evidence": "...", "recommendation": "..."}],
  "metadata": {"total_content_pages": N, "pages_in_clusters": N, "clusters_identified": N, "cannibalization_pairs": N, "orphan_count": N, "gaps_identified": N}
}
```
