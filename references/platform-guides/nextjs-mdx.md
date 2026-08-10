# Platform Guide: Next.js + MDX

For headless / JAMstack sites using Next.js (App Router or Pages Router) with MDX-based content. Alternative to WordPress for technical brands.

## Compatibility

| Component | Version |
|---|---|
| Next.js | 14.0+ (App Router); 13.5+ (Pages Router) |
| MDX | 3.0+ |
| Contentlayer (optional) | 0.3+ |
| Markdoc / Notion (alternative) | latest |

## Publish flow (vs WordPress)

Instead of REST API POST, Next.js publish = **git commit + push**:

```
Step 1: markdown → MDX (with frontmatter)
        - Add JSX components if needed (e.g., <CalloutBox>, <Chart>)
        - Compile schema JSON-LD as <Head> child

Step 2: Write to file system
        projects/{slug}/articles/{article-slug}/final.mdx →
        clone-of-blog-repo/content/posts/{article-slug}.mdx

Step 3: Add images to public/ folder
        clone-of-blog-repo/public/images/{article-slug}/

Step 4: git add + commit + push
        - Triggers Vercel/Netlify deploy
        - ISR (Incremental Static Regeneration) refreshes

Step 5: Ping indexers after deploy succeeds
        (Wait for Vercel webhook → confirmation, then submit to IndexNow)
```

## MDX frontmatter schema

We generate:

```yaml
---
title: "Best Fishing Rods 2026: 7 Tested Picks"
slug: "best-fishing-rods-2026"
description: "Tested 23 rods across 87 trips..."
date: "2026-05-19T10:00:00Z"
lastUpdated: "2026-05-19T10:00:00Z"
author: "Jane Smith"
authorUrl: "/authors/jane-smith"
authorImage: "/images/authors/jane-smith.jpg"
category: "fishing-gear"
tags: ["fishing rods", "saltwater", "G.Loomis", "review-2026"]
coverImage: "/images/best-fishing-rods-2026/cover.webp"
coverImageAlt: "Angler casting G.Loomis NRX+ rod"
ogImage: "/images/best-fishing-rods-2026/cover.webp"
canonical: "https://example.com/blog/best-fishing-rods-2026"
schema: |
  {
    "@context": "https://schema.org",
    "@graph": [
      { "@type": "BlogPosting", ... },
      { "@type": "Person", ... }
    ]
  }
draft: false
---
```

## Schema injection (Next.js App Router pattern)

```tsx
// app/blog/[slug]/page.tsx
import Head from "next/head";

export default function Post({ post }) {
  return (
    <>
      <Head>
        <title>{post.title}</title>
        <meta name="description" content={post.description} />
        <link rel="canonical" href={post.canonical} />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: post.schema }}
        />
      </Head>
      <Article post={post} />
    </>
  );
}
```

## Schema injection (Pages Router pattern)

```tsx
// pages/blog/[slug].tsx
import Head from "next/head";

export default function Post({ post }) {
  return (
    <>
      <Head>...</Head>
      ...
    </>
  );
}
```

## Image optimization

Next.js has built-in `<Image>` component. We pre-process to WebP via `webp_converter.py` then use:

```tsx
import Image from "next/image";

<Image
  src={post.coverImage}
  alt={post.coverImageAlt}
  width={1200}
  height={630}
  priority
/>
```

For inline images in MDX, use the `<NextImage>` shortcut:

```mdx
<NextImage src="/images/section-1.webp" alt="..." width={1024} height={768} />
```

## MDX components for SEO

Custom components our markdown_to_html maps:

| MDX component | HTML output |
|---|---|
| `<Callout type="note">` | `<aside class="callout-note">` |
| `<CitationCapsule>` | `<div class="citation-capsule">` (40-60w block) |
| `<Chart data={...} />` | Inline `<svg>` |
| `<FAQ items={[...]} />` | `<section class="faq">` + FAQPage schema |
| `<Author />` | Person schema + bio block |

## Deployment + invalidation

For Vercel:
- Push to main branch → automatic deploy
- ISR refreshes pages on next request after `revalidate` interval
- For instant invalidation: `await res.revalidate('/blog/' + slug)`

For Netlify:
- Git push → build → deploy
- No ISR (full static rebuild)
- Use webhooks for partial invalidation

## Robots.txt

Place in `public/robots.txt`:

```
User-agent: *
Allow: /

User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

Sitemap: https://example.com/sitemap.xml
```

## Sitemap

Next.js 14+ supports `app/sitemap.ts`:

```ts
import type { MetadataRoute } from "next";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const posts = await getAllPosts();
  return posts.map(post => ({
    url: `https://example.com/blog/${post.slug}`,
    lastModified: post.lastUpdated,
    changeFrequency: "monthly",
    priority: 0.8,
  }));
}
```

## RSS / JSON Feed

For AI engines that consume feeds:

```ts
// app/feed.xml/route.ts
import { Feed } from "feed";
export async function GET() {
  const feed = new Feed({
    title: "Example Blog",
    description: "...",
    id: "https://example.com",
    link: "https://example.com",
  });
  for (const post of await getAllPosts()) {
    feed.addItem({
      title: post.title,
      id: `https://example.com/blog/${post.slug}`,
      link: `https://example.com/blog/${post.slug}`,
      date: new Date(post.date),
      description: post.description,
    });
  }
  return new Response(feed.rss2(), {
    headers: { "Content-Type": "application/xml" },
  });
}
```

## When to use Next.js vs WordPress

| Use Next.js if | Use WordPress if |
|---|---|
| Site has custom interactivity | Site is mostly content |
| Brand has dev team | Brand has content team |
| Performance is critical (Core Web Vitals) | Yoast / Rank Math features needed |
| Vercel / Netlify infrastructure | Managed WP hosting (WPEngine) |
| MDX components for unique layouts | Standard blog post structure |
| Git-based content workflow | WYSIWYG editor preferred |

## Limitations vs WordPress

- No native draft preview (need staging deploy)
- No native comments (use Disqus/Hyvor/etc.)
- No native author profiles (build custom)
- No native categories/tags UI (use frontmatter)
- No live preview before publish (use Vercel preview deploys)

## Cross-publishing

Some sites publish to BOTH (WP as primary, Next.js as canonical):
- WP is editorial UX
- Next.js mirrors via webhook → REST pull → static rebuild

Our `wp_publisher.py` can be extended with a `--also-write-mdx` flag for this.

## See also

- `scripts/build/markdown_to_html.py` — handles markdown → HTML (and MDX-ish)
- `references/platform-guides/wordpress.md` — alternative
- Next.js MDX docs: https://nextjs.org/docs/app/building-your-application/configuring/mdx
