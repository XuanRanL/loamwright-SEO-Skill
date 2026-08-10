# Xuanran SEO · WordPress MU-Plugins

This directory contains "Must Use" plugins that the Xuanran SEO Blog Writer needs
installed on your WordPress site to set SEO meta fields via REST API.

## Files

| File | Purpose | Required for |
|---|---|---|
| `xuanran-rank-math-rest-bridge.php` | Exposes Rank Math meta to WP REST | Sites using **Rank Math SEO** |
| `seo-machine-yoast-rest.php` | Exposes Yoast meta to WP REST | Sites using **Yoast SEO** |

You only need to install the one that matches your site's SEO plugin.

## Why MU-plugins?

Both Rank Math and Yoast deliberately do **not** register their post meta with
`show_in_rest => true` in their default builds. That means a plain
`PATCH /wp-json/wp/v2/posts/{id}` with `{"meta": {"rank_math_title": "..."}}`
silently succeeds but stores nothing — the field stays empty in the SEO plugin's
admin UI.

The fix is a small MU-plugin that calls `register_post_meta()` for the SEO
plugin's known meta keys with proper sanitization, JSON schema (for array
fields like `rank_math_robots`), and `auth_callback`. After that, standard WP
core REST writes work normally.

## Installation

### Method 1: SFTP / cPanel File Manager

1. Connect to your site over SFTP (or use cPanel → File Manager)
2. Navigate to `wp-content/`
3. Create `mu-plugins/` directory if it doesn't exist (note: `mu-plugins`, plural,
   exactly that name — WordPress only auto-loads from this exact path)
4. Upload the appropriate `.php` file into `wp-content/mu-plugins/`
5. **No activation needed** — MU-plugins load automatically on every request

### Method 2: WP-CLI (faster for bulk deployment)

```bash
# Single site
wp scaffold mu-plugin --plugin_root=/var/www/html/wp-content xuanran-rank-math
# Then copy the .php file content into the scaffolded file

# OR just drop the file
cp xuanran-rank-math-rest-bridge.php /path/to/wp-content/mu-plugins/
```

### Method 3: Plugin file upload (Free hosts that block direct SFTP)

If your host doesn't allow SFTP, you can convert the MU-plugin into a regular
plugin by:

1. Create a folder named `xuanran-rank-math-bridge/`
2. Drop the `.php` file inside, renamed to match the folder
3. Zip the folder → upload via WP admin → Plugins → Add New → Upload Plugin
4. Activate it like any other plugin

The functionality is identical; only the loading mechanism differs.

## Verification

After installation, hit the bridge's health-check endpoint to confirm it loaded:

```bash
curl -s https://yoursite.com/wp-json/xuanran/v1/rank-math-bridge | jq
```

Expected response:

```json
{
  "bridge_active": true,
  "bridge_version": "1.0.0",
  "rank_math_active": true,
  "rank_math_version": "1.0.245",
  "registered_keys": ["rank_math_title", "rank_math_description", ...]
}
```

If you get a 404, the file is not in the right place. Check:
- Path is exactly `wp-content/mu-plugins/xuanran-rank-math-rest-bridge.php`
- File permissions allow PHP to read it (644 is safe)
- No PHP syntax error (check error log)

From inside the Xuanran SEO Blog Writer plugin:

```bash
python -c "
from scripts.wordpress.wp_client import WPClient
wp = WPClient('your-site-slug')
with wp:
    h = wp.health_check()
    print(f'SEO plugin detected: {h[\"seo_plugin\"]}')
    print(f'Rank Math bridge:    {h[\"rankmath_bridge\"]}')
    print(f'Rank Math version:   {h[\"rankmath_version\"]}')
"
```

Should print:
```
SEO plugin detected: rankmath
Rank Math bridge:    True
Rank Math version:   1.0.245
```

## Security model

Both MU-plugins use the standard WordPress capability model:

- All write callbacks check `user_can($user_id, 'edit_post', $post_id)`
- This requires the Application Password user be at least **Editor** role
  (Author works for posts they own; Contributor will silently fail)
- The bridge endpoints respect the same auth as core `/wp/v2/posts/{id}`,
  so Application Passwords + HTTP Basic over HTTPS is the recommended auth
- No sensitive data is logged or returned by the health-check endpoint

If you want to lock down the health check to authenticated users only, change
`'permission_callback' => '__return_true'` to:

```php
'permission_callback' => function () {
    return current_user_can( 'edit_posts' );
}
```

## Uninstallation

Simply delete the file from `wp-content/mu-plugins/`. There is no DB cleanup
needed — `register_post_meta` is a runtime registration, not stored.

Your existing SEO meta in `wp_postmeta` table is untouched.

## Compatibility

- WordPress: 5.6+ (tested up to 6.7)
- PHP: 7.4+ (tested on 8.1, 8.2, 8.3)
- Rank Math: Free 1.0.x and Pro
- Yoast SEO: 22.x+
- Coexistence: Both bridges can run simultaneously if your site somehow runs
  both SEO plugins (not recommended by either vendor, but the bridges won't
  conflict).

## Troubleshooting

### Health check returns 404 even after install

- Is the file at exactly `wp-content/mu-plugins/`? (singular `plugins` is wrong)
- Does PHP have read permission on the file?
- Check `wp-content/debug.log` for PHP parse errors
- Some security plugins (Wordfence "Real-Time Live Traffic") show MU-plugin
  loads — verify it appears there

### Meta still empty after REST write

- Re-fetch with `?_fields=meta` to see what landed
- Run `wp post meta list <id> | grep rank_math` (WP-CLI) to see DB rows
- Check that the Application Password user is Editor or higher

### `class-paper.php:526 foreach() warning` after writes

- Almost always `rank_math_robots` shape mismatch
- Confirm you're sending JSON `["index","follow"]`, not a string
- Delete the corrupt meta row: `wp post meta delete <id> rank_math_robots`
- Re-write with proper array

### SEO Score column shows N/A

- Expected for posts written via REST — Rank Math's content analyzer is JS-only
- To populate: Rank Math admin → Status & Tools → Database Tools →
  "Update SEO Scores" → click button
- Or per-post via WP-CLI: `wp eval 'rank_math()->update_post_score(<id>);'`

## See also

- `references/platform-guides/rank-math-meta-fields.md` — full meta key reference
- `scripts/wordpress/wp_publisher.py` — Python side that uses these endpoints
- Rank Math official docs: https://rankmath.com/kb/headless-cms-support/
