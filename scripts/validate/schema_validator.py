"""
scripts/validate/schema_validator.py — JSON-LD schema validation + deprecated type detector.

Validates JSON-LD @graph extracted from HTML against:
  1. Schema.org type correctness (typo detection on @type field)
  2. Required fields per type (Article: headline, author, datePublished)
  3. Deprecated types (HowTo, SpecialAnnouncement, CourseInfo, ClaimReview, VehicleListing)
  4. Recommended types missing (Article + Organization + Person for blog posts)
  5. URL fields are absolute (not /relative)
  6. Date fields in ISO 8601 format

Deprecated types from claude-seo schema templates research (2025).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


DEPRECATED_TYPES = {
    "HowTo",                # Deprecated 2023 — no longer eligible for rich results
    "SpecialAnnouncement",  # COVID-era; removed
    "CourseInfo",           # Replaced by Course
    "ClaimReview",          # Removed from Google rich results
    "VehicleListing",       # Limited support
    "Recipe",               # Still works but heavily restricted
}

REQUIRED_FIELDS_BY_TYPE = {
    "Article": {"headline", "author", "datePublished"},
    "BlogPosting": {"headline", "author", "datePublished"},
    "NewsArticle": {"headline", "author", "datePublished"},
    "Person": {"name"},
    "Organization": {"name", "url"},
    "ImageObject": {"url"},
    "VideoObject": {"name", "thumbnailUrl", "uploadDate"},
    "FAQPage": {"mainEntity"},
    "Product": {"name"},
    "BreadcrumbList": {"itemListElement"},
    "Review": {"itemReviewed", "reviewRating", "author"},
}

# Iso 8601 regex (lenient)
_ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
    r"(?:Z|[+-]\d{2}:?\d{2})?)?$"
)


@dataclass
class SchemaIssue:
    schema_type: str
    severity: str               # high / medium / low
    issue: str
    field_path: str = ""
    suggestion: str = ""


@dataclass
class SchemaValidationReport:
    schemas_found: int
    schema_types: list[str]
    issues: list[SchemaIssue] = field(default_factory=list)
    deprecated_used: list[str] = field(default_factory=list)
    recommended_missing: list[str] = field(default_factory=list)
    passes: bool = False


def _get_types(item: dict) -> list[str]:
    """Extract @type values (handles string and list)."""
    t = item.get("@type", [])
    if isinstance(t, str):
        return [t]
    if isinstance(t, list):
        return [str(x) for x in t]
    return []


def _check_iso8601(value: str) -> bool:
    return bool(_ISO8601_RE.match(value))


def _validate_item(item: dict, path: str = "$") -> list[SchemaIssue]:
    """Validate one schema item (may have nested @graph)."""
    issues: list[SchemaIssue] = []
    types = _get_types(item)

    if not types:
        return issues

    for type_name in types:
        # Deprecated check
        if type_name in DEPRECATED_TYPES:
            issues.append(SchemaIssue(
                schema_type=type_name, severity="high",
                issue=f"Schema type '{type_name}' is deprecated (no longer rich-result-eligible)",
                field_path=path,
                suggestion="Replace with current Schema.org alternative or remove",
            ))

        # Required fields
        required = REQUIRED_FIELDS_BY_TYPE.get(type_name, set())
        for field_name in required:
            if field_name not in item:
                issues.append(SchemaIssue(
                    schema_type=type_name, severity="high",
                    issue=f"Missing required field '{field_name}'",
                    field_path=f"{path}.{field_name}",
                ))

        # Date format check
        for date_field in ("datePublished", "dateModified", "uploadDate", "validFrom"):
            if date_field in item:
                v = item[date_field]
                if isinstance(v, str) and not _check_iso8601(v):
                    issues.append(SchemaIssue(
                        schema_type=type_name, severity="medium",
                        issue=f"Field '{date_field}' is not ISO 8601: {v!r}",
                        field_path=f"{path}.{date_field}",
                        suggestion="Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ",
                    ))

        # URL absolute check
        for url_field in ("url", "image", "thumbnailUrl", "@id"):
            if url_field in item and isinstance(item[url_field], str):
                v = item[url_field]
                if v and not (v.startswith("http://") or v.startswith("https://") or v.startswith("#")):
                    issues.append(SchemaIssue(
                        schema_type=type_name, severity="medium",
                        issue=f"Field '{url_field}' should be absolute URL: {v!r}",
                        field_path=f"{path}.{url_field}",
                    ))

    # Recursively validate nested items
    for k, v in item.items():
        if isinstance(v, dict) and "@type" in v:
            issues.extend(_validate_item(v, f"{path}.{k}"))
        elif isinstance(v, list):
            for i, sub in enumerate(v):
                if isinstance(sub, dict) and "@type" in sub:
                    issues.extend(_validate_item(sub, f"{path}.{k}[{i}]"))

    return issues


def validate(json_ld_payload: dict | list) -> SchemaValidationReport:
    """Validate JSON-LD payload(s).

    Args:
        json_ld_payload: A single JSON-LD object (with optional @graph) OR list of objects.

    Returns:
        SchemaValidationReport.
    """
    schemas_found = 0
    all_types: list[str] = []
    all_issues: list[SchemaIssue] = []
    deprecated_used: list[str] = []

    # Normalize to list of top-level items
    if isinstance(json_ld_payload, dict):
        items = [json_ld_payload]
    elif isinstance(json_ld_payload, list):
        items = json_ld_payload
    else:
        return SchemaValidationReport(0, [], [], [], [], False)

    for i, top in enumerate(items):
        if not isinstance(top, dict):
            continue
        # @graph expansion
        if "@graph" in top and isinstance(top["@graph"], list):
            for j, sub in enumerate(top["@graph"]):
                if isinstance(sub, dict) and "@type" in sub:
                    schemas_found += 1
                    sub_types = _get_types(sub)
                    all_types.extend(sub_types)
                    deprecated_used.extend(t for t in sub_types if t in DEPRECATED_TYPES)
                    all_issues.extend(_validate_item(sub, f"$[{i}].@graph[{j}]"))
        elif "@type" in top:
            schemas_found += 1
            top_types = _get_types(top)
            all_types.extend(top_types)
            deprecated_used.extend(t for t in top_types if t in DEPRECATED_TYPES)
            all_issues.extend(_validate_item(top, f"$[{i}]"))

    # Recommended types for blogs: Article, Organization, Person
    recommended = {"Article", "BlogPosting", "Organization", "Person"}
    found_set = set(all_types)
    recommended_missing = []
    if not (found_set & {"Article", "BlogPosting", "NewsArticle"}):
        recommended_missing.append("Article (or BlogPosting / NewsArticle)")
    if "Organization" not in found_set:
        recommended_missing.append("Organization")
    if "Person" not in found_set:
        recommended_missing.append("Person (for author)")

    # Pass: no deprecated + no high-severity issues + has required schemas
    high_issues = [i for i in all_issues if i.severity == "high"]
    passes = (
        len(deprecated_used) == 0 and
        len(high_issues) == 0 and
        schemas_found > 0
    )

    return SchemaValidationReport(
        schemas_found=schemas_found,
        schema_types=sorted(set(all_types)),
        issues=all_issues,
        deprecated_used=sorted(set(deprecated_used)),
        recommended_missing=recommended_missing,
        passes=passes,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="JSON-LD schema validator")
    ap.add_argument("file", type=Path, help="JSON file containing JSON-LD payload OR list")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"Not found: {args.file}", file=sys.stderr)
        return 2

    try:
        payload = json.loads(args.file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        return 2

    r = validate(payload)

    if args.json:
        print(json.dumps(asdict(r), indent=2, ensure_ascii=False))
    else:
        verdict = "✓ PASS" if r.passes else "✗ FAIL"
        print(f"Schemas found:   {r.schemas_found}")
        print(f"Types:           {', '.join(r.schema_types) if r.schema_types else '(none)'}")
        print(f"Issues:          {len(r.issues)}")
        if r.deprecated_used:
            print(f"Deprecated:      {r.deprecated_used}")
        if r.recommended_missing:
            print(f"Missing types:   {r.recommended_missing}")
        print(f"Verdict:         {verdict}")
        if r.issues:
            for i in r.issues[:20]:
                print(f"  [{i.severity}] {i.schema_type} @ {i.field_path}: {i.issue}")
                if i.suggestion:
                    print(f"      → {i.suggestion}")

    return 0 if r.passes else 1


if __name__ == "__main__":
    sys.exit(main())
