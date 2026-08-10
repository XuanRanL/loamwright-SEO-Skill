"""Article CSS Generator.

Reads projects/{slug}/brand/brand-config.json and outputs projects/{slug}/brand/article-css.css,
a scoped CSS stylesheet for blog articles. The output is scoped to `.{slug}-pillar` so it
applies only when the article body is wrapped in that class.

Inputs (from brand-config.json):
  - site_slug
  - colors.primary, colors.secondary, colors.accent
  - colors.surface_mode   ("light" | "dark", default "light")  ← NEW (2026-06-23)
  - typography.heading_font, typography.body_font

Output:
  - projects/{slug}/brand/article-css.css  (~10 KB source, ~7-8 KB minified)

Design philosophy:
  - Scoped to .{slug}-pillar wrapper -> no theme conflicts
  - Token-driven (CSS custom properties) -> easy theme variants
  - LIGHT mode (default): dark text on the white content background most themes provide.
  - DARK mode (colors.surface_mode == "dark"): light text + gold accents, for brands/themes
    that render the post on a dark/near-black page background (e.g. Woodmart sites whose
    `html,body { background:#1A1A1C }`). In light mode a dark-text stylesheet renders
    invisible (dark-on-dark); dark mode fixes that and also forces the theme-rendered
    single-post <title> to a legible light color.
  - Mobile-first, print-friendly
  - Styles all structural elements: H2/H3, abstract, takeaways, TOC,
    tables, figures+figcaptions, blockquotes, references, FAQ, links, lists
  - Compatible with WordPress KSES (admin users with unfiltered_html)
  - Works alongside Woodmart, GeneratePress, Astra, Kadence, and other modern themes

Usage:
    python -m scripts.build.article_css_generator <slug>
    python -m scripts.build.article_css_generator <slug> --json
    python -m scripts.build.article_css_generator <slug> --output custom/path.css

The publish phase reads the generated file and injects it as inline <style>
in each article's WordPress post body.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rel_lum(hex_color: str) -> float:
    def _ch(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _hex_to_rgb(hex_color)
    return 0.2126 * _ch(r) + 0.7152 * _ch(g) + 0.0722 * _ch(b)


def _contrast(a: str, b: str) -> float:
    l1, l2 = _rel_lum(a), _rel_lum(b)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


def _readable_on(bg: str) -> str:
    """Near-black or near-white text — whichever has higher contrast on `bg`. Used for text
    placed directly on the brand accent (e.g. the At-a-Glance table header)."""
    dark, light = "#1b1f1d", "#ffffff"
    return dark if _contrast(dark, bg) >= _contrast(light, bg) else light


def _mix_hex(a: str, b: str, t: float) -> str:
    """Blend two hex colors: t fraction of a, (1-t) of b."""
    ra, ga, ba = _hex_to_rgb(a)
    rb, gb, bb = _hex_to_rgb(b)
    return "#{:02X}{:02X}{:02X}".format(
        round(ra * t + rb * (1 - t)), round(ga * t + gb * (1 - t)), round(ba * t + bb * (1 - t)))


def _legible_on_dark(accent: str, bg: str = "#1A1A1C", target: float = 4.5) -> str:
    """Lighten `accent` toward white just enough to clear `target` contrast on the dark bg,
    keeping as much brand hue as possible. Deep/saturated accents (which fixed-percentage
    lightening left illegible on near-black — BUG 6) now get a guaranteed-legible derivation."""
    for pct in range(95, -1, -5):
        c = _mix_hex(accent, "#ffffff", pct / 100)
        if _contrast(c, bg) >= target:
            return c
    return "#F5F5F0"


def _css_font(value: str) -> str:
    """Return a CSS-safe font value. A pre-quoted / multi-family STACK (contains a comma or a
    quote) is emitted verbatim; a bare single family name is wrapped in single quotes. Without
    this, a project storing a full stack (project-juliet's `heading_family`) produced invalid
    `font-family: ''Inter', ...'` and got no brand font at all (BUG 2)."""
    v = value.strip()
    if "," in v or "'" in v or '"' in v:
        return v
    return f"'{v}'"


def _project_paths(slug: str) -> tuple[Path, Path, Path]:
    """Return (project_root, brand_config_path, output_css_path)."""
    repo_root = Path(__file__).resolve().parents[2]
    project_dir = repo_root / "projects" / slug
    brand_cfg = project_dir / "brand" / "brand-config.json"
    out = project_dir / "brand" / "article-css.css"
    return project_dir, brand_cfg, out


def _slug_class(slug: str) -> str:
    """Convert project slug to safe CSS class name. Strips dots/underscores."""
    safe = slug.lower().replace("_", "-").replace(".", "-")
    return f"{safe}-pillar"


def _palette(mode: str, primary: str, secondary: str, accent: str) -> dict[str, str]:
    """Return the full semantic token map for the requested surface mode.

    LIGHT values reproduce the pre-2026-06-23 output (backward compatible).
    DARK values are tuned for a near-black page background with gold accents and
    pass WCAG AA contrast (body text >=7:1, muted text >=4.5:1 on #1A1A1C).
    """
    if mode == "dark":
        return {
            "primary": primary,            # only used for the subtle image shadow
            "text": "#DAD9D4",
            "text-muted": "#A6A7AD",
            "heading": "#F5F5F0",
            "heading-2": "#E8E8E2",
            "em": "#CFCFC9",
            "rule": accent,                # h2 underline + abstract border (brand accent on dark)
            "accent": accent,
            "accent-bar": accent,
            # Brand-parameterized (was hardcoded gold, project-echo-only) AND contrast-clamped on
            # near-black: fixed-percentage lightening left deep/saturated accents illegible
            # (BUG 6), so derive a guaranteed-legible hex from the accent instead.
            "link": _legible_on_dark(accent),
            "link-border": f"color-mix(in srgb, {accent} 42%, transparent)",
            "link-hover-bg": f"color-mix(in srgb, {accent} 16%, transparent)",
            "on-accent": _readable_on(accent),
            "card": "#202023",
            "card-kt": "#1f1f22",
            "card-toc": "#1d1d20",
            "card-quote": "#202023",
            "code-bg": "#26262A",
            "border": "#34343A",
            "border-soft": "#2A2A2E",
            "thead-bg": "#26262A",
            "thead-fg": "#F5F5F0",
            "table-bg": "#1b1b1e",
            "table-stripe": "#202023",
            "table-hover": "#2A2A2E",
            "strong": _legible_on_dark(accent, target=4.0),
            "marker": accent,
            "marker-ol": accent,
            "hr": "#34343A",
            "ref-link": _legible_on_dark(accent),
            "ref-link-border": f"color-mix(in srgb, {accent} 35%, transparent)",
            # Status tokens (typed callouts). info/tip reuse brand link/accent; only warn/danger
            # need fixed hues, tuned legible on near-black.
            "warn-bg": "#2A2416",
            "warn-border": "#E0A93B",
            "danger-bg": "#2A1A1A",
            "danger-border": "#E06A5A",
        }
    # light (default — historical behavior)
    return {
        "primary": primary,
        "text": "#1b1f1d",
        "text-muted": "#5b665f",
        "heading": primary,
        "heading-2": f"color-mix(in srgb, {primary} 90%, #000)",
        "em": f"color-mix(in srgb, {primary} 90%, #000)",
        "rule": primary,
        "accent": accent,
        "accent-bar": accent,
        "link": secondary,
        "link-border": f"color-mix(in srgb, {secondary} 32%, transparent)",
        "link-hover-bg": f"color-mix(in srgb, {secondary} 8%, #fff)",
        "card": f"color-mix(in srgb, {primary} 5%, #fff)",
        "card-kt": f"color-mix(in srgb, {accent} 18%, #fff)",
        "card-toc": "#fafbfa",
        "card-quote": f"color-mix(in srgb, {accent} 18%, #fff)",
        "code-bg": f"color-mix(in srgb, {primary} 5%, #fff)",
        "border": "#d8dfdb",
        "border-soft": "#ecefed",
        "thead-bg": primary,
        "thead-fg": "#fff",
        "table-bg": "#fff",
        "table-stripe": f"color-mix(in srgb, {primary} 5%, #fff)",
        "table-hover": f"color-mix(in srgb, {accent} 18%, #fff)",
        "strong": primary,
        "marker": accent,
        "marker-ol": primary,
        "hr": "#d8dfdb",
        "ref-link": f"color-mix(in srgb, {primary} 90%, #000)",
        "ref-link-border": f"color-mix(in srgb, {primary} 25%, transparent)",
        # Contrast-safe foreground for text placed directly on the brand accent (At-a-Glance header).
        "on-accent": _readable_on(accent),
        # Status tokens (typed callouts). info/tip reuse brand link/accent; only warn/danger
        # need fixed hues (amber-700 / red-700, >=4.5:1 on the light content background).
        "warn-bg": "color-mix(in srgb, #B45309 10%, #fff)",
        "warn-border": "#B45309",
        "danger-bg": "color-mix(in srgb, #B42318 8%, #fff)",
        "danger-border": "#B42318",
    }


def build_css(brand: dict[str, Any], wrapper_class: str) -> str:
    """Build the article CSS from brand config dict.

    `brand` must contain `colors` and `typography` (matches brand-config.schema.json).
    `colors.surface_mode` ("light"|"dark", default "light") selects the palette.
    """
    colors = brand.get("colors", {})
    typo = brand.get("typography", {})
    # Accept BOTH nested colors.{primary,...} (canonical, 5/6 projects) AND the flat
    # primary_color/secondary_color/accent_color that /init's setup_wizard writes
    # (loamwright). The split silently fell back to the #0F3D2E default instead of the
    # real brand teal — the same flat/nested mismatch that greyed the charts (2026-06-29).
    primary = colors.get("primary") or brand.get("primary_color") or "#0F3D2E"
    secondary = colors.get("secondary") or brand.get("secondary_color") or "#B91C5C"
    accent = colors.get("accent") or brand.get("accent_color") or "#D4A574"
    mode = str(colors.get("surface_mode", brand.get("surface_mode", "light"))).lower()
    if mode not in ("light", "dark"):
        mode = "light"
    # Accept every font-key shape real projects use: canonical typography.{heading,body}_font,
    # project-juliet's typography.{heading,body}_family, and project-kilo/project-hotel's top-level
    # `fonts:` block. Without this, regenerating those projects silently reset fonts to Manrope/Inter.
    fonts = brand.get("fonts", {})
    heading_font = (typo.get("heading_font") or typo.get("heading_family") or typo.get("heading")
                    or fonts.get("heading") or fonts.get("heading_font") or "Manrope")
    body_font = (typo.get("body_font") or typo.get("body_family") or typo.get("body")
                 or fonts.get("body") or fonts.get("body_font") or "Inter")
    # CSS-safe: a full pre-quoted stack is emitted verbatim; a bare name is quoted (BUG 2).
    heading_css = _css_font(heading_font)
    body_css = _css_font(body_font)

    sel = f".{wrapper_class}"
    pal = _palette(mode, primary, secondary, accent)
    tokens = "\n".join(f"  --xr-{k}: {v};" for k, v in pal.items())

    css = f"""/*
 * Article CSS — generated by scripts/build/article_css_generator.py
 * Project slug: {brand.get('site_slug','?')}
 * Wrapper class: .{wrapper_class}
 * Surface mode: {mode}
 * Brand colors: primary={primary} | secondary={secondary} | accent={accent}
 * Brand fonts: heading={heading_font} | body={body_font}
 *
 * Scoped to .{wrapper_class}. Safe to inject inline via <style> in post body.
 * Compatible with Woodmart, Astra, Kadence, GeneratePress and other modern WP themes.
 */

{sel} {{
  /* ── Semantic tokens (surface_mode={mode}) ────────────────────── */
{tokens}

  /* ── Typography ────────────────────────────────────────────── */
  font-family: {body_css}, -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  color: var(--xr-text);
  font-size: 17px;
  line-height: 1.72;
  max-width: 760px;
  margin: 0 auto;
  word-wrap: break-word;
}}

{sel} p {{ margin: 0 0 1.15em; }}

{sel} h1, {sel} h2, {sel} h3, {sel} h4 {{
  font-family: {heading_css}, {body_css}, -apple-system, system-ui, sans-serif;
  font-weight: 700;
  color: var(--xr-heading);
  letter-spacing: -0.012em;
  line-height: 1.28;
  margin-top: 0;
}}

{sel} h2 {{
  font-size: 1.65em;
  margin: 2.4em 0 0.7em;
  padding-bottom: 0.45em;
  border-bottom: 2px solid var(--xr-rule);
  position: relative;
}}
{sel} h2::after {{
  content: "";
  position: absolute;
  bottom: -2px;
  left: 0;
  width: 64px;
  height: 2px;
  background: var(--xr-accent-bar);
}}
{sel} h3 {{
  font-size: 1.2em;
  margin: 1.7em 0 0.55em;
  color: var(--xr-heading-2);
}}
{sel} h4 {{
  font-size: 1.05em;
  margin: 1.4em 0 0.45em;
  color: var(--xr-heading-2);
}}

/* ── Abstract callout ─────────────────────────────────────────── */
{sel} h2#abstract + p,
{sel} h2#abstract + p + p {{
  background: var(--xr-card);
  border-left: 4px solid var(--xr-rule);
  padding: 1.25em 1.6em;
  border-radius: 0 6px 6px 0;
  font-size: 1.03em;
  line-height: 1.78;
}}
{sel} h2#abstract + p {{ margin-bottom: 1em; }}
{sel} h2#abstract + p + p {{ margin-top: 0; }}

