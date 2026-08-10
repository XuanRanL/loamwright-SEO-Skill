---
name: self-upgrade
description: 9-step in-place upgrade from marketplace remote. Triggered by bin/update-check returning UPGRADE_AVAILABLE OR /upgrade command. Backs up old version + git fetch + version sync + cache purge + changelog summary.
allowed-tools: [Read, Bash, Edit]
---

# Self Upgrade

Per toprank pattern: 9-step upgrade with dev-symlink detection.

## Workflow
```
1. Log start to ~/.xuanran-seo/upgrade-log.json
2. Detect install dir + check for dev-symlink (skip upgrade if dev mode)
3. Save current version + state to /tmp/xs-upgrade-backup/
4. git fetch origin main + git reset --hard origin/main in marketplace clone
5. rsync to versioned cache dir
6. Update ~/.claude/plugins/installed_plugins.json:
   - new installPath
   - new version
   - new gitCommitSha
7. Purge old cache (keep only latest 3 versions + dev)
8. Parse CHANGELOG.md between old and new versions → 3-7 bullets
9. Write ~/.xuanran-seo/just-upgraded-from = old_version
   Clear ~/.xuanran-seo/last-update-check
   Resume original skill that triggered upgrade
```

## Entry points
- Inline: `bin/update-check` returns `UPGRADE_AVAILABLE x.y.z` → auto-trigger
- Standalone: `/upgrade` command

## See also
- `bin/update-check`
- `bin/preamble.md` (consumed UPGRADE_AVAILABLE signal)
