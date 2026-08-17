---
name: cost-estimator
description: Pre-flight cost estimate for a planned /article run. Use BEFORE /article or when user asks "how much will this cost?" / "what's the estimate?". Outputs USD breakdown by category + 80% confidence band + budget check.
allowed-tools: [Bash, Read]
disable-model-invocation: false
user-invocable: true
---

# Cost Estimator (Pre-flight)

Before user commits 30 min + $2.40 to /article, show them the estimate.

## When to invoke

- `/cost-estimate` — defaults to listicle 6000w
- `/cost-estimate listicle 6000`
- `/cost-estimate --brief workspace/abc/brief.json`
- User asks: "how much for a pillar page?", "what does an article cost?", "is this gonna be over budget?"
- Auto-trigger via L1 SKILL.md before phase-research starts (mandatory pre-flight)

## How to invoke

```bash
# By format + word count
python -m scripts._core.cost_estimator --format listicle --words 6000

# From an existing brief.json
python -m scripts._core.cost_estimator --brief workspace/abc123/brief.json --json

# With cheaper config
python -m scripts._core.cost_estimator \
    --format how-to-guide --words 4500 \
    --images 2 --image-quality medium --batch

# Machine-readable
python -m scripts._core.cost_estimator --format pillar-page --json
```

## Output (human-readable)

```
━━━ /article cost estimate ━━━━━━━━━━━━━━━━━━━━━━━━━
  Format: listicle (target 6000 words)
  Images: 6 × high-quality 1024² (batch)   ← count = image_policy.DEFAULT_IMAGE_COUNT (format rows may set fewer)
  Drafter / pipeline model: claude-opus-4-7 / claude-opus-4-7
  Cache hit rate assumed: 30%

Breakdown:
  Research (Tavily ×8 adv search + 12 extracts): $0.1664
  Drafting (6000w via claude-opus-4-7, 21,000 in + 8,400 out + 9,000 cached): $0.3360
  Pipeline stages (13 stages, 124,000 in + 13,500 out via claude-opus-4-7): $0.6469
  Images (4 × gpt-image-2 high 1024² batch): $0.4220
  Overhead buffer (10%): $0.1571

  TOTAL:         $1.73
  80% range:    $1.30 – $2.25

  ✓ Within budget.
```

## Typical costs by format (rough)

| Format | Words | Est. cost (high+batch) |
|---|---|---|
| news-analysis | 1500 | ~$1.40 |
| definition | 3500 | ~$2.00 |
| how-to-guide | 4500 | ~$2.40 |
| product-review | 4500 | ~$2.40 |
| comparison | 4500 | ~$2.50 |
| case-study | 5500 | ~$3.10 |
| listicle | 6000 | ~$1.73 |
| pillar-page | 6500 | ~$3.40 |

## Levers to lower cost

1. **Use Batch API for images** — 50% off (default; toggle with `--no-batch`)
2. **Lower image quality** — `medium` cuts image cost 4×, `low` cuts 35×
3. **Fewer images** — `--images 2` instead of 4
4. **Cheaper drafter model** — `--drafter-model claude-sonnet-4-6` cuts ~60%
5. **Cheaper pipeline model** — `--pipeline-model claude-haiku-4-5` cuts ~80%
6. **Smaller word count** — costs scale ~linearly with words

## Budget check semantics

`approved`   — Within per-article + daily limits
`needs_approval` — Above 50% of per-article budget OR 80% daily
`blocked`    — Exceeds per-article OR would push daily over limit

If `blocked`, suggest lowering image quality OR shortening word count OR raising
budget in `~/.xuanran-seo/config.yaml`.

## What this skill does NOT do

- ❌ Actually run /article (that's L1 SKILL.md)
- ❌ Calibrate estimates from past runs (future closed-loop work — Step P2-真)
- ❌ Lock in pricing (estimates can be ±25%)

## Pre-flight integration

L1 SKILL.md should call this BEFORE phase-research kicks off:
```bash
python -m scripts._core.cost_estimator --brief workspace/$TASK/brief.json --json
```
If `total_usd > per_article_limit`: pause and ask user before continuing.
