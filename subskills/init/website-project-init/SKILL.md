---
name: website-project-init
description: Initialize a new website project from a URL. FIRST asks the user for all required credentials (Anthropic / Tavily / OpenAI / WordPress App Password / brand config), then deep-scans the site (40 pages with 5-tier JS fallback waterfall), generates projects/{slug}/ archive (business-context, brand identity, competitors, GEO baseline, personas, target keywords). Use when user provides a URL + wants to set up a new client / new site, runs /init, or supplies just a domain with no other task. Triggers on URLs not yet in projects/.
allowed-tools: [Read, Write, Edit, Bash, Task, AskUserQuestion, WebFetch, WebSearch]
disable-model-invocation: false
---

# Website Project Init

The first command for every new client website. Sets up credentials, scans the
site, and produces a complete `projects/{slug}/` archive that all subsequent
`/article` / `/audit` / `/refresh` commands inherit from.

## Mandatory ordering

**STEP 0 (CRITICAL) — Setup Wizard FIRST**

Before ANY web crawling or analysis happens, run the setup wizard to ensure
we have all credentials and brand context. The wizard is non-negotiable
because:
  - /init Stage 1 needs Tavily key
  - /init Stage 7 (GEO baseline) needs Anthropic for AI probe
  - Image gen later needs OpenAI key
  - Publish later needs WordPress App Password
  - Image Art Direction needs brand colors

Running scan first and discovering credentials missing later wastes the
crawl + frustrates the user. So:

```python
from scripts._core.setup_wizard import SetupWizard
wiz = SetupWizard(site_slug, site_url)
status = wiz.detect_existing()
```

Then for each `provider.found == False` and `provider.tier in (REQUIRED, RECOMMENDED, PUBLISH)`,
ask the user via natural conversation:

  - Tier 1 (Anthropic, contact_email): HARD REQUIRED — halt /init if user refuses
  - Tier 2 (Tavily, OpenAI, Gemini): STRONGLY RECOMMENDED — warn but allow skip; explain what features unlock
  - Tier 3 (WordPress): REQUIRED ONLY IF user plans to publish via /publish; ask upfront so they don't get stuck later
  - Tier 4 (Brand config): RECOMMENDED — can be filled later via /context edit but image-gen + voice need this
  - Tier 5 (IndexNow, YouTube): OPTIONAL — explain features they unlock

For each credential the user provides:
  1. Save via `wiz.save_credential(provider, value)` (or `wiz.save_wordpress(...)` etc.)
  2. Live-test with `wiz._test_provider(provider)` (or full validate)
  3. If test fails, show the error and ask again

### Recommended interactive flow (use AskUserQuestion tool)

```
1. Detect what's already present (env vars + ~/.xuanran-seo/credentials/)
2. Present summary: "Found X credentials, need Y more. Want to configure now?"
3. For each missing tier-1/2/3 item:
     Ask via AskUserQuestion (or natural NL if user prefers chat)
     Save + validate
4. Show final "ready for" matrix:
     ✓ init   ✓ article   ✓ image_gen   ✗ publish_wp   ✓ ai_visibility
5. If WP not configured + user wants to publish later, surface that early
6. ASK THE BLOG-SIDEBAR QUESTION NOW (see below) — capture intent up front
7. Then proceed to STEP 1.
```

**Step 0b — Blog sidebars: ask now, build later (MANDATORY question)**

Ask this in the opening wizard, alongside the publish question. Do **not** default
it silently and do **not** postpone the asking — a sidebar shapes every blog
template on the site, and discovering at the end that the operator wanted one
(or emphatically did not) is a rebuild, not a tweak.

> **Do you want custom blog sidebars for this site?**
>
> - **Yes, custom (recommended for commercial sites)** — two purpose-built
>   sidebars: the blog index gets navigation (its own Categories widget first),
>   each article gets a promotional rail (image-led CTA card, products, other
>   pages worth reading). Borderless, built from your brand palette.
> - **Yes, but index only** — leave article pages on the theme default.
> - **No** — the theme's existing sidebar is left completely alone. Nothing is
>   generated and nothing is deployed.

Record the answer immediately in `business-context.json :: blog_sidebars.enabled`
(plus `index_modules` / `post_modules` if they picked a partial set) so the later
build step reads intent rather than re-asking.

**Why ask here but build at Step 12c:** the sidebar needs the brand palette
(Step 11.7), the product catalog (Step 4) and the tool/landing pages (Step 11)
to exist before it can be rendered. Asking early costs nothing; building early
would produce a sidebar with no colours and no links.

## Pipeline (after wizard complete)

```
Step 0.5: Create standard tree — invoke ensure_project_tree(slug)
          - Creates projects/{slug}/ with all 9 standard subdirs
          - .seo/, brand/, research/, articles/, clusters/, metrics/, audits/, assets/, credentials/
          - Writes auto .gitignore
Step 1: Discovery           — Tavily extract homepage + tech_detect (CMS / SPA / Shopify Hydrogen / etc)
Step 2: Crawl (40 pages)    — 5-tier waterfall: tavily → patchright → firecrawl → jina.ai/reader → raw + hydration
Step 3: Brand Identity       — About + Footer + Contact → company/founded/NAP/socials → brand/brand-identity.json
Step 4: Product Intelligence — Categories / Top SKUs / Price tier / Brand catalog → research/product-intelligence.json
Step 5: Voice Reverse-engineer — Read 5 existing blog posts + About → analyze actual voice vs self-described → brand/voice-samples/
Step 6: SEO Baseline         — title/meta/H1/schema across 40 pages + CWV + Yoast detection → research/seo-baseline.json
Step 7: GEO Baseline         — Active probe: ChatGPT / PPLX / Claude / Gemini × 5 queries → research/ai-probes/{date}.json
Step 8: Competitor ID         — SERP top-10 for 3 derived keywords → research/competitors.json
Step 9: Existing Clusters     — Cluster existing blog by SERP overlap → research/existing-clusters.json
Step 10: Persona Reverse      — Infer 1-2 NNGroup 4-tone personas from copy + products → brand/personas/{id}.json
Step 11: Synthesis            — Write project.yaml + init-report.md (root) + internal-links-map.md (root)
Step 11.5: Featured-image inline policy — Ask theme behaviour → business-context.featured_image_inline_policy
Step 11.6: Image-pipeline policy        — mode/size/aspect defaults → business-context.image_pipeline_policy
Step 11.7: Image brand identity         — visual style + COVER text overlay + WATERMARK + packaging label
          ↳ Writes brand/../brand-guideline.yaml (image-prompt-designer reads it; watermark gated on it)
          ↳ Skipping it = unbranded covers + NO watermark (the 2026-06-06 project-kilo gap)
Step 12: Article CSS Design   — Ask the user whether to generate a scoped article CSS
          ↳ If yes: python -m scripts.build.article_css_generator {slug}
          ↳ Reads brand/brand-config.json colors + fonts
          ↳ Outputs brand/article-css.css + brand/article-css.min.css
          ↳ Scoped to .{slug}-pillar wrapper class
          ↳ wp_publisher.py auto-injects this on every future /article publish
Step 12b: Style tokens (de-fingerprint) — ALWAYS, immediately after Step 12, no user question:
          ↳ python -m scripts._core.style_tokens --generate {slug}
          ↳ Derives per-project class names (HMAC of a private salt) so published
            output shares no cross-site class vocabulary with other installs/projects
          ↳ Writes brand/style-tokens.json; wp_publisher + verify_post + the
            reinject fleet tools resolve names through it automatically
          ↳ Internal artifacts (draft.md, lints, agent contracts) keep the legacy
            names (xr-*, article-signature) — the mapping happens ONLY at the
            publish boundary

Step 12c: Blog Sidebars — build what Step 0b already agreed to (no re-asking)
          ↳ Skip entirely if business-context.json :: blog_sidebars.enabled is false/absent
          ↳ python -m scripts.build.blog_sidebar_generator {slug}
          ↳ Reads brand/brand-identity.json palette + brand-config fonts +
            conversion_offers (default + EXCLUDED product categories) + anchor_links
          ↳ Outputs brand/blog-sidebars.php (mu-plugin) + brand/blog-sidebars.css
          ↳ Two DIFFERENT sidebars: index = find (Categories first), post = promote
          ↳ Deploy is a SEPARATE hop (Rule 13): the generator installs nothing
          ↳ python -m scripts.wordpress.deploy_blog_sidebars {slug} --check | --apply

Step 13: Citation & Signature Policy — Ask the user for the project's reference / authorship preferences
          ↳ Stores answers in business-context.json :: references_policy
          ↳ wp_publisher.py reads this policy on every future /article publish
          ↳ Defaults assumed if user skips: references_required=true, style=apa7,
            entries_target=8-10, signature_required=true, author={brand_name} team
```

