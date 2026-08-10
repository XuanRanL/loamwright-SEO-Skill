"""
scripts/wordpress/wc_catalog_sync.py — read-only WooCommerce product-catalog sync.

CLI:
    python -m scripts.wordpress.wc_catalog_sync --project-slug {slug} [--json]

Fetches every publish-status product (paginated) plus all product categories
from the site's WooCommerce REST API (``/wc/v3``) via ``WPClient``, trims
``short_description`` to <=200 chars with HTML tags stripped, and writes
``projects/{slug}/product-catalog.json``.

This is the ONLY network-touching piece of the v3.38.0 ecommerce-CTA feature
(design: docs/superpowers/plans/2026-07-09-cta-completion-plan.md Task 2/3).
``cta_brief_builder.py``'s ecommerce resolver reads the cached file this
script produces — never the live API — so the LLM pipeline stays offline.

Pagination gotcha (same pattern as scripts/wordpress/fix_founder_name.py):
WordPress/WooCommerce list endpoints return HTTP 400 for a page requested
PAST the last one — NOT an empty list. We terminate the normal way on a SHORT
page (``len(page) < per_page``), but we ALSO tolerate the 400-past-last-page
case (it fires when the total item count happens to be an exact multiple of
``per_page``, so the "short page" signal never arrives) by catching a 400 on
any page after the first and treating it as end-of-results. A 400 on the
FIRST page is a real failure (bad params / wc/v3 unreachable) and is raised.

Atomicity: the full catalog dict is built ENTIRELY in memory and sanity- and
schema-validated before a single byte is written. On ANY failure (network,
non-2xx after the tolerated case above, malformed response body, schema
validation failure) the function raises and the existing
``product-catalog.json`` (if any) is left completely untouched — the write
step is a single ``file_lock.atomic_write_text`` call that only ever runs
after every prior step already succeeded.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from scripts.wordpress.wp_client import WPApiError

PLUGIN_ROOT = Path(__file__).resolve().parents[2]

PRODUCTS_PER_PAGE = 50
CATEGORIES_PER_PAGE = 100
SHORT_DESC_MAX_LEN = 200

PRODUCT_FIELDS = (
    "id,name,slug,permalink,status,categories,price,stock_status,short_description"
)
CATEGORY_FIELDS = "id,name,slug,count,parent"


# ─── WPClient protocol (duck-typing for tests) ────────────────────────────────

class _WPLike(Protocol):
    """Minimal interface consumed by this module — satisfied by WPClient and test stubs."""

    def get(self, path: str, **kwargs: Any) -> Any:
        ...


# ─── short_description trimming ───────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def trim_short_description(raw: str | None, *, max_len: int = SHORT_DESC_MAX_LEN) -> str:
    """Strip HTML tags (simple regex — WC-controlled field, not untrusted user
    input needing full sanitization), collapse whitespace, and hard-cut to
    ``max_len`` chars.

    Tags are replaced with a single space (not deleted outright) so adjacent
    block elements like ``<p>Hello</p><p>World</p>`` don't glue into
    "HelloWorld" once the tags disappear.
    """
    if not raw:
        return ""
    no_tags = _TAG_RE.sub(" ", raw)
    collapsed = _WS_RE.sub(" ", no_tags).strip()
    return collapsed[:max_len]


# ─── Pagination ────────────────────────────────────────────────────────────────

def _paginate(
    wp: _WPLike, path: str, *, per_page: int, fixed_params: dict[str, Any]
) -> list[dict[str, Any]]:
    """Generic paginated GET helper for ``/wc/v3`` list endpoints.

    Terminates on a short page (``len(page) < per_page``) OR on an HTTP 400
    raised for a page beyond the first (see module docstring). A 400 on the
    first page is a real failure and is re-raised.
    """
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        params: dict[str, Any] = dict(fixed_params)
        params["per_page"] = per_page
        params["page"] = page
        try:
            resp = wp.get(path, params=params)
        except WPApiError as exc:
            if page > 1 and exc.status == 400:
                break
            raise
        batch = resp.json_data
        if batch is None:
            batch = []
        if not isinstance(batch, list):
            raise RuntimeError(
                f"{path} page {page} returned a non-list body "
                f"({type(batch).__name__}); refusing to treat as valid data"
            )
        items.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return items


def fetch_all_products(
    wp: _WPLike, *, per_page: int = PRODUCTS_PER_PAGE
) -> list[dict[str, Any]]:
    """Paginated GET ``/wc/v3/products``, publish-status only, ``_fields``-trimmed."""
    return _paginate(
        wp,
        "/wc/v3/products",
        per_page=per_page,
        fixed_params={"status": "publish", "_fields": PRODUCT_FIELDS},
    )


def fetch_all_categories(
    wp: _WPLike, *, per_page: int = CATEGORIES_PER_PAGE
) -> list[dict[str, Any]]:
    """Paginated GET ``/wc/v3/products/categories``, ``_fields``-trimmed."""
    return _paginate(
        wp,
        "/wc/v3/products/categories",
        per_page=per_page,
        fixed_params={"_fields": CATEGORY_FIELDS},
    )


# ─── Normalization ─────────────────────────────────────────────────────────────

def _normalize_product(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "name": raw.get("name", "") or "",
        "slug": raw.get("slug", "") or "",
        "permalink": raw.get("permalink", "") or "",
        "status": raw.get("status", "") or "",
        "categories": raw.get("categories") or [],
        "price": raw.get("price", "") or "",
        "stock_status": raw.get("stock_status", "") or "",
        "short_description": trim_short_description(raw.get("short_description")),
    }


def _normalize_category(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "name": raw.get("name", "") or "",
        "slug": raw.get("slug", "") or "",
        "count": raw.get("count", 0) or 0,
        "parent": raw.get("parent", 0) or 0,
    }


# ─── Build + validate (pure — no filesystem I/O) ──────────────────────────────

def build_catalog(wp: _WPLike, *, project_slug: str) -> dict[str, Any]:
    """Fetch products + categories and assemble the full catalog dict IN MEMORY.

    No filesystem write happens here — the caller decides when/whether to
    persist, so any fetch failure never touches disk.
    """
    raw_products = fetch_all_products(wp)
    raw_categories = fetch_all_categories(wp)

    products = [_normalize_product(p) for p in raw_products if isinstance(p, dict)]
    categories = [_normalize_category(c) for c in raw_categories if isinstance(c, dict)]

    return {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "project_slug": project_slug,
        "product_count": len(products),
        "category_count": len(categories),
        "categories": categories,
        "products": products,
        "_generated_by": "wc-catalog-sync",
    }


def _validate_catalog(catalog: dict[str, Any]) -> None:
    """Validate the built catalog is well-formed BEFORE it's ever written.

    Two layers: (1) internal shape/count sanity (fast, always available) and
    (2) full JSON-Schema validation against
    ``schemas/product-catalog.schema.json`` when present.

    Note: a catalog with ``product_count == 0`` is NOT treated as invalid — a
    brand-new/empty store is a legitimate real-world state. What this guards
    against is a malformed/corrupt in-memory build (wrong types, mismatched
    counts), not an empty-but-well-formed one.
    """
    products = catalog.get("products")
    categories = catalog.get("categories")
    if not isinstance(products, list) or not isinstance(categories, list):
        raise ValueError("catalog 'products'/'categories' must be lists")
    if catalog.get("product_count") != len(products):
        raise ValueError("product_count does not match products array length")
    if catalog.get("category_count") != len(categories):
        raise ValueError("category_count does not match categories array length")
    if catalog.get("_generated_by") != "wc-catalog-sync":
        raise ValueError("catalog missing/incorrect _generated_by marker")

    schema_file = PLUGIN_ROOT / "schemas" / "product-catalog.schema.json"
    if schema_file.exists():
        import jsonschema

        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        jsonschema.validate(catalog, schema)


# ─── Sync (fetch -> validate -> atomic write) ─────────────────────────────────

def sync_catalog(
    wp: _WPLike, *, project_slug: str, out_path: Path
) -> dict[str, Any]:
    """Full sync: fetch, validate, THEN a single atomic write.

    On ANY failure, raises WITHOUT touching ``out_path`` — the existing file
    (if any) is left completely untouched. Only a fully-built, validated
    catalog ever reaches the write step.
    """
    catalog = build_catalog(wp, project_slug=project_slug)
    _validate_catalog(catalog)

    from scripts._core import file_lock

    file_lock.atomic_write_text(
        out_path, json.dumps(catalog, indent=2, ensure_ascii=False)
    )
    return catalog


# ─── CLI entry point ───────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only WooCommerce (/wc/v3) product-catalog sync. Writes "
            "projects/{slug}/product-catalog.json. Never touches the existing "
            "file on failure (validated fully in memory, then one atomic write)."
        )
    )
    parser.add_argument("--project-slug", required=True, metavar="SLUG")
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Emit a single JSON line to stdout",
    )
    args = parser.parse_args()

    project_slug: str = args.project_slug
    json_output: bool = args.json_output
    out_path = PLUGIN_ROOT / "projects" / project_slug / "product-catalog.json"

    try:
        from scripts.wordpress.wp_client import WPClient  # lazy import to avoid creds load on module import

        wp = WPClient(project_slug)
        try:
            catalog = sync_catalog(wp, project_slug=project_slug, out_path=out_path)
        finally:
            close = getattr(wp, "close", None)
            if callable(close):
                close()
    except Exception as exc:
        result: dict[str, Any] = {
            "success": False,
            "project_slug": project_slug,
            "error": f"{type(exc).__name__}: {exc}",
            "path": str(out_path),
        }
        if json_output:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(
                f"ERROR: wc_catalog_sync failed for {project_slug}: {exc}",
                file=sys.stderr,
            )
        return 1

    result = {
        "success": True,
        "project_slug": project_slug,
        "product_count": catalog["product_count"],
        "category_count": catalog["category_count"],
        "path": str(out_path),
    }
    if json_output:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(
            f"wc_catalog_sync: {project_slug}: {catalog['product_count']} products, "
            f"{catalog['category_count']} categories -> {out_path}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
