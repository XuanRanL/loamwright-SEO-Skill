---
name: surface-targeting
description: User selects which surfaces to win (owned/google-serp/google-aio/chatgpt/perplexity/claude/gemini/reddit/youtube). Drives format choice + content style. From claude-blog Phase 0 pattern.
allowed-tools: [Read, Write, AskUserQuestion]
---

# Surface Targeting

The single most underused SEO decision: pick WHICH search surfaces you're trying to win BEFORE writing.

## 5 surfaces (per claude-blog catalog)

1. **owned** — your own site, blog, newsletter
2. **google-serp** — traditional Google search results
3. **google-aio** — Google AI Overviews (formerly SGE)
4. **ai-assistant** — ChatGPT / Perplexity / Claude / Gemini citations
5. **community** — Reddit, Quora, forums, YouTube comments

## Inputs
- `research.json` (serp_features + ai_engine_findings)
- `projects/{slug}/business-context.json` (target ai engines from brand config)

## Decision

Use AskUserQuestion to confirm:
- Which 1-3 surfaces matter most for THIS article?
- Or accept defaults from brand-config.target_ai_engines

## Output
Updates `state.brief.target_surfaces[]`:
```json
["google-aio", "ai-assistant-chatgpt", "owned"]
```

This drives:
- format-selector decision (chatgpt → listicle; pplx → case-study; claude → review)
- outline-architect (more Citation Capsules if ai-assistant; marks
  `is_featured_snippet_target` sections when the SERP shows featured_snippet/ai_overview)
- humanizer voice (more E-E-A-T for ai-assistant; more SEO density for google-serp)
- (v3.35: featured-snippet-optimizer and voice-search-optimizer are RETIRED — the
  extractive answer shape is owned by the citation-capsule-builder stage)

## Handoff
`recommended_next_skill`: `format-selector`
