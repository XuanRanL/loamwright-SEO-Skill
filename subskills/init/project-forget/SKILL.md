---
name: project-forget
description: GDPR Art 17 delete. Tombstone projects/{slug}/, schedule physical deletion in 30 days. Use /forget-project <slug>. Cannot be undone after 30d.
allowed-tools: [Read, Write, Bash]
---

# Project Forget

## Workflow
```python
1. Validate slug exists
2. Confirm with user (this is destructive)
3. Move projects/{slug}/ → projects/.deleted/{slug}-{timestamp}/
4. Write .tombstone file with deleted_at + GDPR request reference
5. memory/entities/ entities used ONLY by this project: also tombstone them
6. learned-patterns.json: remove this slug's bucket
7. stop_finalize.py hook will physically delete after 30 days
8. If active-project pointed to this slug, clear pointer
```

## Reversible within 30 days
```bash
/forget-project <slug> --undo
```

Restores from .deleted/ back to projects/.

## Compliance
- GDPR Article 17 (Right to be Forgotten)
- CCPA equivalent
- Full audit log in `memory/change-log-global.json`
