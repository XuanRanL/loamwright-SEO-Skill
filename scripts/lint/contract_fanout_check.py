#!/usr/bin/env python3
"""Rule 11 executor — find instruction layers still stating a retired contract.

WHY THIS EXISTS
Writer/agent/host-facing contracts are duplicated BY DESIGN across seven layers:
`skills/`, `subskills/`, `agents/`, `templates/`, `references/`, `AGENTS.md`, and
the orchestrator dispatch prompts. Changing one while another still states the old
contract re-creates the bug at the untouched source, because the instruction that
reaches the writer is whichever layer it happens to load.

Rule 11 prescribes a mechanical check — "grep the old contract's distinctive
phrases before declaring the change done" — and then asks a human to remember to
run it. Every other rule in CLAUDE.md has an executor: Rule 6 has the wiring audit,
Rule 12 has `_content_gate_reason`, Rule 13 has `deploy_*.py --check`, Rule 8 has
nine enforcement layers. Rule 11 had a paragraph. So it was the rule that silently
did not fire: the v3.42.0 style-token contract shipped correct CODE while nine
instruction files kept telling operators to verify a class name that tokenized
projects can no longer emit — a check that could not pass on any of 13 projects.

HOW A RULE IS EXPRESSED
Not "this phrase is banned" — the legacy names remain correct when describing
INTERNAL artifacts, and a lint that fires on correct usage gets muted, which is
worse than no lint. Instead each rule says:

    if a file mentions <pattern>, that same file MUST also mention <requires>

That is the shape of a fanned-out contract: you may keep talking about the old
name, but you may not do so without acknowledging what replaced it.

Usage
-----
    python -m scripts.lint.contract_fanout_check
    python -m scripts.lint.contract_fanout_check --json
    python -m scripts.lint.contract_fanout_check --rule style-tokens-v3420
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY = PLUGIN_ROOT / "references" / "retired-contracts.json"

# Layers that carry instructions. History and post-mortems are exempt by design:
# a CHANGELOG entry describing the old contract is the paper trail, not a relapse.
DEFAULT_SCOPE = ["skills/**/*.md", "subskills/**/*.md", "agents/*.md",
                 "templates/*.md", "references/*.md", "AGENTS.md",
                 "scripts/pipeline/*.py"]
DEFAULT_EXEMPT = ["CHANGELOG.md", "memory/**", "docs/**",
                  "references/retired-contracts.json"]


def _load_rules(only: str | None = None) -> list[dict[str, Any]]:
    if not REGISTRY.exists():
        return []
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    rules = data.get("retired_contracts") or []
    return [r for r in rules if not only or r.get("id") == only]


def _files(scope: list[str], exempt: list[str]) -> list[Path]:
    seen: dict[Path, None] = {}
    for pat in scope:
        for p in PLUGIN_ROOT.glob(pat):
            if p.is_file():
                seen[p] = None
    out = []
    for p in seen:
        rel = p.relative_to(PLUGIN_ROOT).as_posix()
        if any(p.match(e) or rel.startswith(e.rstrip("*/")) for e in exempt):
            continue
        out.append(p)
    return sorted(out)


def run(only: str | None = None) -> dict[str, Any]:
    rules = _load_rules(only)
    violations: list[dict[str, Any]] = []

    for rule in rules:
        pattern = re.compile(rule["pattern"])
        requires = re.compile(rule["requires"])
        files = _files(rule.get("scope") or DEFAULT_SCOPE,
                       (rule.get("exempt") or []) + DEFAULT_EXEMPT)
        for f in files:
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if not pattern.search(text):
                continue
            if requires.search(text):
                continue          # the file acknowledges the new contract
            lines = [i + 1 for i, ln in enumerate(text.splitlines())
                     if pattern.search(ln)]
            violations.append({
                "rule": rule["id"],
                "file": f.relative_to(PLUGIN_ROOT).as_posix(),
                "lines": lines[:8],
                "states": rule["retired_contract"],
                "cure": rule["cure"],
            })

    return {"rules_checked": len(rules),
            "violations": violations,
            "passed": not violations}


def main() -> int:
    ap = argparse.ArgumentParser(description="Rule 11 — retired-contract fan-out check")
    ap.add_argument("--rule", help="check a single rule id")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    res = run(a.rule)
    if a.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res["passed"] else 1

    if not res["rules_checked"]:
        print("contract_fanout_check: no rules registered "
              f"(expected {REGISTRY.relative_to(PLUGIN_ROOT)})", file=sys.stderr)
        return 2
    if res["passed"]:
        print(f"contract_fanout_check: OK — {res['rules_checked']} contract(s), "
              f"no stale instruction layer")
        return 0

    print(f"contract_fanout_check: {len(res['violations'])} stale layer(s)\n")
    for v in res["violations"]:
        print(f"  {v['file']}:{','.join(map(str, v['lines']))}")
        print(f"      rule   : {v['rule']}")
        print(f"      states : {v['states']}")
        print(f"      cure   : {v['cure']}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
