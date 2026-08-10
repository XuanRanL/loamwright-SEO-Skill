# Voice: Professional

> Default voice for B2B / SaaS / authoritative content. Pair with purposes from `references/style/purposes/`.

## Calibration

| Dimension | Setting | Range |
|---|---|---|
| Person | 3rd person primary, 1st person 10-15% | "The team found..." / occasional "We tested..." |
| Contractions | Allowed sparingly (15-25%) | "don't" yes, but not "ain't" or "wanna" |
| Sentence length avg | 16-22 words | with 0.35+ burstiness (target σ/μ > 0.30) |
| Sentence length variance | Required | Mix 6w fragments, 14w mid, 28w+ long |
| Jargon density | Moderate | Define inline on first use; assume reader knows industry basics |
| Humor | Subtle, dry | Wry observations OK; no slapstick, no exclamations |
| Hedging | Calibrated | "likely", "tends to" — never "might possibly" |
| Hyperbole | None | No "incredibly", "amazingly", "world-class" |
| Reading level | Grade 10-12 | Flesch 50-65 |

## Structural patterns

- **Open with**: A specific data point, a counter-intuitive claim, or a defined problem
- **Avoid open with**: "In today's...", "Have you ever...", "Let me tell you..."
- **Sentence starts**: Mix subject-verb (60%), prepositional phrase (20%), conjunctive adverb (10%), other (10%)
- **Paragraph length**: 60-150 words target; break ≥150
- **Closing**: Recommendation or open question, never "In conclusion"

## Vocabulary signature

**Preferred verbs**: shows, demonstrates, measures, indicates, suggests, found, observed, tested, ran, ranked, performed

**Preferred nouns**: data, study, result, finding, sample, baseline, benchmark, ratio, threshold, criterion

**Avoid** (per references/style/banned-words.md): delve, leverage, multifaceted, robust, seamless, navigate, paradigm, foster, harness, comprehensive

## Tone modulation

| Topic | Tonal adjustment |
|---|---|
| Technical deep-dive | More 3rd person, less 1st; tighter jargon density |
| Comparison / vs | Balanced, never advocacy; "X excels at A, Y at B" |
| Case study | More 1st person ("We deployed...", "We measured..."); more specific numbers |
| Opinion / thought leadership | More 1st person (25-35%); clear thesis statement |
| Tutorial / how-to | 2nd person ("you") for steps; 1st for asides |

## Self-check before submission

- [ ] First-person rate within 10-15% (count `\b(I|we|our|us|my|me)\b`)
- [ ] No banned vocabulary (run `scripts/lint/banned_word_lint.py`)
- [ ] Burstiness σ/μ > 0.30 (run `scripts/lint/sentence_variance.py`)
- [ ] AI-Slop score < 20 (run `scripts/lint/ai_tells_detector.py`)
- [ ] No hedging stacks (no "might possibly", "could potentially")
- [ ] No exclamation points except in direct quotes
- [ ] No imperatives mixed in 3rd-person narrative

## Example calibration

**Bad (too AI / promotional)**:
> Mobile-first design is crucial in today's digital landscape. By leveraging robust frameworks, companies can unlock seamless customer experiences. Furthermore, this approach delivers comprehensive results across multiple touchpoints.

**Good (professional voice)**:
> Mobile-first design now drives 67% of e-commerce revenue (Shopify 2026). The shift means companies that prioritized desktop redesigns in 2024 are rebuilding from scratch. Three Fortune 500 retailers (Target, Walmart, Best Buy) shipped mobile-first rewrites in Q4 2025, with conversion lifts of 18-31%.

## See also

- `references/style/voices/casual.md` (less formal alternative)
- `references/style/voices/warm.md` (relationship-focused alternative)
- `references/style/purposes/general.md` (purpose overlay)
- `references/style/soul-injection-11.md` (universal humanizing techniques)
