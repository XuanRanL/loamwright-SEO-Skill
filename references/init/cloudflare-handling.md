# Cloudflare Protection · Setup Guide for /init Scraping

If your site (or your client's site) is behind Cloudflare, /init's 5-tier scraper may be blocked. This guide gives you 3 ways to fix it, in order of recommendation.

## Quick decision tree

```
You control the Cloudflare panel?
├── YES → Strategy A: WAF Allow Rule (5 min, free, 100% bypass)
│
└── NO → Do you have authenticated browser access?
    ├── YES → Strategy B: Cookie Injection (5 min, free, breaks every 1-30 days)
    │
    └── NO → Strategy C: Commercial proxy (sign up, $50-300/mo)
```

## Strategy A · WAF Allow Rule (⭐ recommended)

**Best for**: Your own sites + clients who let you configure CF.

**Effect**: 100% bypass, persistent, no IP dependency, no cookie expiry.

### Setup steps (5 min per site)

1. **Generate a secret token** (32-char hex)

   ```bash
   python -c "import secrets; print(secrets.token_hex(16))"
   ```

   Example output: `REPLACE-WITH-YOUR-32-CHAR-HEX-TOKEN`

2. **Save to plugin credentials**

   ```bash
   mkdir -p projects/{site-slug}/credentials
   ```

   Edit `projects/{site-slug}/credentials/cloudflare.json`:
   ```json
   {
     "bypass_token": "REPLACE-WITH-YOUR-32-CHAR-HEX-TOKEN",
     "configured_in_cf": false
   }
   ```

3. **Configure Cloudflare WAF**

   - Log into Cloudflare → select your site
   - Navigate: **Security → WAF → Custom rules**
   - Click **Create rule**
   - Set:
     - Rule name: `Allow xuanran-seo scraper`
     - When incoming requests match:
       - Field: `Header`
       - Header name: `X-Xuanran-SEO-Token`
       - Operator: `equals`
       - Value: `<paste your token>`
     - Then take action: `Skip`
     - With these settings:
       - ✓ All remaining custom rules
       - ✓ Managed Challenge
       - ✓ Super Bot Fight Mode
       - ✓ Bot Fight Mode
       - ✓ Bot Management
       - ✓ Rate limiting rules
   - Click **Deploy**

4. **Test**

   ```bash
   curl -H "X-Xuanran-SEO-Token: REPLACE-WITH-YOUR-32-CHAR-HEX-TOKEN" \
        https://your-site.com/some-page
   ```

   Should return 200 with content.

5. **Mark configured**

   Edit `cloudflare.json`:
   ```json
   {
     "bypass_token": "...",
     "configured_in_cf": true,
     "configured_at": "2026-05-19"
   }
   ```

### Trade-offs of Strategy A

| Pro | Con |
|---|---|
| 100% bypass rate | Need CF admin access to each site |
| Persistent (no expiry) | Token is sensitive (treat like API key) |
| Bypasses ALL CF layers | If token leaks, anyone can scrape |
| 0 ongoing cost | One-time 5-min setup per site |

### Security notes

- **Keep token secret** — anyone with it can bypass your CF protection
- **Rotate annually** — generate new token, update both CF rule + cloudflare.json
- **Per-site tokens** — don't reuse across clients (use different per project)
- **Storage**: cloudflare.json is in `projects/{slug}/credentials/` which is gitignored

## Strategy B · Cookie Injection

**Best for**: Sites you can't admin but where you have authenticated browser access.

**Effect**: Bypass L1-L3 CF challenges (Bot Fight Mode, Super Bot Fight, Managed Challenge), but NOT Bot Management Enterprise.

### Setup steps (5-10 min, recurring)

1. **Open the target site in your browser**

   Use Chrome or Firefox (Chrome example below).

2. **Pass the CF challenge naturally**

   - If there's a "Just a moment..." page, wait it out
   - If there's a Turnstile/CAPTCHA, solve it
   - Browse a couple of pages

3. **Extract cookies**

   **Method 1: DevTools (free, manual)**
   - Press F12
   - **Application → Cookies → https://your-site.com**
   - Find these cookies:
     - `cf_clearance` (the main one; 1-30 day TTL)
     - `__cf_bm` (24-30 minute TTL — shorter; refresh more often)
   - Copy values

   **Method 2: Browser extension (faster)**
   - Install [EditThisCookie](https://chromewebstore.google.com/detail/editthiscookie/) for Chrome
   - Visit your site (after passing challenge)
   - Click extension icon → Export → JSON

4. **Save to plugin**

   Edit `projects/{site-slug}/credentials/cf-cookies.json`:
   ```json
   {
     "cf_clearance": "abc123def456...",
     "__cf_bm": "xyz789...",
     "expires": "2026-06-19",
     "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_0) AppleWebKit/605.1.15 ...",
     "accept_language": "en-US,en;q=0.9",
     "extracted_at": "2026-05-19"
   }
   ```

   **Critical**: also include the User-Agent + Accept-Language from your browser. CF often validates these against the cookie origin.

5. **Test**

   ```bash
   python -m scripts.fetch.cloudflare_bypass \
       --url https://your-site.com \
       --strategy cookies \
       --slug your-site
   ```

6. **Refresh schedule**

   - `__cf_bm` expires in 30 min → re-export weekly minimum
   - `cf_clearance` expires in 1-30 days (varies by CF config) → re-export when failed

### Trade-offs of Strategy B

| Pro | Con |
|---|---|
| Don't need CF admin access | Cookies expire (need re-export) |
| Free | Manual re-extraction every 1-30 days |
| Works for L1-L3 challenges | Doesn't work for Bot Management Enterprise |
| Same as your real browser | Doesn't scale to many sites |

### When NOT to use Strategy B

- Bot Management Enterprise sites (need Strategy C)
- Sites with strict CAPTCHA + JS challenges every visit
- More than ~10 sites (the re-extraction overhead is large)

## Strategy C · Commercial Proxy (ScraperAPI / Bright Data)

**Best for**: Many sites + sites with aggressive Bot Management.

**Effect**: 90%+ bypass rate across all CF layers; rotating residential IPs + JS rendering.

### Setup steps (10-20 min, one-time)

1. **Sign up for ScraperAPI** (recommended starter)

   - https://scraperapi.com
   - Free tier: 1,000 API credits/month (~1000 requests with render+premium)
   - Pricing: $49/mo (100K credits) → $299/mo (3M credits)

   Alternatives:
   - Bright Data (more residential, more expensive)
   - Scrapingbee (simpler API, mid-range)

2. **Get API key**

   - Dashboard → API Keys → copy key

3. **Save to plugin**

   ```bash
   echo "YOUR_API_KEY_HERE" > ~/.xuanran-seo/credentials/scraperapi.key
   chmod 600 ~/.xuanran-seo/credentials/scraperapi.key
   ```

   Or env variable:
   ```bash
   export SCRAPERAPI_KEY=YOUR_API_KEY_HERE
   ```

4. **Test**

   ```bash
   python -m scripts.fetch.cloudflare_bypass \
       --url https://heavily-protected-site.com \
       --strategy commercial
   ```

5. **Use in /init**

   `multi_tier_fetch.py` automatically tries commercial as Tier 2.5 when other tiers fail.

### Trade-offs of Strategy C

| Pro | Con |
|---|---|
| 90%+ bypass success | Costs $50-300/month for serious use |
| Works on Bot Management Enterprise | Slower (~3-5s per request vs 200ms direct) |
| No CF admin needed | Quota limits |
| Rotating residential IPs | Some sites still detect proxies |

### Cost calculator

For 100 sites × 40 pages /init × 1 /article/month × 8 Tavily calls:

- Direct scraping (Tier 1-2): $0
- ScraperAPI fallback for CF sites (~30%): 100 × 40 × 0.30 = 1200 requests/init wave + 8 × 1 × 0.30 × 100 = 240 requests/month for /article
- Total ~1440 ScraperAPI requests/month
- Cost: free tier covers this; if much more → $49/mo plan

## Combined strategy (recommended for production)

For your 100+ site setup:

```yaml
Per-site configuration in projects/{slug}/credentials/cloudflare.json:

# Own sites (full CF control):
{
  "strategy": "header_token",
  "bypass_token": "...",
  "configured_in_cf": true
}

# Client sites with CF cooperation:
{
  "strategy": "header_token",
  "bypass_token": "...",
  "configured_in_cf": true
}

# Client sites without CF cooperation:
{
  "strategy": "cookies",
  "extracted_at": "2026-05-19",
  "expires": "2026-06-19"
}

# Very hard sites (Bot Management):
{
  "strategy": "commercial",
  "tier": "premium"
}
```

## /init integration

When you run `/init https://protected-site.com --site-slug X`:

```
Stage 1: Discovery
  → cloudflare_detector.py detects CF protection
  → strategy from projects/{X}/credentials/cloudflare.json
  → cloudflare_bypass.py applies strategy
  → success → proceed
  → failure → surface clear error

Stage 2: Crawl 40 pages
  → For each URL, retry with bypass strategy
  → Track success rate per page

Output:
  init-report.md lists pages successfully scraped vs blocked
  init-report.md suggests strategy upgrade if needed
```

## Setup wizard integration

Run `/setup-wizard --site-slug X` to get interactive CF setup:

```
Q: Is your-site.com behind Cloudflare?
A: yes
Q: Do you have admin access to Cloudflare?
A: yes
→ Walks through Strategy A setup
Q: Want me to test now?
A: yes
→ Tests the configured bypass
```

## Troubleshooting

### "I configured the WAF rule but it's still blocking"

Check:
1. WAF rule is in **Custom Rules**, not **Page Rules**
2. Rule is **Enabled** (toggle on right)
3. Token in JSON matches token in WAF rule (case-sensitive)
4. No typo in header name: `X-Xuanran-SEO-Token` (capital X, dash, capital X, etc.)
5. Rule order: this rule should be ABOVE any blocking rules

### "Cookies worked yesterday but not today"

Cookies expired. Common TTLs:
- `__cf_bm`: 30 minutes
- `cf_clearance`: 1-30 days (site-configured)

Re-extract from browser.

### "ScraperAPI returns 200 but content looks like CF challenge"

The page is using Bot Management Enterprise + has detection beyond what ScraperAPI's basic plan covers.

Options:
- Upgrade ScraperAPI to premium IPs (`premium: true` in request)
- Try Bright Data (better residential pool)
- Use Strategy A (WAF Allow rule) if you can get CF admin access

### "I have 100 sites — Strategy A is too tedious"

Automation:
1. For all your OWN sites, generate ONE token, use across all
2. Use Cloudflare API to deploy WAF rule programmatically:
   ```bash
   # CF API token with Zone:Read + Zone:Edit
   curl -X POST \
     "https://api.cloudflare.com/client/v4/zones/{zone_id}/firewall/rules" \
     -H "Authorization: Bearer YOUR_CF_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "filter": {"expression": "(http.request.headers[\"x-xuanran-seo-token\"] eq \"<token>\")"},
       "action": "skip",
       "skip": {"... skip everything ...}
     }'
   ```

3. For client sites, ask each client to deploy the rule once

## See also

- `scripts/_core/cloudflare_detector.py` — detect CF protection layer
- `scripts/fetch/cloudflare_bypass.py` — 3-strategy bypass
- `scripts/fetch/multi_tier_fetch.py` — 5-tier waterfall with CF bypass integrated
- `subskills/init/website-project-init/SKILL.md` — /init full flow
