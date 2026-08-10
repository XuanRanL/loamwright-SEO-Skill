---
name: project-list
description: List all projects/{slug}/ with status (fresh/stale/expired). Use /list-projects.
allowed-tools: [Read, Bash, Glob]
---

# Project List

## Output
```
Active: example-com

Available projects:
  ✓ example-com           initialized 2026-05-19  status: fresh
                          industry: ecommerce-fishing-gear · pages: 39
  
    saas-startup-com      initialized 2026-04-01  status: fresh
                          industry: saas · pages: 28
  
  ⚠ old-client-com         initialized 2025-12-15  status: EXPIRED
                          industry: legacy-retail · pages: 42
                          → Run: /init <url> --refresh
```

## Workflow
```python
for slug_dir in projects/*/:
    if .tombstone exists: skip
    bc = load projects/{slug}/business-context.json
    print slug + status + key metadata
```
