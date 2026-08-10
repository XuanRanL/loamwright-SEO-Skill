#!/usr/bin/env python3
"""One-time OAuth setup for Google APIs (GSC + GA4 + CrUX).

Opens browser for user authorization, captures refresh token, stores it
for future API calls by audit agents.

Usage:
    python -m scripts.audit.google_oauth_setup
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]

REDIRECT_PORT = 8085
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"

CRED_DIR = Path.home() / ".xuanran-seo" / "credentials"
TOKEN_FILE = CRED_DIR / "google-oauth-token.json"
CLIENT_FILE = CRED_DIR / "google-oauth-client.json"


def load_client_credentials() -> tuple[str, str]:
    """Resolve the OAuth client id/secret — NEVER hardcoded in the repo.

    Priority: env vars GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET →
    ~/.xuanran-seo/credentials/google-oauth-client.json ({"client_id", "client_secret"}).
    """
    env_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    env_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
    if env_id and env_secret:
        return env_id, env_secret
    if CLIENT_FILE.exists():
        data = json.loads(CLIENT_FILE.read_text(encoding="utf-8"))
        cid = str(data.get("client_id", ""))
        secret = str(data.get("client_secret", ""))
        if cid and secret:
            return cid, secret
    raise SystemExit(
        "No Google OAuth client credentials found.\n"
        "Create an OAuth 2.0 Client ID (Desktop app) in Google Cloud Console\n"
        "(APIs & Services → Credentials), then either:\n"
        f'  - write {{"client_id": "...", "client_secret": "..."}} to {CLIENT_FILE}, or\n'
        "  - set GOOGLE_OAUTH_CLIENT_ID + GOOGLE_OAUTH_CLIENT_SECRET env vars."
    )


class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    auth_code: str | None = None

    def do_GET(self) -> None:
        qs = parse_qs(urlparse(self.path).query)
        code = qs.get("code", [None])[0]
        if code:
            _OAuthCallbackHandler.auth_code = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Authorization successful!</h2>"
                             b"<p>You can close this tab and return to the terminal.</p>"
                             b"</body></html>")
        else:
            error = qs.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<html><body><h2>Error: {error}</h2></body></html>".encode())

    def log_message(self, format: str, *args: object) -> None:
        pass


def run_oauth_flow() -> dict[str, object]:
    """Run the full OAuth flow: open browser → capture code → exchange for tokens."""
    client_id, client_secret = load_client_credentials()
    auth_url = (
        f"{AUTH_ENDPOINT}"
        f"?client_id={client_id}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={'+'.join(SCOPES)}"
        f"&access_type=offline"
        f"&prompt=consent"
    )

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _OAuthCallbackHandler)

    print("Opening browser for Google authorization...", file=sys.stderr)
    print(f"If browser doesn't open, visit:\n{auth_url}\n", file=sys.stderr)
    webbrowser.open(auth_url)

    server.handle_request()
    server.server_close()

    code = _OAuthCallbackHandler.auth_code
    if not code:
        print("ERROR: No authorization code received.", file=sys.stderr)
        sys.exit(1)

    print("Authorization code received. Exchanging for tokens...", file=sys.stderr)

    resp = httpx.post(TOKEN_ENDPOINT, data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=30)

    if resp.status_code != 200:
        print(f"ERROR: Token exchange failed: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)

    tokens = resp.json()

    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": tokens["refresh_token"],
        "access_token": tokens.get("access_token", ""),
        "token_uri": TOKEN_ENDPOINT,
        "scopes": SCOPES,
    }

    CRED_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
    print(f"\nTokens saved to: {TOKEN_FILE}", file=sys.stderr)
    print("Google Search Console + Analytics access is now configured!", file=sys.stderr)

    return token_data


def get_access_token() -> str:
    """Read stored refresh token and get a fresh access token."""
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(f"No OAuth token at {TOKEN_FILE}. Run: python -m scripts.audit.google_oauth_setup")

    data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    resp = httpx.post(TOKEN_ENDPOINT, data={
        "client_id": data["client_id"],
        "client_secret": data["client_secret"],
        "refresh_token": data["refresh_token"],
        "grant_type": "refresh_token",
    }, timeout=30)

    if resp.status_code != 200:
        raise RuntimeError(f"Token refresh failed: {resp.status_code} {resp.text}")

    tokens = resp.json()
    return str(tokens["access_token"])


def main() -> None:
    print("=== Google OAuth Setup for Website Audit ===\n", file=sys.stderr)
    print("This will authorize access to:", file=sys.stderr)
    print("  - Google Search Console (readonly)", file=sys.stderr)
    print("  - Google Analytics 4 (readonly)\n", file=sys.stderr)

    run_oauth_flow()

    print("\nVerifying access token...", file=sys.stderr)
    try:
        token = get_access_token()
        print(f"Access token obtained: {token[:20]}...", file=sys.stderr)
        print("\nAll good! The audit agents can now access GSC + GA4.", file=sys.stderr)
    except Exception as e:
        print(f"WARNING: Token verification failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
