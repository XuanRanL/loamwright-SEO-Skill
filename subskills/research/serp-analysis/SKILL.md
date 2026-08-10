---
name: serp-analysis
description: Identifies SERP features for a keyword (featured_snippet / video / image_pack / shopping / AI_overview / PAA / knowledge_panel / site_links). Use to inform format selection and content planning. Triggered when user requests SERP analysis, asks "what's the SERP for X", or before format selection in /article pipeline.
allowed-tools: [Read, Write, Bash]
---

# SERP Analysis

Detects which SERP features are present for the primary keyword. Drives:
- Format selection (if SERP has lots of video → news/listicle format; if AIO → optimize for AI citation)
- Featured Snippet / AI Overview extraction targeting (owned by `subskills/build/citation-capsule-builder/` since v3.35; sets outline `is_featured_snippet_target`)
- AI Overview targeting (`subskills/optimize/geo-content-optimizer/`)

## Inputs

- `state.brief.primary_keyword`
- `target_market_locale` (for geo-specific SERP)

## Output

Updates `workspace/{task_id}/research.json`:
```json
{
  "serp_features": ["featured_snippet", "video", "ai_overview", "paa_box"],
  "ai_overview_present": true,
  "ai_overview_cited_sources": ["https://example.com/...", ...]
}
```

⚠️ **Populate `serp_features[]` with EVERY observed feature** — mirror every true flag in
`_serp_features_detail` (ai_overview, paa_box, featured_snippet, video, directory_results,
reddit_top_results, paid_ads, local_pack, image_pack, shopping_results, site_links). The
serp-analysis stage auto-completes only at `>=3` entries; surfacing only a subset (e.g. 2 of
5 real features) needlessly stalls the runner and forces a re-dispatch (2026-06-29).

## Workflow

```
1. python -m scripts.fetch.tavily_search "{primary_keyword}" --max 10 --include-answer
2. Parse Tavily response for signals:
   - Tavily "answer" field present + high quality → featured_snippet likely
   - URLs ending in /watch?v= or youtube.com → video pack
   - Image URLs in results → image_pack
   - Shopping links / "shop now" CTAs → shopping
   - "People also ask" header in snippets → paa_box
3. For AI Overview detection:
   - Tavily doesn't directly show AIO, but we can heuristic:
     - If query is informational + Tavily "answer" exists + matches top-3 content → AIO likely
     - Cross-reference with manual SERP check note (TODO M1.5: add SerpAPI integration)
4. For AIO source identification:
   - Look at Tavily top-3 by score → these are likely AIO sources
   - List them in ai_overview_cited_sources
5. Save to research.json
```

## Cost

1× Tavily basic = 1 credit = $0.008

## Handoff

`recommended_next_skill`: `competitor-analysis` (uses serp_features to weight competitor priority)

## See also

- `scripts/fetch/tavily_search.py`
- `subskills/build/citation-capsule-builder/SKILL.md` (absorbed featured-snippet duty, v3.35)
- `subskills/optimize/ai-overview-recovery/SKILL.md`
