from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, cast

import httpx

from scripts._core.news_item import NewsItem, make_item

_ENDPOINT = "https://hn.algolia.com/api/v1/search_by_date"


def _default_get(url: str) -> dict[str, Any]:
    resp = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20.0)
    resp.raise_for_status()
    return cast(dict[str, Any], resp.json())


def _iso(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def fetch(
    query: str,
    lookback_days: int = 7,
    *,
    now: datetime | None = None,
    _http_get: Callable[[str], dict[str, Any]] | None = None,
) -> list[NewsItem]:
    get = _http_get or _default_get
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)
    url = f"{_ENDPOINT}?query={httpx.QueryParams({'q': query})['q']}&tags=story&hitsPerPage=30"
    try:
        data = get(url)
    except Exception as exc:
        print(f"[hn] degrade: {exc}", file=sys.stderr)
        return []
    if not isinstance(data, dict):
        return []
    out: list[NewsItem] = []
    for h in (data.get("hits") or []):
        if not isinstance(h, dict):
            continue
        dt = _iso(h.get("created_at", ""))
        if dt is None or dt < cutoff:
            continue
        oid = h.get("objectID")
        link = h.get("url") or (f"https://news.ycombinator.com/item?id={oid}" if oid else "")
        if not link:
            continue
        out.append(
            make_item(
                headline=h.get("title") or h.get("story_title") or "",
                url=link,
                source_name="Hacker News",
                published_at=dt.isoformat(),
                summary_raw=h.get("story_text") or "",
                connector="hackernews",
                raw_score=float(h.get("points") or 0),
                topic_tags=["hn"],
            )
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--lookback-days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    items = fetch(args.query, args.lookback_days)
    print(json.dumps({"connector": "hackernews", "count": len(items), "items": items}, ensure_ascii=False))


if __name__ == "__main__":
    main()
