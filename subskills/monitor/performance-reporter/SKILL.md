---
name: performance-reporter
description: Aggregate 30+ KPIs across rank/ai-visibility/drift/refresh for time-period view (week/month/quarter). Outputs human-readable executive summary. Triggered by /perf command.
allowed-tools: [Read, Write, Bash]
---

# Performance Reporter

## Inputs (per project)
- `projects/{slug}/rank-history/*.json`
- `projects/{slug}/probes/*.json` (AI engine data)
- `projects/{slug}/drift-report-*.json`
- `projects/{slug}/refresh-queue.json`
- `projects/{slug}/change-log.json` (publish actions)

## Output

`projects/{slug}/perf-{period}-{date}.md`:

```markdown
# Performance Report — {brand} — {period} ending {date}

## Headlines
- Total impressions: {N} ({±}% vs prev period)
- Total clicks: {N} ({±}%)
- Avg position: {pos} ({±})
- AI engine citations: {chatgpt:N, pplx:N, claude:N, gemini:N}

## New articles this period
- {count} published
- {count} reached page 1 within {N} days
- {count} earned AIO citation

## Refresh activity
- {count} articles refreshed
- Avg decay improvement: {pts}

## Issues
- {count} articles in drift alert state
- {count} lost AI engine citations
- {count} need urgent refresh

## Recommendations
- Top 3 priority actions for next period
```

## Periods
- week
- month
- quarter
- year (executive summary)

## See also
- `scripts/monitor/perf_report_generator.py` (TODO)
