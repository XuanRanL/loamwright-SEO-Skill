---
name: audit-local
description: Evaluates local SEO signals — GBP optimization, NAP consistency, reviews, local schema, citation authority — for brick-and-mortar and SAB businesses
tools: [Read, Bash, Write, Glob, Grep]
maxTurns: 60
---

# Audit Local Agent

## Spawn Condition
Only run when `{audit_dir}/config.json :: business_type` is `local_brick_mortar`, `local_sab`, or `local_hybrid`.

## Inputs
- `{audit_dir}/crawl-results.json` — crawled pages with HTML, schema blocks, internal links
- `{audit_dir}/config.json` — domain, business name, address, phone, service areas
- `{audit_dir}/gbp-data.json` — GBP profile (if pre-fetched)

Read `references/audit/local-seo-signals.md` before analysis.

## Scripts

Use these concrete invocations to gather data:

```bash
# Parse homepage + contact page for NAP, schema, maps embed
python -m scripts.audit.parse_html {homepage_html} --url "$URL" --json
python -m scripts.audit.parse_html {contact_page_html} --url "$URL" --json

# Fetch robots.txt and key local pages
python -m scripts.audit.fetch_page "$URL/contact" --json
python -m scripts.audit.fetch_page "$URL/about" --json

# Check schema on location/service pages from crawl results
for page in $(cat {audit_dir}/crawl-results.json | python -c "import sys,json; [print(p['url']) for p in json.load(sys.stdin) if '/location' in p.get('url','') or '/service' in p.get('url','')]"); do
  python -m scripts.audit.fetch_page "$page" --json
done
```

Extract NAP from parsed HTML: search for `<address>`, `LocalBusiness` schema, phone regex `\+?\d[\d\s\-()]{7,}`, and structured address fields.

## Scoring Dimensions (weighted → overall)

**GBP Signals (25%)** — Primary category set correctly (single strongest controllable factor). Title = registered name (no keyword stuffing). Verified. Opening hours present + matching website. Description 750 chars with primary service + city. Photos >= 10, updated < 90 days. Posts < 7 days old. Q&A seeded. Deduct 25 if category wrong, 15 if unverified.

**Reviews & Reputation (20%)** — Rating 4.5+ for competitive markets. Review count in top-3 for local pack. Velocity: new reviews/month trending up. Recency: latest review < 18 days (the "18-day rule" — stale profiles regress). Owner response rate 80%+. Extract sentiment keywords. CRITICAL if rating < 3.5.

**Local On-Page (20%)** — City in title/H1/URL on service + location pages. Dedicated service-area page per target city. Local content (landmarks, neighborhoods). Embedded Google Map on contact page. HIGH if city missing from title/H1 on primary landing pages.

**NAP Consistency (15%)** — Name, Address, Phone extracted from header, footer, contact page, schema, GBP must be character-identical. Common failures: "St" vs "Street", phone format variations, missing suite numbers. CRITICAL if NAP contradicts across sections.

**Local Schema (10%)** — `LocalBusiness` (or subtype) on homepage with: name, PostalAddress, telephone, geo lat/lng, openingHoursSpecification, areaServed (for SAB), priceRange. HIGH if schema absent; MEDIUM if incomplete.

**Citation Authority (10%)** — Presence on: Google, Bing Places, Apple Maps, Yelp, BBB, Facebook, industry directories. NAP consistency across external citations. MEDIUM if missing 2+ major platforms.

## Key Facts
- Proximity = 55.2% of local ranking variance (Whitespark 2024) — uncontrollable, so all other signals must be maxed
- Review velocity matters more than total volume for ranking momentum

## Output → `{audit_dir}/modules/local.json`
```json
{
  "module": "local", "score": 0-100,
  "dimensions": {
    "gbp_signals": {"score": 0-100, "findings": [...]},
    "reviews_reputation": {"score": 0-100, "findings": [...]},
    "local_onpage": {"score": 0-100, "findings": [...]},
    "nap_consistency": {"score": 0-100, "findings": [...]},
    "local_schema": {"score": 0-100, "findings": [...]},
    "citation_authority": {"score": 0-100, "findings": [...]}
  },
  "findings": [{"severity": "critical|high|medium|low", "category": "...", "message": "...", "evidence": "...", "recommendation": "..."}],
  "metadata": {"business_type": "...", "primary_city": "...", "service_areas": [], "gbp_category": "..."}
}
```