/* ── Key Takeaways: bordered card list ────────────────────────── */
{sel} h2#key-takeaways + ul {{
  list-style: none;
  padding: 0;
  margin: 1em 0 2em;
}}
{sel} h2#key-takeaways + ul li {{
  position: relative;
  padding: 0.85em 1em 0.85em 2.4em;
  background: var(--xr-card-kt);
  border-left: 3px solid var(--xr-accent);
  margin-bottom: 0.45em;
  border-radius: 0 4px 4px 0;
  line-height: 1.6;
}}
{sel} h2#key-takeaways + ul li::before {{
  content: "\\25B8";
  position: absolute;
  left: 0.95em;
  top: 0.85em;
  color: var(--xr-marker-ol);
  font-weight: 700;
}}
{sel} h2#key-takeaways + ul li strong:first-child {{
  display: inline;
  color: var(--xr-strong);
  font-weight: 600;
}}

/* ── Table of Contents ───────────────────────────────────────── */
{sel} h2#table-of-contents + ol {{
  background: var(--xr-card-toc);
  border: 1px solid var(--xr-border);
  border-radius: 8px;
  padding: 1.3em 1.6em 1.3em 3em;
  font-size: 0.96em;
  line-height: 1.85;
  margin-bottom: 1.5em;
}}
@media (min-width: 720px) {{
  {sel} h2#table-of-contents + ol {{
    column-count: 2;
    column-gap: 2.5em;
  }}
  {sel} h2#table-of-contents + ol li {{ break-inside: avoid; }}
}}
{sel} h2#table-of-contents + ol a {{
  color: var(--xr-heading-2);
  border-bottom: 0;
  font-weight: 500;
}}
{sel} h2#table-of-contents + ol a:hover {{ color: var(--xr-link); }}

