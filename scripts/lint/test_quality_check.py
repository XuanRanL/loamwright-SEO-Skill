#!/usr/bin/env python3
"""Find tests that cannot fail — Rule 10's missing executor.

WHY THIS EXISTS
Rule 10 says test the seam, and the 2026-08-04 audit found the disease had moved
one layer deeper: the FIXES were correct and the tests VERIFYING the fixes were
vacuous. A green suite then means nothing, which is worse than no suite, because
it is read as proof.

Two failure shapes, both mechanically detectable, both found in this repo:

1. **A test that re-implements production logic.** `test_anchor_canonical_..._v3413`
   copied the production regex into the test body and asserted against its own
   copy. Deleting the regex from `scripts/build/assemble.py` left the test green.
   A test must call the code, not re-type it.

2. **A vacuous comparison.** The digest ranker's regression test asserted
   `_relevance(cl, TERMS) >= 0.5 * 0.0 + 0.0` — i.e. `>= 0.0` — as the proof of
   "configured terms are not worse than none". It passed while its own fixture
   demonstrated the inversion the test was named for. `assert f(a) > 0` can never
   be the proof of "f(a) is not worse than f(b)": a relative claim needs both
   sides in the assertion.

Usage
-----
    python -m scripts.lint.test_quality_check
    python -m scripts.lint.test_quality_check --json
    python -m scripts.lint.test_quality_check --path tests/research
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

# Regex literals shorter than this are too generic to be evidence of copying.
MIN_PATTERN_LEN = 12

# Words that mark a test as asserting a RELATIVE property between two states.
RELATIVE_WORDS = ("not_worse", "not_better", "beats", "outranks", "higher_than",
                  "lower_than", "at_least_as", "no_worse", "ranks_below",
                  "ranks_above")

ALLOW = "# lint: test-quality-ok"


def _string_constants(tree: ast.AST) -> list[tuple[int, str]]:
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _production_patterns() -> dict[str, str]:
    """Regex literals defined under scripts/, mapped pattern -> file:line."""
    out: dict[str, str] = {}
    for py in (PLUGIN_ROOT / "scripts").rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name not in {"compile", "sub", "match", "search", "findall", "fullmatch"}:
                continue
            for arg in node.args[:1]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                        and len(arg.value) >= MIN_PATTERN_LEN:
                    out.setdefault(
                        arg.value,
                        f"{py.relative_to(PLUGIN_ROOT).as_posix()}:{node.lineno}")
    return out


def _is_zeroish(node: ast.AST) -> bool:
    """True when an expression is a constant that evaluates to 0.

    Catches the literal `0`/`0.0` and the arithmetic disguise `0.5 * 0.0 + 0.0`
    that made the ranker assertion read like a real threshold.
    """
    try:
        value = ast.literal_eval(ast.Expression(body=node))  # type: ignore[arg-type]
    except (ValueError, SyntaxError, TypeError):
        try:
            value = eval(compile(ast.Expression(body=node), "<x>", "eval"), {}, {})
        except Exception:
            return False
    if isinstance(value, bool):
        # `False == 0` is true in Python, which made `assert x is False` — a
        # perfectly good verdict assertion — look like a vacuous zero threshold.
        return False
    return isinstance(value, (int, float)) and value == 0


def _scripts_imports(tree: ast.AST) -> set[str]:
    """Names imported from scripts.* — i.e. the production code under test."""
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("scripts"):
            out |= {a.asname or a.name for a in n.names}
        elif isinstance(n, ast.Import):
            out |= {(a.asname or a.name) for a in n.names if a.name.startswith("scripts")}
    return out


def _enclosing_function(tree: ast.AST, lineno: int) -> ast.FunctionDef | None:
    best = None
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.lineno <= lineno:
            end = getattr(n, "end_lineno", n.lineno)
            if lineno <= end and (best is None or n.lineno > best.lineno):
                best = n
    return best


def _calls_any(fn: ast.FunctionDef, names: set[str]) -> bool:
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            ident = getattr(f, "id", None) or getattr(f, "attr", None)
            root = getattr(getattr(f, "value", None), "id", None)
            if (ident and ident in names) or (root and root in names):
                return True
    return False


def check_file(path: Path, prod: dict[str, str]) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    rel = path.relative_to(PLUGIN_ROOT).as_posix()
    findings: list[dict[str, Any]] = []

    def allowed(lineno: int) -> bool:
        return ALLOW in (lines[lineno - 1] if 0 < lineno <= len(lines) else "")

    imported = {n.split(".")[-1] for n in _scripts_imports(tree)}

    # --- 1. production logic re-implemented in the test body
    for lineno, s in _string_constants(tree):
        if len(s) < MIN_PATTERN_LEN or s not in prod or allowed(lineno):
            continue
        fn = _enclosing_function(tree, lineno)
        if fn is not None and _calls_any(fn, imported):
            # The test drives the real code and uses the pattern only to validate
            # its OUTPUT — that is an assertion, not a re-implementation.
            continue
        findings.append({
            "file": rel, "line": lineno, "kind": "reimplements-production-logic",
            "detail": (f"this pattern is also defined at {prod[s]} — the test asserts "
                       f"against its own copy, so deleting the production code leaves "
                       f"it green. Call the function instead."),
        })

    # --- 2. a relative claim proved by a comparison against zero
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or not fn.name.startswith("test"):
            continue
        doc = (ast.get_docstring(fn) or "").lower()
        relative = (any(w in fn.name for w in RELATIVE_WORDS)
                    or "not worse" in doc or "not better" in doc
                    or "strictly below" in doc or "strictly above" in doc
                    or "ranked below" in doc or "ranked above" in doc)
        if not relative:
            continue
        comparisons = [n for n in ast.walk(fn)
                       if isinstance(n, ast.Assert) and isinstance(n.test, ast.Compare)]
        meaningful = False
        for cmp_ in comparisons:
            for comparator in cmp_.test.comparators:  # type: ignore[attr-defined]
                if not _is_zeroish(comparator):
                    meaningful = True
        if comparisons and not meaningful and not allowed(fn.lineno):
            findings.append({
                "file": rel, "line": fn.lineno, "kind": "vacuous-relative-assertion",
                "detail": ("the name/docstring claims a RELATIVE property but every "
                           "assertion compares against zero. `assert f(a) > 0` cannot "
                           "prove 'f(a) is not worse than f(b)' — assert both sides."),
            })
    return findings


def run(root: str | None = None) -> dict[str, Any]:
    base = PLUGIN_ROOT / (root or "tests")
    prod = _production_patterns()
    findings: list[dict[str, Any]] = []
    files = sorted(base.rglob("test_*.py")) if base.is_dir() else [base]
    for f in files:
        findings.extend(check_file(f, prod))
    return {"scanned": len(files), "findings": findings, "passed": not findings}


def main() -> int:
    ap = argparse.ArgumentParser(description="Find tests that cannot fail (Rule 10)")
    ap.add_argument("--path", help="subtree to scan (default: tests/)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    res = run(a.path)
    if a.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res["passed"] else 1

    if res["passed"]:
        print(f"test_quality_check: OK — {res['scanned']} file(s), no vacuous tests")
        return 0
    print(f"test_quality_check: {len(res['findings'])} finding(s)\n")
    for f in res["findings"]:
        print(f"  {f['file']}:{f['line']}  [{f['kind']}]")
        print(f"      {f['detail']}\n")
    print(f"  (add `{ALLOW}` on the flagged line if it is genuinely intentional)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
