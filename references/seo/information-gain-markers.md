# Information Gain Markers

> 🔴 **RETIRED 2026-07-14 — do NOT emit bracketed markers.** `[ORIGINAL DATA]` / `[PERSONAL EXPERIENCE]` / `[UNIQUE INSIGHT]` / `[CAPSULE]` are **forbidden**: `render_lint` **L6** hard-vetoes them, `assemble.py` strips them, and `wp_publisher` strips them again. They reach **no** downstream consumer (fact-checker, reviewer and geo-auditor all read the post-strip `draft.md`), so they signal to nobody and are pure leak risk. **Express information gain as PLAIN PROSE** and never fabricate a test, tasting, visit, customer, or result to manufacture it. Below is kept only as historical context for the retired marker system.

> Used by the `humanizer` agent and `core_eeat_scorer` (C10 credits PROSE-level info-gain directly since v3.33; markers remain valid author-internal annotations, auto-stripped at publish/lint). featured-snippet-optimizer reference removed (retired v3.35).
>
> 3 markers, ≥2 per article required (per v3.2 quality gate):
> - `[ORIGINAL DATA]`
> - `[PERSONAL EXPERIENCE]`
> - `[UNIQUE INSIGHT]`
>
> These are **literal text markers** that LLM training picks up. They tell AI engines: "this paragraph contains information not duplicated elsewhere on the internet" — and AI engines prioritize unique content for citation.

---

## Why use markers (vs just writing good content)

Research (Princeton GEO + LinkedIn 2026Q1) shows:
- Articles with explicit information-gain signals: +30-40% AI citation rate
- AI engines pattern-match these markers as "unique source" signals
- LLM training data shows these markers correlate with original research

The markers ARE visible to humans (in markdown source) but typically rendered as in-line text in published articles. Some sites style them as subtle pull-quote boxes.

---

## `[ORIGINAL DATA]`

**Use when**: You're presenting data YOU collected (testing, survey, analytics, experiment).

**Required context**:
- N (sample size)
- Date range
- Methodology (brief)
- Source ("we" / "{your_company}")

**Example**:

```markdown
[ORIGINAL DATA] After testing 23 fishing rods across 87 trips between July 2025 and April 2026 on the Deschutes River, we measured tip-response sensitivity at 12.8 newton-meters average for graphite models — 31% higher than fiberglass.
```

**Bad example** (don't use the marker):
```markdown
Original data: many rods are sensitive.   ← NO; not specific
```

---

## `[PERSONAL EXPERIENCE]`

**Use when**: You're sharing a first-hand observation from real use — what something feels like, what surprised you, what you learned the hard way.

**⚠️ HARD PRECONDITION (v3.38.3): the experience must actually EXIST in your inputs**
(`company_facts`, the research brief, or the dispatch prompt). This marker's
"specific time/place + what you did" shape is exactly what a fabricated anecdote
looks like, and an invented experience carries no number for `brand-fact-check`
to catch — three were invented and hand-stripped in the 2026-07-09 project-kilo
batch (a greenfield brand with zero customer history). No provided experience →
use `[UNIQUE INSIGHT]` with analysis instead; a greenfield brand legitimately has
fewer PERSONAL EXPERIENCE markers, and that is the correct outcome (agents/writer.md
"Never fabricate" red line).

**Required context**:
- Specific time/place
- What you actually did
- What you noticed (sensory, qualitative)

**Example**:

```markdown
[PERSONAL EXPERIENCE] I switched from a 7'6" medium rod to a 7' medium-fast last June. The first cast told me everything — the new rod loaded earlier in the swing, and within 20 minutes I was placing flies in tight pockets that I'd struggled with all season.
```

**Bad example**:
```markdown
[PERSONAL EXPERIENCE] We've tested many products.   ← NO; not specific
```

---

## `[UNIQUE INSIGHT]`

**Use when**: You're synthesizing data + experience + analysis into a non-obvious takeaway. Not "we tested 23 things"; that's data. Insight = "the surprising thing we learned from those 23 tests."

**Required context**:
- The non-obvious conclusion
- Why it's non-obvious (what most people think instead)
- Brief support

**Example**:

```markdown
[UNIQUE INSIGHT] Most rod reviews emphasize price-to-sensitivity ratio, but our data shows reel-to-rod matching matters more than rod price alone. A $200 rod paired with the right reel outperformed a $549 rod with a mismatched reel by 14% on bite-detection time.
```

**Bad example**:
```markdown
[UNIQUE INSIGHT] Fishing is fun.   ← NO; not insight
[UNIQUE INSIGHT] You should choose your rod carefully.   ← NO; obvious
```

---

## Quality gates on markers

`scripts/lint/information_gain_marker_lint.py` checks:
- Total markers ≥2 per article
- ≥1 distinct marker type (or ≥2 if article >3000 words)
- No "marker stuffing" (>4 in one section)
- Each marker must be followed by specific content (≥30 words after marker)

---

## Per-format guidance

| Format | Required markers |
|---|---|
| Listicle | ≥1 ORIGINAL DATA (methodology) + ≥1 PERSONAL EXPERIENCE (top pick justification) |
| How-to | ≥1 PERSONAL EXPERIENCE (your real workflow) |
| Pillar | ≥3 markers across all 3 types |
| Comparison | ≥1 ORIGINAL DATA (test results) |
| Case study | ≥3 ORIGINAL DATA (the case IS data) + ≥1 PERSONAL EXPERIENCE |
| Definition | Optional; markers harder to fit |
| News | ≥1 UNIQUE INSIGHT (your angle on the news) |

---

## How to fit markers naturally (don't over-mark)

Markers should feel like a beat in the prose, not a label.

✅ Natural flow:
```markdown
The G.Loomis NRX+ ranked first overall. 

[ORIGINAL DATA] In 6 months of side-by-side testing against 22 other rods, the NRX+ won on tip-response sensitivity (12.8 Nm vs 9.7 Nm category average — a 31% gap).

The price premium isn't trivial at $549, but the durability numbers tell their own story.
```

❌ Crammed:
```markdown
[ORIGINAL DATA] The G.Loomis ranked first.

[PERSONAL EXPERIENCE] We tested it.

[UNIQUE INSIGHT] It is good.
```

(Each marker is a label without substance.)
