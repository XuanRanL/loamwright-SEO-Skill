---
name: competitor-analysis
description: Deep extract top-5 SERP competitors via Tavily 5-tier waterfall. For each: title/meta/H2 structure/word count/schema types/content gap. Triggered by phase-research after serp-analysis.
allowed-tools: [Read, Write, Bash, Task]
---

# Competitor Analysis

## Inputs
- `research.json` (top-10 SERP URLs from keyword-research)
- Own domain (excluded from competitor list)

## Workflow
1. Filter top-10 to top-5 (exclude own domain + aggregators like Amazon if not aggregator-focused)
2. For each: `python -m scripts.fetch.multi_tier_fetch {url}` (use 5-tier waterfall)
3. `python -m scripts.fetch.parse_html {html_file} --json` to extract title/meta/H2/schema
4. LLM analyzes content_gap: what did THIS competitor cover shallowly vs deeply?
5. Save to `workspace/{task}/research/competitors/{i}.json`
6. **Competitor-citation candidate review (Rule 8).** The SERP competitor domains
   you just identified are, by definition, peers ("同行"). Diff them against the
   project's enforced blocklist and surface any NEW ones for the operator to
   approve — never auto-block (avoids false-positives on neutral sites that merely
   rank, e.g. Wikipedia/.gov):

   ```bash
   python -m scripts._core.competitor_domains --task {task_id} --json   # current blocklist + enabled?
   ```

   For each competitor domain NOT already in `do_not_cite_domains`, append it to
   `workspace/{task}/competitor-candidates.json` as `{"domain": ..., "source": "serp",
   "keyword": ...}` and note it in the research handoff so the operator can promote
   genuine competitors into `business-context.json :: citation_source_policy.do_not_cite_domains`.
   These candidates are NOT enforced until promoted.

## Output schema fragment (added to research.json)
```json
"competitor_titles": [
  {
    "title": "Best Fishing Rods 2026 — Saltwater Guide",
    "url": "https://competitor.com/...",
    "domain": "competitor.com",
    "word_count_estimate": 3200,
    "content_gap": "Missing pricing comparison; weak on saltwater-specific testing",
    "schema_types": ["Article", "BlogPosting"],
    "freshness_days": 42
  }
]
```

## Cost
- 5 × Tavily advanced extract = 5 credits ($0.04)
- 1 × Claude Opus synthesis = $0.05
- Total: ~$0.10
