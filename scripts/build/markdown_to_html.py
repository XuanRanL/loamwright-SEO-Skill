"""
scripts/build/markdown_to_html.py — Markdown → Plain HTML for WordPress / any CMS.

Design goals:
  1. Output is **plain HTML** — clean semantic tags, no markdown leakage
  2. WordPress-friendly:
       - H2/H3 get id="..." for ToC anchor links
       - Tables → proper <table><thead><tbody>
       - Images use <img> with alt + (optional) srcset + loading="lazy"
       - No <!DOCTYPE> / <html> / <body> wrapper (it's INSERT INTO post body)
       - Strips frontmatter (those become Yoast meta, not body content)
       - Optionally strips H1 (WP has separate title field)
  3. Image src placeholders: support `[IMAGE-SLOT-N]` and `![alt](placeholder://slot-N)`
     to be replaced post-upload with real Media Library URLs.
  4. Gutenberg block mode optional — wraps content in <!-- wp:html --> blocks.
  5. Both pretty and minified output modes.

Library: markdown-it-py (CommonMark + GFM tables / strikethrough — NO task-lists
  plugin: `- [ ]` renders as literal "[ ]" text; render_lint L13 vetoes it)

Used by:
  - phase-publish stage (final.html for WordPress upload)
  - user-facing copy-paste workflow (final.html for any CMS)
  - integration test fixtures

Usage:
    from scripts.build.markdown_to_html import convert, ConvertOptions

    html = convert(markdown_text, options=ConvertOptions(
        drop_h1=True,
        add_anchor_ids=True,
        wordpress_gutenberg=False,
    ))

    # CLI
    python -m scripts.build.markdown_to_html draft.md -o final.html
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# ─── Scaffold-marker strip (canonical, single source of truth) ─────
#
# Writer subagent prompts instruct authors to annotate sections that carry
# original data / unique insight / personal experience so fact-checker and
# reviewer can score info-gain. Those tokens are author-internal and must NEVER
# reach rendered HTML. assemble.py strips them at assembly time, but the
# optimize-phase subagents (humanizer / geo-auditor) edit the draft AFTER
# assembly and re-introduce them, which used to hard-fail the render-lint L6 gate
# and require a manual strip + re-run (2026-06-18 fix A).
#
# This regex is the ONE source of truth. It MUST stay in sync with
# render_lint._SCAFFOLD_MARKER_LEAK_RE (the L6 detector token set). Importers:
#   - scripts/wordpress/wp_publisher.py  (strips in the publish path)
#   - scripts/lint/render_lint.py        (pre-strips in memory before linting)
#   - scripts/build/assemble.py          (strips at assembly)
SCAFFOLD_MARKER_RE = re.compile(
    r"[ \t]*\[(?:ORIGINAL DATA|UNIQUE INSIGHT|PERSONAL EXPERIENCE|CAPSULE"
    r"|EXAMPLE|CITATION CAPSULE|INFO GAIN)\][ \t]*"
)


def strip_scaffold_markers(text: str) -> tuple[str, int]:
    """Remove writer-side scaffold annotation tokens from markdown/text.

    Returns (cleaned_text, count_removed). Surrounding spaces are collapsed to a
    single space so the prose reads naturally. Case-sensitive (tokens are emitted
    upper-case) to match the L6 detector exactly.
    """
    cleaned, n = SCAFFOLD_MARKER_RE.subn(" ", text)
    return cleaned, n


# ─── Configuration ────────────────────────────────────────────────

@dataclass
class ConvertOptions:
    drop_h1: bool = True
    """If True (default), strip the top-level H1 (WordPress sets title separately)."""

    add_anchor_ids: bool = True
    """Add id='heading-slug' to all H2/H3 for ToC anchor links."""

    wordpress_gutenberg: bool = False
    """If True, wrap output in <!-- wp:html --> ... <!-- /wp:html -->. Otherwise plain HTML."""

    image_srcset: bool = False
    """Emit hand-rolled srcset attribute on <img>.

    DEFAULT: False (changed 2026-05-21 — see [[feedback_markdown_pitfalls_publisher_three_bugs]]).
    The previous default True emitted URLs for {basename}-480w/-768w/-1024w variants that no
    code in this pipeline ever generates — every URL 404s, breaking images on mobile viewports.
    With this flag False, WordPress's wp_image_add_srcset_and_sizes() filter regenerates
    srcset at render time from the standard WP-registered sizes (300x300, 768x768, etc.) which
    actually exist on disk. Re-enable only when an upstream image-post-processor is built that
    actually creates the -480w/-768w/-1024w derivative files."""

    image_lazy_loading: bool = True
    """Add loading='lazy' attribute to <img>."""

    pretty: bool = True
    """Output indented HTML. False = minified."""

    strip_frontmatter: bool = True
    """Drop YAML frontmatter block."""

    add_class_attr: dict[str, str] = field(default_factory=dict)
    """Optional class attributes per element, e.g. {'table': 'wp-block-table', 'blockquote': 'wp-block-quote'}"""

    target_blank_external_links: bool = True
    """Add target='_blank' rel='noopener nofollow' to external (non-anchor) links."""

    site_url: str | None = None
    """If set, links to this domain are kept internal (not target=_blank)."""

    image_url_resolver: Any = None
    """Optional callable (placeholder_str) -> real_url. Used to replace [IMAGE-SLOT-N] placeholders."""


# ─── Frontmatter handling ─────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_markdown)."""
    # Strip UTF-8 BOM if present — Windows editors and Write tools may prepend
    # U+FEFF which breaks the ^--- anchor, causing the entire frontmatter to
    # leak into the rendered article body as visible text.
    if text.startswith('﻿'):
        text = text[1:]
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_text = m.group(1)
    body = text[m.end():]
    try:
        import yaml
        fm = yaml.safe_load(fm_text) or {}
        if not isinstance(fm, dict):
            fm = {}
    except ImportError:
        fm = {}
        for line in fm_text.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, body


