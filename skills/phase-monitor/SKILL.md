---
name: phase-monitor
description: Run Phase Monitor — rank tracking, AI visibility tracking, drift detection, content refresh signals, performance reporting. Use for post-publish monitoring or scheduled checkup. Triggered by /seo-blog monitor, /perf, /rank-check, /drift, /ai-visibility, or as automated scheduled hook (T+7/14/30/90 after publish).
allowed-tools: [Read, Write, Bash, Task]
disable-model-invocation: false
---

# Phase Monitor Orchestrator

Closed-loop monitoring: detect changes → feed back to Optimize phase.

> Unlike other phases this runs **asynchronously** (scheduled), not in a synchronous user-initiated chain.

## Inputs

- `state.project_slug` (required, monitor is always per-project)
- Optional `state.target_urls[]` (specific URLs to check; else all published URLs in change-log)

## Stages (run in parallel, independent)

```
1. rank-tracker
   - Query GSC for impressions/clicks/position per URL (your property only)
   - SerpApi (engine=google) = LIVE SERP rank for tracked keywords incl. competitors —
     GSC only sees your own property; SerpApi sees the whole SERP. Pooled free 250/mo:
     `python -m scripts.fetch.serpapi_query --engine google --q "{keyword}" --gl {cc} --json`
     → find your domain's position in organic_results; record competitor positions too
   - Compare to baseline (projects/{slug}/baselines/)
   - T+7 / T+14 / T+30 / T+90 windows
   - Position change → traffic impact table (#1→#2 = -55%)
   - Output: projects/{slug}/rank-history-{date}.json

2. ai-visibility-tracker
   - Active probe: ChatGPT/PPLX/Claude/Gemini × 5 queries per article
   - SerpApi AI-answer engines = is the article's domain CITED in each engine's AI answer?
     Track BOTH distinct Google GEO surfaces (they cite independently):
       · `--engine ai_overview`    → Google AI Overview (inline summary): check its `references[]` links
       · `--engine google_ai_mode` → Google AI Mode (the dedicated AI tab): richer `references[]`
         ({title, link, source, snippet}) + reconstructed_markdown — a SECOND, independent GEO signal
     Plus `--engine bing` (Bing/Copilot surface). For each engine, match the project domain against
     every `references[].link` → cited? at what rank/index? Record per engine + per query.
     Structured + repeatable; complements the ChatGPT/PPLX/Claude/Gemini LLM probes.
     (Non-US target markets: `naver` / `baidu` are also callable.)
   - Compare to geo-baseline.json
   - ai_resolution_status changes: recognized → partial = alert
   - Cumulative citation count over time
   - Output: projects/{slug}/probes/{engine}-{date}.json

3. drift-detector
   - SHA-256 hash content + meta + schema
   - Compare to projects/{slug}/baselines/{snapshot}.sqlite
   - 17-rule diff (claude-seo pattern)
   - 3 severity levels: critical / high / medium
   - Output: drift-report-{date}.json + new baseline if approved

4. content-refresher
   - Compute decay score (0-100): traffic 30 + rank 25 + CTR 15 + freshness 15 + replacement 15
   - SerpApi `--engine google_trends` interest trajectory for the head term → a declining search-
     interest trend is an early decay signal feeding the freshness component (topic cooling, not
     just rank loss)
   - Threshold actions:
     - <30 → urgent refresh
     - 30-50 → schedule refresh in 7d
     - 50-75 → schedule refresh in 30d
     - >75 → healthy, defer
   - Output: refresh-queue.json

5. performance-reporter
   - Aggregate 30+ KPIs from all 4 above
   - Time periods: week / month / quarter
   - Include AI citation KPIs (per-engine)
   - Output: projects/{slug}/perf-{period}-{date}.md
```

## Alert routing (σ-based severity)

```
P0 (3σ deviation, Emergency): SMS + phone + Slack
P1 (2σ, Critical):            Slack + Email
P2 (1.5σ, Warning):           Email
P3 (1σ, Info):                weekly digest
```

Suppression rules:
- 24h cooldown for same alert
- Weekend +20% threshold (avoid alert storms)
- Maintenance windows (configurable)
- Batch correlation (group related alerts)
- Recovery auto-close

## Triggers

### Manual
- `/rank-check <url>`
- `/ai-visibility <url>`
- `/drift <domain>`
- `/perf <domain>` → full report
- `/alerts` → current alert list

### Scheduled (via hooks/scheduled.json)
- Daily: ai-visibility-tracker for high-priority articles
- Weekly: rank-tracker + drift-detector
- Monthly: performance-reporter (executive summary)

### Event-driven
- New article published → register T+7/14/30/90 callbacks
- Drift detected critical → auto-trigger `/aio-recovery` for AIO-loss case

## Feedback loop (executable dispatcher — Rule 6)

Monitoring is only useful if it drives ACTION. The **decision router** turns the first-party
GSC data into a prioritized, signal-typed optimization plan that names the MINIMAL sufficient
skill per opportunity — instead of a human reading the report and full-rewriting everything:

