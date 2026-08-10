---
name: weekly-digest
description: "Production weekly industry-news digest: harvest Tier-A + Tier-B sources, assemble a digest article, publish as DRAFT, await explicit publish. Triggers on /weekly, 'industry weekly digest', 'weekly roundup', 'weekly report', '行业周报', '每周简报'. NOT a general article — does NOT run keyword-research/SERP/competitor stages."
user-invocable: true
disable-model-invocation: false
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, Task]
---

# /weekly — Weekly Industry Digest Skill (v1.0)

Produces a SEO- and GEO-optimised weekly news digest article, published as **DRAFT** by
default (Rule 5a). The pipeline reuses the standard `run_pipeline` loop from
`skills/seo-blog/SKILL.md` for all build→publish stages, but bypasses keyword-research,
SERP-analysis, and competitor-analysis (meaningless for a digest) via explicit `--action skip`.

---

## ⛔ READ FIRST — Rule 5a: DRAFT by default

Every `/weekly` run creates a WordPress post with `status: "draft"`.  
Publishing live requires explicit user confirmation in the same conversation:
"publish" / "go live" / "发布" / "上线" — or a project-level
`publish_policy.default = "publish"` in `business-context.json`.  
The pipeline MUST NOT flip status to publish without that signal.

---

## Step 0 — Startup: resolve active project (env-first)

```bash
active_slug=$(python -c "from scripts._core import active_project as a; print(a.get_active_project() or '')")
```

If `active_slug` is empty, ask the user which project to run for (`/switch <slug>` or set
`XS_ACTIVE_PROJECT` env var). Do not proceed without a slug.

---

## Step 1 — Load `weekly_digest` config; stop if absent or disabled

```bash
python -c "
import json, sys
from pathlib import Path
bc = json.loads(Path('projects/{slug}/business-context.json').read_text(encoding='utf-8'))
wd = bc.get('weekly_digest', {})
if not wd.get('enabled'):
    print('NOT_ENABLED')
    sys.exit(2)
print('OK')
"
```

If the command prints `NOT_ENABLED` (or the file is missing), stop and tell the user:

> The `weekly_digest` block is absent or `enabled: false` in
> `projects/{slug}/business-context.json`.  Add a `weekly_digest` object with at
> least `{"enabled": true, "series_keyword": "...", "connectors": {...}}` to
> activate the feature. Plan 3 (loamwright rollout) wires the first production config.

---

## Step 2 — Create task workspace

```
tid = "{slug}_wk_{YYYYMMDD}"   # e.g. loamwright_wk_20260630
                                # must match ^[a-z0-9_]{8,32}$
ws  = "memory/workspace/{tid}/"
```

Create the workspace directory:

```bash
python -c "from pathlib import Path; Path('memory/workspace/{tid}').mkdir(parents=True, exist_ok=True); print('ok')"
```

---

## Step 3 — Tier-B harvest (MCP-powered; operator emphasis)

Dispatch the Tier-B researcher **before** the runner so all sources are available for the
single harvest pass in Step 4.

Dispatch `Agent(subagent_type="xuanran-seo-blog-writer:researcher")` with the following
prompt (fill `{slug}`, `{tid}`, and `{mcp_list}` from the project config):

