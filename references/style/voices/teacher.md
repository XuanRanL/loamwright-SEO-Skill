# Voice: Teacher

The patient, knowledgeable teacher voice. Breaks down complex ideas into easier parts; builds up to harder concepts. Uses comparisons, examples, step-by-step explanations. Spots and addresses confusion before it arises. Encouraging tone without sycophancy. May pose thinking questions or mental exercises to involve the reader.

## Best for

- Educational content (tutorials, explainers, courses)
- Technical content for newer audience
- "What is X" definition articles
- Step-by-step guides where reader needs to UNDERSTAND, not just FOLLOW
- E-learning + online course content
- "Beginner's guide to X" / level-guide format
- Industry topics being explained to lay audience
- Documentation introductions

## Hard rules (teacher's 5 principles)

### 1. Build from familiar to unfamiliar

Always start with what the reader already knows. THEN extend.

✗ "Vector embeddings are a way to represent text mathematically." (assumes math background)
✓ "You know how a thesaurus groups similar words together? Vector embeddings do something similar — but in mathematics, not language. Imagine each word is given coordinates on a vast map, and words with similar meaning end up close together."

### 2. Use comparisons + examples + analogies

Make the abstract concrete. Every major concept needs at least one analogy.

✗ "Recursion is when a function calls itself."
✓ "Recursion is like a set of nested mirrors. Each mirror reflects the next, which reflects the next. In code, each call to a function 'reflects' onto a smaller version of the same problem, until it hits the base case — the last mirror that just shows the wall."

### 3. Spot confusion before it arises

Anticipate what the reader will misunderstand. Address it preemptively.

✗ "Here's how it works."
✓ "Before we get into how this works, let's address what most people assume — and where that assumption breaks down. You probably think [X]. But the actual mechanism is [Y]. Now let's see why."

### 4. Encouraging tone without sycophancy

Acknowledge difficulty honestly. But also celebrate small wins.

✗ "This is super easy — anyone can do it!" (lies; condescending)
✓ "This part can feel confusing the first time through. That's normal — even experienced developers occasionally trip on this. Take it slowly. Once it clicks, the rest of the section will feel much easier."

### 5. Pose thinking questions

Mid-flow, ask the reader a question that activates their own thinking:

✓ "Before you read on, ask yourself: what would happen if you ran this code with input X? Predict the output. Then check below."
✓ "Pause here. Think about what's missing from this list — what else might affect the result?"
✓ "If you had to debug this yourself, where would you look first?"

## Voice characteristics

| Trait | Setting |
|---|---|
| Contractions | Yes (it's, don't, you're, we'll) — friendly but not slangy |
| First person | "I" sparing; "we" common (shared inquiry) |
| Direct address | "you" frequent — speaking directly to reader |
| Hedging | Used to acknowledge difficulty ("this is tricky", "many people get confused here") |
| Sentence length | Mixed — short for emphasis, long for explanation |
| Paragraph length | Medium (60-100 words) — let ideas breathe |
| Burstiness | Moderate (SD 5-7) |
| Tone | Patient + curious + encouraging |

## Vocabulary preferences

| Prefer | Avoid |
|---|---|
| "Let's break this down" | "Now we'll explore" (passive) |
| "Picture this:" | "Consider the following:" (formal) |
| "Think of it like..." | "Analogously..." |
| "Here's the key insight" | "The crucial point is..." |
| "Try this:" | "One could attempt..." |
| "If this still feels confusing" | "If unclear..." |
| "Most people don't realize..." | "It is worth noting that..." |
| "Take a moment to..." | "Pause and reflect..." (too formal) |

## Required moves

### Open with curiosity, not authority

✗ "This guide will teach you everything you need to know."
✓ "Have you ever wondered why X happens? It's a stranger question than it seems."

### Explicit "stepping stones"

Use phrases like:
- "Now that you understand X, here's the next piece..."
- "Hold on to that idea — we'll come back to it in a minute."
- "This is where things get interesting."
- "If you remember Y from earlier, this will make sense."

### Worked examples > abstract explanation

Every concept needs at least one worked example. Don't explain → leave reader to apply. Explain → demonstrate → ask reader to predict next.

### Acknowledge difficulty + celebrate progress

Mid-article checkpoints:
- "If you're still with me, we just covered three things..."
- "This part takes most people two reads to internalize. That's fine — keep going."
- "We've now covered the foundation. The next section builds on this."

### End with capability, not summary

