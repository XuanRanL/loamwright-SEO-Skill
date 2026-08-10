# 43 AI Writing Patterns (humanizer-skill catalog)

> Used by `scripts/lint/ai_tells_detector.py`. Each pattern has: ID / category / definition / why-AI / fix-strategy / example.
>
> **Derived from**: humanizer-skill open-source catalog (2026), augmented with 2026-specific community findings.

---

## CONTENT patterns (P1-P8)

### P1 — Significance inflation
**Definition**: Claims of unmeasured impact ("cannot be overstated", "game-changer", "paradigm shift")
**Why AI**: LLMs hedge into grandiosity when uncertain
**Fix**: Replace with specific magnitude (X% change, N units before/after, $ saved)
**AI example**: "The importance of mobile-first design cannot be overstated."
**Human rewrite**: "Mobile traffic now drives 67% of e-commerce orders (Shopify 2026)."

### P2 — Name-dropping without substance
**Definition**: Vague authority references ("industry leaders", "top experts", "leading researchers") with no names
**Why AI**: Sounds authoritative without committing
**Fix**: Name specific people/orgs OR drop the claim
**AI example**: "Industry leaders agree on this approach."
**Human rewrite**: "Three Fortune 500 retailers (Target, Walmart, Best Buy) adopted this in Q4 2025."

### P3 — Shallow -ing phrases
**Definition**: "ensuring/allowing/enabling/providing" + abstract noun + "experience/solution/approach"
**Why AI**: Pattern padding
**Fix**: Cut the -ing phrase; state concrete result
**AI example**: "...thus ensuring a seamless customer experience."
**Human rewrite**: "...so customers complete checkout in under 30 seconds."

### P4 — Promotional / sales language
**Definition**: "industry-leading", "state-of-the-art", "best-in-class", "world-class", "premier"
**Why AI**: Default marketing veneer
**Fix**: Replace with specific differentiator
**AI example**: "Our world-class platform delivers..."
**Human rewrite**: "Our platform processes 12k orders/second (verified by RealityCheck, 2026)."

### P5 — Vague attributions
**Definition**: "Studies have shown", "research indicates", "experts say" with no citation
**Why AI**: Authority laundering
**Fix**: Cite specific study with year + DOI/URL
**AI example**: "Studies have shown that good sleep improves productivity."
**Human rewrite**: "Sleeping 7.5+ hours boosts focus by 27% (Walker, 2017, *Why We Sleep*)."

### P6 — Formulaic challenges
**Definition**: "In today's fast-paced world of X" / "In this digital era"
**Why AI**: Boilerplate opener
**Fix**: Use specific year or delete entirely
**AI example**: "In today's fast-paced digital world..."
**Human rewrite**: "In 2026..." or just start with the topic

### P7 — AI vocabulary cluster
**Definition**: Concentrated use of: multifaceted, tapestry, landscape, intricate, comprehensive, delve, leverage, robust, seamless, foster, harness, paradigm, nestled
**Why AI**: Training data preference
**Fix**: Substitute per references/style/banned-words.md

### P8 — Copula avoidance (over-elevation of "is")
**Definition**: "serves as", "exists as", "functions as", "stands as" replacing plain "is"
**Why AI**: Sounds more formal
**Fix**: Use "is/are" plainly
**AI example**: "Mobile design serves as a critical factor."
**Human rewrite**: "Mobile design is critical."

---

## LANGUAGE/STYLE patterns (P9-P18)

### P9 — Negative parallelism ("not just X, but also Y")
**Fix**: State the positive directly; drop the rhetorical "not just"
**AI example**: "This is not just about speed, but also about reliability."
**Human rewrite**: "Speed and reliability both matter here."

### P10 — Rule-of-three lists
**Definition**: "X, Y, and Z" Oxford-comma list pattern in 80%+ of multi-item sentences
**Fix**: Break rhythm — use 2 or 4 items, OR longer phrasing
**AI example**: "fast, reliable, and scalable"
**Human rewrite**: "fast and reliable, with proven scaling to 100k users"

### P11 — Elegant variation (synonym cycling)
**Definition**: Avoiding repetition by switching utilize → employ → use → leverage in same paragraph
**Fix**: Use "use" consistently; vary structure, not vocabulary

### P12 — False range
**Definition**: "from basic to advanced" / "from beginners to experts" — pretends to cover a spectrum
**Fix**: Make range specific or drop the framing

### P13 — Em-dash overuse
**Definition**: U+2014 em-dashes more than 3 per article
**Fix**: Replace with commas, parens, or full stops
**Critical**: v3.2 zero-tolerance policy

### P14 — Bold / asterisk overuse
**Definition**: More than 2 **bold** runs per H2 section
**Fix**: Bold for scanning anchors only

### P15 — Structured-list syndrome
**Definition**: Five+ consecutive list items where prose paragraphs should appear
**Fix**: Break with prose, alternate format

### P16 — Title-Case Subheadings
**Definition**: H2/H3 in Title Case Like This Throughout The Entire Article
**Fix**: Use sentence case (Capitalize first + proper nouns only)
**AI example**: "## How To Choose The Best Fishing Rod For Beginners"
**Human rewrite**: "## How to choose the best fishing rod for beginners"

### P17 — Curly typographic quotes
**Definition**: Smart quotes ' ' " " instead of straight ASCII
**Why AI**: ChatGPT default tell
**Fix**: Replace with straight quotes (use `scripts/lint/curly_quote_audit.py --fix`)

