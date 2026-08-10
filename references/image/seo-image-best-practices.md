# Image SEO Best Practices (2026)

## Filename
- ✅ Kebab-case: `best-fishing-rods-2026-cover.webp`
- ✅ Contains primary keyword (or close variant)
- ✅ ≤80 chars total
- ❌ Avoid: `IMG_8341.jpg`, `image-1.png`, generic names
- ❌ Avoid: spaces, underscores, special characters

## Alt text
- ✅ Descriptive (what's IN the image, not just what it represents)
- ✅ 60-125 characters (sweet spot)
- ✅ Contains primary keyword naturally (when image relates)
- ✅ One alt per visible image (no duplicates across srcset variants)
- ❌ Don't keyword-stuff
- ❌ Don't start with "Image of..." or "Picture showing..."
- ❌ Don't use alt="" for content images (only for decorative)

Example:
- ❌ Bad: `alt="image"`
- ❌ Bad: `alt="best fishing rods 2026 best fishing rods best 2026"`
- ✅ Good: `alt="Angler casting G.Loomis NRX+ rod at sunset on the Deschutes River"`

## File format
- ✅ Prefer WebP (better compression than JPEG)
- ✅ Keep PNG fallback if alpha needed
- ❌ Avoid GIF for photos (use WebP animated or MP4)
- ❌ Avoid TIFF / BMP for web

## File size
- ✅ Target <200 KB per variant
- ✅ <100 KB for srcset 480w variants
- ❌ Avoid >500 KB photos (mobile data killer)

## Dimensions
- ✅ Cover: 16:9 (1536×1024 or 1792×1024)
- ✅ Section images: 4:3 (1024×768) or 1:1 (1024×1024)
- ✅ Pinterest-friendly cover: 2:3 (1200×1800) for Pinterest-targeted posts

## Srcset (responsive)
Always generate at least 3 widths:
- Section images: 480w / 768w / 1024w
- Cover images: 480w / 1024w / 1536w

```html
<img src="best-rods-cover-1024w.webp"
     srcset="best-rods-cover-480w.webp 480w,
             best-rods-cover-1024w.webp 1024w,
             best-rods-cover-1536w.webp 1536w"
     sizes="(max-width: 768px) 100vw, 1024px"
     alt="Angler at sunset"
     loading="lazy" />
```

## Lazy loading
- ✅ All below-the-fold images: `loading="lazy"`
- ✅ Above-the-fold cover: `loading="eager"` (default; don't add lazy)
- ✅ Use `decoding="async"` for non-critical images

## EXIF / metadata
- ✅ Strip EXIF (GPS data, camera info) for privacy
- ✅ Keep only what's needed (e.g., copyright)
- ❌ Don't expose user-uploaded photo locations

## Schema (JSON-LD)
Every cover image should have ImageObject schema:

```json
{
  "@type": "ImageObject",
  "@id": "https://example.com/article#cover",
  "url": "https://cdn.example.com/best-rods-cover.webp",
  "contentUrl": "https://cdn.example.com/best-rods-cover.webp",
  "width": 1536,
  "height": 1024,
  "caption": "Article cover image",
  "creator": { "@id": "https://example.com/#organization" }
}
```

## Image sitemap
- Add image sitemap or include images in main sitemap
- Helps Google discover and index images
- Use `<image:image>` markup

## CDN
- ✅ Serve images via CDN (Cloudflare / Fastly / Cloudinary)
- ✅ Use HTTP/2 or HTTP/3 for multiplexing
- ✅ Set proper cache headers (1 year for images)

## Generative AI images
- ✅ Disclose AI-generated images if material to the content
- ✅ For product images, prefer real photos when possible (Google Vision can detect AI)
- ✅ Avoid AI images for case studies / reviews (E-E-A-T weakness)
- ⚠️ Acceptable for: conceptual / illustration / decorative / cover art