```
You are the Tier-B harvest arm for the weekly digest.

Project: {slug}
Task ID: {tid}
MCP connectors this project uses: {mcp_list}   # from business-context weekly_digest.connectors.mcp (Tier-B ONLY: consumed by the researcher-agent prompt, deliberately NOT read by industry_news_runner)[]

Goal: Search for industry news items published in the last 7 days that will complement
what the Tier-A connectors find.  Use every MCP connector listed above AND perform
broad Tavily web + news searches for "{series_keyword}".

For each news item you find, emit a normalized NewsItem object with EXACTLY these 10 keys:

{
  "headline":      "<str>  — concise factual title, max 120 chars",
  "url":           "<str>  — canonical URL of the primary source",
  "source_domain": "<str>  — e.g. example.com  (no www.)",
  "source_name":   "<str>  — publication name",
  "published_at":  "<str>  — ISO-8601 UTC, e.g. 2026-06-30T12:00:00+00:00",
  "summary_raw":   "<str>  — 1-3 sentence factual summary, max 500 chars",
  "connector":     "<str>  — e.g. 'tavily_news' | 'mcp_pubmed' | 'web_search'",
  "raw_score":     <float|null>,
  "entities":      ["<str>", ...],
  "topic_tags":    ["<str>", ...]
}

Write ALL found items as a JSON array to:
  memory/workspace/{tid}/tier-b.json

Output format:  {"items": [ <NewsItem>, ... ]}

IRON RULE (Rule 8): Do NOT include any URL from the project's
do_not_cite_domains list in your output.

IRON RULE (extract-verified identity, v3.38.1): every item's headline,
summary_raw, and any statistic in it MUST be derived from the EXTRACTED
content of `url` itself (tavily_extract on that exact URL) — never from a
search snippet, another article about the same topic, or memory. If the
extracted page does not literally support the headline/stat you would
write, DISCARD the item. (2026-07-08 failure: a Tier-B item attributed a
fabricated "Pew 69,000-search study, 15%→8%" to a URL that actually hosts
a Define Media Group 64-site/42% analysis — the fact-checker caught it,
but the item identity must be right at harvest time.)

SCOPE: news EVENTS only. Conference CFPs / "submit a pitch" posts,
webinar promos, product marketing pages, and sponsored listicles are NOT
digest material — do not emit them.
```

Wait for the researcher agent to write `memory/workspace/{tid}/tier-b.json`.
If the researcher fails, `tier-b.json` will be absent — the runner in Step 4 silently
degrades to Tier-A only (no blocking).

Connector config shape (per-project, inside `business-context.json :: weekly_digest`):

```json
{
  "enabled": true,
  "series_keyword": "SEO news this week",
  "lookback_days": 7,
  "follow_up_window_weeks": 4,
  "items_per_issue": 7,
  "category_id": 42,
  "connectors": {
    "rss": { "enabled": true, "feeds": ["https://feeds.example.com/news.rss"] },
    "hackernews": { "enabled": true, "query": "SEO OR search engine" },
    "gdelt": { "enabled": false, "queries": [] },
    "newsapi": { "enabled": false, "domains": [], "queries": [] },
    "community": { "enabled": true, "query": "SEO news 2026", "sources": ["reddit"] },
    "tavily_news": { "enabled": true, "query": "SEO digital marketing news", "max_results": 10 },
    "mcp": []
  }
}
```

---

## Step 4 — Harvest: Tier-A + Tier-B single runner pass

Run the harvest runner **exactly once**, passing `--extra-items` to merge any Tier-B
items the researcher wrote in Step 3.  This single invocation runs all Tier-A connectors,
loads Tier-B items, de-duplicates, cross-week-filters, competitor-filters (Rule 8), ranks,
and writes `covered.json` / `issues.json` exactly once — no second run, no self-filter race:

```bash
python -m scripts.research.industry_news_runner \
    --project {slug} \
    --task-id {tid} \
    --extra-items memory/workspace/{tid}/tier-b.json \
    --json
```

If `tier-b.json` is absent (Step 3 researcher failed), `--extra-items` degrades to `[]`
and Tier-A stands — no blocking, no second run needed.

Writes:
- `memory/workspace/{tid}/news-digest.json` — ranked items, theme_of_week, rejected_competitor_domains[]
- `projects/{slug}/weekly/covered.json` — cross-process-locked append (Rule 7)
- `projects/{slug}/weekly/issues.json` — cross-process-locked append (Rule 7)

### 0-item stop — check before pre-write

Immediately after the runner finishes, verify the digest has items:

```bash
python -c "import json,sys; d=json.load(open('memory/workspace/{tid}/news-digest.json')); sys.exit(0 if d.get('items') else 3)"
```

**Exit 3 → STOP.** Report to the user:

> No qualifying industry news this week — no digest generated.
> (All harvested items were either already covered, filtered as competitors,
> or no items were found by any connector.)