/* ── Tables ──────────────────────────────────────────────────── */
{sel} table {{
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  background: var(--xr-table-bg);
  font-size: 0.93em;
  border: 1px solid var(--xr-border);
  border-radius: 8px;
  overflow: hidden;
  margin: 1.6em 0 1.8em;
}}
{sel} table thead th {{
  background: var(--xr-thead-bg);
  color: var(--xr-thead-fg);
  text-align: left;
  padding: 0.8em 0.95em;
  font-weight: 600;
  font-family: {heading_css}, sans-serif;
  letter-spacing: 0.005em;
  border: 0;
  vertical-align: middle;
}}
{sel} table tbody td {{
  padding: 0.7em 0.95em;
  border-top: 1px solid var(--xr-border-soft);
  vertical-align: top;
  line-height: 1.55;
}}
{sel} table tbody tr:nth-child(even) td {{ background: var(--xr-table-stripe); }}
{sel} table tbody tr:hover td {{ background: var(--xr-table-hover); }}
{sel} table strong {{ color: var(--xr-strong); }}
@media (max-width: 760px) {{
  {sel} table {{
    display: block;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }}
}}

/* ── Figures + captions ──────────────────────────────────────── */
{sel} figure.wp-block-image {{ margin: 2.2em 0; }}
{sel} figure.wp-block-image img {{
  border-radius: 10px;
  box-shadow: 0 6px 28px color-mix(in srgb, var(--xr-primary) 14%, transparent);
  width: 100%;
  height: auto;
  display: block;
}}
{sel} figcaption,
{sel} figcaption.wp-element-caption {{
  font-size: 0.88em;
  color: var(--xr-text-muted);
  text-align: center;
  margin-top: 0.8em;
  font-style: italic;
  line-height: 1.55;
  padding: 0 1em;
}}

