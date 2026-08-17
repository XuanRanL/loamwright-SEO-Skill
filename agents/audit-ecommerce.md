---
name: audit-ecommerce
description: Audits product page SEO — Product/Offer/AggregateRating schema, pricing consistency, variant handling, breadcrumbs, image count, description depth, shipping schema
tools: [Read, Bash, Write, Glob, Grep]
maxTurns: 60
---

# Audit E-commerce Agent

## Spawn Condition
`config.json :: business_type == "ecommerce"`, OR crawl results contain Product schema or product URL patterns (`/product/`, `/shop/`, `/p/`).

## Inputs
- `{audit_dir}/crawl-results.json` — product pages with HTML, schema, links
- `{audit_dir}/config.json` — domain, product URL patterns, category structure

Read `references/audit/schema-types.md` before analysis.

## Scripts
- `python -m scripts.audit.parse_html {html_path} --url {page_url} --json` — the file is positional; output includes a `schema` array with every JSON-LD block (there are no `--extract-*` flags, and pricing is not extracted — read visible prices from the HTML yourself)
- `python -m scripts.validate.schema_validator {schema_json_file} --json` — deep validation of a JSON-LD payload (or list of payloads) saved to a file; the file argument is positional and there is no `--type` flag (it detects types itself)

## 10 Checks

**1. Product Schema** — Every product page needs `Product` with: name, image, description, sku, brand.name, offers. CRITICAL if absent; HIGH if offers missing; MEDIUM if recommended fields missing.

**2. Offer Schema** — Each `offers` must have: price (numeric, matches visible), priceCurrency (ISO 4217), availability (InStock/OutOfStock/PreOrder/BackOrder/Discontinued), url. HIGH if price or availability missing.

**3. AggregateRating** — If reviews visible on page: ratingValue + reviewCount must exist in schema and match displayed stars. HIGH if reviews visible but no schema.

**4. Variant Handling** — Products with size/color variants: parent should use ProductGroup or Product+hasVariant. Each variant needs own Offer+sku. Single canonical URL preferred. MEDIUM if variants create duplicate title/description.

**5. Breadcrumbs** — Visible trail Home > Category > Subcategory > Product with matching BreadcrumbList schema (ListItem with name + item URL). HIGH if schema absent on product pages.

**6. Internal Linking** — Category->product links, product->related (3-6), product->category via breadcrumb, cross-sell/upsell sections. Target 5-10 internal links per product page. MEDIUM if avg < 3.

**7. Pricing Consistency** — Visible price must equal schema offers.price. CRITICAL if mismatch (Google policy violation, manual action risk). Sale prices need priceSpecification.

**8. Images** — Min 3-5 per product. Alt text includes product name. Schema image URL resolves. Multiple angles (front/back/detail/lifestyle). MEDIUM if < 3.

**9. Description Quality** — 400+ words complex products, 200+ simple. Not manufacturer boilerplate. Feature bullets, use cases, comparison context. HIGH if < 100 words (thin).

**10. Shipping/Return Schema** — OfferShippingDetails (delivery time, cost, destination) and MerchantReturnPolicy (window, method, fees) on Offer. LOW if missing (recommended not required).

## Scoring
`(schema*0.25) + (offer*0.20) + (pricing*0.20) + (rating*0.10) + (breadcrumb*0.10) + (links*0.05) + (images*0.05) + (description*0.05)`. If no review system, redistribute rating to offer 0.25 + schema 0.30.

## Output → `{audit_dir}/modules/ecommerce.json`
```json
{
  "module": "ecommerce", "score": 0-100,
  "product_pages_analyzed": N,
  "schema_coverage": {"product_schema_pct": 0, "offer_complete_pct": 0, "rating_pct": 0, "breadcrumb_pct": 0, "shipping_pct": 0},
  "pricing_consistency": {"matches": N, "mismatches": N, "mismatch_urls": []},
  "content_quality": {"avg_word_count": N, "thin_pages": N, "avg_images": N},
  "variant_handling": {"products_with_variants": N, "product_group_used": false, "duplicate_risk_pairs": N},
  "findings": [{"severity": "critical|high|medium|low", "category": "...", "message": "...", "evidence": "...", "recommendation": "..."}],
  "metadata": {"product_url_pattern": "...", "total_product_pages": N, "sample_size": N, "has_review_system": false}
}
```
