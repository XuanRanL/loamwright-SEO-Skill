"""scripts/lint/image_placeholder_check.py — Image-placeholder convention lint.

PURPOSE
─────────
Catches the writer-convention drift surfaced by 2026-05-22 audit and confirmed
across the 3 articles published that same day:

  Writers used:    ![alt](images/cover.png "...")
  Publisher wants: [IMAGE-SLOT-cover]

The mismatch ships a broken-image-icon in the body because the publisher's
`_replace_image_placeholders` only swaps `[IMAGE-SLOT-{slot_id}]` and
`placeholder://slot-{slot_id}` patterns — never the markdown-image-with-relative-path
form. Articles 37244 / 37252 / 37254 all needed a post-publish REST PATCH to
substitute the correct WP-uploaded URLs.

This lint runs BEFORE publish, fails the article if it detects the wrong form.

DETECTED FAILURE MODES
──────────────────────
  D1  Local-path markdown image with no WP URL substitution
      Pattern: ![alt](images/X.{png,jpg,jpeg,webp,gif}) or ![alt](./images/X.…)
      → Reader sees the broken image OR (if publisher substituted by ordinal)
        sees the wrong image in the wrong section.

  D2  Image placeholder count mismatch with outline.json::image_slots
      If outline.json declares 3 image slots but draft.md has only 1 placeholder,
      sections 2 and 3 lack inline images on the published post.
      The publisher attaches them to the media library but they don't render
      inline anywhere.
      ⚠ WIRING REALITY (2026-07-06 audit): D2/D3 read the TOP-LEVEL
      outline.image_slots[] array, which no current outline producer emits, and
      the runner stage passes --image-prompts but not --outline — so D2/D3 are
      LEGACY no-ops in the deterministic pipeline. This is NOT a coverage hole:
      D4/D5 check both directions (missing + orphaned placeholders) against
      image-prompts.json, which IS the slot source of truth. D2/D3 are kept for
      callers that still pass a legacy-shaped outline.

  D3  Slot id in markdown does not match any slot declared in outline.json
      e.g. draft uses `[IMAGE-SLOT-checklist]` but outline only declares
      `cover`, `section_1`, `section_2` — publisher cannot route the image
      and the literal text leaks into the body.

  D4  image-prompts.json exists but draft has ZERO [IMAGE-SLOT-*] placeholders.
      (2026-05-25) Writer agents that receive no slot_id context sometimes
      omit all placeholders. The publisher silently uploads media without
      injecting them into the body — 4 images paid for, 0 rendered.

  D5  image-prompts.json slot_ids don't match draft [IMAGE-SLOT-*] names.
      (2026-05-25) Writers invent abbreviated names (hero vs cover,
      comparison vs comparison_lineup). Publisher's exact-match replacement
      finds nothing and strips the orphaned placeholders.

CLI
───
  python -m scripts.lint.image_placeholder_check --draft path/to/draft.md \\
      [--outline path/to/outline.json] [--image-prompts path/to/image-prompts.json] \\
      [--json]

EXIT
────
  0 = no defects
  1 = at least one D1/D2/D3/D4/D5 defect found
  2 = bad arguments
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


_LOCAL_PATH_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\(\s*(?:\./)?images/([^)\s]+\.(?:png|jpg|jpeg|webp|gif))(?:\s+\"[^\"]*\")?\s*\)",
    re.IGNORECASE,
)
_IMAGE_SLOT_TOKEN_RE = re.compile(r"\[IMAGE-SLOT-([a-z0-9_-]+)\]", re.IGNORECASE)


@dataclass
class Defect:
    defect_class: str  # D1 / D2 / D3
    label: str
    line: int | None
    excerpt: str
    detail: str


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _strip_frontmatter(text: str) -> str:
    """Drop YAML frontmatter at top of file so we don't lint inside it."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def _line_of(offset: int, text: str) -> int:
    return text.count("\n", 0, offset) + 1


