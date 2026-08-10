"""
scripts/_core/google_creds.py — unified Google OAuth credential resolver (GSC + GA4).

Why this exists
---------------
The audit/monitor GSC + GA4 scripts each looked for credentials in a DIFFERENT place
(env vars `GSC_CREDENTIALS_PATH`/`GA4_CREDENTIALS_PATH`, or `gsc-oauth/{slug}.json`, or a
service account) and NONE of them read the token that `scripts/audit/google_oauth_setup.py`
actually writes — so the user's connected Google account was orphaned (a Rule-6 gap: the
credential is present but no consumer reads it).

This module is the single source of truth: it reads
`~/.xuanran-seo/credentials/google-oauth-token.json` (a user OAuth token with refresh_token +
client_id/secret) and returns a fresh access token. Scopes on that token:
`webmasters.readonly` (GSC) + `analytics.readonly` (GA4).

Usage:
    from scripts._core import google_creds
    headers = google_creds.auth_header()          # {"Authorization": "Bearer ..."}
    token   = google_creds.get_access_token()
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Final

import httpx

TOKEN_FILE: Final[Path] = Path.home() / ".xuanran-seo" / "credentials" / "google-oauth-token.json"

_cache: dict[str, Any] = {}


class GoogleCredError(RuntimeError):
    pass


def _load_token() -> dict[str, Any]:
    if not TOKEN_FILE.exists():
        raise GoogleCredError(
            f"Google OAuth token not found: {TOKEN_FILE}. "
            f"Run `python -m scripts.audit.google_oauth_setup` to connect GSC + GA4."
        )
    data: dict[str, Any] = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    for k in ("client_id", "client_secret", "refresh_token", "token_uri"):
        if not data.get(k):
            raise GoogleCredError(f"google-oauth-token.json missing required field: {k}")
    return data


def get_access_token(force: bool = False) -> str:
    """Return a valid access token, refreshing via the stored refresh_token.

    The token is cached in-process until ~60s before expiry so repeated GSC/GA4 calls
    in one run don't re-hit the token endpoint.
    """
    now = time.time()
    if not force and _cache.get("access_token") and _cache.get("expires_at", 0.0) > now + 60:
        token: str = _cache["access_token"]
        return token

    tok = _load_token()
    resp = httpx.post(
        tok["token_uri"],
        data={
            "grant_type": "refresh_token",
            "client_id": tok["client_id"],
            "client_secret": tok["client_secret"],
            "refresh_token": tok["refresh_token"],
        },
        timeout=30.0,
    )
    if resp.status_code != 200:
        raise GoogleCredError(f"Google token refresh failed: {resp.status_code} {resp.text[:160]}")
    j = resp.json()
    access_token: str = j["access_token"]
    _cache["access_token"] = access_token
    _cache["expires_at"] = now + int(j.get("expires_in", 3600))
    return access_token


def auth_header() -> dict[str, str]:
    """Return the Authorization header for a Google REST API call."""
    return {"Authorization": f"Bearer {get_access_token()}"}


def scopes() -> list[str]:
    """The scopes granted on the stored token (for diagnostics)."""
    tok = _load_token()
    sc = tok.get("scopes") or tok.get("scope") or []
    if isinstance(sc, str):
        return sc.split()
    return list(sc)
