---
name: project-show
description: Display current active project's PROJECT.md + brief stats. Use /show-project.
allowed-tools: [Read]
---

# Project Show

## Output
Cat the active project's PROJECT.md.

Resolve the slug **env-first** (so it reports the project THIS session is pinned
to, not whatever a parallel session last wrote to the shared file):

```bash
slug=$(python -c "from scripts._core import active_project as a; print(a.get_active_project() or '')")
```
```python
# equivalent: XS_ACTIVE_PROJECT env var → ~/.xuanran-seo/active-project file
content = read(f"projects/{slug}/PROJECT.md")
print(content)
```
