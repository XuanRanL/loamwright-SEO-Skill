<?php
/**
 * Plugin Name: SEO Machine Yoast REST Bridge
 * Description: Exposes Yoast SEO fields via WordPress REST API for headless / automated workflows.
 *              Drop this file into wp-content/mu-plugins/ — auto-loads, no activation needed.
 * Version:     3.42.18
 * Author:      Xuanran SEO
 * License:     Apache-2.0
 *
 * Endpoints added:
 *   GET  /wp-json/yoast/v1/posts/{id}        — read all Yoast meta fields
 *   POST /wp-json/yoast/v1/posts/{id}         — write focus_keyphrase, seo_title, meta_description
 *
 * Security:
 *   - Auth via WordPress Application Passwords (24-char key, HTTP Basic, HTTPS required)
 *   - Permission callback: user must have edit_post capability for target post
 *   - Sanitizes all input via sanitize_text_field()
 *
 * @link https://developer.wordpress.org/rest-api/extending-the-rest-api/adding-custom-endpoints/
 */

if (!defined('ABSPATH')) {
    exit;  // Direct access not allowed
}

/**
 * Yoast meta keys this MU-plugin exposes.
 * Note: keys prefixed with underscore are private/hidden by default in WP admin.
 */
define('SM_YOAST_FIELDS', [
    'focus_keyphrase'    => '_yoast_wpseo_focuskw',
    'seo_title'          => '_yoast_wpseo_title',
    'meta_description'   => '_yoast_wpseo_metadesc',
    'opengraph_title'    => '_yoast_wpseo_opengraph-title',
    'opengraph_desc'     => '_yoast_wpseo_opengraph-description',
    'twitter_title'      => '_yoast_wpseo_twitter-title',
    'twitter_desc'       => '_yoast_wpseo_twitter-description',
    'canonical'          => '_yoast_wpseo_canonical',
    'primary_category'   => '_yoast_wpseo_primary_category',
    'meta_robots_noindex'=> '_yoast_wpseo_meta-robots-noindex',
    'meta_robots_nofollow'=> '_yoast_wpseo_meta-robots-nofollow',
]);


add_action('rest_api_init', function () {

    // ───── GET endpoint ─────────────────────────────────────
    register_rest_route('yoast/v1', '/posts/(?P<id>\d+)', [
        'methods'             => 'GET',
        'callback'            => 'sm_yoast_get_meta',
        'permission_callback' => 'sm_yoast_permission_check',
        'args' => [
            'id' => [
                'validate_callback' => function($p) { return is_numeric($p); },
                'sanitize_callback' => 'absint',
            ],
        ],
    ]);

    // ───── POST endpoint ────────────────────────────────────
    register_rest_route('yoast/v1', '/posts/(?P<id>\d+)', [
        'methods'             => 'POST',
        'callback'            => 'sm_yoast_set_meta',
        'permission_callback' => 'sm_yoast_permission_check',
        'args' => [
            'id' => [
                'validate_callback' => function($p) { return is_numeric($p); },
                'sanitize_callback' => 'absint',
            ],
        ],
    ]);
});


/**
 * Permission callback — user must be able to edit the target post.
 */
function sm_yoast_permission_check($request) {
    $post_id = (int) $request['id'];
    if (!current_user_can('edit_post', $post_id)) {
        return new WP_Error(
            'rest_forbidden',
            __('You do not have permission to edit this post.'),
            ['status' => 403]
        );
    }
    return true;
}


/**
 * GET /wp-json/yoast/v1/posts/{id}
 */
function sm_yoast_get_meta($request) {
    $post_id = (int) $request['id'];
    if (!get_post($post_id)) {
        return new WP_Error('not_found', __('Post not found'), ['status' => 404]);
    }
    $out = ['id' => $post_id];
    foreach (SM_YOAST_FIELDS as $public_key => $meta_key) {
        $out[$public_key] = get_post_meta($post_id, $meta_key, true);
    }
    return rest_ensure_response($out);
}


/**
 * POST /wp-json/yoast/v1/posts/{id}
 *
 * Body example:
 *   { "focus_keyphrase": "best fishing rods 2026",
 *     "seo_title": "10 Best Fishing Rods for 2026 — Proven Picks",
 *     "meta_description": "Cut through 200+ rod options...",
 *     "opengraph_title": "...",
 *     "twitter_desc": "..." }
 */
function sm_yoast_set_meta($request) {
    $post_id = (int) $request['id'];
    if (!get_post($post_id)) {
        return new WP_Error('not_found', __('Post not found'), ['status' => 404]);
    }

    $params = $request->get_json_params();
    if (!is_array($params)) {
        return new WP_Error('bad_request', __('Body must be JSON object'), ['status' => 400]);
    }

    $updated = [];
    foreach (SM_YOAST_FIELDS as $public_key => $meta_key) {
        if (array_key_exists($public_key, $params)) {
            $value = sanitize_text_field((string) $params[$public_key]);
            $result = update_post_meta($post_id, $meta_key, $value);
            $updated[$public_key] = ($result !== false);
        }
    }

    return rest_ensure_response([
        'id'      => $post_id,
        'updated' => $updated,
    ]);
}


/**
 * Health check endpoint — used by health_check.py / install verification.
 * GET /wp-json/yoast/v1/ping
 */
add_action('rest_api_init', function() {
    register_rest_route('yoast/v1', '/ping', [
        'methods'             => 'GET',
        'callback'            => function() {
            return rest_ensure_response([
                'status' => 'ok',
                'plugin' => 'seo-machine-yoast-rest',
                'version' => '3.2.0',
                'yoast_installed' => defined('WPSEO_VERSION'),
                'yoast_version' => defined('WPSEO_VERSION') ? WPSEO_VERSION : null,
            ]);
        },
        'permission_callback' => '__return_true',  // Public endpoint, no auth needed
    ]);
});
