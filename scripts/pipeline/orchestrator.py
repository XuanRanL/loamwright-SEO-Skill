#!/usr/bin/env python3
"""Pipeline orchestrator — deterministic stage sequencer.

Replaces LLM-as-orchestrator with a state machine that tracks which
pipeline stages have produced their required artifacts. The LLM calls
this script between stages to learn what to do next; the orchestrator
refuses to advance until mandatory outputs exist.

Usage:
    python -m scripts.pipeline.orchestrator --workspace {task_id} --action next [--json]
    python -m scripts.pipeline.orchestrator --workspace {task_id} --action verify --stage {name} [--json]
    python -m scripts.pipeline.orchestrator --workspace {task_id} --action status [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from scripts._core import file_bus  # tolerant_json_load: self-heals subagent JSON tool-tag leaks
from scripts._core import file_lock  # is_locked: real OS-lock liveness, not sidecar existence
from scripts._core.provenance import PROVENANCE_REQUIRED  # single _generated_by source (v3.41.3)
from scripts._core.review_target import review_target  # ONE reviewer-target resolver (2026-08-17)
from scripts.pipeline import fc_verdict  # ONE verdict classifier for all gates (2026-08-02)

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
WS_ROOT = PLUGIN_ROOT / "memory" / "workspace"


@dataclass
class Stage:
    name: str
    phase: str
    executor: str
    required_inputs: list[str]
    expected_outputs: list[str]
    is_mandatory: bool = True
    is_conditional: bool = False
    condition_field: str = ""
    condition_value: object = True
    description: str = ""
    subagent_type: str = ""
    dispatch_prompt: str = ""
    # ── Execution-evidence enforcement (v3.12, 2026-06-02) ──────────────
    # Root cause of the 2026-06-02 "geo step silently skipped" incident:
    # stages with expected_outputs=[] were auto-marked "completed" by
    # verify_stage with NO proof the work ran, so an LLM orchestrator under
    # context/budget pressure could record them done without dispatching the
    # subagent. The cure: every stage that does real work must surface a
    # UNIQUE, provenance-stamped artifact (evidence_artifact) OR prove its
    # work landed in a shared artifact via non-empty evidence_keys. verify
    # no longer trusts the honour system — it checks evidence. A stage that
    # genuinely should not run must be EXPLICITLY skipped (--action skip
    # --reason ...), which records status="skipped" (not "completed") so the
    # audit trail never conflates "ran" with "was quietly dropped".
    evidence_artifact: str = ""          # unique file that proves THIS stage ran
    evidence_keys: list[str] = field(default_factory=list)  # (file, key) pairs proving work landed in a shared artifact
    evidence_in: str = ""                # shared artifact that evidence_keys live in
    # Richness floor (v3.13): a stage whose work folds into a shared artifact
    # (serp-analysis / competitor-analysis fold into research.json) is only
    # "done" if its signature key holds at least this many items — a 1-item stub
    # must NOT count as a real SERP/competitor analysis. Default 1 = "non-empty".
    evidence_min_count: int = 1


STAGES: list[Stage] = [
    # ── Phase Research ──────────────────────────────────────
    Stage("research", "research", "LLM",
          ["state.json"], ["research.json"],
          description="Run Tavily searches for keyword data, SERP features, PAA, and competitor landscape",
          subagent_type="xuanran-seo-blog-writer:researcher",
          dispatch_prompt="Run full Phase Research for keyword '{primary_keyword}' on project {project_slug}. Use the Python scripts (they add key-rotation + retry + cost-ledger + cache; MCP tools are fallback only). MANDATORY: (1) Start with `python -m scripts.fetch.tavily_research \"...{primary_keyword}...\" --model pro` for comprehensive deep research → save to research/deep-research.json. (2) Then run 4-5 `python -m scripts.fetch.tavily_search \"...\" --depth advanced` calls (NEVER basic). (3) Use `python -m scripts.fetch.tavily_extract` for top competitor pages. (4) Run `python -m scripts.fetch.crossref_lookup` for academic sources. (5) SERP GROUND TRUTH (non-negotiable — Tavily inference under-detects features; the 07-01 batch missed a live AI Overview): run `python -m scripts.fetch.serpapi_query --engine google --q \"{primary_keyword}\" --gl us --hl en --json` and derive `serp_features[]` + `_serp_features_detail{{}}` + `ai_overview_present` from its STRUCTURED response (ads/answer_box/related_questions/inline_videos/ai_overview/local_results/inline_images/discussions_and_forums keys), never from memory. Consolidate ALL findings into workspace research.json using the CANONICAL schema keys (primary_keyword / intent as an ENUM STRING / competitor_titles / paa / semantic_clusters / content_gaps) and the CANONICAL serp_features vocabulary — map raw SerpApi keys before writing: ads→paid_ads, related_questions→paa_box, local_results+local_map→local_pack, inline_videos→video_carousel, answer_box→featured_snippet, sitelinks→site_links (full map: scripts/validate/research_contract.py::SERPAPI_TO_CANONICAL). FINAL CONSOLIDATION STEP (mandatory, v3.36.0): run `python -m scripts.validate.research_contract --workspace {task_id} --fix --json` and confirm passed:true — the runner hard-rejects a drifted shape (it will also self-heal known variants once, but an intentional canonical write always beats the safety net). The deep-research pro call is NON-NEGOTIABLE. If a script exhausts all keys and raises, fall back to the matching mcp__tavily__* tool for that one call."),
    Stage("serp-analysis", "research", "LLM",
          ["state.json", "research.json"], ["research.json"],
          is_mandatory=False,
          evidence_in="research.json", evidence_keys=["serp_features"], evidence_min_count=3,
          description="Analyze top-10 SERP: featured snippets, AI overviews, PAA, video/image packs. Update research.json with serp_features[] (>=3 features = real analysis, not a stub)",
          subagent_type="xuanran-seo-blog-writer:researcher",
          dispatch_prompt="Analyze top-10 Google SERP for '{primary_keyword}'. Identify: content types ranking, word counts, H2 structures, featured snippet formats, AI Overview presence, PAA questions. GROUND TRUTH FIRST: populate `_serp_features_detail` FROM a `python -m scripts.fetch.serpapi_query --engine google --q \"{primary_keyword}\" --gl us --hl en --json` structured response (never from Tavily inference or memory — the 07-01 batch under-detected 2 of 5 live features incl. an AI Overview that way), THEN update research.json serp_features[] mirroring every true flag in `_serp_features_detail`, using ONLY the canonical schema vocabulary (schemas/research.schema.json enum, extended v3.36.0): ai_overview, paa_box, featured_snippet, local_pack, paid_ads, related_searches, video_carousel, image_pack, inline_images, shopping_results, site_links, knowledge_graph, top_stories, discussions_and_forums, directory_results, reddit_top_results. Raw SerpApi keys (ads/related_questions/local_results/local_map/inline_videos/answer_box/sitelinks) are NOT valid — map them (scripts/validate/research_contract.py::SERPAPI_TO_CANONICAL), or run `python -m scripts.validate.research_contract --workspace {task_id} --fix --json` which maps them for you. This stage auto-completes once serp_features has >=3 entries; under-populating it (e.g. only 2 of 5 observed features) forces a needless re-dispatch. If the STRUCTURED response genuinely contains fewer than 3 present features (some SERPs really do — 2026-07-06 'local seo ranking factors' had only ai_overview + related_searches), do NOT invent a third: the sanctioned path is `--action skip --stage serp-analysis --reason \"<ground-truth feature list>\"`."),
    Stage("competitor-analysis", "research", "LLM",
          ["state.json", "research.json"], ["research.json"],
          is_mandatory=False,
          evidence_in="research.json", evidence_keys=["competitor_titles", "competitors"], evidence_min_count=3,
          description="Deep-extract top-5 competitor pages: word count, heading structure, content gaps (>=3 competitors = real analysis, not a stub)",
          subagent_type="xuanran-seo-blog-writer:researcher",
          dispatch_prompt="Fetch and analyze top-5 competitor articles for '{primary_keyword}'. Extract: H2/H3 outlines, word counts, products mentioned, strengths/weaknesses, content gaps. Update research.json with a non-empty competitors[] (or competitor_titles[]) — that key is the orchestrator's proof this ran; satisfied when the main research pass already produced it."),

    # ── Phase Plan ──────────────────────────────────────────
    Stage("format-selector", "plan", "LLM",
          ["state.json", "research.json"], ["angle.json"],
          description="Choose format from the format templates + differentiated angle, hook, persona. Read subskills/plan/format-selector/SKILL.md and templates/*.md. Write angle.json.",
          dispatch_prompt="Read research.json + subskills/plan/format-selector/SKILL.md + templates/*.md. Select format_id from the format templates (authoritative id list: schemas/angle.schema.json :: format_id enum — never a hand-counted subset) based on SERP format distribution. Write angle.json with format_id, thesis, differentiator, anti_homogenization, title, slug, h1_title. CONSTRAINT: angle.title MUST be 50-65 characters (schemas/angle.schema.json) and `angle` MUST be one of: how-to|listicle|mistakes|cost-roi|vs|case-study|myths|trends|buyers-guide|problem-solution|localized|persona."),
    Stage("outline-architect", "plan", "LLM",
          ["state.json", "research.json", "angle.json"], ["outline.json"],
          description="Build full H2/H3 outline with word targets per section. Read subskills/build/outline-architect/SKILL.md. Write outline.json.",
          dispatch_prompt="Read angle.json + research.json + projects/{project_slug}/business-context.json :: mandatory_sections + subskills/build/outline-architect/SKILL.md. Build outline.json with sections[] (each has index, h2, anchor_id, word_target, instructions, claim_markers, image_slots), image_slots[], tables_required[]. MUST include every H2 listed in THIS project's business-context.json :: mandatory_sections array (whatever count it declares — do NOT assume a fixed number). If that array is absent, use the format template's default required sections. Do not pause for outline approval (user prefers continuous execution)."),
    Stage("image-prompt-designer", "plan", "LLM",
          ["outline.json"], ["image-prompts.json"],
          description="Design 4 image prompts with art direction prefix",
          subagent_type="xuanran-seo-blog-writer:image-prompt-designer",
          dispatch_prompt="Read outline.json image_slots. FIRST read projects/{project_slug}/brand-guideline.yaml and treat it as AUTHORITATIVE for image style: if it sets visual_style use it; if it provides art_direction_prefix use that text verbatim as the shared prefix (do not recompile a generic one); honor featured_image (render the cover text overlay when text_overlay is true), packaging_branding (CONFIG-AWARE: if forbid_third_party_brands is FALSE — e.g. project-echo, whose subject IS the brand — the REAL subject brand is shown authentically and is NOT relabeled to label_text, only a competing STORE/retailer logo stays banned; if TRUE/default, labels read label_text and never show a third-party brand), realism, and negative_prompt_baseline. If business-context.json :: image_sourcing_policy.source == 'real_product_photos' (e.g. project-echo), product/brand photo slots are NOT AI-generated — emit per photo slot {slot_id, kind:'photo', brand, product_noun, scene, aspect_ratio, people} instead of a fabricated full_prompt (the real-photo executor scripts.openai.real_brand_image_pipeline sources a real product photo + re-scenes it, pack preserved). PER-SLOT product_noun IS MANDATORY on real-photo projects (v3.41.2): the executor sources with the SLOT's noun and drops the project search_terms whenever the slot noun differs — the project noun describes the project's own category, and on an OFF-CORE article it sourced a competitor-branded wrong-subject photo (Farmry on a Senix cover, 3 articles on 2026-07-18). A slot whose correct subject is GENERIC/UNBRANDED (a robotic mower, a PV array, a landmark) sets brand:null — the executor now generates it via the plain-scene AI fallback (openai_image_pipeline provider chain, slot fields only, no art_direction_prefix) instead of skipping; still give such slots product_noun + scene + negative_prompt so the fallback prompt is complete. Do NOT mirror the website's dark UI theme into the imagery. Then design 4 image prompts. Write image-prompts.json. CRITICAL: the slot IDENTIFIER key is slot_id (short form matching outline, e.g. 'cover') — never filename_seed as the identifier — but EVERY slot INCLUDING the photo cover MUST ALSO carry filename_seed (SEO kebab-case media-filename stem; the 2026-07-06 near-me cover shipped as '{{task_id}}_cover.png' because the old wording here read as 'don't emit filename_seed' — the pipeline now falls back to the article slug, but an intentional stem always beats a fallback). quality must be 'low', 'medium', or 'high' (NOT 'hd'). PHOTO RESOLUTION: set aspect_ratio per photo slot (cover='16:9'; section photos '16:9' or '4:3'; portraits '3:4'/'9:16') and do NOT hardcode a small 'size' — the pipeline maps aspect_ratio to a 4K resolution (16:9->3840x2160, 4:3->3264x2448, 1:1->2880x2880, 3:4->2448x3264) and floors any sub-4K size up to its 4K tier, so a legacy 1024/1536 size no longer downgrades the image (2026-06-15 4K fix). CHART SLOTS (mandatory): For EACH slot, set kind='photo' or kind='chart'. A slot is a CHART when its outline kind=='chart' OR its purpose/description is data/diagram-bearing (chart, comparison, coverage, checklist, table, matrix, spectrum, PPFD/DLI/CFM/yield/efficacy numbers). The COVER/featured slot is ALWAYS kind='photo'. For kind=='chart' slots, do NOT write a photographic prompt (AI image models garble axis/value text) — instead emit {slot_id, kind:'chart', filename_seed, alt_text_seed, chart_spec:{...}} where chart_spec is populated with REAL numbers pulled from research.json (never invented): type='vbar' (single-series magnitudes, e.g. % uplift by item) | 'grouped_vbar' (TWO+ series per category, e.g. density AND moisture per material — use this instead of cramming two metrics into one vbar) | 'rangebar' (min-max bands, e.g. PPFD/DLI by stage) | 'table' (multi-column comparison/verdict matrix). vbar: {type,title,subtitle,unit,plus(bool),bars:[{label,value,value_label?,color?}],source}. grouped_vbar: {type,title,subtitle,unit,plus(bool),series:[name1,name2],groups:[{label,values:[v1,v2]}],source}. rangebar: {type,title,subtitle,x_max,x_unit,x_scale('linear'|'log', optional — set 'linear' to stop auto-log on wide ranges),rows:[{label,min,max,range_label,annot}],source}. table: {type,title,subtitle,columns:[...],col_frac:[...],status_col(int idx or -1),rows:[[...]],source}. TABLE TEXT BUDGET (v3.38.3): keep every table CELL <= ~90 chars and every column HEADER to 1-3 short words (long URL-ish headers go in the subtitle) — the renderer now auto-fits (shrinks font / expands rows / ellipsizes as last resort), but a spec written inside the budget renders at full size with zero clamping; the 2026-07-09 batch lost 2 QA regen rounds to 150-200 char cells. These render locally to real labeled PNGs; numbers MUST match the article (they are fact-checkable). RULE 8 — chart sources: chart_spec.source is a CITATION SURFACE (it renders into the PNG footer); it must be a neutral or citable-authority attribution, NEVER a competing agency/vendor brand or domain (the 2026-07-06 batch leaked 'Dashclicks'/'Hustle Marketers' into two chart footers). render_data_charts now auto-neutralizes tainted sources to 'Industry benchmark synthesis' and records sources_sanitized[] — do not rely on the backstop. For kind=='photo' slots emit the usual photographic full_prompt + negative_prompt."),
    Stage("chart-render", "plan",
          "BASH:python -m scripts.build.render_data_charts --task-id {task_id} --project-slug {project_slug} --json",
          ["image-prompts.json"], ["chart-render-result.json"],
          description="Render data/chart image slots (kind=='chart') as REAL labeled charts (titles, axes, units, value labels) via data_chart_png.py, merged into images.json. Closes the 'textless dull chart' gap. Runs BEFORE the photo fork; photos still go to gpt-image."),
    Stage("image-pipeline-fork", "plan",
          "BACKGROUND:python -m scripts.openai.image_fork --requests-file {ws}/image-prompts.json --workspace {ws} --task-id {task_id} --project-slug {project_slug} --mode realtime",
          ["image-prompts.json"], [],
          description="Launch the image fork (Fork B) in background. Routes by project policy: real-photo projects (project-echo) source+re-scene REAL brand photos via real_brand_image_pipeline — per-slot product_noun overrides the project noun, and brand:null slots generate via the plain-scene AI fallback instead of skipping (v3.41.2); all other projects delegate UNCHANGED to openai_image_pipeline (PHOTO slots only; charts rendered by chart-render). Merges into images.json."),

    # ── Phase Build ─────────────────────────────────────────
    Stage("section-drafter", "build", "LLM",
          ["state.json", "research.json", "outline.json"], ["sections/"],
          description="Dispatch N parallel writer subagents (one per H2 section) per subskills/build/section-drafter/SKILL.md. MUST use writer subagents, NOT write sections yourself.",
          subagent_type="xuanran-seo-blog-writer:writer",
          dispatch_prompt="For EACH section in outline.json EXCEPT the References section, spawn a writer subagent with section_spec, research context, voice_pair, image_slot_info. Each writer writes sections/NN_slug.md where NN = that section's outline `index` value, ZERO-BASED and zero-padded to 2 digits (outline index 0 -> 00_..., index 3 -> 03_...) — section_completeness_check diffs the numeric prefixes against outline.sections[].index verbatim, so a 1-based prefix reads as 'section 0 missing' and fails the gate (2026-07-19). Writers emit PLAIN `## H2` headings — NEVER `## H2 {{#anchor}}`; the section_spec's anchor_id is assembly metadata, and assembly injects canonical anchors from heading text. References is fact-checker/finalize-owned: do NOT dispatch a writer for it and do NOT hand-create a placeholder file — assemble.py auto-appends the '## References' stub and section_completeness_check exempts that outline entry (2026-07-07 root cure; before that every batch operator had to rediscover the hand-made placeholder). After ALL writers finish, verify all NON-References section files exist."),
    Stage("section-completeness-check", "build",
          "BASH:python -m scripts.lint.section_completeness_check --workspace {task_id} --json",
          ["outline.json", "sections/"], ["section-completeness.json"],
          description="Verify all outline sections were written (catches writer-subagent silent dropout)"),
    Stage("assembly", "build",
          "BASH:python -m scripts.build.assemble --task-id {task_id} --json",
          ["sections/"], ["draft.md"],
          description="Concatenate sections into draft.md (claim markers stay as-is; citation-inject replaces them after fact-check)"),
    Stage("fact-check-and-citation", "build", "LLM",
          ["draft.md", "research.json"], ["citations.json", "fact-check.json"],
          description="Dispatch fact-checker subagent to verify all claims, check citation URLs, build APA-7 references. MUST use the subagent — do NOT write fact-check.json yourself.",
          subagent_type="xuanran-seo-blog-writer:fact-checker",
          dispatch_prompt="Read draft.md. Verify every factual claim against cited sources via web search. Check DOI resolution. Build citations.json with claim_markers_resolved[] — entries are BARE marker slugs WITHOUT the 'claim:' prefix (e.g. 'c4_matrix_values', NOT 'claim:c4_matrix_values'); the prefixed form silently breaks citation-inject. URL RESOLUTION RECORDING (v3.38.3): for a ref whose DOI/URL is REAL but bot-walled (HEAD 403 / anti-bot block: Taylor & Francis, MDPI, ASTM class), verify the identifier via the Crossref API or a browser UA, then record url_verified: true AND resolved_status: \"bot-403\" (the STRING, never a bare int 403 — an int outside 200-399 without url_verified:true reads as a broken ref and fires the C01 fabricated-citation veto; the 2026-07-09 batch lost a core-EEAT gate to exactly this encoding). A ref you could NOT verify anywhere gets url_verified: false. CHART SYNC (2026-07-01): if a number you correct in the draft ALSO appears in image-prompts.json :: chart_spec (bars[].value, groups[].values, rows, value_label, subtitle, title), update that chart_spec to the verified value in the same pass and record the slot in fact-check.json :: charts_updated[] — the chart-rerender stage right after you re-renders the PNGs, so a stale spec ships a chart contradicting your corrected prose. Do NOT hand-build the References section or any article signature (raw-HTML signatures get entity-escaped at render): the References placeholder is rebuilt from your verified citations.json by the finalize-references-signature stage that runs right after you. STYLE RED LINE for every sentence you ADD or REWRITE in the draft (2026-07-07): ZERO em-dashes (U+2014) — use a comma, period, or parens; render_lint L12 hard-vetoes them, and a correction you propagate across sections multiplies the leak. Write fact-check.json with verdict — EXACTLY one of CLEAN | CLEAN_WITH_NOTES | FIX_REQUIRED | BLOCK_PUBLISH (any other string, e.g. an invented 'issues_fixed', FAILS CLOSED at both pipeline gates; use CLEAN_WITH_NOTES when you fixed issues in place). Must include _generated_by: 'fact-checker-subagent'."),
    Stage("citation-inject", "build",
          "BASH:python -m scripts.build.citation_inject {task_id} --json",
          ["draft.md", "citations.json"], ["citation-inject-result.json"],
          description="Replace [claim:cN] markers with (Author, Year) inline citations from citations.json"),
    Stage("finalize-references-signature", "build",
          "BASH:python -m scripts.build.finalize_refs_signature --task-id {task_id} --project-slug {project_slug} --json",
          ["draft.md", "citations.json"], ["finalize-result.json"],
          description="Rebuild the draft's References block from the VERIFIED citations.json (assemble built it pre-fact-check, so it can carry hallucinated authors the fact-checker only fixed in citations.json) AND auto-generate the article signature if missing (writers are barred from writing it; publisher only tags an existing one). Codifies the 2026-06-03 manual finalizer so neither needs hand-patching."),
    Stage("chart-rerender", "build",
          "BASH:python -m scripts.build.render_data_charts --task-id {task_id} --project-slug {project_slug} --result-file chart-rerender-result.json --json",
          ["image-prompts.json", "fact-check.json"], ["chart-rerender-result.json"],
          description="Re-render chart slots AFTER fact-check so corrected chart_spec numbers "
                      "reach the PNGs (2026-07-01: the fact-checker corrected Census figures in "
                      "the draft while the plan-phase chart kept the stale values — needed a "
                      "manual patch). Idempotent no-op-cost overwrite when specs are unchanged; "
                      "pure local Pillow, no API spend. Writes a DISTINCT result artifact "
                      "(chart-rerender-result.json) because reusing chart-render-result.json "
                      "would be instantly auto-satisfied by the plan-phase run and never execute."),
    Stage("citation-capsule-builder", "build", "LLM",
          ["draft.md", "citations.json"], [],
          is_mandatory=False,
          evidence_artifact="citation-capsule-result.json",
          description="Add 40-60 word AI-quotable citation capsules per H2. Princeton: +28-41% AI citation rate. Also the home of featured-snippet optimization since v3.35 (FS retired as a separate subskill: Ahrefs 2025 shows FS 83% replaced by AIO and both extract the same 40-60w answer shape). Read subskills/build/citation-capsule-builder/SKILL.md.",
          dispatch_prompt="Read draft.md + citations.json + outline.json + subskills/build/citation-capsule-builder/SKILL.md. For each content H2, insert one 40-60 word self-contained paragraph that AI engines can extract verbatim. Must be: specific claim + named source + quantitative data. ZERO em-dashes (U+2014) in any capsule you write (render_lint L12 hard-vetoes them), and every NUMBER in a capsule must be copied verbatim from the section it summarizes — never re-derived or re-rounded (cross-section numeric drift is reviewer-bounced repair work). PRIORITIZE the section(s) outline.json marks is_featured_snippet_target:true — give those the most direct answer-first capsule (declarative first sentence, a specific number, no hedging): featured snippets and AI Overviews select the same extractive shape, so this capsule serves both (this absorbed the retired featured-snippet-optimizer subskill, v3.35). Validate after: python -m scripts.lint.citation_capsule_lint {ws}/draft.md --json --out {ws}/citation-capsule-result.json . MANDATORY EVIDENCE: citation-capsule-result.json must exist (the lint --out writes it: h2s_with_capsule, coverage_pct, passed). The orchestrator will NOT mark this stage complete until it exists. If capsule coverage is already adequate and you choose not to add more, run `--action skip --stage citation-capsule-builder --reason ...` — do not fabricate completion."),

    # ── Phase Optimize ──────────────────────────────────────
    Stage("humanizer", "optimize", "LLM",
          ["draft.md"], ["humanizer-report.json"],
          description="Dispatch humanizer subagent to scan 43 AI-tell patterns, calibrate voice, target ai_slop_score < 20. MUST use the subagent — do NOT write humanizer-report.json yourself.",
          subagent_type="xuanran-seo-blog-writer:humanizer",
          dispatch_prompt="Run humanizer on draft.md. Mode: detect then rewrite if score >= 20. Target: ai_slop_score < 20. NEVER edit an injected CTA module block (an H3 like '### Your next step' / '### Where we can help' / '### Work with us' / '### Ready when you are' / '### Talk to the factory' plus its single paragraph) — its copy is config-authored (business-context.cta) and machine-verified; rewording or deleting it fails the cta_module pre-publish gate. Write humanizer-report.json. Must include _generated_by: 'humanizer-subagent'."),
    Stage("meta-builder", "optimize", "LLM",
          ["draft.md", "outline.json", "state.json"], ["meta.json"],
          description="Generate SEO meta: seo_title (<=60 chars), meta_description (<=160), OG/Twitter, tags, categories. Write FLAT meta.json per workspace schema. Read subskills/optimize/meta-builder/SKILL.md.",
          dispatch_prompt="Read draft.md + outline.json + state.json + business-context + subskills/optimize/meta-builder/SKILL.md. Write FLAT meta.json (NOT nested). Required keys: title, slug, excerpt, seo_title (<=60), meta_description (<=160), focus_keyphrase, canonical_url, robots=['index'], categories[], tags[], og_title, og_description, twitter_card_type, twitter_title, twitter_description. See SKILL.md canonical meta.json schema."),
    # NOTE (2026-07-14): do NOT pass --max-categories here. The selector's documented
    # precedence is `explicit arg > business-context.json :: category_policy.max_per_article
    # > default 3`, so a hardcoded flag on this line SILENTLY OVERRIDES every project's
    # policy and makes them all behave like the one project that wanted 4 (project-charlie).
    # It did exactly that: project-bravo and project-mike both declare max_per_article=1 and
    # were still getting 4 categories per post, which is the single-bucket / category-dup
    # bug family this policy exists to prevent. Omitting the flag lets each project's own
    # policy decide (project-charlie=4, project-bravo/project-mike=1, unset=3).
    Stage("category-selector", "optimize",
          "BASH:python -m scripts.build.category_selector --task-id {task_id} --project-slug {project_slug}",
          ["draft.md", "meta.json"], ["meta.json"],
          evidence_artifact="category-selection-result.json",
          description="Signal-based multi-category selection from categories-config.json. "
                      "PRESERVE-META (v3.41.2): the meta-builder's live-resolvable categories "
                      "occupy cap slots FIRST; scored candidates fill the remainder — the scorer "
                      "sees body keywords only and cannot see format/intent, and replace-not-merge "
                      "dropped the most apt category on 4 real articles (project-foxtrot 07-14, all 3 "
                      "project-lima 07-18). NOTE: this stage mutates meta.json IN PLACE, so meta.json "
                      "existence is NOT proof it ran (meta-builder already created it). It declares "
                      "a distinct evidence_artifact so _stage_complete can't false-positive and "
                      "silently skip it — the 2026-06-03 'every article -> category 144' root cause."),
    Stage("schema-generator", "optimize", "LLM",
          ["draft.md", "outline.json", "meta.json"], ["schema.json"],
          description="Generate FAQPage/ItemList JSON-LD for body injection (>=2 body blocks REQUIRED — see dispatch_prompt). Read subskills/optimize/schema-generator/SKILL.md. Forbidden-types clause is computed per-project from business-context.wordpress.seo_plugin_schema_provided at dispatch time (see _schema_forbidden_types_text).",
          subagent_type="xuanran-seo-blog-writer:schema-generator",
          dispatch_prompt="Read memory/workspace/{task_id}/draft.md FAQ section + outline.json + subskills/optimize/schema-generator/SKILL.md, and follow agents/schema-generator.md. Build FAQPage questions VERBATIM from the draft's FAQ section (never fabricate) and write memory/workspace/{task_id}/schema.json with blocks[] array (you MUST actually write the file — a prose-only summary with no schema.json on disk is a hard failure). Each block: {block_name, ld_json}. Allowed body types: FAQPage, ItemList. {schema_forbidden_types} (the geo-auditor T09 veto scan + CITE gate hard-reject deprecated types as a primary @type — Google deprecated HowTo rich results Sept 2023; emitting one here would fail this same pipeline's later quality gate). MANDATORY (2026-07-05, found via a real batch failure): emit AT LEAST 2 body blocks. FAQPage is near-mandatory (every article has an FAQ section per mandatory_sections). For the 2nd block, use ItemList over any compared/ranked/tabular set of >=3 named entities in the article (outline-architect guarantees >=2 tables per article, so a legitimate ItemList candidate always exists — e.g. platforms compared, criteria in a scorecard, steps in a checklist). Do NOT ship 1 body block based on a judgment call that 'nothing else fits' — for a draft post verify_post check 17 cannot count head-level schema (head isn't fetchable pre-publish), so the >=2 minimum falls entirely on body blocks and 1 block WILL fail live verification, forcing a late manual patch. If you genuinely cannot construct a second block, treat that as a signal to look harder at the comparison/decision tables already in the draft, not to skip it."),
    Stage("internal-linker", "optimize", "LLM",
          ["draft.md"], [],
          is_mandatory=False,
          evidence_artifact="internal-link-report.json",
          description="Inject 10-15 internal links for pillar articles. Uses cross_article_linker.py for portfolio-scope linking",
          subagent_type="xuanran-seo-blog-writer:linker",
          dispatch_prompt="Read draft.md + the project's LIVE published-post inventory (GET /wp-json/wp/v2/posts?per_page=100&status=publish&_fields=slug,link,title with the project CF bypass header) — the local projects/{project_slug}/articles/ folder is a partial snapshot, so verify every target slug resolves live before linking. Inject 10-15 internal links with natural, varied anchor text. ZERO em-dashes (U+2014) in any text you add or rephrase — the humanizer ran before you and will not run again; render_lint L12 hard-vetoes them. MANDATORY EVIDENCE: write internal-link-report.json with _generated_by:'linker-subagent', links_added (int), anchors[] (each {anchor, target_slug, verified_live}). The orchestrator will NOT mark this stage complete until internal-link-report.json exists. If linking is genuinely not wanted, the caller must run `--action skip --stage internal-linker --reason ...`."),
    Stage("geo-content-optimizer", "optimize", "LLM",
          ["draft.md", "research.json"], [],
          is_mandatory=False,
          evidence_artifact="geo-audit.json",
          description="Apply 6 GEO techniques: entity definitions, citation capsules, authority signals, Q&A, fact density, FAQPage schema",
          subagent_type="xuanran-seo-blog-writer:geo-auditor",
          dispatch_prompt="Run CITE 40-item + CORE-EEAT 80-item scoring on draft.md. Apply GEO optimizations: entity definitions, citation capsules, authority signals. FORBIDDEN (2026-07-01): inserting `[ORIGINAL DATA]` / `[UNIQUE INSIGHT]` / `[PERSONAL EXPERIENCE]` or ANY bracketed scaffold marker into the body — they are stripped at publish and lint as L6 leaks, so they can never reach a reader; express information-gain as plain prose (\"we measured/tested N ...\") which the CITE C10 scorer now credits directly. `edits_applied[].type='information_gain_marker'` is a forbidden edit type. Also FORBIDDEN: renaming any H2 heading, touching schema.json/JSON-LD, fabricating first-person experience or client results, editing/removing an injected CTA module block ('### Your next step'-class H3 + its paragraph — config-authored, machine-verified), and adding FAQ questions that are not VERBATIM from research.json paa[] (the paa-alignment-check gate runs after you: every off-PAA question raises faq_count without raising matches and can flip the gate to GATE_FAILED — prefer enriching existing answers). STYLE RED LINES for every character you ADD (2026-07-07 — the humanizer ran BEFORE you and will not run again): ZERO em-dashes (U+2014) — render_lint L12 hard-vetoes them; use a comma, period, or parens. NUMERIC ALIGNMENT: when an edit adds, sharpens, or changes ANY number (sample size, count, percentage, price — e.g. adding 'N = 8 sampled pages' precision), search the WHOLE draft for every other statement of the same fact and update all of them in the same pass, recording the alignment in edits_applied[] — a one-location precision edit created a top-8-vs-top-10 cross-section drift in the 2026-07-07 batch that the reviewer then bounced back as repair work. MANDATORY EVIDENCE: write geo-audit.json with _generated_by:'geo-auditor-subagent', cite_score, core_eeat_score, vetoes_triggered, cap_decision, edits_applied[]. The orchestrator will NOT mark this stage complete until geo-audit.json exists with that provenance — there is no honour-system pass. If you deliberately choose to skip GEO, the orchestrator caller must run `--action skip --stage geo-content-optimizer --reason ...` instead of fabricating completion."),
    Stage("visual-designer", "optimize", "LLM",
          ["draft.md"], [],
          is_mandatory=False,
          evidence_artifact="visual-design-report.json",
          description="Restructure already-humanized prose into evidence-prioritized visual components "
                      "(comparison tables, cited-stat 'By the Numbers' grids, authoritative quotations, "
                      "TL;DR box, glossary cards, sparing callouts) WITHOUT inventing facts, editing "
                      "headings, or touching [claim:*]/citation markers or the References section. "
                      "Substance over ornament; cap decorative pull-quotes at 1 (over-design is a measured failure).",
          subagent_type="xuanran-seo-blog-writer:visual-designer",
          dispatch_prompt="Read draft.md + visual-density.json (if present) + angle.json (format_id) + "
                          "subskills/optimize/visual-designer/SKILL.md + references/style/visual-design-components.md. "
                          "Convert dense prose into NATIVE-MARKDOWN components the project's article-css.css styles "
                          "(tables, `## By the Numbers` bold-led lists, `> **Label:**` callouts, `## Glossary` term "
                          "lists, `## TL;DR` box). NEVER emit raw <div>/<table>/<blockquote> (html:False escapes it -> "
                          "render_lint L1 veto). FORBIDDEN: new facts, heading text/anchor edits, changing "
                          "[claim:*] or (Author, Year) citations, editing the References section, the signature, "
                          "or an injected CTA module block ('### Your next step'-class H3 + paragraph). "
                          "Idempotent: detect components already present and only ADD missing ones; do not double-wrap. "
                          "ZERO em-dashes (U+2014) in any text you write (render_lint L12 hard-vetoes them; use a comma, "
                          "period, or 'by'), and every number you move into a component must be copied verbatim from the "
                          "prose it came from — never re-derived. "
                          "STAT-GRID VALUE CONTRACT (v3.39.0 hard gate, stat-grid-check runs right after you): in a "
                          "`## By the Numbers` list the **bold lead** becomes a LARGE DISPLAY FIGURE in a narrow card, "
                          "so it must be a SHORT NUMBER — <=16 chars, longest word <=10 chars, must START with a "
                          "digit/$/~/±, must NOT end with ':'. All descriptive words go AFTER the closing **, unbolded "
                          "(`**30% more** chlorophyll in shaded tencha`, NOT `**30% more chlorophyll** in shaded tencha`). "
                          "A phrase in the bold overflows and chops MID-WORD (project-foxtrot shipped 'chlorophyll' as "
                          "'chloroph/yll'). An item with NO number is not a stat — use a checklist or prose instead. "
                          "Prioritize Tier-A substance (tables, cited stats, real quotations) and keep decorative boxes "
                          "sparse. MANDATORY EVIDENCE: write visual-design-report.json with "
                          "_generated_by:'visual-designer-subagent', components_added (int), components[] "
                          "(each {type, anchor_h2}), density_score. The orchestrator will NOT mark this stage complete "
                          "until that file exists with that provenance. If the draft is already well-designed and you "
                          "add nothing, still write the report (components_added:0). If visual design is genuinely not "
                          "wanted, the caller must run `--action skip --stage visual-designer --reason ...`."),
    Stage("cta-brief-builder", "optimize",
          "BASH:python -m scripts.optimize.cta_brief_builder --task-id {task_id} --project-slug {project_slug} --json",
          ["draft.md", "state.json"], ["cta-brief.json"],
          is_mandatory=False,
          description="Step 1 of the CTA pipeline (v3.37/v3.38.0): deterministic fact resolver, two "
                      "business-model branches read from business-context.json :: conversion_offers. "
                      "b2b_services: resolves the article's blog category to a matched service/team-"
                      "member/proof-points. ecommerce (v3.38.0): matches the article's real content "
                      "(draft body + keyword/title/H2s) against the offline-synced "
                      "projects/{project_slug}/product-catalog.json (scripts.wordpress.wc_catalog_sync) "
                      "via SKU-verbatim match, then category token-overlap, then the configured "
                      "default_category fallback, emitting a WooCommerce [products ...] shortcode. "
                      "Either branch writes cta-brief.json. Projects without conversion_offers config "
                      "no-op (always writes a sentinel cta-brief.json with resolved_service:null, "
                      "skipped_no_config:true, so this stage still completes and the pipeline is never "
                      "halted); the next stage, cta-writer, is then skipped and cta-injection falls "
                      "back to the legacy static cta.variants path unchanged."),
    Stage("cta-writer", "optimize", "LLM",
          ["cta-brief.json"], ["cta-draft.json"],
          is_mandatory=False,
          is_conditional=True,
          condition_field="cta_brief_present",
          condition_value=True,
          evidence_artifact="cta-draft.json",
          description="Step 2 of the CTA pipeline (v3.37): writes genuinely unique, per-article CTA "
                      "copy (mid + end) using ONLY facts from cta-brief.json — never invents a URL, "
                      "name, or number. Heading text is constrained to the registered "
                      "component_headings CTA phrase list (card/quiet/banner skins) or the CSS never "
                      "applies (see agents/cta-writer.md). Conditional on cta-brief-builder having "
                      "actually produced a brief (projects without conversion_offers config skip this "
                      "stage entirely, no error).",
          subagent_type="xuanran-seo-blog-writer:cta-writer",
          dispatch_prompt="Read memory/workspace/{task_id}/cta-brief.json, memory/workspace/{task_id}/draft.md, "
                          "projects/{project_slug}/brand/voice-samples/actual.md (if present), and "
                          "projects/{project_slug}/cta-history.json (if present). Follow agents/cta-writer.md "
                          "exactly: compose CTA copy for the requested placement(s) from the building-block "
                          "palette, using ONLY facts present in cta-brief.json. The heading for each block MUST "
                          "be copied verbatim from the three registered phrase lists in agents/cta-writer.md "
                          "(card/quiet/banner skins) -- an unregistered heading renders completely unstyled, "
                          "this is a hard technical constraint. HEADING DIVERSITY (v3.38.3, second hard "
                          "constraint): the cta-diversity-check gate right after you FAILS on any heading "
                          "already used by this project's last 5 articles -- check cta-history.json's recent "
                          "entries and pick a registered heading NOT among them; the project's configured "
                          "default heading is a preference, not an override of this gate (in a batch, the "
                          "2nd+ article must rotate). ECOMMERCE (v3.38.0): if cta-brief.json has a "
                          "`resolved_products` object, add a `shortcode` field to the block copied VERBATIM "
                          "from resolved_products.shortcode (never alter/rebuild it), write a topic-bridging "
                          "intro paragraph (no markdown link required — the product grid converts), state NO "
                          "prices/stock, and honor cta-brief.json::constraints (no_person_blocks / grief_safe "
                          "tone); if resolved_products.shortcode is null but target_url is set, fall back to a "
                          "b2b-style single-link paragraph with no shortcode. Write "
                          "memory/workspace/{task_id}/cta-draft.json "
                          "with _generated_by:'cta-writer-subagent'. The orchestrator will not mark this stage "
                          "complete without that file present with that exact provenance field."),
    Stage("cta-diversity-check", "optimize",
          "BASH:python -m scripts.optimize.cta_diversity_check --task-id {task_id} --project-slug {project_slug} --json --out {ws}/cta-diversity.json",
          ["state.json"], ["cta-diversity.json"],
          is_mandatory=False,
          is_conditional=True,
          condition_field="cta_brief_present",
          condition_value=True,
          description="Gate 5 of the CTA pipeline (v3.37): cross-article diversity. Runs AFTER "
                      "cta-writer and BEFORE cta-injection so a repetitive CTA draft — a heading "
                      "reused within the last 5 history entries, or a hook opening sharing its "
                      "first 6 words with a recent article — is caught and re-generated BEFORE it "
                      "is ever placed into draft.md. Conditional on cta_brief_present (the SAME "
                      "gate cta-writer uses): the 5 projects without conversion_offers config never "
                      "reach this stage (auto-skipped with a logged reason), and check_diversity() "
                      "is additionally a no-op PASS when no cta-draft.json exists — so a "
                      "non-adopting project can never halt here. required_inputs is only state.json "
                      "(never cta-draft.json), so it cannot BLOCK on the missing draft the way "
                      "Task 13's cta-brief-builder backward-compat bug did. A failing result "
                      "(passed=false) is a real gate: cta-diversity.json is in _PASS_FLAG_REQUIRED, "
                      "so it blocks completion and routes back to re-dispatch cta-writer with fresh "
                      "creative. NOT in _FRESHNESS_VS_DRAFT: it scores cta-draft.json, not draft.md, "
                      "so a later cta-injection edit to draft.md must not mark it stale."),
    Stage("cta-tone-check", "optimize",
          "BASH:python -m scripts.lint.cta_tone_check --task-id {task_id} --project-slug {project_slug} --json --out {ws}/cta-tone.json",
          ["state.json"], ["cta-tone.json"],
          is_mandatory=False,
          is_conditional=True,
          condition_field="cta_brief_present",
          condition_value=True,
          description="Gate 2 of the CTA pipeline (v3.38.0): deterministic hype/pressure/tone "
                      "lexicon lint (v1, NOT an LLM judge — see subskills/optimize/cta-placement/"
                      "SKILL.md) on cta-draft.json. Runs AFTER cta-diversity-check and BEFORE "
                      "cta-injection so a hype-laden or pressure-tactic CTA draft is caught and "
                      "re-generated before it is ever placed into draft.md. Conditional on "
                      "cta_brief_present (the SAME gate cta-writer/cta-diversity-check use): the "
                      "5 projects without conversion_offers config never reach this stage "
                      "(auto-skipped with a logged reason), and check_tone() is additionally a "
                      "no-op PASS when no cta-draft.json exists — so a non-adopting project can "
                      "never halt here. required_inputs is only state.json (never cta-draft.json), "
                      "so it cannot BLOCK on the missing draft the way Task 13's cta-brief-builder "
                      "backward-compat bug did. A failing result (passed=false) is a real gate: "
                      "cta-tone.json is in _PASS_FLAG_REQUIRED, so it blocks completion and routes "
                      "back to re-dispatch cta-writer with fresh creative (see the operator note in "
                      "subskills/optimize/cta-placement/SKILL.md — a GATE_FAILED here does not fix "
                      "itself). NOT in _FRESHNESS_VS_DRAFT: it scores cta-draft.json, not draft.md, "
                      "so a later cta-injection edit to draft.md must not mark it stale."),
    Stage("cta-injection", "optimize",
          "BASH:python -m scripts.optimize.cta_injector --task-id {task_id} --project-slug {project_slug} --json",
          ["draft.md", "state.json"], ["cta-injection-result.json"],
          description="Step 3 of the CTA pipeline (v3.37, formerly the whole system): places the CTA "
                      "block(s) into draft.md. Consumes cta-draft.json (Step 2's LLM output) when "
                      "present, otherwise falls back unchanged to the legacy static "
                      "business-context.json :: cta.variants config. Deterministic, idempotent. Runs "
                      "AFTER visual-designer (so the LLM can't move/strip the block) and BEFORE "
                      "render-lint (so the lints validate the CTA markdown). Projects without any cta "
                      "config (or enabled:false) no-op but still write the evidence artifact."),
    Stage("cta-record-history", "optimize",
          "BASH:python -m scripts.optimize.cta_diversity_check --task-id {task_id} --project-slug {project_slug} --record --json --out {ws}/cta-history-record.json",
          ["cta-injection-result.json"], ["cta-history-record.json"],
          is_mandatory=False,
          is_conditional=True,
          condition_field="cta_brief_present",
          condition_value=True,
          description="Gate 5 record step (v3.37): runs AFTER cta-injection has actually placed the "
                      "CTA, and appends THIS article's CTA fingerprint (heading + hook prefix) to "
                      "projects/{slug}/cta-history.json so FUTURE articles' cta-diversity-check has "
                      "real history to compare against (without this, Gate 5 could never fire — it "
                      "would forever compare against an empty window). Guarded by "
                      "record_history_if_eligible(): it records ONLY when cta-injection-result.json "
                      "shows passed AND draft_source=='llm'. The legacy static path and no-op "
                      "projects write recorded:false and do NOT pollute the diversity window — the "
                      "eligibility check is Python, not a shell conditional, so it is unit-testable. "
                      "Conditional on cta_brief_present so the 5 non-adopting projects skip it "
                      "entirely. This is NOT a gate: recorded:false is a valid, expected outcome, so "
                      "it is intentionally absent from _PASS_FLAG_REQUIRED and "
                      "run_pipeline._GATE_STAGES — bookkeeping must never halt a publish."),
    Stage("visual-density-check", "optimize",
          "BASH:python -m scripts.lint.visual_density_check --workspace {task_id} --json --out {ws}/visual-density.json",
          ["draft.md"], ["visual-density.json"],
          description="MANDATORY gate: FAIL blocks publish on a wall-of-text FLOOR (< weighted min OR no "
                      "Tier-A table/stat-grid/quotation/chart); the CEILING (over-used pull-quotes/callouts) is "
                      "advisory-warning only. A failing draft routes GATE_FAILED back to visual-designer. Per-project "
                      "opt-out: business-context.json :: visual_density_required=false."),
    Stage("stat-grid-check", "optimize",
          "BASH:python -m scripts.lint.stat_grid_check --workspace {task_id} --json --out {ws}/stat-grid-lint.json",
          ["draft.md"], ["stat-grid-lint.json"],
          description="MANDATORY gate (v3.39.0): the 'By the Numbers' stat-card grid renders each item's "
                      "leading **bold** as a large display FIGURE. S1-S4 fail a value that is too long, "
                      "contains a long word, is not numeric, or is a colon-terminated label -- all of which "
                      "shatter the card (project-foxtrot shipped 'chlorophyll' as 'chloroph/yll'; a 591-post survey "
                      "found 29% of all stat values breaking). The CSS hardening in article_css_generator.py "
                      "makes a bad value degrade gracefully; THIS gate keeps it designed rather than merely "
                      "survivable. A failure routes GATE_FAILED back to visual-designer."),
    Stage("render-lint", "optimize",
          "BASH:python -m scripts.lint.render_lint --workspace {task_id} --json",
          ["draft.md"], ["render-lint.json"],
          description="L1-L9 leak detection: HTML escapes, Pandoc anchors, orphan bold, claim markers, scaffold markers"),
    Stage("image-placeholder-check", "optimize",
          "BASH:python -m scripts.lint.image_placeholder_check --draft {ws}/draft.md --image-prompts {ws}/image-prompts.json --json --out {ws}/image-placeholder-lint.json",
          ["draft.md", "image-prompts.json"], ["image-placeholder-lint.json"],
          description="D1-D5 image placeholder drift detection"),
    Stage("keyword-density-check", "optimize",
          "BASH:python -m scripts.lint.keyword_density {ws}/draft.md --primary \"{primary_keyword}\" --primary-min 0.005 --primary-max 0.010 --json --out {ws}/keyword-density.json",
          ["draft.md"], ["keyword-density.json"],
          description="Primary keyword density check, target 0.5-1.0%, hard veto >1.5%"),
    Stage("paa-alignment-check", "optimize",
          "BASH:python -m scripts.lint.paa_alignment_check --workspace {task_id} --json --out {ws}/paa-alignment-lint.json",
          ["draft.md", "research.json"], ["paa-alignment-lint.json"],
          description="Measure FAQ<->research.paa alignment ON THE DRAFT (>=60% contract; "
                      "required = min(ceil(0.6*faq_count), paa_count)). Executor the "
                      "paa-answer-writer SKILL never had (Rule 6, 4th offense class): "
                      "outline.faq.paa_alignment_pct was a self-report validated by NOTHING. "
                      "No-ops PASS on thin PAA harvests (<3) or missing FAQ (mandatory_sections "
                      "owns that). 2026 basis: PAA grew through 2025 and co-occurs with AIO on "
                      "~90% of AIO SERPs — aligned Q&A feeds both."),
    Stage("locale-spelling-check", "optimize",
          "BASH:python -m scripts.lint.spelling_dialect_check --workspace {task_id} --json --out {ws}/locale-spelling-lint.json",
          ["draft.md", "state.json"], ["locale-spelling-lint.json"],
          description="Dialect-drift gate (localization-pass Mode 1, finally wired — the "
                      "executor existed since v5.0 with zero invocations). Resolves target "
                      "dialect from brief.target_market_locale (en-US default), exempts "
                      "References/quotes/code/URLs/proper-nouns, FAILs only on >=3 "
                      "opposite-dialect spellings (systemic AI-tell drift, e.g. en-GB "
                      "'colour/organise/whilst' leaking into en-US prose). Non-English "
                      "locales + en-CA no-op PASS."),
    Stage("brand-fact-check", "optimize",
          "BASH:python -m scripts.lint.brand_fact_check --workspace {task_id} --json --out {ws}/brand-fact-lint.json",
          ["draft.md", "state.json"], ["brand-fact-lint.json"],
          description="First-person company-fact consistency lint (v3.36.0). The "
                      "2026-07-06 batch fabricated the agency's OWN tenure 3x in one run "
                      "('five years'/'ten years'/'a decade' vs the real 6y in "
                      "business-context.company) and one shipped into a draft post — no "
                      "layer supplied or enforced the company facts (writer.md's red line "
                      "covers EXTERNAL sources only, and GEO scoring actively rewards "
                      "experience phrasing, so the optimize phase pushes agents toward "
                      "inventing exactly these numbers). Checks SELF-referential sentences "
                      "only (first-person/brand-name guard, so third-party advice like "
                      "'the named owner should have five plus years' can never false-fire) "
                      "for tenure / team-size / clients-served numbers vs "
                      "business-context.company. Projects without a company block: "
                      "no-op PASS."),
    Stage("local-uniqueness-check", "optimize",
          "BASH:python -m scripts.lint.local_uniqueness_check --workspace {task_id} --json --out {ws}/local-uniqueness-lint.json",
          ["draft.md", "state.json"], ["local-uniqueness-lint.json"],
          is_conditional=True, condition_field="brief.local_mode", condition_value=True,
          description="Sterling Sky 80/20 anti-doorway gate — MANDATORY when state.brief.local_mode "
                      "is true, auto-skipped otherwise. Composite >=70 PASS, 50-69 WARN (passes), "
                      "<50 OR a missing Sterling category = FAIL (hard veto, route to repair). "
                      "2026-07-01: the SKILL doc declared this gate since v3.4.0 but the v3.7 "
                      "runner migration never carried it into the STAGES table — it had NEVER "
                      "executed in ~60 production workspaces (Rule 6, second offense for this "
                      "feature). First user of the is_conditional stage machinery."),
    Stage("quality-gates", "optimize",
          "BASH:python -m scripts.validate.run_quality_gates --workspace {task_id} --json",
          ["draft.md", "citations.json", "humanizer-report.json"],
          ["quality.json"],
          description="Run 3 automated quality gates: CORE-EEAT (80 items), CITE (40 items), AI-Slop (43 patterns)"),
    Stage("independent-reviewer", "optimize", "LLM",
          ["draft.md", "citations.json"], ["review.json"],
          description="Dispatch independent reviewer subagent for fresh-editor E-E-A-T evaluation. Target score >= 80. MUST use the subagent — do NOT write review.json yourself.",
          subagent_type="xuanran-seo-blog-writer:reviewer",
          dispatch_prompt="Review draft.md as a fresh editor with NO pipeline history. Score 0-100 on E-E-A-T + AI citability. Run an explicit CROSS-SECTION NUMERIC CONSISTENCY sweep: any metric restated across TL;DR / Abstract / Key Takeaways / tables / By-the-Numbers / FAQ / Conclusion must carry the SAME numbers, and any enumerated framework ('the 12 tests') must be referenced with its real count everywhere (the 2026-07-06 batch shipped one pricing band stated 4 different ways and a 6-check scorecard introduced as 'ten questions'); flag drift with BOTH locations quoted. NOTE — CTA blocks are config-authored and machine-verified (business-context.cta + verify checks 29/30): FIRST read memory/workspace/{task_id}/cta-draft.json :: blocks[*].heading — THOSE exact headings (plus their single paragraph and any [products] shortcode) are the machine-owned CTA blocks in this draft; do NOT spend a would-change item proposing their removal, renaming, or rewording (a 2026-08-17 reviewer proposed renaming the registered 'One more thing' H3 because it only knew example headings; the operator executed the rename and the injector then shipped a duplicated CTA — post 38418); placement observations go in notes only. Provide 3 'would change' items. Write review.json. Must include _generated_by: 'reviewer-subagent'."),
    Stage("image-pipeline-join", "publish", "CHECK",
          ["image-prompts.json"], ["images.json"],
          description="Verify Fork B completed and images.json exists"),
    Stage("image-visual-qa", "publish", "LLM",
          ["images.json", "image-prompts.json", "outline.json", "draft.md"],
          ["image-qa-report.json"],
          description="Vision QA: Opus subagent reads every generated PNG, scores 13 defect "
                      "classes (P1-P10 photo, C1-C3 chart), rewrites prompts + triggers targeted "
                      "regeneration (max 2 rounds) via image_regen_slots.py / render_data_charts. "
                      "accept_with_warning never blocks publish.",
          subagent_type="xuanran-seo-blog-writer:image-visual-qa",
          dispatch_prompt="Read workspace images.json and READ EVERY PNG it lists (you have vision). Score each image per agents/image-visual-qa.md taxonomy (P1-P6 error: composition collapse, anatomy deformity, garbled text, empty label chips, third-party brands, content mismatch vs section; P7-P10 warning: brand-color drift, low contrast/muddy, AI-look, style inconsistency; C1-C3 for charts). Judge against projects/{project_slug}/brand-guideline.yaml (palette, label_text, forbid_third_party_brands, realism rules) and each slot's H2 context in draft.md. Verdict per image: any error OR (score<70 AND >=2 warnings) -> regenerate. For photo regen: rewrite prompt (keep art_direction_prefix VERBATIM; targeted negatives per defect; type->theme->layout->subject->background->quality ordering), write image-qa-regen-requests.json, run `python -m scripts.openai.image_regen_slots --workspace {ws} --requests-file {ws}/image-qa-regen-requests.json --task-id {task_id} --json`, re-Read + re-score. For chart defects: fix chart_spec in image-prompts.json (REAL numbers from research.json only) and re-run `python -m scripts.build.render_data_charts --task-id {task_id} --project-slug {project_slug} --json`. Max 2 rounds; still failing -> final_verdict accept_with_warning (NEVER block). Write image-qa-report.json per schemas/image-qa-report.schema.json with _generated_by: 'image-visual-qa-subagent'. PER-SLOT FIELD CONTRACT IS EXACT (v3.38.3 - a 2026-07-10 run wrote slot-level 'verdict' and hard-failed the final gate): every images[] entry MUST carry slot_id, kind, final_verdict ('pass'|'accept_with_warning' - named final_verdict, NOT verdict), final_score (0-100), and round_history (list of {round, score, verdict, defects[]} - a bare 'verdict' key lives INSIDE round_history only). pre_publish_gate reads images[].final_verdict verbatim."),
    Stage("pre-publish-gate", "publish",
          "BASH:python -m scripts.pipeline.pre_publish_gate --workspace {task_id} --json",
          ["draft.md", "meta.json", "citations.json", "images.json",
           "image-qa-report.json",
           "render-lint.json", "image-placeholder-lint.json",
           "fact-check.json", "humanizer-report.json", "review.json",
           "quality.json"],
          ["pre-publish-gate-result.json"],
          description="10-gate mandatory artifact check — MUST pass before wp_publisher"),
    Stage("wordpress-publisher", "publish",
          "BASH:python -m scripts.wordpress.wp_publisher {project_slug} --workspace {task_id} --status draft --json",
          ["draft.md", "meta.json", "images.json", "schema.json",
           "pre-publish-gate-result.json"],
          ["publish-result.json"],
          description="Create/PATCH WordPress draft with images, CSS, schema, RankMath"),
    Stage("verify-post", "publish",
          "BASH:python -m scripts.wordpress.verify_post {project_slug} {post_id} --workspace {task_id} --expected-status draft --json --out {ws}/verify-result.json",
          ["publish-result.json"], ["verify-result.json"],
          description="Structural verification of the published post (full check "
                      "battery in scripts/wordpress/verify_post.py — the count is "
                      "deliberately not stated here; a hardcoded number went stale "
                      "twice)"),
    Stage("indexing-notifier", "publish",
          "BASH:python -m scripts.publish.indexing_notify {project_slug} --workspace {task_id} --json",
          ["verify-result.json"], ["indexing-result.json"],
          is_mandatory=False,
          description="Submit the live URL to Bing IndexNow (Bing + ChatGPT-via-Bing + "
                      "Yandex). Wired v3.42.12 — the subskill claimed 'final step of "
                      "phase-publish' for months with no Stage (Rule 6; the only caller "
                      "of indexnow_submit was the dead agents/publisher.md). NOTIFIER, "
                      "not a gate: drafts record outcome=skipped_draft (Rule 5a — never "
                      "ping a draft URL; re-run the script after the operator flips the "
                      "post live), and submit/transport failures record an honest "
                      "outcome but never block a pipeline whose article already "
                      "published and verified (same never-blocks contract as "
                      "image-visual-qa). GSC URL-inspection stays a documented manual "
                      "step: per-site OAuth + strict quotas across a 13-site fleet."),
]


def _ws(task_id: str) -> Path:
    return WS_ROOT / task_id


def _read_state(task_id: str) -> dict:
    p = _ws(task_id) / "state.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _cta_brief_present(ws: Path) -> bool:
    """Content-derived (Finding 2): True ONLY when cta-brief.json holds a REAL
    resolved brief. SINGLE source of truth for state.json::cta_brief_present,
    the field cta-writer's is_conditional check reads.

    Since Finding 1, cta_brief_builder.py ALWAYS writes cta-brief.json — even the
    no-config sentinel (resolved_service=null / skipped_no_config=true). So the
    old "stage merely completed -> cta_brief_present=True" rule would now dispatch
    cta-writer with an empty sentinel. Presence of the FILE is no longer the
    signal; the presence of a real, usable OFFER is. A sentinel therefore
    yields False, so cta-writer is auto-skipped and cta-injection falls back to
    the legacy static path (backward-compatible for the 5 projects without
    conversion_offers).

    Two offer shapes count as present (v3.38.0 — the Task-3 ecommerce handoff):
      * b2b_services: a non-null `resolved_service` (its `url` is the target).
      * ecommerce: `resolved_service` is ALWAYS null, so the signal is a usable
        `resolved_products` offer — one that carries a product-grid `shortcode`
        OR a fallback shop link (`target_url`). A degenerate fallback (null
        shortcode AND null target_url) has nothing to convert on, so it behaves
        exactly like the sentinel: cta-writer is skipped, not dispatched with an
        empty offer.
    In both shapes `skipped_no_config` (the sentinel flag) forces False.

    A `resolution_failed` brief (v3.42.4: configured offers that could NOT be
    resolved — broken catalog sync, unreachable config) also derives False here
    (there is genuinely no offer to write about), but it must NEVER reach this
    derivation as a completed stage: the cta-brief-builder branch of
    _content_gate_reason() fails the stage first, so the pipeline routes to
    fix/re-dispatch instead of auto-skipping the CTA stages as if the project
    had no config (2026-08-12 audit)."""
    p = ws / "cta-brief.json"
    if not p.exists():
        return False
    try:
        brief = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return False
    if not isinstance(brief, dict):
        return False
    if brief.get("skipped_no_config", False):
        return False
    if brief.get("resolved_service") is not None:
        return True
    rp = brief.get("resolved_products")
    if isinstance(rp, dict) and (rp.get("shortcode") or brief.get("target_url")):
        return True
    return False


def _record_stage(task_id: str, stage_name: str, status: str, reason: str = "") -> None:
    """Write stage start/complete/skipped to BOTH state.json::stage_history AND pipeline-checklist.json.

    status="skipped" is distinct from "completed": it records an EXPLICIT operator
    decision not to run an optional stage, with a logged reason, so the audit trail
    never conflates "ran" with "was quietly dropped" (the 2026-06-02 root cause)."""
    now = datetime.now(timezone.utc).isoformat()
    state_path = _ws(task_id) / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        history = state.setdefault("stage_history", [])
        existing = next((h for h in history if h["stage"] == stage_name), None)
        if status == "in_progress":
            if not existing:
                history.append({"stage": stage_name, "started_at": now, "completed_at": now, "status": "in_progress"})
        elif status in ("completed", "skipped"):
            if existing:
                existing["status"] = status
                existing["completed_at"] = now
                if reason:
                    existing["skip_reason"] = reason
            else:
                entry = {"stage": stage_name, "started_at": now, "completed_at": now, "status": status}
                if reason:
                    entry["skip_reason"] = reason
                history.append(entry)
        if stage_name == "cta-brief-builder" and status == "completed":
            # v3.37: the ONLY writer of state.json::cta_brief_present, which is
            # the field cta-writer's is_conditional check reads
            # (condition_field="cta_brief_present"). cta_brief_builder.py itself
            # only writes cta-brief.json and never touches state.json (mirrors
            # every other Stage executor in this file), so without this the
            # condition could never evaluate True and cta-writer would be
            # permanently auto-skipped even on projects where cta-brief.json
            # was actually produced -- a Rule-6-class silent no-op.
            # Finding 2: the value is CONTENT-derived, NOT completion-derived.
            # Since Finding 1 the stage always completes (even the no-config
            # sentinel), so "completed -> True" would wrongly make cta-writer a
            # dispatch candidate with an empty brief. _cta_brief_present() reads
            # the actual cta-brief.json and is True only for a real resolved_service.
            state["cta_brief_present"] = _cta_brief_present(_ws(task_id))
        state["updated_at"] = now
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    checklist_path = _ws(task_id) / "pipeline-checklist.json"
    if checklist_path.exists():
        cl = json.loads(checklist_path.read_text(encoding="utf-8"))
    else:
        cl = {"task_id": task_id, "stages": {}}
    entry = {"status": status, "at": now}
    if reason:
        entry["skip_reason"] = reason
    cl["stages"][stage_name] = entry
    checklist_path.write_text(json.dumps(cl, indent=2, ensure_ascii=False), encoding="utf-8")


def _stamp_pipeline_complete(task_id: str) -> None:
    """Stamp state.json terminal status when next_stage() finds nothing left to run.

    Before v3.41.0 the PIPELINE_COMPLETE branch only RETURNED completion — no code
    path ever wrote it, so every finished task stayed ``status: "running"`` /
    ``current_stage: <last stage>`` forever and /status reported phantom in-flight
    work (found live on the 2026-07-17 project-hotel batch: 3 verified-draft tasks,
    all still "running"). Idempotent: re-invoking the runner on a finished
    workspace must not churn updated_at.
    """
    state_path = _ws(task_id) / "state.json"
    if not state_path.exists():
        return
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("status") == "completed":
        return
    now = datetime.now(timezone.utc).isoformat()
    state["status"] = "completed"
    state["current_stage"] = "complete"
    state["completed_at"] = now
    state["updated_at"] = now
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def backfill_complete() -> dict:
    """One-time migration: stamp terminal status on historically finished tasks.

    Before v3.41.0, NO code path ever wrote ``status: "completed"`` (see
    _stamp_pipeline_complete), so every finished workspace since the runner's
    introduction reads ``running`` forever and /status reports phantom in-flight
    work (325 phantoms on 2026-07-17). A task is considered finished when its
    own history/artifacts show it reached the pipeline's terminal evidence:
    a completed ``verify-post`` stage OR a ``publish-result.json`` on disk.
    Genuinely abandoned mid-pipeline workspaces are intentionally left
    ``running`` — that is their true state.
    """
    stamped: list[str] = []
    scanned = 0
    if not WS_ROOT.is_dir():
        return {"scanned": 0, "stamped": []}
    for d in sorted(WS_ROOT.iterdir()):
        state_path = d / "state.json"
        if not d.is_dir() or not state_path.exists():
            continue
        scanned += 1
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if state.get("status") == "completed":
            continue
        history = state.get("stage_history") or []
        verify_done = any(
            h.get("stage") == "verify-post" and h.get("status") == "completed"
            for h in history)
        if verify_done or (d / "publish-result.json").exists():
            _stamp_pipeline_complete(d.name)
            stamped.append(d.name)
    return {"scanned": scanned, "stamped": stamped, "stamped_count": len(stamped)}


def _artifact_exists(ws: Path, name: str) -> bool:
    if name.endswith("/"):
        d = ws / name.rstrip("/")
        return d.is_dir() and any(d.iterdir())
    return (ws / name).exists()


# v3.41.3: SHARED with pre_publish_gate via scripts/_core/provenance — the two
# hand-maintained copies had drifted to 3-of-7 overlap (Rule 12). Change the
# contract THERE, never here. (Import lives in the top import block.)
_PROVENANCE_REQUIRED = PROVENANCE_REQUIRED

SUBAGENT_ENFORCED_STAGES = {
    "fact-check-and-citation",
    "humanizer",
    "independent-reviewer",
    "image-visual-qa",
    "cta-writer",
    # v3.41.3: these two stages' artifacts were ALWAYS provenance-gated by
    # _artifact_valid, but the stages were missing from this set, so their
    # dispatch payloads never carried the enforcement_warning telling the
    # subagent to stamp _generated_by — geo-audit.json failed exactly that way
    # on the 2026-07-19 batch (operator had to hand-patch the field in).
    "geo-content-optimizer",
    "visual-designer",
    "internal-linker",
}

# Gate-result artifacts that carry a top-level pass flag. A result whose flag is
# False (or missing) is NOT a valid/complete artifact — it must block progression
# and be re-evaluated on re-run, never bypassed merely because the (failing) file
# exists on disk. (2026-06-04 batch audit RC-B: after a first run wrote
# pre-publish-gate-result.json with passed=False (fact-check verdict FIX_REQUIRED),
# the re-run treated the stage as complete because validity == existence, so the
# gate was skipped and wordpress-publisher ran on the stale failing artifact.)
# The pass key differs per file, so this is a {filename: pass_key} map.
_PASS_FLAG_REQUIRED = {
    "pre-publish-gate-result.json": "passed",
    "render-lint.json": "passed",
    "image-placeholder-lint.json": "passed",
    "section-completeness.json": "passed",
    "visual-density.json": "passed",
    # Stat-grid contract (v3.39.0): a value that is not a short numeric figure
    # shatters the stat card it renders into. passed=false must block, not
    # auto-satisfy. Rule 11: mirrored in run_pipeline._GATE_STAGES.
    "stat-grid-lint.json": "passed",
    "local-uniqueness-lint.json": "passed",
    # Chart renders report "success" not "passed"; a failing render must not
    # auto-satisfy its stage on re-run (same RC-B class as the gates above).
    "chart-render-result.json": "success",
    "chart-rerender-result.json": "success",
    # CTA injection (v3.34): a result with passed=false (bad config / missing
    # variants / unclassifiable heading) must block, not auto-satisfy.
    "cta-injection-result.json": "passed",
    # CTA diversity Gate 5 (v3.37): a repetitive draft (passed=false) must block
    # so cta-writer is re-dispatched before the repeated CTA reaches draft.md.
    # Deliberately NOT in _FRESHNESS_VS_DRAFT — it scores cta-draft.json, not the
    # draft — so cta-injection's later draft.md edit does not mark it stale.
    "cta-diversity.json": "passed",
    # CTA tone Gate 2 (v3.38.0): a hype/pressure-laden draft (passed=false) must
    # block so cta-writer is re-dispatched before the flagged copy reaches
    # draft.md. Deliberately NOT in _FRESHNESS_VS_DRAFT for the same reason as
    # cta-diversity.json above — it scores cta-draft.json, not the draft.
    "cta-tone.json": "passed",
    # NOTE (v3.37): cta-brief.json is intentionally NOT listed here. It has no
    # pass/fail flag by design (comment in the plan: "presence alone is the
    # evidence"), and this dict's own check --
    # `data.get(pass_key) is not True` -- means a key mapped to `None` would
    # make data.get(None) return None on any normal dict, so `None is not True`
    # is always True and _artifact_valid would ALWAYS report the file invalid
    # regardless of content. That inverts the intended "presence is enough"
    # behavior into "never valid". Plain existence + JSON-parseability (already
    # enforced by _artifact_valid's generic checks above) is the correct/only
    # gate for this artifact; do not add it here. (2026-08-12: the v3.42.4
    # `resolution_failed` sentinel IS content-gated, but via the
    # cta-brief-builder branch of _content_gate_reason — the shared helper both
    # completion paths read — not via this pass-flag map, precisely because the
    # artifact has no boolean `passed` and the legitimate skipped_no_config
    # sentinel must keep validating.)
    # v3.35 lint gates (paa-answer-writer + localization-pass root cures).
    "paa-alignment-lint.json": "passed",
    "locale-spelling-lint.json": "passed",
    # v3.36 company-fact lint (2026-07-06 tenure-fabrication root cure).
    "brand-fact-lint.json": "passed",
    # 2026-07-17 audit — two Rule-12 existence-only gates closed:
    # citation-capsule lint writes passed=(coverage >= target); a below-target
    # coverage must re-dispatch the capsule builder, not mark it complete.
    "citation-capsule-result.json": "passed",
    # finalize-refs-signature writes an {"error": ...} payload on failure so a
    # human can debug it — that file's existence proved nothing (same disease
    # as verify-result.json in v3.35.2). It now carries passed.
    "finalize-result.json": "passed",
    # v3.38.3 (2026-07-10) — Rule 12 root cures from the project-juliet batch.
    # keyword-density: passed=false ONLY above the 1.5% hard-stuffing ceiling;
    # the under-band "too_low" stays informational (band field), so this cannot
    # block the common legitimately-sparse long-tail phrase case.
    "keyword-density.json": "passed",
    # quality-gates: passed=all_pass. The fresh ai_slop measurement (quality.json
    # is in _FRESHNESS_VS_DRAFT, so it re-runs after every draft edit) must be
    # able to block; before this, post-humanizer regressions (gold-filament
    # 2026-07-09: 16.13 → 24.25 after linker/geo/cta) sailed to publish because
    # pre-publish adjudicated ai_slop from the STALE humanizer-report.
    # Rule 11: mirror of run_pipeline._GATE_STAGES — change together.
    "quality.json": "passed",
}

# Artifacts that must carry the CANONICAL schema's required keys to be valid.
# (Existence + parseability is not shape-conformance — see the 2026-07-06
# researcher output-shape drift note at the check site in _artifact_valid.)
_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "research.json": ("primary_keyword", "intent", "competitor_titles"),
}

# Deterministic, draft-derived gate artifacts must be at least as NEW as the
# draft they scored. 2026-07-01 (loamphxseo0701): the geo-auditor subagent ran
# run_quality_gates itself mid-stage; the runner later saw quality.json on disk
# and auto-stamped the quality-gates stage COMPLETE without executing it — the
# shipped draft was 11 minutes newer than the quality.json that "gated" it.
# A stale artifact here is simply not valid, so the runner re-executes the
# stage (all are cheap local scripts, seconds at most). LLM artifacts are
# deliberately excluded — re-dispatch costs real money/time; their staleness
# is surfaced as a pre_publish_gate WARN instead (operator's trade-off).
_FRESHNESS_VS_DRAFT = {
    "quality.json",
    "render-lint.json",
    "keyword-density.json",
    "visual-density.json",
    # Scores draft.md, so a later repair edit must re-run it: an edit that
    # re-introduces a phrase-shaped stat value cannot ride a stale pass.
    "stat-grid-lint.json",
    "image-placeholder-lint.json",
    "local-uniqueness-lint.json",
    # CTA injection is cheap + idempotent: a post-repair draft edit re-runs it,
    # which re-verifies the CTA module wasn't stripped and re-stamps the result.
    "cta-injection-result.json",
    "paa-alignment-lint.json",
    "locale-spelling-lint.json",
    "brand-fact-lint.json",
}


def _artifact_valid(ws: Path, name: str) -> bool:
    if not _artifact_exists(ws, name):
        return False
    if name.endswith(".json"):
        try:
            data = file_bus.tolerant_json_load(ws / name)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False
        if name in _PROVENANCE_REQUIRED:
            gen_by = data.get("_generated_by", "")
            if gen_by not in _PROVENANCE_REQUIRED[name]:
                return False
        if name in _PASS_FLAG_REQUIRED:
            # A gate result is valid ONLY when its pass flag is explicitly True.
            pass_key = _PASS_FLAG_REQUIRED[name]
            if not isinstance(data, dict) or data.get(pass_key) is not True:
                return False
        if name in _REQUIRED_KEYS:
            # Canonical-shape floor (2026-07-06): a researcher subagent wrote
            # research.json in a fully custom shape (serp_ground_truth/
            # competitor_analysis/key_themes instead of the canonical
            # schemas/research.schema.json keys). It passed the existence check
            # and the drift only surfaced 3 stages later as a confusing
            # serp-analysis evidence failure, requiring hand-normalization.
            # Enforce the schema's required keys HERE so the drift fails at the
            # research stage itself with the artifact named. PRESENCE is the
            # contract, not richness: the weekly-digest prewrite intentionally
            # ships competitor_titles: [] (digests have no SERP competitors),
            # so an explicitly-present empty list is valid — only an ABSENT/None
            # key (the shape-drift signature) or a blank string is not.
            if not isinstance(data, dict):
                return False
            for k in _REQUIRED_KEYS[name]:
                if k not in data or data.get(k) is None or data.get(k) == "":
                    return False
        if name in _FRESHNESS_VS_DRAFT:
            # Stale deterministic gate artifact (older than the draft it scored)
            # is NOT valid — forces re-execution of the cheap local stage.
            try:
                draft = ws / "draft.md"
                if draft.exists() and (ws / name).stat().st_mtime < draft.stat().st_mtime:
                    return False
            except OSError:
                pass  # unstat-able file: fall through to the existence verdict
        if name == "schema.json":
            # Pre-publish shape guard (2026-07-09): the schema-generator stage's
            # output is a hard wordpress-publisher input but had NO shape check, so a
            # fabricated / 1-block / empty schema.json passed here and only failed
            # LIVE at verify_post check 17 (head schema isn't fetchable pre-publish,
            # so the >=2-body-block minimum falls entirely on this file). Enforce the
            # >=2-block + typed-block contract HERE so the failure surfaces at the
            # schema-generator stage, not as a late manual patch. Root cause of the
            # 2026-07-09 schema-validator-dispatched-to-generate incident.
            blocks = data.get("blocks") if isinstance(data, dict) else None
            if not isinstance(blocks, list) or len(blocks) < 2:
                return False
            for b in blocks:
                ld = b.get("ld_json") if isinstance(b, dict) else None
                if not isinstance(ld, dict) or not ld.get("@type"):
                    return False
        if isinstance(data, dict) and not data:
            return False
        return True
    return True


def _checklist_status(ws: Path, stage_name: str) -> str:
    """Return the recorded status for a stage from pipeline-checklist.json ('' if none)."""
    cl = ws / "pipeline-checklist.json"
    if not cl.exists():
        return ""
    try:
        data = json.loads(cl.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""
    return data.get("stages", {}).get(stage_name, {}).get("status", "")


def _history_status(ws: Path, stage_name: str) -> str:
    """Return the recorded status for a stage from state.json::stage_history ('' if none).

    Mirror of _checklist_status for the SECOND completion store. Completion state
    is persisted in three places (state.json stage_history, pipeline-checklist.json,
    and the artifacts themselves); the 2026-07-09 project-kilo batch showed that a
    hand-edited workspace can desync the two record stores, so any code that wants
    'is this stage recorded?' must be able to ask BOTH."""
    sp = ws / "state.json"
    if not sp.exists():
        return ""
    try:
        state = json.loads(sp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""
    for h in state.get("stage_history", []):
        if isinstance(h, dict) and h.get("stage") == stage_name:
            return h.get("status", "")
    return ""


def _evidence_keys_present(ws: Path, shared_file: str, keys: list[str], min_count: int = 1) -> bool:
    """True if shared_file is valid JSON and at least one of `keys` holds content.

    Used by serp-analysis / competitor-analysis whose work folds into research.json:
    the stage is proven to have run only when its signature keys actually exist with
    content, not merely because the shared file exists. `min_count` is a richness
    floor — a list/dict key must hold >= min_count items, so a 1-item stub does NOT
    count as a real SERP/competitor analysis (the folding loophole)."""
    if not shared_file or not keys:
        return True
    p = ws / shared_file
    if not p.exists():
        return False
    try:
        data = file_bus.tolerant_json_load(p)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    for k in keys:
        v = data.get(k)
        if isinstance(v, (list, dict)):
            if len(v) >= min_count:
                return True
        elif isinstance(v, str):
            if len(v) > 0 and min_count <= 1:
                return True
        elif v not in (None, "", [], {}) and min_count <= 1:
            return True
    return False


def _evidence_ok(stage: Stage, ws: Path) -> tuple[bool, list[str]]:
    """Check a stage's execution evidence. Returns (ok, missing_reasons)."""
    missing: list[str] = []
    if stage.evidence_artifact and not _artifact_valid(ws, stage.evidence_artifact):
        prov = ""
        if stage.evidence_artifact in _PROVENANCE_REQUIRED:
            prov = f" with _generated_by in {_PROVENANCE_REQUIRED[stage.evidence_artifact]}"
        missing.append(f"{stage.evidence_artifact} (execution evidence{prov})")
    if stage.evidence_keys and not _evidence_keys_present(ws, stage.evidence_in, stage.evidence_keys, stage.evidence_min_count):
        floor = f" (>= {stage.evidence_min_count} items)" if stage.evidence_min_count > 1 else ""
        missing.append(f"{stage.evidence_in} must contain non-empty {stage.evidence_keys}{floor}")
    return (len(missing) == 0, missing)


