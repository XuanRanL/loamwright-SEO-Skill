# GEO Score Feedback Loop

The closed-loop that turns AI citation outcomes into brand-guideline + content strategy adjustments.

Without this loop, GEO is one-way: produce → publish → hope. With the loop: produce → publish → measure → adjust → next batch is smarter.

## The loop (6 steps)

```
Step 1: Publish article (with current brand-guideline + format choices)
        ↓
Step 2: T+7/14/30 monitor (gsc + ai_citation_tracker + drift)
        ↓
Step 3: outcome_tagger → winner/mid/loser
        ↓
Step 4: brand_auto_tuner → find winner features
        ↓
Step 5: Human reviews diff.yaml → applies to brand-guideline.yaml
        ↓
Step 6: Next batch uses tuned brand-guideline → cycle repeats
```

## Step-by-step

### Step 1: Publish (T+0)

Article ships to WordPress. Publisher writes:
- `articles/{slug}/publish-log.json` — post URL, publish timestamp, query targets
- `articles/{slug}/features.json` — extracted content features (word_count, h2_count, citation_count, info_gain_markers, ai_slop_score, etc.)

### Step 2: T+7 / T+14 / T+30 monitoring

```bash
# Weekly cron job (or manual)
python -m scripts.monitor.gsc_api_ingest --all-sites --mode weekly
python -m scripts.monitor.bing_webmaster_ingest --all-sites --mode weekly
python -m scripts.monitor.rank_tracker --all-sites
python -m scripts.monitor.ai_citation_tracker --all-sites --top-priority 30
```

Each writes per-article data to `projects/{slug}/audits/`.

### Step 3: outcome_tagger labels articles

```bash
python -m scripts.monitor.outcome_tagger --site my-site
```

Per article assigned a tag:
- **winner** — avg_position ≤10 AND (clicks ≥30 OR AI-cited in ≥2 engines)
- **mid** — avg_position ≤30 AND (clicks ≥5 OR AI-cited in ≥1 engine)
- **loser** — neither (after ≥30 days post-publish)
- **too_new** — <30 days; not yet judgeable

Writes `projects/{slug}/audits/outcomes.json`.

### Step 4: brand_auto_tuner finds winner features

```bash
python -m scripts._core.brand_auto_tuner --site my-site
```

Method:
- Partition outcomes into winners + losers
- For each content feature (word_count, info_gain_marker_count, etc.):
  - Compute Cohen's d effect size between groups
  - Flag features with |d| ≥ 0.5 (medium effect) or ≥ 0.8 (large effect)
- For categorical features (format, voice):
  - Win-rate per category vs portfolio average
  - Flag categories with ≥10pt delta

Outputs:
- `projects/{slug}/audits/brand-tuner-report-{date}.json` — findings
- `projects/{slug}/audits/brand-guideline.diff.{date}.yaml` — suggested overlay

### Step 5: Human review + apply

The diff.yaml is **never auto-applied**. Brand voice is too important to algorithm out without human judgment.

Example diff.yaml (after 47 articles tagged):

```yaml
# Brand-guideline tuner suggestions
# Confidence: medium (winners n=12, losers n=13)

content_targets:
  first_person_pct:
    target: 14.3          # winners' mean
    band_pct: 15
    rationale: "effect 0.84 (large); loser mean was 6.2"
  info_gain_marker_count:
    target: 3.1
    band_pct: 15
    rationale: "effect 1.12 (large); loser mean was 1.2"

category_bias:
  format:
    prefer: ['listicle']
    rationale: "win rate 67% vs portfolio avg 26%"
    avoid: ['how-to-guide']
```

User reviews each suggestion:
- Apply directly to `projects/{slug}/brand/brand-guideline.yaml`
- Mark as "applied" in report
- Or reject (with reason recorded)

### Step 6: Next batch inherits improvements

Subsequent `/article` / `/batch-article` invocations read updated brand-guideline.yaml. Next 47 articles theoretically have higher winner rate.

Repeat cycle. Each cycle compresses uncertainty about what works for THIS brand in THIS niche.

## Cadence

- Monitoring scripts: weekly (cron-friendly)
- outcome_tagger: monthly (needs 30+ days for fair labeling)
- brand_auto_tuner: quarterly (needs ≥10 winners + ≥5 losers for statistical confidence)
- Human review + apply: quarterly

## Confidence tiers

| Winners n | Confidence | Action |
|---|---|---|
| <5 | very low | Wait — publish more |
| 5-9 | low | Directional only; don't tune |
| 10-19 | medium | Apply medium+ findings cautiously |
| 20+ | high | Apply large findings; review medium |

## Statistical method

Cohen's d effect size (NOT p-values, which need large N):

```
d = (mean_winner - mean_loser) / pooled_SD

|d| ≥ 0.8 → large effect (act on it)
|d| ≥ 0.5 → medium (directional)
|d| < 0.5 → ignore (too noisy)
```

For categorical features:
- Win rate per category vs portfolio avg
- Delta ≥ 0.10 → flag direction
- Delta ≥ 0.20 → strong signal

## Anti-patterns

### ❌ Tuning too aggressively too soon

With 8 articles in outcomes, "first_person_pct" effect size is meaningless. Wait for N≥20.

### ❌ Tuning across clients

Each project (per site) has its own outcome dataset. Don't pool across clients — different niches respond differently.

### ❌ Trusting a single high-effect signal

If "use word_count = 3,742" comes back as a "winner feature", that's correlation noise, not causation. Demand multiple supporting signals.

### ❌ Forgetting time decay

An article that became a winner after 6 months has the same weight as one that won in 2 weeks. Future enhancement: weight by time-to-win.

## What gets tuned

**Numeric content targets** (suggested band):
- `word_count` (target ±15%)
- `h2_count` (target ±2)
- `citation_count` (target +/-3)
- `first_person_pct` (target ±15%)
- `info_gain_marker_count` (target ±1)
- `ai_slop_score` (lower-is-better target)

**Categorical biases**:
- `format` (prefer / avoid)
- `voice` (prefer / avoid)
- `purpose` (prefer / avoid)

## What does NOT get tuned

- ❌ Banned words list (too brand-critical for algorithmic tuning)
- ❌ AI visibility profile (ski ramp, H2-as-prompt, etc. are human strategic choices)
- ❌ Author voice (deeply human-crafted; tuner can suggest direction but not overwrite)

## Closing the loop

The loop is "closed" when:
1. New articles inherit tuned guidelines
2. Their outcomes get tagged
3. Next tuner run incorporates them

After 3-4 cycles (≈1 year), the brand-guideline.yaml has been refined ≥3 times based on real data. The plugin "knows" this brand.

## See also

- `scripts/_core/brand_auto_tuner.py` — implementation
- `scripts/monitor/outcome_tagger.py` — labeling
- `subskills/cross-cutting/brand-auto-tuner/SKILL.md` — orchestration
- `references/geo/ai-engine-matrix.md` — per-engine weight signals
