---
name: wordpress-publisher
description: 7-step WordPress publish via scripts/wordpress/wp_publisher.py. Resolves categories/tags + uploads media + creates post + sets Yoast meta + publishes. Returns live URL + change-log entry for 7-day undo. Triggered by /publish OR phase-publish.
allowed-tools: [Read, Write, Bash, Task]
disable-model-invocation: true
---

# WordPress Publisher

Implementation in `scripts/wordpress/wp_publisher.py`. This skill is the entry point.

## Inputs
- `workspace/{task_id}/draft.md` (Stage: optimized)
- `workspace/{task_id}/meta.json`
- `workspace/{task_id}/images/...` (post-processed WebP variants)
- `workspace/{task_id}/quality.json` (MUST be overall_passed=true)
- `workspace/{task_id}/review.json` (Independent reviewer approved)

## Pre-flight gates
```
Halt if any of:
  - quality.overall_passed != true
  - review.score < state.brief.quality_target_score
  - vetoes_triggered non-empty
  - state.repair_iteration >= 4 (exhausted repair)
```

## 7-step (delegate to wp_publisher.py)

```bash
python -m scripts.wordpress.wp_publisher \
    {site_slug} \
    --workspace {task_id} \
    --status publish
```

Internally:
1. Parse draft.md frontmatter + body
2. Resolve categories — **resolve-only, never create** (2026-07-11 root cure). Fast path
   uses `meta.category_ids[]` (pre-resolved by category_selector from the
   categories-live.json snapshot); the name-resolution fallback is HTML-entity-aware
   and runs with `create_missing=False`. An unresolvable category name **aborts the
   publish** before any WP write — the taxonomy is curated at init
   (`scripts.wordpress.setup_categories`), and publish-time creation is how the
   project-hotel `&`-entity duplicate categories were minted (8 top-level dups,
   2026-06-16→20). Deliberate creation requires the explicit
   `--allow-create-categories` CLI flag. To detect/repair duplicates on a live site:
   `python -m scripts.wordpress.dedupe_categories {site_slug} --check|--apply`.