def _check_stage_condition(stage: Stage, state: dict) -> bool:
    if not stage.is_conditional:
        return True
    parts = stage.condition_field.split(".")
    val = state
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p)
        else:
            val = None
            break
    return bool(val) == bool(stage.condition_value)


# fact-check verdict sets live in scripts/pipeline/fc_verdict.py (2026-08-02):
# ONE classifier shared with pre_publish_gate so the two can never drift again.


def _content_gate_reason(ws: Path, stage_name: str) -> str | None:
    """Rule 12 content gates for verdict-carrying artifacts — SINGLE source of truth.

    Returns a human-actionable reason when the stage's artifact exists but SAYS
    fail; None when the gate passes or does not apply. Called by BOTH
    `verify_stage()` (rich ERROR messaging on the direct path) and
    `_stage_complete()` (so `next_stage()`'s RC-A auto-satisfy branch can never
    record a failed gate as 'completed' on a later bare invocation).

    History (2026-07-06, loamwpseo0706): v3.35.2 added these gates only to
    verify_stage(). A bare `run_pipeline` call after a failed verify-post hit
    RC-A, which decided completion via _artifact_valid() (existence/provenance
    only), recorded the FAILED stage completed, and reported the pipeline
    COMPLETE — an intra-file Rule 11 fan-out miss producing exactly the Rule 12
    disease the release was meant to kill. Two paths answering "is this stage
    done?" must read the same fact; this helper IS that fact."""
    if stage_name == "fact-check-and-citation":
        p = ws / "fact-check.json"
        if not p.exists():
            return None
        try:
            verdict = str(json.loads(p.read_text(encoding="utf-8")).get("verdict", "")).strip().upper()
        except Exception:
            return None  # unreadable file is handled by _artifact_valid/missing paths
        cls = fc_verdict.classify(verdict)
        if cls == "block":
            return (
                f"fact-check verdict is {verdict}: issues found that must be resolved. "
                "Fix the draft (apply in_text_replacements, re-source or soften flagged claims, "
                "regenerate any wrong chart), then RE-DISPATCH the fact-checker so it "
                "re-verifies the edited draft and writes a fresh CLEAN verdict. Do NOT "
                "hand-edit the verdict field — the provenance check is designed to catch that."
            )
        if cls == "unknown":
            # Fail CLOSED (2026-08-02): pre-cure this open-world denylist let
            # 'BLOCKED - DO NOT PUBLISH' record the stage as completed while a
            # benign 'issues_fixed' died only at pre-publish — Rule-12 twin-gate
            # drift. Unknown means the producer broke the contract.
            return (
                f"fact-check verdict '{verdict}' is not a recognized verdict — unknown "
                f"verdicts fail closed. The fact-checker must re-emit fact-check.json "
                f"with a canonical verdict ({fc_verdict.CANONICAL_ENUM})."
            )
        return None

    if stage_name == "independent-reviewer":
        p = ws / "review.json"
        if not p.exists():
            return None
        try:
            _score = int(json.loads(p.read_text(encoding="utf-8")).get("score", 0))
            _state = json.loads((ws / "state.json").read_text(encoding="utf-8"))
            _target = review_target(_state)
        except Exception:
            return None  # unreadable artifacts: leave to provenance/missing checks
        if _score < _target:
            return (
                f"review.json score {_score} < state.brief.quality_target_score {_target}. "
                "Repair the draft per review.json would_change[], then RE-DISPATCH the "
                "independent reviewer for a fresh provenance-stamped score. Do NOT edit the score."
            )
        return None

    if stage_name == "verify-post":
        p = ws / "verify-result.json"
        if not p.exists():
            return None
        try:
            _vr = json.loads(p.read_text(encoding="utf-8"))
            _overall_pass = _vr.get("overall_pass")
            _fail_count = _vr.get("fail_count", 0 if _overall_pass else 1)
            _failed_ids = [c.get("id") for c in (_vr.get("checks") or []) if not c.get("passed", True)]
        except Exception:
            _overall_pass, _fail_count, _failed_ids = None, 1, []
        if _overall_pass is False or (_overall_pass is None and _fail_count):
            return (
                f"verify-result.json overall_pass=False (fail_count={_fail_count}, "
                f"failed_checks={_failed_ids}). The live/preview post has a real defect. Fix the "
                "underlying draft/schema/publish-result issue, re-run wordpress-publisher (PATCH, "
                "idempotent) to push the fix, then RE-DISPATCH verify-post for a fresh result. "
                "Do NOT hand-edit verify-result.json to force overall_pass=true."
            )
        return None

    if stage_name == "image-pipeline-join":
        # v3.41.3 (Rule 12): the join was a bare existence CHECK — images.json
        # had no schema and no content gate, so nothing machine-arbitrated what
        # it must SAY. On 2026-07-19 that vacuum let the driving session invent
        # a phantom field contract (local_path/status) and "reconcile" three
        # healthy files; symmetrically, a genuinely broken manifest (missing
        # slot, dangling path) would have sailed through to image-visual-qa.
        # The gate: every slot declared in image-prompts.json has an entry, and
        # every entry's path resolves to a real file (relative paths tolerated
        # against the plugin root — write_artifacts stored one verbatim on
        # 2026-07-19).
        imgs_p = ws / "images.json"
        prompts_p = ws / "image-prompts.json"
        if not imgs_p.exists() or not prompts_p.exists():
            return None  # existence handled by the normal missing-artifact path
        try:
            entries = json.loads(imgs_p.read_text(encoding="utf-8"))
            prompts = json.loads(prompts_p.read_text(encoding="utf-8"))
        except Exception:
            return "images.json or image-prompts.json is unreadable JSON."
        if not isinstance(entries, list):
            return "images.json must be a LIST of slot entries (schemas/images.schema.json)."
        plist = prompts if isinstance(prompts, list) else (
            prompts.get("slots") or prompts.get("images") or prompts.get("prompts")
            or prompts.get("image_prompts") or [])
        declared = {s.get("slot_id") for s in plist if isinstance(s, dict) and s.get("slot_id")}
        present = {e.get("slot_id") for e in entries if isinstance(e, dict)}
        missing_slots = sorted(declared - present)
        if missing_slots:
            return (
                f"images.json is missing entries for declared slot(s) {missing_slots}. "
                "The producing executor (chart-render / image fork) has not merged them — "
                "re-run it; do NOT hand-author entries."
            )
        _root = WS_ROOT.parent.parent
        dangling = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            raw = str(e.get("path") or "")
            if not raw:
                dangling.append(f"{e.get('slot_id')}:<empty path>")
                continue
            p = Path(raw)
            if not p.is_absolute():
                p = _root / p
            if not p.exists():
                dangling.append(f"{e.get('slot_id')}:{raw}")
        if dangling:
            return (
                f"images.json entries point at missing files: {dangling}. Re-run the "
                "producing executor for those slots (render_data_charts / image fork); "
                "do NOT hand-edit paths."
            )
        return None

    if stage_name == "cta-brief-builder":
        # 2026-08-12 release audit (Rule 12/14): the v3.42.4 `resolution_failed`
        # sentinel was PRODUCER-only — cta_brief_builder wrote it and exited 1,
        # but no completion-deciding path read it. _cta_brief_present() correctly
        # derives False (there is no usable offer), which auto-skips the four CTA
        # stages — the exact behavior reserved for a project with NO
        # conversion_offers — so a configured project whose catalog was
        # unreachable/empty shipped every article with no CTA while the runner
        # reported COMPLETE. The sentinel split exists to tell "sells nothing"
        # from "sells things, offers unreachable"; this gate is its READER, in
        # the ONE shared helper both verify_stage() and next_stage()'s RC-A
        # auto-satisfy call (the v3.35.3 lesson). The legitimate
        # skipped_no_config sentinel keeps passing, so the 5 projects without
        # conversion_offers continue to auto-skip quietly.
        p = ws / "cta-brief.json"
        if not p.exists():
            return None
        try:
            brief = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None  # unreadable file is handled by _artifact_valid/missing paths
        if isinstance(brief, dict) and brief.get("resolution_failed") is True:
            cause = str(brief.get("resolution_failure_reason") or "no reason recorded")
            return (
                f"cta-brief.json says resolution_failed=true: this project HAS "
                f"conversion_offers config but the offers could not be resolved — "
                f"{cause} Fix the underlying config/catalog, then re-run "
                "cta-brief-builder for a fresh brief. Do NOT hand-edit the "
                "sentinel: a failed resolution must never be recorded as the "
                "no-config auto-skip."
            )
        return None

    return None


