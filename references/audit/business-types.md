# Business Type Detection Signals

## Overview

The audit pipeline auto-detects the target site's business type to customize agent spawning, scoring weight adjustments, and recommendation priorities. Detection uses a signal-weighted approach across four dimensions: URL patterns, text content, schema markup, and platform markers.

**Confidence thresholds:**
- **High confidence (>=3 dimensions match):** Auto-assign type, proceed with type-specific agents
- **Medium confidence (2 dimensions match):** Auto-assign with user confirmation prompt
- **Low confidence (1 dimension):** Ask user to confirm or select business type

---

## SaaS (Software as a Service)

### URL Pattern Signals
- `/pricing`, `/plans`, `/features`, `/integrations`, `/docs`, `/api`
- `/signup`, `/login`, `/dashboard`, `/app`, `/console`
- `/changelog`, `/roadmap`, `/status`
- Subdomain patterns: `app.`, `docs.`, `api.`, `status.`, `help.`

### Text Content Signals
- "Free trial", "Start free", "No credit card required"
- "Per user/month", "Per seat", "Annual billing", "Enterprise plan"
- "API", "SDK", "Webhook", "Integration"
- "Onboarding", "Dashboard", "Analytics", "Workflow"
- "SOC 2", "GDPR compliant", "SSO", "SAML"

### Schema Signals
- `SoftwareApplication` or `WebApplication` with `offers`
- `Product` with `applicationCategory`
- `Organization` with `sameAs` pointing to GitHub, ProductHunt, G2

### Platform Markers
- JS frameworks: React, Vue, Angular, Svelte (SPA indicators)
- Auth providers: Auth0, Clerk, Firebase Auth cookies/scripts
- Analytics: Mixpanel, Amplitude, Heap, Segment, PostHog
- Payment: Stripe.js, Paddle.js, Chargebee
- Support: Intercom, Zendesk, HubSpot chat widgets
- Status page: Statuspage.io, Instatus, BetterStack

### Conditional Agents to Spawn
- **SaaS Conversion Funnel Audit**: Analyze pricing page structure, CTA placement, social proof
- **Documentation SEO Audit**: Check /docs indexability, search within docs, content freshness
- **Competitor Feature Comparison**: Schema opportunities for `WebApplication.featureList`
- **Integration Page Audit**: Programmatic page quality check (see `quality-gates.md` safe-at-scale)
- **Developer Experience Audit**: API docs, code examples, SDK pages

---

## E-commerce

### URL Pattern Signals
- `/product/`, `/products/`, `/shop/`, `/store/`, `/collections/`
- `/cart`, `/checkout`, `/wishlist`, `/order`
- `/category/`, `/brand/`, `/sale/`, `/clearance/`
- URL parameters: `?variant=`, `?size=`, `?color=`, `?sku=`

### Text Content Signals
- "Add to cart", "Buy now", "In stock", "Out of stock"
- "Free shipping", "Returns policy", "Track order"
- "SKU", "UPC", product specifications tables
- Price patterns: `$XX.XX`, currency symbols with decimals
- "Customer reviews", star ratings, "Verified purchase"

### Schema Signals
- `Product` with `offers`, `sku`, `brand`, `aggregateRating`
- `ProductGroup` with `hasVariant`
- `BreadcrumbList` with category hierarchy
- `MerchantReturnPolicy`, `OfferShippingDetails`
- `ItemList` for category/collection pages

### Platform Markers
- Shopify: `cdn.shopify.com`, `myshopify.com`, Shopify global JS object
- WooCommerce: `/wp-content/plugins/woocommerce/`, `wc-` CSS classes
- Magento: `/pub/static/`, `Magento_` module paths, `mage/` JS
- BigCommerce: `cdn11.bigcommerce.com`, BCData JS object
- Squarespace Commerce: `squarespace-cdn.com` + product JSON
- Payment: Stripe, PayPal, Klarna, Afterpay/Clearpay scripts

### Conditional Agents to Spawn
- **Product Schema Audit**: Validate Product/Offer/AggregateRating on all product pages
- **Category Page Quality Audit**: Check for thin category pages, unique intros, proper internal linking
- **Faceted Navigation Audit**: Crawl budget impact, canonicalization of filtered URLs
- **Product Image Audit**: Alt text, multiple angles, zoom capability, WebP/AVIF format
- **Review Schema Audit**: AggregateRating accuracy, review snippet eligibility
- **Merchant Center Compatibility**: returnPolicyCountry, shippingDetails, product feed alignment

---

## Local Brick-and-Mortar

### URL Pattern Signals
- `/locations`, `/location/`, `/store-locator`, `/find-us`
- `/about-us` with physical address
- `/directions`, `/hours`, `/visit-us`
- City/state in URL slugs: `/austin-tx/`, `/new-york/`

