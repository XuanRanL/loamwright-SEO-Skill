"""scripts/wordpress/tag_seo_resolver.py — Resolve tag SEO spec from
projects/{slug}/tags-config.json.

Called by wp_publisher.py during the article publish flow after the
get_or_create_terms() step. For each tag the article references, this module
returns the SEO spec (description + RankMath meta) to apply. If the tag is
strategic (in tags-config.strategic_tags) → full SEO. If it's a known
noindex_tag → noindex meta. If unknown (organic tag from article frontmatter)
→ policy default (noindex + auto-generated description).

This is the runtime integration point that ensures every tag a published
article touches has correct SEO meta, regardless of whether the tag pre-existed
or was created fresh during publish.
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=8)
def _load_config(site_slug: str) -> dict:
    path = PLUGIN_ROOT / "projects" / site_slug / "tags-config.json"
    if not path.exists():
        return {
            "policy": {
                "default_robots": ["index"],
                "auto_create_default_meta": {
                    "rank_math_robots": ["index"],
                    "description_template": "Articles tagged '{name}' on this site.",
                },
            },
            "strategic_tags": [],
            "baseline_tags": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _index_by_slug(items: list[dict]) -> dict[str, dict]:
    return {t["slug"]: t for t in items if "slug" in t}


def _index_by_name(items: list[dict]) -> dict[str, dict]:
    return {t["name"].lower(): t for t in items if "name" in t}


def _index_by_merge_from(items: list[dict]) -> dict[str, dict]:
    """Map legacy slugs to the canonical strategic_tag they're being merged into."""
    out: dict[str, dict] = {}
    for t in items:
        for legacy in t.get("merge_from_slugs", []):
            out[legacy] = t
    return out


def resolve_tag_seo_spec(site_slug: str, tag_name_or_slug: str) -> dict[str, Any]:
    """Return the SEO spec dict for a tag.

    Lookup order:
      1. strategic_tags by slug
      2. strategic_tags by name (case-insensitive)
      3. strategic_tags via merge_from_slugs (legacy slug → canonical)
      4. baseline_tags by slug / name / merge_from_slugs
      5. Policy default (noindex + auto-template description)

    Returns spec with at least:
      - name (display name)
      - slug (canonical slug)
      - description (string)
      - rank_math_robots (list[str])
      - rank_math_title, rank_math_description, rank_math_focus_keyword (strategic only)
    """
    config = _load_config(site_slug)
    strategic = config.get("strategic_tags", [])
    noindex = config.get("baseline_tags", [])

    strat_by_slug = _index_by_slug(strategic)
    strat_by_name = _index_by_name(strategic)
    strat_by_merge = _index_by_merge_from(strategic)
    base_by_slug = _index_by_slug(noindex)
    base_by_name = _index_by_name(noindex)
    base_by_merge = _index_by_merge_from(noindex)

    key = tag_name_or_slug.strip()
    key_lower = key.lower()
    # Try slug-style first (lowercase, no spaces)
    slug_guess = key_lower.replace(" ", "-")

    # Strategic — full SEO
    for k in (slug_guess, key_lower):
        if k in strat_by_slug:
            return _materialize_strategic(strat_by_slug[k])
    if key_lower in strat_by_name:
        return _materialize_strategic(strat_by_name[key_lower])
    if slug_guess in strat_by_merge:
        return _materialize_strategic(strat_by_merge[slug_guess])

    # Noindex (known)
    policy = config.get("policy", {})
    desc_template = policy.get("auto_create_default_meta", {}).get("description_template")
    # NOTE: description_template is intentionally null in canonical configs (post-2026-05-23).
    # Templates produce structurally-identical sentences across the tag set, which is a
    # hidden anti-pattern flagged by feedback_no_hidden_template_in_taxonomy_copy.md.
    # If a project config still has a non-null template, we tolerate it for backwards-compat,
    # but the canonical path is template=None → empty description → human/LLM follow-up.
    for k in (slug_guess, key_lower):
        if k in base_by_slug:
            t = base_by_slug[k]
            return _materialize_baseline(t, desc_template)
    if key_lower in base_by_name:
        return _materialize_baseline(base_by_name[key_lower], desc_template)
    if slug_guess in base_by_merge:
        return _materialize_baseline(base_by_merge[slug_guess], desc_template)

    # Default — unknown organic tag. Description is intentionally EMPTY so the
    # publisher does not POST a templated string. The tag ships with name+slug+robots
    # only; a follow-up curated-write pass (manual or LLM-driven) fills in the
    # description. Reference style: tags 480W / 640W / 1000W HPS (3-sentence tag-centric).
    return {
        "name": key,
        "slug": slug_guess,
        "description": "",  # left empty — no template fallback
        "rank_math_robots": policy.get("default_robots", ["index"]),
        "_source": "policy_default",
        "_needs_curated_description": True,
    }