# ─── Slug helper for anchor IDs ───────────────────────────────────

# Transliterate common scientific / typographic symbols to ASCII so anchor slugs
# never contain non-ASCII. A raw "µ" survives as the literal char in a rendered
# <h2 id="…µ…"> but is percent-encoded to %C2%B5 inside the TOC <a href> — the two
# then mismatch (render_lint L10 / the 2026-06-04 ferns+seed-starting incident).
# ASCII-only slugs eliminate that entire class. Keep this map in sync with the
# identical one in anchor_link_builder._slug.
_ANCHOR_TRANSLIT = str.maketrans({
    "µ": "u", "μ": "u", "²": "2", "³": "3", "°": "", "×": "x", "÷": "",
    "–": "-", "—": "-", "’": "", "‘": "", "“": "", "”": "",
})


def slugify(text: str) -> str:
    """ASCII slug for anchor IDs. Handles common punctuation and non-ASCII symbols."""
    s = text.lower().strip()
    # Remove markdown bold/italic
    s = re.sub(r"\*+", "", s)
    s = re.sub(r"_+", "", s)
    s = re.sub(r"`+", "", s)
    # Transliterate common symbols, then drop ALL remaining non-ASCII so the
    # rendered heading id always equals the TOC href.
    s = s.translate(_ANCHOR_TRANSLIT)
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    # Whitespace → hyphen
    s = re.sub(r"\s+", "-", s)
    # Collapse multiple hyphens
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    # Cap length but cut on a word (hyphen) boundary so anchors never slice
    # mid-syllable (e.g. '...-for-all-9-com'). Both the heading id and the TOC
    # href run through this same function, so they stay identical either way.
    if len(s) <= 80:
        return s
    cut = s[:80]
    if "-" in cut:
        cut = cut.rsplit("-", 1)[0]
    return cut.strip("-")


# ─── Conversion ───────────────────────────────────────────────────

def convert(text: str, options: ConvertOptions | None = None) -> str:
    """Convert markdown text to plain HTML.

    Args:
        text: Markdown source.
        options: Conversion options. Defaults reasonable for WordPress.

    Returns:
        HTML string. No `<html>` / `<body>` wrapper.
    """
    opt = options or ConvertOptions()

    # Frontmatter strip
    if opt.strip_frontmatter:
        _, body = split_frontmatter(text)
    else:
        body = text

    # Use markdown-it-py with GFM-style enabled
    try:
        from markdown_it import MarkdownIt
        from markdown_it.rules_block import StateBlock
    except ImportError as e:
        raise RuntimeError(
            "markdown-it-py required: pip install markdown-it-py"
        ) from e

    md = MarkdownIt("gfm-like", {"breaks": False, "html": False, "linkify": True, "typographer": False})
    # Enable additional features
    md.enable(["table", "strikethrough"])

    html = md.render(body)

    # Post-process
    if opt.drop_h1:
        html = _drop_h1(html)

    if opt.add_anchor_ids:
        html = _add_anchor_ids(html)

    if opt.image_lazy_loading or opt.image_srcset or opt.image_url_resolver:
        html = _process_images(html, opt)

    if opt.target_blank_external_links:
        html = _process_links(html, opt)

    if opt.add_class_attr:
        html = _add_classes(html, opt.add_class_attr)

    # Clean up empty paragraphs and trim
    html = _cleanup(html)

    if opt.wordpress_gutenberg:
        html = _wrap_gutenberg(html)

    if opt.pretty:
        html = _prettify(html)

    return html


