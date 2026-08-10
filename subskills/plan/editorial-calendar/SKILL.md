---
name: editorial-calendar
description: Build/update content publishing calendar with decay-detection scoring. Outputs schedule + suggested refresh priority. Triggered by /calendar command.
allowed-tools: [Read, Write, Bash]
---

# Editorial Calendar

Maintains an editorial schedule with decay-aware prioritization.

## Inputs
- `projects/{slug}/cluster-plans/*.json` (planned content)
- `projects/{slug}/content-inventory.json` (existing articles)
- `projects/{slug}/refresh-queue.json` (decay candidates from monitor)

## Output
`projects/{slug}/editorial-calendar.json`:
```json
{
  "schedule": [
    {"date": "2026-05-22", "task": "publish: best saltwater fishing rod 2026", "priority": 1},
    {"date": "2026-05-29", "task": "refresh: /guide/saltwater-fishing (decay score 38)", "priority": 1},
    ...
  ],
  "decay_alerts": [...]
}
```

## Decay score (per article)
```
decay = 0.30 × traffic_drop_pct
      + 0.25 × rank_drop
      + 0.15 × ctr_decrease
      + 0.15 × freshness_age_pct
      + 0.15 × replacement_pressure
```

Thresholds:
- <30 → URGENT refresh (within 7d)
- 30-50 → schedule refresh in 7d
- 50-75 → schedule refresh in 30d
- >75 → healthy; defer
