#!/usr/bin/env python3
"""Moz Link Explorer API v2 client.

Retrieves domain authority, page authority, spam score, referring domain counts,
external link counts, and anchor text distribution via the Moz Links API v2.

Usage:
    python -m scripts.audit.moz_api example.com --json
    python -m scripts.audit.moz_api example.com --top-pages --json
    python -m scripts.audit.moz_api example.com --anchor-text --limit 50 --json

Auth:
    Requires Moz access ID and secret key.  Resolved via credential_hub
    (providers ``moz_access_id`` and ``moz_secret_key``), or via env vars
    ``MOZ_ACCESS_ID`` / ``MOZ_SECRET_KEY``, or via CLI flags.

API reference: https://moz.com/help/links-api
Free tier: 2,500 rows / month.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MOZ_API_BASE = "https://lsapi.seomoz.com/v2"

# Moz Links API v2 endpoints
_EP_URL_METRICS = f"{MOZ_API_BASE}/url_metrics"
_EP_ANCHOR_TEXT = f"{MOZ_API_BASE}/anchor_text"
_EP_TOP_PAGES = f"{MOZ_API_BASE}/top_pages"
_EP_LINKS = f"{MOZ_API_BASE}/links"

# Default request timeout (seconds).  Moz can be slow on large domains.
_TIMEOUT = 60


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------


def _resolve_credentials(
    access_id_override: Optional[str] = None,
    secret_key_override: Optional[str] = None,
) -> tuple[str, str]:
    """Return ``(access_id, secret_key)``.

    Resolution order per value:
      1. Explicit override (CLI flag)
      2. Environment variable (``MOZ_ACCESS_ID`` / ``MOZ_SECRET_KEY``)
      3. credential_hub providers ``moz_access_id`` / ``moz_secret_key``

    Raises ``SystemExit`` if neither source yields both values.
    """
    import os

    access_id = access_id_override or os.environ.get("MOZ_ACCESS_ID", "").strip()
    secret_key = secret_key_override or os.environ.get("MOZ_SECRET_KEY", "").strip()

    if not access_id or not secret_key:
        try:
            from scripts._core.credential_hub import get_credential
            if not access_id:
                access_id = get_credential("moz_access_id")
            if not secret_key:
                secret_key = get_credential("moz_secret_key")
        except Exception:
            pass

    if not access_id or not secret_key:
        raise SystemExit(
            "Moz API credentials not found.  Provide via:\n"
            "  --access-id / --secret-key flags, OR\n"
            "  MOZ_ACCESS_ID / MOZ_SECRET_KEY env vars, OR\n"
            "  credential_hub providers moz_access_id / moz_secret_key"
        )
    return access_id, secret_key


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DomainMetrics:
    """Top-level domain/root-domain metrics."""

    domain: str
    domain_authority: int = 0
    page_authority: int = 0
    spam_score: int = 0
    referring_domains: int = 0
    external_links: int = 0
    root_domains_to_root_domain: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "da": self.domain_authority,
            "pa": self.page_authority,
            "spam_score": self.spam_score,
            "referring_domains": self.referring_domains,
            "external_links": self.external_links,
            "root_domains_to_root_domain": self.root_domains_to_root_domain,
            "error": self.error,
        }


@dataclass
class AnchorTextEntry:
    """Single anchor-text record."""

    anchor_text: str
    external_pages: int = 0
    external_root_domains: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_text": self.anchor_text,
            "external_pages": self.external_pages,
            "external_root_domains": self.external_root_domains,
        }


@dataclass
class TopPageEntry:
    """Single top-page record."""

    page_url: str
    page_authority: int = 0
    link_root_domains: int = 0
    external_links: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_url": self.page_url,
            "pa": self.page_authority,
            "link_root_domains": self.link_root_domains,
            "external_links": self.external_links,
        }


@dataclass
class MozResult:
    """Combined result payload for JSON output."""

    domain: str
    metrics: Optional[DomainMetrics] = None
    anchor_text: list[AnchorTextEntry] = field(default_factory=list)
    top_pages: list[TopPageEntry] = field(default_factory=list)
    error: Optional[str] = None
    api_calls_used: int = 0
    response_time_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "anchor_text_distribution": [a.to_dict() for a in self.anchor_text],
            "top_pages": [p.to_dict() for p in self.top_pages],
            "error": self.error,
            "api_calls_used": self.api_calls_used,
            "response_time_ms": self.response_time_ms,
        }


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def _post(
    endpoint: str,
    payload: dict[str, Any],
    access_id: str,
    secret_key: str,
    timeout: int = _TIMEOUT,
) -> dict[str, Any]:
    """Execute an authenticated POST to a Moz v2 endpoint.

    Returns the parsed JSON body or a dict with ``"error"`` on failure.
    """
    try:
        resp = httpx.post(
            endpoint,
            json=payload,
            auth=(access_id, secret_key),
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 429:
            return {"error": "Moz API rate limit exceeded.  Free tier: 2,500 rows/month."}
        if resp.status_code == 401:
            return {"error": "Moz API authentication failed.  Check access_id and secret_key."}
        if resp.status_code == 403:
            return {"error": "Moz API forbidden.  Your plan may not include this endpoint."}
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]
    except httpx.TimeoutException:
        return {"error": f"Moz API request timed out after {timeout}s"}
    except httpx.HTTPStatusError as exc:
        return {"error": f"Moz API HTTP {exc.response.status_code}: {exc.response.text[:300]}"}
    except httpx.HTTPError as exc:
        return {"error": f"Moz API request error: {exc}"}


def _normalize_domain(domain_or_url: str) -> str:
    """Ensure we have a bare domain (no scheme, no path)."""
    raw = domain_or_url.strip().rstrip("/")
    if "://" in raw:
        parsed = urlparse(raw)
        return parsed.netloc or parsed.path.split("/")[0]
    return raw.split("/")[0]


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------


def get_domain_authority(
    domain: str,
    access_id: str,
    secret_key: str,
) -> DomainMetrics:
    """Retrieve DA, PA, spam score, and link counts for a root domain."""
    target = f"https://{_normalize_domain(domain)}/"
    payload: dict[str, Any] = {
        "targets": [target],
    }
    data = _post(_EP_URL_METRICS, payload, access_id, secret_key)
    if "error" in data:
        return DomainMetrics(domain=domain, error=data["error"])

    results = data.get("results", [{}])
    r = results[0] if results else {}

    return DomainMetrics(
        domain=domain,
        domain_authority=int(r.get("domain_authority", 0)),
        page_authority=int(r.get("page_authority", 0)),
        spam_score=int(r.get("spam_score", 0)),
        referring_domains=int(r.get("root_domains_to_root_domain", 0)),
        external_links=int(r.get("external_pages_to_root_domain", 0)),
        root_domains_to_root_domain=int(r.get("root_domains_to_root_domain", 0)),
    )


def get_link_metrics(
    url: str,
    access_id: str,
    secret_key: str,
) -> dict[str, Any]:
    """Retrieve page-level link metrics for a specific URL."""
    payload: dict[str, Any] = {
        "targets": [url],
    }
    data = _post(_EP_URL_METRICS, payload, access_id, secret_key)
    if "error" in data:
        return {"url": url, "error": data["error"]}

    results = data.get("results", [{}])
    r = results[0] if results else {}

    return {
        "url": url,
        "page_authority": int(r.get("page_authority", 0)),
        "domain_authority": int(r.get("domain_authority", 0)),
        "spam_score": int(r.get("spam_score", 0)),
        "external_links_to_page": int(r.get("external_pages_to_page", 0)),
        "root_domains_to_page": int(r.get("root_domains_to_page", 0)),
        "link_root_domains_to_root_domain": int(r.get("root_domains_to_root_domain", 0)),
    }


def get_anchor_text(
    domain: str,
    access_id: str,
    secret_key: str,
    limit: int = 50,
) -> list[AnchorTextEntry]:
    """Retrieve anchor text distribution for a root domain.

    Returns the top ``limit`` anchor text phrases by frequency.
    """
    target = f"https://{_normalize_domain(domain)}/"
    payload: dict[str, Any] = {
        "target": target,
        "scope": "root_domain",
        "limit": min(limit, 100),  # Moz caps at 100 per request
    }
    data = _post(_EP_ANCHOR_TEXT, payload, access_id, secret_key)
    if "error" in data:
        return []

    entries: list[AnchorTextEntry] = []
    for item in data.get("results", []):
        entries.append(
            AnchorTextEntry(
                anchor_text=item.get("anchor_text", ""),
                external_pages=int(item.get("external_pages", 0)),
                external_root_domains=int(item.get("external_root_domains", 0)),
            )
        )
    return entries


def get_top_pages(
    domain: str,
    access_id: str,
    secret_key: str,
    limit: int = 25,
) -> list[TopPageEntry]:
    """Retrieve the top pages by page authority for a root domain."""
    target = f"https://{_normalize_domain(domain)}/"
    payload: dict[str, Any] = {
        "target": target,
        "scope": "root_domain",
        "limit": min(limit, 100),
    }
    data = _post(_EP_TOP_PAGES, payload, access_id, secret_key)
    if "error" in data:
        return []

    pages: list[TopPageEntry] = []
    for item in data.get("results", []):
        pages.append(
            TopPageEntry(
                page_url=item.get("page", ""),
                page_authority=int(item.get("page_authority", 0)),
                link_root_domains=int(item.get("root_domains_to_page", 0)),
                external_links=int(item.get("external_pages_to_page", 0)),
            )
        )
    return pages


# ---------------------------------------------------------------------------
# Combined fetch
# ---------------------------------------------------------------------------


def full_analysis(
    domain: str,
    access_id: str,
    secret_key: str,
    include_anchors: bool = True,
    include_top_pages: bool = True,
    anchor_limit: int = 50,
    top_pages_limit: int = 25,
) -> MozResult:
    """Run a combined domain analysis (metrics + anchors + top pages).

    Each enabled section costs one API call against the monthly quota.
    """
    result = MozResult(domain=_normalize_domain(domain))
    start = time.perf_counter()
    calls = 0

    # 1. Domain-level metrics (always)
    result.metrics = get_domain_authority(domain, access_id, secret_key)
    calls += 1

    if result.metrics.error:
        result.error = result.metrics.error
        result.api_calls_used = calls
        result.response_time_ms = int((time.perf_counter() - start) * 1000)
        return result

    # 2. Anchor text distribution
    if include_anchors:
        result.anchor_text = get_anchor_text(
            domain, access_id, secret_key, limit=anchor_limit
        )
        calls += 1

    # 3. Top pages
    if include_top_pages:
        result.top_pages = get_top_pages(
            domain, access_id, secret_key, limit=top_pages_limit
        )
        calls += 1

    result.api_calls_used = calls
    result.response_time_ms = int((time.perf_counter() - start) * 1000)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moz_api",
        description="Moz Link Explorer API v2 — domain authority, link metrics, anchors, top pages.",
    )
    parser.add_argument(
        "domain",
        help="Domain or URL to analyze (e.g. example.com or https://example.com)",
    )
    parser.add_argument(
        "--access-id",
        default=None,
        help="Moz API access ID override (default: credential_hub or env).",
    )
    parser.add_argument(
        "--secret-key",
        default=None,
        help="Moz API secret key override (default: credential_hub or env).",
    )
    parser.add_argument(
        "--anchor-text",
        action="store_true",
        default=False,
        help="Include anchor text distribution.",
    )
    parser.add_argument(
        "--top-pages",
        action="store_true",
        default=False,
        help="Include top pages by page authority.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Fetch metrics + anchors + top pages.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max rows for anchor text / top pages (default 50, max 100).",
    )
    parser.add_argument(
        "--url-metrics",
        default=None,
        help="Fetch page-level metrics for a specific URL instead of domain-level.",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        default=False,
        help="Output JSON (default: human-readable text).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    access_id, secret_key = _resolve_credentials(args.access_id, args.secret_key)

    # Single-URL mode
    if args.url_metrics:
        metrics = get_link_metrics(args.url_metrics, access_id, secret_key)
        if args.json:
            print(json.dumps(metrics, indent=2, default=str))
        else:
            for k, v in metrics.items():
                print(f"  {k}: {v}")
        return 1 if metrics.get("error") else 0

    # Domain analysis mode
    include_anchors = args.anchor_text or args.all
    include_top_pages = args.top_pages or args.all

    # If no specific flags, default to metrics-only (cheapest)
    result = full_analysis(
        domain=args.domain,
        access_id=access_id,
        secret_key=secret_key,
        include_anchors=include_anchors,
        include_top_pages=include_top_pages,
        anchor_limit=args.limit,
        top_pages_limit=args.limit,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        if result.error:
            print(f"Error: {result.error}", file=sys.stderr)
            return 1

        m = result.metrics
        if m:
            print(f"\n=== Moz Metrics: {result.domain} ===")
            print(f"  Domain Authority (DA):  {m.domain_authority}")
            print(f"  Page Authority (PA):    {m.page_authority}")
            print(f"  Spam Score:             {m.spam_score}%")
            print(f"  Referring Domains:      {m.referring_domains:,}")
            print(f"  External Links:         {m.external_links:,}")

        if result.anchor_text:
            print(f"\n=== Anchor Text Distribution (top {len(result.anchor_text)}) ===")
            for at in result.anchor_text[:20]:
                print(f"  [{at.external_root_domains:>4} RDs] {at.anchor_text}")

        if result.top_pages:
            print(f"\n=== Top Pages (by PA, top {len(result.top_pages)}) ===")
            for tp in result.top_pages[:20]:
                print(f"  PA {tp.page_authority:>3} | {tp.link_root_domains:>5} RDs | {tp.page_url}")

        print(f"\nAPI calls used: {result.api_calls_used}")
        print(f"Response time:  {result.response_time_ms}ms")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
