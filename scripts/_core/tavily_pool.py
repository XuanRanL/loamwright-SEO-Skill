"""scripts/_core/tavily_pool.py — Tavily key pool balance manager.

Reads/writes the balance ledger stored inside tavily-pool.json.  Does NOT expose
raw key values in any output — names only.

CLI:
    python -m scripts._core.tavily_pool [--status]              # default: print table
    python -m scripts._core.tavily_pool --refresh               # fetch usage from API
    python -m scripts._core.tavily_pool --csv                   # table as CSV
    python -m scripts._core.tavily_pool --json                  # machine JSON
    python -m scripts._core.tavily_pool --refresh --batch-size 3 --batch-pause 1.0

Rules:
  - httpx for HTTP (not requests).
  - file_lock for all writes (Rule 7 — pool file is shared across parallel sessions).
  - NEVER prints raw key values; uses "name" field (or auto-generated key-N label).
  - Graceful-degrade: bad pool file / network error → log to stderr, continue.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Final

from scripts._core import credential_hub, file_lock

CRED_DIR: Final[Path] = Path.home() / ".xuanran-seo" / "credentials"
POOL_FILE: Final[Path] = CRED_DIR / "tavily-pool.json"
USAGE_URL: Final[str] = "https://api.tavily.com/usage"


# ─── Ledger helpers ───────────────────────────────────────────────────────────


def _load_ledger() -> list[dict[str, Any]]:
    """Return pool entries as a normalised list of dicts (safe to iterate over)."""
    if not POOL_FILE.exists():
        return []
    try:
        pool: dict[str, Any] = json.loads(POOL_FILE.read_text(encoding="utf-8"))
        raw_keys: list[Any] = pool.get("keys") or []
        entries: list[dict[str, Any]] = []
        for i, entry in enumerate(raw_keys):
            if isinstance(entry, str):
                entries.append(
                    {
                        "name": f"key-{i + 1}",
                        "key": entry,
                        "status": "active",
                        "balance": None,
                        "checked_at": None,
                    }
                )
            elif isinstance(entry, dict):
                entries.append(
                    {
                        "name": entry.get("name") or f"key-{i + 1}",
                        "key": entry.get("key", ""),
                        "status": entry.get("status", "active"),
                        "balance": entry.get("balance"),
                        "checked_at": entry.get("checked_at"),
                    }
                )
        return entries
    except Exception as e:
        print(
            f"⚠ Pool ledger load failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return []


def _total_balance(entries: list[dict[str, Any]]) -> int:
    return sum(
        e["balance"]
        for e in entries
        if isinstance(e.get("balance"), int)
    )


# ─── Network helpers ──────────────────────────────────────────────────────────


def _fetch_usage(api_key: str) -> dict[str, Any]:
    """GET /usage for one key. Returns {} with an 'error' key on failure."""
    import httpx  # local import — not required when only running --status

    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                USAGE_URL,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code == 200:
            data: dict[str, Any] = resp.json()
            # /usage no longer returns flat plan_limit/plan_usage — they moved
            # under "account" (observed 2026-07-25; flat parse read 0/0 and
            # falsely exhausted healthy keys). Normalise to the flat shape.
            account = data.get("account")
            if isinstance(account, dict):
                for field in ("plan_limit", "plan_usage"):
                    if data.get(field) is None and account.get(field) is not None:
                        data[field] = account[field]
            return data
        return {"error": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"error": str(exc)}


# ─── Output formatters ────────────────────────────────────────────────────────


def _print_table(entries: list[dict[str, Any]]) -> None:
    total = _total_balance(entries)
    active_count = sum(1 for e in entries if e.get("status") != "exhausted")
    print(
        f"Tavily pool: {len(entries)} key(s), {active_count} active, "
        f"~{total} credits remaining"
    )
    print()
    print(f"  {'Name':<22}  {'Status':<10}  {'Balance':>8}  Checked At")
    print(f"  {'-' * 22}  {'-' * 10}  {'-' * 8}  {'-' * 24}")
    for e in entries:
        bal_str = str(e["balance"]) if e.get("balance") is not None else "-"
        chk = e.get("checked_at") or "-"
        icon = "+" if e.get("status") != "exhausted" else "x"
        print(
            f"  [{icon}] {e['name']:<20}  "
            f"{e.get('status', 'active'):<10}  "
            f"{bal_str:>8}  {chk}"
        )
    print()
    print(f"  Total balance: {total}")


def _print_csv(entries: list[dict[str, Any]]) -> None:
    writer = csv.writer(sys.stdout)
    writer.writerow(["name", "status", "balance", "checked_at"])
    for e in entries:
        writer.writerow(
            [
                e.get("name", ""),
                e.get("status", "active"),
                e.get("balance", ""),
                e.get("checked_at", ""),
            ]
        )


# ─── CLI entry point ──────────────────────────────────────────────────────────


def _coerce_credit(value: Any) -> int | None:
    """An unambiguously numeric credit count, or None (UNKNOWN).

    2026-08-12 audit: the v3.42.5 fix guarded ``is None`` only, so a FALSY
    non-numeric value slipped through ``int('' or 0)`` and became a REAL zero —
    ``{"plan_limit": "", "plan_usage": ""}`` (a shape ``_fetch_usage``'s own
    account-normalization can produce) resolved to ``(0, None)``, flowed to
    ``credential_hub.set_tavily_key_balance`` and persist-marked a healthy key
    exhausted off an unreadable payload. Rule 14.6 surviving its own fix.

    Accepted: int, float, and numeric strings — ``"0"`` IS a real zero
    (providers stringify numbers often enough that refusing them would turn a
    readable body into a false unknown). Rejected as UNKNOWN: bool (JSON
    true/false is never a credit count), ``''``/``[]``/``{}``/None, and any
    other non-int-coercible shape.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def resolve_remaining(result: dict[str, Any]) -> tuple[int | None, str | None]:
    """Turn a /usage body into a balance, or say why it cannot be one.

    Returns ``(remaining, None)`` on success and ``(None, reason)`` when the
    payload cannot be read.

    A DERIVED ZERO MUST NEVER BE INDISTINGUISHABLE FROM AN UNKNOWN. This is the
    mechanism that drained 53 keys: the provider moved the /usage fields, every
    ``.get()`` returned None, ``or 0`` turned that into 0, and healthy keys were
    persist-marked exhausted. Normalizing the new payload shape (v3.42.2) fixed
    the observed instance, not the class — the next rename repeats it. The
    2026-08-12 audit found the class alive a THIRD time one token over: the
    ``is None`` guard let falsy non-numerics ('' / [] / False) through the same
    ``or 0``, so all coercion now goes through ``_coerce_credit`` and anything
    non-int-coercible is an UNKNOWN (no balance write, never exhausted).

    Rule 9's own lesson (never persist-mark a key on an ambiguous signal) was
    implemented for the HTTP-error path and not for this parse path. An HTTP 200
    whose body we cannot read is an ERROR, not a balance of zero.

    Extracted from ``main()`` because a decision this consequential must be
    testable without driving the whole CLI (Rule 10).
    """
    remaining_raw = result.get("remaining")
    limit_raw = result.get("plan_limit")
    usage_raw = result.get("plan_usage")

    if remaining_raw is None and (limit_raw is None or usage_raw is None):
        return None, f"unrecognized /usage shape (keys={sorted(result)[:6]})"

    unreadable = (None, (f"non-numeric /usage values (remaining={remaining_raw!r} "
                         f"limit={limit_raw!r} usage={usage_raw!r})"))
    if remaining_raw is not None:
        remaining = _coerce_credit(remaining_raw)
        return (remaining, None) if remaining is not None else unreadable
    limit = _coerce_credit(limit_raw)
    usage = _coerce_credit(usage_raw)
    if limit is None or usage is None:
        return unreadable
    return max(0, limit - usage), None


