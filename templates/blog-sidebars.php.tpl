<?php
/**
 * Plugin Name: __BRAND__ Blog Sidebars
 * Description: Two dedicated widget areas (blog index + single post) and the promotional widgets that fill them. Borderless. Never touches the theme's shared sidebar.
 * Version:     1.0.0
 *
 * GENERATED FILE — do not hand-edit on the server.
 * Source: scripts/build/blog_sidebar_generator.py + templates/blog-sidebars.php.tpl
 * Project: __SLUG__      Generated: __GENERATED__
 * Re-run:  python -m scripts.build.blog_sidebar_generator __SLUG__
 *
 * WHY AN MU-PLUGIN
 * register_sidebar() and register_widget() must run before `widgets_init`.
 * mu-plugins load ahead of regular plugins, which guarantees that, and they
 * survive theme updates on sites with no child theme. A snippet-manager plugin
 * is NOT a safe host for this: on one fleet site the identical code as a WPCode
 * Lite PHP snippet never executed, with no error anywhere.
 *
 * DESIGN INTENT
 * The two templates do different jobs. The index helps a reader FIND something
 * (its own categories first). The article page PROMOTES — an image-led CTA card,
 * products, and other pages worth reading. Borderless throughout: separation is
 * whitespace and imagery, never a hairline.
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }

/** Baked at generation time from the project's business-context.json. */
function __PREFIX___config() {
	static $c = null;
	if ( $c === null ) { $c = __CONFIG__; }
	return $c;
}

/* ------------------------------------------------------------------ *
 * Widget areas
 * ------------------------------------------------------------------ */

add_action( 'widgets_init', function () {
	$common = [
		'before_widget' => '<div id="%1$s" class="wd-widget widget sidebar-widget __PREFIX__-side %2$s">',
		'after_widget'  => '</div>',
		'before_title'  => '<h2 class="widget-title __PREFIX__-side__title">',
		'after_title'   => '</h2>',
	];

	register_sidebar( $common + [
		'name'        => '__BRAND__ — Single Post Sidebar',
		'id'          => '__PREFIX__-post-sidebar',
		'description' => 'Blog article pages. Promotional: CTA card, products, other pages.',
	] );

	register_sidebar( $common + [
		'name'        => '__BRAND__ — Blog Index Sidebar',
		'id'          => '__PREFIX__-blog-sidebar',
		'description' => 'Blog index + category/tag archives. Categories first, then supporting modules.',
	] );
} );

/**
 * Swap the area in per template. The theme's shared sidebar is never modified,
 * so pages and shop keep whatever they had.
 *
 * WoodMart resolves the name through this filter. On other themes, wire the two
 * area ids into the template instead — the widgets themselves are theme-neutral.
 */
add_filter( 'woodmart_get_sidebar_name', function ( $name ) {
	if ( is_singular( 'post' ) && is_active_sidebar( '__PREFIX__-post-sidebar' ) ) {
		return '__PREFIX__-post-sidebar';
	}
	if ( __PREFIX___is_listing() && is_active_sidebar( '__PREFIX__-blog-sidebar' ) ) {
		return '__PREFIX__-blog-sidebar';
	}
	return $name;
}, 20 );

function __PREFIX___is_listing() {
	return is_home() || is_category() || is_tag() || is_date() || is_author();
}
function __PREFIX___in_scope() {
	return is_singular( 'post' ) || __PREFIX___is_listing();
}

/* ------------------------------------------------------------------ *
 * CTA image card
 * ------------------------------------------------------------------ *
 * Image + kicker + headline + one button. The image is a real attachment so it
 * inherits the site's own image pipeline (WebP/AVIF, srcset, lazy-load) rather
 * than being a hardcoded path. Alt is intentionally empty: the card is
 * decorative and the headline beside it carries the meaning.
 */

class __PREFIX___Widget_CtaCard extends WP_Widget {
	public function __construct() {
		parent::__construct( '__PREFIX___cta_card', '__BRAND__ · CTA image card', [
			'description' => 'Image + headline + button. Use for tools, offers, or any page worth pushing.',
			'classname'   => 'widget___PREFIX___cta_card __PREFIX__-side--flush',
		] );
	}

