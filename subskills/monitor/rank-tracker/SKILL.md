---
name: rank-tracker
description: Query GSC for impressions/clicks/position; T+7/14/30/90 post-publish baselines. Outputs projects/{slug}/rank-history-{date}.json. Triggered by /rank-check command or scheduled monitor.
allowed-tools: [Read, Write, Bash]
---

# Rank Tracker

## Schedule
After publish, register T+7 / T+14 / T+30 / T+90 callbacks for each URL.

## Workflow
```
1. python -m scripts.monitor.rank_tracker --site {site_slug} --url {url}  # TODO
2. Query Google Search Console API: impressions, clicks, position, queries
3. Compare to baseline (projects/{slug}/seo-baseline.json)
4. Compute deltas:
   - Position change → traffic impact (use #1→#2 = -55% table)
   - Click change
   - New query rankings
5. Save to projects/{slug}/rank-history/{YYYY-MM-DD}.json
6. If rank dropped >5 positions: alert + trigger content-refresher
```

## Position → traffic impact table
| Position | Click share |
|---|---|
| #1 | 31% |
| #2 | 14% |
| #3 | 9% |
| #4 | 6% |
| #5 | 4% |
| #6-10 | ~2-3% each |
| #11+ | <2% |

## See also
- `scripts/monitor/rank_tracker.py` (TODO)
- GSC API: https://developers.google.com/webmaster-tools