# ─── Post-processors ──────────────────────────────────────────────

def _drop_h1(html: str) -> str:
    """Remove the FIRST <h1>...</h1> block (assumed to be the title)."""
    return re.sub(r"<h1[^>]*>.*?</h1>\s*", "", html, count=1, flags=re.DOTALL)


_PANDOC_TRAILING_ANCHOR_RE = re.compile(r'\s*\{#([a-zA-Z0-9_-]+)\}\s*$')
"""Pandoc / Kramdown-style trailing heading anchor: '## Title {#anchor-id}'.

Base markdown-it-py does not parse this syntax — without intervention, the literal
'{#anchor-id}' survives as visible text inside the heading. We strip it here BEFORE
generating the auto-anchor, and use the explicit author-provided slug if present.

See [[feedback_markdown_pitfalls_publisher_three_bugs]] (2026-05-21)."""


def _add_anchor_ids(html: str) -> str:
    """Inject id="..." into H2/H3 tags from explicit Pandoc {#anchor} or auto-slugify.

    Resolution order:
      1. If the heading already has id="…" in attrs, leave it alone.
      2. If the heading text ends with '{#author-slug}', strip the marker and use it as id.
      3. Otherwise, slugify the cleaned heading text.
    """
    def add_id(m: re.Match) -> str:
        tag = m.group(1)
        attrs = m.group(2) or ""
        content = m.group(3)
        if 'id=' in attrs:
            return m.group(0)
        # Strip any HTML tags inside the heading content for slug purposes
        text = re.sub(r"<[^>]+>", "", content)
        # Detect explicit Pandoc {#anchor} at end of heading text
        pandoc_m = _PANDOC_TRAILING_ANCHOR_RE.search(text)
        explicit_anchor = pandoc_m.group(1) if pandoc_m else None
        if pandoc_m:
            text = _PANDOC_TRAILING_ANCHOR_RE.sub('', text).rstrip()
            # Remove the same marker from rendered content so it doesn't print
            content = _PANDOC_TRAILING_ANCHOR_RE.sub('', content).rstrip()
        anchor = explicit_anchor or slugify(text)
        if not anchor:
            return m.group(0)
        new_attrs = (attrs.rstrip() + f' id="{anchor}"').strip()
        return f"<{tag} {new_attrs}>{content}</{tag}>"

    html = re.sub(
        r"<(h[23])(\s+[^>]*)?>(.+?)</\1>",
        add_id, html, flags=re.DOTALL,
    )
    return html


def _process_images(html: str, opt: ConvertOptions) -> str:
    """Process <img> tags: lazy load, srcset, placeholder URL resolution."""
    def transform(m: re.Match) -> str:
        full_tag = m.group(0)
        # Extract attributes
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', full_tag))

        src = attrs.get("src", "")
        alt = attrs.get("alt", "")

        # Resolve placeholder URLs
        if opt.image_url_resolver and src.startswith("placeholder://"):
            try:
                resolved = opt.image_url_resolver(src)
                if resolved:
                    src = resolved
                    attrs["src"] = resolved
            except Exception:
                pass

        # Build attribute list
        new_attrs = []
        new_attrs.append(f'src="{_html_escape(src)}"')
        if alt:
            new_attrs.append(f'alt="{_html_escape(alt)}"')
        if opt.image_lazy_loading and "loading" not in attrs:
            new_attrs.append('loading="lazy"')
        if opt.image_srcset and "srcset" not in attrs and not src.startswith("placeholder://"):
            # Auto-generate srcset from src basename
            sset = _build_srcset(src)
            if sset:
                new_attrs.append(f'srcset="{sset}"')
                new_attrs.append('sizes="(max-width: 768px) 100vw, 1024px"')
        # Preserve other attributes
        for k, v in attrs.items():
            if k in ("src", "alt", "loading", "srcset", "sizes"):
                continue
            new_attrs.append(f'{k}="{_html_escape(v)}"')
        return f"<img {' '.join(new_attrs)} />"

    return re.sub(r"<img\s+[^>]*/?>", transform, html)


