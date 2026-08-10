---
name: rewrite
description: Rewrite + optimize an existing published article. 6-phase workflow (Audit → Research → Chart Gen → Content Rewrite → Verification → Summary). Preserves author voice while applying 6 pillars — fabricated stat replacement, answer-first formatting, AI-detection scrubbing, citation capsule injection, freshness signals, information gain markers. Use /rewrite <file> for full rewrite OR /update <file> for freshness-only refresh.
allowed-tools: [Read, Write, Edit, Bash, Task, WebFetch, WebSearch]
disable-model-invocation: false
user-invocable: true
---

# Rewrite · Optimize Existing Posts

For ranking-decay rescue, refresh cycles, or quality lift on already-published articles. Preserves the author's voice while applying 6 optimization pillars.

## When to invoke

- `/rewrite <file>` — full optimization pass
- `/update <file>` — freshness-only mode (minimal changes, focus on dates + stats)
- Auto-triggered by `content-refresher` when GSC + drift signals indicate rank decay
- Auto-suggested in `outcome_tagger` output for `loser`-tagged articles

## 6 phases

### Phase 1: Audit (read-only)

1. **Read the post** — detect format (MDX / markdown / HTML / WordPress block)
2. **Run quality checklist** against `references/seo/seo-checklist-2026.md`:
   - Count fabricated vs sourced statistics
   - Check answer-first formatting (H2 → stat in first sentence?)
   - Count images + charts (type diversity?)
   - Measure paragraph lengths (any >150 words?)
   - Check heading hierarchy (H1 → H2 → H3, no skips?)
   - Look for FAQ schema
   - Check freshness signals (`lastUpdated`, `dateModified`)
   - Assess self-promotion level
   - Evaluate citation tier quality

3. **AI content detection scan**:
   - **Burstiness score** — sentence length variance. Target SD > 6.
   - **Banned phrase scan** — check against `references/style/banned-words.md`
   - **Vocabulary diversity** — TTR (unique/total). Target > 0.50.
   - **AI content estimate** — composite percentage 0-100%

4. **Video embed check** — if 0 YouTube embeds, flag (strongest AI visibility correlation 0.737)

5. **Cannibalization check**:
   - Identify primary keyword
   - Grep portfolio for other posts targeting same keyword
   - Flag overlap; recommend merge OR differentiate

6. **Calculate current score** across 5 categories:
   - Content Quality (30)
   - SEO Optimization (25)
   - E-E-A-T Signals (15)
   - Technical Elements (15)
   - AI Citation Readiness (15)
   Total: 0-100

7. **Present audit summary** + AI detection results + video status + cannibalization status

8. **Plan mode** — section-by-section optimization plan, wait for user approval

### Phase 2: Research

1. **Identify the post's core topic** from existing content
2. **Find replacement statistics** for fabricated/unsourced data:
   ```bash
   python -m scripts.fetch.tavily_search "{topic} study 2025 2026 data statistics" --depth advanced
   ```
   Target Tier 1-3 sources only.

3. **Find images** if post has <3:
   - Pixabay: `site:pixabay.com [topic keywords]`
   - Unsplash: `site:unsplash.com [topic keywords]`
   - Verify HTTP 200 via link_resolver

4. **Plan charts** if post has <2:
   - Identify data suitable for visualization
   - Select diverse chart types (no repeats)

### Phase 3: Chart generation

If post needs more visual elements, invoke `chart-generator` subskill:

1. Select chart type using diversity rule
2. Pass: chart type, title, data values, source, platform format
3. Embed returned SVG within `<figure>` wrapper
4. Target 2-4 charts per 2,000-word post

### Phase 4: Content rewrite (10-step pipeline)

#### 4a. Preserve what works
- Keep author voice + unique perspective
- Preserve original insights + first-hand experience
- Keep existing quality images + charts
- Maintain internal links

#### 4b. Fix frontmatter
- Add `lastUpdated: "YYYY-MM-DD"` (today)
- Keep original `date` unchanged
- Fix meta description: fact-dense, 150-160 chars, includes 1 statistic
- Add `coverImage` + `coverImageAlt` + `ogImage` if missing
- Verify tags/categories appropriate

