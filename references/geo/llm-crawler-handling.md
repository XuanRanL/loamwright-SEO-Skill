# LLM Crawler Handling

How to handle GPTBot / ClaudeBot / PerplexityBot / GoogleOther / Bingbot via robots.txt + meta robots + Cloudflare rules.

The big trade-off: **allow LLM crawlers** = future AI citations; **block them** = your content doesn't train AI models. Most brands want the former.

## The major LLM crawlers (2026)

| Crawler | User-Agent | Used by | Default policy |
|---|---|---|---|
| `GPTBot` | `Mozilla/5.0 ... GPTBot/1.x` | OpenAI training | **Allow** |
| `OAI-SearchBot` | `Mozilla/5.0 ... OAI-SearchBot/1.x` | OpenAI search results | **Allow** |
| `ChatGPT-User` | `Mozilla/5.0 ... ChatGPT-User/1.x` | Live ChatGPT browse | **Allow** |
| `ClaudeBot` | `Mozilla/5.0 ... ClaudeBot/1.x` | Anthropic training | **Allow** |
| `claude-web` | `Mozilla/5.0 ... claude-web/1.x` | Claude search | **Allow** |
| `Claude-User` | `Mozilla/5.0 ... Claude-User/1.x` | Live Claude browse | **Allow** |
| `PerplexityBot` | `Mozilla/5.0 ... PerplexityBot/1.x` | Perplexity index | **Allow** |
| `Perplexity-User` | `Mozilla/5.0 ... Perplexity-User/1.x` | Live Perplexity | **Allow** |
| `GoogleOther` | `Mozilla/5.0 ... GoogleOther` | Google AI training | **Allow** |
| `Google-Extended` | `Mozilla/5.0 ... Google-Extended` | Bard/Gemini training | **Allow** |
| `Bingbot` | `Mozilla/5.0 ... bingbot/2.0` | Bing + ChatGPT-via-Bing | **Allow** |
| `Bytespider` | `Mozilla/5.0 ... Bytespider` | ByteDance / Doubao | **Conditional** |
| `Diffbot` | `Mozilla/5.0 ... Diffbot/1.x` | Knowledge graph scraping | **Allow** |

## Standard robots.txt for AI-friendly sites

```
# robots.txt — allow all major LLM crawlers
User-agent: *
Allow: /

# Explicit allows for transparency
User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: GoogleOther
Allow: /

# Block aggressive scrapers
User-agent: Bytespider
Disallow: /

User-agent: CCBot
Disallow: /
# (Common Crawl — old + bandwidth heavy; if you allow others, you don't need to allow CCBot)

# Standard exclusions
Disallow: /admin/
Disallow: /wp-admin/
Disallow: /wp-login.php
Disallow: /search?
Disallow: /?s=
Disallow: /tag/
# (Tags can be no-index'd via meta robots instead)

# Sitemaps
Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/sitemap-news.xml
```

## Per-page meta robots

For pages you want indexed by Google + AI but NOT trained on:

```html
<meta name="robots" content="index, follow, noai, noimageai">
```

For Anthropic-specific opt-out:
```html
<meta name="robots" content="index, follow">
<meta name="ClaudeBot" content="noindex">
```

For OpenAI-specific opt-out:
```html
<meta name="GPTBot" content="noindex">
```

## When to BLOCK LLM crawlers

Block if:
- Content is paid (Substack premium, paywall)
- Content is copyrighted by 3rd party (e.g., licensed images you don't own)
- Brand explicitly opts out of AI training
- Legal compliance (e.g., EU GDPR for personal data)

For SEO blogs that want AI citations: **don't block**. Citations require training data.

## Rate limiting (Cloudflare / WAF)

Even when allowing LLM crawlers, rate-limit them to avoid bandwidth issues:

```
Cloudflare rule:
  IF request.user_agent contains "GPTBot" OR "ClaudeBot" OR "PerplexityBot"
  THEN rate_limit = 5 requests/second per IP
       AND log to analytics
```

GPTBot reasonable limits (per OpenAI docs): 1-2 requests/second per IP.

## Cloudflare AI bot management

Cloudflare offers an "AI Scrapers" toggle in their dashboard:
- "Block all known AI bots" (one-click)
- Or selectively allow specific ones

For our SEO blogs: **disable the global block**; allow individually.

## Headless browser detection nuance

Sometimes LLM crawlers use headless Playwright/Chromium (not the documented User-Agent). Detection signals:
- No `Accept-Language` header
- `navigator.webdriver = true` (in JS)
- Missing `Sec-Fetch-*` headers

For SEO sites: don't try to detect/block. False positives kill real users.

## Schema markup for AI consumption

Make sure your schema.org JSON-LD is in HTML (not lazy-loaded JS) so crawlers see it on first GET:

```html
<head>
  <script type="application/ld+json">
    { "@context": "https://schema.org", "@graph": [...] }
  </script>
</head>
```

If schema is injected via JS after page load, crawlers may miss it.

## How to verify your robots.txt is working

```bash
# Check what GPTBot sees
curl -A "Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)" \
     https://example.com/robots.txt

# Check what Google sees (combination of multiple bots)
curl -A "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" \
     https://example.com/blog/post-1
```

## Monitoring crawler activity

Log User-Agent in server logs. Analyze monthly:

| Crawler | Expected req/day for blog with 100 posts |
|---|---|
| Googlebot | 200-2,000 |
| Bingbot | 100-1,000 |
| GPTBot | 50-500 |
| ClaudeBot | 30-300 |
| PerplexityBot | 30-300 |
| Google-Extended | 50-500 |

If you see 100,000+ requests/day from one crawler → potentially abusive; consider rate-limiting.

## Per-project default

In `projects/{slug}/research/business-context.md`, default crawler policy:

```yaml
crawler_policy:
  ai_crawlers: "allow"      # allow | block | conditional
  rate_limit_rps: 2
  block_aggressive: true     # block Bytespider, CCBot
  allow_training: true       # affects noai/noimageai meta
```

## See also

- `references/geo/ai-engine-matrix.md` — per-engine optimization
- `references/geo/ai-citation-patterns.md` — what AI engines look for
- `subskills/optimize/geo-content-optimizer/SKILL.md`