def _build_srcset(src: str) -> str:
    """Build srcset from src URL by inferring width-variants.

    Convention: my-image.webp → my-image-480w.webp / my-image-768w.webp / etc.
    Used by image-post-processor which generates these variants.
    """
    # If src already has a width suffix, skip
    if re.search(r"-\d+w\.(webp|png|jpe?g)", src):
        return ""
    m = re.match(r"^(.+)\.(webp|png|jpe?g)$", src, re.IGNORECASE)
    if not m:
        return ""
    base, ext = m.group(1), m.group(2)
    return ", ".join([
        f"{base}-480w.{ext} 480w",
        f"{base}-768w.{ext} 768w",
        f"{base}-1024w.{ext} 1024w",
    ])


def _process_links(html: str, opt: ConvertOptions) -> str:
    """Add target='_blank' rel to external links (best-effort heuristic)."""
    def transform(m: re.Match) -> str:
        full = m.group(0)
        href = m.group(1)
        # Internal anchors: leave alone
        if href.startswith("#"):
            return full
        # Same-domain: keep internal
        if opt.site_url and opt.site_url in href:
            return full
        # External: add target/rel if not present
        if "target=" in full:
            return full
        # Insert before >
        return full[:-1] + ' target="_blank" rel="noopener nofollow">'

    return re.sub(r'<a\s+href="([^"]+)"[^>]*>', transform, html)


def _add_classes(html: str, class_map: dict[str, str]) -> str:
    """Inject class attribute into specified elements."""
    for tag, cls in class_map.items():
        pattern = re.compile(rf"<({tag})(\s+[^>]*)?>", re.IGNORECASE)
        def repl(m, _cls=cls):
            attrs = (m.group(2) or "").strip()
            if 'class=' in attrs:
                # Append to existing class
                return re.sub(r'class="([^"]*)"', rf'class="\1 {_cls}"', m.group(0))
            return f"<{m.group(1)} {attrs} class=\"{_cls}\">".replace("  ", " ")
        html = pattern.sub(repl, html)
    return html


def _cleanup(html: str) -> str:
    # Remove empty paragraphs
    html = re.sub(r"<p>\s*</p>\s*", "", html)
    # Collapse multiple blank lines
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def _wrap_gutenberg(html: str) -> str:
    """Wrap entire output in a single Gutenberg HTML block."""
    return f"<!-- wp:html -->\n{html}\n<!-- /wp:html -->"


def _prettify(html: str) -> str:
    """Indent HTML for readability (best-effort)."""
    # Simple line-break-after-tag-close for block tags
    block_tags = r"(h[1-6]|p|ul|ol|li|table|thead|tbody|tr|td|th|blockquote|pre|hr|div|figure|figcaption|section)"
    html = re.sub(rf"(</{block_tags}>)", r"\1\n", html)
    html = re.sub(rf"(<{block_tags}(?:\s[^>]*)?>)", r"\n\1", html)
    # Collapse runs
    html = re.sub(r"\n{2,}", "\n", html)
    return html.strip()


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


# ─── CLI ──────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Markdown → HTML converter")
    ap.add_argument("input", type=Path, help="Markdown input file")
    ap.add_argument("-o", "--output", type=Path, help="HTML output (default: stdout)")
    ap.add_argument("--keep-h1", action="store_true", help="Don't strip the H1")
    ap.add_argument("--no-anchors", action="store_true", help="Don't add id= to H2/H3")
    ap.add_argument("--gutenberg", action="store_true", help="Wrap in Gutenberg HTML block")
    ap.add_argument("--minify", action="store_true", help="Output minified HTML")
    ap.add_argument("--no-srcset", action="store_true", help="Don't auto-build srcset")
    ap.add_argument("--site-url", help="Your site URL (so internal links stay non-target=_blank)")
    ap.add_argument("--json", action="store_true", help="Output {html, frontmatter} JSON")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"Not found: {args.input}", file=sys.stderr)
        return 2

    text = args.input.read_text(encoding="utf-8")
    frontmatter, _ = split_frontmatter(text)

    opt = ConvertOptions(
        drop_h1=not args.keep_h1,
        add_anchor_ids=not args.no_anchors,
        wordpress_gutenberg=args.gutenberg,
        pretty=not args.minify,
        image_srcset=not args.no_srcset,
        site_url=args.site_url,
    )

    try:
        html = convert(text, opt)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        result = {"html": html, "frontmatter": frontmatter, "length_chars": len(html)}
        out = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        out = html

    if args.output:
        args.output.write_text(out, encoding="utf-8")
        print(f"Wrote {len(html)} chars to {args.output}", file=sys.stderr)
    else:
        print(out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
