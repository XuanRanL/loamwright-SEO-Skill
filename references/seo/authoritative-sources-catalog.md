# Authoritative Sources Catalog

Used by `evidence_density_check.py` + `cross_reference_check.py` + `agents/fact-checker.md` to recognize source authority levels.

**Key insight**: peer-reviewed academic is NOT the only authoritative source. Industry experts, top-tier journalism, recognized publications, and verified social platforms all count — at different tiers.

## Tier system

```
Tier 1 (highest — always preferred)
├── 1A: Academic         (DOI, .gov, .edu, peer-reviewed journals)
├── 1B: Top-tier news    (NYT, WSJ, FT, Bloomberg, Reuters, BBC, Economist)
├── 1C: Government data  (BLS, Census, Eurostat, World Bank, IMF, OECD)
└── 1D: Major research   (Pew, Gartner, McKinsey, Forrester, Nielsen, Princeton GEO, MIT)

Tier 2 (industry authority — strong for SEO/marketing)
├── 2A: Industry pubs    (SearchEngineLand, TechCrunch, Wired, MarketingProfs per vertical)
├── 2B: Social experts   (Twitter/X verified, LinkedIn verified, Substack with audience)
└── 2C: Company research  (HubSpot State of Marketing, Salesforce, Stripe research, etc.)

Tier 3 (supporting — use sparingly)
├── 3A: Credentialed blogs    (expert author w/ documented credentials)
├── 3B: Documented data       (GitHub repos with public data, public datasets)
└── 3C: Conference talks       (recorded + slide deck accessible)

❌ NEVER cite:
- AI-generated content
- Untraceable studies ("a recent study found...")
- Aggregator URLs without primary source
- Forum posts (Reddit/Quora) as fact source — only as anecdote
- Wikipedia as PRIMARY source (use as cross-reference; cite the underlying source)
- Grounding-redirect URLs (Google AI cache)
```

## Tier 1A — Academic + Government

### Peer-reviewed journals (via DOI)
- `doi.org/10.*` — any DOI
- `pubmed.ncbi.nlm.nih.gov/*`
- `arxiv.org/abs/*` — pre-prints (note: not peer-reviewed yet, but academically rigorous)
- `nature.com/articles/*`
- `science.org/doi/*`
- `nejm.org/doi/*` — New England Journal of Medicine
- `thelancet.com/journals/*`
- `bmj.com/content/*` — British Medical Journal
- `jamanetwork.com/journals/*` — JAMA
- `cochranelibrary.com/*`

### Educational institutions
- `*.edu/*` — any US university
- `*.ac.uk/*` — UK universities
- `harvard.edu`, `stanford.edu`, `mit.edu`, `princeton.edu`, `yale.edu`, `caltech.edu`, `columbia.edu`, `berkeley.edu`, `oxford.ac.uk`, `cam.ac.uk`, `ethz.ch`

### Government domains
- `*.gov/*` — US federal + state
- `*.gov.uk/*` — UK government
- `*.gc.ca/*` — Canada
- `*.gouv.fr/*` — France
- `*.bund.de/*` — Germany
- `gov.au/*` — Australia
- `*.govt.nz/*` — New Zealand

## Tier 1B — Top-tier news (English)

### Global English
- `nytimes.com/*` — New York Times
- `wsj.com/*` — Wall Street Journal
- `ft.com/*` — Financial Times
- `bloomberg.com/news/*`
- `reuters.com/*`
- `apnews.com/*` — Associated Press
- `bbc.com/*` / `bbc.co.uk/*` — British Broadcasting Corp
- `theguardian.com/*`
- `economist.com/*`
- `npr.org/*` — National Public Radio
- `washingtonpost.com/*`
- `theatlantic.com/*`
- `newyorker.com/*` — magazine
- `aljazeera.com/*`
- `cbsnews.com/*` / `nbcnews.com/*` / `abcnews.go.com/*`

### Non-English top news
- `spiegel.de/*` — Der Spiegel (German)
- `zeit.de/*` — Die Zeit (German)
- `lemonde.fr/*` — Le Monde (French)
- `liberation.fr/*` — Libération (French)
- `elpais.com/*` — El País (Spanish)
- `corriere.it/*` — Corriere della Sera (Italian)
- `asahi.com/*` — Asahi Shimbun (Japanese)
- `nhk.or.jp/*` — NHK (Japanese)
- `joins.com/*` — JoongAng (Korean)
- `xinhuanet.com/*` — Xinhua (Chinese state — context-dependent reliability)
- `scmp.com/*` — South China Morning Post

## Tier 1C — Government statistical agencies

