---
name: localization-pass
description: 7-dimension locale adaptation (currency / units / spelling-dialect / idioms / regulations / tone / date-format) + multilingual audit (translation coverage matrix / hreflang validation / SEO parity / freshness check). Triggered when state.brief.target_market_locale != en-US, or via /locale-audit on existing multilingual directory.
allowed-tools: [Read, Write, Edit, Bash, WebFetch]
disable-model-invocation: false
user-invocable: true
---

# Localization Pass · 7-Dimension Adaptation + Multilingual Audit

Single-article locale adaptation OR portfolio-wide multilingual quality audit.

## When to invoke

- During `/article` pipeline when `state.brief.target_market_locale != "en-US"`
- `/locale-audit <directory>` — portfolio audit of existing multilingual content
- After `/article` translation runs to verify per-language SEO parity
- `/locale-check workspace/{task}/draft.md` — single-file dialect check

## Mode 1 · Per-article dialect gate + 7-dimension adaptation

> **Wired v3.35 (2026-07-04):** the dialect check is now the mandatory
> **`locale-spelling-check`** orchestrator stage — it runs on EVERY article
> (including en-US, where its production value is catching en-GB spellings
> leaking from model training data: "colour/organise/whilst" in en-US prose is
> an AI-tell). The executor existed since v5.0 with zero invocations (Rule 6).
> Evidence + thresholds: `references/seo/serp-feature-value-2026.md` §5.

Applied during the Optimize phase; the FULL 7-dimension adaptation applies when
the target locale differs from US-English defaults.

### The 7 dimensions

| # | Dimension | Example transformation |
|---|---|---|
| 1 | **Currency** | `$199` → `£169` / `€189` / `¥21,000` |
| 2 | **Units** | inches → cm, lb → kg, miles → km, °F → °C |
| 3 | **Spelling dialect** | color → colour, organize → organise, customize → customise |
| 4 | **Idioms** | "drop the ball" (US) → "let the side down" (UK) / direct translation (non-EN) |
| 5 | **Regulations** | FTC → ASA (UK) / ACCC (AU) / KSA (KR) / 消费者权益保护法 (CN) |
| 6 | **Tone** | US casual → UK formal / JP polite (敬語) / DE direct |
| 7 | **Date format** | MM/DD/YYYY → DD/MM/YYYY / YYYY-MM-DD / 令和7年 |

### Workflow

```bash
# Step 1 (WIRED, mandatory stage — runs automatically in the pipeline):
python -m scripts.lint.spelling_dialect_check --workspace {task_id} --json
# Resolves target dialect from state.brief.target_market_locale (en-US default).
# Exempt zones: References/Further Reading tail, blockquotes, code, link URLs,
# Capitalized mid-sentence proper nouns ("Labour Party", "Centre for ...").
# Gate: FAIL at drift_count >= 3 (systemic drift); 1-2 hits = warnings.
# Output: workspace/{task}/locale-spelling-lint.json (passed flag enforced by
# the orchestrator, run_pipeline._GATE_STAGES, and the pre-publish gate).

# Step 2 (repair, when the gate FAILs): apply drift_words[].use_instead
# replacements directly (deterministic word swaps — surgical Edit, cheapest
# route), then the freshness rule re-runs Step 1 automatically.
# NOTE (correction, v3.35): the pre-v3.35 claim that "the humanizer agent
# handles the locale layer" was FALSE — the humanizer has no locale code. For
# non-English locales the dialect gate no-ops and the 7-dimension adaptation
# below remains an LLM editing task guided by references/localization/{locale}.md.

# Legacy single-file form (manual diagnostics):
python -m scripts.lint.spelling_dialect_check --input {path}.md --target en-UK --json
```

### Per-locale references (loaded on demand)

- `references/localization/{locale}.md` — currency / units / regulation / cultural per market
- `references/localization/spelling/en-{US,UK,AU,CA,NZ}.md` — 5 English dialect mappings

Currently supported locales (with detail-level references):
- **en-US** (default), **en-UK**, **en-AU**, **en-CA**, **en-NZ**
- **de**, **fr**, **es**, **it**, **pt**, **nl**
- **jp**, **kr**, **cn**, **tw**, **hk**, **sg**

For new locales: ship with skeleton reference + flag for user to fill domain-specific knowledge.

## Mode 2 · `/locale-audit <directory>` — multilingual quality control

Audits a directory of multilingual content for completeness, consistency, hreflang correctness, meta-tag parity, freshness.

### Phase 1: Discovery

1. Scan target directory. Group blog posts by language using:
   - Subdirectory names (`en/`, `de/`, `fr/`)
   - Frontmatter `lang` and `translatedFrom` fields
   - `hreflang-map.json` if present
2. Build content matrix mapping which post exists in which languages
3. Detect source language (most common `translatedFrom` target, or `sourceLanguage` field in `hreflang-map.json`)

### Phase 2: Completeness audit

Translation coverage matrix:

```
| Post (EN) | DE | FR | ES | JA |
|-----------|----|----|----|----|
| how-to-avoid-ai-slop | ok | ok | missing | missing |
| content-marketing-2026 | ok | missing | ok | missing |

Coverage: 60% (6 of 10 expected translations present)
Missing: 4 translations needed
```

### Phase 3: Content parity audit

