"""scripts/build/schema_jsonld_builder.py — Build JSON-LD @graph for SEO article.

Generates:
  - Article (or BlogPosting / NewsArticle)
  - Organization
  - Person (author)
  - BreadcrumbList
  - Format-specific: ItemList (listicle) / Review (review) / FAQPage (FAQ) / etc.

All schemas linked via @id references (per seo-geo @graph linking best practice).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


ArticleType = Literal["Article", "BlogPosting", "NewsArticle"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_jsonld(
    *,
    url: str,
    title: str,
    description: str,
    article_type: ArticleType = "BlogPosting",
    published_date: str | None = None,
    modified_date: str | None = None,
    author_name: str = "Editorial Team",
    author_url: str | None = None,
    author_job_title: str | None = None,
    org_name: str = "",
    org_url: str = "",
    org_logo_url: str = "",
    org_sameas: list[str] | None = None,
    image_url: str = "",
    image_width: int = 1536,
    image_height: int = 1024,
    primary_keyword: str | None = None,
    format_id: str | None = None,
    faq_items: list[dict] | None = None,
    review_items: list[dict] | None = None,
    breadcrumbs: list[dict] | None = None,
    # v3.4.0 local-SEO additions (audit 2026-05-22) — read from
    # business-context.json :: location.* + state.brief.location_anchor.
    # See references/local/industry-to-schema-mapping.md for the full model.
    business_archetype: str | None = None,         # A | B | C | D | E
    business_schema_org_type: str | None = None,    # e.g. "Dentist", "OnlineStore", "LegalService"
    business_additional_type: str | None = None,    # ProductOntology URL for niche industries
    business_nap: dict | None = None,               # {business_name, address: {...}, telephone, email}
    business_gbp: dict | None = None,               # {profile_url, place_id}
    business_ymyl_flag: bool = False,
    business_service_areas: dict | None = None,     # for archetype B/C
    local_mode: bool = False,
    location_anchor: dict | None = None,            # {type, canonical, name_full, containing_state, ...}
    local_article_pattern: str | None = None,       # "service_area" | "spatial_coverage"
) -> dict:
    """Build complete JSON-LD @graph payload.

    Args:
        url: Canonical URL of the page.
        title: Article headline.
        description: Meta description / excerpt.
        article_type: Article / BlogPosting / NewsArticle
        published_date / modified_date: ISO 8601 (default now)
        author_*: author info
        org_*: organization info
        image_*: cover image
        format_id: from 24 formats catalog — drives additional schema types
        faq_items: [{question, answer}, ...] for FAQPage
        review_items: for review-format ItemList
        breadcrumbs: [{name, url}, ...] for BreadcrumbList

    Returns:
        Full @graph JSON-LD dict.
    """
    pub = published_date or _now_iso()
    mod = modified_date or pub

    article_id = f"{url}#article"
    org_id = f"{org_url}#organization" if org_url else f"{url}#organization"
    person_id = f"{author_url}#person" if author_url else f"{url}#author"
    image_id = f"{url}#primaryimage"

    graph: list[dict] = []

    # Article / BlogPosting node
    article_node: dict = {
        "@type": article_type,
        "@id": article_id,
        "headline": title,
        "name": title,
        "description": description,
        "url": url,
        "datePublished": pub,
        "dateModified": mod,
        "inLanguage": "en-US",
        "isPartOf": {"@id": f"{org_url}/#website"} if org_url else None,
        "author": {"@id": person_id},
        "publisher": {"@id": org_id},
    }
    if image_url:
        article_node["image"] = {"@id": image_id}
        article_node["primaryImageOfPage"] = {"@id": image_id}
    if primary_keyword:
        article_node["keywords"] = primary_keyword
    # Drop None values
    article_node = {k: v for k, v in article_node.items() if v is not None}
    graph.append(article_node)

    # Person (author)
    person_node: dict = {
        "@type": "Person",
        "@id": person_id,
        "name": author_name,
        "url": author_url or f"{url}#author",
    }
    if author_job_title:
        person_node["jobTitle"] = author_job_title
    graph.append(person_node)

    # Organization
    if org_name:
        org_node: dict = {
            "@type": "Organization",
            "@id": org_id,
            "name": org_name,
            "url": org_url or "",
        }
        if org_logo_url:
            org_node["logo"] = {
                "@type": "ImageObject",
                "url": org_logo_url,
            }
        if org_sameas:
            org_node["sameAs"] = org_sameas
        graph.append(org_node)

    # Primary ImageObject
    if image_url:
        graph.append({
            "@type": "ImageObject",
            "@id": image_id,
            "url": image_url,
            "contentUrl": image_url,
            "width": image_width,
            "height": image_height,
            "caption": title,
        })

    # BreadcrumbList
    if breadcrumbs:
        items = []
        for i, b in enumerate(breadcrumbs, 1):
            items.append({
                "@type": "ListItem",
                "position": i,
                "name": b["name"],
                "item": b["url"],
            })
        graph.append({
            "@type": "BreadcrumbList",
            "@id": f"{url}#breadcrumb",
            "itemListElement": items,
        })

    # FAQPage (if FAQ items provided)
    if faq_items:
        graph.append({
            "@type": "FAQPage",
            "@id": f"{url}#faq",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": q["question"],
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": q["answer"],
                    },
                }
                for q in faq_items
            ],
        })

    # Format-specific: ItemList for listicle/comparison/shortlist
    if format_id in ("listicle", "comparison", "shortlist-validation", "roundup", "buyers-guide"):
        if review_items:
            graph.append({
                "@type": "ItemList",
                "@id": f"{url}#itemlist",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i,
                        "name": item.get("name", ""),
                        "url": item.get("url", ""),
                    }
                    for i, item in enumerate(review_items, 1)
                ],
            })

    # Format-specific: Review schema for product-review
    if format_id == "product-review" and review_items:
        for item in review_items[:1]:  # main review
            graph.append({
                "@type": "Review",
                "itemReviewed": {
                    "@type": "Product",
                    "name": item.get("name", ""),
                },
                "reviewRating": {
                    "@type": "Rating",
                    "ratingValue": item.get("rating", 4.5),
                    "bestRating": 5,
                },
                "author": {"@id": person_id},
            })

    # ── v3.4.0 local-SEO graph nodes ─────────────────────────────────
    # Wire-up audit 2026-05-22 (P3): previously this Python executor had
    # ZERO location-aware code. The 156-line policy in
    # subskills/optimize/schema-generator/SKILL.md was documentation
    # without an implementation. Now the script honors it.
    if business_archetype in ("A", "B", "C") and business_schema_org_type and business_schema_org_type not in ("OnlineStore", "Organization"):
        # Emit LocalBusiness leaf node (Dentist, Plumber, Restaurant, etc.)
        # Note: Schema.org best practice — use the MOST-SPECIFIC subtype.
        lb_id = f"{org_url}#localbusiness" if org_url else f"{url}#localbusiness"
        lb_node: dict = {
            "@type": business_schema_org_type,
            "@id": lb_id,
            "name": (business_nap or {}).get("business_name") or org_name,
            "url": org_url or url,
        }
        if business_additional_type:
            lb_node["additionalType"] = business_additional_type
        nap_addr = (business_nap or {}).get("address")
        if nap_addr:
            lb_node["address"] = {"@type": "PostalAddress", **nap_addr}
        if (business_nap or {}).get("telephone"):
            lb_node["telephone"] = business_nap["telephone"]
        if (business_nap or {}).get("email"):
            lb_node["email"] = business_nap["email"]
        if business_archetype == "B":
            # Service-area business — explicitly no walk-in
            lb_node["publicAccess"] = False
        if business_service_areas:
            primary_states = business_service_areas.get("primary_states") or []
            if primary_states:
                lb_node["areaServed"] = [
                    {"@type": "State", "name": s} for s in primary_states[:5]
                ]
        if (business_gbp or {}).get("profile_url"):
            lb_node["sameAs"] = [business_gbp["profile_url"]]
        graph.append(lb_node)

        # Pattern A — Service.areaServed for local-mode articles
        if local_mode and location_anchor and local_article_pattern == "service_area":
            la_type = location_anchor.get("type")
            la_name = location_anchor.get("name_full") or location_anchor.get("canonical")
            if la_type == "city" and location_anchor.get("containing_state"):
                area = {
                    "@type": "City",
                    "name": la_name.split(",")[0].strip(),
                    "containedInPlace": {
                        "@type": "State",
                        "name": location_anchor["containing_state"],
                    },
                }
            elif la_type in ("state", "region"):
                area = {"@type": "State", "name": la_name}
            else:
                area = {"@type": "Place", "name": la_name}
            graph.append({
                "@type": "Service",
                "@id": f"{url}#service",
                "provider": {"@id": lb_id},
                "areaServed": area,
            })

    elif business_archetype == "D" and business_schema_org_type == "OnlineStore":
        # National ecommerce — OnlineStore, NOT LocalBusiness. No address required.
        os_id = f"{org_url}#onlinestore" if org_url else f"{url}#onlinestore"
        os_node: dict = {
            "@type": "OnlineStore",
            "@id": os_id,
            "name": (business_nap or {}).get("business_name") or org_name,
            "url": org_url or url,
        }
        if (business_gbp or {}).get("profile_url"):
            os_node["sameAs"] = [business_gbp["profile_url"]]
        graph.append(os_node)

    # Archetype D/E with local_mode → Wirecutter pattern (spatialCoverage)
    if (
        business_archetype in ("D", "E")
        and local_mode
        and location_anchor
        and (local_article_pattern == "spatial_coverage" or local_article_pattern is None)
    ):
        la_name = location_anchor.get("name_full") or location_anchor.get("canonical", "")
        place_id = f"{url}#place"
        place_geo: dict = {"@type": "GeoShape", "addressCountry": location_anchor.get("country", "US")}
        if location_anchor.get("containing_state"):
            place_geo["addressRegion"] = location_anchor["containing_state"]
        elif location_anchor.get("type") in ("state", "region"):
            place_geo["addressRegion"] = location_anchor.get("canonical", "")
        graph.append({
            "@type": "Place",
            "@id": place_id,
            "name": la_name,
            "geo": place_geo,
        })
        # Update the Article node's `about` / `spatialCoverage` / `mentions`
        # Find the Article node (always graph[0])
        if graph and graph[0].get("@type") in ("Article", "BlogPosting", "NewsArticle"):
            graph[0]["spatialCoverage"] = {"@id": place_id}
            graph[0]["about"] = {"@id": place_id}
            # mentions filled by caller via local research bundle (deferred)

    # YMYL extras — reviewedBy + lastReviewed for medical/legal/financial
    if business_ymyl_flag and graph:
        if graph[0].get("@type") in ("Article", "BlogPosting", "NewsArticle"):
            graph[0]["reviewedBy"] = {"@id": person_id}
            graph[0]["lastReviewed"] = mod

    return {
        "@context": "https://schema.org",
        "@graph": graph,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", required=True)
    ap.add_argument("--type", choices=["Article", "BlogPosting", "NewsArticle"], default="BlogPosting")
    ap.add_argument("--published")
    ap.add_argument("--modified")
    ap.add_argument("--author-name", default="Editorial Team")
    ap.add_argument("--author-url")
    ap.add_argument("--org-name", default="")
    ap.add_argument("--org-url", default="")
    ap.add_argument("--org-logo-url", default="")
    ap.add_argument("--image-url", default="")
    ap.add_argument("--primary-keyword")
    ap.add_argument("--format-id")
    ap.add_argument("--faq-json", type=Path, help="JSON file with FAQ items list")
    ap.add_argument("--reviews-json", type=Path)
    ap.add_argument("--breadcrumbs-json", type=Path)
    args = ap.parse_args()

    faq = json.loads(args.faq_json.read_text(encoding="utf-8")) if args.faq_json and args.faq_json.exists() else None
    reviews = json.loads(args.reviews_json.read_text(encoding="utf-8")) if args.reviews_json and args.reviews_json.exists() else None
    breadcrumbs = json.loads(args.breadcrumbs_json.read_text(encoding="utf-8")) if args.breadcrumbs_json and args.breadcrumbs_json.exists() else None

    data = build_jsonld(
        url=args.url, title=args.title, description=args.description,
        article_type=args.type,
        published_date=args.published, modified_date=args.modified,
        author_name=args.author_name, author_url=args.author_url,
        org_name=args.org_name, org_url=args.org_url, org_logo_url=args.org_logo_url,
        image_url=args.image_url,
        primary_keyword=args.primary_keyword, format_id=args.format_id,
        faq_items=faq, review_items=reviews, breadcrumbs=breadcrumbs,
    )

    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