def _materialize_strategic(t: dict) -> dict:
    spec = dict(t)
    spec["_source"] = "strategic"
    return spec


def _materialize_baseline(t: dict, desc_template: str | None) -> dict:
    # Prefer per-tag curated description. If absent and template is None (canonical
    # post-2026-05-23), leave description empty rather than fabricate. If template
    # exists (legacy config), only then apply it — but emit a warning.
    description = t.get("description")
    if not description:
        if desc_template:
            import sys
            print(
                f"⚠ tag_seo_resolver: baseline tag '{t['name']}' has no curated description; "
                f"falling back to legacy template — see feedback_tag_description_must_be_tag_centric.md "
                f"for the recommended migration (template should be null).",
                file=sys.stderr,
            )
            description = desc_template.format(name=t["name"])
        else:
            description = ""  # leave empty for follow-up curated pass
    spec = {
        "name": t["name"],
        "slug": t["slug"],
        "axis": t.get("axis"),
        "description": description,
        "rank_math_robots": t.get("rank_math_robots", ["index"]),
        "_source": "baseline_known",
        "_needs_curated_description": not bool(t.get("description")),
    }
    # Curated full meta on baseline entries passes through (loamwright 2026-07-06
    # pattern); apply_tag_seo() only PATCHes keys present in the spec, so absence
    # keeps the RankMath global template behavior.
    for opt_key in (
        "rank_math_title", "rank_math_description", "rank_math_focus_keyword",
        "rank_math_twitter_card_type",
    ):
        if t.get(opt_key):
            spec[opt_key] = t[opt_key]
    return spec


def apply_tag_seo(wp, tag_id: int, spec: dict, term_meta_writable: bool) -> dict[str, Any]:
    """PATCH a tag with its SEO spec. Returns {description_set, meta_set, meta_deferred}."""
    result = {"description_set": False, "meta_set": False, "meta_deferred": False}

    payload = {}
    if "description" in spec and spec["description"]:
        payload["description"] = spec["description"]
    # Update name + slug only if they differ from what's on the server (avoid breaking slugs)
    # — we skip name/slug updates here; setup_tags.py handles those at canonical setup time

    if payload:
        wp.post(f"/wp/v2/tags/{tag_id}", json_body=payload)
        result["description_set"] = True

    # RankMath meta
    if not term_meta_writable:
        result["meta_deferred"] = True
        return result

    meta_keys = [
        "rank_math_title", "rank_math_description", "rank_math_focus_keyword",
        "rank_math_robots", "rank_math_facebook_title", "rank_math_facebook_description",
        "rank_math_twitter_card_type", "rank_math_twitter_title", "rank_math_twitter_description",
    ]
    meta_payload = {k: spec[k] for k in meta_keys if k in spec}
    if not meta_payload:
        # At minimum, ensure robots is set (project-charlie policy: index by default)
        meta_payload = {"rank_math_robots": spec.get("rank_math_robots", ["index"])}
    wp.post(f"/wp/v2/tags/{tag_id}", json_body={"meta": meta_payload})
    result["meta_set"] = True
    return result


def check_term_meta_writable(wp) -> bool:
    """Probe whether MU plugin v1.2+ is deployed (post_tag term meta support)."""
    try:
        r = wp.get("/xuanran/v1/rank-math-bridge")
        ver = (r.json_data or {}).get("bridge_version", "1.0.0")
        parts = [int(x) for x in ver.split(".")]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts) >= (1, 2, 0)
    except Exception as e:
        # Audit 2026-05-22 P1 — log silent-fallback
        print(
            f"⚠ tag term-meta bridge version check failed: {type(e).__name__}: {e} "
            f"— assuming bridge<1.2.0 (term meta writes will be deferred)",
            file=sys.stderr,
        )
        return False