	public function widget( $args, $instance ) {
		if ( ! __PREFIX___in_scope() ) { return; }

		$url   = trim( (string) ( $instance['url'] ?? '' ) );
		$title = trim( (string) ( $instance['title'] ?? '' ) );
		if ( ! $url || ! $title ) { return; }   // half-configured card renders nothing

		$img    = absint( $instance['img'] ?? 0 );
		$kicker = trim( (string) ( $instance['kicker'] ?? '' ) );
		$btn    = trim( (string) ( $instance['btn'] ?? '' ) );

		echo $args['before_widget'];
		printf( '<a class="__PREFIX__-cta" href="%s">', esc_url( $url ) );
		if ( $img ) {
			echo '<span class="__PREFIX__-cta__img">'
				. wp_get_attachment_image( $img, 'medium_large', false,
					[ 'loading' => 'lazy', 'decoding' => 'async', 'alt' => '' ] )
				. '</span>';
		}
		echo '<span class="__PREFIX__-cta__body">';
		if ( $kicker ) { printf( '<span class="__PREFIX__-cta__kicker">%s</span>', esc_html( $kicker ) ); }
		printf( '<span class="__PREFIX__-cta__title">%s</span>', esc_html( $title ) );
		if ( $btn ) { printf( '<span class="__PREFIX__-cta__btn">%s</span>', esc_html( $btn ) ); }
		echo '</span></a>';
		echo $args['after_widget'];
	}

	public function form( $instance ) {
		foreach ( [
			'kicker' => 'Kicker (small line above)',
			'title'  => 'Headline',
			'btn'    => 'Button label',
			'url'    => 'Link URL',
			'img'    => 'Image attachment ID',
		] as $k => $label ) {
			printf(
				'<p><label for="%1$s">%2$s</label><input class="widefat" id="%1$s" name="%3$s" type="text" value="%4$s"></p>',
				esc_attr( $this->get_field_id( $k ) ), esc_html( $label ),
				esc_attr( $this->get_field_name( $k ) ), esc_attr( $instance[ $k ] ?? '' )
			);
		}
	}

	public function update( $new, $old ) {
		return [
			'kicker' => sanitize_text_field( $new['kicker'] ?? '' ),
			'title'  => sanitize_text_field( $new['title'] ?? '' ),
			'btn'    => sanitize_text_field( $new['btn'] ?? '' ),
			'url'    => esc_url_raw( $new['url'] ?? '' ),
			'img'    => absint( $new['img'] ?? 0 ),
		];
	}
}

/* ------------------------------------------------------------------ *
 * Product promo
 * ------------------------------------------------------------------ */

class __PREFIX___Widget_Products extends WP_Widget {
	public function __construct() {
		// The id_base is a DATA contract, not a label: WordPress stores widget
		// assignments in the `sidebars_widgets` option keyed by it. Renaming it
		// orphans every already-assigned instance — the sidebar silently empties
		// while the file itself deploys and verifies perfectly. It is `_shop`
		// because this widget renders `.__PREFIX__-shop` markup; keep the two in
		// step, and never rename either without re-assigning the live widgets.
		parent::__construct( '__PREFIX___shop', '__BRAND__ · Product promo', [
			'description' => 'Products from one category, image-led. Excluded categories can never render.',
			'classname'   => 'widget___PREFIX___products',
		] );
	}

	public function widget( $args, $instance ) {
		if ( ! __PREFIX___in_scope() || ! function_exists( 'wc_get_products' ) ) { return; }

		$cfg  = __PREFIX___config();
		$slug = sanitize_title( $instance['cat'] ?? $cfg['product_category'] );
		if ( ! $slug ) { return; }

		/*
		 * Hard block. Some categories must never be merchandised from editorial
		 * content — prescription/regulated lines above all. This mirrors the
		 * project's conversion_offers.excluded_categories so the sidebar cannot
		 * become a second route to them.
		 */
		if ( in_array( $slug, (array) $cfg['excluded_product_categories'], true ) ) { return; }

		$limit = max( 1, min( 6, absint( $instance['limit'] ?? $cfg['product_limit_post'] ) ) );
		$products = wc_get_products( [
			'status'   => 'publish',
			'limit'    => $limit,
			'orderby'  => 'popularity',
			'category' => [ $slug ],
		] );
		if ( ! $products ) { return; }

		$heading = trim( (string) ( $instance['title'] ?? '' ) );
		echo $args['before_widget'];
		if ( $heading ) { echo $args['before_title'] . esc_html( $heading ) . $args['after_title']; }
		echo '<ul class="__PREFIX__-shop">';
		foreach ( $products as $p ) {
			printf(
				'<li class="__PREFIX__-shop__i"><a href="%1$s"><span class="__PREFIX__-shop__img">%2$s</span>'
				. '<span class="__PREFIX__-shop__n">%3$s</span></a></li>',
				esc_url( $p->get_permalink() ),
				$p->get_image( 'woocommerce_thumbnail' ),
				esc_html( $p->get_name() )
			);
		}
		echo '</ul>';
		echo $args['after_widget'];
	}

