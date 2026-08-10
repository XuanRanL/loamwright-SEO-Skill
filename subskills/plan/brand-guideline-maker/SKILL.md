---
name: brand-guideline-maker
description: 7-Block interactive interview + URL Analysis triangulation. Builds projects/{slug}/brand-guideline.yaml that gets injected into every /article draft. The single most impactful one-time investment per brand — wrong voice = wrong content forever. Triggered by /brand-guideline command, OR after /init Stage 5 when voice-discrepancy detected.
allowed-tools: [Read, Write, AskUserQuestion, Bash, WebFetch]
disable-model-invocation: false
user-invocable: true
---

# Brand Guideline Maker · 7-Block Interview Pattern

The single most important one-time interview per brand. **5 minutes of careful interview > 100 articles of wrong voice.**

## Operating principle

The user tells you what they THINK their voice is. The URLs they share tell you what their voice ACTUALLY is. Discrepancy is normal. Surface it gently. Let them decide which to lock in.

## Opening (set expectations)

Say to user:

> "Let's build your writing guideline. About 5 minutes. This dictates every draft I produce for you from now on.
>
> I'll ask about your brand, your audience, your writing style — then read some of your actual articles to capture your real voice (not just what you say it is). I'll also walk through 5 AI-visibility principles so you can decide how aggressively each applies.
>
> Ready?"

## Block 1 · The Brand (1-2 min)

Ask:

> "First, tell me about your brand. What does your company do, and who do you write for? A sentence or two is fine."

Then offer voice multi-select via `AskUserQuestion`:

| Voice option | Description |
|---|---|
| Expert and authoritative | Deep domain knowledge, definitive claims |
| Conversational and approachable | Friendly, peer-to-peer tone |
| Playful and witty | Humor, lighter edge |
| Direct and no-nonsense | Stripped-down, plain language |
| Empathetic and supportive | Acknowledges difficulty, encouraging |
| Bold and opinionated | Strong takes, willing to disagree |
| Neutral and informational | Just-the-facts, no editorializing |

Multi-select allowed. Custom additions invited.

## Block 2 · The Audience (1 min)

Ask:

> "Who reads your content? Describe your typical reader — their job, expertise, what they're trying to solve when they land on your blog."

Then scale question:

> "On 1-5, how technical is your audience?
> 1 = complete beginners, 5 = experts who hate being talked down to."

## Block 3 · Writing Preferences (1 min)

Ask 4 quick style questions:

1. Long-form deep dives or concise and scannable?
2. First-person OK ("I've seen this work") or keep impersonal?
3. Humor / sarcasm sometimes, or always straight?
4. Any words, phrases, expressions you never want to see?

## Block 4 · AI Visibility Calibration (2 min — KEY)

This is the load-bearing step. 5 principles × A/B/C preference each.

Frame:

> "Now let's talk how your content should perform in AI search. I'll walk through 5 principles + ask how strictly you want each applied."

### Principle 1 · The Ski Ramp (front-load the insight)

> "Most important insight in the first 20-30% of the article. AI systems are trained on journalism / academic writing — they expect the conclusion at the top, not the bottom.
>
> - Weak: A long intro teasing the insight across 5 paragraphs
> - Strong: 'After analyzing 1.2M ChatGPT citations, I found one pattern so consistent it has a P-Value of 0.0.'
>
> Choose:
> A) Always — lead with insight, no exceptions
> B) Usually — front-load most articles, allow narrative intros for storytelling pieces
> C) Rarely — your brand relies on building context before the payoff"

### Principle 2 · H2s as User Prompts

> "Framing H2 headings as literal questions makes them behave like search queries — AI treats the heading as the prompt and the first paragraph as the answer.
>
> - Weak: `## The History of SEO` → 'It began in the early 90s...'
> - Strong: `## When did SEO start?` → 'SEO started in...'
>
> Choose:
> A) Always — every H2 a question
> B) When natural — questions where they make sense, not forced
> C) Never — declarative headings only"

### Principle 3 · Definitive Language

