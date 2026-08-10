<?php
/**
 * Plugin Name: Xuanran SEO · Rank Math REST Bridge
 * Description: Exposes Rank Math post meta to the WP core REST API so the
 *              Xuanran SEO Blog Writer plugin can write SEO fields via
 *              PATCH /wp-json/wp/v2/posts/{id} with a `meta` object.
 *
 *              Drop this file at:  wp-content/mu-plugins/xuanran-rank-math-rest-bridge.php
 *              MU-plugins auto-load. No activation needed.
 *
 *              Companion plugin: Xuanran SEO Blog Writer (Claude Code plugin)
 *              Use: standard POST /wp/v2/posts/{id} with body:
 *                   { "meta": {
 *                       "rank_math_title": "...",
 *                       "rank_math_description": "...",
 *                       "rank_math_focus_keyword": "kw1, kw2",
 *                       "rank_math_robots": ["index", "follow"],
 *                       ...
 *                   }}
 *
 * Version:     1.5.0
 * Author:      Xuanran SEO Blog Writer
 * License:     GPL-2.0+
 * Requires at least: 5.6
 * Tested up to:      6.7
 *
 * Changelog:
 *   1.5.0 (2026-05-29) — Added WooCommerce native `product_brand` taxonomy (WooCommerce
 *                        9.6+ ships it in core) to term-meta registration, so Rank Math
 *                        SEO fields are writable on brand archives via
 *                        POST /wp/v2/product_brand/{id} with a `meta` body. Needed for the
 *                        project-echo brand migration (brands moved out of product_cat into the
 *                        native brand taxonomy).
 *   1.4.0 (2026-05-28) — Added WooCommerce taxonomies `product_cat` + `product_tag`
 *                        to term-meta registration so Rank Math SEO fields are
 *                        writable on product-category / product-tag archives via
 *                        POST /wp/v2/product_cat/{id} (and /product_tag/{id}) with
 *                        a `meta` body. Broadened term auth to also accept
 *                        `manage_woocommerce` (shop_manager role). Needed for the
 *                        project-echo store (age-restricted product brand category SEO). Without this,
 *                        product_cat terms expose `meta: []` (no registered keys)
 *                        and Rank Math meta is unwritable through core REST.
 *   1.3.0 (2026-05-27) — Added rank_math_rich_snippet + rank_math_snippet_article_type
 *                        to enable per-page schema type control via REST API.
 *                        Needed for P0-02 fix: homepage Article→off (WebPage).
 *   1.2.0 (2026-05-20) — Added register_term_meta() for post_tag taxonomy. Tag
 *                        archive SEO meta is now writable via POST
 *                        /wp/v2/tags/{id} with `meta` body, matching the
 *                        v1.1 category-taxonomy support.
 *   1.1.0 (2026-05-20) — Added register_term_meta() for category taxonomy so
 *                        rank_math_* fields are writable on category archive pages
 *                        via POST /wp/v2/categories/{id} with `meta` body.
 *   1.0.0 (initial)   — Post meta only.
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }

/**
 * Shared auth callback for POST meta: only users with edit_post capability for
 * the specific post may write any field. Application Password user needs >=
 * Editor role (Author works for own posts; Contributor will silently fail).
 */
function xuanran_rmrb_auth( $allowed, $meta_key, $post_id, $user_id ) {
    return user_can( $user_id, 'edit_post', $post_id );
}

/**
 * Shared auth callback for TERM meta: users with manage_categories (core
 * taxonomies) OR manage_woocommerce (product_cat / product_tag, e.g. the
 * shop_manager role) may write term meta. Administrators always pass.
 */
function xuanran_rmrb_term_auth( $allowed, $meta_key, $term_id, $user_id ) {
    return user_can( $user_id, 'manage_categories' )
        || user_can( $user_id, 'manage_woocommerce' );
}

