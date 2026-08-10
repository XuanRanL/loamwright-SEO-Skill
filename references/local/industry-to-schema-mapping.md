# Industry → Schema.org Type Mapping (v1.0, 2026-05-22)

**Source of truth for `schema-generator` subskill's auto-selection.** Generic across all projects. Synthesized from Schema.org canonical docs + Google Search Central + 2026-05-22 deep-research deliverables in `memory/research/local_schema_industry_mapping_2026.json` and `memory/research/project-charlie_final_schema_decision_2026.json`.

---

## TL;DR

`/init` collects 3 facts → plugin auto-selects schema:

```
location.business_archetype  ∈ {A, B, C, D, E}
location.business_category   = <string from the 30+ recommended list>
location.local_article_pattern ∈ {"service_area", "spatial_coverage"}
       ↓ schema-generator reads these
location.schema_org_type     = <auto-resolved leaf, e.g. "Dentist" | "Plumber" | "OnlineStore">
```

If business_category is unknown / unmapped → 3-tier resolution kicks in (see §3).

---

## 1. The 5 Business Archetypes

Each project belongs to exactly one. The archetype determines schema **shape** (LocalBusiness vs Organization, single vs chain, areaServed vs spatialCoverage).

| ID | Name | Defining trait | Examples |
|---|---|---|---|
| **A** | Local brick-and-mortar | Single physical location customers visit | restaurant, dentist, gym, café, salon, retail boutique |
| **B** | Service-area business | Travels to customer; no walk-in | plumber, HVAC, electrician, mobile vet, roofer, locksmith, lawn-care |
| **C** | Multi-location chain | ≥2 physical locations under one brand | restaurant chain, dental group, fitness franchise, law firm w/ branches |
| **D** | National ecommerce | Ships product across country; no brick-and-mortar | DTC ecommerce (any product category), equipment supplier, dropshipper |
| **E** | Pure SaaS / online service | Digital-only delivery; no physical product | SaaS, online course, marketplace, fintech, agency-as-software |

### Archetype → Schema Shape Cheat Sheet

| Archetype | Org/Homepage schema | Article schema for local content |
|---|---|---|
| **A** | LocalBusiness leaf + `address` + `geo` | `Article.about: Place` + `Service.areaServed: City/State` |
| **B** | LocalBusiness leaf + `publicAccess:false` + `address` (HQ) + heavy `areaServed` | `Service.areaServed: City/State` (multiple) |
| **C** | Each location = own LocalBusiness leaf w/ unique `@id` + `parentOrganization` | Per-location: `Service.areaServed` of that city |
| **D** | `OnlineStore` (Google-canonical for ecommerce, **not** LocalBusiness) | **Wirecutter pattern**: `Article.spatialCoverage: Place` + `Article.about: Place` + `Article.mentions: [local entities]`. **NOT** Service.areaServed (misleading) |
| **E** | `Organization` (no LocalBusiness, no OnlineStore) | Wirecutter pattern (same as D) |

### Why this matters (E-E-A-T)

> Falsely declaring `Service.areaServed: Boston` when the business is a national ecommerce that does not "serve" Boston specifically is a **misleading-data signal** under Google's E-E-A-T framework. The Wirecutter pattern (national publication writing *about* local markets) uses `Article.spatialCoverage` / `about` / `mentions` — content is about the place, not a service to it. Adopt this pattern for archetypes D and E.

---

## 2. The 3-Tier Industry Resolution

`/init` asks for `business_category` (free text or dropdown). The plugin then resolves it to a `schema_org_type` via three tiers:

### Tier 1 — Closed-enum (deterministic)

These 15 industries map 1:1 to canonical Schema.org leaves. Plugin auto-fills with confidence.

