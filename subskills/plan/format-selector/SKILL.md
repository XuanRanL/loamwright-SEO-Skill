---
name: format-selector
description: Selects 1 of the evidence-backed blog formats (source of truth = schemas/angle.schema.json :: format_id enum, currently 27, mirroring templates/*.md; catalog research in references/seo/blog-formats-2026.md) based on intent × funnel stage × AI engine target × data availability × existing cluster state. Runs 5-step decision tree. Triggered BEFORE topic-angle-selector — format choice constrains angle space. Use whenever planning a new article, deciding whether to write listicle vs how-to vs pillar vs comparison, or when user says "what format should this article be".
allowed-tools: [Read, Write]
---

# Format Selector

The first thing to decide before writing: **which evidence-backed format**. The
authoritative id list is `schemas/angle.schema.json :: format_id` enum (currently 27,
one per `templates/*.md` basename — `tests/test_batch_queue_format_enum_seam.py` pins
enum ⊇ templates, so NEVER hand-count formats in prose; count drift across layers is a
Rule-11 defect that shipped 24/25/27 disagreeing claims until v3.41.4).

Formats catalog: `references/seo/blog-formats-2026.md` (3-dimensional classification × research data: Wix 2026.3, Yext 680M citations, AirOps 2026.4, Princeton GEO, LinkedIn 2026Q1).

## Inputs

Read from workspace:
- `state.brief.primary_keyword`
- `state.brief.target_surfaces[]`
- `state.brief.word_count_target`
- `state.brief.industry` + YMYL flag
- `research.json` (intent, serp_features, content_gaps)
- `projects/{slug}/existing-clusters.json` (if active project)
- `projects/{slug}/brand-config.json` (target_ai_engines priority)

## Output

`workspace/{task_id}/angle.json` (partial — `format_id` + `modifiers[]` + `template_path` + `rationale`)

The remaining angle fields (title, hook, persona, etc.) come from topic-angle-selector downstream.

⚠️ **`angle.title` MUST be 50-65 characters** and **`angle` MUST be one of the enum**
(`how-to | listicle | mistakes | cost-roi | vs | case-study | myths | trends | buyers-guide
| problem-solution | localized | persona`) — both are hard-enforced by
`schemas/angle.schema.json` via the schema-validate hook, which BLOCKS the write on a
too-short/too-long title or an off-enum `angle`. Aim for ~52-60 chars to leave headroom.

## 6-step decision tree (Step 0 added v3.4.0)

### Step 0: Local-mode short-circuit (v3.4.0, 2026-05-22)

**Runs FIRST. Short-circuits the rest of the tree when local-SEO routing is needed.**

Read `state.brief.local_mode` + `state.brief.location_anchor` (populated by `_detect_local_intent.py` during seo-blog startup).

| `local_mode` | `location_anchor.type` | Force format |
|---|---|---|
| `true` | `state` / `region` / `country` | `local-state-pillar` |
| `true` | `city` / `metro` / `neighborhood` | `local-city-page` |
| `true` | `zip` | `local-city-page` (use zip's containing city via gazetteer; if unresolvable, use `local-state-pillar` w/ state) |
| `true` | `near_me` | DON'T force a local template — "near me" queries don't have a target geography for the writer to anchor to. Fall through to Steps 1-5 normally; emit a warning in angle.json that this is a near-me query best served by a generic format + GBP optimization. |
| `false` | — | Fall through to Step 1-5 (legacy behavior) |

When Step 0 forces a local template, ALSO set in `angle.json`:
- `local_mode: true`
- `location_anchor: <copy from state.brief>`
- `local_article_pattern: <copy from business-context.json :: location.local_article_pattern>` (defaults to `service_area` for archetype A/B/C; `spatial_coverage` for D/E)

If `business-context.json :: location.local_seo_mode == "off"`, Step 0 is skipped entirely — even if local_mode=true on the brief — and Step 1-5 runs (caller wants generic flow).

### Step 1: Intent → default format

Pattern match `primary_keyword`:
| Pattern | Default format |
|---|---|
| "best X" / "top X" / "X tools" | listicle |
| "how to X" / "X step by step" / "X tutorial" | how-to-guide |
| "X vs Y" / "X or Y" / "X alternatives" | comparison |
| "X review" / "is X worth" | product-review |
| "what is X" / "X definition" / "X meaning" | definition |
| "X for beginners" / "X for {persona}" | level-guide |
| "X case study" / "how {company} achieved" | case-study |
| "X problems" / "fix X" / "X not working" | problem-solution |
| "X 2026" / "X trends" / "future of X" | news-analysis |
| "X checklist" / "X template" | checklist OR template-resource |
| (broad topic, word_count >= 4000) | pillar-page |
| (default fallback) | multi-intent-hybrid |

### Step 2: Funnel adjustment

If `target_surfaces` contains "shopping" or "transactional" intent:
- Upgrade to BOFU format: comparison / product-review / shortlist-validation
- Override step 1's choice if it was TOFU-only

### Step 3: AI engine specific weighting

If `target_surfaces` is dominated by ONE AI engine:
| Dominant target | Preferred format adjustment |
|---|---|
| chatgpt | listicle (Wix 40.86% on commercial) / shortlist-validation (AirOps +26.9%) / encyclopedic |
| perplexity | case-study (data-rich) / data-research / definition (entity-rich) |
| claude | product-review (E-E-A-T) / opinion / personal-story |
| gemini / google-aio | how-to-guide / news-analysis / faq-knowledge |

### Step 4: Data availability gate

Check `state.brief` and `projects/{slug}/business-context.json`:
- `original_data_available: true` → strongly prefer `data-research`
- `case_study_available: true` → strongly prefer `case-study`
- Neither → default from Step 1

### Step 5: Existing cluster state

Read `projects/{slug}/existing-clusters.json`:
| State | Override |
|---|---|
| No pillar for this topic, multiple spokes exist | Force `pillar-page` |
| Existing pillar covers this topic | Force a spoke format (listicle / how-to / comparison etc.) |
| Otherwise | Keep Step 1-4 result |

## Modifiers (always applied)

Append to `modifiers[]`:
- Always: `tldr-first` (per Rebeccavandenberg 540-word grounding)
- If any AI engine in `target_surfaces`: `citation-capsules-per-h2` (Princeton +28-41%)
- If `word_count_target >= 3000`: `mandatory-toc`, `info-gain-prose`
- Always: `info-gain-prose` (≥2 distinct plain-prose information-gain signals per article — bracket markers are RETIRED and forbidden)
- If `industry in [health, finance, legal]` OR `ymyl_flag == true`: `strong-eeat-signals`
- (v3.35: do NOT emit `speakable-schema` / `voice-search-friendly` — the
  voice-search-optimizer is retired and no stage consumes those modifiers; they
  remain in angle.schema.json only for legacy-outline tolerance)

## Output schema

```json
{
  "format_id": "listicle",
  "modifiers": ["tldr-first", "citation-capsules-per-h2", "mandatory-toc", "info-gain-prose"],
  "template_path": "templates/listicle.md",
  "rationale": {
    "step_1_intent_match": "Keyword 'best fishing rods 2026' = commercial investigation; default listicle",
    "step_2_funnel_adjustment": "target_surfaces contains google-aio + chatgpt; no shopping upgrade needed",
    "step_3_data_availability": "no original data; using SERP-based competitor analysis",
    "step_4_cluster_state": "no existing pillar for 'fishing rods'; this could become one but word_count_target=6000 fits listicle scope",
    "step_5_modifiers_applied": "tldr-first + citation-capsules + mandatory-toc",
    "citation_rate_expected": 0.41,
    "research_source": "Wix 2026.3 — listicle = 40.86% AI citation rate on commercial queries"
  }
}
```

## Examples

### Example 1: "best fishing rods 2026"
- Step 1: "best X" → listicle
- Step 2: no shopping → keep
- Step 3: target_surfaces=[chatgpt, google-aio] → listicle reinforced (Wix data)
- Step 4: no data → keep
- Step 5: no cluster → keep
- **format_id: listicle**, modifiers: [tldr-first, citation-capsules-per-h2, mandatory-toc, info-gain-prose]

### Example 2: "what is intermittent fasting"
- Step 1: "what is X" → definition
- Step 2: no shopping
- Step 3: if target includes chatgpt → upgrade to encyclopedic (chatgpt loves Wikipedia-style)
- Step 4: ymyl=true (health) → add strong-eeat
- **format_id: encyclopedic** OR definition, modifiers: [tldr-first, citation-capsules, strong-eeat-signals, info-gain]

### Example 3: "shopify vs wordpress comparison 2026"
- Step 1: "X vs Y" → comparison
- Step 2: → comparison (BOFU)
- Step 3: chatgpt + perplexity → comparison
- Step 4: → comparison
- Step 5: → comparison
- **format_id: comparison**, modifiers: [tldr-first, citation-capsules, info-gain, mandatory-toc]

## Handoff

`recommended_next_skill`: `topic-angle-selector` (now has format constraint to work within)

## Entry-point-forced formats (never auto-selected)

Some formats are intentionally excluded from Steps 0-5 above. They can ONLY be
set by a dedicated entry-point skill that pre-writes `angle.json` before this
skill runs. When `angle.json` already contains `format_id`, this skill MUST skip
all steps and pass through the existing value unchanged.

| Format | Forced by | Reason |
|---|---|---|
| `weekly-digest` | `/weekly` entry skill | Requires a fixed issue date + cadence context that keyword-pattern matching cannot provide. The `/weekly` skill pre-writes `angle.json` with `format_id: "weekly-digest"` and `slug_draft: "{industry}-weekly-{YYYY-MM-DD}"`. **`weekly-digest` is NEVER auto-selected by keyword pattern — it is forced only by the `/weekly` entry skill, which pre-writes `angle.json`.** |

## See also

- `references/seo/blog-formats-2026.md` (the 25 formats catalog with research data)
- `references/seo/angle-catalog.md` (12 angles within formats)
- `subskills/build/topic-angle-selector/SKILL.md` (next stage)
- `templates/*.md` (25 outline skeletons)
