---
name: keyword-research
description: Deep keyword research via Tavily SERP + Crossref + AI-search probe. Builds research.json with intent, semantic clusters, PAA, competitor titles, SERP features, AI engine findings, content gaps. Triggered by phase-research orchestrator or directly when user requests keyword research for an article topic. ALWAYS the first stage for /article command. Use it whenever the user provides a keyword + wants to start the SEO writing pipeline OR asks "what should I write about for X" OR "research keyword X for me".
allowed-tools: [Read, Write, Bash, Task]
---

# Keyword Research

8-step pipeline producing the single source of truth for everything downstream: outline, drafter, fact-checker.

## Inputs

- `state.brief.primary_keyword` (required)
- `state.brief.secondary_keywords` (optional)
- `state.brief.industry` / `target_market_locale` (from active project if /init done)
- `state.brief.target_surfaces[]` — `["owned", "google-aio", "chatgpt", "perplexity", "claude", "gemini", "reddit", "youtube"]`

## Output

`workspace/{task_id}/research.json` per `schemas/research.schema.json`

## 9 stages (sequential)

> **Tooling note:** Use the Python scripts below (NOT the raw MCP tools). The scripts add
> key-pool rotation + retry (`scripts/_core/tavily_retry.py`), cost-ledger logging, and
> caching — none of which the MCP tools provide. If a script exhausts all keys and raises,
> fall back to the matching `mcp__tavily__tavily_*` MCP tool for that one call.

### Stage 0: Deep research overview (Tavily Research Pro — MANDATORY)

This is the single most important research call. Tavily Research Pro does iterative
multi-angle synthesis across dozens of sources, producing a comprehensive overview no
individual search can match. Every article MUST start with this call.

```
bash: python -m scripts.fetch.tavily_research "Comprehensive research on '{primary_keyword}' for the {industry} industry. Cover: current state, key players, recent developments 2024-2026, statistics, academic research, industry standards, misconceptions, emerging trends." --model pro --citation-format apa --task-id {task_id} --json
```
Save the full response to `workspace/{task}/research/deep-research.json`.
This becomes the foundation for all downstream stages.

### Stage 1: SERP top-10 baseline (Tavily advanced, 2 credits)
```
bash: python -m scripts.fetch.tavily_search "{primary_keyword}" --depth advanced --max 10 --task-id {task_id} --json
```
Result: top-10 SERP results with titles + URLs + rich snippets.

### Stage 2: Freshness signal (Tavily advanced, 2 credits)
```
bash: python -m scripts.fetch.tavily_search "{primary_keyword} 2025 2026" --depth advanced --max 10 --time-range year --task-id {task_id} --json
```
Compare to Stage 1: which results are fresh vs evergreen?

### Stage 3: PAA extraction (Tavily advanced, 2 credits)
```
bash: python -m scripts.fetch.tavily_search "{primary_keyword} faq frequently asked questions" --depth advanced --max 10 --task-id {task_id} --json
```
Use result snippets to extract PAA questions. Look for question-format strings.

### Stage 4: Competitor deep extract (Tavily extract ×5 URLs)
For top-5 SERP results (excluding own domain if /init detected):
```
bash: python -m scripts.fetch.tavily_extract <url1> <url2> <url3> <url4> <url5> --depth advanced --task-id {task_id} --json
```
Spawn `researcher` agent if extraction needs Crossref or page fetch fallbacks.

Extract from each competitor:
- Title (= competitor.titles[].title)
- Word count
- H2 structure (signals topical coverage)
- Schema types (Article, Product, FAQPage, etc.)
- Content gaps (what they DIDN'T cover well)

### Stage 5: Academic / authority backup (Crossref, free)
```
bash: python -m scripts.fetch.crossref_lookup "{primary_keyword}" --rows 5 --apa
```
Surfaces peer-reviewed sources for fact-checker downstream. Tier-1 source baseline.

### Stage 6: AI-Search engine probe (FUTURE — needs ai_search_probe.py)
For each target_surface in {chatgpt, perplexity, claude, gemini, google-aio}:
- Probe: "tell me about {primary_keyword}"
- Probe: "what's the best {primary_keyword}"
- Parse response → who does the AI cite? Our domain? Competitors?
- Build `ai_engine_findings[engine] = {our_domain_cited, competitors_cited, factual_accuracy}`

(Until ai_search_probe.py is built in M1.5, mark these `null` and continue.)

### Stage 7: Semantic clustering & LSI
Use LLM (Claude Opus) to:
- Read all titles + content gaps
- Extract semantic neighbor keywords (LSI)
- Cluster into 2-4 semantic groups
- Output `semantic_clusters[]`

### Stage 8: Intent classification + gap analysis
Based on top-10 SERP composition:
- Mostly listicles → intent = commercial
- Mostly how-to / step-by-step → intent = informational
- Mostly product/comparison → intent = commercial (this is the
  commercial-investigation case, but the STORED enum value is `commercial` —
  `schemas/state.schema.json` and `research.schema.json` accept only
  informational|commercial|transactional|navigational. The hyphenated
  "commercial-investigation" label is the ANALYST's vocabulary
  (`search_intent_analyzer` uses `commercial_investigation` internally); writing
  it into brief/state/research enums fails schema validation — it burned ~10
  stages of spend before the assemble-time check caught it on 2026-07-19; fresh
  tasks are now schema-gated at the first runner advance. Record the nuance in
  a `_intent_qualifier` side field if it matters downstream.)
- Mostly buy / coupon → intent = transactional

Identify content gaps (5 framework):
- **SEO gap**: keywords ranking #5-#20 we could move up
- **AI gap**: AI engines don't cite us; competitors get cited
- **FAQ gap**: PAA questions no one answers well
- **Format gap**: SERP missing certain format (no case studies; no comparison; etc.)
- **Authority gap**: no Tier-1 source in top-10 → we can be it

## Cost estimate (typical 1 article)

| Stage | API calls | Credits | $ |
|---|---|---|---|
| 1-3 | 3× Tavily basic | 3 | $0.024 |
| 4 | 1× Tavily extract (5 URLs) | 1 | $0.008 |
| 5 | 1× Crossref | 0 | $0 (free) |
| 6 | 0 (until M1.5) | 0 | $0 |
| 7-8 | 1× Claude Opus (LLM synthesis) | — | $0.05 |
| **Total** | | **4** | **~$0.08** |

100 articles/month: ~$8 keyword-research.

## Handoff

After Stage 8, write `workspace/{task_id}/research/handoff.json` per `schemas/handoff.schema.json`:
- `recommended_next_skill`: `format-selector` (in Plan phase)
- `key_findings[]`: top-5 SERP titles + top content gap + dominant intent

## Failure modes

| Failure | Mitigation |
|---|---|
| Tavily quota at 0 | Skip Stage 2 freshness; use Crossref + cached results only |
| Competitor extract returns thin content | Try researcher agent fallback (5-tier waterfall) |
| AI probe fails | Stage 6 mark `probe_failed: true`; continue |
| Crossref no results | Tier-2 sources only; flag in research.json |

## See also

- `agents/researcher.md` (executes the actual API calls)
- `scripts/fetch/tavily_search.py` / `tavily_extract.py` / `crossref_lookup.py`
- `schemas/research.schema.json` (output contract)
- `references/seo/blog-formats-2026.md` (Stage 8 intent → format mapping)