def _stage_complete(stage: Stage, ws: Path) -> bool:
    # An EXPLICIT skip (operator decision, logged reason) resolves an optional stage.
    if _checklist_status(ws, stage.name) == "skipped":
        return True
    # Execution evidence (unique artifact and/or shared-artifact keys) must hold,
    # regardless of any checklist flag. This closes the honour-system hole: a stage
    # that defines evidence cannot be "complete" without it actually existing.
    if stage.evidence_artifact or stage.evidence_keys:
        ok, _ = _evidence_ok(stage, ws)
        if not ok:
            return False
    if stage.expected_outputs:
        if not all(_artifact_valid(ws, o) for o in stage.expected_outputs):
            return False
        # Rule 12 (v3.35.3): existence is not the fact. A verdict-carrying artifact
        # that SAYS fail must not auto-satisfy its stage — otherwise RC-A records the
        # failed stage 'completed' on the next bare invocation and the runner lies
        # COMPLETE (the 2026-07-06 verify-post seam found live in the loamwright batch).
        if _content_gate_reason(ws, stage.name):
            return False
        return True
    # No declared outputs. If the stage carries evidence, the check above already
    # passed -> complete. Otherwise (e.g. image-pipeline-fork BACKGROUND launch),
    # fall back to the checklist record.
    if stage.evidence_artifact or stage.evidence_keys:
        return True
    return _checklist_status(ws, stage.name) == "completed"


