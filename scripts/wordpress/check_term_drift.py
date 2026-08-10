#!/usr/bin/env python3
"""Hop 2→3 drift for category and tag term meta.

WHY THIS EXISTS (Rule 13)
`setup_categories.py` / `setup_tags.py` DO push hop 2 → hop 3 idempotently, so the
write half was never the gap. The gap was detection: the only sync check compared
term **IDs** (`categories_sync_check`: `wp_ids - config_ids`), so a description or
`rank_math_*` value hand-edited in WP admin — or one left behind when the config
was rewritten — was completely invisible. Tags had no live diff at all;
`tags-live.json` exists on 3 projects and is hand-maintained, written by no script.

A term description is customer-facing copy on an indexed archive page. It drifting
away from the config is exactly the "the repo says one thing, the site says
another" failure Rule 13 describes, and it is the last of the three surfaces that
had no executor.

Detection only. `setup_categories` / `setup_tags` remain the writers, so there is
one place that mutates and one place that reports.

Usage
-----
    python -m scripts.wordpress.check_term_drift {slug} --check
    python -m scripts.wordpress.check_term_drift {slug} --check --taxonomy tags
    python -m scripts.wordpress.check_term_drift --all --check --json
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts._core import hop3_drift

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

TAXONOMIES = ("categories", "tags")
_TAG_RE = re.compile(r"<[^>]+>")


def _load_json(p: Path) -> dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _norm(text: str) -> str:
    """Compare wording, not rendering.

    WP returns descriptions HTML-escaped and sometimes wrapped; curly vs straight
    quotes also differ between the config file and what round-trips through the
    database. Normalising to words keeps this sensitive to an EDITED description
    while ignoring transport artifacts — the same lesson the signature checker
    learned the hard way against production.
    """
    t = html.unescape(str(text or ""))
    t = _TAG_RE.sub(" ", t)
    t = (t.replace("’", "'").replace("‘", "'")
          .replace("“", '"').replace("”", '"')
          .replace("—", "-").replace("–", "-"))
    return " ".join(re.sub(r"[^0-9a-z']+", " ", t.lower()).split())


def config_terms(slug: str, taxonomy: str) -> dict[str, dict[str, Any]]:
    """slug -> expected term record, flattened across nesting and tag tiers."""
    proj = PLUGIN_ROOT / "projects" / slug
    out: dict[str, dict[str, Any]] = {}

    if taxonomy == "categories":
        cfg = _load_json(proj / "categories-config.json")

        def walk(items: list[dict[str, Any]]) -> None:
            for c in items or []:
                if isinstance(c, dict) and c.get("slug"):
                    out[str(c["slug"])] = c
                    walk(c.get("children") or [])
        walk(cfg.get("categories") or [])
    else:
        cfg = _load_json(proj / "tags-config.json")
        for key in ("strategic_tags", "baseline_tags"):
            for t in cfg.get(key) or []:
                if isinstance(t, dict) and t.get("slug"):
                    out[str(t["slug"])] = t
    return out


def _expected_desc(rec: dict[str, Any]) -> str:
    return str(rec.get("description") or rec.get("desc") or "")


def compare_term(expected: dict[str, Any], live: dict[str, Any]) -> list[dict[str, Any]]:
    """Field-level differences between config and the live term."""
    issues: list[dict[str, Any]] = []

    want_desc = _expected_desc(expected)
    if want_desc:
        got_desc = live.get("description") or ""
        if _norm(want_desc) != _norm(got_desc):
            issues.append({"field": "description",
                           "expected": want_desc[:70], "found": str(got_desc)[:70]})

    want_name = str(expected.get("name") or "")
    if want_name and _norm(want_name) != _norm(live.get("name") or ""):
        issues.append({"field": "name", "expected": want_name,
                       "found": live.get("name")})

    meta = live.get("meta") or {}
    for cfg_key, wp_key in (("rank_math_title", "rank_math_title"),
                            ("rank_math_description", "rank_math_description")):
        want = str(expected.get(cfg_key) or "")
        if not want:
            continue                      # hop 2 does not assert this field
        got = meta.get(wp_key)
        if got is None:
            continue                      # bridge not exposing it: unknown, not drift
        if _norm(want) != _norm(got):
            issues.append({"field": cfg_key, "expected": want[:70],
                           "found": str(got)[:70]})
    return issues


def run(slug: str, *, taxonomies: tuple[str, ...] = TAXONOMIES) -> dict[str, Any]:
    from scripts.wordpress.wp_client import WPClient

    report: dict[str, Any] = {"project": slug, "scanned": 0, "updated": [],
                              "skipped": [], "errors": []}
    w = WPClient(slug)

    for tax in taxonomies:
        expected = config_terms(slug, tax)
        if not expected:
            continue                      # project has no config for this taxonomy
        live: list[dict[str, Any]] = []
        page = 1
        while True:
            try:
                r = w.get(f"/wp/v2/{tax}", params={"per_page": 100, "page": page,
                                                   "context": "edit"})
            except Exception as e:        # noqa: BLE001
                report["errors"].append({"id": tax, "reason": f"{type(e).__name__}: {e}"})
                break
            batch = r.json_data
            if not isinstance(batch, list) or not batch:
                break
            live.extend(batch)
            if len(batch) < 100:
                break
            page += 1

        by_slug = {str(t.get("slug")): t for t in live if isinstance(t, dict)}
        for slug_key, rec in expected.items():
            report["scanned"] += 1
            got = by_slug.get(slug_key)
            if got is None:
                report["updated"].append({"id": f"{tax}/{slug_key}", "slug": slug_key,
                                          "taxonomy": tax,
                                          "issues": [{"field": "term",
                                                      "expected": "present on site",
                                                      "found": None}]})
                continue
            issues = compare_term(rec, got)
            if issues:
                report["updated"].append({"id": got.get("id"), "slug": slug_key,
                                          "taxonomy": tax, "issues": issues})
            else:
                report["skipped"].append({"id": got.get("id")})
    return report


def all_slugs() -> list[str]:
    root = PLUGIN_ROOT / "projects"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir()
                  and ((p / "categories-config.json").exists()
                       or (p / "tags-config.json").exists()))


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect drift in category/tag term meta")
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--check", action="store_true", required=True,
                    help="report drift; this tool never writes")
    ap.add_argument("--taxonomy", choices=TAXONOMIES, action="append")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    slugs = all_slugs() if a.all else ([a.slug] if a.slug else [])
    if not slugs:
        print("no project selected (pass a slug or --all)", file=sys.stderr)
        return 2

    taxes = tuple(a.taxonomy) if a.taxonomy else TAXONOMIES
    reports = [run(s, taxonomies=taxes) for s in slugs]

    if a.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    else:
        for rep in reports:
            print(hop3_drift.format_check(rep, artifact="term meta", fix_hint="re-run setup_categories / setup_tags to repush"))
            for u in rep["updated"][:20]:
                for i in u["issues"]:
                    print(f"   {u['taxonomy']}/{u['slug']} [{i['field']}] "
                          f"expected={i['expected']!r} found={i['found']!r}")
            for e in rep["errors"]:
                print(f"   ERROR {e['id']}: {e['reason']}")

    return max((hop3_drift.check_exit_code(r) for r in reports), default=0)


if __name__ == "__main__":
    sys.exit(main())
