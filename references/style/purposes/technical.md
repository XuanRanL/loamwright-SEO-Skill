# Purpose: Technical

Documentation, API references, architecture docs, engineering postmortems, technical tutorials, RFCs, deep-dives. Precision is the highest priority. Brevity second. Voice flourish last.

## Layer rules (on top of voice)

- **Code blocks preserved** with appropriate syntax highlighting hints
- **Precise jargon retained** — don't dumb down terms; explain inline when first introduced
- **Numbers over adjectives** — "8 ms p99" not "fast"
- **No metaphors unless genuinely clarifying** — most metaphors confuse more than they help
- **Examples before explanation** — show the code, then describe what it does
- **Concrete failure modes documented** — what breaks, when, and why

## Structural defaults

```
Title: Verb-noun OR noun phrase (no questions)
TL;DR: 40-60w summary of the most important fact (for AI Featured Snippets)

Section 1: What this is (definition + minimal example)
Section 2: How it works (mechanism + diagrams if needed)
Section 3: How to use it (step-by-step or API reference)
Section 4: Edge cases / failure modes
Section 5: Performance characteristics (if applicable)
Section 6: Related: alternatives + when not to use this

References: APA-style for academic; URL list for technical specs (RFCs, W3C, etc.)
```

## Required moves

1. **State what it IS in the first sentence**
   - Wikipedia-style definition
   - Not "Let's explore..." (P32 violation)

2. **Show a working example within first 30% of the doc**
   - Smallest possible code that demonstrates the concept
   - Comment any non-obvious lines

3. **Document failure modes explicitly**
   - What does it do when input is invalid?
   - What does it do under load?
   - What does it do when network fails?

4. **Cite specifications, not blog posts**
   - RFCs (HTTP/2 = RFC 7540)
   - W3C standards (CSS Grid = W3C Recommendation)
   - Academic papers (DOI preferred)
   - Source code (linked to specific commits / line numbers)

5. **Specify version + context**
   - "As of PostgreSQL 16, ..."
   - "In Python 3.12+, ..."
   - "Tested on Linux 6.5 kernel, AMD Ryzen 7950X, 64 GB RAM"

## Banned in technical purpose

- "Easy" or "simple" (subjective; readers will disagree)
- "Just" (minimizes complexity unfairly)
- Marketing language (P4)
- "Revolutionary" (P4 — even when it might be true)
- "Cutting-edge" (P4)
- Em dashes (P13 — global rule)
- "In today's digital landscape" (P29)
- "Let's dive in" (P29)
- "The journey begins" (P40)

## Allowed (and encouraged) for technical purpose

- Strong opinions on engineering trade-offs
  - "Don't use ORMs for this query path — the raw SQL is clearer and 4× faster"
- Honest assessments of tooling
  - "Library X has good docs but poor error messages; here's how to debug"
- Specific performance claims with measurements
  - "p99 latency 47 ms cached, 312 ms uncached (n=1.2M requests)"
- Linking to source code
  - "See [src/cache.rs:243](https://...) for the eviction policy"

## Code block conventions

```javascript
// Bad: no syntax highlighting hint
console.log("hello");
```

```js
// Good: syntax highlighting hint + concise comment
console.log("hello");
```

```rust
// Better: language + filename + brief comment
// src/server.rs
async fn handle_request(req: Request) -> Response {
    // ...
}
```

For runnable examples:
- Include all imports/setup
- Show expected output as a comment
- Mark omitted parts clearly with `// ...`

For pseudo-code:
- Use a non-language hint like `pseudo` or `plain`
- Don't pretend it's executable

## Diagrams

- ASCII for simple block diagrams (always)
- SVG for complex flows (only when ASCII fails)
- NO emoji as visual icons in serious technical docs
- Mermaid syntax acceptable for sequence/flowcharts (GitHub renders it)

## When to use technical purpose

- API documentation
- README files
- Architecture decision records (ADRs)
- RFCs (request-for-comments style)
- Postmortems
- Performance analyses
- Technical tutorials (when audience is engineers, not beginners)
- Engineering deep-dive blog posts

## Combining with voice

| Voice + technical | Typical use |
|---|---|
| `technical + technical` | The default for engineering content |
| `professional + technical` | More general technical content (not pure engineering) |
| `blunt + technical` | Performance critiques, postmortems, anti-pattern posts |
| `warm + technical` | Beginner-oriented tutorials |
| `casual + technical` | Developer-blog informal voice (Substack-y engineering writing) |

## Sample passages

### Bad (technical purpose done wrong)
> In today's rapidly evolving digital landscape, understanding distributed systems is crucial for any modern engineer. Let's dive into the fascinating world of consensus algorithms and explore how they revolutionize the way we think about reliability. We'll embark on a journey through the multifaceted realm of CAP theorem implications.

### Good (technical voice + technical purpose)
> Raft is a consensus algorithm for replicated state machines. Compared to Paxos, it makes leader election and log replication easier to understand and implement. It's the basis for etcd, Consul, CockroachDB, and TiDB.
>
> A Raft cluster has 3-7 nodes. One node is the leader. The others are followers. Clients send all writes to the leader. The leader appends to its log, replicates to followers, waits for quorum (majority) acknowledgment, then commits.
>
> If the leader crashes, followers detect missing heartbeats after `election_timeout` (default 150-300 ms in most implementations). Each follower transitions to candidate, increments its term, and requests votes. The first candidate to receive a majority becomes leader.
>
> Failure mode: split-brain is prevented by the term + quorum requirement. A network partition isolating the old leader from a majority means it can't commit anything new; the new majority elects a new leader and continues.
>
> See [raft.github.io](https://raft.github.io) for the formal paper and visualization.

## Common pitfalls

- Marketing language slipping in ("powerful", "elegant solution")
- Mixing technical content with promotional framing
- Pretending complexity doesn't exist
- Using "we" when there's no "we" (single-author docs)
- Forgetting version numbers + context
- Writing for compilers, not humans (over-formal pseudo-mathematical style)

## See also

- `references/style/voices/technical.md` — most common voice pairing
- `references/style/voices/professional.md` — secondary voice option
- `references/style/banned-words.md` — global banned list (technical adds: "easy", "simple", "just")
- `references/seo/citation-capsules-princeton.md` — for AI citation in technical content
