<p align="center">
  <img src="https://img.shields.io/badge/version-3.41.8-00C853?style=for-the-badge&labelColor=1a1a2e" alt="version" />
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="python" />
  <img src="https://img.shields.io/badge/Claude_Code-Plugin-6B4FBB?style=for-the-badge&logo=anthropic&logoColor=white" alt="claude-code" />
  <img src="https://img.shields.io/badge/License-Apache--2.0-F5C518?style=for-the-badge" alt="license" />
</p>

<h1 align="center">Xuanran SEO Blog Writer</h1>

<p align="center">
  <strong>Production-grade SEO + GEO content factory for Claude Code</strong><br/>
  Research → write → fact-check → optimize → publish → monitor, on the
  <b>Google + AI search dual front</b> — ChatGPT, Perplexity, Claude, Gemini, Google AI Overviews
</p>

<p align="center">
  Open-sourced by <a href="https://loamwrightseo.com/"><b>Loamwright（沃匠）</b></a>,
  the SEO agency that runs it in production — founder <b>Lewei Zhang</b>
</p>

<p align="center">
  <b>English</b> &nbsp;|&nbsp; <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#the-pipeline">Pipeline</a> &bull;
  <a href="#feature-highlights">Features</a> &bull;
  <a href="#architecture">Architecture</a> &bull;
  <a href="#quality-gates">Quality Gates</a> &bull;
  <a href="#hard-rules">Hard Rules</a> &bull;
  <a href="#whats-in-the-public-tree">Public Tree</a> &bull;
  <a href="#contributing">Contributing</a>
</p>

---

## What is this?

