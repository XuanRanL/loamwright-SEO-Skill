"""scripts/lint/tags_config_template_check.py — Prevent the tag-description
hidden-template anti-pattern from re-entering any project's tags-config.json.

Added 2026-05-23 per `feedback_no_hidden_template_in_taxonomy_copy.md` and
`feedback_tag_description_must_be_tag_centric.md`. The anti-pattern: a single
`description_template` like "Articles tagged 'X' on Site — generic content
sentence." applied across every organic tag, producing dozens of structurally
identical descriptions. This hurts taxonomy-archive SEO and AI-extractability.

The canonical post-2026-05-23 state: `description_template = null` for every
project's tags-config.json. New tags created by the publisher get an EMPTY
description that a follow-up curated-write pass fills in (using the 3-sentence
tag-centric structure from tags 480W / 640W / 1000W HPS).

Usage:
    python scripts/lint/tags_config_template_check.py [--project SLUG] [--json]

Exits 0 if all project configs pass. Exits 1 if any project has a non-null
description_template OR a description matching the hidden-template pattern.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]

# Patterns that indicate a hidden template was used to generate descriptions.
# These match the antipattern, not a specific phrasing — any project that adopts
# a similar template gets caught.
HIDDEN_TEMPLATE_PATTERNS = [
    re.compile(r"^Articles tagged ['\"].+?['\"] on .+? content covering this topic\.?$", re.IGNORECASE),
    re.compile(r"^Posts under the ['\"].+?['\"] tag\.?$", re.IGNORECASE),
    re.compile(r"^All ['\"].+?['\"] content on .+?\.$", re.IGNORECASE),
    # Generic "X content —" anti-pattern from memory feedback_no_hidden_template_in_taxonomy_copy.md
    re.compile(r"^.+? content — ", re.IGNORECASE),
]


@dataclass
class TagConfigDefect:
    project_slug: str
    field_path: str          # e.g. "policy.auto_create_default_meta.description_template"
    issue: str               # what's wrong
    value: str               # the offending value (truncated)
    fix: str                 # how to fix


def lint_one_config(project_slug: str, config_path: Path) -> list[TagConfigDefect]:
    """Run all checks against one tags-config.json. Returns defect list."""
    defects: list[TagConfigDefect] = []
    if not config_path.exists():
        return defects  # nothing to lint
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        defects.append(TagConfigDefect(
            project_slug=project_slug,
            field_path="(root)",
            issue=f"tags-config.json is not valid JSON: {e}",
            value="",
            fix="Repair JSON syntax.",
        ))
        return defects

    # Check 1: policy.auto_create_default_meta.description_template must be null
    template = (
        config.get("policy", {})
        .get("auto_create_default_meta", {})
        .get("description_template")
    )
    if template is not None and template != "":
        defects.append(TagConfigDefect(
            project_slug=project_slug,
            field_path="policy.auto_create_default_meta.description_template",
            issue="description_template is set to a non-null string — every new auto-created "
                  "tag will inherit the same skeleton sentence (anti-pattern).",
            value=str(template)[:120],
            fix="Set to null. New tags get an empty description; follow-up curated pass fills "
                "them in using the 3-sentence tag-centric structure (see tags 480W / 640W / "
                "1000W HPS for reference).",
        ))

    # Check 2: scan strategic_tags + baseline_tags for descriptions matching the
    # hidden-template patterns
    for list_name in ("strategic_tags", "baseline_tags"):
        for entry in config.get(list_name, []):
            desc = entry.get("description", "") or ""
            if not desc.strip():
                continue
            for pat in HIDDEN_TEMPLATE_PATTERNS:
                if pat.match(desc.strip()):
                    defects.append(TagConfigDefect(
                        project_slug=project_slug,
                        field_path=f"{list_name}[{entry.get('slug') or entry.get('name')}].description",
                        issue="description matches a hidden-template anti-pattern (e.g. "
                              "'Articles tagged X on Site — ...' shape).",
                        value=desc[:120],
                        fix="Rewrite as tag-centric 3-sentence structure. Reference: tags 480W / "
                            "640W / 1000W HPS in project-charlie project. Target 280-400 chars / "
                            "45-58 words.",
                    ))
                    break

    return defects


def find_project_configs(project_filter: str | None = None) -> list[tuple[str, Path]]:
    """Return list of (project_slug, tags-config.json path) tuples."""
    projects_dir = PLUGIN_ROOT / "projects"
    if not projects_dir.exists():
        return []
    out: list[tuple[str, Path]] = []
    for proj in sorted(projects_dir.iterdir()):
        if not proj.is_dir():
            continue
        slug = proj.name
        if project_filter and slug != project_filter:
            continue
        cfg = proj / "tags-config.json"
        if cfg.exists():
            out.append((slug, cfg))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", help="Limit to one project slug")
    ap.add_argument("--json", action="store_true", help="Emit JSON report to stdout")
    args = ap.parse_args()

    configs = find_project_configs(args.project)
    all_defects: list[TagConfigDefect] = []
    for slug, cfg_path in configs:
        all_defects.extend(lint_one_config(slug, cfg_path))

    report = {
        "passed": not all_defects,
        "projects_scanned": [s for s, _ in configs],
        "defect_count": len(all_defects),
        "defects": [asdict(d) for d in all_defects],
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Tags-config template check — {len(configs)} project(s) scanned")
        if not all_defects:
            print(f"  ✓ All {len(configs)} project configs pass.")
        else:
            print(f"  ✗ {len(all_defects)} defect(s) found:")
            for d in all_defects:
                print(f"    [{d.project_slug}] {d.field_path}")
                print(f"      issue: {d.issue}")
                print(f"      value: {d.value}")
                print(f"      fix:   {d.fix}")
    return 0 if not all_defects else 1


if __name__ == "__main__":
    sys.exit(main())