| business_category | schema_org_type | Archetype default | YMYL? |
|---|---|---|---|
| `restaurant` | `Restaurant` | A | no |
| `cafe` | `CafeOrCoffeeShop` | A | no |
| `bar` | `BarOrPub` | A | no |
| `bakery` | `Bakery` | A | no |
| `dentist` | `Dentist` | A or C | **YMYL-medical** |
| `medical_clinic` | `MedicalClinic` | A or C | **YMYL-medical** |
| `veterinarian` | `VeterinaryCare` | A or C | no |
| `legal_service` | `LegalService` | A, B, or C | **YMYL-legal** |
| `accountant` | `AccountingService` | A, B, or C | **YMYL-financial** |
| `financial_advisor` | `FinancialService` | A, B, or C | **YMYL-financial** |
| `plumber` | `Plumber` | B | no |
| `hvac` | `HVACBusiness` | B | no |
| `electrician` | `Electrician` | B | no |
| `roofer` | `RoofingContractor` | B | no |
| `real_estate_agent` | `RealEstateAgent` | A or C | **YMYL-financial** |

**Behavior**: schema-generator emits the leaf as `@type` directly. For YMYL categories, also emits `Person.hasCredential` + `lastReviewed` per `references/local/local-schema-graph-canonical.md` (when present).

### Tier 2 — Soft-warning (recommended leaf exists, but verify)

These 10 industries have a sensible default but the plugin emits a warning to confirm the choice at /init time. The user can override via free text.

| business_category | recommended schema_org_type | Why warning |
|---|---|---|
| `auto_repair` | `AutoRepair` | Multiple Schema.org subtypes (AutoBodyShop, AutoRepair, AutoWash) — pick by service mix |
| `auto_sales` | `AutoDealer` | Used vs new vs leasing have different schemas (still all AutoDealer base) |
| `gym` | `ExerciseGym` | Distinct from HealthClub / SportsClub — confirm |
| `yoga_studio` | `HealthAndBeautyBusiness` | No exact leaf; HealthAndBeautyBusiness is closest |
| `personal_trainer` | `ExerciseGym` (if facility) OR `Person` (if mobile/freelance) | Depends on archetype A vs B |
| `chiropractor` | `Chiropractic` | Schema.org has Chiropractic; some prefer MedicalBusiness — use Chiropractic |
| `mortgage_broker` | `FinancialService` | No dedicated leaf; use FinancialService + Service.areaServed |
| `insurance_agent` | `InsuranceAgency` | Use InsuranceAgency leaf |
| `pet_groomer` | `HealthAndBeautyBusiness` | No pet-specific Schema.org type; this is the canonical workaround |
| `landscaper` | `ProfessionalService` | No dedicated leaf; ProfessionalService + areaServed |

**Behavior**: schema-generator emits the recommended leaf but logs `"⚠ Tier-2 default chosen; review schema_org_type if business doesn't fit"` to stderr.

### Tier 3 — Open fallback (manual override required)

If `business_category` is not in Tier 1 or Tier 2 (e.g. niche industries like `cannabis_b2b_equipment`, `esg_consultant`, `mobile_pet_dentistry`, `ada_compliance_auditor`), the plugin:

1. Asks at /init: "What's the closest Schema.org type?" with the canonical archetype-driven defaults:
   - Archetype A/B/C → suggests `LocalBusiness` (generic) + warns "Most-specific leaf gets better SERP enhancement per Google docs"
   - Archetype D → suggests `OnlineStore`
   - Archetype E → suggests `Organization`
2. Accepts a free-text Schema.org type if user knows better (e.g. `Store`, `ProfessionalService`)
3. Optionally accepts `additionalType` (a URL or ProductOntology) for industries not natively typed
4. Records the choice in `business-context.json :: location.schema_org_type` + a `_notes` field explaining the manual override

**Example** — project-charlie (cannabis B2B equipment supplier):
```json
"location": {
  "business_archetype": "D",
  "business_category": "cannabis_b2b_equipment",
  "schema_org_type": "OnlineStore",
  "additional_type": "https://www.productontology.org/id/Horticultural_lighting",
  "local_article_pattern": "spatial_coverage",
  "_notes": "Tier-3 manual override 2026-05-22. cannabis_b2b_equipment has no native Schema.org leaf. OnlineStore is Google's recommended ecommerce type. additionalType references ProductOntology for horticultural lighting niche. local articles use Wirecutter spatial_coverage pattern because project-charlie doesn't physically serve any specific state."
}
```