add_action( 'init', function () {

    /* ─────────────────────────────────────────────────────────────
     * Scalar string fields (the bulk of Rank Math meta)
     * ───────────────────────────────────────────────────────────── */
    $scalar_strings = [
        // Core SEO
        'rank_math_title',                  // %title%/%sep% variables OK
        'rank_math_description',            // NO underscore prefix
        'rank_math_focus_keyword',          // comma-separated, NOT array
        'rank_math_breadcrumb_title',
        'rank_math_pillar_content',         // "on" | "" (string-as-bool)

        // Social — Facebook / OpenGraph
        'rank_math_facebook_title',
        'rank_math_facebook_description',
        'rank_math_twitter_use_facebook',   // "on" | ""
        'rank_math_twitter_card_type',      // summary | summary_large_image
        'rank_math_twitter_title',
        'rank_math_twitter_description',

        // News / Misc
        'rank_math_news_sitemap_robots',    // index | noindex (Pro only, harmless)

        // Schema type (controls which @type appears in JSON-LD @graph)
        // Values: article | book | course | event | jobposting | music |
        //         product | recipe | restaurant | service | software |
        //         video | off (= no rich snippet, just WebPage/Organization)
        'rank_math_rich_snippet',
        'rank_math_snippet_article_type',   // Article | BlogPosting | NewsArticle
    ];
    foreach ( $scalar_strings as $key ) {
        register_post_meta( '', $key, [
            'type'              => 'string',
            'single'            => true,
            'show_in_rest'      => true,
            'sanitize_callback' => 'sanitize_text_field',
            'auth_callback'     => 'xuanran_rmrb_auth',
        ] );
    }

    /* ─────────────────────────────────────────────────────────────
     * URL-typed scalars (stricter sanitization)
     * ───────────────────────────────────────────────────────────── */
    $url_keys = [
        'rank_math_canonical_url',
        'rank_math_facebook_image',
        'rank_math_twitter_image',
    ];
    foreach ( $url_keys as $key ) {
        register_post_meta( '', $key, [
            'type'              => 'string',
            'single'            => true,
            'show_in_rest'      => true,
            'sanitize_callback' => 'esc_url_raw',
            'auth_callback'     => 'xuanran_rmrb_auth',
        ] );
    }

    /* ─────────────────────────────────────────────────────────────
     * Integer scalars
     * ───────────────────────────────────────────────────────────── */
    $int_keys = [
        'rank_math_primary_category',       // term ID
        'rank_math_facebook_image_id',      // attachment ID
    ];
    foreach ( $int_keys as $key ) {
        register_post_meta( '', $key, [
            'type'              => 'integer',
            'single'            => true,
            'show_in_rest'      => true,
            'sanitize_callback' => 'absint',
            'auth_callback'     => 'xuanran_rmrb_auth',
        ] );
    }

    /* ─────────────────────────────────────────────────────────────
     * rank_math_robots — array of enum strings
     * Pitfall: MUST be real array. Comma-string or serialized string
     * triggers class-paper.php:526 foreach() warnings.
     * ───────────────────────────────────────────────────────────── */
    register_post_meta( '', 'rank_math_robots', [
        'type'         => 'array',
        'single'       => true,
        'show_in_rest' => [
            'schema' => [
                'type'  => 'array',
                'items' => [
                    'type' => 'string',
                    'enum' => [
                        'index', 'noindex', 'nofollow', 'noarchive',
                        'noimageindex', 'nosnippet',
                    ],
                ],
            ],
        ],
        'sanitize_callback' => function ( $value ) {
            if ( ! is_array( $value ) ) { return []; }
            $allowed = [ 'index', 'noindex', 'nofollow', 'noarchive',
                         'noimageindex', 'nosnippet' ];
            $clean = array_intersect( $allowed, array_map( 'sanitize_key', $value ) );
            return array_values( $clean );
        },
        'auth_callback' => 'xuanran_rmrb_auth',
    ] );

    /* ─────────────────────────────────────────────────────────────
     * rank_math_advanced_robots — associative object
     * Format: {"max-snippet":"-1","max-image-preview":"large", ...}
     * ───────────────────────────────────────────────────────────── */
    register_post_meta( '', 'rank_math_advanced_robots', [
        'type'         => 'object',
        'single'       => true,
        'show_in_rest' => [
            'schema' => [
                'type'                 => 'object',
                'additionalProperties' => [ 'type' => 'string' ],
                'properties'           => [
                    'max-snippet'       => [ 'type' => 'string' ],
                    'max-video-preview' => [ 'type' => 'string' ],
                    'max-image-preview' => [ 'type' => 'string' ],
                ],
            ],
        ],
        'sanitize_callback' => function ( $value ) {
            if ( ! is_array( $value ) ) { return []; }
            $clean = [];
            foreach ( [ 'max-snippet', 'max-video-preview', 'max-image-preview' ] as $k ) {
                if ( isset( $value[ $k ] ) ) {
                    $clean[ $k ] = sanitize_text_field( (string) $value[ $k ] );
                }
            }
            return $clean;
        },
        'auth_callback' => 'xuanran_rmrb_auth',
    ] );

    /* ─────────────────────────────────────────────────────────────
     * Optional: trigger Rank Math SEO score refresh after focus_keyword write
     * Rank Math's content analyzer is JS-driven (only runs in editor), so this
     * is a best-effort nudge. The user still needs to run
     *   Rank Math → Status & Tools → Database Tools → Update SEO Scores
     * for bulk-imported posts to get scores in the All Posts list.
     * ───────────────────────────────────────────────────────────── */
    add_action( 'updated_post_meta', function ( $meta_id, $post_id, $meta_key ) {
        if ( 'rank_math_focus_keyword' !== $meta_key ) { return; }
        if ( function_exists( 'rank_math' )
             && method_exists( rank_math(), 'update_post_score' ) ) {
            rank_math()->update_post_score( $post_id );
        }
    }, 10, 3 );

    /* ═════════════════════════════════════════════════════════════
     * TERM META — register the same Rank Math keys for blog + WooCommerce
     * taxonomies so they're writable via:
     *   POST /wp/v2/categories/{id}    with body {"meta": {...}}
     *   POST /wp/v2/tags/{id}          with body {"meta": {...}}
     *   POST /wp/v2/product_cat/{id}    with body {"meta": {...}}   (WooCommerce)
     *   POST /wp/v2/product_tag/{id}    with body {"meta": {...}}   (WooCommerce)
     *   POST /wp/v2/product_brand/{id}  with body {"meta": {...}}   (WooCommerce 9.6+ native brands)
     * v1.1.0 added category; v1.2.0 added post_tag; v1.4.0 added product_cat +
     * product_tag; v1.5.0 added product_brand. (All WooCommerce taxonomies are
     * registered show_in_rest by core, so register_term_meta() is all that is
     * needed to expose the Rank Math keys.)
     * ═════════════════════════════════════════════════════════════ */
    $taxonomies_with_rm_meta = [ 'category', 'post_tag', 'product_cat', 'product_tag', 'product_brand' ];

    $term_scalar_strings = [
        'rank_math_title',
        'rank_math_description',
        'rank_math_focus_keyword',
        'rank_math_breadcrumb_title',
        'rank_math_facebook_title',
        'rank_math_facebook_description',
        'rank_math_twitter_use_facebook',
        'rank_math_twitter_card_type',
        'rank_math_twitter_title',
        'rank_math_twitter_description',
    ];
    foreach ( $taxonomies_with_rm_meta as $tax ) {
        foreach ( $term_scalar_strings as $key ) {
            register_term_meta( $tax, $key, [
                'type'              => 'string',
                'single'            => true,
                'show_in_rest'      => true,
                'sanitize_callback' => 'sanitize_text_field',
                'auth_callback'     => 'xuanran_rmrb_term_auth',
            ] );
        }
    }

    $term_url_keys = [
        'rank_math_canonical_url',
        'rank_math_facebook_image',
        'rank_math_twitter_image',
    ];
    foreach ( $taxonomies_with_rm_meta as $tax ) {
        foreach ( $term_url_keys as $key ) {
            register_term_meta( $tax, $key, [
                'type'              => 'string',
                'single'            => true,
                'show_in_rest'      => true,
                'sanitize_callback' => 'esc_url_raw',
                'auth_callback'     => 'xuanran_rmrb_term_auth',
            ] );
        }
    }

    foreach ( $taxonomies_with_rm_meta as $tax ) {
        register_term_meta( $tax, 'rank_math_robots', [
            'type'         => 'array',
            'single'       => true,
            'show_in_rest' => [
                'schema' => [
                    'type'  => 'array',
                    'items' => [
                        'type' => 'string',
                        'enum' => [
                            'index', 'noindex', 'nofollow', 'noarchive',
                            'noimageindex', 'nosnippet',
                        ],
                    ],
                ],
            ],
            'sanitize_callback' => function ( $value ) {
                if ( ! is_array( $value ) ) { return []; }
                $allowed = [ 'index', 'noindex', 'nofollow', 'noarchive',
                             'noimageindex', 'nosnippet' ];
                $clean = array_intersect( $allowed, array_map( 'sanitize_key', $value ) );
                return array_values( $clean );
            },
            'auth_callback' => 'xuanran_rmrb_term_auth',
        ] );

        register_term_meta( $tax, 'rank_math_advanced_robots', [
            'type'         => 'object',
            'single'       => true,
            'show_in_rest' => [
                'schema' => [
                    'type'                 => 'object',
                    'additionalProperties' => [ 'type' => 'string' ],
                    'properties'           => [
                        'max-snippet'       => [ 'type' => 'string' ],
                        'max-video-preview' => [ 'type' => 'string' ],
                        'max-image-preview' => [ 'type' => 'string' ],
                    ],
                ],
            ],
            'sanitize_callback' => function ( $value ) {
                if ( ! is_array( $value ) ) { return []; }
                $clean = [];
                foreach ( [ 'max-snippet', 'max-video-preview', 'max-image-preview' ] as $k ) {
                    if ( isset( $value[ $k ] ) ) {
                        $clean[ $k ] = sanitize_text_field( (string) $value[ $k ] );
                    }
                }
                return $clean;
            },
            'auth_callback' => 'xuanran_rmrb_term_auth',
        ] );
    }
} );

