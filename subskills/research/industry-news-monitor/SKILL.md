---
name: industry-news-monitor
description: "Weekly industry-news harvest — runs Tier-A deterministic connectors + Tier-B researcher arm, de-duplicates, cross-week filters, competitor-filters (Rule 8), ranks clusters by significance, and updates covered/issues state. Called by the /weekly skill (Step 3–4). NOT user-invocable standalone."
allowed-tools: [Read, Write, Bash]
user-invocable: false
disable-model-invocation: false
---

# Industry News Monitor — Harvest Subskill

This subskill documents the full harvest architecture for the weekly digest.
The `/weekly` skill orchestrates it (Steps 3–4); this file is the definitive
reference for how harvesting works and how to extend it.

---

## Harvest architecture: two tiers

```
Tier-A (deterministic, scriptable)        Tier-B (MCP / deep-web, researcher agent)
─────────────────────────────────         ──────────────────────────────────────────
RSS feeds                                 MCP tools (pubmed, tavily, biorxiv, etc.)
HackerNews search                         Community deep searches (Reddit/X)
GDELT news graph                          Specialised industry APIs
NewsAPI (paid, per-project)               Broad Tavily news searches
Community (Tavily reddit/x)               Paywalled trade publication extracts
Tavily topic="news" search                ─────────────────────────────────────────
─────────────────────────────             Writes: memory/workspace/{tid}/tier-b.json
Writes: memory/workspace/{tid}/           (NewsItem JSON array)
        news-digest.json (initial pass)   ↓
                                          Merged by runner via --extra-items flag
```

---

## Tier-A executor

### Invocation (Rule 6 — concrete bash command, not pseudo-code)

```bash
python -m scripts.research.industry_news_runner \
    --project {slug} \
    --task-id {tid} \
    [--extra-items memory/workspace/{tid}/tier-b.json] \
    [--lookback-days N] \
    [--window-weeks N] \
    --json
```

`scripts/research/industry_news_runner.py` is the single source of truth for Tier-A.
It reads `projects/{slug}/business-context.json :: weekly_digest.connectors` and
calls the enabled connector modules from `scripts/fetch/`.

### Single-pass harvest (Step 4 of /weekly)

The `/weekly` skill runs the runner **exactly once** with `--extra-items` pointing at the
researcher's `tier-b.json` output (written in Step 3).  The runner appends Tier-B items to
the Tier-A set before de-dup/filter/rank — it does NOT replace the Tier-A results:

```bash
python -m scripts.research.industry_news_runner \
    --project {slug} \
    --task-id {tid} \
    --extra-items memory/workspace/{tid}/tier-b.json \
    --json
```

Running the runner only once (not separately for Tier-A then again for Tier-B) prevents
the `cross_week_filter` from silently dropping Tier-A stories that were just written to
`covered.json` with `status:"reported"` moments earlier.

### Outputs

| File | Description |
|---|---|
| `memory/workspace/{tid}/news-digest.json` | Ranked digest with items[], theme_of_week, rejected_competitor_domains[], connectors_run[] |
| `projects/{slug}/weekly/covered.json` | Cross-process-locked append of newly-reported URLs + status |
| `projects/{slug}/weekly/issues.json` | Cross-process-locked append of issue stub {date, task_id, item_count} |

---

## Connector registry

Per-project connector config lives at:

```
projects/{slug}/business-context.json :: weekly_digest.connectors
```

### Tier-A connector map

| Key | Module | Required config keys |
|---|---|---|
| `rss` | `scripts.fetch.rss_fetch` | `feeds: [url, ...]` |
| `hackernews` | `scripts.fetch.hackernews_search` | `query: "..."` |
| `gdelt` | `scripts.fetch.gdelt_query` | `queries: ["...", ...]` |
| `newsapi` | `scripts.fetch.newsapi_query` | `domains: [...]`, `queries: [...]` |
| `community` | `scripts.fetch.community_search` | `query: "..."`, `sources: ["reddit"\|"x"]` |
| `tavily_news` | `scripts.fetch.tavily_search` (topic=news) | `query: "..."`, `max_results: N` |

