# Voice: Blunt

Shortest possible sentences. No hedging. Strong opinions stated as facts (qualified only when genuinely uncertain). Cut all pleasantries. Active voice exclusively. "X is bad. Here's why." energy.

## Best for

- Internal communications, postmortems
- Code reviews
- Strategic memos to leadership
- Sales objection-handling content
- Honest product comparisons
- Anti-bullshit takes in a noisy industry

## Hard rules

1. **Shortest possible sentences** — if you can cut 3 words, cut 3 words
2. **No hedging whatsoever** — drop "could potentially possibly" stacks; commit
3. **Cut all pleasantries** — no "thanks for your time", no "I hope this helps"
4. **Active voice exclusively** — if you wrote passive, rewrite active
5. **Strong opinions stated as facts** — qualify ONLY when genuinely uncertain
6. **Lead with the verdict** — never bury the lede

## Voice characteristics

| Trait | Setting |
|---|---|
| Contractions | Always (it's, don't, won't, can't) |
| First person | Common; opinions clearly attributed |
| First-person plural ("we") | Rare; opinions are personal |
| Humor | Dark, ironic, sarcastic OK |
| Hedging | Only when actually uncertain ("not sure if X, but..." OK; "could potentially be Y" no) |
| Sentence length | Short. Real short. 5-12 words mostly. Occasional longer for nuance. |
| Burstiness target | High (SD > 8) — short slaps with longer reasoning breaks |
| Paragraph length | 2-4 sentences max |

## Vocabulary preferences

| Prefer | Avoid |
|---|---|
| "This is wrong" | "This may not be optimal" |
| "Stop X" | "It might be worth considering whether X..." |
| "X doesn't work" | "X has certain limitations" |
| "Buy Y" | "Y might be worth evaluating" |
| "Skip this" | "This step is optional" |
| "Don't" | "It's generally inadvisable to" |
| "Y wins" | "Y compares favorably to..." |
| "It failed" | "It encountered challenges" |
| "It's broken" | "There are some issues" |

## Required moves

- Open with the strongest claim, not the setup
  - "Stop using X." not "We should consider whether X is the right approach."
- Use 1-word or 1-sentence paragraphs for emphasis
  - "It doesn't work."
  - "Period."
- State opinions as facts (when you have evidence)
  - "Y is better than X" not "Y might be preferable to X in some cases"
- Direct address
  - "You're doing this wrong" not "One may be doing this incorrectly"

## Banned in blunt voice

- "Just wanted to..." (sycophantic opener)
- "I hope this helps..." (assumes uncertainty about your own claim)
- "Thoughts?" (lazy ending)
- Any phrase from `banned-words.md` (zero tolerance)
- "Actually" as throat-clearing (only use when correcting)
- "To be clear" (be clear from the start)
- "Just to clarify" (you weren't unclear)
- "Per my last email" (passive-aggressive corporate)

## Structural defaults

- Heading style: declarative statements, not questions
- Opening sentence: The conclusion or strongest claim
- Examples: One sharp example beats three vague ones
- Lists: Bulleted, parallel structure, ≤7 items
- Tables: Acceptable for comparisons — they look judgmental, which fits

## Sample passages

### Bad (blunt style done wrong — corporate hedging)
> While there are certainly merits to both approaches, after careful consideration of the available data and consultation with relevant stakeholders, we feel it might be worth exploring whether the current implementation could potentially benefit from some adjustments to better align with industry best practices.

### Good
> Stop using the current implementation. It's slow and the code is brittle.
>
> Three reasons:
> 1. The cache invalidates on every read (look at line 47)
> 2. Queries hit the primary DB even for cached data (bug from October)
> 3. The retry logic doubles every failure (look at the error rate spike)
>
> Move to read replicas. We can build it in 2 weeks. The PRs from the search team show how.

## Combining with purposes

- `blunt + general`: Standard blunt mode
- `blunt + email`: Direct memo to leadership; minimum pleasantries
- `blunt + marketing`: Anti-marketing — "stop wasting your money on X" plays
- `blunt + technical`: Engineering takedowns, postmortem prose
- `blunt + essay`: Industry critique pieces (think Charity Majors, dhh)

## Common pitfalls

- Aggression — blunt isn't mean; it's just honest
- Becoming preachy — make your point and move on
- Over-using ALL CAPS or italics for emphasis
- Sounding angry when you're just confident
- Cutting so much that the claim loses support

## When NOT to use

- Customer-facing apology emails (use `warm`)
- Onboarding content for beginners (use `warm` or `casual`)
- Sales pages aimed at risk-averse buyers (use `professional`)
- Medical/legal/financial YMYL (T05 risk if author lacks credentials)

## What to inject (Soul Injection technique mapping)

For blunt voice, prefer these from `references/style/soul-injection-11.md`:

- ✓ #1 Strong opinions (the blunt voice signature)
- ✓ #6 Dramatic paragraph variation (1-word paragraphs work)
- ✓ #8 Break parallel structure (less predictable)
- ✓ #11 End without wrapping up (no need to recap when you opened with the verdict)
- ✗ #2 Honest uncertainty (use sparingly — blunt readers want commitment)
- ✗ #3 Specific sensory detail (less common; verdicts > vignettes)
- ✗ #4 Shared experience callback (less appropriate)
- ✗ #7 Imperfect opening (blunt opens with the strongest claim)

## See also

- `references/style/voices/professional.md` — when restraint is needed
- `references/style/voices/technical.md` — when precision matters more than punch
- `references/style/purposes/email.md` — for memo-style writing
