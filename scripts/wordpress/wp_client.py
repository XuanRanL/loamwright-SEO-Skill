"""
scripts/wordpress/wp_client.py — Authenticated WordPress REST client.

Auth: WordPress Application Passwords (24-char key, HTTP Basic over HTTPS).
Reads credentials via scripts/_core/credential_hub.get_wordpress_creds(site_slug).

All URL fetches go through scripts/_core/ssrf_guard.validate_url().

Features:
  - Sync httpx client (simple; async could be added if needed)
  - Retry with exponential backoff on 429/5xx
  - Lazy connection (no network at import)
  - JSON response handling (raises WPApiError on non-2xx)
  - Logging hook for call counts (cost_ledger compatible)
  - Multipart upload support (for media)

Usage:
    from scripts.wordpress.wp_client import WPClient

    wp = WPClient("example-com")           # reads ~/.xuanran-seo/credentials/wordpress/example-com.json
    health = wp.health_check()             # GET /wp-json + /yoast/v1/ping
    posts = wp.get("/wp/v2/posts", params={"per_page": 10})
    post = wp.post("/wp/v2/posts", json={"title": "...", ...})
    media = wp.upload_media(path, alt="...", caption="...")
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts._core import credential_hub
from scripts._core.credential_hub import WPCreds
from scripts._core.ssrf_guard import validate_url, SSRFError


log = logging.getLogger("xuanran-seo.wp_client")


_DEFAULT_CF_HEADER = "X-Xuanran-SEO-Token"


def _load_cf_bypass_token(site_slug: str) -> tuple[str | None, str]:
    """Load Cloudflare bypass token + header name from projects/{slug}/credentials/cloudflare.json.

    Returns ``(token_or_None, header_name)``. The header name defaults to
    ``X-Xuanran-SEO-Token`` so existing projects are unaffected; a project whose
    cloudflare.json sets a custom ``header_name`` (e.g. project-echo → ``x-project-echo-bypass``)
    gets the correct header — otherwise the WAF Allow rule never matches and every
    REST call 403s (the 2026-06-20 project-echo gap). Returns ``(None, default)`` if the
    file is missing or strategy != header_token. Silent fallback by design — most
    sites won't have CF in front of WP REST.
    """
    try:
        from scripts._core.file_bus import PLUGIN_ROOT
        cf_file = PLUGIN_ROOT / "projects" / site_slug / "credentials" / "cloudflare.json"
        if not cf_file.exists():
            return None, _DEFAULT_CF_HEADER
        data = json.loads(cf_file.read_text(encoding="utf-8"))
        if data.get("strategy") != "header_token":
            return None, _DEFAULT_CF_HEADER
        # Accept both key conventions: project-echo uses `header_name`, while project-kilo /
        # project-hotel use `bypass_header`. Reading only one key silently ignored the
        # other and worked solely by coincidence when the project's header equalled the
        # default (2026-06-21 audit). Likewise accept the common token-key aliases.
        header = data.get("header_name") or data.get("bypass_header") or _DEFAULT_CF_HEADER
        token = (
            data.get("bypass_token")
            or data.get("cloudflare_bypass_token")
            or data.get("token")
            or None
        )
        return token, header
    except Exception as e:
        # Audit 2026-05-22 P1 — log silent-fallback. Missing token causes
        # Cloudflare 403 "Just a moment..." on every WP REST call; surfacing
        # the load error makes that root cause visible.
        print(
            f"⚠ Cloudflare bypass token load failed: "
            f"{type(e).__name__}: {e} — REST calls may 403 on CF-protected sites",
            file=sys.stderr,
        )
        return None, _DEFAULT_CF_HEADER


# ─── Exceptions ────────────────────────────────────────────────

class WPApiError(Exception):
    """Base for WordPress REST API errors."""
    def __init__(self, status: int, message: str, response_body: str | None = None):
        super().__init__(f"WP API {status}: {message}")
        self.status = status
        self.message = message
        self.response_body = response_body


class WPAuthError(WPApiError):
    """401 or 403 from WP."""


class WPNotFoundError(WPApiError):
    """404 from WP."""


class WPRateLimitError(WPApiError):
    """429 from WP."""


# ─── Client ────────────────────────────────────────────────────

@dataclass
class WPResponse:
    """Parsed WordPress response."""
    status: int
    json_data: Any
    headers: dict[str, str]


class WPClient:
    """Synchronous WordPress REST client."""

    DEFAULT_TIMEOUT: float = 30.0
    # 2026-08-05: raised 120 -> 600. A 4K article image (3840x2160, 7-10 MB PNG) makes
    # WordPress generate the full thumbnail set server-side, which regularly runs past
    # 120 s on these hosts. The upload SUCCEEDS but the client gives up first, and because
    # the retry predicate below includes httpx.TimeoutException, the non-idempotent media
    # POST is then re-sent: every timeout mints a DUPLICATE attachment. Observed on
    # project-alpha task art_20260805142931_001_8ef9, where one slot produced section-6,
    # section-6-2 and section-6-3 at exactly ~120 s apart before the publisher gave up
    # and rolled back. Host limits were never the constraint (upload_max_filesize=168M,
    # post_max_size=192M, nginx client_max_body_size=168m, max_execution_time=0) - the
    # client timeout was. Raising the ceiling removes the trigger; the deeper fix is to
    # stop retrying non-idempotent POSTs on timeout, which is a wider behavior change.
    #
    # WHY 600 AND NOT SOME NUMBER NEAR THE REAL LIMIT: the binding constraint upstream is
    # Cloudflare's ~100 s edge timeout (HTTP 524), not this value. Sitting BELOW the edge
    # timeout is the harmful case, because the client then raises httpx.ReadTimeout — which
    # IS in the retry predicate below — and re-sends the upload, minting a duplicate. Sitting
    # comfortably ABOVE it means the edge answers first with a 524, which surfaces as
    # WPApiError(524) and is NOT retried. So the large value is deliberately generous: its job
    # is to lose the race to Cloudflare, not to win it. A slow origin still fails the upload;
    # it just fails ONCE, with a real status code, instead of silently duplicating.
    # (Root cause of the 2026-08-05 stall was an Action Scheduler runaway degrading the origin
    # to ~32 s responses; a container restart took it to ~1 s. Infrastructure, not this class.)
    UPLOAD_TIMEOUT: float = 600.0
    MAX_RETRIES: int = 3

    def __init__(
        self,
        site_slug: str,
        *,
        creds: WPCreds | None = None,
        allow_http_for_testing: bool = False,
        user_agent: str = "XuanranSEO/3.2.0 WordPress-Client",
    ):
        """Initialize client for a given WP site.

        Args:
            site_slug: Project slug; loads credentials from
                       ~/.xuanran-seo/credentials/wordpress/{slug}.json
            creds: Override loaded creds (for testing).
            allow_http_for_testing: If True, allow http:// site URLs (don't use in prod).
        """
        if creds is None:
            creds = credential_hub.get_wordpress_creds(site_slug)
        self.creds = creds
        self.site_slug = site_slug
        self.allow_http_for_testing = allow_http_for_testing
        self.user_agent = user_agent
        self.call_count = 0  # for telemetry
        self.bytes_sent = 0
        self.bytes_received = 0

        # Validate base URL once
        try:
            v = validate_url(
                creds.url,
                allow_http=allow_http_for_testing,
                resolve_dns=False,  # WP sites resolve at API call time
            )
            self._base = v.url.rstrip("/")
        except SSRFError as e:
            raise WPApiError(0, f"WP base URL fails SSRF check: {e}") from e

        self._client = None  # lazy

    # ─── Core ───────────────────────────────────────────────

    def _ensure_client(self):
        if self._client is None:
            import httpx
            headers = {"User-Agent": self.user_agent}
            # Auto-inject Cloudflare bypass token if configured for this site
            cf_token, cf_header = _load_cf_bypass_token(self.site_slug)
            if cf_token:
                headers[cf_header] = cf_token
            # XS_FORCE_IPV4=1 binds the transport to a local IPv4 address, forcing
            # IPv4 connections. Host-side anti-bot layers (SiteGround sgcaptcha)
            # flag per-IP; a flagged IPv6 can serve 202 challenge pages on every
            # REST call while the same site answers normally over IPv4.
            transport = None
            if os.environ.get("XS_FORCE_IPV4") == "1":
                transport = httpx.HTTPTransport(local_address="0.0.0.0")
            self._client = httpx.Client(
                base_url=self._base + "/wp-json",
                auth=(self.creds.username, self.creds.app_password),
                headers=headers,
                timeout=self.DEFAULT_TIMEOUT,
                follow_redirects=True,  # CF sometimes redirects 301 to canonical URL
                transport=transport,
            )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ─── HTTP verbs ──────────────────────────────────────────

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: Any = None,
        data: dict | None = None,
        files: dict | None = None,
        headers: dict | None = None,
        timeout: float | None = None,
    ) -> WPResponse:
        """Generic request with retry / error handling.

        Args:
            method: HTTP verb
            path: relative path, e.g. "/wp/v2/posts/123" (we prepend /wp-json)
            params: query params
            json_body: JSON body (auto-sets Content-Type)
            data: form data
            files: multipart files
            headers: extra headers
            timeout: override default
        """
        from tenacity import (
            retry, stop_after_attempt, wait_exponential,
            retry_if_exception_type, before_log,
        )
        import httpx

        self._ensure_client()
        self.call_count += 1

        @retry(
            stop=stop_after_attempt(self.MAX_RETRIES),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, WPRateLimitError)),
            before=before_log(log, logging.DEBUG),
            reraise=True,
        )
        def _send() -> "httpx.Response":
            kwargs: dict[str, Any] = {}
            if params is not None:
                kwargs["params"] = params
            if json_body is not None:
                kwargs["json"] = json_body
            if data is not None:
                kwargs["data"] = data
            if files is not None:
                kwargs["files"] = files
            if headers:
                kwargs["headers"] = headers
            if timeout:
                kwargs["timeout"] = timeout

            r = self._client.request(method, path, **kwargs)
            self.bytes_sent += len(json.dumps(json_body or "")) if json_body else 0
            self.bytes_received += len(r.content)
            return r

        try:
            r = _send()
        except Exception as e:
            raise WPApiError(0, f"Network error: {e}") from e

        # Status handling
        if r.status_code == 401:
            raise WPAuthError(401, "Authentication failed (wrong username or app password?)",
                              response_body=r.text[:500])
        if r.status_code == 403:
            raise WPAuthError(403, "Forbidden (user lacks capability)",
                              response_body=r.text[:500])
        if r.status_code == 404:
            raise WPNotFoundError(404, f"Not found: {path}",
                                  response_body=r.text[:500])
        if r.status_code == 429:
            raise WPRateLimitError(429, "Rate limited",
                                   response_body=r.text[:500])
        if r.status_code >= 500:
            raise WPApiError(r.status_code, f"Server error: {r.status_code}",
                             response_body=r.text[:500])
        if r.status_code >= 400:
            try:
                err = r.json()
                msg = err.get("message", r.text[:200])
            except Exception:
                msg = r.text[:200]
            raise WPApiError(r.status_code, msg, response_body=r.text[:500])

        try:
            data = r.json()
        except Exception:
            data = None
        return WPResponse(status=r.status_code, json_data=data, headers=dict(r.headers))

    def get(self, path: str, **kwargs) -> WPResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> WPResponse:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> WPResponse:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs) -> WPResponse:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs) -> WPResponse:
        return self.request("DELETE", path, **kwargs)

    # ─── Media multipart upload ───────────────────────────

    def upload_file(
        self,
        path: Path,
        endpoint: str = "/wp/v2/media",
        *,
        alt_text: str = "",
        caption: str = "",
        title: str = "",
        description: str = "",
        post_id: int | None = None,
    ) -> dict:
        """Upload a file (typically an image) to Media Library.

        Returns the created WP Media object dict (with id, source_url, etc.).
        """
        if not path.exists():
            raise FileNotFoundError(path)

        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "application/octet-stream"

        form: dict[str, Any] = {}
        if alt_text:
            form["alt_text"] = alt_text
        if caption:
            form["caption"] = caption
        if title:
            form["title"] = title
        if description:
            form["description"] = description
        if post_id is not None:
            form["post"] = post_id

        files = {
            "file": (path.name, path.open("rb"), mime),
        }

        try:
            r = self.request(
                "POST", endpoint,
                data=form, files=files,
                timeout=self.UPLOAD_TIMEOUT,
            )
        finally:
            files["file"][1].close()

        if r.status != 201:
            raise WPApiError(r.status, f"Media upload unexpected status {r.status}")
        return r.json_data

    # ─── Convenience ─────────────────────────────────────────

    def health_check(self) -> dict:
        """Check WP REST root + Yoast MU-plugin presence.

        Returns:
            {
              wp_rest: bool,
              seo_plugin: "yoast" | "rankmath" | None,
              yoast_mu_plugin: bool, yoast_version: str|None,
              rankmath_bridge: bool, rankmath_version: str|None,
              info: dict
            }
        """
        info: dict[str, Any] = {"site": self._base}
        wp_ok = False
        yoast_ok = False
        yoast_v = None
        rankmath_bridge_ok = False
        rankmath_v = None
        seo_plugin: str | None = None

        try:
            r = self.get("/")
            namespaces = r.json_data.get("namespaces", [])
            info["wp_namespaces"] = namespaces
            wp_ok = True
            # Detect active SEO plugin via REST namespaces
            if any(ns.startswith("rankmath") for ns in namespaces):
                seo_plugin = "rankmath"
            elif any(ns.startswith("yoast") for ns in namespaces):
                seo_plugin = "yoast"
        except Exception as e:
            info["wp_error"] = str(e)

        # Yoast MU-plugin probe
        try:
            r = self.get("/yoast/v1/ping")
            yoast_ok = True
            yoast_v = r.json_data.get("version") if r.json_data else None
            info["yoast_installed_on_site"] = r.json_data.get("yoast_installed", False) if r.json_data else None
        except WPNotFoundError:
            info["yoast_error"] = "MU-plugin endpoint not found (install seo-machine-yoast-rest.php)"
        except Exception as e:
            info["yoast_error"] = str(e)

        # Rank Math bridge probe
        try:
            r = self.get("/xuanran/v1/rank-math-bridge")
            if r.json_data and r.json_data.get("bridge_active"):
                rankmath_bridge_ok = True
                rankmath_v = r.json_data.get("rank_math_version")
                info["rankmath_bridge_keys"] = r.json_data.get("registered_keys", [])
                info["rankmath_installed"] = r.json_data.get("rank_math_active", False)
        except WPNotFoundError:
            info["rankmath_bridge_error"] = (
                "MU-plugin not installed. Install "
                "install/wordpress-mu-plugin/xuanran-rank-math-rest-bridge.php "
                "to wp-content/mu-plugins/"
            )
        except Exception as e:
            info["rankmath_bridge_error"] = str(e)

        return {
            "wp_rest": wp_ok,
            "seo_plugin": seo_plugin,
            "yoast_mu_plugin": yoast_ok,
            "yoast_version": yoast_v,
            "rankmath_bridge": rankmath_bridge_ok,
            "rankmath_version": rankmath_v,
            "info": info,
        }

    def current_user(self) -> dict:
        """Return current authenticated user info."""
        r = self.get("/wp/v2/users/me")
        return r.json_data

    def telemetry(self) -> dict:
        return {
            "call_count": self.call_count,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
        }
