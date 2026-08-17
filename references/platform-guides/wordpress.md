# Platform Guide: WordPress

WordPress-specific gotchas, plugin compatibility, and publish pipeline details.

## Compatibility matrix (verified 2026-05)

| Component | Required | Notes |
|---|---|---|
| WordPress core | 6.5+ | REST API + Application Passwords stable |
| PHP | 8.1+ | Required for modern security |
| HTTPS | **Mandatory** | Application Passwords reject HTTP |
| REST API | Enabled (default) | If disabled by plugin → publish fails |
| Application Passwords | Enabled (default) | User → Profile → Application Passwords |
| Yoast SEO | 22.x+ | OR Rank Math 1.0.220+ (alternative) |
| Block Editor (Gutenberg) | Default in 6.x | Classic Editor plugin breaks block content |

## Authentication

Application Password is the standard. **Never use** the user's main password in REST API calls.

### Setup procedure
1. Admin → Users → Profile
2. Scroll to "Application Passwords"
3. Name: `xuanran-seo-plugin`
4. Click "Add New Application Password"
5. Copy the 24-character password (shown ONCE)
6. Store in `projects/{slug}/credentials/wordpress.json`:
   ```json
   {
     "url": "https://example.com",
     "username": "editor-account",
     "app_password": "xxxx xxxx xxxx xxxx xxxx xxxx"
   }
   ```

### Required user role
- **Author**: can create posts but not other authors' posts
- **Editor** (recommended): can manage all posts + uploads
- **Administrator**: too privileged for routine publishing

## Publish flow (7-step from wp_publisher.py)

```
Step 1: markdown → HTML (markdown_to_html.py)
        - Drop H1 (WP titles handle that)
        - Add anchor IDs to H2/H3
        - Lazy-load images
        - srcset for responsive images

Step 2: Upload media (wp_media.py)
        - POST /wp-json/wp/v2/media (multipart)
        - Returns media_id + URL

Step 3: Resolve taxonomy (wp_taxonomy.py)
        - GET /wp-json/wp/v2/categories?search=
        - Create missing via POST
        - Cache result in .seo/wp-taxonomy-cache.json (24h TTL)

Step 4: Create post as DRAFT
        - POST /wp-json/wp/v2/posts
        - status: "draft" initially (so preview is possible)
        - featured_media: from Step 2
        - categories + tags: from Step 3

Step 5: Inject schema + Yoast meta
        - PATCH /wp-json/wp/v2/posts/{id}
        - meta._yoast_wpseo_title
        - meta._yoast_wpseo_metadesc
        - meta._yoast_wpseo_focuskw
        - meta._schema_jsonld (requires MU-plugin OR custom field)

Step 6+7: Flip draft → live + re-verify + notify indexers
        - ONE executor owns the sequence (v3.42.16):
          python -m scripts.wordpress.flip_post_live {slug} --workspace {task_id} --json
        - It PATCHes status → publish, re-verifies the live URL, then re-runs
          the indexing notifier (IndexNow: Bing, ChatGPT-via-Bing, Yandex, Naver).
        - Exit 2 = live but indexing NOT submitted. Never hand-PATCH the status.
```

## Common pitfalls

### 1. HTTPS strict requirement
WP App Passwords explicitly reject HTTP. Even on localhost development sites, you need a self-signed cert.

### 2. REST API disabled by security plugins
Some plugins (Disable REST API, iThemes Security) block REST entirely. Required action: whitelist `/wp-json/` for authenticated users.

### 3. Block Editor vs Classic Editor
- Block Editor: stores content as `<!-- wp:paragraph -->` block comments. Our HTML output is compatible.
- Classic Editor: stores raw HTML. Both work but block compatibility is more brittle.

### 4. Yoast plugin conflicts
- Yoast adds its own schema. If we inject schema_jsonld via MU-plugin, Yoast might add a duplicate.
- Solution: install our `wordpress-mu-plugin/seo-machine-yoast-rest.php` which makes Yoast skip if our meta key is set.