3. Resolve tags (get_or_create_terms — tags stay create-on-the-fly; tag_policy governs indexing)
4. Upload all images to Media Library (multipart) — populates **all 4 media fields**: `title`, `alt_text`, `caption`, `description` (sourced from `workspace/{task}/image_metadata.json`)
5. Replace [IMAGE-SLOT-*] placeholders in body — **excludes images flagged `is_featured: true`** (cover image is rendered by the theme's post_thumbnail automatically; including it inline causes a visible duplicate)
6. **References section** (MANDATORY, not "if missing"):
   a. Detect any existing `## References` / `<h2>References</h2>` / `<h2 id="references">` H2 in the body.
   b. If absent → append APA-7 References block from `workspace/{task}/citations.json` (8-10 entries, all link-resolvable, mix of peer-reviewed / industry-standard / vendor-datasheet as actually cited in body).
   c. If present but contains <3 `<li>` entries → augment to ≥3 from citations.json (the existing "Further Reading" paragraph does NOT satisfy this check — must be a proper `<ol>` under an H2).
   d. Append `<hr />` + article signature paragraph (`<p class="article-signature">` with last-reviewed date + author + project-specific CTA per `projects/{slug}/CLAUDE.md`).
   e. Order: any `## Further Reading` (if present) must come BEFORE `## References`. Article signature comes LAST. Schema `<script type="application/ld+json">` blocks go OUTSIDE the CSS wrapper close, AFTER signature.
7. markdown_to_html → HTML
8. Wrap each `<img>` in `<figure class="wp-block-image"><figcaption class="wp-element-caption">…</figcaption></figure>` so captions render visibly — sourced from image metadata
9. **Apply project styling**: read `projects/{slug}/brand/article-css.min.css` (or `article-css.css`) and inject as inline `<style>`; wrap body in the project wrapper (`_apply_project_styling` resolves the PUBLISHED name via `scripts/_core/style_tokens.py` — tokenized projects do NOT ship `{slug}-pillar`); wrap the whole content in a single `<!-- wp:html -->` block so WordPress preserves HTML verbatim (`<p>` tags, `<style>`, `<figure>` all survive)
10. POST /wp/v2/posts (`status: "draft"` — DEFAULT per HARD RULE 5a in root CLAUDE.md) → set featured_media → set Yoast/RankMath meta
11. Return post_id + preview URL to caller. Do NOT auto-flip to publish.
12. Publish-flip is a SEPARATE call by the orchestrator AFTER explicit user confirmation OR pre-authorized policy (`business-context.json :: publish_policy.default`). The flip itself is: `PATCH /wp/v2/posts/{id} {"status": "publish"}`. Caller invokes step 12 only after confirmation; this script's `publish()` function flips automatically only when `PublishInput.status == "publish"` (which is no longer the default).

## Auto-behaviors that are now durable (no caller action required)

- **internal-links-map refresh (v3.41.0):** after every successful publish flow,
  `wp_publisher.py` calls `scripts/wordpress/sync_links_map.py` to regenerate the
  `## Published articles` section of `projects/{slug}/internal-links-map.md` from the
  live WP REST inventory (status=publish only — a draft-create is a no-op refresh).
  Best-effort: a sync failure warns and never fails the publish. Standalone backfill:
  `python -m scripts.wordpress.sync_links_map {slug}`.

These behaviors run automatically inside `wp_publisher.py:publish()` and apply to every project:

| Behavior | Source data | What it does |
|---|---|---|
| **No cover-in-body** | `images[].is_featured: true` | Filters out featured images from body placeholder substitution (defense-in-depth on top of image-slot-allocator marking cover `body_render: false`) |
| **4-field media metadata** | `images[].alt`, `.caption`, `.title`, `.description` | All four fields posted to `/wp/v2/media` on upload |
| **Figure + figcaption wrap** | image metadata `caption` field | Bare `<img>` tags get wrapped in Gutenberg `<!-- wp:image -->` blocks with `<figcaption>` so captions display under each image |
| **References block (mandatory)** | `workspace/{task}/citations.json` | Always-runs: ensures an `<h2>References</h2>` + `<ol>` with ≥3 link-resolvable entries exists. Inline-paragraph citations ("Further Reading" prose blocks) do NOT satisfy this. Override only if `projects/{slug}/CLAUDE.md` sets `references_required: false`. |
| **Article signature** | `projects/{slug}/CLAUDE.md` author + CTA | Always-runs: appends `<hr />` + `<p class="article-signature">` paragraph as the final body element (before the JSON-LD scripts that sit outside the CSS wrapper) |
| **Project article CSS injection** | `projects/{slug}/brand/article-css.min.css` | Inline `<style>` prepended to post body; body wrapped in the project wrapper, style-token-resolved at the publish boundary |
| **Verbatim HTML preservation** | wp:html block markers | Whole content wrapped in `<!-- wp:html -->...<!-- /wp:html -->` so WordPress does NOT strip `<p>` tags via classic-content sanitization |

## Failure handling
- Media upload fails → rollback all media (delete uploaded)
- Post creation fails → rollback media
- Yoast set fails → log warning, continue (post still created)
- Publish PATCH fails → leave as draft, alert user
- `article-css.css` missing → still wrap body in `<div class="{slug}-pillar">` (no style block), so theme CSS or later Customizer rules can still target the wrapper

## ⚠️ Critical anti-pattern: NEVER inject `<!-- wp:image -->` blocks INSIDE the markdown body

Ad-hoc workspace scripts (e.g. `memory/workspace/{task}/publish_to_wp.py`) sometimes bypass `wp_publisher.py` and try to inject Gutenberg image blocks directly into the markdown body before conversion. This is broken and the failure is silent at PATCH time but visible on the rendered page.

**Why it breaks (2026-05-20 incident, post 37103 first publish attempt):**
1. The draft body contains `<!-- wp:image {...} -->\n<figure>...</figure>\n<!-- /wp:image -->` as raw text.
2. `scripts.build.markdown_to_html.convert(body)` runs `markdown-it-py` with `html: False` (the safe default — see `markdown_to_html.py:159`).
3. With `html: False`, markdown-it-py escapes the angle brackets: `<` → `&lt;`, `"` → `&quot;`. The Gutenberg comment markers become literal text: `&lt;!-- wp:image {&quot;id&quot;:37100,...&quot;} --&gt;`.
4. WordPress receives this as post content and runs `wptexturize()` on the literal text — which converts the now-unprotected `--` ASCII double-dash into `&#8211;` (en-dash) because, from `wptexturize`'s perspective, this is just text, not HTML markup.
5. On the rendered page, users see literal text like `<!– wp:image {"id":37100} –>` followed by working `<figure>` tags. Images may or may not render depending on what survived; the page is visibly broken.

**Correct pattern (`wp_publisher.py` does this; ad-hoc scripts MUST follow the same):**

```python
# 1. Convert markdown to HTML WITHOUT any wp:image markup in the body
html = md_to_html(body_md, opt)  # body_md has plain ![alt](url) or no images at all

# 2. Inject Gutenberg image blocks AFTER conversion, on the rendered HTML
def build_image_block(media_id, url, alt, caption):
    return (
        f'<!-- wp:image {{"id":{media_id},"sizeSlug":"large","linkDestination":"none"}} -->\n'
        f'<figure class="wp-block-image size-large">'
        f'<img src="{url}" alt="{alt}" class="wp-image-{media_id}"/>'
        f'<figcaption class="wp-element-caption">{caption}</figcaption>'
        f'</figure>\n'
        f'<!-- /wp:image -->\n'
    )

# Inject by finding an H2 anchor in the rendered HTML and inserting the block after it
html = inject_after_h2(html, "Subsystem 2 — Electrical", build_image_block(...))
```

If you must include image markup in the markdown body (e.g. for a draft preview), set `ConvertOptions.allow_raw_html=True` (see option doc) so `markdown-it-py` passes through `html: True` — but only if you trust the markdown source completely (we do, since we author it).

**Verification step that catches this bug:**
After publish, GET the live URL and grep for these escape-bug signatures:

| Signature | Means |
|---|---|
| `&lt;!-- wp:image` | Gutenberg block markers got HTML-escaped |
| `&lt;!– wp:image` | Same, plus wptexturize then converted `--` to en-dash |
| `&#8211; wp:image` | Same as above with the en-dash entity literal |

Any of these = the bug; treat as veto, fix the publish script and re-PATCH. Full reasoning: see auto-memory `feedback_wp_image_blocks_after_markdown_conversion.md`.

## See also
- `scripts/wordpress/wp_publisher.py`
- `scripts/wordpress/wp_taxonomy.py`
- `scripts/wordpress/wp_media.py`
- `scripts/build/article_css_generator.py` — generates `projects/{slug}/brand/article-css.css` from brand-config.json
