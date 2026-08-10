#!/usr/bin/env python3
"""
hooks/pre_tool_use_cost_guard.py — Block Bash commands that would blow the budget.

Fires before any Bash tool call. Inspects the command for known cost-incurring
patterns (anthropic / openai / tavily / gemini API calls in Python one-liners,
or running scripts that hit paid APIs) and either:
  - exit 0: proceed (cost OK or unknown)
  - exit 1: warn but proceed
  - exit 2: BLOCK (over daily cap)

Claude Code passes the tool input via JSON on stdin:
  { "tool_name": "Bash", "tool_input": { "command": "...", "description": "..." } }

This hook is informational unless daily cap is exceeded.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


# Lazy import to avoid blocking startup
def _check_daily_cap() -> tuple[bool, float, float]:
    """Returns (over_cap, used_usd, limit_usd)."""
    try:
        # Use absolute path import
        from datetime import datetime, timedelta, timezone
        ledger = Path.home() / ".xuanran-seo" / "cost-ledger.jsonl"
        cfg = Path.home() / ".xuanran-seo" / "config.yaml"

        limit = 50.0  # default daily cap
        if cfg.exists():
            try:
                import yaml
                d = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
                limit = float(d.get("cost_limits", {}).get("daily_total_usd", 50))
            except Exception:
                pass

        if not ledger.exists():
            return False, 0.0, limit

        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        total = 0.0
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
                ts = datetime.fromisoformat(e["timestamp"])
                if ts >= cutoff:
                    total += float(e["cost_usd"])
            except Exception:
                continue
        return total >= limit, total, limit
    except Exception:
        return False, 0.0, 50.0


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0

    tool_name = data.get("tool_name", "")
    if tool_name != "Bash":
        return 0

    command = data.get("tool_input", {}).get("command", "")

    # Look for cost-incurring patterns
    cost_patterns = [
        "anthropic.Anthropic", "openai.OpenAI", "TavilyClient",
        "genai.Client", "openai.images.generate",
        "client.messages.create", "client.batches.create",
        "tavily_search", "tavily_extract",
        "scripts.wordpress.wp_publisher",
        "scripts/fetch/", "openai_image",
    ]

    has_cost_pattern = any(p in command for p in cost_patterns)

    over_cap, used, limit = _check_daily_cap()

    if over_cap:
        print(f"[cost-guard] BLOCKED: Daily cap ${limit:.2f} reached (used: ${used:.4f}).",
              file=sys.stderr)
        print(f"[cost-guard] Either wait until midnight UTC or raise cost_limits.daily_total_usd",
              file=sys.stderr)
        print(f"[cost-guard] in ~/.xuanran-seo/config.yaml", file=sys.stderr)
        # Only block API-calling commands; let other Bash through even at cap
        if has_cost_pattern:
            return 2

    # Warn if approaching cap
    if used >= limit * 0.8 and has_cost_pattern:
        print(f"[cost-guard] ⚠️ At 80% of daily cap (${used:.4f} / ${limit:.2f})",
              file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
