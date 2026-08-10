# Category Design Principles

These six rules govern every category architecture decision under this plugin. They came from production audits — each one was learned by violating it and watching the consequences.

---

## Rule 1 — One subcategory = one primary intent

Every subcategory maps to exactly ONE of:

- **Informational** — answers "what is" / "how does" / "why" / "how to" — definitions, science, calculators, glossaries, how-to guides, technology deep dives
- **Commercial-Investigation** — answers "which should I buy" / "what's best" — buyer guides, head-to-head comparisons, roundups
- **Transactional** — answers "buy now" — product detail pages, pricing pages (these typically live in Woocommerce `product_cat`, not in the blog taxonomy)

**The cannibalization risk:** A subcategory that mixes intents will cannibalize itself in SERPs. If `lighting-guides` contains both `What is PPFD?` (Informational) and `Best 1000W LED 2026` (Commercial-Investigation), Google cannot decide which page to rank for which query — the category archive page competes with its own children for both query types and loses to a competitor's intent-pure architecture.

**The check:** For every subcategory, articulate the search query a reader would type to land on it. If two different query types fit, you have an intent collision — split or rename.

**Bad:**
- `lighting-guides` (mixes "what is PPFD" with "best 1000W LED")
- `controllers` (mixes buyer evaluation with how-to-install)
- `cannabis-info` (catch-all)

**Good:**
- `lighting-buyer-guides` (Commercial-Investigation only)
- `lighting-how-to` (Informational only)
- `lighting-glossary` (Informational, definition-level)
- `power-controllers` (Commercial-Investigation, controller buyer guides only) + `power-how-to` (Informational, controller setup walkthroughs)

---

## Rule 2 — Subcategories are content-type axes, not facets

Subcategories classify content by **what kind of article it is** (buyer guide vs comparison vs how-to vs calculator vs glossary). They do NOT classify by **what dimension the content addresses** (wattage, crop, scale, brand, region).

**Faceted dimensions belong in tags**, not subcategories. WordPress tags are flat, can multi-apply, and produce faceted archive pages without polluting the category hierarchy.

**The reasoning:** A single article like *"Best 1000W LED for Cannabis Flowering in California 2026"* hits four facet dimensions (wattage, crop, stage, region). If those were subcategories, the article would need four primary-category assignments — which dilutes the topical-authority signal and confuses canonicalization. As tags, all four apply cleanly without breaking the single-primary-category rule.

**Bad subcategory choices** (these should be tags):
- `lighting/by-wattage/1000w`, `lighting/by-wattage/640w`, etc.
- `lighting/by-crop/cannabis`, `lighting/by-crop/leafy-greens`
- `lighting/by-scale/tent`, `lighting/by-scale/commercial`
- `lighting/by-brand/fluence`, `lighting/by-brand/gavita`

**Good subcategory choices** (content types):
- `lighting-buyer-guides`, `lighting-comparisons`, `lighting-how-to`, `lighting-calculators`, `lighting-technology`, `lighting-glossary`

Combined with tags like `1000w`, `cannabis`, `flowering`, `commercial-scale`, `fluence`, the faceted navigation handles every "X for Y" combination without subcategory bloat.

---

## Rule 3 — 5–10 top-level + 2 levels deep maximum

