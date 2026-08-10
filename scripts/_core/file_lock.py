"""scripts/_core/file_lock.py — cross-platform advisory file lock.

Why this exists
---------------
Several pieces of user-level global state are shared across every Claude Code
session running this plugin:

  - ~/.xuanran-seo/cost-ledger.jsonl              (append per API call)
  - ~/.xuanran-seo/credentials/.tavily-rr-counter (round-robin RMW)

When the user runs 3 parallel sessions (one per project), concurrent writes from
separate OS processes can interleave/corrupt these files. This module provides a
tiny, dependency-free, cross-platform exclusive lock so those critical sections
serialize across processes.

Design notes
------------
- The lock is taken on a sibling sidecar file ``{path}.lock`` so we never have to
  truncate/recreate the data file while holding the lock.
- We use the OS advisory lock (``msvcrt`` on Windows, ``fcntl`` on POSIX). The OS
  releases the lock automatically when the holding process exits, so a session
  killed mid-write (Ctrl-C) can NEVER leave a permanent deadlock — unlike an
  ``O_EXCL`` lock-file scheme, which needs stale-lock timeouts.
- Acquisition is non-blocking + polled so we get identical ``timeout`` semantics
  on both platforms and raise a clear ``LockTimeout`` instead of hanging forever.

Usage::

    from scripts._core import file_lock

    with file_lock.locked(LEDGER_FILE):
        ...  # exclusive critical section
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


class LockTimeout(TimeoutError):
    """Raised when an exclusive lock cannot be acquired within the timeout."""


def atomic_write_text(path: Path | str, text: str, *, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` atomically (temp file in same dir + os.replace).

    Why: several shared-state files (tavily-pool.json, covered.json) are read by
    callers that do NOT take the lock. A plain ``write_text`` truncates then
    writes, so an interleaving reader can observe an empty/half-written file and
    fail to parse it (Rule 7). ``os.replace`` is atomic on POSIX and on Windows
    (same volume), so a reader always sees either the complete old file or the
    complete new one — never a torn one. Writers that ALSO hold the lock get
    correctness against each other; this protects the lock-free readers.

    The temp file is created in the destination directory (same filesystem, so
    the rename is a true atomic replace) and is cleaned up on any failure so no
    sidecar is ever left behind.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(p.parent), prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, p)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _try_acquire(fh: IO[str]) -> None:
    """Attempt a single non-blocking exclusive lock; raise OSError if held."""
    if sys.platform == "win32":
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release(fh: IO[str]) -> None:
    """Release the lock held on ``fh``."""
    if sys.platform == "win32":
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def is_locked(path: Path | str) -> bool:
    """True if another PROCESS currently holds the exclusive lock on ``path``.

    Liveness is decided by trying to take the OS advisory lock, NOT by whether the
    sidecar file exists. The sidecar is deliberately left on disk after a normal
    release (see ``locked``), so ``lock_path.exists()`` is true forever after the
    first run and is therefore useless as a liveness test.

    That exact confusion was a real bug: ``orchestrator --action reset`` gated on
    ``.exists()`` and so refused to run on ANY workspace a driver had ever touched,
    making the sanctioned reset path permanently unreachable (found 2026-07-14).

    Returns False if the lock is free (or the sidecar does not exist yet).
    """
    lock_path = Path(str(path) + ".lock")
    if not lock_path.exists():
        return False
    try:
        fh: IO[str] = open(lock_path, "a+", encoding="utf-8")
    except OSError:
        # Cannot even open it — treat as locked rather than stomping on it.
        return True
    try:
        try:
            _try_acquire(fh)
        except OSError:
            return True  # someone else holds it
        _release(fh)
        return False
    finally:
        fh.close()


@contextmanager
def locked(path: Path | str, *, timeout: float = 10.0, poll: float = 0.05) -> Iterator[None]:
    """Hold an exclusive cross-process lock for the duration of the ``with`` block.

    Args:
        path:    The resource being protected. The lock is taken on the sibling
                 file ``{path}.lock`` (created if absent).
        timeout: Maximum seconds to wait for the lock before raising LockTimeout.
        poll:    Seconds to sleep between non-blocking acquire attempts.

    Raises:
        LockTimeout: The lock could not be acquired within ``timeout`` seconds.
    """
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fh: IO[str] = open(lock_path, "a+", encoding="utf-8")  # noqa: SIM115 (held across block)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                _try_acquire(fh)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise LockTimeout(
                        f"Could not acquire lock {lock_path} within {timeout}s"
                    )
                time.sleep(poll)
        try:
            yield
        finally:
            _release(fh)
    finally:
        fh.close()
