"""Sanitized open-source export — the ONLY supported path to a public repo.

Builds a publishable copy of this plugin under ``dist/opensource-export/``:

1. Source list = ``git ls-files`` (tracked files only — runtime junk never ships).
2. Drops every path in the map's ``exclude`` list (private test suite, memory/,
   docs/, evals/, per-client one-off scripts, the map itself).
3. Applies the ordered replacement rules from ``OPENSOURCE-SANITIZE-MAP.json``
   to every text file (client slugs/domains → neutral aliases, e-mail, names).
4. Generates public-only files (``.gitignore``, ``projects/README.md``).
5. Leak scan: greps the whole output for every ``verify_terms`` entry and FAILS
   (exit 1) on any hit. An export that was not verified must never be pushed.

The private repo (this working tree) is never modified. The map file holds all
private terms; this script stays generic so it can ship in the public tree.

Usage:
    python -m scripts.release.opensource_export                # export + verify
    python -m scripts.release.opensource_export --json         # machine summary
    python -m scripts.release.opensource_export --git-init     # + fresh git repo
    python -m scripts.release.opensource_export --out DIR      # custom target

Exit codes: 0 = exported + verified clean · 1 = leak-scan hits · 2 = usage/env.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAP = REPO_ROOT / "OPENSOURCE-SANITIZE-MAP.json"
DEFAULT_OUT = REPO_ROOT / "dist" / "opensource-export"
MARKER_NAME = ".opensource-export-marker"
TOOLS_DIR = Path.home() / ".xuanran-seo" / "tools"

PUBLIC_GITIGNORE = """\
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage

# Virtual environments
.venv/
venv/