def _lint_passed(ws: Path, filename: str) -> bool:
    p = ws / filename
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("passed", False)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False


def _schema_forbidden_types_text(project_slug: str) -> str:
    """Compute the schema-generator 'Forbidden body types' clause from THIS
    project's actual business-context.json :: wordpress.seo_plugin_schema_provided,
    instead of a hardcoded project-charlie-derived list. Root cure for the loamwright
    CITE I01-I10 scoring gap (2026-07-08): business-context.json had no `wordpress`
    key at all, so cite_scorer.py correctly credited nothing from head schema, while
    this dispatch_prompt used to hardcode "Forbidden: Article, BlogPosting,
    Organization, Person, WebPage, WebSite, ImageObject, BreadcrumbList" regardless
    of the project's actual config or its absence -- two independent code paths
    silently disagreeing about the same fact (Rule 9/12 disease). See
    subskills/optimize/schema-generator/SKILL.md's "SEO-plugin coordination" section
    for the documented contract this now actually implements: read the project's
    provided list; when absent, "no policy declared" applies (legacy: emit freely).
    """
    if not project_slug:
        return ("Forbidden body types: standalone top-level HowTo/Dataset/SpecialAnnouncement/Q&A "
                "(deprecated rich-result types; T09 veto). No project context available to resolve "
                "wordpress.seo_plugin_schema_provided, so treat this as 'no policy declared'.")
    bc_path = PLUGIN_ROOT / "projects" / project_slug / "business-context.json"
    provided: list[str] = []
    if bc_path.exists():
        try:
            bc = json.loads(bc_path.read_text(encoding="utf-8"))
            provided = list((bc.get("wordpress") or {}).get("seo_plugin_schema_provided") or [])
        except Exception:
            provided = []
    always_forbidden = "standalone top-level HowTo/Dataset/SpecialAnnouncement/Q&A (deprecated rich-result types; T09 veto)"
    if provided:
        head_list = ", ".join(provided)
        return (
            f"Forbidden body types: {head_list} (per THIS project's business-context.json :: "
            f"wordpress.seo_plugin_schema_provided -- RankMath/the SEO plugin already emits these "
            f"in <head> on every post; duplicating them in the body fragments @id entity-linking), "
            f"AND {always_forbidden}."
        )
    return (
        f"No head-emitted-schema policy declared for project '{project_slug}' "
        f"(business-context.json has no wordpress.seo_plugin_schema_provided list). Per "
        f"subskills/optimize/schema-generator/SKILL.md's documented fallback, this means "
        f"'no policy declared -> legacy behavior applies': you MAY emit standard supplemental "
        f"types (Organization, Person, WebPage, WebSite, ImageObject, BreadcrumbList, Article, "
        f"BlogPosting) if genuinely useful, since nothing here confirms the SEO plugin already "
        f"covers them in <head>. Still forbidden: {always_forbidden}. "
        f"(If you can confirm empirically what the live <head> actually emits for this project, "
        f"prefer skipping those types anyway and flag the project-config gap in your report.)"
    )


