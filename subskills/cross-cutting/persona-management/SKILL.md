---
name: persona-management
description: Create + store + enforce writing personas using NNGroup 4-dimension tone framework. Personas define readability targets, sentence length distribution, vocabulary tier, contraction frequency, summary box label. Used by section-drafter + humanizer + rewrite to enforce consistent voice. Different from brand-guideline-maker — personas live INSIDE a brand and represent author/audience variants.
allowed-tools: [Read, Write, AskUserQuestion, WebFetch, Bash]
disable-model-invocation: false
user-invocable: true
---

# Persona Management · Writing Voice Profiles

Create, store, enforce writing personas. Different from `brand-guideline-maker` (which is the brand-level voice) — personas live INSIDE a brand and represent author voices OR audience-tuned variants (e.g., one brand might have "Director persona" for C-suite content + "Practitioner persona" for IC-level content).

## Commands

| Command | Purpose |
|---|---|
| `/persona create` | Interactive interview to build a new persona |
| `/persona list [--project X]` | Show all saved personas (optionally per project) |
| `/persona use <name>` | Set active persona for current session |
| `/persona show <name>` | Display full persona profile |
| `/persona delete <name>` | Tombstone a persona |

## Create workflow · 6-step interview

Run the interactive interview. Ask each step, wait for response, then proceed.

### Step 1: Brand + audience basics

Ask:
- **Persona name** (kebab-case slug)
- **Brand or sub-brand** this persona writes for
- **Industry** — primary sector
- **Target audience** — role + experience level + goals (one persona = one audience segment)
- **One-sentence mission** — what this persona helps people do

### Step 2: Tone dimensions (NNGroup 4-dimension framework)

Present each dimension as a 0.0 to 1.0 slider. Explain both ends with examples.

| Dimension | 0.0 End | 1.0 End | Example at 0.0 | Example at 1.0 |
|---|---|---|---|---|
| `funny_serious` | Funny | Serious | "Let's be real, nobody reads Terms of Service" | "Understanding legal agreements protects your business" |
| `formal_casual` | Formal | Casual | "We are pleased to announce" | "Guess what — we shipped it!" |
| `respectful_irreverent` | Respectful | Irreverent | "We appreciate your patience" | "Yeah, that old way was broken" |
| `enthusiastic_matter_of_fact` | Enthusiastic | Matter-of-fact | "This changes everything!" | "Here are the results." |

Defaults if user unsure: `[0.6, 0.5, 0.3, 0.5]` (slightly serious, balanced formality, respectful, balanced enthusiasm).

### Step 3: Writing rules

Ask vocabulary tier first → auto-suggest matching readability band → user can override.

| Setting | Question | Default |
|---|---|---|
| Vocabulary tier | Consumer / Professional / Technical | Professional |
| Readability band | Auto-filled from tier (see table) | Grade 8-10 |
| Sentence length mean | Average words per sentence | 18 |
| Sentence length std | Variation (target burstiness) | 6 |
| Contraction frequency | 0.0 (never) to 1.0 (always) | 0.6 |
| Max passive voice | Percentage cap on passive | 10% |

### Step 4: Do's and Don'ts

Ask for 3-5 items in each list. Provide starter examples based on tone dimensions.

**Example Do's**:
- "Use data to back claims"
- "Address the reader as you"
- "Open with a question or stat"

**Example Don'ts**:
- "Don't use jargon without defining it"
- "Don't start sentences with There is/There are"
- "Don't use cliches like game-changer"

### Step 5: Summary label preference

Label used for summary/takeaway boxes:

- Key Takeaways (default)
- The Bottom Line
- What You'll Learn
- TL;DR
- Quick Summary
- In a Nutshell
- Custom label

### Step 6: Voice samples (optional but valuable)

Ask if user has 1-3 URLs of existing content exemplifying the desired voice.

For each URL:
1. Fetch via `scripts/fetch/tavily_extract.py` (advanced + markdown)
2. Run analysis:
   ```bash
   python -m scripts.lint.sentence_variance --input <text> --json
   python -m scripts.lint.perplexity_estimator --input <text> --json
   python -m scripts.lint.ai_tells_detector --input <text> --json
   ```
3. Extract: sentence length mean/std, contraction rate, tone dimension estimates, vocabulary level

Compare extracted values with persona settings → flag mismatches.

### Save

Write completed persona JSON to:
```
projects/{slug}/personas/{persona-name}.json
```

Use kebab-case filename (e.g., `cfo-thought-leader.json`).

## Persona profile schema

