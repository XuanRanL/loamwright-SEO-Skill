---
name: community-research
description: Always-on Reddit/X community research — fetch professional experience/insights/experimental results, split signal vs claim, multi-dimensionally verify claims. Signals feed writer/PAA/real-language; verified claims cite the authoritative corroborating source, never the community URL.
allowed-tools: [Read, Write, Bash]
---

# Community Research (Reddit + X)

Runs on EVERY article (cost ≈ 0 via the Tavily key-pool — NOT the official Reddit/X
API, which is approval-gated and commercially priced). Reddit/X URLs are **NEVER**
cited.

## Why this exists

Reddit and X host first-hand professional experience, expert opinions, and experimental
results that the SEO content database does not. Google increasingly ranks Reddit; AI
engines cite community discussion. Capturing this — verified — is a direct E-E-A-T and
content-uniqueness lever.

## Invocation (real executor — Rule 6, not pseudo-code)

```bash
python -m scripts.research.community_research_runner \
  --topic "{primary_keyword}" --task-id {task_id} --sources reddit,x --json
```

Reads `projects/{slug}/business-context.json :: community_research` for per-project
subreddits/handles and `default` (on/off). Writes
`memory/workspace/{task_id}/research/community-research.json` and merges a
`community_insights` key into `research.json`.

## Output contract

- **`signals`** (`real_language` / `pain_points` / `questions` / `contrarian_views` /
  `success_stories`) → used freely by writer + PAA. Never stated as fact, never cited.
- **`claims[]`** — each quarantined and scored on 4 dimensions
  (authoritative corroboration / community consensus / author credibility / engagement),
  with `verdict` + `writer_guidance`:
  - `state_as_fact_with_auth_cite` → writer may state as fact, citing
    `authoritative_source` (the corroborating authority — **NOT** the community URL).
  - `attributed_hedge_no_cite` → write as "some practitioners report…", no citation.
  - dropped if contradicted by an authoritative source.

## Iron rule

Community URLs (`reddit.com` / `x.com` / `twitter.com`) NEVER enter References,
in-text citations, body outbound links, or JSON-LD `citation`/`sameAs`. The community
URL is recorded as `source_url` provenance only. Enforced by
`tests/test_community_never_cited.py`.

## Handoff

`recommended_next_skill`: `surface-targeting` (or back to the phase-research orchestrator).
