"""
scripts/lint/keyword_density.py — Keyword density check (primary + secondary).

Target bands:
  - Primary keyword:    0.8% – 1.3% of total body word count
  - Secondary keywords: 0.3% – 0.7% each

Below the band = under-optimized; above = keyword stuffing (Google penalty risk).

Matching is:
  - Case-insensitive
  - Whole-word (won't count "chair" inside "chairman")
  - Plural-aware (chair / chairs both count for "chair")
  - Markdown-stripped (doesn't count keywords inside code blocks or URLs)

Used by:
  - section-drafter self_check (per-section target density)
  - quality-gate-seo (overall article density)
  - meta-builder (verify slug/excerpt contains primary keyword)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scripts.lint._text_utils import count_words, strip_markdown


@dataclass
class KeywordHit:
    keyword: str
    count: int
    density: float           # raw fraction (0.01 = 1%)
    density_pct: float       # as percentage
    target_min: float        # e.g. 0.005
    target_max: float        # e.g. 0.010
    band: str                # "too_low" / "optimal" / "too_high"
    within_band: bool


@dataclass
class DensityReport:
    total_word_count: int
    primary: KeywordHit | None
    secondaries: list[KeywordHit] = field(default_factory=list)
    overall_pass: bool = False
    # v3.38.3 gate semantics (Rule 12 root cure, 2026-07-10). The documented
    # policy has always been asymmetric: under-band is informational (semantic
    # SEO tolerates a sparse exact phrase), over 1.5% is a HARD stuffing veto.
    # But the executor exited 1 on ANY out-of-band result and nothing read the
    # artifact, so the 2026-07-09 batch logged meaningless exit:1 on every
    # legitimately-sparse long-tail phrase while a real >1.5% stuffing case had
    # NO enforcement layer at all. `passed` is the gate flag consumed by
    # run_pipeline._GATE_STAGES + orchestrator._PASS_FLAG_REQUIRED: it is False
    # ONLY on the hard veto (or an empty/unreadable draft).
    hard_veto: bool = False
    passed: bool = True


def _word_pattern(keyword: str) -> re.Pattern[str]:
    """Build a case-insensitive whole-word regex tolerant of plurals.

    Strategy: build alternation of:
      - exact keyword phrase (escaped, word boundaries)
      - keyword + 's' (English plural)
      - keyword + 'es' (regular plural for sibilants)
    For multi-word keywords, only the LAST word gets pluralized.
    """
    parts = keyword.strip().split()
    if not parts:
        raise ValueError("Empty keyword")
    head = " ".join(re.escape(p) for p in parts[:-1])
    last = re.escape(parts[-1])
    pluralized = rf"{last}(?:s|es)?"
    if head:
        full = rf"\b{head}\s+{pluralized}\b"
    else:
        full = rf"\b{pluralized}\b"
    return re.compile(full, re.IGNORECASE)


def count_keyword(text_plain: str, keyword: str) -> int:
    """Count occurrences of keyword in plain text (markdown-stripped)."""
    pattern = _word_pattern(keyword)
    return len(pattern.findall(text_plain))


def analyze(
    text: str,
    primary_keyword: str,
    secondary_keywords: list[str] | None = None,
    *,
    primary_min: float = 0.005,
    primary_max: float = 0.010,
    secondary_min: float = 0.003,
    secondary_max: float = 0.007,
    hard_max: float = 0.015,
) -> DensityReport:
    plain = strip_markdown(text)
    total = count_words(plain, strip_md=False)
    secondary_keywords = secondary_keywords or []

    if total == 0:
        # An empty/unreadable draft is a real failure, not a soft warning.
        return DensityReport(total_word_count=0, primary=None, overall_pass=False,
                             hard_veto=False, passed=False)

    def hit(kw: str, tmin: float, tmax: float) -> KeywordHit:
        c = count_keyword(plain, kw)
        density = c / total if total > 0 else 0
        if density < tmin:
            band = "too_low"
        elif density > tmax:
            band = "too_high"
        else:
            band = "optimal"
        return KeywordHit(
            keyword=kw, count=c, density=round(density, 5),
            density_pct=round(density * 100, 3),
            target_min=tmin, target_max=tmax,
            band=band, within_band=(band == "optimal"),
        )

    primary_hit = hit(primary_keyword, primary_min, primary_max)
    secondary_hits = [hit(kw, secondary_min, secondary_max) for kw in secondary_keywords]

    overall = primary_hit.within_band and all(s.within_band for s in secondary_hits)
    # Hard veto: PRIMARY keyword above the stuffing ceiling only. Secondaries and
    # under-band never hard-veto (Moz 2025 asymmetric-penalty evidence; see
    # skills/seo-blog SKILL.md "Cannot proceed past Optimize unless").
    veto = primary_hit.density > hard_max
    return DensityReport(
        total_word_count=total,
        primary=primary_hit,
        secondaries=secondary_hits,
        overall_pass=overall,
        hard_veto=veto,
        passed=not veto,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Keyword density checker")
    ap.add_argument("file", type=Path)
    ap.add_argument("--primary", required=True, help="Primary keyword")
    ap.add_argument("--secondary", nargs="*", default=[], help="Secondary keywords (space-separated)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--primary-min", type=float, default=0.005)
    ap.add_argument("--primary-max", type=float, default=0.010)
    ap.add_argument("--secondary-min", type=float, default=0.003)
    ap.add_argument("--secondary-max", type=float, default=0.007)
    ap.add_argument("--hard-max", type=float, default=0.015,
                    help="Primary-density HARD stuffing ceiling (fraction). Above this: passed=false + exit 1.")
    ap.add_argument("--out", type=Path, default=None, help="Write JSON output to this file (file-bus)")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    text = args.file.read_text(encoding="utf-8")
    r = analyze(
        text, args.primary, args.secondary,
        primary_min=args.primary_min, primary_max=args.primary_max,
        secondary_min=args.secondary_min, secondary_max=args.secondary_max,
        hard_max=args.hard_max,
    )

    if args.json:
        out = {
            "file": str(args.file),
            "total_word_count": r.total_word_count,
            "primary": asdict(r.primary) if r.primary else None,
            "secondaries": [asdict(s) for s in r.secondaries],
            "overall_pass": r.overall_pass,
            "hard_veto": r.hard_veto,
            "hard_max": args.hard_max,
            "passed": r.passed,
        }
        json_str = json.dumps(out, indent=2, ensure_ascii=False)
        print(json_str)
        if args.out:
            args.out.write_text(json_str, encoding="utf-8")
    else:
        print(f"File: {args.file}")
        print(f"Total words: {r.total_word_count}")
        print()
        if r.primary:
            p = r.primary
            icon = "✓" if p.within_band else "✗"
            print(f"{icon} Primary  '{p.keyword}': {p.count} hits → {p.density_pct}%  ({p.band})")
            print(f"    target: [{p.target_min*100:.1f}%, {p.target_max*100:.1f}%]")
        for s in r.secondaries:
            icon = "✓" if s.within_band else "✗"
            print(f"{icon} Secondary '{s.keyword}': {s.count} → {s.density_pct}%  ({s.band})")
            print(f"    target: [{s.target_min*100:.1f}%, {s.target_max*100:.1f}%]")
        print()
        band_note = "" if r.overall_pass else " (out-of-band = informational; only >hard-max blocks)"
        print(f"Band check: {'PASS' if r.overall_pass else 'WARN'}{band_note}")
        print(f"Gate: {'PASS' if r.passed else 'HARD VETO (primary density above stuffing ceiling)'}")

    # v3.38.3: exit 1 ONLY on the hard veto (or empty draft) — the runner's
    # _GATE_STAGES reads `passed` from the artifact; under-band is a warning.
    return 0 if r.passed else 1


if __name__ == "__main__":
    sys.exit(main())
