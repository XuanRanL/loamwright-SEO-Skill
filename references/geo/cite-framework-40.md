# CITE Framework — 40-Item AI Citation Worthiness Rubric

> Used by `subskills/optimize/quality-gate-cite/` and `scripts/validate/cite_scorer.py`. 
> Borrowed from seo-geo-claude-skills with v3.2 refinements.

CITE = **C**itation worthiness + **I**dentity clarity + **T**rust signals + **E**minence

Each dimension has 10 items, each scored 0/1 (binary). Total possible: 40.

---

## C: Citation Worthiness (10 items, 25% weight)

How extractable + quotable is the content for AI engines?

| ID | Item | Why it matters |
|---|---|---|
| C01 | TL;DR / direct answer in first 540 words | AI grounding cutoff |
| C02 | Each H2 has Citation Capsule (40-60w self-contained) | Princeton GEO +28-41% |
| C03 | ≥1 specific data point per 200 words | Quotability anchor |
| C04 | FAQ section with extractable Q&A | FAQPage schema source |
| C05 | Sentence length variance (burstiness >0.3) | Avoids "uniform AI feel" |
| C06 | All facts have inline (Author, Year) citations | LLM trust signal |
| C07 | References section with ≥3 Tier-1 sources | Authority chain |
| C08 | Statistics shown with year/sample size | "(N=10,000, 2025)" pattern |
| C09 | No fabricated DOIs (verified by HEAD check) | **VETO if violated** |
| C10 | Original data marked with `original data (plain prose)` | Information gain signal |

## I: Identity Clarity (10 items, 25% weight)

Does the AI engine know who you are?

| ID | Item | Why it matters |
|---|---|---|
| I01 | Organization schema with name + URL + sameAs | Entity resolution |
| I02 | Wikidata entry exists for brand | Cross-engine entity match |
| I03 | Wikipedia page (or referenced in one) | High-authority entity |
| I04 | Brand mentioned consistently (same exact name) | Entity disambiguation |
| I05 | Author has Person schema | byline → schema chain |
| I06 | Author bio includes credentials | Expertise signal |
| I07 | Author has external social profiles (sameAs) | Cross-platform identity |
| I08 | Founded date / About info in schema | Disambiguation |
| I09 | Geographic identity (where based) | Local SEO + entity |
| I10 | Industry / category clearly stated | Entity classification |

## T: Trust Signals (10 items, 25% weight)

Why should an AI engine cite this over alternatives?

| ID | Item | Why it matters |
|---|---|---|
| T01 | HTTPS only | Basic table stakes |
| T02 | Privacy policy + Terms linked | YMYL trust |
| T03 | Affiliate / sponsored disclosure (if commercial) | **VETO if missing** — FTC |
| T04 | Statistics verifiable by primary source | **VETO if fabricated** |
| T05 | Author E-E-A-T markup complete | **VETO if missing for YMYL** |
| T06 | Last reviewed / updated date visible | Freshness signal |
| T07 | Reviewer separate from author (if YMYL) | Editorial process |
| T08 | Customer reviews / testimonials present (if applicable) | Social proof |
| T09 | All JSON-LD schemas validate (no errors) | **VETO at cap** |
| T10 | No deprecated schema types (HowTo, etc.) | Schema hygiene |

## E: Eminence (10 items, 25% weight)

Authority strength of the source.

| ID | Item | Why it matters |
|---|---|---|
| E01 | Domain age >2 years | Authority threshold |
| E02 | ≥10 referring domains | Backlink minimum |
| E03 | ≥3 backlinks from Tier-1 publishers | Authority cluster |
| E04 | Domain Rating (Ahrefs) ≥30 OR DA (Moz) ≥30 | Quantified authority |
| E05 | Content updated within 12 months | Freshness premium |
| E06 | Original research / studies published | Source-of-truth status |
| E07 | Cited by other authoritative sources | Backlink reciprocity |
| E08 | Active on multiple platforms (sameAs ≥3) | Distribution breadth |
| E09 | Mentioned in industry publications | Earned media |
| E10 | Has answered media inquiries / cited in journalism | Highest authority |

---

## Vetoes (sub-set within the 40 items)

Three Vetoes that trigger Cap algorithm or BLOCKED verdict:

| Veto | Item | Triggers when | Effect |
|---|---|---|---|
| **T03** | Missing affiliate / sponsored disclosure | Article is commercial (review, comparison, listicle with affiliate links) AND no disclosure block | CAP final score at 60 |
| **T05** | Missing E-E-A-T markup | YMYL industry (health, finance, legal) AND author Person schema missing OR no credentials | CAP final score at 60 |
| **T09** | Schema broken | Required schema types missing OR JSON-LD validation fails | CAP final score at 70 |

Cap algorithm:
- 0 Vetoes: `final_score = raw_score`
- 1 Veto: `final_score = min(raw_score, cap_value)` for that veto
- 2+ Vetoes: verdict = BLOCKED, `final_score = min(raw_score, 50)`

---

## Scoring

```
raw_score = sum(item_score for item in 40_items)  # 0-40
percentage = raw_score / 40 * 100                  # 0-100
verdict = "SHIP" if percentage >= 80 and no vetoes
          else "FIX" if percentage >= 60
          else "BLOCKED"
```

For ranking among multiple articles:
```
weighted = (C_score * 0.25 + I_score * 0.25 + T_score * 0.25 + E_score * 0.25)
```

(Per-dimension weights can be adjusted per industry; default 25% each.)

---

## How to use this rubric

### At drafting time (section-drafter)
After writing each H2, check:
- C02: did I include a Citation Capsule?
- C03: do I have a specific data point in this section?
- C05/C08: is my sentence variance good and stats shown with year?

### At fact-check (fact-checker agent)
- C06: every claim has inline citation
- C07: References section has Tier-1 sources
- C09: HEAD check passed for all DOIs
- T04: every statistic traceable to primary

### At schema-generator
- I01-I10: schema completeness
- T01, T09: schema validation
- T03: affiliate/sponsored block injection

### At quality-gate-cite (the final gate)
- Run all 40 items through `scripts/validate/cite_scorer.py`
- Output `quality.gates.cite` JSON
- Trigger repair if score <80 OR veto triggered

---

## See also

- `references/geo/core-eeat-80.md` (broader E-E-A-T 80-item gate)
- `references/seo/citation-capsules-princeton.md` (C02 details)
- `references/seo/seo-checklist-2026.md` (related checklist)
- `scripts/validate/cite_scorer.py` (automated scoring)
- `schemas/quality.schema.json` (output format)