### Text Content Signals
- Physical address with street, city, state, ZIP
- "Visit us at", "Located in", "Serving [city]"
- Business hours ("Mon-Fri 9am-5pm", "Open 7 days")
- "Walk-ins welcome", "By appointment", "Parking available"
- Phone number with local area code
- "Serving [city] since [year]"

### Schema Signals
- `LocalBusiness` (or specific subtypes: Restaurant, DentalClinic, AutoRepair, etc.)
- `PostalAddress` with `streetAddress`, `addressLocality`, `addressRegion`
- `openingHoursSpecification`
- `geo` with `latitude`/`longitude`
- `areaServed`

### Platform Markers
- Google Maps embed (`maps.googleapis.com`, `google.com/maps/embed`)
- Yelp badge/widget
- OpenTable, Resy, or booking widgets (restaurants)
- Square, Toast, Clover POS markers
- Local directory badges (BBB, Chamber of Commerce)

### Conditional Agents to Spawn
- **GBP Alignment Audit**: Cross-check website NAP vs. GBP data, category match, attribute coverage
- **Local Schema Deep Audit**: LocalBusiness subtype accuracy, openingHours, geo coordinates
- **Citation Consistency Audit**: NAP across Tier 1-3 directories (see `local-seo-signals.md`)
- **Review Signal Audit**: Review count, velocity, recency, sentiment, platform distribution
- **Location Page Quality Audit**: Unique content per location, doorway page risk assessment

---

## Local SAB (Service Area Business)

### URL Pattern Signals
- `/service-area`, `/areas-served`, `/service-locations`
- `/services/`, `/service/[service-name]`
- City-specific service pages: `/plumbing-austin-tx/`, `/ac-repair-dallas/`
- No `/visit-us` or `/directions` (no storefront)

### Text Content Signals
- "Serving [city] and surrounding areas"
- "We come to you", "Mobile service", "On-site"
- "Service area includes", "Coverage area"
- Service-specific language without storefront references
- "Licensed and insured", "BBB accredited"
- "Free estimates", "Same-day service", "Emergency service"

### Schema Signals
- `LocalBusiness` with `areaServed` but NO `streetAddress` in public markup (or PO Box)
- `Service` with `areaServed` and `provider`
- `hasMap` absent or pointing to service area polygon
- Multiple `areaServed` entries (cities/regions)

### Platform Markers
- Housecall Pro, ServiceTitan, Jobber scheduling widgets
- "Book online" / scheduling calendar embeds
- Before/after photo galleries (contractors, cleaning, landscaping)
- License number display (state-mandated for trades)

### Conditional Agents to Spawn
- **Service Area Page Audit**: Doorway page risk vs. legitimate SAB pages, unique content per city
- **GBP SAB Configuration Audit**: Verify GBP set to SAB mode (hidden address), service area defined
- **Service Page Depth Audit**: Each service has dedicated page with sufficient depth, not just a list
- **Location Page Scaling Audit**: If 30+ city pages, enforce quality-gates.md location thresholds
- **Competitor Radius Analysis**: Map competitor SAB coverage overlap

---

## Local Hybrid (Storefront + Service Area)

### URL Pattern Signals
- Combination of brick-and-mortar AND SAB signals
- `/locations` + `/service-area`
- Physical addresses for some locations + service area descriptions for others
- `/showroom`, `/warehouse` (physical) + `/delivery-area`, `/installation-area` (service)

### Text Content Signals
- "Visit our showroom" AND "We also serve..."
- Physical address present AND service area described
- "Pickup available" AND "Delivery to [area]"
- "In-store and mobile service"

### Schema Signals
- `LocalBusiness` with BOTH `address` (physical) AND `areaServed` (service radius)
- Multiple `location` entries mixing physical and service-area types
- `hasOfferCatalog` with both in-store and service offerings

### Platform Markers
- Combination of storefront markers (POS, maps embed) AND service markers (scheduling, booking)
- Delivery radius tools (DoorDash, Uber integration for restaurants)
- "Ship to store" / "Buy online pickup in store" (BOPIS) features

### Conditional Agents to Spawn
- All agents from **Local Brick-and-Mortar** AND **Local SAB** combined
- **Hybrid Schema Audit**: Ensure schema correctly represents both physical locations and service areas without conflicting signals
- **Cannibalization Audit**: Check that storefront pages and SAB city pages do not compete for same keywords

---

## Publisher / Media

### URL Pattern Signals
- `/article/`, `/post/`, `/story/`, `/opinion/`, `/editorial/`
- `/author/`, `/journalist/`, `/contributor/`
- `/category/`, `/tag/`, `/topic/`
- `/archive/`, `/issue/`, `/edition/`
- Date-based URLs: `/2026/05/25/article-slug`