Do NOT proceed to pre-write, pipeline, or publish when the digest has 0 items.
`digest_artifacts.py` raises `ValueError` as a backstop if a 0-item digest somehow
reaches `build_outline` (Rule 6).

### Step 4b — MANDATORY curation review of news-digest.json

Open `news-digest.json` and review the 7 selections BEFORE pre-writing artifacts.
The 2026-08-02 root cures fixed the mechanical failures (follow-ups now APPEND
after fresh items and can never own `theme_of_week`; evergreen/how-to titles are
filtered with drops listed in the runner's `evergreen_dropped[]`; "via @handle"
headline suffixes are stripped at ingestion; relevance is token-based), but two
KNOWN RANKING LIMITATIONS remain — by decision, not oversight (no eval harness
exists to validate a re-tune):

- **The authority boost favors Tier-A domains structurally.** The authority
  list is derived from the project's own RSS/NewsAPI source list, so an
  extract-verified Tier-B item from an off-list domain (axios.com,
  pressgazette.co.uk) scores 0.15×0.5 lower — roughly a 1.75-day recency
  handicap.
- **Corroboration is constant** (clusters are keyed by canonical URL, so
  cross-domain coverage of one story never merges) — the 0.25 weight
  discriminates nothing.

When the picks are wrong, HAND-CURATE from the Tier-B pool (`tier-b.json`):
clone `build_digest()`'s item shape exactly, use positional cluster ids, and
repair `projects/{slug}/weekly/covered.json` in BOTH directions under
`file_lock.locked` — remove the runner's rows for stories you dropped (a false
"reported" mark suppresses that story forever) and append rows for stories you
added (else they resurface next week).

---

## Step 5 — Pre-write pipeline artifacts

Convert `news-digest.json` into the 5 standard pipeline artifacts (state, research, angle,
outline, image-prompts) so the orchestrator can skip the research/plan stages:

```bash
python -m scripts.research.digest_artifacts \
    --task-id {tid} \
    --project {slug} \
    --json
```

Reads: `memory/workspace/{tid}/news-digest.json` + `projects/{slug}/business-context.json`  
Writes (all in `memory/workspace/{tid}/`):
- `state.json` — phase=`plan`, current_stage=`format-selector`, command=`weekly-digest`
- `research.json` — digest items as `digest_items[]`; empty `serp_features[]`/`competitor_titles[]`
- `angle.json` — format_id=`weekly-digest`, angle=`trends`; since 2026-08-02 the series
  conventions are ENCODED: title `{IND} Weekly, {Month D YYYY}: {hook}` and slug
  `{ind}-weekly-YYYY-MM-DD`, both derived from the ISSUE date in `{tid}` (never the
  harvest wall-clock — the 07-22 issue slugged itself 07-23 by crossing UTC midnight).
  Both `slug` and `slug_draft` are written. No hand-correction step needed.
- `outline.json` — TL;DR + one section per item + FAQ + References. Claim markers are
  POSITIONAL (`c1_src`…`c7_src`), independent of cluster ids — hand-curated ids like
  `hc1` no longer produce schema-illegal `[claim:hc1_src]` markers.
- `image-prompts.json` — single `cover` photo slot

Note: the assembled draft contains NO `## Conclusion` for this format — the format
baseline (`references/seo/format-mandatory-sections.json :: weekly-digest`) excludes
it, and `assemble.py` now honors that resolution instead of injecting the
`_(See verdict in main body sections.)_` placeholder stub (2026-08-02 root cure).

---

## Step 6 — Skip irrelevant research stages

The SERP-analysis and competitor-analysis stages are meaningless for a news digest (there
is no single target keyword; content comes from the harvest, not from SERP gaps).
Explicitly skip them with a logged reason so the audit trail is clean:

```bash
python -m scripts.pipeline.orchestrator \
    --workspace {tid} \
    --action skip \
    --stage serp-analysis \
    --reason "weekly-digest: no single-keyword SERP; content sourced from harvest"

python -m scripts.pipeline.orchestrator \
    --workspace {tid} \
    --action skip \
    --stage competitor-analysis \
    --reason "weekly-digest: no competitor analysis; digest format covers news events, not keyword gaps"
```

