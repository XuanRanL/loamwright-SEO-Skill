---
name: project-switch
description: Switch active project. Updates ~/.xuanran-seo/active-project pointer. All subsequent commands inherit new project's business-context. Triggered by /switch <slug>.
allowed-tools: [Read, Write]
---

# Project Switch

Single-line operation: change which project is active.

## Workflow
```python
1. Verify projects/<slug>/business-context.json exists
2. If freshness_state == "expired": warn user (suggest --refresh)
3. Write slug via scripts._core.active_project.set_active_project(slug)
   (writes ~/.xuanran-seo/active-project; emits a stderr warning if
    XS_ACTIVE_PROJECT is set — see "Env-pinned sessions" below)
4. Show summary of newly active project:
   - Domain
   - Industry
   - Last refresh date
   - Project age
```

```bash
python -c "from scripts._core import active_project as a; a.set_active_project('<slug>')"
```

## Env-pinned sessions (parallel multi-session)
If this session was launched with `XS_ACTIVE_PROJECT` set (via
`bin/launch-session.*`), `/switch` does **NOT** change the project for the current
session — the env var is authoritative. The file write only affects future,
non-env-pinned sessions. `set_active_project` prints a warning in this case so the
behavior is never silent. To change a pinned session's project, relaunch it with a
different `XS_ACTIVE_PROJECT`.

## CLI
```bash
/switch example-com
```

## Side effects
- All subsequent commands inherit new business-context
- workspace/{task_id}/ tasks under OLD project don't move; only active pointer changes

## See also
- `subskills/init/project-list/SKILL.md`
- `subskills/init/website-project-init/SKILL.md`
