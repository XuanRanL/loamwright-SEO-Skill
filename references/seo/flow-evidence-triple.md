# FLOW Evidence Triple

Every public statistic in a published article needs **three things** to be AI-citation-ready and ranking-defensible:

1. **Year anchor in prose** — explicit time marker so readers + crawlers can place the data
2. **Inline citation** — publisher + title in parenthetical or markdown link
3. **URL with retrieval date in References** — full source attribution

Without all three, the claim is undefendable when Google or an AI engine asks "where did this come from?"

## The rule (mandatory in fact-checker gate)

For every statistic with a numeric value (percentage, dollar amount, multiplier, ratio):

```
{year-anchor prose}  +  ({source-inline citation})  →  full Reference with URL
```

## Examples

### ❌ Fails the triple

> Research shows that 73% of marketers use AI tools.

Missing: year, source, citation, URL. Cannot be verified.

### ✓ Passes the triple

> In 2026, 73% of marketers reported daily AI tool use (HubSpot State of Marketing, 2026).

- **Year anchor**: "In 2026"
- **Inline citation**: "(HubSpot State of Marketing, 2026)"
- **Reference list entry**: `HubSpot. (2026). State of marketing report. https://hubspot.com/marketing-statistics (retrieved 2026-05-19)`

## When the triple is REQUIRED

**Always**:
- Any numeric stat (X%, $Y, Nx)
- Direct quotes
- Named-source claims ("according to Gartner...")
- Comparative claims ("higher than industry average")

**Optional but recommended**:
- Round-number estimates ("millions of users")
- Industry generalizations
- Personal experience (use real first-hand experience (plain prose) instead)

**Never required**:
- Definitions
- Author opinion (clearly labeled)
- Hypothetical scenarios

## How fact-checker enforces this

`agents/fact-checker.md` Step 3-5 pipeline:

```
1. Extract every numeric claim from draft.md
2. For each claim:
   - Has year anchor?       → if no: flag for rewrite OR delete
   - Has inline citation?    → if no: Crossref + Tavily search for source
   - Has resolvable URL?    → link_resolver HEAD check; reject grounding-redirects
3. Build References section (APA 7) from passed claims
4. T04 veto fires if any unresolved fabricated stat remains
```

## Year anchor patterns (acceptable forms)

- "In 2026, ..."
- "As of Q1 2026, ..."
- "By 2026, ..."
- "The 2026 [Source] survey found ..."
- "Since 2024, ..."
- "Between 2023 and 2026, ..."

**Avoid** vague time references:
- "Recently, ..." (when?)
- "These days, ..." (when?)
- "Modern marketers ..." (no time anchor)
- "In recent studies ..." (which year?)

## Inline citation formats

### APA 7 inline (preferred for academic-style)
- `(HubSpot, 2026)`
- `(Smith, 2025, p. 12)` — page-specific quote

### Journalistic inline (preferred for blog content)
- `(HubSpot State of Marketing, 2026)`
- `[Gartner](https://gartner.com/report-2026), 2026`
- `, according to a 2026 Gartner report,`

### Markdown link (when URL is in the citation)
- `73% of marketers use AI ([HubSpot 2026](https://hubspot.com/...))`

## URL requirements

References section entries must have URLs that:

1. **Return HTTP 200** when HEAD-checked (link_resolver.py)
2. **Are canonical** (not URL shorteners that may break)
3. **Are not grounding-redirects** (Google AI cache `vertexaisearch.cloud.google.com/grounding-api-redirect/...`)
4. **Are public** (not behind paywall unless noted as such)
5. **Include retrieval date** for time-sensitive sources

## Tier system

When citing, prefer higher tiers:

| Tier | Examples | When citing |
|---|---|---|
| 1 | Peer-reviewed (DOI), .gov, .edu | Always preferred |
| 2 | Major publishers (NYT, FT, Bloomberg, Reuters, Nature) | Acceptable |
| 3 | Industry SaaS research (HubSpot, Salesforce, McKinsey) | Acceptable for industry stats |
| 4 | Personal blogs, smaller publications | Use sparingly |
| ❌ | AI-generated, untraceable studies, aggregators | NEVER |

## What fact-checker does NOT enforce

- ❌ Whether your interpretation is correct (that's reviewer's job)
- ❌ Subjective claims (no citation needed)
- ❌ "Common knowledge" facts (e.g., the year iPhone launched)
- ❌ Brand-internal claims about your own product

## Composition

```
section-drafter writes draft with [claim:N] markers
        ↓
fact-checker resolves each claim via Crossref + Tavily
        ↓
build References section + replace [claim:N] with (Source, Year)
        ↓
geo-auditor checks Triple compliance per H2
        ↓
T04 veto fires if any claim fails the triple after repair
```

## See also

- `agents/fact-checker.md` — the agent enforcing this
- `references/apa-citation-rules.md` — APA 7 format details
- `references/geo/cite-framework-40.md` — full CITE 40-item rubric
- `references/seo/citation-capsules-princeton.md` — Citation Capsule pattern