For every post that exists in multiple languages:

| Check | What | Severity |
|---|---|---|
| Section count | Same number of H2 + H3 sections | Critical |
| FAQ count | Same number of FAQ items | High |
| Image count | Same number of images | High |
| Chart count | Same number of charts (SVG figures) | High |
| Word count ratio | Within expected band (DE +20-30%, JA -20%, ES +10%) | Medium |
| Link count | Similar internal + external link counts | Medium |
| Citation capsule count | Same number per H2 across versions | Medium |
| Frontmatter parity | All required fields per version | High |

Flag every significant deviation as an issue.

### Phase 4: SEO parity audit

For every language version verify:

| Element | Check | Severity |
|---|---|---|
| Title tag | Present, correct length for language | Critical |
| Meta description | Present, correct length, contains a stat | Critical |
| `lang` attribute / frontmatter `lang` | Present, valid ISO 639-1 | Critical |
| Schema `inLanguage` | Matches `lang` | High |
| Schema `translationOfWork` | Points to source URL | High |
| Alt text | Translated (no English alt in non-EN posts) | High |
| Slug | Localized (no English slug in non-EN posts) | Medium |
| Tags | Localized | Medium |
| Keywords | Localized | Medium |

### Phase 5: Hreflang audit

If `hreflang-tags.html`, `hreflang-sitemap.xml`, or `hreflang-map.json` exists:

| Check | What | Severity |
|---|---|---|
| Self-referencing | Each page references itself | Critical |
| Return tags | Every relationship bidirectional | Critical |
| `x-default` | Present, points to source language | Critical |
| Language codes | Valid ISO 639-1 (with optional region) | High |
| URL consistency | Same protocol, trailing-slash convention | Medium |
| Completeness | Every language version represented | High |

If no hreflang files exist: critical gap. Offer regeneration via translate skill.

### Phase 6: Freshness audit

For posts with `translatedDate` frontmatter:

| Check | What | Severity |
|---|---|---|
| Source updated after translation | Source modified after `translatedDate` | Critical |
| Translation older than 90 days | May need refresh | Medium |
| `lastUpdated` mismatch across versions | Versions out of sync | Medium |
| File mtime newer than `translatedDate` | Content changed without frontmatter update | Warning |

Emit actionable commands per stale file:

```
3 translations are stale:
- de/ki-trends-2026.md (source updated 2 days ago)
  → Run: /translate en/ai-trends-2026.md --to de
- fr/ki-trends-2026.md (source updated 2 days ago)
  → Run: /translate en/ai-trends-2026.md --to fr
- es/tendencias-ia-2026.md (translation >90 days old)
  → Run: /translate en/ai-trends-2026.md --to es
```

### Phase 7: Report

Output to `projects/{slug}/locale-audit-{date}.md`:

```markdown
## Multilingual content audit report

### Summary
- Posts audited: [N] across [N] languages
- Overall health: [score] / 100
- Critical issues: [N]
- Warnings: [N]

### Translation coverage
[Matrix from Phase 2]

### Issues found

#### Critical
- [Issue with file references]

#### Warnings
- [Issue with file references]

#### Passed
- [Checks that passed]

### Prioritized fixes
1. [Highest-impact action]
2. [...]

### Stale-translation alerts
[Runnable commands from Phase 6]

### Quick fixes
- Run `/translate <file> --to <missing-langs>` for [N] missing translations
- Run `/multilingual` to regenerate hreflang assets
- Run `/locale <file> --locale <code>` for weak cultural adaptations
```

## Error handling

| Scenario | Action |
|---|---|
| Empty directory | "No blog posts found in [path]" |
| Only one language present | Report coverage, suggest target languages |
| No hreflang files | Flag as critical gap, offer regeneration |
| Unrecognized file format | Skip with warning |
| Reference file missing for target locale | Fall back to nearest variant + warn |

## Locale-specific quirks (high-leverage examples)

**German (de)**: 20-30% longer than English; preserve compound nouns (Marketingautomatisierung); use Sie (formal) by default unless brand voice says otherwise.

**Japanese (ja)**: 20% shorter than English; 敬語 (formal) for B2B; consider character-level character counting not byte counting; date format YYYY-MM-DD or 令和N年.

**French (fr)**: Espace insécable before ; ? ! :, after «»; numbers use comma decimal (3,14 not 3.14); EUR uses €.

**Simplified Chinese (cn)**: ~50% shorter than English; full-width punctuation in body, half-width in code; date YYYY-MM-DD or YYYY年MM月DD日; avoid Taiwan-specific vocabulary.

**Traditional Chinese (tw / hk)**: Same as cn but full-width punctuation throughout + Traditional characters + region-specific vocabulary.

## Cost

For typical article localization (US → UK / non-EN):
- 1× Claude Opus pass through 7 dimensions: ~$0.15
- Spell/dialect lint runs: free
- WebFetch for cultural references if needed: free
- **Total: ~$0.15 per locale**

For audit mode (no rewriting):
- Pure deterministic checks: free
- Optional LLM summary at end: ~$0.05

## See also

- `references/localization/{locale}.md` — per-market detail
- `scripts/lint/spelling_dialect_check.py` — verification linter
- `subskills/optimize/humanizer/SKILL.md` — voice + purpose system used during adaptation
