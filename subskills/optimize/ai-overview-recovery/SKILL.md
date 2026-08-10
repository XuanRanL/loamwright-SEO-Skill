---
name: ai-overview-recovery
description: 4-phase recovery when Google AI Overview drops an article. Measure damage → diagnose skip reason → rewrite → T+7/14/28 monitor. Triggered by drift-detector AIO loss alert OR /aio-recovery command.
allowed-tools: [Read, Write, Edit, Bash, Task]
---

# AI Overview Recovery Playbook

When Google AIO stops citing your article, run this recovery (per seo-geo pattern).

## Phase 0: CONFIRM the loss is real (v3.35 — churn guard)

**AIO citations churn ~45% per render** (Ahrefs 2025: consecutive AIO renders of the
same query share only ~54.5% of cited URLs). A single uncited probe is noise, not a
loss — recovering from churn wastes a full rewrite cycle and poisons the journal.

- The automated trigger is already guarded: `refresh_decision_router` emits
  `NOT_IN_AI` only after **2 consecutive uncited probes ≥ 48h apart** (observations
  persisted in `projects/{slug}/audits/aio-observations.json`; an in-between cited
  probe resets the clock). A router-emitted NOT_IN_AI action is therefore
  pre-confirmed — proceed to Phase 1.
- For a MANUAL `/aio-recovery` invocation: check `aio-observations.json` first. If
  the loss has only one observation, re-probe after 48h instead of starting recovery:
  `python -m scripts.monitor.refresh_decision_router --site {slug} --json`
- Evidence: `references/seo/serp-feature-value-2026.md` §4.

## Phase 1: Measure Damage (Day 0)
- Check GSC: AIO impressions drop
- Run ai_search_probe to confirm
- Document: which queries lost AIO citation? Traffic impact?

## Phase 2: Diagnose Skip Reason (Day 0-2)
4 query strategy classifiers:
- (A) Freshness — content >12 months old, new competitors fresher
- (B) Authority — competitors gained backlinks; we lost
- (C) Structure — H2/H3 structure no longer matches query intent
- (D) Entity — entity ambiguity (e.g., merger renamed brand)

Run:
```bash
python -m scripts.fetch.ai_search_probe \
    --brand "{brand}" --domain "{site}" \
    --queries "{affected_queries_comma_separated}"
```

## Phase 3: Targeted Rewrite (Day 3-5)
Per diagnosis:
- (A) Add dateModified + fresh stats + 2026 data
- (B) Build authority — add citations to Tier-1, get backlinks
- (C) Restructure H2s to match query intent
- (D) Add Organization schema with sameAs + add clarification copy

## Phase 3.5: Record the change (closes the monitor verify loop)

After the targeted rewrite is republished, RECORD it so the verification loop can measure whether
AIO citation recovers (Rule 6: the real executor for the "fixer skills should call --record" wiring,
not a prose note). The diagnosis class (A/B/C/D) is the change `--type`:

```bash
python -m scripts.monitor.optimization_journal --record \
    --site {site} --post-id {post_id} --url {live_url} \
    --type aio-recovery --query "{primary_affected_query}" \
    --before "{old_structure_or_stat}" --after "{new_structure_or_stat}"
```

## Phase 4: Monitor (Day 7 / 14 / 28)
- Re-probe AI engines weekly
- Check GSC AIO impressions weekly (`optimization_journal --verify --site {site} --window 14` reads the recorded baseline)
- If recovered: document what worked
- If still lost at Day 28: escalate to repair-orchestrator with from-scratch level

## See also
- `references/geo/ai-overview-recovery-playbook.md`
