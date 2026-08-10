"""
scripts/monitor/gsc_api_ingest.py — Pull GSC Search Analytics via API.

Multi-tenant: pulls metrics for one site (per-site call) or many (--all-sites).

Uses Google Search Console API v1 (searchanalytics.query).
Auth precedence:
  1. Per-site OAuth refresh token (projects/{slug} → credentials/gsc-oauth/{slug}.json)
  2. Global service account (credentials/google-service-account.json)

Pull modes:
  - daily: yesterday's data (~16h delay — GSC lag)
  - weekly: last 7 days
  - last-28: last 28 days (T+28 monitoring window)
  - range: explicit --start / --end

Dimensions returned: date, page, query, country, device.
Default dimensions: page + query (most useful for outcome tagging).

Output: projects/{site_slug}/metrics/gsc-{period}-{date}.json
+ memory/metrics-index.json updated.

CLI:
    python -m scripts.monitor.gsc_api_ingest --site my-site --mode daily
    python -m scripts.monitor.gsc_api_ingest --site my-site --mode range \\
        --start 2026-04-01 --end 2026-04-30
    python -m scripts.monitor.gsc_api_ingest --all-sites --mode weekly
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts._core import credential_hub, google_creds
from scripts._core.file_bus import PLUGIN_ROOT


GSC_API_URL = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site_url}/searchAnalytics/query"
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"


@dataclass
class GscRow:
    page: str = ""
    query: str = ""
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0


@dataclass
class IngestResult:
    site_slug: str
    site_url: str
    period: str
    start_date: str
    end_date: str
    row_count: int
    output_path: str = ""
    by_url: dict[str, dict] = field(default_factory=dict)
    by_query: dict[str, dict] = field(default_factory=dict)
    error: str | None = None


def _resolve_site_url(site_slug: str) -> str:
    """Find the exact GSC property string for a project.

    Primary source: projects/{slug}/business-context.json :: analytics.gsc_property
    (the canonical mapping, e.g. "sc-domain:example.com" or "https://example.com/").
    Falls back to the legacy project.yaml gsc.property_url, then the bare domain.
    Root-cause fix: this previously only read project.yaml (which these projects don't
    use — they use business-context.json), so it fell through to a broken bare-domain guess.
    """
    bc = PLUGIN_ROOT / "projects" / site_slug / "business-context.json"
    if bc.exists():
        try:
            data = json.loads(bc.read_text(encoding="utf-8"))
            prop = (data.get("analytics") or {}).get("gsc_property")
            if prop:
                return str(prop)
        except Exception:
            pass
    project_yaml = PLUGIN_ROOT / "projects" / site_slug / "project.yaml"
    if project_yaml.exists():
        try:
            import yaml
            data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
            gsc = (data or {}).get("gsc", {})
            url = gsc.get("property_url") or (data or {}).get("site_url")
            if url:
                return url
        except Exception:
            pass
    # Fall back to using slug as bare domain
    return f"https://{site_slug.replace('-', '.')}"


def _get_access_token(site_slug: str) -> str:
    """Get a GSC access token.

    Primary = the unified Google credential (`google_creds`, which reads the connected
    account-level OAuth token at credentials/google-oauth-token.json). Falls back to the
    legacy per-site OAuth (gsc-oauth/{slug}.json) then a service account, for setups that
    use those instead. Root-cause fix: this function previously only looked at the two
    fallbacks — both absent here — so the connected GSC token was never used.
    """
    # 0. Unified Google credential — the account-level OAuth token actually connected.
    try:
        return google_creds.get_access_token()
    except google_creds.GoogleCredError:
        pass

    # 1. Try per-site OAuth
    try:
        oauth = credential_hub.get_gsc_oauth(site_slug)
        import httpx
        r = httpx.post(
            oauth.token_uri,
            data={
                "client_id": oauth.client_id,
                "client_secret": oauth.client_secret,
                "refresh_token": oauth.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json()["access_token"]
    except credential_hub.CredentialNotFoundError:
        pass

    # 2. Service account
    sa = credential_hub.get_google_service_account()
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as GoogleRequest
    except ImportError:
        raise RuntimeError(
            "google-auth not installed. Run: pip install google-auth google-auth-httplib2"
        )

    creds = service_account.Credentials.from_service_account_file(
        sa.sa_json_path, scopes=[GSC_SCOPE]
    )
    creds.refresh(GoogleRequest())
    return creds.token


def query_gsc(
    site_url: str,
    access_token: str,
    *,
    start_date: str,
    end_date: str,
    dimensions: list[str] | None = None,
    row_limit: int = 25000,
) -> list[GscRow]:
    """Call GSC searchAnalytics.query and return all rows (paginated)."""
    import httpx
    dimensions = dimensions or ["page", "query"]

    # GSC API site URL needs to be URL-encoded
    from urllib.parse import quote
    encoded_site = quote(site_url, safe="")
    endpoint = GSC_API_URL.format(site_url=encoded_site)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    all_rows: list[GscRow] = []
    start_row = 0
    while True:
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": dimensions,
            "rowLimit": row_limit,
            "startRow": start_row,
        }
        r = httpx.post(endpoint, headers=headers, json=body, timeout=60.0)
        if r.status_code == 403:
            raise PermissionError(
                f"GSC API rejected: 403. Verify service account / OAuth user has "
                f"access to property {site_url!r} in Search Console settings."
            )
        r.raise_for_status()
        data = r.json()
        rows = data.get("rows", []) or []
        if not rows:
            break

        for row in rows:
            keys = row.get("keys", [])
            page_idx = dimensions.index("page") if "page" in dimensions else None
            query_idx = dimensions.index("query") if "query" in dimensions else None
            all_rows.append(GscRow(
                page=keys[page_idx] if page_idx is not None else "",
                query=keys[query_idx] if query_idx is not None else "",
                clicks=int(row.get("clicks", 0)),
                impressions=int(row.get("impressions", 0)),
                ctr=float(row.get("ctr", 0.0)),
                position=float(row.get("position", 0.0)),
            ))

        if len(rows) < row_limit:
            break
        start_row += len(rows)
        if len(all_rows) > 100_000:
            break  # safety cap

    return all_rows


def _aggregate(rows: list[GscRow]) -> tuple[dict, dict]:
    """Roll up per-URL and per-query."""
    by_url: dict[str, dict] = {}
    by_query: dict[str, dict] = {}

    for r in rows:
        if r.page:
            d = by_url.setdefault(r.page, {
                "page": r.page, "clicks": 0, "impressions": 0,
                "position_sum": 0.0, "position_count": 0, "queries": [],
            })
            d["clicks"] += r.clicks
            d["impressions"] += r.impressions
            d["position_sum"] += r.position * max(r.impressions, 1)
            d["position_count"] += max(r.impressions, 1)
            if r.query and len(d["queries"]) < 20:
                d["queries"].append({"q": r.query, "clicks": r.clicks, "pos": r.position})

        if r.query:
            d = by_query.setdefault(r.query, {
                "query": r.query, "clicks": 0, "impressions": 0,
                "position_sum": 0.0, "position_count": 0, "pages": [],
            })
            d["clicks"] += r.clicks
            d["impressions"] += r.impressions
            d["position_sum"] += r.position * max(r.impressions, 1)
            d["position_count"] += max(r.impressions, 1)
            if r.page and len(d["pages"]) < 10:
                d["pages"].append({"page": r.page, "clicks": r.clicks, "pos": r.position})

    for d in by_url.values():
        d["avg_position"] = round(d["position_sum"] / d["position_count"], 2) if d["position_count"] else 0.0
        d["ctr"] = round(d["clicks"] / d["impressions"], 4) if d["impressions"] else 0.0
        del d["position_sum"], d["position_count"]
    for d in by_query.values():
        d["avg_position"] = round(d["position_sum"] / d["position_count"], 2) if d["position_count"] else 0.0
        d["ctr"] = round(d["clicks"] / d["impressions"], 4) if d["impressions"] else 0.0
        del d["position_sum"], d["position_count"]

    return by_url, by_query


def _date_range_for_mode(mode: str) -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    if mode == "daily":
        # GSC has ~16h lag, so yesterday is safest
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


def ingest_site(
    site_slug: str,
    *,
    mode: str = "weekly",
    start_date: str = "",
    end_date: str = "",
    dimensions: list[str] | None = None,
) -> IngestResult:
    """Pull GSC data for a single site and write to disk."""
    site_url = _resolve_site_url(site_slug)
    if mode != "range":
        start_date, end_date = _date_range_for_mode(mode)

    try:
        token = _get_access_token(site_slug)
    except (credential_hub.CredentialNotFoundError, RuntimeError) as e:
        return IngestResult(
            site_slug=site_slug, site_url=site_url, period=mode,
            start_date=start_date, end_date=end_date, row_count=0,
            error=str(e),
        )

    try:
        rows = query_gsc(site_url, token,
                         start_date=start_date, end_date=end_date,
                         dimensions=dimensions or ["page", "query"])
    except (PermissionError, Exception) as e:
        return IngestResult(
            site_slug=site_slug, site_url=site_url, period=mode,
            start_date=start_date, end_date=end_date, row_count=0,
            error=f"GSC API error: {e}",
        )

    by_url, by_query = _aggregate(rows)

    out_dir = PLUGIN_ROOT / "projects" / site_slug / "metrics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"gsc-api-{mode}-{end_date}.json"
    payload = {
        "site_slug": site_slug, "site_url": site_url, "period": mode,
        "start_date": start_date, "end_date": end_date,
        "row_count": len(rows),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "by_url": by_url, "by_query": by_query,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # Update metrics index (same shape as gsc_csv_ingest)
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
        "source": "gsc-api", "period": mode,
        "start_date": start_date, "end_date": end_date,
        "path": str(out_path), "rows": len(rows),
        "unique_urls": len(by_url),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    })
    site["latest_ingest"] = end_date
    index_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")

    return IngestResult(
        site_slug=site_slug, site_url=site_url, period=mode,
        start_date=start_date, end_date=end_date, row_count=len(rows),
        output_path=str(out_path), by_url=by_url, by_query=by_query,
    )


def list_sites() -> list[str]:
    """Find all configured projects."""
    projects_dir = PLUGIN_ROOT / "projects"
    if not projects_dir.is_dir():
        return []
    return sorted(p.name for p in projects_dir.iterdir() if p.is_dir())


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest GSC data via API")
    ap.add_argument("--site")
    ap.add_argument("--all-sites", action="store_true")
    ap.add_argument("--mode", choices=["daily", "weekly", "last-28", "range"],
                    default="weekly")
    ap.add_argument("--start", help="Start date YYYY-MM-DD (with --mode range)")
    ap.add_argument("--end", help="End date YYYY-MM-DD (with --mode range)")
    ap.add_argument("--dimensions", default="page,query",
                    help="GSC dimensions, comma-separated")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.site and not args.all_sites:
        print("Need --site <slug> or --all-sites", file=sys.stderr)
        return 2

    dims = [d.strip() for d in args.dimensions.split(",") if d.strip()]
    sites = list_sites() if args.all_sites else [args.site]

    results = []
    for slug in sites:
        r = ingest_site(
            slug, mode=args.mode,
            start_date=args.start or "", end_date=args.end or "",
            dimensions=dims,
        )
        results.append(r)
        if not args.json:
            if r.error:
                print(f"  ✗ {slug}: {r.error}")
            else:
                print(f"  ✓ {slug}: {r.row_count} rows, {len(r.by_url)} URLs → {Path(r.output_path).name}")

    if args.json:
        # Compact output — drop full by_url/by_query
        summary = [{
            "site_slug": r.site_slug, "row_count": r.row_count,
            "unique_urls": len(r.by_url), "start_date": r.start_date,
            "end_date": r.end_date, "output_path": r.output_path,
            "error": r.error,
        } for r in results]
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    failures = sum(1 for r in results if r.error)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
