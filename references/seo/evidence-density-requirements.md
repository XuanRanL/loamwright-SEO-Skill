# Evidence Density Requirements

## Hard rule: ≥1 table in first 50% of article

In addition to per-format table count minimums, **at least 1 table MUST appear in the front half** of the article (before the 50% word-count mark).

**Why**:
- AI engines extract verbatim from early sections preferentially
- Featured Snippet candidates live in early-article tables
- Readers who don't scroll past 50% still see the value
- Original v1.5 prompt requirement: "Put the table more toward the front"

`evidence_density_check.py` validates this — table_locations array includes line numbers; we check the first table's position.



The hard-rule baseline for "real data + papers + sufficient evidence to prove viewpoints + ≥2 tables".

Used by `scripts/lint/evidence_density_check.py` + `seo-auditor` + `geo-auditor` quality gates.

## The 4 evidence-density rules

### Rule 1: ≥2 markdown tables per article

**Minimum 2 tables** in every article (some formats require more — see per-format).

**Why**:
- ChatGPT citation lift: 3 tables = +25.7% AI citation rate (AirOps 2026.4 data)
- AIO Featured Snippet: tables often extracted verbatim
- Scan-ability: readers tolerate longer content with tables
- Comparison clarity: tables beat prose for 3+ items × 2+ attributes

**Hard rule per format**:

| Format | Min tables | Recommended | Rationale |
|---|---|---|---|
| listicle | 2 | 3-5 | Criteria + specs + comparison |
| pillar-page | 3 | 4-6 | Multiple sub-topics need comparison |
| **comparison** | **3** | **3** (AirOps rule) | Quick + pricing + feature-by-feature |
| case-study | 2 | 3 | Before/after + metrics + KPIs |
| how-to-guide | 2 | 2-3 | Prerequisites + troubleshooting |
| product-review | 2 | 3 | Specs + competitor + price |
| definition | 2 | 2 | Types/categories + comparisons |
| encyclopedic | 3 | 4-6 | Types + history + classification |
| data-research | 4 | 6-10 | Multiple findings need viz |
| buyers-guide | 3 | 4-5 | Criteria + comparison + use-cases |
| faq-knowledge | 2 | 2-3 | Quick-reference Q&A summary |
| roundup | 2 | 3 | Categories + price + comparison |
| shortlist-validation | 1 | 2 | (compact format; less is OK) |
| news-analysis | 1 | 1-2 | (short format; not data-heavy) |
| opinion | 1 | 2 | (argument > tables) |
| personal-story | 1 | 1-2 | (narrative > tables) |
| interview | 1 | 1-2 | (dialog > tables) |
| problem-solution | 2 | 2-3 | Cause/symptom + solution steps |
| glossary-hub | 2 | 3 | Alphabetical index + sub-topic groups |
| curated-roundup | 3 | 4 | Categories + ranking + comparison |
| level-guide | 2 | 3 | Per-level breakdown |
| multi-intent-hybrid | 3 | 4 | Definition + comparison + decision matrix |
| template-resource | 1 | 1-2 | (template IS the asset) |
| checklist | 1 | 2 | (checklist IS the table; bonus tips table) |

**Default for any format**: minimum 2 tables.

### Rule 2: ≥3 specific numeric stats with FLOW Evidence Triple

Every article needs ≥3 statistics with:
1. **Year anchor** — "In 2026," / "As of Q1 2026,"
2. **Inline citation** — "(Source, Year)" or markdown link
3. **URL in References** — link-resolvable (200 OK)

**Why**:
- "Articles without ≥3 specific stats get 0 AI citation rate" (Princeton GEO 2026 data)
- Stats = quotability anchors for ChatGPT/Perplexity
- Stats = trust signals for readers

**Hard rule per format**:

