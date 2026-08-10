# Em-Dash Prohibition

Loaded by the writer, humanizer, and section-drafter. A publish-blocking style rule.

## The rule

**The em-dash `—` (U+2014) count in any section MUST be exactly 0.** The em-dash is the single
strongest "written by AI" tell in 2026 — LLMs over-use it at a rate no human writer matches, and
readers (and AI-detectors) pattern-match on it. It is banned outright in body prose, headings,
table cells, blockquote attributions, callouts, list items, and captions.

Also avoid the en-dash `–` (U+2013) as a sentence connector (a numeric range like `2–4` is fine
but prefer `2 to 4`). The horizontal-bar `―` (U+2015) is likewise banned.

## What to write instead

Recast the sentence. The em-dash almost always hides one of these, and each has a cleaner form:

| You wanted an em-dash for… | Write instead |
|---|---|
| A parenthetical aside | commas, or parentheses: `the fixture (rated 1000W) draws…` |
| A sharp break / reveal | a period. Two short sentences beat one dashed one. |
| A range | the word "to": `30 to 40 watts`, not `30—40 watts` |
| An attribution after a quote | a new line, or the word "by": `…the tenth link.\n\nJames, Loamwright` |
| A list lead-in | a colon `:` |
| Emphasis | rephrase, or bold the key clause |

## Examples

- ❌ `Photon efficacy — not wattage — decides your bill.`
  ✅ `Photon efficacy, not wattage, decides your bill.`
- ❌ `Size for the canopy — not the room.`
  ✅ `Size for the canopy, not the room.` (or two sentences)
- ❌ `Budget tier — under $300 — suits a single tent.`
  ✅ `The budget tier (under $300) suits a single tent.`

## Enforcement

The writer self-checks `em_dash_count == 0`; render_lint and the pre-publish gates re-verify on
the assembled draft. A single em-dash reaching the draft is a hard finding, not a soft note. When
in doubt, delete the dash and add a period.
