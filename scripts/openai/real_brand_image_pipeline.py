"""
scripts/openai/real_brand_image_pipeline.py — real-brand image executor (skill-level,
project-configured; project-echo is the first project to opt in, but nothing here is vertical-
or project-echo-specific — every vertical-specific value flows from the project's config via
ImageBrandPolicy, and the project slug is resolved per task, never hardcoded).

For a project whose image_brand_policy.source_real_photos is true, this produces article
images as REAL product PHOTOS of the real brand, re-scened by AI with the real pack
preserved — instead of AI-fabricated packs. Per slot:

    source a real product photo (real_photo_sourcer: Tavily + Brave, +Firecrawl page)
      → AI-edit the scene, preserve the pack (product_photo_editor → relay /edits)
      → fit to the 4K tier → save PNG
      → emit a wp_publisher-compatible images.json entry

This module's PURE pieces (entry assembly + merge-by-slot) are unit-tested; the network
orchestration + CLI are exercised by a live ``--smoke`` run.
"""
from __future__ import annotations

import re
from typing import Any

_VALID_SOURCES = frozenset({"realtime", "batch", "chart_render", "skipped", "failed"})

# 2026-07-16 project-echo/project-lima batch: a landmark/streetscape slot's `brand` field is
# often authored as a DESCRIPTIVE placeholder ("none (landmark / streetscape — no
# age-restricted product product depicted)"), not a true empty string. That non-empty text used to
# sail past the `if not brand` check below and get formatted straight into the
# project's "{brand} age-restricted product pack studio product photo" search query, sourcing and
# then compositing a fabricated product box (observed shipping a box literally reading
# "NONE", and separately a box carrying a leaked "Unsplash+" stock-photo watermark).
# Any brand string that starts with a no-product sentinel word is treated the same as
# an empty brand — no real-product sourcing is attempted for that slot.
_NO_PRODUCT_BRAND_RE = re.compile(r"^(none|n/?a|no brand|no product)\b", re.IGNORECASE)


def _is_no_product_brand(brand: str) -> bool:
    return bool(_NO_PRODUCT_BRAND_RE.match(brand.strip()))


def build_image_entry(
    slot_id: str,
    path: str,
    *,
    filename: str,
    alt: str,
    is_featured: bool,
    source: str = "realtime",
    caption: str = "",
    title: str = "",
    description: str = "",
) -> dict[str, Any]:
    """Build one wp_publisher-compatible images.json entry (the full 9-field contract)."""
    if source not in _VALID_SOURCES:
        raise ValueError(f"source must be one of {sorted(_VALID_SOURCES)}, got {source!r}")
    return {
        "slot_id": slot_id,
        "path": str(path),
        "filename": filename,
        "alt": alt,
        "caption": caption,
        "title": title or slot_id.replace("_", " ").title(),
        "description": description,
        "is_featured": bool(is_featured),
        "source": source,
    }


