#!/usr/bin/env python3
"""scripts/optimize/cta_brief_builder.py — Step 1 of the cta-writer pipeline (v3.37).

Deterministic fact resolver. Reads the article's blog category, looks up the
project's service-routing-map.json, pulls the matched service record from
business-context.json :: conversion_offers.services[], plus a matching team
member (by specialty_services) and proof point, and writes cta-brief.json —
facts only, zero prose. This is what guarantees the CTA's link target and any
cited stat/name are always correct; the downstream cta-writer LLM stage never
picks these itself (see agents/cta-writer.md).

No conversion_offers config on the project -> build_brief returns None, but
main() STILL writes a minimal sentinel cta-brief.json (resolved_service=null,
skipped_no_config=true). This is deliberate: the orchestrator Stage declares
expected_outputs=["cta-brief.json"] with no conditional guard, so writing NO
file would fail verify_stage() and HARD-HALT the whole pipeline (action=ERROR)
for the 5 sibling projects that have no conversion_offers config. The sentinel
satisfies the existence check unconditionally; its CONTENT (resolved_service is
null) is what signals "no real brief", so downstream cta_brief_present derives
False, cta-writer is skipped, and cta-injection falls back to the legacy static
cta.variants path in cta_injector.py. See Finding 1/2 (v3.37).

Usage:
    python -m scripts.optimize.cta_brief_builder --task-id {tid} --project-slug {slug} --json
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
WS_ROOT = PLUGIN_ROOT / "memory" / "workspace"

RESULT_FILENAME = "cta-brief.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


_SLUG_COLLAPSE_RE = re.compile(r"[&\s]+")
_HYPHEN_RUN_RE = re.compile(r"-+")


def _slugify_category(name: str) -> str:
    """Normalize a human-readable category name into a routing-map-key-shaped
    slug: lowercase; replace `&` and whitespace runs with a single hyphen;
    collapse repeated hyphens; strip leading/trailing hyphens.

    "Enterprise SEO" -> "enterprise-seo"
    "SEO for Large & Complex Sites" -> "seo-for-large-complex-sites"
    """
    s = _SLUG_COLLAPSE_RE.sub("-", name.strip().lower())
    s = _HYPHEN_RUN_RE.sub("-", s)
    return s.strip("-")


def _category_candidates(task_id: str) -> list[tuple[str, str]]:
    """Ordered (category, source) candidates to try against the routing map.

    Preference order:
      1. state.json :: brief.category (or top-level .category) — the cleanest
         signal, kept first in case a future stage ever writes it. No pipeline
         stage currently does (verified against 3 real production workspaces:
         loamentaudit0707/loamgoogagcy0707/loamwebfirms0707 all have
         brief.category=None), so this is normally empty in practice today.
      2. memory/workspace/{task_id}/meta.json :: categories[] — the REAL
         category data. Written by the meta-builder stage, which is
         guaranteed to run before cta-brief-builder (stage index 17 vs 23 in
         scripts/pipeline/orchestrator.py). These are human-readable category
         names (e.g. "Enterprise SEO"), not routing-map slugs, so callers must
         run them through `_slugify_category` before testing membership.
    """
    candidates: list[tuple[str, str]] = []

    state = _load_json(WS_ROOT / task_id / "state.json") or {}
    brief = state.get("brief") or {}
    state_cat = brief.get("category") or state.get("category")
    if state_cat:
        candidates.append((str(state_cat), "state"))

    meta = _load_json(WS_ROOT / task_id / "meta.json") or {}
    for cat in meta.get("categories") or []:
        if isinstance(cat, str) and cat.strip():
            candidates.append((cat, "meta"))

    return candidates


def _article_category(task_id: str) -> str | None:
    """Back-compat single-value accessor (used for the no-config sentinel's
    informational `blog_category` field, where routing-map resolution never
    happens). Real resolution against the routing map goes through
    `_category_candidates` + `_resolve_service_slug_multi` instead, since only
    that path can express "try candidate 2 if candidate 1 doesn't map"."""
    candidates = _category_candidates(task_id)
    return candidates[0][0] if candidates else None


def _resolve_service_slug(project_slug: str, category: str | None,
                           routing_map: dict[str, Any]) -> tuple[str | None, bool]:
    """Return (service_slug, fallback_used) for a SINGLE already-normalized
    category key (exact routing-map key match, no slugification). This is the
    single-candidate primitive; `_resolve_service_slug_multi` wraps it to try
    the state+meta candidate list in order, slugifying meta-sourced names
    first (state-sourced values are matched as-is — if a future stage does
    write brief.category, it's expected to already be a routing-map-shaped
    slug, matching pre-existing behavior/tests)."""
    if category and category in routing_map:
        entry = routing_map.get(category)
        if isinstance(entry, dict):
            slug = entry.get("slug")
            if isinstance(slug, str) and slug:
                return slug, False
    return None, True


def _resolve_service_slug_multi(
    project_slug: str, candidates: list[tuple[str, str]], routing_map: dict[str, Any],
) -> tuple[str | None, str | None, str | None, bool]:
    """Try each (category, source) candidate in priority order; return the
    first one that resolves to a routing-map hit.

    Returns (service_slug, matched_category, category_source, fallback_used).
    `category_source` is "state" | "meta" | None (None only when nothing
    matched — i.e. fallback_used is True).
    """
    for category, source in candidates:
        key = category if source == "state" else _slugify_category(category)
        slug, fallback = _resolve_service_slug(project_slug, key, routing_map)
        if not fallback:
            return slug, category, source, False
    return None, None, None, True


def _find_service(services: list[dict[str, Any]], slug: str) -> dict[str, Any] | None:
    for s in services:
        if s.get("slug") == slug:
            return s
    return None


def _match_team_member(team: list[dict[str, Any]],
                        service_slug: str | None) -> dict[str, Any] | None:
    """Match a team member by `specialty_services` membership. `service_slug`
    is None on the ecommerce path (there is no b2b service slug to match
    against there — see Finding 2, v3.38 review); explicitly short-circuit
    rather than rely on the incidental fact that `None in [...]` is False,
    which would silently misbehave if a malformed `specialty_services` entry
    ever contained a JSON null."""
    if not service_slug:
        return None
    for member in team:
        if service_slug in (member.get("specialty_services") or []):
            return {k: member[k] for k in ("name", "role", "photo_media_url") if k in member}
    return None


def _match_proof_points(proof_points: list[dict[str, Any]], service_slug: str | None,
                         limit: int = 2) -> list[dict[str, Any]]:
    # No per-service tagging on proof_points yet — service_slug is accepted
    # (and may be None on the ecommerce path, see Finding 2) but ignored;
    # return the strongest general entries (case studies first, then stats),
    # capped at `limit`.
    case_studies = [p for p in proof_points if p.get("type") == "case_study"]
    stats = [p for p in proof_points if p.get("type") == "stat"]
    return (case_studies + stats)[:limit]


# ─── Ecommerce resolver (business_model == "ecommerce") ──────────────────
#
# Deterministic product/category resolver for WooCommerce projects. Matches the
# article's REAL content (draft body + primary keyword + meta title/H2s) against
# the LOCALLY CACHED product-catalog.json (synced offline by
# scripts/wordpress/wc_catalog_sync.py — the pipeline itself never touches the
# live WC API). Emits a WooCommerce `[products ...]` shortcode that WordPress
# expands at page-view time; the LLM never assembles the shortcode. Blog taxonomy
# is organized by reader intent, NOT a mirror of product taxonomy
# (feedback_blog_taxonomy_not_product_mirror.md), so matching is on article
# CONTENT, never on the blog-category name.

# Standard connective/filler words stripped from both article and category token
# sets before scoring, so overlap reflects meaningful terms only.
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "your",
    "from", "made", "by", "at", "is", "are", "as", "it", "this", "that", "you",
    "best", "top", "guide", "how", "what", "why", "review", "reviews", "vs",
    "buy", "buying", "buyers", "buyer", "explained", "ideas",
})

# Tokens that are too generic to count as a MEANINGFUL category match on their
# own — an intersection made up only of these does not clear the "≥1 non-generic
# token hit" bar. Kept modest and catalog-neutral: marketing/tier filler plus the
# two words that pervade the largest real catalogs (every project-juliet category
# contains "filament"; most project-hotel products are "custom"), which would
# otherwise let a keyword match nearly every category.
_GENERIC_TOKENS = frozenset({
    "series", "collection", "collections", "products", "product", "standard",
    "basic", "premium", "pro", "shop", "store", "new", "sale", "custom", "kit",
    "kits", "set", "sets", "filament", "filaments",
})

_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _tokenize(text: str) -> set[str]:
    """Lowercase, HTML-unescape, split on any non-alphanumeric run, drop
    stopwords and single-character tokens. Used for both article and category
    token sets so `&amp;`, hyphens, em-dashes, and punctuation all normalize the
    same way."""
    lowered = html.unescape(text or "").lower()
    return {
        tok for tok in re.split(r"[^a-z0-9]+", lowered)
        if len(tok) > 1 and tok not in _STOPWORDS
    }


def _split_body(task_id: str) -> str:
    """Return draft.md body with any leading `---` frontmatter stripped. Empty
    string when the draft is absent (SKU matching then no-ops; category matching
    falls back to keyword/title/H2 signal)."""
    draft = _load_text(WS_ROOT / task_id / "draft.md")
    if draft is None:
        return ""
    if draft.startswith("---"):
        end = draft.find("\n---\n", 3)
        if end > 0:
            return draft[end + 5:]
    return draft


def _load_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _article_signal(task_id: str) -> tuple[str, set[str], set[str]]:
    """Return (draft_body, article_token_set, core_token_set).

    `article_token_set` = primary_keyword + meta title + draft H2 headings.
    `core_token_set` = primary_keyword + meta title ONLY — the tokens that say
    what the article IS ABOUT, as opposed to a word that merely appeared in one
    subheading. `_match_category` requires a core hit (see its docstring for the
    v3.42.3 precision cure). draft_body is returned separately because SKU-level
    matching is a verbatim substring test against the full body, not a token
    test."""
    body = _split_body(task_id)
    state = _load_json(WS_ROOT / task_id / "state.json") or {}
    brief = state.get("brief") or {}
    keyword = str(brief.get("primary_keyword") or "")

    meta = _load_json(WS_ROOT / task_id / "meta.json") or {}
    title = str(meta.get("title") or meta.get("seo_title") or "")

    h2s = " ".join(_H2_RE.findall(body))
    core = _tokenize(f"{keyword} {title}")
    tokens = core | _tokenize(h2s)
    return body, tokens, core


def _match_products(products: list[dict[str, Any]], body: str,
                    cap: int = 3) -> list[dict[str, Any]]:
    """SKU-level: products whose full (HTML-unescaped) name appears verbatim
    (case-insensitive) in the draft body, in document order, capped at `cap`.
    Trivially-short names (<2 tokens OR <8 chars) are skipped — a product literally
    named 'Urn' would false-fire on every mention of the word."""
    if not body:
        return []
    body_lower = body.lower()
    hits: list[tuple[int, dict[str, Any]]] = []
    for p in products:
        raw = p.get("name")
        if not isinstance(raw, str):
            continue
        name = html.unescape(raw).strip()
        if len(name) < 8 or len(name.split()) < 2:
            continue
        idx = body_lower.find(name.lower())
        if idx >= 0:
            hits.append((idx, p))
    hits.sort(key=lambda t: t[0])
    return [p for _, p in hits[:cap]]


def _match_category(categories: list[dict[str, Any]], article_tokens: set[str],
                    *, core_tokens: set[str] | None = None,
                    min_score: float = 0.5) -> dict[str, Any] | None:
    """Category-level: precision-oriented token overlap between the article
    signal and each in-stock category's name+slug tokens. Score =
    |intersection| / |category tokens|. A category qualifies only when
    score ≥ min_score AND the intersection has ≥1 non-generic token AND (when
    `core_tokens` is supplied and non-empty) the intersection contains ≥1 token
    from the article's CORE signal. Ties on score break toward the higher
    product count. count==0 categories excluded.

    CORE-HIT REQUIREMENT (v3.42.3). Score alone is |overlap| / |category
    tokens|, so a category whose name+slug reduce to a SINGLE token scores a
    perfect 1.0 off one incidental article word and structurally outranks every
    multi-token category — the denominator, not the relevance, decides. Caught
    live on 2026-08-04: an project-alpha German-Shepherd JOINT-SUPPLEMENT buyer's
    guide resolved the one-token `prescription` category (score 1.00) because
    the phrase "Prescription Diets" appeared in one H2, beating `hip-joint`
    (score 0.50) which actually holds the article's subject product. That would
    have injected a shoppable grid of Rx antiparasitics and antibiotics into a
    supplements article — the project's own documented CRIT-1 defect. Requiring
    the overlap to touch the primary keyword or title makes the grid reflect
    what the article is ABOUT, not a word that happened to appear in a
    subheading; a near-miss now degrades to the configured `default_category`
    rather than to a wrong category. Callers that pass no `core_tokens` keep the
    legacy behavior."""
    best: tuple[float, int, dict[str, Any]] | None = None
    eff = _effective_counts(categories)
    for cat in categories:
        if not isinstance(cat, dict) or not _stocked(cat, eff):
            continue
        slug = cat.get("slug")
        if not isinstance(slug, str) or not slug:
            continue
        cat_tokens = _tokenize(str(cat.get("name") or "")) | _tokenize(slug)
        if not cat_tokens:
            continue
        overlap = article_tokens & cat_tokens
        if not overlap:
            continue
        score = len(overlap) / len(cat_tokens)
        if score < min_score:
            continue
        if not (overlap - _GENERIC_TOKENS):
            continue  # overlap is entirely generic filler -> not meaningful
        if core_tokens and not (overlap & core_tokens):
            continue  # matched only on a peripheral H2 word -> not the topic
        count = int(cat.get("count") or 0)
        if best is None or (score, count) > (best[0], best[1]):
            best = (score, count, cat)
    return best[2] if best else None


def _excluded_category_slugs(offers: dict[str, Any]) -> set[str]:
    """Slugs from `conversion_offers.excluded_categories` — product categories
    this project must NEVER surface in a blog CTA grid, whatever the matcher
    scores (v3.42.3).

    This is a COMPLIANCE control, deliberately independent of match precision.
    A category can be perfectly on-topic and still be illegal to merchandise
    from an article: project-alpha's `prescription` line (fluralaner, doxycycline,
    albendazole, milbemycin-praziquantel) is prescription-only in the US, with
    15 states requiring an in-person VCPR, so a shoppable grid of it inside
    editorial content implies no-prescription purchase. Precision fixes reduce
    the odds of surfacing it; only an explicit blocklist makes it impossible.
    Entries are matched against BOTH the category slug and the slugified
    category name, so config may use either form."""
    raw = offers.get("excluded_categories")
    if not isinstance(raw, list):
        return set()
    return {
        _slugify_category(html.unescape(str(item))).strip()
        for item in raw if str(item).strip()
    } - {""}


def _drop_excluded(categories: list[dict[str, Any]], excluded: set[str],
                   ) -> list[dict[str, Any]]:
    """Filter `categories` down to those not named by `excluded` (by slug or by
    slugified name). Applied before BOTH content matching and default_category
    resolution, so no code path can reach a blocked category."""
    if not excluded:
        return categories
    kept: list[dict[str, Any]] = []
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        slug = str(cat.get("slug") or "")
        name_slug = _slugify_category(html.unescape(str(cat.get("name") or "")))
        if slug in excluded or (name_slug and name_slug in excluded):
            continue
        kept.append(cat)
    return kept


def _effective_counts(categories: list[dict[str, Any]]) -> dict[int, int]:
    """Products *available under* each category, including its descendants.

    WooCommerce's `count` is the number of products assigned DIRECTLY to that
    term — never a subtree total. So a category whose products all live in its
    children reports `count: 0` and reads as out of stock. The same misreading of
    the same field made two sidebar modules render nothing and was cured there in
    v3.42.3 by switching to `get_terms()`; this is the Python half of that fix
    (Rule 11 — a field whose meaning you just corrected has other readers).

    Measured against all 12 catalogs on 2026-08-05, this changes no current
    match: today every category holding products also carries its own non-zero
    count. That is worth stating plainly rather than claiming a fleet-wide win —
    the audit that surfaced this read project-hotel's four zero-count top-level
    categories as miscounted parents, when in truth that site has six products
    total and those subtrees are empty all the way down. The rollup is kept
    because the semantics are right and a nested catalog will hit it; it is not
    kept because it fixed something today.
    """
    by_id = {c["id"]: c for c in categories
             if isinstance(c, dict) and isinstance(c.get("id"), int)}
    eff = {cid: int(c.get("count") or 0) for cid, c in by_id.items()}
    for cid, cat in by_id.items():
        own = int(cat.get("count") or 0)
        if not own:
            continue
        parent, seen = cat.get("parent"), {cid}
        # A malformed catalog can describe a parent cycle; walking it must
        # terminate rather than hang the pipeline.
        while isinstance(parent, int) and parent in by_id and parent not in seen:
            seen.add(parent)
            eff[parent] += own
            parent = by_id[parent].get("parent")
    return eff


def _stocked(cat: dict[str, Any], eff: dict[int, int]) -> bool:
    """True when this category can actually show a product (own or inherited)."""
    cid = cat.get("id")
    if isinstance(cid, int) and cid in eff:
        return eff[cid] > 0
    return (cat.get("count") or 0) > 0


def _find_category_by_key(categories: list[dict[str, Any]], key: str,
                          ) -> dict[str, Any] | None:
    """Resolve a configured default_category (a slug, or a human category name)
    to a category that can actually show products. Slug match first, then a
    slugified-name match, so config can name it either way."""
    if not key:
        return None
    eff = _effective_counts(categories)
    for cat in categories:
        if not isinstance(cat, dict) or not _stocked(cat, eff):
            continue
        if cat.get("slug") == key:
            return cat
        name = cat.get("name")
        if isinstance(name, str) and _slugify_category(html.unescape(name)) == key:
            return cat
    return None


def _ids_shortcode(ids: list[int]) -> str:
    """Return the WooCommerce [products ids=...] shortcode with UNQUOTED
    attribute values (v3.38.0 root cure — see module-level Task 4 note below
    _category_shortcode). `ids` are comma-joined ints, so the value is
    guaranteed free of whitespace/quotes and safe to interpolate bare."""
    joined = ",".join(str(i) for i in ids)
    return f"[products ids={joined} columns=3 orderby=menu_order]"


# Safe WP-term-slug charset for direct interpolation into a shortcode
# attribute value. Defense-in-depth (Task 4 review recommendation, v3.38.0): a
# catalog category slug is normally lowercase/hyphen (WP's default), but this
# module must never trust that blindly — an unexpected slug shape containing
# whitespace, '"', or ']' interpolated unescaped would break the shortcode's
# own attribute parsing or inject stray shortcode syntax. '%' is allowed for
# percent-encoded non-ASCII slugs WP itself generates.
_CATEGORY_SLUG_CHARSET_RE = re.compile(r"^[a-z0-9%-]+$")


def _category_shortcode(slug: str) -> str | None:
    """Return the WooCommerce [products category=...] shortcode, or None if
    `slug` contains any character outside the safe charset — callers must
    treat None as "no shortcode" and surface a warning, never fall back to
    interpolating the raw slug anyway.

    Attributes are emitted UNQUOTED (v3.38.0 root cure, Task 4 follow-up):
    the publisher's markdown->HTML conversion step (markdown-it, html=False)
    HTML-escapes literal `"` characters in plain-text nodes to `&quot;`,
    which breaks WordPress's shortcode_parse_atts() (it requires a LITERAL
    quote character to recognize a name="value" pair -- see
    tests/test_products_shortcode_render_passthrough.py for the full
    mechanics and the confirming proof). WordPress parses unquoted
    `attr=value` tokens (value has no whitespace/quotes) identically to
    quoted ones, and the charset guard above already guarantees this slug
    has no whitespace/quote/bracket characters, so the unquoted form is safe
    by construction — there is nothing left for markdown-it to mis-escape."""
    if not _CATEGORY_SLUG_CHARSET_RE.match(slug):
        return None
    return f"[products category={slug} limit=3 columns=3 orderby=popularity]"


def _build_ecommerce_brief(
    task_id: str, project_slug: str, offers: dict[str, Any], bc: dict[str, Any],
    *, write: bool = False,
) -> dict[str, Any] | None:
    """Resolver for `business_model == "ecommerce"`. Returns None on a
    missing/malformed/empty catalog so main() writes the standard sentinel and
    the pipeline never crashes (same graceful contract as the routing-map path)."""
    catalog_path_str = offers.get("catalog_path")
    if catalog_path_str:
        cp = Path(catalog_path_str)
        catalog_path = cp if cp.is_absolute() else PLUGIN_ROOT / catalog_path_str
    else:
        catalog_path = PLUGIN_ROOT / "projects" / project_slug / "product-catalog.json"

    catalog = _load_json(catalog_path)
    if not isinstance(catalog, dict):
        return None
    products = catalog.get("products")
    categories = catalog.get("categories") or []
    if not isinstance(products, list) or not products:
        return None
    if not isinstance(categories, list):
        categories = []

    body, article_tokens, core_tokens = _article_signal(task_id)
    _state = _load_json(WS_ROOT / task_id / "state.json") or {}
    brief_state = _state.get("brief") or {}

    mode = "fallback"
    _hint_applied = False
    ids: list[int] = []
    product_names: list[str] = []
    category_slug: str | None = None
    shortcode: str | None = None
    warnings: list[str] = []

    # Compliance blocklist applied BEFORE any resolution path (v3.42.3), so
    # neither content matching nor the default_category fallback can reach a
    # category this project forbids merchandising from editorial content.
    excluded = _excluded_category_slugs(offers)
    categories_pre_exclusion = list(categories)
    if excluded:
        before = len(categories)
        categories = _drop_excluded(categories, excluded)
        if len(categories) != before:
            warnings.append(
                f"{before - len(categories)} product categor"
                f"{'y' if before - len(categories) == 1 else 'ies'} suppressed by "
                f"conversion_offers.excluded_categories ({sorted(excluded)})"
            )

    matched = _match_products(products, body)
    # Empty-ids guard (Task 4, v3.38.0): a SKU-verbatim hit only counts as
    # "ids mode" when at least one matched product survives with a valid
    # integer catalog id. A catalog entry with a malformed/missing id (e.g.
    # id as a string, or absent) must not produce an empty `ids=""`
    # shortcode — fall through to category matching instead, same as a
    # genuine no-SKU-match would.
    matched_ids = [p["id"] for p in matched if isinstance(p.get("id"), int)] if matched else []
    if matched and matched_ids:
        mode = "ids"
        ids = matched_ids
        product_names = [html.unescape(str(p.get("name", ""))).strip() for p in matched]
        shortcode = _ids_shortcode(ids)
    else:
        if matched and not matched_ids:
            warnings.append(
                "SKU-verbatim match(es) found in the article body, but none had "
                "a valid integer catalog 'id' -- falling through to category "
                "matching rather than emit an empty [products ids=] shortcode"
            )
        # Operator-designated category (state.brief.cta_category_hint, 2026-08-08):
        # a batch content plan knows the intended product angle ("Ear wash") even
        # when token matching structurally cannot — a one-token category name
        # ('digestion') has no core-hit, and a long name ('Ear, Eye & Skin Care')
        # dilutes below the 0.5 threshold on a single core token. The hint beats
        # content matching but NEVER the compliance rails: it resolves against the
        # post-exclusion, in-stock category list, so an excluded/Rx category hint
        # degrades to the normal matcher with an explicit warning (Rule 12: "it
        # is excluded" and "it does not exist" are different findings).
        cat = None
        hint = str((brief_state.get("cta_category_hint") or "")).strip()
        if hint:
            hint_key = _slugify_category(html.unescape(hint))
            cat = _find_category_by_key(categories, hint_key)
            if cat is not None:
                _hint_applied = True
            else:
                pre_drop = _find_category_by_key(categories_pre_exclusion, hint_key)
                if pre_drop is not None:
                    warnings.append(
                        f"brief.cta_category_hint {hint!r} resolves to an EXCLUDED "
                        f"category ({pre_drop.get('slug')!r}) -- hint refused, "
                        "falling back to content matching"
                    )
                else:
                    warnings.append(
                        f"brief.cta_category_hint {hint!r} matches no stocked "
                        "catalog category -- falling back to content matching"
                    )
        if cat is None:
            cat = _match_category(categories, article_tokens, core_tokens=core_tokens)
        if cat is not None:
            category_slug = cat["slug"]
            shortcode = _category_shortcode(category_slug)
            if shortcode is not None:
                mode = "category"
            else:
                warnings.append(
                    f"category slug {category_slug!r} rejected by the shortcode "
                    f"charset guard (^[a-z0-9%-]+$) -- shortcode suppressed"
                )
        else:
            # Fallback: a configured default_category (if it exists in-stock),
            # else a link-only brief to the shop with NO shortcode.
            default_key = offers.get("default_category")
            default_cat = _find_category_by_key(categories, str(default_key)) if default_key else None
            if default_cat is not None:
                category_slug = default_cat["slug"]
                shortcode = _category_shortcode(category_slug)
                if shortcode is None:
                    warnings.append(
                        f"default_category slug {category_slug!r} rejected by "
                        f"the shortcode charset guard (^[a-z0-9%-]+$) -- "
                        f"shortcode suppressed"
                    )

    # target_url must stay null whenever a shortcode was resolved (Finding 1,
    # v3.38 review): the whole downstream chain (cta-writer: no link when a
    # grid is present; cta_injector: link-waiver with shortcode; verify_post
    # check 29: "target_url is null for catalog-category ecommerce briefs")
    # assumes a shortcode-bearing brief has no target_url. Only the pure
    # fallback path (no shortcode resolved at all) carries fallback_url
    # through as target_url — that's what makes it a usable offer with a real
    # link. Setting both would make check 29 run its URL sub-check against a
    # CTA that (correctly) renders a product grid with no href, hard-failing
    # every grid-bearing ecommerce CTA.
    fallback_url = offers.get("fallback_url")
    target_url = (
        fallback_url if isinstance(fallback_url, str) and fallback_url and shortcode is None
        else None
    )

    company = bc.get("company") or {}
    team = company.get("team") or []
    proof_points = company.get("proof_points") or []
    constraints = offers.get("constraints")
    if not isinstance(constraints, dict):
        constraints = {}

    brief: dict[str, Any] = {
        "task_id": task_id,
        "business_model": "ecommerce",
        "blog_category": _article_category(task_id),
        # No blog-category routing on the ecommerce path (matching is content-based),
        # so category_source is null — same debuggability convention as the b2b
        # path's "no candidate resolved" case. resolved_products.mode carries the
        # ecommerce match-strategy provenance instead.
        "category_source": None,
        "resolved_service": None,
        "resolved_products": {
            "mode": mode,
            "ids": ids,
            "category_slug": category_slug,
            "product_names": product_names,
            "shortcode": shortcode,
            # Provenance: True when the category came from the operator's
            # brief.cta_category_hint rather than content matching (2026-08-08).
            **({"category_from_hint": True} if _hint_applied else {}),
            **({"warning": "; ".join(warnings)} if warnings else {}),
        },
        "constraints": constraints,
        "target_url": target_url,
        # No b2b service slug exists on the ecommerce path — `mode` ("ids" /
        # "category" / "fallback") is a match-strategy label, not a service
        # slug, and passing it through would risk a literal string collision
        # against a real b2b service's specialty_services (e.g. a project
        # that names a service slug "category"). Finding 2, v3.38 review.
        "matched_team_member": _match_team_member(team, None),
        "matched_proof_points": _match_proof_points(proof_points, None),
        "fallback_used": mode == "fallback",
        "_generated_by": "cta-brief-builder",
        "generated_at": _now_iso(),
    }

    if write:
        _write_brief(task_id, brief)
    return brief


def _sentinel_brief(task_id: str) -> dict[str, Any]:
    """No-config sentinel written when build_brief() resolves nothing.

    cta-brief-builder MUST always write cta-brief.json (Finding 1): the
    orchestrator Stage has expected_outputs=["cta-brief.json"] and no
    conditional guard, so an absent file fails verify_stage() and hard-halts
    the pipeline before cta-injection for every project without a
    conversion_offers config. The sentinel's content (resolved_service=null,
    skipped_no_config=true) makes cta_brief_present derive False downstream, so
    cta-writer is skipped, not dispatched."""
    return {
        "task_id": task_id,
        "blog_category": _article_category(task_id),
        "category_source": None,
        "resolved_service": None,
        "target_url": None,
        "matched_team_member": None,
        "matched_proof_points": [],
        "fallback_used": True,
        "skipped_no_config": True,
        "_generated_by": "cta-brief-builder",
        "generated_at": _now_iso(),
    }


def _resolution_failure_reason(project_slug: str) -> str | None:
    """Why a configured project still resolved nothing — or None if unconfigured.

    "This project sells nothing" and "this project sells things and I could not
    reach them" are opposite facts, and until v3.42.4 both were written as
    `skipped_no_config: true`. The orchestrator reads that flag to auto-skip four
    CTA stages and then reports the pipeline COMPLETE, so a client site whose
    product catalog had silently synced empty published every article with no CTA
    at all, while the console printed "no conversion_offers config" — a diagnosis
    that was not merely unhelpful but false. Return a concrete cause so the caller
    can fail loudly instead of skipping quietly.
    """
    bc = _load_json(PLUGIN_ROOT / "projects" / project_slug / "business-context.json")
    offers = bc.get("conversion_offers") if isinstance(bc, dict) else None
    if not isinstance(offers, dict) or not offers:
        return None                      # genuinely unconfigured: a real skip

    cat_path = PLUGIN_ROOT / "projects" / project_slug / "product-catalog.json"
    if not cat_path.exists():
        return (f"conversion_offers is configured but {cat_path.name} is missing — "
                f"run: python -m scripts.wordpress.wc_catalog_sync {project_slug}")
    catalog = _load_json(cat_path)
    products = catalog.get("products") if isinstance(catalog, dict) else None
    if not isinstance(products, list) or not products:
        return (f"conversion_offers is configured but the product catalog is EMPTY "
                f"(products=0, synced {catalog.get('synced_at') or 'unknown'}). "
                f"An empty catalog for an ecommerce project is a broken sync, not a "
                f"project without offers — re-run wc_catalog_sync and check the "
                f"WooCommerce credentials.")
    return ("conversion_offers is configured and the catalog has products, but no "
            "category could be resolved for this article. Check "
            "conversion_offers.default_category against the catalog's slugs.")


def _write_brief(task_id: str, brief: dict[str, Any]) -> None:
    ws = WS_ROOT / task_id
    ws.mkdir(parents=True, exist_ok=True)
    (ws / RESULT_FILENAME).write_text(
        json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")


def build_brief(task_id: str, project_slug: str, *, write: bool = False) -> dict[str, Any] | None:
    bc_path = PLUGIN_ROOT / "projects" / project_slug / "business-context.json"
    bc = _load_json(bc_path)
    if not bc:
        return None
    offers = bc.get("conversion_offers")
    if not isinstance(offers, dict):
        return None
    if offers.get("business_model") == "ecommerce":
        return _build_ecommerce_brief(task_id, project_slug, offers, bc, write=write)
    if offers.get("business_model") != "b2b_services":
        return None
    services = offers.get("services") or []
    if not services:
        return None

    routing_map_path = PLUGIN_ROOT / offers["category_routing_map"] if offers.get(
        "category_routing_map") else None
    routing_map = _load_json(routing_map_path) if routing_map_path else {}
    routing_map = routing_map or {}

    candidates = _category_candidates(task_id)
    slug, matched_category, category_source, fallback_used = _resolve_service_slug_multi(
        project_slug, candidates, routing_map)
    if slug is None:
        # Fallback default: first service flagged for seo-consulting-style
        # generic advisory, else the first service in the catalog.
        default = _find_service(services, "seo-consulting") or services[0]
        slug = default["slug"]

    service = _find_service(services, slug) or services[0]
    company = bc.get("company") or {}
    team = company.get("team") or []
    proof_points = company.get("proof_points") or []

    brief: dict[str, Any] = {
        "task_id": task_id,
        # matched_category is the candidate that actually resolved the routing-map
        # hit (may be a later candidate than the first, or from meta.json rather
        # than state); falls back to the first candidate (informational only,
        # non-authoritative) when nothing resolved.
        "blog_category": matched_category if matched_category is not None else _article_category(task_id),
        "category_source": category_source,
        "resolved_service": service,
        "target_url": service["url"],
        "matched_team_member": _match_team_member(team, slug),
        "matched_proof_points": _match_proof_points(proof_points, slug),
        "fallback_used": fallback_used,
        "_generated_by": "cta-brief-builder",
        "generated_at": _now_iso(),
    }

    if write:
        _write_brief(task_id, brief)

    return brief


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve the CTA fact brief for an article")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--project-slug", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    brief = build_brief(args.task_id, args.project_slug, write=True)
    if brief is None:
        # Finding 1: even with no conversion_offers config, ALWAYS write a
        # sentinel cta-brief.json so the orchestrator stage completes and the
        # pipeline advances to cta-injection instead of hard-halting on a
        # missing expected output.
        sentinel = _sentinel_brief(args.task_id)
        reason = _resolution_failure_reason(args.project_slug)
        if reason:
            # Configured project, unresolvable offers. Still WRITE the artifact —
            # its absence hard-halts the pipeline before cta-injection — but do
            # not let it claim "no config", and exit non-zero so the runner
            # surfaces ERROR with the cause instead of skipping four CTA stages
            # and reporting COMPLETE.
            sentinel["skipped_no_config"] = False
            sentinel["resolution_failed"] = True
            sentinel["resolution_failure_reason"] = reason
        _write_brief(args.task_id, sentinel)
        if args.json:
            print(json.dumps(sentinel, indent=2, ensure_ascii=False))
        elif reason:
            print(f"cta_brief_builder: RESOLUTION FAILED — {reason}", file=sys.stderr)
        else:
            print("cta_brief_builder: no conversion_offers config; wrote sentinel "
                  "cta-brief.json (skipped_no_config=true, cta-writer will be skipped)")
        return 1 if reason else 0

    if args.json:
        print(json.dumps(brief, indent=2, ensure_ascii=False))
    else:
        print(f"cta_brief_builder: resolved service={brief['resolved_service']['slug']} "
              f"fallback={brief['fallback_used']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