/* ── Inline emphasis ─────────────────────────────────────────── */
{sel} strong {{ color: var(--xr-strong); font-weight: 600; }}
{sel} em {{ font-style: italic; color: var(--xr-em); }}
{sel} code {{
  background: var(--xr-code-bg);
  padding: 0.12em 0.4em;
  border-radius: 3px;
  font-size: 0.92em;
  color: var(--xr-strong);
  font-family: ui-monospace, 'SF Mono', Menlo, Monaco, 'Cascadia Mono', monospace;
}}

/* ── Blockquote ──────────────────────────────────────────────── */
{sel} blockquote {{
  background: var(--xr-card-quote);
  border-left: 4px solid var(--xr-accent);
  padding: 1.2em 1.55em;
  margin: 1.7em 0;
  font-size: 1em;
  color: var(--xr-text);
  border-radius: 0 8px 8px 0;
}}
{sel} blockquote p:last-child {{ margin-bottom: 0; }}
{sel} blockquote strong:first-child {{
  color: var(--xr-strong);
  font-weight: 700;
  font-size: 1.02em;
}}

/* ── Links ───────────────────────────────────────────────────── */
{sel} a {{
  color: var(--xr-link);
  text-decoration: none;
  border-bottom: 1px solid var(--xr-link-border);
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
  word-break: break-word;
}}
{sel} a:hover {{
  color: var(--xr-link);
  border-bottom-color: var(--xr-link);
  background: var(--xr-link-hover-bg);
}}
{sel} h2 a, {sel} h3 a {{ color: inherit; border-bottom: 0; }}

