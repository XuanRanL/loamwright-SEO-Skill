"""
scripts/monitor/outcome_tagger.py — Tag published articles as winner / mid / loser.

Closed-loop feedback. Joins:
  - GSC metrics (clicks, impressions, average position) from gsc_csv_ingest
  - AI citation probe results (ai_search_probe.py)
  - Days since publish (controls for fairness — don't judge 3-day-old articles)

Decision rules (configurable, default tuned for personal-use SEO):
  WINNER: avg_position ≤10 AND (clicks ≥30 OR AI-cited in ≥2 engines)
  MID:    avg_position ≤30 AND (clicks ≥5  OR AI-cited in ≥1 engine)
  LOSER:  Neither (after ≥30 days post-publish window)
  TOO_NEW: Published <30 days ago (not yet judgeable)

Output:
  projects/{slug}/outcomes.json — per-article tag + drivers + features

This is the foundation for brand_auto_tuner.py (P1) which finds the patterns
distinguishing winners from losers.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from scripts._core.file_bus import PLUGIN_ROOT


Outcome = Literal["winner", "mid", "loser", "too_new", "no_data"]


@dataclass
class ArticleOutcome:
    article_url: str
    article_slug: str
    site_slug: str
    published_at: str
    days_since_publish: int
    outcome: Outcome
    avg_position: float = 0.0
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    ai_citations_count: int = 0       # how many AI engines cite this URL
    ai_citation_engines: list[str] = field(default_factory=list)
    drivers: list[str] = field(default_factory=list)   # why this verdict
    features: dict = field(default_factory=dict)        # for tuner — extracted features
    last_evaluated_at: str = ""


def _load_latest_gsc(site_slug: str) -> dict:
    """Load most recent GSC ingest by_url map."""
    index_path = PLUGIN_ROOT / "memory" / "metrics-index.json"
    if not index_path.exists():
        return {}
    try:
        idx = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    site = (idx.get("sites") or {}).get(site_slug)
    if not site:
        return {}
    ingests = site.get("ingests") or []
    if not ingests:
        return {}
    ingests.sort(key=lambda e: e.get("date_range", ""), reverse=True)
    latest = ingests[0]
    try:
        data = json.loads(Path(latest["path"]).read_text(encoding="utf-8"))
        return data.get("by_url") or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _load_articles_index(site_slug: str) -> list[dict]:
    """Read published articles for the site from project archive."""
    articles_dir = PLUGIN_ROOT / "projects" / site_slug / "articles"
    if not articles_dir.is_dir():
        return []
    articles = []
    for art_dir in articles_dir.iterdir():
        if not art_dir.is_dir():
            continue
        meta_file = art_dir / "publish-log.json"
        if not meta_file.exists():
            continue
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            articles.append({
                "slug": art_dir.name,
                "url": data.get("post_url", ""),
                "published_at": data.get("published_at", ""),
                "features_path": art_dir / "features.json",
                "review_path": art_dir / "review.json",
            })
        except (OSError, json.JSONDecodeError):
            continue
    return articles


def _load_ai_probes(site_slug: str) -> dict:
    """Load AI engine probe results — which articles are cited by which engines."""
    probes_dir = PLUGIN_ROOT / "projects" / site_slug / "research" / "ai-probes"
    if not probes_dir.is_dir():
        return {}
    result: dict = {}  # url -> {engines: [...]}
    for f in probes_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            # Probe data shape: {"engine": "chatgpt", "citations": [{"url": "..."}]}
            engine = data.get("engine", "unknown")
            for cit in data.get("citations", []) or []:
                u = cit.get("url", "")
                if u:
                    result.setdefault(u, {"engines": []})
                    if engine not in result[u]["engines"]:
                        result[u]["engines"].append(engine)
        except (OSError, json.JSONDecodeError):
            continue
    return result


def _extract_features(art: dict) -> dict:
    """Extract content features for the tuner to correlate against outcome."""
    features = {}
    fpath = art.get("features_path")
    if fpath and fpath.exists():
        try:
            f = json.loads(fpath.read_text(encoding="utf-8"))
            # Take a flat selection of features
            for key in [
                "format", "word_count", "h2_count", "h3_count",
                "citation_count", "tier1_citation_count",
                "image_count", "table_count", "list_count",
                "info_gain_marker_count", "first_person_pct",
                "ai_slop_score", "core_eeat_score", "cite_score",
                "primary_keyword", "voice", "purpose", "ymyl",
            ]:
                if key in f:
                    features[key] = f[key]
        except (OSError, json.JSONDecodeError):
            pass
    rpath = art.get("review_path")
    if rpath and rpath.exists():
        try:
            r = json.loads(rpath.read_text(encoding="utf-8"))
            features["reviewer_score"] = r.get("score")
        except (OSError, json.JSONDecodeError):
            pass
    return features


def _judge(
    days_old: int,
    pos: float,
    clicks: int,
    ai_count: int,
    *,
    min_days: int = 30,
    winner_pos: float = 10.0,
    winner_clicks: int = 30,
    winner_ai_engines: int = 2,
    mid_pos: float = 30.0,
    mid_clicks: int = 5,
    mid_ai_engines: int = 1,
) -> tuple[Outcome, list[str]]:
    """Apply decision rules."""
    drivers = []

    if days_old < min_days:
        drivers.append(f"too_new (published {days_old}d ago, need ≥{min_days}d)")
        return "too_new", drivers

    if pos == 0 and clicks == 0 and ai_count == 0:
        drivers.append("no_data (not in GSC nor AI probes)")
        return "no_data", drivers

    is_winner_pos = 0 < pos <= winner_pos
    is_winner_clicks = clicks >= winner_clicks
    is_winner_ai = ai_count >= winner_ai_engines

    if is_winner_pos and (is_winner_clicks or is_winner_ai):
        drivers.append(f"top-{int(winner_pos)} rank (pos {pos:.1f})")
        if is_winner_clicks:
            drivers.append(f"strong traffic ({clicks} clicks)")
        if is_winner_ai:
            drivers.append(f"AI-cited in {ai_count} engines")
        return "winner", drivers

    is_mid_pos = 0 < pos <= mid_pos
    is_mid_clicks = clicks >= mid_clicks
    is_mid_ai = ai_count >= mid_ai_engines

    if (is_mid_pos and is_mid_clicks) or is_mid_ai:
        if is_mid_pos:
            drivers.append(f"ranked (pos {pos:.1f})")
        if is_mid_clicks:
            drivers.append(f"mid traffic ({clicks} clicks)")
        if is_mid_ai:
            drivers.append(f"AI-cited in {ai_count} engines")
        return "mid", drivers

    drivers.append(f"low rank (pos {pos:.1f}), {clicks} clicks, AI {ai_count} engines")
    return "loser", drivers


def tag_all(site_slug: str) -> list[ArticleOutcome]:
    """Tag every published article for a site."""
    gsc_by_url = _load_latest_gsc(site_slug)
    ai_by_url = _load_ai_probes(site_slug)
    articles = _load_articles_index(site_slug)

    now = datetime.now(timezone.utc)
    results: list[ArticleOutcome] = []

    for art in articles:
        url = art["url"]
        gsc = gsc_by_url.get(url, {})

        # Some GSC entries use HTTPS canonical; try also without trailing slash
        if not gsc:
            for variant in (url.rstrip("/"), url + "/"):
                if variant in gsc_by_url:
                    gsc = gsc_by_url[variant]
                    break

        ai = ai_by_url.get(url, {})

        # Days since publish
        days_old = 0
        if art["published_at"]:
            try:
                pub = datetime.fromisoformat(art["published_at"].replace("Z", "+00:00"))
                days_old = (now - pub).days
            except (ValueError, TypeError):
                pass

        ai_engines = ai.get("engines") or []
        outcome, drivers = _judge(
            days_old=days_old,
            pos=gsc.get("avg_position", 0.0),
            clicks=gsc.get("clicks", 0),
            ai_count=len(ai_engines),
        )

        results.append(ArticleOutcome(
            article_url=url,
            article_slug=art["slug"],
            site_slug=site_slug,
            published_at=art["published_at"],
            days_since_publish=days_old,
            outcome=outcome,
            avg_position=gsc.get("avg_position", 0.0),
            clicks=gsc.get("clicks", 0),
            impressions=gsc.get("impressions", 0),
            ctr=gsc.get("ctr", 0.0),
            ai_citations_count=len(ai_engines),
            ai_citation_engines=ai_engines,
            drivers=drivers,
            features=_extract_features(art),
            last_evaluated_at=now.isoformat(),
        ))

    return results


def save_outcomes(site_slug: str, outcomes: list[ArticleOutcome]) -> Path:
    """Write outcomes.json for the site."""
    out_path = PLUGIN_ROOT / "projects" / site_slug / "audits" / "outcomes.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "site_slug": site_slug,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "winner": sum(1 for o in outcomes if o.outcome == "winner"),
            "mid": sum(1 for o in outcomes if o.outcome == "mid"),
            "loser": sum(1 for o in outcomes if o.outcome == "loser"),
            "too_new": sum(1 for o in outcomes if o.outcome == "too_new"),
            "no_data": sum(1 for o in outcomes if o.outcome == "no_data"),
        },
        "outcomes": [asdict(o) for o in outcomes],
    }
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Tag articles as winner/mid/loser")
    ap.add_argument("--site", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    outcomes = tag_all(args.site)
    if not outcomes:
        print(f"No published articles found for {args.site}.", file=sys.stderr)
        return 1

    out_path = save_outcomes(args.site, outcomes)

    if args.json:
        print(json.dumps({
            "site_slug": args.site,
            "output_path": str(out_path),
            "counts": {
                "winner": sum(1 for o in outcomes if o.outcome == "winner"),
                "mid": sum(1 for o in outcomes if o.outcome == "mid"),
                "loser": sum(1 for o in outcomes if o.outcome == "loser"),
                "too_new": sum(1 for o in outcomes if o.outcome == "too_new"),
                "no_data": sum(1 for o in outcomes if o.outcome == "no_data"),
            },
        }, indent=2))
    else:
        print(f"━━ Outcome tagging for {args.site} ━━━━━━━━━━━━━━")
        for label in ("winner", "mid", "loser", "too_new", "no_data"):
            n = sum(1 for o in outcomes if o.outcome == label)
            print(f"  {label:10s} {n}")
        print(f"  total      {len(outcomes)}")
        print(f"  saved to:  {out_path}")

        winners = [o for o in outcomes if o.outcome == "winner"]
        if winners:
            print()
            print("Top winners:")
            for w in sorted(winners, key=lambda x: -x.clicks)[:5]:
                print(f"  {w.clicks:4d} clicks · pos {w.avg_position:.1f} · "
                      f"AI {w.ai_citations_count} · {w.article_slug}")

        losers = [o for o in outcomes if o.outcome == "loser"]
        if losers:
            print()
            print("Refresh candidates (losers, oldest first):")
            for l in sorted(losers, key=lambda x: -x.days_since_publish)[:5]:
                print(f"  {l.days_since_publish}d old · pos {l.avg_position:.1f} · {l.article_slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