def detect_D1_local_path_images(body: str) -> list[Defect]:
    """Markdown image syntax with local 'images/X.png' path."""
    defects: list[Defect] = []
    for m in _LOCAL_PATH_IMAGE_RE.finditer(body):
        defects.append(
            Defect(
                defect_class="D1",
                label="local-path markdown image (should be [IMAGE-SLOT-…])",
                line=_line_of(m.start(), body),
                excerpt=m.group(0)[:200],
                detail=(
                    "Writers must use `[IMAGE-SLOT-{slot_id}]` placeholder tokens. "
                    "Markdown images with relative path `images/X.png` are not "
                    "substituted by wp_publisher._replace_image_placeholders() and "
                    "ship as broken image references. See "
                    "references/style/markdown-authoring-conventions.md and the "
                    "image_prompts.json + outline.json contracts."
                ),
            )
        )
    return defects


def detect_D2_count_mismatch(
    body: str, outline: dict | None
) -> list[Defect]:
    """Number of [IMAGE-SLOT-…] tokens in body != number of image_slots in outline."""
    if not outline:
        return []
    image_slots = outline.get("image_slots", [])
    if not isinstance(image_slots, list) or not image_slots:
        return []
    expected_count = len(image_slots)
    tokens_in_body = list(_IMAGE_SLOT_TOKEN_RE.finditer(body))
    actual_count = len(tokens_in_body)
    if actual_count == expected_count:
        return []
    return [
        Defect(
            defect_class="D2",
            label="image placeholder count mismatch with outline.json",
            line=None,
            excerpt=f"{actual_count} found in body / {expected_count} declared in outline.image_slots",
            detail=(
                f"outline.json declares {expected_count} image_slots "
                f"({[s.get('slot_id') for s in image_slots]}) but body has "
                f"{actual_count} [IMAGE-SLOT-…] placeholders. Either reduce the "
                f"declared slots in outline.json or add the missing placeholders "
                f"to draft.md at appropriate points (typically after the H2 "
                f"named in outline.image_slots[*].after_section_index)."
            ),
        )
    ]


def detect_D3_unknown_slot_ids(body: str, outline: dict | None) -> list[Defect]:
    """[IMAGE-SLOT-X] references a slot_id not declared in outline.image_slots."""
    if not outline:
        return []
    declared_slot_ids = {
        s.get("slot_id") for s in outline.get("image_slots", []) if s.get("slot_id")
    }
    if not declared_slot_ids:
        return []
    defects: list[Defect] = []
    for m in _IMAGE_SLOT_TOKEN_RE.finditer(body):
        slot_id = m.group(1)
        if slot_id not in declared_slot_ids:
            defects.append(
                Defect(
                    defect_class="D3",
                    label="unknown image slot id (not in outline.image_slots)",
                    line=_line_of(m.start(), body),
                    excerpt=m.group(0),
                    detail=(
                        f"slot_id '{slot_id}' is not declared in outline.json "
                        f"image_slots. Declared: {sorted(declared_slot_ids)}. "
                        f"Either add it to outline (with after_section_index + "
                        f"subject) or change the placeholder to one of the "
                        f"declared slot_ids."
                    ),
                )
            )
    return defects


def _extract_prompt_slot_ids(image_prompts: list | dict | None) -> set[str]:
    """Extract slot_ids from image-prompts.json (handles multiple shapes).

    Slots marked is_featured=True are uploaded as featured_media only and never
    need an inline [IMAGE-SLOT-*] placeholder (no_inline project policy).  Exclude
    them so D4/D5 checks don't false-fire on those projects.
    """
    # Centralized normalizer handles list AND {prompts:{slot_id:...}} dict, so the
    # D4/D5 placeholder check can never again go blind on a dict-shaped file (2026-06-29).
    from scripts._core.image_prompts import normalize_image_prompts
    prompts = normalize_image_prompts(image_prompts)
    return {
        p.get("slot_id")
        for p in prompts
        if isinstance(p, dict) and p.get("slot_id") and not p.get("is_featured")
    }


