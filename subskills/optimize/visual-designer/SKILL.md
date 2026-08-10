---
name: visual-designer
description: Optimize-phase pass that restructures a humanized draft into scannable visual components (tables, cited-stat grids, quotations, callouts, glossary, TL;DR) using native markdown the scoped CSS styles. Substance over ornament; enforces a floor and a ceiling. Runs after humanizer/geo/linker, before render-lint.
allowed-tools: [Read, Edit, Write, Bash]
disable-model-invocation: false
user-invocable: false
---

# Visual Designer (optimize phase)

Make the article scannable and well-designed without changing what it says. This is a
presentation pass. See `agents/visual-designer.md` for the role and hard constraints, and
`references/style/visual-design-components.md` for the exact native-markdown pattern of every
component. This SKILL is the playbook.

## Step 0 — Read the situation

```bash
# density result (which components are missing / over-used), if the check already ran
cat memory/workspace/{task}/visual-density.json 2>/dev/null
```
Read `draft.md` and `angle.json` (`format_id`). The format decides which components fit.

## Step 1 — Plan by format (substance first)

| Format | Add (in priority order) |
|---|---|
| pillar | comparison table (Types/Choosing), `## By the Numbers`, 1 quotation, `## Glossary` (What-is-X), a checklist (Getting started) |
| comparison / review | up to 3 tables (quick / pricing / feature), 1 verdict quotation |
| how-to / buyers-guide | numbered framework, ≤2 `> **Warning:**` callouts on failure steps, 1 spec table |
| listicle / roundup | a spec table or `## By the Numbers` per item cluster, ≤1 callout per top pick |
| weekly-digest | `## At a Glance` table, `## By the Numbers`, callouts for opinion blocks |
| opinion | 1 real quotation, minimal boxes |

Only add what genuinely fits the content. Do NOT invent a comparison that is not in the text.

### ⛔ Stat-grid value contract (hard gate — `scripts/lint/stat_grid_check.py`, v3.39.0)

In a `## By the Numbers` list the **bold lead becomes a large DISPLAY FIGURE** inside a narrow
card. It must be a short number: **≤16 chars · longest word ≤10 chars · starts with a
digit/`$`/`~`/`±` · does not end with `:`**. All descriptive words go AFTER the closing `**`.

```markdown
❌ - **30% more chlorophyll** in shaded tencha        →  ✅ - **30% more** chlorophyll in shaded tencha
❌ - **$12,000 to $25,000+ per month** retainer band  →  ✅ - **$12k-$25k/mo** enterprise retainer band
❌ - **Notched Izod verdict:** TPU absorbs 4x         →  ✅ - **4x** the notched Izod impact energy of PLA
```

A phrase in the bold overflows the card and chops MID-WORD (project-foxtrot shipped `chlorophyll` as
`chloroph / yll`; a 591-post survey found 107 of 365 stat values breaking across 8 projects).
**An item with no number is not a stat** — 25 of those 107 defects were writers using the grid as a
generic bold-led checklist. Use a checklist or prose instead.
Verify before finishing: `python -m scripts.lint.stat_grid_check --workspace {task_id} --json`

## Step 2 — Convert prose to components (native markdown only)

- **Comparison table** — a real GFM pipe table (≤6 cols). Keep each `[claim:cN]` on its cell.
- **By the Numbers** — a NEW `## By the Numbers` section + a `- **N unit** label [claim:cN]`
  list of 3 to 6 numbers ALREADY in the draft. Never invent a number.
- **Quotation** — lift an existing, already-cited authority statement into
  `> **Per {source},** ... [claim:cN].`
- **TL;DR** — a NEW `## TL;DR` near the top + a 1 to 3 sentence answer-first paragraph drawn
  from the article's own conclusion.
- **Glossary** — a NEW `## Glossary` + `- **Term** — definition` list for first-mention terms.
- **Callout** — `> **Warning:/Tip:/Note:** ...` for one thing per section a reader must not miss.
- **Pull-quote** — `> ❝ line ❞` at MOST once per article, editorial only.

## Step 3 — Respect the floor and the ceiling

- **Floor:** the article needs ≥1 Tier-A substance component (table / stat grid / quotation)
  and a weighted score ≥ the minimum. A wall of text fails.
- **Ceiling (evidence-based, do not exceed):** ≤1 decorative pull-quote; ≤~1 callout per
  section; never let decorative boxes outnumber substance. Over-design (many colored boxes)
  is a measured failure (banner blindness) — restraint wins.

## Step 4 — Idempotency + safety

- If a component is already present, do NOT duplicate it. Only add missing ones.
- Never edit heading text/anchors, `[claim:*]` / `(Author, Year)` citations, the References
  section, or the signature. Never write raw HTML. Never add an em-dash.

## Step 5 — Verify + write evidence

```bash
python -m scripts.lint.visual_density_check --workspace {task} --json
```
Confirm `passed: true` (or that you added everything the content supports). Then write
`memory/workspace/{task}/visual-design-report.json` with `_generated_by:"visual-designer-subagent"`,
`components_added`, `components[]`, `density_score`. The orchestrator gates on that file.

## Notes

- render-lint (L1-L9) runs right after you — any raw HTML or orphan bold you introduce is
  caught there, so keep to clean native markdown.
- Typed callouts and pull-quotes get their color/pull-quote styling from the publisher hook
  `_tag_callouts_and_pullquotes` (it reads the blockquote's bold label). You only write the
  `> **Label:** ...` markdown; the class is added at publish.