> "AI systems prefer 'X is defined as Y' over vague openers. The word 'is' acts as a strong bridge.
>
> - Weak: 'In this fast-paced world, automation is becoming key...'
> - Strong: 'Marketing automation is the process of using software to...'
>
> Choose:
> A) Always — every section opens with a direct declarative
> B) Usually — definition-heavy sections; more narrative elsewhere
> C) Sometimes — only for technical or educational content"

### Principle 4 · Entity Richness (~20% target)

> "Heavily-cited content has ~20% entity density — naming brands, tools, people, platforms specifically, not generics.
>
> - Weak: 'There are many good tools for this task.' (0% entity density)
> - Strong: 'Top tools include Salesforce, HubSpot, and Pipedrive.' (30% entity density)
>
> Choose:
> A) Aggressive — name everything, including competitors
> B) Moderate — name tools / platforms freely; selective on competitors
> C) Conservative — owned-brand mentions only, avoid naming competitors"

### Principle 5 · Balanced Sentiment (~0.47 sweet spot)

> "Most-cited content sits at sentiment ~0.47 — neither dry facts nor pure opinion. The analyst voice: state the fact, then explain what it means.
>
> - 0.0 (Pure Objectivity — avoid): 'The iPhone 15 was released in September 2023.'
> - 1.0 (Pure Subjectivity — avoid): 'The iPhone 15 is an absolutely stunning masterpiece I love.'
> - 0.47 (Sweet Spot): 'While the iPhone 15 features a standard A16 chip, its low-light photography performance makes it a superior choice for content creators.'
>
> Choose:
> A) Analyst voice — fact + interpretation
> B) Lean objective — data and facts, minimal editorializing
> C) Lean opinionated — strong takes are part of our brand"

After all 5, summarize:

> "Got it. Your AI visibility profile:
> - Ski Ramp: [A/B/C]
> - H2s as prompts: [A/B/C]
> - Definitive language: [A/B/C]
> - Entity richness: [A/B/C]
> - Sentiment target: [A/B/C]
>
> I'll apply these as defaults across every draft. You can override per-brief."

## Block 5 · Competitor Awareness (30 sec)

Ask:

> "Are there blogs or writers in your space whose style you admire — even competitors? I WON'T copy them, but knowing your benchmark helps me understand what you're aiming for."

Reassurance is important. Otherwise users withhold useful info.

## Block 6 · URL Analysis (3 min — TRIANGULATION)

Say:

> "Now the most important part. Share 3 URLs from your own blog — ideally articles you're proud of or that represent the style you want replicated. I'll read them and extract your actual voice, not just your self-description."

Wait for 3 URLs.

For each URL:
- Run `scripts.fetch.tavily_extract` (advanced + format=markdown)
- Take first 1000 words
- Run lint suite:
  ```bash
  python -m scripts.lint.sentence_variance --input <text>
  python -m scripts.lint.ai_tells_detector --input <text>
  python -m scripts.lint.banned_word_lint --input <text>
  python -m scripts.lint.em_dash_audit --input <text>
  python -m scripts.lint.perplexity_estimator --input <text>
  ```

Analyze and capture:
- Average sentence length + variance
- Paragraph length distribution
- First person rate (1st person sentences / total)
- Tone register (formal vs casual)
- Humor / sarcasm markers
- Technical jargon density
- How intros are structured
- Recurring phrases / patterns

Note **how closely the content already applies the 5 AI visibility principles**.

After reading all three, say:

> "Got it. Here's what I picked up from your actual content:"

Then surface 5-8 bullet points with specifics. For example:

- "Your intros tend to open with a provocative question rather than a definition"
- "You use 'we' more than 'I' — voice feels like a team, not a solo expert"
- "Sentences average ~12 words — short and punchy"
- "You name-drop tools and competitors freely — high entity density already"
- "Dry wit running through most pieces — not jokes, but raised-eyebrow observations"
- "Your content applies the ski ramp naturally — insights land early"

### Flag discrepancies (THE KEY MOVE)

Compare Block 1-4 self-description vs what URLs actually show.

If gap: surface gently. Example:

