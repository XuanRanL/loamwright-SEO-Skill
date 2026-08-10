# CTA Placement — Evidence Base (v3.34, researched 2026-07-04)

This file was referenced by `subskills/optimize/cta-placement/SKILL.md` as "(TODO)" since
v5.0 without existing. It now backs the deterministic executor
`scripts/optimize/cta_injector.py` (the `cta-injection` orchestrator stage).

## What the data says

### Placement (conversion)

- **Anchor-text CTAs (a hyperlinked sentence early/mid-post) drove 47-93% of each post's
  leads; end-of-post banner CTAs averaged ~6%** (HubSpot anchor-text CTA study, Pamela
  Vaughan — dated but still the most-cited placement benchmark; single-site data).
- Mid-post contextual CTA placed "after providing relevant context": **+32% downloads**
  (Fuel Your Digital case study via protocol80, 2025; small single case).
- Personalized / intent-matched CTAs convert **+202%** vs generic (HubSpot, 330k+ CTAs).
- The old "claude-blog research" numbers this SKILL used to cite (single CTA +266%,
  centered +682%) have no verifiable source — treat as folklore; superseded by the above.

### Self-promotion vs E-E-A-T (risk)

- Google's helpful-content guidance does NOT penalize commercial intent; E-E-A-T is judged
  on main content, and a visually distinct promo block is not the MC being judged.
- The **real** danger zone is self-ranking "best-of" listicles: SaaS brands lost 30-50%
  organic visibility in the Dec 2025 core update, concentrated in "our product is #1"
  listicles (Lily Ray/Amsive via Search Engine Land). Google's reviews-system doc requires
  first-hand evidence + **disclosure when your own product is included**.
- Product-led weaving (Ahrefs methodology): only weave the product where it genuinely
  solves the searcher's problem; "if your product isn't a good fit for a point, don't
  force it."

### GEO / AI-citability

- Princeton GEO (KDD 2024, 10k queries): citations/quotations/statistics raise generative
  visibility up to ~40%; **persuasive/promo styling did NOT help**. Factual density gets
  cited; promo prose doesn't. → Keep the body neutral, put conversion in a visually
  separated block.
- LLM-referral visitors convert far higher than organic (reported 15.9% ChatGPT / 10.5%
  Perplexity vs ~1.76% organic; Ahrefs: 0.5% of traffic, 12.1% of signups). A BOFU CTA
  module on a page AI engines cite is the highest-leverage conversion slot on the site.
- No evidence a separated CTA box reduces AI citation; extractors take answer-shaped main
  content and ignore UI chrome.

## How the pipeline implements this

> **Contract note (v3.38.0):** the table below states the evidence-driven
> *design decisions*; the row that used to describe the executor as a single
> "deterministic injector, not writer prose" is stale — since v3.37 CTA
> generation is a **three-stage pipeline** (fact resolver → LLM composer →
> deterministic placement, see the row below), not a single script. The
> authoritative, currently-accurate contract (stage order, gates, config
> schema, wiring map) lives in
> `subskills/optimize/cta-placement/SKILL.md` — treat that file as the
> source of truth for HOW the system runs; this file stays the source of
> truth for WHY (the underlying research this design responds to).

| Decision | Rationale |
|---|---|
| Three-stage generation — `cta-brief-builder` (deterministic fact resolver) → `cta-writer` (LLM composer, service-aware) → `cta-injection` (deterministic placement, `cta_injector.py`) — never hand-authored writer prose | Rule 6: the original all-LLM-prose version of this feature was dead for 2 major versions; every stage is either a mandatory BASH script (cannot silently not-run) or a subagent-enforced, provenance-checked LLM stage. See `subskills/optimize/cta-placement/SKILL.md` for the full stage table, gates, and config schema. |
| `end` placement default (before Further Reading/References) | BOFU slot; AI-referral traffic converts 6-9x organic on exactly these cited pages |
| `mid` placement opt-in per project (~35% word mark, never after the first content section) | Mid/contextual carries the strongest conversion data but reads as an ad on pure-informational ecommerce content; lead-gen projects (loamwright) opt in |
| One styled block per placement, calm card design (`.xr-cta-box`) | Banner blindness is a measured failure; the card must read as part of the article |
| Copy variants rotated by task_id | No-hidden-templates rule: identical copy on every article is a cross-article footprint |
| No UTM on internal links | UTM on same-domain links resets GA4 sessions (self-referral) — the old SKILL's advice was an analytics anti-pattern |
| No numbers in CTA copy | A stat inside a component needs a `[claim:*]` marker; CTA copy is config-authored, not fact-checked — so it must not carry stats at all |
| Excluded from `visual_density_check` weights | Promo is not substance; it must never satisfy the Tier-A floor |
| Writers no longer add a prose CTA sentence to conclusions on cta-enabled projects | Two adjacent CTAs (prose + card) read as pressure; the card replaces the sentence |
| Age-restricted projects (project-echo): neutral concierge copy + 21+ line, never urgency | Compliance > conversion |
| Grief content (project-hotel): "ready when you are" register, no urgency | Never a hard CTA on a grief page (project rule) |

## Wiring map (Rule 6 receipts)

- Executor: `scripts/optimize/cta_injector.py`
- Stage: `cta-injection` in `scripts/pipeline/orchestrator.py` (mandatory; after
  visual-designer, before render-lint; `_PASS_FLAG_REQUIRED` + `_FRESHNESS_VS_DRAFT`)
- Checklist: `scripts/pipeline/pipeline_checklist.py :: MANDATORY_STAGES`
- Runner gate: `scripts/pipeline/run_pipeline.py :: _GATE_STAGES`
- Pre-publish gate: `scripts/pipeline/pre_publish_gate.py :: check_cta_module` (re-scans
  the CURRENT draft — catches repair loops stripping the block)
- Component binding: `scripts/_core/component_headings.py :: COMPONENTS["cta"]`
  (publisher class-tags `<p>` after the CTA heading as `xr-cta-box`)
- CSS: `scripts/build/article_css_generator.py` (single source; regenerate per project)
- Live verification: `scripts/wordpress/verify_post.py :: check 29`
- Config: `projects/{slug}/business-context.json :: cta` (schema:
  `schemas/business-context.schema.json`)
- Tests: `tests/test_cta_injector.py` (unit + Rule-10 seam)
