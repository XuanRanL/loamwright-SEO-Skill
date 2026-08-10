---
name: topic-angle-selector
description: Within the chosen format, generates 6 title candidates across ≥3 angles, validates each via title_validator.py, scores CTR potential, picks top-1. Required step before outline-architect. Use whenever planning to write — happens after format-selector and before outline.
allowed-tools: [Read, Write, Bash]
---

# Topic Angle Selector

Given a chosen `format_id`, generate 6 strong title candidates, validate them, pick the winner.

## Inputs

- `state.brief.primary_keyword` + `secondary_keywords`
- `angle.json.format_id` (from format-selector)
- `research.json` (top competitor titles, content gaps)
- `references/seo/power-words.md`
- `references/seo/angle-catalog.md` (12 angles)
- `references/seo/micro-copy-tactics.md`
- `projects/{slug}/brand-config.json` (target_locale, banned_competitors)
- `projects/{slug}/business-context.json :: voice_default` → **register** (see below)

## Two title fields (2026-06-16) — generate BOTH

Stop conflating one string. Produce two aligned fields (full rationale:
`docs/title-optimization-plan-2026-06-16.md`):

| Field | Job | Constraint |
|---|---|---|
| **`seo_title`** | The indexed `<title>` / `rank_math_title` / `og:title`. Survives Google's rewrite (Google rewrites ~76% of titles; >65 chars → ~99.9%). | **51–60 chars** (hard-fail >65 / <30), primary keyword once + front-loaded, sentence case, **no bracketed/parenthesized year**, register-compliant. |
| **`h1`** | The on-page H1 / WordPress post `title`. Carries the full human thesis + nuance + the year if wanted. | Longer OK (≤ ~90 chars). **MUST share the entity + primary keyword + every number that is in `seo_title`** (Google preserves a number in the displayed title 97.3% of the time only when it is in BOTH). |

The old single `title` field still maps to `h1` for back-compat (publisher routes
`meta.title` → WP post title, `meta.seo_title` → `rank_math_title`).

## Register (pick before generating)

Read `business-context.json :: voice_default` and resolve a register — or call
`scripts.validate.title_validator.infer_register(voice_default)`:

| Register | Projects | Digit | Power words | Hard-banned |
|---|---|---|---|---|
| `b2b_technical` | project-charlie, project-juliet | real metric/count, in H1 too | discouraged (warn) | hype: amazing/revolutionary/game-changer |
| `b2b_procurement` | project-kilo | economics numbers | discouraged | hype |
| `dtc_celebration` | project-hotel (living-pet/gift) | optional, soft | warmth ok | hype, urgency |
| `dtc_grief` | project-hotel (pet-loss/memorial) | **default none; soft if used** | **BANNED** | hype, urgency, **best/top/proven/ranked/guaranteed/#1**, exclamation |
| `ecommerce` | project-echo (after /init) | product specs | optional | — |
| `default` | unknown | optional | optional | — |

**project-hotel spans two registers** — pick `dtc_grief` for pet-loss/memorial/cremation
content and `dtc_celebration` for living-pet/gift content, per the article's intent. Do
NOT use one project-wide register for it.

## Output

Updates `workspace/{task_id}/angle.json` with:
- `seo_title` (winning, validated short `<title>`)
- `h1` (aligned long display title — also written to `title` for back-compat)
- `register` (the resolved register key)
- `slug_draft`
- `angle` (one of 12)
- `hook`
- `promise`
- `power_word` (optional now — empty string is valid)
- `digit` (optional now — empty string is valid)
- `persona`
- `alternative_titles_considered[]` (5 backups for repair Round 5; each an `{seo_title, h1}` pair)

## Workflow

### Stage 1: Generate 6 candidates (LLM)

Each candidate is an `{seo_title, h1}` pair. Constraints (changed 2026-06-16 — evidence in
`docs/title-optimization-plan-2026-06-16.md`):

