# Visual Design Components (global)

Loaded by every writer agent. Companion to `markdown-authoring-conventions.md`.

A good article is not a wall of paragraphs. It breaks into scannable visual units: tables,
callouts, stat grids, definition cards, quotations. This is the catalog of every component
you may build and the EXACT native-markdown pattern for each. The project's scoped CSS turns
that plain markdown into cards, grids, and callouts automatically. **You never write a class,
a `<style>`, or an HTML wrapper. Write the markdown; the CSS does the rest.**

---

## The one rule that governs all of them

The publisher renders your markdown with `html:False`. Any raw HTML tag you type (`<div>`,
`<span>`, `<table>`, `<blockquote>`, `<hr />`) is escaped to visible `&lt;div&gt;` text and
HARD-VETOED by render_lint (L1). So **every component below is plain markdown.** Components are
"selected" by writing a specific heading text (its auto-slug id drives the CSS) or a specific
markdown structure. To trigger a component, use the EXACT heading text shown (`## By the
Numbers`, `## At a Glance`, `## Glossary`, `## TL;DR`).

Three constraints still apply INSIDE every component (they never relax):
- **Em-dash count is 0.** No `—` (U+2014) in attributions, table cells, or separators. Use a
  comma, a period, or the word "by".
- **Every number needs a source marker.** A stat, price, percentage, or date inside a
  component gets a `[claim:cN_S]` marker, exactly like body prose. Never write your own
  `(Author, Year)`. Never invent a figure to fill a component.
- **No banned words / AI-tells** inside component text.

---

## Priority: substance beats ornament (evidence-based)

Not all components are equal. Peer-reviewed evidence (Princeton GEO, KDD 2024) shows the
components that actually raise AI-citation are the CONTENT ones, and eye-tracking (Nielsen
Norman Group) shows decorative boxes can be *ignored* (banner blindness) or *hurt* reading.
Build in this order:

- **Tier A — build first (high value for readers AND AI):** comparison/data **tables**,
  a **cited-statistics** block, an **authoritative quotation**, a **direct-answer-first**
  opening sentence under each descriptive H2. (Quotation +41%, Statistics +30.6%, Cite-sources
  +27.5% in the GEO study.)
- **Tier B — use where the format fits:** FAQ/Q&A content, numbered how-to steps, glossary
  cards, an At-a-Glance summary table, an information-carrying chart (paired with its data).
- **Tier C — use SPARINGLY, this is where over-design lives:** typed callout boxes,
  big-number "stat band", decorative pull-quotes. A decorative pull-quote that just repeats
  body text is the single lowest-value element (adds nothing for AI, disrupts reading). Cap:
  at most ONE table per section, ONE callout per section, ≤1 decorative pull-quote per article.

**Restraint rule:** the measured failures are all *over-design* failures, never under-design.
When in doubt, a descriptive subheading + a short list beats a colored box. Only box something
a reader genuinely needs to stop for (a real warning, a real key stat, a real external quote).

---

## Component 1 · Comparison / data table  (Tier A)

**When:** you compare 2+ things across 2+ attributes (tiers, methods, specs, X-vs-Y), or
present a small structured dataset. AI lifts tables verbatim into answers.
**When NOT:** a single value or a 1-D list (use a stat or a bullet); never force prose into a
grid; keep to ≤6 columns and ideally ≤5 rows.
**Only build a table when `section_spec.needs_table == true`** (keeps it coherent with the
table gate). Native GFM pipe table:
```markdown
| Tier | Efficacy | Price | Best for |
|---|---|---|---|
| Budget | Below 2.4 [claim:c5_1] | $150 to $300 | Single tent |
| Premium | 3.0 and up [claim:c5_3] | $1,200 plus | Sealed rooms |
```
For a decision snapshot, put it under `## At a Glance` (accent header, bold first column).

## Component 2 · Cited-statistics block "By the Numbers"  (Tier A)

**When:** 3 to 6 headline numbers that anchor the article. The most quotable block for AI.
**When NOT:** a single number (put it in prose); numbers that only make sense compared (table);
**any item that has no number at all** (use a checklist or prose — see the red line below).
Write a heading + a bold-first bullet list. The bold leading run becomes the big number:
```markdown
## By the Numbers

- **2,400 µmol/s** photon flux from a true 1000W fixture [claim:c2_1]
- **5x5 ft** flowering canopy covered [claim:c2_2]
- **30-75%** of cost recoverable via rebates [claim:c6_1]
```
One per article. The number MUST also read as plain text (AI reads HTML, not styled pixels).

### ⛔ THE VALUE CONTRACT (hard gate — `scripts/lint/stat_grid_check.py`)

**The bold lead is the DISPLAY FIGURE, not a title and not a sentence.** It is rendered as large
type inside a narrow card. Everything descriptive goes AFTER the closing `**`, unbolded.

