# Weekly Digest Template

> Format ID: `weekly-digest`. Recurring multi-item industry-news digest, published on a fixed weekly cadence.
> Used by `outline-architect` when `format_id == "weekly-digest"`.
> **Entry point: `/weekly` skill only — NEVER auto-selected by the keyword pattern in `format-selector`.**

## Default structure

```
{Industry} Weekly: {YYYY-MM-DD} — {Punchy Hook Phrase}

## TL;DR
This week's 3-5 biggest items as bullets. Grounding block: every bullet ≤ 15 words. (Target: 60-90w)

## The Big Story
The #1 item of the week. Brand "so what" + one cited number.
Sub-structure:
  ### What Happened (150w facts, ≥1 citation)
  ### Why It Matters to {Reader Persona} (150w brand angle)
  ### Our Take (100w labeled opinion — use original analysis (plain prose))

## Also This Week
Each item: **{Item Title}** — what happened WITH inline citation + our take (labeled opinion).
Repeat N times (3-6 items, each ~150-200w):
  ### {Item Title}
  What happened (1 para, ≥1 citation). Our take (1 para, label as opinion).

## By the Numbers
One or more hard stats harvested this week. Mark each with original data (plain prose) if first-party;
otherwise mark source inline. Format as callout or table. (Optional; target: ~150w)

## On Our Radar
Short bullet list (4-6 items) of smaller news items that don't warrant full coverage.
Each bullet: ≤ 25 words + source hyperlink. (Target: ~150w)

## Follow-ups
Updates to stories covered in a prior digest issue. Reference the prior issue date.
Format: **{Original story headline} (covered {YYYY-MM-DD})** — update in ≤ 50 words.

## FAQ
2-3 questions readers are likely to ask THIS week, based on the Big Story and Also This Week.
Each answer: 50-100 words. Use `## FAQ` as the H2 (triggers FAQPage schema injection).

## References
APA-7 formatted entries. Target 8-10, hard cap 15. Every URL must be link-resolvable.
Mix must include ≥ 1 news source (Tier-1) per major story + ≥ 1 industry standard body.

<hr />

<p class="article-signature"><em>Last reviewed and updated: {Month Year}. Author: {Project author/team}. {Project-specific CTA}.</em></p>
```

## Word budget (2,000–2,800w target)

| Section | Words | Notes |
|---|---|---|
| TL;DR | 75 | 60-90w range; 3-5 bullets |
| The Big Story | 400 | ~14% |
| Also This Week (4 items × 175w) | 700 | Scale items to hit total target |
| By the Numbers | 150 | Optional; omit if no hard stats |
| On Our Radar | 150 | ~5-6 bullets |
| Follow-ups | 150 | Optional; omit in inaugural issue |
| FAQ (2-3 × 90w) | 225 | |
| References | (count separate) | Not in word count |
| **Total body** | **~1,850–2,650w** | Add transition sentences to fill |

## Slug pattern

```
{industry}-weekly-{YYYY-MM-DD}
```

Examples:
- `seo-weekly-2026-07-07`
- `3d-printing-weekly-2026-07-07`

## Required modifiers

- `tldr-first` ✓ — TL;DR block is the mandatory first body H2; grounding block for AI engines
- `freshness-critical` ✓ — `dateModified` is essential; publish within 24-48h of the issue date
- `citation-capsules-per-h2` ✓ — every H2 section must carry ≥ 1 inline citation (Princeton +28-41%)
- `info-gain-prose` ✓ — ≥1 piece of original analysis (editorial take) + any original data, in plain prose

## Hard rules

1. Publish within 24-48h of the stated issue date (freshness decay is rapid for news digests)
2. Cite ≥ 1 Tier-1 source per major story item (The Big Story + each Also This Week item)
3. Distinguish facts from editorial opinion — use original analysis (plain prose) for the brand take
4. `datePublished` + `dateModified` are mandatory in schema (freshness signal)
5. TL;DR bullet items must link to the section below (anchor or scroll) where possible
6. "Our Take" paragraphs must be labeled as opinion, never presented as fact
7. By the Numbers section: always cite the source inline; original data (plain prose) only if first-party
8. Follow-ups: always reference the prior issue date explicitly

## Schema additions

- `BlogPosting` (base — weekly digest is editorial content, not breaking news)
- `ItemList` — list of stories covered this issue (for structured extraction by AI engines)
- `FAQPage` — from the FAQ section (triggers rich results)
- `datePublished` + `dateModified` on BlogPosting (mandatory for freshness signal)

## Image slots

- Cover: editorial image for The Big Story (avoid generic stock; prefer data visualizations)
- Section: optional inline chart or screenshot if By the Numbers has significant data

## Entry-point note

This format is **only reachable via `/weekly`**. The `/weekly` entry skill pre-writes `angle.json`
with `format_id: "weekly-digest"` and `slug_draft` using the `{industry}-weekly-{YYYY-MM-DD}` pattern
before the pipeline starts. The `format-selector` skill does NOT auto-select this format via
keyword pattern matching.

## Time decay

Weekly digest articles serve freshness traffic then archive:
- T+0 to T+6 days: primary traffic window
- T+7 to T+30 days: index archive / cluster authority
- T+30+: minimal fresh traffic; value is in series cohesion and internal linking

## Common pitfalls

- ❌ Publishing more than 48h after the stated issue date (freshness signal lost)
- ❌ Also This Week items without inline citations (cite every factual claim)
- ❌ Editorial take ("Our Take") not labeled as opinion — always flag
- ❌ TL;DR longer than 90 words — keep bullets tight, AI grounding needs density not length
- ❌ Missing `dateModified` in schema — defeats the entire freshness-critical modifier
- ❌ Treating By the Numbers stats as [ORIGINAL DATA] when sourced externally
- ❌ Skipping Follow-ups permanently — returning readers expect continuity
- ❌ Auto-selecting this format via keyword — only `/weekly` entry skill should force it
