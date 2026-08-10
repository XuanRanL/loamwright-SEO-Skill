# Locale: Mainland China (zh-CN, Simplified Chinese)

China mainland market. **Simplified Chinese (简体中文)**. Different from Taiwan/HK.

## Quick reference

| Dimension | Setting |
|---|---|
| Currency | CNY `¥` (`¥1,234.56`) or `人民币` |
| Date format | `2026年5月19日` or `2026-05-19` (ISO preferred in formal) |
| Distance | km, m (metric only) |
| Weight | kg, g (metric only) |
| Temperature | °C |
| Punctuation | Full-width (，。！？；：「」) |
| Word count | ~50% shorter than English (Chinese is very dense) |

## Language notes

- **Simplified characters (简体)**: 国 not 國; 学 not 學; 龙 not 龍. Used in mainland China.
- **Full-width punctuation**: ，（NOT ,） 。（NOT .） ！？「」 in body text.
- **Half-width in code/URLs**: keep half-width Latin punctuation in `code blocks`.
- **No spaces between characters**: Chinese is written without word spacing.
- **Numbers**: 阿拉伯数字 (1, 2, 3) for most content; 中文数字 (一, 二, 三) for formal/literary.
- **English mixed**: technical content often mixes English (e.g., AI, API, SEO).

## Market characteristics

- Largest internet user base globally (~1B+)
- Different ecosystem: Baidu (search), Weibo (microblog), WeChat (super-app), Douyin (TikTok parent)
- **Google blocked** in mainland China; SEO targets Baidu primarily
- Mobile-first absolute (~85% traffic)
- E-commerce + livestream commerce massive

## CRITICAL: Different search ecosystem

If targeting mainland China:
- **Baidu SEO** is the primary game (different from Google)
- **WeChat search** important for organic
- **Toutiao + Douyin** for content discovery
- Sites hosted outside China = slow / blocked → consider China-hosting + ICP license
- Google Search Console / Bing Webmaster do NOT apply

This plugin's GSC + Bing integrations don't help in China. Use Baidu Search Resource Platform instead.

## Cultural references

- Holidays: Spring Festival (春节, Jan/Feb), National Day Golden Week (Oct 1-7), Mid-Autumn (中秋)
- WeChat ecosystem central to daily life
- Mobile payment ubiquitous (Alipay 支付宝, WeChat Pay 微信支付)
- Generational tensions (post-90s vs post-2000s consumption patterns)

## Regulatory + compliance

- CAC — Cyberspace Administration of China (data + content)
- SAMR — State Administration for Market Regulation (advertising)
- NMPA — health + medical
- CSRC — financial markets
- PIPL — Personal Information Protection Law (China's GDPR equivalent)

**Critical**: content review BEFORE publish. Politically sensitive topics blocked. Foreign companies need ICP license for hosting.

**Affiliate disclosure**: "*本文包含联盟链接。如果您通过这些链接购买，我们将获得佣金，但不会增加您的额外费用。*"

## YMYL caution

- Health: NMPA approval needed for medical claims; supplement claims restricted
- Financial: CSRC requires disclaimers + licensing for advice
- Legal: 律师 (lvshi, licensed lawyers) only

## Content length norms

Chinese is extremely dense:

| Content type | English (words) | Chinese (characters 字) |
|---|---|---|
| News-analysis | 1,000w | 1,500-2,000 字 |
| How-to guide | 2,500w | 3,500-5,000 字 |
| Listicle | 5,000w | 7,000-10,000 字 |
| Pillar page | 6,000w | 9,000-12,000 字 |

## Tone calibration

- Formal default for B2B
- Younger audiences (Gen Z): more casual + internet slang
- "您" (formal you) vs "你" (informal you)
- Avoid politically sensitive metaphors
- Number-heavy content (Chinese culture loves data)

## Distinctive features

- **Censorship/politeness**: certain topics restricted (政治, religion, etc.)
- **Numerology**: 8 lucky (发 prosperity), 4 unlucky (死 death)
- **Color symbolism**: red = lucky, white = mourning, gold = wealth
- **Generational slang**: changes rapidly; check current usage
- **Pinyin**: tone marks dropped in casual writing; included in dictionaries

## Time zones

- CST (UTC+8) — China Standard Time, year-round; no DST
- Covers all China (no provincial variants despite size)

Publish at 9 AM CST.

## See also
- `references/localization/tw.md` — Traditional Chinese variant
- `references/localization/hk.md` — Cantonese / Traditional
- `references/localization/sg.md` — Mandarin sibling with English mix
- Note: China-targeted content needs Baidu SEO + ICP hosting
