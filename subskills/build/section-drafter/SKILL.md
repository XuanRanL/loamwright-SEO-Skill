---
name: section-drafter
description: Dispatches N writer agents in parallel, one per H2 section, each receiving an isolated context with section spec + style references + research brief slice. Writes each section to workspace/{task}/sections/{N}.json conforming to section.schema.json. Critical Build phase step. Use after outline-architect produces outline.json.
allowed-tools: [Read, Write, Task]
---

# Section Drafter (Parallel Dispatcher)

This skill is a **dispatcher**, not a writer. It spawns N parallel `writer` agents (one per H2), each writing one section in isolation, then collects results.

## References section is NOT dispatched (ownership contract, 2026-07-07)

The outline's final `## References` section gets **no writer**: the fact-checker
builds its content (citations.json) and `finalize-references-signature` renders it.
Do NOT spawn a writer for it and do NOT hand-create a `sections/NN_references.md`
placeholder — `assemble.py` auto-appends the `## References` stub when no section
file supplies one, and `section_completeness_check` exempts the References outline
entry (reported in `exempt_indices[]`). Before 2026-07-07 every batch operator had
to rediscover the hand-made placeholder just to pass the completeness gate.

## Inputs

- `outline.json` (N sections to write)
- `angle.json` (title, hook, format_id, modifiers)
- `research.json` (overall research)
- `research-brief.json` (filtered quotes & stats, per H2) — OPTIONAL: produced only by
  an out-of-band head-of-research run; the normal runner flow has writers reading
  research.json directly (wiring status documented 2026-07-06 in agents/head-of-research.md)
- `projects/{slug}/brand-voice.md` OR `brand-config.json.voice_pair`

## Output

`workspace/{task_id}/sections/{NN}_{slug}.md` — one file per non-References
outline section, where **NN = the zero-padded ZERO-BASED outline index**
(outline index 0 → `00_...`; `section_completeness_check` diffs the numeric
prefixes against `outline.sections[].index` verbatim — a 1-based prefix reads
as "section 0 missing + phantom section N" and fails the gate; 2026-07-19).
Legacy JSON form `sections/{0..N-1}.json` per `schemas/section.schema.json`
is still accepted by assemble.py.

**Writers emit PLAIN headings** (`## Title`, never `## Title {#anchor}`): the
`anchor_id` in each dispatched section_spec is assembly metadata — assembly
computes canonical anchors from heading text, and a writer-copied anchor
desynchronized the TOC + duplicated the Conclusion on 2026-07-19 (both now
machine-corrected in anchor_link_builder/assemble, but the contract stands).

## Parallel dispatch pattern

```python
tasks = []
for section in outline.sections:
    # Slice research relevant to this H2
    research_slice = filter_research_for_section(research_brief, section.h2, section.section_intent)
    # Context summary of OTHER sections (≤800 words; not full draft)
    context_summary = summarize_others(outline.sections, exclude_index=section.index, max_words=800)
    
    tasks.append({
        "subagent_type": "writer",
        # section_spec.anchor_id is ASSEMBLY metadata — tell the writer to
        # ignore it for heading text (plain `## H2`, no {#anchor}); see Output.
        "section_spec": section,
        "context_summary": context_summary,
        "title": angle.title,
        "hook": angle.hook,
        "format_id": angle.format_id,
        "modifiers": angle.modifiers,
        "primary_keyword": brief.primary_keyword,
        "secondary_keywords": brief.secondary_keywords,
        "research_brief_relevant_section": research_slice,
        "quotes_and_stats_bank": filter_bank(research_brief, section),
        "voice_pair": brand.voice_default.pair,

        # v5.1 image-slot wiring (audit 2026-05-25 — writers omit or rename
        # [IMAGE-SLOT-X] placeholders when they don't receive slot_id names).
        # Load image-prompts.json and match slot_id to section by outline
        # image_slots[].position or by sections[].image_slot boolean order.
        # Writer receives the EXACT slot_id string to embed; no guessing.
        "image_slot_info": _match_image_slot_to_section(
            outline.get("image_slots", []),
            image_prompts,  # loaded from workspace image-prompts.json
            section,
        ),
        # Returns None when this section has no allocated image, or:
        # {"slot_id": "hps-vs-led", "position": "in_section_4",
        #  "description": "Side-by-side HPS vs LED...", "is_featured": false}
        # Writer MUST embed [IMAGE-SLOT-{slot_id}] at the indicated position.

        # v5.0 Stage C wiring (audit 2026-05-22 found this was missing — writers
        # produce generic content even when seo-blog detected local_mode=true).
        # ALL four fields below MUST be passed; agents/writer.md expects them.
        "local_mode": brief.get("local_mode", False),
        "location_anchor": brief.get("location_anchor"),  # null when local_mode=false
        "locality_signals_required": (
            6 if brief.get("local_mode")
              and section.get("block_type") == "unique_per_locality"
            else 0
        ),
        "local_article_pattern": (
            (business_context or {}).get("location", {}).get("local_article_pattern")
            if brief.get("local_mode") else None
        ),

        # v3.36.0 company-facts wiring (audit 2026-07-06 — three writers/optimizers
        # invented the agency's OWN tenure in one batch because nothing supplied the
        # real numbers). Writers may state company self-facts (tenure / team size /
        # clients served) ONLY from this block; the deterministic brand-fact-check
        # stage hard-fails contradictions against business-context.company.
        # v3.38.3: the same block gates EXPERIENCE ANECDOTES — a writer may narrate
        # a first-person event ("we printed N units for a client in Q1") ONLY when
        # that experience exists here or in the research brief; a fabricated
        # anecdote carries no number for brand-fact-check to catch, so the writer
        # red line (agents/writer.md "Never fabricate ... anecdote") is the gate.
        # Greenfield projects (no company.team, no case studies) => writers use
        # original analysis (plain prose) instead of real first-hand experience (plain prose).
        "company_facts": (business_context or {}).get("company"),

        "references_to_load": [
            # CRITICAL — publish-blocking rules; load FIRST every run.
            # Audit 2026-05-22: omitting this doc has been root cause of 4+ post-publish
            # incidents (raw <strong> escapes, Pandoc {#anchor}, broken srcset,
            # image-placeholder drift). render_lint will hard-veto any violation.
            "references/style/markdown-authoring-conventions.md",
            # Visual-design components catalog (v3.31, 2026-06-30). Loaded so writers can
            # realize the section's design_components as native-markdown (tables, cited-stat
            # blocks, quotations, callouts, glossary) that the scoped CSS styles.
            "references/style/visual-design-components.md",
            "references/style/voices/" + voice + ".md",
            "references/style/purposes/" + purpose + ".md",
            "references/style/banned-words.md",
            "references/style/ai-tells-43.md",
            "references/style/em-dash-prohibition.md",
            "references/seo/citation-capsules-princeton.md",
            f"templates/{angle.format_id}.md",
        ] + (
            # Load Sterling Sky 80/20 guidance ONLY when writing a local article
            [
                "references/local/sterling-sky-80-20-rule.md",
                "references/local/industry-to-schema-mapping.md",
            ]
            if brief.get("local_mode") else []
        )
    })

