#!/usr/bin/env python3
"""Hop 2→3 drift for the MU-plugin REST bridges deployed to every host.

WHY THIS EXISTS (Rule 13)
`install/wordpress-mu-plugin/*.php` are shipped by hand — copied into
`wp-content/mu-plugins/` on each of ~13 hosts. Every reference to them in
`scripts/` is an *instruction*, not an executor, so nothing ever compared what is
deployed against what this repo ships.

Detection existed only as a per-call side effect: `wp_client` reads `bridge_version`
while doing something else, and `setup_categories` / `tag_seo_resolver` gate on
`>= 1.1.0` / `>= 1.2.0`. That answers "can this one call proceed", never "is the
fleet current". `manifest_consistency_check` compares the PHP header against local
`VERSION` — which is hop-1 self-consistency, not hop-3 drift.

Consequence: a host silently running an old bridge degrades quietly. RankMath meta
writes are skipped rather than failing loudly, so articles publish without their
SEO meta and the pipeline reports success.

This needs no shell access — the bridges expose their own version over REST, so it
works on all 13 projects, unlike the file-level tools that need `host_access`.

Usage
-----
    python -m scripts.wordpress.check_mu_plugin_drift {slug} --check
    python -m scripts.wordpress.check_mu_plugin_drift --all --check
    python -m scripts.wordpress.check_mu_plugin_drift --all --check --json
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
MU_DIR = PLUGIN_ROOT / "install" / "wordpress-mu-plugin"

# endpoint -> (php file, json field carrying the deployed version)
BRIDGES = {
    "rank-math": ("xuanran-rank-math-rest-bridge.php",
                  "/xuanran/v1/rank-math-bridge", "bridge_version"),
    "yoast": ("seo-machine-yoast-rest.php",
              "/seo-machine/v1/yoast-status", "version"),
}

_VER_RE = re.compile(r"^\s*\*\s*Version:\s*([0-9][0-9A-Za-z.\-]*)", re.M)


def shipped_version(php_name: str) -> str | None:
    """The version this repo ships, read from the plugin header."""
    p = MU_DIR / php_name
    if not p.exists():
        return None
    m = _VER_RE.search(p.read_text(encoding="utf-8", errors="replace"))
    return m.group(1) if m else None


def _parse(v: str | None) -> tuple[int, ...]:
    if not v:
        return ()
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:4])


def compare_version(shipped: str | None, deployed: str | None) -> dict[str, Any]:
    """Classify one bridge. Unknown is never reported as current."""
    if shipped is None:
        return {"state": "no_local_file"}
    if deployed is None:
        # Absent bridge and unreachable host are DIFFERENT findings; the caller
        # distinguishes them. Here "we could not read a version" is never "fine".
        return {"state": "not_deployed", "shipped": shipped}
    if _parse(deployed) == _parse(shipped):
        return {"state": "in_sync", "shipped": shipped, "deployed": deployed}
    if _parse(deployed) < _parse(shipped):
        return {"state": "STALE", "shipped": shipped, "deployed": deployed}
    return {"state": "AHEAD", "shipped": shipped, "deployed": deployed}


def run(slug: str) -> dict[str, Any]:
    from scripts.wordpress.wp_client import WPClient

    report: dict[str, Any] = {"project": slug, "scanned": 0, "updated": [],
                              "skipped": [], "errors": []}
    try:
        w = WPClient(slug)
    except Exception as e:                                  # noqa: BLE001
        report["errors"].append({"id": slug, "reason": f"no WP client: {e}"})
        return report

    # Which SEO plugin does this site actually run? A bridge for a plugin the
    # site does not use is NOT missing — it is not applicable. This is the same
    # mistake the JSON-LD checker made one commit earlier: absence is only drift
    # when the artifact is supposed to be there. The fleet runs RankMath, so
    # reporting the Yoast bridge "not_deployed" on all 13 projects would be pure
    # noise, and noise is how a detector gets muted.
    active: set[str] = set()
    try:
        r = w.get("/xuanran/v1/rank-math-bridge")
        if isinstance(r.json_data, dict) and r.json_data.get("rank_math_active"):
            active.add("rank-math")
    except Exception:                                       # noqa: BLE001
        pass
    try:
        r = w.get("/seo-machine/v1/yoast-status")
        if isinstance(r.json_data, dict) and r.json_data.get("yoast_installed"):
            active.add("yoast")
    except Exception:                                       # noqa: BLE001
        pass

    for name, (php, endpoint, field) in BRIDGES.items():
        report["scanned"] += 1
        shipped = shipped_version(php)
        deployed = None
        try:
            r = w.get(endpoint)
            if isinstance(r.json_data, dict):
                deployed = r.json_data.get(field)
        except Exception as e:                              # noqa: BLE001
            msg = str(e)
            if "404" not in msg and "not found" not in msg.lower():
                # A transport failure is not a content verdict (Rule 12).
                report["errors"].append({"id": f"{slug}/{name}",
                                         "reason": f"unreachable: {msg[:120]}"})
                continue

        res = compare_version(shipped, deployed)
        if res["state"] == "not_deployed" and active and name not in active:
            res = {"state": "not_applicable", "shipped": shipped,
                   "detail": f"site runs {'/'.join(sorted(active))}, not {name}"}
        rec = {"id": f"{slug}/{name}", "bridge": name, "php": php, **res}
        if res["state"] in ("STALE", "not_deployed", "AHEAD"):
            report["updated"].append(rec)
        else:
            report["skipped"].append(rec)
    return report


def all_slugs() -> list[str]:
    root = PLUGIN_ROOT / "projects"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and (p / "business-context.json").exists())


def main() -> int:
    ap = argparse.ArgumentParser(description="Fleet staleness of the MU-plugin bridges")
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--check", action="store_true", required=True,
                    help="report drift; this tool never writes")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    slugs = all_slugs() if a.all else ([a.slug] if a.slug else [])
    if not slugs:
        print("no project selected (pass a slug or --all)", file=sys.stderr)
        return 2

    reports = [run(s) for s in slugs]
    if a.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    else:
        for rep in reports:
            print(hop3_drift.format_check(rep, artifact="mu-plugin bridges", fix_hint="copy the PHP into wp-content/mu-plugins/ on those hosts"))
            for u in rep["updated"]:
                print(f"   {u['id']:<28} {u['state']:<13} "
                      f"shipped={u.get('shipped')} deployed={u.get('deployed')}")
            for e in rep["errors"]:
                print(f"   ERROR {e['id']}: {e['reason']}")
        stale = sum(1 for r in reports for u in r["updated"] if u["state"] == "STALE")
        if stale:
            print(f"\n{stale} stale bridge(s) — copy the PHP from "
                  f"install/wordpress-mu-plugin/ into wp-content/mu-plugins/ on those hosts.")
    return max((hop3_drift.check_exit_code(r) for r in reports), default=0)


if __name__ == "__main__":
    sys.exit(main())