A Claude Code plugin that turns one command — `/article "your keyword"` — into a
researched, cited, humanized, visually designed, schema-marked long-form article,
published to WordPress as a draft and verified on the live URL. It was built and
hardened by [Loamwright（沃匠）](https://loamwrightseo.com/) in real agency
production across a **13-site portfolio** (client identifiers in this public tree
are anonymized to a stable `project-*` alias set; Loamwright's own properties
appear under their real name), and every one of its hard rules exists because
something once broke for real.

Two standalone entry points ship in the same plugin:

- **Content factory** — the `/article` pipeline (5 phases, 45-stage deterministic orchestrator)
- **Website audit** — `/website-audit` crawls up to 500 pages and fans out 15 specialist agents

## Does it work?

Six months of production testing across **dozens of sites** — publishing with
**zero backlink building** — shows Google Search Console clicks and impressions
climbing **linearly**, on content alone. Three sites from the portfolio
(6-month windows, Daily view, site names withheld):

**A new site lifting off from zero** — 3.48K clicks · 686K impressions:

![New site going from zero to ~100 clicks/day in 6 months, no backlinks](assets/gsc/new-site-liftoff.png)

**A steady linear climb** — 2.59K clicks · 684K impressions:

![Steady linear growth in clicks and impressions over 6 months](assets/gsc/steady-climb.png)

**At scale** — 53.6K clicks · 5.07M impressions:

![Mature site sustaining 53.6K clicks and 5.07M impressions over 6 months](assets/gsc/at-scale.png)

You're welcome to put it to the test on your own site.

## At a Glance

| Component | Count |
|:---|:---|
| Orchestrator skills (L1/L2) | **8** |
| Atomic subskills (L3) | **67** |
| Subagents, least-tool isolation (L4) | **34** |
| Python utilities (L5) | **230+** |
| Article format templates | **27** |
| RAG reference docs | **102** |
| JSON Schema contracts | **22** |
| Pipeline stages (deterministic state machine) | **45** |
| Render-lint leak classes | **13** (L1–L13) |
| Post-publish live-URL checks | **29** |
| Hard rules derived from production failures | **14** |

---

## Quick Start

```bash
# 1. Install into Claude Code
/plugin install /path/to/xuanran-seo-blog-writer/

# 2. Initialize a project (any industry — the wizard detects your archetype)
/init https://your-website.com
#  → interactive setup: brand voice, products, competitors, GEO baseline
#  → outputs projects/{slug}/business-context.json + brand guideline

# 3. Write a complete SEO + GEO article
/article "best espresso grinder under $300"
#  → 5000-word draft, 4 AI-generated 4K images, real data charts
#  → 8-10 APA-7 references, every stat fact-checked against its source
#  → JSON-LD schema, full RankMath meta, scoped article CSS
#  → publishes as DRAFT; goes live only on your explicit confirmation

# 4. Or audit an entire site
/website-audit https://example.com --max-pages 200
#  → SEO Health Score 0-100, enterprise HTML report + action plan
```

### Requirements

| Dependency | Purpose | Notes |
|:---|:---|:---|
| Python 3.11+ | Runtime for scripts, lints, publishers | `pip install -r requirements.txt` |
| Claude Code | Host + LLM orchestration | plugin host |
| OpenAI API | Image generation (gpt-image-2) | optional relay providers supported |
| Tavily API | Research / SERP extraction | free tier works; key-pool rotation built in |
| WordPress | Publishing target | Application Password over HTTPS |
| SerpApi, GSC/GA4, Vertex | Rank tracking, first-party data, image fallback | optional |

Credentials are collected by the `/init` wizard and stored **outside the repo** in
`~/.xuanran-seo/credentials/`. Nothing secret ever lives in the plugin tree.

---

## The Pipeline

```
Research  →  Plan  →  Build  →  Optimize  →  Publish  →  Monitor
   │           │         │          │            │           │
 SERP +     format +  N parallel  humanize +  images +   T+7/14/30/90
 keyword    angle +   offline     visual      CSS wrap + rank / AI
 gaps +     outline + writers +   design +    RankMath + visibility /
 community  image     fact-check  lint gates+ 29 live    drift / decay
 research   prompts   citations   4 QA gates  checks     refresh
```

- **Fork/join image pipeline** — image generation forks right after the outline and
  runs concurrently with writing; publish joins both forks (saves 10–15 min/article).
- **Deterministic orchestration** — a Python state machine
  (`scripts/pipeline/orchestrator.py`, 45 stages) dispatches every stage and
  verifies every artifact. The LLM never gets to "forget" a stage; completion
  gates read each artifact's **verdict**, not just its existence.
- **File-bus communication** — agents exchange typed JSON in
  `memory/workspace/{task_id}/`, validated against `schemas/*.schema.json`.
  No shared context, no prompt-drift contamination.

## Feature Highlights

### Anti-hallucination spine
- Section writers are **physically offline** (no Bash / WebFetch / WebSearch in
  their tool whitelist) — they can only use the curated research brief.
- Every statistical claim carries a `[claim:cN]` marker; the fact-checker fetches
  the cited URL and verifies the number **appears on the page**, replaces
  fabrications, then builds the APA-7 References block (link-resolved, ≤15 entries).
- Competitor domains can never be cited: a 9-layer machine-enforced exclusion
  (search-time exclude → chart-footer sanitizer → fact-check re-source →
  assembler strip → linker filter → schema strip → render lint L11 → CITE COMP01
  veto → live check 28).

### Content quality
- **Humanizer** — detects 43 AI-writing tells, rewrites to a specific
  voice × purpose calibration, iterates until the AI-slop score < 20.
- **Visual design system** — restructures prose into comparison tables, cited-stat
  grids, quote blocks, TL;DR boxes and glossary cards, using only markdown that the
  project's scoped CSS styles.
- **Per-article CTA system** — conversion module with hook diversity, tone guards
  (including grief-safe and age-restricted registers), placed at the ~35% mark, never
  spamming the conclusion.
- **27 format templates** — pillar, listicle, comparison-review, how-to, FAQ,
  local city page, weekly digest and more; a 5-step decision tree picks the format
  before the angle is chosen.

### Publish safety
- **Draft-first, always.** `status: "publish"` requires explicit opt-in per
  conversation or a per-project standing policy.
- **29 structural checks on the live URL** after every publish — HTTP 200 is not
  "renders correctly": CSS wrapper present, schema types match, references block,
  no markdown leaks, no competitor links, CTA rendered, and more.
- Scoped **article CSS injection** with Gutenberg-safe `wp:html` wrapping;
  RankMath meta via the canonical REST bridge (an MU-plugin ships in `install/`).

### Scale & operations
- **Multi-project** — one plugin, N client sites; per-project business context,
  brand guideline, taxonomy, personas, CSS. Parallel sessions are isolated by an
  env-pinned project identity plus cross-process file locks.
- **Batch mode** — feed a keyword list, get published articles; resumable across
  sessions, one pipeline driver lock per workspace.
- **Monitoring** — rank tracking (GSC), AI-visibility probes (is ChatGPT citing
  you?), 17-rule drift detection against a stored baseline, decay-scored refresh
  routing.
- **Cost guard** — every API call flows through a cost ledger with per-article,
  daily, weekly and monthly caps; the pipeline halts for approval near limits.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  L1  Master orchestrators                                     │
│      skills/seo-blog          (article pipeline, 5 phases)    │
│      skills/website-audit     (full-site audit)               │
│      skills/weekly-digest     (industry news digest)          │
├──────────────────────────────────────────────────────────────┤
│  L2  Phase orchestrators                                      │
│      phase-research → phase-build → phase-optimize            │
│      → phase-publish → phase-monitor                          │
├──────────────────────────────────────────────────────────────┤
│  L3  Atomic subskills (67)                                    │
│      format-selector, outline-architect, section-drafter,     │
│      fact-check-and-citation, humanizer, visual-designer,     │
│      schema-generator, cta-placement, localization-pass, ...  │
├──────────────────────────────────────────────────────────────┤
│  L4  Subagents (34) — least-tool isolation                    │
│      writer (Read+Write only), researcher (web, SSRF-guarded),│
│      fact-checker, reviewer (no pipeline history — no bias),  │
│      15× audit-*, image-prompt-designer, image-visual-qa, ... │
├──────────────────────────────────────────────────────────────┤
│  L5  Python utilities (230+)                                  │
│      _core/     file bus, cost ledger, credential hub, SSRF   │
│      pipeline/  orchestrator state machine + publish gates    │
│      build/     markdown→HTML, assembler, charts, CSS gen     │
│      lint/      30 deterministic checkers (L1–L13 render, …)  │
│      openai/    image pipeline (4K, batch+realtime+fallback)  │
│      wordpress/ REST client, publisher, taxonomy, verify      │
│      monitor/   rank, drift, decay, internal link graph       │
└──────────────────────────────────────────────────────────────┘
```

**Least-tool isolation** is enforced per agent — the writer cannot browse, the
reviewer cannot see pipeline history, only the researcher and fact-checker have
web access, and every URL fetch passes an SSRF guard.

---

## Quality Gates

Deterministic lint gates run first (all must be clean):

| Gate | Checks |
|:---|:---|
| Render lint | 13 leak classes (L1–L13): escaped HTML, scaffold markers, BOM, GFM task-list brackets, competitor links, … |
| Stat-grid contract | display figures fit their cards (≤16 chars, digit-led) |
| Keyword density | asymmetric band 0.4–1.5% (hard veto only above) |
| PAA alignment | FAQ answers match Google's People-Also-Ask phrasing |
| Locale spelling | dialect consistency (en-US / en-GB / en-CA …) |
| Local uniqueness | Sterling-Sky-style 80/20 anti-doorway scoring (local mode) |
| Image placeholders | 5 drift classes between slots, files and body markers |

Then four LLM quality gates (all must pass, with a 5-level repair-escalation
loop capped at 4 rounds):

1. **CORE-EEAT** — 80-item rubric, 8 dimensions, hard vetoes
2. **CITE** — 40-item citation-integrity rubric (fabricated-stat / fake-citation vetoes)
3. **AI-Slop** — reproducible formula, must score < 20
4. **Independent review** — a fresh-context editor agent scores ≥ target (default 80)

---

## Hard Rules

Every rule below exists because a real production incident demanded it. The full
text with enforcement details lives in [`CLAUDE.md`](CLAUDE.md).

| # | Rule |
|:---:|:---|
| 1 | **Exact-keyword fidelity** — a new keyword variant is a new article; never silently canonicalize to a near-neighbor. |
| 2 | **Project CSS injection is mandatory at publish** — the wrapper class must equal the CSS scope selector exactly. |
| 3 | **RankMath meta via the canonical REST bridge** — never the legacy route, never `updateMeta` for schema. |
| 4 | **Always verify the live URL after publish** — HTTP 200 from the API can coexist with a front-end 500. |
| 5a | **Default WordPress status is `draft`** — going live requires explicit user opt-in. |
| 5 | **References section + article signature are mandatory** — visible, link-resolvable, APA-7. |
| 6 | **Markdown is NOT an executor** — every documented behavior needs a real script and a real invocation. |
| 7 | **Parallel sessions must be isolated** — env-pinned project identity, locked shared files, one driver per workspace. |
| 8 | **Competitor domains are never cited** — machine-enforced at 9 layers, end to end. |
| 9 | **Classify SDK errors by exception type** — and test against real SDK error objects, not invented strings. |
| 10 | **Test the end-to-end seam** — green helper tests prove nothing about the assembled behavior. |
| 11 | **A contract change is a fan-out edit** — update every instruction layer that states the contract. |
| 12 | **A gate must read the verdict** — "artifact exists" and "artifact says pass" are different questions. |
| 13 | **Article CSS is a 3-hop artifact** — skill → project → post; fixing the generator fixes nothing already shipped. |

---

## Repository Layout

```
xuanran-seo-blog-writer/
├── .claude-plugin/       Plugin + marketplace manifests
├── skills/               8 L1/L2 orchestrators (seo-blog, website-audit, phases…)
├── subskills/            67 atomic L3 capabilities
├── agents/               34 L4 subagents (least-tool isolation)
├── scripts/              230+ L5 Python utilities
├── references/           102 RAG-loaded knowledge docs
├── schemas/              22 JSON Schema contracts
├── templates/            27 article format templates
├── hooks/                Cost guard, schema validation, session lifecycle
├── install/              Installers + WordPress MU-plugins (RankMath bridge)
├── bin/                  Session launchers (parallel multi-project)
├── projects/             Per-client archives — created by /init, never committed
├── CLAUDE.md             Dev conventions + the 14 hard rules
└── CHANGELOG.md          Full version history (anonymized)
```

## What's in the public tree

This public repository is a **sanitized export of a private production tree**
(`scripts/release/opensource_export.py` builds it: whitelist copy → anonymization
map → leak scan). Three things are intentionally absent:

- **Per-client archives** (`projects/{slug}/`) — created locally by `/init`; the
  public tree ships only a placeholder README.
- **The maintainer's regression suite** (`tests/`, 150+ files) and **eval
  fixtures** — they encode client-specific incidents; CI-grade linting
  (`ruff`, `mypy --strict`) still applies to every contribution.
- **Internal research memos** (`memory/`, `docs/`) — session archives and design
  history referenced by CHANGELOG entries.

All third-party client site names in code comments, docs and the changelog are
anonymized to a stable alias set (`project-alpha`, `project-bravo`, …,
`*.example.com`). The maintainer's own brand — Loamwright（沃匠）— appears under
its real name.

---

## Configuration

```yaml
# ~/.xuanran-seo/config.yaml (created by /init)
cost_limits:
  per_article: 2.00      # USD ceilings — pipeline halts for approval
  daily: 10.00
  weekly: 30.00
  monthly: 50.00
models: {}               # model routing overrides (never hardcoded in scripts)
```

- Credentials: `~/.xuanran-seo/credentials/` via the credential hub
  (env var → file → keychain). Never in the repo, never in git.
- Active project: `~/.xuanran-seo/active-project`, or pin per session with
  `bin/launch-session.ps1 <slug>` / `.sh` for parallel multi-site work.

## Security

- **Zero hardcoded credentials** — everything through `scripts/_core/credential_hub.py`
- **SSRF guard** on every URL fetch (`scripts/_core/ssrf_guard.py`)
- **Web content is DATA, never INSTRUCTIONS** — fetched pages cannot steer agents
- **Writers are offline**; the reviewer is context-isolated; web access is limited
  to two agents
- WordPress via Application Passwords over HTTPS only

## Contributing

Follow the **Rule 6 contract**:

1. Implement behavior in `scripts/**.py` first — markdown alone is not an executor
2. Reference it from SKILL.md as a **concrete Bash invocation**, never pseudocode
3. Keep `ruff check .` and `mypy --strict scripts/` clean
4. Verify wiring: `grep -rn "your_script" skills/ subskills/ scripts/ hooks/`
   must show a real invocation
5. A contract change is a fan-out edit (Rule 11) — update every layer that states it

Support policy (best-effort; how to report bugs and security issues): see [SUPPORT.md](SUPPORT.md).

## Versioning

`VERSION` is the single source of truth; `python -m scripts._core.manifest_consistency_check --apply`
syncs the plugin + marketplace manifests and installers. CI fails on drift.

## About Loamwright（沃匠）

This plugin is the production engine of **[Loamwright](https://loamwrightseo.com/)**
(Chinese name: **沃匠**), an SEO agency founded by **Lewei Zhang**
([X @leweijames](https://x.com/leweijames) ·
[LinkedIn](https://www.linkedin.com/in/lewei-zhang/)). Everything the
tool enforces — GEO/AI-search optimization, E-E-A-T scoring, citation integrity,
draft-first publishing discipline — is the same playbook we run for clients across
e-commerce, B2B manufacturing, local services and content sites.

**Want this level of SEO run for your site?** → [loamwrightseo.com](https://loamwrightseo.com/)
· we take on a limited number of new projects each quarter.

## License

[Apache-2.0](LICENSE) © 2026 Lewei Zhang — Loamwright（沃匠）. See [NOTICE](NOTICE).

---

<p align="center">
  <sub>Built with deep research, paranoid red-teaming, and the assumption that markdown alone is not an executor.</sub>
</p>