A connector is active when its key is present in the config dict, `enabled: true` (or no
`enabled` key — absence means enabled), and has the required config keys populated.

### Tier-B connector map (MCP — researcher arm)

The `mcp[]` array in `weekly_digest.connectors` is a list of MCP connector descriptors.
The researcher agent reads this list and calls the corresponding MCP tools:

```json
"mcp": [
  { "tool": "mcp__tavily__tavily_search",  "query_template": "{series_keyword} site:reddit.com" },
  { "tool": "mcp__pubmed__search_articles", "query_template": "{series_keyword}" },
  { "tool": "mcp__biorxiv__search_preprints", "category": "bioinformatics" }
]
```

The researcher is the ONLY agent with MCP access.  It dispatches exactly the MCP tools
listed, writes normalized NewsItem objects, and stops.

---

## NewsItem shape (exact 10-key contract)

All items — Tier-A and Tier-B — must conform to this shape:

```json
{
  "headline":      "string  — concise factual title, max 120 chars",
  "url":           "string  — canonical URL of primary source",
  "source_domain": "string  — e.g. techcrunch.com (no www.)",
  "source_name":   "string  — publication display name",
  "published_at":  "string  — ISO-8601 UTC timestamp",
  "summary_raw":   "string  — 1-3 sentence factual summary, max 500 chars",
  "connector":     "string  — e.g. 'rss' | 'tavily_news' | 'mcp_pubmed' | 'extra'",
  "raw_score":     "float | null  — provider relevance score",
  "entities":      ["string", ...],
  "topic_tags":    ["string", ...]
}
```

`source_domain` is derived automatically by `scripts/_core/news_item.make_item()` from
`url`; Tier-B items may set it explicitly or omit it (the loader derives it).

Tier-B items written to `tier-b.json` should use the `{"items": [...]}` envelope.

---

## De-dup / cross-week filter / Rule-8 filter / rank pipeline

After Tier-A + Tier-B items are loaded, the runner applies a 4-stage pipeline:

### Stage 1 — Cluster (de-duplicate)

`cluster_items(items)` groups items by `canonical_url` (scheme-normalised, www-stripped,
trailing-slash-stripped).  Each cluster has a `head` (most-recent item) and a `corroboration`
count (distinct source domains).

### Stage 2 — Cross-week filter

`cross_week_filter(clusters, covered)` drops clusters whose `canonical_url` was already
reported AND whose status in `covered.json` is NOT in `{"developing", "unconfirmed", "watch"}`.

Active follow-up stories (status ∈ the active set) pass through so they can be re-surfaced as
`kind: "follow_up"` items APPENDED after the fresh items (2026-08-02: follow-ups trail the
issue and can never own `theme_of_week` — pre-cure they were prepended, which made a stale
follow-up the theme/H1 three issues running).

### Stage 3 — Competitor filter (Rule 8)

`competitor_filter(clusters, do_not_cite_domains)` applies the per-project
`citation_source_policy.do_not_cite_domains` blocklist (suffix-match; subdomains blocked).

- Clusters where **all** members are from blocked domains → dropped entirely.
- Clusters with some clean members → head reassigned to the most-recent clean member;
  blocked members removed from the cluster.
- Rejected domains logged in `news-digest.json :: rejected_competitor_domains[]`.

The blocklist is the SAME list used by the article pipeline (Rule 8, root CLAUDE.md).

### Stage 4 — Rank

`rank_clusters(clusters, now_iso, project_terms, authority_domains)` scores each cluster
(doc synced to the REAL formula 2026-07-01 — the old doc omitted the authority term):

```
significance = 0.30 × recency
             + 0.25 × corroboration_norm
             + 0.20 × relevance(project_terms)
             + 0.15 × authority(head domain ∈ authority_domains)
             + 0.10 × raw_score_norm
```