✗ "In conclusion, we discussed X, Y, Z."
✓ "By now, you should be able to: explain [concept] to a colleague; debug [problem type]; recognize [signal] when it appears. If any of those feels uncertain, pick that section and reread."

## Allowed in teacher voice

- Direct address ("you", "let's")
- Rhetorical questions ("What do you think happens next?")
- Acknowledgments ("This part is tricky")
- Worked examples + try-it-yourself prompts
- Mid-paragraph asides
- Cross-references back to earlier ideas
- Mild humor when illustrating (not joke-cracking)

## Banned (teacher voice specific)

In addition to global banned-words.md:
- "Just" (minimizes effort unfairly — "just install npm install" hides real complexity)
- "Simply" (same problem)
- "Obviously" / "Clearly" (condescending; nothing is obvious to a learner)
- "It's easy" (often a lie; teaches reader to feel stupid when it's hard for them)
- "We won't go into detail" without follow-up (creates frustration; either provide it or point to resource)
- "Advanced users can skip this" (excludes; restructure instead)

## Sample passage

### Bad (teacher voice done wrong — condescending)
> Hello dear student! Today we're going to learn about CSS Grid! It's super easy and I just KNOW you'll love it! Don't worry if you don't understand at first — that's totally fine! Let's begin!

### Good (teacher voice + technical purpose)
> CSS Grid is one of those tools that feels mysterious until it doesn't — and then you wonder how you ever built layouts without it.
>
> Let's start with what you might already know: Flexbox arranges things in a row or column. You can stack items, space them out, align them. That's helpful, but limited. What if you wanted a layout where some items span two columns, others span three rows, and the whole thing rearranges on smaller screens?
>
> That's where CSS Grid earns its name. Think of it as a grid you can draw on a page — with rows and columns you define yourself. Each child element gets placed onto that grid by saying "I want to be in column 2 to 4, row 1 to 3." It's like assigned seating, but for layout.
>
> Try this before reading on: open your code editor. Create a parent div with three child divs. Apply `display: grid` and `grid-template-columns: 1fr 1fr 1fr` to the parent. What happens?
>
> If you predicted "the three children sit side-by-side in equal-width columns," you're right. That `1fr 1fr 1fr` declared three equal columns — fr means "fraction of available space."
>
> Now here's where most tutorials would give you twenty more property names. Let's not do that yet. Stop with these three children + three columns. Try changing the children's content (long sentences, single words, an image). See how the columns respond. Notice what stays equal and what shifts.
>
> This experiment matters because Grid behaves in ways your intuition might mispredict. The columns are equal because we declared them so — but if you add `auto` instead of `1fr`, columns size to their content. The distinction will become important when we add responsive design later.

## Combining with purposes

| Voice + purpose | Typical use |
|---|---|
| `teacher + technical` | The canonical combination — programming tutorials, dev docs |
| `teacher + general` | Educational blog posts ("How does X work?") |
| `teacher + essay` | Long-form explainer of a concept |
| `teacher + marketing` | AVOID — marketing brevity conflicts with teacher's careful build-up |
| `teacher + email` | AVOID — emails should be short; teacher needs space |

## When NOT to use

- Authoritative declarations (use professional or blunt)
- Quick-answer FAQ (use general)
- Marketing copy (teacher's slow build-up doesn't fit conversion goals)
- News + breaking events (urgency conflicts with teacher pace)
- Highly technical advanced docs assuming reader is expert (waste of teacher's patient build-up)

## Soul Injection compatibility

All 11 Soul Injection patterns work well with teacher voice:

- ✓ #1 Strong opinions (when sharing teaching philosophy)
- ✓ #2 Honest uncertainty (models how learners should feel)
- ✓ #3 Specific sensory detail (worked examples are sensory)
- ✓ #4 Shared experience callback ("you know that feeling when...")
- ✓ #5 Allow tangents (controlled — to illuminate, not to confuse)
- ✓ #6 Dramatic paragraph variation (1-word emphasis fine)
- ✓ #7 Imperfect opening (curious question works well)
- ✓ #8 Break parallel structure (avoid formulaic tutorials)
- ✓ #9 Callbacks (essential for stepping stone metaphor)
- ✓ #10 Self-correct (models intellectual honesty)
- ✓ #11 End without wrap-up (end with capability, not summary)

## See also

- `references/style/voices/nussbaum-academic.md` — formal sibling (philosophical analysis)
- `references/style/voices/warm.md` — most similar (empathy-driven)
- `references/style/purposes/technical.md` — most common purpose pairing
- `templates/level-guide.md` — format-fit for teacher voice
- `templates/how-to-guide.md` — common template
