# Source Freshness Rules

Per-topic time-sensitivity thresholds. Used by `scripts/lint/source_freshness_check.py` + `agents/fact-checker.md`.

## Why freshness matters

- **AI engines** (especially Google AIO) heavily prefer recent dateModified
- **Reader trust**: a 2018 statistic about "current AI adoption" reads as stale
- **Compliance**: regulations change; outdated regulatory citations are misleading
- **E-E-A-T**: Google quality raters check date currency

## Default freshness thresholds

For a published 2026 article, cited sources should be:

| Topic category | Max source age | Hard fail age | Notes |
|---|---|---|---|
| **Tech / AI / Software** | 2 years | 4 years | Fast-moving; AI tech moves every 6 mo |
| **SEO / Digital marketing** | 2 years | 4 years | Algorithm + platform changes |
| **News / current events** | 3 months | 12 months | Breaks become "old" fast |
| **Financial markets** | 1 year | 2 years | Quarterly numbers preferred |
| **Cryptocurrency** | 6 months | 2 years | Highly volatile |
| **Medical / health** | 5 years | 10 years | Slower-moving science |
| **Pharmaceutical** | 3 years | 8 years | FDA changes |
| **Mental health** | 5 years | 10 years | Research evolves slowly |
| **Legal / regulatory** | Match effective date | 5 years | Some laws stable for decades |
| **Demographics / Census** | 5 years | 10 years | Updated every 5-10 years naturally |
| **Industry size / revenue** | 2 years | 4 years | Annual reports drive this |
| **Education** | 5 years | 10 years | Curriculum changes slow |
| **Historical / classical** | Unlimited | Unlimited | "1750 Treaty of Aix-la-Chapelle" stays valid |
| **Cultural / arts** | 5-10 years | Unlimited | Slow cultural shifts |
| **Real estate market** | 1 year | 3 years | Market moves yearly |
| **Travel / hospitality** | 2 years | 4 years | Industry recovers/shifts post-events |
| **Food / restaurants** | 5 years | 10 years | Recipes timeless, restaurant data not |
| **Climate / environment** | 3 years | 8 years | Data updates regularly |

## Detection logic

For each cited source in References + inline:

1. **Extract year**:
   - From APA-format citation: `(Author, 2024)` → 2024
   - From URL: `2024/01/15` in path
   - From dateModified meta tag (requires fetch)
   - From explicit "as of YYYY" prose

2. **Classify topic**: keyword analysis of article + brief metadata
   - "AI / GPT / LLM / ChatGPT" → Tech / AI category
   - "SEO / ranking / Google" → SEO category
   - "stock / market / earnings" → Financial markets
   - etc.

3. **Compare** source year against topic threshold:
   - Within max threshold → ✓ Fresh
   - Within hard-fail threshold → ⚠️ Stale (warning)
   - Beyond hard-fail → ✗ Too old (must replace or remove)

4. **Output report**:
   - Per-source freshness status
   - Recommended actions for stale sources

## CLI example

```bash
python -m scripts.lint.source_freshness_check \
    --input draft.md \
    --topic tech \
    --json
```

```json
{
  "topic": "tech",
  "max_age_years": 2,
  "hard_fail_age_years": 4,
  "sources_analyzed": 12,
  "fresh_sources": 8,
  "stale_sources": 3,
  "fail_sources": 1,
  "stale_details": [
    {
      "claim": "73% of marketers use AI",
      "source_year": 2022,
      "age_years": 4,
      "status": "stale",
      "recommended_action": "Find 2025+ replacement"
    }
  ],
  "fail_details": [
    {
      "claim": "ChatGPT has 100M users",
      "source_year": 2020,
      "age_years": 6,
      "status": "fail",
      "recommended_action": "REQUIRED: replace with recent source"
    }
  ]
}
```

## What fact-checker does with stale sources

```
For each stale source:
  1. Search Tavily for SAME claim with newer date
  2. If found and resolves: replace the citation
  3. If not found: mark claim for rewrite (delete or change wording to remove time-sensitivity)
  4. Log in citations.json
```

## Special cases

### "As of {Year}" qualifier

If the prose explicitly says "As of 2022, ..." then the source can be older. The qualifier preserves accuracy.

✗ Bad: "73% of marketers use AI" (no year) → fail if source is 2022
✓ OK: "As of 2022, 73% of marketers used AI tools" → 2022 source is fine

### Historical claims

If the claim is about a historical event:

✗ Bad: "1750 Treaty of Aix-la-Chapelle" cited from 2024 source about 2024 events → fail
✓ OK: "1750 Treaty of Aix-la-Chapelle ended the War of the Austrian Succession" → unlimited age OK

### Methodology references

Citing the methodology behind a research approach:

✓ OK: "Following the framework established by Anderson (1985), ..." → methodology citation always valid

### Forward-looking claims

"By 2030, AI will..." — the claim itself is forward; source should still be recent (≤2 years for predictions).

## Update topic thresholds

For new topics or refinements:

```yaml
# In config (future)
freshness_thresholds:
  custom_topics:
    crypto: { max: 6mo, fail: 2y }
    climate: { max: 3y, fail: 8y }
```

## See also

- `references/seo/flow-evidence-triple.md` — year anchor requirement
- `scripts/lint/source_freshness_check.py` — implementation
- `references/seo/authoritative-sources-catalog.md` — source authority tiering