```bash
# diagnose one project (or --all) → projects/{slug}/audits/refresh-plan.json + ranked report
python -m scripts.monitor.refresh_decision_router --site {slug} --json
```

It classifies each opportunity by signal and routes it (grounded in 2026 CTR/GEO thresholds):

| Signal (auto-detected) | Action | Skill to run |
|---|---|---|
| **CONTENT_GAP** — a tag/category archive ranks a query (no dedicated article) | create | `seo-blog` `/article` (check cannibalization first) |
| **PAGE2_DEPTH** — real article pos 11-20, high impr, ~0 clicks | optimize (depth) | `subskills/cross-cutting/rewrite/` (full) |
| **LOW_CTR** — real article top-10 but CTR < ½ the position benchmark | optimize (surgical) | `subskills/optimize/meta-builder/` (title/meta only) |
| **DEEP_WEAK** — real article pos > 20 | optimize (comprehensive) | `subskills/cross-cutting/rewrite/` |
| **NOT_IN_AI** — query triggers AI Overview/Mode, our domain not cited | optimize (GEO) | `subskills/optimize/ai-overview-recovery/` |
| **CANNIBALIZE** — 2+ of our pages rank the same query | consolidate | `rewrite` audit + manual 301 |
| "Schema broken" (drift-detector) | fix | `subskills/optimize/schema-generator/` |

**DRAFT-FIRST / human-in-the-loop:** the router only WRITES the plan — it never mutates or
republishes a live post. Each action is executed as a separate, gated step via the named skill
(which republishes as a draft by default, per Rule 5a). The router replaces the *triage*, not the
*review*.

### Second axis — content quality (the router is signal-only)

The router acts on SEARCH signals (CTR/rank/AI) and never reads the body, so it misses a post that
ranks fine yet is thin, stale, orphaned or weakly-sourced. Run the content scanner as the
complementary CONTENT axis:

```bash
python -m scripts.monitor.content_audit --site {slug} --json   # → projects/{slug}/audits/content-audit.json
```

It flags (mechanical, cheap): THIN, STALE, ORPHAN (<3 distinct internal links), THIN_SOURCING
(<2 distinct external citations — an E-E-A-T risk on YMYL), YEAR_DRIFT. Fix ORPHAN with
`internal-linker`, THIN_SOURCING by adding authoritative citations (`mcp__us-gov__*` /
`mcp__pubmed__*`), THIN/STALE via `rewrite` `/update`. What it CANNOT see — factual errors,
outdated specifics, citation AUTHORITY — needs an LLM read: route those posts to the
`fact-checker` agent / `rewrite` Phase-1 audit (which use the authoritative-source MCPs). The
scanner tells you WHICH posts to send there.

### Closing the loop — verification + structural fixers

Three executors complete the lifecycle (all write project-level plans/journals; none auto-mutate
a live site — Rule 5a):

```bash
# 1. VERIFICATION — record every optimization with a baseline; re-check the delta at T+14/T+30.
#    Without this, every title/citation/rewrite fix is fire-and-forget and unprovable.
python -m scripts.monitor.optimization_journal --verify --site {slug} --window 14    # did it work?
python -m scripts.monitor.optimization_journal --report --site {slug}
#    --record is now wired into the post-publish fixers (rewrite Phase 7, ai-overview-recovery
#    Phase 3.5); they journal the before/after when they apply a change. Enforced by
#    tests/test_optimization_journal_wiring.py (Rule 6: no markdown-only "should call").

# 2. INTERNAL-LINK GRAPH — the orphan fixer the per-post linker can't be (it only links forward).
python -m scripts.monitor.internal_link_graph --site {slug} --json   # → internal-link-plan.json
#    Apply the suggested INBOUND links via the internal-linker subskill (draft-first).

# 3. PRUNE / CONSOLIDATE PLANNER — the "act" half of content cleanup (content_audit only detects).
python -m scripts.monitor.prune_consolidate_planner --site {slug} --json   # → prune-consolidate-plan.json
#    DESTRUCTIVE output (301 merges / noindex) — human signs off; never auto-executed.
```

Lifecycle now closed: create → publish → monitor (dual-engine) → diagnose (signal + content axes)
→ fix (minimal skill, draft-first) → **record the change** → **T+14/30 verify it worked** → learn.

## Output

Per project, accumulated history:
```
projects/{slug}/
├── rank-history-{YYYY-MM-DD}.json
├── perf-week-{YYYY-MM-DD}.md
├── perf-month-{YYYY-MM-DD}.md
├── probes/{engine}-{YYYY-MM-DD}.json
├── drift-report-{YYYY-MM-DD}.json
├── baselines/{snapshot-sha}.sqlite
└── refresh-queue.json
```

## See also

- 5 sub-skills under `subskills/monitor/`
- `references/geo/geo-score-feedback-loop.md` (T+14/45/90 windows design)
- `scripts/monitor/perf_report_generator.py`
