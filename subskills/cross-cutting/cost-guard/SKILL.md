---
name: cost-guard
description: Budget enforcement. Estimate → check → log → summary. Daily total + per-init + per-article + per-image-batch caps from config.yaml. Triggered by every API call upstream.
allowed-tools: [Read, Bash]
---

# Cost Guard

Implementation: `scripts/_core/cost_ledger.py`.

This skill is mostly a wrapper to expose cost-guard ops via slash commands.

## CLI commands
```bash
# Estimate cost for an upcoming API call
python -m scripts._core.cost_ledger --estimate --model claude-opus-4-7 --in 5000 --out 2000

# Get current day's spend summary
python -m scripts._core.cost_ledger --summary --period day --json

# Reset today's ledger (admin only)
python -m scripts._core.cost_ledger --reset-today
```

## Caps (from ~/.xuanran-seo/config.yaml)
```yaml
cost_limits:
  daily_total_usd: 50
  per_init_usd: 1.5
  per_article_usd: 3.0
  per_image_batch_usd: 2.0
```

## Hook integration
- `hooks/pre_tool_use_cost_guard.py` enforces caps before Bash commands
- Every API-calling script logs to ledger after call

## See also
- `scripts/_core/cost_ledger.py`
- `hooks/pre_tool_use_cost_guard.py`
