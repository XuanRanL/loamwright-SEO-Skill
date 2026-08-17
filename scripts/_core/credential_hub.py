"""
scripts/_core/credential_hub.py — Central credential resolution.

Resolves API credentials from 3 sources in priority order:
  1. Environment variable (e.g. ANTHROPIC_API_KEY)
  2. File at ~/.xuanran-seo/credentials/{provider}.key
  3. OS keychain (future; not implemented in v3.2)

Supports providers:
  - anthropic (Claude API)
  - openai (gpt-image-2, Batch API)
  - openclawroot (third-party OpenAI-compatible image gateway; realtime only)
  - tavily (web search)
  - gemini / google (Gemini API + YouTube + GSC + PageSpeed)
  - youtube (alias for google)
  - wordpress (multi-site, indexed by slug)
  - bing-indexnow (IndexNow key + key location URL)
  - crossref (no key needed; returns user-agent string for polite pool)

Usage (Python):
    from scripts._core import credential_hub as ch

    api_key = ch.get_credential("anthropic")
    wp = ch.get_wordpress_creds("example-com")  # WPCreds dataclass
    status = ch.check_all()  # dict for health_check

Usage (CLI):
    python -m scripts._core.credential_hub --check --json
    python -m scripts._core.credential_hub --get anthropic
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Final, Literal

from scripts._core import file_lock


# ─── Constants ──────────────────────────────────────────────────────

XS_HOME: Final[Path] = Path.home() / ".xuanran-seo"
CRED_DIR: Final[Path] = XS_HOME / "credentials"
WP_DIR: Final[Path] = CRED_DIR / "wordpress"

# Provider → (env_var, file_basename)
_PROVIDERS: Final[dict[str, tuple[str, str]]] = {
    "anthropic":           ("ANTHROPIC_API_KEY",     "anthropic.key"),
    "openai":              ("OPENAI_API_KEY",        "openai.key"),
    # Third-party OpenAI-compatible image gateway (configurable primary, see
    # scripts/_core/image_provider.py). Official 'openai' above stays as fallback.
    "openclawroot":        ("OPENCLAWROOT_API_KEY",  "openclawroot.key"),
    "chatgpt-code":        ("CHATGPT_CODE_API_KEY",  "chatgpt-code.key"),
    # mikuapi.org — third-party OpenAI-compatible image gateway (gpt-image-2,
    # /v1/images/generations). Verified 2026-06-28: returns EXACT requested pixels
    # for 3840x2160 AND 2880x2880 (passes the hard dimension gate), real OpenAI
    # gpt-image output (C2PA provenance preserved); long-edge cap 3840. Primary
    # image provider as of 2026-06-28; chatgpt-code/vertex-gemini/openai = fallbacks.
    "mikuapi":             ("MIKUAPI_API_KEY",       "mikuapi.key"),
    # Google Vertex AI express-mode image gen (Gemini 3 Pro Image / Nano Banana
    # Pro — true 4K, ~10x cheaper than OpenAI). The AQ.-prefix API key is passed
    # via the x-goog-api-key header (NOT Bearer/?key=); it ONLY works on Vertex
    # express, not AI Studio generativelanguage. See image_provider.py +
    # openai_image_pipeline._generate_vertex_gemini.
    "vertex-gemini":       ("VERTEX_GEMINI_API_KEY",  "vertex-gemini.key"),
    "tavily":              ("TAVILY_API_KEY",        "tavily.key"),
    "gemini":              ("GOOGLE_API_KEY",        "gemini.key"),
    "google":              ("GOOGLE_API_KEY",        "gemini.key"),  # alias
    "google_api_key":      ("GOOGLE_API_KEY",        "gemini.key"),  # audit scripts
    "google_psi_api_key":  ("GOOGLE_API_KEY",        "gemini.key"),  # pagespeed_check.py
    "youtube":             ("YOUTUBE_API_KEY",       "youtube.key"),
    "bing-indexnow":       ("BING_INDEXNOW_KEY",     "bing-indexnow.key"),
    "bing-webmaster":      ("BING_WEBMASTER_API_KEY", "bing-webmaster.key"),
    "perplexity":          ("PERPLEXITY_API_KEY",    "perplexity.key"),
    "geoapify":            ("GEOAPIFY_API_KEY",      "geoapify.key"),
    "moz_access_id":       ("MOZ_ACCESS_ID",         "moz-access-id.key"),
    "moz_secret_key":      ("MOZ_SECRET_KEY",        "moz-secret-key.key"),
    "scraperapi":          ("SCRAPERAPI_KEY",         "scraperapi.key"),
    # Independent web/image search source (quota separate from Tavily — used as a
    # second image source for real-product-photo sourcing, dodges Tavily 432).
    # Brave key has BOTH /res/v1/images/search and /res/v1/web/search access.
    "brave-search":        ("BRAVE_SEARCH_API_KEY",   "brave-search.key"),
    "brave":               ("BRAVE_SEARCH_API_KEY",   "brave-search.key"),  # alias
    # Firecrawl scrape/crawl/search (canonical high-res product-image extraction
    # from a specific page + JS-heavy research). Pool of 2 accounts in
    # firecrawl-pool.json; firecrawl.key is the first/primary.
    "firecrawl":           ("FIRECRAWL_API_KEY",      "firecrawl.key"),
}

# Multi-tenant / agency-scale credential paths
# Service account: one JSON for all sites where SA has been verified as user.
GOOGLE_SA_FILE: Final[Path] = CRED_DIR / "google-service-account.json"
GSC_OAUTH_DIR:  Final[Path] = CRED_DIR / "gsc-oauth"      # per-site tokens
BING_WEBMASTER_DIR: Final[Path] = CRED_DIR / "bing-webmaster"  # per-site keys (optional)


# ─── Custom exceptions ─────────────────────────────────────────────

class CredentialError(Exception):
    """Base exception for credential issues."""


class CredentialNotFoundError(CredentialError):
    """Credential could not be resolved from any source."""


class CredentialFormatError(CredentialError):
    """Credential found but format invalid."""


# ─── WordPress credential schema ───────────────────────────────────

@dataclass(frozen=True)
class WPCreds:
    """WordPress site credentials (one per site)."""
    url: str
    username: str
    app_password: str
    site_slug: str

    def basic_auth_header(self) -> str:
        """Return value for Authorization: Basic ..."""
        import base64
        token = base64.b64encode(f"{self.username}:{self.app_password}".encode()).decode()
        return f"Basic {token}"


@dataclass(frozen=True)
class BingIndexNow:
    """IndexNow key + hosted location."""
    key: str
    key_location: str   # full URL: https://your-site.com/abcd1234.txt
    host: str           # your-site.com


@dataclass(frozen=True)
class GoogleServiceAccount:
    """Google service account credentials for GSC API + other Google services.

    Multi-tenant: ONE service account verified as user across many properties.
    Path points to a JSON file (the SA key, downloaded from GCP IAM console).
    """
    sa_json_path: str
    client_email: str           # extracted from JSON
    project_id: str             # extracted from JSON

    @classmethod
    def from_file(cls, path: Path) -> "GoogleServiceAccount":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            sa_json_path=str(path),
            client_email=data.get("client_email", ""),
            project_id=data.get("project_id", ""),
        )


@dataclass(frozen=True)
class GscOAuth:
    """Per-site OAuth refresh-token for sites where SA isn't verified."""
    site_slug: str
    refresh_token: str
    client_id: str
    client_secret: str
    token_uri: str = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class BingWebmasterCred:
    """Bing Webmaster Tools API credentials.

    API key obtained from https://www.bing.com/webmasters → Settings → API Access.
    One key works across all verified sites in the BWT account.
    """
    api_key: str
    user_agent: str = "xuanran-seo-bwt-client"