- `bls.gov/*` — US Bureau of Labor Statistics
- `census.gov/*` — US Census
- `federalreserve.gov/*` — US Fed
- `bea.gov/*` — US Bureau of Economic Analysis
- `cdc.gov/*` — US Centers for Disease Control
- `nih.gov/*` — US National Institutes of Health
- `fda.gov/*` — US Food and Drug Administration
- `ons.gov.uk/*` — UK Office for National Statistics
- `ec.europa.eu/eurostat/*` — Eurostat
- `worldbank.org/*` — World Bank data
- `imf.org/data/*` — IMF data portal
- `oecd.org/*` — OECD
- `who.int/*` — World Health Organization
- `un.org/data/*` — UN data

## Tier 1D — Major research institutes

- `pewresearch.org/*` — Pew Research Center
- `gartner.com/*` (research reports)
- `forrester.com/*` (research reports)
- `mckinsey.com/featured-insights/*` (McKinsey Insights)
- `nielsen.com/insights/*` — Nielsen
- `gallup.com/*` — Gallup polls
- `hbr.org/*` — Harvard Business Review
- `sloanreview.mit.edu/*` — MIT Sloan
- `kellogginsight.com/*` — Northwestern Kellogg
- `weforum.org/agenda/*` — World Economic Forum

## Tier 2A — Industry publications (per vertical)

### SEO / Marketing
- `searchengineland.com/*`
- `searchenginejournal.com/*`
- `moz.com/blog/*`
- `ahrefs.com/blog/*`
- `semrush.com/blog/*`
- `marketingprofs.com/*`
- `contentmarketinginstitute.com/*`
- `hubspot.com/marketing-statistics/*`
- `wordstream.com/blog/*`

### Tech / Engineering
- `techcrunch.com/*`
- `theverge.com/*`
- `arstechnica.com/*`
- `wired.com/*`
- `technologyreview.com/*` — MIT Tech Review
- `venturebeat.com/*`
- `protocol.com/*`
- `theinformation.com/*`
- `stratechery.com/*` — Ben Thompson

### Developer / Engineering blogs
- `engineering.fb.com/*` — Meta engineering
- `netflixtechblog.com/*` — Netflix tech
- `eng.uber.com/*` — Uber engineering
- `aws.amazon.com/blogs/*` — AWS official
- `cloud.google.com/blog/*` — GCP
- `azure.microsoft.com/en-us/blog/*`
- `martinfowler.com/*` — Martin Fowler
- `dev.to/*` (caveat: community-driven; check author credentials)

### Finance
- `marketwatch.com/*`
- `cnbc.com/*`
- `barrons.com/*`
- `morningstar.com/*`
- `seekingalpha.com/*` (caveat: opinion-heavy)

### Health (high E-E-A-T required)
- `mayoclinic.org/*`
- `clevelandclinic.org/*`
- `webmd.com/*` (Tier 2 — caveat: ads + general guidance not always primary source)
- `healthline.com/*` (Tier 2 caveat — quality varies)
- `medlineplus.gov/*` (Tier 1C actually — NIH-affiliated)

### E-commerce / SaaS
- `shopify.com/research/*` — Shopify Research
- `bigcommerce.com/blog/*`
- `stripe.com/*` (resources / atlas)
- `statista.com/*` (Tier 2 caveat — secondary aggregator; original source preferred)

### Industry-specific (sampling)
- Real estate: `nar.realtor/*` (National Association of Realtors)
- Automotive: `kbb.com/*`, `edmunds.com/*`
- Travel: `nomadlist.com/*`, `expedia.com/research`
- Education: `edsurge.com/*`, `chronicle.com/*`

## Tier 2B — Social platform experts

### Recognition criteria
Tier 2B sources are recognized when:
1. Verified status (X blue check, LinkedIn verified badge)
2. Author has documented credentials (job title at known org, published author, professor)
3. URL is from one of these platforms with stable canonical:

### Acceptable URL patterns
- `twitter.com/{handle}/status/{id}` or `x.com/{handle}/status/{id}` — direct post URL
- `linkedin.com/posts/{handle}_*` — direct LinkedIn post
- `linkedin.com/pulse/*` — LinkedIn published articles
- `{handle}.substack.com/p/*` — Substack publications
- `medium.com/@{handle}/{slug}` — Medium (older platform, used by some pros)
- `bsky.app/profile/{handle}/post/{id}` — Bluesky

### What "verified expert" means
NOT just blue-checked. Must have:
- Documented credential (CEO of X, professor at Y, author of Z)
- Public LinkedIn confirming
- ≥10K relevant followers OR ≥5 years of consistent industry posting
- Cited by Tier 1A/B sources at least once

### Examples (per vertical)
- **SEO**: @glenngabe, @brodieclark, @lilyraynyc (Tier 2B)
- **Marketing**: @brittanymullerand, @ahrefs official
- **Tech**: @paulg (Y Combinator), @dhh (Basecamp)
- **AI/ML**: @karpathy, @AnthropicAI, @OpenAIDevs

### Verification process
Before citing as Tier 2B, fact-checker MUST:
1. Confirm verified badge in current state (not just historical)
2. Cross-reference with the person's LinkedIn / company page
3. Document credentials in citations.json

