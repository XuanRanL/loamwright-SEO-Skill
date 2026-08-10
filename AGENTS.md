# AGENTS.md — Universal Host Intent Router

This file routes user intent to skills, **host-agnostic**. Any AI host (Claude Code, OpenClaw, Codex, Hermes, custom) can read this single file and know which skill to invoke.

---

## Intent → Skill Routing

### Project initialization

**Triggers**: "init", "new website", "new client", "audit my site for setup", "/init", user gives a URL with no other task
→ Load skill: `subskills/init/website-project-init/SKILL.md`

**Triggers**: "/switch", "switch project", "change active site"
→ Load skill: `subskills/init/project-switch/SKILL.md`

**Triggers**: "/list-projects", "list my sites", "what projects do I have"
→ Load skill: `subskills/init/project-list/SKILL.md`

### Article creation (most common)

**Triggers**: "/article", "write a blog about", "create an article on", "blog post on X", "SEO article for", user gives keyword + intent to write
→ Load skill: `skills/seo-blog/SKILL.md` (master orchestrator, runs all 5 phases)

**Triggers**: "/rewrite", "rewrite this article", "update this post"
→ Load skill: `subskills/optimize/content-refresher/SKILL.md`

**Triggers**: "/refresh", "refresh this page", "decay-aware update"
→ Load skill: `subskills/monitor/content-refresher/SKILL.md`

### Single-phase entry

**Triggers**: "research", "keyword research", "what's the SERP for", "/seo-blog research"
→ Load skill: `skills/phase-research/SKILL.md`

**Triggers**: "outline", "plan article", "/seo-blog plan"
→ Load skill: `skills/phase-build/SKILL.md`

**Triggers**: "audit", "check page", "/audit"
→ Load skill: `skills/phase-optimize/SKILL.md`

**Triggers**: "publish", "send to WordPress", "/publish"
→ Load skill: `skills/phase-publish/SKILL.md`

### Specialty entries

**Triggers**: "featured snippet", "position zero", "抢 0 号位"
→ Load skill: `subskills/build/citation-capsule-builder/SKILL.md`
   (featured-snippet-optimizer RETIRED v3.35 — FS 83% replaced by AI Overviews;
   the capsule stage owns the 40-60w extractive answer shape both features select)

**Triggers**: "PAA", "People Also Ask", "Q&A optimization"
→ Load skill: `subskills/optimize/paa-answer-writer/SKILL.md`
   (wording rules for writers; the >=60% contract is machine-enforced by the
   mandatory `paa-alignment-check` stage — scripts/lint/paa_alignment_check.py)

**Triggers**: "AIO recovery", "AI Overview lost", "/aio-recovery"
→ Load skill: `subskills/optimize/ai-overview-recovery/SKILL.md`

**Triggers**: "AI visibility", "is ChatGPT citing me", "/ai-visibility"
→ Load skill: `subskills/monitor/ai-visibility-tracker/SKILL.md`

**Triggers**: "factcheck", "verify citations", "/factcheck"
→ Load skill: `subskills/build/fact-check-and-citation/SKILL.md`

**Triggers**: "humanize", "remove AI tells", "/humanize"
→ Load skill: `subskills/optimize/humanizer/SKILL.md`

**Triggers**: "translate", "localize", "/translate <locale>", "/locale-audit"
→ Load skill: `subskills/optimize/localization-pass/SKILL.md`
   (Mode 1 dialect gate is the mandatory `locale-spelling-check` stage since v3.35;
   Mode 2 /locale-audit portfolio parity remains this skill's interactive job)

**Triggers**: "cluster", "topic cluster", "pillar + spoke", "/cluster"
→ Load skill: `subskills/plan/topic-clustering/SKILL.md`

**Triggers**: "cannibalization", "self-competing keywords"
→ Load skill: `subskills/monitor/drift-detector/SKILL.md`

**Triggers**: "schema", "JSON-LD", "structured data"
→ Load skill: `subskills/optimize/schema-generator/SKILL.md`

### Brand & configuration

**Triggers**: "/brand-guideline", "set brand voice", "configure voice"
→ Load skill: `subskills/plan/brand-guideline-maker/SKILL.md`

**Triggers**: "/context show / edit", "view brand context"
→ Load skill: `subskills/cross-cutting/context-manager/SKILL.md`

**Triggers**: "/config", "settings"
→ Open `~/.xuanran-seo/config.yaml` for editing

### Monitor / Performance

**Triggers**: "/rank-check", "Google rank for", "where do I rank"
→ Load skill: `subskills/monitor/rank-tracker/SKILL.md`

**Triggers**: "/drift", "what changed", "drift detection"
→ Load skill: `subskills/monitor/drift-detector/SKILL.md`

**Triggers**: "/perf", "performance report", "KPI summary"
→ Load skill: `subskills/monitor/performance-reporter/SKILL.md`

**Triggers**: "/alerts", "monitoring alerts"
→ Load skill: `subskills/cross-cutting/alert-manager/SKILL.md`

### Meta commands

**Triggers**: "/skillify", "turn this into a skill"
→ Load skill: `subskills/cross-cutting/skillify/SKILL.md`

**Triggers**: "/evolve", "learn from past runs"
→ Load skill: `subskills/cross-cutting/self-upgrade/SKILL.md`

**Triggers**: "/guard --versions", "version consistency check"
→ Run script: `scripts/_core/manifest_consistency_check.py`

---

## Universal Startup

Every skill invocation should first run `bin/preamble.md` for:
- Version check (compare local vs marketplace)
- Active project loading (`~/.xuanran-seo/active-project` → `projects/{slug}/business-context.json`)
- Credential validation (warn if missing)
- Cost ledger state (warn if approaching daily cap)

---

## Routing Priority (when triggers overlap)

1. **Explicit slash command** (e.g., `/init`, `/article`) — direct route
2. **URL + write intent** ("write a blog about X for example.com") — `/article` with X as keyword
3. **URL alone** ("example.com") — `/init` if not yet in projects/; else show project status
4. **Keyword alone** — `/article`
5. **Ambiguous** — ask for clarification with 3 options

---

## Cross-Host Notes

- **Claude Code**: Reads `.claude-plugin/plugin.json` first, then this file as fallback
- **Gemini API host**: Compile-time via `install/gemini-api/compile_skill.py`, this file becomes the routing rules in a system prompt
- **Codex / Hermes**: Read this file directly at session start
- **Generic**: This file is the source of truth for ALL hosts

---

*Version 3.41.8 · 2026-08-01*