#### 4c. Apply answer-first formatting
Every H2 section MUST open with a 40-60 word paragraph containing:
- At least one specific statistic with source attribution
- A direct answer to the heading's implicit question

#### 4d. Replace fabricated statistics
- Search patterns: `[Number]%`, `[Number]x`, unsourced claims
- Replace with real data from Tier 1-3 sources
- Always include inline attribution: `([Source Name](url), year)`

#### 4e. Improve headings
- Convert statements to questions where natural (60-70% target)
- Keep 2-3 statement headings for variety
- Ensure keyword appears in 2-3 headings naturally

#### 4f. Fix paragraph length
- Split any paragraph >150 words
- Target 40-80 words per paragraph
- Each paragraph starts with its most important sentence

#### 4g. Add visual elements
- Embed new images after H2 headings, spaced evenly
- Embed charts within relevant sections
- Adapt embed format to detected platform

#### 4h. Add YouTube embeds (if missing)
- Search 2-3 relevant videos
- Embed via platform-appropriate format (srcdoc lazy loading)
- Place: 1 after introduction, 1-2 mid-article
- Include noscript fallback for AI crawlers

#### 4i. Add/improve FAQ
- If no FAQ exists, add 3-5 questions
- If FAQ exists, ensure answers are 40-60 words with statistics
- Add FAQ schema markup

#### 4j. Reduce self-promotion
- Max 1 brand mention (author bio context only)
- Remove "At [Company], we..." patterns
- Convert promotional sections to educational content

#### 4k. Citation Capsule injection
For each H2 section, generate or improve a citation capsule:
- 40-60 word self-contained passage per H2
- Contains: one specific claim + one data point + source attribution
- Declarative style — AI system can extract and quote directly
- Placed naturally within section body, not as separate callout

#### 4l. Anti-AI-detection patterns
- Eliminate em dashes — replace every U+2014 with comma, hyphen, colon, period
- Replace flagged AI phrases from `references/style/banned-words.md`
- Vary sentence length deliberately — inject short (5-10 words) between long (18-25 words)
- Inject rhetorical questions every 200-300 words
- Use contractions naturally
- Include hedging language ("in our experience", "we've found that")

#### 4m. Summary box (Key Takeaways)
If post lacks summary box, add immediately after introduction:
```markdown
> **Key Takeaways**
> - [Core finding with statistic and source]
> - [Second key insight]
> - [Third actionable takeaway]
```
3-5 bullets, 40-60 words combined, self-contained.

Configurable label per brand: "The Bottom Line" / "Quick Summary" / "What You Need to Know" / "TL;DR".

#### 4n. Information Gain (PROSE — never bracketed markers)

🔴 **Do NOT inject `[ORIGINAL DATA]` / `[PERSONAL EXPERIENCE]` / `[UNIQUE INSIGHT]` markers.** They are FORBIDDEN: `render_lint` **L6** hard-vetoes them and they are stripped at publish, so they can never reach a reader. (This step previously told you to inject them — a Rule-11 fan-out miss, fixed 2026-07-14.) Write the substance as plain prose instead:

- **Proprietary data / experiments** — only if they genuinely exist. ⚠️ Never invent one.
- **First-hand observations** — only if REAL. ⚠️ Never invent a test, tasting, visit, or customer.
- **Novel analysis / an honest trade-off named / a common error corrected / a comparison nobody publishes** — always available, always legitimate, and the right default when there is no first-party data.

If post lacks original value markers:
- Ask author for first-hand data or experience
- At minimum, add analytical insights connecting existing research in new ways
- Target: ≥2-3 markers per post

### Phase 5: Verification

After rewriting, verify ALL quality gates pass:

#### Core quality gates
1. Every H2 opens with statistic + source
2. No paragraph exceeds 150 words
3. Zero fabricated statistics
4. Heading hierarchy clean
5. FAQ section present with schema
6. Images have descriptive alt text
7. Cover image present (`coverImage` + `ogImage`)
8. If MDX: build project to verify no compilation errors