> "One thing worth flagging: you said you prefer the analyst voice (~0.47 sentiment), but the articles I read lean closer to 0.30 — quite factual, not much interpretation. I'll aim for 0.47 unless you tell me otherwise.
>
> Want to:
> A) Keep your stated target (0.47) — articles will gain interpretation layer
> B) Match your actual style (0.30) — keep what's working
> C) Average — aim for 0.40 as compromise"

Then ask:

> "Does this feel accurate? Anything I missed or got wrong?"

Adjust based on response.

## Block 7 · Taboos and Non-Negotiables (30 sec)

Ask:

> "Last thing. Any hard rules?
>
> - Topics or angles you never touch?
> - Competitor names you avoid mentioning?
> - Formatting rules (e.g., always numbered lists, never tables)?
> - Anything that would make you cringe if you saw it in a draft?"

## Output: `projects/{slug}/brand-guideline.yaml`

```yaml
brand_name: "Acme Corp"
generated_at: "2026-05-19T14:32:00Z"
revision: 1   # increments on /brand-guideline re-run

# Block 1
business_summary: |
  Acme makes B2B SaaS analytics for finance teams.
voice_adjectives: [Expert, Direct, Bold]

# Block 2
audience:
  description: "CFOs and finance VPs at series B-D companies"
  expertise_level: 4
  intent: "Choosing analytics tools; benchmarking competitors"

# Block 3
writing_preferences:
  depth: "long-form"           # long-form | concise
  first_person_ok: true
  humor_allowed: true
  brand_banned_words:
    - "synergy"
    - "best-in-class"
    - "10x your"

# Block 4 — AI visibility profile
ai_visibility:
  ski_ramp: "A"               # A=always, B=usually, C=rarely
  h2_as_prompts: "B"
  definitive_language: "A"
  entity_richness: "B"
  sentiment_target: 0.47        # numeric or A/B/C

# Block 5
benchmark_blogs:
  - "https://stripe.com/blog"
  - "https://intercom.com/blog"

# Block 6 — URL analysis results
url_analysis:
  urls_analyzed:
    - "https://acme.com/blog/post-1"
    - "https://acme.com/blog/post-2"
    - "https://acme.com/blog/post-3"
  observations:
    - "Sentences average 14 words; high variance"
    - "First-person rate 18%"
    - "Em dashes used 0 times (good)"
    - "Entity density measured 22% (already aggressive)"
  discrepancies_with_self_description:
    - "Said 'Direct' but tone is closer to 'analytical'"
  applied_resolution: "Match actual"

# Block 7
taboos:
  banned_topics: ["politics"]
  banned_competitor_names: []
  formatting_rules:
    - "Always use markdown tables, not bullet pseudo-tables"
    - "No emoji in any draft"
  cringe_triggers: ["delve", "tapestry", "in today's fast-paced world"]

# Derived for L1 orchestrator
voice: "professional"
purpose: "general"
banned_words_combined:
  # union of brand_banned_words + global references/style/banned-words.md
```

## Handoff

After writing brand-guideline.yaml:

1. Update `projects/{slug}/project.yaml`:
   - `brand_guideline_path: brand-guideline.yaml`
   - `brand_guideline_revision: 1`
2. Print summary:
   > "✓ brand-guideline.yaml written. Will inject into every /article from now on."
3. Recommended next:
   - If part of /init flow: continue Stage 6 (entity baseline)
   - If standalone: done; suggest `/article <keyword>` to test

## When to re-run

- Quarterly review
- After major brand pivot
- When `brand_auto_tuner.py` recommends voice adjustment based on outcome data
- After `voice-discrepancy.md` triggers in URL Analysis

## What this skill does NOT do

- ❌ Auto-detect voice without user confirmation (too consequential)
- ❌ Apply to retrospective articles (only new drafts going forward)
- ❌ Override per-brief specifications (briefs win when explicit)

## See also

- `references/style/voices/{voice}.md` — voice profile detail
- `references/style/purposes/{purpose}.md` — purpose modifiers
- `scripts/lint/*` — used in Block 6 analysis
- `subskills/cross-cutting/brand-auto-tuner/SKILL.md` — closed-loop adjustment