## Tier 2C — Company-published research with methodology

### Acceptable
- HubSpot State of Marketing (annual, with methodology section)
- Salesforce State of [X] reports
- Stripe Atlas / Index
- Cloudflare Radar
- Shopify Commerce reports
- LinkedIn Workforce reports
- Adobe Digital Trends
- Atlassian State of Teams

### Requirements for company research to count
- Methodology section disclosed
- Sample size mentioned
- Date range explicit
- Publisher's name + URL stable

## Tier 3A — Credentialed blogs

Use sparingly. Acceptable when:
- Author has documented professional credentials
- Blog has been active ≥2 years
- Cited by Tier 1 or Tier 2 sources at least once
- Specific claim being cited is non-controversial

Examples:
- `tomwarren.co.uk` (Verge editor's personal blog)
- `kalzumeus.com` (Patrick McKenzie — fintech)
- `randsinrepose.com` (Rands — engineering leadership)

## Tier 3B — Documented data sources

- `github.com/*/*` — public repositories (use as primary if it's the dataset)
- `data.world/*` — open data platform
- `kaggle.com/datasets/*` — public datasets
- `data.gov/*` — government open data
- `openpolicedata.org/*`

## Tier 3C — Conference / talk

Acceptable when:
- Slide deck publicly accessible
- Video recording exists (YouTube / Vimeo / conference site)
- Speaker has documented credentials

## What we will NEVER cite

```
NEVER (causes T04 / C01 veto)
├── AI-generated content (ChatGPT outputs, GPT-* citations)
├── Untraceable "a recent study found..."
├── grounding-redirect URLs (vertexaisearch.cloud.google.com/...)
├── URL shorteners without resolution (bit.ly, t.co)
├── Reddit / Quora as fact source (only as anecdote evidence)
├── Wikipedia as primary (cite Wikipedia's source instead)
├── Aggregator domains (medium.com curators, fast-fashion content farms)
├── Fake authority impersonators
├── Competitor / peer ("同行") domains (causes COMP01 hard veto) ← per-project
│     blocklist in business-context.json :: citation_source_policy.do_not_cite_domains.
│     Direct competitors only — suppliers (Samsung, Mean Well) + standards bodies
│     (DLC, ICNIRP) stay citable. No datasheet exception. Brand NAMES in prose OK;
│     only citing/linking the domain is forbidden. See root CLAUDE.md Rule 8.
└── Pay-to-play "research reports" without methodology
```

## Tier scoring in evidence_density_check.py

```python
# Each Tier-1 source: 10 points toward "Tier-1 source min" rule
# Each Tier-2 source: 6 points (counts toward "≥2 total" Tier-2 requirement)
# Each Tier-3 source: 3 points
# Default min Tier-1: 1, but YMYL = 3
# Default min Tier-1+Tier-2 combined: 2, YMYL = 5
```

## How fact-checker uses this catalog

```
For each [claim:cN_S] in draft:
  1. Crossref lookup → DOI → Tier 1A
  2. Tavily search → categorize by domain → Tier 1B/2A/etc.
  3. HEAD check via link_resolver
  4. Tag the source with tier in citations.json
  5. Cross-reference: ≥1 independent corroborating source (different domain)
  6. Time-sensitivity: per-topic threshold (see source-freshness-rules.md)
```

## Per-vertical Tier-1 preference order

| Vertical | Preferred Tier 1 |
|---|---|
| SEO / Marketing | 2A (industry pubs) → 1D (Pew/Gartner) → 1B (top news) |
| Health / Medical | 1A (peer-reviewed) → 1C (CDC/NIH/WHO) → 2A (Mayo Clinic) |
| Financial | 1B (Bloomberg/FT) → 1C (Fed/Treasury) → 1D (Pew) |
| Tech / Engineering | 1A (academic) → 2A (Verge/TechCrunch) → 2B (verified experts) → 1D (Gartner) |
| Government / Civic | 1C (statistical agencies) → 1A (academic) → 1B (NYT/WP) |
| Legal | 1C (.gov bills, court docs) → 1A (academic) → 1B (Reuters Legal) |
| Education | 1A (academic) → 1C (NCES/DoE) → 1D (Kellogg/HBS) |

## Update cadence

This catalog should be updated:
- **Annually**: review which sources joined/left major publication status
- **When platform changes**: e.g., X removed blue check in 2023, need to update verification approach
- **When new authoritative pubs emerge**: e.g., Stratechery in 2014, The Information in 2013

## See also

- `references/seo/evidence-density-requirements.md` — the 4 evidence rules
- `references/seo/source-freshness-rules.md` — time-sensitivity rules
- `scripts/lint/evidence_density_check.py` — automated check
- `scripts/validate/cross_reference_check.py` — second-pass verification
- `agents/fact-checker.md` — uses this catalog during verification
