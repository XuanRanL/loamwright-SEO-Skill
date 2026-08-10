"""scripts/publish/gsc_submit.py — Google Search Console URL Inspection submit.

Submit a newly-published URL to GSC via URL Inspection API for indexing acceleration.
Complements Bing IndexNow (which handles Bing + ChatGPT-via-Bing + Yandex / Naver).

Auth: per-site OAuth refresh-token (preferred) OR global service account.
Endpoint: POST https://searchconsole.googleapis.com/v1/urlInspection/index:inspect

CLI:
    python -m scripts.publish.gsc_submit --site my-site --url https://example.com/post --json
    python -m scripts.publish.gsc_submit --site my-site --from-file urls.txt
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final

import httpx

from scripts._core import credential_hub


URL_INSPECTION_ENDPOINT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters"


@dataclass
class GscSubmitResult:
    url: str
    site_url: str
    submitted: bool = False
    coverage_state: str = ""
    last_crawl: str = ""
    indexing_state: str = ""
    page_fetch_state: str = ""
    google_canonical: str = ""
    response_time_ms: int = 0
    error: str | None = None


def _get_access_token(site_slug: str) -> str:
    """Same priority as gsc_api_ingest: per-site OAuth → service account."""
    try:
        oauth = credential_hub.get_gsc_oauth(site_slug)
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


def _resolve_site_url(site_slug: str) -> str:
    """Read project.yaml for GSC property URL."""
    from scripts._core.project_paths import project_yaml_path
    p = project_yaml_path(site_slug)
    if p.exists():
        try:
            import yaml
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            gsc = (data or {}).get("gsc", {})
            url = gsc.get("property_url") or (data or {}).get("site_url")
            if url:
                return url
        except Exception:
            pass
    return f"https://{site_slug.replace('-', '.')}"


def inspect_url(site_slug: str, inspection_url: str,
                *, timeout: float = 30.0) -> GscSubmitResult:
    """Submit URL to GSC URL Inspection API."""
    site_url = _resolve_site_url(site_slug)

    try:
        token = _get_access_token(site_slug)
    except (credential_hub.CredentialNotFoundError, RuntimeError) as e:
        return GscSubmitResult(url=inspection_url, site_url=site_url, error=str(e))

    body = {
        "inspectionUrl": inspection_url,
        "siteUrl": site_url,
        "languageCode": "en-US",
    }

    t0 = time.time()
    try:
        r = httpx.post(
            URL_INSPECTION_ENDPOINT,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=timeout,
        )
        elapsed = int((time.time() - t0) * 1000)
        if r.status_code == 403:
            return GscSubmitResult(
                url=inspection_url, site_url=site_url,
                response_time_ms=elapsed,
                error=f"GSC 403: verify Search Console access for {site_url}",
            )
        if r.status_code == 429:
            return GscSubmitResult(
                url=inspection_url, site_url=site_url,
                response_time_ms=elapsed,
                error="GSC 429: rate limited (default 2,000 queries/day quota)",
            )
        r.raise_for_status()
        data = r.json()
        inspection = data.get("inspectionResult", {})
        index_status = inspection.get("indexStatusResult", {})
        return GscSubmitResult(
            url=inspection_url,
            site_url=site_url,
            submitted=True,
            coverage_state=index_status.get("coverageState", ""),
            last_crawl=index_status.get("lastCrawlTime", ""),
            indexing_state=index_status.get("indexingState", ""),
            page_fetch_state=index_status.get("pageFetchState", ""),
            google_canonical=index_status.get("googleCanonical", ""),
            response_time_ms=elapsed,
        )
    except httpx.HTTPError as e:
        return GscSubmitResult(
            url=inspection_url, site_url=site_url,
            response_time_ms=int((time.time() - t0) * 1000),
            error=f"HTTP error: {e}",
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Submit URL to Google Search Console URL Inspection API")
    ap.add_argument("--site", required=True)
    ap.add_argument("--url")
    ap.add_argument("--from-file", type=Path, help="One URL per line")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    urls = []
    if args.url:
        urls.append(args.url)
    if args.from_file:
        urls.extend([u.strip() for u in args.from_file.read_text(encoding="utf-8").splitlines()
                     if u.strip() and not u.startswith("#")])
    if not urls:
        print("Need --url or --from-file", file=sys.stderr)
        return 2

    results = []
    for url in urls:
        r = inspect_url(args.site, url)
        results.append(r)
        if not args.json:
            icon = "✓" if r.submitted else "✗"
            if r.submitted:
                print(f"  {icon} {url}")
                print(f"      coverage: {r.coverage_state} | indexing: {r.indexing_state}")
                if r.last_crawl:
                    print(f"      last_crawl: {r.last_crawl}")
            else:
                print(f"  {icon} {url}  error: {r.error}")
        # Rate limit safety: 1 req / 2 seconds (2000/day limit)
        if len(urls) > 1:
            time.sleep(2)

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))

    return 0 if all(r.submitted for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