**Step 12c — Blog Sidebars (build step, not a question)**

Only runs when Step 0b captured a yes. Nothing here re-asks the operator.

```bash
python -m scripts.build.blog_sidebar_generator {slug} --json
```

Produces two artifacts under `projects/{slug}/brand/`:

| File | What it is | Where it goes |
|---|---|---|
| `blog-sidebars.php` | mu-plugin: registers two widget areas + three widgets, project config baked in | `wp-content/mu-plugins/{slug}-blog-sidebars.php` |
| `blog-sidebars.css` | matching stylesheet, built from the brand palette | a WPCode CSS snippet, location **Site Wide Header** |

**Then deploy it — the generator does NOT install anything (Rule 13).** These are
3-hop artifacts: the generator is hop 1→2, and the copy running on the WordPress
host is a separate hop-3 artifact that keeps whatever was installed the day it
shipped. **Ask for the host recipe while you are already asking about WordPress access**
(Step 3), not at deploy time — a config key that is read by an executor but asked
for by nobody is why this check was inert on 12 of 13 projects:

> "The sidebar mu-plugin is a FILE on the server, so deploying and drift-checking it
> needs shell access — separate from the REST credentials. If your site runs in
> Docker over SSH, what's the ssh host alias and the container name? (Skip if you'd
> rather deploy by hand — the tool will print the exact steps instead.)"

Store as `business-context.json :: wordpress.host_access = {ssh, container,
mu_plugins}`. It holds **no credentials** — `ssh` is an ssh-config alias, so the key
stays in the agent. Then use the deployer:

```bash
python -m scripts.wordpress.deploy_blog_sidebars {slug} --check   # drift, changes nothing
python -m scripts.wordpress.deploy_blog_sidebars {slug} --apply   # scp -> php -l -> install -> readback
python -m scripts.wordpress.deploy_blog_sidebars --all --check --json   # fleet-wide
```

`--check` exits non-zero on drift and is the only way to know a template fix
actually reached the site. Without `host_access` the tool prints the manual steps
rather than guessing at a transport — it never silently skips. On Windows run it
from **PowerShell**; Git Bash cannot reach the ssh agent key, and the resulting
connection failure is reported as `unreachable`, never as "not deployed".

Editing `templates/blog-sidebars.*.tpl` is therefore a three-part change: fix the
template, regenerate every project, then `--check`/`--apply` every live site.
Stopping at the template fixes only sites that have not been built yet.

**Four deployment rules learned the hard way (2026-08-04, project-alpha).** Every one
of these produced a silent failure that looked like working code:

1. **mu-plugin, never a snippet manager.** The identical PHP as a WPCode Lite
   snippet never executed — published, correctly typed, parse-clean, no error
   logged anywhere. A `wp_head` canary was the only thing that proved it. Widget
   and sidebar registration must beat `widgets_init`, which only an mu-plugin
   guarantees.
2. **Safelist the class prefix** in whatever Remove-Unused-CSS the host runs.
   FlyingPress ships an EMPTY safelist, so the whole stylesheet is stripped in
   production while a logged-in admin sees it working perfectly.
3. **Never `delete_option()` a plugin's cache to "refresh" it.** WPCode's own
   `delete_cache()` does `update_option($name, array())` — it keeps the row.
   Deleting the row instead made every WPCode snippet on the site stop
   outputting, sitewide, self-perpetuating, silently. Recovery is
   `wpcode()->cache->cache_all_loaded_snippets()`.
4. **Respect OPcache before believing a fix failed.** Typical container config is
   `validate_timestamps=On, revalidate_freq=60`: purge the page cache too early
   after writing the mu-plugin and the pages regenerate against the old compiled
   file. Wait out the window, then purge.