| Format | Min stats | YMYL min |
|---|---|---|
| Default | 3 | 5 |
| case-study | 5 (it's about data) | 7 |
| data-research | 10 | 15 |
| product-review | 5 (specific test data) | 5 |
| pillar-page | 5 | 7 |
| listicle | 4 (1 per top picks + overall) | 5 |
| news-analysis | 3 | 4 |
| opinion | 3 (back the claim) | 4 |
| personal-story | 2 (your data) | 3 |
| definition | 3 | 4 |
| encyclopedic | 5 | 7 |

### Rule 3: ≥1 peer-reviewed / Tier-1 source

Every article should cite ≥1 source from:
- **Crossref DOI** (peer-reviewed journal)
- `.gov` / `.edu` domain
- Wikipedia / Wikidata (as cross-reference, not primary)
- Authoritative industry research (Nielsen, Pew, McKinsey published reports)

**YMYL formats** (medical/financial/legal/safety): ≥3 Tier-1 sources

**Why**:
- E-E-A-T scoring: peer-reviewed = 10/10 expertise signal
- Google quality raters explicitly look for academic citations on YMYL topics
- Tier-1 sources have built-in trust signal for AI engines

**Hard rule per format**:

| Format | Min Tier-1 | YMYL min Tier-1 |
|---|---|---|
| Default | 1 | 3 |
| data-research | 2 (methodology refs) | 5 |
| case-study | 1 (methodology paper if applicable) | 3 |
| pillar-page | 2 | 5 |
| encyclopedic | 3 | 7 |
| definition | 1 (defining authoritative source) | 3 |
| opinion | 1 (supporting research) | 3 |
| news-analysis | 0-1 (news primary, research secondary) | 2 |
| personal-story | 0 (experience-driven) | 2 |

### Rule 4: ≥2 Information Gain Markers

Every article needs ≥2 of these markers:
- `original data (plain prose)` — your own data
- `real first-hand experience (plain prose)` — first-hand observation
- `original analysis (plain prose)` — non-obvious analysis

**Why**: AI engines pattern-match these markers as "unique source" signals. +30-40% AI citation rate.

**Hard rule per format**:

| Format | Min markers | Required mix |
|---|---|---|
| Default | 2 | any 2 |
| case-study | 3 | ≥1 ORIGINAL DATA + ≥1 PERSONAL EXPERIENCE |
| data-research | 4 | ≥3 ORIGINAL DATA |
| personal-story | 2 | ≥1 PERSONAL EXPERIENCE + ≥1 UNIQUE INSIGHT |
| opinion | 2 | ≥1 UNIQUE INSIGHT |
| pillar-page | 3 | mix of all 3 |
| encyclopedic | 3 | mix of all 3 |

## How these rules are enforced

### Lint script: `scripts/lint/evidence_density_check.py`

```bash
python -m scripts.lint.evidence_density_check --input draft.md --format listicle --json
```

Checks all 4 rules + outputs:
- table_count + meets_rule
- stat_with_citation_count + meets_rule
- tier1_source_count + meets_rule
- info_gain_marker_count + meets_rule
- overall_pass / fail
- recommendations per failure

### Integration with quality gates

Added to `cite_scorer.py` as 4 new items:
- **C12**: Tables ≥ format-required (10 pts)
- **C13**: Stats with FLOW Triple ≥ format-required (10 pts)
- **C14**: ≥1 Tier-1 source (8 pts)
- **C15**: ≥2 Information Gain Markers (5 pts)

Total CITE rubric grows from 40 → 33 points adjusted (rebalanced).

### Veto behavior

Rule 1 (tables) and Rule 2 (stats) failures → repair-orchestrator level 1 (surgical fix).
Rule 3 (Tier-1 source) failure on YMYL → T05 veto (60-cap).
Rule 4 (markers) failure → soft warning + recommendation to add markers.

## Why this matters

User original prompt explicitly requested:
- "真实数据" (real data) → enforced by T04 + this lint
- "论文" (papers) → enforced by Rule 3
- "充分信息证明观点" (sufficient evidence for viewpoints) → enforced by Rule 2 (≥3 stats)
- "至少 2 个 table" (≥2 tables) → enforced by Rule 1

Without these as automated checks, LLMs reliably skip them under pressure (especially when generating quickly).

## Recommendations for content creators

1. **Start with the data** — before writing prose, list:
   - What 3-5 stats you have
   - What 1-2 academic sources support your claim
   - What 2-3 tables you'll include

2. **Outline tables explicitly** in outline-architect output:
   - Table 1: {Comparison X vs Y vs Z}
   - Table 2: {Pricing tiers}

3. **Mark Information Gain inline** during drafting:
   - `original data (plain prose) In our 6-month test...`
   - `real first-hand experience (plain prose) When I switched from X to Y...`
   - `original analysis (plain prose) Most analysts miss that...`

4. **Cite Tier-1 sources explicitly**:
   - Prefer DOI links
   - Use APA 7 inline format
   - Date the retrieval

## See also

- `scripts/lint/evidence_density_check.py` — the validator
- `scripts/validate/cite_scorer.py` — integration point
- `references/seo/flow-evidence-triple.md` — the FLOW Triple definition
- `references/seo/information-gain-markers.md` — RETIRED marker system (historical record)
- `references/geo/core-eeat-80.md` — full E-E-A-T rubric
- `references/apa-citation-rules.md` — citation format
