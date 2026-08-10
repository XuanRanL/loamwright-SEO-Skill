"""
scripts/_core/tavily_retry.py — Resilient retry wrapper for Tavily API calls.

The three Tavily fetch scripts (tavily_search, tavily_research, tavily_extract) call
the API once and raise on any failure. credential_hub.get_tavily_key() rotates across
a key pool on each call, but the scripts never re-called it on failure — so a single
429/quota/connection error killed the whole research stage.

This module adds the missing resilience layer:
  - Retry transient failures (rate limit 429, quota 432/433, connection, timeout)
  - Rotate to the NEXT pool key on each retry (get_tavily_key advances the RR counter)
  - Exponential backoff between attempts
  - Fail fast on non-transient errors (400 bad request, auth) — retrying won't help
  - Reactively mark quota-exhausted keys in the pool ledger (429/432/433) so
    get_tavily_key skips them on future calls without waiting for --refresh

This is the PRIMARY path. MCP Tavily tools (mcp__tavily__tavily_*) are a documented
fallback the orchestrator/researcher can use if these scripts exhaust all keys.
"""
from __future__ import annotations

import sys
import time
from typing import Callable, TypeVar

try:
    from scripts._core.credential_hub import (
        tavily_pool_size,
        mark_tavily_key_exhausted,
        mark_tavily_key_invalid,
    )
except Exception:  # pragma: no cover — keep the retry layer usable in isolation
    def tavily_pool_size() -> int:
        return 1

    def mark_tavily_key_exhausted(key: str) -> None:
        pass

    def mark_tavily_key_invalid(key: str) -> None:
        pass

T = TypeVar("T")

# ── Classification: type FIRST, message phrases only as a fallback ───────────
#
# The tavily-python SDK collapses HTTP status into a few EXCEPTION TYPES and puts
# the response body's ``detail.error`` text in the message — the numeric status
# code is NOT in str(exc):
#     HTTP 429         -> UsageLimitExceededError(detail)   # per-minute rate limit
#     HTTP 403/432/433 -> ForbiddenError(detail)            # plan / usage limit
#     HTTP 401         -> InvalidAPIKeyError(detail)
#     HTTP 400         -> BadRequestError(detail)
# Matching on "429"/"432"/"rate limit" substrings therefore never fires for real
# SDK exceptions (2026-06-30 audit). Classify by TYPE NAME first; keep the phrase
# markers below only for non-SDK callers (serpapi_query, raw connection errors).

# SDK exception type names (lower-cased) that mean "retry with a fresh key".
_TRANSIENT_TYPE_NAMES = frozenset({
    "usagelimitexceedederror",   # tavily: HTTP 429 (rate limit, transient, retry-after)
    "forbiddenerror",            # tavily: HTTP 403/432/433 (plan / usage limit)
    "timeouterror",              # tavily + stdlib
})

# SDK exception type names that ALSO mean "this key's credits are spent" → the
# key should be persist-marked exhausted in the pool ledger.
# NOTE: UsageLimitExceededError (429) is deliberately NOT here. Tavily 429 is a
# per-minute RATE limit (transient); persist-marking it would remove a HEALTHY
# key from the pool under exactly the parallel-session bursts the pool exists to
# serve (Rule 7). Genuine credit exhaustion is detected authoritatively by the
# balance ledger (--refresh -> /usage -> set_tavily_key_balance); a 429 whose
# body explicitly says the monthly usage is spent is still caught by the phrase
# markers below.
_QUOTA_TYPE_NAMES = frozenset({
    "forbiddenerror",            # tavily: HTTP 432/433 plan-limit exhaustion
})

# Phrase markers — message-substring fallback for callers that raise plain
# Exceptions (serpapi_query.SerpApiQuotaError, raw httpx/connection errors).
_TRANSIENT_MARKERS = (
    "429", "432", "433",           # numeric (string callers only)
    "rate limit", "quota", "usage limit", "too many requests",
    "timeout", "timed out",
    "connection", "connectionerror", "connecterror",
    "502", "503", "504",           # upstream gateway errors
    "temporarily unavailable",
)

# Phrase markers that specifically mean THIS key's monthly credits are spent.
# Deliberately EXCLUDES "429" / "rate limit" / "too many requests": those are
# per-minute throttles, not credit exhaustion, and must not drain healthy keys.
_QUOTA_MARKERS = (
    "432", "433",
    "quota", "usage limit", "plan limit",
    "out of credits", "insufficient credit",
    "exceeded your", "monthly limit", "monthly usage",
)


# SDK exception type names that mean THIS KEY IS DEAD (revoked / account
# deactivated / 401). Neither transient nor quota (2026-07-01): the old code
# fail-fasted the WHOLE call on the first dead key and never recorded it, so the
# same key was re-selected by round-robin on every future run (observed 3× in the
# 2026-07-01 batch: "account deactivated" recurring across all researcher agents).
# A dead key must be (a) persist-marked so the pool skips it forever, and
# (b) rotated past — 99 healthy keys should not be masked by 1 revoked one.
_INVALID_KEY_TYPE_NAMES = frozenset({
    "invalidapikeyerror",        # tavily: HTTP 401
    "unauthorizederror",
})

_INVALID_KEY_MARKERS = (
    "invalid api key",
    "account deactivated",
    "account has been deactivated",
    "unauthorized", "401",
)


def _typename(exc: Exception) -> str:
    return type(exc).__name__.lower()


def is_invalid_key_error(exc: Exception) -> bool:
    """True when the error means the KEY itself is dead (revoked/deactivated/401).

    Type-name first (Rule 9), message-substring fallback for plain-Exception
    callers. Distinct from quota exhaustion: an exhausted key resets with the
    billing cycle; an invalid key never comes back.
    """
    if _typename(exc) in _INVALID_KEY_TYPE_NAMES:
        return True
    msg = f"{type(exc).__name__}: {exc}".lower()
    return any(m in msg for m in _INVALID_KEY_MARKERS)