	public function form( $instance ) {
		$cfg = __PREFIX___config();
		printf( '<p><label for="%1$s">Heading</label><input class="widefat" id="%1$s" name="%2$s" type="text" value="%3$s"></p>',
			esc_attr( $this->get_field_id( 'title' ) ), esc_attr( $this->get_field_name( 'title' ) ),
			esc_attr( $instance['title'] ?? '' ) );
		printf( '<p><label for="%1$s">Product category slug</label><input class="widefat" id="%1$s" name="%2$s" type="text" value="%3$s"></p>',
			esc_attr( $this->get_field_id( 'cat' ) ), esc_attr( $this->get_field_name( 'cat' ) ),
			esc_attr( $instance['cat'] ?? $cfg['product_category'] ) );
		printf( '<p><label for="%1$s">How many (1-6)</label><input class="widefat" id="%1$s" name="%2$s" type="number" min="1" max="6" value="%3$d"></p>',
			esc_attr( $this->get_field_id( 'limit' ) ), esc_attr( $this->get_field_name( 'limit' ) ),
			absint( $instance['limit'] ?? $cfg['product_limit_post'] ) );
	}

	public function update( $new, $old ) {
		return [
			'title' => sanitize_text_field( $new['title'] ?? '' ),
			'cat'   => sanitize_title( $new['cat'] ?? '' ),
			'limit' => max( 1, min( 6, absint( $new['limit'] ?? 2 ) ) ),
		];
	}
}

/* ------------------------------------------------------------------ *
 * Page promo — other guides, landing pages, tools
 * ------------------------------------------------------------------ */

class __PREFIX___Widget_PagePromo extends WP_Widget {
	public function __construct() {
		parent::__construct( '__PREFIX___page_promo', '__BRAND__ · Page promo', [
			'description' => 'Pushes other guides / landing pages / tools. Auto-fills with related posts on an article.',
			'classname'   => 'widget___PREFIX___page_promo',
		] );
	}

	public function widget( $args, $instance ) {
		if ( ! __PREFIX___in_scope() ) { return; }

		$rows = [];

		// On an article, sibling guides from the same pillar come first — they are
		// the most relevant thing to promote and they need no configuration.
		if ( is_singular( 'post' ) ) {
			$cats = get_the_category();
			if ( $cats ) {
				$root = $cats[0]->parent ? $cats[0]->parent : $cats[0]->term_id;
				$q = new WP_Query( [
					'post_type'           => 'post',
					'posts_per_page'      => 3,
					'post__not_in'        => [ get_the_ID() ],
					'ignore_sticky_posts' => true,
					'no_found_rows'       => true,
					'cat'                 => $root,
				] );
				while ( $q->have_posts() ) {
					$q->the_post();
					$rows[] = [
						'url'   => get_permalink(),
						'label' => get_the_title(),
						'thumb' => get_the_post_thumbnail( get_the_ID(), 'thumbnail',
							[ 'loading' => 'lazy', 'alt' => '' ] ),
					];
				}
				wp_reset_postdata();
			}
		}

		if ( ! $rows ) {
			foreach ( (array) __PREFIX___config()['promo_pages'] as $row ) {
				if ( ! empty( $row['url'] ) && ! empty( $row['label'] ) ) { $rows[] = $row; }
			}
		}
		if ( ! $rows ) { return; }

		$heading = trim( (string) ( $instance['title'] ?? '' ) );
		echo $args['before_widget'];
		if ( $heading ) { echo $args['before_title'] . esc_html( $heading ) . $args['after_title']; }
		echo '<ul class="__PREFIX__-promo">';
		foreach ( $rows as $r ) {
			printf(
				'<li class="__PREFIX__-promo__i"><a href="%1$s">%2$s<span class="__PREFIX__-promo__n">%3$s</span></a></li>',
				esc_url( $r['url'] ),
				! empty( $r['thumb'] ) ? '<span class="__PREFIX__-promo__img">' . $r['thumb'] . '</span>' : '',
				esc_html( $r['label'] )
			);
		}
		echo '</ul>';
		echo $args['after_widget'];
	}

	public function form( $instance ) {
		printf( '<p><label for="%1$s">Heading</label><input class="widefat" id="%1$s" name="%2$s" type="text" value="%3$s"></p>',
			esc_attr( $this->get_field_id( 'title' ) ), esc_attr( $this->get_field_name( 'title' ) ),
			esc_attr( $instance['title'] ?? '' ) );
	}

	public function update( $new, $old ) {
		return [ 'title' => sanitize_text_field( $new['title'] ?? '' ) ];
	}
}

add_action( 'widgets_init', function () {
	register_widget( '__PREFIX___Widget_CtaCard' );
	register_widget( '__PREFIX___Widget_Products' );
	register_widget( '__PREFIX___Widget_PagePromo' );
} );
