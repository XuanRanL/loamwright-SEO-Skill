"""
scripts/monitor/ai_citation_tracker.py — Cross-portfolio AI citation tracking.

Iterates over published articles + Phase-3 entities, probes AI engines
(via ai_search_probe.py), and tracks:
  - Which articles get cited by which AI engines, over time
  - Citation count delta vs baseline
  - "Just-lost" alerts (cited last week, not this week)
  - "Just-gained" celebrations (newly cited)

Output: projects/{site_slug}/ai-citations/{date}.json
+ memory/ai-citation-history.json (cross-portfolio time-series)

Schedule recommendation: weekly. Each probe ~$0.05 × N engines × N queries.
For 100 articles × 4 engines × 1 query = 400 probes × $0.05 = $20/week.
Use --top-priority to limit to highest-value articles.

CLI:
    python -m scripts.monitor.ai_citation_tracker --site my-site
    python -m scripts.monitor.ai_citation_tracker --all-sites --top-priority 20
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from scripts._core.file_bus import PLUGIN_ROOT


@dataclass
class ArticleCitationStatus:
    article_url: str
    article_slug: str
    primary_keyword: str = ""
    engines_citing: list[str] = field(default_factory=list)
    engines_not_citing: list[str] = field(default_factory=list)
    delta_vs_prev: dict[str, str] = field(default_factory=dict)  # engine → "gained"/"lost"/"unchanged"
    probe_cost_usd: float = 0.0
    last_probed_at: str = ""


def _load_articles(site_slug: str, *, top_priority: int = 0) -> list[dict]:
    """Read published articles; optionally limit to top_priority by recency or recent clicks."""
    articles_dir = PLUGIN_ROOT / "projects" / site_slug / "articles"
    if not articles_dir.is_dir():
        return []
    arts = []
    for d in articles_dir.iterdir():
        if not d.is_dir():
            continue
        log = d / "publish-log.json"
        if not log.exists():
            continue
        try:
            data = json.loads(log.read_text(encoding="utf-8"))
            arts.append({
                "slug": d.name,
                "url": data.get("post_url", ""),
                "primary_keyword": data.get("primary_keyword", ""),
                "published_at": data.get("published_at", ""),
            })
        except (OSError, json.JSONDecodeError):
            continue

    if top_priority > 0:
        # Sort by recency (newer = higher priority) - rough heuristic
        arts.sort(key=lambda a: a.get("published_at", ""), reverse=True)
        arts = arts[:top_priority]

    return arts


def _load_prev_status(site_slug: str) -> dict[str, list[str]]:
    """Get previous run's engines_citing per URL — used for gained/lost delta."""
    history = PLUGIN_ROOT / "memory" / "ai-citation-history.json"
    if not history.exists():
        return {}
    try:
        h = json.loads(history.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    site = (h.get("sites") or {}).get(site_slug, {})
    last_run = site.get("last_run", {})
    return last_run.get("by_url", {})


def _probe_article(url: str, query: str, engines: list[str]) -> tuple[list[str], list[str], float]:
    """Probe each engine; return (cites, doesnt_cite, total_cost)."""
    try:
        from scripts.fetch.ai_search_probe import _probe_chatgpt, _probe_perplexity
        # Probe modules
        engine_fns = {
            "chatgpt": "scripts.fetch.ai_search_probe._probe_chatgpt",
            "perplexity": "scripts.fetch.ai_search_probe._probe_perplexity",
            "claude": "scripts.fetch.ai_search_probe._probe_claude",
            "gemini": "scripts.fetch.ai_search_probe._probe_gemini",
        }
    except ImportError as e:
        return [], engines, 0.0

    cites = []
    not_cites = []
    cost = 0.0
    from urllib.parse import urlparse
    domain = urlparse(url).netloc

    for eng in engines:
        try:
            mod_path = engine_fns.get(eng)
            if not mod_path:
                continue
            mod, fn_name = mod_path.rsplit(".", 1)
            import importlib
            module = importlib.import_module(mod)
            fn = getattr(module, fn_name)
            result = fn(query)
            cost += getattr(result, "cost_usd", 0) or 0.0
            text = getattr(result, "response_text", "") or ""
            cites_urls = getattr(result, "cites_in_response", []) or []
            cited = (
                domain in text
                or any(domain in u for u in cites_urls)
                or url in text
            )
            if cited:
                cites.append(eng)
            else:
                not_cites.append(eng)
        except (AttributeError, Exception):
            not_cites.append(eng)

    return cites, not_cites, cost


def track_site(
    site_slug: str,
    *,
    engines: list[str] | None = None,
    top_priority: int = 0,
) -> list[ArticleCitationStatus]:
    """Probe each article across engines."""
    engines = engines or ["chatgpt", "perplexity", "claude", "gemini"]
    arts = _load_articles(site_slug, top_priority=top_priority)
    prev = _load_prev_status(site_slug)
    now = datetime.now(timezone.utc).isoformat()

    results: list[ArticleCitationStatus] = []
    for art in arts:
        url = art["url"]
        keyword = art["primary_keyword"] or art["slug"].replace("-", " ")
        cites, not_cites, cost = _probe_article(url, keyword, engines)

        prev_engines = set(prev.get(url, []))
        cur_engines = set(cites)
        delta = {}
        for eng in engines:
            if eng in cur_engines and eng not in prev_engines:
                delta[eng] = "gained"
            elif eng in prev_engines and eng not in cur_engines:
                delta[eng] = "lost"
            else:
                delta[eng] = "unchanged"

        results.append(ArticleCitationStatus(
            article_url=url,
            article_slug=art["slug"],
            primary_keyword=keyword,
            engines_citing=cites,
            engines_not_citing=not_cites,
            delta_vs_prev=delta,
            probe_cost_usd=round(cost, 4),
            last_probed_at=now,
        ))

    return results


def save_results(site_slug: str, results: list[ArticleCitationStatus]) -> Path:
    out_dir = PLUGIN_ROOT / "projects" / site_slug / "audits" / "ai-citations"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    out_path = out_dir / f"{today}.json"
    out_path.write_text(json.dumps({
        "site_slug": site_slug,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "total_probed": len(results),
        "total_cost_usd": round(sum(r.probe_cost_usd for r in results), 4),
        "results": [asdict(r) for r in results],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    # Update history
    history_path = PLUGIN_ROOT / "memory" / "ai-citation-history.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    h = {}
    if history_path.exists():
        try:
            h = json.loads(history_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            h = {}
    sites = h.setdefault("sites", {})
    site = sites.setdefault(site_slug, {"runs": []})
    by_url = {r.article_url: r.engines_citing for r in results}
    site["runs"].append({
        "date": today,
        "total_probed": len(results),
        "by_url_count": {url: len(eng) for url, eng in by_url.items()},
    })
    site["last_run"] = {"date": today, "by_url": by_url}
    history_path.write_text(json.dumps(h, indent=2, ensure_ascii=False), encoding="utf-8")

    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-portfolio AI citation tracker")
    ap.add_argument("--site")
    ap.add_argument("--all-sites", action="store_true")
    ap.add_argument("--engines", default="chatgpt,perplexity,claude,gemini")
    ap.add_argument("--top-priority", type=int, default=0,
                    help="Limit to top N most-recent articles per site (cost control)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.site and not args.all_sites:
        print("Need --site or --all-sites", file=sys.stderr)
        return 2

    engines = [e.strip() for e in args.engines.split(",") if e.strip()]
    sites = (
        sorted(p.name for p in (PLUGIN_ROOT / "projects").iterdir() if p.is_dir())
        if args.all_sites else [args.site]
    )

    grand_total_cost = 0.0
    for slug in sites:
        results = track_site(slug, engines=engines, top_priority=args.top_priority)
        if not results:
            print(f"  • {slug}: no articles", file=sys.stderr)
            continue
        out_path = save_results(slug, results)
        cost = sum(r.probe_cost_usd for r in results)
        grand_total_cost += cost

        if args.json:
            print(json.dumps({
                "site": slug, "probed": len(results),
                "cost_usd": round(cost, 4),
                "output_path": str(out_path),
            }, indent=2))
        else:
            gained = sum(1 for r in results for v in r.delta_vs_prev.values() if v == "gained")
            lost = sum(1 for r in results for v in r.delta_vs_prev.values() if v == "lost")
            print(f"  ✓ {slug}: {len(results)} probed (${cost:.2f}) "
                  f"  gained: {gained}  lost: {lost}")

    if not args.json:
        print(f"\nTotal probe cost: ${grand_total_cost:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
