# APA 7 Citation Rules (Quick Reference)

> Used by `scripts/validate/apa_format_validator.py` and `subskills/build/fact-check-and-citation/`.

---

## ⚠️ CRITICAL RULE: In-text citations are NEVER hyperlinked

In-text APA citations like `(Smith, 2024)` or `(Smith & Lee, 2024, p. 45)` MUST appear as **plain text** in the article body.

- ✗ Wrong: `According to research, X is true ([Smith, 2024](https://doi.org/...))`
- ✗ Wrong: `According to research, X is true (<a href="...">Smith, 2024</a>)`
- ✓ Right: `According to research, X is true (Smith, 2024)`

**Why**:
- APA 7 convention (Publication Manual 7th ed., section 8.21)
- Hyperlinks in body text create visual noise + break reading flow
- Screen readers handle plain text citations better
- AI engines parse plain-text citations more reliably

**Where links DO appear**: the References section at the end of the article. DOIs and URLs there ARE clickable.

This rule is enforced by `apa_format_validator.py`. Violations are flagged as warnings (not hard fail, since legacy content may have them).

---

## In-text citation (parenthetical)

### Single author
`(Smith, 2023)`

### Two authors
`(Smith & Lee, 2024)`

### Three or more authors (use "et al." from first cite)
`(Smith et al., 2024)`

### Specific page (for direct quotes)
`(Smith, 2023, p. 45)` or `(Smith, 2023, pp. 45-47)`

### Multiple sources in same parenthesis
`(Smith, 2023; Lee, 2024; Wang, 2025)`

### Organization as author (use full name first time, abbreviation after)
First: `(World Health Organization [WHO], 2024)`
Subsequent: `(WHO, 2024)`

### No date
`(Smith, n.d.)`

### Personal communication (NOT in References)
`(J. Smith, personal communication, May 19, 2026)`

---

## In-text citation (narrative — inline in sentence)

### Single author
`Smith (2023) found that...`

### Two authors
`Smith and Lee (2024) demonstrated...`

### Three or more
`Smith et al. (2024) reported...`

---

## Reference list entry formats

### Journal article (DOI required)
```
Author, A. A., Author, B. B., & Author, C. C. (Year). Title of article. 
  Journal Name, Volume(Issue), Pages. https://doi.org/10.xxxx/xxxxxxxx
```

Example:
```
Smith, J. R., & Lee, K. (2023). Lumbar support and posture outcomes 
  in modern office workers. Journal of Ergonomics, 45(3), 211-228. 
  https://doi.org/10.1234/joe.2023.0211
```

### Book (whole book)
```
Author, A. A. (Year). Book title in sentence case. Publisher.
```

Example:
```
Walker, M. (2017). Why we sleep: Unlocking the power of sleep and dreams. 
  Scribner.
```

### Chapter in edited book
```
Author, A. A. (Year). Chapter title. In E. Editor (Ed.), Book title 
  (pp. xx-xx). Publisher.
```

### Online newspaper / magazine article
```
Author, A. A. (Year, Month Day). Article title. Newspaper Name. URL
```

Example:
```
Smith, J. (2024, March 15). New SEO trends emerge. The New York Times. 
  https://www.nytimes.com/2024/03/15/...
```

### Webpage (general)
```
Author, A. A. (Year, Month Day). Title of webpage. Site Name. URL
```

If no author or organization, start with title.

### Report / white paper
```
Author, A. A., or Organization. (Year). Title of report (Report No. xxx). 
  Publisher. URL or DOI
```

### Dataset
```
Author, A. A. (Year). Title of dataset (Version) [Data set]. Publisher. 
  DOI or URL
```

---

## CRITICAL rules

### Year and DOI
- ✅ Always include year
- ✅ Always include DOI if available (prefer DOI over URL)
- ✅ DOI format: `https://doi.org/10.xxxx/...` (NOT `doi.org/...` without `https://`)
- ❌ Never write "Retrieved from," "from," or "source"

### Hyperlinks
- ✅ Reference list URLs/DOIs ARE links (clickable)
- ❌ In-text citations are NOT hyperlinks (e.g., `(Smith, 2023)` is plain text)
- ❌ Don't hyperlink author names in body prose

### Capitalization
- ✅ Article/book titles: sentence case (only first word + proper nouns)
- ✅ Journal titles: Title Case (italicized in print; we use plain text)
- ✅ Names: standard capitalization

### Author count
- 1-20 authors: list all
- 21+ authors: list first 19, then ..., then last author

### No author
- Start entry with title

### Same author same year
- Use lowercase suffix: `(Smith, 2023a)`, `(Smith, 2023b)`

---

## URL / DOI requirements (v3.2 specific)

Per `scripts/validate/link_resolver.py`:

- ✅ DOI returns 200 OK on HEAD request
- ✅ URL returns 200 OK (not 404, not 302 to a generic page)
- ❌ URLs containing `grounding-api-redirect` (Google AI redirects) → REJECTED
- ❌ URLs to PDFs hosted on `cdn.openai.com` → REJECTED (likely AI-generated)
- ❌ Shortened URLs (bit.ly, t.co) → resolve to canonical first

---

## What counts as Tier 1 vs Tier 2 vs Tier 3 sources

### Tier 1 (highest authority, prefer for E-E-A-T)
- Peer-reviewed journals (Nature, Science, NEJM, JAMA, Cell, etc.)
- .gov publications (NIH, FDA, CDC, CDC, WHO, BLS, Census)
- .edu primary research
- Established research institutes (NBER, Pew Research, Brookings, Cochrane)

### Tier 2 (industry authority, OK for commercial topics)
- Major news outlets (NYT, WaPo, FT, WSJ, Reuters, AP, BBC)
- Industry publications with editorial standards (Bloomberg, Reuters, Wired)
- Company first-party research (Shopify reports, HubSpot studies)
- Trade associations

### Tier 3 (acceptable for context, not for hard claims)
- Major SaaS blogs (Moz, Ahrefs, SEMrush, Buffer) — known authors
- Personal blogs by known experts
- Industry forums / Reddit (only as primary opinion source, never for facts)

### NEVER cite (Tier 0 / banned)
- AI-generated content (use OpenAI/Anthropic only for definitions, never as authority)
- Untraceable "studies have shown..."
- Stock photo / shutterstock as source
- 404'd URLs
- Aggregator sites that summarize other primary sources

---

## Maximum references per article

**Cap: 10 references** per blog article (v3.2 spec).

Why: Beyond 10, the References section becomes noise. The 10-cite limit forces:
- Picking strongest sources
- Combining adjacent claims into single citation when possible
- Not citing same source 3 times in same paragraph

Exception: data-research / case-study formats may go to 15 if methodology requires.

---

## Order in References section

Alphabetical by first author's surname. Multiple works by same author: chronological (oldest first), with year disambiguation suffix if needed.

---

## See also

- `scripts/validate/apa_format_validator.py` (enforcement)
- `scripts/validate/link_resolver.py` (URL validation)
- `subskills/build/fact-check-and-citation/SKILL.md` (citation pipeline)
- `references/seo/citation-capsules-princeton.md` (in-text citation density)