### 5. Featured image upload size
- WP default max upload: 2 MB
- Our cover images at 1024² high quality WebP: usually 80-150 KB ✓ within limits
- For larger sites, increase via PHP ini: `upload_max_filesize = 8M`

### 6. ACF (Advanced Custom Fields) conflicts
- ACF stores fields in `wp_postmeta`. Our schema injection uses the same table.
- Use distinct meta key prefixes: `_xuanran_seo_*` to avoid collisions.

### 7. Category vs Tag distinction
- Categories: hierarchical, broad (e.g., "Marketing", "SEO Guides")
- Tags: flat, granular (e.g., "ChatGPT", "AI-citation")
- Default mapping in `meta.json`:
  - `categories` array → WP categories
  - `tags` array → WP tags
- WP requires terms exist before assigning; our wp_taxonomy.py creates them if missing.

### 8. Slug conflicts
- WP auto-suffixes duplicate slugs (`fishing-rod` → `fishing-rod-2`)
- We control slug via `meta.json.slug`; if a duplicate exists, we get a -2 silently
- Recommendation: query existing post by slug FIRST before creating

## Required server-side configuration

In `wp-config.php` for safety:

```php
// Allow Application Passwords
add_filter('wp_is_application_passwords_available', '__return_true');

// Increase upload limit
// (Also set in php.ini)

// Disable XML-RPC (security best practice)
add_filter('xmlrpc_enabled', '__return_false');
```

## MU-plugin (Must-Use plugin) we ship

`install/wordpress-mu-plugin/seo-machine-yoast-rest.php` does:

1. Exposes `_xuanran_seo_schema_jsonld` meta field to REST API
2. Adds `_yoast_wpseo_title/metadesc/focuskw` to REST schema (Yoast doesn't expose these by default)
3. Suppresses Yoast schema if our schema present (prevents duplicate)
4. Adds `<script type="application/ld+json">` to `<head>` from our schema field

Install: copy `seo-machine-yoast-rest.php` to `wp-content/mu-plugins/`.

## Rollback strategy

Every publish action logs to `projects/{slug}/.seo/change-log.json`:

```json
{
  "change_id": "ch-20260519-7c2f8a4b",
  "action": "publish",
  "post_id": 1247,
  "post_url": "https://example.com/post-slug",
  "status": "publish",
  "expires_at": 1716660720,
  "rollback_data": {
    "media_ids": [4521, 4522],
    "category_ids": [42],
    "tag_ids": [101, 102]
  }
}
```

Rollback within 7 days:
```bash
python -m scripts.publish.change_log show ch-20260519-7c2f8a4b
# Then via wp_publisher --post-id 1247 --status draft (or trash)
```

## Multi-site WordPress

For agencies managing 100+ WP sites:

- Each site = one `projects/{slug}/credentials/wordpress.json`
- Each WP App Password is per-site (don't share across clients)
- Each site needs its own MU-plugin install (or central WP-CLI script)
- Use Cloudflare → WP via mTLS for production deployments

## Testing without affecting production

Before testing publish on a real site:
1. Set up a WordPress sandbox (local-WP, Cloudways, or DigitalOcean)
2. Verify Application Password works:
   ```bash
   curl -u "user:pass" https://sandbox.example.com/wp-json/wp/v2/users/me
   ```
3. Run `python -m scripts.wordpress.wp_publisher --site-slug sandbox --status draft ...`
4. Check post in WP admin
5. Only then point at production

## See also

- `scripts/wordpress/wp_publisher.py` — main publish orchestrator
- `scripts/wordpress/wp_taxonomy.py` — categories/tags
- `scripts/wordpress/wp_media.py` — media upload
- `agents/publisher.md` — publish agent
- `install/wordpress-mu-plugin/seo-machine-yoast-rest.php` — MU-plugin