This records `status:"skipped"` (NOT `"completed"`) in the stage-history with the reason,
so a later auditor can tell what ran from what was deliberately dropped. Skipping a
**mandatory** stage is refused (exit 1) — only optional stages can be skipped.

⚠️ **Do NOT `--action skip` the `visual-designer` stage for a digest.** The
`visual-density-check` gate is **mandatory** (v3.31): it blocks publish on a wall-of-text
(no table / cited-stat block / quotation). The visual-designer restructures the digest into
an At-a-Glance table + a By-the-Numbers stat block that clear the floor, so it must run. A
digest that already carries those (they are the standard digest layout) passes; skipping the
designer on a thin digest would make the BASH density gate block publish.

---

## Step 7 — Drive build → publish via the standard run_pipeline loop

The digest is now a standard pipeline artifact set.  Drive it with the same
`run_pipeline` DISPATCH_LLM loop documented in `skills/seo-blog/SKILL.md`:

```
REPEAT:
  1. result = Bash("python -m scripts.pipeline.run_pipeline --workspace {tid} --json"
                   [+ " --completed-llm {last_llm_stage}" if you just finished one])

  2. Read result.action:
     "COMPLETE"     → Digest pipeline done. Proceed to Step 8 (post-publish verification).
     "DISPATCH_LLM" → Dispatch Agent(subagent_type=result.subagent_type, prompt=result.dispatch_prompt).
                      After the subagent finishes, confirm expected_outputs exist,
                      then GOTO 1 with --completed-llm {result.stage}.
     "GATE_FAILED"  → Fix the draft or re-dispatch the failing subagent per
                      subskills/cross-cutting/repair-orchestrator, then GOTO 1.
     "WAIT"         → A CHECK isn't ready. Wait briefly, GOTO 1.
     "BLOCKED"      → Fix missing inputs per result.missing_inputs, then GOTO 1.
     "ERROR"        → Inspect result.detail, fix the crash, GOTO 1.
```

The runner services: section-drafter / fact-check / humanizer / geo-auditor /
reviewer / meta-builder / image-visual-qa / publisher stages in the correct order.

⚠ **Command-timeout discipline (2026-08-02):** the `run_pipeline` invocation that
services `wordpress-publisher` runs a media upload that alone takes ~140s on a 4K
cover — give that Bash call a timeout of **≥600s**. A tool-level timeout that kills
the runner mid-publisher leaves the stage `in_progress` with no `publish-result.json`.
Recovery procedure: (1) ghost-check WordPress FIRST — `GET /wp/v2/posts?slug={slug}
&status=any` via `WPClient('{slug}')` (the publisher is not idempotent; a re-run
after a half-completed create makes a ghost post); (2) if no post exists, run the
stage command directly (`python -m scripts.wordpress.wp_publisher {slug} --workspace
{tid} --status draft --json`) to capture its real stderr, then re-invoke the runner
to reconcile.

**Publish defaults to DRAFT** (Rule 5a).  The publisher creates the post as
`status: "draft"`.  Do NOT flip to publish during the loop without explicit user
confirmation.

Publisher targeting note: the digest's dedicated WordPress category
(`weekly_digest.category_id`) is pinned into `meta.category_ids` **automatically**
by the `category-selector` optimize-phase stage — it detects `format_id:
"weekly-digest"` in `angle.json` and short-circuits content-derived selection
(`scripts/build/category_selector.py`). No manual step is required; just ensure
`category_id` is set in the project config before the first run. (Before
2026-06-30 this was an unwired claim and digests silently fell through to
Uncategorized — Rule 6.)

---

## Step 8 — Post-publish verification and preview handoff

After `run_pipeline` reports `COMPLETE` and the post exists as a draft:

```bash
python -m scripts.wordpress.verify_post {slug} {post_id} \
    --workspace {tid} \
    --expected-status draft \
    --min-images 1
```

