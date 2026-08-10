"""scripts/lint/silent_except_audit.py — Audit broad-except + silent-fallback patterns.

PURPOSE
─────────
Catches the failure mode that produced version 3.3.3:

    try:
        ... # something that might raise NameError, TypeError, etc.
    except Exception:
        pass        # OR  return {}  OR  return None  OR  continue
    return DEFAULT  # silently masks the real bug

This pattern has caused 4+ production incidents:
- 3.3.3 NameError on PLUGIN_ROOT swallowed → entire schema policy filter no-op'd
- 3.3.0 silent fallback on featured_image_inline_policy.mode → [IMAGE-SLOT-cover] literal leak
- 3.2.x silent skip on citations loader key drift → ZERO citations loaded for compliant fact-checker output

Audit 2026-05-22 P1 fixed the 10 known instances. THIS lint prevents new ones.

DETECTED PATTERNS
─────────────────
  S1  except (without `as` clause) followed by silent return/pass/continue:
        except:          ← bare except (always suspicious)
        except Exception:
        except (X, Y):
        — followed within 3 lines by: pass | return ... | continue (with no
          intervening logging call to print/logging/sys.stderr)

  S2  except clause that catches the exception variable but never uses it:
        except Exception as e:
            return None    ← `e` unused, error swallowed

POLICY
──────
A broad except IS allowed if:
  - It logs the exception to stderr / logging / a structured error sink
  - It re-raises after cleanup (try/finally pattern)
  - It transforms into a domain-specific exception (raise X from e)
  - It's annotated with `# silent-except: OK because ...` comment within 2 lines

Otherwise the lint flags it.

CLI
───
  python -m scripts.lint.silent_except_audit  [--path <dir>]  [--json]  [--strict]

  --strict makes any finding exit with non-zero (CI use).
  Default exits 0 (informational) so legacy code doesn't break the CI.

EXIT
────
  0 = clean OR informational-only mode
  1 = findings exist AND --strict
  2 = bad arguments
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


# Substrings whose presence in the except body counts as "logged"
_LOG_TOKENS = (
    "print(",
    "logging.",
    "logger.",
    "log.error",
    "log.warn",
    "log.exception",
    "sys.stderr",
    "stderr",
    "raise",  # re-raise is fine
    "warnings.warn",
)

# Comment annotations that whitelist a finding
_WHITELIST_COMMENT_PREFIXES = (
    "# silent-except: OK",
    "# silent-except: ok",
    "# noqa: silent-except",
)


@dataclass
class Finding:
    path: str
    line: int
    class_id: str   # S1 / S2
    excerpt: str
    detail: str


def _is_silent_body(body: list[ast.stmt], source_lines: list[str]) -> tuple[bool, str]:
    """Inspect except-clause body. Return (is_silent, reason)."""
    # Stringify the body to check for log tokens
    body_strs: list[str] = []
    for stmt in body:
        if hasattr(ast, "unparse"):
            try:
                body_strs.append(ast.unparse(stmt))
            except Exception:
                body_strs.append("")
        # also collect raw source lines for comment-annotation check
    body_str = " ".join(body_strs).lower()

    # Check for any log/raise token
    for tok in _LOG_TOKENS:
        if tok in body_str:
            return False, f"logged via '{tok}'"

    # If body is a single pass / continue / return-with-trivial-default → silent
    if len(body) == 1:
        s = body[0]
        if isinstance(s, ast.Pass):
            return True, "bare `pass` with no logging"
        if isinstance(s, ast.Continue):
            return True, "bare `continue` with no logging"
        if isinstance(s, ast.Return):
            # Return None / [] / {} / set() / False / "" — all silent defaults
            v = s.value
            if v is None:
                return True, "bare `return` (None)"
            if isinstance(v, ast.Constant) and v.value in (None, False, "", 0):
                return True, f"silent default return {v.value!r}"
            if isinstance(v, ast.Dict):
                if not v.keys:
                    return True, "silent empty-dict return"
            elif isinstance(v, (ast.List, ast.Set, ast.Tuple)) and not v.elts:
                return True, "silent empty-collection return"
            if isinstance(v, ast.Call):
                # `return set()` / `return dict()` / `return list()`
                if isinstance(v.func, ast.Name) and v.func.id in ("set", "dict", "list", "tuple") and not v.args and not v.keywords:
                    return True, f"silent {v.func.id}() return"
            # other returns (with a meaningful value) — not flagged as silent
            return False, "return with a meaningful value"

    # Multi-statement body without log token: only flag if the LAST statement
    # is a return/pass/continue. Otherwise the body might be doing legitimate
    # recovery work even without log token (e.g. updating state, writing fallback file).
    last = body[-1]
    if isinstance(last, (ast.Pass, ast.Continue)):
        return True, "no logging + trailing pass/continue"
    if isinstance(last, ast.Return) and last.value is None:
        return True, "no logging + trailing bare return"

    return False, "multi-statement body, not clearly silent"


def _has_whitelist_comment(source_lines: list[str], lineno: int) -> bool:
    """Check ±2 lines around the except clause for a whitelist annotation."""
    for offset in (-2, -1, 0, 1, 2):
        i = lineno + offset
        if 0 <= i - 1 < len(source_lines):
            stripped = source_lines[i - 1].strip()
            for prefix in _WHITELIST_COMMENT_PREFIXES:
                if stripped.startswith(prefix):
                    return True
    return False


def _classify_handler(handler: ast.ExceptHandler) -> str | None:
    """Return "broad" if this except catches Exception / BaseException / bare, else None."""
    t = handler.type
    if t is None:
        return "broad"   # bare except:
    if isinstance(t, ast.Name) and t.id in ("Exception", "BaseException"):
        return "broad"
    if isinstance(t, ast.Tuple):
        for elt in t.elts:
            if isinstance(elt, ast.Name) and elt.id in ("Exception", "BaseException"):
                return "broad"
    return None  # specific exception class


def audit_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        source = path.read_text(encoding="utf-8")
        source_lines = source.split("\n")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return findings

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            broad = _classify_handler(handler)
            if broad != "broad":
                continue
            if _has_whitelist_comment(source_lines, handler.lineno):
                continue

            is_silent, reason = _is_silent_body(handler.body, source_lines)
            if not is_silent:
                continue

            # Excerpt: handler line + 2 below
            start_line = handler.lineno - 1
            excerpt = "\n".join(source_lines[start_line:start_line + 4]).strip()
            class_id = "S2" if handler.name else "S1"  # has `as e:` but unused
            findings.append(Finding(
                path=str(path),
                line=handler.lineno,
                class_id=class_id,
                excerpt=excerpt[:400],
                detail=(
                    f"broad except + silent body ({reason}). "
                    "Either (a) log the exception to stderr/logging, "
                    "(b) catch a more specific exception class, or "
                    "(c) annotate with `# silent-except: OK because <reason>` "
                    "comment within 2 lines of the except clause."
                ),
            ))

    return findings


def iter_python_files(root: Path) -> Iterable[Path]:
    skip_dirs = {".venv", "__pycache__", ".git", "node_modules", "dist", "build", ".pytest_cache"}
    for p in root.rglob("*.py"):
        if any(part in skip_dirs for part in p.parts):
            continue
        yield p


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit broad-except + silent-fallback patterns")
    ap.add_argument("--path", default="scripts", help="Root path to scan (default: scripts/)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="Exit non-zero if findings exist")
    ap.add_argument("--out", help="Also write JSON report to this path")
    args = ap.parse_args()

    root = Path(args.path)
    if not root.exists():
        print(f"path not found: {root}", file=sys.stderr)
        return 2

    all_findings: list[Finding] = []
    files_scanned = 0
    for f in iter_python_files(root):
        files_scanned += 1
        all_findings.extend(audit_file(f))

    report = {
        "scanned_root": str(root),
        "files_scanned": files_scanned,
        "finding_count": len(all_findings),
        "findings": [asdict(f) for f in all_findings],
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"silent_except_audit: scanned {files_scanned} files under {root}")
        if not all_findings:
            print(f"  CLEAN — 0 silent-except findings")
        else:
            print(f"  {len(all_findings)} finding(s):")
            for f in all_findings:
                print(f"    [{f.class_id}] {f.path}:{f.line}")
                for line in f.excerpt.split("\n")[:3]:
                    print(f"        {line}")

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.strict and all_findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
