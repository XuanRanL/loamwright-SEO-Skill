# Data Research Template

> Format ID: `data-research`. Original data + analysis. Strongest E-E-A-T + AI citation format.
> Used when you have proprietary data (survey, internal analytics, experiments).

## Why this format ranks high

- AI engines (especially Perplexity + ChatGPT) prioritize original data
- E-E-A-T "Experience" pillar maxed (you generated the data)
- Backlink magnet (others cite original research)
- Long-tail traffic (data + statistics queries)

## Default structure

```
{Topic} Statistics ({Year}): What {N} {Subjects} Tell Us

## TL;DR (40-60w)
3 most surprising findings.

## Key findings (5-7 specific bullet stats with charts)

## Methodology (~400-500w — CRITICAL for E-E-A-T)
- Sample size (N=...)
- Recruitment method
- Survey/experiment timeline
- Variables measured
- Analytic methods
- Caveats / limitations

## Finding 1: {headline insight} (~600-800w)
- The stat with chart
- Why it matters
- Cross-tabs by segment
- Implications

## Finding 2 ... Finding N (same structure, ~600w each)

## Industry comparison (~400w)
How our data compares to public benchmarks.

## What this means for {persona} (~300w)
Actionable interpretation.

## Methodology + caveats (~250w)
What this study DOESN'T tell us. Honesty builds trust.

## How to get the raw data (~150w)
"Email us at..." or "Download full report PDF at..."

## FAQ (5-7)

## References (≤15 — methodology citations may push higher)
```

## Word budget (5000w target)

| Section | Words | % |
|---|---|---|
| TL;DR + Key findings | 400 | 8 |
| Methodology | 500 | 10 |
| 4 findings × 700w | 2800 | 56 |
| Industry comparison | 400 | 8 |
| What this means | 300 | 6 |
| Caveats | 250 | 5 |
| Data access + FAQ | 350 | 7 |

## Required modifiers
- `tldr-first`, `citation-capsules-per-h2`, `mandatory-toc`
- `strong-eeat-signals` ✓ (this format IS the E-E-A-T showcase)
- `info-gain-prose` ✓ REQUIRES ≥3 pieces of original data
- `chart-required` ✓ ≥4 charts/visualizations

## Hard rules
1. ≥3 pieces of original data
2. ≥4 charts (different types — bar, line, scatter, pie)
3. Methodology section MANDATORY (not optional)
4. N (sample size) prominent
5. Caveats section mandatory (what data doesn't show)
6. Raw data accessible (CSV link / contact)
7. Authors have credentials

## Schema additions
- `Article` base
- `Dataset` schema (if data is publicly accessible)
- `Person` author with credentials
- `Organization`
- `Review` if reviewing methodology

## Image slots
- Cover: signature chart
- Section 1: methodology diagram
- Section 2-3: per-finding charts

## Multi-modal content
- Charts via `chart_svg_builder.py`
- Optional: downloadable PDF report
- Optional: interactive data viz (Datawrapper, Tableau Public)

## Time investment

Data research articles take 4-10× longer than listicles to write because the data must exist:
- Either pre-collected (your analytics, customer surveys)
- Or commissioned (Pollfish, Prolific, Centiment survey)

But ROI is highest of any format (backlinks, citations, authority).

## Common pitfalls
- ❌ Made-up statistics (T04 veto — never)
- ❌ Tiny sample (N<100) presented as definitive
- ❌ No methodology section
- ❌ Charts without source attribution
- ❌ "Industry shows" without specifying which industry
