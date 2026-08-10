"""
scripts/audit/ga4_fetch.py — GA4 report via the Analytics Data API (runReport).

Referenced by the audit-google agent; now exists and reads the unified Google credential
(scripts/_core/google_creds). Defaults to a channel-group breakdown so "Organic Search"
sessions are directly visible.

    python -m scripts.audit.ga4_fetch --property-id 538840772 --days 28 --json

Resolve the property id per project from
projects/{slug}/business-context.json :: analytics.ga4_property_id.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from typing import Any

import httpx

from scripts._core import google_creds

API = "https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport"


def fetch(
    property_id: str,
    *,
    days: int = 28,
    dimensions: list[str] | None = None,
    metrics: list[str] | None = None,
) -> dict[str, Any]:
    """Run a GA4 report for the last `days` days (default: sessions/users by channel group)."""
    dims = dimensions or ["sessionDefaultChannelGroup"]
    mets = metrics or ["sessions", "totalUsers", "engagedSessions", "screenPageViews"]
    end = date.today()
    start = end - timedelta(days=days)
    body: dict[str, Any] = {
        "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
        "dimensions": [{"name": d} for d in dims],
        "metrics": [{"name": m} for m in mets],
    }
    url = API.format(pid=property_id)
    resp = httpx.post(
        url, headers={**google_creds.auth_header(), "Content-Type": "application/json"},
        json=body, timeout=45.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"GA4 {resp.status_code} for property {property_id!r}: {resp.text[:200]}"
        )
    data: dict[str, Any] = resp.json()
    return data


def _rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    dim_names = [d["name"] for d in data.get("dimensionHeaders", [])]
    met_names = [m["name"] for m in data.get("metricHeaders", [])]
    out: list[dict[str, Any]] = []
    for row in data.get("rows", []):
        rec: dict[str, Any] = {}
        for i, dv in enumerate(row.get("dimensionValues", [])):
            rec[dim_names[i] if i < len(dim_names) else f"dim{i}"] = dv.get("value")
        for i, mv in enumerate(row.get("metricValues", [])):
            rec[met_names[i] if i < len(met_names) else f"met{i}"] = mv.get("value")
        out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch a GA4 report (runReport)")
    ap.add_argument("--property-id", required=True, help="GA4 numeric property id, e.g. 538840772")
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--dimensions", default="sessionDefaultChannelGroup")
    ap.add_argument("--metrics", default="sessions,totalUsers,engagedSessions,screenPageViews")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        data = fetch(args.property_id, days=args.days,
                     dimensions=[d.strip() for d in args.dimensions.split(",") if d.strip()],
                     metrics=[m.strip() for m in args.metrics.split(",") if m.strip()])
    except (RuntimeError, google_creds.GoogleCredError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    rows = _rows(data)
    if args.json:
        print(json.dumps({"property_id": args.property_id, "days": args.days, "rows": rows},
                         indent=2, ensure_ascii=False))
    else:
        print(f"GA4 {args.property_id}  last {args.days}d  rows={len(rows)}")
        for r in rows:
            print("  " + "  ".join(f"{k}={v}" for k, v in r.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