| Rule | Limit | Defect |
|---|---|---|
| Value length | ≤ 16 characters | `S1` |
| Longest word in the value | ≤ 10 characters | `S2` |
| Value must START with a number | digit / `$£€¥` / `~ ≈ ± + - < > #` | `S3` |
| Value must not end with `:` | it is a label, not a figure | `S4` |
| Item count | 3-6 (warning only) | `S5` |

```markdown
❌ - **30% more chlorophyll** in shaded tencha, 5.65 vs 4.33 mg/g   (S1+S2)
✅ - **30% more** chlorophyll in shaded tencha, 5.65 vs 4.33 mg/g

❌ - **$12,000 to $25,000+ per month** enterprise retainer band      (S1)
✅ - **$12k-$25k/mo** enterprise retainer band

❌ - **Notched Izod verdict:** TPU absorbs 4x the impact energy      (S1+S3+S4)
✅ - **4x** the notched Izod impact energy of PLA
```

**Why this is a hard gate and not a style note.** The card gives the value a narrow column of
large type. A value longer than the column overflows, and because the article wrapper sets
`word-wrap: break-word` (a deliberate long-URL guard) the overflow chops the word IN HALF.
project-foxtrot shipped `chlorophyll` rendered as **`chloroph / yll`**. A 2026-07-14 survey of 591 posts
found **107 of 365 stat values (29%) breaking this way across 8 projects**, most of them already
live. The CSS was hardened the same day so a bad value now degrades gracefully instead of
shattering — but graceful degradation is the safety net, not the target. This contract is the
target, and the lint enforces it.

If an item genuinely has no number, it does not belong in a stat grid. Use a checklist
(Component 6) or plain prose.

## Component 3 · Authoritative quotation  (Tier A — highest AI lift)

**When:** quote a REAL external authority (expert, standards body, cited study) from your
quotes bank, with attribution. This is the strongest single AI-citation lever.
**When NOT:** never invent a quote; never quote competitor article text (red line). This is
NOT a decorative pull-quote (see Component 8).
```markdown
> **Per the DLC V5.0 spec,** horticultural fixtures must hit 2.5 µmol/J to qualify [claim:c4_1].
```
Blockquote with a bold lead renders as an accent card. Keep to 1 to 3 sentences.

## Component 4 · TL;DR / bottom-line box  (Tier A/B)

**When:** a 1 to 3 sentence answer-first summary near the top (answer-engine + snippet bait).
Use the heading `## TL;DR` (or `## In short` / `## The bottom line`); the paragraph after it
becomes an accent highlight box, distinct from the 2-paragraph `## Abstract`.
```markdown
## TL;DR

Size flowering canopies at 30 to 40 watts per square foot [claim:c3_2], then derate 30 percent for greens.
```
**When NOT:** a TL;DR that just restates the title adds nothing.