**Verification is visual, not textual.** Grepping rendered HTML for a class name
proves nothing — `class="x-wrap"` appears in the markup whether or not the CSS
that styles it was delivered. Screenshot the page
(`python -m scripts.audit.capture_screenshot {url} --viewport desktop --full`,
plus the project's CF-bypass header if it has one) and look. Cache-bust every
verification fetch; identical byte counts across runs mean you are reading a
cached page, not a deployment failure.

**Widget assignment.** The generator creates the areas; it does not fill them.
Assign in Appearance > Widgets, or programmatically by writing
`sidebars_widgets` plus each `widget_{id_base}` option. The CTA card needs a real
media-library attachment ID — generate the image with the normal image pipeline
and upload it through WordPress so it inherits WebP/srcset/lazy-load.

**What it deliberately does NOT do:** touch the theme's shared widget area. The
generator only ever adds its own two areas, so pages, shop and any existing
sidebar keep their current behaviour.

**Step 13 — Citation & Signature Policy (interactive)**

After Step 12, ask four questions via `AskUserQuestion`:

1. **References section required?** (default: yes)
   - Yes — every article ends with `<h2>References</h2>` + `<ol>` (mandatory; can't ship without it)
   - No — articles may publish without a References block (only choose for highly informal projects)

2. **Citation style?** (default: APA 7)
   - APA 7 (academic standard, recommended) — Author, Year, Italic Title, Journal/Source, DOI/URL
   - Numbered footnote-style — `[1] Source title. URL.`
   - Inline parenthetical only — `(Author, Year)` with no end-of-post list (only valid if `references_required=false`)

3. **Article signature paragraph?** (default: yes for commercial/YMYL projects)
   - Yes — append `<hr />` + `<p class="article-signature">` after References with last-reviewed date + author + CTA
   - No — skip the signature paragraph

4. **Author / signature wording.** Free text. Default suggestion: `"Last reviewed and updated: {Month Year}. Author: {brand_name} {industry} team. {CTA pointing to /contact/ or relevant project page}."`

5. **Publish-default behavior.** (default: `draft` — safer for review-before-live workflows)
   - **Draft (default, recommended)** — every new article is created as draft; goes live only after explicit user confirmation per article. Right choice for: commercial brands, YMYL content (health/finance/legal/cannabis), content that needs final eyeballing for pricing/spec errors, anyone whose editor reviews drafts in wp-admin preview.
   - **Auto-publish** — articles go live immediately at publish-phase end. Only choose for: personal blogs, dev diaries, low-stakes content where speed > review-checkpoint. Even with this set, individual `/article` runs can be overridden to draft by phrasing ("write but don't publish yet").

6. **Mandatory section structure.** (default: all 6 required for commercial/buyer-guide sites)

   Six H2 sections that EVERY article on this site will be required to include — regardless of format (pillar, listicle, comparison, how-to, etc.). Articles missing any required section will be vetoed by the Format-Fit quality gate. Choose the set that matches your editorial standards:

   - **Full 6 (recommended for commercial / buyer-guide / YMYL sites):** Abstract + Key Takeaways + Table of Contents + FAQ + Conclusion + References. This is the project-charlie pattern: every article begins with a callout-style Abstract H2 and a bolded-bullet Key Takeaways list, navigates via an anchored TOC, ends with a Q&A block aligned to People Also Ask, a synthesis Conclusion, and an APA-7 References block. AI-Overview citation rate and dwell time consistently improve when all six are present.
   - **Lean 4 (for news / opinion / personal-story sites):** Abstract + FAQ + Conclusion + References. Skip TOC (articles are short) and Key Takeaways (less aligned with narrative voice).
   - **Custom set:** name specific sections you want mandatory. Anything not named here is left to each format template's discretion.

   Save the resolved choice in `business-context.json :: mandatory_sections` — the seo-blog quality gate reads it on every article publish.

6c. **Weekly industry digest (行业信息周报).** (default: off — opt-in)

   Does this site want a recurring weekly industry-news digest, runnable via the `/weekly` command? A digest harvests the last 7 days of industry news across a multi-source connector layer (RSS feeds, NewsAPI, GDELT, Hacker News, Tavily news, Reddit/X community) plus an optional MCP/web research pass, then assembles a curated post (TL;DR → big story → also-this-week → optional By-the-Numbers → On-Our-Radar → FAQ → References) carrying the brand's own "so what" take, and maintains a series hub page. It reuses the normal build/optimize/publish pipeline (draft-first).

   If yes, ask for and store under `business-context.json :: weekly_digest`:
   - the niche news **sources** — `connectors.rss.feeds[]` (feed URLs), `connectors.newsapi.domains[]`, `connectors.gdelt.queries[]`, `connectors.hackernews.query`, `connectors.tavily_news.query`, `connectors.community.query`;
   - per-vertical **MCP sources** in `connectors.mcp[]` (e.g. a vertical/health project → `us-gov` FDA/CDC; a pharma project → `pubmed`/`biorxiv`; an SEO agency → none);
   - the WordPress `category_id` for the digest, the `hub_page` path (default `/weekly-digest/`; set per project, e.g. `/seo-news/` for an SEO agency), the `series_keyword`, and cadence knobs (`items_per_issue`, `lookback_days`, `follow_up_window_weeks`).

   Worked example: `projects/loamwright/business-context.json :: weekly_digest`. Absent this block, `/weekly` stops gracefully ("not configured"). The digest's required sections (TL;DR/FAQ/References) come from the skill-level `references/seo/format-mandatory-sections.json` baseline — no per-project `mandatory_sections.by_format` is needed unless the project wants to diverge.

6b. **Competitor / peer citation policy (Rule 8).** (default: ON for commercial/ecommerce sites)

   Should competitor / peer ("同行") websites be BLOCKED from appearing as a cited
   source — in-text citations, the References list, body outbound links, and JSON-LD
   citation/sameAs? (Competitor brand NAMES can still be mentioned in comparison prose;
   only citing/linking their domain is blocked.)

   - **Yes (recommended for commercial / ecommerce / competitive niches):** ask the
     user to list their direct competitor domains (and obvious competing online stores).
     Save to `business-context.json :: citation_source_policy` with
     `enforcement:"hard_veto"`, `exclude_competitor_domains:true`,
     `scope:["in_text_citations","references","outbound_links","schema_citation"]`,
     `do_not_cite_domains:[...the list...]`, `competitor_brands:[...]`,
     `allow_brand_mention_in_prose:true`, `datasheet_exception:false`,
     `sole_source_behavior:"research_replacement"`. List DIRECT competitors only —
     suppliers and standards bodies stay citable. (Suffix match blocks subdomains;
     extra entries are harmless.) The whole pipeline (fact-check → render_lint L11 →
     CITE COMP01 → pre-publish gate → verify_post) then enforces it.
   - **No (informational / non-commercial sites):** omit the block (or set
     `exclude_competitor_domains:false`). The guard becomes a full no-op.

   Either way, the SERP competitor-analysis stage will surface newly-seen competitor
   domains into `competitor-candidates.json` for review, so the list stays current.
   See root CLAUDE.md Rule 8.

6d. **CTA module (v3.34).** (default: ON for commercial sites — **mid placement**, v3.41.5)

   Should every article carry a designed conversion card (styled `.xr-cta-box`, injected
   deterministically by the mandatory `cta-injection` stage)? Ask for:
   - **funnel target** — the ONE page conversions go to (a /contact/ page, free-audit
     form, sample-order page, or /shop/). Usually `content_strategy.lead_magnet` or
     `company.contact_url` already names it.
   - **placements** — **`mid` is the DEFAULT** (after the content section at the ~35%
     word mark: the product grid + CTA sit in the article's front-middle where readers
     actually are — operator decision 2026-07-24; the pre-v3.41.5 wording here declared
     `end` the default and told operators to "reserve mid for lead-gen sites", which
     propagated end-only into 11 of 12 project configs). `end` (before Further
     Reading/References) remains a supported value but NO project or format uses
     it — the last exception (weekly-digest, v3.35.1) was retired by the operator
     on 2026-07-25, and `tests/test_cta_placement_mid_default_seam.py` fails on
     any config that reintroduces it. Do not offer `end` in the interview.
   - **heading** — MUST be one of the phrases `scripts/_core/component_headings`
     COMPONENTS['cta'] recognizes ("Your next step", "Where we can help", "Work with
     us", "Ready when you are", "Talk to the factory", "下一步"). A new phrase requires
     adding it to the classifier FIRST (otherwise the stage hard-fails — by design).
   - **2-3 copy variants per placement**, written in the project voice: one paragraph,
     bold lead, ≥1 markdown link, NO numbers (a component stat needs a [claim] marker),
     no em-dash, no urgency on age-restricted/grief verticals.

   Save to `business-context.json :: cta` (schema: `schemas/business-context.schema.json`).
   Skipping = no block written = the stage no-ops forever (informational sites). See
   `references/seo/cta-placement-data.md` for the evidence base and
   `subskills/optimize/cta-placement/SKILL.md` for the executor contract.

7. **Local SEO — business archetype.** (one of A-E; determines schema generation for keyword+location articles)

   Which best describes your business? The plugin auto-selects schema.org `@type` from this answer.

   - **A — Local brick-and-mortar.** Single physical location customers visit (restaurant, dentist, gym, café, salon). → LocalBusiness leaf w/ address.
   - **B — Service-area business.** You travel to customers; no walk-in (plumber, HVAC, electrician, mobile vet). → LocalBusiness leaf w/ `publicAccess:false` + heavy `areaServed`.
   - **C — Multi-location chain.** ≥2 physical locations under one brand (chain restaurant, dental group, multi-state law firm). → Per-location LocalBusiness + parentOrganization.
   - **D — National ecommerce.** Ship product nationwide; no brick-and-mortar (DTC ecommerce, B2B equipment supplier, dropshipper). → `OnlineStore` (Google's canonical recommendation).
   - **E — Pure SaaS / online service.** Digital-only delivery, no physical product (SaaS, online course, marketplace, fintech). → `Organization`.

   If unsure between A and B: do customers come to YOU at a fixed location (A) or do you go to them (B)? If unsure between D and E: do you sell a tangible product that gets shipped (D) or only deliver a digital service (E)?

8. **Local SEO — business category.** (free text; resolves to Schema.org leaf via 3-tier algorithm)

   What's your industry? Examples by archetype:
   - A/C: `restaurant`, `dentist`, `medical_clinic`, `legal_service`, `veterinarian`, `gym`, `real_estate_agent`, `accountant`
   - B: `plumber`, `hvac`, `electrician`, `roofer`, `auto_repair`, `landscaper`, `pet_groomer`
   - D: `cannabis_b2b_equipment`, `solar_installer_dtc`, `pet_food_dtc`, `outdoor_gear_dtc` (Tier 3 — manual override)
   - E: `b2b_saas`, `online_course_platform`, `agency_consulting`, `marketplace`

   See `references/local/industry-to-schema-mapping.md` §1-3 for the full 30+ Tier 1 + Tier 2 enum and the 3-tier resolution algorithm. Tier 1 categories (15 well-known industries) resolve deterministically to a Schema.org leaf. Tier 2 (10 fuzzy industries) get a default + warning. Tier 3 (anything else) require you to pick a Schema.org type manually.

9. **Local SEO — article pattern.** (`service_area` | `spatial_coverage`; determines schema for keyword+location articles)

   When you write a "keyword + city/state" article, do you actually SERVE that location, or are you a national/global business WRITING ABOUT it?

   - **service_area** (archetype A/B/C default) — Real geographic service. Article emits `Service.areaServed: <location>` schema. Use when you have a meaningful business presence in the location.
   - **spatial_coverage** (archetype D/E default — the "Wirecutter pattern") — National business writing about the local market. Article emits `Article.spatialCoverage + about + mentions` schema. Use when you ship/serve nationally and the location is the article's subject, not a service area.

   **IMPORTANT**: Choosing `service_area` for archetype D/E (declaring service in a place you don't actually serve) is an E-E-A-T misleading-data signal. Google has hit sites with manual actions for this. If in doubt and you're archetype D or E, pick `spatial_coverage`.

10. **Local SEO — mode.** (`off` | `opportunistic` | `primary_strategy`)

    How aggressively do you want local SEO content?

    - **off** — Plugin treats all keywords as generic; never routes to local-* templates even if keyword contains a location modifier. Choose if you only do non-local content.
    - **opportunistic (recommended for D/E)** — Plugin auto-detects "keyword + location" via `_detect_local_intent.py` and routes to local-* template; otherwise standard flow. Default for projects with full `location.*` set.
    - **primary_strategy** — Aggressive local: multi-state pillars + city pages by default. Choose for service-area businesses (B) doing dedicated local SEO.

11. **NAP information.** (optional; required for LocalBusiness schema emission)

    Business name, address, phone, email. The plugin uses this for `LocalBusiness.address`, `LocalBusiness.telephone`, etc. If not provided:
    - Archetype A/B/C: plugin emits `LocalBusiness` schema WITHOUT address — Google may downgrade rich-results eligibility (per `references/local/industry-to-schema-mapping.md` §8 penalty triggers)
    - Archetype D/E: no impact (OnlineStore/Organization don't require address per Google docs)
    - You can skip and add later via `projects/{slug}/business-context.json :: location.nap`

12. **Google Business Profile (GBP).** (optional)

    Profile URL + place_id if you have one. Plugin uses it for `sameAs` linking. Strongly recommended for archetypes A/B/C — GBP integration is the #1 local SEO ranking factor per 2026 Whitespark/BrightLocal data.

   ```jsonc
   "mandatory_sections": {
     "enforcement": "hard_veto",      // "hard_veto" | "warning" | "off"
     "sections": [
       {"id": "abstract", "h2_pattern": "^Abstract($|:)", "position": "first_body_h2"},
       {"id": "key_takeaways", "h2_pattern": "^Key Takeaways$", "position": "after_abstract"},
       {"id": "table_of_contents", "h2_pattern": "^Table of Contents$", "position": "after_key_takeaways"},
       {"id": "faq", "h2_pattern": "^(Frequently Asked Questions|FAQ)$", "position": "before_conclusion"},
       {"id": "conclusion", "h2_pattern": "^(Conclusion|Final Verdict|The Bottom Line)( *:.*)?$", "position": "before_references"},
       {"id": "references", "h2_pattern": "^References$", "h2_id": "references", "position": "last_h2"}
     ]
   }
   ```

Store the resolved answers in `business-context.json`:
```jsonc
{
  // ... other init fields ...
  "references_policy": {
    "required": true,                       // hard veto at publish if missing
    "style": "apa7",                        // apa7 | numbered | inline
    "entries_target_min": 8,
    "entries_target_max": 10,
    "entries_hard_cap": 15,
    "require_link_resolvable": true,
    "require_one_peer_reviewed_when_available": true
  },
  "article_signature": {
    "required": true,
    "html_class": "article-signature",
    "authoring_format": "markdown_italic",
    "markdown_template": "*Last reviewed and updated: {month_year}. Author: {brand_name} team. For {project_specific_CTA}, [contact our team]({contact_url}).*",
    "wording_template_rendered": "<p class=\"article-signature\"><em>Last reviewed and updated: {month_year}. Author: {brand_name} team. For {project_specific_CTA}, <a href=\"{contact_url}\">contact our team</a>.</em></p>",
    "contact_url": "https://{site_url}/contact/",
    "_authoring_note": "Writers MUST author the signature using the `markdown_template` form (markdown italic with a markdown link). The publisher's wp_publisher.py:1150-1167 auto-tags the LAST <p><em>...</em></p> with class='article-signature' at render time, producing the `wording_template_rendered` HTML. NEVER write raw <p class='article-signature'>...</p> in markdown body — markdown-it-py with html=False will escape it to literal text. See references/style/markdown-authoring-conventions.md Rule 2 and feedback_markdown_pitfalls_publisher_three_bugs."
  },
  "publish_policy": {
    "default": "draft",                     // "draft" (safe default) | "publish" (auto-publish opt-in)
    "require_confirmation_for_publish": true,
    "note": "When default=draft, individual /article runs report preview URL and wait for user 'publish' before flipping. When default=publish, articles go live at publish-phase end without checkpoint."
  },
  "mandatory_sections": {
    "enforcement": "hard_veto",
    "sections": [
      {"id": "abstract", "h2_pattern": "^Abstract($|:)", "position": "first_body_h2"},
      {"id": "key_takeaways", "h2_pattern": "^Key Takeaways$", "position": "after_abstract"},
      {"id": "table_of_contents", "h2_pattern": "^Table of Contents$", "position": "after_key_takeaways"},
      {"id": "faq", "h2_pattern": "^(Frequently Asked Questions|FAQ)$", "position": "before_conclusion"},
      {"id": "conclusion", "h2_pattern": "^(Conclusion|Final Verdict|The Bottom Line)( *:.*)?$", "position": "before_references"},
      {"id": "references", "h2_pattern": "^References$", "h2_id": "references", "position": "last_h2"}
    ]
  }
}
```

If the project later changes its mind, the user can edit `business-context.json` directly and re-run nothing — the publisher reads the policy on every publish.

**Local SEO storage** — answers from Q7-Q12 above are stored under `business-context.json :: location`:

```jsonc
{
  "location": {
    "country": "US",                                  // existing field
    "languages": ["en-US"],                           // existing field
    "business_archetype": "D",                        // Q7: A | B | C | D | E
    "business_category": "cannabis_b2b_equipment",    // Q8: free text
    "schema_org_type": "OnlineStore",                 // auto-resolved from Q7+Q8 via Tier 1/2/3
    "additional_type": "https://www.productontology.org/id/Horticultural_lighting",  // Tier 3 only
    "ymyl_flag": false,                                // auto-set by Tier 1 (medical/legal/financial=true)
    "local_article_pattern": "spatial_coverage",     // Q9: service_area | spatial_coverage
    "local_seo_mode": "opportunistic",                 // Q10: off | opportunistic | primary_strategy
    "nap": {                                            // Q11: optional (NAP block)
      "business_name": "Project Charlie",
      "address": {
        "streetAddress": "...",
        "addressLocality": "...",
        "addressRegion": "...",
        "postalCode": "...",
        "addressCountry": "US"
      },
      "telephone": "+1-XXX-XXX-XXXX",
      "email": "hello@example.com"
    },
    "gbp": {                                            // Q12: optional (GBP)
      "profile_url": "https://www.google.com/maps/place/...",
      "place_id": "...",
      "verified": true,
      "primary_category": "..."
    },
    "service_areas": {                                 // optional, used when local_seo_mode=primary_strategy
      "type": "national",                              // "national" | "regional" | "city-only" | "global"
      "primary_states": ["CA", "CO", "OK", "MA"],
      "secondary_states": [...],
      "excluded_states": [...]
    }
  }
}
```

The schema-generator subskill reads these on every `/article` publish to auto-select Schema.org type per `references/local/industry-to-schema-mapping.md`. The `_detect_local_intent.py` script reads `local_seo_mode` to decide whether to route keyword+location articles to local-* templates.

**Step 11.5 — Featured-image inline policy (interactive)**

WordPress themes vary in how they render the post's featured image:
- **Most themes (Woodmart, Astra, GeneratePress with default settings)** auto-render the featured image at the top of every single-post page. Including it in the post body produces a visible duplicate.
- **Custom themes / child themes / themes with featured-media auto-render disabled** require the body to embed the cover inline, otherwise it never appears.

Ask the user:

> "Does your WordPress theme auto-render the featured_media image at the top of single-post pages?
>
> Options:
> (1) **Yes — theme auto-renders featured image** (default for Woodmart, most modern WP themes). The article body will NOT include the cover image inline — only the section-level images go in the body. The cover image is still uploaded and set as `featured_media` for the theme to render automatically. This is the safe default.
> (2) **No — theme does NOT auto-render featured image**. The article body WILL include the cover image inline, by default between the Abstract and Key Takeaways H2s (hero-shot position). The cover is still set as `featured_media` for OpenGraph and schema metadata.
> (3) **Mixed / I'm not sure** — pick option 1 (safe default); we can flip it later by editing `business-context.json :: featured_image_inline_policy`."

Save the resolved choice in `business-context.json`:

```jsonc
{
  "featured_image_inline_policy": {
    "mode": "no_inline",                  // "no_inline" (default) | "inline" | "manual"
    "inline_position": "after_abstract",  // when mode=inline: "after_abstract" | "after_h1" | "after_toc" | "after_key_takeaways"
    "rationale": "Set during /init based on theme question. Edit this field directly to change behaviour for future articles.",
    "set_at": "{ISO_DATE}",
    "set_in_session": "{task_id}"
  }
}
```

Behaviour at publish time:
- `mode: "no_inline"` — wp_publisher excludes the cover slot from body image processing. Theme auto-renders featured image.
- `mode: "inline"` — wp_publisher injects the cover as a Gutenberg `<!-- wp:image -->` block at the configured `inline_position`. Theme typically does NOT auto-render (per project's theme config).
- `mode: "manual"` — operator handles cover placement per article (the article's draft.md will contain an explicit `[IMAGE-SLOT-cover]` token where they want it).

The 2026-05-20 project-charlie incident on post 37063 was a `mode: "no_inline"` situation
where the cover was incorrectly included in body. The 2026-05-21 project-charlie design
change flipped that project to `mode: "inline"` after the theme template was updated
to suppress featured-media auto-render.

If the user picks option 3 and you have no way to test, set `mode: "no_inline"` as
the safe default — duplicates are visible immediately; missing covers in body when
theme also doesn't render are less obvious. See memory: [[feedback-no-inline-featured-image]]

**Step 11.6 — Image-pipeline policy (interactive; safe defaults baked in)**

Two policy fields control how images are generated for each `/article` run on this project. The recommended defaults reflect the 2026-05-21 deep-research findings (memories: [[feedback-batch-image-default-and-polling]], [[feedback-image-gen-forks-post-plan]]); both can be changed later by editing `business-context.json` directly.

| Field | Recommended | Why |
|---|---|---|
| `image_pipeline_policy.mode` | `"realtime"` | OpenAI batch image API takes ~45 min wall time for a 4-image article in current conditions. Realtime parallel-of-4 finishes in ~3 min, costs 2× ($0.66 vs $0.33), but for operator-driven publish flows the ~12-minute wall-time savings is worth more than the $0.33 cost delta. Switch to `"batch"` only for overnight bulk runs. |
| `image_pipeline_policy.kickoff_timing` | `"post_plan"` | Image prompts derive from the outline (stable across repair rounds), not the prose. Forking image generation as a background task right after `outline-architect` overlaps the ~3-min image API time with the ~15-min foreground Build+Optimize phases — net effect: image API time becomes invisible to the operator. |
| `image_pipeline_policy.realtime_parallel_workers` | `4` | `generate_realtime_all()` uses `ThreadPoolExecutor(max_workers=4)`. Tier-3+ OpenAI image-API accounts permit 5+ concurrent requests; 4 is the safe ceiling with rate-limit headroom. Lower to 2-3 only if 429s start appearing in `image_pipeline.log`. |

Ask the user (only if they want to deviate from these defaults — otherwise just bake them in silently with a one-line confirmation):

> "I'm setting up the image-generation policy with the recommended defaults: realtime mode (~3 min, $0.66 per 4-image article), forked off in the background right after the outline (so image API time doesn't block your wait), 4 concurrent workers. This is the right default for operator-driven publish runs.
>
> Want to change any of these? (e.g. you'll be running 50+ articles overnight where the 50% batch cost savings matters more than wall-time)"

If user accepts defaults, write:

```jsonc
{
  "image_pipeline_policy": {
    "mode": "realtime",
    "kickoff_timing": "post_plan",
    "realtime_parallel_workers": 4,
    "max_wait_minutes": 25,
    "poll_interval_seconds": 60,
    "fallback_enabled": true,
    "rationale": "Set during /init with recommended defaults per 2026-05-21 research. Edit this field directly to change behaviour for future articles.",
    "set_at": "{ISO_DATE}",
    "set_in_session": "{task_id}"
  }
}
```

If user wants batch mode (overnight bulk): same shape, just `"mode": "batch"` and raise `"max_wait_minutes"` to 60 to give batch a fair chance.

If user wants legacy serial ordering for any reason: `"kickoff_timing": "publish"` (image gen runs in Phase Publish only, blocks the publisher).

**Step 11.7 — Image brand identity: visual style, cover text overlay & watermark (interactive)**

Step 11.6 sets *how* images are generated (mode/size/aspect); this step sets *what they look like and how they are branded*. It writes `projects/{slug}/brand-guideline.yaml`, which is the AUTHORITATIVE file `agents/image-prompt-designer.md` reads for visual style, and which drives the post-process brand watermark (`scripts/openai/image_watermark.py`, auto-invoked by the pipeline after each save). **If this file is absent, the designer falls back to a generic prefix, covers get no headline overlay or brand label, and NO watermark is ever applied** (the watermark step is gated on `brand-guideline.yaml :: watermark.enabled`). This was the 2026-06-06 project-kilo gap: covers shipped unbranded with no watermark because the project had no brand-guideline.yaml. Always run this step at init.

Ask the user via `AskUserQuestion` (4 questions; offer the recommended option first):

1. **Visual style** — `photo-realistic-editorial` (recommended for product/B2B/commercial: real materials, bright trade-catalog look) vs `clean-technical-illustration` (diagram-forward) vs `lifestyle` (people/context). Drives `visual_style` + the shared `art_direction_prefix`.
2. **Cover text overlay** — "Should blog **cover** images carry a short headline burned into the image (2-5 word hook, e.g. 'GOLD PLA SOURCING'), like a magazine cover?" Recommended **yes** for editorial/buyer content. Sets `featured_image.text_overlay` + `text_kind: short_hook` + `text_style` (use brand accent color for the underline keyline; pick the lighter/more legible of the two brand colors if the primary is dark).
3. **Brand watermark** — "Stamp a small brand-name watermark on every generated image (crisp post-process text, bottom-right)?" Recommended **yes** for brand recognition / scrape attribution. Sets `watermark.enabled: true`, `watermark.text: "{BRAND}"`, `apply_to: all`. (Default off only if the user explicitly wants clean unmarked images.) Note: this is a PIL text overlay — no logo asset file is needed; if the user later supplies a logo PNG that is a separate enhancement.
4. **In-scene packaging label** — confirm the brand name to render on spools/cartons/boxes (`packaging_branding.label_text`), and that competitor brands must never be rendered (`forbid_third_party_brands: true`, listing the project's real competitors in the negative baseline).

Then write `projects/{slug}/brand-guideline.yaml` (mirror the canonical schema used by sibling projects — see `projects/project-juliet/brand-guideline.yaml` and `projects/project-kilo/brand-guideline.yaml` for working examples). Required blocks: `visual_style`, `art_direction_prefix`, `realism`, `packaging_branding` (label_text + forbid_third_party_brands), `featured_image` (text_overlay + text_kind + text_style + aspect_ratio/size matching Step 11.6 cover policy), `section_image` (text_overlay:false + inline aspect/size), `watermark` (enabled/text/position/opacity/color/font_size_frac/margin_frac/shadow/apply_to), `negative_prompt_baseline`.

Colour note: express the brand palette inline in `art_direction_prefix` + `featured_image.text_style`. If the brand primary is dark (poor legibility as a white-text underline on bright covers), route the cover-overlay keyline to the lighter brand accent (the project-kilo guideline uses copper `#9E5A2E` for the underline because its teal `#0E4F4A` is too dark).

If the user skips this step entirely, write a minimal `brand-guideline.yaml` with `visual_style` + `art_direction_prefix` + `negative_prompt_baseline` and `watermark.enabled: false`, so the designer still gets a real style (never the generic fallback) — and tell the user they can enable the overlay/watermark later by editing the file.

**Step 12 — Article CSS Design (interactive)**

After synthesis, ask the user:

> "Would you like me to design a scoped CSS stylesheet for your blog articles? It uses your
> brand colors and fonts to style H2/H3 headings, tables, figures + captions, abstracts,
> key-takeaway lists, blockquotes, references, FAQ, and mobile/print breakpoints. The CSS
> is scoped to a `.{slug}-pillar` wrapper so it won't conflict with your theme. The publisher
> auto-injects it inline on every article — no Customizer access needed.
>
> Options: (1) Generate with brand defaults  (2) Preview first  (3) Skip"

If yes (option 1 or 2):
```python
from scripts.build.article_css_generator import generate
result = generate(site_slug)
# result -> {css_path, min_path, wrapper_class, css_size_bytes, min_size_bytes}
```

If preview (option 2), show the user the first 40 lines of the generated CSS and ask for confirmation
before keeping it; if they want changes, they can edit `projects/{slug}/brand/article-css.css` directly
and re-run `python -m scripts.build.article_css_generator {slug}` after editing brand-config.json colors.

If skip (option 3), the publisher will fall back to wrapping body in `<div class="{slug}-pillar">` without
inline `<style>`, so theme CSS still has a stable hook if the user wants to add custom styling later.

**Step 13.5 — Conversion Offer Strategy (interactive)**

Branches on the `business_archetype` resolved earlier in this flow (Step 13's
Q7 A-E archetype classification used for schema.org type selection — see
`location.business_archetype` above).

- **Service business (archetype A/B/C/E — professional services, agencies):**
  Ask the user to confirm/collect `conversion_offers.services[]`. Offer to
  pre-fill by re-reading the site's own service pages:
  ```bash
  python3 -c "
  from scripts.wordpress.wp_client import WPClient
  c = WPClient('{slug}')
  r = c.get('/wp/v2/pages', params={'per_page': 50, '_fields': 'id,slug,link,title'})
  for p in r.json_data: print(p['id'], p['slug'], p['title']['rendered'])
  "
  ```
  For each confirmed service page, extract `positioning`/`persona`/
  `distinct_value_prop`/`own_page_cta_copy` (its own CTA button text, if any)
  from the fetched content — same method used for the loamwright rollout
  (2026-07-08). Then ask for `company.team[]` (`name`/`role` required, plus
  `photo_media_url`/`specialty_services[]` — check the About/Team page's own
  media for existing headshots via `/wp/v2/media?search={name}`) and
  `company.proof_points[]` (`type: "case_study"|"stat"` plus
  `subject`/`metric`/`period`/`url`/`claim` — real case-study numbers, from
  the Home/About page or client-provided). Write a project-level routing file
  (referenced from `conversion_offers.category_routing_map`, e.g.
  `projects/{slug}/service-routing-map.json`) mapping each blog category
  pillar (from Step 14's taxonomy, or a placeholder if Step 14 hasn't run
  yet — revisit after Step 14) to the matching service `slug`. Schema for all
  of the above: `schemas/business-context.schema.json :: conversion_offers` /
  `:: company`.

- **Ecommerce (archetype D):** Enable the shortcode-based product-recommendation
  mechanism by **default** (v3.38.0 — the resolver shipped in Tasks 3-5 of the
  2026-07-09 CTA completion plan and is live-verified on 2 real WooCommerce
  projects, see `projects/project-echo/business-context.json` and
  `projects/project-hotel/business-context.json`). Only skip if the user
  explicitly declines.

  1. **Sync the live catalog:**
     ```bash
     python -m scripts.wordpress.wc_catalog_sync --project-slug {slug} --json
     ```
     This writes `projects/{slug}/product-catalog.json` (products +
     categories, `count` per category). Read-only against `/wc/v3` — never
     touched again by the LLM pipeline; `cta_brief_builder.py`'s ecommerce
     resolver reads this cached file at build time, not the live API.

  2. **Present the synced categories with their `count`** and ask the user to
     confirm `default_category` — recommend the best-populated **in-stock**
     top-level category (highest `count`, `parent: 0`) as the default. This is
     the fallback used ONLY when neither of the resolver's two content-based
     strategies matches (see step 4 below) — it is not the primary mechanism.

  3. **Ask for `fallback_url`** — the shop/collection URL used as the brief's
     `target_url` (WooCommerce category permalinks aren't in the cached
     catalog, so this is supplied directly). Usually `{site_url}/shop/`.

  4. **Ask about constraints** — two real per-project examples to cite:
     - **Person-blocks policy** (`constraints.no_person_blocks: true`) — set
       this when the project's author-entity policy is Organization-only/YMYL
       (no named-person CTA blocks). Worked example: `project-echo` (vertical
       vertical, `no_person_blocks: true` because `author_entity.mode:
       editorial_team` forbids named-person/avatar CTA blocks).
     - **Tone sensitivity** (`constraints.tone: "grief_safe"` +
       `constraints.banned_phrases[]`) — set this for bereavement/sensitive
       verticals where urgency language ("flash sale", "act fast", "limited
       stock") reads as tone-deaf. Worked example: `project-hotel` (pet-memorial
       vertical, `tone: "grief_safe"` triggers `cta_tone_check.py`'s grief
       sublexicon gate; `banned_phrases` adds commerce-pushy phrases the
       lexicon doesn't already cover).
     Any other project-specific constraint keys pass through verbatim into
     `cta-brief.json :: constraints` and are readable by `cta-writer` and the
     tone gate even without dedicated schema support.

  5. Write the result to `business-context.json :: conversion_offers`:
     ```jsonc
     {
       "conversion_offers": {
         "business_model": "ecommerce",
         "default_category": "the-recommended-slug",
         "fallback_url": "https://{site_url}/shop/",
         "constraints": { "no_person_blocks": true }   // or tone/banned_phrases, or both
       }
     }
     ```
     `catalog_path` is optional — omit it to use the default
     `projects/{slug}/product-catalog.json`.

  6. **Ensure the AND-gate is closed.** `conversion_offers` only powers the
     brief-builder + cta-writer (Steps 1-2 of the CTA pipeline) — the injector
     (Step 3) still requires the LEGACY `business-context.json :: cta.enabled:
     true` (+ `cta.placements`) to actually place anything (see Step 13's 6d
     above and `subskills/optimize/cta-placement/SKILL.md`'s "AND-gate"
     warning). If Step 13's 6d question was answered "no CTA module" for this
     project, either revisit that answer now or the ecommerce brief will be
     resolved and authored but never injected.

  **How the resolver actually matches (for context when explaining this to
  the user):** `cta_brief_builder.py`'s ecommerce branch tries, in order: (a)
  **SKU verbatim** — a product's exact name appears in the article body, cap 3
  hits, emits `[products ids=1,2,3 columns=3 orderby=menu_order]`; (b)
  **category token-overlap** — the article's keyword+title+H2 tokens overlap
  ≥50% with an in-stock category's name+slug tokens (with ≥1 non-generic
  token), emits `[products category=slug limit=3 columns=3
  orderby=popularity]`; (c) **default_category fallback** — the category
  configured above, same shortcode shape. All shortcode attribute values are
  emitted **quote-less** (`category=slug` not `category="slug"`) — this is a
  deliberate root-cure (v3.38.0 Task 4): the publisher's markdown-it
  conversion HTML-escapes literal `"` in plain-text nodes to `&quot;`, which
  breaks WordPress's `shortcode_parse_atts()`; the quote-less form has nothing
  left to mis-escape and is proven safe by
  `tests/test_products_shortcode_render_passthrough.py`. If none of the three
  strategies resolves (empty/malformed catalog, non-in-stock default), the
  brief degrades gracefully to a link-only CTA (`target_url` = `fallback_url`,
  no shortcode) — the pipeline never halts.

  **Periodic re-sync.** Re-run `wc_catalog_sync` whenever the catalog changes
  materially (new product lines, categories restocked/discontinued, price
  tiers shifted) — the cached `product-catalog.json` is the resolver's ONLY
  view of the store and goes stale silently otherwise. There's no automatic
  schedule; treat it as a manual maintenance step, e.g. before a batch of new
  articles in a refreshed category.

  If the user explicitly declines ecommerce CTA enablement: `conversion_offers`
  stays unset for this project (same absent-config behavior as below).

Absent this step's data entirely (user declines it, or an existing project
predates v3.38): `conversion_offers` stays unset,
`scripts.optimize.cta_brief_builder` writes only its no-config sentinel
(`resolved_service:null`, `skipped_no_config:true`) instead of a resolved
brief, `cta-writer` is auto-skipped, and `cta_injector.py` runs the legacy
static-variant path (`business-context.json :: cta`, Step 13's 6d) unchanged.
This step is purely additive — see `subskills/optimize/cta-placement/SKILL.md`
for the full three-stage contract this data feeds.

**Step 14 — Category Architecture (interactive, optional but recommended)**

After Step 13 (Citation & Signature Policy), ask the user:

> "Would you like me to design a blog category architecture now? It maps your content to 5–10 top-level
> categories with 4–6 subcategories each, every category gets a tight description (35–80 words), and
> all RankMath SEO meta (title, description, focus keyword, OG/Twitter) gets pre-filled. The architecture
> follows the intent-classified content-type pattern that anchors topical authority for the site.
>
> Options: (1) Design now (interactive)  (2) Use the project-charlie template as a starting point  (3) Skip"

If yes (option 1 or 2), delegate to the `wordpress-category-setup` subskill:

```
Task(
  subagent_type="general-purpose",
  description="Design WordPress category taxonomy",
  prompt="""
  Use the wordpress-category-setup subskill to design and apply a category architecture
  for project {site_slug}. Mode: interactive (option 1) OR apply-from-template (option 2).
  Reference: subskills/init/wordpress-category-setup/SKILL.md.
  """
)
```

The subskill handles: design interview, RankMath meta generation, validation against the 6 design principles
(`subskills/init/wordpress-category-setup/references/category-design-principles.md`), apply via
`scripts/wordpress/setup_categories.py`, and live-URL verification.

If skip (option 3), the project starts with WordPress's single default `Uncategorized` category. Users can run
`/setup-categories` later when they're ready. Note: `/article` will still publish posts under `Uncategorized`
or whatever single category the publisher picks — but topical-authority signal is weak until the architecture
is set up.

**Critical Step 0.5 implementation**:

```python
from scripts._core.project_paths import ensure_project_tree, project_root
root = ensure_project_tree(site_slug)
# Now safe to write to brand/, research/, audits/, .seo/, etc.
```

## Inputs

- `state.brief.primary_keyword` = "site_url" interpretation
- `state.brief.url`              = the URL passed
- Optional `--depth quick|normal|deep` (default normal=40 pages)
- Optional `--brand "Acme Inc"` / `--industry "fishing"` to skip detection
- Optional `--skip-wizard` (advanced: assume credentials are already configured)

## Outputs (canonical layout per `references/project-folder-layout.md`)

```
projects/{slug}/
├── project.yaml                       Root — site metadata + init summary
├── internal-links-map.md              Root — empty initially; populated by publisher
├── PROJECT.md                         Root — human-readable summary (open first)
├── init-report.md                     Root — issues found + priority recommendations
│
├── .seo/                              Runtime state + cache (mostly gitignored)
│   ├── state.json                     Active pipeline state
│   ├── change-log.json                7-day undo log
│   ├── baselines/{snapshot}.sqlite    Drift baseline
│   ├── _meta/
│   │   ├── init-version.txt
│   │   ├── init-duration.json         Per-stage timing
│   │   └── init-cost.json             Total spend during /init
│   ├── research-cache/                70d TTL
│   ├── screenshots/                   ATF / mobile / desktop captures
│   └── observability/                 (gitignored — debug logs)
│
├── brand/                             Brand assets
│   ├── brand-config.json              From setup_wizard (Tier 4)
│   ├── brand-identity.json            Auto-detected: company, NAP, founded, socials
│   ├── voice-samples/
│   │   ├── self-described.md          What client says about their voice
│   │   ├── actual.md                  Data-derived voice from existing content
│   │   └── discrepancy.md             ⭐ THE DIFF between the two
│   └── personas/
│       ├── primary.json
│       └── secondary-1.json
│
├── research/                          Research outputs
│   ├── business-context.md            Machine-readable; all skills inherit from this
│   ├── tech-stack.json                CMS / plugins / fonts / CDN
│   ├── product-intelligence.json
│   ├── competitors.json               3-5 true competitors (SERP-overlap-derived)
│   ├── seo-baseline.json
│   ├── geo-baseline.json              AI engine recognition per chatgpt/pplx/claude/gemini
│   ├── existing-clusters.json
│   ├── target-keywords.md
│   ├── keyword-universe.md
│   ├── ai-citation-targets.md
│   └── ai-probes/{date}.json          AI engine probe raw responses
│
├── articles/                          (empty until first /article publishes)
├── clusters/                          (empty until first /cluster runs)
├── metrics/                           (empty until first gsc_api_ingest)
├── audits/                            (empty until first outcome_tagger / rank_tracker)
│   ├── rank-history/
│   ├── drift-reports/
│   └── ai-citations/
├── assets/images/                     (empty until first article publishes)
└── credentials/                       (gitignored)
    └── (populated by setup_wizard)
```

## Failure modes

| Failure | Action |
|---|---|
| Tier-1 credentials missing + user refuses to provide | Halt with helpful error message |
| Tier-2 missing | Warn; mark project as `partial_setup`; some features unavailable |
| Tier-3 (WP) missing | Warn — `/publish` won't work; can revisit later via `/setup-wizard` |
| 5-tier waterfall all fail for a page | Write to `unreachable.json`; don't block |
| AI probe API timeout | Mark `probe_failed: true`; continue with stale/no GEO data |
| Cost exceeds `init_max_usd` cap | Halt with summary; can retry with `--depth quick` |
| Active project already exists for this URL | Auto-suffix slug `example-com-2`, OR offer `/init <url> --refresh` |

## Active project pointer

After successful /init, write:
```
~/.xuanran-seo/active-project  →  example-com
```

All subsequent `/article` etc. commands read this single line to know which
project's context to inherit. User can switch via `/switch <slug>`.

## Cost & time

| Mode | Pages | Time | API Cost |
|---|---|---|---|
| quick | 10 | <1 min | $0.15-0.25 |
| **normal** | **40** | **3-5 min** | **$0.55-0.95** |
| deep | 100 | 8-15 min | $1.50-2.50 |

`scripts/_core/cost_guard.estimate()` runs before crawl to surface budget.

## See also

- `SKILL-ARCHITECTURE-V3-INIT-COMMAND.md` (in plugin docs) — full /init spec
- `scripts/_core/setup_wizard.py` — credential collection helper
- `scripts/fetch/multi_tier_fetch.py` (TODO M1.5) — 5-tier waterfall
- `subskills/cross-cutting/memory-manager/SKILL.md` (TODO) — project archival