---

## 3. Schema-generator Decision Algorithm

Pseudo-code the schema-generator subskill executes:

```python
def select_schema_org_type(business_context: dict) -> dict:
    loc = business_context.get("location", {})
    archetype = loc.get("business_archetype")
    category = loc.get("business_category")
    explicit = loc.get("schema_org_type")

    # 1. Explicit override wins
    if explicit:
        return {
            "schema_org_type": explicit,
            "additional_type": loc.get("additional_type"),
            "tier_resolved": "manual",
            "ymyl": loc.get("ymyl_flag", False),
        }

    # 2. Try Tier 1 (closed-enum)
    if category in TIER_1_MAPPING:
        return TIER_1_MAPPING[category]

    # 3. Try Tier 2 (soft-warning, recommended default)
    if category in TIER_2_MAPPING:
        warn_stderr(f"Tier-2 default chosen for {category!r}; review schema_org_type")
        return TIER_2_MAPPING[category]

    # 4. Tier 3 fallback — archetype-driven safe default
    archetype_defaults = {
        "A": {"schema_org_type": "LocalBusiness"},  # generic; ask for more specific
        "B": {"schema_org_type": "LocalBusiness", "publicAccess": False},
        "C": {"schema_org_type": "LocalBusiness"},
        "D": {"schema_org_type": "OnlineStore"},
        "E": {"schema_org_type": "Organization"},
    }
    if archetype not in archetype_defaults:
        raise ValueError(f"business_archetype must be A-E, got {archetype!r}")

    warn_stderr(f"Tier-3 fallback for category={category!r}; archetype={archetype}")
    return {
        **archetype_defaults[archetype],
        "tier_resolved": "fallback",
        "needs_manual_review": True,
    }
```

---

## 4. local_article_pattern: service_area vs spatial_coverage

Determines schema for "[keyword] [location]" articles.

### Pattern: `service_area` (archetypes A/B/C default)

Use when business actually serves the geographic area in the article.

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Service",
      "@id": "{post_url}#service",
      "provider": {"@id": "{site_url}#localbusiness"},
      "areaServed": {
        "@type": "City",
        "name": "Denver",
        "containedInPlace": {"@type": "State", "name": "Colorado"}
      },
      "serviceType": "Plumbing"
    }
  ]
}
```

### Pattern: `spatial_coverage` (archetypes D/E default — Wirecutter)

Use when business writes ABOUT a location it doesn't service (national ecommerce, SaaS, agency).

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Article",
      "@id": "{post_url}#article",
      "spatialCoverage": {
        "@type": "Place",
        "name": "Oklahoma",
        "geo": {"@type": "GeoCoordinates", "addressCountry": "US", "addressRegion": "OK"}
      },
      "about": {"@id": "{post_url}#place-oklahoma"},
      "mentions": [
        {"@type": "Organization", "name": "OG&E", "url": "https://www.oge.com/"},
        {"@type": "GovernmentOrganization", "name": "Oklahoma Medical Marijuana Authority"}
      ]
    },
    {
      "@type": "Place",
      "@id": "{post_url}#place-oklahoma",
      "name": "Oklahoma cannabis cultivation market",
      "geo": {"@type": "GeoShape", "addressCountry": "US", "addressRegion": "OK"}
    }
  ]
}
```

### Why never mix the two

`Service.areaServed: Oklahoma` while business actually has no Oklahoma service = **misleading-data signal**. Google's E-E-A-T framework explicitly catches this; sites have been hit with manual actions for false LocalBusiness assertions. **Always default to spatial_coverage for archetypes D/E.**

---

## 5. YMYL Schema Extras

For Tier 1 + Tier 2 categories flagged YMYL (medical, legal, financial):