```json
{
  "name": "cfo-thought-leader",
  "description": "Analyst voice for finance VP audience",
  "brand": "Acme Corp",
  "industry": "B2B SaaS / FinTech",
  "audience": "CFOs + finance VPs at series B-D companies",
  "mission": "Help finance leaders choose analytics tools",
  "tone_dimensions": {
    "funny_serious": 0.85,
    "formal_casual": 0.30,
    "respectful_irreverent": 0.20,
    "enthusiastic_matter_of_fact": 0.40
  },
  "readability": {
    "flesch_grade_min": 9,
    "flesch_grade_max": 11,
    "flesch_ease_min": 45,
    "flesch_ease_max": 55
  },
  "style": {
    "sentence_length_mean": 16,
    "sentence_length_std": 8,
    "contraction_frequency": 0.40,
    "passive_voice_max_pct": 8,
    "vocabulary_tier": "professional",
    "summary_label": "Key Takeaways"
  },
  "voice_samples": [
    "https://acme.com/blog/cfo-toolkit",
    "https://acme.com/blog/forecasting-accuracy"
  ],
  "voice_sample_analysis": {
    "actual_sentence_mean": 15.8,
    "actual_contraction_rate": 0.37,
    "actual_burstiness_sd": 7.4,
    "tone_estimate": [0.83, 0.28, 0.22, 0.42],
    "matches_settings": true
  },
  "do": [
    "Use data to back every major claim",
    "Address the reader directly as you",
    "Lead sections with actionable insight"
  ],
  "dont": [
    "Don't use buzzwords without context",
    "Don't write sentences longer than 30 words",
    "Don't open with We at Acme"
  ],
  "created_at": "2026-05-19",
  "active_for_project": "acme-corp-site",
  "tombstoned": false
}
```

## Readability bands by vocabulary tier

| Tier | Flesch Grade | Flesch Ease | Typical use |
|---|---|---|---|
| Consumer | 6-8 | 60-80 | Health, lifestyle, personal finance |
| Professional | 8-10 | 50-60 | B2B, marketing, management |
| Technical | 10-12 | 30-50 | Engineering, medical, legal |

When user picks a tier, auto-fill readability fields. Let them override for non-standard combinations (e.g., technical vocabulary at consumer readability for explainer content).

## Integration with /article + /rewrite

When a persona is active (via `/persona use <name>`):

1. **Pre-generation** — Load persona JSON, inject tone dimensions + style rules into the system prompt for `section-drafter` (writer agent)
2. **During generation** — Writer follows do/dont rules, targets sentence length mean/std, uses contractions at specified frequency
3. **Post-generation validation** — Check output against persona constraints:
   - Sentence length distribution within 1σ of target mean
   - Readability score within specified grade band
   - Passive voice percentage under max
   - No violations of "dont" rules (via pattern matching)
4. **Validation fails** → flag specific violations + suggest edits via humanizer

## When to create multiple personas vs single brand-guideline

| Use a single brand-guideline | Use multiple personas |
|---|---|
| One audience segment, one voice | Multiple audience segments (C-suite + IC + customers) |
| Solo founder content | Multi-author blog |
| Niche site (one topic) | Hub site (many topic clusters with different voices) |
| Always same tone | Need formal voice for whitepapers + casual for blog |

Personas live INSIDE a brand-guideline.yaml. Brand-level rules (banned words, AI visibility settings) apply universally; persona rules override per article when one is active.

## List command

Glob `projects/{slug}/personas/*.json` (or all projects if no filter):

| Persona | Brand | Audience | Vocabulary | Active |
|---|---|---|---|---|
| cfo-thought-leader | Acme Corp | Finance VPs | Professional | ✓ |
| practitioner-guide | Acme Corp | Senior analysts | Technical | — |
| starter-friendly | Acme Corp | Junior analysts | Consumer | — |

If no personas: prompt to create one.

## Show command

Read persona JSON + display formatted summary with all tone dimensions, style rules, do/dont lists.

## Use command

Read persona JSON + confirm activation. Print summary of constraints that'll be enforced. Persona stays active for current conversation session. `section-drafter` and `rewrite` check for active persona before generating content.

## Error handling

- **Invalid tone values** (outside 0.0-1.0): clamp to nearest valid bound + warn
- **Unreachable voice samples**: skip + note in profile that sample unavailable
- **Empty personas directory**: prompt user to create one first
- **Name conflicts** during create: ask whether to overwrite or choose different name
- **Malformed JSON**: report error + offer to recreate from interview

## See also

- `subskills/plan/brand-guideline-maker/SKILL.md` — brand-level voice (parent of personas)
- `references/style/voices/*` — pre-built voice templates that can seed a persona
- `subskills/optimize/humanizer/SKILL.md` — enforces persona constraints during cleanup
- `agents/writer.md` — reads active persona for section-drafter dispatch