def _extract_all_prompt_slot_ids(image_prompts: list | dict | None) -> set[str]:
    """ALL declared slot_ids, INCLUDING is_featured ones (2026-07-01).

    D5's orphan direction must check against the full declared set: a body
    [IMAGE-SLOT-cover] whose prompt entry carries is_featured=true is perfectly
    routable by the publisher — flagging it as "not declared" (the 2026-07-01
    loamdentallocal0701 false D5) forced designers to write is_featured:false on
    covers, which then propagated into images.json and cost post 788 its
    featured_media. The featured-exclusion set above remains correct for D4 and
    for the missing-in-body direction (featured slots never REQUIRE a body token).
    """
    from scripts._core.image_prompts import normalize_image_prompts
    prompts = normalize_image_prompts(image_prompts)
    return {
        p.get("slot_id")
        for p in prompts
        if isinstance(p, dict) and p.get("slot_id")
    }


def detect_D4_zero_placeholders(body: str, prompt_slot_ids: set[str]) -> list[Defect]:
    """image-prompts.json has slots but draft has ZERO placeholders."""
    if not prompt_slot_ids:
        return []
    tokens_in_body = list(_IMAGE_SLOT_TOKEN_RE.finditer(body))
    if tokens_in_body:
        return []
    return [
        Defect(
            defect_class="D4",
            label="draft has ZERO [IMAGE-SLOT-*] placeholders but image-prompts.json declares slots",
            line=None,
            excerpt=f"0 placeholders in body / {len(prompt_slot_ids)} in image-prompts.json",
            detail=(
                f"image-prompts.json declares {len(prompt_slot_ids)} image slots "
                f"({sorted(prompt_slot_ids)}) but the draft body contains zero "
                f"[IMAGE-SLOT-*] placeholders. The publisher will upload all "
                f"images to WordPress media library but none will appear in the "
                f"post body. Fix: insert [IMAGE-SLOT-<slot_id>] at the correct "
                f"position for each slot."
            ),
        )
    ]


def detect_D5_slot_id_name_mismatch(
    body: str,
    prompt_slot_ids: set[str],
    all_slot_ids: set[str] | None = None,
) -> list[Defect]:
    """Draft [IMAGE-SLOT-X] names don't match image-prompts.json slot_ids.

    Orphan direction checks against ``all_slot_ids`` (INCLUDING featured slots,
    2026-07-01) — a declared-but-featured cover token in the body is routable, not
    orphaned. Missing direction keeps the non-featured set: featured slots never
    require a body token.
    """
    if not prompt_slot_ids:
        return []
    body_slot_ids = {m.group(1) for m in _IMAGE_SLOT_TOKEN_RE.finditer(body)}
    if not body_slot_ids:
        return []
    defects: list[Defect] = []
    orphaned_in_body = body_slot_ids - (all_slot_ids or prompt_slot_ids)
    missing_in_body = prompt_slot_ids - body_slot_ids
    for slot_id in sorted(orphaned_in_body):
        m = None
        for m in _IMAGE_SLOT_TOKEN_RE.finditer(body):
            if m.group(1) == slot_id:
                break
        defects.append(
            Defect(
                defect_class="D5",
                label="draft placeholder name not in image-prompts.json",
                line=_line_of(m.start(), body) if m else None,
                excerpt=f"[IMAGE-SLOT-{slot_id}]",
                detail=(
                    f"Draft uses slot_id '{slot_id}' but image-prompts.json only "
                    f"declares: {sorted(prompt_slot_ids)}. The publisher matches "
                    f"by exact slot_id — this placeholder will be silently stripped "
                    f"and no image will appear at this position. Fix: rename the "
                    f"placeholder to match one of the declared slot_ids."
                ),
            )
        )
    for slot_id in sorted(missing_in_body):
        defects.append(
            Defect(
                defect_class="D5",
                label="image-prompts.json slot missing from draft",
                line=None,
                excerpt=f"[IMAGE-SLOT-{slot_id}] expected but absent",
                detail=(
                    f"image-prompts.json declares slot_id '{slot_id}' but no "
                    f"[IMAGE-SLOT-{slot_id}] placeholder exists in the draft body. "
                    f"The image will be uploaded but never rendered inline. Fix: "
                    f"add [IMAGE-SLOT-{slot_id}] at the appropriate position."
                ),
            )
        )
    return defects


