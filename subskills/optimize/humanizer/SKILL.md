---
name: humanizer
description: Detect 43 AI writing patterns + rewrite to specific human voice. 5×5 voice × purpose matrix + AI-Slop formula scoring + 3 modes (detect / rewrite / edit) + iterative N≤3 convergence. North star — LLMs regress to statistical mean; humans are weird, specific, inconsistent. Use after section-drafter, before fact-check-and-citation.
allowed-tools: [Read, Write, Edit, Grep, Glob, Bash]
disable-model-invocation: false
user-invocable: true
---

# Humanizer · Make Text Sound Like a Human Wrote It

## Operating principle

**LLMs regress to the statistical mean. Humans are weird, specific, and inconsistent.**

The fundamental AI tell: text that emerges from nowhere, addressed to no one, with no stake in its claims. Human writing reveals a mind behind it. If the reader can't picture a specific person writing this, it's not done.

A ruthless editor who despises AI slop. Don't just remove bad patterns. Replace them with something that has a pulse.

## When to invoke

- After `section-drafter` produces `workspace/{task_id}/draft.md` (Stage: section-drafted)
- Before `fact-check-and-citation` (so fact-checker validates human-form claims)
- Auto-triggered by repair-orchestrator when AI-Slop score >50 OR ≥5 patterns detected
- User can manually invoke `/humanize` on existing prose

## Three modes

| Mode | What it does | When |
|---|---|---|
| `detect` | Scan + report 0-100 AI-Slop score + per-pattern list. No rewrite. | Pre-flight audit |
| `rewrite` | Full rewrite with voice + soul injection | Default mode in /article pipeline |
| `edit` | In-place file edit, minimal targeted changes | Refresh / surgical repair |

## Five voices × five purposes (25 combinations)

| Voice | Personality | Best for |
|---|---|---|
| `casual` | Contractions, first person, fragments | Blog posts, social media |
| `professional` | Selective contractions, dry wit | Business comms, reports |
| `technical` | Precise vocabulary, code-like clarity | API docs, READMEs |
| `warm` | "We" language, empathy, short paragraphs | Tutorials, onboarding |
| `blunt` | Shortest sentences, no hedging, active voice | Internal comms, reviews |

| Purpose layer | What it adds |
|---|---|
| `essay` | No contractions, formal headings, structured arguments |
| `email` | Greetings/sign-offs allowed, no markdown |
| `marketing` | Short paragraphs, concrete benefits, single CTA |
| `technical` | Code blocks preserved, precise jargon retained |
| `general` | No purpose-specific overrides (default) |

Voice + purpose combine layered. Voice handles personality; purpose handles register.

## The 43 patterns

Full descriptions in `references/style/ai-tells-43.md`. Summary table:

### Content patterns (P1-P8)
- **P1** Significance Inflation ("represents a pivotal moment")
- **P2** Notability Name-Dropping (listing pubs vs reporting what they said)
- **P3** Superficial -ing Phrases ("ensuring", "fostering")
- **P4** Promotional Language ("nestled", "vibrant", "boasts")
- **P5** Vague Attributions ("experts argue", "studies show")
- **P6** Formulaic Challenges Sections ("Despite X, faces Y")
- **P7** AI Vocabulary cluster ("delve", "additionally", "crucial", "landscape", "tapestry")
- **P8** Copula Avoidance ("serves as" instead of "is")

### Language & style (P9-P18)
- **P9** Negative Parallelisms ("not just X, it's Y")
- **P10** Rule of Three (forced triadic lists)
- **P11** Synonym Cycling (entity referred to 3 ways in a paragraph)
- **P12** False Ranges ("from X to Y" non-spectrum)
- **P13** Em Dash Ban — zero tolerance (U+2014)
- **P14** Boldface/Formatting Overuse
- **P15** Structured List Syndrome (every paragraph is a bullet list)
- **P16** Title Case in Headings
- **P17** Curly Quotes (ChatGPT fingerprint) + Oxford comma overuse
- **P18** Formal Register Overuse (bureaucratic when conversational fits)