- **5–10 top-level categories.** Fewer than 5 means under-segmented (you're missing topical authority opportunities); more than 10 dilutes user attention and crawl budget. Most successful niche sites land at 6–8.
- **2 levels deep maximum.** Parent → child. Going to 3 levels (parent → child → grandchild) creates URL bloat, makes breadcrumbs unreadable, and Google de-prioritizes deep paths in crawl scheduling.

**Why 2 levels:** WordPress permalinks for a category archive at 3 levels are `/category/parent/child/grandchild/` — too long for natural breadcrumb display, and the grandchild's siblings under different parents get separated by URL distance.

**Override exception:** Sites with genuinely deep product hierarchies (electronics retailers with thousands of SKUs across product families) may justify 3 levels in the Woocommerce `product_cat` taxonomy — but the BLOG taxonomy should stay at 2 levels. They're separate taxonomies.

---

## Rule 4 — Each subcategory must produce ≥5 articles in 12 months or merge

A subcategory with 1–3 articles is a thin-content signal. The archive page renders with too little content for Google to evaluate; users hit it expecting a list of options and find one or two posts; the topical-authority signal is weakened.

**At the quarterly review:**
- Subcategories with ≥5 articles: healthy
- Subcategories with 3–4 articles: monitor; aim for 5 within next quarter
- Subcategories with ≤2 articles after 12 months: merge into a sibling subcategory or up into the parent

**Subcategory split criterion (opposite case):** If a subcategory exceeds 20–30 articles within 12 months, consider splitting into two on a meaningful axis (intent, scope, or scale).

---

## Rule 5 — Descriptions are 35–80 words, plain prose, no HTML, no inline links, no inside-baseball

**Length:** 35–80 words. Older guidance (150–300 words) is dated to when category pages needed body content to rank; in 2026 Google evaluates category pages by the post list, not the description text. Users scan 79% of the time (Nielsen/Norman) — long descriptions are friction, not value.

**Plain prose, no HTML:** The description renders above the post grid. Theme rendering strips `<p>` tags, RankMath strips HTML when generating meta-description fallback, AI-search engines strip HTML for citation extraction. HTML in the field is at best ignored, at worst leaves orphan markup.

**No inline links:** The post grid renders right below the description. Inline links to specific articles duplicate that signal, create cannibalization risk against the category URL, and disappear in HTML-stripped contexts. Reserve internal linking for the actual article bodies.

**No inside-baseball:** Phrases like "E-E-A-T anchor", "engineering pillar that anchors content across every product subcategory", "demoted to lower-priority internal linking" describe YOUR content architecture — not what the reader cares about. The reader is a cultivator (or whoever your persona is) looking for answers about their grow room — not a content strategist.

**The formula:** "{What kind of content} for {who}. {2–3 specific topic markers}, {credibility-grounding clause}."

**Examples** (project-charlie v2):

> "LED, HPS, and CMH grow lights for half-commercial cannabis cultivators and vertical-farm operators. Buyer guides, head-to-head comparisons, PPFD calculators, and component-level technology coverage — every spec grounded in DLC V4.0 efficacy data and third-party photometric reports rather than vendor marketing claims." (41 words)

> "NEC-compliant electrical infrastructure for cannabis cultivation. Sub-panel sizing for 6-, 12-, and 24-fixture flowering rooms; 240V vs 120V branch selection; the NEC 210.19(A) 80% continuous-load derate rule; GFCI requirements per NEC 210.8(B); surge protective devices per NEC 230.67." (44 words)

See `category-description-style-guide.md` for the full good/bad examples set.

---

## Rule 6 — Slug uniqueness: parent-prefixed

WordPress category slugs are globally unique across the entire `category` taxonomy. Two subcategories named "Buyer Guides" under different parents cannot both have slug `buyer-guides` — one will be auto-renamed to `buyer-guides-2`, which is messy.

**The solution:** Use parent-prefixed slugs:
- `lighting-buyer-guides` (under Lighting)
- `climate-buyer-guides` (under Climate Control)
- `air-buyer-guides` (under Air Management)

The display NAME can still be "Buyer Guides" (concise in breadcrumbs and menus), but the SLUG carries the parent prefix for URL uniqueness.

**Why not nested slugs (`lighting/buyer-guides`)?** WordPress permalink rewrite rules CAN produce nested URLs if `Settings > Permalinks > Category base` is configured appropriately, but the underlying slug is still flat. Most themes display URLs as `/category/{parent-slug}/{child-slug}/` regardless of slug naming, so prefixed slugs `lighting-buyer-guides` render as `/category/lighting/lighting-buyer-guides/` — readable, no collision.

---

## Pruning + split rules (operational)

These rules govern the quarterly category review:

| Condition | Action |
|---|---|
| Subcategory has 0 articles after 6 months | Merge up to parent OR delete |
| Subcategory has 1 article after 12 months | Demote: convert to a tag, delete the subcategory, retag the article |
| Subcategory has >20 articles in 12 months | Consider splitting on a meaningful axis (intent / scope / scale) |
| Two subcategories have >40% article overlap (same tags) | Merge — they're not actually distinct intents |
| User feedback consistently lands on wrong category | Rename the subcategory to match search intent better, OR split |

The setup_categories.py script is idempotent — pruning + renaming is a re-run, not a destructive operation.
