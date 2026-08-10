from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from scripts._core.news_item import NewsItem, make_item

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
_SPAN = {7: "1week", 14: "2weeks"}


def _default_get(url_with_query: str) -> dict[str, Any] | None:
    # GDELT returns empty body when throttled; treat any non-JSON as None.
    try:
        resp = httpx.get(url_with_query, headers={"User-Agent": _UA}, timeout=30.0)
        if not resp.text.strip():
            return None
        result = resp.json()
        return result if isinstance(result, dict) else None
    except Exception:
        return None


def _seendate_to_iso(s: str) -> str:
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def fetch(
    queries: list[str],
    lookback_days: int = 7,
    *,
    min_interval_s: float = 5.0,
    _sleep: Callable[[float], None] = time.sleep,
    _http_get: Callable[[str], dict[str, Any] | None] | None = None,
) -> list[NewsItem]:
    get = _http_get or _default_get
    span = _SPAN.get(lookback_days, "1week")
    out: list[NewsItem] = []
    for idx, q in enumerate(queries):
        if idx > 0:
            _sleep(min_interval_s)  # hard rate-limit: 1 request / 5s
        params = (
            f"?query={httpx.QueryParams({'query': q})['query']}"
            f"&mode=artlist&maxrecords=20&timespan={span}&sort=datedesc&format=json"
        )
        data = get(_ENDPOINT + params)
        if not data:
            print(f"[gdelt] empty/throttled for {q!r}", file=sys.stderr)
            continue
        for a in (data.get("articles") or []):
            if not isinstance(a, dict):
                continue
            url = a.get("url") or ""
            if not url:
                continue
            out.append(
                make_item(
                    headline=a.get("title", ""),
                    url=url,
                    source_name=a.get("domain", ""),
                    published_at=_seendate_to_iso(a.get("seendate", "")),
                    summary_raw="",
                    connector="gdelt",
                )
            )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", nargs="+", required=True)
    ap.add_argument("--lookback-days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    items = fetch(args.queries, args.lookback_days)
    print(json.dumps({"connector": "gdelt", "count": len(items), "items": items}, ensure_ascii=False))


if __name__ == "__main__":
    main()