- 6 candidates spanning ≥3 different angles (from `references/seo/angle-catalog.md`)
- Each **`seo_title`** is **51–60 chars** (hard ceiling 65), primary_keyword **once, front-loaded**
- Each **`h1`** carries the full thesis; shares the entity + keyword + every number in its `seo_title`
- **A power word is OPTIONAL, not required** — and is BANNED in the `dtc_grief` register. Lead
  with specificity (a defining metric, a contrast, the article's actual finding), not a power word.
- **A digit is OPTIONAL, not required** — include one only when it is a real list count or metric
  AND it also appears in the `h1`. For informational / myth-buster / grief intents, omit it.
- Each in sentence case (NOT Title Case)
- **No bracketed/parenthesized year in `seo_title`** (`(2026)`/`[2026]` are rewrite-bait — put the
  year in the `h1` instead)
- Respect the register's hard-banned terms (see table above)
- Vary openings: entity-first / contrast-first / verb-first / question-first (only for true
  question intent — questions give NO SERP-CTR premium per Backlinko 2025)

Suggested distribution per 6 candidates:
- 2 from intent-matching angle
- 2 from adjacent angles
- 2 wild-card (myths / case-study / trends)

### Stage 2: Validate each candidate

Validate the `seo_title`, passing the register and the paired `h1` so alignment + number
preservation are checked:
```bash
python -m scripts.validate.title_validator "{seo_title}" \
    --primary "{primary_keyword}" --register "{register}" --h1 "{h1}" --json
```

Filter to those with `all_passed: true` (no hard issues). The `warnings[]` array is advisory —
prefer candidates with the fewest warnings but do not reject on warnings alone. If fewer than 3
pass, regenerate. Common hard failures now: `seo_title` >65 chars, a number in `seo_title` absent
from `h1`, a register-banned term. (Title Case and bracketed/parenthesized years are advisory
warnings, NOT hard fails — though sentence case + year-in-h1 remain the house preference.)

### Stage 3: LLM CTR scoring

For surviving candidates, ask Claude Opus:
- Score 0-100 on: clarity, urgency, specificity, hook strength, primary keyword placement
- Rank top-3

### Stage 3.5: SERP-clone rejection (anti-homogenization)

After CTR scoring, compare each surviving candidate against `research.competitor_titles[].title`.
Reject any candidate that matches a SERP top-10 title pattern. Common clone patterns to detect:

- `"The Complete Guide to X"` / `"The Ultimate Guide to X"` / `"The 2026 Guide to X"`
- `"Best X for [year]"` (when not differentiated by data, count, or persona)
- `"X: Buyer's Guide"` (generic, no thesis hook)
- `"X 101"` / `"Everything You Need to Know About X"`
- Generic `"[N] Best X"` lists when SERP top-10 already has multiple `[N] Best X` results

A candidate is "SERP-cloning" if its non-keyword tokens overlap ≥60% with any top-10 competitor
title. When detected, force the model to regenerate with one of these distinctive frames:

- **Contrarian disambiguation**: leads with what the article reframes (e.g., "Real Draw vs Equivalent")
- **Specific number-as-thesis**: leads with a defining metric (e.g., "The 2.7 µmol/J Threshold")
- **Decision-framework label**: leads with the original IP the article introduces (e.g., "PPE Tier System")
- **Persona-narrowed**: leads with the audience the article is uniquely written for (e.g., "for Half-Commercial Growers")

The winning title must (a) state the article's actual thesis, not its category, and (b) be
discoverably different from every top-10 SERP competitor.

### Stage 4: Pick top-1

The single winner.

### Stage 5: Hook + promise generation

For the winner, generate:
- Hook (opening line of TL;DR section, 25-50 words)
- Promise (what the reader gets, ≤30 words)
- Persona (target reader; 5-10 words; e.g., "intermediate angler who fishes 20+ days/year")

### Stage 6: Slug draft

Generate slug ≤40 chars, kebab-case, includes primary keyword tokens.

## Banned candidates

Do not include titles that:
- Mention `brand-config.banned_competitors` by name
- Use 2+ Power Words (one is already discouraged; two is spammy/AI-tell)
- Are in Title Case throughout
- Use clichés: "Ultimate Best Ever", "World's #1", "Revolutionary Game-Changer"
- Promise impossible specifics ("Get 1000% ROI in 7 Days")
- Match the formulaic AI-tell pattern `N Best X for {Year}: {Power-Word} Picks` as a bare
  formula (no thesis) — Stage 3.5 will reject these as SERP-clones anyway
- Put a `(Year)`/`[Year]` suffix in the `seo_title` (rewrite-bait; the year belongs in `h1`)
- For `dtc_grief`: any power word, any commercial superlative (best/top/proven/ranked/#1),
  urgency, or exclamation

## Output example

```json
{
  "seo_title": "7 best 1000 watt LED grow lamps: HPS-replacement tested",
  "h1": "The 7 best 1000 watt LED grow lamps for 2026: commercial picks tested on efficiency, coverage, and HPS-replacement cost",
  "title": "The 7 best 1000 watt LED grow lamps for 2026: commercial picks tested on efficiency, coverage, and HPS-replacement cost",
  "register": "b2b_technical",
  "slug_draft": "best-1000-watt-led-grow-lamps",
  "angle": "comparison",
  "hook": "After bench-testing 7 commercial 1000W-class LED lamps against measured PPE, coverage uniformity, and a 3-year HPS-replacement cost model, here is the ranking that survived the data.",
  "promise": "Pick the right 1000W-class lamp for a commercial canopy without overpaying on watts you can't use.",
  "power_word": "",
  "digit": "7",
  "persona": "Half-commercial cannabis cultivator (1–50 lights, 500–5000 sqft canopy)",
  "alternative_titles_considered": [
    {"seo_title": "1000 watt LED grow lamps: 7 picks vs HPS, by cost", "h1": "1000 watt LED grow lamps for 2026: 7 commercial picks compared against HPS on total cost"},
    {"seo_title": "1000 watt LED grow lamps: real PPE vs marketing watts", "h1": "1000 watt LED grow lamps: real photon efficiency vs marketing wattage, 7 models measured"}
  ],
  "validation": {
    "seo_title_chars": 55,
    "all_passed": true,
    "warnings": ["power word 'tested' discouraged in b2b_technical"]
  }
}
```

> Note how the digit `7` and entity `1000 watt` appear in **both** `seo_title` and `h1` (number
> preservation), the year lives only in the `h1`, and no power word is forced.

## Handoff

`recommended_next_skill`: `outline-architect` (uses chosen angle + format to design H2 structure)

## See also

- `scripts/validate/title_validator.py` (6-check validator)
- `references/seo/power-words.md` (Power Word library)
- `references/seo/angle-catalog.md` (12 angles)
- `subskills/build/outline-architect/SKILL.md` (next stage)
