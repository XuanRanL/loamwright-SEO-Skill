# 11 Soul Injection Techniques

> Used by `humanizer` agent + `agents/writer.md` to add human texture without sacrificing E-E-A-T.
>
> **Borrowed from**: humanizer-skill catalog (2026), augmented with thruuu pattern.
>
> Apply sparingly — 1-3 per article, NOT in every section. Used to break uniform AI rhythm.

---

## 1. Real opinion (with reasoning)

Don't hedge. State a position. Back it up.

**Without**: "Some users find feature X helpful."
**With**: "I think feature X is overrated. We disabled it for our team in Q3 and saw no productivity drop."

Marker: 1st person + concrete reasoning.

---

## 2. Honest uncertainty

AI never admits it doesn't know. Humans do.

**Without**: "The optimal frequency is daily."
**With**: "I'm not sure the daily frequency is right for everyone — my team found it overwhelming, but a smaller team might handle it fine."

Marker: "I'm not sure" / "I don't know" / "this might be wrong but"

---

## 3. Specific sensory detail

Concrete > abstract.

**Without**: "We were debugging late at night."
**With**: "I was debugging this at 2am with cold coffee and a fan that wouldn't stop wheezing."

Marker: Specific time, specific physical context, sensory adjective.

---

## 4. Shared experience callback

Build rapport via assumed common ground (use carefully — must be specific to your audience).

**Without**: "Setting up the environment can be frustrating."
**With**: "You know that feeling when you've spent 4 hours on what should be a 20-minute setup? That."

Marker: "You know that feeling when..." / "We've all been there with..."

---

## 5. Allowed tangent

Briefly veer off-topic, then come back. Signals natural human thinking.

**Without**: (stays on topic)
**With**: "Speaking of timeouts (and now I'm thinking about my old Apache 2.0 days, where timeouts were measured in minutes), the modern HTTP/2 multiplexing means..."

Marker: Parenthetical aside + return signal ("anyway", "where was I", "back to").

---

## 6. Dramatic paragraph variation

5-word paragraph next to 80-word paragraph.

**Without**:
```
Paragraph 1: 25 words.
Paragraph 2: 27 words.
Paragraph 3: 24 words.
```

**With**:
```
[55-word paragraph with full thought]

Then it broke.

[80-word paragraph explaining what broke and how we fixed it]
```

Marker: Single-sentence or 5-word paragraph alongside longer ones.

---

## 7. Imperfect opening

AI opens with thesis statements. Humans wander in.

**Without**: "This article explores the benefits of TypeScript."
**With**: "So I was looking at the logs around 11pm, trying to figure out why production was throwing weird errors, and..."

Marker: "So I was..." / "Look, here's what happened..." / "Okay, so..."

---

## 8. Occasional broken parallelism

AI loves rule-of-three perfect parallels. Humans break them.

**Without**: "We rebuilt the API, redesigned the UI, and rewrote the docs."
**With**: "We rebuilt the API, redesigned the UI. Docs got rewritten too, eventually."

Marker: Different structure on items in a series.

---

## 9. Callbacks (echo earlier text)

Reference something said earlier in the article. AI rarely does this.

**Without**: (each section stands alone)
**With**: "Remember that 28% sensitivity boost from section 2? Here's where it actually matters in practice."

Marker: "Remember when I said..." / "Going back to that point about..."

---

## 10. Self-correction

AI revises silently. Humans say "wait, actually..."

**Without**: "Use authentication to secure the endpoint."
**With**: "Use authentication to secure the endpoint — well, technically authentication AND authorization are two different things, but everyone uses 'auth' to mean both, so just bear with me."

Marker: "Wait, that's not quite right" / "Let me rephrase that" / "Actually..."

---

## 11. Don't strong wrap up

AI's reflex is to end with synthesis. Don't.

**Without**: "In conclusion, TypeScript offers many benefits. By embracing these strategies..."
**With**: "Anyway, that's the setup. Try it and see what breaks in your codebase. (It will break something — that's how you'll learn the rest.)"

Marker: Permission to leave threads open. No "in conclusion" / "in summary".

---

## How humanizer agent uses this

When fixing flagged AI patterns:
1. Identify which pattern fired (e.g., P9 negative parallelism)
2. Find the offending line
3. Pick the Soul Injection that fits the local context
4. Apply ONE technique, not multiple

Don't over-soul. 2-3 injections per 3000-word article is plenty. More feels performative.

---

## Common mistakes (don't over-soul)

- ❌ Every paragraph has a "anyway"  
- ❌ Every section starts with "So I was..."
- ❌ Every claim is hedged ("I'm not sure but maybe...")
- ❌ Multiple soul injections in adjacent paragraphs
- ❌ Soul injection in technical instructions (just be clear there)

Subtlety wins. The goal isn't to PERFORM human-ness; it's to STOP performing AI-ness.
