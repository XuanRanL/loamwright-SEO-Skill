# Banned Words & Phrases (with substitution suggestions)

> Used by `scripts/lint/banned_word_lint.py`. Format: `- **word** → suggestion1, suggestion2, ...`
> 
> **Why ban each**: see categorization. **When OK to use**: rare, only when backed by specific data (e.g., "critical" is OK if measured impact is shown; otherwise use specific magnitude words).

---

## Original v1.5 prompt heritage bans (must NOT appear)

The legacy v1.5 default prompt explicitly banned these. Preserved + extended here:

### Sales-y verbs
- **unlock** → enable, provide access to, open
- **unleash** → release, deploy, activate
- **unveil** → introduce, present, reveal
- **unravel** → understand, work through, untangle
- **uncover** → find, identify, discover

### Overused intensifiers
- **critical** → essential (only if measurable), specific magnitude word
- **crucial** → essential (only if measurable), specific magnitude word
- **essential** → required (with reason), key (with data)

### Filler phrases
- **it's important to** → just state the fact
- **it's worth noting** → just state the fact
- **remember that** → just state it
- **it's important to note** → cut entirely

### AI-vocabulary cluster
- **Delve** → look at, explore, examine
- **take a dive into** → examine, study
- **embark on a journey** → start, begin (avoid travel metaphors)
- **pave the way** → enable, allow, set up

### Lazy wrap-ups
- **In conclusion** → just stop, OR "to summarize the data:"
- **in summary** → just stop, OR specific synthesis
- **ultimately** → cut, or specific timeframe ("by 2030")

### Formal filler
- **Furthermore** → also, plus, and
- **moreover** → also, additionally (use sparingly)
- **additionally** → also, plus

### Travel-brochure
- **Bustling** → busy, active, crowded
- **vibrant** → colorful, lively, dynamic (only when measurable)
- **hustle and bustle** → activity, traffic

### Era / world clichés (P29 from 43-pattern catalog)
- **In today's world** → cut, or specific year
- **In today's era** → cut, or specific year
- **In today's digital era** → cut entirely
- **In the world of** → cut, or "Within [specific domain]"
- **In today's fast-paced world** → cut entirely

---

## Empty intensifiers (state magnitude instead)

- **crucial** → important, central, necessary for X to work
- **critical** → central, load-bearing, necessary for X
- **essential** → needed, required, core to X
- **vital** → needed, core, load-bearing
- **imperative** → needed, important, necessary
- **pivotal** → central, decisive

---

## AI vocabulary tells

- **delve** → explore, examine, look at
- **delves** → explores, examines
- **leverage** → use, apply, draw on
- **leverages** → uses, applies
- **multifaceted** → many-sided, complex
- **tapestry** → pattern, mix, set
- **landscape** → scene, field, industry
- **intricate** → complex, detailed
- **robust** → strong, reliable
- **seamless** → smooth, uninterrupted
- **foster** → build, grow, encourage
- **harness** → use, apply
- **paradigm** → model, framework
- **dynamic** → active, changing
- **vibrant** → active, lively
- **nestled** → located, set
- **cutting-edge** → latest, advanced
- **testament** → proof, evidence, example
- **realm** → field, area
- **navigate** → work through, handle
- **navigating** → working through
- **comprehensive** → complete, thorough

---

## Promotional clichés

- **unleash** → release, let loose, use
- **unleashed** → released
- **unlock** → enable, open up
- **unlocks** → enables
- **unveil** → reveal, introduce, show
- **unveiled** → revealed
- **unravel** → explain, untangle
- **uncover** → find, discover
- **revolutionary** → new, different

---

## Transition tics (just delete or use 'also/and')

- **furthermore** → also, and, plus
- **moreover** → also, and
- **additionally** → also, plus, and
- **in addition** → also, plus

---

## Conclusion tics (just end the article)

- **in conclusion** → so, all told, (just stop)
- **in summary** → so, in short, (just stop)
- **ultimately** → in the end, finally, (omit)
- **to wrap up** → (omit)
- **remember that** → (omit), note:

---

## Hedging / padding (delete)

- **it's important to note** → (omit), note:
- **it's worth mentioning** → (omit)
- **it's important to** → (omit)
- **it should be noted** → (omit)
- **needless to say** → (omit)
- **as previously mentioned** → (omit)
- **as mentioned earlier** → (omit)
- **as we discussed** → (omit)

---

## Filler openers (use specific year or just delete)

- **in today's world** → in 2026, (specific year)
- **in the world of** → in, for
- **in today's era** → today, in 2026
- **in today's digital era** → today, online
- **in today's fast-paced world** → today

---

## Filler verbs

- **take a dive into** → explore
- **embark on a journey** → start, begin
- **pave the way** → enable, lead to

---

## Generic empty references

- **this** → (specify what 'this' refers to)
- **and** (at line start) → (rewrite sentence; don't start with conjunction)

---

## Categorized counts (for reporting)

| Category | Count |
|---|---|
| Empty intensifiers | 6 |
| AI vocabulary tells | 22 |
| Promotional clichés | 9 |
| Transition tics | 4 |
| Conclusion tics | 5 |
| Hedging / padding | 8 |
| Filler openers | 5 |
| Filler verbs | 3 |
| **Total** | **62** |

---

## When exceptions are allowed

A banned word is allowed if **all three** conditions hold:
1. It serves a specific factual claim (not vague intensifier)
2. The claim is backed by data (percent, year, number)
3. No suggested substitution preserves meaning

Example **ALLOWED**: "Studies show 67% of users find this feature *crucial* for daily workflow (UX Research Quarterly, 2025)." — "crucial" here describes measured user sentiment, not vague intensifier.

Example **NOT ALLOWED**: "Choosing the right rod is crucial." — vague intensifier; use "Choosing the right rod can change your daily catch rate by 40-50%" instead.
