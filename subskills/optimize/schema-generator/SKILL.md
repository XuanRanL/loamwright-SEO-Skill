---
name: schema-generator
description: Generate complete JSON-LD @graph for an article — BlogPosting/Article + Person + Organization + BreadcrumbList + FAQPage + ImageObject + VideoObject. Stable @id references for entity linking. Validates against Google requirements + warns deprecated types (HowTo, SpecialAnnouncement, Q&A). +13% AI citation likelihood when 3+ schema types present.
allowed-tools: [Read, Write, Bash]
disable-model-invocation: false
user-invocable: true
---

# Schema Generator · JSON-LD @graph

Generates complete, validated JSON-LD structured data for blog posts. The head-level
article graph (meta.json :: schema_jsonld) uses the combined `@graph` pattern with
stable `@id` references; BODY supplemental blocks (`workspace/{task}/schema.json`)
use the `blocks[]` shape — one entry per rendered `<script>` tag, because
`verify_post` check 17 counts TAGS, not `@graph` members (see Step 11).

> **Rule 8 — no competitor domains in URL fields.** Any `citation`, `sameAs`, `url`, or
> `isBasedOn` value you emit must NOT point at a competitor/peer ("同行") domain.
> `sameAs`/`url` are brand-owned (safe); if you ever emit a `citation` array from the
> article's sources, run each URL through
> `python -m scripts._core.competitor_domains --task {tid} --check-url "{url}"` first.
> `verify_post` check 28 + the CITE `COMP01` veto scan the rendered schema, so a
> competitor URL here will block publish. See root CLAUDE.md Rule 8.

## SEO-plugin coordination (READ THIS FIRST)

Before generating ANY schema type, read `projects/{slug}/business-context.json :: wordpress.seo_plugin_schema_provided`. This is an explicit list of `@type` values the project's SEO plugin (RankMath, Yoast, AIOSEO, etc.) already emits natively in `<head>` on every post. **DO NOT regenerate those types in `schema.json`.** Duplicating them produces:
- Either silent Google-side de-duplication (harmless but wastes bytes), OR
- Worse: competing `@id` references that fragment entity-linking signals across head and body, hurting structured-data extraction confidence.

**Canonical project-charlie example** (RankMath Pro + global Breadcrumb JSON-LD enabled, 2026-05-21+):
```json
"seo_plugin_schema_provided": [
  "Article", "BlogPosting", "Organization", "Person",
  "WebPage", "WebSite", "ImageObject", "BreadcrumbList"
]
```

