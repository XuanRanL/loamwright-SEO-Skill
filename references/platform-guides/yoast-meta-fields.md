# Platform Guide: Yoast SEO Meta Fields

Yoast SEO REST API field mapping for programmatic SEO field injection.

By default, Yoast does NOT expose its meta fields to the REST API. Our MU-plugin (`install/wordpress-mu-plugin/seo-machine-yoast-rest.php`) bridges this.

## Yoast meta keys we set

| Field | WP meta key | Set via | Char limit |
|---|---|---|---|
| SEO Title | `_yoast_wpseo_title` | meta-builder | 50-65 |
| Meta Description | `_yoast_wpseo_metadesc` | meta-builder | 150-160 |
| Focus Keyphrase | `_yoast_wpseo_focuskw` | brief.primary_keyword | natural |
| Canonical URL | `_yoast_wpseo_canonical` | rarely overridden | URL |
| Robots-noindex | `_yoast_wpseo_meta-robots-noindex` | rarely | 0/1 |
| Robots-nofollow | `_yoast_wpseo_meta-robots-nofollow` | rarely | 0/1 |
| OG Title | `_yoast_wpseo_opengraph-title` | meta-builder (defaults to SEO title) | 50-65 |
| OG Description | `_yoast_wpseo_opengraph-description` | meta-builder (defaults to meta-desc) | 150-160 |
| OG Image | `_yoast_wpseo_opengraph-image` | featured_media URL | URL |
| OG Image ID | `_yoast_wpseo_opengraph-image-id` | featured_media_id | int |
| Twitter Card | `_yoast_wpseo_twitter-card-type` | "summary_large_image" | enum |
| Twitter Title | `_yoast_wpseo_twitter-title` | (defaults to OG title) | 70 |
| Twitter Description | `_yoast_wpseo_twitter-description` | (defaults to OG desc) | 200 |
| Twitter Image | `_yoast_wpseo_twitter-image` | (defaults to OG image) | URL |
| Schema page-type | `_yoast_wpseo_schema_page_type` | "WebPage" or "FAQPage" | enum |
| Schema article-type | `_yoast_wpseo_schema_article_type` | "Article", "BlogPosting", "NewsArticle" | enum |

## How to set via REST API

Via `PATCH /wp-json/wp/v2/posts/{id}`:

```json
{
  "meta": {
    "_yoast_wpseo_title": "Best Fishing Rods 2026: 7 Tested Picks",
    "_yoast_wpseo_metadesc": "Tested 23 rods across 87 trips. Top pick: G.Loomis NRX+. Full ranking with sensitivity data + price comparison.",
    "_yoast_wpseo_focuskw": "best fishing rods 2026",
    "_yoast_wpseo_opengraph-image-id": 4521,
    "_yoast_wpseo_schema_article_type": "BlogPosting"
  }
}
```

## Field generation rules

### `_yoast_wpseo_title`

Format: `{Primary Keyword} | {Brand Name}` (Yoast's "%%title%% %%sep%% %%sitename%%" template).

We override with the explicit title from meta.json (our title is already brand-aware).

Validation:
- 50-65 chars ideal (Google truncates ~62 chars on desktop, ~30 mobile)
- Primary keyword in first 60 chars
- One power word recommended (Best, Proven, Ultimate, etc.)
- No clickbait patterns

### `_yoast_wpseo_metadesc`

150-160 chars. Must contain primary keyword once. Should:
- Open with strongest claim or stat
- Include 1 power word
- End with implicit benefit or call

Example:
> "Tested 23 fishing rods across 87 trips. Top pick: G.Loomis NRX+ ($549). Full ranking with sensitivity data, price comparison, and saltwater notes. (158 chars)"

### `_yoast_wpseo_focuskw`

Exact primary keyword. No commas, no modifiers. Used by Yoast to rate the article's keyword optimization.

If multi-word keyword:
- ✓ "best fishing rods 2026"
- ✗ "best, fishing, rods" (separate keywords)

### `_yoast_wpseo_schema_article_type`

| Format | Recommended type |
|---|---|
| listicle | BlogPosting |
| how-to-guide | Article (NOT HowTo — deprecated for primary) |
| pillar-page | Article |
| comparison | BlogPosting |
| case-study | Article |
| definition | Article (with DefinedTerm mainEntity) |
| news-analysis | NewsArticle |
| product-review | BlogPosting (with Review schema in @graph) |

## Conflict with our schema injection

Yoast auto-generates schema. If we ALSO inject schema_jsonld via MU-plugin, you get duplicates.

**Solution**: MU-plugin checks for our schema and suppresses Yoast's:

```php
// In MU-plugin
add_filter('wpseo_json_ld_output', function($output) {
    if (get_post_meta(get_the_ID(), '_xuanran_seo_schema_injected', true)) {
        return false;   // suppress Yoast schema
    }
    return $output;
});
```

When we set `_xuanran_seo_schema_injected = 1` + `_xuanran_seo_schema_jsonld = <our @graph>`:
- Yoast schema: suppressed
- Our @graph: rendered in `<head>`

## Alternative: Rank Math instead of Yoast

If site uses Rank Math (alternative SEO plugin), field keys differ:

| Concept | Yoast key | Rank Math key |
|---|---|---|
| SEO Title | `_yoast_wpseo_title` | `rank_math_title` |
| Meta Desc | `_yoast_wpseo_metadesc` | `rank_math_description` |
| Focus KW | `_yoast_wpseo_focuskw` | `rank_math_focus_keyword` |
| OG Title | `_yoast_wpseo_opengraph-title` | `rank_math_facebook_title` |
| OG Desc | `_yoast_wpseo_opengraph-description` | `rank_math_facebook_description` |
| OG Image | `_yoast_wpseo_opengraph-image` | `rank_math_facebook_image` |

Our `wp_publisher.py` auto-detects which plugin is active (via REST `/wp/v2/types/post` schema) and maps fields accordingly.

## Validation rules (Yoast green-light)

Yoast SEO analysis page expects:
1. ✓ Focus keyphrase in title
2. ✓ Focus keyphrase in meta description
3. ✓ Focus keyphrase in slug
4. ✓ Focus keyphrase in H1 (or document title)
5. ✓ Focus keyphrase in first 100 words
6. ✓ Keyphrase density 0.5-2.5%
7. ✓ Internal links present
8. ✓ Outbound links present (1+ Tier-1)
9. ✓ Images with alt text
10. ✓ Meta description filled

Our `scripts/validate/title_validator.py` + `keyword_density.py` + `link_resolver.py` cover items 1-9 automatically.

## Bulk operations

For bulk updating Yoast fields across published articles:

```bash
# Update meta desc for all listicles older than 6 months
python -m scripts.wordpress.wp_publisher \
    --site-slug my-site \
    --bulk-update-meta \
    --filter "format=listicle&older_than=6mo" \
    --field "_yoast_wpseo_metadesc" \
    --template "{title} — Updated for 2026. {primary_kw} comparison + tested picks."
```

## See also

- `scripts/wordpress/wp_publisher.py` — sets Yoast fields during publish
- `scripts/build/markdown_to_html.py` — converts our markdown to WP-ready HTML
- `install/wordpress-mu-plugin/seo-machine-yoast-rest.php` — bridge for REST
- `references/platform-guides/wordpress.md` — overall WP guide
