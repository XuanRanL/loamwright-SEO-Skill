#!/usr/bin/env python3
"""Hop 2→3 drift for the FACTS frozen into published post bodies.

WHY THIS EXISTS (Rule 13 + Rule 14)
Three of the six unguarded 3-hop surfaces are the same shape: a value resolved
from project config at publish time and then frozen, verbatim, into every post
body. Changing the config changes nothing already published, and until now nothing
could see the difference:

* **JSON-LD @graph** — org name / url / logo / sameAs, baked into each post's
  inline `<script type="application/ld+json">`. `verify_post` check 17 counts
  blocks and collects `@type` names; it never compares payload VALUES. Change the
  org logo and 13 sites keep serving the old one, invisibly. Highest blast radius
  of the unguarded set.
* **Article signature** — `<p class="article-signature">`. `verify_post` asserts
  the element EXISTS, not what it says. The proof this gap is real is
  `scripts/wordpress/fix_founder_name.py`: a hardcoded one-off regex written to
  repair exactly this damage on one project, after the fact.
* **CTA product SKUs** — `[products ids="…"]`. `reinject_cta_placement` states its
  scope as "the CTA cluster" and moves it verbatim; it never re-resolves ids. A
  retired SKU stays in every live shortcode forever, and `wc_catalog_sync`
  refreshes hop 2 FROM WooCommerce, which is how the mismatch is created without
  being reported.

This is detection only. It never writes — repairing each surface is a separate,
deliberate act, and a checker that also mutates is one an operator stops trusting.

Usage
-----
    python -m scripts.wordpress.check_post_drift {slug} --check
    python -m scripts.wordpress.check_post_drift {slug} --check --json
    python -m scripts.wordpress.check_post_drift {slug} --check --surface jsonld
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts._core import hop3_drift

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

SURFACES = ("jsonld", "signature", "skus")

_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I)


def _signature_re(slug: str) -> re.Pattern[str]:
    """Match the signature paragraph by its PUBLISHED class name.

    On style-token projects (13 of 13 today) `article-signature` ships as a
    per-project HMAC token — project-alpha publishes `q7zw2w-3u4auk`. Grepping the
    legacy name finds nothing and reports every post as missing its signature.
    This is the exact trap `references/retired-contracts.json ::
    style-tokens-v3420` exists to catch, walked into here in brand-new code:
    resolve the name, never hand-write it.
    """
    names = {"article-signature"}
    try:
        from scripts._core import style_tokens
        tok = style_tokens.class_for(slug, "article-signature")
        if isinstance(tok, str) and tok:
            names.add(tok)
    except Exception:                       # noqa: BLE001 — untokenized project
        pass
    alt = "|".join(re.escape(n) for n in sorted(names))
    return re.compile(
        rf'<p[^>]*class=["\'][^"\']*(?:{alt})[^"\']*["\'][^>]*>(.*?)</p>',
        re.S | re.I)


_SKU_RE = re.compile(r'\[products[^\]]*\bids=["\']?([0-9,\s]+)["\']?', re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _load_json(p: Path) -> dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def expected_org(bc: dict[str, Any]) -> dict[str, Any]:
    """The org identity hop 2 says every published graph should carry."""
    company = bc.get("company") or {}
    return {
        "name": bc.get("brand_name") or company.get("name") or "",
        "url": (bc.get("site_url") or "").rstrip("/"),
        "logo": company.get("logo") or company.get("logo_url") or "",
        "sameAs": sorted(str(x) for x in (company.get("sameAs")
                                          or company.get("social_profiles") or [])),
    }


def _graph_nodes(content: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for block in _LD_RE.findall(content or ""):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        items = data.get("@graph") if isinstance(data, dict) else None
        for n in (items if isinstance(items, list) else [data]):
            if isinstance(n, dict):
                nodes.append(n)
    return nodes


def org_in_post(content: str) -> dict[str, Any] | None:
    """The Organization/Person node actually published in this post."""
    for n in _graph_nodes(content):
        t = n.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(str(x) in ("Organization", "Corporation", "LocalBusiness",
                          "OnlineStore", "Person") for x in types):
            logo = n.get("logo")
            if isinstance(logo, dict):
                logo = logo.get("url", "")
            same = n.get("sameAs") or []
            return {
                "name": str(n.get("name") or ""),
                "url": str(n.get("url") or "").rstrip("/"),
                "logo": str(logo or ""),
                "sameAs": sorted(str(x) for x in (same if isinstance(same, list) else [same])),
            }
    return None


def signature_text(content: str, slug: str = "") -> str | None:
    m = _signature_re(slug).search(content or "")
    if not m:
        return None
    return " ".join(_TAG_RE.sub(" ", m.group(1)).split())


def sku_ids(content: str) -> list[int]:
    out: list[int] = []
    for m in _SKU_RE.findall(content or ""):
        for part in m.split(","):
            part = part.strip()
            if part.isdigit():
                out.append(int(part))
    return out


_PLACEHOLDER_RE = re.compile(r"\{[^}]*\}")
_MDLINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_CJK_RE = re.compile(r"[㐀-鿿぀-ヿ가-힯]")


def _norm_sig(text: str) -> str:
    """Compare wording, not punctuation spacing.

    Stripping tags turns `</a>.` into `audit .` while the template says `audit.`
    — a single space that made every correctly-published post look drifted on the
    first live run. Normalising to alphanumeric words keeps the check sensitive to
    a changed NAME (which is the whole point) while ignoring rendering artifacts.
    """
    return " ".join(re.sub(r"[^0-9a-z]+", " ", str(text or "").lower()).split())


def signature_fragments(template: str) -> list[str]:
    """Invariant literal runs of the signature template.

    The template is the source of truth, and it is NOT a literal string: it
    carries `{month_year}` placeholders and markdown links that render away.
    Comparing the whole thing (or comparing against the human-readable `author`
    descriptor, which is what the first version of this check did) flags every
    correctly-published post. Split on the variable parts and keep the runs long
    enough to be evidence.
    """
    t = _MDLINK_RE.sub(r"\1", str(template or ""))
    t = t.replace("*", " ")
    parts = [" ".join(x.split()) for x in _PLACEHOLDER_RE.split(t)]
    return [x for x in parts if len(x) >= 12]


def _identity_clause(fragments: list[str]) -> str:
    """The sentence that names WHO wrote and reviewed the article.

    The longest fragment also swallows the CTA sentence, so a project that varies
    its call-to-action wording ("Want this run on your site?" vs "Want the same
    read on your own site?") looked like signature drift. Attribution is the thing
    worth guarding; CTA phrasing is editorial. Narrow to the sentence carrying
    "author"/"reviewed" when there is one.
    """
    for frag in sorted(fragments, key=len, reverse=True):
        for sentence in re.split(r"(?<=[.!?])\s+", frag):
            low = sentence.lower()
            if "author" in low or "reviewed by" in low:
                return sentence.strip(" .")
    return max(fragments, key=len)


def _signature_matches(published: str, template: str) -> bool:
    """True when the published signature carries the template's identity text.

    A localized signature (CJK body against a Latin template) is NOT drift: the
    project simply has no template recorded for that locale, and flagging every
    translated post would bury the real findings. Recorded as a known limit
    rather than guessed at.
    """
    frags = signature_fragments(template)
    if not frags:
        return True
    # Matching ANY fragment is too weak: "Last reviewed and updated:" is
    # boilerplate that survives a changed author, so a post crediting the wrong
    # person still passed. The LONGEST fragment carries the identity (author and
    # reviewer names), so that is the one that has to be present.
    identity = _identity_clause(frags)
    if _norm_sig(identity) in _norm_sig(published):
        return True
    if _CJK_RE.search(published) and not _CJK_RE.search(template):
        return True          # locale variant, no template configured for it
    return False



def _compare(post: dict[str, Any], *, bc: dict[str, Any], catalog_ids: set[int],
             sig_expected: str, surfaces: tuple[str, ...],
             slug: str = "") -> list[dict[str, Any]]:
    content = ((post.get("content") or {}).get("raw")
               or (post.get("content") or {}).get("rendered") or "")
    issues: list[dict[str, Any]] = []

    if "jsonld" in surfaces:
        want = expected_org(bc)
        got = org_in_post(content)
        if got is None:
            # NOT drift. Whether org identity is baked into the body is
            # project-dependent: when RankMath (or another SEO plugin) already
            # emits Organization in the document HEAD, the pipeline deliberately
            # skips that type, and the head node is rendered LIVE from WP options
            # — so it is not a frozen 3-hop artifact at all and updates itself.
            # Verified on project-alpha 2026-08-05: body carries FAQPage + ItemList
            # only, while the head serves Organization + Person from RankMath.
            # Reporting absence as drift would fire on every post of every such
            # project — a detector that cries wolf is one that gets muted.
            pass
        else:
            for k in ("name", "url", "logo", "sameAs"):
                if not want[k]:
                    continue            # hop 2 does not assert this field
                if got.get(k) != want[k]:
                    issues.append({"surface": "jsonld", "field": k,
                                   "expected": want[k], "found": got.get(k)})

    if "signature" in surfaces and sig_expected:
        got = signature_text(content, slug)
        if got is None:
            issues.append({"surface": "signature", "field": "element",
                           "expected": sig_expected[:60], "found": None})
        elif not _signature_matches(got, sig_expected):
            issues.append({"surface": "signature", "field": "text",
                           "expected": sig_expected[:80], "found": got[:80]})

    if "skus" in surfaces and catalog_ids:
        stale = [i for i in sku_ids(content) if i not in catalog_ids]
        if stale:
            issues.append({"surface": "skus", "field": "ids",
                           "expected": "ids present in product-catalog.json",
                           "found": stale})
    return issues


def run(slug: str, *, surfaces: tuple[str, ...] = SURFACES,
        post_ids: list[int] | None = None) -> dict[str, Any]:
    from scripts.wordpress.wp_client import WPClient

    proj = PLUGIN_ROOT / "projects" / slug
    bc = _load_json(proj / "business-context.json")
    catalog = _load_json(proj / "product-catalog.json")
    catalog_ids = {int(p["id"]) for p in (catalog.get("products") or [])
                   if isinstance(p, dict) and str(p.get("id", "")).isdigit()}

    sig_cfg = bc.get("article_signature") or {}
    # markdown_template is what actually gets published. `author` is a
    # human-readable descriptor ("Loamwright SEO Team (reviewed by ...)") that
    # never appears verbatim in a post — using it flagged 12 correctly-published
    # posts on the first live run.
    sig_expected = str(sig_cfg.get("markdown_template")
                       or sig_cfg.get("template")
                       or sig_cfg.get("author") or "")

    report: dict[str, Any] = {"project": slug, "surfaces": list(surfaces),
                              "scanned": 0, "updated": [], "skipped": [],
                              "errors": []}
    if not bc:
        report["errors"].append({"id": None, "reason": f"no business-context for {slug}"})
        return report

    w = WPClient(slug)
    targets: list[dict[str, Any]] = []
    if post_ids:
        for pid in post_ids:
            targets.append(w.get(f"/wp/v2/posts/{pid}",
                                 params={"context": "edit"}).json_data)
    else:
        page = 1
        while True:
            r = w.get("/wp/v2/posts", params={
                "status": "publish", "per_page": 100, "page": page,
                "context": "edit", "_fields": "id,slug,status,link,content"})
            batch = r.json_data
            if not isinstance(batch, list) or not batch:
                break
            targets.extend(batch)
            if len(batch) < 100:
                break
            page += 1

    report["scanned"] = len(targets)
    for post in targets:
        try:
            issues = _compare(post, bc=bc, catalog_ids=catalog_ids,
                              sig_expected=sig_expected, surfaces=surfaces,
                              slug=slug)
        except Exception as e:                      # noqa: BLE001 — one bad post must not abort the sweep
            report["errors"].append({"id": post.get("id"),
                                     "reason": f"{type(e).__name__}: {e}"})
            continue
        if issues:
            # "updated" is the shared hop3_drift vocabulary for "would change".
            report["updated"].append({"id": post.get("id"), "slug": post.get("slug"),
                                      "status": post.get("status"), "issues": issues})
        else:
            report["skipped"].append({"id": post.get("id")})
    return report


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Detect drift in facts frozen into published post bodies")
    ap.add_argument("slug")
    ap.add_argument("--check", action="store_true", required=True,
                    help="report drift; this tool never writes")
    ap.add_argument("--surface", choices=SURFACES, action="append",
                    help="limit to one surface (repeatable)")
    ap.add_argument("--post-ids", help="comma-separated ids; default = all published")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    ids = [int(x) for x in a.post_ids.split(",")] if a.post_ids else None
    rep = run(a.slug, surfaces=tuple(a.surface) if a.surface else SURFACES,
              post_ids=ids)

    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(hop3_drift.format_check(rep, artifact="post-body facts", fix_hint="detection only; repair is a separate step"))
        by_surface: dict[str, int] = {}
        for u in rep["updated"]:
            for i in u["issues"]:
                by_surface[i["surface"]] = by_surface.get(i["surface"], 0) + 1
        for s, n in sorted(by_surface.items()):
            print(f"    {s}: {n} issue(s)")
        for u in rep["updated"][:20]:
            for i in u["issues"]:
                print(f"   {u['id']:>7} [{i['surface']}/{i['field']}] "
                      f"expected={i['expected']!r} found={i['found']!r}")
        for e in rep["errors"]:
            print(f"   ERROR {e['id']}: {e['reason']}")
    return hop3_drift.check_exit_code(rep)


if __name__ == "__main__":
    sys.exit(main())