| YMYL type | Additional schema |
|---|---|
| medical (Dentist, MedicalClinic, Chiropractic, VeterinaryCare) | `MedicalWebPage` wrapper + `Article.reviewedBy: Person.hasCredential: MedicalDoctor/RegisteredHealthProfessional` + `lastReviewed: <date>` |
| legal (LegalService) | `Article.author.hasCredential: BarMembership` (state-specific) + `lastReviewed` |
| financial (FinancialService, AccountingService) | `Article.author.hasCredential: CPA/CFP/CFA` + `lastReviewed` |

The schema-generator emits these as supplemental blocks when:
- `business-context.json :: location.ymyl_flag == true`
- OR the business_category resolves to a known YMYL Tier 1/2 entry

---

## 6. Edge cases captured during research

| Industry | What you'd guess | Correct |
|---|---|---|
| Attorney | `Attorney` | **`LegalService`** (Attorney type is DEPRECATED in Schema.org) |
| Cannabis dispensary | `LocalBusiness` | `Store` + `additionalType: <ProductOntology cannabis URL>` (no native type) |
| Cannabis B2B equipment | `LocalBusiness` | `OnlineStore` (ecommerce) + `additionalType: ProductOntology horticultural lighting` |
| Pure SaaS | `SoftwareApplication` | `Organization` (SoftwareApplication is for the PRODUCT, not the company) |
| Multi-location franchise | One `LocalBusiness` w/ multiple `areaServed` | **Each location = own `@id`**; root `Organization` w/ `parentOrganization` links |
| National DTC ecommerce | `Store` | **`OnlineStore`** (Google's canonical recommendation per developers.google.com) |
| Mortgage broker | `LegalService` (because financial advisory) | `FinancialService` (financial > legal here) |
| Mobile vet | `VeterinaryCare` w/ address | `VeterinaryCare` + `publicAccess: false` + `areaServed` (service-area pattern) |

---

## 7. AggregateRating + Review schema warning

**Self-attested AggregateRating on a LocalBusiness/Organization will be silently dropped by Google** (Sept 2019 enforcement update — no rich-results display). To show stars in SERP:

- ✅ Reviews must come from a third-party source (e.g. embedded via Yelp/G2/Trustpilot APIs)
- ✅ Use `Review` schema with `author.@type: Person` + verifiable identity
- ❌ Don't self-write 5-star reviews inside your own schema
- ❌ Don't add an inflated `aggregateRating.ratingValue` without a real review corpus

The schema-generator subskill MUST NOT auto-emit `aggregateRating` unless `business-context.json :: location.review_source` declares the third-party feed.

---

## 8. Penalty triggers — schema-generator MUST NOT emit

Based on Google's structured-data documentation:

| Anti-pattern | Why penalized |
|---|---|
| `LocalBusiness` without `address` | LocalBusiness requires address per Google docs |
| `LocalBusiness` with `<5 decimal precision` on `geo.latitude/longitude` | Imprecise geo signals "fake business" |
| Hidden content marked up (markup describing content the user can't see) | Google penalizes "spammy structured data" per spam policy |
| `priceRange` ≥100 chars | Free-form abuse; Google's parser ignores or flags |
| Self-attested AggregateRating | See §7 |
| Schema describing competitor products | Misleading data |
| `Service.areaServed` not actually serving | E-E-A-T misleading-data signal |

---

## 9. Update procedure

When Schema.org adds new leaves or Google updates structured-data docs, this file (and `schemas/business-context.schema.json :: location.business_category` enum) needs updating. Procedure:

1. Audit changes via deep-research: search `site:developers.google.com/search/docs/appearance/structured-data updated:YYYY-MM`
2. Update Tier 1 / Tier 2 tables in this doc
3. Update `business-context.schema.json` enum + this doc's `_schema_version`
4. Bump plugin version per `CLAUDE.md` after-edit sync workflow
5. Document the addition in CHANGELOG with the Schema.org version that introduced it

Current schema version: `Schema.org 24.0` + `Google Search Central as of 2026-05-22`.