Per the list above, **for project-charlie the schema-generator should ONLY emit body-supplemental types not in the list**, i.e.:
- ✅ `FAQPage` (always emit if FAQ section exists; highest AI-Overview citation value) — see Hard Rule 6, near-mandatory
- ✅ `ItemList` (for listicle / comparison-review formats with a ranked list, OR any compared/tabular set of >=3 named entities — the default 2nd block; see Hard Rule 6)
- ✅ `Recipe`, `Course`, `Event`, `VideoObject`, `SoftwareApplication` (format-dependent)
- ❌ `HowTo`, `Dataset`, `Q&A`, `SpecialAnnouncement` — NEVER as a standalone top-level `@type` (Step 10 deprecated-type list; `agents/schema-validator.md`'s T09 veto scan hard-rejects these as a primary type). `HowTo` content may still be nested as `Article.mainEntity: HowTo` if a project's `seo_plugin_schema_provided` doesn't already cover `Article` in head — do not emit it as its own top-level block.
- ❌ Skip `BlogPosting`, `Organization`, `Person`, `BreadcrumbList`, `WebPage`, `WebSite`, `ImageObject`, `Article` — RankMath handles all 8

For projects WITHOUT `seo_plugin_schema_provided` set (no policy declared), the legacy behavior applies — emit everything. The `wp_publisher._append_custom_schema_blocks` also defense-in-depths this filter: even if `schema.json` contains a forbidden type, the publisher skips it on write.

**Root cure (2026-07-08):** the `schema-generator` dispatch_prompt in `scripts/pipeline/orchestrator.py` used to hardcode the project-charlie 8-type list above as a UNIVERSAL "Forbidden body types" clause applied to every project, regardless of that project's actual config (or its absence). This silently disagreed with `scripts/validate/cite_scorer.py`, which reads the SAME config key and correctly credits nothing when it's absent — so a project missing this config (loamwright, found via a real 3-article batch: CITE stuck at 72.5-75/100 "FIX" instead of "SHIP" on all 3 articles) got dinged by the scorer for missing head-level Organization/Person/WebSite schema, while the dispatch_prompt SIMULTANEOUSLY told the schema-generator agent those types were already covered and forbidden from the body. The orchestrator now computes this clause per-project at dispatch time via `_schema_forbidden_types_text(project_slug)` — reading the real config and falling back to the "no policy declared" language above when absent, instead of assuming any single project's list is universal. Test: `tests/test_schema_forbidden_types_project_aware_2026_07_08.py`.

**Verification:** post-publish, `scripts/wordpress/verify_post.py` check 17 scans BOTH head and body JSON-LD. Required schema types are satisfied if they appear in either context. So skipping a head-provided type from body still passes verify.

## Local-aware schema generation (v5.0 Stage B — 2026-05-22)

Before emitting schema, check `business-context.json :: location.*` for these fields:

- `location.business_archetype` (A | B | C | D | E)
- `location.business_category` (string)
- `location.schema_org_type` (auto-resolved leaf, e.g. `Dentist`, `OnlineStore`, `LegalService`)
- `location.additional_type` (optional ProductOntology URL for niche industries)
- `location.local_article_pattern` (`service_area` | `spatial_coverage`)
- `location.ymyl_flag` (boolean)
- `location.nap` (NAP block, optional)
- `location.gbp` (Google Business Profile, optional)

If these fields are present, generate schema per the 5-archetype + 3-tier resolution model in `references/local/industry-to-schema-mapping.md`. Decision flow:

### When NOT to emit LocalBusiness/Organization in body

If `location.schema_org_type` matches one of the head-emitted types (already in `wordpress.seo_plugin_schema_provided`), skip it — same de-duplication rule as the standard flow above.

If `business-context.json` has no `location.*` block at all, fall back to legacy behavior (emit nothing about location; treat as non-local content).

### Archetype A/B/C (LocalBusiness leaf in body)

When `location.business_archetype ∈ {A, B, C}` AND `location.schema_org_type` resolves to a LocalBusiness sub-type AND it's NOT in `seo_plugin_schema_provided`:

```jsonc
{
  "@type": "<schema_org_type>",                  // e.g. "Dentist", "Plumber", "Restaurant"
  "@id": "{site_url}#localbusiness",
  "name": "<location.nap.business_name>",
  "url": "{site_url}",
  "telephone": "<location.nap.telephone>",
  "email": "<location.nap.email>",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "<from location.nap.address>",
    "addressLocality": "...",
    "addressRegion": "...",
    "postalCode": "...",
    "addressCountry": "..."
  },
  "areaServed": [                                // for archetype B (service-area), populate from location.service_areas
    {"@type": "City", "name": "Denver"},
    {"@type": "City", "name": "Boulder"}
  ],
  "publicAccess": false,                          // archetype B only (no walk-in)
  "sameAs": ["<location.gbp.profile_url>"]
}
```

**Multi-location chain (archetype C)**: emit EACH location as its own LocalBusiness with a unique `@id` + `parentOrganization` link to the root `Organization`. Don't collapse into one entity with multiple addresses.

### Archetype D (OnlineStore + Wirecutter pattern)

When `location.business_archetype == "D"` (national ecommerce, no brick-and-mortar):

```jsonc
{
  "@type": "OnlineStore",                         // canonical per developers.google.com/search/docs/appearance/structured-data/organization
  "@id": "{site_url}#onlinestore",
  "name": "<location.nap.business_name OR business name from site>",
  "url": "{site_url}",
  // NOTE: NO `address` (no physical storefront) and NO `Service.areaServed` (would be misleading)
  "sameAs": ["<location.gbp.profile_url>", ...other social URLs...]
}
```

For LOCAL articles ("keyword + location" pattern), use **spatial_coverage** pattern. NEVER emit `Service.areaServed: <location>` for archetype D — declaring service-area for a place you don't actually service is an E-E-A-T misleading-data signal.

### Archetype E (Organization, no LocalBusiness, no OnlineStore)

Pure SaaS / digital-only:

```jsonc
{
  "@type": "Organization",
  "@id": "{site_url}#organization",
  "name": "<business name>",
  "url": "{site_url}",
  "sameAs": [...]
}
```

LOCAL articles use spatial_coverage pattern, same as archetype D.

### Local-article schema (location-mentioning blog posts)

When the article is local-intent (state.brief.local_mode == true) AND `location.local_article_pattern` is set:

**Pattern `service_area`** (archetypes A/B/C default): emit Service schema with areaServed.

```jsonc
{
  "@type": "Service",
  "@id": "{post_url}#service",
  "provider": {"@id": "{site_url}#localbusiness"},
  "areaServed": {
    "@type": "City",                              // or State, or AdministrativeArea
    "name": "Denver",
    "containedInPlace": {"@type": "State", "name": "Colorado"}
  },
  "serviceType": "<inferred from business_category>"
}
```

**Pattern `spatial_coverage`** (archetypes D/E default — Wirecutter): emit Article.spatialCoverage + Article.about + Article.mentions.

```jsonc
{
  "@type": "Article",
  "@id": "{post_url}#article",
  "spatialCoverage": {
    "@type": "Place",
    "name": "<state/city name>",
    "geo": {"@type": "GeoCoordinates", "addressCountry": "US", "addressRegion": "OK"}
  },
  "about": {"@id": "{post_url}#place"},
  "mentions": [
    {"@type": "Organization", "name": "<local utility / trade assoc>", "url": "..."},
    {"@type": "GovernmentOrganization", "name": "<local regulator>"}
  ]
},
{
  "@type": "Place",
  "@id": "{post_url}#place",
  "name": "<market description>",
  "geo": {"@type": "GeoShape", "addressCountry": "US", "addressRegion": "OK"}
}
```

### YMYL extras (when `location.ymyl_flag == true`)

Emit per business_category:
- Medical (Dentist, MedicalClinic, Chiropractic) → `Article.reviewedBy: Person.hasCredential.MedicalDoctor` + `lastReviewed`
- Legal (LegalService) → `Article.author.hasCredential: BarMembership (state-specific)` + `lastReviewed`
- Financial (FinancialService, AccountingService) → `Article.author.hasCredential: CPA/CFP/CFA` + `lastReviewed`

### Decision summary

```
business_archetype + business_category present in business-context.json?
├── NO → legacy behavior (no LocalBusiness, no spatial_coverage; only standard supplementals)
└── YES
    ├── schema_org_type ∈ seo_plugin_schema_provided → SKIP that emission
    └── ELSE → emit per archetype:
        ├── A/B/C → LocalBusiness leaf (+ areaServed for B; + parentOrganization for C)
        ├── D    → OnlineStore (no address, no areaServed)
        └── E    → Organization

    AND if state.brief.local_mode == true:
        ├── local_article_pattern = service_area → Service + areaServed
        └── local_article_pattern = spatial_coverage → Article.spatialCoverage + about + mentions

    AND if ymyl_flag == true → reviewedBy + hasCredential + lastReviewed
```

See `references/local/industry-to-schema-mapping.md` for the full canonical model + edge cases (deprecated Attorney, cannabis dispensary without native type, etc.).

## When to invoke

- After `meta-builder` completes (Stage: meta-built)
- Before `wordpress-publisher` (publish needs the schema for `<head>` injection)
- Auto-triggered by L2 phase-publish orchestrator
- User can re-generate via `/schema workspace/{task_id}/draft.md`

## Workflow

### Step 1: Read content + extract schema data

Read the article + meta.json + brief.json. Extract:
- **Title** (headline)
- **Author** (name, job title, social links, credentials)
- **Dates** (datePublished, dateModified)
- **Description** (meta description)
- **FAQ section** (Q&A pairs)
- **Images** (cover URL, dimensions, alt text; inline images)
- **Organization info** (site name, URL, logo)
- **Word count** (approximate from content length)
- **Tags/categories** (for BreadcrumbList category)
- **Slug** (from frontmatter)
- **Videos** (any embedded YouTube)

### Step 2: Generate BlogPosting (or Article / NewsArticle) schema

Complete with all required + recommended properties:

```json
{
  "@type": "BlogPosting",
  "@id": "{siteUrl}/blog/{slug}#article",
  "headline": "Post title (max 110 chars)",
  "description": "Meta description (150-160 chars)",
  "datePublished": "YYYY-MM-DD",
  "dateModified": "YYYY-MM-DD",
  "author": { "@id": "{siteUrl}/author/{author-slug}#person" },
  "publisher": { "@id": "{siteUrl}#organization" },
  "image": { "@id": "{siteUrl}/blog/{slug}#primaryimage" },
  "mainEntityOfPage": {
    "@type": "WebPage",
    "@id": "{siteUrl}/blog/{slug}"
  },
  "wordCount": 2400,
  "articleBody": "First 200 characters of content as excerpt..."
}
```

Required: `@type`, `headline`, `datePublished`, `author`, `publisher`, `image`.
Recommended: `description`, `dateModified`, `mainEntityOfPage`, `wordCount`, `articleBody`.

### Step 3: Generate Person (author) schema

Stable `@id` for cross-referencing:

```json
{
  "@type": "Person",
  "@id": "{siteUrl}/author/{author-slug}#person",
  "name": "Author Name",
  "jobTitle": "Role or Title",
  "url": "{siteUrl}/author/{author-slug}",
  "sameAs": [
    "https://twitter.com/handle",
    "https://linkedin.com/in/handle",
    "https://github.com/handle"
  ]
}
```

Optional (include when available): `alumniOf`, `worksFor`.

### Step 4: Generate Organization schema

Blog's parent organization entity:

```json
{
  "@type": "Organization",
  "@id": "{siteUrl}#organization",
  "name": "Organization Name",
  "url": "{siteUrl}",
  "logo": {
    "@type": "ImageObject",
    "url": "{siteUrl}/logo.png",
    "width": 600,
    "height": 60
  },
  "sameAs": [
    "https://twitter.com/org",
    "https://linkedin.com/company/org"
  ]
}
```

Logo requirements: valid image URL, ≥112×112px, ≤600px wide, rectangular preferred for BlogPosting publishers.

### Step 5: Generate BreadcrumbList

Navigation breadcrumb showing content hierarchy:

```json
{
  "@type": "BreadcrumbList",
  "@id": "{siteUrl}/blog/{slug}#breadcrumb",
  "itemListElement": [
    {"@type": "ListItem", "position": 1, "name": "Home", "item": "{siteUrl}"},
    {"@type": "ListItem", "position": 2, "name": "Category", "item": "{siteUrl}/blog/category/{slug}"},
    {"@type": "ListItem", "position": 3, "name": "Post Title", "item": "{siteUrl}/blog/{slug}"}
  ]
}
```

If no category: use "Blog" as second breadcrumb with `{siteUrl}/blog` URL.

### Step 6: Generate FAQPage schema

Extract Q&A pairs from FAQ section:

```json
{
  "@type": "FAQPage",
  "@id": "{siteUrl}/blog/{slug}#faq",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "What is the question?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Complete answer (40-60 words with statistic)."
      }
    }
  ]
}
```

**Important**: Google restricted FAQ rich results to government + health sites since Aug 2023. However FAQ schema STILL provides value:
- AI systems (ChatGPT, Perplexity, Gemini) extract FAQ data for citations
- Structures content for future rich result eligibility changes
- Improves content organization signals

### Step 7: Generate VideoObject (if videos present)

Per YouTube video embedded:

```json
{
  "@type": "VideoObject",
  "@id": "{siteUrl}/blog/{slug}#video-{index}",
  "name": "Video title",
  "description": "First 200 chars of description",
  "thumbnailUrl": "https://img.youtube.com/vi/{videoId}/hqdefault.jpg",
  "uploadDate": "{ISO 8601 date}",
  "contentUrl": "https://www.youtube.com/watch?v={videoId}",
  "embedUrl": "https://www.youtube.com/embed/{videoId}",
  "duration": "PT{M}M{S}S"
}
```

Use `#video-1`, `#video-2` for `@id` fragments. Extract metadata from embed noscript fallback or YouTube Data API.

### Step 8: Generate ImageObject

Cover image schema:

```json
{
  "@type": "ImageObject",
  "@id": "{siteUrl}/blog/{slug}#primaryimage",
  "url": "https://cdn.example.com/...",
  "width": 1200,
  "height": 630,
  "caption": "Descriptive caption matching alt text"
}
```

Requirements:
- URL crawlable + publicly accessible
- Actual dimensions
- Caption aligns with alt text
- Preferred: 1200×630 (OG-compatible) or 1920×1080

### Step 9: Format-specific additions

| Format | Additional schema |
|---|---|
| listicle / shortlist-validation | `ItemList` with each ranked item |
| product-review | `Review` + `AggregateRating` |
| faq-knowledge | `FAQPage` as primary (also via `mainEntity` in Article) |
| news-analysis | `NewsArticle` replaces `BlogPosting` |
| case-study | `Article` + `organizationReferenced` |
| comparison | `Review` (paired) |
| definition | `DefinedTerm` + `partOfSet: DefinedTermSet` |

### Step 10: Validate + warn

Check for deprecated types + apply validation rules.

**NEVER use these deprecated types**:
- **HowTo** — Deprecated Sept 2023 (Google no longer shows rich results); use `mainEntity: HowTo` on Article
- **SpecialAnnouncement** — Deprecated July 2025
- **Practice Problem** — Deprecated (education markup)
- **Dataset** — Deprecated for general use
- **Sitelinks Search Box** — Deprecated
- **Q&A** — Deprecated Jan 2026 (distinct from FAQPage)

**Validation checks**:
1. All `@id` references resolve to entities within the `@graph`
2. `dateModified` ≥ `datePublished`
3. `headline` ≤ 110 characters
4. `description` between 50-160 characters
5. All URLs absolute (not relative)
6. Image dimensions positive integers
7. BreadcrumbList positions sequential from 1
8. FAQPage has ≥2 questions

Run:
```bash
python -m scripts.validate.schema_validator workspace/{task}/schema.json
```

### Step 11: Output — TWO different destinations, TWO different shapes

⚠️ **Rule 11 reconciliation (2026-07-06).** This step previously taught ONE combined
`@graph` in a single script tag for everything. That contract conflicts with the
BODY-block pipeline: `verify_post.py` check 17 counts rendered
`<script type="application/ld+json">` TAGS, and for a draft post only BODY tags are
fetchable — so a combined 2-member `@graph` written to `workspace/{task}/schema.json`
renders as ONE tag and fails the ≥2-blocks contract on the live post (this exact
miscount failed WP post 1449 in the 2026-07-06 loamwright batch). **One "block" =
one rendered script tag.**

**Destination A — head-level article graph** (`meta.json :: schema_jsonld`, emitted by
RankMath/head injection): the combined `@graph` pattern IS correct here — BlogPosting +
Person + Organization (+ BreadcrumbList) in one tag with stable `@id` links:

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    { "@type": "BlogPosting", ... },
    { "@type": "Person", ... },
    { "@type": "Organization", ... }
  ]
}
</script>
```

**Destination B — body supplemental blocks** (`workspace/{task}/schema.json`, injected
by the publisher after the CSS wrapper): the CANONICAL shape is `blocks[]`, one entry
per intended script tag — NEVER a combined `@graph`:

```jsonc
{
  "blocks": [
    { "block_name": "faq",          "ld_json": { "@context": "https://schema.org", "@type": "FAQPage",  ... } },
    { "block_name": "pricing_list", "ld_json": { "@context": "https://schema.org", "@type": "ItemList", ... } }
  ]
}
```

The publisher defensively splits a bare `@graph` into one tag per member since
2026-07-06, but the fallback is a safety net, not the contract — emit `blocks[]`.

**@graph pattern benefits (Destination A only)**:
- Entity linking via stable `@id` references
- Google + AI systems parse `@graph` arrays correctly
- Easier to maintain

## Why this matters for AI citation

Pages with **3+ schema types** show approximately **+13% AI citation likelihood**. This skill generates up to 7 types (BlogPosting, Person, Organization, BreadcrumbList, FAQPage, ImageObject, VideoObject) to maximize both search engine understanding AND AI extraction.

## CLI invocation

```bash
python -m scripts.build.schema_jsonld_builder \
    --url "{post_url}" \
    --title "{title}" \
    --description "{excerpt}" \
    --type BlogPosting \
    --published "{datetime}" \
    --modified "{datetime}" \
    --author-name "{author}" \
    --author-url "{author_url}" \
    --org-name "{brand}" \
    --org-url "{site_url}" \
    --org-logo-url "{logo}" \
    --image-url "{cover_image_url}" \
    --primary-keyword "{kw}" \
    --format-id "{format_id}" \
    --faq-json {faq.json} \
    --breadcrumbs-json {breadcrumbs.json}
