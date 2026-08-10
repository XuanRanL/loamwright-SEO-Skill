"""
scripts/_core/fleet_view.py — Multi-site agency dashboard.

The /fleet command. For someone managing 100+ sites across multiple clients,
this is the daily landing page:
  - Total: N sites, M articles published this month, $X spent
  - Health: sites with drift alerts / lost AI citations / cost overruns
  - By vertical: B2B / B2C / publisher / ecom breakdown
  - By client: aggregate cost + performance per client
  - Top movers: 5 sites with biggest clicks gain / drop

CLI:
    python -m scripts._core.fleet_view                      # default summary
    python -m scripts._core.fleet_view --client client-a
    python -m scripts._core.fleet_view --vertical b2b-saas
    python -m scripts._core.fleet_view --json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from scripts._core import cost_ledger
from scripts._core.file_bus import PLUGIN_ROOT


@dataclass
class SiteSummary:
    site_slug: str
    client: str = ""
    vertical: str = ""               # b2b-saas / b2c-ecom / publisher / agency
    site_url: str = ""
    article_count: int = 0
    articles_last_30d: int = 0
    impressions_30d: int = 0
    clicks_30d: int = 0
    avg_position: float = 0.0
    ai_citations: dict[str, int] = field(default_factory=dict)
    drift_alerts: int = 0
    cost_30d_usd: str = "0.00"
    health: str = "ok"               # ok / watch / critical
    health_reasons: list[str] = field(default_factory=list)


@dataclass
class FleetReport:
    generated_at: str
    total_sites: int
    total_articles: int
    articles_last_30d: int
    total_impressions_30d: int
    total_clicks_30d: int
    total_cost_30d_usd: str
    by_vertical: dict[str, int] = field(default_factory=dict)
    by_client: dict[str, dict] = field(default_factory=dict)
    by_health: dict[str, int] = field(default_factory=dict)
    sites: list[SiteSummary] = field(default_factory=list)
    top_climbers: list[str] = field(default_factory=list)
    top_losers: list[str] = field(default_factory=list)


def _load_project_meta(site_slug: str) -> dict:
    """Read project.yaml or fallback to project.json."""
    proj_dir = PLUGIN_ROOT / "projects" / site_slug
    for fname in ("project.yaml", "project.json"):
        p = proj_dir / fname
        if not p.exists():
            continue
        try:
            if fname.endswith(".yaml"):
                import yaml
                return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


def _site_cost_30d(site_slug: str) -> Decimal:
    """Sum cost-ledger entries for this site over last 30 days."""
    ledger = cost_ledger.LEDGER_FILE
    if not ledger.exists():
        return Decimal("0")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    total = Decimal("0")
    try:
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
                if e.get("project_slug") != site_slug:
                    continue
                ts = datetime.fromisoformat(e["timestamp"])
                if ts < cutoff:
                    continue
                total += Decimal(e.get("cost_usd", "0"))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    except OSError:
        return Decimal("0")
    return total


def _site_articles(site_slug: str) -> tuple[int, int]:
    """Return (total, published_last_30d)."""
    arts_dir = PLUGIN_ROOT / "projects" / site_slug / "articles"
    if not arts_dir.is_dir():
        return 0, 0
    total = 0
    recent = 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    for d in arts_dir.iterdir():
        log = d / "publish-log.json"
        if not log.exists():
            continue
        total += 1
        try:
            data = json.loads(log.read_text(encoding="utf-8"))
            if (data.get("published_at", "") or "")[:10] >= cutoff:
                recent += 1
        except (OSError, json.JSONDecodeError):
            continue
    return total, recent


def _site_gsc_30d(site_slug: str) -> tuple[int, int, float]:
    """Aggregate latest GSC ingest (≤30 days)."""
    metrics_dir = PLUGIN_ROOT / "projects" / site_slug / "metrics"
    if not metrics_dir.is_dir():
        return 0, 0, 0.0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    imp = clk = 0
    pos_sum = 0.0
    pos_count = 0
    for f in metrics_dir.glob("gsc-*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if (data.get("end_date") or "") < cutoff:
                continue
            for u in (data.get("by_url") or {}).values():
                imp += u.get("impressions", 0)
                clk += u.get("clicks", 0)
                if u.get("avg_position", 0) > 0:
                    pos_sum += u["avg_position"] * max(u.get("impressions", 1), 1)
                    pos_count += max(u.get("impressions", 1), 1)
        except (OSError, json.JSONDecodeError):
            continue
    avg_pos = pos_sum / pos_count if pos_count else 0.0
    return imp, clk, round(avg_pos, 2)


def _site_drift_alerts(site_slug: str) -> int:
    drift_dir = PLUGIN_ROOT / "projects" / site_slug / "audits" / "drift-reports"
    if not drift_dir.is_dir():
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    n = 0
    for f in drift_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            ts = (data.get("current_captured_at") or "")[:10]
            if ts >= cutoff and data.get("overall_severity") in ("critical", "high"):
                n += 1
        except (OSError, json.JSONDecodeError):
            continue
    return n


def _site_ai_citations(site_slug: str) -> dict[str, int]:
    history = PLUGIN_ROOT / "memory" / "ai-citation-history.json"
    if not history.exists():
        return {}
    try:
        h = json.loads(history.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    last = (h.get("sites") or {}).get(site_slug, {}).get("last_run", {})
    by_url = last.get("by_url", {}) or {}
    counts: dict[str, int] = {}
    for engines in by_url.values():
        for eng in engines:
            counts[eng] = counts.get(eng, 0) + 1
    return counts


def _decide_health(site: SiteSummary) -> tuple[str, list[str]]:
    """Determine overall health flag."""
    reasons = []
    if site.drift_alerts >= 3:
        reasons.append(f"{site.drift_alerts} drift alerts")
    if site.clicks_30d == 0 and site.article_count > 0:
        reasons.append("No clicks last 30d despite publishing")
    if Decimal(site.cost_30d_usd) > Decimal("100"):
        reasons.append(f"High spend (${site.cost_30d_usd})")
    if not reasons:
        return "ok", []
    if len(reasons) >= 2 or site.drift_alerts >= 5:
        return "critical", reasons
    return "watch", reasons


def build_site_summary(site_slug: str) -> SiteSummary:
    meta = _load_project_meta(site_slug)
    total, recent = _site_articles(site_slug)
    imp, clk, pos = _site_gsc_30d(site_slug)
    drift = _site_drift_alerts(site_slug)
    ai = _site_ai_citations(site_slug)
    cost = _site_cost_30d(site_slug)

    s = SiteSummary(
        site_slug=site_slug,
        client=meta.get("client", ""),
        vertical=meta.get("vertical", ""),
        site_url=meta.get("site_url", ""),
        article_count=total,
        articles_last_30d=recent,
        impressions_30d=imp,
        clicks_30d=clk,
        avg_position=pos,
        ai_citations=ai,
        drift_alerts=drift,
        cost_30d_usd=str(cost.quantize(Decimal("0.01"))),
    )
    s.health, s.health_reasons = _decide_health(s)
    return s


def build_fleet_report(
    *,
    client_filter: str = "",
    vertical_filter: str = "",
) -> FleetReport:
    projects_dir = PLUGIN_ROOT / "projects"
    if not projects_dir.is_dir():
        return FleetReport(generated_at=datetime.now(timezone.utc).isoformat(),
                           total_sites=0, total_articles=0, articles_last_30d=0,
                           total_impressions_30d=0, total_clicks_30d=0,
                           total_cost_30d_usd="0.00")

    sites = []
    for p in sorted(projects_dir.iterdir()):
        if not p.is_dir():
            continue
        if not (p / "project.yaml").exists() and not (p / "project.json").exists():
            continue
        s = build_site_summary(p.name)
        if client_filter and s.client != client_filter:
            continue
        if vertical_filter and s.vertical != vertical_filter:
            continue
        sites.append(s)

    total_imp = sum((s.impressions_30d for s in sites), 0)
    total_clk = sum((s.clicks_30d for s in sites), 0)
    total_articles = sum((s.article_count for s in sites), 0)
    recent_articles = sum((s.articles_last_30d for s in sites), 0)
    total_cost = sum((Decimal(s.cost_30d_usd) for s in sites), Decimal("0"))

    by_vertical: dict[str, int] = {}
    by_client: dict[str, dict] = {}
    by_health = {"ok": 0, "watch": 0, "critical": 0}

    for s in sites:
        by_vertical[s.vertical or "uncategorized"] = (
            by_vertical.get(s.vertical or "uncategorized", 0) + 1
        )
        client = s.client or "own"
        c = by_client.setdefault(client, {
            "site_count": 0, "clicks_30d": 0,
            "cost_30d_usd": Decimal("0"), "drift_alerts": 0,
        })
        c["site_count"] += 1
        c["clicks_30d"] += s.clicks_30d
        c["cost_30d_usd"] += Decimal(s.cost_30d_usd)
        c["drift_alerts"] += s.drift_alerts
        by_health[s.health] += 1

    # Stringify client cost
    for c in by_client.values():
        c["cost_30d_usd"] = str(c["cost_30d_usd"].quantize(Decimal("0.01")))

    # Top climbers / losers — sort by clicks (need historical comparison ideally;
    # for now use absolute clicks as a proxy for "movers")
    top_climbers = sorted(sites, key=lambda x: -x.clicks_30d)[:5]
    top_losers = [s for s in sites if s.drift_alerts > 0 or s.health == "critical"][:5]

    return FleetReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_sites=len(sites),
        total_articles=total_articles,
        articles_last_30d=recent_articles,
        total_impressions_30d=total_imp,
        total_clicks_30d=total_clk,
        total_cost_30d_usd=str(total_cost.quantize(Decimal("0.01"))),
        by_vertical=by_vertical,
        by_client=by_client,
        by_health=by_health,
        sites=sites,
        top_climbers=[s.site_slug for s in top_climbers],
        top_losers=[s.site_slug for s in top_losers],
    )


def _fmt_fleet(r: FleetReport) -> str:
    out = ["━━ Fleet view ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    out.append(f"  Generated:    {r.generated_at[:19]}Z")
    out.append(f"  Sites:        {r.total_sites}  ({r.articles_last_30d} new articles / 30d)")
    out.append(f"  Total articles: {r.total_articles}")
    out.append(f"  Impressions:  {r.total_impressions_30d:,} / 30d")
    out.append(f"  Clicks:       {r.total_clicks_30d:,} / 30d")
    out.append(f"  Cost:         ${r.total_cost_30d_usd} / 30d")
    out.append("")
    out.append("  Health:")
    for k, v in r.by_health.items():
        icon = {"ok": "✓", "watch": "⚠", "critical": "🔴"}.get(k, "•")
        out.append(f"    {icon} {k:<10s} {v}")
    out.append("")
    out.append("  By vertical:")
    for v, n in sorted(r.by_vertical.items(), key=lambda x: -x[1]):
        out.append(f"    {n:>3d}  {v}")
    out.append("")
    out.append("  By client:")
    for c, info in sorted(r.by_client.items(), key=lambda x: -x[1]["site_count"]):
        out.append(f"    {info['site_count']:>3d} sites  ${info['cost_30d_usd']:>8s}  "
                   f"{info['clicks_30d']:>6d} clk  "
                   f"({info['drift_alerts']} drift)  {c}")
    out.append("")
    out.append("  Top performers (30d clicks):")
    for slug in r.top_climbers:
        s = next((x for x in r.sites if x.site_slug == slug), None)
        if s:
            out.append(f"    {s.clicks_30d:>5d} clk  pos {s.avg_position:>4.1f}  {s.site_slug}")
    if r.top_losers:
        out.append("")
        out.append("  Needs attention:")
        for slug in r.top_losers:
            s = next((x for x in r.sites if x.site_slug == slug), None)
            if s:
                reasons = "; ".join(s.health_reasons) or "n/a"
                out.append(f"    [{s.health}]  {s.site_slug}  ({reasons})")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Multi-site fleet dashboard")
    ap.add_argument("--client", default="", help="Filter by client name")
    ap.add_argument("--vertical", default="", help="Filter by vertical")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = build_fleet_report(client_filter=args.client, vertical_filter=args.vertical)

    if args.json:
        # Convert sites
        out = asdict(r)
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    else:
        print(_fmt_fleet(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