`--min-images 1` is **required**: a digest ships a single cover photo (often
featured-only under a `no_inline` policy), so the default `--min-images 4` would
report OVERALL FAIL on every digest even when publish is perfect.

Run the 13-point structural verification on the **preview URL**:
`{wp_site_url}/?p={post_id}&preview=true`

Checks include (from `seo-blog SKILL.md` Rule 4):
1. HTTP 200 on the preview URL (not 500)
2. Project CSS wrapper class present in rendered HTML
3. All image WP URLs render under `wp-content/uploads/`
4. `<title>`, `<link rel="canonical">`, `<meta name="robots">` match planned meta
5. At least 2 JSON-LD blocks present; expected schema types confirmed
6. `<h2>References</h2>` present with ≥1 `<li>` link-resolvable entry
7. Article signature paragraph present (project-dependent)

Report the preview URL to the user.  Confirm covered/issues state was updated by
Step 4 (the single runner pass writes covered/issues exactly once).

---

## Step 9 — Await explicit publish confirmation

Present the user with:

```
Draft created: {preview_url}
Verification: {verification_summary}

To publish live, reply "publish" or "发布".
```

On explicit confirmation → PATCH `status: "publish"` → re-verify the live public URL.

---

## Step 10 — Refresh the series hub page (runs only after the digest is live)

Once the digest post is **published** (Step 9) and has a real permalink, record
the issue and (re)build the series hub page (whose path is the project's
`weekly_digest.hub_page`, default `/weekly-digest/` — a project value, never
hardcoded in skill code). This is a concrete executor — the hub is NOT updated by
`run_pipeline`, so this step must run explicitly (Rule 6):

```bash
python -m scripts.wordpress.hub_page_publisher --project {slug} \
    --task-id {tid} \
    --issue-title "{published_post_title}" \
    --issue-url "{published_post_permalink}" \
    --issue-date {YYYY-MM-DD} \
    --item-count {published_item_count} \
    --status publish \
    --json
```

Notes:
- `--task-id` makes the issue record **idempotent** (a re-run updates the row in
  place; it never appends a duplicate). The title/url backfill the harvest-time
  stub so the hub lists a real link instead of "Untitled Issue → #".
- **Publishing the hub (the series index visitors/crawlers actually reach):**
  because this step runs ONLY after the user already confirmed publishing the
  digest live, pass `--status publish` so the hub goes live too. Without it the
  hub is created `draft` and — since refresh never flips status (H5) — stays a
  permanent draft (the configured `hub_page`, e.g. `/weekly-digest/` → 404). This
  was the H1/Bug-1 silent failure.
  - You may omit `--status` for a project whose
    `business-context.json :: publish_policy.default == "publish"`: the publisher
    auto-resolves to `publish` for that project (Rule 5a project-level opt-in,
    via `hub_page_publisher.resolve_hub_status`).
  - On a weekly REFRESH of an already-published hub you may omit `--status`
    (H5: omitting it leaves the live hub's status untouched). Passing
    `--status publish` again is also safe (idempotent).
- Skip this step while the digest is still a draft (no public permalink yet); a
  draft hub for a draft digest is correct (Rule 5a).

---

## See also

- `subskills/research/industry-news-monitor/SKILL.md` — harvest architecture detail
- `scripts/research/industry_news_runner.py` — Tier-A connector executor + `--extra-items` merge
- `scripts/research/digest_artifacts.py` — pre-writer CLI (5 pipeline artifacts)
- `skills/seo-blog/SKILL.md` — run_pipeline DISPATCH_LLM loop (canonical reference)
- `scripts/pipeline/orchestrator.py` — `--action skip` stage skipping
- `scripts/pipeline/run_pipeline.py` — the runner driving the build→publish loop
- `templates/weekly-digest.md` — article format template (format_id: weekly-digest)
- Rule 5a (root CLAUDE.md) — publish defaults to draft unconditionally
- Rule 7 (root CLAUDE.md) — env-first project resolution; covered.json locked writes
- Rule 8 (root CLAUDE.md) — competitor domains never cited in harvest output
