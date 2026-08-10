---
name: fact-check-and-citation
description: Verify every statistical claim by fetching cited URLs + checking the data appears on the page. Crossref-first for academic; Tavily-fallback for industry. Replaces fabricated/unsourced stats. Builds APA 7 References block, ≤10 entries, all link-resolvable. The single most important anti-hallucination gate in the pipeline. Use after section-drafter (before humanizer if humanizer might break citations) or after humanizer (preferred — humanizer doesn't touch quoted material).
allowed-tools: [Read, Write, Edit, Bash, Task, WebFetch]
disable-model-invocation: false
user-invocable: true
---

# Fact-Check and Citation

The single most important anti-hallucination step. Without it, LLM-fabricated statistics make it to publication. With it, every cited fact is real and verifiable. Without exception.

## When to invoke

- After `section-drafter` completes (Stage: humanizer-complete OR section-drafted)
- Before `assembly` (final draft.md assembly)
- Auto-triggered by `repair-orchestrator` when any C01 (fabricated citation) veto fires
- User can manually invoke `/factcheck workspace/{task_id}/draft.md`

## Inputs

- `workspace/{task_id}/sections/*.json` — each has `claims[]` array
- `workspace/{task_id}/research.json` — Tier-1 source candidates already discovered
- `references/apa-citation-rules.md`

## Workflow

### Step 1: Extract all statistical claims

Scan the draft for every claim that includes a number, percentage, dollar amount, or named source. Build claims list:

| Field | Description |
|---|---|
| claim_text | The exact sentence or phrase containing the statistic |
| value | The numeric value (e.g., "42%", "$1.2M", "3x") |
| attribution | Named source if present (e.g., "HubSpot", "Gartner 2025") |
| url | Cited URL if present (markdown link or parenthetical) |
| location | Heading or line number where the claim appears |

### Step 2: Spawn fact-checker agent

```bash
# Internal — fact-checker is the agent that does the actual verification work
```

Invoke `agents/fact-checker.md` with:
- `sections_dir = workspace/{task}/sections/`
- `mode = "fact-check"`
- `max_refs = 10` (or 15 for case-study / data-research formats)

The fact-checker has the tool whitelist: `Read, Write, WebFetch, Bash`.

### Step 3: Per-claim verification pipeline

For each claim with `needs_source=true`:

1. **Crossref lookup** (academic preference, free, fast)
   ```bash
   python -m scripts.fetch.crossref_lookup "{hint_query}" --rows 5 --apa
   ```
   If hit + DOI → step 4.

2. **Link resolver check on DOI URL**
   ```bash
   python -m scripts.validate.link_resolver "https://doi.org/{doi}"
   ```
   If 200 OK → USE IT.

3. **Tavily advanced fallback** (for industry, news, recent statistics)
   ```bash
   python -m scripts.fetch.tavily_search "{hint_query}" --depth advanced
   ```
   For top-3 results → run link_resolver. First passing → USE IT.

4. **If nothing resolves** → mark claim as `deleted`. Surface to writer to rewrite the paragraph without the unsupportable claim.

### Step 4: Verification scoring (per claim)

| Score | Status | Criteria |
|---|---|---|
| 1.0 | VERIFIED | Exact number found on cited page in matching context |
| 0.7-0.9 | PARAPHRASE | Similar data with different wording, rounding, or timeframe |
| 0.3-0.6 | WEAK | Source page covers topic but specific stat not visible |
| 0.0 | NOT FOUND | Cited page does not contain the claimed data anywhere |
| N/A | UNVERIFIED | No source URL provided for the claim |

Scoring guidance:
- "43%" when source says "nearly half" → 0.8
- "2024" data when source has "2023" → 0.7
- Citation to homepage when stat lives on subpage → 0.3
- 404 / unreachable URL → 0.0

### Step 5: Claim extraction patterns (regex hints)

**Fully cited (highest confidence)**:
- `[Number]% [claim] ([Source], [Year])` — parenthetical citation
- `[claim] [Number]% ... [markdown link to source]` — inline link
- `According to [Source], [Number]...` — attribution lead

**Uncited statistics (flag for sourcing)**:
- `[Number]% of [noun phrase]` — standalone percentage
- `[Number]x more/less/higher/lower` — multiplier claims
- `$[Number] [claim]` — dollar figures without attribution

**Weak signals (check context before extracting)**:
- "studies show", "research indicates", "data suggests" + nearby number
- "survey found", "report reveals", "analysis shows" + nearby number
- Round numbers in isolation ("millions of users") — skip unless specific

### Step 6: Build References section

Output `workspace/{task_id}/citations.json` per `schemas/citations.schema.json`, AND
`workspace/{task_id}/fact-check.json` per `schemas/fact-check.schema.json` — its `verdict`
is EXACTLY one of `CLEAN | CLEAN_WITH_NOTES | FIX_REQUIRED | BLOCK_PUBLISH` (any other
string fails closed at the orchestrator gate and pre_publish_gate; `CLEAN_WITH_NOTES` is
the canonical "issues found and fixed in place" verdict — 2026-08-02,
`scripts/pipeline/fc_verdict.py`).

**Canonical top-level key is `citations`** (matches `wp_publisher._load_citation_entries`
canonical reader path). Legacy/alternate keys also accepted by the publisher:
`refs`, `references`, `items`, or bare top-level list — but new emitters
should write `citations` for clarity and forward-compat.

**URL-resolution recording (v3.38.3, mandatory):** a ref that is REAL but
bot-walled (Taylor & Francis / MDPI / ASTM return HEAD 403 to script UAs) gets
`url_verified: true` + `resolved_status: "bot-403"` (the STRING — never the bare
int `403`, which reads as a broken ref and fires the C01 fabricated-citation
veto) + a `resolution_note` naming how it was verified (Crossref masthead /
browser UA). `url_verified: true` is authoritative for the C01 scorer. A ref you
could not verify anywhere gets `url_verified: false`. Full contract:
`agents/fact-checker.md` §"URL resolution recording".

```json
{
  "task_id": "abc123",
  "citations": [
    {
      "id": 1,
      "apa_7": "Smith, J. (2024). Title of work. Publisher. https://doi.org/10.1234/xyz",
      "url": "https://doi.org/10.1234/xyz",
      "url_verified": true,
      "tier": 1,
      "type": "peer_reviewed",
      "verified_via": "crossref",
      "claim_markers_resolved": ["c1_3", "c2_5"]
    }
  ],
  "in_text_replacements": [
    {"marker": "[claim:c1_3]", "replace_with": "(Smith, 2024)"},
    {"marker": "[claim:c4_exp]", "replace_with": ""}
  ],
  "deleted_claims": [{"id": "c2_4", "reason": "no_resolvable_source"}],
  "verification_summary": {
    "total_claims": 18,
    "verified": 12,
    "paraphrase": 3,
    "weak": 1,
    "not_found": 0,
    "unverified": 0,
    "deleted": 2
  }
}
```

### Step 7: APA format validation

```bash
python -m scripts.validate.apa_format_validator workspace/{task}/citations.json
```

Verifies all entries match APA 7 format. Failure → fact-checker agent retries.

## Critical rules

### NEVER fabricate

LLMs are prone to invent plausible-sounding citations. We block this physically by:

1. **Crossref is the ONLY source for DOIs** — we don't trust LLM to generate DOIs
2. Every URL goes through `link_resolver.py` HEAD check
3. URLs in UNRELIABLE_HOSTS list (cdn.openai.com, certain aggregators) are rejected
4. URL shorteners are resolved to canonical first
5. Grounding-redirect URLs (Google AI cache) are rejected
6. AI-generated content URLs are rejected

### Tier preference

1. Crossref-verified DOIs (Tier 1) — peer-reviewed
2. `.gov` / `.edu` URLs (Tier 1)
3. Major publishers (NYT, FT, Bloomberg, Reuters) (Tier 2)
4. Industry SaaS research with published methodology (Tier 3)
5. Personal blogs (Tier 3, accept sparingly)
6. NEVER: AI-generated content, untraceable studies, aggregator URLs

### Reference cap

- Default: 10 max
- Exception for `data-research` / `case-study` formats: up to 15

## FLOW Evidence Triple (required for every public statistic)

Three required elements for every numeric claim that survives verification:

1. **Year anchor in prose** — "In 2026," or "as of Q1 2026"
2. **Inline citation** — publisher + title in parenthetical
3. **URL with retrieval date** — in References section

Without all three, the claim is not citation-ready for AI engines.

## Limitations

- **Paywalled content**: WebFetch cannot access content behind login walls. Score as WEAK (0.5) with paywall note.
- **Dynamic pages**: JS-rendered content may not be available via WebFetch. If minimal content returned, note in status.
- **PDF sources**: WebFetch may not extract PDF text reliably. Flag PDF URLs for manual verification.
- **Archived pages**: If URL returns 404, suggest checking web.archive.org.
- **Rate limits**: Process no more than 10 URLs per run. If >10 cited URLs, verify first 10, list rest as SKIPPED.

## Handoff

After successful citations.json:
- `recommended_next_skill`: `assembly` (script, no LLM)
- `key_findings`: `{"refs_resolved": 8, "deleted_claims": ["c2_4"], "unverified_count": 0}`

If significant deletions (>3 claims deleted):
- `completion_status`: "DONE_WITH_CONCERNS"
- Trigger `section-drafter` retry for the specific paragraphs that lost their support

If all citations fail:
- `completion_status`: "BLOCKED"
- Escalate to `repair-orchestrator` (research quality issue, not fact-check failure)

If C01 veto triggers (fabricated citation detected):
- Hard fail — escalate to repair level 3+
- Article does not publish until resolved

## Cost estimate

Typical article with 15 unique claims:
- 15× Crossref (free)
- ~10× Tavily advanced fallback for non-academic claims = 20 credits = $0.16
- ~25× link_resolver HEAD checks (free)
- ~1× Claude Opus synthesis + APA formatting = $0.10
- **Total: ~$0.26 per article**

## See also

- `agents/fact-checker.md` — the agent doing verification work
- `scripts/fetch/crossref_lookup.py`
- `scripts/fetch/tavily_search.py`
- `scripts/validate/link_resolver.py`
- `scripts/validate/apa_format_validator.py`
- `references/apa-citation-rules.md`
- `references/seo/citation-capsules-princeton.md` — FLOW Evidence Triple full spec
