# Micro-Copy Tactics

> Used by `subskills/build/topic-angle-selector/`, `subskills/optimize/meta-builder/`, and business-context.cta variant authoring (the cta-injection stage). featured-snippet-optimizer retired v3.35; cta-placement superseded by scripts/optimize/cta_injector.py v3.34.
>
> Title micro-formulas, opening hooks, CTA copy patterns.

---

## Title micro-formulas (specificity-first, per title-optimization overhaul 2026-06-16)

Every title is now a PAIR — a short `seo_title` (51–60 chars, the indexed `<title>` that survives Google's rewrite) and a longer `h1` (the on-page display title carrying the full thesis). The formulas below describe the **`seo_title`** shape; pair each one with an aligned, richer `h1` that shares the same entity + primary keyword + any number.

### F1 — Entity + disambiguating contrast
`{Entity}: {Real thing} vs {Assumed thing}`
- "1000 watt LED grow light: real draw vs equivalent"

### F2 — Count-as-thesis (B2B only; count must ALSO be in the h1)
`{N} {Entity}: {Decision axis} tested`
- "7 best 1000 watt LED grow lamps: HPS-replacement tested"

### F3 — Decision framework / what's-included
`{Entity}: what's included vs missing`
- "1000 watt grow light kit: what's included vs missing"

### F4 — Question-as-intent-match (only for true question intent; NO CTR premium per Backlinko 2025)
`{Exact question}? {Plain promise}`
- "Does marijuana grow in bulbs? A plain botanical answer"

### F5 — Gentle-helper (grief/celebration; no digit-as-hard-sell, no power word)
`{Reader's situation}: {gentle promise}`
- "What to do with your dog's ashes: gentle keepsake ideas"

### F6 — Economics frame (procurement)
`{Entity}: {cost/economics axis}`
- "Bulk PLA filament: cost-per-kg across 3 MOQ tiers"

### Retired title patterns (do not generate)

These hard-code unverified "power word + digit + year" folklore and read as AI-tells. Do not produce any of them:

- ❌ `{N} Proven {X} for {Year}` — "proven" + forced digit + year suffix
- ❌ `The Ultimate Guide to {X}` / `The Complete Guide to {X}` — power-word definition formula
- ❌ Bare `{N} Best {X} ({Year})` with no thesis — category-led, not finding-led; also a SERP-clone shape
- ❌ Any `(Year)` or `[Year]` suffix IN THE `seo_title` — rewrite-bait (parentheses changed ~62%, brackets ~78%); the year belongs in the `h1`, not the indexed `<title>`
- ❌ Two or more power words in one title — spammy / AI-tell (anti-stuffing ceiling)

---

## Opening hook formulas

The first 2 sentences. These determine bounce rate.

### Hook 1: Specific Data Point
Open with a surprising statistic or specific number.

> Mobile-first design drives 67% of e-commerce revenue (Shopify 2026), but most B2B sites still treat mobile as an afterthought. Here's what's changed.

### Hook 2: Counter-Intuitive Claim
Lead with something that contradicts common wisdom.

> Despite Yoast's advice, putting your focus keyword in the URL doesn't move the needle in 2026 — and we have 100k SERP queries proving it.

### Hook 3: Specific Pain Point + Promise
Address a known reader frustration directly.

> If you've spent more than 3 hours trying to make a Featured Snippet "appear" without success, this guide cuts straight to what actually works.

### Hook 4: Implicit Persona Filter
Filter readers immediately via specifics.

> This guide is for anglers fishing 15-30 days a year in the Pacific Northwest who want to upgrade from a $100 entry rod without paying $500+.

### Hook 5: Anecdote → Generalize
Brief specific story → broader insight.

> Last Tuesday I rebuilt our checkout flow at 11pm because conversion dropped 23% after the previous deploy. Here's what I learned about WordPress + WooCommerce performance that I wish I'd known months earlier.

### What to AVOID in hooks

- ❌ "In today's fast-paced world..." (P6)
- ❌ "This article will explore..." (P29)
- ❌ "Have you ever wondered..." (P29 variant)
- ❌ "Imagine if..."
- ❌ "Welcome to..."
- ❌ Generic statement of intent

---

## CTA copy patterns

### Soft CTA (preferred for editorial content)
- "If this helped, we've also put together a {bonus thing} at {link}."
- "We've tested 12 more {category} like this. See the full ranking → {link}"
- "Want updates when we publish the next {topic} test? Subscribe → {link}"

### Informational CTA (best for tools / pillars)
- "Download the {topic} checklist (free, no email required) → {link}"
- "See our complete {category} comparison spreadsheet → {link}"

### Hard CTA (only when you have proof + relevance)
- "Get a 14-day free trial of {Product} → {link} (no credit card)"
- "Buy the {Product} we ranked #1 in this test → {link} (we may earn a commission, see disclosure)"

### CTA placement (per claude-blog data: +266%, +682%)
- Single CTA only (one primary in body, optional one in conclusion)
- Place at 30-40% article mark (centered)
- Never above-the-fold (looks like ad)
- Never in a sidebar that floats
- Include clear value prop next to the link

---

## Meta description formulas

160 characters max. Must contain primary keyword 1x naturally.

### Formula M-A: Question + Promise
`{What's the X question}? {Specific number} {Authority Word} {finding}.`
- "What's the best fishing rod for saltwater? 7 tested picks, with sensitivity data from 87 trips."

### Formula M-B: Outcome + Method
`{Get X result} by {doing Y}. Data + examples for {persona}.`
- "Get featured-snippet rankings by writing 40-60 word answer blocks. Data + 12 templates for SEO writers."

### Formula M-C: Data Hook
`{Surprising stat} ({year}). What it means for {persona}.`
- "67% of mobile users abandon carts after 3 seconds (Shopify 2026). What it means for B2C founders."

---

## Anti-formulas (don't use)

- ❌ "Tap here to learn more" (no value prop)
- ❌ "Discover the secrets of..." (P41 infomercial)
- ❌ "You won't believe..." (clickbait)
- ❌ "Top X you need to know" (low specificity)
- ❌ "{N} reasons why..." (overused)
- ❌ Generic CTAs ("Sign up today!")