### Text Content Signals
- Byline with author name and date
- "Published", "Updated", "Reviewed by"
- "Source:", "According to", inline citations
- "Subscribe", "Newsletter", "Member-only"
- "Related articles", "Read more", "Continue reading"
- High word count (1,500+ average)

### Schema Signals
- `Article`, `NewsArticle`, `BlogPosting` with full `author` Person
- `WebSite` with `SearchAction` (sitelinks search box)
- `ProfilePage` for author pages
- `BreadcrumbList` with topic hierarchy
- `Speakable` for voice search optimization
- `ImageObject` with `copyrightHolder`

### Platform Markers
- WordPress: `/wp-content/`, `wp-` CSS classes, REST API
- Ghost: `ghost-` classes, Ghost API
- Substack: `substack.com` domain or `substackcdn.com` assets
- Medium: `medium.com` domain or Medium API markers
- Webflow: `webflow.io`, Webflow JS
- Paywall markers: `piano.io`, `tinypass`, Memberful, Patreon

### Conditional Agents to Spawn
- **Author E-E-A-T Audit**: Author pages exist, credentials visible, sameAs to external profiles
- **Content Freshness Audit**: Publication dates, update frequency, stale content identification
- **Topical Authority Audit**: Content cluster completeness, internal linking depth, pillar-cluster structure
- **Syndication/Duplicate Audit**: Canonical tags for syndicated content, cross-domain duplicate detection
- **AI Citation Readiness Audit**: Structured claims, references sections, quotable passages, llms.txt

---

## Agency (Marketing, Design, Development, Consulting)

### URL Pattern Signals
- `/services/`, `/solutions/`, `/capabilities/`
- `/case-studies/`, `/portfolio/`, `/work/`, `/clients/`
- `/team/`, `/about/`, `/culture/`
- `/blog/`, `/insights/`, `/resources/`, `/whitepapers/`
- `/contact/`, `/get-a-quote/`, `/request-proposal/`

### Text Content Signals
- "Our services", "What we do", "How we work"
- "Case study", "Client results", "ROI", "Before and after"
- Client logos section ("Trusted by", "Our clients include")
- "Request a proposal", "Schedule a consultation", "Get a quote"
- Industry jargon specific to agency type (SEO, PPC, UX, Branding)
- Awards: "Clutch", "Agency of the Year", "Webby"

### Schema Signals
- `Organization` with `knowsAbout`, `numberOfEmployees`
- `Service` with specific `serviceType` (SEO, Web Design, etc.)
- `Person` for team members with `jobTitle` and `worksFor`
- `Review` / `AggregateRating` from clients
- `CreativeWork` for portfolio items

### Platform Markers
- Clutch.co widget or badge
- HubSpot, Salesforce, or CRM integration markers
- Project management tool integrations (Monday.com, Asana, Basecamp)
- Design tools: Figma embeds, Dribbble links, Behance portfolio
- Calendly, Acuity, or Cal.com scheduling embeds

### Conditional Agents to Spawn
- **Service Page Depth Audit**: Each service has dedicated page, not just a bullet in a list
- **Case Study Audit**: Structured case studies with measurable outcomes, schema markup
- **Thought Leadership Audit**: Blog quality, publication frequency, author authority
- **Social Proof Audit**: Client logos, testimonials, third-party review platform presence
- **Lead Generation Audit**: CTA placement, form accessibility, conversion path clarity

---

## Detection Algorithm

### Signal Scoring

Each detected signal contributes points to its business type. The type with the highest weighted score wins.

```
Signal weights:
  URL patterns:        1 point each (max 5 per type)
  Text content:        1 point each (max 5 per type)
  Schema signals:      2 points each (max 10 per type)
  Platform markers:    3 points each (max 9 per type)

Minimum threshold to assign type: 8 points
```

### Multi-Type Handling

Sites can match multiple types. Common combinations:
- **SaaS + Publisher**: SaaS with a content marketing blog (common). Primary = SaaS, secondary = Publisher.
- **E-commerce + Local**: Retail store with online shop. Primary = whichever has more pages.
- **Agency + Publisher**: Agency with significant blog. Primary = Agency, secondary = Publisher.
- **Local Brick-and-Mortar + Local SAB**: Hybrid. Use the dedicated Hybrid type.

When multi-type is detected, spawn agents from both types but deduplicate overlapping audits.

### Fallback

If no type reaches the 8-point threshold:
1. Default to **Generic Website** profile (no type-specific agents)
2. Use default scoring weights from `scoring-weights.md`
3. Include a recommendation in the report to classify the site manually for future audits
