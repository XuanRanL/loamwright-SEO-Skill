# Power Words for SEO Titles & CTAs

> Used by `topic-angle-selector` and `meta-builder`. As of the **2026-06 revision**, power words are **OPTIONAL and register-gated** — `scripts/validate/title_validator.py` no longer requires one in any title.
>
> **Source**: 2026 SERP analysis + neuromarketing studies (Wix 2026.3, CXL Institute, ClickFlow), revised against 2025–26 randomized-trial evidence (see "What the 2025–26 evidence actually says").

---

Treat the five tables below as a vocabulary to reach for *sparingly*, not a checklist to satisfy.

## 1. Authority words (build E-E-A-T trust)

Use when content references original research, case studies, or expert sources.

| Word | When to use | Example |
|---|---|---|
| **Proven** | Method has tested results | "7 Proven Tactics for X" |
| **Expert** | Author is a recognized authority | "Expert Guide to Y" |
| **Data-Backed** | Claims include hard numbers | "Data-Backed Strategy" |
| **Research-Based** | Cites peer-reviewed sources | "Research-Based Approach" |
| **Certified** | Has formal credentials/certifications | "Certified Method" |
| **Tested** | Hands-on validation done | "Tested in 87 Trips" |
| **Verified** | Third-party confirmation | "Verified by Y" |
| **Documented** | Has paper trail | "Documented Cases" |
| **Audited** | Formal review completed | "Audited Process" |

---

## 2. Action words (drive immediate behavior)

Use when reader should DO something after reading.

| Word | When to use | Example |
|---|---|---|
| **Step-by-Step** | Sequential instructions | "Step-by-Step Setup Guide" |
| **Actionable** | Reader can use today | "9 Actionable Tips" |
| **Practical** | Real-world applicable | "Practical Framework" |
| **Hands-On** | Try-it-now content | "Hands-On Tutorial" |
| **Quick** | Time-constrained | "Quick Reference Guide" |
| **Instant** | Immediate result | "Instant Fix" |
| **Easy** | Low barrier | "Easy 5-Minute Setup" |
| **Simple** | Reduced complexity | "Simple Approach" |
| **Effective** | Validated to work | "Effective Method" |

---

## 3. Result words (promise specific outcome)

Use when content delivers measurable benefit.

| Word | When to use | Example |
|---|---|---|
| **High-Impact** | Significant change | "High-Impact Tactics" |
| **Results-Focused** | Outcome-oriented | "Results-Focused Plan" |
| **Time-Saving** | Reduces work hours | "Time-Saving Workflows" |
| **Cost-Cutting** | Reduces expense | "Cost-Cutting Tips" |
| **Revenue-Boosting** | Increases income | "Revenue-Boosting Channels" |
| **Conversion-Lifting** | Improves CR | "Conversion-Lifting CTAs" |
| **Profitable** | Drives margin | "Profitable Niches" |
| **Productive** | Output-focused | "Productive Habits" |
| **Game-Changing** | (Use only with data) | "Game-Changing Tool That Cut Our Costs 40%" |

---

## 4. Emotion words (create resonance)

Use sparingly — only when content delivers emotional payoff.

| Word | When to use | Example |
|---|---|---|
| **Effortless** | Frictionless experience | "Effortless Setup" |
| **Guaranteed** | (Use only with real guarantee) | "Guaranteed Method (or money back)" |
| **Bulletproof** | Resilient to failure | "Bulletproof Strategy" |
| **Surprising** | Counter-intuitive insights | "Surprising Findings" |
| **Eye-Opening** | Reveals hidden truth | "Eye-Opening Analysis" |
| **Mind-Blowing** | Rare; only for truly novel | "Mind-Blowing Result" |
| **Brilliant** | Smart approach | "Brilliant Solution" |
| **Powerful** | Significant capability | "Powerful Tool" |
| **Smart** | Strategic | "Smart Tactics" |

---

## 5. Specificity words (quantify scope)

Use to make ambitious claims credible.

| Word | When to use | Example |
|---|---|---|
| **Complete** | Covers all aspects | "Complete 2026 Guide" |
| **Comprehensive** | (Only if truly exhaustive) | "Comprehensive Reference" |
| **Ultimate** | (Only if backed by depth) | "Ultimate Resource" |
| **Definitive** | Authoritative reference | "Definitive Guide" |
| **All-Inclusive** | Nothing left out | "All-Inclusive Resource" |
| **Total** | Full coverage | "Total Approach" |
| **Full** | Comprehensive | "Full Walkthrough" |
| **Master** | Expert-level depth | "Master Guide" |
| **Advanced** | Beyond beginner | "Advanced Techniques" |

---

## What the 2025–26 evidence actually says

- **Positive power words can slightly DECREASE click-through.** In randomized trials, each additional *negative* word raised CTR by **+2.3%** and each additional *positive* word *lowered* it by **−1.0%** — but that was on clickbait **news** headlines (Nature Human Behaviour, May 2023). Do **not** port this effect to B2B or grief content. Net: a power word is **not** a reliable CTR lever.
- **The old CTR-uplift claims did not survive verification.** "+36% CTR from a digit" (HubSpot) and "+13.8% from a power word" (BuzzSumo) were never replicated under controlled conditions — treat both as folklore and **do not gate** on them.
- **Question titles give NO significant SERP-CTR advantage** over declarative ones (**15.5%** for questions vs **16.3%** for declarative, Backlinko Apr-2025).
- **Google rewrites ~76% of titles** (Q1-2025). Length sweet spot is **51–60 characters**. Matching the on-page H1 to the `<title>` cuts the rewrite rate from **61.6% → 20.6%**, and a number in the title is preserved **97.3%** of the time when it appears in **both** the H1 and the `<title>`.

---

## Rules for using Power Words in titles

### Register gating (enforced by `title_validator.py`):
- **`default` / `ecommerce` / `dtc_celebration`** — power words are **OPTIONAL**. Use one only when it earns its place; never to satisfy a quota.
- **`b2b_technical` / `b2b_procurement`** — **DISCOURAGED (warn)**. Let concrete specificity (numbers, model names, measured outcomes) be the authority signal instead of an adjective.
- **`dtc_grief`** — **HARD-BANNED**. Power words are tonally wrong for memorial / pet-loss content and will fail validation.

### Anti-spam ceiling (KEPT, all registers):
- **Maximum 2 power words** per title. Two or more reads as an AI-tell and **fails** validation.

### Title mechanics (all registers):
- **Title length target 51–60 characters** (matches the 2025 SERP sweet spot).
- **Primary keyword present** (once is ideal; appearing 2+ times warns, it does not fail).
- **Sentence case** is the house preference (Title Case is a warning, not a hard fail).
- **No bracketed or parenthesized year** in the `seo_title` — put the year in the H1 instead.

---

## Title formula library

The canonical title formulas now live in **`references/seo/micro-copy-tactics.md`** (the F1–F6 specificity-first set). This file is kept focused on the power-word vocabulary only — consult micro-copy-tactics for the formula patterns.

---

## See also

- `references/seo/micro-copy-tactics.md` (title micro-formulas)
- `references/seo/angle-catalog.md` (12 angle types)
- `references/seo/blog-formats-2026.md` (format selection)
- `scripts/validate/title_validator.py` (enforcement)