def main() -> int:  # noqa: C901 — the branching is intentional CLI dispatch
    ap = argparse.ArgumentParser(
        description="Tavily key pool balance manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m scripts._core.tavily_pool --status\n"
            "  python -m scripts._core.tavily_pool --refresh --batch-size 5\n"
            "  python -m scripts._core.tavily_pool --json\n"
        ),
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--status",
        action="store_true",
        help="Print stored ledger table (no network calls, default).",
    )
    mode.add_argument(
        "--refresh",
        action="store_true",
        help="Fetch usage from Tavily API and update the ledger.",
    )
    mode.add_argument(
        "--csv",
        action="store_true",
        help="Print stored ledger as CSV (no network).",
    )
    mode.add_argument(
        "--json",
        action="store_true",
        help="Print stored ledger as machine-readable JSON (no network).",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=5,
        metavar="N",
        help="Keys per batch during --refresh (default 5).",
    )
    ap.add_argument(
        "--batch-pause",
        type=float,
        default=2.0,
        metavar="S",
        help="Seconds to pause between batches during --refresh (default 2.0).",
    )
    args = ap.parse_args()

    # ── --json ────────────────────────────────────────────────────────────────
    if args.json:
        entries = _load_ledger()
        # Strip "key" field — never expose raw key values in output
        safe: list[dict[str, Any]] = [
            {k: v for k, v in e.items() if k != "key"} for e in entries
        ]
        total = _total_balance(entries)
        active_count = sum(1 for e in entries if e.get("status") != "exhausted")
        print(
            json.dumps(
                {
                    "pool_size": len(entries),
                    "active_count": active_count,
                    "total_balance": total,
                    "keys": safe,
                },
                indent=2,
            )
        )
        return 0

    # ── --csv ─────────────────────────────────────────────────────────────────
    if args.csv:
        entries = _load_ledger()
        _print_csv(entries)
        return 0

    # ── --refresh ─────────────────────────────────────────────────────────────
    if args.refresh:
        if not POOL_FILE.exists():
            print("No tavily-pool.json found.", file=sys.stderr)
            return 1

        try:
            pool: dict[str, Any] = json.loads(
                POOL_FILE.read_text(encoding="utf-8")
            )
            raw_keys: list[Any] = pool.get("keys") or []
        except Exception as exc:
            print(f"Error reading pool: {exc}", file=sys.stderr)
            return 1

        # Normalise to list of (name, key_value) tuples (Fix 2: carry names)
        key_pairs: list[tuple[str, str]] = []
        for i, entry in enumerate(raw_keys):
            if isinstance(entry, str) and entry:
                key_pairs.append((f"key-{i + 1}", entry))
            elif isinstance(entry, dict):
                kv: str = entry.get("key", "")
                if kv:
                    name: str = entry.get("name") or f"key-{i + 1}"
                    key_pairs.append((name, kv))

        if not key_pairs:
            print("Pool has no keys.", file=sys.stderr)
            return 1

        batch_size: int = args.batch_size
        batch_pause: float = args.batch_pause
        updated = 0
        errors = 0

        for batch_start in range(0, len(key_pairs), batch_size):
            batch = key_pairs[batch_start : batch_start + batch_size]
            for name, k in batch:
                result = _fetch_usage(k)
                if "error" in result:
                    err = str(result["error"])
                    # HTTP 401 from /usage = the key itself is dead (revoked /
                    # account deactivated). Persist-mark it so rotation skips it
                    # (2026-07-01) — "leaving prior value" kept dead keys active
                    # forever and they were re-selected on every run.
                    if "401" in err:
                        credential_hub.mark_tavily_key_invalid(k)
                        print(
                            f"  ✗ {name}: {err} — key marked INVALID (dead/revoked)",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            f"  ⚠ {name}: {err} — leaving prior value",
                            file=sys.stderr,
                        )
                    errors += 1
                else:
                    remaining, why = resolve_remaining(result)
                    if why is not None:
                        print(f"  ⚠ {name}: {why} — leaving prior value",
                              file=sys.stderr)
                        errors += 1
                        continue
                    assert remaining is not None
                    credential_hub.set_tavily_key_balance(k, remaining)
                    updated += 1

            # Pause between batches (skip after the last batch)
            if batch_start + batch_size < len(key_pairs):
                time.sleep(batch_pause)

        print(f"Refresh complete: {updated} updated, {errors} error(s)")
        entries = _load_ledger()
        _print_table(entries)
        return 0 if errors == 0 else 1

    # ── --status (default) ────────────────────────────────────────────────────
    entries = _load_ledger()
    if not entries:
        print(
            "No Tavily pool configured. "
            "Create ~/.xuanran-seo/credentials/tavily-pool.json "
            'with {"keys": [{"name": "...", "key": "tvly-..."}]}'
        )
        return 0
    _print_table(entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
