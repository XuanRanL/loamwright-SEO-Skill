---
name: manifest-consistency-checker
description: Verify VERSION + plugin.json + marketplace.json + install.sh + install.ps1 + CHANGELOG + __init__.py all agree on version. Auto-fix via --apply. Run via /guard --versions.
allowed-tools: [Read, Bash]
---

# Manifest Consistency Checker

Implementation: `scripts/_core/manifest_consistency_check.py`.

## CLI
```bash
# Check (CI use)
python -m scripts._core.manifest_consistency_check --check

# Auto-fix
python -m scripts._core.manifest_consistency_check --apply

# Bump version (semver)
python -m scripts._core.manifest_consistency_check --bump patch  # 3.2.0 → 3.2.1
python -m scripts._core.manifest_consistency_check --bump minor  # 3.2.0 → 3.3.0
python -m scripts._core.manifest_consistency_check --bump major  # 3.2.0 → 4.0.0
```

## Files synced
1. VERSION (source of truth)
2. .claude-plugin/plugin.json
3. .claude-plugin/marketplace.json
4. install/claude-code/install.sh
5. install/claude-code/install.ps1
6. install/wordpress-mu-plugin/seo-machine-yoast-rest.php
7. CHANGELOG.md
8. scripts/__init__.py

## CI integration
GitHub Actions runs `--check` on every commit; non-zero exit = drift = build fails.

## See also
- `scripts/_core/manifest_consistency_check.py`