def _render_dispatch_prompt(dispatch_prompt: str, task_id: str, state: dict) -> str:
    """Template a Stage's dispatch_prompt with task/project-specific values.

    Extracted from next_stage() (2026-07-08, Rule 10) so this seam is directly
    testable without assembling a full ~19-stage workspace fixture just to reach
    a stage buried deep in STAGES — the extraction changes nothing about behavior,
    only makes the substitution independently callable.
    """
    ws = str(_ws(task_id))
    project_slug = state.get("project_slug", "")
    primary_kw = state.get("brief", {}).get("primary_keyword", "")
    prompt = dispatch_prompt.replace("{task_id}", task_id)
    prompt = prompt.replace("{ws}", ws)
    prompt = prompt.replace("{project_slug}", project_slug)
    prompt = prompt.replace("{primary_keyword}", primary_kw)
    if "{schema_forbidden_types}" in prompt:
        prompt = prompt.replace("{schema_forbidden_types}", _schema_forbidden_types_text(project_slug))
    return prompt


def _resolve_command(stage: Stage, task_id: str, state: dict) -> str | None:
    if stage.executor.startswith("BASH:"):
        cmd = stage.executor[5:]
    elif stage.executor.startswith("BACKGROUND:"):
        cmd = stage.executor[11:]
    else:
        return None
    ws = str(_ws(task_id))
    project_slug = state.get("project_slug", "")
    primary_kw = state.get("brief", {}).get("primary_keyword", "")
    pr = _ws(task_id) / "publish-result.json"
    post_id = ""
    if pr.exists():
        try:
            post_id = str(json.loads(pr.read_text(encoding="utf-8")).get("post_id", ""))
        except Exception:
            pass
    cmd = cmd.replace("{task_id}", task_id)
    cmd = cmd.replace("{ws}", ws)
    cmd = cmd.replace("{project_slug}", project_slug)
    cmd = cmd.replace("{primary_keyword}", primary_kw)
    cmd = cmd.replace("{post_id}", post_id)
    if "{post_id}" in stage.executor and not post_id:
        return None
    return cmd


