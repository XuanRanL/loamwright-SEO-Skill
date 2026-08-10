---
name: wordpress-category-setup
description: Design and deploy a WordPress blog category taxonomy (top-level categories + subcategories) with descriptions, slugs, and RankMath SEO meta. Three modes — interactive (design from scratch with the user), apply (deploy an existing categories-config.json), refresh (re-sync to live site). Use when user runs /setup-categories, when /init asks about content architecture, or when a project is preparing to publish its first articles and needs the topical-authority foundation. Triggers on "setup categories", "category architecture", "blog taxonomy", "category SEO", "/setup-categories".
allowed-tools: [Read, Write, Edit, Bash, Task, AskUserQuestion]
disable-model-invocation: false
user-invocable: true
---

# WordPress Category Setup

The category taxonomy is the topical-authority foundation of every WordPress content site. This subskill designs it (interactively) and deploys it (via `scripts/wordpress/setup_categories.py`) with full SEO optimization — slug, description, RankMath title, meta description, focus keyword, robots directive, and OG/Twitter overrides.

The canonical reference implementation is the **project-charlie** project, which has 6 top-level + 29 subcategories live with full RankMath metadata. New projects should adapt that pattern to their industry.

## When to use

- **After `/init` completes** for a new WordPress project — before the first `/article` runs, so articles have proper categories to land in
- **When expanding** an existing project's product/content scope (e.g. project-charlie adding HVAC product line ⇒ activate the Climate Control category)
- **When migrating** from a flat taxonomy (single "Blog" or "Buyer Guides" category) to a structured one
- **When auditing** an existing site that has organically grown messy categories

## Hard prerequisites

1. **Project exists**: `projects/{slug}/` must be initialized (run `/init <url>` first)
2. **WP credentials work**: `~/.xuanran-seo/credentials/wordpress/{slug}.json` exists and `WPClient(slug).health_check()` returns 200
3. **MU plugin v1.1+ deployed** (RankMath bridge with `register_term_meta` for category taxonomy): probe `GET /xuanran/v1/rank-math-bridge` — `bridge_version >= 1.1.0` required for the SEO title / focus keyword / OG fields to persist on category archives. Without v1.1, you still get descriptions + slugs + parent hierarchy, but RankMath custom titles default to the global template `%term% %sep% %sitename%`.
4. **SEO plugin = RankMath** (per `business-context.json :: wordpress.seo_plugin`). Yoast support is out of scope — Yoast uses different meta key names and ACL rules.

## Three modes

### Mode A — Interactive design (greenfield, after /init)

Use when `projects/{slug}/categories-config.json` does NOT exist. The subskill walks an editorial-design interview, drafts the config, shows it for confirmation, then applies.

**Workflow:**

1. **Load context.** Read `projects/{slug}/business-context.json` for `industry`, `target_audience.primary`, `voice` ratios, and (if present) `default_categories` and `default_tags_pool`. These constrain category names and descriptions to the brand voice.

2. **Surface the design principles** (see `references/category-design-principles.md`). Walk the user through the six rules before designing — the rules drive every later decision and rejecting them upfront saves redesigns later.

3. **Top-level category interview.** Ask the user to name 5–10 top-level categories. Recommend mapping to (a) product lines, (b) major service axes, or (c) the underlying engineering subsystems for a technical site (project-charlie used the 6-subsystem cultivation framework).

4. **For each top-level**, ask 4–7 subcategories with intent classification:
   - **Informational** (definition, how-to, science, calculator, glossary)
   - **Commercial-Investigation** (buyer guide, comparison, roundup)
   - **Transactional** (rare for blog content; usually surfaced via shop)

   Reject any subcategory that conflates intents (e.g. a "Guides" subcategory mixing "What is PPFD?" with "Best 1000W LED 2026" — the first is Informational, the second is Commercial-Investigation; they cannibalize on the same archive page). This is project-charlie's Rule 3 (see `skills/seo-blog/SKILL.md`).

5. **Draft descriptions** using the style guide (`references/category-description-style-guide.md`):
   - 35–80 words
   - Plain prose, NO HTML, NO inline links
   - Lead with WHAT content is in the category
   - Then WHO it's for (persona from business-context)
   - Concrete topic markers (product names, certifications, standards)
   - No inside-baseball ("E-E-A-T anchor", "engineering pillar that anchors content", "demoted to lower-priority linking")

6. **Draft RankMath meta** per category:
   - `rank_math_title` (50–60 chars): `{Category Name}: {Differentiating Phrase} | {Brand Name}`
   - `rank_math_description` (150–160 chars): single-sentence summary including focus keyword in first 120 chars
   - `rank_math_focus_keyword`: 1–3 primary keywords this archive page targets
   - `rank_math_robots`: `["index"]` (always — there is no reason to noindex a real category archive)
   - `rank_math_facebook_*` and `rank_math_twitter_*`: shorter restatement for social cards
   - `rank_math_twitter_card_type`: `summary_large_image`

7. **Validate against the design principles**:
   - All slugs unique (use parent-prefixed: `lighting-buyer-guides`, not `lighting/buyer-guides`)
   - Every subcategory has exactly ONE primary intent
   - Every description is 35–80 words, plain prose, no `<a href`, no `<p>`
   - Every description has zero inside-baseball language (use the banned-phrases checklist in the style guide)

