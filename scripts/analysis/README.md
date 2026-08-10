# scripts/analysis/

Deterministic Python analysis modules. Each exposes a focused capability used
by higher-level orchestrators in `scripts/research/`, `subskills/*/SKILL.md`,
and `agents/*.md`.

## Modules

### Data source clients (external APIs)
- `dataforseo.py` — DataForSEO API client (SERP, keyword volume, ranks)
- `google_search_console.py` — GSC Search Analytics API (overlaps with `scripts/monitor/gsc_api_ingest.py`; prefer the monitor one)
- `google_analytics.py` — GA4 API client (sessions, conversions, engagement)
- `wordpress_publisher.py` — WP REST publisher (overlaps with `scripts/wordpress/wp_publisher.py`; prefer the canonical one)

### Content scoring
- `content_scorer.py` — composite content quality score
- `seo_quality_rater.py` — SEO-specific rating
- `readability_scorer.py` — Flesch-Kincaid + sentence complexity
- `trust_signal_analyzer.py` — E-E-A-T signal detection in body content
- `content_length_comparator.py` — length vs competitor depth analysis

### SEO analysis
- `keyword_analyzer.py` — keyword categorization + difficulty estimation
- `search_intent_analyzer.py` — intent classification (informational / commercial / transactional / navigational)
- `competitor_gap_analyzer.py` — finds keywords competitors rank for that we don't
- `opportunity_scorer.py` — prioritizes keyword opportunities by (volume × win-probability × business value)

### Page-level analysis
- `above_fold_analyzer.py` — what shows in first viewport
- `landing_page_scorer.py` — landing page quality
- `landing_performance.py` — conversion + bounce metrics
- `cta_analyzer.py` — CTA presence + placement quality
- `cro_checker.py` — CRO best practices audit
- `engagement_analyzer.py` — dwell time, scroll depth, interaction signals

### Content production helpers
- `article_planner.py` — article outline planning logic
- `section_writer.py` — section drafting helpers
- `content_scrubber.py` — content cleanup utilities

### Aggregation
- `data_aggregator.py` — combines signals from multiple data sources
- `social_research_aggregator.py` — pulls signals from social platforms

## Usage pattern

Modules are called either:
1. From `scripts/research/research_*.py` orchestrators (typical path)
2. Directly by L3 subskill SKILL.md via `python -c "from analysis.X import Y; ..."`
3. By agents that need deterministic analysis (e.g., `seo-auditor.md`)

### Direct invocation example

```python
import sys
sys.path.insert(0, "scripts/analysis")

from search_intent_analyzer import SearchIntentAnalyzer
from opportunity_scorer import OpportunityScorer

intent = SearchIntentAnalyzer().classify("best fishing rods 2026")
# → {"intent": "commercial", "confidence": 0.84}

scorer = OpportunityScorer()
opps = scorer.score(by_url_data)
# → [{"url": "...", "opportunity_score": 87, "reason": "..."}, ...]
```

## Config + credentials

Each external-API module reads credentials from `~/.xuanran-seo/credentials/`:
- `dataforseo.json` — `{"login": "...", "password": "..."}`
- `google-service-account.json` — Google service account JSON
- `google-analytics.json` — GA4 property ID + scope

See `scripts/_core/credential_hub.py` for the canonical credential model.

## Cross-module dependencies

Some modules import from each other:
- `research_*.py` → `opportunity_scorer`, `search_intent_analyzer`, `dataforseo`, etc.
- `competitor_gap_analyzer` → `dataforseo`
- `data_aggregator` → multiple data source clients

All cross-imports use flat module-name imports (no nested package structure).

## Overlapping modules

Some functionality duplicates what exists elsewhere in our project. The
canonical version is in the location listed below; the analysis module is
kept for orchestrator scripts that imported it before the canonical version
existed:

| Module here (analysis) | Canonical version | Action |
|---|---|---|
| `google_search_console.py` | `scripts/monitor/gsc_api_ingest.py` | Prefer canonical for new code |
| `wordpress_publisher.py` | `scripts/wordpress/wp_publisher.py` | Prefer canonical |

## Not in this directory

- Linters (style, AI-tells) → `scripts/lint/`
- Quality scorers (CORE-EEAT, CITE, AI-Slop) → `scripts/validate/`
- Build helpers (assemble, slug, anchor) → `scripts/build/`
- Image pipeline → `scripts/image/` + `scripts/openai/`
- Monitor (rank, drift, AI citation) → `scripts/monitor/`
- WordPress publishing → `scripts/wordpress/`
- Cost/credentials/file-bus core → `scripts/_core/`