# Runtime data (created per task / per project — never plugin source)
workspace/
memory/
projects/*/
!projects/README.md

# User secrets (NEVER commit)
*.key
*.pem
.env
.env.local
config.local.yaml

# Build outputs
/dist/
/build/

# Logs / OS / editor
*.log
.DS_Store
Thumbs.db
.vscode/
.idea/

# Export tooling bookkeeping
.opensource-export-marker
"""

PROJECTS_README = """\
# projects/

Per-client project archives live here — one directory per site, created by the
`/init` wizard (`subskills/init/website-project-init`). Each archive holds the
project's `business-context.json`, brand guideline, taxonomy config, article
CSS, personas, and research caches.

**Everything under `projects/{slug}/` is client-confidential and gitignored.**
Only this README is tracked. Run `/init https://your-site.com` to create your
first project; credentials are stored outside the repo in `~/.xuanran-seo/`.
"""


@dataclass(frozen=True)
class Rule:
    """One ordered replacement: literal ``find`` → ``replace``.

    ``paths`` (include globs) / ``exclude_paths`` scope a rule to specific
    files — needed because some private terms are also legitimate data (e.g.
    place names inside the world gazetteer must never be rewritten).
    """

    find: str
    replace: str
    case_insensitive: bool
    paths: tuple[str, ...] = ()
    exclude_paths: tuple[str, ...] = ()

    def compiled(self) -> re.Pattern[str]:
        flags = re.IGNORECASE if self.case_insensitive else 0
        return re.compile(re.escape(self.find), flags)

    def applies_to(self, rel_path: str) -> bool:
        if any(fnmatch.fnmatch(rel_path, g) for g in self.exclude_paths):
            return False
        if self.paths:
            return any(fnmatch.fnmatch(rel_path, g) for g in self.paths)
        return True


@dataclass(frozen=True)
class SanitizeMap:
    """Parsed OPENSOURCE-SANITIZE-MAP.json."""

    rules: tuple[Rule, ...]
    exclude: tuple[str, ...]
    verify_terms: tuple[str, ...]


def load_map(path: Path) -> SanitizeMap:
    """Load and validate the private anonymization map."""
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(
            f"[export] map file not found: {path} — the export cannot run "
            "without the private anonymization map (exit 2)."
        ) from None
    rules = tuple(
        Rule(
            find=str(entry["find"]),
            replace=str(entry["replace"]),
            case_insensitive=bool(entry.get("ci", False)),
            paths=tuple(str(p) for p in entry.get("paths", [])),
            exclude_paths=tuple(str(p) for p in entry.get("exclude_paths", [])),
        )
        for entry in raw.get("replacements", [])
    )
    exclude = tuple(str(e) for e in raw.get("exclude", []))
    verify_terms = tuple(str(t) for t in raw.get("verify_terms", []))
    if not rules or not verify_terms:
        raise SystemExit("[export] map has no replacements/verify_terms (exit 2).")
    return SanitizeMap(rules=rules, exclude=exclude, verify_terms=verify_terms)


def git_tracked_files(repo: Path) -> list[str]:
    """Repo-relative paths of every git-tracked file (the ONLY export source)."""
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    return [p for p in proc.stdout.decode("utf-8").split("\0") if p]


def is_excluded(rel_path: str, exclude: tuple[str, ...]) -> bool:
    """Prefix match for ``dir/`` entries, exact/fnmatch for file entries."""
    for pattern in exclude:
        if pattern.endswith("/"):
            if rel_path.startswith(pattern):
                return True
        elif rel_path == pattern or fnmatch.fnmatch(rel_path, pattern):
            return True
    return False


def sanitize_text(
    text: str, rules: tuple[Rule, ...], rel_path: str = ""
) -> tuple[str, dict[str, int]]:
    """Apply every applicable rule in order; return text + per-rule counts."""
    fired: dict[str, int] = {}
    for rule in rules:
        if rel_path and not rule.applies_to(rel_path):
            continue
        pattern = rule.compiled()
        text, count = pattern.subn(rule.replace, text)
        if count:
            fired[rule.find] = fired.get(rule.find, 0) + count
    return text, fired


def _prepare_out_dir(out: Path, force: bool) -> None:
    """Empty the target dir, preserving .git (republish) — refuse foreign dirs."""
    if not out.exists():
        out.mkdir(parents=True)
        return
    if any(out.iterdir()) and not (out / MARKER_NAME).exists() and not force:
        raise SystemExit(
            f"[export] {out} is non-empty and has no {MARKER_NAME} — refusing to "
            "wipe a directory this tool did not create (use --force to override)."
        )
    for child in out.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def export_tree(
    repo: Path, out: Path, smap: SanitizeMap, force: bool
) -> dict[str, Any]:
    """Copy + sanitize the tracked tree into ``out``. Returns summary stats."""
    _prepare_out_dir(out, force)
    exported = 0
    sanitized_files = 0
    excluded: list[str] = []
    binary_copied: list[str] = []
    total_fired: dict[str, int] = {}

    for rel in git_tracked_files(repo):
        if is_excluded(rel, smap.exclude):
            excluded.append(rel)
            continue
        src = repo / rel
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            dst.write_bytes(data)
            binary_copied.append(rel)
            exported += 1
            continue
        new_text, fired = sanitize_text(text, smap.rules, rel_path=rel)
        if fired:
            sanitized_files += 1
            for term, count in fired.items():
                total_fired[term] = total_fired.get(term, 0) + count
        dst.write_bytes(new_text.encode("utf-8"))
        exported += 1

    (out / ".gitignore").write_text(PUBLIC_GITIGNORE, encoding="utf-8")
    projects_dir = out / "projects"
    projects_dir.mkdir(exist_ok=True)
    (projects_dir / "README.md").write_text(PROJECTS_README, encoding="utf-8")
    (out / MARKER_NAME).write_text(
        "Generated by scripts/release/opensource_export.py — safe to wipe.\n",
        encoding="utf-8",
    )
    return {
        "exported_files": exported,
        "sanitized_files": sanitized_files,
        "excluded_files": len(excluded),
        "binary_copied": binary_copied,
        "replacements_fired": total_fired,
    }


def verify_clean(out: Path, verify_terms: tuple[str, ...]) -> list[dict[str, Any]]:
    """Leak scan: case-insensitive substring search of every exported file."""
    lowered = [t.lower() for t in verify_terms]
    hits: list[dict[str, Any]] = []
    for path in sorted(out.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.relative_to(out).parts:
            continue
        if path.name == MARKER_NAME:
            continue
        try:
            content = path.read_bytes().decode("utf-8", errors="ignore").lower()
        except OSError:
            continue
        for term in lowered:
            count = content.count(term)
            if count:
                hits.append(
                    {
                        "file": str(path.relative_to(out)),
                        "term": term,
                        "count": count,
                    }
                )
    return hits


def _find_tool(name: str) -> str | None:
    exe = shutil.which(name)
    if exe:
        return exe
    for cand in (TOOLS_DIR / f"{name}.exe", TOOLS_DIR / name):
        if cand.exists():
            return str(cand)
    return None


def run_secret_scans(out: Path, require: bool) -> dict[str, Any]:
    """Gitleaks + TruffleHog over the export TREE and its git HISTORY.

    The privacy leak scan (verify_clean) only knows the named private terms;
    it cannot catch entropy-shaped credentials — a hardcoded Google OAuth
    secret survived it on 2026-08-01 and was caught only by GitHub push
    protection. This stage runs BOTH scanners locally before anything is
    pushed. Any finding fails the export (exit 1). Missing binaries are a
    warning by default and fatal with ``require=True`` (the release flow).
    """
    gl, th = _find_tool("gitleaks"), _find_tool("trufflehog")
    cfg = REPO_ROOT / ".gitleaks.toml"
    gl_cfg = ["-c", str(cfg)] if cfg.exists() else []
    missing = [n for n, e in (("gitleaks", gl), ("trufflehog", th)) if e is None]
    if missing and require:
        raise SystemExit(
            f"[export] secret scanners missing: {missing} — install into "
            f"{TOOLS_DIR} or PATH (release flow requires them; exit 2)."
        )
    result: dict[str, Any] = {"missing": missing, "findings": 0, "scans": {}}
    has_git = (out / ".git").exists()

    def _run(label: str, cmd: list[str], finding_codes: tuple[int, ...]) -> None:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        hit = proc.returncode in finding_codes
        ok = proc.returncode == 0
        result["scans"][label] = {
            "rc": proc.returncode,
            "status": "findings" if hit else ("clean" if ok else "error"),
            "tail": (proc.stdout + proc.stderr)[-400:].strip() if (hit or not ok) else "",
        }
        if hit:
            result["findings"] += 1
        elif not ok:
            raise SystemExit(
                f"[export] secret scanner {label} errored (rc={proc.returncode}): "
                f"{(proc.stderr or proc.stdout)[-300:]}"
            )

    if gl:
        _run("gitleaks-tree",
             [gl, "detect", "--no-git", "-s", str(out), *gl_cfg,
              "--exit-code", "1", "--no-banner", "--redact"], (1,))
        if has_git:
            # Scans the export repo's COMMITTED history — i.e. what is (or is
            # about to be) public. A finding here means an already-published
            # commit carries it: fix the source, then rebuild history.
            _run("gitleaks-history",
                 [gl, "detect", "-s", str(out), *gl_cfg, "--exit-code", "1",
                  "--no-banner", "--redact"], (1,))
    # Lob (direct-mail API) keys are `test_`/`live_` + 35 chars, which pytest
    # FILENAMES like `test_quality_gates_brief_seam_2026_07_17.py` satisfy — and
    # Lob's test API "verifies" such strings, so the finding blocks the release
    # as a verified secret (first hit: CHANGELOG.md, 2026-08-10). This project
    # never touches Lob; excluding that one detector keeps every other detector
    # armed. Do NOT widen this to a path exclusion — CHANGELOG prose is exactly
    # where a real secret would land.
    th_excl = ["--exclude-detectors", "lob"]
    if th:
        _run("trufflehog-tree",
             [th, "filesystem", str(out), "--fail", "--no-update", "--json",
              *th_excl], (183,))
        if has_git:
            _run("trufflehog-history",
                 [th, "git", f"file://{out.as_posix()}", "--fail",
                  "--no-update", "--json", *th_excl], (183,))
    return result


def git_init_public(out: Path, version: str) -> str:
    """Init a fresh public repo with a NEUTRAL identity (never the dev's)."""
    if not (out / ".git").exists():
        subprocess.run(["git", "init", "-b", "main"], cwd=out, check=True)
    neutral = [
        ["git", "config", "user.name", "XuanRanL"],
        ["git", "config", "user.email", "XuanRanL@users.noreply.github.com"],
    ]
    for cmd in neutral:
        subprocess.run(cmd, cwd=out, check=True)
    subprocess.run(["git", "add", "-A"], cwd=out, check=True)
    msg = f"chore(release): public export v{version}"
    commit = subprocess.run(
        ["git", "commit", "-m", msg],
        cwd=out,
        capture_output=True,
        text=True,
    )
    if commit.returncode != 0 and "nothing to commit" not in commit.stdout:
        raise SystemExit(f"[export] git commit failed: {commit.stderr.strip()}")
    return msg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sanitized open-source export — whitelist copy + anonymize + leak scan."
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP, dest="map_path")
    parser.add_argument("--skip-verify", action="store_true")
    parser.add_argument("--no-secret-scan", action="store_true",
                        help="skip gitleaks/trufflehog (NOT for releases)")
    parser.add_argument("--require-secret-scan", action="store_true",
                        help="missing scanner binaries become a hard failure")
    parser.add_argument("--git-init", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    smap = load_map(args.map_path)
    summary = export_tree(REPO_ROOT, args.out, smap, force=args.force)
    summary["out"] = str(args.out)

    hits: list[dict[str, Any]] = []
    if not args.skip_verify:
        hits = verify_clean(args.out, smap.verify_terms)
    summary["leak_scan_hits"] = hits

    secret: dict[str, Any] = {"missing": [], "findings": 0, "scans": {}}
    if not args.no_secret_scan:
        secret = run_secret_scans(args.out, require=args.require_secret_scan)
    summary["secret_scan"] = secret
    summary["clean"] = not hits and secret["findings"] == 0

    version_file = REPO_ROOT / "VERSION"
    version = (
        version_file.read_text(encoding="utf-8").strip()
        if version_file.exists()
        else "0.0.0"
    )
    summary["version"] = version

    if args.git_init and summary["clean"]:
        summary["git_commit"] = git_init_public(args.out, version)

    if args.as_json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(
            f"[export] {summary['exported_files']} files → {args.out} "
            f"({summary['sanitized_files']} sanitized, "
            f"{summary['excluded_files']} excluded)"
        )
        if hits:
            print(f"[export] ❌ LEAK SCAN FAILED — {len(hits)} hit(s):")
            for hit in hits[:40]:
                print(f"  {hit['file']}: '{hit['term']}' ×{hit['count']}")
            print("[export] DO NOT PUBLISH this output.")
        if secret["findings"]:
            print(f"[export] ❌ SECRET SCAN FAILED — {secret['findings']} scanner(s) found secrets:")
            for label, s in secret["scans"].items():
                if s["status"] == "findings":
                    print(f"  {label}: {s['tail'][:200]}")
            print("[export] DO NOT PUBLISH this output.")
        elif secret["missing"]:
            print(f"[export] ⚠ secret scanners not run: {secret['missing']} missing "
                  f"(install into {TOOLS_DIR})")
        elif not args.no_secret_scan:
            ran = ", ".join(secret["scans"])
            print(f"[export] ✅ secret scan clean ({ran})")
        if summary["clean"] and not args.skip_verify:
            print("[export] ✅ leak scan clean — safe to publish.")
    return 0 if summary["clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
