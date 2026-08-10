---
name: topic-clustering
description: Plan + execute pillar-and-spoke content clusters from a single seed keyword. Three layers — Semantic Clustering (SERP-overlap brain), Cluster Architecture (hub-spoke structure), Execution Engine (batch dispatch to /article with shared cluster context). Detects cannibalization. Generates interactive SVG cluster map. The strategy-to-execution gap.
allowed-tools: [Read, Write, Bash, Task, WebSearch, WebFetch]
disable-model-invocation: false
user-invocable: true
---

# Topic Clustering · Semantic Cluster Engine

Plans + executes entire interlinked content ecosystems from a single seed keyword. Three layers: the brain (semantic clustering), the structure (hub-spoke architecture), the machine (execution engine).

## When to invoke

- `/cluster` — interactive (asks plan or execute)
- `/cluster plan <seed-keyword>` — SERP-based semantic analysis → cluster plan + map
- `/cluster plan --from strategy <path>` — import existing strategic plan + validate against SERP
- `/cluster execute [path-to-plan]` — sequential `/article` calls with cluster context + auto-interlinks
- `/cannibalization` — diagnostic-only check on existing portfolio

## Cross-references to other subskills

| Subskill | When this calls it |
|---|---|
| `format-selector` | Determines per-spoke article format |
| `outline-architect` | Builds per-spoke outline within cluster context |
| `batch-article` queue | Execute phase enqueues spokes for sequential processing |
| `internal-linker` + `cross_article_linker.py` | Inject inter-spoke + hub-spoke links post-write |
| `schema-generator` | Add `BreadcrumbList`, `ItemList`, `Article` schema cluster-wide |
| `seo-content-writer` | Per-post content production |

## Plan Phase · `/cluster plan <seed-keyword>`

### Step 1: Seed keyword expansion

Use WebSearch to expand the seed into a keyword universe of 30-50 phrases:

1. Direct search of `<seed>` to capture related searches + "People also ask"
2. Long-tail expansion: `<seed> guide`, `<seed> tips`, `<seed> tools`, `<seed> examples`, `<seed> vs`, `best <seed>`, `how to <seed>`
3. Question mining: `what is <seed>`, `how does <seed> work`, `why <seed>`, `<seed> for beginners`
4. Intent variants:
   - Commercial: best, top, review, comparison, pricing
   - Informational: guide, tutorial, explained, examples
   - Transactional: buy, download, tool, software, service
5. Year freshness: `<seed> 2026`

### Step 2: Semantic clustering (SERP-overlap based)

Group expanded keywords by these priority rules:

1. **SERP Overlap Analysis** (primary signal) — two keywords with **5+ shared top-10 results** target the same intent and belong in one post
2. **Intent Classification** — each keyword tagged informational / commercial / transactional / navigational
3. **Entity Mapping** — identifies people, products, frameworks, organizations Google associates with the topic
4. **Grouping** — combine keywords sharing intent + topical proximity; each group becomes one hub-spoke branch

SERP overlap thresholds (cannibalization decision matrix):

| Shared top-10 URLs | Decision |
|---|---|
| 7-10 | MERGE — same intent; pick one keyword, drop the others |
| 4-6 | CLUSTER candidate — related; interlink heavily as a spoke pair |
| 2-3 | INTERLINK lightly — adjacent topics |
| 0-1 | SEPARATE topics — no cross-link needed |

### Step 3: Cluster architecture design

Build hub-and-spoke:

- **Pillar (hub)**: targets the broadest keyword. Word count 2,500-4,000. Template `pillar-page`. Links down to every spoke.
- **Spokes**: each targets a long-tail cluster. Word count 1,200-1,800. Template auto-selected by intent. Links up to pillar + across to siblings.

Formation rules:
- 2-5 clusters per pillar
- 2-4 spokes per cluster
- Total: 1 pillar + 5-15 spokes
- Every spoke targets a unique primary keyword (zero cannibalization)

### Step 4: Internal link matrix