/* ─────────────────────────────────────────────────────────────
 * Health-check endpoint: /wp-json/xuanran/v1/rank-math-bridge
 * Lets the Python wp_client confirm this MU-plugin is installed + active.
 * ───────────────────────────────────────────────────────────── */
add_action( 'rest_api_init', function () {
    register_rest_route( 'xuanran/v1', '/rank-math-bridge', [
        'methods'             => 'GET',
        'permission_callback' => '__return_true',
        'callback'            => function () {
            return [
                'bridge_active'    => true,
                'bridge_version'   => '1.5.0',
                'rank_math_active' => class_exists( 'RankMath' ),
                'rank_math_version' => defined( 'RANK_MATH_VERSION' )
                                       ? RANK_MATH_VERSION : null,
                'taxonomies_covered' => [ 'category', 'post_tag', 'product_cat', 'product_tag', 'product_brand' ],
                'registered_keys'  => [
                    'rank_math_title',
                    'rank_math_description',
                    'rank_math_focus_keyword',
                    'rank_math_canonical_url',
                    'rank_math_robots',
                    'rank_math_advanced_robots',
                    'rank_math_primary_category',
                    'rank_math_breadcrumb_title',
                    'rank_math_pillar_content',
                    'rank_math_facebook_title',
                    'rank_math_facebook_description',
                    'rank_math_facebook_image',
                    'rank_math_twitter_use_facebook',
                    'rank_math_twitter_card_type',
                    'rank_math_twitter_title',
                    'rank_math_twitter_description',
                    'rank_math_twitter_image',
                    'rank_math_rich_snippet',
                    'rank_math_snippet_article_type',
                ],
            ];
        },
    ] );
} );
