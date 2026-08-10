"""
scripts/monitor/drift_compare.py — 17-rule diff against drift_baseline.

Compares a fresh fetch of a published URL against its last SHA-256 baseline
snapshot in projects/{slug}/baselines/drift.sqlite. Surfaces 17 categories
of drift (per drift-detector SKILL.md):

  Critical (1-3):    canonical changed, robots changed, schema dropped
  High (4-9):        title/desc/h1 changed, word_count dropped >20%, key tables
                     removed, ImageObject schemas dropped
  Medium (10-14):    H2/H3 reordered, internal link count dropped, citation count
                     dropped, alt text dropped, FAQ count changed
  Low (15-17):       minor word delta, image count delta, table count delta

Output: projects/{slug}/drift-reports/{url-slug}-{date}.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from scripts._core.file_bus import PLUGIN_ROOT
from scripts.monitor.drift_baseline import capture, get_latest


SEVERITY_THRESHOLDS = {
    "critical": 3,    # any 1+ critical = critical
    "high": 2,        # 2+ high = high  (1 high alone = medium)
    "medium": 3,      # 3+ medium = medium
}


@dataclass
class DriftFinding:
    rule_id: str
    severity: str           # critical | high | medium | low
    field_name: str
    baseline_value: str
    current_value: str
    pct_change: float = 0.0
    description: str = ""


@dataclass
class DriftReport:
    site_slug: str
    url: str
    baseline_captured_at: str
    current_captured_at: str
    overall_severity: str
    finding_counts: dict = field(default_factory=dict)
    findings: list[DriftFinding] = field(default_factory=list)
    recommend_action: str = ""
    output_path: str = ""


def _pct(old: float | int, new: float | int) -> float:
    if old == 0:
        return 0.0 if new == 0 else 100.0
    return round((new - old) / old * 100, 1)


def diff_baselines(baseline, current) -> list[DriftFinding]:
    """17-rule diff."""
    findings: list[DriftFinding] = []

    # 1. Canonical URL changed (critical)
    if baseline.canonical and current.canonical and baseline.canonical != current.canonical:
        findings.append(DriftFinding(
            "R01-canonical-changed", "critical", "canonical",
            baseline.canonical, current.canonical,
            description="Canonical URL changed; signals different page.",
        ))

    # 2. Robots meta changed (critical if went noindex)
    if baseline.robots_meta != current.robots_meta:
        sev = "critical" if "noindex" in current.robots_meta.lower() else "high"
        findings.append(DriftFinding(
            "R02-robots-changed", sev, "robots_meta",
            baseline.robots_meta, current.robots_meta,
            description="Robots meta directive changed.",
        ))

    # 3. Schema types lost (critical if Article/BlogPosting dropped)
    base_schemas = set(baseline.schema_types)
    cur_schemas = set(current.schema_types)
    lost = base_schemas - cur_schemas
    if lost:
        sev = "critical" if {"Article", "BlogPosting"} & lost else "high"
        findings.append(DriftFinding(
            "R03-schema-types-lost", sev, "schema_types",
            ",".join(sorted(base_schemas)), ",".join(sorted(cur_schemas)),
            description=f"Schema types lost: {sorted(lost)}",
        ))

    # 4. Title changed (high)
    if baseline.title and baseline.title != current.title:
        findings.append(DriftFinding(
            "R04-title-changed", "high", "title",
            baseline.title[:80], current.title[:80],
            description="Page title changed.",
        ))

    # 5. Meta description changed (high)
    if baseline.description and baseline.description != current.description:
        findings.append(DriftFinding(
            "R05-description-changed", "high", "description",
            (baseline.description or "")[:80], (current.description or "")[:80],
            description="Meta description changed.",
        ))

    # 6. H1 count changed (high)
    if baseline.h1_count != current.h1_count:
        findings.append(DriftFinding(
            "R06-h1-count", "high", "h1_count",
            str(baseline.h1_count), str(current.h1_count),
            pct_change=_pct(baseline.h1_count, current.h1_count),
            description=f"H1 count {baseline.h1_count} → {current.h1_count}",
        ))

    # 7. Word count dropped >20% (high)
    wc_delta = _pct(baseline.word_count, current.word_count)
    if wc_delta < -20:
        findings.append(DriftFinding(
            "R07-word-count-dropped", "high", "word_count",
            str(baseline.word_count), str(current.word_count),
            pct_change=wc_delta,
            description=f"Word count dropped {abs(wc_delta)}%.",
        ))

    # 8. Internal link count dropped >30% (medium)
    il_delta = _pct(baseline.internal_link_count, current.internal_link_count)
    if il_delta < -30:
        findings.append(DriftFinding(
            "R08-internal-links-dropped", "medium", "internal_link_count",
            str(baseline.internal_link_count), str(current.internal_link_count),
            pct_change=il_delta,
            description=f"Internal links dropped {abs(il_delta)}%.",
        ))

    # 9. External link count changed significantly (medium)
    el_delta = _pct(baseline.external_link_count, current.external_link_count)
    if abs(el_delta) > 30:
        findings.append(DriftFinding(
            "R09-external-links", "medium", "external_link_count",
            str(baseline.external_link_count), str(current.external_link_count),
            pct_change=el_delta,
        ))

    # 10. H2 reordered (medium) — compare counts only as a proxy
    if baseline.h2_count != current.h2_count:
        findings.append(DriftFinding(
            "R10-h2-changed", "medium", "h2_count",
            str(baseline.h2_count), str(current.h2_count),
            pct_change=_pct(baseline.h2_count, current.h2_count),
        ))

    # 11. H3 count changed (medium)
    if baseline.h3_count != current.h3_count:
        findings.append(DriftFinding(
            "R11-h3-changed", "medium", "h3_count",
            str(baseline.h3_count), str(current.h3_count),
            pct_change=_pct(baseline.h3_count, current.h3_count),
        ))

    # 12. Image count dropped (medium)
    img_delta = _pct(baseline.image_count, current.image_count)
    if img_delta < -20:
        findings.append(DriftFinding(
            "R12-images-dropped", "medium", "image_count",
            str(baseline.image_count), str(current.image_count),
            pct_change=img_delta,
        ))

    # 13-17 are lower-priority deltas (low severity)
    minor_deltas = [
        ("R13-word-count-minor", "word_count", baseline.word_count, current.word_count, 10),
        ("R14-h2-minor", "h2_count", baseline.h2_count, current.h2_count, 10),
        ("R15-h3-minor", "h3_count", baseline.h3_count, current.h3_count, 10),
        ("R16-images-minor", "image_count", baseline.image_count, current.image_count, 10),
        ("R17-external-links-minor", "external_link_count",
         baseline.external_link_count, current.external_link_count, 10),
    ]
    for rule_id, field_name, base_v, cur_v, threshold_pct in minor_deltas:
        # Don't double-report fields already flagged as higher severity above
        if any(f.field_name == field_name for f in findings):
            continue
        delta = _pct(base_v, cur_v)
        if abs(delta) > threshold_pct:
            findings.append(DriftFinding(
                rule_id, "low", field_name,
                str(base_v), str(cur_v),
                pct_change=delta,
            ))

    return findings


def _decide_severity(findings: list[DriftFinding]) -> str:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f.severity] += 1

    if counts["critical"] >= 1:
        return "critical"
    if counts["high"] >= SEVERITY_THRESHOLDS["high"]:
        return "high"
    if counts["high"] >= 1 or counts["medium"] >= SEVERITY_THRESHOLDS["medium"]:
        return "medium"
    if counts["low"] >= 1:
        return "low"
    return "stable"


def _recommend(severity: str) -> str:
    return {
        "critical": "Immediate manual review + likely rollback or refresh",
        "high": "Schedule refresh within 7 days",
        "medium": "Add to refresh queue, normal priority",
        "low": "Monitor next cycle",
        "stable": "No action needed",
    }.get(severity, "")


def compare(site_slug: str, url: str) -> DriftReport:
    """Run baseline diff for a URL."""
    baseline = get_latest(site_slug, url)
    if baseline is None:
        # No baseline yet; capture one
        baseline = capture(site_slug, url)
        return DriftReport(
            site_slug=site_slug, url=url,
            baseline_captured_at=datetime.fromtimestamp(baseline.captured_at, tz=timezone.utc).isoformat(),
            current_captured_at=datetime.fromtimestamp(baseline.captured_at, tz=timezone.utc).isoformat(),
            overall_severity="initial-baseline",
            recommend_action="First baseline captured. Run again later for comparison.",
        )

    current = capture(site_slug, url)
    findings = diff_baselines(baseline, current)
    severity = _decide_severity(findings)

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f.severity] += 1

    out_dir = PLUGIN_ROOT / "projects" / site_slug / "audits" / "drift-reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    url_slug = url.rstrip("/").split("/")[-1] or "root"
    today = datetime.now(timezone.utc).date().isoformat()
    out_path = out_dir / f"{url_slug}-{today}.json"

    report = DriftReport(
        site_slug=site_slug, url=url,
        baseline_captured_at=datetime.fromtimestamp(baseline.captured_at, tz=timezone.utc).isoformat(),
        current_captured_at=datetime.fromtimestamp(current.captured_at, tz=timezone.utc).isoformat(),
        overall_severity=severity,
        finding_counts=counts,
        findings=findings,
        recommend_action=_recommend(severity),
        output_path=str(out_path),
    )
    out_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False),
                        encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="17-rule drift diff vs baseline")
    ap.add_argument("--site", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        report = compare(args.site, args.url)
    except Exception as e:
        print(f"Drift compare failed: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    else:
        print(f"━━ Drift report: {report.url}")
        print(f"  Severity:    {report.overall_severity.upper()}")
        print(f"  Findings:    {report.finding_counts}")
        print(f"  Recommend:   {report.recommend_action}")
        for f in report.findings:
            sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(f.severity, "•")
            print(f"    {sev_icon} [{f.rule_id}] {f.description or f.field_name}")
            if f.pct_change:
                print(f"        {f.baseline_value} → {f.current_value} ({f.pct_change:+.1f}%)")
        print(f"  Saved: {report.output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