8. **Show full proposal to user** as a structured table → confirm.

9. **Save** to `projects/{slug}/categories-config.json` (schema: see template).

10. **Apply** via `python -m scripts.wordpress.setup_categories {slug}`.

11. **Verify** — fetch 3–5 live archive URLs with CF bypass header (if configured); confirm HTTP 200, description rendered, RankMath title in `<title>`, focus keyword in meta description.

### Mode B — Apply existing config

Use when `projects/{slug}/categories-config.json` already exists (manually authored, copied from another project, or generated by a previous Mode A run).

**Workflow:**

1. Validate the config against the schema (`schemas/categories-config.schema.json` — to be created when needed).
2. Audit live site state: which categories already exist by slug?
3. Show diff: NEW vs UPDATE vs UNCHANGED counts.
4. Confirm with user → apply.
5. Verify.

Command: `python -m scripts.wordpress.setup_categories {slug}` (idempotent — safe to re-run).

### Mode C — Refresh / re-sync

Use when categories-config.json has been edited locally and you want to push changes to the live site.

**Workflow:** identical to Mode B. The setup script is idempotent — it PATCHes existing categories with the new field values and creates any new ones.

## The 6 design principles (full reference: `references/category-design-principles.md`)

Quick summary — read the full reference doc before designing:

1. **One subcategory = one primary intent** (Informational / Commercial-Investigation / Transactional). No catch-all "Guides" subcategories.
2. **Subcategories are content-type axes, not facets.** Wattage, crop, scale, brand are TAG axes, not subcategories.
3. **5–10 top-level + 2 levels deep maximum.** Beyond this, dilutes topical authority.
4. **Each subcategory must produce ≥5 articles in 12 months or merge** at the next quarterly review.
5. **Descriptions are 35–80 words, plain prose, no HTML, no inline links, no inside-baseball.** The post grid below already shows links; the description provides context.
6. **Slug uniqueness:** parent-prefixed (`lighting-buyer-guides`) so WordPress's global slug uniqueness rule doesn't collide.

## Failure modes & recovery

| Symptom | Cause | Recovery |
|---|---|---|
| `GET /xuanran/v1/rank-math-bridge` returns 404 | MU plugin not installed | Deploy `install/wordpress-mu-plugin/xuanran-rank-math-rest-bridge.php` to `wp-content/mu-plugins/` on the server. No activation needed; MU plugins auto-load. |
| Bridge returns `bridge_version: "1.0.0"` | MU plugin too old, lacks term meta | Upgrade to v1.1+ (replace the file). After re-deploy, re-run setup_categories to populate RankMath term meta. |
| `meta: []` returned after PATCH | RankMath term meta keys not registered | Same as above — MU plugin v1.1+ required. Without it, description still applies but custom SEO titles fall back to global template. |
| Category created but archive URL returns 404 | Permalink not flushed | Visit `wp-admin/options-permalink.php` and save (no changes needed — just trigger flush). |
| Description renders with HTML entities `&lt;p&gt;` | Theme escaped the description | Re-run setup_categories with v2 plain-text descriptions (no HTML). See project-charlie v1→v2 migration. |
| Posts assigned to wrong category | Manual reassignment needed | `POST /wp/v2/posts/{id}` with `{"categories": [new_id]}` — this REPLACES all categories on the post (single primary recommended). |
| Duplicate categories on the live site (same name, two term IDs — usually a parentless top-level stray next to the curated child) | Historical publish-time creation minted a dup: pre-v3.19.2 the name match wasn't HTML-entity-aware, so every `&`-bearing name missed and got re-created (project-hotel 8 pairs, project-kilo orphans). The publisher is resolve-only since 2026-07-11, so new dups can't be minted — but old damage persists until repaired. | `python -m scripts.wordpress.dedupe_categories {slug} --check` to detect (exit 1 = dups found); `--apply` to repair: backs up, reassigns every affected post to the canonical (config-listed) term, fixes `rank_math_primary_category`, deletes the strays, writes 301 rules to `projects/{slug}/.seo/category-dedupe-redirects-{date}.json` (import in Rank Math → Redirections), and refreshes categories-live.json. |

## Slash command

The `/setup-categories` slash command (registered in `.claude-plugin/plugin.json`) invokes this subskill with the active project slug. The user can override with `/setup-categories {slug}` to operate on a specific project.

## See also

- `references/category-design-principles.md` — the 6 design rules in detail
- `references/category-description-style-guide.md` — how to write tight, link-free descriptions
- `templates/categories-config-template.json` — empty starter template
- `projects/project-charlie/categories-config.json` — canonical reference (6 top + 29 sub, all 35 live)
- `projects/project-charlie/content-taxonomy.md` — full design doc with subcategory specs and cross-linking matrix
- `scripts/wordpress/setup_categories.py` — the idempotent applier
- `install/wordpress-mu-plugin/xuanran-rank-math-rest-bridge.php` v1.1+ — the term-meta bridge
- `skills/seo-blog/SKILL.md` Rule 3 — the mandatory-sections gate that complements categories at the article level
