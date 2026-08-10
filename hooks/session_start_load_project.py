#!/usr/bin/env python3
"""
hooks/session_start_load_project.py — Claude Code SessionStart hook.

Fires once per Claude Code session start. Loads:
  - ~/.xuanran-seo/active-project pointer
  - projects/{slug}/business-context.json
  - Cost ledger daily summary

Prints brief status to stdout (visible to Claude as context).

Exit 0 always (informational, never blocks).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _plugin_root() -> Path | None:
    """Find plugin root by walking up from this file."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "VERSION").exists() and (p / ".claude-plugin").is_dir():
            return p
        p = p.parent
    return None


def main() -> int:
    plugin = _plugin_root()
    if not plugin:
        return 0

    # Resolve active project — XS_ACTIVE_PROJECT env var first (per-session pin),
    # then the shared ~/.xuanran-seo/active-project file. This lets parallel
    # sessions each pin a distinct project. See scripts/_core/active_project.py.
    pinned_via_env = bool(os.environ.get("XS_ACTIVE_PROJECT", "").strip())
    if str(plugin) not in sys.path:
        sys.path.insert(0, str(plugin))
    try:
        from scripts._core import active_project  # noqa: E402
        slug = active_project.get_active_project()
    except Exception:
        # Defensive fallback to a direct file read if the import ever fails.
        active_file = Path.home() / ".xuanran-seo" / "active-project"
        slug = (
            active_file.read_text(encoding="utf-8").strip()
            if active_file.exists()
            else None
        )

    if not slug:
        print(
            "[xuanran-seo] No active project. Run /init <url>, /switch <slug>, "
            "or launch with XS_ACTIVE_PROJECT=<slug> (parallel sessions)."
        )
        return 0

    bc_file = plugin / "projects" / slug / "business-context.json"
    if not bc_file.exists():
        print(f"[xuanran-seo] Active project '{slug}' but business-context.json missing.")
        print(f"[xuanran-seo] Run /init <url> --refresh or /switch <other-slug>")
        return 0

    try:
        bc = json.loads(bc_file.read_text(encoding="utf-8"))
        domain = bc.get("domain", slug)
        industry = bc.get("industry", {}).get("primary", "unknown") if isinstance(bc.get("industry"), dict) else bc.get("industry", "unknown")
        freshness = bc.get("freshness_state", "unknown")

        msg = f"[xuanran-seo] Active project: {slug} ({domain}) · industry: {industry}"
        if pinned_via_env:
            msg += " · 📌 pinned via XS_ACTIVE_PROJECT"
        if freshness == "expired":
            msg += " · ⚠️ business-context expired (>90d), suggest /init --refresh"
        elif freshness == "stale":
            msg += " · context aging (>60d)"
        print(msg)

        # Cost summary (best-effort)
        ledger = Path.home() / ".xuanran-seo" / "cost-ledger.jsonl"
        if ledger.exists():
            try:
                from datetime import datetime, timedelta, timezone
                cutoff = datetime.now(timezone.utc) - timedelta(days=1)
                total = 0.0
                count = 0
                for line in ledger.read_text(encoding="utf-8").splitlines():
                    try:
                        e = json.loads(line)
                        ts = datetime.fromisoformat(e["timestamp"])
                        if ts >= cutoff:
                            total += float(e["cost_usd"])
                            count += 1
                    except Exception:
                        continue
                if count > 0:
                    print(f"[xuanran-seo] Last 24h spend: ${total:.4f} ({count} calls)")
            except Exception:
                pass

    except Exception as e:
        print(f"[xuanran-seo] Could not load business-context: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
