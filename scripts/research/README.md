# scripts/research/

High-level research orchestrator scripts. Each combines multiple analysis
modules (in `scripts/analysis/`) to answer a specific research question for
a project.

## Scripts

| Script | Question it answers |
|---|---|
| `seo_baseline_analysis.py` | Where do we stand today on high buyer-intent keywords? |
| `research_quick_wins.py` | Which keywords ranking 11-20 can be pushed to page 1? |
| `research_competitor_gaps.py` | Where are competitors ranking that we aren't? |
| `research_performance_matrix.py` | Which existing pages over/underperform vs their potential? |
| `research_priorities_comprehensive.py` | What's the prioritized action list across all signals? |
| `research_serp_analysis.py` | What does the SERP look like for our target keywords? |
| `research_topic_clusters.py` | How do our keywords cluster by intent + topic? |
| `research_trending.py` | What topics are gaining velocity in our niche? |

## When invoked

- During `/init` Stage 6-7 (SEO baseline establishment)
- Periodically (monthly / quarterly) for portfolio review
- Before launching a new content campaign (`/cluster` planning)
- After `/batch-article` completes a wave (post-mortem)

## How they integrate

```
gsc_api_ingest (or bing_webmaster_ingest)   ← data pull
            ↓
projects/{slug}/metrics/*.json
            ↓
scripts/research/research_quick_wins.py     ← orchestrator
            ↓
       uses
       ┌──────────────┴──────────────┐
       ↓                              ↓
scripts/analysis/dataforseo.py   scripts/analysis/opportunity_scorer.py
scripts/analysis/google_search_console.py
            ↓
projects/{slug}/research/{date}.json + .md
```

## Config dependencies

Most research scripts read from `~/.xuanran-seo/credentials/` for:
- `dataforseo.json` — DataForSEO API (login + password)
- `google-service-account.json` — GSC API
- `google-analytics.json` — GA4 (property ID + SA scope)
- Project-specific: `projects/{slug}/config/competitors.json` — target keywords + competitors

## Typical workflow

```bash
# Weekly portfolio research routine
python -m scripts.research.research_quick_wins --site my-site
python -m scripts.research.research_competitor_gaps --site my-site
python -m scripts.research.research_performance_matrix --site my-site

# Combined priorities (reads all of the above)
python -m scripts.research.research_priorities_comprehensive --site my-site
```

## Output

Per-script output saved to:
- `projects/{slug}/research/{script_name}-{date}.json` (machine-readable)
- `projects/{slug}/research/{script_name}-{date}.md` (human-readable report)
- Aggregated via `perf_report_generator.py` into per-period executive summary

## What these scripts do NOT do

- ❌ Mutate published content (read-only research)
- ❌ Call LLM APIs (deterministic Python analysis only)
- ❌ Replace `/article` or `/batch-article` (they inform what to write, not how)
- ❌ Substitute for `outcome_tagger.py` (which tracks already-published article outcomes)