### Communication (P19-P21)
- **P19** Chatbot Artifacts ("I hope this helps", "Certainly!")
- **P20** Knowledge-Cutoff Disclaimers ("As of my last training")
- **P21** Sycophantic Tone ("Great question!")

### Filler & Hedging (P22-P30)
- **P22** Filler Phrases
- **P23** Excessive Hedging (stacked: "could potentially possibly")
- **P24** Generic Positive Conclusions ("future looks bright")
- **P25** Hallucination Markers (overly specific fabricated dates)
- **P26** Perfect/Error Alternation (mixed human+AI editing)
- **P27** Question-Format Section Titles ("What makes X unique?")
- **P28** Markdown Bleeding (`**bold**` in non-md contexts)
- **P29** Comprehensive Overview Opening ("In this article, we will explore")
- **P30** Uniform Sentence Length (15-25 words throughout)

### Emerging 2026 (P31-P43)
- **P31** Elegant Variation / Noun-Phrase Cycling
- **P32** Collaborative Communication Leaking ("we will explore")
- **P33** Placeholder Text ([Your Name], 2025-XX-XX)
- **P34** Chatbot Reference Markup Leaking (citeturn0search0)
- **P35** UTM Source Parameters from AI Tools (?utm_source=chatgpt.com)
- **P36** Sudden Style/Register Shift (mixed authorship)
- **P37** Overattribution / Source-Listing as Content
- **P38** Paragraph-Reshuffling Immunity (swap-and-still-works)
- **P39** "Whether" Summary Sentence Endings
- **P40** Symbolic Gloss / Meaning-Telling
- **P41** Infomercial Engagement Hooks ("The catch?", "The brutal truth?")
- **P42** Erratic Inline Bolding
- **P43** Treadmill Effect (low information density / restatement loops)

## The Burstiness Principle

AI detectors measure "burstiness" — sentence length variance. Human writing has HIGH burstiness; AI has LOW.

Target patterns:
- Mix short (3-8 words), medium (12-20 words), long (25-40 words) in every paragraph
- Never have 3+ consecutive sentences of similar length
- Let a sentence run long when the thought needs room to breathe, winding through qualifications before landing
- A fragment, used sparingly, can land a point.

⛔ **Do NOT raise burstiness by mass-inserting terse fragment-closers.** Burstiness is a
coefficient of variation (σ/μ) with no floor on short sentences, so stacking 2-5 word
fragments ("Pure leakage." "Stage first." "Two in three, gone.") mechanically lifts the
score AND drops `ai_slop_score` under the gate — but a human/LLM reviewer reads a run of
terse closers as **the single most visible AI tell** (it flagged exactly this on the
2026-06-29 batch). Cap: at most ~1 fragment per 150-200 words, and NEVER as a repeated
paragraph-ending device. Raise burstiness mainly by letting some sentences run LONG, not
by piling up fragments. If you can only clear `<20` by stacking fragments, the draft needs
real rewriting, not staccato.

## The Perplexity Principle

AI text has LOW perplexity (predictable word choices). Human text has HIGHER (more surprising).

Increase perplexity naturally:
- Choose the second or third word that comes to mind, not the first
- Use domain-specific jargon or slang appropriate to the audience
- Make unexpected analogies from personal experience
- Occasional informal transitions ("Anyway,", "So here's the thing:", "Look,", "Thing is,")

## Soul Injection (11 techniques)

Full descriptions in `references/style/soul-injection-11.md`. Brief:

1. **Have actual opinions** — "This API is frustrating" > "The API has limitations"
2. **Honest uncertainty** — "I'm not sure this is right, but..."
3. **Specific sensory detail** — "2am with cold coffee and a stack trace" > "complex"
4. **Shared experience callback** — "You know that feeling when..."
5. **Allow tangents** — brief digressions signal thinking, not algorithm
6. **Dramatic paragraph variation** — 4 sentences, then 1 line. Like this.
7. **Imperfect opening** — start mid-thought: "So I was looking at the logs..."
8. **Break parallel structure** — three items same grammar, fourth different
9. **Use callbacks** — reference earlier in piece
10. **Self-correct** — "well, technically..." signals real-time thinking
11. **End without wrapping up** — not every piece needs a neat conclusion

