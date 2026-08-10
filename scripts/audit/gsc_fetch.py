"""
scripts/audit/gsc_fetch.py — Google Search Console search-analytics for a property.

The audit-google agent + phase-monitor rank-tracker reference this command; it now exists
and reads the unified Google credential (scripts/_core/google_creds) — no env-var setup.

    python -m scripts.audit.gsc_fetch --property "sc-domain:example.com" --days 28 --json
    python -m scripts.audit.gsc_fetch --property "https://example.com/" --days 7 --dimensions query,page --json

Property string MUST match the GSC siteUrl exactly: Domain properties are `sc-domain:example.com`;
URL-prefix properties are `https://example.com/`. (Resolve per project from
projects/{slug}/business-context.json :: analytics.gsc_property.)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from scripts._core import google_creds

API = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"


def fetch(
    property_url: str,
    *,
    days: int = 28,
    dimensions: list[str] | None = None,
    row_limit: int = 100,
) -> dict[str, Any]:
    """Query GSC Search Analytics for the last `days` days."""
    dims = dimensions or ["query"]
    end = date.today()
    start = end - timedelta(days=days)
    body: dict[str, Any] = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": dims,
        "rowLimit": row_limit,
    }
    url = API.format(site=quote(property_url, safe=""))
    resp = httpx.post(
        url, headers={**google_creds.auth_header(), "Content-Type": "application/json"},
        json=body, timeout=45.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"GSC {resp.status_code} for {property_url!r}: {resp.text[:200]} "
            f"(is the account a verified user of this property?)"
        )
    data: dict[str, Any] = resp.json()
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch Google Search Console search-analytics")
    ap.add_argument("--property", required=True, help='GSC siteUrl, e.g. "sc-domain:example.com"')
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--dimensions", default="query", help="comma list: query,page,country,device,date")
    ap.add_argument("--row-limit", type=int, default=100)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        data = fetch(args.property, days=args.days,
                     dimensions=[d.strip() for d in args.dimensions.split(",") if d.strip()],
                     row_limit=args.row_limit)
    except (RuntimeError, google_creds.GoogleCredError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    rows = data.get("rows", [])
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"GSC {args.property}  last {args.days}d  rows={len(rows)}")
        for r in rows[:20]:
            keys = " / ".join(r.get("keys", []))
            print(f"  {keys[:60]:60s} clicks={r.get('clicks',0):>6} impr={r.get('impressions',0):>7} "
                  f"ctr={r.get('ctr',0):.3f} pos={r.get('position',0):.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
