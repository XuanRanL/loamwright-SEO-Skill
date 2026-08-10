#!/usr/bin/env python3
"""Relocate the CTA module (heading + copy + [products] grid) end -> mid in LIVE posts.

WHY THIS EXISTS (the same 3-hop reality as reinject_article_css, 2026-07-25)
---------------------------------------------------------------------------
v3.41.5 flipped the fleet default to placements=["mid"] (front-middle, after the
content section at the ~35% word mark) at the SKILL level (injector default) and
the PROJECT level (all 12 business-context.json). But hop 3 — the CTA already
baked into published post bodies at publish time — stays end-placed forever
unless edited in place. This tool closes hop 3 for the CTA, exactly as
reinject_article_css closes it for the stylesheet.

It touches ONLY the CTA cluster (the `<h3>{registered heading}</h3>` +
`<p class="xr-cta-box…">…</p>` + optional `<p>[products …]</p>` run) — never the
stylesheet, never any other body content, never the JSON-LD.

Actions per post (mirrors scripts/optimize/cta_injector.py semantics):
  - end cluster only            -> MOVE it to the mid host section (~35% word mark,
                                   never after the first content section)
  - both mid AND end clusters   -> REMOVE the end cluster (legacy mid+end configs)
  - mid only / no module        -> no-op
  - banner-skin cluster         -> FLAG + skip (banner is an end-designed strip)
  - fewer than 3 content H2s    -> skip (too short for a mid CTA — injector rule)

(Weekly-digest posts were exempt until 2026-07-25; the operator then retired the
last `end` exception, so digests migrate like any other post.)

USAGE
-----
    python -m scripts.wordpress.reinject_cta_placement project-india --dry-run
    python -m scripts.wordpress.reinject_cta_placement --all --dry-run
    python -m scripts.wordpress.reinject_cta_placement --all --apply
    python -m scripts.wordpress.reinject_cta_placement loamwright --apply --post-ids 2122
    # drafts are included by default (a draft with an end CTA republishes the
    # defect later); restrict to live-only with --publish-only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from scripts._core import hop3_drift
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts._core.component_headings import classify_heading  # noqa: E402
from scripts.optimize.cta_injector import _STRUCTURAL_H2_RE, _MID_MARK  # noqa: E402

_TAG_RE = re.compile(r"<[^>]+>")
_H2_RE = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.S)
_H3_RE = re.compile(r"<h3\b[^>]*>(.*?)</h3>", re.S)
# after the h3: the tagged copy paragraph, then optionally the shortcode paragraph.
# cta_pat is a regex fragment — the legacy class or a legacy|token alternation for
# tokenized projects (2026-08-01 de-fingerprint boundary).
def _cluster_tail_re(cta_pat: str = "xr-cta-box") -> re.Pattern[str]:
    return re.compile(
        r'\s*<p class="' + cta_pat + r'[^"]*">.*?</p>(?:\s*<p>\[products\b[^\]]*\]</p>)?',
        re.S,
    )
_TAIL_H2_RE = re.compile(r"<h2\b[^>]*>\s*(?:References|Further Reading)\b", re.I)


def _text(html_fragment: str) -> str:
    return _TAG_RE.sub(" ", html_fragment).strip()


def find_cta_clusters(body: str, cta_pat: str = "xr-cta-box") -> list[dict[str, Any]]:
    """Every registered-heading h3 followed by its CTA-tagged paragraph (+ grid)."""
    clusters: list[dict[str, Any]] = []
    tail_re = _cluster_tail_re(cta_pat)
    for m in _H3_RE.finditer(body):
        heading = _text(m.group(1))
        skin = classify_heading(heading)
        if skin is None or "cta" not in str(skin):
            continue
        tail = tail_re.match(body, m.end())
        if not tail:
            continue  # a registered phrase used as a plain heading, not a module
        clusters.append({
            "start": m.start(), "end": tail.end(), "heading": heading,
            "skin": str(skin), "has_shortcode": "[products" in body[m.end():tail.end()],
        })
    return clusters


def content_sections(body: str) -> list[dict[str, Any]]:
    """Non-structural, non-component H2 sections (mirrors cta_injector)."""
    h2s = list(_H2_RE.finditer(body))
    sections: list[dict[str, Any]] = []
    for i, m in enumerate(h2s):
        end = h2s[i + 1].start() if i + 1 < len(h2s) else len(body)
        text = _text(m.group(1))
        structural = bool(_STRUCTURAL_H2_RE.match(text)) or classify_heading(text) is not None
        if not structural:
            sections.append({"heading": text, "start": m.start(), "end": end,
                             "words": len(_text(body[m.start():end]).split())})
    return sections


def classify_placement(body: str, cluster: dict[str, Any]) -> str:
    """'end' when no content H2 begins between the cluster and EOF/tail — i.e. the
    cluster sits in the tail zone; otherwise 'mid'."""
    after = body[cluster["end"]:]
    nxt = _H2_RE.search(after)
    while nxt is not None:
        text = _text(nxt.group(1))
        if _TAIL_H2_RE.match(nxt.group(0)):
            return "end"
        if not (_STRUCTURAL_H2_RE.match(text) or classify_heading(text) is not None):
            return "mid"
        nxt = _H2_RE.search(after, nxt.end())
    return "end"


def compute_mid_insertion(body: str) -> tuple[int, str] | None:
    """(offset, host_heading) after the section containing the ~35% word mark.
    None when < 3 content sections (too short — injector rule)."""
    sections = content_sections(body)
    if len(sections) < 3:
        return None
    total = sum(s["words"] for s in sections)
    cum = 0
    host = sections[-2]
    for s in sections:
        cum += s["words"]
        if cum >= total * _MID_MARK:
            host = s
            break
    if host is sections[0]:
        host = sections[1]
    return host["end"], host["heading"]


def migrate_body(body: str, *, slug: str = "", title: str = "",
                 cta_pat: str = "xr-cta-box") -> tuple[str, str, dict[str, Any]]:
    """Return (new_body, action, detail). new_body == body when action is a no-op."""
    detail: dict[str, Any] = {}
    clusters = find_cta_clusters(body, cta_pat)
    if not clusters:
        return body, "no_cta_module", detail
    detail["clusters"] = [
        {"heading": c["heading"], "skin": c["skin"],
         "placement": classify_placement(body, c)} for c in clusters
    ]

    placements = [classify_placement(body, c) for c in clusters]
    end_clusters = [c for c, p in zip(clusters, placements) if p == "end"]
    mid_clusters = [c for c, p in zip(clusters, placements) if p == "mid"]

    if not end_clusters:
        return body, "already_mid", detail
    if len(end_clusters) > 1:
        return body, "flagged_multiple_end", detail

    end_c = end_clusters[0]
    # A banner-skin END cluster: fine to REMOVE when a mid module already exists
    # (loamwright's v3.37 mid-card + end-banner pattern), but never MOVE a
    # full-width dark end strip into the article body — that is a design
    # decision, so an end-banner with no mid sibling gets flagged instead.
    if end_c["skin"] == "cta_banner" and not mid_clusters:
        return body, "flagged_banner", detail
    block_html = body[end_c["start"]:end_c["end"]].strip()

    # Remove the end cluster (normalize the seam it leaves behind).
    removed = body[:end_c["start"]].rstrip() + "\n" + body[end_c["end"]:].lstrip("\n")

    if mid_clusters:
        # A mid module already exists (legacy mid+end): end block is simply retired.
        return removed, "removed_end_kept_mid", detail

    ins = compute_mid_insertion(removed)
    if ins is None:
        return body, "too_short_for_mid", detail
    offset, host = ins
    detail["mid_host_section"] = host
    new_body = removed[:offset].rstrip("\n") + "\n" + block_html + "\n" + removed[offset:].lstrip("\n")
    return new_body, "moved_end_to_mid", detail


def run(slug: str, *, apply: bool, post_ids: list[int] | None,
        publish_only: bool) -> dict[str, Any]:
    from scripts._core import style_tokens
    from scripts.wordpress.wp_client import WPClient

    # Tokenized projects publish token-named CTA classes — match either form.
    cta_pat = style_tokens.match_alternation(slug, "xr-cta-box")
    w = WPClient(slug)
    targets: list[dict[str, Any]] = []
    if post_ids:
        for pid in post_ids:
            targets.append(w.get(f"/wp/v2/posts/{pid}",
                                 params={"context": "edit"}).json_data)
    else:
        statuses = ("publish",) if publish_only else ("publish", "draft")
        for status in statuses:
            page = 1
            while True:
                r = w.get("/wp/v2/posts", params={
                    "status": status, "per_page": 100, "page": page,
                    "context": "edit", "_fields": "id,slug,status,title,content"})
                batch = r.json_data
                if not isinstance(batch, list) or not batch:
                    break
                targets.extend(batch)
                if len(batch) < 100:
                    break
                page += 1

    report: dict[str, Any] = {"project": slug, "applied": apply,
                              "scanned": len(targets), "updated": [],
                              "skipped": [], "flagged": [], "errors": []}
    for p in targets:
        pid = p["id"]
        body = (p.get("content") or {}).get("raw") or ""
        title = p.get("title", {})
        title = title.get("raw") or title.get("rendered") or "" if isinstance(title, dict) else str(title)
        new_body, action, detail = migrate_body(body, slug=p.get("slug", ""), title=title,
                                                cta_pat=cta_pat)

        row = {"id": pid, "slug": p.get("slug"), "status": p.get("status"),
               "action": action, **detail}
        if action in ("no_cta_module", "already_mid", "too_short_for_mid"):
            report["skipped"].append(row)
            continue
        if action.startswith("flagged"):
            report["flagged"].append(row)
            continue

        # Safety: a MOVE must preserve the exact word MULTISET (a relocation
        # reorders words by construction, so sequence comparison would always
        # refuse — caught by the 2026-07-25 fleet dry-run). Content may only
        # change position, never appear or disappear.
        if action == "moved_end_to_mid" and (
                sorted(_TAG_RE.sub(" ", new_body).split())
                != sorted(_TAG_RE.sub(" ", body).split())):
            report["errors"].append({"id": pid, "reason": "word-level diff beyond relocation; refusing"})
            continue

        if apply:
            try:
                r = w.post(f"/wp/v2/posts/{pid}", json_body={"content": new_body})
                row["http"] = r.status
                back_raw = ((w.get(f"/wp/v2/posts/{pid}", params={"context": "edit"})
                             .json_data.get("content") or {}).get("raw") or "")
                back_clusters = find_cta_clusters(back_raw, cta_pat)
                back_placements = [classify_placement(back_raw, c) for c in back_clusters]
                row["verified"] = (
                    ("end" not in back_placements) and
                    (len(back_clusters) == (1 if action == "moved_end_to_mid" else len(back_placements)))
                )
                row["placements_after"] = back_placements
            except Exception as e:
                report["errors"].append({"id": pid, "reason": f"{type(e).__name__}: {e}"})
                continue
        report["updated"].append(row)

    return report


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Relocate the CTA module end->mid in existing posts (hop 3 of v3.41.5)")
    ap.add_argument("slug", nargs="?", help="project slug; or use --all")
    ap.add_argument("--all", action="store_true", help="run over every projects/*/")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true",
                   help="report drift, change nothing; exit 1 if any post is stale")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--post-ids", help="comma-separated ids; default = all posts")
    ap.add_argument("--publish-only", action="store_true",
                    help="skip drafts (default includes them: a draft with an end CTA republishes the defect later)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if bool(a.slug) == bool(a.all):
        ap.error("give exactly one of: a project slug, or --all")
    # Enumerate by business-context.json — credential resolution belongs to
    # WPClient/credential_hub (user-level ~/.xuanran-seo/credentials/wordpress/
    # {slug}.json), NOT to a project-tree file check: the first fleet dry-run
    # silently missed project-charlie + project-delta, whose creds are user-level only.
    slugs = ([p.name for p in sorted((PLUGIN_ROOT / "projects").iterdir())
              if (p / "business-context.json").exists()]
             if a.all else [a.slug])
    ids = [int(x) for x in a.post_ids.split(",")] if a.post_ids else None

    exit_code = 0
    for slug in slugs:
        try:
            rep = run(slug, apply=a.apply, post_ids=ids, publish_only=a.publish_only)
        except Exception as e:
            print(f"[{slug}] ERROR: {type(e).__name__}: {e}")
            exit_code = 1
            continue
        if a.json:
            print(json.dumps(rep, ensure_ascii=False, indent=2))
        else:
            verb = "UPDATED" if a.apply else "WOULD UPDATE"
            print(f"[{rep['project']}] scanned {rep['scanned']} · {verb} "
                  f"{len(rep['updated'])} · skipped {len(rep['skipped'])} · "
                  f"flagged {len(rep['flagged'])} · errors {len(rep['errors'])}")
            for u in rep["updated"]:
                mark = ""
                if a.apply:
                    mark = " ✓" if u.get("verified") else " ✗ NOT VERIFIED"
                host = f" -> after '{u.get('mid_host_section')}'" if u.get("mid_host_section") else ""
                print(f"   {u['id']:>7} [{u.get('status','?'):<7}] {u['action']}"
                      f"{host} {u.get('slug','')}{mark}")
            for f_ in rep["flagged"]:
                print(f"   FLAG {f_['id']} {f_['action']} {f_.get('slug','')}: {f_.get('clusters')}")
            for e in rep["errors"]:
                print(f"   ERROR {e['id']}: {e['reason']}")
        if a.check:
            print(hop3_drift.format_check(rep, artifact="CTA placement"))
            exit_code = max(exit_code, hop3_drift.check_exit_code(rep))
        elif rep["errors"] or any(a.apply and not u.get("verified") for u in rep["updated"]):
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
