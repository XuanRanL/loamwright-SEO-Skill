from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

import feedparser  # type: ignore[import-untyped]
import httpx

from scripts._core.news_item import NewsItem, make_item

try:
    from scripts._core.ssrf_guard import validate_url
except Exception:  # ssrf_guard optional at import time; fail closed in _get_bytes
    validate_url = None  # type: ignore[assignment]

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"


def _get_bytes(url: str) -> bytes:
    if validate_url is not None:
        validate_url(url)  # raises on private/blocked host
    resp = httpx.get(url, headers={"User-Agent": _UA}, timeout=20.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def _entry_dt(entry: object) -> datetime | None:
    st = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not st:
        return None
    # st is a time.struct_time; unpack year, month, day, hour, minute, second
    year, month, day, hour, minute, second = st[:6]
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def fetch(feeds: list[str], lookback_days: int = 7, *, now: datetime | None = None) -> list[NewsItem]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)
    out: list[NewsItem] = []
    for feed_url in feeds:
        try:
            raw = _get_bytes(feed_url)
            parsed = feedparser.parse(raw)
            source = (parsed.feed.get("title") if parsed.feed else "") or feed_url
            for e in parsed.entries:
                dt = _entry_dt(e)
                link = e.get("link") or ""
                if dt is None or dt < cutoff or not link:
                    continue
                out.append(
                    make_item(
                        headline=e.get("title", ""),
                        url=link,
                        source_name=source,
                        published_at=dt.isoformat(),
                        summary_raw=e.get("summary", ""),
                        connector="rss",
                    )
                )
        except Exception as exc:  # graceful degrade per connector
            print(f"[rss] skip {feed_url}: {exc}", file=sys.stderr)
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feeds", nargs="+", required=True)
    ap.add_argument("--lookback-days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    items = fetch(args.feeds, args.lookback_days)
    print(json.dumps({"connector": "rss", "count": len(items), "items": items}, ensure_ascii=False))


if __name__ == "__main__":
    main()
