# Voice: Technical

Precise vocabulary, code-like clarity, deadpan deliveries. Each sentence makes one point. No metaphors unless they genuinely clarify (most don't).

## Best for

- API documentation
- Engineering READMEs
- Technical specifications
- Architecture decision records
- Engineering blog posts (postmortems, deep-dives)

## Hard rules

1. **Use the exact term** — don't simplify for the sake of accessibility. If the term is `consistent hashing`, use `consistent hashing`, not "a way of distributing things."
2. **One claim per sentence** — long sentences become harder to verify. Break them.
3. **Concrete numbers over vague quantifiers** — "8ms p99" not "fast", "32 GB RAM" not "lots of memory"
4. **No metaphors unless genuinely clarifying** — and most aren't
5. **Allowed: dry, deadpan observations about technical absurdity** — "Of course this only happens in production"
6. **Active voice exclusively for engineering claims** — "The cache invalidates on write" not "Cache is invalidated on write"

## Voice characteristics

| Trait | Setting |
|---|---|
| Contractions | Selective (it's, don't OK; wouldn't've never) |
| First person | Sparingly — only when reporting your own experience |
| First-person plural ("we") | Common when describing team decisions |
| Humor | Dry, ironic, deadpan only |
| Hedging | Quantitative ("p99 latency", "in 80% of cases") not qualitative ("usually") |
| Sentence length | Short for facts; longer for explanations. Mix freely. |
| Burstiness target | High (SD > 7) — short staccato facts alongside longer reasoning |

## Vocabulary preferences

| Prefer | Avoid |
|---|---|
| invalidates | impacts (vague) |
| measured | proves |
| benchmarked | tested (be specific) |
| O(n log n) | scales well (vague) |
| at p99 | usually (uncalibrated) |
| 32 ms | quickly (vague) |
| in 80% of requests | mostly (uncalibrated) |
| serialize | seamlessly handle |
| race condition | issue |
| backpressure | slowness |

## Banned constructions (in addition to global banned-words.md)

- "elegantly solves" — say what it does
- "elegant solution" — show the code
- "sophisticated approach" — describe the approach
- "powerful framework" — say what it does
- "robust system" — say what failure modes it handles
- "seamless integration" — say what setup is required
- "best-in-class" — meaningless benchmark claim
- "state-of-the-art" — name the prior art

## Structural defaults

- Heading style: noun phrases or short imperative (not questions)
- Examples: code blocks before prose explanation
- Diagrams: ASCII or simple SVG; describe complex shapes in prose
- Lists: when items have parallel structure
- Tables: for comparing 3+ alternatives on 2+ dimensions

## Sample passages

### Bad (over-narrative technical writing)
> Have you ever wondered what happens when you call an API at scale? Well, in today's interconnected world, where APIs serve as the backbone of modern software, understanding these complex interactions becomes crucial. Our cutting-edge solution leverages a robust architecture to seamlessly handle even the most demanding workloads.

### Good
> A typical API endpoint serves three roles: authenticate the caller, validate the request, return data. Each adds latency. Authentication usually costs 3-8 ms (token verification, optional DB lookup). Validation runs in 1-2 ms for schemas under 50 fields. Data fetching dominates at 20-200 ms depending on cache hit rate.
>
> At p99, our checkout endpoint sees 47 ms for cached responses and 312 ms for cache misses. The 6.6× gap is where most user-perceived latency lives.

## Combining with purposes

- `technical + general` (default for code docs): Just the rules above
- `technical + technical` (whitepaper): Add precise math notation, formal definitions
- `technical + email`: Add greeting/sign-off, no markdown
- `technical + marketing`: NEVER — promotional language poisons technical content
- `technical + essay`: Add structured argument sections + formal references

## What to inject (Soul Injection technique mapping)

For technical voice, prefer these from `references/style/soul-injection-11.md`:

- ✓ #2 Honest uncertainty ("I'm not sure why this happens, but our metric shows...")
- ✓ #3 Specific sensory detail ("running at 2am with 8GB allocated to the JVM")
- ✓ #5 Allow tangents (briefly, for related technical context)
- ✓ #6 Dramatic paragraph variation
- ✓ #10 Self-correct ("Actually, that's wrong — the lock is held until commit")
- ✗ #1 Strong opinions (use selectively — engineering opinions OK; business opinions not for technical voice)
- ✗ #4 Shared experience callback (less useful for technical content)
- ✗ #7 Imperfect opening (technical readers want clear structure)

## See also

- `references/style/voices/blunt.md` — when even tighter is needed
- `references/style/purposes/technical.md` — purpose layer for technical writing
- `references/style/banned-words.md` — global banned list
- `references/style/ai-tells-43.md` — what to scrub
