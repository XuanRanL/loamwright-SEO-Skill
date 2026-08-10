"""
scripts/wordpress/wp_taxonomy.py — WordPress categories + tags discovery / create.

Operations:
  - list_all(taxonomy)                    → fetch all (pages until done)
  - find_by_slug(taxonomy, slug)
  - find_by_name(taxonomy, name)
  - create(taxonomy, name, slug?, description?, parent?) → new term ID
  - get_or_create(taxonomy, names)        → bulk resolve, create missing
  - bulk_create_with_dedup(taxonomy, names) → idempotent batch

Cache: results saved to projects/{slug}/.seo/wp-taxonomy-cache.json (24h TTL).

This is what the user asked about:
  "获取wordpress blog Category, tags"  → list_all() + find_by_*
  "写入tags"                            → create() / get_or_create()

Used by:
  - wp_publisher.py during publish step
  - /list-projects --refresh-taxonomy command (for quick inspection)

CLI:
    python -m scripts.wordpress.wp_taxonomy example-com --list-categories
    python -m scripts.wordpress.wp_taxonomy example-com --list-tags
    python -m scripts.wordpress.wp_taxonomy example-com --resolve-tags "fishing,rods,2026"
    python -m scripts.wordpress.wp_taxonomy example-com --resolve-categories "Buying Guides"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from scripts.wordpress.wp_client import WPClient, WPApiError, WPNotFoundError


# Taxonomy literal type for type-safety
Taxonomy = Literal["categories", "tags"]

CACHE_TTL_SECONDS: int = 24 * 3600


# ─── Data types ────────────────────────────────────────────

@dataclass(frozen=True)
class WPTerm:
    """A category or tag from WordPress."""
    id: int
    name: str
    slug: str
    description: str
    count: int                    # how many posts use this term
    parent: int                    # 0 for top-level (categories only)
    taxonomy: str                  # "categories" | "tags"


@dataclass
class TaxonomyCache:
    """Per-site cache of taxonomy terms."""
    site_slug: str
    fetched_at: float
    categories: list[WPTerm] = field(default_factory=list)
    tags: list[WPTerm] = field(default_factory=list)

    def is_stale(self) -> bool:
        return (time.time() - self.fetched_at) > CACHE_TTL_SECONDS


# ─── Cache I/O ────────────────────────────────────────────

def _cache_path(site_slug: str) -> Path:
    """Path to taxonomy cache file (lives in projects/{slug}/.seo/)."""
    from scripts._core.file_bus import PLUGIN_ROOT
    cache = PLUGIN_ROOT / "projects" / site_slug / ".seo" / "wp-taxonomy-cache.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    return cache


def load_cache(site_slug: str) -> TaxonomyCache | None:
    p = _cache_path(site_slug)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        cats = [WPTerm(**t) for t in data.get("categories", [])]
        tags = [WPTerm(**t) for t in data.get("tags", [])]
        return TaxonomyCache(
            site_slug=site_slug,
            fetched_at=data.get("fetched_at", 0),
            categories=cats,
            tags=tags,
        )
    except Exception as e:
        # Audit 2026-05-22 P1 — log silent-fallback
        print(
            f"⚠ taxonomy cache load failed for site_slug={site_slug!r}: "
            f"{type(e).__name__}: {e} — fresh fetch required",
            file=sys.stderr,
        )
        return None


def save_cache(cache: TaxonomyCache) -> None:
    p = _cache_path(cache.site_slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "site_slug": cache.site_slug,
        "fetched_at": cache.fetched_at,
        "categories": [asdict(c) for c in cache.categories],
        "tags": [asdict(t) for t in cache.tags],
    }, indent=2, ensure_ascii=False), encoding="utf-8")


# ─── Discovery ────────────────────────────────────────────

def list_all(client: WPClient, taxonomy: Taxonomy) -> list[WPTerm]:
    """Fetch all terms for a taxonomy, paginating through all pages.

    WP REST returns max 100 per page; we walk x-wp-totalpages header.
    """
    endpoint = f"/wp/v2/{taxonomy}"
    page = 1
    per_page = 100
    results: list[WPTerm] = []

    while True:
        r = client.get(endpoint, params={"page": page, "per_page": per_page, "hide_empty": False})
        if not isinstance(r.json_data, list):
            break
        for item in r.json_data:
            results.append(WPTerm(
                id=item["id"],
                name=item["name"],
                slug=item["slug"],
                description=item.get("description", ""),
                count=item.get("count", 0),
                parent=item.get("parent", 0),
                taxonomy=taxonomy,
            ))
        total_pages = int(r.headers.get("x-wp-totalpages", "1"))
        if page >= total_pages:
            break
        page += 1

    return results


def refresh_cache(client: WPClient, site_slug: str) -> TaxonomyCache:
    """Fetch fresh categories + tags, save cache."""
    cats = list_all(client, "categories")
    tags = list_all(client, "tags")
    cache = TaxonomyCache(
        site_slug=site_slug,
        fetched_at=time.time(),
        categories=cats,
        tags=tags,
    )
    save_cache(cache)
    return cache


def get_cache_or_refresh(client: WPClient, site_slug: str, *, force: bool = False) -> TaxonomyCache:
    if not force:
        cache = load_cache(site_slug)
        if cache and not cache.is_stale():
            return cache
    return refresh_cache(client, site_slug)


# ─── Find by slug/name ────────────────────────────────────

def find_by_slug(cache: TaxonomyCache, taxonomy: Taxonomy, slug: str) -> WPTerm | None:
    slug = slug.lower().strip()
    terms = cache.categories if taxonomy == "categories" else cache.tags
    for t in terms:
        if t.slug.lower() == slug:
            return t
    return None


def _norm_name(s: str) -> str:
    """Normalize a taxonomy name for matching: HTML-unescape + collapse whitespace + lowercase.

    WordPress returns term names HTML-entity-encoded (e.g. ``Drying, Storage &amp; Handling``),
    but callers query with the literal characters (``Drying, Storage & Handling``). Without
    unescaping, every name containing ``&`` / ``<`` / ``>`` / ``'`` / ``"`` fails the exact
    match, falls through to ``create()``, and mints a DUPLICATE top-level category — the
    2026-06-21 project-kilo bug (orphans 351/352/367/440/507/529). Unescaping both sides makes
    name resolution robust for every project, not just those whose slug happens to match.
    """
    import html
    return " ".join(html.unescape(s).split()).lower()


def find_by_name(cache: TaxonomyCache, taxonomy: Taxonomy, name: str) -> WPTerm | None:
    """Case-insensitive, HTML-entity-normalized name match.

    When more than one term normalizes to the same name (e.g. a canonical child category
    plus a stray top-level duplicate), prefer the lowest id (created first / canonical) so a
    duplicate cannot shadow the original.
    """
    name_n = _norm_name(name)
    terms = cache.categories if taxonomy == "categories" else cache.tags
    matches = [t for t in terms if _norm_name(t.name) == name_n]
    if not matches:
        return None
    return min(matches, key=lambda t: t.id)


# ─── Create ──────────────────────────────────────────────

def create(
    client: WPClient,
    taxonomy: Taxonomy,
    name: str,
    *,
    slug: str | None = None,
    description: str = "",
    parent: int = 0,
) -> WPTerm:
    """Create a new term. Returns the created WPTerm."""
    if not name.strip():
        raise ValueError("Term name cannot be empty")

    payload: dict = {"name": name.strip(), "description": description}
    if slug:
        payload["slug"] = slug.strip()
    if taxonomy == "categories" and parent:
        payload["parent"] = parent

    try:
        r = client.post(f"/wp/v2/{taxonomy}", json_body=payload)
    except WPApiError as e:
        # WP returns 400 with code 'term_exists' if duplicate
        if e.status == 400 and "exists" in str(e.message).lower():
            # Refetch and find (HTML-entity-normalized, so '&amp;' names resolve)
            terms = list_all(client, taxonomy)
            name_n = _norm_name(name)
            for t in terms:
                if _norm_name(t.name) == name_n:
                    return t
        raise

    if r.status not in (200, 201):
        raise WPApiError(r.status, f"Unexpected status creating {taxonomy}")

    return WPTerm(
        id=r.json_data["id"],
        name=r.json_data["name"],
        slug=r.json_data["slug"],
        description=r.json_data.get("description", ""),
        count=r.json_data.get("count", 0),
        parent=r.json_data.get("parent", 0),
        taxonomy=taxonomy,
    )


# ─── Get-or-create (bulk) ──────────────────────────────

def get_or_create_terms(
    client: WPClient,
    site_slug: str,
    taxonomy: Taxonomy,
    names: list[str],
    *,
    create_missing: bool = True,
    refresh_cache_on_miss: bool = True,
) -> tuple[list[WPTerm], list[str]]:
    """Resolve a list of term names to WPTerms; create missing if requested.

    Returns:
        (resolved_terms, names_that_couldnt_resolve)
    """
    cache = get_cache_or_refresh(client, site_slug)
    resolved: list[WPTerm] = []
    missing: list[str] = []

    for name in names:
        name = name.strip()
        if not name:
            continue
        # NAME-FIRST resolution (2026-07-01). The caller passes display NAMES from
        # meta.json, so the HTML-entity-aware exact-name match is authoritative.
        # slugify(name) is only a heuristic FALLBACK for slug-like inputs: the old
        # slug-first order let slugify("Link Building & Digital PR") =
        # "link-building-digital-pr" hit the CHILD term "Digital PR" (whose real slug
        # is exactly that) before the entity-aware name match for the pillar (slug
        # "link-building") ever ran — post 788 landed in the wrong subcategory. A
        # display name's slugification matching a DIFFERENT term's slug is a
        # collision, not a resolution.
        t = find_by_name(cache, taxonomy, name)
        if not t:
            from slugify import slugify
            t = find_by_slug(cache, taxonomy, slugify(name))
        if t:
            resolved.append(t)
        else:
            missing.append(name)

    if missing and create_missing:
        created = []
        for name in missing:
            try:
                term = create(client, taxonomy, name)
                resolved.append(term)
                created.append(term)
            except Exception as e:
                # leave in missing list
                continue
        # Refresh cache so future calls see new terms
        if created and refresh_cache_on_miss:
            refresh_cache(client, site_slug)
        # Recompute missing after creation attempts. WP echoes created names
        # entity-ENCODED (&amp;), so compare via _norm_name — raw .lower() left every
        # freshly created &-name in `missing` (same disease as the find_by_name bug).
        created_names = {_norm_name(c.name) for c in created}
        missing = [m for m in missing if _norm_name(m) not in created_names]

    return resolved, missing


# ─── CLI ─────────────────────────────────────────────────

def _print_terms(terms: list[WPTerm], limit: int = 50) -> None:
    for t in terms[:limit]:
        print(f"  [{t.id:4d}]  {t.name:40s}  slug={t.slug:30s}  count={t.count}")
    if len(terms) > limit:
        print(f"  ... and {len(terms) - limit} more")


def main() -> int:
    ap = argparse.ArgumentParser(description="WP taxonomy (categories/tags) operations")
    ap.add_argument("site_slug", help="Project slug (must have wordpress/<slug>.json credentials)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list-categories", action="store_true")
    g.add_argument("--list-tags", action="store_true")
    g.add_argument("--resolve-tags", help="Comma-separated tag names to resolve/create")
    g.add_argument("--resolve-categories", help="Comma-separated category names to resolve/create")
    g.add_argument("--refresh", action="store_true", help="Force refresh cache")
    ap.add_argument("--no-create", action="store_true", help="Don't create missing terms (resolve only)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--allow-http", action="store_true", help="Allow http:// WP site (testing only)")
    args = ap.parse_args()

    try:
        wp = WPClient(args.site_slug, allow_http_for_testing=args.allow_http)
    except Exception as e:
        print(f"Error initializing WP client: {e}", file=sys.stderr)
        return 2

    with wp:
        if args.refresh:
            cache = refresh_cache(wp, args.site_slug)
            print(f"Refreshed: {len(cache.categories)} categories, {len(cache.tags)} tags")
            return 0

        if args.list_categories:
            cache = get_cache_or_refresh(wp, args.site_slug)
            if args.json:
                print(json.dumps([asdict(t) for t in cache.categories], indent=2, ensure_ascii=False))
            else:
                print(f"Categories ({len(cache.categories)}):")
                _print_terms(cache.categories)
            return 0

        if args.list_tags:
            cache = get_cache_or_refresh(wp, args.site_slug)
            if args.json:
                print(json.dumps([asdict(t) for t in cache.tags], indent=2, ensure_ascii=False))
            else:
                print(f"Tags ({len(cache.tags)}):")
                _print_terms(cache.tags)
            return 0

        if args.resolve_tags:
            names = [n.strip() for n in args.resolve_tags.split(",") if n.strip()]
            resolved, missing = get_or_create_terms(
                wp, args.site_slug, "tags", names,
                create_missing=not args.no_create,
            )
            if args.json:
                print(json.dumps({
                    "resolved": [asdict(t) for t in resolved],
                    "missing": missing,
                }, indent=2, ensure_ascii=False))
            else:
                print(f"Resolved {len(resolved)}/{len(names)} tags:")
                for t in resolved:
                    print(f"  [{t.id}]  {t.name}  (slug: {t.slug})")
                if missing:
                    print(f"Missing/failed ({len(missing)}): {missing}")
            return 0 if not missing else 1

        if args.resolve_categories:
            names = [n.strip() for n in args.resolve_categories.split(",") if n.strip()]
            resolved, missing = get_or_create_terms(
                wp, args.site_slug, "categories", names,
                create_missing=not args.no_create,
            )
            if args.json:
                print(json.dumps({
                    "resolved": [asdict(t) for t in resolved],
                    "missing": missing,
                }, indent=2, ensure_ascii=False))
            else:
                print(f"Resolved {len(resolved)}/{len(names)} categories:")
                for t in resolved:
                    print(f"  [{t.id}]  {t.name}  (slug: {t.slug})")
                if missing:
                    print(f"Missing/failed ({len(missing)}): {missing}")
            return 0 if not missing else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