# Dispatch all N in single batch (Task tool with multiple invokes)
results = await dispatch_parallel(tasks)
```

## Why parallel

- Each section is independent (with context summary, no info leaks between sections)
- Wall-clock time = max(section drafts) not sum
- Each writer's context window stays focused (one section)
- Easier to retry single failed sections

## Per-section context budget (CRITICAL)

Each writer receives:
- Their own section spec (~500 chars)
- 800-word context summary of OTHER sections (not full text — just titles + 1-line intent)
- Research brief slice relevant to their H2 (~1000-2000 chars)
- Quotes & stats relevant to their H2 (filtered, ~500-1000 chars)
- Style references (loaded by writer via Read)

Total context: ~5000 chars input + writer's own LLM context window.

DO NOT send the full draft to each writer. That defeats the parallel + isolation pattern.

## Validation after collection

For each section returned, verify:
1. JSON conforms to `schemas/section.schema.json`
2. `word_count` within `[budget × 0.9, budget × 1.1]`
3. `self_check.em_dash_count == 0`
4. `self_check.banned_words_found == false`
5. `self_check.ai_tells_found == false`
6. `citation_capsule.word_count` between 35-70 (40-60 ideal)
7. `claims[]` exists if section_intent implies factual content
8. **Design components realized** (v3.31): for each component named in `section.design_components`,
   confirm the corresponding native-markdown structure is present in the section body, e.g.
   `comparison_table` → a `|...|...|` pipe table; `stat_grid` → a `## By the Numbers` (or
   `## Key Stats`) heading + a bold-led `- **N** ...` list; `callout` → a `> **Label:** ...`
   blockquote; `glossary` → a `## Glossary` `**Term** — def` list. A writer that silently
   skipped a planned component is a failure — re-dispatch that section with the missing
   component named explicitly (reuses the retry machinery below). Never accept raw HTML tags
   (`<div>`, `<table>`) in the body — that is a render-lint L1 veto, re-dispatch.

If any section fails: re-dispatch ONE writer for that section (max 2 retries per section).

## Retry strategy

For a failed section:
```python
retry_section(failed_section, attempt=1):
    # Add: "Previous attempt failed validation: {specific issues}. 
    #       Focus on: ${issues_list}. Word budget unchanged."
    spawn writer again with the same inputs PLUS the failure note
    
    if still fails:
        retry_section(failed_section, attempt=2):
            # Lower the bar slightly:
            # - allow word_count to ±20% instead of ±10%
            # - allow 1 banned word (replace inline before commit)
        
        if still fails:
            mark section as "needs_human_review"
            escalate to repair-orchestrator
```

## Output collection

After all N sections returned + validated:
```
workspace/{task_id}/sections/
  0.json
  1.json
  2.json
  ...
  N-1.json
```

Each conforms to `schemas/section.schema.json`.

## Handoff

`recommended_next_skill`: `fact-check-and-citation` (verify all claims; build References)

After fact-check returns, `assembly` script combines sections → draft.md.

## Cost estimate

For typical 6000-word article with 8 H2 sections:
- 8 parallel writer calls
- Each ~3000 input tokens + ~600 output tokens
- Per writer cost: ~$0.030 (Claude Opus 4.7)
- Total: ~$0.24 (well within per-article budget of $3)

## Common failure modes

| Failure | Action |
|---|---|
| 1 section fails validation 3× | Mark as needs_review; continue with placeholder; orchestrator decides |
| All N sections fail | Escalate to repair-orchestrator stage-rewrite |
| Writer hits maxTurns | Retry with more focused inputs; or split into smaller sections |
| Cost-guard blocks parallel batch | Run serially with cost re-checks per section |
| Single section duplicates content from another | Re-dispatch with stronger context_summary emphasizing "don't repeat: X" |

## See also

- `agents/writer.md` (the agent being dispatched)
- `schemas/section.schema.json` (output contract per section)
- `subskills/build/fact-check-and-citation/SKILL.md` (next stage)
- `scripts/build/assemble.py` (M-NOW.5 TODO; combines sections → draft.md)
