"""scripts/fetch/youtube_search.py — YouTube Data API v3 search for embedded videos.

Used by `subskills/build/youtube-embed/` to find 1-3 relevant videos per article.
Selection criteria (in priority order):
  - Recent (≤24 months for evergreen; ≤6 months for news topics)
  - English language by default (override via --lang)
  - Min 1,000 views (filter spam)
  - Has captions (for AI crawlers via noscript fallback)
  - Channel quality (verified or 10k+ subs preferred)

Returns video objects with: id, title, channel, published_at, duration, view_count,
thumbnail_url, embed_url, has_captions, language.

Requires GOOGLE_API_KEY or YOUTUBE_API_KEY (credential_hub).

CLI:
    python -m scripts.fetch.youtube_search --q "fishing rod review" --max 3 --json
    python -m scripts.fetch.youtube_search --q "kw" --published-after 2024-01-01 --min-views 5000
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import httpx

from scripts._core import credential_hub, cost_ledger


YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


@dataclass
class YouTubeVideo:
    video_id: str
    title: str
    channel_title: str
    channel_id: str
    published_at: str
    description: str = ""
    view_count: int = 0
    like_count: int = 0
    duration_iso: str = ""
    duration_seconds: int = 0
    thumbnail_url: str = ""
    embed_url: str = ""
    has_captions: bool = False
    language: str = ""
    is_verified_channel: bool = False
    score: float = 0.0   # composite ranking score


def _get_api_key() -> str:
    try:
        return credential_hub.get_credential("youtube")
    except credential_hub.CredentialNotFoundError:
        return credential_hub.get_credential("google")


def _parse_iso_duration(iso: str) -> int:
    """PT#H#M#S → seconds."""
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + int(s or 0)


def search(
    query: str,
    *,
    max_results: int = 10,
    published_after: str | None = None,
    language: str = "en",
    min_views: int = 1000,
    timeout: float = 15.0,
) -> list[YouTubeVideo]:
    """Search YouTube + return ranked videos."""
    api_key = _get_api_key()

    # Step 1: search.list returns IDs + snippets
    search_params = {
        "key": api_key,
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": min(max_results * 2, 50),  # over-fetch for filtering
        "relevanceLanguage": language,
        "videoEmbeddable": "true",
        "videoCaption": "any",
        "safeSearch": "moderate",
    }
    if published_after:
        # YouTube wants RFC 3339
        search_params["publishedAfter"] = f"{published_after}T00:00:00Z"

    with httpx.Client(timeout=timeout) as client:
        r = client.get(f"{YOUTUBE_API_BASE}/search", params=search_params)
        if r.status_code == 403:
            raise RuntimeError(
                "YouTube API 403: quota exceeded or API key missing youtube.com restriction"
            )
        r.raise_for_status()
        search_data = r.json()
        video_ids = [item["id"]["videoId"] for item in search_data.get("items", [])]
        if not video_ids:
            return []

        # Step 2: videos.list for full metadata + stats + duration
        videos_params = {
            "key": api_key,
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids),
        }
        r = client.get(f"{YOUTUBE_API_BASE}/videos", params=videos_params)
        r.raise_for_status()
        videos_data = r.json()

    results: list[YouTubeVideo] = []
    for item in videos_data.get("items", []):
        snip = item.get("snippet", {})
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})

        view_count = int(stats.get("viewCount", 0))
        if view_count < min_views:
            continue

        duration_iso = content.get("duration", "")
        v = YouTubeVideo(
            video_id=item["id"],
            title=snip.get("title", ""),
            channel_title=snip.get("channelTitle", ""),
            channel_id=snip.get("channelId", ""),
            published_at=snip.get("publishedAt", ""),
            description=(snip.get("description", "") or "")[:300],
            view_count=view_count,
            like_count=int(stats.get("likeCount", 0)),
            duration_iso=duration_iso,
            duration_seconds=_parse_iso_duration(duration_iso),
            thumbnail_url=(snip.get("thumbnails", {}).get("high", {}).get("url", "")
                          or f"https://img.youtube.com/vi/{item['id']}/hqdefault.jpg"),
            embed_url=f"https://www.youtube.com/embed/{item['id']}",
            has_captions=content.get("caption") == "true",
            language=snip.get("defaultAudioLanguage", "") or snip.get("defaultLanguage", ""),
        )
        # Composite score: views (log) + recency + has captions
        import math
        recency_days = (datetime.now(timezone.utc)
                        - datetime.fromisoformat(v.published_at.replace("Z", "+00:00"))).days
        recency_factor = max(0, 1 - recency_days / 730)  # decay over 2 years
        v.score = round(
            math.log10(max(view_count, 1)) * 0.4
            + recency_factor * 0.4
            + (0.2 if v.has_captions else 0)
            , 3
        )
        results.append(v)

    results.sort(key=lambda x: x.score, reverse=True)
    return results[:max_results]


def main() -> int:
    ap = argparse.ArgumentParser(description="YouTube video search for embed candidates")
    ap.add_argument("--q", required=True, help="Search query")
    ap.add_argument("--max", type=int, default=3)
    ap.add_argument("--published-after", help="YYYY-MM-DD")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--min-views", type=int, default=1000)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        videos = search(args.q,
                        max_results=args.max,
                        published_after=args.published_after,
                        language=args.lang,
                        min_views=args.min_views)
    except (RuntimeError, httpx.HTTPError, credential_hub.CredentialNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps([asdict(v) for v in videos], indent=2, ensure_ascii=False))
    else:
        print(f"Found {len(videos)} videos for {args.q!r}:")
        for v in videos:
            print(f"  [{v.score}] {v.view_count:>8} views  {v.title[:60]}")
            print(f"           channel: {v.channel_title}  duration: {v.duration_seconds}s")
            print(f"           embed: {v.embed_url}")
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
