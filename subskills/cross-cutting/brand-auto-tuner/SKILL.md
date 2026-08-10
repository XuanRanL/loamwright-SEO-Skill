---
name: brand-auto-tuner
description: Analyze winner vs loser articles to find features that distinguish them, then suggest brand-guideline.yaml updates. Use after ≥10 articles have outcome tags. Closes the data-loop: production → measurement → learning → next-cycle adjustment.
allowed-tools: [Bash, Read]
disable-model-invocation: false
user-invocable: true
---

# Brand Auto-Tuner

The third leg of the closed-loop. After outcome_tagger labels articles as
winner / mid / loser based on real GSC + AI citation data, this finds the
patterns that distinguish winners and suggests brand-guideline tweaks.

## When to invoke

- After 10+ articles have outcome tags (run `outcome_tagger.py` first)
- Monthly or quarterly, as the dataset grows
- After a major content campaign to see what worked
- Before starting a new content campaign (lock in learnings)
- `/tuner` or `/auto-tune` (user invokes)

## How to invoke

```bash
# Single site
python -m scripts._core.brand_auto_tuner --site my-site

# All sites in portfolio
python -m scripts._core.brand_auto_tuner --all-sites

# Higher threshold for noisier datasets
python -m scripts._core.brand_auto_tuner --site my-site --min-per-group 10
```

## Output

Two files per site:
- `projects/{slug}/brand-tuner-report-{date}.json` — full findings
- `projects/{slug}/brand-guideline.diff.{date}.yaml` — suggested overlay

The diff is NOT auto-applied. User reviews, then manually merges desired
findings into `brand-guideline.yaml`.

## Sample output

```
━━ Brand tuner: my-fishing-site ━━━━━━━━━━━━━━━━━━━━━━━
  Articles:    47 (winners 12, mid 22, losers 13)
  Confidence:  medium
  Findings:    6
  Output:      projects/my-site/brand-tuner-report-2026-05-19.json
  Diff:        projects/my-site/brand-guideline.diff.2026-05-19.yaml

  Significant patterns:
    🔴 [large ] first_person_pct
        winners have higher first_person_pct (mean 14.3 vs losers 6.2). 
        Consider targeting around 14.3 (band ±15%).
    🔴 [large ] info_gain_marker_count
        winners have higher info_gain_marker_count (mean 3.1 vs losers 1.2). 
        Consider targeting around 3.1 (band ±15%).
    🟡 [medium] tier1_citation_count
        winners have higher tier1_citation_count (mean 4.2 vs losers 2.1). 
        Consider targeting around 4.2 (band ±15%).
    🟡 [medium] format=listicle
        format='listicle' wins more often (rate 67% vs portfolio avg 26%). 
        Bias towards this format.
    🟡 [medium] ai_slop_score
        winners have lower ai_slop_score (mean 18.2 vs losers 31.5). 
        Consider targeting around 18.2 (band ±15%).
    🟡 [medium] format=how-to-guide
        format='how-to-guide' wins less often (rate 12% vs portfolio avg 26%). 
        Avoid this format.
```

## Method

### Numeric features (Cohen's d effect size)

For each feature in `[word_count, h2_count, citation_count, tier1_citation_count,
image_count, info_gain_marker_count, first_person_pct, ai_slop_score,
core_eeat_score, cite_score, reviewer_score, ...]`:

1. Pool winners' values + losers' values
2. Cohen's d = (mean_winner - mean_loser) / pooled_SD
3. |d| ≥ 0.8 → **large** (worth acting on)
4. 0.5 ≤ |d| < 0.8 → **medium** (directional hint)
5. < 0.5 → ignored (too noisy)

### Categorical features (win-rate delta)

For each category of `format`, `voice`, `purpose`:

1. Compute win rate per category vs portfolio-wide average
2. Delta ≥ 0.10 → flag direction
3. Delta ≥ 0.20 → strong signal

### Confidence tiers

| Winners n | Confidence | What to do |
|---|---|---|
| <5 | very low | Wait — publish more |
| 5-9 | low | Directional only; don't tune |
| 10-19 | medium | Apply medium+ findings cautiously |
| 20+ | high | Apply large findings; review medium |

## How to apply findings

1. Open `projects/{slug}/brand-guideline.diff.{date}.yaml`
2. Review each suggestion against your own judgment
3. Manually copy approved items into `projects/{slug}/brand-guideline.yaml`
4. Move applied finding from `pending` → `applied` in the report file
5. Run brand-tuner again after next batch to verify the change helped

**This is intentionally NOT auto-apply.** Brand voice is too important to
algorithm out. The tuner finds signals; the human decides.

## Limitations

- Statistical method is intentionally simple (Cohen's d, no regression). With
  small N, false positives are common. Manual review essential.
- Confounding: longer articles may correlate with everything; doesn't prove
  causation. The tuner reports correlations; reader interprets.
- Doesn't account for time-decay: an article that became a winner after 6
  months has the same weight as one that won in 2 weeks.

## What this skill does NOT do

- ❌ Auto-edit brand-guideline.yaml
- ❌ Run regressions / ML models (intentionally simple)
- ❌ Determine causation (correlation only)
- ❌ Combine learnings across clients (per-site only — different niches)

## Composition

```
Closed-loop, quarterly:

1. gsc_api_ingest --all-sites --mode last-28
2. ai_citation_tracker --all-sites --top-priority 50
3. outcome_tagger --site X      → labels winners/mid/losers
4. brand_auto_tuner --site X    → suggests guideline updates
5. Human review                  → apply approved findings
6. Next batch: /batch-article picks up tuned guideline
```