def merge_images_by_slot(
    prior: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Upsert ``new`` entries into ``prior`` keyed by slot_id (new wins).

    Preserves any prior slot not present in ``new`` — e.g. chart slots written by
    render_data_charts.py — matching openai_image_pipeline's merge behavior.
    """
    by_slot: dict[str, dict[str, Any]] = {}
    for e in prior:
        if isinstance(e, dict) and e.get("slot_id"):
            by_slot[str(e["slot_id"])] = e
    for e in new:
        if isinstance(e, dict) and e.get("slot_id"):
            by_slot[str(e["slot_id"])] = e
    return list(by_slot.values())


# ─── Aspect → 4K tier + slug helpers (pure) ────────────────────────────────────

_ASPECT_TARGETS: dict[str, tuple[int, int]] = {
    "1:1": (2880, 2880),
    "16:9": (3840, 2160),
    "4:3": (3264, 2448),
    "3:2": (3456, 2304),
    "3:4": (2448, 3264),
    "9:16": (2160, 3840),
}


def target_for_aspect(aspect: str) -> tuple[int, int]:
    """Map an aspect ratio to its 4K-tier (w, h). Defaults to square."""
    return _ASPECT_TARGETS.get(aspect.strip(), (2880, 2880))


def _slugify(text: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return s or "image"


def _is_cover_slot(slot_id: str) -> bool:
    """True if this slot is the cover/featured slot.

    Real workspaces name the cover ``slot-cover`` (not the bare ``cover`` the
    old `slot_id == "cover"` checks assumed), so the cover never got
    ``is_featured=True`` → the publisher set no WP featured_media → under the
    ``no_inline`` policy the cover rendered NOWHERE (2026-06-29 project-echo miss).

    2026-07-01: delegates to the shared single source of truth (the same logic
    now also guards openai_image_pipeline + wp_publisher's featured fallback).
    """
    from scripts._core.image_prompts import is_cover_slot
    return is_cover_slot(slot_id)


def build_alt_text(brand: str, scene: str, product_noun: str = "product") -> str:
    """Build the image alt text. Domain-neutral default; the SLOT (article subject)
    supplies ``product_noun`` — never assume the project's category noun fits.

    v3.41.2: the joiner is a comma, NOT an em-dash. The old ``ā€” `` template shipped
    a U+2014 into every alt attribute (render_lint L12's exact veto target) and,
    combined with the project-level noun, produced factually wrong alts like
    "A real Senix remote control slope mower" on off-core articles (Senix makes no
    slope mowers). Alt text is a rendered-HTML surface; it obeys the same style
    red lines as body prose.
    """
    noun = (product_noun or "product").strip() or "product"
    b = (brand or "").strip()
    lead = f"A real {b} {noun}" if b else f"A {noun}"
    return f"{lead}, {scene.strip()}"[:125]


_DEFAULT_SCENE = "a premium dark charcoal duty-free shelf with a warm champagne-gold rim light"


def parse_photo_slot(slot: Any) -> dict[str, Any] | None:
    """Parse an image-prompts.json slot into a real-photo job, or None if not applicable.

    Returns None for chart slots and for slots that don't name a real brand to source.
    A slot whose ``brand`` is a no-product sentinel ("none ...", "n/a", etc. — the
    convention for a landmark/streetscape slot) still parses, but carries
    ``no_product: True`` so the caller can skip real-photo sourcing entirely instead of
    formatting the placeholder text into a product-photo search query (see module-level
    comment on ``_NO_PRODUCT_BRAND_RE`` for the incident this guards against).
    """
    if not isinstance(slot, dict):
        return None
    if str(slot.get("kind", "photo")).lower() == "chart":
        return None
    brand = str(slot.get("brand") or "").strip()
    slot_id = str(slot.get("slot_id") or slot.get("slot") or "").strip()
    if not slot_id:
        return None
    # v3.41.2: an EMPTY brand parses as no_product=True instead of returning None.
    # Pre-fix, a brand:null photo slot (the correct design for a generic unbranded
    # subject — a robotic mower, a PV array) VANISHED here: run_for_workspace's
    # `if parsed is None: continue` dropped it with no entry, no log, no image
    # (2026-07-18 art-002: all 3 photo slots silently missing at publish time).
    # Parsing it as no_product routes it to the plain-scene AI fallback instead.
    no_product = _is_no_product_brand(brand) or not brand
    scene = str(slot.get("scene") or slot.get("setting") or "").strip() or _DEFAULT_SCENE
    aspect = str(slot.get("aspect_ratio") or slot.get("aspect") or "1:1").strip() or "1:1"
    return {
        "slot_id": slot_id,
        "brand": brand,
        "no_product": no_product,
        "scene": scene,
        "aspect": aspect,
        "people": bool(slot.get("people", False)),
        "is_featured": bool(slot.get("is_featured", _is_cover_slot(slot_id))),
        # v3.41.2: the ARTICLE's subject noun, as designed per-slot. The project
        # policy noun is a fallback only — passing the project noun for an
        # off-core article is how "Senix push mowers" got sourced as a
        # competitor-branded slope mower (Farmry, 3 articles on 2026-07-18).
        "product_noun": str(slot.get("product_noun") or "").strip(),
        # Raw slot kept for the plain-scene AI fallback's prompt synthesis.
        "raw": slot,
    }


# ─── Per-slot orchestration (network; validated by live --smoke) ───────────────


def generate_slot(
    brand: str,
    scene: str,
    *,
    slot_id: str = "cover",
    out_dir: str,
    project_slug: str | None = None,
    aspect: str = "1:1",
    preserve: bool = True,
    people: bool = False,
    use_mask: bool = False,
    purpose: str = "",
    engine: str = "auto",
    product_noun: str = "product",
    search_terms: tuple[str, ...] = (),
    negative_terms: tuple[str, ...] = (),
    ymyl_clause: str = "",
    style_clause: str = "",
    task_id: str = "",
) -> dict[str, Any] | None:
    """Source a real product photo → re-scene (preserve pack) → fit to 4K tier → save.

    Returns a wp_publisher-compatible images.json entry, or None if no real photo found.
    """
    import io
    from pathlib import Path
    from PIL import Image
    from scripts.openai import real_photo_sourcer as sourcer
    from scripts.openai import product_photo_editor as editor

    sourced = sourcer.source_real_photo(
        brand, purpose, product_noun=product_noun,
        search_terms=search_terms, negative_terms=negative_terms,
    )
    if sourced is None:
        return None
    _cand, raw = sourced

    edited_bytes = editor.rescene_product(
        raw, scene, brand=brand, preserve=preserve, people=people, use_mask=use_mask,
        aspect=aspect, engine=engine,
        product_noun=product_noun, ymyl_clause=ymyl_clause, style_clause=style_clause,
    )
    img = Image.open(io.BytesIO(edited_bytes)).convert("RGB")
    tw, th = target_for_aspect(aspect)
    img = editor.fit_to_tier(img, tw, th)

    # Task-scoped filename so two different articles that both depict, say, BrandA
    # cannot dedup to each other's WP media on upload (the publisher dedups by the
    # on-disk basename with check_existing_by_filename=True). The unique name MUST be
    # the actual file on disk, not just the images.json `filename` field.
    fname = f"{_slugify(brand)}-{slot_id}"
    if task_id:
        fname = f"{fname}-{_slugify(task_id)}"

    out_path = Path(out_dir) / f"{fname}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)

    if project_slug:
        try:
            from scripts.openai import image_watermark
            image_watermark.apply_from_project(str(out_path), project_slug, is_featured=_is_cover_slot(slot_id))
        except Exception:
            pass

    alt = build_alt_text(brand, scene, product_noun)
    return build_image_entry(
        slot_id, str(out_path),
        filename=fname,
        alt=alt, is_featured=_is_cover_slot(slot_id), source="realtime",
    )


def _generate_plain_scene_ai(
    parsed: dict[str, Any],
    out_dir: str,
    *,
    task_id: str = "",
    project_slug: str | None = None,
) -> dict[str, Any] | None:
    """Generate a brand-less generic-scene slot via the normal AI provider chain.

    v3.41.2 root cure: a photo slot with no real brand to source (brand:null, or a
    "none ..." landmark sentinel) previously had NO generator at all — the comment
    read "No fallback plain-scene generator exists yet" and the slot shipped as
    source:"skipped" (or, for brand:null, vanished without even an entry). On the
    2026-07-18 solar-mower article that left every photo slot missing at publish
    time. A generic unbranded subject (a robotic mower, a PV array, an unbranded
    zero-turn) is exactly what AI generation is FOR, so route these slots through
    openai_image_pipeline's provider chain (mikuapi → vertex → openai), the same
    path every non-real-photo project already uses.

    The prompt is synthesized from the SLOT's own fields only. Deliberately NO
    project art_direction_prefix: on off-core articles the prefix's project-category
    language (slope mowers) overrode the slot subject and produced a wrong-subject
    image (2026-07-18 bad-boy cover, round 1). Returns a wp_publisher-compatible
    entry, or None on any failure (caller records the skip; never aborts the batch).
    """
    import sys
    from pathlib import Path
    try:
        raw = parsed.get("raw") or {}
        slot_id = parsed["slot_id"]
        noun = str(parsed.get("product_noun") or "").strip()
        scene = str(parsed.get("scene") or "").strip()

        full = str(raw.get("full_prompt") or raw.get("prompt") or "").strip()
        if full:
            prompt_parts = [full]
        else:
            subject = str(raw.get("subject") or "").strip()
            composition = str(raw.get("composition") or "").strip()
            mood = str(raw.get("mood") or "").strip()
            core = ", ".join(x for x in (noun or subject, scene, composition, mood) if x)
            if not core:
                return None
            prompt_parts = [f"A realistic, high-detail photograph of {core}."]
        prompt_parts.append(
            "Generic unbranded equipment and setting: no logos, no brand names, "
            "no wordmarks, no readable text, no watermark, no chart or diagram overlay."
        )
        neg = str(raw.get("negative_prompt") or "").strip()
        if neg:
            prompt_parts.append(f"Do not include: {neg}")
        prompt = " ".join(prompt_parts)

        tw, th = target_for_aspect(parsed.get("aspect") or "1:1")

        fname = str(raw.get("filename_seed") or raw.get("filename") or "").strip() or f"{slot_id}-scene"
        fname = _slugify(fname)
        if task_id:
            fname = f"{fname}-{_slugify(task_id)}"

        import openai as _openai_sdk
        from scripts._core.image_provider import resolve_providers
        from scripts.openai import openai_image_pipeline as _oip

        providers = resolve_providers()
        if not providers:
            return None
        clients: list[tuple[Any, Any]] = []
        for p in providers:
            if getattr(p, "protocol", "openai") == "vertex_gemini":
                clients.append((p, None))
                continue
            kwargs: dict[str, Any] = {"api_key": p.api_key}
            if p.base_url:
                kwargs["base_url"] = p.base_url
            clients.append((p, _openai_sdk.OpenAI(**kwargs)))

        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        spec = _oip.ImagePromptSpec(
            slot=slot_id, prompt=prompt, size=f"{tw}x{th}", quality="high", filename=fname,
        )
        log = _oip.PipelineLogger(out_path.parent, json_mode=False)
        res = _oip.generate_realtime_one(clients, spec, out_path, log)
        if not getattr(res, "success", False) or not getattr(res, "image_path", ""):
            return None

        alt = build_alt_text("", scene or noun, noun or "scene")
        return build_image_entry(
            slot_id, str(res.image_path), filename=fname, alt=alt,
            is_featured=parsed.get("is_featured", _is_cover_slot(slot_id)),
            source="realtime",
        )
    except Exception as exc:  # a fallback must never abort the batch
        print(f"[real_brand_image_pipeline] plain-scene AI fallback failed for "
              f"slot {parsed.get('slot_id')!r}: {exc}", file=sys.stderr)
        return None


def _resolve_project_slug(workspace: str, explicit: str | None) -> str | None:
    """Resolve the project slug for a workspace WITHOUT hardcoding any project.

    Skill-level code must not assume a specific project. Priority:
    explicit arg → the workspace's ``state.json :: project_slug`` (the canonical
    per-task identity, set at task creation per Rule 7) → the active project
    (env-first via active_project). Returns None if unresolved — in which case
    ``load_image_brand_policy("")`` yields backward-compatible neutral defaults.
    """
    if explicit:
        return explicit
    import json
    from pathlib import Path
    try:
        sj = Path(workspace) / "state.json"
        if sj.exists():
            slug = json.loads(sj.read_text(encoding="utf-8")).get("project_slug")
            if slug:
                return str(slug)
    except Exception:
        pass
    try:
        from scripts._core import active_project
        return active_project.get_active_project() or None
    except Exception:
        return None


def run_for_workspace(workspace: str, project_slug: str | None = None) -> list[dict[str, Any]]:
    """Process every real-photo slot in a workspace's image-prompts.json → merged images.json.

    Reads image-prompts.json, sources+re-scenes a real photo per product slot, and merges
    the entries into images.json (preserving chart slots). Returns the merged list.

    ``project_slug`` is resolved per-task (state.json → active project) when not passed —
    skill-level code never assumes a particular project.
    """
    import json
    from pathlib import Path
    from scripts._core.image_brand_policy import load_image_brand_policy

    ws = Path(workspace)
    task_id = ws.name  # workspace dir basename == task_id; scopes filenames to avoid cross-article dedup
    project_slug = _resolve_project_slug(workspace, project_slug)
    prompts_file = ws / "image-prompts.json"
    images_dir = ws / "images"
    # Centralized normalizer handles list AND {prompts:{slot_id:...}} dict, so a
    # dict-shaped file can never again silently source ZERO real photos (2026-06-29).
    from scripts._core.image_prompts import load_image_prompts
    raw = load_image_prompts(prompts_file)

    policy = load_image_brand_policy(project_slug or "")
    entries: list[dict[str, Any]] = []
    for slot in raw:
        parsed = parse_photo_slot(slot)
        if parsed is None:
            continue
        if parsed["no_product"]:
            # Landmark/streetscape/brand-less slot: never format placeholder brand
            # text into a product-photo search query (that fabricated a box literally
            # reading "NONE" and, separately, one carrying a leaked "Unsplash+"
            # watermark). v3.41.2: these slots now generate via the plain-scene AI
            # fallback (unbranded generic subject through the normal provider chain)
            # instead of shipping nothing — the skip entry survives only as the
            # last resort when the fallback itself fails.
            entry = _generate_plain_scene_ai(
                parsed, str(images_dir), task_id=task_id, project_slug=project_slug,
            )
            if entry is None:
                entry = build_image_entry(
                    parsed["slot_id"], "", filename=f"{parsed['slot_id']}-no-product-scene",
                    alt=f"{parsed['scene'][:110]} (no product depicted)",
                    is_featured=parsed["is_featured"], source="skipped",
                )
            entries.append(entry)
            continue
        people = parsed["people"] and policy.people_allowed   # project can veto people
        # v3.41.2: the SLOT's subject noun wins over the project policy noun. When
        # the slot declares its own noun (an off-core article's subject), the
        # project-level search_terms describe the WRONG subject — the exact defect
        # that sourced a competitor-branded slope mower (Farmry) onto a Senix
        # push-mower cover — so they are dropped in favor of the domain-neutral
        # "{brand} {noun}" query templates. Slots without a noun keep the full
        # project policy (backward compatible).
        _slot_noun = parsed.get("product_noun") or ""
        _noun = _slot_noun or policy.product_noun
        _terms = policy.search_terms if (not _slot_noun or _slot_noun == policy.product_noun) else ()
        try:
            entry = generate_slot(
                parsed["brand"], parsed["scene"], slot_id=parsed["slot_id"],
                out_dir=str(images_dir), project_slug=project_slug, aspect=parsed["aspect"],
                people=people, use_mask=True, engine=policy.edit_engine,
                product_noun=_noun, search_terms=_terms,
                negative_terms=policy.negative_terms, ymyl_clause=policy.ymyl_clause,
                style_clause=policy.style_clause, task_id=task_id,
            )
        except Exception as exc:  # one bad slot must not abort the whole batch
            import sys
            print(f"[real_brand_image_pipeline] slot {parsed['slot_id']!r} ({parsed['brand']}) "
                  f"failed: {exc}", file=sys.stderr)
            entry = build_image_entry(
                parsed["slot_id"], "", filename=f"{_slugify(parsed['brand'])}-{parsed['slot_id']}",
                alt=f"{parsed['brand']} (image generation failed)",
                is_featured=parsed["is_featured"], source="failed",
            )
        if entry is None:
            entry = build_image_entry(
                parsed["slot_id"], "", filename=f"{_slugify(parsed['brand'])}-{parsed['slot_id']}",
                alt=f"{parsed['brand']} (no real product photo found)",
                is_featured=parsed["is_featured"], source="skipped",
            )
        entries.append(entry)

    images_file = ws / "images.json"
    prior: list[dict[str, Any]] = []
    if images_file.exists():
        try:
            data = json.loads(images_file.read_text(encoding="utf-8"))
            prior = data if isinstance(data, list) else (data.get("images", []) if isinstance(data, dict) else [])
        except Exception:
            prior = []
    merged = merge_images_by_slot(prior, entries)
    images_file.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser(description="Real-brand image executor (source real photo → re-scene).")
    ap.add_argument("--smoke", action="store_true", help="run ONE slot end-to-end (live)")
    ap.add_argument("--brand", default="", help="real product brand to source, e.g. BrandA / BrandA / BrandB")
    ap.add_argument("--product-noun", default="product", help="vertical noun, e.g. 'age-restricted product pack' (else generic)")
    ap.add_argument("--scene", default="a deep charcoal duty-free shelf with a warm champagne-gold rim light")
    ap.add_argument("--slot-id", default="cover")
    ap.add_argument("--aspect", default="1:1")
    ap.add_argument("--out", default=".", help="output directory")
    ap.add_argument("--project-slug", default="", help="resolved from state.json/active project if omitted")
    ap.add_argument("--people", action="store_true")
    ap.add_argument("--use-mask", action="store_true", help="pixel-lock the pack via a center mask")
    ap.add_argument("--engine", default="auto", help="auto|vertex|relay|vertex_only|relay_only")
    ap.add_argument("--workspace", default="", help="process all real-photo slots in a workspace's image-prompts.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.workspace and not args.smoke:
        merged = run_for_workspace(args.workspace, args.project_slug or None)
        print(json.dumps({"ok": True, "count": len(merged),
                          "slots": [e["slot_id"] for e in merged]}, ensure_ascii=False))
        return 0

    if args.smoke:
        if not args.brand:
            print("ERROR: --smoke requires --brand", file=sys.stderr)
            return 2
        entry = generate_slot(
            args.brand, args.scene, slot_id=args.slot_id, out_dir=args.out,
            project_slug=args.project_slug, aspect=args.aspect,
            people=args.people, use_mask=args.use_mask, engine=args.engine,
            product_noun=args.product_noun,
        )
        if entry is None:
            print(json.dumps({"ok": False, "error": "no real product photo found"}))
            return 1
        print(json.dumps({"ok": True, "entry": entry}, ensure_ascii=False, indent=2))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
