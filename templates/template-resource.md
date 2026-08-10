# Template Resource Template

> Format ID: `template-resource`. Article providing a downloadable template/asset.
> High lead-gen value + strong SEO + AI citation potential.

## Default structure

```
{Asset Name} Template: {Specific Use Case} ({Year})

## TL;DR (40-60w)
What the template is + how to download + how to use.

## What this template does (~300-400w)
Concrete use case.
Who it's for.
Specific outcome enabled.

## How to use the template (~400-500w step-by-step)
1. Download the template (link)
2. Customize for your situation
3. Distribute / use
4. Iterate based on feedback

## Walkthrough: filling out the template (~500-700w)
Worked example with realistic data.

## Common variations (~400-500w)
"If your situation is X, modify Y in the template."

## Why this template structure works (~250-300w)
Justification for design choices.

## Where this template falls short (~150-200w)
Honest limitations.

## Customize the template (~200w download CTA)
"Get the editable version" → email gate OR open download.

## Examples from real users (~300w)
2-3 case examples (anonymized OK).

## FAQ (5-7)

## References (≤6)
```

## Word budget (2500-3000w target)

Compact format. The DOWNLOAD is the value, not the article length.

| Section | Words | % |
|---|---|---|
| TL;DR + what does | 400 | 14 |
| How to use | 450 | 16 |
| Walkthrough | 600 | 21 |
| Variations | 450 | 16 |
| Why it works | 275 | 10 |
| Limitations | 175 | 6 |
| Download CTA + examples | 500 | 18 |

## Required modifiers
- `tldr-first`, `featured-snippet-targets`
- `info-gain-prose` ≥1 (the template itself is the original asset)

## Hard rules
1. Template is real + downloadable (not just described)
2. ≥1 worked example with realistic data
3. Variations section mandatory
4. Honest limitations section
5. ≥1 user example (anonymized OK)
6. Lead-gen disclosure if email-gated

## Schema additions
- `Article` base
- `HowTo` as `mainEntity` for usage steps
- `CreativeWork` for the template itself (with URL to download)
- `FAQPage`

## When to use vs how-to-guide
- how-to: process explanation
- template-resource: process + downloadable asset

## Common templates to offer
- Brief templates (marketing brief, creative brief)
- Strategy templates (SWOT, RACI, OKR)
- Calendar templates (content, editorial)
- Tracker templates (project, expense)
- Outline templates (writing structures)
- Checklist templates (process verification)

## Lead-gen strategy

Choose:
- **Open download**: builds traffic + backlinks + brand
- **Email gate**: builds list but reduces SEO signals (people share less)
- **Hybrid**: open download + optional email signup

For SEO blogs: prefer open download.

## Image slots
- Cover: screenshot of template OR mock-up
- Section 1: filled-in example
- Section 2: variation example

## Common pitfalls
- ❌ Just describing the template without offering it
- ❌ Template behind a friction-heavy gate
- ❌ Template is generic (not specific to use case)
- ❌ No real example
- ❌ Missing variations
- ❌ "Email us for the template" without auto-delivery
