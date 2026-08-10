#!/usr/bin/env python3
"""Pre-delivery validation for audit reports.

Checks completeness, score integrity, and report quality before presenting to user.

Usage:
    python -m scripts.audit.validate_audit_report ./seo-audit-example-2026-05-25/ --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_CORE_MODULES = [
    "technical",
    "content",
    "schema",
    "sitemap",
    "performance",
    "visual",
    "geo",
    "sxo",
]


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8-sig")
        return json.loads(text)
    except (json.JSONDecodeError, OSError):
        return None


def validate(audit_dir: Path) -> dict[str, Any]:
    """Validate audit output directory for completeness and integrity.

    Returns dict with: passed (bool), errors (list), warnings (list), checks (dict).
    """
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, bool] = {}

    # Check 1: scores.json exists and is valid
    scores = _load_json(audit_dir / "scores.json")
    checks["scores_json_exists"] = scores is not None
    if not scores:
        errors.append("scores.json missing or invalid")
    else:
        overall = scores.get("overall_score")
        checks["score_in_range"] = isinstance(overall, (int, float)) and 0 <= overall <= 100
        if not checks["score_in_range"]:
            errors.append(f"overall_score out of range: {overall}")

        badge = scores.get("badge")
        checks["badge_valid"] = badge in ("Excellent", "Good", "Needs Improvement", "Poor")
        if not checks["badge_valid"]:
            errors.append(f"Invalid badge: {badge}")

        categories = scores.get("categories", {})
        checks["categories_present"] = len(categories) >= 5
        if not checks["categories_present"]:
            warnings.append(f"Only {len(categories)} categories scored (expected 7)")

        # Verify weight sum ~= 1.0
        total_weight = sum(c.get("weight", 0) for c in categories.values())
        checks["weights_sum_valid"] = 0.95 <= total_weight <= 1.05
        if not checks["weights_sum_valid"]:
            errors.append(f"Category weights sum to {total_weight:.3f} (expected ~1.0)")

    # Check 2: Core modules present
    modules_dir = audit_dir / "modules"
    checks["modules_dir_exists"] = modules_dir.is_dir()
    if modules_dir.is_dir():
        present_modules = [f.stem for f in modules_dir.glob("*.json")]
        missing_core = [m for m in REQUIRED_CORE_MODULES if m not in present_modules]
        checks["all_core_modules_present"] = len(missing_core) == 0
        if missing_core:
            errors.append(f"Missing core modules: {', '.join(missing_core)}")

        # Check each module has valid structure
        for mod_file in modules_dir.glob("*.json"):
            mod_data = _load_json(mod_file)
            if mod_data is None:
                errors.append(f"Module {mod_file.stem}: invalid JSON")
                continue
            if not isinstance(mod_data, dict):
                errors.append(f"Module {mod_file.stem}: not a dict")
                continue
            if "score" not in mod_data:
                errors.append(f"Module {mod_file.stem}: missing 'score' field")
            elif not (0 <= mod_data["score"] <= 100):
                errors.append(f"Module {mod_file.stem}: score {mod_data['score']} out of range")
            if "findings" not in mod_data:
                warnings.append(f"Module {mod_file.stem}: missing 'findings' field")
            elif not isinstance(mod_data["findings"], list):
                errors.append(f"Module {mod_file.stem}: 'findings' is not a list")
    else:
        errors.append("modules/ directory not found")

    # Check 3: crawl-results.json
    crawl = _load_json(audit_dir / "crawl-results.json")
    checks["crawl_results_exists"] = crawl is not None
    if crawl is None:
        warnings.append("crawl-results.json missing")
    elif isinstance(crawl, list) and len(crawl) == 0:
        errors.append("crawl-results.json is empty (0 pages crawled)")

    # Check 4: business-type.json
    biz = _load_json(audit_dir / "business-type.json")
    checks["business_type_exists"] = biz is not None
    if biz is None:
        warnings.append("business-type.json missing")

    # Check 5: No empty module findings (warning only)
    if modules_dir.is_dir():
        for mod_file in modules_dir.glob("*.json"):
            mod_data = _load_json(mod_file)
            if mod_data and isinstance(mod_data, dict):
                findings = mod_data.get("findings", [])
                if len(findings) == 0 and mod_file.stem != "drift":
                    warnings.append(f"Module {mod_file.stem}: zero findings (may indicate incomplete analysis)")

    passed = len(errors) == 0

    return {
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate audit report completeness")
    parser.add_argument("audit_dir", help="Path to audit output directory")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    audit_dir = Path(args.audit_dir).resolve()

    if not audit_dir.is_dir():
        print(f"Error: Not a directory: {audit_dir}", file=sys.stderr)
        sys.exit(1)

    result = validate(audit_dir)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = "✅ PASSED" if result["passed"] else "❌ FAILED"
        print(f"Validation: {status}")
        print(f"  Errors: {result['error_count']}")
        print(f"  Warnings: {result['warning_count']}")
        if result["errors"]:
            print("\nErrors:")
            for e in result["errors"]:
                print(f"  ❌ {e}")
        if result["warnings"]:
            print("\nWarnings:")
            for w in result["warnings"]:
                print(f"  ⚠️  {w}")

    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