# ─── Core resolution ────────────────────────────────────────────────

def get_credential(provider: str) -> str:
    """Resolve a single-string credential from env or file.

    Args:
        provider: One of the keys in _PROVIDERS dict.

    Returns:
        The credential string (stripped).

    Raises:
        CredentialNotFoundError: Neither env var nor file present.
        ValueError: Unknown provider.
    """
    if provider not in _PROVIDERS:
        raise ValueError(f"Unknown provider: {provider!r}. Known: {sorted(_PROVIDERS)}")

    env_var, file_name = _PROVIDERS[provider]

    # 1. Environment variable wins
    env_val = os.environ.get(env_var, "").strip()
    if env_val:
        return env_val

    # 2. File at ~/.xuanran-seo/credentials/{name}
    cred_file = CRED_DIR / file_name
    if cred_file.exists():
        try:
            content = cred_file.read_text(encoding="utf-8").strip()
            if content:
                return content
        except OSError as e:
            raise CredentialFormatError(f"Cannot read {cred_file}: {e}") from e

    raise CredentialNotFoundError(
        f"No credential for {provider!r}: env var ${env_var} not set, "
        f"and file {cred_file} not found or empty."
    )


def _load_tavily_pool() -> dict[str, Any]:
    """Load the Tavily pool JSON from disk. Returns {} on any error."""
    pool_file = CRED_DIR / "tavily-pool.json"
    try:
        if pool_file.exists():
            return json.loads(pool_file.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except Exception as e:
        print(
            f"⚠ Tavily pool load failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
    return {}


def _save_tavily_pool(pool: dict[str, Any]) -> None:
    """Save the Tavily pool JSON using a cross-process lock (Rule 7).

    Writes atomically (temp + os.replace) so lock-free readers (get_tavily_key,
    tavily_pool._load_ledger) never observe a torn / half-written file.
    """
    pool_file = CRED_DIR / "tavily-pool.json"
    with file_lock.locked(pool_file):
        file_lock.atomic_write_text(pool_file, json.dumps(pool, indent=2))


def _update_tavily_pool(mutate: Callable[[dict[str, Any]], None]) -> None:
    """Locked read-modify-write of tavily-pool.json (Rule 7 TOCTOU fix).

    Atomically reads the pool, calls mutate(pool) to edit in place, then writes
    back within a single lock. Ensures concurrent calls don't clobber each other's
    changes.

    Args:
        mutate: Callable that takes pool dict, modifies it in place, returns None.
    """
    pool_file = CRED_DIR / "tavily-pool.json"
    try:
        with file_lock.locked(pool_file):
            try:
                pool: dict[str, Any] = (
                    json.loads(pool_file.read_text(encoding="utf-8"))
                    if pool_file.exists()
                    else {}
                )
            except Exception:
                return
            if not isinstance(pool, dict) or not isinstance(pool.get("keys"), list):
                return
            mutate(pool)
            # Atomic replace so lock-free readers never see a torn file (Rule 7).
            file_lock.atomic_write_text(pool_file, json.dumps(pool, indent=2))
    except Exception as e:
        print(
            f"⚠ tavily pool update failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )


def _mark_tavily_key_status(key: str, status: str) -> None:
    """Set a Tavily pool key's persistent status in the pool ledger.

    Finds the entry whose "key" value equals ``key``, sets status=``status``
    and checked_at=<UTC ISO now>, then persists the change.  No-op if the key
    is not found in the pool.  NEVER raises — called from within retry loops
    where a secondary failure must not mask the primary one.

    All read-modify-write is atomic inside a single lock (Rule 7).
    """
    import datetime

    def _do_mark(pool: dict[str, Any]) -> None:
        raw_keys: list[Any] = pool.get("keys") or []
        found = False
        new_keys: list[Any] = []
        for entry in raw_keys:
            if isinstance(entry, str):
                k_val: str = entry
                entry_dict: dict[str, Any] = {"key": entry}
            else:
                entry_dict = dict(entry) if isinstance(entry, dict) else {}
                k_val = entry_dict.get("key", "")
            if k_val == key:
                entry_dict["status"] = status
                entry_dict["checked_at"] = (
                    datetime.datetime.now(datetime.timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
                found = True
                new_keys.append(entry_dict)
            else:
                # Preserve original form for entries that were not matched
                new_keys.append(entry)
        if found:
            pool["keys"] = new_keys

    _update_tavily_pool(_do_mark)


def mark_tavily_key_exhausted(key: str) -> None:
    """Mark a key's monthly credits as spent (resets with the billing cycle)."""
    _mark_tavily_key_status(key, "exhausted")


def mark_tavily_key_invalid(key: str) -> None:
    """Mark a key as DEAD (revoked / account deactivated / 401) — never auto-recovers.

    2026-07-01: previously no such state existed, so a deactivated key stayed
    status-less (treated active) and was re-selected by round-robin on every
    run. `tavily_pool --refresh` clears this only if /usage starts answering for
    the key again (i.e. the account was reactivated).
    """
    _mark_tavily_key_status(key, "invalid")


def set_tavily_key_balance(
    key: str,
    balance: int,
    *,
    exhausted_threshold: int = 5,
) -> None:
    """Update the balance and derived status of a Tavily pool key.

    Sets balance, checked_at (UTC now), and status:
      - balance > exhausted_threshold  → "active"
      - balance <= exhausted_threshold → "exhausted"

    All read-modify-write is atomic inside a single lock (Rule 7).
    NEVER raises.
    """
    import datetime

    def _do_update(pool: dict[str, Any]) -> None:
        raw_keys: list[Any] = pool.get("keys") or []
        found = False
        new_keys: list[Any] = []
        for entry in raw_keys:
            if isinstance(entry, str):
                k_val: str = entry
                entry_dict: dict[str, Any] = {"key": entry}
            else:
                entry_dict = dict(entry) if isinstance(entry, dict) else {}
                k_val = entry_dict.get("key", "")
            if k_val == key:
                entry_dict["balance"] = balance
                entry_dict["checked_at"] = (
                    datetime.datetime.now(datetime.timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
                entry_dict["status"] = (
                    "active" if balance > exhausted_threshold else "exhausted"
                )
                found = True
                new_keys.append(entry_dict)
            else:
                new_keys.append(entry)
        if found:
            pool["keys"] = new_keys

    _update_tavily_pool(_do_update)


def get_tavily_key() -> str:
    """Return a Tavily API key with balance-aware round-robin rotation.

    Resolution order:
      1. ~/.xuanran-seo/credentials/tavily-pool.json (balance-aware multi-key rotation)
      2. ~/.xuanran-seo/credentials/tavily.key       (single key)
      3. TAVILY_API_KEY env var

    With a pool, only keys whose status is NOT "exhausted" are eligible for
    selection.  If ALL keys are exhausted the function falls back to rotating
    across all keys (with a stderr warning) so callers are never left without
    a key to try — the caller (tavily_retry.with_retry) handles 429s reactively.
    Entries that lack a "status" field are treated as active (backward compat).

    The round-robin counter file is read/updated under a cross-process lock
    (Rule 7 — parallel sessions must not pick the same key).
    """
    pool_file = CRED_DIR / "tavily-pool.json"
    if pool_file.exists():
        try:
            pool = json.loads(pool_file.read_text(encoding="utf-8"))
            raw_keys: list[Any] = pool.get("keys") or []
            if raw_keys:
                # Normalize every entry to a dict for uniform handling
                all_entries: list[dict[str, Any]] = []
                for entry in raw_keys:
                    if isinstance(entry, str):
                        all_entries.append({"key": entry})
                    elif isinstance(entry, dict):
                        all_entries.append(entry)

                # Build active subset; missing "status" → treated as active.
                # "invalid" (dead/revoked key, 2026-07-01) is skipped exactly
                # like "exhausted" — but NEVER falls back into rotation below:
                # a revoked key can't serve requests no matter how desperate.
                _dead = {"exhausted", "invalid"}
                active: list[dict[str, Any]] = [
                    e for e in all_entries if e.get("status") not in _dead
                ]

                if not active:
                    # All exhausted/invalid: warn + fall back to rotating the
                    # exhausted ones (they may have reset with the billing
                    # cycle) — but never the invalid ones.
                    print(
                        "⚠ All Tavily keys marked exhausted/invalid — run "
                        "`python -m scripts._core.tavily_pool --refresh` "
                        "to update balances",
                        file=sys.stderr,
                    )
                    active = [e for e in all_entries if e.get("status") != "invalid"] or all_entries

                counter_file = CRED_DIR / ".tavily-rr-counter"
                # Cross-process lock around the read-modify-write: parallel
                # sessions must not read the same counter value and pick the
                # same key (which defeats the multi-key pool and burns quota).
                with file_lock.locked(counter_file):
                    idx = 0
                    if counter_file.exists():
                        try:
                            idx = int(
                                counter_file.read_text(encoding="utf-8").strip()
                            )
                        except Exception:
                            idx = 0
                    idx = idx % len(active)
                    chosen: dict[str, Any] = active[idx]
                    # Wrap the counter so the file stays small (Fix 4)
                    counter_file.write_text(str((idx + 1) % len(active)), encoding="utf-8")

                key_val: str = chosen.get("key", "")
                if key_val:
                    return key_val
        except Exception as e:
            # Audit 2026-05-22 P1 — log silent-fallback
            print(
                f"⚠ Tavily key round-robin rotation failed: {type(e).__name__}: {e} "
                f"— falling back to single 'tavily' credential",
                file=sys.stderr,
            )
    return get_credential("tavily")


def tavily_pool_size() -> int:
    """Number of keys available for Tavily round-robin rotation (>= 1).

    The retry layer (tavily_retry.with_retry) uses this to rotate through the
    WHOLE pool before giving up. Root cause of the 2026-06-04 batch incident: a
    10-key pool existed, but the expensive /research call capped rotation at 3,
    so it never reached the one key that still had research credits and the pro
    deep-research silently fell back on 2 of 3 articles. Returns 1 when no pool
    is configured (single-key / env-var path), so small setups keep a couple of
    transient retries on the same key.
    """
    pool_file = CRED_DIR / "tavily-pool.json"
    if pool_file.exists():
        try:
            pool = json.loads(pool_file.read_text(encoding="utf-8"))
            keys = pool.get("keys") or []
            if keys:
                return len(keys)
        except Exception:
            pass
    return 1


def get_wordpress_creds(site_slug: str) -> WPCreds:
    """Load WordPress credentials for a specific site.

    Reads from ~/.xuanran-seo/credentials/wordpress/{site_slug}.json:
        { "url": "...", "username": "...", "app_password": "..." }

    Args:
        site_slug: Project slug (e.g. 'example-com')

    Returns:
        WPCreds dataclass.

    Raises:
        CredentialNotFoundError: Site config file missing.
        CredentialFormatError: Missing required fields.
    """
    if not site_slug or not site_slug.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"Invalid site_slug: {site_slug!r}")

    cfg_file = WP_DIR / f"{site_slug}.json"
    if not cfg_file.exists():
        raise CredentialNotFoundError(
            f"WordPress config not found for site {site_slug!r}. "
            f"Expected: {cfg_file}"
        )

    try:
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CredentialFormatError(f"Invalid JSON in {cfg_file}: {e}") from e

    required = {"url", "username", "app_password"}
    missing = required - data.keys()
    if missing:
        raise CredentialFormatError(
            f"WordPress config {cfg_file} missing keys: {sorted(missing)}"
        )

    url = data["url"].rstrip("/")
    if not url.startswith("https://"):
        raise CredentialFormatError(
            f"WordPress URL must be HTTPS (Application Passwords requirement): {url}"
        )

    return WPCreds(
        url=url,
        username=data["username"],
        app_password=data["app_password"],
        site_slug=site_slug,
    )


def get_bing_indexnow(project_slug: str | None = None) -> BingIndexNow:
    """Resolve Bing IndexNow key + key location URL.

    The key is the value (32-char hex). The key location is a URL
    where the key file is hosted on your domain. Both must be configured.

    PER-PROJECT FIRST (2026-08-17): the credential binds to ONE host, but the
    fleet is ~13 sites — a single global file can only ever fit one of them
    (every other site's submission 422s: URL host ≠ credential host). When a
    project_slug is given, ~/.xuanran-seo/credentials/bing-indexnow/{slug}.json
    wins; the global bing-indexnow.json remains as the single-site fallback.
    The same key VALUE may be reused across hosts — each host just serves its
    own {key}.txt — so minting once and stamping 13 per-slug files is fine.

    File shape (both levels):
        { "key": "abcd...", "key_location": "https://example.com/abcd.txt", "host": "example.com" }

    Env fallback: BING_INDEXNOW_KEY, BING_INDEXNOW_KEY_LOCATION, BING_INDEXNOW_HOST
    """
    candidates = []
    if project_slug:
        candidates.append(CRED_DIR / "bing-indexnow" / f"{project_slug}.json")
    candidates.append(CRED_DIR / "bing-indexnow.json")
    for cfg_file in candidates:
        if cfg_file.exists():
            try:
                data = json.loads(cfg_file.read_text(encoding="utf-8"))
                return BingIndexNow(
                    key=data["key"],
                    key_location=data["key_location"],
                    host=data["host"],
                )
            except (json.JSONDecodeError, KeyError) as e:
                raise CredentialFormatError(f"Invalid {cfg_file.name}: {e}") from e

    key = os.environ.get("BING_INDEXNOW_KEY", "").strip()
    loc = os.environ.get("BING_INDEXNOW_KEY_LOCATION", "").strip()
    host = os.environ.get("BING_INDEXNOW_HOST", "").strip()
    if key and loc and host:
        return BingIndexNow(key=key, key_location=loc, host=host)

    raise CredentialNotFoundError(
        "Bing IndexNow not configured. Set credentials/bing-indexnow/{slug}.json "
        "(per-site, preferred on a multi-site fleet), credentials/bing-indexnow.json "
        "(single-site), or BING_INDEXNOW_{KEY,KEY_LOCATION,HOST} env vars."
    )


def get_google_service_account() -> GoogleServiceAccount:
    """Resolve Google service account JSON.

    Looks in this order:
      1. $GOOGLE_APPLICATION_CREDENTIALS env (Google convention)
      2. ~/.xuanran-seo/credentials/google-service-account.json
    """
    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(GOOGLE_SA_FILE)

    for p in candidates:
        if p.exists():
            try:
                return GoogleServiceAccount.from_file(p)
            except (json.JSONDecodeError, OSError) as e:
                raise CredentialFormatError(f"Invalid SA JSON at {p}: {e}") from e

    raise CredentialNotFoundError(
        "Google service account not configured. "
        f"Set $GOOGLE_APPLICATION_CREDENTIALS or place JSON at {GOOGLE_SA_FILE}.\n"
        "Setup: GCP IAM → Service Accounts → Create → Download JSON key. "
        "Then add the SA email as a 'restricted' user in each Search Console "
        "property at https://search.google.com/search-console."
    )


def get_gsc_oauth(site_slug: str) -> GscOAuth:
    """Per-site GSC OAuth refresh-token credentials.

    Use this for client sites where service account can't be added.
    Reads ~/.xuanran-seo/credentials/gsc-oauth/{site_slug}.json:
        { "refresh_token": "...", "client_id": "...", "client_secret": "..." }
    """
    if not site_slug or not site_slug.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"Invalid site_slug: {site_slug!r}")

    cfg_file = GSC_OAUTH_DIR / f"{site_slug}.json"
    if not cfg_file.exists():
        raise CredentialNotFoundError(
            f"GSC OAuth not found for site {site_slug!r}. Expected: {cfg_file}"
        )

    try:
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CredentialFormatError(f"Invalid JSON in {cfg_file}: {e}") from e

    for k in ("refresh_token", "client_id", "client_secret"):
        if k not in data:
            raise CredentialFormatError(f"{cfg_file} missing key: {k}")

    return GscOAuth(
        site_slug=site_slug,
        refresh_token=data["refresh_token"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
    )


def get_bing_webmaster() -> BingWebmasterCred:
    """Resolve Bing Webmaster Tools API key.

    Sources:
      1. $BING_WEBMASTER_API_KEY env var
      2. ~/.xuanran-seo/credentials/bing-webmaster.key
      3. ~/.xuanran-seo/credentials/bing-webmaster.json (full config)
    """
    cfg_file = CRED_DIR / "bing-webmaster.json"
    if cfg_file.exists():
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            return BingWebmasterCred(
                api_key=data["api_key"],
                user_agent=data.get("user_agent", "xuanran-seo-bwt-client"),
            )
        except (json.JSONDecodeError, KeyError) as e:
            raise CredentialFormatError(f"Invalid bing-webmaster.json: {e}") from e

    try:
        key = get_credential("bing-webmaster")
        return BingWebmasterCred(api_key=key)
    except CredentialNotFoundError:
        raise CredentialNotFoundError(
            "Bing Webmaster API key not found. "
            "Set $BING_WEBMASTER_API_KEY or create "
            f"{CRED_DIR / 'bing-webmaster.key'}. "
            "Get the key at https://www.bing.com/webmasters → Settings → API Access."
        )


def get_crossref_user_agent() -> str:
    """Return User-Agent string for Crossref polite pool.

    Crossref recommends:  YourApp/Version (mailto:contact@example.com)
    Reads from ~/.xuanran-seo/config.yaml: contact_email, otherwise default.
    """
    contact = os.environ.get("CROSSREF_MAILTO", "")
    if not contact:
        # Try config.yaml
        cfg = XS_HOME / "config.yaml"
        if cfg.exists():
            try:
                import yaml  # type: ignore[import-untyped]
                data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
                contact = data.get("contact_email", "") if isinstance(data, dict) else ""
            except Exception as e:
                # Audit 2026-05-22 P1 — log silent-fallback
                print(
                    f"⚠ contact_email load from config failed: "
                    f"{type(e).__name__}: {e} — using default UA contact",
                    file=sys.stderr,
                )
    if not contact:
        contact = "contact@xuanran-seo.local"
    return f"XuanranSEO/3.2.0 (mailto:{contact})"


# ─── Bulk check (for health_check) ──────────────────────────────────

def check_all() -> dict[str, dict[str, Any]]:
    """Check all known providers, return per-provider status.

    Returns:
        {provider: {"found": bool, "source": "env"|"file"|"missing", "error": str|None}}
    """
    result: dict[str, dict[str, Any]] = {}

    # Single-string providers
    for provider in _PROVIDERS:
        if provider == "google":   # skip alias
            continue
        env_var, file_name = _PROVIDERS[provider]
        env_val = os.environ.get(env_var, "").strip()
        file_path = CRED_DIR / file_name
        file_exists = file_path.exists() and file_path.read_text(encoding="utf-8").strip()

        if env_val:
            result[provider] = {"found": True, "source": "env", "error": None}
        elif file_exists:
            result[provider] = {"found": True, "source": "file", "error": None}
        else:
            result[provider] = {
                "found": False,
                "source": "missing",
                "error": f"set ${env_var} or write {file_path}",
            }

    # WordPress (multi-site)
    wp_sites = []
    if WP_DIR.exists():
        for f in WP_DIR.glob("*.json"):
            try:
                creds = get_wordpress_creds(f.stem)
                wp_sites.append({"slug": creds.site_slug, "url": creds.url, "ok": True})
            except Exception as e:
                wp_sites.append({"slug": f.stem, "ok": False, "error": str(e)})
    result["wordpress"] = {
        "found": len(wp_sites) > 0,
        "source": "files",
        "sites": wp_sites,
    }

    return result


# ─── CLI ──────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Credential hub CLI")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="Check all providers")
    g.add_argument("--get", metavar="PROVIDER", help="Get a single credential")
    g.add_argument("--get-wp", metavar="SLUG", help="Get WordPress credentials for site")
    ap.add_argument("--json", action="store_true", help="JSON output (for programmatic use)")
    args = ap.parse_args()

    if args.check:
        status = check_all()
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            for k, v in status.items():
                icon = "✓" if v.get("found") else "✗"
                src = v.get("source", "")
                print(f"  {icon} {k:20s} ({src})")
                if v.get("error"):
                    print(f"      → {v['error']}")
        # Exit code based on critical missing keys
        critical = ["anthropic", "openai", "tavily"]
        if all(status.get(k, {}).get("found") for k in critical):
            return 0
        return 1

    if args.get:
        try:
            val = get_credential(args.get)
            if args.json:
                print(json.dumps({"provider": args.get, "value": val, "found": True}))
            else:
                # Print only first 8 + last 4 chars (security)
                masked = val[:8] + "..." + val[-4:] if len(val) > 12 else "***"
                print(f"{args.get}: {masked}")
            return 0
        except CredentialError as e:
            if args.json:
                print(json.dumps({"provider": args.get, "found": False, "error": str(e)}),
                      file=sys.stderr)
            else:
                print(f"Error: {e}", file=sys.stderr)
            return 1

    if args.get_wp:
        try:
            creds = get_wordpress_creds(args.get_wp)
            data = asdict(creds)
            data["app_password"] = "***" + creds.app_password[-4:]  # mask
            if args.json:
                print(json.dumps(data, indent=2))
            else:
                print(f"Site:     {creds.site_slug}")
                print(f"URL:      {creds.url}")
                print(f"Username: {creds.username}")
                print(f"Password: ***{creds.app_password[-4:]}")
            return 0
        except CredentialError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
