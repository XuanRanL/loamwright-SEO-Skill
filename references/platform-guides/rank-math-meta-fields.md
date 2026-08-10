# Rank Math · SEO Meta Field Reference

Reference for setting Rank Math SEO meta on WordPress posts via REST API.

**Prerequisite**: Install the `xuanran-rank-math-rest-bridge.php` MU-plugin on
the target site. See `install/wordpress-mu-plugin/README.md`.

## Complete field reference

| Meta key | Type | Storage | Module | Notes |
|---|---|---|---|---|
| `rank_math_title` | string | scalar | core | SEO title; `%title%` / `%sep%` variables OK |
| `rank_math_description` | string | scalar | core | Meta description. **Not** `_rank_math_description` |
| `rank_math_focus_keyword` | string | scalar, **comma-separated** | core | Free version limits to 5 keywords |
| `rank_math_canonical_url` | string | scalar (URL) | core | sanitized with `esc_url_raw` |
| `rank_math_robots` | array | array of enum strings | core | Values: `index` `noindex` `nofollow` `noarchive` `noimageindex` `nosnippet`. **MUST be real array** |
| `rank_math_advanced_robots` | object | assoc object | advanced | Keys: `max-snippet` `max-video-preview` `max-image-preview` |
| `rank_math_primary_category` | int | scalar (term ID) | advanced | One per post |
| `rank_math_breadcrumb_title` | string | scalar | advanced | Shorter title for breadcrumbs only |
| `rank_math_pillar_content` | string | scalar `"on"` or `""` | advanced | Boolean-as-string |
| `rank_math_facebook_title` | string | scalar | social | OG title |
| `rank_math_facebook_description` | string | scalar | social | OG description |
| `rank_math_facebook_image` | string (URL) | scalar | social | OG image URL |
| `rank_math_facebook_image_id` | int | scalar (attachment ID) | social | Optional; sets WP attachment |
| `rank_math_twitter_use_facebook` | string `"on"`/`""` | scalar | social | If `on`, Twitter falls back to FB fields |
| `rank_math_twitter_card_type` | string | scalar | social | `summary_large_image` / `summary` |
| `rank_math_twitter_title` | string | scalar | social | |
| `rank_math_twitter_description` | string | scalar | social | |
| `rank_math_twitter_image` | string (URL) | scalar | social | |
| `rank_math_seo_score` | int | scalar | analysis | **Calculated, not writable** — see "SEO Score" below |

## Critical pitfalls

### 1. `rank_math_focus_keyword` is a string, NOT an array

```python
# ✓ Correct
{"rank_math_focus_keyword": "commercial LED grow light, DLC certification"}

# ✗ Wrong (this is the Yoast way; Rank Math uses comma-separated string)
{"rank_math_focus_keyword": ["commercial LED grow light", "DLC certification"]}
```

### 2. `rank_math_robots` is an array of enum strings

```python
# ✓ Correct
{"rank_math_robots": ["index", "follow"]}

# ✗ Wrong — comma-string triggers class-paper.php:526 foreach() warning
{"rank_math_robots": "index,follow"}

# ✗ Wrong — pre-serialized PHP also breaks
{"rank_math_robots": 'a:2:{i:0;s:5:"index";i:1;s:6:"follow";}'}
```

### 3. `rank_math_description` has no underscore prefix

```python
# ✓ Correct
{"rank_math_description": "..."}

# ✗ Wrong (silently ignored)
{"_rank_math_description": "..."}
```

### 4. Empty string deletes the meta row

```python
# Sending an empty string DELETES the row
{"rank_math_title": ""}  # → meta row removed

# To leave field empty, omit the key entirely
{"rank_math_focus_keyword": "..."}  # don't include rank_math_title
```

### 5. SEO Score is computed, not writable

`rank_math_seo_score` only populates when Rank Math's JS content analyzer runs
in the post editor. Setting it via REST stores an int but it'll be overwritten
on next editor save.