def next_stage(task_id: str) -> dict:
    ws = _ws(task_id)
    if not ws.exists():
        return {"stage": None, "status": "ERROR", "reason": f"Workspace {task_id} not found"}

    state = _read_state(task_id)

    # v3.41.3 — validate FRESH tasks against state.schema.json BEFORE any stage
    # runs. A brief with an invalid enum (`intent_override:
    # "commercial-investigation"`, 2026-07-19) previously sailed through
    # research + plan + build and only failed at assemble.py's mid-pipeline
    # validation, after ~10 stages of spend. The runner path (_read_state) is a
    # raw json.loads by design (legacy workspaces predate newer schema
    # constraints), so the gate applies ONLY to genuinely fresh tasks — no
    # stage_history AND no checklist records — exactly the ones whose brief was
    # just seeded and is still cheap to fix.
    def _is_fresh_task() -> bool:
        if state.get("stage_history"):
            return False
        clp = ws / "pipeline-checklist.json"
        if clp.exists():
            try:
                if (json.loads(clp.read_text(encoding="utf-8")).get("stages") or {}):
                    return False
            except Exception:
                return False
        return True

    if state and _is_fresh_task() and isinstance(state.get("brief"), dict):
        # Validate the BRIEF sub-object only (the observed failure class:
        # invalid enum values seeded at task creation). Full-state validation
        # stays where it always was (file_bus.write/read_state + assemble);
        # demanding the complete canonical state shape here would break
        # legitimately minimal test fixtures and hand-seeded workspaces whose
        # briefs are fine.
        try:
            import jsonschema

            _schema_p = Path(__file__).resolve().parents[2] / "schemas" / "state.schema.json"
            _brief_schema = (
                json.loads(_schema_p.read_text(encoding="utf-8"))
                .get("properties", {})
                .get("brief")
            )
            if _brief_schema:
                jsonschema.validate(state["brief"], _brief_schema)
        except jsonschema.ValidationError as exc:
            return {
                "stage": None,
                "status": "ERROR",
                "action": "ERROR",
                "reason": (
                    "state.json brief fails schemas/state.schema.json on a FRESH "
                    f"task (fix the brief before any spend): {exc.message} at "
                    f"brief/{'/'.join(str(p) for p in exc.absolute_path)}"
                ),
            }
        except Exception:
            pass  # schema unreadable / jsonschema absent: never block on the gate itself

    completed = []
    skipped = []

    for stage in STAGES:
        if not _check_stage_condition(stage, state):
            skipped.append(stage.name)
            # Audit-trail completeness (2026-07-06): root CLAUDE.md documents
            # conditional stages as "auto-skipped with a LOGGED skipped status",
            # but this branch previously just continued — the loamwright 3-article
            # batch shipped with local-uniqueness-check absent from stage_history
            # entirely. Record the auto-skip once (idempotent via checklist guard)
            # so audits can distinguish "condition not met" from "never considered".
            # v3.38.3: same both-stores guard as the RC-A stamp below — a checklist
            # record with a hand-truncated stage_history left conditional stages
            # permanently absent from the history (caught by the reset seam test).
            if (_checklist_status(ws, stage.name) not in ("completed", "skipped")
                    or _history_status(ws, stage.name) not in ("completed", "skipped")):
                _record_stage(task_id, stage.name, "skipped",
                              f"auto-skipped: condition {stage.condition_field}="
                              f"{stage.condition_value!r} not met")
            continue

        if _stage_complete(stage, ws):
            completed.append(stage.name)
            # RC-A (2026-06-04 audit): a stage whose completion is auto-satisfied by
            # an artifact a prior stage/process produced — serp_features/competitors
            # folded into research.json, or images.json produced by the background
            # fork for image-pipeline-join — is detected as done HERE but was never
            # stamped, because recording lived only in verify_stage (which such
            # auto-satisfied stages never reach). Stamp it now so the stage_history /
            # pipeline-checklist audit trail has zero silent gaps. Idempotent: the
            # guard skips anything already recorded completed/skipped, and RC-B
            # ensures a FAILED gate is NOT _stage_complete, so it is never recorded
            # complete here.
            # v3.38.3 (2026-07-10 project-kilo re-angle incident): the stamp guard used
            # to read ONLY the checklist. A hand-edited workspace (stage_history
            # truncated for a "reset", checklist left intact) then satisfied the
            # guard, so 6 auto-satisfied stages were never re-stamped into
            # stage_history — a permanently desynced audit trail with silent gaps.
            # The guard now asks BOTH record stores and re-stamps whichever is
            # missing (preserving an explicit 'skipped' status), so the audit
            # trail self-heals. NOTE this heals RECORDS only — it does not re-run
            # work; forcing a re-run is the sanctioned `--action reset` below.
            _cl_status = _checklist_status(ws, stage.name)
            _hist_status = _history_status(ws, stage.name)
            if _cl_status not in ("completed", "skipped") or _hist_status not in ("completed", "skipped"):
                _stamp = _cl_status if _cl_status in ("completed", "skipped") else (
                    _hist_status if _hist_status in ("completed", "skipped") else "completed")
                _record_stage(task_id, stage.name, _stamp)
                # Finding 3 (generalized, v3.38.0): _record_stage() may persist
                # NEW state.json fields as a side effect of recording a stage
                # complete (e.g. cta_brief_present for "cta-brief-builder" —
                # see the special case inside _record_stage). The in-memory
                # `state` dict used to evaluate a LATER conditional stage's
                # condition in THIS SAME next_stage() loop is otherwise still
                # the pre-update read: it would see the stale (absent/False)
                # value, record that later stage "skipped", and — because a
                # skip is terminal (_stage_complete short-circuits on it) —
                # that stage would NEVER run even once state.json on disk is
                # correct. Originally this was patched ONLY for
                # stage.name == "cta-brief-builder"; that name-keyed special
                # case would silently reproduce the exact same bug for ANY
                # future stage whose completion writes a new condition field.
                # Re-reading the WHOLE state from disk here is general by
                # construction: it picks up cta_brief_present today and
                # whatever field a future RC-A-satisfied stage writes,
                # without this call site needing to know the stage's name.
                state = _read_state(task_id)
            continue

        inputs_ready = all(
            _artifact_valid(ws, i) if i in _PROVENANCE_REQUIRED else _artifact_exists(ws, i)
            for i in stage.required_inputs
        )

        if not stage.is_mandatory:
            if not inputs_ready:
                skipped.append(stage.name)
                continue
        if not inputs_ready:
            missing = []
            for i in stage.required_inputs:
                if i in _PROVENANCE_REQUIRED:
                    if not _artifact_valid(ws, i):
                        missing.append(f"{i} (provenance invalid or missing)")
                elif not _artifact_exists(ws, i):
                    missing.append(i)
            return {
                "stage": stage.name,
                "status": "BLOCKED",
                "phase": stage.phase,
                "reason": f"Missing required inputs: {missing}",
                "missing_inputs": missing,
                "pipeline_progress": {
                    "completed": len(completed),
                    "total": len(STAGES),
                    "pct": round(len(completed) / len(STAGES) * 100, 1),
                },
            }

        _record_stage(task_id, stage.name, "in_progress")

        result: dict = {
            "stage": stage.name,
            "status": "READY",
            "phase": stage.phase,
            "executor": stage.executor.split(":")[0],
            "description": stage.description,
            "required_inputs": stage.required_inputs,
            "expected_outputs": stage.expected_outputs,
            "is_mandatory": stage.is_mandatory,
            "command": _resolve_command(stage, task_id, state),
            "pipeline_progress": {
                "completed": len(completed),
                "total": len(STAGES),
                "pct": round(len(completed) / len(STAGES) * 100, 1),
            },
        }
        if stage.subagent_type:
            result["subagent_type"] = stage.subagent_type
        if stage.name in SUBAGENT_ENFORCED_STAGES:
            result["subagent_enforced"] = True
            result["enforcement_warning"] = (
                f"MANDATORY: Stage '{stage.name}' MUST be dispatched via Agent(subagent_type='{stage.subagent_type}'). "
                f"Writing the output artifact directly will fail provenance validation. "
                f"The orchestrator checks _generated_by field on {stage.expected_outputs}."
            )
        if stage.dispatch_prompt:
            result["dispatch_prompt"] = _render_dispatch_prompt(stage.dispatch_prompt, task_id, state)
        return result

    _stamp_pipeline_complete(task_id)
    return {
        "stage": None,
        "status": "PIPELINE_COMPLETE",
        "completed": completed,
        "skipped": skipped,
        "pipeline_progress": {
            "completed": len(completed),
            "total": len(STAGES),
            "pct": 100.0,
        },
    }


