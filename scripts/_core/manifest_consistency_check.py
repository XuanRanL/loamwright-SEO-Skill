"""
scripts/_core/manifest_consistency_check.py — Keep VERSION in sync across all manifests.

Files that must agree on version:
    1. VERSION                           (single source of truth)
    2. .claude-plugin/plugin.json        ("version" field)
    3. .claude-plugin/marketplace.json   ("version" field AND every
       plugins[].version — the field /plugin install actually registers;
       it went stale to 3.14.1 unnoticed until 2026-08-01 because only the
       outer key was checked)
    4. install/claude-code/install.sh    ($PLUGIN_VERSION variable)
    5. install/claude-code/install.ps1   ($PluginVersion variable)
    6. install/wordpress-mu-plugin/seo-machine-yoast-rest.php
                                          (Version: header + 'Version' = "x.y.z")
    7. CHANGELOG.md                       (## [x.y.z] heading)
    8. README.md                          (any "v3.x.x" mention)
    9. scripts/__init__.py / scripts/_core/__init__.py (__version__)

CLI:
    python -m scripts._core.manifest_consistency_check
    python -m scripts._core.manifest_consistency_check --check
    python -m scripts._core.manifest_consistency_check --apply       # auto-fix
    python -m scripts._core.manifest_consistency_check --json
    python -m scripts._core.manifest_consistency_check --bump patch  # 3.2.0 → 3.2.1

CI integration: GitHub Actions runs --check on every commit; non-zero exit = drift.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal


# ─── Locate plugin root ─────────────────────────────────────────

def _plugin_root() -> Path:
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "VERSION").exists() and (p / ".claude-plugin").is_dir():
            return p
        p = p.parent
    raise RuntimeError("Cannot find plugin root")


PLUGIN_ROOT: Final[Path] = _plugin_root()

VERSION_RE: Final[re.Pattern[str]] = re.compile(r"^\d+\.\d+\.\d+$")


# ─── Per-file handlers ───────────────────────────────────────────

@dataclass
class FileVersion:
    path: Path
    current: str | None
    expected: str
    matches: bool
    error: str | None = None


def _read_version_file() -> str:
    v = (PLUGIN_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not VERSION_RE.match(v):
        raise ValueError(f"VERSION file content invalid: {v!r}")
    return v


def _check_json(path: Path, expected: str, *, key_chain: list[str | int]) -> FileVersion:
    """Check JSON file's nested "version" key (int items index into lists)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cur = data
        for k in key_chain:
            cur = cur[k]
        return FileVersion(path=path, current=str(cur), expected=expected, matches=str(cur) == expected)
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        return FileVersion(path=path, current=None, expected=expected, matches=False, error=str(e))


def _check_regex(path: Path, expected: str, pattern: re.Pattern[str]) -> FileVersion:
    """Check version via regex; extract group(1) as the current version."""
    try:
        content = path.read_text(encoding="utf-8")
        m = pattern.search(content)
        if not m:
            return FileVersion(path=path, current=None, expected=expected, matches=False,
                               error=f"No version pattern match in {path.name}")
        return FileVersion(path=path, current=m.group(1), expected=expected,
                           matches=m.group(1) == expected)
    except FileNotFoundError as e:
        return FileVersion(path=path, current=None, expected=expected, matches=False, error=str(e))


def _check_all(expected: str) -> list[FileVersion]:
    """Run all version checks. Files that don't exist are reported but not fatal."""
    checks: list[FileVersion] = []

    # 1. VERSION file (sanity)
    checks.append(FileVersion(
        path=PLUGIN_ROOT / "VERSION",
        current=expected,
        expected=expected,
        matches=True,
    ))

    # 2. plugin.json
    checks.append(_check_json(
        PLUGIN_ROOT / ".claude-plugin" / "plugin.json",
        expected, key_chain=["version"]
    ))

    # 3. marketplace.json — outer version AND every plugins[].version.
    # plugins[].version is what /plugin install actually registers; checking
    # only the outer key let it sit stale at 3.14.1 (found 2026-08-01).
    mp_path = PLUGIN_ROOT / ".claude-plugin" / "marketplace.json"
    checks.append(_check_json(mp_path, expected, key_chain=["version"]))
    try:
        n_plugins = len(json.loads(mp_path.read_text(encoding="utf-8")).get("plugins", []))
    except (FileNotFoundError, json.JSONDecodeError):
        n_plugins = 0
    for i in range(n_plugins):
        checks.append(_check_json(mp_path, expected, key_chain=["plugins", i, "version"]))

    # 4. install.sh: PLUGIN_VERSION="3.2.0"
    checks.append(_check_regex(
        PLUGIN_ROOT / "install" / "claude-code" / "install.sh",
        expected,
        re.compile(r'^PLUGIN_VERSION="([0-9]+\.[0-9]+\.[0-9]+)"', re.MULTILINE)
    ))

    # 5. install.ps1: $PluginVersion = "3.2.0"
    checks.append(_check_regex(
        PLUGIN_ROOT / "install" / "claude-code" / "install.ps1",
        expected,
        re.compile(r'^\$PluginVersion\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', re.MULTILINE)
    ))

    # 6. WordPress MU-plugin
    php_file = PLUGIN_ROOT / "install" / "wordpress-mu-plugin" / "seo-machine-yoast-rest.php"
    checks.append(_check_regex(
        php_file, expected,
        re.compile(r"\*\s*Version:\s*([0-9]+\.[0-9]+\.[0-9]+)")
    ))

    # 7. CHANGELOG.md
    checks.append(_check_regex(
        PLUGIN_ROOT / "CHANGELOG.md", expected,
        re.compile(r"^##\s+\[([0-9]+\.[0-9]+\.[0-9]+)\]", re.MULTILINE)
    ))

    # 8. scripts/__init__.py
    checks.append(_check_regex(
        PLUGIN_ROOT / "scripts" / "__init__.py", expected,
        re.compile(r'^__version__\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', re.MULTILINE)
    ))

    return checks