#### New element verification
9. TL;DR box present after introduction (40-60 words, contains statistic)
10. ≥2-3 information gain markers present
11. Citation capsules in major H2 sections (40-60 words, self-contained)
12. Internal linking zones marked or actual links present (5-10 per 2,000 words)
13. No banned AI phrases remain

#### Burstiness + naturalness check
14. Sentence length variance: SD > 6
15. Contractions used naturally throughout
16. Rhetorical questions present (1 per 200-300 words)
17. AI content estimate reduced from audit baseline
18. Score improved across all 5 categories vs Phase 1 audit
19. YouTube video embeds present with lazy loading, aria-labels, noscript fallback

### Phase 6: Summary

```
## Optimization Complete: [Title]

### Score Change
- Before: [X]/100 ([Rating])
- After: [Y]/100 ([Rating])
- [Per-category breakdown]

### AI Detection
- Before: ~[X]% AI-detected
- After: ~[Y]% AI-detected
- Phrases replaced: [N]
- Burstiness improved: [SD-before] → [SD-after]

### Cannibalization
- [Status: none / flagged N posts / resolved]

### Changes Made
- [X] statistics replaced with sourced data
- [X] SVG charts added (types: ...)
- [X] images added
- Answer-first formatting applied to [N] H2 sections
- FAQ schema with [N] questions
- TL;DR box: [added/updated]
- Information gain markers: [N]
- Citation capsules: [N] across H2 sections
- AI phrases replaced: [N]
- lastUpdated → [date]
- Self-promotion reduced to [N] mentions

### Ready for
- /audit <file> to verify final score
- /publish (republish to WP) or manual deploy
```

### Phase 7: Record the optimization (closes the monitor verify loop)

After the rewrite is republished to the live URL, RECORD it so `phase-monitor` can verify the
ranking delta at T+14/T+30 (Rule 6: this is the real executor for the "fixer skills should call
--record" wiring — not a prose note). Capture a `before`/`after` of the single most material change
(e.g. the title or the primary H2 answer) and the driving query:

```bash
python -m scripts.monitor.optimization_journal --record \
    --site {project_slug} --post-id {post_id} --url {live_url} \
    --type rewrite --query "{primary_keyword}" \
    --before "{before_snippet}" --after "{after_snippet}"
```

Then `phase-monitor` runs `optimization_journal --verify --site {slug} --window 14` to measure whether
the rewrite actually moved the metric. Skip `--record` only for a pure typo fix (no rank intent).

## Update mode (freshness-only)

When invoked as `/update <file>`, focus on freshness:

1. Update statistics to latest available data (2025-2026)
2. Add new developments since last update
3. Refresh images if older than 1 year
4. Update `lastUpdated` in frontmatter
5. Preserve existing structure — minimize rewrites
6. Target: ≥30% content change to register as "fresh" for AI crawlers

## When NOT to rewrite (defer to other skills)

- Pure typo fix → use direct Edit, not /rewrite
- New language version needed → `/locale-audit` then `/translate`
- Voice mismatch only → use `/humanize`
- Schema markup missing only → use `/schema`
- Internal links missing only → use cross_article_linker.py
- Fact-check needed only → use `/factcheck`

`/rewrite` is the comprehensive umbrella; use targeted skills when scope is narrower.

## Cost estimate

Typical 2,000-word article full rewrite:
- 1× Claude Opus comprehensive pass: ~$0.40
- 2× Tavily advanced for new sources: $0.03
- 1-2× chart generation: $0.01
- Total: ~$0.45

Update mode is cheaper (~$0.15) since it's mostly date + 1-2 stats.

## See also

- `subskills/optimize/humanizer/SKILL.md` — Phase 4l AI-detection scrubbing
- `subskills/build/fact-check-and-citation/SKILL.md` — Phase 4d source verification
- `subskills/build/citation-capsule-builder/SKILL.md` — Phase 4k capsule generation
- `subskills/monitor/content-refresher/SKILL.md` — auto-detects when to invoke /rewrite
- `references/seo/seo-checklist-2026.md` — full quality scoring rubric
