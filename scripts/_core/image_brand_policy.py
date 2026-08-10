"""
scripts/_core/image_brand_policy.py — config-aware image brand policy.

Decides, per project, whether article IMAGES may depict real product brands and
whether they should be sourced as real photographs (vs AI-generated). This is the
single source of truth that makes the image dispatch prompts (orchestrator) and the
visual-QA rules respect ``brand-guideline.yaml :: packaging_branding.forbid_third_party_brands``
instead of hardcoding "never a third-party brand".

Background: project-echo is enthusiast education (科普) — age-restricted product brands (BrandA,
BrandB, BrandC…) are the SUBJECT, not competitors. So project-echo sets
``forbid_third_party_brands: false`` + ``image_sourcing_policy.source: real_product_photos``
and its article images are real photos of the real brand. Every OTHER project leaves
the default (forbid real brands, generic/relabeled packs) untouched — so this is fully
backward compatible.

The competitor-exclusion rules (render_lint L11, competitor_domains.py) are CITATIONS
only and never touched images; the only image-level enforcement was prompt text, which
``brand_clause_for_prompt`` now drives from config.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Repo/plugin root: scripts/_core/image_brand_policy.py -> parents[2]. Works from
# both the source tree and the installed plugin cache (projects/ sits beside scripts/).
_PLUGIN_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ImageBrandPolicy:
    """Resolved per-project policy for brands in article images."""
    allow_real_brands: bool       # may images show the real subject brand (e.g. real BrandA pack)?
    source_real_photos: bool      # source real product photos (vs AI-generate the product)?
    people_allowed: bool          # may a person appear (still YMYL-constrained)?
    preserve_real_product: bool   # when editing, must the real product stay pixel-faithful?
    edit_engine: str              # which edit engine: "auto"|"vertex"|"relay" (config-switchable)
    # ── Domain-neutral defaults; a project supplies its own vertical's wording via config so
    #    the skill-level sourcer/editor stay clean (no hardcoded "age-restricted product"/vertical-YMYL). ──
    product_noun: str = "product"            # e.g. project-echo → "age-restricted product pack"; watch site → "watch"
    search_terms: tuple[str, ...] = ()       # query templates (may contain "{brand}"); () → generic
    negative_terms: tuple[str, ...] = ()     # extra scoring negatives (e.g. project-echo "off-theme")
    ymyl_clause: str = ""                     # project YMYL constraint appended to the edit prompt
    style_clause: str = ""                    # project house art-direction line for the edit prompt


def _section(d: Any, key: str) -> dict[str, Any]:
    """Return d[key] if it's a dict, else {} — defensive against malformed config."""
    if isinstance(d, dict):
        v = d.get(key)
        if isinstance(v, dict):
            return v
    return {}


def image_brand_policy_from_configs(
    business_context: dict[str, Any] | None,
    brand_guideline: dict[str, Any] | None,
) -> ImageBrandPolicy:
    """Resolve the image brand policy from the two project config dicts (PURE).

    Defaults are backward compatible: a project that sets none of these keys forbids
    real brands and does not source real photos (legacy behavior).
    """
    bc = business_context or {}
    bg = brand_guideline or {}

    packaging = _section(bg, "packaging_branding")
    # Legacy default = forbid (True). Only an explicit False unlocks real brands.
    forbid = packaging.get("forbid_third_party_brands", True)
    allow_real_brands = forbid is False

    sourcing = _section(bc, "image_sourcing_policy")
    source_real_photos = sourcing.get("source") == "real_product_photos"

    editing = _section(sourcing, "editing_real_photos")
    people_allowed = bool(editing.get("people_allowed", False))

    real_edit = _section(bg, "real_photo_editing")
    preserve_real_product = bool(real_edit.get("preserve_real_product", True))

    # Edit-engine choice is config-switchable so the future "switch back to chatgpt-code
    # once its 4K returns" is a one-line config change, not a code edit. Default "auto"
    # (Vertex true-4K primary → chatgpt-code relay fallback).
    edit_engine = str(editing.get("edit_engine") or "auto").strip().lower() or "auto"

    # Project-specific vertical wording. Absent => domain-neutral defaults (skill-level stays
    # clean: a future non-vertical real-brand project supplies its own nouns/terms/YMYL).
    product_noun = str(sourcing.get("product_noun") or "product").strip() or "product"
    search_terms = tuple(
        str(t).strip() for t in (sourcing.get("search_terms") or []) if str(t).strip()
    )
    negative_terms = tuple(
        str(t).strip().lower() for t in (sourcing.get("negative_terms") or []) if str(t).strip()
    )
    style_clause = str(sourcing.get("style_clause") or "").strip()
    ymyl_clause = str(editing.get("ymyl_clause") or "").strip()

    return ImageBrandPolicy(
        allow_real_brands=allow_real_brands,
        source_real_photos=source_real_photos,
        people_allowed=people_allowed,
        preserve_real_product=preserve_real_product,
        edit_engine=edit_engine,
        product_noun=product_noun,
        search_terms=search_terms,
        negative_terms=negative_terms,
        ymyl_clause=ymyl_clause,
        style_clause=style_clause,
    )


_ALLOW_CLAUSE = (
    "IMAGE BRAND POLICY: this project depicts REAL product brands authentically. "
    "The article's real subject brand (e.g. a real BrandA / BrandB pack, a real BrandC "
    "device) is shown exactly as it actually looks — do NOT relabel it to a house brand, "
    "avoid it, or substitute a generic/fabricated pack. The ONLY brand still banned in "
    "imagery is a competing online STORE / retailer's logo or wordmark."
)

_FORBID_CLAUSE = (
    "IMAGE BRAND POLICY: any visible brand label on packaging must read the project's "
    "label_text; never render a third-party / competitor brand logo or trademark."
)


def brand_clause_for_prompt(policy: ImageBrandPolicy) -> str:
    """Return the dispatch-prompt clause for image-prompt-designer / visual-QA."""
    return _ALLOW_CLAUSE if policy.allow_real_brands else _FORBID_CLAUSE


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_image_brand_policy(project_slug: str) -> ImageBrandPolicy:
    """Load the policy for a project from its on-disk config (thin wrapper).

    Missing/unreadable config => the backward-compatible default (forbid real brands,
    no real-photo sourcing) — so an unknown project is always safe.
    """
    proj = _PLUGIN_ROOT / "projects" / project_slug
    bc = _load_json(proj / "business-context.json")
    bg = _load_yaml(proj / "brand-guideline.yaml")
    return image_brand_policy_from_configs(bc, bg)
