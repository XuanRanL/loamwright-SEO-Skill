from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx

from scripts._core.news_item import NewsItem, make_item

_ENDPOINT = "https://newsapi.org/v2/everything"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def resolve_key(env: Mapping[str, str] | None = None, creds_dir: Path | None = None) -> str | None:
    env = os.environ if env is None else env
    if env.get("NEWSAPI_KEY"):
        return env["NEWSAPI_KEY"].strip()
    creds_dir = creds_dir or (Path.home() / ".xuanran-seo" / "credentials")
    key_file = creds_dir / "newsapi.key"
    if key_file.exists():
        txt = key_file.read_text(encoding="utf-8").strip()
        return txt or None
    return None


def _default_get(url: str, headers: dict[str, str]) -> dict[str, Any]:
    resp = httpx.get(url, headers=headers, timeout=25.0)
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


def _iso(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def fetch(
    query: str,
    domains: list[str],
    lookback_days: int = 7,
    *,
    api_key: str | None = None,
    now: datetime | None = None,
    _http_get: Callable[[str, dict[str, str]], dict[str, Any] | None] | None = None,
) -> list[NewsItem]:
    # Anti-noise rule: NewsAPI is only useful with a domain whitelist (verified 2026-06-30).
    if not domains:
        print("[newsapi] no domains whitelist -> skip", file=sys.stderr)
        return []
    key = api_key if api_key is not None else resolve_key()
    if not key:
        print("[newsapi] no API key -> skip", file=sys.stderr)
        return []
    get = _http_get or _default_get
    now = now or datetime.now(timezone.utc)
    frm = (now - timedelta(days=lookback_days)).date().isoformat()
    qp = httpx.QueryParams(
        {"q": query, "domains": ",".join(domains), "from": frm,
         "language": "en", "sortBy": "publishedAt", "pageSize": "50"}
    )
    url = f"{_ENDPOINT}?{qp}"
    try:
        data = get(url, {"X-Api-Key": key, "User-Agent": _UA})
    except Exception as exc:
        print(f"[newsapi] degrade: {exc}", file=sys.stderr)
        return []
    if not isinstance(data, dict):
        print("[newsapi] response is not a dict", file=sys.stderr)
        return []
    if data.get("status") != "ok":
        print(f"[newsapi] non-ok: {data.get('code')}", file=sys.stderr)
        return []
    out: list[NewsItem] = []
    for a in (data.get("articles") or []):
        if not isinstance(a, dict):
            continue
        dt = _iso(a.get("publishedAt", ""))
        url_ = a.get("url") or ""
        if dt is None or not url_:
            continue
        out.append(
            make_item(
                headline=a.get("title", ""),
                url=url_,
                source_name=(a.get("source") or {}).get("name", ""),
                published_at=dt.isoformat(),
                summary_raw=a.get("description", ""),
                connector="newsapi",
            )
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--domains", nargs="*", default=[])
    ap.add_argument("--lookback-days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    items = fetch(args.query, args.domains, args.lookback_days)
    print(json.dumps({"connector": "newsapi", "count": len(items), "items": items}, ensure_ascii=False))


if __name__ == "__main__":
    main()
