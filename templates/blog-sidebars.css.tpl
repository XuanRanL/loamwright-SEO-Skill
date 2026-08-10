/* =====================================================================
   __SLUG__ — blog sidebars (index + single post)
   GENERATED. Source: templates/blog-sidebars.css.tpl
   Re-run: python -m scripts.build.blog_sidebar_generator __SLUG__
   Generated: __GENERATED__

   DEPLOY AS: a WPCode CSS snippet, location "Site Wide Header".

   TWO THINGS THAT SILENTLY BREAK THIS
   1. Remove-Unused-CSS. If the host runs one (FlyingPress, Perfmatters,
      LiteSpeed…), add `__PREFIX__-` to its safelist or every rule below is
      stripped in production while still looking correct to a logged-in admin.
   2. A theme or an existing snippet drawing widget dividers with !important.
      The borderless override below carries !important for exactly that reason,
      scoped to `.__PREFIX__-side` so unrelated widgets keep their styling.
   ===================================================================== */

.wd-sidebar .__PREFIX__-side,
.sidebar-container .__PREFIX__-side,
.widget-area .__PREFIX__-side {
	--__PREFIX__-primary: __C_PRIMARY__;
	--__PREFIX__-accent: __C_ACCENT__;
	--__PREFIX__-accent-dk: __C_ACCENT_DARK__;
	--__PREFIX__-surface: __C_SURFACE__;
	--__PREFIX__-surface-2: __C_SURFACE2__;
	--__PREFIX__-ink: __C_INK__;
	--__PREFIX__-muted: __C_MUTED__;

	/* Borderless: no border, no card outline, no shadow. Separation comes from
	   whitespace and imagery. !important defeats theme/snippet dividers. */
	border: 0 !important;
	border-bottom: 0 !important;
	padding: 0 !important;
	margin: 0 0 34px !important;
	background: transparent !important;
	box-shadow: none;
	border-radius: 0;
	font-size: 14px;
	line-height: 1.5;
	color: var(--__PREFIX__-ink);
}

.wd-sidebar .__PREFIX__-side:last-child,
.sidebar-container .__PREFIX__-side:last-child,
.widget-area .__PREFIX__-side:last-child { margin-bottom: 0 !important; }

.wd-sidebar .__PREFIX__-side .__PREFIX__-side__title,
.wd-sidebar .__PREFIX__-side .widget-title {
	font-family: "__F_HEADING__", Georgia, serif;
	font-size: 18px;
	font-weight: 400;
	line-height: 1.25;
	color: var(--__PREFIX__-primary);
	margin: 0 0 14px;
	padding: 0;
	border: 0;
	text-transform: none;
	letter-spacing: 0;
}

.wd-sidebar .__PREFIX__-side a { color: var(--__PREFIX__-primary); text-decoration: none; }
.wd-sidebar .__PREFIX__-side a:hover { color: var(--__PREFIX__-accent-dk); }

/* ---------------- CTA image card ---------------- */

.__PREFIX__-cta {
	display: block;
	overflow: hidden;
	border-radius: 14px;
	background: var(--__PREFIX__-surface);
	transition: transform .2s ease;
}
.__PREFIX__-cta:hover { transform: translateY(-2px); }

.__PREFIX__-cta__img { display: block; }
.__PREFIX__-cta__img img {
	display: block;
	width: 100%;
	height: auto;
	aspect-ratio: 4 / 3;      /* reserved box — no layout shift */
	object-fit: cover;
	border: 0;
}

.__PREFIX__-cta__body { display: block; padding: 16px 18px 18px; }

.__PREFIX__-cta__kicker {
	display: block;
	font-size: 10.5px;
	font-weight: 700;
	letter-spacing: .1em;
	text-transform: uppercase;
	color: var(--__PREFIX__-accent-dk);
	margin-bottom: 7px;
}

.__PREFIX__-cta__title {
	display: block;
	font-family: "__F_HEADING__", Georgia, serif;
	font-size: 19px;
	line-height: 1.22;
	color: var(--__PREFIX__-primary);
	margin-bottom: 14px;
}

.__PREFIX__-cta__btn {
	display: inline-block;
	padding: 9px 20px;
	border-radius: 999px;
	background: var(--__PREFIX__-accent);
	color: #fff;
	font-size: 12.5px;
	font-weight: 700;
	transition: background .18s ease;
}
.__PREFIX__-cta:hover .__PREFIX__-cta__btn { background: var(--__PREFIX__-accent-dk); }

/* ---------------- Product promo ---------------- */

