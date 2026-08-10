# Sterling Sky 80/20 Rule — Anti-Doorway Uniqueness Heuristic

**Status (v3.4.0, 2026-05-22)**: Heuristic — NOT Google's officially-published threshold. Used in this plugin as ONE of FOUR input signals (see `scripts/lint/local_uniqueness_check.py`), not as the sole verdict.

---

## What it is

Sterling Sky (Joy Hawkins' local-SEO consultancy) reverse-engineered Google's doorway-page spam policy and published the "80/20 rule" as guidance: a local-SEO page may safely re-use up to ~80% boilerplate (subject knowledge, generic explanations, format scaffolding) AS LONG AS at least ~20% is genuinely unique-per-locality (location-specific facts, programs, case studies, neighborhoods, pricing).

The rule was synthesized from years of audit data — sites that follow it tend to keep rankings through Google spam updates; sites that violate it (e.g. swapping only the city name across 50 pages) get demoted.

**Sterling Sky's original source**: https://www.sterlingsky.ca/ — Joy Hawkins' blog and presentations at LocalU events. Joy also cross-publishes on Moz, Search Engine Land, and other industry outlets, which is why the rule appears across multiple sources but traces to a single author.

## What it ISN'T

Per our 2026-05-22 critical-validation research (`memory/research/v5_critical_validation_2026.json`):

- **It is NOT Google's published threshold.** Google's doorway page spam policy (last updated 2025-12-10) describes the pattern qualitatively ("multiple pages targeted at specific regions/cities that funnel users to one page") but publishes ZERO quantitative thresholds. The 80/20 number is heuristic; do not market it as "Google's rule."
- **It is NOT a single-Jaccard threshold.** Sentence-overlap measured by Jaccard ratio is one possible operationalization, but it's crude — two pages can share 80% sentences and still be legitimate (boilerplate disclaimers, dates, attribution) OR share 50% and still be doorway (templated structure with city-name swap).
- **It is NOT a hard veto on its own.** Use as ONE input among at least 4 factors.

## The 4 categories that count as "unique-per-locality"

Per Sterling Sky synthesis, ≥20% unique content must fall into one of these categories (NOT generic platitudes):

1. **Local programs / incentives** — Named utility rebates, state regulations, municipal codes, licensing requirements, government grants, tax breaks
2. **Local case studies / customer references / press citations** — Named clients, real published case studies, local press coverage from city-level outlets
3. **Local landmarks / neighborhoods / regional language** — Specific neighborhoods, highway corridors, regional terms, local employers/institutions
4. **Local pricing / logistics / market data** — City/state-specific dollar amounts, demographic data, lead times, market sizes

If your "unique" 20% is platitudes like "Texas has unique needs" or "the Boston market is competitive", that doesn't count. Genuine local content names specific things.

## How this plugin implements the rule

`scripts/lint/local_uniqueness_check.py` scores 4 INDEPENDENT factors:

| Factor | Weight | What it measures |
|---|---|---|
| F1 — Entity density | 35% | Count of distinct named-entity-style phrases |
| F2 — Factual claim density | 30% | Count of quantitative facts ($X, N%, kWh, populations, years, units) |
| F3 — Sibling Jaccard similarity | 25% | Sentence-overlap vs already-published sibling articles (1 - max_sim) |
| F4 — Lexical diversity (TTR) | 10% | Type-token ratio over content words |

Composite score = weighted sum (0-100).
- ≥70 → PASS (genuine local content)
- 50-69 → WARN
- <50 → FAIL

PLUS: **all 4 categories must be satisfied** (at least 1 program + 1 case study + 1 landmark + 1 pricing data). Missing any category → automatic FAIL regardless of composite score.

This composite approach is more robust than pure Jaccard because:
- It rewards content that includes specific entities + facts even if some sentences are reused
- It penalizes content that has high sentence-Jaccard with siblings (real doorway pattern)
- It catches "zero-substance" templates via the category check (lexical diversity + category enforcement)

## Why we don't enforce Jaccard alone

Sterling Sky's own writing emphasizes that 80/20 is a guideline, not a measurement. The risk of single-Jaccard:
- False positives on legitimate boilerplate (disclaimers, dates, attribution, navigation text)
- False negatives on shallow content with low overlap but no real local substance
- No defense against "fact-free" templates that have unique sentence structures but say nothing locality-specific

The 4-factor composite captures BOTH dimensions: structural uniqueness (F3) AND substantive uniqueness (F1+F2+category check).

## Source attribution

- Sterling Sky: https://www.sterlingsky.ca/ (Joy Hawkins)
- Moz contributor profile: https://moz.com/community/users/joyhawkins
- LocalU events: https://www.localu.org/
- Google's doorway page spam policy: https://developers.google.com/search/docs/essentials/spam-policies#doorway-pages

## When this rule probably under-protects

- When Google rolls out a spam update that targets a NEW pattern Sterling Sky hasn't yet catalogued. The 80/20 rule is reactive.
- When publishers find creative ways to game the 4 categories (e.g. fake case studies, hallucinated rebate programs). Catch via citation validation, not uniqueness lint.
- When the cluster has only 1 article and the lint has no siblings to compare against. F3 returns neutral 70/100 in this case; the other factors still score.

## When this rule probably over-protects

- For genuinely niche industries where there's a small finite set of relevant facts about each location. A plumber writing 50 city pages may not be able to find 20% unique-per-city content because plumbing is plumbing. Use `local-rebate-guide` format instead of `local-city-page` — rebate content has natural per-location variation. Or consolidate to fewer pages that aggregate multiple cities.

## Update history

- 2026-05-22: documented as plugin's canonical rule in v3.4.0 release. NOT marketed as "Google's threshold" per validation research verdict.
