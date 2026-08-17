<?php
/**
 * Plugin Name: Xuanran SEO · Page Schema Types
 * Description: Gives WordPress *pages* the correct schema.org type without Rank Math Pro.
 *
 *              Rank Math Free offers only one page-level schema choice per post type:
 *              an "article" rich snippet, or "off". Neither is right for a page:
 *                - the default (`pt_page_default_rich_snippet = article`) marks up
 *                  contact pages, legal pages and storefronts as `Article`;
 *                - setting a page to "off" does NOT downgrade it to `WebPage` — it
 *                  removes the ENTIRE graph for that URL, leaving only BreadcrumbList
 *                  (verified live 2026-08-15 on project-alpha /about-us/, /contact-us/,
 *                  /faq/, which had been switched off for exactly that mistaken reason).
 *
 *              This plugin hooks Rank Math's public `rank_math/json_ld` filter — the
 *              same seam Pro's schema templates use — and on pages only:
 *                1. drops the `Article` (#richSnippet) node,
 *                2. drops the author `Person` node if nothing else references it,
 *                3. refines the `WebPage` node's @type to a WebPage subtype
 *                   (AboutPage / ContactPage / …) from the map below.
 *
 *              Organization, WebSite, BreadcrumbList and any content-generated
 *              FAQPage node are left untouched.
 *
 *              Drop at: wp-content/mu-plugins/xuanran-page-schema.php
 *              MU-plugins auto-load; no activation needed.
 *
 * Version:     1.0.2
 * Author:      Xuanran SEO Blog Writer
 * License:     GPL-2.0+
 * Requires at least: 5.6
 * Tested up to:      6.7
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'XUANRAN_PAGE_SCHEMA_VERSION', '1.0.2' );

/**
 * Health-check endpoint: /wp-json/xuanran/v1/page-schema
 * Lets scripts/wordpress/check_mu_plugin_drift.py see the DEPLOYED version, so
 * this hop-3 surface is detectable rather than assumed (Rule 13).
 */
add_action(
	'rest_api_init',
	function () {
		register_rest_route(
			'xuanran/v1',
			'/page-schema',
			[
				'methods'             => 'GET',
				'permission_callback' => '__return_true',
				'callback'            => function () {
					return [
						'page_schema_active'  => true,
						'page_schema_version' => XUANRAN_PAGE_SCHEMA_VERSION,
						'rank_math_active'    => class_exists( 'RankMath' ),
						'mapped_slugs'        => array_keys( xuanran_page_schema_map() ),
					];
				},
			]
		);
	}
);

/**
 * Slug → schema.org WebPage subtype.
 *
 * Only add a subtype when the page genuinely is that thing. Anything not listed
 * falls back to plain `WebPage`, which is always correct for a page and is a
 * strict improvement on `Article`. Do not invent claims here: `MedicalWebPage`,
 * for instance, asserts medical content and is deliberately NOT used.
 */
function xuanran_page_schema_map() {
	$map = [
		// About / company identity
		'about'          => 'AboutPage',
		'about-us'       => 'AboutPage',
		'about-us-3'     => 'AboutPage', // project-lima "About project-lima", project-mike "About us"
		'our-story'      => 'AboutPage',
		'our-kilns'      => 'AboutPage', // project-delta's about page
		'why-project-alpha'  => 'AboutPage',
		'company'        => 'AboutPage',
		// Contact
		'contact'        => 'ContactPage',
		'contact-us'     => 'ContactPage',
		// Commerce utility
		'checkout'       => 'CheckoutPage',
		'cart'           => 'CheckoutPage',
		// Account / order lookup
		'my-account'     => 'ProfilePage',
		'track-order'    => 'WebPage',
	];

	/**
	 * Filter the slug → schema type map so a site can extend it without editing
	 * this file.
	 */
	return apply_filters( 'xuanran/page_schema_map', $map );
}

add_filter(
	'rank_math/json_ld',
	function ( $data, $jsonld ) {
		// Pages only. Leave posts, products and archives exactly as they are.
		if ( ! is_page() ) {
			return $data;
		}
		// The WooCommerce shop page is a page but is handled as a CollectionPage.
		if ( function_exists( 'is_shop' ) && is_shop() ) {
			return $data;
		}
		if ( ! is_array( $data ) ) {
			return $data;
		}

		$types_of = static function ( $node ) {
			if ( ! is_array( $node ) || ! isset( $node['@type'] ) ) {
				return [];
			}
			return is_array( $node['@type'] ) ? $node['@type'] : [ $node['@type'] ];
		};

		$article_keys = [];
		$author_ids   = [];
		$webpage_key  = null;

		foreach ( $data as $key => $node ) {
			$types = $types_of( $node );
			if ( ! $types ) {
				continue;
			}

			// The rich-snippet Article node Rank Math adds for the page.
			if ( array_intersect( $types, [ 'Article', 'BlogPosting', 'NewsArticle' ] ) ) {
				$article_keys[] = $key;
				if ( isset( $node['author']['@id'] ) ) {
					$author_ids[] = $node['author']['@id'];
				}
				continue;
			}

			// The page's own WebPage node (may already be a subtype, e.g. CollectionPage).
			if ( in_array( 'WebPage', $types, true ) && null === $webpage_key ) {
				$webpage_key = $key;
			}
		}

		// NOTE: do NOT return early when there is no Article node. A page can
		// already be Article-free (its rich snippet was switched off, or a
		// content block supplied its own type) and still deserve the WebPage
		// refinement below — skipping it left project-mike /about-us-3/ as a plain
		// WebPage while every other about page became an AboutPage.
		foreach ( $article_keys as $key ) {
			unset( $data[ $key ] );
		}

		// Drop the author Person node only if no surviving node still points at it.
		if ( $author_ids ) {
			$still_referenced = static function ( $haystack, $id ) use ( &$still_referenced ) {
				foreach ( $haystack as $v ) {
					if ( is_array( $v ) ) {
						if ( $still_referenced( $v, $id ) ) {
							return true;
						}
					} elseif ( is_string( $v ) && $v === $id ) {
						return true;
					}
				}
				return false;
			};
			foreach ( $data as $key => $node ) {
				if ( ! isset( $node['@id'] ) || ! in_array( $node['@id'], $author_ids, true ) ) {
					continue;
				}
				$others = $data;
				unset( $others[ $key ] );
				if ( ! $still_referenced( $others, $node['@id'] ) ) {
					unset( $data[ $key ] );
				}
			}
		}

		// Refine the WebPage type where we can name the page honestly.
		if ( null !== $webpage_key ) {
			$post = get_queried_object();
			$slug = ( $post && isset( $post->post_name ) ) ? $post->post_name : '';
			$map  = xuanran_page_schema_map();
			if ( $slug && isset( $map[ $slug ] ) ) {
				$data[ $webpage_key ]['@type'] = $map[ $slug ];
			}
		}

		return $data;
	},
	99,
	2
);
