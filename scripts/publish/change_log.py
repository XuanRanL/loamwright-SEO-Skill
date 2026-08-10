"""scripts/publish/change_log.py — Per-project + global change log with 7-day undo.

Tracks every mutation (publish, draft-create, refresh, rollback, delete).
Enables 7-day undo on publish actions (per v3.2 spec).

Two log files:
  - projects/{slug}/.seo/change-log.json  — per-project changes
  - memory/change-log-global.json    — cross-project changes (audit)
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from scripts._core import file_lock


@dataclass
class ChangeEntry:
    change_id: str
    action: str                  # publish / create-draft / refresh / rollback / delete / update
    timestamp: str
    expires_at: float            # for 7-day undo
    site_slug: str
    post_id: int | None = None
    post_url: str | None = None
    status: str | None = None
    media_ids: list[int] = field(default_factory=list)
    featured_media_id: int | None = None
    rollback_data: dict = field(default_factory=dict)
    actor: str = "xuanran-seo"
    notes: str = ""


def _plugin_root() -> Path:
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "VERSION").exists() and (p / ".claude-plugin").is_dir():
            return p
        p = p.parent
    raise RuntimeError("Cannot find plugin root")


def generate_change_id() -> str:
    """Format: ch-{YYYYMMDD}-{8-char-hex}"""
    return f"ch-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{secrets.token_hex(4)}"


def append(
    site_slug: str,
    action: str,
    *,
    post_id: int | None = None,
    post_url: str | None = None,
    status: str | None = None,
    media_ids: list[int] | None = None,
    featured_media_id: int | None = None,
    rollback_data: dict | None = None,
    notes: str = "",
    undo_days: int = 7,
) -> ChangeEntry:
    """Append a change entry to both per-project + global logs."""
    now = datetime.now(timezone.utc)
    entry = ChangeEntry(
        change_id=generate_change_id(),
        action=action,
        timestamp=now.isoformat(),
        expires_at=(now + timedelta(days=undo_days)).timestamp(),
        site_slug=site_slug,
        post_id=post_id,
        post_url=post_url,
        status=status,
        media_ids=media_ids or [],
        featured_media_id=featured_media_id,
        rollback_data=rollback_data or {},
        notes=notes,
    )

    plugin = _plugin_root()
    project_log = plugin / "projects" / site_slug / ".seo" / "change-log.json"
    global_log = plugin / "memory" / "change-log-global.json"

    # Write project log
    project_log.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    if project_log.exists():
        try:
            entries = json.loads(project_log.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []
    entries.append(asdict(entry))
    project_log.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write global log. Cross-process lock the read-modify-write: this is a single
    # shared file across ALL parallel sessions (every project publishes into it),
    # so two concurrent publishes must not clobber each other's audit entry.
    # (The per-project log above is scoped by site_slug, so it needs no lock.)
    global_log.parent.mkdir(parents=True, exist_ok=True)
    with file_lock.locked(global_log):
        g_entries = []
        if global_log.exists():
            try:
                g_entries = json.loads(global_log.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                g_entries = []
        g_entries.append(asdict(entry))
        global_log.write_text(json.dumps(g_entries, indent=2, ensure_ascii=False), encoding="utf-8")

    return entry


def find_undoable(site_slug: str | None = None) -> list[ChangeEntry]:
    """List all entries within their 7-day undo window."""
    plugin = _plugin_root()
    now = time.time()
    results = []

    if site_slug:
        logs = [plugin / "projects" / site_slug / ".seo" / "change-log.json"]
    else:
        logs = list((plugin / "projects").glob("*/.seo/change-log.json"))

    for log in logs:
        if not log.exists():
            continue
        try:
            entries = json.loads(log.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for e in entries:
            if e.get("expires_at", 0) > now and e.get("action") in {"publish", "refresh", "delete"}:
                results.append(ChangeEntry(**e))

    results.sort(key=lambda e: e.timestamp, reverse=True)
    return results


def get_by_id(change_id: str) -> ChangeEntry | None:
    """Find a specific change by ID across all logs."""
    plugin = _plugin_root()
    for log in (plugin / "projects").glob("*/.seo/change-log.json"):
        try:
            entries = json.loads(log.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for e in entries:
            if e.get("change_id") == change_id:
                return ChangeEntry(**e)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-project + global change log")
    sub = ap.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("append", help="Append entry")
    add.add_argument("site_slug")
    add.add_argument("action")
    add.add_argument("--post-id", type=int)
    add.add_argument("--post-url")
    add.add_argument("--notes", default="")

    li = sub.add_parser("list", help="List undoable entries")
    li.add_argument("--site-slug")
    li.add_argument("--json", action="store_true")

    show = sub.add_parser("show", help="Show entry by ID")
    show.add_argument("change_id")

    args = ap.parse_args()

    if args.cmd == "append":
        entry = append(args.site_slug, args.action,
                       post_id=args.post_id, post_url=args.post_url,
                       notes=args.notes)
        print(f"Appended: {entry.change_id}")
        return 0

    if args.cmd == "list":
        entries = find_undoable(args.site_slug)
        if args.json:
            print(json.dumps([asdict(e) for e in entries], indent=2, ensure_ascii=False))
        else:
            print(f"Found {len(entries)} undoable entries:")
            for e in entries:
                expires_in = int((e.expires_at - time.time()) / 3600)
                print(f"  {e.change_id}  {e.action:15s} {e.site_slug}  expires in {expires_in}h")
                if e.post_url:
                    print(f"      → {e.post_url}")
        return 0

    if args.cmd == "show":
        e = get_by_id(args.change_id)
        if not e:
            print(f"Not found: {args.change_id}", file=sys.stderr)
            return 1
        print(json.dumps(asdict(e), indent=2, ensure_ascii=False))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
