"""
scripts/_core/project_paths.py — Canonical project folder path resolver.

Every script / agent / skill that touches `projects/{slug}/...` MUST go through
this module. Otherwise paths drift, refactors break things, and multi-tenant
isolation gets fuzzy.

Standard project layout (see references/project-folder-layout.md):

    projects/{slug}/
    ├── project.yaml                     (root — metadata)
    ├── internal-links-map.md            (root — frequently consulted)
    ├── KNOWN_ISSUES.md                  (root — optional)
    ├── .seo/                            (hidden runtime state)
    │   ├── state.json
    │   ├── change-log.json
    │   ├── wp-taxonomy-cache.json
    │   ├── baselines/drift.sqlite
    │   ├── archive/
    │   ├── backups/
    │   ├── summaries/
    │   └── observability/
    ├── brand/                           (brand assets)
    │   ├── brand-guideline.yaml
    │   ├── brand-config.json
    │   ├── personas/{persona-id}.json
    │   └── voice-samples/
    ├── research/                        (research outputs)
    │   ├── business-context.md
    │   ├── competitors.json
    │   ├── seo-baseline.json
    │   ├── target-keywords.md
    │   ├── keyword-universe.md
    │   ├── content-gaps.json
    │   └── ai-probes/{date}.json
    ├── articles/{article-slug}/         (published articles)
    ├── clusters/{seed-slug}/            (topic clusters)
    ├── metrics/{source}-{period}-{date}.json
    ├── audits/                          (all reports + monitor outputs)
    │   ├── outcomes.json
    │   ├── rank-history/{date}.json
    │   ├── drift-reports/{url}-{date}.json
    │   ├── ai-citations/{date}.json
    │   ├── cross-link-suggestions-{date}.json
    │   ├── refresh-queue.json
    │   ├── perf-{period}-{date}.md
    │   ├── brand-tuner-report-{date}.json
    │   └── brand-guideline.diff.{date}.yaml
    ├── assets/images/{article-slug}/    (media)
    └── credentials/                     (gitignored — API keys)
        └── wordpress.json

Usage:
    from scripts._core.project_paths import project_root, brand_dir, audits_dir

    p = project_root("client-a")                      # → Path
    bg = brand_dir("client-a") / "brand-guideline.yaml"
    out = audits_dir("client-a") / "outcomes.json"

    # Or create the standard tree for a new project:
    ensure_project_tree("client-a")
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final, Literal

from scripts._core.file_bus import PLUGIN_ROOT


# Subdirectory names (single source of truth — do not hardcode elsewhere)
SEO_DIR: Final[str] = ".seo"
BRAND_DIR: Final[str] = "brand"
RESEARCH_DIR: Final[str] = "research"
ARTICLES_DIR: Final[str] = "articles"
CLUSTERS_DIR: Final[str] = "clusters"
METRICS_DIR: Final[str] = "metrics"
AUDITS_DIR: Final[str] = "audits"
ASSETS_DIR: Final[str] = "assets"
CREDENTIALS_DIR: Final[str] = "credentials"

# .seo/ subdirs
SEO_BASELINES_DIR: Final[str] = "baselines"
SEO_ARCHIVE_DIR: Final[str] = "archive"
SEO_BACKUPS_DIR: Final[str] = "backups"
SEO_SUMMARIES_DIR: Final[str] = "summaries"
SEO_OBSERVABILITY_DIR: Final[str] = "observability"

# Standard subdirs to create on /init
STANDARD_SUBDIRS: Final[tuple[str, ...]] = (
    SEO_DIR,
    BRAND_DIR,
    RESEARCH_DIR,
    ARTICLES_DIR,
    CLUSTERS_DIR,
    METRICS_DIR,
    AUDITS_DIR,
    ASSETS_DIR,
    CREDENTIALS_DIR,
)

SEO_SUBDIRS: Final[tuple[str, ...]] = (
    SEO_BASELINES_DIR,
    SEO_ARCHIVE_DIR,
    SEO_BACKUPS_DIR,
    SEO_SUMMARIES_DIR,
    SEO_OBSERVABILITY_DIR,
)

AUDITS_SUBDIRS: Final[tuple[str, ...]] = (
    "rank-history",
    "drift-reports",
    "ai-citations",
)

BRAND_SUBDIRS: Final[tuple[str, ...]] = (
    "personas",
    "voice-samples",
)

RESEARCH_SUBDIRS: Final[tuple[str, ...]] = (
    "ai-probes",
)


# ── Validation ────────────────────────────────────────────────────

class InvalidSlugError(ValueError):
    """Slug failed validation — only alphanum + dash + dot allowed."""


def _validate_slug(slug: str) -> None:
    """Site slugs are file-system identifiers; must be safe."""
    if not slug:
        raise InvalidSlugError("Empty slug")
    if not all(c.isalnum() or c in "-._" for c in slug):
        raise InvalidSlugError(
            f"Invalid slug {slug!r}: only alphanumeric, dash, dot, underscore allowed"
        )
    if slug.startswith(".") or slug.endswith(".") or ".." in slug:
        raise InvalidSlugError(f"Invalid slug {slug!r}: cannot start/end with dot or contain '..'")


# ── Path resolvers ─────────────────────────────────────────────────

def projects_root() -> Path:
    """The parent directory for all project archives."""
    return PLUGIN_ROOT / "projects"


def project_root(slug: str) -> Path:
    """The root of a specific project."""
    _validate_slug(slug)
    return projects_root() / slug


def seo_dir(slug: str) -> Path:
    return project_root(slug) / SEO_DIR


def brand_dir(slug: str) -> Path:
    return project_root(slug) / BRAND_DIR


def research_dir(slug: str) -> Path:
    return project_root(slug) / RESEARCH_DIR


def articles_dir(slug: str) -> Path:
    return project_root(slug) / ARTICLES_DIR


def clusters_dir(slug: str) -> Path:
    return project_root(slug) / CLUSTERS_DIR


def metrics_dir(slug: str) -> Path:
    return project_root(slug) / METRICS_DIR


def audits_dir(slug: str) -> Path:
    return project_root(slug) / AUDITS_DIR


def assets_dir(slug: str) -> Path:
    return project_root(slug) / ASSETS_DIR


def credentials_dir(slug: str) -> Path:
    return project_root(slug) / CREDENTIALS_DIR


# ── Specific file paths (the most-frequently used) ─────────────────

def project_yaml_path(slug: str) -> Path:
    return project_root(slug) / "project.yaml"


def internal_links_map_path(slug: str) -> Path:
    return project_root(slug) / "internal-links-map.md"


def known_issues_path(slug: str) -> Path:
    return project_root(slug) / "KNOWN_ISSUES.md"


# .seo/ files
def state_path(slug: str) -> Path:
    return seo_dir(slug) / "state.json"


def change_log_path(slug: str) -> Path:
    return seo_dir(slug) / "change-log.json"


def wp_taxonomy_cache_path(slug: str) -> Path:
    return seo_dir(slug) / "wp-taxonomy-cache.json"


def drift_baseline_db_path(slug: str) -> Path:
    return seo_dir(slug) / SEO_BASELINES_DIR / "drift.sqlite"


# brand/ files
def brand_guideline_path(slug: str) -> Path:
    return brand_dir(slug) / "brand-guideline.yaml"


def brand_config_path(slug: str) -> Path:
    return brand_dir(slug) / "brand-config.json"


def personas_dir(slug: str) -> Path:
    return brand_dir(slug) / "personas"


# research/ files
def business_context_path(slug: str) -> Path:
    return research_dir(slug) / "business-context.md"


def competitors_path(slug: str) -> Path:
    return research_dir(slug) / "competitors.json"


def seo_baseline_path(slug: str) -> Path:
    return research_dir(slug) / "seo-baseline.json"


def target_keywords_path(slug: str) -> Path:
    return research_dir(slug) / "target-keywords.md"


def ai_probes_dir(slug: str) -> Path:
    return research_dir(slug) / "ai-probes"


# audits/ files
def outcomes_path(slug: str) -> Path:
    return audits_dir(slug) / "outcomes.json"


def rank_history_dir(slug: str) -> Path:
    return audits_dir(slug) / "rank-history"


def drift_reports_dir(slug: str) -> Path:
    return audits_dir(slug) / "drift-reports"


def ai_citations_dir(slug: str) -> Path:
    return audits_dir(slug) / "ai-citations"


def refresh_queue_path(slug: str) -> Path:
    return audits_dir(slug) / "refresh-queue.json"


# credentials/ files
def wordpress_credentials_path(slug: str) -> Path:
    return credentials_dir(slug) / "wordpress.json"


# ── Tree creation + validation ─────────────────────────────────────

def ensure_project_tree(slug: str) -> Path:
    """Create the full standard subdirectory tree for a project.

    Idempotent — safe to call on existing project.

    Returns:
        Path to project root.
    """
    root = project_root(slug)
    root.mkdir(parents=True, exist_ok=True)

    # Top-level subdirs
    for d in STANDARD_SUBDIRS:
        (root / d).mkdir(exist_ok=True)

    # .seo/ subdirs
    seo = root / SEO_DIR
    for d in SEO_SUBDIRS:
        (seo / d).mkdir(exist_ok=True)

    # audits/ subdirs
    aud = root / AUDITS_DIR
    for d in AUDITS_SUBDIRS:
        (aud / d).mkdir(exist_ok=True)

    # brand/ subdirs
    brand = root / BRAND_DIR
    for d in BRAND_SUBDIRS:
        (brand / d).mkdir(exist_ok=True)

    # research/ subdirs
    research = root / RESEARCH_DIR
    for d in RESEARCH_SUBDIRS:
        (research / d).mkdir(exist_ok=True)

    # assets/images/
    (root / ASSETS_DIR / "images").mkdir(exist_ok=True)

    # Mark .seo/ + credentials/ + .seo/backups + .seo/archive as gitignored
    _write_gitignore(slug)

    return root


def _write_gitignore(slug: str) -> None:
    """Write a project-local .gitignore covering volatile + sensitive directories."""
    gitignore = project_root(slug) / ".gitignore"
    content = """\
