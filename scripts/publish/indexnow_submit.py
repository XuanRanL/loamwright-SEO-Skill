"""scripts/publish/indexnow_submit.py — Bing IndexNow URL submission.

Per https://www.indexnow.org/documentation (2026-05 verified):
  - Single endpoint: POST https://api.indexnow.org/indexnow
  - Up to 10,000 URLs per request
  - JSON body: { host, key, keyLocation, urlList }
  - Supports: Bing / ChatGPT-via-Bing / Yandex / Naver / Seznam / Yep

Usage:
    python -m scripts.publish.indexnow_submit https://example.com/new-post
    python -m scripts.publish.indexnow_submit url1 url2 url3 ...
    python -m scripts.publish.indexnow_submit --from-file urls.txt --json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from scripts._core import credential_hub
from scripts._core.ssrf_guard import validate_url, SSRFError


INDEXNOW_URL = "https://api.indexnow.org/indexnow"
MAX_URLS_PER_REQUEST = 10_000


@dataclass
class IndexNowResult:
    submitted_urls: list[str]
    status_code: int
    success: bool
    response_time_ms: int
    error: str | None = None


def submit(urls: list[str], *, project_slug: str | None = None,
           retry: int = 2, timeout: float = 10.0) -> IndexNowResult:
    """Submit a batch of URLs to IndexNow.

    Per docs:
      - 200 = success
      - 202 = accepted (still processing)
      - 400 = bad request (check key/keyLocation)
      - 403 = key file not found at keyLocation
      - 422 = URL mismatched key host
      - 429 = rate limit (back off)
    """
    if not urls:
        return IndexNowResult([], 0, False, 0, error="No URLs provided")

    if len(urls) > MAX_URLS_PER_REQUEST:
        return IndexNowResult([], 0, False, 0,
                              error=f"Too many URLs (max {MAX_URLS_PER_REQUEST})")

    # SSRF check
    safe_urls = []
    for u in urls:
        try:
            validate_url(u)
            safe_urls.append(u)
        except SSRFError as e:
            print(f"SSRF reject: {u}: {e}", file=sys.stderr)
    if not safe_urls:
        return IndexNowResult([], 0, False, 0, error="All URLs SSRF-rejected")

    # Load credentials (per-project file wins on a multi-site fleet)
    try:
        creds = credential_hub.get_bing_indexnow(project_slug)
    except credential_hub.CredentialNotFoundError as e:
        return IndexNowResult([], 0, False, 0, error=str(e))
    except credential_hub.CredentialFormatError as e:
        return IndexNowResult([], 0, False, 0, error=str(e))

    # Wrong-credential guard (2026-08-17): a host-mismatched submission is a
    # guaranteed 422 — fail loud and actionable BEFORE the network call instead
    # of letting the API refuse it opaquely.
    from urllib.parse import urlparse
    cred_host = (creds.host or "").lower().removeprefix("www.")
    for u in safe_urls:
        uh = ((urlparse(u).hostname or "").lower()).removeprefix("www.")
        if not (uh == cred_host or uh.endswith("." + cred_host)):
            return IndexNowResult([], 0, False, 0, error=(
                f"IndexNow credential is for host '{creds.host}' but URL host is "
                f"'{uh}' — this submission would 422. Configure "
                f"credentials/bing-indexnow/{project_slug or '{slug}'}.json for this site."))

    payload = {
        "host": creds.host,
        "key": creds.key,
        "keyLocation": creds.key_location,
        "urlList": safe_urls,
    }

    t0 = time.time()
    last_error = None
    for attempt in range(retry + 1):
        try:
            r = httpx.post(
                INDEXNOW_URL,
                json=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=timeout,
            )
            elapsed = int((time.time() - t0) * 1000)
            if r.status_code in (200, 202):
                return IndexNowResult(safe_urls, r.status_code, True, elapsed)
            if r.status_code == 429:
                # Rate limit — back off
                time.sleep(2 ** attempt)
                last_error = "rate limited"
                continue
            return IndexNowResult(
                safe_urls, r.status_code, False, elapsed,
                error=f"IndexNow returned {r.status_code}: {r.text[:200]}",
            )
        except httpx.HTTPError as e:
            last_error = str(e)
            time.sleep(0.5 * (2 ** attempt))

    elapsed = int((time.time() - t0) * 1000)
    return IndexNowResult(safe_urls, 0, False, elapsed,
                          error=f"Failed after retries: {last_error}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Submit URL(s) to Bing IndexNow")
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--from-file", type=Path, help="File with URLs (one per line)")
    ap.add_argument("--project-slug", default=None, help="Resolve per-site credentials/bing-indexnow/{slug}.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    urls = list(args.urls)
    if args.from_file and args.from_file.exists():
        urls.extend([
            u.strip() for u in args.from_file.read_text(encoding="utf-8").splitlines()
            if u.strip() and not u.startswith("#")
        ])
    if not urls:
        print("No URLs to submit", file=sys.stderr)
        return 2

    result = submit(urls, project_slug=args.project_slug)

    if args.json:
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    else:
        icon = "✓" if result.success else "✗"
        print(f"{icon} IndexNow: {result.status_code}  {len(result.submitted_urls)} URLs  ({result.response_time_ms}ms)")
        if result.error:
            print(f"  Error: {result.error}")
        elif result.success:
            print(f"  Submitted: {len(result.submitted_urls)} URL(s)")
            print(f"  Supported: Bing / ChatGPT-via-Bing / Yandex / Naver / Seznam / Yep")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