**To populate scores after bulk REST imports**: Rank Math admin →
**Status & Tools → Database Tools → Update SEO Scores** → click button.

Per-post via WP-CLI: `wp eval 'rank_math()->update_post_score(<id>);'`

## How wp_publisher uses this

The `_set_rankmath_meta()` function in `scripts/wordpress/wp_publisher.py` reads
generic SEO fields from `meta.json` and maps to Rank Math keys:

| Your `meta.json` field | Mapped to Rank Math key |
|---|---|
| `seo_title` (or `title`) | `rank_math_title` |
| `meta_description` (or `excerpt`) | `rank_math_description` |
| `focus_keyphrase` | `rank_math_focus_keyword` |
| `canonical_url` | `rank_math_canonical_url` |
| `breadcrumb_title` | `rank_math_breadcrumb_title` |
| `pillar_content` (truthy) | `rank_math_pillar_content` = "on" |
| `robots` (list) | `rank_math_robots` |
| `advanced_robots` (dict) | `rank_math_advanced_robots` |
| `primary_category` (int) | `rank_math_primary_category` |
| `og_title` | `rank_math_facebook_title` |
| `og_description` | `rank_math_facebook_description` |
| `og_image` | `rank_math_facebook_image` |
| (no `og_image`, but has featured) | `rank_math_facebook_image_id` = featured ID |
| `twitter_use_facebook` | `rank_math_twitter_use_facebook` = "on" |
| `twitter_card_type` | `rank_math_twitter_card_type` |
| `twitter_title` | `rank_math_twitter_title` |
| `twitter_description` | `rank_math_twitter_description` |
| `twitter_image` | `rank_math_twitter_image` |

## Example meta.json for Rank Math

```json
{
  "title": "Commercial LED Grow Light Buyer's Guide 2026",
  "slug": "commercial-led-grow-light-buyers-guide-2026",
  "excerpt": "How to evaluate PPE, DLC certification, and BMS controls...",

  "focus_keyphrase": "commercial LED grow light, DLC certification, PPE",
  "seo_title": "Commercial LED Grow Light Buyer's Guide 2026 | project-charlie",
  "meta_description": "Evaluate PPE, DLC certification, and BMS controls when sourcing LED fixtures.",

  "canonical_url": "https://project-charlie.example.com/buyer-guides/commercial-led-grow-light/",
  "breadcrumb_title": "Buyer's Guide",
  "pillar_content": true,

  "robots": ["index", "follow"],
  "advanced_robots": {
    "max-snippet": "-1",
    "max-image-preview": "large",
    "max-video-preview": "-1"
  },

  "og_title": "Commercial LED Grow Light Buyer's Guide 2026",
  "og_description": "How to source LED fixtures for cannabis cultivation.",
  "twitter_card_type": "summary_large_image",

  "categories": ["Buyer Guides"],
  "tags": ["LED grow light", "DLC certification", "PPE"]
}
```

(`og_image` is omitted intentionally → wp_publisher auto-uses the featured
image attachment ID for `rank_math_facebook_image_id`.)

## Verification after write

```python
from scripts.wordpress.wp_client import WPClient
wp = WPClient('site-slug')
with wp:
    r = wp.get(f'/wp/v2/posts/{post_id}', params={'_fields': 'meta', 'context': 'edit'})
    meta = r.json_data.get('meta', {})
    for key in ['rank_math_title', 'rank_math_description', 'rank_math_focus_keyword', 'rank_math_robots']:
        print(f'{key}: {meta.get(key)!r}')
```

Should echo back exactly what you sent. If a field is `None` or missing, the
bridge MU-plugin didn't register it (check bridge version + verify field name).

## See also

- `install/wordpress-mu-plugin/xuanran-rank-math-rest-bridge.php` — the bridge plugin
- `install/wordpress-mu-plugin/README.md` — install instructions
- Rank Math KB: https://rankmath.com/kb/headless-cms-support/
- WP register_meta reference: https://developer.wordpress.org/reference/functions/register_meta/