For each spoke `S`:
- `S` → Pillar (always; anchor text uses the pillar's primary keyword)
- Pillar → `S` (always; anchor text uses `S`'s primary keyword)
- `S` → other spokes in the same cluster (2-3 links each, contextual anchors)
- `S` → spokes in adjacent clusters (0-1 links, only when semantically relevant)

Verify every spoke has ≥3 incoming links. Count total planned interlinks.

### Step 5: Generate output files

All plan + execute artifacts go into a project subdirectory:

```
projects/{slug}/clusters/<seed-keyword-slug>/
  ├── cluster-plan.json
  ├── cluster-map.html        (XSS-safe SVG; no JS)
  ├── pillar-<slug>.md        (Execute Phase)
  ├── <spoke-slug>.md         (Execute Phase, one per spoke)
  └── cluster-scorecard.md    (Execute Phase)
```

#### `cluster-plan.json` schema

```json
{
  "seed_keyword": "<seed>",
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "pillar": {
    "id": "P",
    "title": "...",
    "primary_keyword": "broadest keyword",
    "secondary_keywords": ["..."],
    "search_volume_estimate": "high|medium|low",
    "template": "pillar-page",
    "word_count_target": 3000,
    "cluster": "pillar"
  },
  "clusters": [
    {
      "name": "Cluster A: Theme",
      "intent": "informational|commercial|transactional",
      "color": "#2563eb",
      "posts": [
        {
          "id": "A1",
          "title": "...",
          "primary_keyword": "long-tail keyword",
          "secondary_keywords": ["..."],
          "search_volume_estimate": "high|medium|low",
          "template": "how-to-guide",
          "word_count_target": 1500,
          "links_to": ["P", "A2"],
          "links_from": ["P", "A2"]
        }
      ]
    }
  ],
  "total_posts": 9,
  "total_interlinks": 23,
  "estimated_total_words": 18000,
  "estimated_total_cost_usd": "22.50"
}
```

Volume estimates are relative (high/medium/low) from SERP signals — for precise data use DataForSEO via `scripts/analysis/dataforseo.py`.

#### `cluster-map.html` (XSS-safe SVG)

Static, self-contained HTML + inline SVG. Hard rules:
- NO inline `<script>` blocks
- NO `onclick`, `onmouseover`, or any `on*` event attributes
- NO external script `<src>` references
- Every text label escaped: `&` → `&amp;`, `<` → `&lt;`, `>` → `&gt;`, `"` → `&quot;`, `'` → `&#39;`
- Hover effects via CSS `:hover` only
- Accessibility via `<title>` child elements inside SVG nodes (browser-native tooltips, no JS)

Map shows: central pillar node, color-coded cluster groups radiating outward, spoke nodes within each cluster, link lines connecting related nodes.

### Step 6: Pre-flight cost estimate + user confirmation

Sum per-post estimated cost (via `scripts/_core/cost_estimator.py`). Present:

> "Cluster plan: pillar + 8 spokes, 18,500 words, 23 interlinks.
> Estimated total cost: $22.50.
> Proceed to execute? (Or refine the plan first.)"

Wait for explicit user approval. Do NOT auto-execute.

## Execute Phase · `/cluster execute [path-to-plan]`

### Step 1: Load plan

Read `cluster-plan.json` from user-specified path or most recent `clusters/*/cluster-plan.json` in the project. Validate JSON structure.

If no plan exists: `"No cluster plan found. Run /cluster plan <seed-keyword> first."`

### Step 2: Determine execution order

1. Pillar page FIRST (so spokes can link to a known filename)
2. Then spokes, ordered by `(cluster priority desc, search_volume_estimate desc, post id alphabetical)`
3. Cluster priority = sum of estimated volumes within cluster (highest first)
4. Alternate between clusters when 2+ exist — diversifies early content spread

### Step 3: Per-post execution — cluster context + /article dispatch

Construct cluster context block, prepend to the brief passed to L1 seo-blog:

```yaml
cluster_context:
  cluster_name: "Cluster A: Theme"
  post_role: "spoke"  # or "pillar"
  primary_keyword: "..."
  secondary_keywords: [...]
  template: "how-to-guide"
  word_count_target: 1500
  already_written: ["pillar-x.md", "spoke-a1.md"]   # link to these
  upcoming: ["spoke-a3.md", "spoke-b1.md"]          # use [INTERNAL-LINK] placeholders
  link_requirements:
    must_link_up_to_pillar: true
    must_link_to_cluster_siblings: ["A2"]
    optional_links_to: ["B1"]
```

Add to brief.json + dispatch the full `/article` pipeline (research → plan → build → optimize → publish → monitor baseline).

**FLOW Evidence Triple propagation (required)** — cluster context must include:

> "Apply FLOW Evidence Triple to every public statistic. Year anchor in prose ('In 2026,'), inline citation with publisher + title, URL with retrieval date in the source block. Drop unverifiable stats. Replace contradicted ones."

This cascade is required because cluster execution is high-leverage (5-15 posts at once). Without explicit propagation, individual spokes could silently skip evidence discipline.

### Step 4: Backward link injection

After each post is written:

1. Scan all previously written posts in the cluster directory for `[INTERNAL-LINK: keyword -> filename.md]` markers referencing the just-written post
2. Replace each with a real markdown link: `[keyword](filename.md)`
3. Add cluster metadata to post frontmatter: `cluster:`, `cluster_role:`, `cluster_group:`

### Step 5: Failure handling

- If `/article` fails for a single post (timeout, error, quality gate fail): log + continue with remaining
- Do NOT abort the cluster
- Scorecard marks the gap + recommends retry with manual `/article` invocation
- If user cancels mid-execution: save progress; detect already-written files on next `/cluster execute` and resume

### Step 6: Generate `cluster-scorecard.md`

After all posts complete:
- Per-post status (written / failed / skipped) + file path + word count
- Per-post quality score (call `/audit` on each in parallel) + cluster average
- Cluster cohesion score (0-100 composite of link reciprocity, intent diversity, template diversity, keyword coverage)
- Internal-link audit: outgoing + incoming counts per post, orphan flags, unresolved `[INTERNAL-LINK]` markers
- Cannibalization check: any two posts sharing primary keyword OR >70% keyword overlap
- Image generation summary: hero images generated vs skipped
- Recommended next actions: `/schema`, `/seo-check`, `/repurpose`

### Step 7: Final report

Concise summary: totals, scorecard path, next-action commands.

## Cannibalization detection (standalone diagnostic)

When `/cannibalization` is invoked WITHOUT planning a new cluster:

1. Read all `projects/{slug}/articles/*/publish-log.json`
2. Build primary-keyword → post URL map
3. Pairwise check:
   - Same primary keyword → CRITICAL (consolidate)
   - >70% keyword overlap → HIGH (differentiate or merge)
   - Title-shingle similarity >0.6 → MEDIUM (review)
4. Output `projects/{slug}/cannibalization-report-{date}.md` with merge/differentiate recommendations

## Quality gates

| Gate | Check | Action on fail |
|---|---|---|
| Cluster minimum | ≥2 clusters with ≥2 posts each | Warn during plan; suggest expansion |
| Cannibalization | No two posts share primary keyword | BLOCK execution; require plan adjustment |
| Link completeness | Every post has ≥3 incoming internal links | Warn in scorecard |
| Word count | Pillar ≥2,500w; spokes ≥1,200w | Pass to /article as hard constraint |
| Intent diversity | ≥2 distinct intents across clusters | Warn in scorecard |
| Template diversity | ≥3 distinct templates across cluster | Warn in scorecard |

## Error handling

| Scenario | Action |
|---|---|
| Seed too broad (>50 keyword variants) | Suggest narrowing focus before clustering |
| Seed too narrow (<5 keyword variants) | Offer smaller cluster (pillar + 2-3 spokes) or suggest broadening |
| WebSearch unavailable | Fall back to LLM reasoning for keyword expansion; note reduced accuracy |
| `/article` fails for one post | Log, skip, continue; mark gap in scorecard |
| `cluster-plan.json` malformed | Validate + report parse errors with line numbers |
| User cancels mid-execution | Save progress; resume on next invocation with auto-detection |

## See also

- `references/seo/blog-formats-2026.md` — per-format word count + template guide
- `scripts/_core/batch_queue.py` — execution queue
- `scripts/optimize/cross_article_linker.py` — post-write link injection
- `scripts/analysis/dataforseo.py` — for precise volume data
- `subskills/plan/format-selector/SKILL.md` — per-spoke format decision