## AI-Slop scoring formula

```
score = 4 × patterns_hit + 25 × (1 - burstiness_normalized) + 15 × vocabulary_blacklist_ratio
clamped to 0-100
```

Score interpretation:

| Range | Verdict | Quality gate |
|---|---|---|
| 0-20 | Pristine | ✓ Ships |
| 21-40 | Mostly human | ✓ Ships with --score note |
| 41-60 | Mixed | ⚠ Repair-orchestrator level 1-2 |
| 61-80 | AI-leaning | ⛔ Repair level 3 (section regen) |
| 81-100 | Pure AI smell | ⛔ Repair level 4-5 (full regen or scratch) |

Implementation: `scripts/validate/ai_slop_score.py`.

## Workflow (in /article pipeline)

### Phase 1: Detect

```bash
python -m scripts.validate.ai_slop_score \
    --input workspace/{task_id}/draft.md \
    --json > workspace/{task_id}/ai-slop-pre.json
```

Read result. If `score < 20`: skip humanizer (already clean).

### Phase 2: Spawn humanizer agent

Invoke `agents/humanizer.md` (Edit-only tool whitelist — physically cannot Write). Pass:
- `--mode rewrite`
- `--voice {brand-guideline.voice}` (from project)
- `--purpose {brand-guideline.purpose}`
- `--score` (compute final score)
- `--iterate 3` (convergence)

Humanizer agent reads draft.md + this catalog + soul-injection-11.md, then Edits the draft.md in place.

### Phase 3: Re-detect

```bash
python -m scripts.validate.ai_slop_score \
    --input workspace/{task_id}/draft.md \
    --json > workspace/{task_id}/ai-slop-post.json
```

Compare pre vs post. If post-score still >50, escalate to repair-orchestrator.

### Phase 4: Frontmatter handoff

Update `workspace/{task_id}/state.json`:
- `stage: humanizer-complete`
- `ai_slop_pre: 67`
- `ai_slop_post: 18`
- `iterations: 2`

Next stage: `fact-check-and-citation`.

## Final quality checklist (humanizer agent enforces)

1. **Read aloud test** — does it sound like a person talking?
2. **Check the opening** — boring overview sentence? Hook instead
3. **Check the ending** — generic positive wrap-up? Cut or replace with specific
4. **Count "delves"** — kill any AI blacklist words
5. **Zero em dashes** — search for U+2014, replace with commas/colons/hyphens
6. **Sentence length audit** — 3+ similar in a row → vary
7. **"Who wrote this?" test** — can reader picture a specific person?

## What this skill does NOT do

- ❌ Modify quoted material, Citation Capsules, References section
- ❌ Make claims more specific by inventing facts (that's fact-checker's red line)
- ❌ Change headings (linker rule applies — headings sacred)
- ❌ Add new sections (only existing prose)
- ❌ Skip the post-rewrite re-score check

## Composition

```
section-drafter
  ↓ draft.md (Stage: section-drafted)
ai_slop_score (detect mode)
  ↓ ai-slop-pre.json
humanizer agent (rewrite mode)
  ↓ draft.md edited in place (Stage: humanizer-complete)
ai_slop_score (re-detect)
  ↓ ai-slop-post.json
  ↓
  → if post-score <50: fact-check-and-citation
  → if post-score ≥50: repair-orchestrator level 2
  → if post-score ≥70: repair-orchestrator level 3 (section regen)
```

## See also

- `references/style/ai-tells-43.md` — full pattern definitions with triggers + fixes + examples
- `references/style/soul-injection-11.md` — 11 humanization techniques
- `references/style/banned-words.md` — AI vocabulary blacklist
- `references/style/voices/{voice}.md` — per-voice detailed rules
- `references/style/purposes/{purpose}.md` — per-purpose modifiers
- `agents/humanizer.md` — the Edit-only subagent
- `scripts/validate/ai_slop_score.py` — formula implementation
