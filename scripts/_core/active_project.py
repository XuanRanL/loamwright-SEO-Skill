"""scripts/_core/active_project.py — resolve the active project slug.

Single source of truth for "which project is this session serving?".

Resolution order (this ordering is the whole point):
  1. ``XS_ACTIVE_PROJECT`` environment variable  ← per-session, authoritative
  2. ``~/.xuanran-seo/active-project`` file       ← single-session fallback

Why env-first
-------------
The active-project file is ONE shared, user-level file. When the user runs
multiple Claude Code sessions in parallel (one per project), they would all write
and read the same file — last-writer-wins — and a session could burn the WRONG
``project_slug`` into a task's ``state.json`` at task-creation time, then research
/ write / publish to the wrong WordPress site.

By making the env var authoritative, each session is launched with
``XS_ACTIVE_PROJECT=<slug>`` (see ``bin/launch-session.*``) and never touches the
shared file. The env var is immutable for the life of the process and invisible
to other sessions, so cross-session contamination is structurally impossible.

Single-session / interactive use is unchanged: with the env var unset, the file
fallback behaves exactly as before.

See: docs/superpowers/specs/2026-06-06-parallel-sessions-isolation-design.md
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Final

ENV_VAR: Final[str] = "XS_ACTIVE_PROJECT"
ACTIVE_FILE: Final[Path] = Path.home() / ".xuanran-seo" / "active-project"

# Project slugs: alnum start, then alnum/-/_ (matches the validation used by
# credential_hub.get_wordpress_creds and the projects/{slug}/ directory naming).
_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def _valid(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug))


def get_active_project() -> str | None:
    """Return the active project slug — env var first, then the shared file.

    Returns:
        The resolved slug, or ``None`` if neither source yields a valid slug.
    """
    env_val = os.environ.get(ENV_VAR, "").strip()
    if env_val:
        if _valid(env_val):
            return env_val
        print(
            f"⚠ {ENV_VAR}={env_val!r} is not a valid project slug — ignoring it",
            file=sys.stderr,
        )

    if ACTIVE_FILE.exists():
        try:
            slug = ACTIVE_FILE.read_text(encoding="utf-8").strip()
        except OSError as e:
            print(f"⚠ could not read {ACTIVE_FILE}: {e}", file=sys.stderr)
            return None
        if slug and _valid(slug):
            return slug

    return None


def set_active_project(slug: str) -> None:
    """Write the shared active-project file (used by /switch and /init).

    If ``XS_ACTIVE_PROJECT`` is set for the current session, this write does NOT
    change the project the current session resolves to (the env var wins). A
    stderr warning is emitted so ``/switch`` inside an env-pinned session can't
    silently mislead — only future, non-env-pinned sessions are affected.

    Raises:
        ValueError: ``slug`` is not a valid project slug.
    """
    slug = slug.strip()
    if not _valid(slug):
        raise ValueError(f"Invalid project slug: {slug!r}")

    ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(slug, encoding="utf-8")

    env_val = os.environ.get(ENV_VAR, "").strip()
    if env_val and env_val != slug:
        print(
            f"⚠ {ENV_VAR}={env_val!r} is set: this session stays pinned to "
            f"{env_val!r}. The active-project file now says {slug!r}, which only "
            f"affects sessions launched WITHOUT the env var.",
            file=sys.stderr,
        )


def _main(argv: list[str] | None = None) -> int:
    """Tiny CLI so ``python -m scripts._core.active_project`` is not a silent no-op.

    v3.41.2: pre-fix, invoking this module with ``--set X`` exited 0 having done
    NOTHING (no __main__ handler existed) — a silent-failure footgun observed live
    on 2026-07-18 when a session believed it had switched projects. Rule-6 class:
    an invocation that looks like an executor must either execute or fail loudly.
    """
    import argparse
    ap = argparse.ArgumentParser(description="Get or set the active project slug")
    ap.add_argument("--set", dest="set_slug", default=None, metavar="SLUG",
                    help="Set the active project (writes the shared file; env pin wins in-session)")
    ap.add_argument("--get", action="store_true", help="Print the resolved active project")
    args = ap.parse_args(argv)
    if args.set_slug:
        set_active_project(args.set_slug)
        print(f"active project set to: {args.set_slug}")
        return 0
    slug = get_active_project()
    print(slug or "(none)")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    raise SystemExit(_main())
