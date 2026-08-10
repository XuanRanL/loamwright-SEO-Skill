#!/usr/bin/env python3
"""Migrate LIVE posts from the legacy class vocabulary to per-project style
tokens (hop 3 of the 2026-08-01 de-fingerprint effort — Rule 13: fixing the
generator/publisher changes nothing already shipped).

What it touches, per post: every legacy class name (``xr-*``,
``article-signature``, ``{slug}-pillar``, ``xuanran-pending-image`` …) in the
post's raw content — both the inline ``<style>`` block AND the body class
attributes — via the same pure ``style_tokens.transform`` the publisher uses.
Nothing else: no wording, no structure, no JSON-LD (class names do not occur
inside schema payloads; the word-multiset safety gate below enforces it).

PRE-FLIGHT (mandatory, automatic): fetches one rendered live page and checks
whether any OTHER stylesheet on the page (theme CSS, WPCode snippet) targets
the legacy names. If so, renaming the body classes would silently detach that
styling — the run ABORTS with a report instead (fix the snippet first).

USAGE
-----
    python -m scripts.wordpress.reinject_style_tokens {slug} --dry-run
    python -m scripts.wordpress.reinject_style_tokens {slug} --apply
    python -m scripts.wordpress.reinject_style_tokens {slug} --apply --post-ids 12,34
    python -m scripts.wordpress.reinject_style_tokens {slug} --revert --post-ids 12
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from scripts._core import hop3_drift
from scripts._core import style_tokens

_TAG_RE = re.compile(r"<[^>]+>")
_STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)
_LEGACY_PROBE = re.compile(r"(?<![\w-])(?:xr-[a-z0-9][a-z0-9-]*|article-signature|xuanran-pending-image|xuanran-image-placeholder)(?![\w-])")


def _word_multiset(html: str) -> list[str]:
    """Reader-visible words only: class renames live inside tag attributes and
    the inline <style> block, so both are stripped before comparing."""
    return sorted(_TAG_RE.sub(" ", _STYLE_BLOCK_RE.sub(" ", html)).split())


def preflight_external_css(slug: str, sample_url: str,
                           own_style_norm: str | None = None) -> list[str]:
    """Return legacy-name hits in NON-article styles on a rendered live page.

    ``own_style_norm`` = the sample post's OWN raw <style> content, whitespace-
    normalized. Identifying the article's block by CONTENT (not by "contains
    the wrapper selector") matters: a site-level Customizer/WPCode copy of the
    stylesheet also contains the wrapper selector and must be FLAGGED, not
    skipped (found live on the 2026-08-01 pilot migration)."""
    import httpx

    headers = {"User-Agent": "Mozilla/5.0 (style-token preflight)"}
    try:
        from scripts.wordpress.wp_client import _load_cf_bypass_token

        token, header = _load_cf_bypass_token(slug)
        if token and header:
            headers[header] = token
    except Exception:
        pass
    page = httpx.get(sample_url, headers=headers, timeout=30,
                     follow_redirects=True).text

    wrapper = style_tokens.legacy_wrapper_class(slug)
    probe = re.compile(_LEGACY_PROBE.pattern.replace(
        "xuanran-image-placeholder", f"xuanran-image-placeholder|{re.escape(wrapper)}"))
    hits: list[str] = []
    # Every <style> block that is NOT the article's own inlined stylesheet
    # (identified by CONTENT match against the post's raw style block).
    for m in re.finditer(r"<style\b[^>]*>(.*?)</style>", page, re.S | re.I):
        css = m.group(1)
        if own_style_norm and "".join(css.split()) == own_style_norm:
            continue  # the article's own inlined stylesheet
        hits.extend(probe.findall(css))
    # Same-origin external stylesheets (theme / WPCode-generated files).
    origin = "/".join(sample_url.split("/")[:3])
    for href in re.findall(r'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']([^"\']+)', page, re.I):
        url = href if href.startswith("http") else origin + href
        if not url.startswith(origin):
            continue
        try:
            import httpx

            css = httpx.get(url, timeout=20, follow_redirects=True).text
            hits.extend(_LEGACY_PROBE.findall(css))
        except Exception:
            continue
    return sorted(set(hits))


def run(slug: str, *, apply: bool, revert: bool,
        post_ids: list[int] | None, skip_preflight: bool) -> dict[str, Any]:
    from scripts.wordpress.wp_client import WPClient

    if not style_tokens.enabled(slug):
        raise SystemExit(f"{slug} is not tokenized — run "
                         f"`python -m scripts._core.style_tokens --generate {slug}` first")
    fn = style_tokens.reverse_transform if revert else style_tokens.transform
    # Post-level probe includes the project's dynamic legacy wrapper name.
    probe = re.compile(
        r"(?<![\w-])(?:xr-[a-z0-9][a-z0-9-]*|article-signature"
        r"|xuanran-pending-image|xuanran-image-placeholder|"
        + re.escape(style_tokens.legacy_wrapper_class(slug))
        + r")(?![\w-])"
    )

    w = WPClient(slug)
    targets: list[dict[str, Any]] = []
    if post_ids:
        for pid in post_ids:
            targets.append(w.get(f"/wp/v2/posts/{pid}",
                                 params={"context": "edit"}).json_data)
    else:
        for status in ("publish", "draft"):
            page = 1
            while True:
                r = w.get("/wp/v2/posts", params={
                    "status": status, "per_page": 100, "page": page,
                    "context": "edit", "_fields": "id,slug,status,link,content"})
                batch = r.json_data
                if not isinstance(batch, list) or not batch:
                    break
                targets.extend(batch)
                if len(batch) < 100:
                    break
                page += 1

    report: dict[str, Any] = {"project": slug, "applied": apply, "revert": revert,
                              "scanned": len(targets), "updated": [],
                              "skipped": [], "errors": [], "preflight": None}

    if apply and not revert and not skip_preflight:
        sample_post = next((p for p in targets
                            if p.get("status") == "publish" and p.get("link")), None)
        sample = sample_post.get("link") if sample_post else None
        if sample:
            raw = ((sample_post or {}).get("content") or {}).get("raw") or ""
            sm = re.search(r"<style\b[^>]*>(.*?)</style>", raw, re.S | re.I)
            own_norm = "".join(sm.group(1).split()) if sm else None
            hits = preflight_external_css(slug, str(sample), own_norm)
            report["preflight"] = {"sample": sample, "external_legacy_hits": hits}
            if hits:
                report["errors"].append({
                    "id": None,
                    "reason": f"PREFLIGHT ABORT: non-article CSS on {sample} targets "
                              f"legacy names {hits} — update that theme/WPCode "
                              f"snippet first or rerun with --skip-preflight",
                })
                return report

    for p in targets:
        pid = p["id"]
        body = (p.get("content") or {}).get("raw") or ""
        new_body = fn(body, slug)
        if new_body == body:
            report["skipped"].append({"id": pid, "slug": p.get("slug"),
                                      "reason": "nothing to rename"})
            continue
        # Safety: renaming classes must never change reader-visible words.
        if _word_multiset(new_body) != _word_multiset(body):
            report["errors"].append({"id": pid,
                                     "reason": "word-level diff beyond class rename; refusing"})
            continue
        renamed = len(probe.findall(body)) if not revert else None
        entry: dict[str, Any] = {"id": pid, "slug": p.get("slug"),
                                 "status": p.get("status"),
                                 "legacy_occurrences": renamed}
        if apply:
            try:
                r = w.post(f"/wp/v2/posts/{pid}", json_body={"content": new_body})
                entry["http"] = r.status
                back = w.get(f"/wp/v2/posts/{pid}",
                             params={"context": "edit"}).json_data
                back_raw = ((back.get("content") or {}).get("raw") or "")
                if revert:
                    entry["verified"] = back_raw == new_body
                else:
                    entry["verified"] = (back_raw == new_body
                                         and not probe.search(back_raw))
            except Exception as e:  # surface, never swallow
                report["errors"].append({"id": pid,
                                         "reason": f"{type(e).__name__}: {e}"})
                continue
        report["updated"].append(entry)

    return report


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Rename legacy style classes to per-project tokens on live posts")
    ap.add_argument("slug")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true",
                   help="report drift, change nothing; exit 1 if any post is stale")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--revert", action="store_true",
                   help="token→legacy (uses the stored map inverted)")
    ap.add_argument("--post-ids", help="comma-separated ids; default = all posts")
    ap.add_argument("--skip-preflight", action="store_true",
                    help="skip the external-CSS legacy-name scan (NOT recommended)")
    ap.add_argument("--json", action="store_true", dest="as_json")
    a = ap.parse_args()

    ids = [int(x) for x in a.post_ids.split(",")] if a.post_ids else None
    rep = run(a.slug, apply=a.apply or a.revert, revert=a.revert,
              post_ids=ids, skip_preflight=a.skip_preflight)

    if a.as_json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        verb = ("REVERTED" if a.revert else "UPDATED") if (a.apply or a.revert) else "WOULD UPDATE"
        print(f"[{rep['project']}] scanned {rep['scanned']} · {verb} {len(rep['updated'])} "
              f"· skipped {len(rep['skipped'])} · errors {len(rep['errors'])}")
        for u in rep["updated"][:50]:
            ok = u.get("verified")
            mark = "" if ok is None else (" ✓" if ok else " ✗ NOT VERIFIED")
            print(f"   {u['id']:>7} [{u.get('status','?'):<7}] {u.get('slug','')}{mark}")
        for e in rep["errors"]:
            print(f"   ERROR {e.get('id')}: {e['reason']}")
    if a.check:
        print(hop3_drift.format_check(rep, artifact="style tokens"))
        return hop3_drift.check_exit_code(rep)
    return 1 if rep["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
