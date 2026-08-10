# Purpose: Email

Direct one-to-one or one-to-few communication. Greeting + sign-off allowed (in fact, expected). No markdown rendering (assume plain text or basic HTML email client). Short, scannable, action-oriented.

## Layer rules (on top of voice)

- **Greeting** is required ("Hi {Name}," / "Hey {Name}," / "Dear {Name},")
- **Sign-off** is required ("Thanks," / "Best," / "{Your Name}")
- **No markdown formatting** (`**bold**` becomes literal asterisks in plain-text email)
- **Subject line** must exist and earn the open
- **One ask per email** — if you need 3 things, that's 3 emails (or a meeting)
- **Short** — 50-200 words ideal; 400 max

## Structural defaults

```
Subject: [Specific, action-implying]

[Greeting],

[1 sentence: context — why am I writing]

[1-2 sentences: the ask or the information]

[1 sentence: what I need next, with deadline if relevant]

[Sign-off],
[Your name]
```

## Subject line rules

- Specific: not "Question" or "Quick check"
- Action-implying when possible: "Approval needed by Friday: Q3 budget"
- ≤60 characters (mobile clients truncate after this)
- Match the email body's ask (don't bait-and-switch)

| Bad subject | Good subject |
|---|---|
| "Touching base" | "Status on auth migration: blocked on review" |
| "Re: meeting" | "Reschedule Thu 2pm sync to Fri 10am?" |
| "Quick question" | "Production deploy: confirm rollback procedure" |
| "Update" | "Auth bug fixed; verification needed by EOD" |

## Required moves

1. **State purpose in first sentence**
   - "Following up on yesterday's discussion about X..."
   - "Quick question on the Q4 budget allocation..."
   - "Status update on the auth migration..."

2. **Single clear ask**
   - "Can you approve by Friday?"
   - "Is the rollback procedure documented anywhere?"
   - "Would 2pm Thursday work for a 30-min call?"

3. **Make the response easy**
   - Yes/no question > open-ended question
   - Suggest a time > "When are you free?"
   - Provide context links > assume they remember

## Banned in email purpose

- "I hope this email finds you well" (P21 + lazy opener)
- "Just touching base" (no purpose stated)
- "Per my last email" (passive-aggressive)
- "Going forward..." (corporate filler)
- "Circle back" (corporate filler)
- "Reach out" (corporate filler — use "contact" or "ask")
- "Please find attached" (just say "I've attached X")
- "Kindly..." (formal padding)

## Sign-off conventions

| Sign-off | Tone |
|---|---|
| "Thanks," | Neutral, default |
| "Best," | Slightly formal, default for external |
| "Cheers," | Casual, common in UK/AU/NZ |
| "Talk soon," | Warm, ongoing relationship |
| "Best regards," | Formal, when you don't know recipient well |
| "Yours sincerely," | Very formal; only for letters posing as emails |
| "/{first name}" or "—{first name}" | Internal, fast-paced teams |

Match sign-off to voice + relationship. Avoid "Sincerely" (overly formal) and "Warmly" (over-performed warmth).

## When to use email purpose

- Customer support replies (with `warm` voice)
- Sales follow-ups (with `professional` voice; conservative — never `marketing`)
- Internal coordination (with `professional` or `blunt`)
- Personal correspondence (with `casual` or `warm`)
- Cold outreach (with `professional`, max 80 words)

## Sample emails

### Bad (email purpose done wrong)
> Subject: Update
>
> I hope this email finds you well. Just wanted to circle back regarding the recent discussion we had about the new project initiative. As you may recall, we touched base on several action items that need to be addressed going forward. I was wondering if you might have some time in the near future to potentially reconvene and discuss next steps.
>
> Please let me know your thoughts at your earliest convenience.
>
> Kindly,
> Jane

### Good (professional voice + email purpose)
> Subject: Auth migration: need your approval by Thursday
>
> Hi David,
>
> The auth migration PR is ready for review. Three reviewers approved last week; I'm waiting on your sign-off before deploying.
>
> The PR addresses the SAML issue you raised in November. Quick summary: tokens now rotate every 15 min with refresh tokens valid 7 days. Tested against the staging IdP yesterday.
>
> PR link: https://github.com/...
>
> If Thursday morning works to review together, I can hold 9-9:30 AM. Otherwise, async approval works too.
>
> Thanks,
> Jane

## Combining with voice

| Voice + email | Typical use |
|---|---|
| `professional + email` | Default for work emails |
| `casual + email` | Internal teammate notes |
| `warm + email` | Customer support, onboarding |
| `blunt + email` | Memo to exec, fast-paced internal |
| `technical + email` | Engineering notes, postmortem updates |

## Length guidance

- Cold outreach: ≤80 words
- Internal coordination: 50-150 words
- Customer support: 80-250 words (depending on complexity)
- Status updates: 100-200 words
- Apology / escalation emails: 150-300 words (more context needed)

If the email exceeds 400 words, you probably need a meeting OR a doc with an email summary.

## See also

- `references/style/voices/professional.md` — most common voice pairing
- `references/style/voices/warm.md` — for customer-facing
- `references/style/voices/blunt.md` — for fast internal memos
- `references/style/banned-words.md` — corporate filler banned globally
