# SERP-Feature Tactic Value — Evidence Base (researched 2026-07-04)

Backs the v3.35 wire-vs-retire decisions for the 5 formerly Rule-6-dead optimize
subskills. Every claim below carried a source + date at research time; flagged
DATA vs OPINION.

## §1 Featured snippets → RETIRED as a separate step (merged into citation-capsule-builder)

- DATA (Ahrefs, Jun 2025): FS prevalence fell 18% → 8% of tracked searches Jan-Jun
  2025; 0.9 correlation between FS decline and AIO growth; ~83% replacement rate in
  8 months; FS and AIO rarely co-occur.
- DATA (Semrush 10M-keyword AIO study, 2025): FS appears less often when an AIO is
  present; AIO coverage itself is volatile (6.49% → ~25% → 15.69% across 2025).
- OPINION (consistent): the 40-60w direct-answer block after a question H2 is the
  same extractive shape AIO selects — the tactic survives inside AIO optimization.
- **Pipeline consequence:** the wired `citation-capsule-builder` stage already
  writes 40-60w extractive capsules per H2; since v3.35 its dispatch PRIORITIZES
  sections outline marks `is_featured_snippet_target` (that flag finally has a
  consumer). `snippet_format` is deprecated orphan data.

## §2 People Also Ask → WIRED (`paa-alignment-check` stage)

- DATA (seoClarity, Feb 2025): PAA prevalence GREW +34.7% US mobile / +37.5% US
  desktop Feb 2024 → Jan 2025 (+112% UK mobile). Historical "PAA collapse" reports
  (2022/2023 RankRanger dips) reverted within days — single-week dips are test noise.
- DATA (Semrush 2025): PAA co-occurs with AIO on ~90% of AIO SERPs — one of the few
  features AIO does NOT displace. PAA direct clicks are low (~3% of SERP clicks);
  the value is that Q&A-formatted content aligned to real PAA phrasing feeds AIO /
  AI-search answers.
- **Pipeline consequence:** the ">=60% of FAQ from research.paa" contract
  (documented since v5.0, validated by nothing) is now measured on the DRAFT by
  `scripts/lint/paa_alignment_check.py` (mandatory stage + pre-publish gate).
  Honest-supply rule: required = min(ceil(0.6×faq_count), paa_count).

## §3 Voice search → RETIRED

- DATA: the "50% of searches by voice by 2020" statistic is a mis-attributed zombie
  citation (never a real ComScore projection; never materialized).
- OPINION (Search Engine Land guide, updated Nov 2025): every VSO tactic (question
  headings, conversational long-tail, FAQ blocks, snippet formatting,
  FAQPage/HowTo/LocalBusiness schema, speed) is standard SEO — no voice-only tactic
  exists. The real shift went to conversational AI (ChatGPT voice, Gemini Live),
  which consumes the same answer-first content the pipeline already produces.
- **Pipeline consequence:** voice-search-optimizer retired; `scripts/lint/
  voice_search_check.py` retained as a MANUAL diagnostic CLI only (not a stage).
  2026 content-mill "27% of queries are voice" stats recycle the debunked lineage —
  do not resurrect this stage on their strength.

## §4 AI Overview citation recovery → KEPT (monitor-side) + churn guard

- DATA (Ahrefs 2025, "AI Overviews Change Every 2 Days"): consecutive AIO renders
  share only ~54.5% of cited URLs (~45% churn per render); AIO text changes ~70% of
  renders. A single uncited probe is noise, not a loss.
- DATA (Ahrefs): 38% of AIO citations come from top-10 organic results — classic
  ranking recovery remains the biggest lever.
- DATA (Seer Interactive, Sep 2025): organic CTR −61% under AIO, but cited pages
  recover ~+120% clicks/impression vs uncited — recovery is worth real effort.
- DATA (vendor case, unaudited): freshness update recovered citation rate 41%→73%;
  stat-density/structured-answer edits move citations in 30-45 days.
- **Pipeline consequence:** `refresh_decision_router` now requires the domain to be
  uncited in 2 consecutive probes ≥48h apart (observations persisted in
  projects/{slug}/audits/aio-observations.json) before emitting NOT_IN_AI → the
  ai-overview-recovery playbook. Detection tooling market for deeper tracking:
  Semrush AI Toolkit, Ahrefs Brand Radar, ZipTie, Otterly, Profound.

## §5 Localization QA (single-locale English sites) → WIRED as a cheap lint

- DATA (Google/Mueller 2017, reaffirmed 2021): spelling/grammar are NOT a ranking
  signal but a "gray zone" — heavy errors impair comprehension and perceived quality.
  Nothing covers en-GB-vs-en-US spelling on a single-locale site specifically.
- OPINION (localization industry): unit/currency/spelling mismatches create reader
  hesitation; all published evidence concerns cross-market localization, not
  native-site QA.
- **Practical read:** the real pipeline risk is consistency drift — en-GB spellings
  ("colour", "organise", "whilst") leaking from model training data into en-US
  prose is an AI-tell. A regex/wordlist lint captures ~all the value at zero cost.
- **Pipeline consequence:** `spelling_dialect_check.py --workspace` (mandatory
  `locale-spelling-check` stage): exempts References/quotes/code/URLs/proper nouns,
  FAILs only at ≥3 opposite-dialect hits. localization-pass Mode 2 (/locale-audit
  portfolio parity) stays a user-invocable standalone tool.

## Cross-cutting

- SparkToro 2026: <1/3 of Google searches now produce a click — extractive/citation
  optimization (§1/§2/§4 shapes) is where the remaining leverage sits.
