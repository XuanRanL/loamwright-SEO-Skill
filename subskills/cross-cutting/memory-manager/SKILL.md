---
name: memory-manager
description: Manage HOT/WARM/COLD memory transitions, Wiki Phase 1/2/3 entity sedimentation, GDPR Art 17 purge. Triggered by hooks/stop_finalize.py + /forget-project command.
allowed-tools: [Read, Write, Bash]
---

# Memory Manager

Per seo-geo HOT/WARM/COLD pattern.

## Memory layers

```
projects/{slug}/                ← Per-client (HOT/WARM)
  ├── business-context.json     ← 90d TTL
  ├── research-cache/            ← 72h TTL
  └── ...

memory/                          ← Global (HOT/WARM/COLD)
  ├── entities/{id}.md           ← Permanent (Wiki Phase 1/2/3)
  ├── wiki/                      ← Phase 1/2/3 sediment
  ├── workspace/{task_id}/       ← HOT (current task)
  └── learned-patterns.json      ← Permanent (self-improvement)
```

## Wiki Phase sedimentation
- Phase 1: Mention (1-2 articles cite entity)
- Phase 2: Established (3-9 cites; add 47 signals)
- Phase 3: Authority (10+ cites; full schema + ai_resolution probe weekly)

## GDPR Art 17 (forget command)
```
/forget-project <slug>:
  1. Move projects/{slug}/ → projects/.deleted/{slug}-{timestamp}/
  2. Tombstone file with deleted_at timestamp
  3. Schedule physical deletion in 30 days (per stop_finalize.py hook)
  4. Memory/entities/: do NOT delete unless explicit (cross-project shared)
```

## Workflows

### HOT → WARM (task completion)
After Stage: final, workspace/{task} → memory/workspace/.archived/{YYYY-MM}/{task}/

### WARM → COLD (90d expiry)
After 90d: projects/{slug}/business-context.json.freshness_state = "expired"
→ Suggest /init --refresh

### Cleanup (stop_finalize hook)
- Archive completed tasks
- Purge .deleted projects >30d old
- Compact wiki entries that haven't been cited in 12 months
