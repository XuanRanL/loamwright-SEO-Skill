"""
scripts/monitor/rank_tracker.py — T+7/14/30/90 rank tracking with traffic impact.

Implements the SKILL.md spec for subskills/monitor/rank-tracker.

Workflow:
  1. Read project's published articles (last 90 days)
  2. For each: determine which check window applies (T+7, T+14, T+30, T+90)
  3. Pull GSC API data for current period vs baseline
  4. Compute rank delta + traffic impact (using #1→#2 = -55% click share table)
  5. Save to projects/{slug}/rank-history/{date}.json
  6. If any URL dropped >5 positions: flag for refresh queue

CLI:
    python -m scripts.monitor.rank_tracker --site my-site
    python -m scripts.monitor.rank_tracker --site my-site --window T+30
    python -m scripts.monitor.rank_tracker --all-sites --json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts._core.file_bus import PLUGIN_ROOT
from scripts.monitor import gsc_api_ingest


# Click-share table per claude-blog data (used to convert position → expected traffic loss)
CLICK_SHARE_BY_POSITION: dict[int, float] = {
    1: 0.31, 2: 0.14, 3: 0.09, 4: 0.06, 5: 0.04,
    6: 0.03, 7: 0.025, 8: 0.022, 9: 0.02, 10: 0.018,
}

# Default to ~0.005 for positions 11-20
def _click_share(pos: float) -> float:
    if pos <= 0:
        return 0.0
    p = int(round(pos))
    if p in CLICK_SHARE_BY_POSITION:
        return CLICK_SHARE_BY_POSITION[p]
    if p <= 20:
        return 0.005
    return 0.001


@dataclass
class RankRow:
    article_slug: str
    url: str
    published_at: str
    days_since_publish: int
    window: str               # "T+7" | "T+14" | "T+30" | "T+90" | "ongoing"
    baseline_position: float = 0.0
    current_position: float = 0.0
    position_delta: float = 0.0       # current - baseline (negative = improved)
    current_clicks: int = 0
    current_impressions: int = 0
    expected_clicks_at_baseline_pos: int = 0
    traffic_impact_pct: float = 0.0   # vs expected at baseline pos
    flag_drop: bool = False           # True if dropped >5 positions
    flag_no_data: bool = False
    new_queries: list[str] = field(default_factory=list)
    lost_queries: list[str] = field(default_factory=list)


def _window_for_age(days: int) -> str:
    if days <= 10:
        return "T+7"
    if days <= 17:
        return "T+14"
    if days <= 35:
        return "T+30"
    if days <= 95:
        return "T+90"
    return "ongoing"


def _load_articles(site_slug: str) -> list[dict]:
    """Read published articles from project archive."""
    articles_dir = PLUGIN_ROOT / "projects" / site_slug / "articles"
    if not articles_dir.is_dir():
        return []
    out = []
    for art_dir in articles_dir.iterdir():
        if not art_dir.is_dir():
            continue
        log = art_dir / "publish-log.json"
        if not log.exists():
            continue
        try:
            data = json.loads(log.read_text(encoding="utf-8"))
            out.append({
                "slug": art_dir.name,
                "url": data.get("post_url", ""),
                "published_at": data.get("published_at", ""),
                "queries_target": data.get("queries_target", []),
            })
        except (OSError, json.JSONDecodeError):
            continue
    return out


def _load_baseline(site_slug: str) -> dict:
    """SEO baseline from /init Stage 7 (or first GSC pull)."""
    base = PLUGIN_ROOT / "projects" / site_slug / "research" / "seo-baseline.json"
    if not base.exists():
        return {}
    try:
        return json.loads(base.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_latest_gsc(site_slug: str) -> dict:
    """Most recent GSC ingest by_url."""
    index = PLUGIN_ROOT / "memory" / "metrics-index.json"
    if not index.exists():
        return {}
    try:
        idx = json.loads(index.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    site = (idx.get("sites") or {}).get(site_slug, {})
    ingests = site.get("ingests") or []
    if not ingests:
        return {}
    ingests = [i for i in ingests if i.get("source", "").startswith("gsc")]
    if not ingests:
        return {}
    ingests.sort(key=lambda e: e.get("end_date", e.get("ingested_at", "")), reverse=True)
    try:
        data = json.loads(Path(ingests[0]["path"]).read_text(encoding="utf-8"))
        return data.get("by_url") or {}
    except (OSError, json.JSONDecodeError):
        return {}


def track_site(site_slug: str) -> list[RankRow]:
    """Compute rank rows for all articles."""
    articles = _load_articles(site_slug)
    if not articles:
        return []

    by_url = _load_latest_gsc(site_slug)
    baseline = _load_baseline(site_slug)
    baseline_by_url = baseline.get("by_url") or {}

    now = datetime.now(timezone.utc)
    rows: list[RankRow] = []

    for art in articles:
        url = art["url"]
        days = 0
        if art["published_at"]:
            try:
                pub = datetime.fromisoformat(art["published_at"].replace("Z", "+00:00"))
                days = (now - pub).days
            except (ValueError, TypeError):
                pass

        window = _window_for_age(days)
        current = by_url.get(url, {})
        baseline_entry = baseline_by_url.get(url, {})

        cur_pos = float(current.get("avg_position", 0.0))
        base_pos = float(baseline_entry.get("avg_position", 0.0)) or cur_pos
        delta = cur_pos - base_pos if (cur_pos > 0 and base_pos > 0) else 0.0

        cur_clicks = int(current.get("clicks", 0))
        cur_imp = int(current.get("impressions", 0))

        expected_clicks_at_baseline = (
            int(cur_imp * _click_share(base_pos)) if base_pos > 0 and cur_imp > 0 else 0
        )
        if expected_clicks_at_baseline > 0:
            impact = (cur_clicks - expected_clicks_at_baseline) / expected_clicks_at_baseline * 100
        else:
            impact = 0.0

        # Query diff
        cur_queries = {q["q"] for q in current.get("queries", []) or []}
        baseline_queries = {q["q"] for q in baseline_entry.get("queries", []) or []}
        new_q = sorted(cur_queries - baseline_queries)[:10]
        lost_q = sorted(baseline_queries - cur_queries)[:10]

        rows.append(RankRow(
            article_slug=art["slug"],
            url=url,
            published_at=art["published_at"],
            days_since_publish=days,
            window=window,
            baseline_position=round(base_pos, 2),
            current_position=round(cur_pos, 2),
            position_delta=round(delta, 2),
            current_clicks=cur_clicks,
            current_impressions=cur_imp,
            expected_clicks_at_baseline_pos=expected_clicks_at_baseline,
            traffic_impact_pct=round(impact, 1),
            flag_drop=delta > 5,
            flag_no_data=(cur_pos == 0 and cur_clicks == 0),
            new_queries=new_q,
            lost_queries=lost_q,
        ))

    return rows


def save_rank_history(site_slug: str, rows: list[RankRow]) -> Path:
    out_dir = PLUGIN_ROOT / "projects" / site_slug / "audits" / "rank-history"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    out_path = out_dir / f"{today}.json"
    out_path.write_text(json.dumps({
        "site_slug": site_slug,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "rows": [asdict(r) for r in rows],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="T+7/14/30/90 rank tracker")
    ap.add_argument("--site")
    ap.add_argument("--all-sites", action="store_true")
    ap.add_argument("--window", choices=["T+7", "T+14", "T+30", "T+90"],
                    help="Filter to only this window")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.site and not args.all_sites:
        print("Need --site or --all-sites", file=sys.stderr)
        return 2

    if args.all_sites:
        sites = sorted(p.name for p in (PLUGIN_ROOT / "projects").iterdir() if p.is_dir())
    else:
        sites = [args.site]

    all_results = []
    for slug in sites:
        rows = track_site(slug)
        if args.window:
            rows = [r for r in rows if r.window == args.window]
        if rows:
            path = save_rank_history(slug, rows)
            all_results.append({"site": slug, "rows": len(rows), "path": str(path)})

    if args.json:
        # Detailed JSON per site
        out = {}
        for slug in sites:
            rows = track_site(slug)
            if args.window:
                rows = [r for r in rows if r.window == args.window]
            out[slug] = [asdict(r) for r in rows]
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        for r in all_results:
            print(f"  ✓ {r['site']}: {r['rows']} articles tracked → {r['path']}")
            rows = track_site(r['site'])
            drops = [x for x in rows if x.flag_drop]
            if drops:
                print(f"    ⚠ {len(drops)} article(s) dropped >5 positions:")
                for d in drops[:5]:
                    print(f"      {d.position_delta:+.1f}  {d.article_slug}  ({d.baseline_position:.1f}→{d.current_position:.1f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