def lint_draft(
    draft_path: Path,
    outline_path: Path | None,
    image_prompts_path: Path | None = None,
) -> dict:
    raw = _read_text(draft_path)
    body = _strip_frontmatter(raw)
    outline: dict | None = None
    if outline_path and outline_path.exists():
        outline = json.loads(outline_path.read_text(encoding="utf-8"))

    image_prompts_data: list | dict | None = None
    if image_prompts_path and image_prompts_path.exists():
        image_prompts_data = json.loads(image_prompts_path.read_text(encoding="utf-8"))
    prompt_slot_ids = _extract_prompt_slot_ids(image_prompts_data)
    all_slot_ids = _extract_all_prompt_slot_ids(image_prompts_data)

    defects: list[Defect] = []
    defects.extend(detect_D1_local_path_images(body))
    defects.extend(detect_D2_count_mismatch(body, outline))
    defects.extend(detect_D3_unknown_slot_ids(body, outline))
    defects.extend(detect_D4_zero_placeholders(body, prompt_slot_ids))
    defects.extend(detect_D5_slot_id_name_mismatch(body, prompt_slot_ids, all_slot_ids))

    return {
        "passed": len(defects) == 0,
        "defect_count": len(defects),
        "defects": [asdict(d) for d in defects],
        "leak_classes": sorted({d.defect_class for d in defects}),
        "source_path": str(draft_path),
        "outline_path": str(outline_path) if outline_path else None,
        "image_prompts_path": str(image_prompts_path) if image_prompts_path else None,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Image-placeholder convention lint")
    p.add_argument("--draft", help="path to draft.md (or use --workspace)")
    p.add_argument(
        "--outline",
        help="path to outline.json (recommended — enables D2/D3 checks)",
    )
    p.add_argument(
        "--image-prompts",
        help="path to image-prompts.json (enables D4/D5 checks — "
        "auto-found from workspace if omitted)",
    )
    p.add_argument("--workspace", help="task workspace dir (auto-finds draft+outline+image-prompts)")
    p.add_argument("--json", action="store_true", help="emit JSON report to stdout")
    p.add_argument("--out", help="also write JSON report to this path")
    args = p.parse_args()

    if args.workspace:
        ws = Path(args.workspace)
        draft_path = ws / "draft.md"
        outline_path = ws / "outline.json"
        image_prompts_path = ws / "image-prompts.json"
    else:
        if not args.draft:
            print("--draft or --workspace required", file=sys.stderr)
            return 2
        draft_path = Path(args.draft)
        outline_path = Path(args.outline) if args.outline else None
        image_prompts_path = Path(args.image_prompts) if args.image_prompts else None

    if not draft_path.exists():
        print(f"draft not found: {draft_path}", file=sys.stderr)
        return 2

    if outline_path and not outline_path.exists():
        outline_path = None

    if image_prompts_path and not image_prompts_path.exists():
        image_prompts_path = None

    report = lint_draft(draft_path, outline_path, image_prompts_path)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if report["passed"]:
            print(f"image_placeholder_check: PASS ({draft_path})")
        else:
            print(f"image_placeholder_check: FAIL — {report['defect_count']} defect(s)")
            for d in report["defects"]:
                line_str = f"L{d['line']}" if d["line"] else "—"
                print(f"  [{d['defect_class']}] {line_str}: {d['label']}")
                print(f"      excerpt: {d['excerpt']}")
                print(f"      detail:  {d['detail']}")

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