.__PREFIX__-shop {
	list-style: none;
	margin: 0;
	padding: 0;
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 14px;
}

.__PREFIX__-shop__i { min-width: 0; }
.__PREFIX__-shop__i > a { display: block; }

/* One product in a two-column grid leaves a dead half-row. Let it span. */
.__PREFIX__-shop__i:only-child { grid-column: 1 / -1; }
.__PREFIX__-shop__i:only-child .__PREFIX__-shop__img img { aspect-ratio: 16 / 10; }
.__PREFIX__-shop__i:only-child .__PREFIX__-shop__n { font-size: 14px; }

.__PREFIX__-shop__img { display: block; }
.__PREFIX__-shop__img img {
	display: block;
	width: 100%;
	height: auto;
	aspect-ratio: 1 / 1;
	object-fit: cover;
	border: 0;
	border-radius: 12px;
	background: var(--__PREFIX__-surface);
	transition: transform .2s ease;
}
.__PREFIX__-shop__i > a:hover .__PREFIX__-shop__img img { transform: scale(1.03); }

.__PREFIX__-shop__n {
	display: -webkit-box;
	-webkit-line-clamp: 2;
	-webkit-box-orient: vertical;
	overflow: hidden;
	margin-top: 8px;
	font-size: 12.5px;
	line-height: 1.35;
	color: var(--__PREFIX__-muted);
}

/* ---------------- Page promo ---------------- */

.__PREFIX__-promo { list-style: none; margin: 0; padding: 0; }
.__PREFIX__-promo__i { margin-bottom: 14px; }
.__PREFIX__-promo__i:last-child { margin-bottom: 0; }

.__PREFIX__-promo__i > a { display: flex; align-items: center; gap: 12px; border: 0; }

.__PREFIX__-promo__img { flex: none; display: block; }
.__PREFIX__-promo__img img {
	display: block;
	width: 62px;
	height: 62px;
	object-fit: cover;
	border: 0;
	border-radius: 10px;
	background: var(--__PREFIX__-surface);
}

.__PREFIX__-promo__n {
	font-size: 13.5px;
	line-height: 1.35;
	color: var(--__PREFIX__-ink);
	display: -webkit-box;
	-webkit-line-clamp: 3;
	-webkit-box-orient: vertical;
	overflow: hidden;
}
.__PREFIX__-promo__i > a:hover .__PREFIX__-promo__n { color: var(--__PREFIX__-accent-dk); }

/* Rows with no thumbnail (tool links) get a soft accent instead of a border. */
.__PREFIX__-promo__i > a:not(:has(.__PREFIX__-promo__img)) {
	padding: 10px 0 10px 14px;
	border-left: 3px solid var(--__PREFIX__-surface-2);
	border-radius: 0 8px 8px 0;
	background: linear-gradient(90deg, var(--__PREFIX__-surface) 0%, transparent 70%);
}
.__PREFIX__-promo__i > a:not(:has(.__PREFIX__-promo__img)):hover {
	border-left-color: var(--__PREFIX__-accent);
}

/* ---------------- Core Categories widget, borderless ---------------- */

.wd-sidebar .__PREFIX__-side.widget_categories ul,
.wd-sidebar .__PREFIX__-side.widget_categories li {
	border: 0 !important;
	list-style: none;
	margin-left: 0;
	padding-left: 0;
}
.wd-sidebar .__PREFIX__-side.widget_categories li { padding: 8px 0; font-size: 14px; }
.wd-sidebar .__PREFIX__-side.widget_categories li a { color: var(--__PREFIX__-ink); }
.wd-sidebar .__PREFIX__-side.widget_categories li a:hover { color: var(--__PREFIX__-accent-dk); }
.wd-sidebar .__PREFIX__-side.widget_categories .children { margin-top: 4px; padding-left: 14px; }
.wd-sidebar .__PREFIX__-side.widget_categories .children li { padding: 5px 0; font-size: 13px; }

/* ---------------- Responsive / motion / print ---------------- */

@media (max-width: 1024px) {
	.wd-sidebar .__PREFIX__-side { margin-bottom: 26px !important; }
	.__PREFIX__-cta__title { font-size: 18px; }
}

@media (prefers-reduced-motion: reduce) {
	.__PREFIX__-cta,
	.__PREFIX__-cta__btn,
	.__PREFIX__-shop__img img { transition: none; }
	.__PREFIX__-cta:hover { transform: none; }
	.__PREFIX__-shop__i > a:hover .__PREFIX__-shop__img img { transform: none; }
}

@media print {
	.wd-sidebar .__PREFIX__-side { display: none; }
}