/* ── Horizontal rules ────────────────────────────────────────── */
{sel} hr {{
  border: 0;
  height: 1px;
  background: linear-gradient(to right, transparent, var(--xr-hr), transparent);
  margin: 2.8em 0;
}}

/* ── Lists ───────────────────────────────────────────────────── */
{sel} ul, {sel} ol {{ margin: 0.6em 0 1.3em; padding-left: 1.6em; }}
{sel} ul li, {sel} ol li {{ margin-bottom: 0.4em; }}
{sel} ul li::marker {{ color: var(--xr-marker); }}
{sel} ol li::marker {{ color: var(--xr-marker-ol); font-weight: 600; }}

/* ── References ──────────────────────────────────────────────── */
{sel} h2#references + ol {{
  font-size: 0.9em;
  color: var(--xr-text-muted);
  padding-left: 1.6em;
  line-height: 1.6;
}}
{sel} h2#references + ol li {{ margin-bottom: 0.8em; }}
{sel} h2#references + ol li a {{
  color: var(--xr-ref-link);
  border-bottom-color: var(--xr-ref-link-border);
  word-break: break-all;
}}

/* ── FAQ Q-as-bold (class-based — :only-child unreliable because it ignores text nodes) ─ */
{sel} p.faq-question {{
  margin-top: 1.4em;
  margin-bottom: 0.35em;
}}
{sel} p.faq-question strong {{
  font-size: 1.05em;
  color: var(--xr-strong);
  font-weight: 700;
}}

/* ── Final signature (class-based — applied by publisher to last <em>-only paragraph) ─ */
{sel} p.article-signature {{
  text-align: center;
  font-size: 0.88em;
  color: var(--xr-text-muted);
  margin-top: 2.5em;
  padding-top: 1.5em;
  border-top: 1px solid var(--xr-border);
}}
{sel} p.article-signature em {{ font-style: normal; }}

/* ── By the Numbers: stat-card grid (markdown list rendered as cards) ─
   Primary binding = .xr-stat-grid class (publisher tags it via the shared
   scripts/_core/component_headings classifier — immune to anchor dedup,
   topic-scoped headings and localization). The [id^=…] attribute selectors are
   the legacy/no-retag fallback (2026-07-01; exact #ids left every stat grid of
   the 07-01 batch unstyled once dedup emitted #by-the-numbers-2).

   ⚠️ THE VALUE MUST NEVER CHOP MID-WORD (2026-07-14 root cure). The old rules
   were `minmax(150px, 1fr)` + a flat `font-size: 2em`, which left the value only
   ~110px of content box at ~34px type: about 5-6 characters. Every longer word
   overflowed, and because the pillar wrapper sets `word-wrap: break-word` (a
   deliberate long-URL guard) that overflow INHERITED IN and shattered the word:
   project-foxtrot shipped "chlorophyll" rendered as "chloroph / yll". A survey of 591
   posts found 107 of 365 stat values (29%) breaking this way across 8 projects.
   Four rules keep it safe at ANY column width, so the component degrades
   gracefully instead of shattering even when a writer over-stuffs the value:
     1. minmax 210px  -> a real "value + unit" actually fits
     2. clamp()       -> the value shrinks instead of overflowing
     3. word-break/overflow-wrap: normal + hyphens: manual
                      -> explicitly CANCELS the inherited break-word; the value
                         may wrap at spaces, never inside a word
     4. min-width: 0  -> grid blow-out guard (a long word must not widen the track)
   The content-side contract (bold = a SHORT numeric value, label goes unbolded)
   is enforced separately by scripts/lint/stat_grid_check.py. Do not "simplify"
   these rules away; both layers are load-bearing. */
{sel} ul.xr-stat-grid,
{sel} h2[id^="by-the-numbers"] + ul,
{sel} h2[id^="key-stats"] + ul {{
  list-style: none; padding: 0; margin: 1.2em 0 2em;
  display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 0.85em;
}}
{sel} ul.xr-stat-grid li,
{sel} h2[id^="by-the-numbers"] + ul li,
{sel} h2[id^="key-stats"] + ul li {{
  background: var(--xr-card); border: 1px solid var(--xr-border);
  border-top: 3px solid var(--xr-accent); border-radius: 8px;
  padding: 1.05em 1.1em; margin: 0; line-height: 1.42;
  font-size: 0.9em; color: var(--xr-text-muted);
  min-width: 0;
}}
{sel} ul.xr-stat-grid li::marker,
{sel} h2[id^="by-the-numbers"] + ul li::marker,
{sel} h2[id^="key-stats"] + ul li::marker {{ content: ""; }}
{sel} ul.xr-stat-grid li strong:first-child,
{sel} h2[id^="by-the-numbers"] + ul li strong:first-child,
{sel} h2[id^="key-stats"] + ul li strong:first-child {{
  display: block; font-family: {heading_css}, sans-serif;
  font-size: clamp(1.15rem, 0.55rem + 1.6vw, 1.75rem);
  line-height: 1.12; color: var(--xr-heading);
  font-weight: 800; margin-bottom: 0.2em; letter-spacing: -0.02em;
  overflow-wrap: normal; word-break: normal; word-wrap: normal; hyphens: manual;
  text-wrap: balance;
}}

