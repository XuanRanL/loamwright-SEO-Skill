# Purpose: Marketing

Content with a conversion goal — landing pages, sales pages, product pages, lead-gen articles. Strong CTAs allowed. Benefits over features. But beware of triggering AI-tell patterns common in low-quality marketing copy.

## Layer rules (on top of voice)

- **Short paragraphs** (3-5 sentences max; 2-3 sentence paragraphs preferred)
- **Concrete benefits** over abstract features ("save 4 hours/week" not "boost productivity")
- **One clear CTA** at the end (per claude-blog data: +266% engagement vs no CTA, +682% vs 2+ CTAs)
- **Numeric proof points** where possible (specific stat with source)
- **Disclosure required** for affiliate / sponsored / promotional content (FTC compliance)
- **No "boost" / "skyrocket" / "10x" hyperbole** — triggers AI-slop detection

## Structural defaults

```
Hero (~80-150w):
  - Specific outcome or value prop in first line
  - Numeric proof point in second line (when possible)
  - Soft CTA or scroll cue

Body (60-70% of total):
  - 3-5 sections, each ~200-400w
  - Each section: claim + proof + benefit + transition
  - At least 1 case study or specific example per 800 words

Closing (~150-250w):
  - Synthesis of value prop
  - The CTA (singular)
  - Trust signal (testimonial / customer count / award / etc.)
```

## Banned in marketing purpose

The AI-slop trap is highest in this purpose. Be aggressive about avoiding:

- "Boost your X" — generic; replace with specific outcome
- "Skyrocket Y" — overpromises; replace with measured claim
- "10x your Z" — uncalibrated hype
- "Revolutionary" — almost always false
- "Game-changing" — almost always false
- "Cutting-edge" — almost always lazy
- "Robust solution" — meaningless
- "Best-in-class" — uncalibrated
- "Leverage" (as verb) — corporate filler
- "Enable you to..." — passive; use direct action verbs
- "Unlock the power of..." — clichéd
- "Discover the secrets..." — clickbait
- "Take your X to the next level" — meaningless
- "Empower your team..." — corporate filler

## Required moves

1. **Lead with the outcome, not the feature**
   - Bad: "Our platform uses advanced ML"
   - Good: "Cut report-building time from 4 hours to 12 minutes"

2. **Quantify when possible**
   - Bad: "Save significant time"
   - Good: "Save 4 hours per week per analyst"

3. **Single CTA at the end**
   - One primary action per page
   - Not "Sign up" + "Demo" + "Pricing" + "Whitepaper" (decision paralysis)

4. **Trust signal in closing**
   - Specific (logo grid, customer count, ROI stat)
   - Not "thousands of happy customers" (vague)

5. **Disclosure when applicable**
   - Affiliate: "I may earn a commission if you buy through this link" (per FTC)
   - Sponsored: "This article was sponsored by [Brand]"
   - Promotional: "Disclosure: I work at [Company]"

## Hard rules (T03 veto territory)

- Affiliate links without disclosure → T03 veto fires (BLOCK publish)
- Sponsored content without disclosure → T03 veto fires
- YMYL marketing (medical/financial advice as marketing) → requires credentialed author
- "Best X for Y" listicles with affiliate links → require disclosure

## Sample passages

### Bad (marketing purpose done wrong)
> Welcome to the future of productivity! Our cutting-edge AI-powered platform is here to revolutionize the way you work. By leveraging advanced machine learning and seamlessly integrating with your existing workflow, we empower teams to unlock unprecedented levels of efficiency. Take your productivity to the next level with our game-changing solution!

### Good (professional voice + marketing purpose)
> Marketing teams using Reporter cut their weekly report-building time from 4 hours to 12 minutes.
>
> Reporter connects to your Google Analytics, GSC, and CRM. It pulls the metrics you care about, formats them in the report templates your team uses, and posts the result to your Slack or email. Setup takes 8 minutes. The first report runs immediately.
>
> Last quarter, 47 marketing teams switched from manual spreadsheet reports. Their average time-savings: 14.6 hours per analyst per week, validated via timesheet data.
>
> **Try Reporter free for 14 days →** [link]
>
> No credit card required. Cancel anytime via the dashboard.

## Combining with voice

| Voice + marketing | Typical use |
|---|---|
| `professional + marketing` | B2B SaaS landing pages, sales pages |
| `casual + marketing` | DTC ecommerce, lifestyle products |
| `warm + marketing` | Community-driven brands, education |
| `blunt + marketing` | Anti-marketing — "stop wasting money on X" |
| `technical + marketing` | AVOID — promotional language poisons technical credibility |

## Common pitfalls

- Stacking 5+ AI-vocabulary words in one paragraph (immediate detection)
- Using a different voice mid-page (e.g., warm landing → professional pricing → casual FAQ)
- 3+ CTAs competing for attention
- Trust signals that are too generic ("trusted by leading brands" — name them)
- Missing disclosure on affiliate content (legal risk)

## When NOT to use marketing purpose

- Help center docs (use `general` purpose)
- Tutorials (use `general` or `technical`)
- Blog posts that incidentally mention a product (use `general`)
- Customer support replies (use `email`)

## CTA placement

Per data: single CTA at ~30-40% mark of long-form content OR end of short-form content (≤800 words).

- NEVER above the fold (looks like ad)
- NEVER in a floating sidebar (distracting)
- ALWAYS with clear value prop next to the link

## See also

- `references/seo/micro-copy-tactics.md` — CTA copy patterns
- `references/style/banned-words.md` — global banned list (marketing has additional bans)
- `references/seo/cta-placement-data.md` — placement research
- `references/style/voices/professional.md` — most common pairing