def is_transient(exc: Exception) -> bool:
    """True if the error is worth retrying with a different key / after backoff."""
    if _typename(exc) in _TRANSIENT_TYPE_NAMES:
        return True
    msg = f"{type(exc).__name__}: {exc}".lower()
    return any(m in msg for m in _TRANSIENT_MARKERS)


def is_quota_error(exc: Exception) -> bool:
    """True only when THIS key's monthly credits are genuinely spent.

    Decided by SDK exception TYPE first (ForbiddenError = 432/433 plan limit),
    then by explicit credit-exhaustion phrases in the message. Critically, a
    bare 429 / rate-limit (tavily's UsageLimitExceededError with a throttle
    body) is NOT a quota error — it is a transient per-minute rate limit, and
    marking the key exhausted on it would drain healthy keys under parallel
    bursts (Rule 7). Timeouts, connection resets and upstream 5xx are likewise
    transient but never quota.
    """
    if _typename(exc) in _QUOTA_TYPE_NAMES:
        return True
    msg = f"{type(exc).__name__}: {exc}".lower()
    return any(m in msg for m in _QUOTA_MARKERS)


def with_retry(
    call: Callable[[str], T],
    *,
    get_key: Callable[[], str],
    max_attempts: int | None = None,
    base_delay: float = 1.5,
    max_delay: float = 8.0,
    label: str = "tavily",
) -> T:
    """Run `call(api_key)` with retry-on-transient + key rotation.

    Args:
        call: function that takes an api_key and performs the API request.
        get_key: zero-arg callable returning a key (rotates on each call).
        max_attempts: total attempts across the key pool. Default None means
            "rotate through the WHOLE pool" (== tavily_pool_size(), floored at 4
            for tiny pools and capped at 12). Pass an int only to override; do
            NOT hard-code a value smaller than the pool, or a quota-limited pool
            may never reach its one working key (the 2026-06-04 incident).
        base_delay: seconds; backoff is base_delay * 2**(attempt-1).
        max_delay: hard cap on any single backoff sleep, so rotating through a
            large pool cannot stall for tens of minutes.
        label: for log messages.

    Returns:
        Whatever `call` returns on the first success.

    Raises:
        The last exception if all attempts fail, or immediately on a
        non-transient error (retrying a malformed request is pointless).
    """
    if max_attempts is None:
        # Rotate through every pool key (a 432-rejected attempt costs no credits),
        # with a floor so single-key setups still retry a transient blip and a cap
        # so a misconfigured huge pool can't loop indefinitely.
        max_attempts = min(max(4, tavily_pool_size()), 12)
    last_exc: Exception | None = None
    attempt = 0
    # Invalid (dead/deactivated/401) keys are a POOL-STATE problem, not a service
    # problem: rotating past one must NOT consume the transient-retry budget.
    # 2026-07-01: a contiguous tranche of 42 deactivated keys (un-probed import)
    # exhausted all 12 attempts on corpses and failed the call while 58 healthy
    # keys sat unused. Skips get their own bound (pool size) so an all-dead pool
    # still terminates instead of looping forever.
    invalid_rotations = 0
    max_invalid_rotations = max(tavily_pool_size(), max_attempts) + 1
    while attempt < max_attempts:
        try:
            api_key = get_key()
        except Exception as e:
            # Key resolution itself failed — no point retrying without a key source
            raise RuntimeError(f"{label}: could not resolve API key: {e}") from e

        try:
            return call(api_key)
        except Exception as e:  # noqa: BLE001 — we classify below
            last_exc = e
            if is_invalid_key_error(e):
                # Dead key (revoked/deactivated/401): persist-mark it so the pool
                # never selects it again, then rotate to the next key immediately
                # (no backoff, no attempt charged — the failure is key-local,
                # not service-side).
                invalid_rotations += 1
                try:
                    mark_tavily_key_invalid(api_key)
                except Exception:
                    pass  # marking failure must never mask the original error
                print(
                    f"⚠ {label}: key rejected as INVALID "
                    f"(skip {invalid_rotations}/{max_invalid_rotations}, attempts uncharged) "
                    f"({type(e).__name__}: {str(e)[:120]}); marked invalid + rotating",
                    file=sys.stderr,
                )
                if invalid_rotations >= max_invalid_rotations:
                    raise RuntimeError(
                        f"{label}: no usable key in the pool — {invalid_rotations} "
                        f"consecutive keys rejected as invalid. Run "
                        f"`python -m scripts._core.tavily_pool --refresh` and/or add keys. "
                        f"Last error: {last_exc}"
                    ) from last_exc
                continue
            attempt += 1
            if not is_transient(e):
                # Bad request, malformed payload, etc. — retrying won't help, fail fast.
                raise
            # Reactive exhaustion marking: if this key returned a quota/rate-limit
            # signal, mark it exhausted in the pool ledger so get_tavily_key skips
            # it on future calls without waiting for an explicit --refresh run.
            if is_quota_error(e):
                try:
                    mark_tavily_key_exhausted(api_key)
                except Exception:
                    pass  # marking failure must never mask the original error
            if attempt < max_attempts:
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                print(
                    f"⚠ {label}: transient error on attempt {attempt}/{max_attempts} "
                    f"({type(e).__name__}: {str(e)[:120]}); rotating key + retrying in {delay:.1f}s",
                    file=sys.stderr,
                )
                time.sleep(delay)

    raise RuntimeError(
        f"{label}: all {max_attempts} attempts failed (rotated across key pool). "
        f"Last error: {last_exc}"
    ) from last_exc
