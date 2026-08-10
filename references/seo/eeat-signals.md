# E-E-A-T Signals Catalog

> Google's quality framework (Experience / Expertise / Authoritativeness / Trustworthiness) — expanded 2024 with the second "E".
>
> Used by `core_eeat_scorer.py` + `subskills/optimize/geo-content-optimizer/` + every quality gate.

---

## E1: Experience (added 2024)

First-hand experience with the topic. "I actually did this" signals.

### Strong signals
- "I tested X for 6 months and found Y"
- "After 87 trips on the river, we noticed Z"
- Photos / screenshots from real use
- Specific dates, settings, conditions
- "What went wrong" sections (real users hit failures)
- Time investment quantified ("spent 14 hours setting up")

### Weak signals (won't pass on their own)
- "It is generally known that..."
- "Studies show..."
- Stock photos
- "Common wisdom suggests..."

### How to demonstrate in content
- `real first-hand experience (plain prose)` marker
- First-person voice 10-15% (per `style/voices/professional.md`)
- Specific numerical results
- Photos/screenshots with timestamps
- "Methodology" section in case studies

---

## E2: Expertise

Domain knowledge demonstrated through correctness + depth + addressing edge cases.

### Strong signals
- Correct domain terminology (no misuse)
- Acknowledging edge cases beyond the basics
- Common misconceptions debunked
- Citing peer-reviewed research where applicable
- Industry standards referenced (ISO numbers, RFCs)
- Author has documented credentials in bio

### Weak signals
- Generic overview without depth
- Misusing technical terms
- Skipping caveats / "it depends" without specifics
- Citing only your own blog

### How to demonstrate
- Author byline with credentials
- Author bio at end with full title + employer
- 1+ Tier-1 citation per major claim
- Inline `(Author, Year)` per APA
- Discuss alternative approaches

---

## A: Authoritativeness

Recognized as a source TO others in the field.

### Strong signals
- Backlinks from Tier-1 publishers
- Wikipedia / Wikidata entry exists for brand/author
- Cited by other authoritative sources
- Industry awards / mentions
- Spoke at recognized conferences
- Featured in major media (TechCrunch, Forbes, WSJ, etc.)
- Original research published (with citations from others)

### Weak signals
- Only self-claimed authority ("the leading provider")
- Only mentions from low-domain-authority sites
- Spammy backlink profile

### How to demonstrate in content
- Link to: about page, team page, awards page
- Reference your own published research
- Quote external experts who back your position
- Schema.org `Organization` with `award` + `subjectOf`

---

## T: Trustworthiness

The article + author + site can be trusted not to deceive.

### Strong signals
- HTTPS site-wide
- Privacy policy + Terms accessible
- Author contactable (email or social)
- Last reviewed / updated date visible
- Affiliate / sponsored disclosure when applicable
- Editorial corrections policy
- Reviewer separate from author for YMYL
- No fabricated statistics (every claim sourced)
- No misleading claims

### Weak signals (lower trust)
- Anonymous author
- Stock photos labeled as "real customers"
- Sponsored content without disclosure
- Affiliate links without disclosure (FTC violation in US)
- Statistics with no source
- Outdated information (no last-reviewed date)

### How to demonstrate in content
- ≥3 Tier-1 sources in References
- Inline citations for every numeric claim
- Author bio with contact link
- Last-updated stamp at top + bottom
- Affiliate disclosure block (if applicable, per FTC)

---

## YMYL (Your Money or Your Life) topics

Google holds these to a HIGHER E-E-A-T bar:
- **Medical** — health, drugs, treatment, mental health
- **Financial** — investing, loans, taxes, insurance
- **Legal** — laws, contracts, immigration
- **Safety** — vehicle safety, child safety, food safety
- **Government / civics** — voting, taxes, public services
- **News / journalism** — political, geopolitical events

For YMYL, additionally require:
- Author MUST have documented expertise (license, degree, professional title)
- Editor / reviewer different from author
- Recent dateModified (within 12 months)
- Citations to peer-reviewed sources (not just blog posts)
- Disclaimers where appropriate ("Not medical advice")

YMYL veto triggers (per `core_eeat_scorer.py`):
- **T05**: Author E-E-A-T missing on YMYL → cap at 60
- **T03**: Missing affiliate disclosure on commercial YMYL → BLOCKED

---

## Per-dimension content checklist (in scorer)

### Experience (10 items per `references/geo/core-eeat-80.md`)
- E01: Author describes hands-on use
- E02: First-person ≥10% of paragraphs
- E03: Process details (steps actually taken)
- E04: Time/effort quantified
- E05: Failures / what didn't work mentioned
- E06: Tools / equipment used named
- E07: Setting / context specified
- E08: Outcomes / results measured
- E09: Photos / screenshots from real use
- E10: Compared to alternatives via direct experience

### Expertise (10)
- Ex01: Author credentials in byline
- Ex02-Ex10: see core-eeat-80.md

### Authoritativeness (10)
- A01-A10: see core-eeat-80.md

### Trustworthiness (10)
- T01-T10: see core-eeat-80.md

---

## Per-format E-E-A-T emphasis

| Format | Most important dimension |
|---|---|
| Case study | Experience (data is everything) |
| How-to guide | Expertise (correct + complete steps) |
| Listicle | Experience + Authoritativeness (we tested, we know) |
| Comparison | Trustworthiness (balanced, no shilling) |
| Review | Experience + Trustworthiness (real use + disclosure) |
| Definition | Expertise (correct + nuanced) |
| Pillar | All four (comprehensive coverage) |
| News | Trustworthiness (sourcing, currency) |

---

## How to measure (in CI / scoring)

Run `core_eeat_scorer.py` per article. Pass = 80+ raw, no Vetoes.

For YMYL, additional `--ymyl` flag adds 5 mandatory items:
- Author has documented license/degree
- Reviewer cited separately
- Disclaimer present
- Dates within 12 months
- Tier-1 sources only