### P18 — Formal register shift
**Definition**: utilize, commence, terminate, endeavor, facilitate in casual context
**Fix**: Use plain alternatives (use/start/end/try/help)

---

## COMMUNICATION patterns (P19-P21)

### P19 — Chatbot artifacts
**Definition**: "I'd be happy to", "As an AI", "Sure!", "Certainly!", "Of course!"
**Fix**: Delete entirely — these are conversational AI sediment

### P20 — Knowledge-cutoff disclaimer
**Definition**: "As of my last knowledge update", "As of my knowledge cutoff"
**Fix**: State a real date or remove

### P21 — Sycophantic tone
**Definition**: "Great question!", "Excellent point!", "That's absolutely correct"
**Fix**: Get to substance

---

## FILLER patterns (P22-P30)

### P22 — Filler phrases
**Definition**: "it's important to note", "it's worth mentioning"
**Fix**: Delete; state the fact

### P23 — Hedging stacks
**Definition**: "might possibly potentially", "may perhaps", "could potentially"
**Fix**: One hedge max; or commit

### P24 — Generic positive conclusion
**Definition**: "By embracing these strategies, you can..."
**Fix**: End with specific next action

### P25 — Hallucination markers
**Definition**: "Research has shown..." with no source or year
**Fix**: Add (Author, Year) citation or delete claim

### P26 — Perfect/error alternation
**Definition**: 3+ perfectly-formatted numbered list items in a row (no fragments, no asides)
**Fix**: Break rhythm with fragment or aside

### P27 — Question-format titles
**Definition**: All H2 headings as questions
**Fix**: Mix declarative + question (>3 in one article = AI rhythm)

### P28 — Markdown bleeding into prose
**Definition**: Asterisks mid-sentence, escape characters showing
**Fix**: Clean markdown rendering check
**NOT a defect** (2026-07-17): a correctly-closed `*italic*` run is valid markdown, not
bleed — scientific binomials (`*Hibiscus sabdariffa*`, `*Camellia sinensis*`) MUST stay
italic (ICN convention) and the humanizer must never strip them to clear this pattern.
`ai_tells_detector` now exempts italic-only-balanced lines from P28; only genuine
unbalanced/orphan markers and mid-sentence `**bold**` overuse still fire.

### P29 — Comprehensive overview opening
**Definition**: "This article will explore..." / "In this guide, we will cover..."
**Fix**: Open with hook, not meta-description

### P30 — Uniform sentence length
**Definition**: ≥3 consecutive sentences within ±3 words of each other
**Fix**: See `scripts/lint/sentence_variance.py` for measurement (burstiness > 0.30 target)

---

## EMERGING 2026 patterns (P31-P37) — newer AI tells

### P31 — Phrase-level elegant variation
**Definition**: "in essence", "in other words", "put simply", "essentially", "fundamentally", "basically" — all used in one article
**Fix**: Pick one; usually "or" suffices

### P32 — "We will explore" leak
**Definition**: "We'll explore / examine / dive into / cover / look at"
**Fix**: Just start exploring; don't announce

### P33 — Placeholder text in published copy
**Definition**: `[insert your X here]`, `[TODO]`, `[FIXME]`
**Critical**: Remove before publish

### P34 — Chatbot reference markup
**Definition**: `citeturn0search0`, `oai_citation`, `cite\nturn0`
**Critical**: NEAR-DEFINITIVE AI evidence

### P35 — `utm_source=chatgpt.com`
**Definition**: URL parameter exposing source
**Critical**: NEAR-DEFINITIVE AI evidence

### P36 — Register shift (formal → casual mid-sentence)
**Definition**: "Utilize the platform" + "gonna/wanna/kinda"
**Fix**: Pick a register

### P37 — Source-listing as content
**Definition**: "Source: 1. X, 2. Y, 3. Z" instead of in-text citations
**Fix**: Integrate via in-text + References section

---

## COMMUNITY 2026 patterns (P38-P43) — Reddit/forum-discovered

### P38 — Paragraph-reshuffling immunity
**Definition**: Paragraphs can be reordered without changing meaning (filler-heavy)
**Fix**: Each paragraph must depend on what comes before

### P39 — "Whether you prefer..." closing summary
**Definition**: "Whether you're a beginner or a professional, this guide..."
**Fix**: End with single recommendation, not audience matrix

### P40 — Symbolic gloss
**Definition**: "represents", "symbolizes", "stands for", "embodies" + abstract concept
**Fix**: Be concrete — what does it DO?

### P41 — Infomercial hooks
**Definition**: "The catch?", "The kicker?", "The twist?", "The best part?", "The secret?"
**Fix**: Just state the fact

### P42 — Erratic inline bolding
**Definition**: 3+ **bolded phrases** per paragraph
**Fix**: Bold for scan anchors only

### P43 — Treadmill Effect
**Definition**: 500 words containing 100 words of new info; rest is "in other words/put simply" loops
**Critical**: Highest-impact fix — info density audit

---

## How to use this catalog

1. **At drafting time** (section-drafter agent): self-check after writing each section
2. **At quality gate** (ai_slop_score): counts distinct patterns hit (input to formula)
3. **At humanizer**: locates patterns to rewrite (`scripts/lint/ai_tells_detector.py --json`)
4. **At repair time**: surgical mode replaces hit lines

**Hard pass criteria** (per v3.2):
- ≤5 distinct patterns triggered
- AI-Slop score < 20
- Zero P13 (em-dash) hits
- Zero P34/P35 (chatbot reference markup) hits