def verify_stage(task_id: str, stage_name: str) -> dict:
    ws = _ws(task_id)
    stage = next((s for s in STAGES if s.name == stage_name), None)
    if not stage:
        return {"stage": stage_name, "passed": False, "reason": f"Unknown stage: {stage_name}"}

    found: list[str] = []
    missing: list[str] = []
    for o in stage.expected_outputs:
        if _artifact_valid(ws, o):
            found.append(o)
        else:
            missing.append(o)

    # Execution evidence (unique artifact and/or shared-artifact keys).
    ev_ok, ev_missing = _evidence_ok(stage, ws)
    missing.extend(ev_missing)

    # The honour-system pass is GONE. A stage with neither outputs nor evidence is
    # only auto-recordable when it is a BACKGROUND launch (image-pipeline-fork),
    # whose real output (images.json) is checked later at the JOIN. Any other
    # work-stage with no evidence cannot be verified and must be wired with an
    # evidence_artifact, or explicitly skipped via `--action skip`.
    has_check = bool(stage.expected_outputs or stage.evidence_artifact or stage.evidence_keys)
    if not has_check:
        if stage.executor.startswith("BACKGROUND") or stage.name == "image-pipeline-fork":
            _record_stage(task_id, stage_name, "completed")
            return {"stage": stage_name, "passed": True,
                    "reason": "Background launch recorded (real output verified later at JOIN)."}
        return {"stage": stage_name, "passed": False,
                "reason": ("Stage defines no expected_outputs and no evidence_artifact, so its execution "
                           "cannot be verified. This is a wiring bug — add an evidence_artifact to the Stage "
                           "definition. To intentionally skip an optional stage, use "
                           f"`--action skip --stage {stage_name} --reason \"...\"`.")}

    passed = len(missing) == 0

    # Content gates for verdict-carrying artifacts (fact-check verdict 2026-06-29,
    # review score 2026-07-01, verify-post overall_pass 2026-07-05). Since v3.35.3
    # the checks live in ONE shared helper, `_content_gate_reason()`, used by both
    # this direct path AND `_stage_complete()` (next_stage's RC-A auto-satisfy) —
    # the 2026-07-06 COMPLETE-lie seam was these gates existing only here, so a
    # bare re-invocation after a gate ERROR silently recorded the stage completed.
    _gate_reason: str | None = None
    if passed:
        _gate_reason = _content_gate_reason(ws, stage_name)
        if _gate_reason:
            passed = False
            missing.append(_gate_reason)

    if passed:
        _record_stage(task_id, stage_name, "completed")

    extra = {}
    if "render-lint.json" in found:
        extra["render_lint_passed"] = _lint_passed(ws, "render-lint.json")
    if "image-placeholder-lint.json" in found:
        extra["image_placeholder_passed"] = _lint_passed(ws, "image-placeholder-lint.json")
    if "fact-check.json" in found:
        try:
            fc = json.loads((ws / "fact-check.json").read_text(encoding="utf-8"))
            extra["fact_check_verdict"] = fc.get("verdict", "UNKNOWN")
        except Exception:
            pass
    if "review.json" in found:
        try:
            rv = json.loads((ws / "review.json").read_text(encoding="utf-8"))
            extra["review_score"] = rv.get("score", 0)
        except Exception:
            pass
    if stage.evidence_artifact == "geo-audit.json" and _artifact_valid(ws, "geo-audit.json"):
        try:
            ga = json.loads((ws / "geo-audit.json").read_text(encoding="utf-8"))
            extra["geo_cite_score"] = ga.get("cite_score")
            extra["geo_core_eeat_score"] = ga.get("core_eeat_score")
        except Exception:
            pass

    result = {
        "stage": stage_name,
        "passed": passed,
        "outputs_found": found,
        "outputs_missing": missing,
        **extra,
    }
    if _gate_reason:
        result["reason"] = _gate_reason
    return result