# xuanran-seo project .gitignore
# Sensitive
credentials/

# Runtime state — gitignore the volatile parts; keep state.json + change-log.json tracked
.seo/observability/
.seo/backups/
.seo/archive/
.seo/baselines/*.sqlite
.seo/baselines/*.sqlite-journal

# Build outputs
assets/images/*/tmp/
"""
    if not gitignore.exists():
        gitignore.write_text(content, encoding="utf-8")


def list_projects() -> list[str]:
    """Return all configured projects (alphabetical)."""
    proj_root = projects_root()
    if not proj_root.is_dir():
        return []
    return sorted(
        p.name for p in proj_root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


def is_initialized(slug: str) -> bool:
    """Check if a project has the standard tree."""
    try:
        _validate_slug(slug)
    except InvalidSlugError:
        return False
    root = project_root(slug)
    if not root.is_dir():
        return False
    return all((root / d).is_dir() for d in STANDARD_SUBDIRS)


def health_check(slug: str) -> dict:
    """Run structural integrity check on a project."""
    root = project_root(slug)
    if not root.is_dir():
        return {"slug": slug, "exists": False, "errors": ["Project root does not exist"]}

    errors = []
    warnings = []

    # Required subdirs
    for d in STANDARD_SUBDIRS:
        if not (root / d).is_dir():
            errors.append(f"Missing standard subdir: {d}/")

    # Required files
    if not project_yaml_path(slug).is_file():
        errors.append("Missing project.yaml")

    # Warn-only
    if not internal_links_map_path(slug).is_file():
        warnings.append("internal-links-map.md missing (will be auto-created on first publish)")
    if not brand_guideline_path(slug).is_file():
        warnings.append("brand/brand-guideline.yaml missing (run /brand-guideline)")
    if not seo_baseline_path(slug).is_file():
        warnings.append("research/seo-baseline.json missing (run /init Stage 6-7)")

    return {
        "slug": slug,
        "exists": True,
        "initialized": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "root": str(root),
    }


# ── CLI ────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Project folder structure resolver")
    sub = ap.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="Create standard tree for a new project")
    init.add_argument("slug")

    ls = sub.add_parser("list", help="List all projects")

    chk = sub.add_parser("check", help="Health-check a project")
    chk.add_argument("slug")

    path = sub.add_parser("path", help="Resolve a standard path")
    path.add_argument("slug")
    path.add_argument("location", choices=[
        "root", "seo", "brand", "research", "articles",
        "clusters", "metrics", "audits", "assets", "credentials",
        "outcomes", "state", "change-log", "drift-db", "brand-guideline",
    ])

    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd == "init":
        try:
            root = ensure_project_tree(args.slug)
        except InvalidSlugError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps({"slug": args.slug, "root": str(root), "created": True}, indent=2))
        else:
            print(f"✓ Project tree initialized: {root}")
            print(f"  Subdirs: {', '.join(STANDARD_SUBDIRS)}")
            print(f"  Next: run /init {args.slug} OR /brand-guideline")
        return 0

    if args.cmd == "list":
        projects = list_projects()
        if args.json:
            print(json.dumps(projects, indent=2))
        else:
            print(f"Found {len(projects)} project(s):")
            for p in projects:
                ok = "✓" if is_initialized(p) else "⚠"
                print(f"  {ok} {p}")
        return 0

    if args.cmd == "check":
        h = health_check(args.slug)
        if args.json:
            print(json.dumps(h, indent=2))
        else:
            icon = "✓" if h.get("initialized") else "✗"
            print(f"{icon} {args.slug}: {h['root'] if h.get('exists') else 'NOT FOUND'}")
            for e in h.get("errors", []):
                print(f"  ✗ {e}")
            for w in h.get("warnings", []):
                print(f"  ⚠ {w}")
        return 0 if h.get("initialized") else 1

    if args.cmd == "path":
        resolvers = {
            "root": project_root,
            "seo": seo_dir,
            "brand": brand_dir,
            "research": research_dir,
            "articles": articles_dir,
            "clusters": clusters_dir,
            "metrics": metrics_dir,
            "audits": audits_dir,
            "assets": assets_dir,
            "credentials": credentials_dir,
            "outcomes": outcomes_path,
            "state": state_path,
            "change-log": change_log_path,
            "drift-db": drift_baseline_db_path,
            "brand-guideline": brand_guideline_path,
        }
        try:
            p = resolvers[args.location](args.slug)
        except InvalidSlugError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps({"slug": args.slug, "location": args.location, "path": str(p)}, indent=2))
        else:
            print(p)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
