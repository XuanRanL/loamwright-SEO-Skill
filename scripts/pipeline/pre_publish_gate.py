#!/usr/bin/env python3
"""Pre-publish artifact gate — HARD BLOCK if mandatory artifacts are missing.

This script runs BEFORE wp_publisher.py and refuses to proceed unless
every required artifact exists and passes validation. This is the
enforcement mechanism that prevents the LLM orchestrator from skipping
quality-critical pipeline stages.

Usage:
    python -m scripts.pipeline.pre_publish_gate --workspace {task_id} [--json]

Exit codes:
    0 = all gates pass, safe to publish
    1 = one or more gates failed, MUST NOT publish
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts._core import file_bus  # tolerant_json_load: self-heals subagent JSON tool-tag leaks
from scripts._core.provenance import PROVENANCE_REQUIRED  # single _generated_by source (v3.41.3)
from scripts._core.review_target import DEFAULT_REVIEW_TARGET, review_target  # ONE reviewer-target resolver (2026-08-17)
from scripts.pipeline import fc_verdict  # ONE verdict classifier for all gates (2026-08-02)

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent


def _ws(task_id: str) -> Path:
    return PLUGIN_ROOT / "memory" / "workspace" / task_id


def _loadj(path: Path):
    """Tolerant JSON load — strips BOM / trailing subagent tool-tags and self-heals.

    Subagent-authored artifacts (fact-check.json, humanizer-report.json, review.json,
    citations.json, quality.json) occasionally carry trailing tool-call wrapper text that
    breaks a strict json.loads. Routing every read through file_bus.tolerant_json_load means
    a leak self-heals here too, not just at the orchestrator verify gate (2026-06-03)."""
    return file_bus.tolerant_json_load(path)


def check_artifact(ws: Path, filename: str, label: str) -> dict:
    path = ws / filename
    if not path.exists():
        return {"gate": label, "status": "FAIL", "reason": f"{filename} does not exist"}
    try:
        data = _loadj(path)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"gate": label, "status": "FAIL", "reason": f"{filename} is not valid JSON: {e}"}
    return {"gate": label, "status": "PASS", "data": data, "path": str(path)}


def check_draft(ws: Path) -> dict:
    draft = ws / "draft.md"
    if not draft.exists():
        return {"gate": "draft", "status": "FAIL", "reason": "draft.md does not exist"}
    content = draft.read_text(encoding="utf-8")
    word_count = len(content.split())
    if word_count < 1000:
        return {"gate": "draft", "status": "FAIL", "reason": f"draft.md is only {word_count} words (minimum 1000)"}
    return {"gate": "draft", "status": "PASS", "word_count": word_count}


def check_images(ws: Path) -> dict:
    images_json = ws / "images.json"
    image_prompts = ws / "image-prompts.json"
    if not images_json.exists() and not image_prompts.exists():
        return {
            "gate": "images",
            "status": "FAIL",
            "reason": "Neither images.json nor image-prompts.json exists. "
                      "Fork B (image pipeline) was never launched. "
                      "Run: python -m scripts.openai.openai_image_pipeline generate --workspace {task_id}",
        }
    if image_prompts.exists() and not images_json.exists():
        return {
            "gate": "images",
            "status": "FAIL",
            "reason": "image-prompts.json exists but images.json does not. "
                      "Image pipeline was designed but never executed.",
        }
    # Every DECLARED slot must have produced an image. Catches a chart that failed
    # to render (bad chart_spec / crashed renderer) or a photo that failed to
    # generate — its slot is absent from images.json and the [IMAGE-SLOT-x]
    # placeholder would otherwise leak into the published body. (v3.13 Q4-3 fix.)
    try:
        # Centralized normalizer: a dict-shaped image-prompts.json previously made
        # `declared` empty and this gate pass VACUOUSLY (article shipped with missing
        # images + green gate). Now every declared slot is seen (2026-06-29).
        from scripts._core.image_prompts import load_image_prompts
        prompts = load_image_prompts(image_prompts)
        imgs = json.loads(images_json.read_text(encoding="utf-8"))
        imgs = imgs if isinstance(imgs, list) else imgs.get("images", [])
        have = {e.get("slot_id") for e in imgs if isinstance(e, dict)}
        declared = [p.get("slot_id") for p in prompts if isinstance(p, dict) and p.get("slot_id")]
        missing = [s for s in declared if s not in have]
        if missing:
            return {
                "gate": "images",
                "status": "FAIL",
                "reason": f"{len(missing)} declared image slot(s) have NO image in images.json: "
                          f"{missing}. A chart failed to render or a photo failed to generate; "
                          "the [IMAGE-SLOT-…] placeholder would leak. Re-run chart-render / the "
                          "image pipeline (check chart-render-result.json errors).",
                "missing_slots": missing,
            }
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        return {"gate": "images", "status": "FAIL", "reason": f"images manifest unreadable: {e}"}
    return {"gate": "images", "status": "PASS"}


def check_image_qa(ws: Path) -> dict:
    """Image visual-QA gate (2026-06-10).

    The image-visual-qa subagent must have run (report exists, provenance valid).
    Policy: accept_with_warning NEVER blocks (draft-first preview catches it);
    but a report claiming 'pass' on a round that still carries an error-severity
    defect is internally inconsistent (fabrication smell) and FAILS.
    """
    report = ws / "image-qa-report.json"
    if not report.exists():
        return {
            "gate": "image_qa", "status": "FAIL",
            "reason": "image-qa-report.json does not exist. The image-visual-qa "
                      "subagent was never dispatched — generated images shipped "
                      "unseen. Dispatch it (stage 'image-visual-qa') before publish.",
        }
    try:
        data = _loadj(report)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"gate": "image_qa", "status": "FAIL",
                "reason": f"image-qa-report.json unreadable: {e}"}
    prov_err = _check_provenance(data, "image-qa-report.json")
    if prov_err:
        return {"gate": "image_qa", "status": "FAIL",
                "reason": f"provenance: {prov_err}"}

    warnings: list[str] = []
    for img in data.get("images", []):
        slot = img.get("slot_id", "?")
        verdict = img.get("final_verdict", "")
        history = img.get("round_history", [])
        last = history[-1] if history else {}
        last_errors = [d for d in last.get("defects", [])
                       if d.get("severity") == "error"]
        if verdict == "pass" and last_errors:
            return {
                "gate": "image_qa", "status": "FAIL",
                "reason": f"inconsistent report: slot '{slot}' final_verdict=pass "
                          f"but last round still has error defect(s) "
                          f"{[d.get('code') for d in last_errors]}. "
                          "Re-dispatch image-visual-qa.",
            }
        if verdict == "accept_with_warning":
            warnings.append(slot)
        elif verdict != "pass":
            return {
                "gate": "image_qa", "status": "FAIL",
                "reason": f"slot '{slot}' has unrecognized final_verdict "
                          f"'{verdict}' (expected pass|accept_with_warning).",
            }
    # Stale-QA guard (2026-07-01): an image regenerated/re-rendered AFTER the QA
    # pass ships unseen (loamdentallocal0701: the click-share chart was re-rendered
    # with new numbers after QA approved the old one). WARN — the operator must
    # re-verify the changed file(s) or re-dispatch image-visual-qa.
    stale: list[str] = []
    try:
        report_mtime = report.stat().st_mtime
        images_json = ws / "images.json"
        if images_json.exists():
            entries = _loadj(images_json)
            if isinstance(entries, dict):
                entries = entries.get("images", [])
            for e in entries if isinstance(entries, list) else []:
                p = Path(str(e.get("path") or ""))
                if p.exists() and p.stat().st_mtime > report_mtime:
                    stale.append(str(e.get("slot_id") or p.name))
    except Exception:
        stale = []  # the guard itself must never break the gate

    if stale:
        return {"gate": "image_qa", "status": "WARN",
                "reason": f"{len(stale)} image file(s) changed AFTER the QA report was "
                          f"written: {stale}. They shipped unseen — re-verify them or "
                          "re-dispatch image-visual-qa.",
                "stale_slots": stale}
    if warnings:
        return {"gate": "image_qa", "status": "WARN",
                "reason": f"{len(warnings)} slot(s) accepted with unresolved "
                          f"warnings after max regen rounds: {warnings}. "
                          "Review them on the draft preview.",
                "slots": warnings}
    return {"gate": "image_qa", "status": "PASS",
            "summary": data.get("summary", {})}


# Per-format markdown-table floors. DERIVED, not duplicated: the floors live in
# scripts/lint/evidence_density_check.py::FORMAT_RULES and this gate reads them.
#
# Until v3.42.4 there were TWO maps — a live one-entry literal here and the full
# table over there — and this comment pointed at the dead one as "where the full
# per-format evidence floors live". Two sources of truth, one of them unreachable,
# with the live one advertising the dead one. A later editor updating FORMAT_RULES
# (v3.42.2 did exactly that) changed nothing that runs. Importing makes the
# advertised source of truth the actual one.
def _tables_min_by_format() -> dict[str, int]:
    from scripts.lint.evidence_density_check import FORMAT_RULES
    default = int(FORMAT_RULES.get("default", {}).get("min_tables", 2))
    return {fmt: int(r["min_tables"]) for fmt, r in FORMAT_RULES.items()
            if fmt != "default" and int(r.get("min_tables", default)) != default}


_TABLES_MIN_BY_FORMAT: dict[str, int] = _tables_min_by_format()


def check_tables(ws: Path) -> dict:
    draft = ws / "draft.md"
    if not draft.exists():
        return {"gate": "tables", "status": "FAIL", "reason": "draft.md missing"}
    content = draft.read_text(encoding="utf-8")
    lines = content.split("\n")
    header_seps = [
        line for line in lines
        if line.strip().startswith("|")
        and "|" in line[1:]
        and set(line.replace("|", "").replace("-", "").replace(" ", "").replace(":", "")) <= {""}
    ]
    actual_tables = len(header_seps)
    fmt = ""
    try:
        fmt = str(json.loads((ws / "angle.json").read_text(encoding="utf-8")).get("format_id") or "")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    required = _TABLES_MIN_BY_FORMAT.get(fmt, 2)
    if actual_tables < required:
        return {
            "gate": "tables",
            "status": "WARN",
            "reason": f"Only {actual_tables} table(s) found. Spec requires >={required} "
                      f"for format '{fmt or 'default'}'. "
                      "chart-generator stage may have been skipped.",
            "table_count": actual_tables,
        }
    return {"gate": "tables", "status": "PASS", "table_count": actual_tables,
            "required": required}


def check_schema(ws: Path) -> dict:
    schema = ws / "schema.json"
    if not schema.exists():
        return {
            "gate": "schema",
            "status": "WARN",
            "reason": "schema.json does not exist. schema-generator stage was skipped. "
                      "No FAQPage/Dataset/HowTo JSON-LD will be injected.",
        }
    return {"gate": "schema", "status": "PASS"}


def check_render_lint(ws: Path) -> dict:
    lint = ws / "render-lint.json"
    if not lint.exists():
        return {
            "gate": "render_lint",
            "status": "FAIL",
            "reason": "render-lint.json does not exist. render_lint.py was never run. "
                      "L1-L9 leak classes unchecked.",
        }
    data = json.loads(lint.read_text(encoding="utf-8"))
    if not data.get("passed", False):
        return {
            "gate": "render_lint",
            "status": "FAIL",
            "reason": f"render_lint found {data.get('defect_count', '?')} defect(s)",
            "defects": data.get("defects", []),
        }
    return {"gate": "render_lint", "status": "PASS"}


def check_citations(ws: Path) -> dict:
    citations = ws / "citations.json"
    if not citations.exists():
        return {"gate": "citations", "status": "FAIL", "reason": "citations.json does not exist"}
    data = _loadj(citations)
    entries = data.get("citations", data.get("refs", data.get("items", [])))
    if isinstance(data, list):
        entries = data
    if len(entries) < 3:
        return {
            "gate": "citations",
            "status": "FAIL",
            "reason": f"Only {len(entries)} citation(s). Minimum 3 required.",
        }
    return {"gate": "citations", "status": "PASS", "count": len(entries)}


def check_meta(ws: Path) -> dict:
    meta = ws / "meta.json"
    if not meta.exists():
        return {"gate": "meta", "status": "FAIL", "reason": "meta.json does not exist"}
    data = json.loads(meta.read_text(encoding="utf-8"))
    missing = []
    for field in ["title", "slug", "seo_title", "meta_description", "focus_keyphrase", "categories"]:
        if not data.get(field):
            missing.append(field)
    if missing:
        return {"gate": "meta", "status": "FAIL", "reason": f"Missing required fields: {missing}"}
    cats = data.get("categories", [])
    # v3.38.3: a single category is a LEGITIMATE outcome, not selector-skip
    # evidence — several projects deliberately run one-primary-category-per-post
    # (loamwright: facets are tags), and category_selector proves it ran by
    # writing category_ids. Only warn when there is real skip evidence:
    # zero categories, or a lone category WITHOUT resolved category_ids.
    if not cats:
        return {"gate": "meta", "status": "WARN",
                "reason": "No categories. category_selector.py may not have run."}
    if len(cats) < 2 and not data.get("category_ids"):
        return {
            "gate": "meta",
            "status": "WARN",
            "reason": (f"Only {len(cats)} category and no category_ids — "
                       f"category_selector.py may not have run."),
        }
    return {"gate": "meta", "status": "PASS"}


def check_image_placeholder_lint(ws: Path) -> dict:
    lint = ws / "image-placeholder-lint.json"
    if not lint.exists():
        return {
            "gate": "image_placeholder",
            "status": "FAIL",
            "reason": "image-placeholder-lint.json does not exist. "
                      "Run: python -m scripts.lint.image_placeholder_check --workspace {task_id} --json",
        }
    data = json.loads(lint.read_text(encoding="utf-8"))
    if not data.get("passed", False):
        defects = data.get("defects", [])
        return {
            "gate": "image_placeholder",
            "status": "FAIL",
            "reason": f"image_placeholder_check found {len(defects)} defect(s): "
                      + "; ".join(d.get("class", "unknown") for d in defects[:3]),
        }
    return {"gate": "image_placeholder", "status": "PASS"}


def check_section_completeness(ws: Path) -> dict:
    lint = ws / "section-completeness.json"
    if not lint.exists():
        outline = ws / "outline.json"
        sections_dir = ws / "sections"
        if outline.exists() and sections_dir.exists():
            outline_data = json.loads(outline.read_text(encoding="utf-8"))
            expected = len(outline_data.get("sections", []))
            actual = len(list(sections_dir.glob("*.md")))
            if actual < expected:
                return {
                    "gate": "section_completeness",
                    "status": "WARN",
                    "reason": f"sections/ has {actual} files but outline declares {expected}. "
                              f"Writer may have silently dropped {expected - actual} section(s).",
                }
        return {"gate": "section_completeness", "status": "PASS"}
    data = json.loads(lint.read_text(encoding="utf-8"))
    if not data.get("passed", False):
        return {
            "gate": "section_completeness",
            "status": "FAIL",
            "reason": f"Missing sections: {data.get('missing_indices', [])}",
        }
    return {"gate": "section_completeness", "status": "PASS"}


def check_keyword_density(ws: Path) -> dict:
    lint = ws / "keyword-density.json"
    if not lint.exists():
        return {
            "gate": "keyword_density",
            "status": "WARN",
            "reason": "keyword-density.json does not exist. keyword_density.py was not run.",
        }
    data = json.loads(lint.read_text(encoding="utf-8"))
    primary_data = data.get("primary") or {}
    primary_pct = primary_data.get("density_pct", data.get("primary_density_pct", 0))
    if primary_pct > 1.5:
        return {
            "gate": "keyword_density",
            "status": "FAIL",
            "reason": f"Primary keyword density {primary_pct:.2f}% exceeds 1.5% hard limit (over-optimization).",
        }
    return {"gate": "keyword_density", "status": "PASS", "density_pct": primary_pct}


def check_stat_grid(ws: Path) -> dict:
    """MANDATORY (v3.39.0): block a publish whose 'By the Numbers' stat cards will shatter.

    The stat grid renders each item's leading **bold** as a large display FIGURE. A value that
    is a phrase rather than a figure ('30% more chlorophyll', 'Notched Izod verdict:') overflows
    its card and, because the pillar wrapper sets word-wrap:break-word, chops MID-WORD -- project-foxtrot
    shipped 'chlorophyll' as 'chloroph / yll'. A 591-post survey (2026-07-14) found 107 of 365
    stat values breaking this way across 8 projects, on mostly-live posts.
    The CSS hardening makes a bad value degrade gracefully; this gate keeps it correct.
    """
    lint = ws / "stat-grid-lint.json"
    if not lint.exists():
        # No stat grid in the article is the common case, but the STAGE must still have run:
        # a missing artifact means stat-grid-check never executed (Rule 12: check the verdict,
        # not merely the artifact -- and here, that the producer ran at all).
        return {"gate": "stat_grid", "status": "FAIL",
                "reason": "stat-grid-lint.json does not exist; the stat-grid-check stage did not run."}
    data = json.loads(lint.read_text(encoding="utf-8"))
    if not data.get("passed", False):
        bad = "; ".join(
            f"{d.get('code')} {d.get('value')!r}" for d in data.get("defects", [])[:4])
        return {"gate": "stat_grid", "status": "FAIL",
                "reason": (f"{len(data.get('defects', []))} stat-card value(s) will break the layout: "
                           f"{bad}. Bold ONLY the number and its unit; move the description into the "
                           f"unbolded label. Re-dispatch visual-designer."),
                "defects": data.get("defects", [])}
    return {"gate": "stat_grid", "status": "PASS",
            "grids": data.get("grids_found", 0),
            "items": data.get("items_checked", 0),
            "warnings": data.get("warnings", [])}


def check_visual_density(ws: Path) -> dict:
    """MANDATORY (2026-07-01): block a wall-of-text publish. FAILs only on the FLOOR (a genuine
    lack of substance components — no table/stat-grid/quotation + below the weighted minimum);
    the visual-designer stage runs right before this and clears the floor for legitimate
    articles, so it rarely fires. Ceiling issues (over-used pull-quotes/callouts) are surfaced
    as advisory warnings, never a block."""
    lint = ws / "visual-density.json"
    if not lint.exists():
        return {"gate": "visual_density", "status": "FAIL",
                "reason": "visual-density.json does not exist; the visual-density-check stage did not run."}
    data = json.loads(lint.read_text(encoding="utf-8"))
    if not data.get("passed", False):
        return {"gate": "visual_density", "status": "FAIL",
                "reason": (f"wall-of-text: weighted score {data.get('weighted_score','?')}, "
                           f"tier_a {data.get('tier_a_count','?')}. "
                           + "; ".join(data.get("defects", []))[:220]
                           + " Re-dispatch visual-designer to add a table / stat block / quotation."),
                "by_type": data.get("by_type", {})}
    return {"gate": "visual_density", "status": "PASS",
            "weighted_score": data.get("weighted_score", 0),
            "warnings": data.get("warnings", []),
            "by_type": data.get("by_type", {})}


# v3.41.3: SHARED with the orchestrator via scripts/_core/provenance — this
# local copy had drifted to 3-of-7 overlap with the orchestrator's (Rule 12).
# Change the contract THERE, never here. (Import lives in the top import block.)
PROVENANCE_REQUIREMENTS = PROVENANCE_REQUIRED


def _check_provenance(data: dict, filename: str) -> str | None:
    allowed = PROVENANCE_REQUIREMENTS.get(filename, [])
    if not allowed:
        return None
    generated_by = data.get("_generated_by", "")
    if not generated_by:
        return (
            f"{filename} is missing _generated_by field. "
            f"This file may have been manually created instead of generated by the "
            f"required subagent ({', '.join(allowed)}). "
            f"Re-dispatch the subagent to produce a legitimate artifact."
        )
    if generated_by not in allowed:
        return (
            f"{filename} _generated_by='{generated_by}' is not in the allowed "
            f"provenance list {allowed}. Re-dispatch the correct subagent."
        )
    return None


def check_fact_check(ws: Path) -> dict:
    fc = ws / "fact-check.json"
    if not fc.exists():
        return {
            "gate": "fact_check",
            "status": "FAIL",
            "reason": "fact-check.json does not exist. The fact-checker subagent was never dispatched. "
                      "This means citation URLs are unverified, claims are unchecked, and product names "
                      "may be fabricated. Dispatch the fact-checker subagent before publishing.",
        }
    data = _loadj(fc)
    prov_err = _check_provenance(data, "fact-check.json")
    if prov_err:
        return {"gate": "fact_check", "status": "FAIL", "reason": prov_err}
    verdict = data.get("verdict", "UNKNOWN")
    # Single shared classifier (2026-08-02 root cure): this gate and the
    # orchestrator content gate previously kept diverging verdict sets
    # (closed-world whitelist here vs open-world denylist there) — Rule 12.
    cls = fc_verdict.classify(verdict)
    if cls == "block":
        return {
            "gate": "fact_check",
            "status": "FAIL",
            "reason": f"fact-check verdict is {verdict}. Fix flagged claims before publishing. "
                      f"Issues: {data.get('claims_flagged', data.get('issues', []))}",
        }
    if cls == "unknown":
        return {
            "gate": "fact_check",
            "status": "FAIL",
            "reason": f"fact-check verdict '{verdict}' is not a recognized verdict — unknown "
                      f"verdicts fail closed. The fact-checker must emit one of: "
                      f"{fc_verdict.CANONICAL_ENUM}.",
        }
    return {"gate": "fact_check", "status": "PASS", "verdict": verdict}


def check_humanizer(ws: Path) -> dict:
    hr = ws / "humanizer-report.json"
    if not hr.exists():
        return {
            "gate": "humanizer",
            "status": "FAIL",
            "reason": "humanizer-report.json does not exist. The humanizer subagent was never dispatched. "
                      "AI-slop patterns (43 tell patterns) are unchecked. Dispatch the humanizer before publishing.",
        }
    data = _loadj(hr)
    prov_err = _check_provenance(data, "humanizer-report.json")
    if prov_err:
        return {"gate": "humanizer", "status": "FAIL", "reason": prov_err}
    slop_score = data.get("ai_slop_score")
    # Humanizer may report ai_slop_score as a structured dict {before, after, threshold}.
    # Unwrap to the post-rewrite scalar the gate compares against.
    if isinstance(slop_score, dict):
        slop_score = slop_score.get("after", slop_score.get("score", slop_score.get("before")))
    if slop_score is None:
        slop_score = data.get("ai_slop_score_after")
    if slop_score is None:
        slop_score = data.get("score_after")
    if slop_score is None:
        return {
            "gate": "humanizer",
            "status": "FAIL",
            "reason": "humanizer-report.json missing ai_slop_score field (tried: ai_slop_score, ai_slop_score_after, score_after). Re-run humanizer.",
        }

    # v3.38.3 freshness cure (Rule 12): the humanizer runs EARLY in optimize;
    # linker / geo / visual-designer / cta-injection all edit the draft AFTER
    # it, so humanizer-report.json can be stale by the time we gate publish.
    # The quality-gates stage re-measures ai_slop on the near-final draft, and
    # quality.json is freshness-enforced vs draft.md by the orchestrator
    # (_FRESHNESS_VS_DRAFT), so when quality.json is NEWER than the humanizer
    # report, its measurement is the truth. The 2026-07-09 gold-filament run
    # hit exactly this: the humanizer reported 16.13, the post-GEO/CTA draft
    # measured 24.25, and this gate read the stale 16.13. Prefer the newer
    # artifact.
    slop_source = "humanizer-report.json"
    qj = ws / "quality.json"
    if qj.exists():
        try:
            if qj.stat().st_mtime >= hr.stat().st_mtime:
                q_slop = (_loadj(qj).get("ai_slop") or {}).get("score")
                if isinstance(q_slop, (int, float)):
                    slop_score = q_slop
                    slop_source = "quality.json (fresher re-measurement)"
        except Exception:
            pass  # unreadable quality.json is check_quality_gates' problem, not ours

    if slop_score >= 20:
        return {
            "gate": "humanizer",
            "status": "FAIL",
            "reason": f"AI-slop score {slop_score} >= 20 threshold (source: {slop_source}). "
                      "Post-humanizer stages likely re-introduced AI tells: re-dispatch the "
                      "humanizer on the CURRENT draft, then re-run quality gates.",
        }
    return {"gate": "humanizer", "status": "PASS", "ai_slop_score": slop_score,
            "ai_slop_source": slop_source}


def check_reviewer(ws: Path) -> dict:
    rv = ws / "review.json"
    if not rv.exists():
        return {
            "gate": "reviewer",
            "status": "FAIL",
            "reason": "review.json does not exist. The independent reviewer subagent was never dispatched. "
                      "No fresh-editor E-E-A-T evaluation. No quality score. Dispatch the reviewer before publishing.",
        }
    data = _loadj(rv)
    prov_err = _check_provenance(data, "review.json")
    if prov_err:
        return {"gate": "reviewer", "status": "FAIL", "reason": prov_err}
    verdict = data.get("verdict", "")
    rejection_verdicts = {"rejected", "REJECTED", "fail", "FAIL", "FIX_REQUIRED"}
    if verdict in rejection_verdicts:
        would_change = data.get("would_change", [])
        return {
            "gate": "reviewer",
            "status": "FAIL",
            "reason": f"Reviewer verdict is '{verdict}'. Would change: {would_change[:3]}",
        }
    score = data.get("score", 0)
    target = _reviewer_target(ws)
    if score < target:
        return {
            "gate": "reviewer",
            "status": "FAIL",
            "reason": f"Review score {score} < target {target} "
                      f"(state.brief.quality_target_score, default 80). Fix issues and re-review.",
        }
    return {"gate": "reviewer", "status": "PASS", "score": score, "target": target}


def _reviewer_target(ws: Path) -> int:
    """The project-facing review threshold: state.brief.quality_target_score.

    2026-07-01: this brief field was previously read by NO code — the SKILL contract
    says `gates.independent_review.score >= state.brief.quality_target_score`, but the
    gate hardcoded 80, so an 84 sailed past an 85-target brief (loamdentallocal0701).
    2026-08-17: resolution now delegates to scripts/_core/review_target.py — the twin
    gates (this one and orchestrator._content_gate_reason) each carried their own
    `or 80` literal while the schema annotated `default: 95`, and a brief author who
    trusted the schema burned six repair rounds against a bar no code enforces.
    """
    try:
        state = json.loads((ws / "state.json").read_text(encoding="utf-8"))
        return review_target(state)
    except Exception:
        return DEFAULT_REVIEW_TARGET


def check_quality_gates(ws: Path) -> dict:
    qj = ws / "quality.json"
    if not qj.exists():
        return {
            "gate": "quality_gates",
            "status": "FAIL",
            "reason": "quality.json does not exist. The 3 automated quality scorers "
                      "(CORE-EEAT, CITE, AI-Slop) were never run. "
                      "Run: python -m scripts.validate.run_quality_gates --workspace {task_id}",
        }
    data = _loadj(qj)
    combined = data.get("combined_verdict", "UNKNOWN")
    all_pass = data.get("all_pass", False)
    override_note = data.get("override_note")

    # Hard CITE/EEAT vetoes always block (fabricated/missing E-E-A-T, broken/deprecated schema,
    # competitor/peer domain cited as a source — COMP01, added 2026-06-20, root CLAUDE.md Rule 8).
    cite_vetoes = [v for v in data.get("cite", {}).get("vetoes", []) if v in ("T03", "T05", "T09", "COMP01")]
    eeat_vetoes = list(data.get("core_eeat", {}).get("vetoes", []))
    hard_vetoes = cite_vetoes + eeat_vetoes

    # Block ONLY on genuinely-failing verdicts or hard vetoes.
    #
    # Rationale (2026-06-03): the old code hard-blocked SHIP_WITH_NOTES, which is produced by
    # run_quality_gates ONLY when CORE-EEAT and CITE both passed (SHIP/FIX, no hard vetoes) and
    # merely the heuristic ai-slop score is borderline (~20). That borderline is already
    # adjudicated TWICE downstream — by check_humanizer (humanizer-report ai_slop_score < 20)
    # and check_reviewer (independent score >= target). Blocking it here was redundant
    # double-jeopardy that forced a manual `override_note` on otherwise-shippable drafts every
    # run. SHIP_WITH_NOTES literally means "shippable, with notes", so we surface it as a WARN.
    blocking_verdicts = {"BLOCKED", "FIX_REQUIRED"}
    if (combined in blocking_verdicts or hard_vetoes) and not override_note:
        return {
            "gate": "quality_gates",
            "status": "FAIL",
            "reason": f"quality.json combined_verdict={combined}, hard_vetoes={hard_vetoes}. "
                      f"CORE-EEAT: {data.get('core_eeat', {}).get('verdict', '?')}, "
                      f"CITE: {data.get('cite', {}).get('verdict', '?')}, "
                      f"AI-Slop: {data.get('ai_slop', {}).get('score', '?')}. "
                      f"This is a substantive failure (bad verdict or hard veto), not a borderline note. "
                      f"Fix the flagged dimension; only add an 'override_note' with justification if you "
                      f"have an out-of-band reason.",
        }
    result = {
        "gate": "quality_gates",
        "status": "PASS" if (combined.startswith("SHIP") and all_pass) else "WARN",
        "combined_verdict": combined,
        "core_eeat_score": data.get("core_eeat", {}).get("score", 0),
        "cite_score": data.get("cite", {}).get("score", 0),
        "ai_slop_score": data.get("ai_slop", {}).get("score", 0),
    }
    if result["status"] == "WARN":
        result["reason"] = (f"{combined} — substantive gates passed; ai-slop is borderline "
                            f"(humanizer + independent reviewer gates adjudicate this separately).")
    return result


def check_citation_inject(ws: Path) -> dict:
    """Verify claim markers were replaced, not just stripped."""
    cir = ws / "citation-inject-result.json"
    if not cir.exists():
        draft = ws / "draft.md"
        if draft.exists():
            import re
            text = draft.read_text(encoding="utf-8")
            markers = re.findall(r"\[claim:[^\]]+\]", text, re.IGNORECASE)
            if markers:
                return {
                    "gate": "citation_inject",
                    "status": "FAIL",
                    "reason": f"citation-inject never ran. {len(markers)} [claim:*] markers remain in draft.md. "
                              f"Run: python -m scripts.build.citation_inject {{task_id}} --json",
                }
            return {
                "gate": "citation_inject",
                "status": "WARN",
                "reason": "citation-inject-result.json missing but no [claim:*] markers in draft. "
                          "Markers may have been stripped without (Author, Year) replacement.",
            }
        return {"gate": "citation_inject", "status": "FAIL", "reason": "draft.md and citation-inject-result.json both missing"}
    data = json.loads(cir.read_text(encoding="utf-8"))
    if data.get("markers_after", 0) > 0:
        # The result file can be STALE: citation-inject ran and left N markers, but a
        # downstream stage (e.g. the geo-auditor) then resolved them in the draft
        # without refreshing this file. The live draft is authoritative — re-scan it
        # rather than trusting the recorded count (the 2026-06-04 ferns gate-stall).
        draft = ws / "draft.md"
        live_markers = []
        if draft.exists():
            import re as _re
            live_markers = _re.findall(
                r"\[claim:[^\]]+\]", draft.read_text(encoding="utf-8"), _re.IGNORECASE)
        if live_markers:
            return {
                "gate": "citation_inject",
                "status": "FAIL",
                "reason": f"{len(live_markers)} claim markers remain in draft.md after citation-inject "
                          f"(e.g. {live_markers[0]}). Run: python -m scripts.build.citation_inject {{task_id}}",
            }
        # Result file was stale; the live draft is clean — pass with a note.
        return {
            "gate": "citation_inject",
            "status": "PASS",
            "note": f"result file recorded markers_after={data.get('markers_after')} but live draft.md is "
                    "marker-free (resolved downstream); trusting the live draft.",
            "replacements_applied": data.get("replacements_applied", 0),
        }
    return {
        "gate": "citation_inject",
        "status": "PASS",
        "replacements_applied": data.get("replacements_applied", 0),
        "markers_stripped": data.get("markers_stripped_no_replacement", 0),
    }


def check_mandatory_sections(ws: Path) -> dict[str, Any]:
    """Enforce the active project's mandatory_sections (project-agnostic).

    Reads projects/{slug}/business-context.json :: mandatory_sections and verifies
    each declared h2_pattern matches an H2 in draft.md. Projects that declare no
    mandatory_sections PASS automatically (format-template defaults apply).

    This is the executor for the "Format-Fit gate" that skills/seo-blog/SKILL.md
    documented but never had as code (Rule-6 violation found 2026-05-27).
    """
    project_slug = ""
    state = ws / "state.json"
    if state.exists():
        try:
            project_slug = json.loads(state.read_text(encoding="utf-8")).get("project_slug", "")
        except Exception:
            pass
    format_id = None
    angle = ws / "angle.json"
    if angle.exists():
        try:
            format_id = json.loads(angle.read_text(encoding="utf-8")).get("format_id")
        except Exception:
            pass
    try:
        from scripts.lint.mandatory_sections_check import check as ms_check
        result = ms_check(ws, project_slug, format_id)
    except Exception as e:
        return {"gate": "mandatory_sections", "status": "WARN",
                "reason": f"mandatory_sections check error (non-blocking): {e}"}
    if not result["passed"]:
        missing = [m["id"] for m in result.get("missing_sections", [])]
        return {
            "gate": "mandatory_sections",
            "status": "FAIL",
            "reason": f"project '{project_slug}' requires sections {missing} but they are "
                      f"absent from draft.md. {result['reason']}",
        }
    return {
        "gate": "mandatory_sections",
        "status": "PASS",
        "checked": result.get("checked_count", 0),
        "project_slug": project_slug,
    }


def check_local_uniqueness(ws: Path) -> dict:
    """MANDATORY-when-local (2026-07-01): Sterling Sky 80/20 anti-doorway gate.
    Non-local articles PASS with a note. Local articles FAIL when the lint
    artifact is missing (the local-uniqueness-check stage never ran — the exact
    Rule 6 gap this closes: the gate was documented since v3.4.0 but the v3.7
    runner migration dropped it, so it had NEVER executed in production) or
    when the composite verdict failed."""
    state = _loadj(ws / "state.json") or {}
    if not bool((state.get("brief") or {}).get("local_mode")):
        return {"gate": "local_uniqueness", "status": "PASS",
                "reason": "not a local article (state.brief.local_mode is falsy)"}
    lint = ws / "local-uniqueness-lint.json"
    if not lint.exists():
        return {"gate": "local_uniqueness", "status": "FAIL",
                "reason": "local_mode=true but local-uniqueness-lint.json does not exist; "
                          "the local-uniqueness-check stage did not run."}
    data = _loadj(lint) or {}
    if data.get("passed") is not True:
        return {"gate": "local_uniqueness", "status": "FAIL",
                "reason": (f"Sterling Sky uniqueness failed: composite "
                           f"{data.get('composite_score', '?')} (verdict "
                           f"{data.get('verdict', '?')}), missing categories: "
                           f"{data.get('missing_categories', [])}. Doorway-page risk — "
                           "strengthen locality-unique content, then re-run the lint.")}
    return {"gate": "local_uniqueness", "status": "PASS",
            "composite_score": data.get("composite_score"),
            "verdict": data.get("verdict"),
            "missing_categories": data.get("missing_categories", [])}


def check_brand_facts(ws: Path) -> dict:
    """MANDATORY-when-company-facts-exist (v3.36.0): first-person company-fact
    consistency. The 2026-07-06 batch fabricated the agency's own tenure 3x in one
    run and one instance shipped into a draft post — writer.md's fabrication red
    line covers EXTERNAL sources only, so self-referential 'experience' numbers
    passed every gate. Projects without business-context.company facts PASS
    (no-op, same opt-in contract as local_uniqueness / cta_module)."""
    state = _loadj(ws / "state.json") or {}
    slug = state.get("project_slug") or ""
    try:
        from scripts.lint.brand_fact_check import load_company_facts
        facts = load_company_facts(slug) if slug else None
    except Exception:  # noqa: BLE001 - the guard itself must never break the gate
        facts = None
    if not facts:
        return {"gate": "brand_facts", "status": "PASS",
                "reason": "project declares no business-context.company facts (no-op)"}
    lint = ws / "brand-fact-lint.json"
    if not lint.exists():
        return {"gate": "brand_facts", "status": "FAIL",
                "reason": "business-context.company facts exist but brand-fact-lint.json "
                          "does not; the brand-fact-check stage did not run."}
    data = _loadj(lint) or {}
    if data.get("passed") is not True:
        v = data.get("violations", [])
        return {"gate": "brand_facts", "status": "FAIL",
                "reason": (f"{len(v)} first-person company-fact violation(s) - e.g. "
                           f"{(v[0].get('detail') if v else '?')} Fix the draft to match "
                           "business-context.company (or drop the number), then re-run "
                           "the brand-fact-check stage.")}
    return {"gate": "brand_facts", "status": "PASS",
            "checked": data.get("checked", {})}


def check_gate_freshness(ws: Path) -> dict:
    """Draft edits AFTER a gate/subagent artifact was written mean that artifact
    scored a draft the reader never sees (loamphxseo0701: the shipped draft was
    11 minutes newer than quality.json).

    Split severity (2026-08-17):
    - fact-check / humanizer-report / quality staleness stays ADVISORY (WARN):
      later optimize stages (linker, visual-designer, cta-injection) legitimately
      edit the draft after those artifacts in the normal stage order.
    - review.json staleness is a FAIL. The independent reviewer is the LAST
      content stage; in the normal order nothing edits draft.md after a passing
      review, and the review-gate repair contract already mandates re-dispatching
      the reviewer after any repair edit (which makes review.json newest again),
      so this cannot deadlock the sanctioned flow. It exists because a real batch
      (post 38418, 2026-08-17) shipped a draft whose review described the
      pre-edit body: a mid-repair edit landed 1 minute after the final review,
      the old severity was WARN, WARN is non-blocking, and a duplicated CTA
      shipped live unreviewed. An unreviewed shipped draft is exactly the
      condition the reviewer gate exists to prevent — the freshness check must
      be able to FAIL for that reason (Rule 14)."""
    draft = ws / "draft.md"
    if not draft.exists():
        return {"gate": "gate_freshness", "status": "PASS", "reason": "no draft.md"}
    stale: list[str] = []
    review_stale = False
    try:
        draft_mtime = draft.stat().st_mtime
        for name in ("fact-check.json", "humanizer-report.json",
                     "review.json", "quality.json"):
            p = ws / name
            if p.exists() and p.stat().st_mtime < draft_mtime:
                stale.append(name)
                if name == "review.json":
                    review_stale = True
    except OSError:
        stale = []  # the guard itself must never break the gate
    if review_stale:
        return {"gate": "gate_freshness", "status": "FAIL",
                "reason": "draft.md is NEWER than review.json — the draft that would ship "
                          "was never reviewed. RE-DISPATCH the independent reviewer for a "
                          "fresh provenance-stamped score of the CURRENT draft, then re-run "
                          f"this gate. (Also stale, advisory: "
                          f"{[s for s in stale if s != 'review.json']})",
                "stale_artifacts": stale}
    if stale:
        return {"gate": "gate_freshness", "status": "WARN",
                "reason": f"draft.md is NEWER than {len(stale)} gate artifact(s): {stale}. "
                          "Post-gate edits shipped unscored — for material edits, re-dispatch "
                          "the stale subagent(s); for surgical fixes, re-run render-lint and "
                          "note the delta.",
                "stale_artifacts": stale}
    return {"gate": "gate_freshness", "status": "PASS"}


def check_cta_module(ws: Path) -> dict:
    """CTA module presence (v3.34). Projects with business-context.json :: cta.enabled
    must ship the designed CTA block(s) — the cta-injection stage wrote them, but a
    later repair loop / subagent edit can strip a block, so the gate re-scans the
    CURRENT draft via the injector's own --check logic (shared classifier), not the
    possibly-stale result artifact. Disabled/no-config projects PASS (no-op)."""
    state_path = ws / "state.json"
    if not state_path.exists():
        return {"gate": "cta_module", "status": "PASS", "reason": "no state.json (skipped)"}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        slug = state.get("project_slug", "")
        from scripts.optimize.cta_injector import inject
        result = inject(ws.name, slug, check_only=True)
    except Exception as e:  # the guard must never crash the gate
        return {"gate": "cta_module", "status": "WARN",
                "reason": f"cta check failed to run (non-blocking): {e}"}
    if not result.get("enabled"):
        return {"gate": "cta_module", "status": "PASS",
                "reason": "project has no cta config / enabled=false"}
    if result.get("passed"):
        return {"gate": "cta_module", "status": "PASS",
                "placements": result.get("placements_applied", [])}
    return {"gate": "cta_module", "status": "FAIL",
            "reason": "; ".join(result.get("errors", [])) or "expected CTA placement missing",
            "placements_applied": result.get("placements_applied", []),
            "placements_requested": result.get("placements_requested", [])}


def check_paa_alignment(ws: Path) -> dict:
    """FAQ<->research.paa alignment (v3.35). Computed FRESH on the current draft
    (not from a possibly-stale artifact) — same live-recheck pattern as
    check_cta_module. No-ops PASS on thin PAA harvests / missing FAQ."""
    try:
        from scripts.lint.paa_alignment_check import check as _paa_check
        r = _paa_check(ws.name)
    except Exception as e:  # the guard must never crash the gate
        return {"gate": "paa_alignment", "status": "WARN",
                "reason": f"paa check failed to run (non-blocking): {e}"}
    if r.get("passed"):
        return {"gate": "paa_alignment", "status": "PASS",
                "alignment_pct": r.get("alignment_pct"),
                "matched": r.get("matched"), "faq_count": r.get("faq_count")}
    return {"gate": "paa_alignment", "status": "FAIL",
            "reason": "; ".join(r.get("notes", [])) or "FAQ<->PAA alignment below contract",
            "unmatched_questions": r.get("unmatched_questions", [])}


def check_locale_spelling(ws: Path) -> dict:
    """Dialect-drift gate (v3.35, localization-pass Mode 1). Computed fresh;
    non-English locales / en-CA / clean drafts PASS."""
    try:
        from scripts.lint.spelling_dialect_check import check_workspace as _locale_check
        r = _locale_check(ws.name)
    except Exception as e:
        return {"gate": "locale_spelling", "status": "WARN",
                "reason": f"locale check failed to run (non-blocking): {e}"}
    if r.get("passed"):
        status = "PASS" if not r.get("warnings") else "WARN"
        return {"gate": "locale_spelling", "status": status,
                "target_dialect": r.get("target_dialect"),
                "drift_count": r.get("drift_count"),
                "reason": "; ".join(r.get("warnings", []))}
    return {"gate": "locale_spelling", "status": "FAIL",
            "reason": "; ".join(r.get("notes", [])) or "systemic dialect drift",
            "drift_words": r.get("drift_words", [])}


MANDATORY_GATES = [
    ("draft", check_draft),
    ("meta", check_meta),
    ("citations", check_citations),
    ("citation_inject", check_citation_inject),
    ("images", check_images),
    ("image_qa", check_image_qa),
    ("render_lint", check_render_lint),
    ("image_placeholder", check_image_placeholder_lint),
    ("mandatory_sections", check_mandatory_sections),
    ("fact_check", check_fact_check),
    ("humanizer", check_humanizer),
    ("reviewer", check_reviewer),
    ("quality_gates", check_quality_gates),
    ("visual_density", check_visual_density),
    ("stat_grid", check_stat_grid),
    ("local_uniqueness", check_local_uniqueness),
    ("brand_facts", check_brand_facts),
    ("cta_module", check_cta_module),
    ("paa_alignment", check_paa_alignment),
    ("locale_spelling", check_locale_spelling),
    # FAIL only when review.json is older than draft.md (unreviewed content);
    # its WARN outcomes stay non-blocking here — only status=="FAIL" flips
    # all_pass. Was in ADVISORY_GATES until 2026-08-17, where run_gate() never
    # read its status and the 38418 replay (edit after review) still exited 0.
    ("gate_freshness", check_gate_freshness),
]

ADVISORY_GATES = [
    ("tables", check_tables),
    ("schema", check_schema),
    ("section_completeness", check_section_completeness),
    ("keyword_density", check_keyword_density),
]


def run_gate(task_id: str) -> dict:
    ws = _ws(task_id)
    if not ws.exists():
        return {"passed": False, "error": f"Workspace {task_id} does not exist"}

    results = []
    all_pass = True

    for label, checker in MANDATORY_GATES:
        result = checker(ws)
        results.append(result)
        if result["status"] == "FAIL":
            all_pass = False

    for label, checker in ADVISORY_GATES:
        result = checker(ws)
        results.append(result)

    return {
        "passed": all_pass,
        "mandatory_pass": all_pass,
        "results": results,
        "fail_count": sum(1 for r in results if r["status"] == "FAIL"),
        "warn_count": sum(1 for r in results if r["status"] == "WARN"),
        "pass_count": sum(1 for r in results if r["status"] == "PASS"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-publish artifact gate")
    parser.add_argument("--workspace", required=True, help="Task ID")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_gate(args.workspace)

    ws = _ws(args.workspace)
    result_path = ws / "pre-publish-gate-result.json"
    result_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for r in report["results"]:
            icon = {"PASS": "OK", "WARN": "!!", "FAIL": "XX"}[r["status"]]
            print(f"  [{icon}] {r['gate']}: {r.get('reason', 'passed')}")
        print()
        if report["passed"]:
            print("  All mandatory gates PASSED. Safe to publish.")
        else:
            print(f"  BLOCKED: {report['fail_count']} mandatory gate(s) failed.")
            print("  Fix the failures above before running wp_publisher.py.")

    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
