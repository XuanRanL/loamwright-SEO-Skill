---
name: phase-build
description: Run Phase Build — section drafting (N parallel agents), fact-check, citation injection, assembly. Use when research.json and outline.json exist and need to write the actual article body. Triggered by /seo-blog build, "draft the article now", "write the body".
allowed-tools: [Read, Write, Edit, Task]
disable-model-invocation: false
---

# Phase Build Orchestrator

Convert outline.json → full markdown draft via parallel section writers + fact verification.

## Inputs

Required in `workspace/{task_id}/`:
- `state.json`
- `research.json`
- `angle.json` (from format-selector + topic-angle-selector)
- `outline.json` (from outline-architect)

## Stages

```
1. section-drafter (parallel N=outline.sections.length)
   - Spawn N independent subagents via Task tool
   - Each gets: ONE section spec + 800-word context summary of others
   - Each writes markdown + claims[] + citation_capsule
   - Tool whitelist: Read, Write ONLY (no WebFetch, no Bash)
   - Output: workspace/{task}/sections/{0..N-1}.json
   
2. citation-capsule-builder
   - Verify each H2 has 40-60 word AI-quotable block
   - Princeton GEO requirement (+28-41% AI citation rate)

3. chart-generator (if outline.sections[].needs_table)
   - Generate ≥2 markdown tables OR XSS-safe SVG charts
   - At least 1 in front 50% of article

4. fact-check-and-citation
   - For each [claim:cN_S] marker: Crossref → Tavily → HEAD check
   - Build References section (APA 7, ≤10 entries)
   - Replace markers with (Author, Year) in-text
   - Output: workspace/{task}/citations.json

5. assembly (scripts/build/assemble.py)
   - Concatenate: Abstract → Key Takeaways → ToC → Body → FAQ → Conclusion → References
   - Anchor links auto-generated for ToC
   - Mandatory-H2 coverage is enforced by scripts/lint/mandatory_sections_check.py,
     which reads THIS project's `business-context.json :: mandatory_sections` (assemble.py
     imports `_load_mandatory_sections` from it). Do NOT substitute
     markdown_structure_check.py here: it carries a HARDCODED section table and would
     override the project contract (see feedback_project_contract_not_hardcoded_labels).
     It remains available as a standalone structural report, not as this stage's gate.
   - Output: workspace/{task}/draft.md (frontmatter Stage: build-done)
```

## Parallel execution pattern

Section drafter spawns subagents in single Task batch:

```python
tasks = []
for section in outline.sections:
    tasks.append({
        "subagent_type": "writer",
        "section_spec": section,
        "context_summary": summarize_others(outline, section),
        "primary_keyword": state.brief.primary_keyword,
        "format_id": angle.format_id,
        "modifiers": angle.modifiers,
        "references_to_load": [
            "style/voices/" + brand_voice_choice,
            "style/banned-words.md",
            "style/ai-tells-43.md",
            "style/em-dash-prohibition.md",
            "seo/citation-capsules-princeton.md"
        ]
    })

results = parallel_dispatch(tasks)  # 1 round-trip, N writers
```

## Hard constraints (enforced post-section)

Each section must pass `self_check`:
- word_count within `[budget × 0.9, budget × 1.1]`
- em_dash_count == 0
- banned_words_found == false
- ai_tells_found == false
- has citation_capsule of 40-60 words
- contains claims with hint_query for fact-checker

Otherwise section is rejected and drafter retried (max 2 retries per section).

## Post-build lint (mandatory before handoff to Optimize)

```bash
# Section completeness — catches writer subagent silent dropout (6/50 sections
# dropped in 2026-05-22 batch). Run immediately after Stage 1 parallel dispatch
# returns, BEFORE Stage 4 fact-check.
python -m scripts.lint.section_completeness_check --workspace {task_id} --json
# exit 0 = all sections present; exit 1 = missing or extra
# Auto-writes to workspace/{task_id}/section-completeness.json (file-bus)
# Missing indices → re-dispatch writer subagent for each before proceeding.
```

## Output

- `workspace/{task}/sections/*.json` (N files, schemas/section.schema.json)
- `workspace/{task}/citations.json` (schemas/citations.schema.json)
- `workspace/{task}/draft.md` (markdown with frontmatter `Stage: build-done`)

## Handoff

`recommended_next_skill: "phase-optimize"`

## See also

- `subskills/build/section-drafter/SKILL.md`
- `subskills/build/fact-check-and-citation/SKILL.md`
- `subskills/build/citation-capsule-builder/SKILL.md`
- `agents/writer.md`
- `agents/fact-checker.md`
