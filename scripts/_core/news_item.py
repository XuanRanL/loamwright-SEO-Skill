from __future__ import annotations

import re
from typing import TypedDict
from urllib.parse import urlparse, urlunparse

# RSS feeds (SEJ notably) append social attribution to <title>:
#   "Story headline via @sejournal, @AuthorHandle"
# Published verbatim, this suffix reached live H2s AND was persisted into
# covered.json, where it could resurface as a follow-up headline → theme → H1
# (2026-08-02 root cure). make_item is the single choke point every connector
# passes through, so the strip lives here, not per-connector. Only a TRAILING
# "via @handle(, @handle)*" is removed — a mid-sentence "via" survives.
_VIA_HANDLE_SUFFIX_RE = re.compile(
    r"\s+via\s+@[\w.\-]+(?:\s*,\s*@[\w.\-]+)*\s*$", re.IGNORECASE
)


def clean_headline(headline: str) -> str:
    """Strip feed-injected social-attribution suffixes from a headline."""
    return _VIA_HANDLE_SUFFIX_RE.sub("", headline or "").strip()


class NewsItem(TypedDict):
    headline: str
    url: str
    source_domain: str
    source_name: str
    published_at: str  # ISO-8601
    summary_raw: str
    connector: str
    raw_score: float | None
    entities: list[str]
    topic_tags: list[str]


def domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def canonical_url(url: str) -> str:
    p = urlparse(url)
    netloc = p.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return urlunparse((p.scheme or "https", netloc, p.path.rstrip("/"), "", "", ""))


def make_item(
    *,
    headline: str,
    url: str,
    source_name: str,
    published_at: str,
    summary_raw: str,
    connector: str,
    raw_score: float | None = None,
    entities: list[str] | None = None,
    topic_tags: list[str] | None = None,
) -> NewsItem:
    clean_url = url.strip()
    return NewsItem(
        headline=clean_headline(headline),
        url=clean_url,
        source_domain=domain_of(clean_url),
        source_name=source_name.strip(),
        published_at=published_at,
        summary_raw=(summary_raw or "").strip(),
        connector=connector,
        raw_score=raw_score,
        entities=entities or [],
        topic_tags=topic_tags or [],
    )


def dedup_key(item: NewsItem) -> str:
    return canonical_url(item["url"])
