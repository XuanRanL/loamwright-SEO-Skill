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
    python -m scripts.lint.contract_fanout_check --include-projects

SCOPE (v3.42.11 — Rule 14 pass)
This executor reported "OK — 3 contracts, no stale instruction layer" while 25
files still stated the retired `{slug}-pillar` contract. It was not wrong about
what it read; it could not read the layer where the stale contract lives:

  * there was no `projects/**` glob at all — yet `projects/{slug}/CLAUDE.md` is
    auto-loaded by every session opened in that directory and is the densest
    instruction layer in the tree;
  * `references/*.md` was NON-recursive, reaching 4 of 101 reference docs — the
    style guides that actually instruct writers all live one directory down.

Both are now scanned, always. They are reported as an ADVISORY bucket rather
than folded into the exit code, because per-client project docs are gitignored,
operator-owned state: curing 24 of them is a deliberate act, not a side effect
of fixing this tool's eyesight. `--include-projects` promotes the advisory
bucket into the exit code for anyone who wants CI to gate on it.

What is NOT acceptable, and the reason the bucket is printed unconditionally: a
default run that says "OK" without naming the surface it declined to block on.
That silence is the thing Rule 14 is about.
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

# Instruction layers the globs above cannot see. Always scanned; reported
# separately; promoted into the exit code with --include-projects.
#   projects/**/*.md  — per-client CLAUDE.md / PROJECT.md / init-report.md, each
#                       auto-loaded for sessions opened in that project dir
#   references/**/*.md — the same reference tree, recursively (4 of 101 before)
ADVISORY_SCOPE = ["projects/**/*.md", "references/**/*.md"]

DEFAULT_EXEMPT = ["CHANGELOG.md", "memory/**", "docs/**",
                  "dist/**", "references/retired-contracts.json"]


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


def _scan(rule: dict[str, Any], files: list[Path]) -> list[dict[str, Any]]:
    pattern = re.compile(rule["pattern"])
    requires = re.compile(rule["requires"])
    found: list[dict[str, Any]] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not pattern.search(text):
            continue
        if requires.search(text):
            continue              # the file acknowledges the new contract
        lines = [i + 1 for i, ln in enumerate(text.splitlines())
                 if pattern.search(ln)]
        found.append({
            "rule": rule["id"],
            "file": f.relative_to(PLUGIN_ROOT).as_posix(),
            "lines": lines[:8],
            "states": rule["retired_contract"],
            "cure": rule["cure"],
        })
    return found


def run(only: str | None = None, include_projects: bool = False) -> dict[str, Any]:
    """Scan both surfaces.

    `violations`          — shipped instruction layers; these drive the exit code.
    `advisory_violations` — per-client project docs and nested reference docs.
                            Always scanned so the result can never read as "clean"
                            when it merely means "unscanned"; folded into
                            `violations` only when include_projects is set.
    """
    rules = _load_rules(only)
    violations: list[dict[str, Any]] = []
    advisory: list[dict[str, Any]] = []

    for rule in rules:
        exempt = (rule.get("exempt") or []) + DEFAULT_EXEMPT
        blocking_files = _files(rule.get("scope") or DEFAULT_SCOPE, exempt)
        violations += _scan(rule, blocking_files)

        if rule.get("scope"):
            continue      # a rule that pins its own scope means it, verbatim
        already = set(blocking_files)
        extra = [p for p in _files(ADVISORY_SCOPE, exempt) if p not in already]
        advisory += _scan(rule, extra)

    if include_projects:
        violations += advisory

    return {"rules_checked": len(rules),
            "violations": violations,
            "advisory_violations": [] if include_projects else advisory,
            "advisory_count": 0 if include_projects else len(advisory),
            "passed": not violations}


def _print_violations(violations: list[dict[str, Any]]) -> None:
    for v in violations:
        print(f"  {v['file']}:{','.join(map(str, v['lines']))}")
        print(f"      rule   : {v['rule']}")
        print(f"      states : {v['states']}")
        print(f"      cure   : {v['cure']}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Rule 11 — retired-contract fan-out check")
    ap.add_argument("--rule", help="check a single rule id")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--include-projects", action="store_true",
                    help="promote the advisory surface (projects/**/*.md and nested "
                         "references/**/*.md) into the exit code instead of only "
                         "reporting it")
    a = ap.parse_args()

    res = run(a.rule, include_projects=a.include_projects)
    if a.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res["passed"] else 1

    if not res["rules_checked"]:
        print("contract_fanout_check: no rules registered "
              f"(expected {REGISTRY.relative_to(PLUGIN_ROOT)})", file=sys.stderr)
        return 2

    if res["passed"]:
        print(f"contract_fanout_check: OK — {res['rules_checked']} contract(s), "
              f"no stale SHIPPED instruction layer")
    else:
        print(f"contract_fanout_check: {len(res['violations'])} stale layer(s)\n")
        _print_violations(res["violations"])

    # Never let a pass read as "everything was checked". Printed on pass AND on
    # fail, because the surface it names is the one the old globs could not see.
    if res["advisory_count"]:
        files = sorted({v["file"] for v in res["advisory_violations"]})
        print(f"\ncontract_fanout_check: advisory — {res['advisory_count']} stale "
              f"layer(s) across {len(files)} per-client/nested file(s) NOT counted "
              f"in the exit code:")
        for name in files:
            print(f"    {name}")
        print("  These are operator-owned (projects/** is gitignored client state) "
              "and nested reference docs.\n  Curing them is a deliberate act; run "
              "with --include-projects to gate on them.")

    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