/* ── TL;DR / bottom-line highlight box (accent-tint, bolder than abstract) ─ */
{sel} p.xr-tldr-box,
{sel} h2[id^="tldr"] + p,
{sel} h2#in-short + p,
{sel} h2#the-bottom-line + p {{
  background: var(--xr-card-kt); border-left: 5px solid var(--xr-accent);
  border-radius: 0 8px 8px 0; padding: 1.15em 1.5em; margin: 1em 0 2em;
  font-size: 1.06em; line-height: 1.7; color: var(--xr-text); font-weight: 500;
}}

/* ── At a Glance: emphasized comparison table (accent header + bold first column) ─
   [id$=…] also binds variant phrasings like "This Week at a Glance" (digest). */
{sel} table.xr-glance-table thead th,
{sel} h2[id^="at-a-glance"] + table thead th,
{sel} h2[id$="at-a-glance"] + table thead th {{ background: var(--xr-accent); color: var(--xr-on-accent); }}
{sel} table.xr-glance-table tbody td:first-child,
{sel} h2[id^="at-a-glance"] + table tbody td:first-child,
{sel} h2[id$="at-a-glance"] + table tbody td:first-child {{
  font-weight: 700; color: var(--xr-strong);
  background: var(--xr-card-kt); border-right: 1px solid var(--xr-border);
}}

/* ── Glossary / definition cards (markdown list rendered as cards) ─ */
{sel} ul.xr-glossary-list,
{sel} h2[id^="glossary"] + ul {{ list-style: none; padding: 0; margin: 1.2em 0 2em; }}
{sel} ul.xr-glossary-list li,
{sel} h2[id^="glossary"] + ul li {{
  padding: 0.7em 1em 0.7em 1.1em; margin-bottom: 0.5em;
  background: var(--xr-card-toc); border: 1px solid var(--xr-border);
  border-left: 3px solid var(--xr-accent); border-radius: 0 6px 6px 0; line-height: 1.55;
}}
{sel} ul.xr-glossary-list li::marker,
{sel} h2[id^="glossary"] + ul li::marker {{ content: ""; }}
{sel} ul.xr-glossary-list li strong:first-child,
{sel} h2[id^="glossary"] + ul li strong:first-child {{ color: var(--xr-strong); font-weight: 700; }}

/* ── Checklist card list (F4 fix: was weighted + playbooked but never styled) ─ */
{sel} ul.xr-checklist, {sel} ol.xr-checklist {{ list-style: none; padding: 0; margin: 1.2em 0 2em; }}
{sel} ul.xr-checklist li, {sel} ol.xr-checklist li {{
  padding: 0.65em 1em 0.65em 2.3em; margin-bottom: 0.5em; position: relative;
  background: var(--xr-card); border: 1px solid var(--xr-border);
  border-radius: 6px; line-height: 1.55;
}}
{sel} ul.xr-checklist li::marker, {sel} ol.xr-checklist li::marker {{ content: ""; }}
{sel} ul.xr-checklist li::before, {sel} ol.xr-checklist li::before {{
  content: "\\2713"; position: absolute; left: 0.85em; top: 0.62em;
  color: var(--xr-accent); font-weight: 800;
}}

