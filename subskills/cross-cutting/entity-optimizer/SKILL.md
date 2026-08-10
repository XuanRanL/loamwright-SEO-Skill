---
name: entity-optimizer
description: PARKED (2026-07-17 wiring audit) — designed but never wired; nothing routes here and its companion agents/entity-extractor.md is equally unreachable. Track 47 entity signals per entity (per seo-geo). Maintains ai_resolution_status per engine (recognized/partial/unrecognized/confused). The ONLY skill that writes to memory/entities/.
allowed-tools: [Read, Write, Bash]
disable-model-invocation: true
user-invocable: false
---

# Entity Optimizer

> ⚠️ **PARKED — NOT WIRED (2026-07-17 wiring audit).** No skill, orchestrator stage, or
> hook routes to this subskill; `memory/entities/` has no writer today. This document is
> design, not behavior (Rule 6). Wiring the Wiki-Phase entity feature (or deleting this
> pair) is a product decision — see CHANGELOG [3.40.0].

Sole writer of `memory/entities/{id}.md`.

## 47 entity signals (per seo-geo)

Each entity entry tracks:
- name + aliases
- type (Organization / Person / Place / Product / Concept)
- @id (canonical URL or Wikidata QID)
- description (definitive)
- founding date (if Org)
- industry
- key relationships (sameAs, subsidiaries, etc.)
- ai_resolution_status per engine (chatgpt/pplx/claude/gemini)
- last_probed_at
- citation_count_30d
- (... 47 total)

## Workflow

```
1. After research / draft / publish, scan for entities mentioned
2. For each new entity:
   - Create memory/entities/{slug}.md
   - Populate from Wikidata if available
   - Probe AI engines for recognition
3. For each existing entity:
   - Update citation_count
   - Re-probe if ai_resolution_status known stale (>30d)
4. Cross-project linking: entities are global (used across all projects)
```

## ai_resolution_status states
- recognized: brand named accurately + sources cite our URL
- partial: brand named but facts wrong OR our URL not cited
- unrecognized: brand not mentioned
- confused: brand mentioned but mixed with another (HIGH RISK)

## See also
- `references/geo/47-entity-signals.md` (TODO)
- `scripts/fetch/ai_search_probe.py`