# ─── Apply (auto-fix) ────────────────────────────────────────────

def _apply_fix(check: FileVersion) -> bool:
    """Update a file in-place to match expected version. Returns True if changed."""
    if check.matches:
        return False
    if check.error and "FileNotFound" in check.error:
        return False  # don't create missing files; warn user

    path = check.path
    content = path.read_text(encoding="utf-8")

    name = path.name
    if name == "plugin.json" or name == "marketplace.json":
        # JSON replacement — for marketplace.json also sync every
        # plugins[].version (the field /plugin install registers).
        try:
            data = json.loads(content)
            data["version"] = check.expected
            if name == "marketplace.json":
                for plugin_entry in data.get("plugins", []):
                    if isinstance(plugin_entry, dict) and "version" in plugin_entry:
                        plugin_entry["version"] = check.expected
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return True
        except json.JSONDecodeError:
            return False

    elif name == "install.sh":
        new = re.sub(
            r'(^PLUGIN_VERSION=")[0-9]+\.[0-9]+\.[0-9]+(")',
            rf'\g<1>{check.expected}\g<2>',
            content, flags=re.MULTILINE,
        )
        if new != content:
            path.write_text(new, encoding="utf-8")
            return True

    elif name == "install.ps1":
        new = re.sub(
            r'(^\$PluginVersion\s*=\s*")[0-9]+\.[0-9]+\.[0-9]+(")',
            rf'\g<1>{check.expected}\g<2>',
            content, flags=re.MULTILINE,
        )
        if new != content:
            path.write_text(new, encoding="utf-8")
            return True

    elif name.endswith(".php"):
        new = re.sub(
            r'(\*\s*Version:\s*)[0-9]+\.[0-9]+\.[0-9]+',
            rf'\g<1>{check.expected}',
            content,
        )
        if new != content:
            path.write_text(new, encoding="utf-8")
            return True

    elif name == "CHANGELOG.md":
        # Only update if current top heading is the expected — don't add a new heading;
        # That's the human's responsibility (write the actual changelog entries first).
        return False

    elif name == "__init__.py":
        new = re.sub(
            r'(^__version__\s*=\s*")[0-9]+\.[0-9]+\.[0-9]+(")',
            rf'\g<1>{check.expected}\g<2>',
            content, flags=re.MULTILINE,
        )
        if new != content:
            path.write_text(new, encoding="utf-8")
            return True

    return False


# ─── Bump helpers ────────────────────────────────────────────────

def _bump(version: str, level: Literal["patch", "minor", "major"]) -> str:
    parts = [int(p) for p in version.split(".")]
    if level == "patch":
        parts[2] += 1
    elif level == "minor":
        parts[1] += 1
        parts[2] = 0
    elif level == "major":
        parts[0] += 1
        parts[1] = 0
        parts[2] = 0
    return ".".join(str(p) for p in parts)


# ─── CLI ─────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Manifest version consistency check")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", default=True,
                   help="Default mode: report drift (non-zero exit on drift)")
    g.add_argument("--apply", action="store_true",
                   help="Auto-fix all files to match VERSION")
    g.add_argument("--bump", choices=["patch", "minor", "major"],
                   help="Bump version (writes new VERSION + applies)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    expected = _read_version_file()

    # Handle --bump
    if args.bump:
        new_v = _bump(expected, args.bump)
        (PLUGIN_ROOT / "VERSION").write_text(new_v + "\n", encoding="utf-8")
        print(f"Bumped VERSION: {expected} → {new_v}")
        expected = new_v
        args.apply = True

    checks = _check_all(expected)

    if args.apply:
        applied = 0
        for c in checks:
            if not c.matches:
                if _apply_fix(c):
                    applied += 1
        # re-check
        checks = _check_all(expected)
        drift = [c for c in checks if not c.matches]
        if args.json:
            print(json.dumps({
                "expected_version": expected,
                "applied_count": applied,
                "remaining_drift": [
                    {"path": str(c.path.relative_to(PLUGIN_ROOT)), "current": c.current, "error": c.error}
                    for c in drift
                ],
            }, indent=2))
        else:
            print(f"Expected version: {expected}")
            print(f"Auto-fixed: {applied} file(s)")
            if drift:
                print(f"Remaining drift ({len(drift)}):")
                for c in drift:
                    rel = c.path.relative_to(PLUGIN_ROOT)
                    print(f"  ✗ {rel}: current={c.current!r}  error={c.error or ''}")
        return 0 if not drift else 1

    # --check (default)
    drift = [c for c in checks if not c.matches]
    if args.json:
        print(json.dumps({
            "expected_version": expected,
            "total_checked": len(checks),
            "drift_count": len(drift),
            "drift": [
                {
                    "path": str(c.path.relative_to(PLUGIN_ROOT)),
                    "current": c.current,
                    "expected": c.expected,
                    "error": c.error,
                }
                for c in drift
            ],
        }, indent=2))
    else:
        print(f"Expected version: {expected}")
        print(f"Files checked:    {len(checks)}")
        if not drift:
            print("✓ All manifests consistent")
        else:
            print(f"✗ {len(drift)} file(s) out of sync:")
            for c in drift:
                rel = c.path.relative_to(PLUGIN_ROOT)
                if c.error:
                    print(f"  ✗ {rel}: ERROR {c.error}")
                else:
                    print(f"  ✗ {rel}: {c.current!r} ≠ {c.expected!r}")
            print("\nRun with --apply to auto-fix.")

    return 0 if not drift else 1


if __name__ == "__main__":
    sys.exit(main())
