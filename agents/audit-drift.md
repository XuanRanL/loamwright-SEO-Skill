---
name: audit-drift
description: Detects SEO regressions by comparing current crawl against a stored baseline using 17 comparison rules at 3 severity tiers — surfaces schema removals, canonical changes, noindex additions, CWV degradation
tools: [Read, Bash, Write, Glob, Grep]
maxTurns: 60
---

# Audit Drift Agent

## Spawn Condition
Previous baseline exists: `{audit_dir}/baseline/` directory present, OR `config.json :: baseline_path` valid. If no baseline, write minimal output noting absence and exit.

## Inputs
- `{audit_dir}/crawl-results.json` — current state
- `{audit_dir}/baseline/crawl-results.json` — prior state
- `{audit_dir}/baseline/modules/*.json` — prior module scores

## Scripts
There is NO executor for the audit-dir comparison this agent performs — no
`scripts.audit.drift_compare` module exists. Read `crawl-results.json` and
`baseline/crawl-results.json` yourself and apply the 17 rules below manually.

Related but DIFFERENT workflow: `python -m scripts.monitor.drift_compare --site {project_slug} --url {live_url} --json`
compares ONE published URL against its SQLite baseline in
`projects/{slug}/baselines/drift.sqlite` (the /drift monitor path). It does not
read audit-dir crawl results and takes no `--current`/`--baseline` flags.

## 17 Comparison Rules

**CRITICAL** (immediate ranking impact):
1. Schema removed — had structured data, now absent
2. Canonical changed — href differs
3. Canonical removed — was present, now missing
4. Noindex added — was indexable, now noindex
5. H1 removed — was present, now missing
6. H1 changed >50% — token overlap < 50%
7. Title removed — `<title>` absent
8. Status 4xx/5xx — was 200, now error

**WARNING** (likely impact):
9. Title changed — content differs
10. Meta description changed
11. CWV regressed >20% — any metric degraded >20%
12. Module score dropped 10+ pts
13. OG tags removed — og:title/description/image gone
14. Schema modified — type or content materially changed

**INFO** (notable, no immediate penalty):
15. New schema added
16. H2 structure changed — headings added/removed/reordered
17. Content hash changed — body content edited

Pages in baseline but absent from current = CRITICAL (rule 8). Pages in current but absent from baseline = INFO (new page).

## Scoring
```
base = 100; per_critical = -15 (cap -60); per_warning = -5 (cap -30); per_info = -1 (cap -10)
drift_score = max(0, 100 + critical_penalty + warning_penalty + info_penalty)
```
90-100 stable | 70-89 minor drift | 50-69 significant | 30-49 major regressions | 0-29 critical drift.

## Output → `{audit_dir}/modules/drift.json`
```json
{
  "module": "drift", "score": 0-100,
  "baseline_date": "YYYY-MM-DD", "current_date": "YYYY-MM-DD", "days_since_baseline": N,
  "summary": {"pages_compared": N, "pages_added": N, "pages_removed": N, "critical_count": N, "warning_count": N, "info_count": N},
  "regressions": [{"rule_id": 1, "rule_name": "...", "severity": "critical|warning|info", "url": "...", "old_value": "...", "new_value": "...", "impact": "..."}],
  "score_deltas": {"technical": {"baseline": N, "current": N, "delta": N}, "content": {"baseline": N, "current": N, "delta": N}},
  "findings": [{"severity": "critical|high|medium|low", "category": "...", "message": "...", "evidence": "old: X -> new: Y", "recommendation": "..."}],
  "metadata": {"baseline_path": "...", "pages_in_baseline": N, "pages_in_current": N}
}
```
Map rule severities to findings: critical->critical, warning->high, info->low.
