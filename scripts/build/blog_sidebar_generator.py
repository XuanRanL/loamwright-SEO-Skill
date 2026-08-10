#!/usr/bin/env python3
"""Generate a project's blog sidebars (blog index + single post).

Emits two deployable artifacts under ``projects/{slug}/brand/``:

* ``blog-sidebars.php`` — a self-contained mu-plugin registering two widget
  areas and the widgets that fill them, with the project's config baked in
* ``blog-sidebars.css`` — the matching stylesheet, built from the project's
  brand palette and fonts

WHY AN MU-PLUGIN, NOT A THEME EDIT OR A SNIPPET
Registering sidebars and widgets has to happen before ``widgets_init`` fires.
mu-plugins load ahead of regular plugins, which guarantees that. It also
survives theme updates on the many fleet sites that run no child theme. The
2026-08-04 project-alpha deployment proved the alternative the hard way: the same
code as a WPCode Lite PHP snippet never executed at all, silently.

WHY THE CONFIG IS BAKED IN AT GENERATION TIME
The mu-plugin runs on the WordPress host, which has no access to this repo. So
the generator resolves everything from ``business-context.json`` here and writes
a literal ``$CONFIG`` array into the PHP. Re-run the generator to change it.

Usage
-----
    python -m scripts.build.blog_sidebar_generator {slug} [--json]
    python -m scripts.build.blog_sidebar_generator {slug} --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent


# --------------------------------------------------------------------------- #
# config resolution
# --------------------------------------------------------------------------- #

def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


DEFAULT_PALETTE = {
    "primary": "#1a3d1a",
    "accent": "#e86a10",
    "accent_dark": "#d45e0d",
    "surface": "#f4f7f4",
    "surface_2": "#e6ece7",
    "ink": "#1b1f1d",
    "muted": "#5b665f",
}


def _modules(configured: Any, default: list[str]) -> list[str]:
    """An explicitly empty module list means "none", not "give me the defaults"."""
    return list(configured) if isinstance(configured, list) else list(default)


def resolve_config(slug: str) -> dict[str, Any]:
    """Build the render config from the project's own files.

    Everything here degrades: a project with no brand-config still gets a
    working, if plainer, sidebar.
    """
    proj = PLUGIN_ROOT / "projects" / slug
    if not proj.is_dir():
        raise SystemExit(f"project not found: {proj}")

    bc = _load_json(proj / "business-context.json")
    brand_cfg = _load_json(proj / "brand" / "brand-config.json")
    brand_id = _load_json(proj / "brand" / "brand-identity.json")
    sidebars = bc.get("blog_sidebars") or {}

    # The kill switch has to be READ by something, or it is decoration. /init
    # Step 0b asks the operator whether this site wants custom sidebars and
    # records the answer here; the schema makes `enabled` required. Until v3.42.4
    # no executor consulted it, so answering "no" and then running the generator
    # produced sidebars anyway — Rule 6 (documentation is not an executor) inside
    # the very feature that shipped with it.
    if sidebars.get("enabled") is False:
        raise SystemExit(
            f"blog sidebars are disabled for {slug} "
            f"(business-context.json :: blog_sidebars.enabled = false). "
            f"Set it to true to opt this project in.")

    # ---- palette, least-specific source first so the more curated one wins:
    #        neutral default  <  brand-config.colors  <  brand-identity.brand_visuals
    #        <  blog_sidebars.palette (explicit operator override)
    #      brand-identity is written by /init Step 11.7 against the real site and
    #      names roles precisely (deep_green vs orange_accent); brand-config often
    #      carries a generic `primary` that is really the accent. Letting the
    #      generic key win produced orange headings on a green-headed brand.
    palette = dict(DEFAULT_PALETTE)
    for k, v in (brand_cfg.get("colors") or {}).items():
        if k in palette and isinstance(v, str) and v.startswith("#"):
            palette[k] = v

    visuals = brand_id.get("brand_visuals") or {}
    colors = visuals.get("colors") or {}
    for key, candidates in {
        "primary": ("deep_green", "primary", "brand_primary"),
        "accent": ("orange_accent", "accent", "brand_accent"),
        "accent_dark": ("orange_primary_dark", "accent_dark"),
    }.items():
        for c in candidates:
            if isinstance(colors.get(c), str) and colors[c].startswith("#"):
                palette[key] = colors[c]
                break
    surfaces = colors.get("mint_surfaces") or colors.get("surfaces") or []
    if isinstance(surfaces, list) and surfaces:
        palette["surface"] = surfaces[0]
        if len(surfaces) > 1:
            palette["surface_2"] = surfaces[1]

    palette.update({k: v for k, v in (sidebars.get("palette") or {}).items()
                    if isinstance(v, str) and v.startswith("#")})

    fonts = visuals.get("fonts") or {}
    heading_font = sidebars.get("heading_font") or fonts.get("heading") or "Georgia"
    body_font = sidebars.get("body_font") or fonts.get("body") or "inherit"

    site_url = (bc.get("site_url") or "").rstrip("/")

    # ---- product category for the promo module
    offers = bc.get("conversion_offers") or {}
    product_cat = (
        sidebars.get("product_category")
        or offers.get("default_category")
        or ""
    )
    # Categories that must never be merchandised from editorial content.
    excluded = list(offers.get("excluded_categories") or [])
    excluded += list(sidebars.get("excluded_product_categories") or [])

    # ---- promoted pages: prefer explicit config, else anchor_links, else nothing
    promo_pages = sidebars.get("promo_pages")
    if not promo_pages:
        promo_pages = []
        for url in (bc.get("anchor_links") or []):
            path = url.replace(site_url, "").strip("/") if site_url else url.strip("/")
            if not path or "product-category" in path or path in ("shop",):
                continue
            label = path.replace("-", " ").replace("/", " ").strip().title()
            promo_pages.append({"url": url, "label": label})
        promo_pages = promo_pages[:3]

    return {
        "slug": slug,
        "site_url": site_url,
        "brand_name": bc.get("brand_name") or brand_id.get("brand_name") or slug,
        "palette": palette,
        "heading_font": heading_font,
        "body_font": body_font,
        "prefix": sidebars.get("class_prefix") or "xrsb",
        "product_category": product_cat,
        "product_limit_post": int(sidebars.get("product_limit_post") or 2),
        "product_limit_index": int(sidebars.get("product_limit_index") or 4),
        "excluded_product_categories": sorted(set(excluded)),
        "promo_pages": promo_pages,
        # `is None`, NOT `or`: an EMPTY list is a deliberate choice, and it is
        # exactly how /init's "index sidebar only" option is encoded. Falling back
        # on falsiness turned "give this site no post sidebar" into "give it the
        # full promotional default" — the opposite of what was asked for.
        "index_modules": _modules(sidebars.get("index_modules"),
                                  ["categories", "cta_card", "products", "page_promo"]),
        "post_modules": _modules(sidebars.get("post_modules"),
                                 ["cta_card", "products", "page_promo"]),
        "cta_post": sidebars.get("cta_post") or {},
        "cta_index": sidebars.get("cta_index") or {},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# --------------------------------------------------------------------------- #
# PHP emission
# --------------------------------------------------------------------------- #

def _php_value(v: Any, indent: int = 1) -> str:
    pad = "\t" * indent
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if v is None:
        return "''"
    if isinstance(v, list):
        if not v:
            return "[]"
        inner = ",\n".join(f"{pad}\t{_php_value(x, indent + 1)}" for x in v)
        return "[\n" + inner + f",\n{pad}]"
    if isinstance(v, dict):
        if not v:
            return "[]"
        inner = ",\n".join(
            f"{pad}\t{_php_str(k)} => {_php_value(val, indent + 1)}"
            for k, val in v.items()
        )
        return "[\n" + inner + f",\n{pad}]"
    return _php_str(str(v))


def _php_str(s: str) -> str:
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


def render_php(cfg: dict[str, Any]) -> str:
    p = cfg["prefix"]
    tpl = (PLUGIN_ROOT / "templates" / "blog-sidebars.php.tpl").read_text(encoding="utf-8")
    return (
        tpl.replace("__CONFIG__", _php_value({
            "slug": cfg["slug"],
            "prefix": p,
            "product_category": cfg["product_category"],
            "product_limit_post": cfg["product_limit_post"],
            "product_limit_index": cfg["product_limit_index"],
            "excluded_product_categories": cfg["excluded_product_categories"],
            "promo_pages": cfg["promo_pages"],
        }, indent=0))
        .replace("__PREFIX__", p)
        .replace("__BRAND__", cfg["brand_name"])
        .replace("__SLUG__", cfg["slug"])
        .replace("__GENERATED__", cfg["generated_at"])
    )


def render_css(cfg: dict[str, Any]) -> str:
    p = cfg["prefix"]
    pal = cfg["palette"]
    tpl = (PLUGIN_ROOT / "templates" / "blog-sidebars.css.tpl").read_text(encoding="utf-8")
    out = tpl
    for token, value in {
        "__PREFIX__": p,
        "__SLUG__": cfg["slug"],
        "__GENERATED__": cfg["generated_at"],
        "__C_PRIMARY__": pal["primary"],
        "__C_ACCENT__": pal["accent"],
        "__C_ACCENT_DARK__": pal["accent_dark"],
        "__C_SURFACE__": pal["surface"],
        "__C_SURFACE2__": pal["surface_2"],
        "__C_INK__": pal["ink"],
        "__C_MUTED__": pal["muted"],
        "__F_HEADING__": cfg["heading_font"],
    }.items():
        out = out.replace(token, str(value))
    return out


# --------------------------------------------------------------------------- #

def generate(slug: str, dry_run: bool = False) -> dict[str, Any]:
    cfg = resolve_config(slug)
    php = render_php(cfg)
    css = render_css(cfg)

    out_dir = PLUGIN_ROOT / "projects" / slug / "brand"
    php_path = out_dir / "blog-sidebars.php"
    css_path = out_dir / "blog-sidebars.css"

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        php_path.write_text(php, encoding="utf-8")
        css_path.write_text(css, encoding="utf-8")

    return {
        "slug": slug,
        "php_path": str(php_path),
        "css_path": str(css_path),
        "php_bytes": len(php.encode("utf-8")),
        "css_bytes": len(css.encode("utf-8")),
        "class_prefix": cfg["prefix"],
        "product_category": cfg["product_category"],
        "excluded_product_categories": cfg["excluded_product_categories"],
        "promo_pages": [x["url"] for x in cfg["promo_pages"]],
        "index_modules": cfg["index_modules"],
        "post_modules": cfg["post_modules"],
        "palette": cfg["palette"],
        "dry_run": dry_run,
        "deploy_hint": (
            "Copy blog-sidebars.php to wp-content/mu-plugins/{slug}-blog-sidebars.php "
            "(chown www-data), paste blog-sidebars.css into a WPCode CSS snippet "
            "(Site Wide Header), then assign widgets. Add the class prefix to any "
            "Remove-Unused-CSS safelist."
        ).format(slug=slug),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate per-project blog sidebars")
    ap.add_argument("slug", help="Project slug under projects/")
    ap.add_argument("--dry-run", action="store_true", help="Render without writing")
    ap.add_argument("--json", action="store_true", help="Machine-readable output")
    a = ap.parse_args()

    res = generate(a.slug, dry_run=a.dry_run)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"blog sidebars for {res['slug']}"
              f"{' (dry run)' if res['dry_run'] else ''}")
        print(f"  php : {res['php_path']} ({res['php_bytes']} bytes)")
        print(f"  css : {res['css_path']} ({res['css_bytes']} bytes)")
        print(f"  prefix: .{res['class_prefix']}-*")
        print(f"  product category: {res['product_category'] or '(none — module self-disables)'}")
        if res["excluded_product_categories"]:
            print(f"  never merchandised: {', '.join(res['excluded_product_categories'])}")
        print(f"  promo pages: {len(res['promo_pages'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
