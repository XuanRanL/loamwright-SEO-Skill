---
name: fleet-view
description: Multi-site agency dashboard. Use /fleet to see 100+ sites in one view — health, clicks, cost, drift alerts, by-client + by-vertical aggregation. Daily landing page for an operator managing many SEO projects.
allowed-tools: [Bash, Read]
disable-model-invocation: false
user-invocable: true
---

# Fleet View

Single screen for someone running an SEO agency with 100+ sites across multiple
clients and verticals.

## When to invoke

- `/fleet` — full multi-site dashboard
- `/fleet --client acme-corp` — filter to one client's sites
- `/fleet --vertical b2b-saas` — filter by vertical
- Daily landing page after morning coffee — what needs attention?

## How to invoke

```bash
python -m scripts._core.fleet_view
python -m scripts._core.fleet_view --client client-a
python -m scripts._core.fleet_view --vertical b2c-ecom
python -m scripts._core.fleet_view --json
```

## Output (human)

```
━━ Fleet view ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Generated:    2026-05-19T14:32:01Z
  Sites:        127  (38 new articles / 30d)
  Total articles: 4,213
  Impressions:  18,432,100 / 30d
  Clicks:       412,330 / 30d
  Cost:         $1,847.32 / 30d

  Health:
    ✓ ok        103
    ⚠ watch      18
    🔴 critical    6

  By vertical:
     67  b2b-saas
     34  b2c-ecom
     19  publisher
      7  agency

  By client:
     45 sites  $  723.40   201,440 clk  ( 3 drift)  own
     28 sites  $  421.00   118,322 clk  ( 7 drift)  acme-corp
     20 sites  $  345.21    62,128 clk  ( 4 drift)  beta-llc
     ...

  Top performers (30d clicks):
    14,832 clk  pos  3.2  example-site-1
     8,217 clk  pos  4.1  example-site-2
     ...

  Needs attention:
    [critical]  site-x  (5 drift alerts; Lost AI citations)
    [watch]    site-y  (No clicks last 30d despite publishing)
```

## Project metadata for fleet (project.yaml)

For the fleet view to surface per-vertical and per-client, each project's
`projects/{slug}/project.yaml` should have:

```yaml
site_url: https://example.com
client: acme-corp          # or "own" for self-managed
vertical: b2b-saas         # b2b-saas | b2c-ecom | publisher | agency | local | other
```

If missing, site appears under `uncategorized` vertical and `own` client.

## Health categorization rules

| Health | Trigger |
|---|---|
| **ok** | No issues |
| **watch** | 1 issue: drift alerts >0 / no recent clicks / spend >$50/30d |
| **critical** | 2+ issues OR ≥5 drift alerts OR ≥$100 cost with declining clicks |

## Aggregation efficiency

For 100+ sites, the script reads:
- `projects/{slug}/project.yaml` (metadata)
- `projects/{slug}/articles/*/publish-log.json` (counts)
- `projects/{slug}/metrics/gsc-*.json` (latest 30d traffic)
- `projects/{slug}/drift-reports/*.json` (severity counts)
- `projects/{slug}/ai-citations/*.json` (citation counts)
- `~/.xuanran-seo/cost-ledger.jsonl` (cost rollup, filtered by project_slug)

Typical execution: 100 sites × ~5 files each = 500 file reads, ~3 seconds.

## What this skill does NOT do

- ❌ Mutate site state (read-only summary)
- ❌ Trigger refreshes (use `/refresh-queue`)
- ❌ Pull fresh GSC/Bing data (use `gsc_api_ingest` first)
- ❌ Detailed per-article view (use `/portfolio --site X`)

## Composition

```
Daily routine for an agency operator:

1. /fleet                                 → see what needs attention
2. gsc_api_ingest --all-sites --mode weekly  → pull fresh data
3. rank_tracker --all-sites               → compute T+N rank deltas
4. /fleet                                 → see updated health
5. For each "critical" site: /portfolio --site X → dig in
6. drift_compare for flagged URLs
7. /refresh-queue based on findings
```