def reset_to_stage(task_id: str, stage_name: str, reason: str = "") -> dict:
    """Sanctioned workspace reset: make `stage_name` and everything AFTER it re-run.

    WHY (2026-07-09 project-kilo re-angle incident, v3.38.3): completion state is
    persisted in THREE stores — state.json::stage_history, pipeline-checklist.json,
    and the artifacts themselves (expected_outputs + evidence_artifact files). An
    operator hand-reset that truncates stage_history and deletes the primary
    artifacts but misses the checklist and the *-result.json evidence files leaves
    _stage_complete() satisfied, so the runner silently jumps the "reset" stages
    (6 stages were skipped that way in a real batch: chart-render,
    image-pipeline-fork, citation-inject, finalize-references-signature,
    chart-rerender, category-selector). Hand-rolled resets cannot win against three
    distributed stores; this action clears ALL three atomically, deriving the
    deletion set from the STAGES table itself (single source of truth — Rule 6).

    Semantics and limits:
      - Stages strictly BEFORE `stage_name` are untouched (research is preserved).
      - Resetting to a stage at-or-before `assembly` yields a clean rebuild.
        Resetting to a LATER stage clears records/evidence so those stages re-run,
        but in-place draft.md edits by already-run downstream stages are NOT
        reverted (the re-editing stages are idempotent by design; still, prefer a
        fresh task_id for a full re-angle — see skills/seo-blog SKILL.md).
      - Refuses to run while a run_pipeline driver holds the workspace lock.
      - Cannot undo WordPress side effects: if a post was already created, it is
        reported as a warning, never deleted.
    """
    ws = _ws(task_id)
    if not ws.exists():
        return {"passed": False, "error": f"Workspace {task_id} not found"}
    idx = next((i for i, s in enumerate(STAGES) if s.name == stage_name), None)
    if idx is None:
        return {"passed": False,
                "error": f"Unknown stage '{stage_name}'. Valid: {[s.name for s in STAGES]}"}
    # Liveness must be decided by trying to TAKE the OS advisory lock, never by the
    # sidecar's existence. run_pipeline deliberately leaves {ws}/.pipeline-driver.lock
    # on disk after a normal release (the docs say "never delete the lock sidecar"), so
    # an `.exists()` test is true forever after the first driver run — which made this
    # guard refuse to reset ANY workspace a driver had ever touched, rendering the
    # sanctioned `--action reset` path permanently unreachable (found 2026-07-14, while
    # trying to re-arm the gates after a legitimate post-review draft edit).
    if file_lock.is_locked(ws / ".pipeline-driver"):
        return {"passed": False,
                "error": "A run_pipeline driver is ACTIVELY holding this workspace's lock "
                         "(.pipeline-driver.lock). Never reset under an active driver; "
                         "wait for it to return (v3.36.2 one-driver rule)."}

    import shutil
    tail = STAGES[idx:]
    tail_names = [s.name for s in tail]
    warnings: list[str] = []

    # WordPress side effects are irreversible from here — surface, never delete.
    if "wordpress-publisher" in tail_names and (ws / "publish-result.json").exists():
        try:
            pub = json.loads((ws / "publish-result.json").read_text(encoding="utf-8"))
            warnings.append(
                f"wordpress-publisher already ran (post_id={pub.get('post_id')}, "
                f"status={pub.get('status')}). The WP post is NOT deleted by reset — "
                f"handle it manually (delete the draft or expect the publisher's "
                f"idempotency pre-check to reuse it).")
        except (json.JSONDecodeError, UnicodeDecodeError):
            warnings.append("wordpress-publisher already ran (publish-result.json "
                            "unreadable). The WP post is NOT deleted by reset.")

    # 1) Delete artifacts: expected_outputs + evidence_artifact from the Stage
    #    table, plus per-stage extras for shared artifacts stages MERGE into
    #    (images.json is written by BOTH chart-render and the photo fork, so it
    #    is not any single stage's expected_output).
    _RESET_EXTRAS: dict[str, list[str]] = {
        "chart-render": ["images.json"],
        "image-pipeline-fork": ["images.json", "images/"],
    }
    deleted: list[str] = []
    for s in tail:
        # A CHECK stage VERIFIES an artifact; it never PRODUCES one. Its
        # "expected_outputs" is really a precondition someone upstream wrote. Deleting
        # it is therefore always wrong, and when the real producer sits BEFORE the reset
        # point (so it will not re-run) it is a hard deadlock: image-pipeline-join is a
        # CHECK on images.json, which is written by image-pipeline-fork/chart-render back
        # in the plan phase. Resetting to any post-fork stage used to delete images.json
        # and then WAIT forever for a fork that would never run again, orphaning ~30MB of
        # already-paid-for 4K renders on disk (found 2026-07-14 resetting to render-lint
        # after a post-review draft edit).
        #
        # Stages that legitimately REGENERATE images.json (chart-render,
        # image-pipeline-fork) still clear it via _RESET_EXTRAS below.
        names = [] if s.executor == "CHECK" else list(s.expected_outputs)
        if s.evidence_artifact:
            names.append(s.evidence_artifact)
        names.extend(_RESET_EXTRAS.get(s.name, []))
        for name in names:
            if name.endswith("/"):
                d = ws / name.rstrip("/")
                if d.is_dir():
                    shutil.rmtree(d)
                    deleted.append(name)
            else:
                p = ws / name
                if p.exists():
                    p.unlink()
                    deleted.append(name)

    # 2) Clear BOTH record stores for the tail stages.
    records_removed: list[str] = []
    state_path = ws / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        before = state.get("stage_history", [])
        kept = [h for h in before if h.get("stage") not in tail_names]
        records_removed.extend(sorted({h.get("stage") for h in before
                                       if h.get("stage") in tail_names}))
        state["stage_history"] = kept
        state["phase"] = tail[0].phase
        state["current_stage"] = stage_name
        if "cta-brief-builder" in tail_names:
            state.pop("cta_brief_present", None)
        if reason:
            state.setdefault("reset_log", []).append({
                "reset_to": stage_name, "reason": reason,
                "at": datetime.now(timezone.utc).isoformat()})
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    checklist_path = ws / "pipeline-checklist.json"
    if checklist_path.exists():
        try:
            cl = json.loads(checklist_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            cl = {"task_id": task_id, "stages": {}}
        for n in tail_names:
            cl.get("stages", {}).pop(n, None)
        checklist_path.write_text(json.dumps(cl, indent=2, ensure_ascii=False),
                                  encoding="utf-8")

    # 3) Project-level rolling CTA history: drop THIS task's fingerprints if the
    #    recording stage is being re-run, or the diversity gate will later count
    #    the pre-reset CTA against the re-written one.
    if "cta-record-history" in tail_names and state_path.exists():
        slug = json.loads(state_path.read_text(encoding="utf-8")).get("project_slug", "")
        hist_path = PLUGIN_ROOT / "projects" / slug / "cta-history.json" if slug else None
        if hist_path and hist_path.exists():
            try:
                hist = json.loads(hist_path.read_text(encoding="utf-8"))
                if isinstance(hist, list):
                    pruned = [e for e in hist if not (isinstance(e, dict)
                                                      and e.get("task_id") == task_id)]
                    if len(pruned) != len(hist):
                        hist_path.write_text(
                            json.dumps(pruned, indent=2, ensure_ascii=False),
                            encoding="utf-8")
                        records_removed.append(f"cta-history.json entries for {task_id}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                warnings.append(f"projects/{slug}/cta-history.json unreadable — "
                                f"stale CTA fingerprints for {task_id} may remain.")

    return {
        "passed": True,
        "reset_to": stage_name,
        "stages_reset": tail_names,
        "artifacts_deleted": deleted,
        "records_removed": records_removed,
        "warnings": warnings,
        "reason": reason,
    }


def skip_stage(task_id: str, stage_name: str, reason: str) -> dict:
    """Explicitly skip an OPTIONAL stage with a logged reason.

    This is the sanctioned alternative to silently marking an unrun stage 'completed'.
    Mandatory stages cannot be skipped. The skip is recorded as status='skipped'
    (not 'completed') in both state.json::stage_history and pipeline-checklist.json,
    so the audit trail is honest about what ran versus what was deliberately dropped."""
    stage = next((s for s in STAGES if s.name == stage_name), None)
    if not stage:
        return {"stage": stage_name, "passed": False, "reason": f"Unknown stage: {stage_name}"}
    if stage.is_mandatory:
        return {"stage": stage_name, "passed": False,
                "reason": f"Stage '{stage_name}' is MANDATORY and cannot be skipped. It must run and produce its artifacts."}
    if not reason or not reason.strip():
        return {"stage": stage_name, "passed": False,
                "reason": "--reason is required to skip a stage (the audit trail must record WHY)."}
    _record_stage(task_id, stage_name, "skipped", reason.strip())
    return {"stage": stage_name, "passed": True, "status": "skipped", "skip_reason": reason.strip()}


def pipeline_status(task_id: str) -> dict:
    ws = _ws(task_id)
    if not ws.exists():
        return {"error": f"Workspace {task_id} not found"}

    state = _read_state(task_id)
    completed = []
    remaining = []
    skipped = []
    current = None

    for stage in STAGES:
        if not _check_stage_condition(stage, state):
            skipped.append(stage.name)
            continue
        if _stage_complete(stage, ws):
            completed.append(stage.name)
        elif current is None and stage.is_mandatory:
            current = stage.name
            remaining.append(stage.name)
        else:
            remaining.append(stage.name)

    mandatory_stages = [s for s in STAGES if s.is_mandatory and _check_stage_condition(s, state)]
    mandatory_done = [s.name for s in mandatory_stages if _stage_complete(s, ws)]

    return {
        "task_id": task_id,
        "completed_stages": completed,
        "current_stage": current,
        "remaining_stages": remaining,
        "skipped_stages": skipped,
        "completion_pct": round(len(completed) / len(STAGES) * 100, 1),
        "mandatory_completed": len(mandatory_done),
        "mandatory_total": len(mandatory_stages),
        "phase": next((s.phase for s in STAGES if s.name == current), "complete"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline orchestrator")
    parser.add_argument("--workspace", default=None, help="Task ID (not needed for backfill-complete)")
    parser.add_argument("--action", required=True, choices=["next", "verify", "status", "skip", "reset", "backfill-complete"])
    parser.add_argument("--stage", default=None, help="Stage name (for verify/skip/reset)")
    parser.add_argument("--reason", default="", help="Why an optional stage is being skipped (required for skip) or the workspace is being reset")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.action == "backfill-complete":
        result = backfill_complete()
    elif args.action == "next":
        if not args.workspace:
            parser.error("--workspace required for next action")
        result = next_stage(args.workspace)
    elif args.action == "verify":
        if not args.stage:
            parser.error("--stage required for verify action")
        result = verify_stage(args.workspace, args.stage)
    elif args.action == "skip":
        if not args.stage:
            parser.error("--stage required for skip action")
        result = skip_stage(args.workspace, args.stage, args.reason)
    elif args.action == "reset":
        if not args.stage:
            parser.error("--stage required for reset action")
        result = reset_to_stage(args.workspace, args.stage, args.reason)
    elif args.action == "status":
        result = pipeline_status(args.workspace)
    else:
        parser.error(f"Unknown action: {args.action}")
        return

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if args.action == "next":
            if result.get("status") == "PIPELINE_COMPLETE":
                print(f"  Pipeline COMPLETE. {result['pipeline_progress']['completed']}/{result['pipeline_progress']['total']} stages done.")
            elif result.get("status") == "BLOCKED":
                print(f"  BLOCKED at {result['stage']} ({result['phase']})")
                print(f"  Missing: {result['missing_inputs']}")
            else:
                pct = result["pipeline_progress"]["pct"]
                print(f"  NEXT: {result['stage']} ({result['phase']}) [{pct:.0f}% complete]")
                print(f"  {result['description']}")
                if result.get("command"):
                    print(f"  Command: {result['command']}")
                if result["expected_outputs"]:
                    print(f"  Must produce: {result['expected_outputs']}")
        elif args.action == "verify":
            icon = "OK" if result["passed"] else "XX"
            print(f"  [{icon}] {result['stage']}: {'passed' if result['passed'] else 'FAILED'}")
            if result.get("outputs_missing"):
                print(f"  Missing: {result['outputs_missing']}")
            if not result["passed"] and result.get("reason"):
                print(f"  Reason: {result['reason']}")
        elif args.action == "skip":
            icon = "SKIP" if result["passed"] else "XX"
            print(f"  [{icon}] {result['stage']}: {result.get('reason') or result.get('skip_reason')}")
        elif args.action == "reset":
            if result.get("passed"):
                print(f"  [RESET] to '{result['reset_to']}': {len(result['stages_reset'])} stages re-armed, "
                      f"{len(result['artifacts_deleted'])} artifacts deleted")
                for w in result.get("warnings", []):
                    print(f"  WARNING: {w}")
            else:
                print(f"  [XX] reset failed: {result.get('error')}")
        elif args.action == "status":
            print(f"\n  Pipeline Status: {args.workspace}")
            print(f"  Progress: {result['completion_pct']:.0f}% ({result['mandatory_completed']}/{result['mandatory_total']} mandatory)")
            print(f"  Phase: {result['phase']}")
            if result["current_stage"]:
                print(f"  Current: {result['current_stage']}")
            print(f"  Completed: {len(result['completed_stages'])}")
            print(f"  Remaining: {len(result['remaining_stages'])}")
            if result["skipped_stages"]:
                print(f"  Skipped: {result['skipped_stages']}")

    if args.action == "next" and result.get("status") == "BLOCKED":
        sys.exit(1)
    elif args.action in ("verify", "skip", "reset") and not result.get("passed", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