/* ── CTA module (v3.37 — injected by scripts/optimize/cta_injector.py from
   either cta-draft.json (LLM-authored, per-article) or the legacy static
   cta.variants config; publisher tags the paragraph after the CTA heading
   with .xr-cta-box (+ .xr-cta-quiet or .xr-cta-banner) via the shared
   component_headings classifier). Deliberately calmer than an ad banner for
   the base card skin — banner blindness is a measured failure — but the
   button itself must read as unmistakably clickable. ─ */
{sel} p.xr-cta-box {{
  background: linear-gradient(135deg, var(--xr-card-kt), transparent 140%);
  border: 1px solid var(--xr-border);
  border-left: 5px solid var(--xr-accent);
  border-radius: 10px;
  padding: 1.3em 1.55em;
  margin: 1em 0 2.4em;
  font-size: 1.03em;
  line-height: 1.68;
  position: relative;
  overflow: hidden;
}}
{sel} p.xr-cta-box strong:first-child {{
  display: block;
  font-family: {heading_css}, sans-serif;
  font-size: 1.12em;
  color: var(--xr-heading);
  margin-bottom: 0.3em;
}}
{sel} p.xr-cta-box img {{
  float: left;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  object-fit: cover;
  margin: 0 0.8em 0.4em 0;
  border: 2px solid var(--xr-bg, #fff);
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}}
{sel} p.xr-cta-box a {{
  display: inline-flex;
  align-items: center;
  gap: 0.4em;
  font-weight: 700;
  font-size: 0.97em;
  background: var(--xr-accent);
  color: var(--xr-on-accent, #fff);
  padding: 0.62em 1.15em;
  border-radius: 8px;
  text-decoration: none;
  margin-top: 0.35em;
  transition: transform 150ms ease, box-shadow 150ms ease;
}}
{sel} p.xr-cta-box a:hover {{
  transform: translateY(-1px);
  box-shadow: 0 6px 14px rgba(0,0,0,0.18);
}}
/* Quiet skin: editorial/quote-hook variant, outline button not filled. */
{sel} p.xr-cta-box.xr-cta-quiet {{
  background: transparent;
  border: none;
  border-top: 3px solid var(--xr-heading);
  border-bottom: 3px solid var(--xr-heading);
  border-radius: 0;
  text-align: center;
  padding: 1.4em 0.6em;
}}
{sel} p.xr-cta-box.xr-cta-quiet a {{
  background: transparent;
  color: var(--xr-heading);
  border: 2px solid var(--xr-heading);
}}
/* Banner skin: full-width dark strip, used only at the 'end' placement. */
{sel} p.xr-cta-box.xr-cta-banner {{
  background: var(--xr-heading);
  border: none;
  border-radius: 8px;
  color: #fff;
  padding: 1.1em 1.4em;
}}
{sel} p.xr-cta-box.xr-cta-banner strong:first-child {{
  color: #fff;
}}
{sel} p.xr-cta-box.xr-cta-banner a {{
  background: var(--xr-accent);
}}
/* Couple the CTA heading to its card where :has() is available (graceful:
   without :has() the heading renders as a normal h3 above the card). */
{sel} h3:has(+ p.xr-cta-box) {{
  color: var(--xr-heading);
  margin: 2.6em 0 0.5em;
}}

/* ── Typed callout boxes (publisher tags a blockquote by its leading bold label) ─ */
{sel} blockquote.callout {{ border-radius: 8px; padding: 1.1em 1.35em; }}
{sel} blockquote.callout-note {{ background: var(--xr-card); border-left: 4px solid var(--xr-border); }}
{sel} blockquote.callout-info {{ background: var(--xr-card-toc); border-left: 4px solid var(--xr-link); }}
{sel} blockquote.callout-tip {{ background: var(--xr-card-kt); border-left: 4px solid var(--xr-accent); }}
{sel} blockquote.callout-warning {{ background: var(--xr-warn-bg); border-left: 4px solid var(--xr-warn-border); }}
{sel} blockquote.callout-warning strong:first-child {{ color: var(--xr-warn-border); }}
{sel} blockquote.callout-danger {{ background: var(--xr-danger-bg); border-left: 4px solid var(--xr-danger-border); }}
{sel} blockquote.callout-danger strong:first-child {{ color: var(--xr-danger-border); }}

/* ── Pull-quote (publisher tags a quote-marked blockquote; decorative, use sparingly) ─ */
{sel} blockquote.pull-quote {{
  background: none; border: 0; border-left: 0; text-align: center;
  font-family: {heading_css}, serif; font-size: 1.5em; line-height: 1.4;
  color: var(--xr-heading); max-width: 90%; margin: 2.2em auto; padding: 0.2em 1em;
  position: relative; font-weight: 600;
}}
{sel} blockquote.pull-quote::before {{
  content: "\\201C"; font-size: 2.4em; color: var(--xr-accent);
  display: block; line-height: 0.6; margin-bottom: 0.1em;
}}

/* ── Accessibility (2026-07-01): visible keyboard focus + reduced motion ─ */
{sel} a:focus-visible {{
  outline: 2px solid var(--xr-accent); outline-offset: 2px; border-radius: 2px;
}}
@media (prefers-reduced-motion: reduce) {{
  {sel} *, {sel} *::before, {sel} *::after {{
    transition-duration: 0.01ms !important; animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important; scroll-behavior: auto !important;
  }}
}}

/* ── Mobile ──────────────────────────────────────────────────── */
@media (max-width: 720px) {{
  {sel} ul.xr-stat-grid, {sel} h2[id^="by-the-numbers"] + ul, {sel} h2[id^="key-stats"] + ul {{ grid-template-columns: repeat(auto-fit, minmax(165px, 1fr)); gap: 0.6em; }}
  {sel} blockquote.pull-quote {{ font-size: 1.25em; }}
  {sel} {{ font-size: 16px; padding: 0 4px; }}
  {sel} h2 {{ font-size: 1.4em; margin: 2em 0 0.6em; }}
  {sel} h3 {{ font-size: 1.12em; }}
  {sel} h2#abstract + p,
  {sel} h2#abstract + p + p,
  {sel} p.xr-cta-box,
  {sel} blockquote {{ padding: 1em 1.1em; }}
  {sel} p.xr-cta-box img {{ float: none; display: block; margin: 0 0 0.6em; }}
  {sel} p.xr-cta-box a {{ width: 100%; justify-content: center; }}
  {sel} h2#key-takeaways + ul li {{ padding-left: 2.2em; }}
  {sel} h2#table-of-contents + ol {{ padding: 1em 1.2em 1em 2.5em; }}
  {sel} table {{ font-size: 0.86em; }}
  {sel} table thead th,
  {sel} table tbody td {{ padding: 0.6em 0.75em; }}
}}

/* ── Print ───────────────────────────────────────────────────── */
@media print {{
  {sel} {{ color: #000; font-size: 11pt; max-width: none; }}
  {sel} h1, {sel} h2, {sel} h3, {sel} h4 {{ color: #000; }}
  {sel} a {{ color: #000; border-bottom: 0; }}
  {sel} a::after {{ content: " (" attr(href) ")"; font-size: 0.85em; color: #555; }}
  {sel} figure.wp-block-image img {{ box-shadow: none; }}
  {sel} table {{ font-size: 9pt; }}
  {sel} table thead th {{ background: #eee; color: #000; }}
  {sel} h2#abstract + p, {sel} h2#abstract + p + p,
  {sel} h2#key-takeaways + ul li, {sel} blockquote,
  {sel} h2#table-of-contents + ol, {sel} table tbody td {{ background: #fff; color: #000; }}
}}
"""

    if mode == "dark":
        # The post <title> (H1) is rendered by the THEME, outside .{wrapper_class}, in a
        # near-black page-title bar. On a dark theme it inherits a faint default color and
        # is unreadable. This non-scoped block ships inside the post-body <style>, so it only
        # affects THIS post's single page. Forces the theme title to a legible light color.
        css += f"""
/* ── Single-post title legibility (theme-rendered, outside .{wrapper_class}) ─ */
.single-post .entry-title,
.single-post .wd-page-title-content .title,
.single-post .wd-page-title .title,
.single .wd-entities-title,
.single h1.entry-title,
.single .page-title {{
  color: #F5F5F0 !important;
}}
.single-post .wd-page-title-content .wd-page-subtitle,
.single-post .wd-page-title-content .breadcrumbs,
.single-post .wd-page-title-content .breadcrumbs * {{
  color: #B7B8BE !important;
}}
"""
    return css


def minify_css(css: str) -> str:
    """Lightly minify CSS (strip comments, collapse whitespace)."""
    import re
    # Strip /* ... */ comments
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    # Collapse multiple whitespace
    css = re.sub(r"\s+", " ", css).strip()
    return css


def generate(slug: str, output: Path | None = None, minified_too: bool = True) -> dict[str, Any]:
    """Generate article CSS for a project. Returns paths and sizes."""
    project_dir, brand_cfg, default_out = _project_paths(slug)
    if not brand_cfg.exists():
        raise FileNotFoundError(
            f"brand-config.json not found at {brand_cfg}. "
            f"Run /init for project '{slug}' first."
        )
    brand = json.loads(brand_cfg.read_text(encoding="utf-8"))
    wrapper = _slug_class(slug)
    css = build_css(brand, wrapper)

    out = output or default_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(css, encoding="utf-8")

    result = {
        "slug": slug,
        "wrapper_class": wrapper,
        "surface_mode": str(brand.get("colors", {}).get("surface_mode", "light")).lower(),
        "css_path": str(out),
        "css_size_bytes": out.stat().st_size,
    }
    if minified_too:
        min_path = out.with_suffix(".min.css")
        minified = minify_css(css)
        min_path.write_text(minified, encoding="utf-8")
        result["min_path"] = str(min_path)
        result["min_size_bytes"] = min_path.stat().st_size
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("slug", help="Project slug under projects/")
    ap.add_argument("-o", "--output", type=Path, help="Output CSS path (default: projects/{slug}/brand/article-css.css)")
    ap.add_argument("--no-minified", action="store_true", help="Skip generating .min.css companion")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON result")
    args = ap.parse_args()

    try:
        result = generate(args.slug, output=args.output, minified_too=not args.no_minified)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"OK: article CSS generated for '{result['slug']}'")
        print(f"  wrapper class: .{result['wrapper_class']}")
        print(f"  surface mode:  {result['surface_mode']}")
        print(f"  CSS:        {result['css_path']} ({result['css_size_bytes']:,} bytes)")
        if "min_path" in result:
            print(f"  Minified:   {result['min_path']} ({result['min_size_bytes']:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
