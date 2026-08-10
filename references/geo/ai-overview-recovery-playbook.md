# AI Overview Recovery Playbook

> Used by `subskills/optimize/ai-overview-recovery/` when `drift-detector` flags AIO citation loss.
>
> 4-phase recovery process. Estimated time: 0-28 days.

---

## Why AIO citations get dropped

Google AIO refreshes its sources continuously. Common reasons your article disappears:

| Cause | Frequency | Recoverable? |
|---|---|---|
| Freshness aged | 35% | Easy (update dateModified + add 2026 stats) |
| Better competitor appeared | 25% | Medium (need to differentiate) |
| Structural mismatch | 20% | Medium (restructure H2) |
| Entity confusion | 10% | Hard (Wikipedia / Wikidata fix) |
| Site-wide signal drop | 5% | Very Hard (full site audit) |
| Penalty / spam flag | 3% | Site-wide; need manual action |
| Random rotation | 2% | Wait 1-2 weeks |

---

## Phase 1: Measure Damage (Day 0)

### Inputs
- URL that lost AIO citation
- Affected queries (which queries used to cite us)
- Time of loss (when did GSC show the drop)

### Actions
```
1. Open GSC for the URL
2. Filter by "search appearance: AI Overviews"
3. Identify which queries dropped impressions
4. Calculate traffic impact:
   - Impressions lost
   - Click-through-rate change
   - Resulting clicks lost
5. Re-probe affected queries:
   python -m scripts.fetch.ai_search_probe \
       --brand "{brand}" --domain "{site}" \
       --queries "{q1},{q2},{q3}"
6. Document baseline:
   - Which queries (was citing us, now not)
   - Replacement citations (who Google now cites)
   - Format of replacement (listicle / how-to / etc.)
```

### Output
`projects/{slug}/aio-incidents/{url-slug}-{date}.json`:
```json
{
  "url": "https://example.com/best-fishing-rods-2026",
  "loss_detected_at": "2026-05-15",
  "affected_queries": ["best fishing rods 2026", "fishing rod review", ...],
  "impressions_lost_estimate": 4200,
  "replacement_competitors": ["rival1.com", "rival2.com"],
  "diagnosis_pending": true
}
```

---

## Phase 2: Diagnose Skip Reason (Day 0-2)

Run 4 query strategy classifiers:

### Classifier A: Freshness check
```
✓ dateModified within 12 months?
✓ Stats reference 2026 or later?
✓ Recent comments / updates section?
✓ Annual refresh marker ("2026 update")?
```
If 1+ fails → primary cause: FRESHNESS

### Classifier B: Authority check
```
✓ Referring domains stable?
✓ Tier-1 backlinks present?
✓ Author bio + credentials visible?
✓ Organization schema with sameAs?
```
If 1+ degraded → primary cause: AUTHORITY

### Classifier C: Structure check
```
✓ H2/H3 hierarchy clear?
✓ JSON-LD schemas all present?
✓ Featured Snippet target paragraphs at H2 start?
✓ FAQ schema with 5+ items?
```
If structure simplified vs replacement → primary cause: STRUCTURE

### Classifier D: Entity check
```
✓ Brand name consistent throughout?
✓ Wikidata QID linked?
✓ Wikipedia mention exists?
✓ Author Person schema with credentials?
```
If entity ambiguity rose → primary cause: ENTITY CONFUSION

### Output
`projects/{slug}/aio-incidents/{url-slug}-{date}-diagnosis.json`:
```json
{
  "primary_cause": "freshness",
  "secondary_causes": ["entity_confusion"],
  "confidence": 0.85,
  "evidence": ["dateModified 2024-08; replacement cites 2026 data"],
  "recommended_actions": [...]
}
```

---

## Phase 3: Targeted Rewrite (Day 3-5)

Apply fixes per primary cause:

### If FRESHNESS:
- Update dateModified
- Add 3-5 specific 2026 stats with sources
- Add "2026 update" / "last reviewed [date]" stamps
- Update opening with current-year framing
- Verify all references are from last 18 months

### If AUTHORITY:
- Add 2-3 Tier-1 citations
- Expand References section (10 → up to 15 if needed)
- Add author bio expansion with credentials
- Strengthen Person + Organization schemas
- Add sameAs to social profiles
- Get 1-2 fresh backlinks (outreach campaign — 30-60 day lead time)

### If STRUCTURE:
- Restructure H2 hierarchy to match dominant SERP pattern
- Add Featured Snippet target blocks (40-60w after each H2)
- Expand FAQ section
- Add proper schema graph (Article + FAQPage + ImageObject + BreadcrumbList)
- Ensure ≥2 tables with ≥1 in front 50%

### If ENTITY CONFUSION:
- Submit/update Wikidata entry
- Strengthen Wikipedia mention if applicable
- Make brand naming 100% consistent throughout
- Add Organization schema with foundingDate, address, sameAs
- Disambiguate from similar brands explicitly in body

After rewrite:
- Trigger fact-checker re-run
- Re-run quality gates
- Publish via wordpress-publisher (PATCH same post_id)
- Trigger indexing-notifier

---

## Phase 4: Monitor (Day 7 / 14 / 28)

```
Day 7: Re-probe ai_search_probe for affected queries
       Check GSC AIO impressions
Day 14: Re-probe + GSC + position tracking
Day 28: Re-probe + GSC + final verdict
```

### Outcomes:
| Result at Day 28 | Action |
|---|---|
| Citation restored | Document fix in `learned-patterns.json`; close incident |
| Partial recovery (some queries) | Iterate on remaining causes |
| No recovery | Escalate to from-scratch rewrite OR accept loss |

---

## Anti-patterns (don't do)

- ❌ "Just add the keyword more times" — won't fix AIO
- ❌ "Buy backlinks" — Google penalizes; AIO will drop further
- ❌ Rewriting title without rewriting content
- ❌ Fake "updated" timestamps (Google detects, penalizes)
- ❌ Stuffing FAQ schema with same answer (low quality)
- ❌ Hoping it'll come back without intervention

---

## Cost / time per phase

| Phase | Time | Cost |
|---|---|---|
| 1 Measure | 30 min | $0 (mostly GSC review + 1 probe) |
| 2 Diagnose | 1 hr | ~$0.50 (Tavily + probe re-runs) |
| 3 Rewrite | 2-4 hr | ~$2-3 (LLM rewrite via pipeline) |
| 4 Monitor (3 checkpoints) | 30 min total | $0.50 (probes) |
| **Total** | **~5 hr** | **~$3-4** |

---

## Save the playbook outcome

Every recovery attempt feeds `memory/learned-patterns.json`:
- What signal class caused the drop?
- What fix worked?
- How long to recovery?

This data tunes the playbook for next time.
