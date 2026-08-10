---
name: ai-visibility-tracker
description: Active probe of ChatGPT/PPLX/Claude/Gemini to check if our article is cited. Compares to projects/{slug}/geo-baseline.json. Triggered by /ai-visibility command or daily/weekly schedule.
allowed-tools: [Read, Write, Bash]
---

# AI Visibility Tracker

Re-runs `scripts.fetch.ai_search_probe` periodically per article.

## Workflow
```bash
python -m scripts.fetch.ai_search_probe \
    --brand "{brand}" \
    --domain "{domain}" \
    --engines chatgpt,perplexity,claude,gemini \
    --queries "specific queries from this article's title + variants" \
    --json > projects/{slug}/probes/{engine}-{date}.json
```

Compare to baseline:
- ai_resolution_status improvement / regression
- Citation count change
- Brand mention frequency change

## Alert triggers
| Condition | Action |
|---|---|
| Engine status: recognized → partial/unrecognized | Warning (P2) |
| All engines went partial/unrecognized | Critical (P1) |
| Brand mentioned but "confused" with another | Emergency (P0) |
| Factual errors increased | High (P2) |
| New citation by engine | Info (P3, positive!) |

## Schedule
- Tier 1 articles (revenue-critical): daily
- Tier 2: weekly
- Tier 3 (most): monthly
- Brand-level probes: daily

## See also
- `scripts/fetch/ai_search_probe.py`
- `references/geo/geo-score-feedback-loop.md` (T+14/45/90 windows)