`recency` = 1.0 for items published today, 0.0 for items 7+ days old.
`project_terms` comes from `business-context.json :: content_strategy.primary_clusters`.
`authority_domains` is derived from the project's RSS feeds + NewsAPI domains, plus an
optional explicit `weekly_digest.authority_domains` override.

Clusters are sorted descending; only the top `items_per_issue` (default 7) appear in the
digest body.

---

## Follow-up state machine

Stories with active status are tracked across issues to enable longitudinal reporting.

### Status values

| Status | Meaning | Cross-week behavior |
|---|---|---|
| `reported` | Covered; story resolved | Dropped from next digest |
| `developing` | Story is actively evolving | Passes cross-week filter; re-surfaced as follow-up |
| `unconfirmed` | Claim unverified at publish time | Passes filter; researcher re-checks |
| `watch` | Operator manually flagged for monitoring | Always passes filter |

### Lifecycle

```
New item appears in harvest
     ↓ (runner: _load_covered + cross_week_filter)
Story is NEW (not in covered.json) → appended to digest as kind:"new"
     ↓ (runner: _write_covered, status="reported")
Covered with status="reported" → dropped from next week's digest
     ↓ (manual edit or future automation)
Operator edits covered.json status → "developing" / "watch"
     ↓ (runner: _emit_followups)
Next week: story re-surfaces as kind:"follow_up" item, appended after fresh items
```

### Covered.json cross-process write (Rule 7)

```python
# Locked write in industry_news_runner._write_covered():
with locked(path):
    path.write_text(json.dumps(entries, ...), encoding="utf-8")
```

`scripts/_core/file_lock.locked(path)` is the ONLY sanctioned way to write `covered.json`
and `issues.json`.  Never write them directly — concurrent sessions corrupt the file.

---

## Pre-write artifacts (Step 5 of /weekly)

After the digest is final, `digest_artifacts.py` converts it into the 5 standard pipeline
artifacts so the orchestrator can advance without running the research/plan stages:

```bash
python -m scripts.research.digest_artifacts \
    --task-id {tid} \
    --project {slug} \
    --json
```

See `scripts/research/digest_artifacts.py` for the 5-artifact builder functions.

**research.json competitor exemption:** The digest's `research.json` emits
`competitor_titles: []` intentionally — digests have no competitors — and is written via
plain Python outside the PostToolUse schema-validate hook, so it is NOT subject to
`research.schema.json`'s `minItems:3` rule; do not fabricate titles or weaken the schema.

---

## Error degradation

| Failure | Behavior |
|---|---|
| Tier-A connector HTTP error | Connector recorded as `"degraded"` in `connectors_run[]`; other connectors continue |
| Tier-B researcher agent fails | `tier-b.json` absent → runner silently ignores `--extra-items` (Tier-A digest stands) |
| `covered.json` locked (concurrent session) | `_write_covered` retries via `file_lock.locked`; if timeout → warning logged, digest proceeds |
| All Tier-A connectors degrade | Empty digest → runner exits with `{"ok": true, "items": 0}`; /weekly skill reports to user before continuing |
| `do_not_cite_domains` removes all clusters | digest has 0 items → /weekly skill reports to user; do NOT publish an empty article |

---

## Testing

Structural wiring: `tests/test_weekly_skill_wiring.py`  
NewsItem contract: `tests/test_news_item.py`  
Rule 8 competitor filter: `tests/test_competitor_domains.py`, `tests/test_competitor_citation_e2e.py`

---

## See also

- `scripts/research/industry_news_runner.py` — full Tier-A executor + `--extra-items` loader
- `scripts/_core/news_item.py` — `NewsItem` TypedDict + `make_item()` factory
- `scripts/_core/file_lock.py` — cross-process locking (Rule 7)
- `scripts/_core/competitor_domains.py` — Rule 8 domain filter (shared with article pipeline)
- `skills/weekly-digest/SKILL.md` — the /weekly orchestration skill that calls this subskill
- `scripts/research/digest_artifacts.py` — pre-writer that converts digest → 5 pipeline artifacts
