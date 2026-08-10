"""
scripts/monitor/bing_webmaster_ingest.py — Pull Bing Webmaster Tools data via API.

Bing Webmaster Tools API (2026 stable endpoint):
  Base: https://ssl.bing.com/webmaster/api.svc/json/
  Auth: apikey query parameter (single key works across all verified sites in BWT account)

Endpoints used:
  - GetRankAndTrafficStats (impressions, clicks, average position over time)
  - GetQueryStats (per-query metrics)
  - GetPageQueryStats (per-page metrics)
  - GetUrlInfo (single URL deep dive)

Output: projects/{site_slug}/metrics/bing-{period}-{date}.json
+ memory/metrics-index.json updated.

CLI:
    python -m scripts.monitor.bing_webmaster_ingest --site my-site --mode weekly
    python -m scripts.monitor.bing_webmaster_ingest --all-sites --mode last-28
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts._core import credential_hub
from scripts._core.file_bus import PLUGIN_ROOT


BWT_BASE = "https://ssl.bing.com/webmaster/api.svc/json"


@dataclass
class BingRow:
    page: str = ""
    query: str = ""
    impressions: int = 0
    clicks: int = 0
    position: float = 0.0
    date: str = ""


@dataclass
class BingIngestResult:
    site_slug: str
    site_url: str
    period: str
    start_date: str
    end_date: str
    rank_traffic_rows: int = 0
    query_stat_rows: int = 0
    output_path: str = ""
    error: str | None = None


def _resolve_site_url(site_slug: str) -> str:
    """Resolve the verified Bing site URL for a project.

    Primary: projects/{slug}/business-context.json :: site_url (the canonical source, shared
    with the Google ingest), normalized to the trailing-slash form Bing verifies. Falls back to
    the legacy project.yaml, then a bare-domain guess. Aligns Bing site-resolution with the GSC
    fix so both engines read one source of truth and don't silently depend on project.yaml
    existing (the bare-domain fallback breaks for any project whose slug != registered domain,
    e.g. project-echo -> project-echo.example.com).
    """
    import json
    bc = PLUGIN_ROOT / "projects" / site_slug / "business-context.json"
    if bc.exists():
        try:
            data = json.loads(bc.read_text(encoding="utf-8"))
            url = data.get("site_url")
            if url:
                return str(url).rstrip("/") + "/"
        except Exception:
            pass
    project_yaml = PLUGIN_ROOT / "projects" / site_slug / "project.yaml"
    if project_yaml.exists():
        try:
            import yaml
            data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
            bwt = (data or {}).get("bing_webmaster", {})
            url = bwt.get("site_url") or (data or {}).get("site_url")
            if url:
                return url
        except Exception:
            pass
    return f"https://{site_slug.replace('-', '.')}/"


def _bwt_call(endpoint: str, api_key: str, params: dict, user_agent: str) -> dict:
    """Single BWT API call."""
    import httpx
    full_params = {"apikey": api_key, **params}
    url = f"{BWT_BASE}/{endpoint}"
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json",
    }
    r = httpx.get(url, params=full_params, headers=headers, timeout=30.0)
    if r.status_code == 401:
        raise PermissionError("BWT 401: API key invalid or site not verified")
    if r.status_code == 403:
        raise PermissionError("BWT 403: insufficient permissions for this site")
    r.raise_for_status()
    return r.json()


def get_rank_and_traffic_stats(site_url: str, api_key: str, user_agent: str) -> list[dict]:
    """Pull aggregate impressions/clicks/position over recent dates."""
    raw = _bwt_call("GetRankAndTrafficStats", api_key,
                    {"siteUrl": site_url}, user_agent)
    return raw.get("d", []) or []


def get_query_stats(site_url: str, api_key: str, user_agent: str) -> list[dict]:
    """Per-query stats."""
    raw = _bwt_call("GetQueryStats", api_key,
                    {"siteUrl": site_url}, user_agent)
    return raw.get("d", []) or []


def get_page_query_stats(site_url: str, page_url: str,
                         api_key: str, user_agent: str) -> list[dict]:
    """Per-(page, query) stats. Call per page of interest."""
    raw = _bwt_call("GetPageQueryStats", api_key,
                    {"siteUrl": site_url, "page": page_url}, user_agent)
    return raw.get("d", []) or []


def _normalize_query_stats(raw: list[dict]) -> dict:
    """Normalize BWT query stats → consistent schema."""
    by_query: dict[str, dict] = {}
    for row in raw:
        q = row.get("Query") or row.get("query") or ""
        if not q:
            continue
        d = by_query.setdefault(q, {
            "query": q, "clicks": 0, "impressions": 0,
            "position": 0.0,
        })
        d["clicks"] += int(row.get("Clicks", 0))
        d["impressions"] += int(row.get("Impressions", 0))
        pos = float(row.get("AvgImpressionPosition") or row.get("Position", 0))
        if pos > 0:
            d["position"] = pos
    return by_query


def _date_range_for_mode(mode: str) -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    if mode == "daily":
        d = today - timedelta(days=2)
        return d.isoformat(), d.isoformat()
    if mode == "weekly":
        end = today - timedelta(days=2)
        start = end - timedelta(days=6)
        return start.isoformat(), end.isoformat()
    if mode == "last-28":
        end = today - timedelta(days=2)
        start = end - timedelta(days=27)
        return start.isoformat(), end.isoformat()
    raise ValueError(f"Unknown mode: {mode}")


def ingest_site(site_slug: str, mode: str = "weekly") -> BingIngestResult:
    """Pull BWT data for a single site."""
    site_url = _resolve_site_url(site_slug)
    start_date, end_date = _date_range_for_mode(mode)

    try:
        creds = credential_hub.get_bing_webmaster()
    except credential_hub.CredentialNotFoundError as e:
        return BingIngestResult(
            site_slug=site_slug, site_url=site_url, period=mode,
            start_date=start_date, end_date=end_date, error=str(e),
        )

    try:
        rank_traffic = get_rank_and_traffic_stats(site_url, creds.api_key, creds.user_agent)
        query_stats_raw = get_query_stats(site_url, creds.api_key, creds.user_agent)
    except (PermissionError, Exception) as e:
        return BingIngestResult(
            site_slug=site_slug, site_url=site_url, period=mode,
            start_date=start_date, end_date=end_date,
            error=f"BWT API error: {e}",
        )

    by_query = _normalize_query_stats(query_stats_raw)

    out_dir = PLUGIN_ROOT / "projects" / site_slug / "metrics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"bing-{mode}-{end_date}.json"
    payload = {
        "site_slug": site_slug, "site_url": site_url,
        "period": mode, "start_date": start_date, "end_date": end_date,
        "source": "bing-webmaster-api",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "rank_traffic_stats": rank_traffic,
        "by_query": by_query,
        "rank_traffic_rows": len(rank_traffic),
        "query_stat_rows": len(by_query),
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # Update index
    index_path = PLUGIN_ROOT / "memory" / "metrics-index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    idx: dict = {}
    if index_path.exists():
        try:
            idx = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            idx = {}
    sites = idx.setdefault("sites", {})
    site = sites.setdefault(site_slug, {"ingests": []})
    site["ingests"].append({
        "source": "bing-webmaster-api", "period": mode,
        "start_date": start_date, "end_date": end_date,
        "path": str(out_path),
        "rank_traffic_rows": len(rank_traffic),
        "query_stat_rows": len(by_query),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    })
    index_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")

    return BingIngestResult(
        site_slug=site_slug, site_url=site_url, period=mode,
        start_date=start_date, end_date=end_date,
        rank_traffic_rows=len(rank_traffic),
        query_stat_rows=len(by_query),
        output_path=str(out_path),
    )


def list_sites() -> list[str]:
    projects_dir = PLUGIN_ROOT / "projects"
    if not projects_dir.is_dir():
        return []
    return sorted(p.name for p in projects_dir.iterdir() if p.is_dir())


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest Bing Webmaster data via API")
    ap.add_argument("--site")
    ap.add_argument("--all-sites", action="store_true")
    ap.add_argument("--mode", choices=["daily", "weekly", "last-28"],
                    default="weekly")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.site and not args.all_sites:
        print("Need --site <slug> or --all-sites", file=sys.stderr)
        return 2

    sites = list_sites() if args.all_sites else [args.site]
    results = [ingest_site(s, args.mode) for s in sites]

    if args.json:
        print(json.dumps([{
            "site_slug": r.site_slug, "rank_traffic_rows": r.rank_traffic_rows,
            "query_stat_rows": r.query_stat_rows,
            "output_path": r.output_path, "error": r.error,
        } for r in results], indent=2, ensure_ascii=False))
    else:
        for r in results:
            if r.error:
                print(f"  ✗ {r.site_slug}: {r.error}")
            else:
                print(f"  ✓ {r.site_slug}: traffic={r.rank_traffic_rows} "
                      f"queries={r.query_stat_rows} → {Path(r.output_path).name}")

    return 0 if all(r.error is None for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
