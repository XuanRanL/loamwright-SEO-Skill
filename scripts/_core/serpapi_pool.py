"""
scripts/_core/serpapi_pool.py — SerpApi key pool + round-robin rotation.

Mirrors the Tavily key pool (credential_hub.get_tavily_key): SerpApi's free tier is
250 searches per account per month, so the agency pools many free accounts and rotates
across them to maximise combined free quota — exactly like the 100-key Tavily pool.

Kept self-contained (NOT folded into credential_hub) so the whole SerpApi feature is one
module pair (this + scripts/fetch/serpapi_query.py) and so it can be added without touching
credential_hub's unrelated state.

Key resolution order:
  1. ~/.xuanran-seo/credentials/serpapi-pool.json   {"keys": ["k1", "k2", ...]}
  2. ~/.xuanran-seo/credentials/serpapi.key          (single key)
  3. SERPAPI_KEY env var

Rule 7 (parallel-session isolation): the round-robin counter and the pool file are
shared user-level mutable files, so every read-modify-write goes through
file_lock.locked() — parallel sessions must not pick the same key (which would defeat
the pool and burn one account's quota while others sit idle).

CLI:
    python -m scripts._core.serpapi_pool --status [--json]   # pool size + live quota
    python -m scripts._core.serpapi_pool --add KEY           # append a key (validated first)
    python -m scripts._core.serpapi_pool --validate [--json] # live /account check per key
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Final

from scripts._core import file_lock

CRED_DIR: Final[Path] = Path.home() / ".xuanran-seo" / "credentials"
POOL_FILE: Final[Path] = CRED_DIR / "serpapi-pool.json"
COUNTER_FILE: Final[Path] = CRED_DIR / ".serpapi-rr-counter"
SINGLE_KEY_FILE: Final[Path] = CRED_DIR / "serpapi.key"
ENV_VAR: Final[str] = "SERPAPI_KEY"

ACCOUNT_URL: Final[str] = "https://serpapi.com/account.json"


def _load_keys() -> list[str]:
    """Return the list of pool keys (normalised to str), or [] if no pool file."""
    if POOL_FILE.exists():
        try:
            pool = json.loads(POOL_FILE.read_text(encoding="utf-8"))
            raw = pool.get("keys") or []
            out: list[str] = []
            for k in raw:
                v = k if isinstance(k, str) else (k.get("key", "") if isinstance(k, dict) else "")
                if v:
                    out.append(v)
            return out
        except Exception as e:  # noqa: BLE001 — log + fall through to single-key
            print(
                f"⚠ SerpApi pool load failed: {type(e).__name__}: {e} "
                f"— falling back to single key",
                file=sys.stderr,
            )
    return []


def pool_size() -> int:
    """Number of keys available for round-robin rotation (floored at 1)."""
    n = len(_load_keys())
    return n if n else 1


def get_serpapi_key() -> str:
    """Return a SerpApi key, round-robin across the pool when one is configured.

    Falls back to the single `serpapi.key` file, then the SERPAPI_KEY env var.
    The RR counter read-modify-write is wrapped in a cross-process lock (Rule 7).

    Raises:
        RuntimeError: no key configured anywhere.
    """
    keys = _load_keys()
    if keys:
        try:
            with file_lock.locked(COUNTER_FILE):
                idx = 0
                if COUNTER_FILE.exists():
                    try:
                        idx = int(COUNTER_FILE.read_text(encoding="utf-8").strip())
                    except Exception:
                        idx = 0
                idx = idx % len(keys)
                chosen = keys[idx]
                COUNTER_FILE.write_text(str(idx + 1), encoding="utf-8")
            return chosen
        except Exception as e:  # noqa: BLE001 — log + fall through
            print(
                f"⚠ SerpApi RR rotation failed: {type(e).__name__}: {e} "
                f"— falling back to single key",
                file=sys.stderr,
            )

    env_val = os.environ.get(ENV_VAR, "").strip()
    if env_val:
        return env_val
    if SINGLE_KEY_FILE.exists():
        v = SINGLE_KEY_FILE.read_text(encoding="utf-8").strip()
        if v:
            return v
    raise RuntimeError(
        "No SerpApi key configured. Add ~/.xuanran-seo/credentials/serpapi-pool.json "
        "(\"keys\": [...]), or serpapi.key, or set SERPAPI_KEY."
    )


def add_key(key: str) -> int:
    """Append a key to the pool (deduped). Returns the new pool size. Locked write."""
    key = key.strip()
    if not key:
        raise ValueError("empty key")
    CRED_DIR.mkdir(parents=True, exist_ok=True)
    with file_lock.locked(POOL_FILE):
        data: dict[str, Any] = {"keys": []}
        if POOL_FILE.exists():
            try:
                data = json.loads(POOL_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {"keys": []}
        raw = data.get("keys") or []
        norm = [k if isinstance(k, str) else k.get("key", "") for k in raw]
        norm = [k for k in norm if k]
        if key not in norm:
            norm.append(key)
        data["keys"] = norm
        POOL_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return len(norm)


def account_status(api_key: str) -> dict[str, Any]:
    """Query SerpApi /account for a key. Does NOT consume a search.

    Returns the parsed JSON (plan_searches_left / total_searches_left / this_month_usage).
    """
    import httpx

    with httpx.Client(timeout=20.0) as client:
        resp = client.get(ACCOUNT_URL, params={"api_key": api_key})
    try:
        data: dict[str, Any] = resp.json()
        return data
    except Exception:
        return {"error": f"non-JSON response (status {resp.status_code})"}


def _mask(key: str) -> str:
    return key[:6] + "…" + key[-4:] if len(key) > 12 else "***"


def main() -> int:
    ap = argparse.ArgumentParser(description="SerpApi key pool manager")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true", help="Pool size + live remaining quota per key")
    g.add_argument("--add", metavar="KEY", help="Validate + append a key to the pool")
    g.add_argument("--validate", action="store_true", help="Live /account check every pooled key")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.add:
        status = account_status(args.add)
        if status.get("error"):
            print(f"✗ key rejected by /account: {status['error']}", file=sys.stderr)
            return 1
        size = add_key(args.add)
        left = status.get("total_searches_left", status.get("plan_searches_left", "?"))
        msg = {"added": True, "pool_size": size, "searches_left": left}
        print(json.dumps(msg) if args.json else f"✓ added (pool={size}); searches_left={left}")
        return 0

    keys = _load_keys()
    if not keys:
        # maybe a single-key setup
        try:
            keys = [get_serpapi_key()]
        except RuntimeError:
            print("No SerpApi keys configured.", file=sys.stderr)
            return 1

    if args.status or args.validate:
        rows = []
        total_left = 0
        for k in keys:
            st = account_status(k)
            left = st.get("total_searches_left", st.get("plan_searches_left"))
            ok = st.get("error") is None and left is not None
            if isinstance(left, int):
                total_left += left
            rows.append({"key": _mask(k), "ok": ok,
                         "searches_left": left, "error": st.get("error")})
        out = {"pool_size": len(keys), "total_searches_left": total_left, "keys": rows}
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(f"SerpApi pool: {len(keys)} key(s), ~{total_left} searches left this month")
            for r in rows:
                icon = "✓" if r["ok"] else "✗"
                print(f"  {icon} {r['key']}  left={r['searches_left']}"
                      + (f"  ({r['error']})" if r["error"] else ""))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