```

Output → `workspace/{task}/schema.json` → merged into `meta.json` → injected at publish.

## Output options

- **Embedded HTML** — ready to paste into `<head>` or before `</body>`
- **Standalone JSON** — for CMS schema fields or API injection
- **MDX component** — if project uses MDX, wrap in component

## Hard rules

1. NEVER use deprecated schema types (T09 veto trigger)
2. Every `@id` MUST resolve within the `@graph`
3. All URLs absolute, all dates ISO 8601
4. Logo image MUST be crawlable + publicly accessible
5. Author Person schema MUST include credentials for YMYL topics (T05 risk)
6. **MUST emit >=2 body JSON-LD blocks (2026-07-05).** `verify_post.py` check 17 requires
   >=2 total JSON-LD blocks (head+body combined), but for a DRAFT post (the Rule 5a
   default) `<head>` is not fetchable, so the minimum falls entirely on body blocks.
   `FAQPage` is near-mandatory (every article has an FAQ section per
   `mandatory_sections`); for the 2nd block, default to `ItemList` over any
   compared/ranked/tabular set of >=3 named entities — `outline-architect` guarantees
   >=2 tables per article, so a legitimate candidate always exists (platforms compared,
   scorecard criteria, checklist steps). A 2026-07-05 production run shipped only
   `FAQPage` on the judgment call "nothing else fits," which passed this SKILL's own
   review but failed `verify_post` check 17 on the live post, forcing a late manual
   patch. Treat "I can't find a 2nd block" as a signal to look harder at the article's
   existing comparison tables, not as a valid outcome — this rule now applies before
   step 10's deprecated-type filter, so do not reach for `HowTo`/`Dataset`/`Q&A` as a
   shortcut to hit the count; those remain forbidden as standalone top-level types (rule 1).

## See also

- `scripts/build/schema_jsonld_builder.py` — implementation
- `scripts/validate/schema_validator.py` — validation runner
- `subskills/publish/schema-injector/SKILL.md` — injection into final HTML
- `agents/schema-validator.md` — JSON-LD validator agent
- `references/geo/cite-framework-40.md` — T09 deprecated schema veto
