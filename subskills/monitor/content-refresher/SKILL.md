---
name: content-refresher
description: Compute 0-100 decay score; trigger refresh workflow on aging articles. Score = 0.30×traffic + 0.25×rank + 0.15×ctr + 0.15×freshness + 0.15×replacement. Triggered by /refresh command or weekly schedule.
allowed-tools: [Read, Write, Bash, Task]
---

# Content Refresher

## Decay score formula
```
decay = 0.30 × traffic_drop_pct
      + 0.25 × rank_drop_normalized
      + 0.15 × ctr_decrease_pct
      + 0.15 × freshness_age_normalized
      + 0.15 × replacement_pressure
```

## Data sources (real executors — Rule 6)

3 of the 5 inputs come from the connected first-party Google data — pull them per project
(IDs live in `projects/{slug}/business-context.json :: analytics`):

```bash
# traffic_drop_pct ← GA4 organic sessions over the window
python -m scripts.audit.ga4_fetch --property-id {analytics.ga4_property_id} --days 28 --json
# rank_drop_normalized + ctr_decrease_pct ← GSC position/CTR per URL over time
python -m scripts.monitor.gsc_api_ingest --site {slug} --mode last-28 --json
```

`freshness_age_normalized` = days since dateModified; `replacement_pressure` = SERP churn for
the target keyword (`scripts.fetch.serpapi_query --engine google`). Degrade gracefully: a project
whose GA4 property is brand-new (0 traffic rows) scores `traffic_drop=0` until data accumulates —
empty GA4 is NOT a crash. Both Google sources authenticate through `scripts/_core/google_creds.py`
(the unified token), so no per-call credential setup is needed.

| Score | Action |
|---|---|
| <30 | URGENT — refresh within 7d |
| 30-50 | Refresh in 7d |
| 50-75 | Refresh in 30d |
| >75 | Healthy; defer |

## Action routing (don't always full-rewrite)

Before doing a full rewrite, run the decision router — it diagnoses the signal and names the
MINIMAL sufficient action, so a top-10 page that's only under-clicked gets a cheap title/meta fix
(`meta-builder`) instead of a $0.45 rewrite, and a tag-page "content gap" gets a NEW article:

```bash
python -m scripts.monitor.refresh_decision_router --site {slug} --json   # → refresh-plan.json
```

Map the plan's `recommended_skill` to the action below. The full rewrite workflow here is the
DEEP_WEAK / PAGE2_DEPTH path; LOW_CTR → meta-builder, NOT_IN_AI → ai-overview-recovery,
CONTENT_GAP → `/article`, CANNIBALIZE → consolidate.

## Refresh workflow

When triggered for a URL (DEEP_WEAK / PAGE2_DEPTH path):
```
1. Read existing post (via WP REST GET /posts/{id})
2. Spawn researcher to find what's changed since publish (new data, new competitors)
3. Spawn writer agent in "rewrite" mode for affected sections
4. Update dateModified
5. Re-publish via wordpress-publisher (PATCH same post_id, don't create new)
6. Re-trigger indexing-notifier
```

## See also
- `subskills/monitor/drift-detector/SKILL.md` (related; detects HOW content changed)
- `subskills/cross-cutting/repair-orchestrator/SKILL.md` (escalation if refresh fails)
