"""
scripts/monitor/monitor_smoke.py — one-command end-to-end monitoring health check.

Exercises the full monitoring chain on REAL data for a project and confirms every integration
fires:
  - GSC   (first-party clicks / impressions / position)            via scripts.audit.gsc_fetch
  - GA4   (traffic by channel, incl. the "AI Assistant" channel)   via scripts.audit.ga4_fetch
  - SERP  (live whole-SERP rank for the project's top GSC query)   via scripts.fetch.serpapi_query
  - GEO   (is the domain cited in Google AI Overview / AI Mode?)    via serpapi_query

It also surfaces **ranking-opportunity** queries — high impressions but weak position and no
clicks — which are the content-refresher's prime refresh candidates.

    python -m scripts.monitor.monitor_smoke --site project-charlie --json
    python -m scripts.monitor.monitor_smoke --all --days 28
    python -m scripts.monitor.monitor_smoke --site project-charlie --no-serp   # skip SerpApi (0 quota)

Reads per-project IDs from projects/{slug}/business-context.json :: analytics. Each stage is
independent — one stage failing (e.g. a brand-new GA4 with no rows) does not fail the others.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from typing import Any
from urllib.parse import urlparse

from scripts.audit import ga4_fetch, gsc_fetch
from scripts.fetch import serpapi_query

# A query with at least this many impressions but ranking this weak and getting no clicks is a
# "ranking opportunity" — visible to Google, not winning the click. Prime refresh candidate.
OPP_MIN_IMPRESSIONS = 50
OPP_MIN_POSITION = 20.0


def _domain(site_url: str) -> str:
    host = urlparse(site_url).netloc or site_url
    return host.lower().lstrip("www.")


def _load_analytics(slug: str) -> tuple[dict[str, Any], str]:
    path = f"projects/{slug}/business-context.json"
    data = json.loads(open(path, encoding="utf-8").read())
    return data.get("analytics", {}), data.get("site_url", "")


def check_site(slug: str, *, days: int = 28, include_serp: bool = True) -> dict[str, Any]:
    """Run the full monitoring chain for one project; never raises (errors captured per stage)."""
    out: dict[str, Any] = {"site": slug, "days": days, "stages": {}}
    try:
        analytics, site_url = _load_analytics(slug)
    except Exception as e:
        out["error"] = f"no business-context: {e}"
        return out
    domain = _domain(site_url)
    out["domain"] = domain

    # ── GSC ──
    top_query: str | None = None
    try:
        g = gsc_fetch.fetch(analytics["gsc_property"], days=days, dimensions=["query"], row_limit=1000)
        rows = g.get("rows", [])
        rows.sort(key=lambda r: r.get("impressions", 0), reverse=True)
        opps = [
            {"query": r["keys"][0], "impressions": r["impressions"],
             "position": round(r["position"], 1), "clicks": r["clicks"]}
            for r in rows
            if r.get("impressions", 0) >= OPP_MIN_IMPRESSIONS
            and r.get("position", 0) >= OPP_MIN_POSITION
            and r.get("clicks", 0) == 0
        ]
        if rows:
            top_query = rows[0]["keys"][0]
        out["stages"]["gsc"] = {
            "ok": True, "queries": len(rows),
            "total_clicks": sum(r.get("clicks", 0) for r in rows),
            "total_impressions": sum(r.get("impressions", 0) for r in rows),
            "top_query": top_query,
            "ranking_opportunities": opps[:10],
        }
    except Exception as e:
        out["stages"]["gsc"] = {"ok": False, "error": str(e)[:120]}

    # ── GA4 ──
    try:
        ga = ga4_fetch.fetch(analytics["ga4_property_id"], days=days)
        rows4 = ga4_fetch._rows(ga)
        channels = {r.get("sessionDefaultChannelGroup", "?"): int(r.get("sessions", 0)) for r in rows4}
        out["stages"]["ga4"] = {
            "ok": True, "channels": channels,
            "organic_sessions": channels.get("Organic Search", 0),
            "ai_assistant_sessions": channels.get("AI Assistant", 0),
        }
    except Exception as e:
        out["stages"]["ga4"] = {"ok": False, "error": str(e)[:120]}

    # ── Bing Webmaster (first-party Bing search data — the second engine) ──
    try:
        from scripts._core import credential_hub
        from scripts.monitor import bing_webmaster_ingest as bwi
        bw = credential_hub.get_bing_webmaster()
        bsite = bwi._resolve_site_url(slug)
        qstats = bwi.get_query_stats(bsite, bw.api_key, bw.user_agent)
        out["stages"]["bing"] = {
            "ok": True, "site": bsite, "query_count": len(qstats),
            "clicks": sum(int(r.get("Clicks", 0) or 0) for r in qstats),
            "impressions": sum(int(r.get("Impressions", 0) or 0) for r in qstats),
        }
    except Exception as e:
        out["stages"]["bing"] = {"ok": False, "error": str(e)[:120]}

    # ── SERP + GEO (optional; costs SerpApi quota) ──
    if include_serp and top_query:
        try:
            d = serpapi_query.query("google", top_query, params={"gl": "us", "hl": "en"}, use_cache=True)
            org = d.get("organic_results", [])
            pos = next((o.get("position") for o in org if domain in (o.get("link") or "")), None)
            aio = serpapi_query.ai_overview(top_query, params={"gl": "us", "hl": "en"}, use_cache=True)
            aio_block = aio.get("ai_overview") if isinstance(aio.get("ai_overview"), dict) else {}
            aio_refs = aio_block.get("references", []) if isinstance(aio_block, dict) else []
            am = serpapi_query.query("google_ai_mode", top_query, use_cache=True)
            am_refs = am.get("references", []) or []
            out["stages"]["serp"] = {
                "ok": True, "query": top_query, "organic_count": len(org),
                "domain_serp_position": pos,
                "ai_overview_present": bool(d.get("ai_overview") or aio_refs),
                "cited_in_ai_overview": any(domain in (r.get("link") or "") for r in aio_refs),
                "cited_in_ai_mode": any(domain in (r.get("link") or "") for r in am_refs),
                "top_competitors": [o.get("link") for o in org[:3]],
            }
        except Exception as e:
            out["stages"]["serp"] = {"ok": False, "error": str(e)[:120]}
    elif include_serp:
        out["stages"]["serp"] = {"ok": False, "error": "no GSC top query to probe"}

    out["chain_ok"] = all(s.get("ok") for k, s in out["stages"].items() if k in ("gsc", "ga4"))
    return out


def _print_human(rep: dict[str, Any]) -> None:
    print(f"── {rep['site']} ({rep.get('domain','?')}) · last {rep['days']}d ──")
    if rep.get("error"):
        print(f"  ERROR: {rep['error']}")
        return
    s = rep["stages"]
    g = s.get("gsc", {})
    if g.get("ok"):
        print(f"  GSC: {g['queries']} queries · {g['total_impressions']} impr · {g['total_clicks']} clicks · top={g['top_query']!r}")
        for o in g.get("ranking_opportunities", [])[:5]:
            print(f"     ⚠ opportunity: {o['query']!r}  impr={o['impressions']} pos={o['position']} clicks={o['clicks']}")
    else:
        print(f"  GSC: FAIL {g.get('error')}")
    a = s.get("ga4", {})
    print(f"  GA4: {'organic='+str(a['organic_sessions'])+' ai_assistant='+str(a['ai_assistant_sessions'])+' '+str(a['channels']) if a.get('ok') else 'FAIL '+str(a.get('error'))}")
    b = s.get("bing", {})
    print(f"  Bing: {'queries='+str(b['query_count'])+' clicks='+str(b['clicks'])+' impr='+str(b['impressions']) if b.get('ok') else 'FAIL '+str(b.get('error'))}")
    se = s.get("serp")
    if se and se.get("ok"):
        print(f"  SERP[{se['query']!r}]: domain_pos={se['domain_serp_position']} · AIO={se['ai_overview_present']} "
              f"cited_AIO={se['cited_in_ai_overview']} cited_AImode={se['cited_in_ai_mode']}")
    elif se:
        print(f"  SERP: {se.get('error')}")
    print(f"  chain_ok={rep.get('chain_ok')}")


def main() -> int:
    ap = argparse.ArgumentParser(description="End-to-end monitoring smoke test for a project")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--site", help="project slug")
    grp.add_argument("--all", action="store_true", help="all projects")
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--no-serp", action="store_true", help="skip SerpApi stages (saves quota)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    slugs = ([os.path.basename(os.path.dirname(p)) for p in sorted(glob.glob("projects/*/business-context.json"))]
             if args.all else [args.site])
    reports = [check_site(s, days=args.days, include_serp=not args.no_serp) for s in slugs]

    if args.json:
        print(json.dumps(reports if args.all else reports[0], indent=2, ensure_ascii=False))
    else:
        for r in reports:
            _print_human(r)
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
