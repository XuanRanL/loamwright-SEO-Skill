---
name: phase-research
description: Run Phase 1 Research only — keyword research, SERP analysis, competitor analysis, content gap analysis, surface targeting. Use when user wants research-only output without writing an article. Triggered by /seo-blog research, "research this keyword", "what's the SERP for X", "competitor analysis for".
allowed-tools: [Read, Write, Bash, Task]
disable-model-invocation: false
---

# Phase Research Orchestrator

Run 6 research sub-skills in sequence, accumulate findings into `research.json`.
Stage 6 (community-research) is ALWAYS-ON.

## Inputs

- `state.json` with `state.brief.primary_keyword` required
- Optional `state.project_slug` for project-aware research (cache reuse, competitor exclusion)

## Stages

```
1. keyword-research        →  Tavily + Crossref + AI-search probe
                              + SerpApi autocomplete + related_questions (true PAA)
                              Output: primary keyword expansion + LSI + intent + PAA

2. serp-analysis           →  13 SERP features detection (Google + Bing + AIO)
                              SerpApi = REAL organic positions + featured snippet +
                              People-Also-Ask + AI Overview (structured, not generic search)
                              Output: serp_features[], top-10 URLs

3. competitor-analysis     →  top-5 competitor deep extract (5-tier waterfall)
                              Output: competitor_titles[] with content_gap

4. content-gap-analysis    →  5 frameworks: SEO/AI/FAQ/Format/Authority gaps
                              Output: content_gaps[] with opportunity_score

5. surface-targeting       →  User selects 1-5 surfaces (owned/serp/aio/chatgpt/pplx/claude/gemini/reddit/youtube)
                              Output: brief.target_surfaces[] updated

6. community-research      →  ALWAYS-ON Reddit + X pass (cost ≈ 0 via the Tavily pool).
                              Real executor (Rule 6 — not pseudo-code):
                                python -m scripts.research.community_research_runner \
                                  --topic "{primary_keyword}" --task-id {task_id} --sources reddit,x --json
                              Splits signal vs claim; multi-dimensionally verifies claims.
                              Output: research.json :: community_insights (signals + verified claims).
                              IRON RULE: community URLs never cited — a verified claim cites the
                              authoritative corroborating source, never the reddit.com/x.com URL.
                              Per-project subreddits/handles + on/off default in
                              business-context.json :: community_research (degrades gracefully if absent).
```

### SerpApi — structured SERP + AI Overview (fills the Tavily gap)

Tavily gives generic web search/extract; it does NOT return Google's ranked positions,
People-Also-Ask, featured snippet, or the AI Overview. For real SERP intelligence use the
pooled SerpApi wrapper (free 250 searches/mo per account, round-robin across the pool like
the Tavily key pool). Real executors (not pseudo-code):

```bash
# real organic positions + PAA + related searches + (if present) AI Overview block
python -m scripts.fetch.serpapi_query --engine google --q "{primary_keyword}" --gl us --hl en --json
# keyword expansion straight from Google
python -m scripts.fetch.serpapi_query --engine google_autocomplete --q "{primary_keyword}" --json
# is Google AI Overview triggered for this query? (core GEO signal; auto-follows page_token)
python -m scripts.fetch.serpapi_query --engine ai_overview --q "{primary_keyword}" --json
```

Remaining free quota across the pool: `python -m scripts._core.serpapi_pool --status`.
Degrades gracefully — if no SerpApi key is configured, skip these and fall back to Tavily.

**Engine selection — registry-driven, vertical-aware (do NOT reason over all ~110 engines).**
SerpApi has ~110 engines; a curated SEO-relevant subset is registered with their real query
params + the verticals/intents/surfaces that should trigger them. Get the shortlist for THIS
article, then call `serpapi_query` only for the 2-4 that fit:

```bash
# shortlist the engines worth calling for this article (deterministic, no quota cost)
python -m scripts._core.serpapi_engines --suggest --vertical {vertical} --intent {intent} --surfaces {surfaces} --json
#  → core (google, autocomplete, trends, ai_overview) for every article, PLUS e.g.
#    ecommerce (google_shopping, amazon, walmart) for a product review, or
#    local (google_local, google_maps, yelp) for a local topic, or youtube for a video surface.
# then run each suggested engine (the selector also tells you each engine's right query param):
python -m scripts.fetch.serpapi_query --engine {engine} --q "{primary_keyword}" --json
```

Discipline: always run the core 3-4 (`google` + `google_autocomplete` + `google_trends` +
`ai_overview`); add only the 1-3 vertical/surface engines the selector surfaces — don't call them
all. Full catalog: `python -m scripts._core.serpapi_engines --list`. Any of the ~110 engines is
still directly callable with `--engine X` even if it isn't in the registry.

## Cost guards

- Tavily basic = 1 credit, advanced = 2 credits
- SerpApi: free 250 searches/mo per pooled account, $0 on the free tier (rotates across the
  pool on quota, same as Tavily); usage still logged via cost_ledger for visibility
- Per stage: estimate before run, halt if exceeds budget
- Use `memory/research-cache/` for repeat queries within 24-72h (SerpApi cached 6h)

## Output

`workspace/{task_id}/research.json` conforming to `schemas/research.schema.json`.

## Handoff

`schemas/handoff.schema.json` with `recommended_next_skill = "format-selector"` (Plan phase).

## Failure modes

| Failure | Action |
|---|---|
| Tavily quota exhausted | Fall back to Crossref + cache-only research |
| SERP fetch fails | Try patchright (Tier 2) for blocked pages |
| AI probe all-engines fail | Mark `ai_engine_findings.probe_failed: true`, continue |
| No competitors found in top-10 | Expand SERP to top-20, lower confidence flag |

## See also

- `subskills/research/keyword-research/SKILL.md`
- `subskills/research/serp-analysis/SKILL.md`
- `subskills/research/competitor-analysis/SKILL.md`
- `subskills/research/content-gap-analysis/SKILL.md`
- `subskills/research/surface-targeting/SKILL.md`
- `subskills/research/community-research/SKILL.md`
