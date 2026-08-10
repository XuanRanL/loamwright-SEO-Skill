---
name: cost-summary
description: Aggregate past spending (day/week/month) — total USD, per-model, per-endpoint. Use when user runs /cost or asks "how much have I spent?" / "what's my burn?" / "show me the bill".
allowed-tools: [Bash, Read]
disable-model-invocation: false
user-invocable: true
---

# Cost Summary

What the user has actually spent. Pairs with `cost-estimator` (forward-looking).

## When to invoke

- `/cost` — today's spending (default)
- `/cost week` — last 7 days
- `/cost month` — last 30 days
- User asks: "how much have I spent?", "what's the bill?", "show me the burn"

## How to invoke

```bash
python -m scripts._core.cost_ledger --summary --period day
python -m scripts._core.cost_ledger --summary --period week
python -m scripts._core.cost_ledger --summary --period month --json
```

## Output (human-readable)

```
Period:  day
Total:   $4.7321
Entries: 38
By model:
  $2.1430  claude-opus-4-7
  $1.8470  gpt-image-2
  $0.5230  claude-sonnet-4-6
  $0.1820  tavily
  $0.0371  gemini-3.1-pro
```

## What this skill does

- Reads `~/.xuanran-seo/cost-ledger.jsonl`
- Filters by time window (day/week/month back from now)
- Aggregates total + by model + by endpoint
- Reports daily burn rate vs configured limit
- Surfaces unusual spending (e.g., >$5 in one task)

## What this skill does NOT do

- ❌ Bill anyone (cost_ledger is local-only)
- ❌ Predict next month (use cost-estimator for forward)
- ❌ Charge a card (no payment integration)

## Daily limit warning

If `total > 0.8 × daily_limit`, surface a warning:
```
⚠ Daily spend at 84% of $50 limit. 7h remaining in day.
```

If `total > daily_limit`:
```
⛔ Daily limit exceeded. cost-ledger.check() will block further LLM calls
   until tomorrow OR until you raise daily_total_usd in ~/.xuanran-seo/config.yaml
```

## Interpreting the breakdown

| Model dominates → | Means |
|---|---|
| claude-opus-4-7 | Drafter + reviewer (expected for production) |
| gpt-image-2 | High image volume — consider --image-quality medium |
| tavily >$1 | Many research-heavy /article runs (normal) |
| gemini >$1 | LLM-judge for quality gates running often (consider sampling) |

## Where ledger lives

`~/.xuanran-seo/cost-ledger.jsonl` — append-only JSONL.

Reset today's entries (admin):
```bash
python -m scripts._core.cost_ledger --reset-today
```
