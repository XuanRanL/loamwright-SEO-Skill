# Industry → Voice Defaults

Used by `subskills/plan/brand-guideline-maker/SKILL.md` Block 1 to **suggest** voice based on detected industry. **User can always override** — this is a default, not a rule.

## Decision flow

```
/brand-guideline interview Block 1 captures:
  - business_summary
  - industry vertical
        ↓
brand-guideline-maker reads this table
        ↓
Suggests: primary_voice + alternate_voice  
        ↓
User confirms / overrides
```

## Industry → recommended voices

| Industry / vertical | Primary voice | Alternate voice | Avoid voice | Rationale |
|---|---|---|---|---|
| **SaaS B2B (general)** | professional | teacher | playful | Business audience expects competence; teacher useful for product education |
| **SaaS developer tools** | technical | teacher | luxury | Engineering audience; clarity > friendliness |
| **B2C ecom (general)** | casual | storyteller | nussbaum-academic | Lifestyle / mass market |
| **B2C lifestyle / fashion** | storyteller | casual | technical | Aspirational + scene-driven |
| **Tech / engineering** | technical | teacher | luxury | Precision + accessibility |
| **Tech / consumer apps** | casual | playful | nussbaum-academic | Approachable + memorable |
| **Finance / fintech** | authoritative | journalist | playful | Trust + neutrality critical |
| **Investment / wealth management** | authoritative | nussbaum-academic | casual | Sophistication + caution |
| **Insurance** | professional | warm | playful | Trust + accessibility |
| **Banking** | authoritative | professional | playful | Regulated tone |
| **Health / wellness (general)** | warm | teacher | playful | Empathy + education |
| **Health / medical (clinical)** | authoritative | scientific | casual | Credibility critical (YMYL) |
| **Pharma** | scientific | authoritative | inspirational | Evidence-based required |
| **Mental health** | warm | teacher | inspirational | Sensitive + supportive |
| **Legal services** | authoritative | journalist | playful | Precision + neutrality |
| **Legal tech** | professional | technical | luxury | Business-tech blend |
| **Education / e-learning** | teacher | warm | luxury | Pedagogical |
| **Higher education** | nussbaum-academic | teacher | playful | Intellectual |
| **K-12 / parents** | warm | teacher | nussbaum-academic | Supportive |
| **Luxury retail (jewelry, watches)** | luxury | journalist | casual | Refined + restrained |
| **Luxury hospitality** | luxury | storyteller | playful | Heritage + curated |
| **Premium real estate** | luxury | conversational | casual | Refined + relational |
| **News / publisher** | journalist | blunt | luxury | Fact-driven |
| **Travel** | storyteller | casual | luxury | Narrative + accessible |
| **Travel (luxury / boutique)** | luxury | storyteller | casual | Premium positioning |
| **Food / cooking** | warm | storyteller | nussbaum-academic | Sensory + relational |
| **Food (fine dining)** | storyteller | luxury | playful | Heritage + craft |
| **Fashion / beauty** | casual | inspirational | technical | Aspirational + accessible |
| **Fashion (luxury)** | luxury | storyteller | playful | Refined |
| **Gaming** | casual | playful | nussbaum-academic | Audience expects fun |
| **Real estate (residential)** | conversational | storyteller | luxury | Relational |
| **Real estate (commercial)** | authoritative | professional | casual | Business + investment |
| **Sustainability / climate** | warm | nussbaum-academic | playful | Considered + earnest |
| **Sustainability tech** | technical | warm | luxury | Engineering + values |
| **Agency / consulting** | nussbaum-academic | professional | casual | Thought leadership |
| **Personal brand / creator** | casual | conversational | nussbaum-academic | Authentic + relatable |
| **Marketing / advertising** | professional | casual | nussbaum-academic | Industry-standard mix |
| **Crypto / web3** | blunt | technical | luxury | Direct + technical |
| **Outdoor / adventure** | storyteller | casual | luxury | Scene-driven |
| **Fitness / wellness (consumer)** | inspirational | warm | technical | Motivational |
| **Sports content** | storyteller | casual | nussbaum-academic | Narrative-driven |
| **Music / arts** | storyteller | conversational | technical | Cultural + relational |
| **Automotive (mainstream)** | professional | technical | luxury | Authoritative + accessible |
| **Automotive (luxury)** | luxury | technical | casual | Premium positioning |
| **Pet care** | warm | casual | technical | Empathetic |
| **Parenting** | warm | conversational | technical | Supportive |
| **Religion / spirituality** | warm | conversational | playful | Considered tone |
| **Politics / civic** | journalist | nussbaum-academic | playful | Neutral or analytical |
| **Charity / nonprofit** | warm | storyteller | luxury | Mission-driven |
| **B2B services (general)** | professional | authoritative | casual | Business-trust |
| **B2B services (creative)** | nussbaum-academic | conversational | technical | Thought + relational |
| **B2B services (technical)** | technical | professional | playful | Domain expertise |
| **Government / public sector** | professional | journalist | playful | Institutional tone |
| **Government tech** | technical | professional | playful | Regulated |
| **Smart home / IoT** | technical | casual | nussbaum-academic | Tech + accessible |
| **Subscription box / DTC** | casual | playful | luxury | Mass-market consumer |
| **Sustainability fashion** | warm | storyteller | luxury | Values + narrative |
| **Cannabis (medical)** | authoritative | warm | playful | Compliance-aware |
| **Cannabis (recreational)** | casual | playful | luxury | Cultural shift |
| **Adult content** | (handle separately) | | | Separate brand guideline |

## YMYL (Your Money or Your Life) override

For all YMYL topics, regardless of industry voice default:

- Author credentials MUST be visible
- Voice must support credibility — prefer:
  - authoritative, professional, scientific, journalist, nussbaum-academic
- Avoid as primary voice for YMYL:
  - playful, casual (unless paired with clearly credentialed expert author)
  - luxury (positioning conflict)

## Multi-segment brand

If a brand spans multiple industries (e.g., consulting firm serving B2B SaaS + Finance):

- Pick ONE primary voice for the brand
- Use **personas** for audience variants:
  - "CFO persona" — authoritative
  - "Marketing manager persona" — professional
  - "Developer persona" — technical
- Personas can adjust tone within the brand voice; don't have to switch voices

## How brand-guideline-maker uses this table

In Block 1 of the interview, after the user describes business + industry:

```
Detected industry: SaaS B2B (general)
Recommended primary voice: professional
Recommended alternate voice: teacher
Avoid: playful

Would you like to:
A) Use 'professional' as primary (recommended)
B) Use 'teacher' as alternate (also strong fit)
C) Pick a different voice (show 15 options)
```

User can accept, choose alternate, or override entirely.

## Reviewing this table

Update annually based on:
- New industries emerging (e.g., AI agents as service in 2027)
- Industry-specific E-E-A-T requirements changing
- Cultural shifts in tone preferences

## See also

- `references/style/voices/*.md` — 15 voice files
- `references/style/format-voice-affinities.md` — format × voice fit
- `subskills/plan/brand-guideline-maker/SKILL.md` — uses this table