⚠️ **ARTICLE-LEVEL ONLY (v3.38.3).** The `## TL;DR` box lives at the TOP of the
article (assemble.py auto-emits it from `outline.tldr_seed`). NEVER open a body
SECTION with its own `## TL;DR` H2: the parent section H2 is left with zero body
content, the box's H3s hijack the section's outline, and a duplicate `#tldr-2`
anchor ships (2026-07-09 batch, reviewer-bounced). When a section spec carries
`tldr_box` in `design_components`, realize it as an **answer-first opening
PARAGRAPH** (a crisp 1-2 sentence direct answer as the section's first lines) —
same extraction value, no structural damage. Section-level `## TL;DR`/`## Glossary`
/`## By the Numbers` H2s are legal ONLY at a section BOUNDARY (after all of the
section's H3s), never between H3s.

## Component 5 · Numbered framework / how-to steps  (Tier B)

**When:** an actionable sequence the reader executes. (Keep the CONTENT; Google removed HowTo
rich results in 2023, so do not expect a SERP feature.)
```markdown
1. **Measure the true canopy,** not the room. A 5x5 tent lights a 4.5x4.5 canopy.
2. **Set target PPFD by crop and stage** before you shop [claim:c8_1].
```

**Checklist realization — NEVER GFM checkboxes.** When a section spec assigns a `checklist`
component, realize it as plain bullets (`- item`), bold-led bullets (`- **Lead.** detail`), or
the numbered framework above. NEVER `- [ ]` / `- [x]` task-list syntax: the publisher's
markdown-it has no task-list plugin, so the literal `[ ]` bracket ships to the reader
(`render_lint` L13 hard veto; caught live in the 2026-07-07 batch).

## Component 6 · Glossary / definition cards  (Tier B — good for GEO entity clarity)

**When:** define 3+ key terms/entities (feeds clean "X is Y" extraction). Use `## Glossary`
+ a `**Term** — definition` list:
```markdown
## Glossary

- **PPFD** — photosynthetic photon flux density; µmol/m²/s at the canopy [claim:c1_1].
- **DLI** — daily light integral; PPFD integrated over the photoperiod.
```

## Component 7 · Typed callout box  (Tier C — sparingly, restrained)

**When:** lift ONE thing a reader must not miss: a warning, a rule of thumb, a key term. One
per section max. Write a blockquote led by a bold label the publisher recognizes:
```markdown
> **Warning:** Never run a 1000W fixture on a 120V circuit; use a dedicated 240V line [claim:c7_1].
> **Tip:** Confirm DLC rebate eligibility before you read the spec sheet.
```
Recognized labels: `**Note:**`, `**Info:**`, `**Tip:**`, `**Warning:**` (also `**Caution:**`,
`**Important:**`). Bold the label, colon, then the sentence. **When NOT:** for a normal
supporting sentence (leave it in the paragraph); avoid multiple loud boxes per screen, they
get pattern-matched as ads and skipped.

## Component 8 · Decorative pull-quote  (Tier C — lowest value, ≤1 per article)

**When:** once, to spotlight a single memorable line in an editorial/opinion piece. Evidence
says decorative pull-quotes can *reduce* reading and add nothing for AI, so use rarely and
never to repeat text you already wrote as a fact.
```markdown
> ❝ Photon efficacy, not wattage, decides your electricity bill. ❞
```
If the line carries a number, mark it `[claim:cN]`. Attribution on its own line, no em-dash.

## Component 9 · CTA module  (pipeline-injected — writers NEVER hand-author this)

**What:** the project's designed conversion card: `### {heading}` + one bold-led
paragraph with a link to the project's funnel page, rendered in one of 3 visual
skins depending on which heading was used — card (`xr-cta-box`, filled button,
default), quiet (`xr-cta-box xr-cta-quiet`, outline button, editorial tone), or
banner (`xr-cta-box xr-cta-banner`, full-width strip, `end` placement only).

**Building-block palette** (compose from these, cap at 2-3 per block — an
avatar AND a stat line AND a quote AND a long paragraph is over-decorated):
circular avatar photo, bold stat/proof-point opening segment, italic
quote-hook + attribution, and the filled-or-outline button (just the
paragraph's markdown link — the CSS renders the button chrome).

**How it's generated (v3.37, three orchestrator stages, in order):**
`cta-brief-builder` (deterministic fact resolver — resolves the matched
service/team member/proof point from `business-context.json ::
conversion_offers`, or writes a no-config sentinel) → `cta-writer` (LLM,
composes genuinely unique per-article copy from ONLY the resolved facts,
conditional on a real brief) → `cta-injection` (deterministic placement into
draft.md; falls back to the legacy static `business-context.json :: cta.variants`
config on projects without `conversion_offers`). Full contract, CLI
invocations, and config schema: `subskills/optimize/cta-placement/SKILL.md`.

**Writer/optimizer contract:** do NOT write, move, reword, or delete a CTA
block. The heading text is drawn from a registered 21-phrase list across the
3 skins (`scripts/_core/component_headings.py :: COMPONENTS['cta'|'cta_quiet'|'cta_banner']`)
— an unrecognized heading renders unstyled. The pre-publish gate re-scans for
stripped blocks and verify_post check 29 confirms the card renders live with
the correct link target. On cta-enabled projects, also write NO prose CTA
sentence in the conclusion — the card replaces it.
**Not substance:** this component is deliberately excluded from the visual-density floor.
Copy rules: no em-dash, no UTM on internal links; numbers are allowed ONLY when
copied verbatim from a resolved `conversion_offers` proof point (fact-checked by
`brand_fact_check.py`) — never invented.

---

## Do-not list (all components)

- ❌ No raw HTML wrappers (`<div class="callout">`, `<table>`, `<blockquote>`). Escaped to
  visible text, render_lint L1 veto.
- ❌ No `<hr />`. Write `---` on its own line.
- ❌ No em-dash inside attributions, table cells, or stat separators.
- ❌ No unsourced number in any component. Mark it `[claim:cN_S]`.
- ❌ Do not overload one section: at most one table, one callout, one stat block per H2.
- ❌ Do not label a component to the reader ("Callout:", "Stat grid:"). The reader sees only
  the styled result; the trigger heading text (`## By the Numbers`) is the exception and is fine.

## Component ↔ format affinity (quick guide)

| Format | Lean on |
|---|---|
| Pillar | comparison table, By the Numbers, 1 quotation, glossary (first-mention terms), checklist |
| Listicle / roundup | per-item spec table or stat row, ≤1 callout per top pick |
| Comparison / review | 3 tables (quick / pricing / feature), 1 verdict quotation |
| How-to / buyers-guide | numbered framework, ≤2 warning callouts, 1 spec table |
| Weekly digest | At a Glance table, By the Numbers, callouts for the "Our Take" opinion |
| Opinion | 1 real quotation, minimal boxes (highest over-design risk) |
