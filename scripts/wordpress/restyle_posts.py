"""scripts/wordpress/restyle_posts.py — Phase-4 retrofit: re-style already-published posts.

The v3.31 visual design system only reaches a post at PUBLISH time (the article
CSS is inlined per-post and component classes are tagged on the rendered HTML).
Every post published before v3.31 therefore carries the OLD stylesheet forever —
the audit found all 6 pre-v3.31 loamwright posts embed a 9,044-byte CSS with zero
of the 9 component tokens. No migration tool existed (the audit's single largest
unbuilt surface). This is that tool.

What it does per post (on content.raw, preserving publish status):
  1. Replace the inline ``<style>…</style>`` block with the project's CURRENT
     article CSS (regenerate first via article_css_generator if you changed brand).
  2. Re-run the publisher's idempotent class taggers on the stored HTML:
     component blocks (stat grid / TL;DR / At-a-Glance / glossary / checklist via
     scripts/_core/component_headings) + typed callouts / pull-quotes.
  3. ``--apply`` PATCHes the post; default is a DRY-RUN diff summary.

Usage:
    python -m scripts.wordpress.restyle_posts {site_slug} --all-published --json
    python -m scripts.wordpress.restyle_posts {site_slug} --post-ids 700,706 --apply
    python -m scripts.wordpress.restyle_posts {site_slug} --all-published --check
        # gate mode: 0 = read everything, no legacy class leaks;
        # 1 = leaks survive; 2 = some post unreadable (never counted as clean)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from scripts._core import style_tokens
from scripts._core.component_headings import tag_component_blocks
from scripts.wordpress.wp_client import WPClient
from scripts.wordpress.wp_publisher import (
    _load_project_article_css,
    _minify_css,
    _tag_callouts_and_pullquotes,
)

_STYLE_RE = re.compile(r"<style>.*?</style>", re.DOTALL | re.IGNORECASE)


def _count_class_name(html: str, name: str) -> int:
    """Occurrences of one exact class name, in class attributes + CSS selectors."""
    esc = re.escape(name)
    in_attr = len(re.findall(rf'class="[^"]*(?<![\w-]){esc}(?![\w-])', html))
    in_css = len(re.findall(rf"\.{esc}(?![\w-])", html))
    return in_attr + in_css


def count_legacy_leaks(html: str, site_slug: str) -> dict[str, Any]:
    """Count legacy class names that survived in output that should be tokenized.

    Covers the FULL published-fingerprint family, not just ``xr-*``: the
    ``style_tokens.LEGACY_SPECIAL`` names (article-signature, faq-question,
    pending-image markers) and the ``{slug}-pillar`` wrapper are the same
    fingerprint — and the wrapper/signature family is what the motivating
    incident actually leaked. The 2026-08-12 audit found the old detector
    blind to all of them.

    Rule 14: the ``legacy_class_leaks`` key is ALWAYS present, and "could not
    check" is never folded into 0. ``wrapper_check`` says how far the check got:

      ``"checked"``         slug known + tokenized project: full family,
                            wrapper included
      ``"not_tokenized"``   slug known, project has no style tokens: legacy
                            names ARE the published contract there, so 0 is a
                            verdict, not an omission
      ``"skipped_no_slug"`` no slug: the wrapper class cannot be derived and
                            tokenization is unknowable; the count covers only
                            the slug-independent families it CAN check
    """
    xr = len(re.findall(r'class="[^"]*(?<![\w-])xr-', html)) + len(
        re.findall(r"\.xr-[a-z0-9][a-z0-9-]*", html)
    )
    special = sum(_count_class_name(html, n) for n in style_tokens.LEGACY_SPECIAL)
    if not site_slug:
        return {"legacy_class_leaks": xr + special, "wrapper_check": "skipped_no_slug"}
    if not style_tokens.enabled(site_slug):
        return {"legacy_class_leaks": 0, "wrapper_check": "not_tokenized"}
    wrapper = _count_class_name(html, style_tokens.legacy_wrapper_class(site_slug))
    return {"legacy_class_leaks": xr + special + wrapper, "wrapper_check": "checked"}


def restyle_content(raw: str, css_min: str, site_slug: str = "") -> tuple[str, dict]:
    """Pure transform: swap the inline stylesheet + re-tag components. Idempotent.

    TOKEN CONTRACT (2026-08-08): on style-token projects the PUBLISHED wrapper +
    component class names are per-project HMAC tokens, not the legacy names
    (scripts/_core/style_tokens; applied by wp_publisher at the publish
    boundary). This tool re-taggs with LEGACY names and loads the LEGACY-flavor
    generated CSS, so the whole output MUST pass through
    ``style_tokens.transform`` before it ships — without that, the fresh
    ``.{slug}-pillar`` stylesheet matches nothing in an already-tokenized body
    and the post renders completely unstyled (this exact failure shipped to 3
    live project-alpha posts on 2026-08-08 before being caught by readback).
    ``transform`` is a no-op for non-token projects and leaves existing token
    names untouched, so applying it unconditionally is safe and idempotent."""
    stats = {"style_replaced": False, "old_style_bytes": 0, "new_style_bytes": len(css_min)}
    m = _STYLE_RE.search(raw)
    new_style = f"<style>{css_min}</style>"
    if m:
        stats["old_style_bytes"] = len(m.group(0)) - len("<style></style>")
        out = raw[:m.start()] + new_style + raw[m.end():]
        stats["style_replaced"] = True
    else:
        # No inline style yet — insert right after the first wp:html opener if present.
        marker = "<!-- wp:html -->"
        idx = raw.find(marker)
        if idx >= 0:
            at = idx + len(marker)
            out = raw[:at] + "\n" + new_style + raw[at:]
            stats["style_replaced"] = True
        else:
            out = new_style + "\n" + raw
            stats["style_replaced"] = True
    before = out
    out = _tag_callouts_and_pullquotes(out)
    out = tag_component_blocks(out)
    stats["classes_added"] = int(out != before)
    if site_slug:
        out = style_tokens.transform(out, site_slug)
    # On a token project, any surviving legacy name is a leak — count it across
    # the FULL family and ALWAYS report the verdict keys, so a dry-run surfaces
    # the defect instead of hiding it and an absent key can never read as
    # "clean" (Rule 14; see count_legacy_leaks).
    stats.update(count_legacy_leaks(out, site_slug))
    stats["xr_class_count"] = len(re.findall(r'class="[^"]*xr-', out))
    return out, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Retrofit published posts with the current article CSS + component classes")
    ap.add_argument("site_slug")
    ap.add_argument("--post-ids", default="", help="Comma-separated post IDs")
    ap.add_argument("--all-published", action="store_true", help="Retrofit every published post")
    ap.add_argument("--apply", action="store_true", help="PATCH the posts (default: dry-run)")
    ap.add_argument(
        "--check", action="store_true",
        help=(
            "Gate mode (dry-run, never PATCHes): exit 1 if any legacy class "
            "leak survives in the would-be output, 2 if any post could not be "
            "read (unreadable is never 'clean'), 0 only when every post was "
            "read and is leak-free."
        ),
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.check and args.apply:
        print("Error: --check is a dry-run gate; drop --apply.", file=sys.stderr)
        return 2

    css = _load_project_article_css(args.site_slug)
    if not css:
        print(f"Error: no article CSS found for project '{args.site_slug}'", file=sys.stderr)
        return 2
    css_min = _minify_css(css) if "/*" in css or "  " in css else css

    results: list[dict] = []
    with WPClient(args.site_slug) as wp:
        ids: list[int] = []
        if args.post_ids:
            ids = [int(x) for x in args.post_ids.split(",") if x.strip()]
        elif args.all_published:
            page = 1
            while True:
                r = wp.get(f"/wp/v2/posts?per_page=100&page={page}&status=publish&_fields=id")
                batch = r.json_data or []
                ids.extend(int(p["id"]) for p in batch)
                if len(batch) < 100:
                    break
                page += 1
        else:
            print("Error: pass --post-ids or --all-published", file=sys.stderr)
            return 2

        for pid in ids:
            try:
                r = wp.get(f"/wp/v2/posts/{pid}?context=edit&_fields=id,slug,status,content")
                post = r.json_data or {}
                raw = (post.get("content") or {}).get("raw", "")
            except Exception as exc:
                # A transport failure is NOT a content verdict (Rule 12/13):
                # record the post as unreadable rather than crashing or, worse,
                # letting it silently count as clean.
                results.append({"post_id": pid, "skipped": f"unreadable: {type(exc).__name__}: {exc}"})
                continue
            if not raw:
                results.append({"post_id": pid, "skipped": "no raw content"})
                continue
            new_raw, stats = restyle_content(raw, css_min, site_slug=args.site_slug)
            changed = new_raw != raw
            rec = {"post_id": pid, "slug": post.get("slug"), "status": post.get("status"),
                   "changed": changed, **stats, "applied": False}
            if changed and args.apply:
                wp.post(f"/wp/v2/posts/{pid}", json_body={"content": new_raw})
                rec["applied"] = True
            results.append(rec)

    processed = [r for r in results if "skipped" not in r]
    unreadable = [r for r in results if "skipped" in r]
    # Deliberate indexing (not .get(..., 0)): restyle_content guarantees the key
    # on every processed post, and a missing key here would be a wiring bug that
    # must surface loudly, never read as 0 leaks (Rule 14.6).
    leaks = sum(r["legacy_class_leaks"] for r in processed)

    summary = {
        "site": args.site_slug,
        "mode": "check" if args.check else ("apply" if args.apply else "dry-run"),
        "posts": results,
        "changed": sum(1 for r in results if r.get("changed")),
        "applied": sum(1 for r in results if r.get("applied")),
        "legacy_class_leaks": leaks,
        "unreadable": len(unreadable),
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        line = (f"{summary['mode']}: {summary['changed']} changed, "
                f"{summary['applied']} applied of {len(results)} post(s); "
                f"legacy class leaks: {leaks}")
        if processed and all(r.get("wrapper_check") == "not_tokenized" for r in processed):
            line += " (project not tokenized: legacy names are canonical there)"
        if unreadable:
            line += f"; UNREADABLE: {len(unreadable)} post(s) — not verified clean"
        print(line)

    if args.check:
        if leaks:
            return 1
        if unreadable:
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
