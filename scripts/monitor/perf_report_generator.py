"""
scripts/monitor/perf_report_generator.py — Period performance report.

Aggregates across rank-history + ai-citations + drift-reports + refresh-queue
+ change-log to produce a human-readable executive summary per site.

Period: week / month / quarter / year.
Output: projects/{slug}/perf-{period}-{date}.md

Optionally generates a cross-portfolio rollup (--fleet flag).

CLI:
    python -m scripts.monitor.perf_report_generator --site my-site --period month
    python -m scripts.monitor.perf_report_generator --fleet --period quarter
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts._core.file_bus import PLUGIN_ROOT


@dataclass
class PerfReport:
    site_slug: str
    period: str
    period_start: str
    period_end: str
    prev_period_start: str
    prev_period_end: str
    total_impressions: int = 0
    total_clicks: int = 0
    avg_position: float = 0.0
    impressions_delta_pct: float = 0.0
    clicks_delta_pct: float = 0.0
    position_delta: float = 0.0
    ai_citations: dict[str, int] = field(default_factory=dict)
    new_articles_count: int = 0
    new_articles_page1_count: int = 0
    new_articles_aio_count: int = 0
    refresh_count: int = 0
    drift_alert_count: int = 0
    lost_ai_citations: int = 0
    urgent_refresh_count: int = 0
    recommendations: list[str] = field(default_factory=list)
    output_path: str = ""


def _period_dates(period: str) -> tuple[str, str, str, str]:
    """Return (cur_start, cur_end, prev_start, prev_end) ISO strings."""
    today = datetime.now(timezone.utc).date()
    if period == "week":
        cur_end = today
        cur_start = today - timedelta(days=6)
        prev_end = cur_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=6)
    elif period == "month":
        cur_end = today
        cur_start = today - timedelta(days=29)
        prev_end = cur_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=29)
    elif period == "quarter":
        cur_end = today
        cur_start = today - timedelta(days=89)
        prev_end = cur_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=89)
    elif period == "year":
        cur_end = today
        cur_start = today - timedelta(days=364)
        prev_end = cur_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=364)
    else:
        raise ValueError(f"Unknown period: {period}")
    return (cur_start.isoformat(), cur_end.isoformat(),
            prev_start.isoformat(), prev_end.isoformat())


def _pct_delta(prev: float | int, cur: float | int) -> float:
    if prev == 0:
        return 0.0 if cur == 0 else 100.0
    return round((cur - prev) / prev * 100, 1)


def _gather_gsc(site_slug: str, start: str, end: str) -> dict:
    """Aggregate GSC ingest files falling within [start, end]."""
    metrics_dir = PLUGIN_ROOT / "projects" / site_slug / "metrics"
    if not metrics_dir.is_dir():
        return {"impressions": 0, "clicks": 0, "position_sum": 0.0, "position_count": 0}
    totals = {"impressions": 0, "clicks": 0, "position_sum": 0.0, "position_count": 0}
    for f in metrics_dir.glob("gsc-*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            end_date = data.get("end_date") or data.get("date_range", "")
            if not (start <= end_date <= end):
                continue
            for url_data in (data.get("by_url") or {}).values():
                totals["impressions"] += url_data.get("impressions", 0)
                totals["clicks"] += url_data.get("clicks", 0)
                pos = url_data.get("avg_position", 0)
                imp = url_data.get("impressions", 0)
                if pos > 0 and imp > 0:
                    totals["position_sum"] += pos * imp
                    totals["position_count"] += imp
        except (OSError, json.JSONDecodeError):
            continue
    return totals


def _gather_ai_citations(site_slug: str, end: str) -> dict[str, int]:
    """Count current AI citations per engine."""
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


def _gather_new_articles(site_slug: str, start: str, end: str) -> int:
    """Count articles published in window."""
    articles_dir = PLUGIN_ROOT / "projects" / site_slug / "articles"
    if not articles_dir.is_dir():
        return 0
    n = 0
    for d in articles_dir.iterdir():
        log = d / "publish-log.json"
        if not log.exists():
            continue
        try:
            data = json.loads(log.read_text(encoding="utf-8"))
            pub = (data.get("published_at") or "")[:10]
            if start <= pub <= end:
                n += 1
        except (OSError, json.JSONDecodeError):
            continue
    return n


def _gather_drift_alerts(site_slug: str, start: str, end: str) -> int:
    """Count drift reports with critical/high severity."""
    drift_dir = PLUGIN_ROOT / "projects" / site_slug / "audits" / "drift-reports"
    if not drift_dir.is_dir():
        return 0
    n = 0
    for f in drift_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            date_str = (data.get("current_captured_at") or "")[:10]
            if not (start <= date_str <= end):
                continue
            if data.get("overall_severity") in ("critical", "high"):
                n += 1
        except (OSError, json.JSONDecodeError):
            continue
    return n


def generate(site_slug: str, period: str = "month") -> PerfReport:
    cs, ce, ps, pe = _period_dates(period)

    cur = _gather_gsc(site_slug, cs, ce)
    prev = _gather_gsc(site_slug, ps, pe)

    avg_pos_cur = (cur["position_sum"] / cur["position_count"]) if cur["position_count"] else 0.0
    avg_pos_prev = (prev["position_sum"] / prev["position_count"]) if prev["position_count"] else 0.0

    new_articles = _gather_new_articles(site_slug, cs, ce)
    drift_alerts = _gather_drift_alerts(site_slug, cs, ce)
    ai_citations = _gather_ai_citations(site_slug, ce)

    recommendations = []
    if cur["clicks"] < prev["clicks"] * 0.85:
        recommendations.append("⚠ Clicks dropped >15% vs prev period; investigate top losers")
    if drift_alerts >= 3:
        recommendations.append(f"⚠ {drift_alerts} drift alerts; review refresh queue")
    if new_articles == 0:
        recommendations.append("• No new articles this period; consider publishing cadence")
    if not ai_citations:
        recommendations.append("• No AI citations tracked; run ai_citation_tracker.py")

    report = PerfReport(
        site_slug=site_slug,
        period=period,
        period_start=cs, period_end=ce,
        prev_period_start=ps, prev_period_end=pe,
        total_impressions=cur["impressions"],
        total_clicks=cur["clicks"],
        avg_position=round(avg_pos_cur, 2),
        impressions_delta_pct=_pct_delta(prev["impressions"], cur["impressions"]),
        clicks_delta_pct=_pct_delta(prev["clicks"], cur["clicks"]),
        position_delta=round(avg_pos_cur - avg_pos_prev, 2),
        ai_citations=ai_citations,
        new_articles_count=new_articles,
        drift_alert_count=drift_alerts,
        recommendations=recommendations,
    )

    # Render markdown
    md = render_md(report)
    out_dir = PLUGIN_ROOT / "projects" / site_slug / "audits"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"perf-{period}-{ce}.md"
    out_path.write_text(md, encoding="utf-8")
    report.output_path = str(out_path)
    return report


def render_md(r: PerfReport) -> str:
    lines = [
        f"# Performance Report — {r.site_slug} — {r.period} ending {r.period_end}",
        "",
        f"_Period: {r.period_start} → {r.period_end} (vs {r.prev_period_start} → {r.prev_period_end})_",
        "",
        "## Headlines",
        "",
        f"- Total impressions: **{r.total_impressions:,}** ({r.impressions_delta_pct:+.1f}% vs prev period)",
        f"- Total clicks: **{r.total_clicks:,}** ({r.clicks_delta_pct:+.1f}%)",
        f"- Avg position: **{r.avg_position:.1f}** ({r.position_delta:+.2f})",
    ]

    if r.ai_citations:
        ai_summary = ", ".join(f"{eng}:{n}" for eng, n in r.ai_citations.items())
        lines.append(f"- AI citations: {ai_summary}")

    lines += [
        "",
        "## Content activity",
        "",
        f"- New articles published: {r.new_articles_count}",
        "",
        "## Issues",
        "",
        f"- Drift alerts (high/critical): {r.drift_alert_count}",
    ]

    if r.recommendations:
        lines += ["", "## Recommendations", ""]
        lines += [f"- {rec}" for rec in r.recommendations]

    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Period performance report")
    ap.add_argument("--site")
    ap.add_argument("--fleet", action="store_true",
                    help="Generate report for all projects")
    ap.add_argument("--period", choices=["week", "month", "quarter", "year"],
                    default="month")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.site and not args.fleet:
        print("Need --site or --fleet", file=sys.stderr)
        return 2

    sites = (
        sorted(p.name for p in (PLUGIN_ROOT / "projects").iterdir() if p.is_dir())
        if args.fleet else [args.site]
    )

    reports = []
    for slug in sites:
        try:
            r = generate(slug, args.period)
            reports.append(r)
            if not args.json:
                print(f"  ✓ {slug}: {r.total_clicks:,} clicks ({r.clicks_delta_pct:+.1f}%) "
                      f"→ {Path(r.output_path).name}")
        except Exception as e:
            print(f"  ✗ {slug}: {e}", file=sys.stderr)

    if args.json:
        print(json.dumps([asdict(r) for r in reports], indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
