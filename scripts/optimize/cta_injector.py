#!/usr/bin/env python3
"""CTA module injector — deterministic executor for the article CTA 板块 (v3.34, 2026-07-04).

Root cure for the third Rule-6 offense: `subskills/optimize/cta-placement/SKILL.md`
documented a CTA-placement behavior since v5.0 but NO executor existed and no
orchestrator stage dispatched it — no production article ever received a designed
CTA module (audit 2026-07-04). This script IS the executor, wired as the mandatory
`cta-injection` stage in scripts/pipeline/orchestrator.py.

What it does
------------
Reads `projects/{slug}/business-context.json :: cta` and injects up to two
NATIVE-MARKDOWN CTA blocks into workspace draft.md:

  * placement "mid" — after the content section containing the ~35% word mark
    (never above the fold, never inside a structural section)
  * placement "end" — immediately before `## Further Reading` / `## References`
    (the BOFU slot; AI-referral visitors convert 6-9x organic, so the cited
    article's bottom is the highest-leverage conversion position)

Each block is `### {heading}` + ONE paragraph. For b2b-services CTAs the
paragraph carries at least one markdown link (the conversion element). For
ecommerce CTAs (v3.38.0) the block may instead carry a WooCommerce products
shortcode, copied VERBATIM from cta-brief.json :: resolved_products.shortcode,
placed on its own blank-line-separated line after the paragraph so WordPress
expands it into a product grid — there the grid is the conversion element and
the markdown-link requirement is waived. The heading is classified by
scripts/_core/component_headings (component id "cta"), so the publisher
auto-tags the sibling <p> with class="xr-cta-box" and the project's generated
article CSS styles it as a conversion card. The component is deliberately
EXCLUDED from the visual-density floor (promo is not substance).

Copy discipline
---------------
- Variants rotate deterministically by task_id (no two consecutive articles ship
  identical copy — the no-hidden-templates rule).
- Em-dashes are sanitized to commas (component em-dash count must be 0) and
  ASCII apostrophes to U+2019 (Cloudflare OWASP 942100 blocks ASCII ' on some
  project WAFs).
- No UTM parameters on internal links: UTM on same-domain links resets GA4
  session attribution (self-referral) — the old cta-placement SKILL's "add UTM"
  advice was an analytics anti-pattern and is intentionally dropped.

Config contract (business-context.json)
---------------------------------------
"cta": {
  "enabled": true,
  "placements": ["mid"],                  // any of "mid", "end"; default mid (v3.41.5)
  "heading": "Your next step",            // MUST classify as component id "cta"
  "variants": {
    "mid": [{"id": "...", "text": "one paragraph with a [link](url)"}],
    "end": [{"id": "...", "text": "..."}]
  },
  "target_url": "https://example.com/contact/"   // used by verify_post check 29
}
Absent block or enabled=false → full no-op (backward compatible), the stage still
writes its evidence artifact with passed=true.

Repairing an already-injected CTA (v3.38.3, sanctioned path)
-------------------------------------------------------------
Injection is IDEMPOTENT by skin-heading detection: if a cta-class heading is
already present in draft.md, the placement is skipped ("already present").
This means editing cta-draft.json AFTER injection and re-running the injector
is a NO-OP — the 2026-07-09 loamwright batch hit this repairing a CTA stat and
had to hand-edit draft.md (drift risk between cta-draft.json and the draft).
The sanctioned repair flow is:
  1. fix cta-draft.json (keep the registered heading),
  2. DELETE the stale injected block from draft.md (the `### {heading}` line +
     its single paragraph, + shortcode line if ecommerce),
  3. re-run the injector — with the heading gone, idempotency no longer
     triggers and the block re-injects fresh from cta-draft.json.
Never leave draft.md and cta-draft.json disagreeing: verify_post check 29 and
the cta-tone/diversity gates all read the DRAFT.

Usage:
    python -m scripts.optimize.cta_injector --task-id {tid} --project-slug {slug} --json
    python -m scripts.optimize.cta_injector --task-id {tid} --project-slug {slug} --check --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts._core.component_headings import classify_heading
from scripts._core.heading_anchor import ANCHOR_FRAGMENT

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
WS_ROOT = PLUGIN_ROOT / "memory" / "workspace"

RESULT_FILENAME = "cta-injection-result.json"

# H2/H3 heading line, tolerating a trailing {#anchor}. re.M is load-bearing:
# every consumer runs finditer over the whole multi-line body.
_HEADING_RE = re.compile(
    r"^(#{2,3})\s+(.+?)\s*(" + ANCHOR_FRAGMENT + r")?\s*$", re.M)
# Structural H2s that must never receive the mid CTA (mandatory sections + the
# References tail). Component headings (TL;DR / By the Numbers / Glossary / ...)
# are excluded via classify_heading, so they don't need to be listed here.
_STRUCTURAL_H2_RE = re.compile(
    r"^(abstract|key takeaways|table of contents|frequently asked questions|faq|"
    r"common questions|conclusion|final verdict|the bottom line|references|"
    r"further reading)\b",
    re.IGNORECASE,
)
_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)\s]+)[^)]*\)")
_MID_MARK = 0.35  # insert after the content section containing this word-mark

# Strict shape gate for an LLM-draft block's "shortcode" field (Finding 2,
# v3.38.1 security fix). cta-draft.json is LLM-authored and untrusted — before
# this gate, ANY non-empty string in "shortcode" was emitted verbatim into
# draft.md AND waived the markdown-link requirement, so a hallucinated or
# injected value (`<script>alert(1)</script>`, `[gallery ids=1,2,3]`) shipped
# straight to the published page. Only the exact quote-less WooCommerce
# `[products ...]` shape that cta_brief_builder.py actually emits (since Task
# 4's unquoted-attribute root cure — quoted attrs break WordPress's own
# shortcode_parse_atts()) is accepted; anything else is treated as no
# shortcode at all. Attribute values allow `_` (WooCommerce's own
# `orderby=menu_order` uses it) alongside the slug-safe `[a-z0-9%-]` charset;
# quotes, angle brackets, and any other punctuation are refused outright.
_SAFE_PRODUCTS_SHORTCODE_RE = re.compile(
    r"^\[products(?:\s+[a-z_]+=[a-z0-9_,%-]+)*\]$"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_cta_config(project_slug: str) -> dict[str, Any] | None:
    bc_path = PLUGIN_ROOT / "projects" / project_slug / "business-context.json"
    if not bc_path.exists():
        return None
    try:
        bc = json.loads(bc_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    cta = bc.get("cta")
    return cta if isinstance(cta, dict) else None


def _load_cta_draft(ws: Path) -> dict[str, Any] | None:
    p = ws / "cta-draft.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or data.get("_generated_by") != "cta-writer-subagent":
        return None
    return data


def sanitize_copy(text: str) -> str:
    """Enforce component copy rules without rewriting meaning.

    - em-dash (U+2014) / en-dash-as-separator → comma (component em-dash count is 0)
    - ASCII apostrophe → U+2019 (project-charlie-class CF WAF blocks ASCII ' — OWASP 942100)
    - curly DOUBLE quotes → ASCII " (v3.41.3: nothing needs them, and they were
      one of the two P17 sources in the 2026-07-19 ai_slop deadlock; the
      apostrophe curl above stays because the WAF bypass depends on it —
      ai_tells_detector now suppresses P17 inside CTA extents instead)
    - collapse doubled whitespace introduced by the replacements
    """
    text = re.sub(r"\s*—\s*", ", ", text)
    text = text.replace("'", "’")
    text = text.replace("“", '"').replace("”", '"')
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _split_frontmatter(content: str) -> tuple[str, str]:
    """Return (frontmatter_including_fences, body). Frontmatter may be absent."""
    if content.startswith("---"):
        end = content.find("\n---\n", 3)
        if end > 0:
            return content[: end + 5], content[end + 5:]
    return "", content


def _scan_existing_cta(body: str) -> list[dict[str, Any]]:
    """Find already-present CTA blocks (idempotency + --check). A CTA block is an
    H2/H3 whose text classifies as ANY CTA component id ('cta', 'cta_quiet',
    'cta_banner' — the 3 visual skins split out in v3.38.0 Task 2).

    ROOT CURE (2026-07-08, found live on the loamwright weekly digest): this
    used to test `== "cta"` exactly. When the cta-writer picked a quiet/banner
    skin heading (e.g. "Let us make this the last audit you need" →
    classifies as "cta_banner"), the existing block was invisible to this scan,
    so (a) a pipeline re-invoke after a downstream gate failure re-injected a
    DUPLICATE CTA into the draft/post, and (b) `placements_applied` stayed []
    (line ~499 uses the same classification), which made verify_post check 29
    silently skip — one Rule-11 fan-out miss, three symptoms."""
    found = []
    for m in _HEADING_RE.finditer(body):
        comp = classify_heading(m.group(2))
        if comp is not None and comp.startswith("cta"):
            found.append({"heading": m.group(2), "offset": m.start()})
    return found


def _content_duplicate_errors(body: str, resolved: dict[str, tuple[str, str, str]]) -> list[str]:
    """CONTENT-IDENTITY duplicate scan — the second idempotency layer (2026-08-17).

    The first layer (_scan_existing_cta, heading classification) has a structural
    blind spot the 2026-07-08 cure could not close: a block whose heading was
    hand-renamed to something that classifies as NO component at all is invisible
    to it. Found live on a real batch (post 38418): a reviewer would-change
    proposed renaming the injected "One more thing" H3, an operator executed the
    rename mid-repair, and the driver's re-run then injected a SECOND identical
    paragraph + [products] shortcode — every downstream check counted only
    classified/token-tagged blocks, so the live draft shipped with the same CTA
    twice, one styled, one bare.

    This layer keys on the CONTENT (the sanitized paragraph text and the verbatim
    shortcode line), which a heading rename cannot hide:
    - >1 copy of a placement's text/shortcode in the body → duplicate already
      shipped; fail loudly with the repair path.
    - >=1 copy while heading-classification says the placement is ABSENT → an
      unregistered (renamed) copy exists; injecting would create the duplicate,
      so the injection is refused and the gate fails instead.
    """
    errs: list[str] = []
    for placement, (_heading, raw_text, shortcode) in resolved.items():
        text = sanitize_copy(raw_text).strip()
        n_text = body.count(text) if text else 0
        n_sc = body.count(shortcode.strip()) if shortcode and shortcode.strip() else 0
        if n_text > 1 or n_sc > 1:
            errs.append(
                f"placement '{placement}': CTA content appears {max(n_text, n_sc)}× in the "
                f"draft (text×{n_text}, shortcode×{n_sc}) — a duplicate CTA block exists, "
                f"almost certainly one copy under a hand-renamed heading the classifier "
                f"cannot see. Sanctioned repair: DELETE the copy whose heading is not the "
                f"registered cta-draft.json heading (heading + paragraph + shortcode "
                f"line), keep the registered block, then re-run this injector."
            )
    return errs


def _classify_existing_placements(body: str) -> set[str]:
    """Map existing CTA blocks to 'mid' / 'end' by their position relative to the
    References/Further Reading tail (before tail-start = mid, inside tail zone = end)."""
    existing = _scan_existing_cta(body)
    if not existing:
        return set()
    tail = _find_tail_offset(body)
    placements: set[str] = set()
    for e in existing:
        # "end" = the CTA sits within 2 sections of the tail; approximate by: no
        # content H2 between the CTA and the tail heading.
        between = body[e["offset"]: tail if tail is not None else len(body)]
        h2s_between = [
            m for m in _HEADING_RE.finditer(between)
            if m.start() > 0 and len(m.group(1)) == 2
        ]
        if tail is not None and not h2s_between:
            placements.add("end")
        else:
            placements.add("mid")
    return placements


def _find_tail_offset(body: str) -> int | None:
    """Character offset of the `## Further Reading` or `## References` H2 line
    (whichever comes first) — the insertion anchor for the 'end' placement."""
    best: int | None = None
    for m in _HEADING_RE.finditer(body):
        if len(m.group(1)) != 2:
            continue
        text = m.group(2).strip().lower()
        if text.startswith("further reading") or text.startswith("references"):
            if best is None or m.start() < best:
                best = m.start()
    return best


def _content_sections(body: str) -> list[dict[str, Any]]:
    """Content H2 sections eligible to host the mid CTA: not structural, not a
    component heading. Returns [{start, end, words}] in document order (end =
    offset where the NEXT H2 begins, i.e. the insertion point 'after this section')."""
    h2s = [m for m in _HEADING_RE.finditer(body) if len(m.group(1)) == 2]
    sections: list[dict[str, Any]] = []
    for i, m in enumerate(h2s):
        end = h2s[i + 1].start() if i + 1 < len(h2s) else len(body)
        text = m.group(2).strip()
        structural = bool(_STRUCTURAL_H2_RE.match(text)) or classify_heading(text) is not None
        sections.append({
            "heading": text,
            "start": m.start(),
            "end": end,
            "words": len(body[m.start():end].split()),
            "structural": structural,
        })
    return [s for s in sections if not s["structural"]]


def _pick_variant(variants: list[dict[str, Any]], task_id: str, placement: str) -> dict[str, Any]:
    """Deterministic per-task rotation (stable across re-runs, varies across articles)."""
    digest = hashlib.md5(f"{task_id}:{placement}".encode("utf-8")).hexdigest()
    return variants[int(digest, 16) % len(variants)]


def _build_block(heading: str, text: str, shortcode: str | None = None) -> str:
    """Emit the CTA block. When `shortcode` is present and non-empty (the
    ecommerce path), it is placed on its OWN blank-line-separated line after the
    intro paragraph so WordPress expands it into a product grid — a shortcode
    glued onto the paragraph would be swallowed into that <p> and never run.
    The shortcode is written VERBATIM (never sanitized): it carries no
    apostrophes/em-dashes by construction, and sanitize_copy is for prose only."""
    if shortcode:
        return f"### {heading}\n\n{text}\n\n{shortcode}\n"
    return f"### {heading}\n\n{text}\n"


def _insert_at(body: str, offset: int, block: str) -> str:
    """Insert `block` at `offset`, normalizing blank-line separation on both sides."""
    before, after = body[:offset].rstrip("\n"), body[offset:].lstrip("\n")
    return f"{before}\n\n{block}\n{after}"


def _validate_variant(v: dict[str, Any], *, has_shortcode: bool = False) -> str | None:
    """Return an error string, or None when the variant is usable.

    The markdown-link requirement is WAIVED when the block carries a WooCommerce
    products shortcode (has_shortcode=True): the rendered product grid IS the
    conversion element, so the intro paragraph does not need its own link.
    Blocks WITHOUT a shortcode keep the requirement — a CTA with neither a link
    nor a grid converts nothing."""
    text = str(v.get("text", "")).strip()
    if not text:
        return f"variant '{v.get('id', '?')}' has empty text"
    if "\n\n" in text:
        return f"variant '{v.get('id', '?')}' must be a single paragraph (no blank lines)"
    if not has_shortcode and not _LINK_RE.search(text):
        return f"variant '{v.get('id', '?')}' has no markdown link — a CTA without a link converts nothing"
    return None


def inject(task_id: str, project_slug: str, *, check_only: bool = False) -> dict[str, Any]:
    ws = WS_ROOT / task_id
    result: dict[str, Any] = {
        "passed": True,
        "enabled": False,
        "task_id": task_id,
        "project_slug": project_slug,
        "placements_requested": [],
        "placements_applied": [],
        "newly_injected": [],
        "skipped": [],
        "variants_used": {},
        "target_url": None,
        "draft_source": "static",
        "warnings": [],
        "errors": [],
        "check_only": check_only,
        "_generated_by": "cta-injector",
        "generated_at": _now_iso(),
    }

    cfg = _load_cta_config(project_slug)
    if not cfg or cfg.get("enabled") is not True:
        result["skipped"].append({"placement": "*", "reason": "no cta config or enabled=false (no-op)"})
        return result

    result["enabled"] = True
    static_heading = str(cfg.get("heading", "")).strip()
    # DEFAULT = ["mid"] (v3.41.5, operator decision 2026-07-24): the product grid +
    # CTA belong in the FRONT-MIDDLE of the article (after the content section at
    # the ~35% word mark), not at the end. The old ["end"] fallback, combined with
    # /init prescribing "end (default)" and "reserve mid for lead-gen sites",
    # propagated end-only into 11 of 12 project configs — a skill-level default
    # error that presented as a per-project choice. "end" remains a supported
    # VALUE for backward compatibility, but no project or format rule uses it:
    # the last exception (weekly-digest) was retired 2026-07-25 and the fleet
    # test fails on any config that reintroduces it.
    placements = [p for p in cfg.get("placements", ["mid"]) if p in ("mid", "end")]

    # Format-aware placement override (v3.35.1): a mid-article conversion card
    # between the stories of a weekly-digest roundup reads as an ad break, not a
    # module. cta.format_rules = {format_id: [placements]} narrows placements per
    # article format; the article's format_id comes from angle.json (all pipeline
    # tasks have one, digests included).
    format_id = None
    angle_path = ws / "angle.json"
    if angle_path.exists():
        try:
            format_id = json.loads(angle_path.read_text(encoding="utf-8")).get("format_id")
        except (json.JSONDecodeError, UnicodeDecodeError):
            format_id = None
    result["format_id"] = format_id
    format_rules = cfg.get("format_rules") or {}
    if format_id and format_id in format_rules:
        allowed = [p for p in format_rules[format_id] if p in ("mid", "end")]
        dropped = [p for p in placements if p not in allowed]
        if dropped:
            result["skipped"].extend(
                {"placement": p, "reason": f"cta.format_rules[{format_id!r}] excludes it"}
                for p in dropped)
        placements = [p for p in placements if p in allowed]

    result["placements_requested"] = placements
    result["target_url"] = cfg.get("target_url")

    llm_draft = _load_cta_draft(ws)
    # cta-draft.json's top-level "blocks" is LLM-authored and untrusted: it may be
    # absent, null, a list, or a string instead of the expected dict. Resolve to a
    # safe dict ONCE here (mirroring the isinstance guard already applied to the
    # whole cta-draft.json object in _load_cta_draft), so a malformed "blocks"
    # degrades to "no LLM blocks available" rather than crashing the whole
    # mandatory cta-injection stage on `.get(placement)` against a non-dict.
    llm_blocks_raw = llm_draft.get("blocks") if llm_draft else None
    llm_blocks: dict[str, Any] = llm_blocks_raw if isinstance(llm_blocks_raw, dict) else {}
    static_variants_by_placement = cfg.get("variants", {})

    # Resolve (heading, text, shortcode) per placement: prefer the LLM draft's
    # block for that placement; fall back to the static config when the draft
    # lacks it. `shortcode` is the ecommerce products shortcode (nominally
    # copied verbatim from cta-brief.json :: resolved_products.shortcode by the
    # cta-writer subagent, but the subagent's OWN output is untrusted LLM text
    # — _SAFE_PRODUCTS_SHORTCODE_RE below gates it) — None for b2b/static
    # blocks or any value that fails the shape gate.
    resolved: dict[str, tuple[str, str, str | None]] = {}
    used_llm_for: set[str] = set()
    for placement in placements:
        block = llm_blocks.get(placement)
        if isinstance(block, dict) and str(block.get("heading", "")).strip() and str(block.get("text", "")).strip():
            raw_sc = block.get("shortcode")
            shortcode = raw_sc.strip() if isinstance(raw_sc, str) and raw_sc.strip() else None
            if shortcode is not None and not _SAFE_PRODUCTS_SHORTCODE_RE.match(shortcode):
                result["warnings"].append(
                    f"placement '{placement}': cta-draft.json shortcode {shortcode!r} does not "
                    f"match the strict quote-less [products ...] shape — dropped as untrusted "
                    f"LLM output; the markdown-link requirement re-applies for this block."
                )
                shortcode = None
            resolved[placement] = (str(block["heading"]).strip(), str(block["text"]).strip(), shortcode)
            used_llm_for.add(placement)
        elif static_heading and placement in static_variants_by_placement:
            variants = [v for v in static_variants_by_placement.get(placement, []) if isinstance(v, dict)]
            for v in variants:
                verr = _validate_variant(v)
                if verr:
                    result["warnings"].append(f"{placement}: {verr}")
            usable = [v for v in variants if _validate_variant(v) is None]
            if usable:
                variant = _pick_variant(usable, task_id, placement)
                resolved[placement] = (static_heading, str(variant["text"]), None)
                result["variants_used"][placement] = variant.get("id", "?")
            else:
                result["passed"] = False
                result["errors"].append(
                    f"placement '{placement}' requested but no usable variant in "
                    f"business-context.json :: cta.variants.{placement}"
                )

    if used_llm_for:
        result["draft_source"] = "llm"
    if not used_llm_for and llm_draft is not None:
        result["warnings"].append(
            "cta-draft.json present but had no usable block for the requested "
            "placement(s) — fell back to the static cta.variants config"
        )

    # Per-block heading validation — this is the direct fix for the
    # silent-styling-failure risk: an LLM-authored heading that is not in the
    # component_headings registry hard-fails THIS block rather than silently
    # rendering unstyled.
    for placement, (heading, _text, _sc) in list(resolved.items()):
        if classify_heading(heading) is None or "cta" not in str(classify_heading(heading)):
            result["passed"] = False
            result["errors"].append(
                f"cta block '{placement}' heading '{heading}' is not recognized by "
                f"scripts/_core/component_headings (no 'cta'/'cta_quiet'/'cta_banner' match) "
                f"— the publisher would never tag it and the CSS would never style it."
            )
            del resolved[placement]

    if not resolved and placements:
        result["passed"] = False
        result["errors"].append(
            "no usable CTA content resolved for any requested placement (LLM draft "
            "empty/invalid and no usable static variant configured)"
        )
        return result

    draft_path = ws / "draft.md"
    if not draft_path.exists():
        result["passed"] = False
        result["errors"].append("draft.md not found")
        return result

    content = draft_path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(content)

    existing = _classify_existing_placements(body)
    to_apply = [p for p in resolved if p not in existing]
    for p in placements:
        if p in existing:
            result["skipped"].append({"placement": p, "reason": "already present (idempotent)"})

    # Second idempotency layer: content identity (2026-08-17). Runs in BOTH
    # inject and --check modes — a duplicate that already shipped must fail the
    # --check exactly as hard as it fails the injection run.
    dup_errors = _content_duplicate_errors(body, resolved)
    if dup_errors:
        result["passed"] = False
        result["errors"].extend(dup_errors)
    # An unregistered (renamed) copy: classification says absent, content says
    # present — injecting would mint the duplicate. Refuse those placements.
    blocked: list[str] = []
    for p in list(to_apply):
        _h, raw_text, sc = resolved[p]
        text = sanitize_copy(raw_text).strip()
        if (text and text in body) or (sc and sc.strip() and sc.strip() in body):
            to_apply.remove(p)
            blocked.append(p)
    if blocked and not check_only:
        result["passed"] = False
        for p in blocked:
            result["errors"].append(
                f"placement '{p}': REFUSED to inject — the CTA content already exists in "
                f"the draft under a heading the classifier does not recognize (a renamed "
                f"copy). Restore the registered cta-draft.json heading on that block (or "
                f"delete it) and re-run; injecting now would duplicate the CTA."
            )

    if check_only:
        expected = list(resolved.keys())
        prior_path = ws / RESULT_FILENAME
        if prior_path.exists():
            try:
                prior = json.loads(prior_path.read_text(encoding="utf-8"))
                if prior.get("_generated_by") == "cta-injector":
                    expected = [p for p in prior.get("placements_applied", []) if p in placements]
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        result["placements_applied"] = sorted(existing & set(placements))
        missing = [p for p in expected if p not in existing]
        if missing:
            result["passed"] = False
            result["errors"].append(
                f"--check: CTA placement(s) {missing} were applied by the cta-injection "
                f"stage but are no longer in the draft — a repair loop or subagent "
                f"stripped the CTA module. Re-run: python -m scripts.optimize.cta_injector "
                f"--task-id {task_id} --project-slug {project_slug} --json"
            )
        return result

    mutated = False
    for placement in to_apply:
        heading, raw_text, shortcode = resolved[placement]
        err = _validate_variant({"id": placement, "text": raw_text}, has_shortcode=bool(shortcode))
        if err:
            result["passed"] = False
            result["errors"].append(f"placement '{placement}': {err}")
            continue
        # sanitize_copy applies to the intro prose ONLY — the shortcode is placed
        # verbatim (it has no apostrophes/em-dashes to mangle, and touching it
        # would risk corrupting WordPress's attribute parsing).
        text = sanitize_copy(raw_text)
        block = _build_block(heading, text, shortcode)

        if placement == "end":
            tail = _find_tail_offset(body)
            if tail is None:
                result["skipped"].append({
                    "placement": "end",
                    "reason": "no '## References' / '## Further Reading' H2 found — draft is "
                              "malformed for this stage (mandatory_sections gate will block it)",
                })
                continue
            body = _insert_at(body, tail, block)
        else:  # mid
            sections = _content_sections(body)
            if len(sections) < 3:
                result["skipped"].append({
                    "placement": "mid",
                    "reason": f"only {len(sections)} content sections — too short for a mid CTA",
                })
                continue
            total = sum(s["words"] for s in sections)
            cum = 0
            host = sections[-2]
            for s in sections:
                cum += s["words"]
                if cum >= total * _MID_MARK:
                    host = s
                    break
            if host is sections[0] and len(sections) > 1:
                host = sections[1]
            body = _insert_at(body, host["end"], block)
            result["variants_used"]["mid_host_section"] = host["heading"]

        mutated = True
        result["newly_injected"].append(placement)

    if mutated:
        draft_path.write_text(frontmatter + body, encoding="utf-8")

    result["placements_applied"] = sorted(_classify_existing_placements(body) & set(placements))
    return result


def _write_result(task_id: str, result: dict[str, Any]) -> None:
    ws = WS_ROOT / task_id
    ws.mkdir(parents=True, exist_ok=True)
    (ws / RESULT_FILENAME).write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Inject the project's CTA module into draft.md")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--project-slug", required=True)
    ap.add_argument("--check", action="store_true",
                    help="Verify expected CTA placements exist; never mutate the draft")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = inject(args.task_id, args.project_slug, check_only=args.check)
    if not args.check:
        _write_result(args.task_id, result)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        flag = "OK" if result["passed"] else "FAIL"
        print(f"  [{flag}] cta-injection: enabled={result['enabled']} "
              f"applied={result['placements_applied']} new={result['newly_injected']}")
        for e in result["errors"]:
            print(f"    - ERROR: {e}")
        for s in result["skipped"]:
            print(f"    - skip {s['placement']}: {s['reason']}")
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
