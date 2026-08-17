# Markdown Authoring Conventions (Global)

Applies to every project. Loaded into the writer agent's context for every `/article` run.

These rules exist because the publisher uses **`markdown-it-py` with `html=False`** (intentional XSS hardening — see `scripts/build/markdown_to_html.py:159`). The setting escapes raw HTML tags in the markdown body to text entities. Writing patterns that work in other markdown ecosystems (Pandoc, GitHub flavor with extensions, Kramdown) will silently leak as broken text in the rendered article.

Every rule below has a real production incident behind it. Don't treat them as style preferences — they are the canonical form because the alternatives break.

---

## Rule 1 · Use markdown bold, never raw `<strong>`

**Canonical form:**
```markdown
- **Lead clause** rest of the bullet sentence.
```

**Forbidden:**
```markdown
- **<strong>Lead clause</strong> rest of bullet.    ← orphan **, missing closing
- **<strong>Lead clause</strong>** rest of bullet.  ← nested double-strong, prints '<strong>' literal
- <strong>Lead clause</strong> rest of bullet.       ← raw HTML alone, escapes to '&lt;strong&gt;'
```

**Why:** With `html=False`, raw `<strong>` is escaped to `&lt;strong&gt;` (visible literal text). The `**` markers then cannot pair across the escape, so they ALSO print as literal asterisks. Result: bullet renders as `**&lt;strong&gt;Lead clause&lt;/strong&gt; rest…` instead of bold text.

**Same rule for any raw HTML tag in body text:** `<em>`, `<span>`, `<mark>`, `<cite>`, `<u>`, `<sub>`, `<sup>`, `<small>`, `<del>`, `<ins>`. Use markdown equivalents where they exist; for ones markdown doesn't cover, the publisher provides post-conversion class injection (see `_add_classes` in `markdown_to_html.py`).

**Production incident:** 2026-05-21 task 7w0gl0260521 (post 37163) — every Key Takeaways bullet rendered as visible broken text. Repaired by post-publish PATCH. Now caught by `render_lint` L1 + L3 (pre-publish) and `verify_post` checks 06 + 21 (post-publish).

---

## Rule 2 · Article signature as markdown italic, never raw `<p>` HTML

**Canonical form (place as the LAST paragraph before any references-only blocks):**
```markdown
*Last reviewed and updated: {Month Year}. Author: {Brand} team. For {project-specific CTA}, [contact our team]({contact_url}).*
```

**Forbidden:**
```markdown
<p class="article-signature"><em>Last reviewed... <a href="...">contact</a>.</em></p>
```

**Why:** Same as Rule 1 — `html=False` escapes `<p class=`, `<em>`, and `<a href=` to `&lt;p class=…`. The signature renders as visible broken HTML and the publisher's auto-class-tagger (`wp_publisher.py:1150-1167`) can't find a `<p><em>X</em></p>` to add the `article-signature` class to.

**How it works:** The publisher's `_apply_project_styling` finds the LAST `<p><em>…</em></p>` in the body (within 2500 chars of end) and adds `class="article-signature"` to it. The markdown italic form produces exactly that structure automatically.

**Production incident:** Same 2026-05-21 task. Repaired via `<!-- wp:html -->` Gutenberg-block wrapper PATCH. Now caught by `verify_post` check 11.

---

## Rule 3 · References block as markdown ordered list, never raw `<ol><li>` HTML

**Canonical form:**
```markdown
## References

1. Chandra, S., Lata, H., Khan, I. A., & ElSohly, M. A. (2008). Photosynthetic response of *Cannabis sativa* L. to variations in photosynthetic photon flux densities, temperature and CO₂ conditions. *Physiology and Molecular Biology of Plants*, 14(4), 299–306. https://doi.org/10.1007/s12298-008-0027-x
2. DesignLights Consortium. (2025). *Horticultural Qualified Products List*. https://designlights.org/qpl/
3. ... (8-10 entries total, hard cap 15)
```

**Forbidden:**
```markdown
## References

<ol>
<li>Chandra, S., Lata, H., Khan, I. A., & ElSohly, M. A. (2008). ...</li>
<li>DesignLights Consortium. (2025). ...</li>
</ol>
```

**Why:** Same escape rule. markdown-it produces a clean `<ol><li>...</li></ol>` from the numbered list form. Raw `<ol>` in source → escape leak → entire references block becomes visible broken text.

**Production incident:** Post 37126 shipped 2026-05-21 with entire References block as escaped HTML. Live for 24 hours before being detected by the new verify_post check 06 + 10. Repaired via PATCH.

---

## Rule 4 · Never use Pandoc/Kramdown `## Title {#anchor-id}` syntax

**Canonical form (let the publisher auto-generate anchor IDs from heading text):**
```markdown
## Why the 700-Watt Class Exists

## PPFD Coverage Math
```

**Forbidden:**
```markdown
## Why the 700-Watt Class Exists {#why-700w}
```

**Why:** Base `markdown-it-py` (configured `MarkdownIt("gfm-like")`) does NOT parse the Pandoc `{#xxx}` attribute syntax. The literal `{#xxx}` text leaks into the rendered H2 as visible text. The publisher's `_add_anchor_ids` now strips trailing `{#xxx}` defensively (as of 2026-05-21), but the canonical convention is to omit it entirely and let the auto-slugifier work.

**For TOC anchor links:** WordPress auto-generates `id="..."` from H2 text (slugified). Reference them in the TOC as `[Section Title](#section-title-slugified)`. If you need a *custom* short anchor that differs from the heading slug, you have two options:
1. Inline HTML anchor in a `<!-- wp:html -->` Gutenberg block (escape-safe), OR
2. Just rename the heading to match the slug you want.

**Production incident:** Same 2026-05-21 task. Nine H2s shipped with literal `{#electrical-budget}`, `{#tco}`, etc. visible. Now caught by `render_lint` L2 + `verify_post` check 19.

**Scope clarification (2026-07-06) — who this rule binds, and the one sanctioned exception:**
This rule is for WRITER agents authoring section `.md` files. AFTER assembly, `draft.md`
H2s legitimately carry trailing `{#anchor-id}` suffixes — `assemble.py` /
`anchor_link_builder` injects them on purpose as the file-bus contract for TOC anchor
slugs, and the publisher's `_add_anchor_ids` consumes them into real `id="..."`
attributes at conversion time (render_lint runs the same conversion before scanning, so
they never reach L2). Humanizer / reviewer / geo agents reading `draft.md`: do NOT flag
or strip these — two humanizers in the 2026-07-06 loamwright batch false-positived on
exactly this and wasted a review cycle. The rule's target is hand-authored `{#...}` in
SECTION files, where nothing downstream owns the suffix.

**Read the two halves precisely (2026-07-19 hardening):** "assembly owns `{#...}`"
is NOT license for a writer to pre-anchor headings in section files — not even by
copying the outline's `anchor_id` (that field is TOC metadata, never heading text).
A writer-anchored heading duplicated the Conclusion (the project `h2_pattern`
full-match saw `Conclusion {#conclusion}` and appended a stub) and killed 8 of 14
TOC links (heading kept the writer's anchor while the TOC linked the text-slug).
Both are now machine-corrected — `anchor_link_builder.inject_anchors` strips and
replaces ANY pre-existing anchor with the canonical text-slug, and assemble
normalizes h2 before dedup/pattern checks — but section files stay plain-heading
by contract.

---

## Rule 5 · Never declare custom `<img srcset="...">` in markdown source

**Canonical form (just markdown image syntax — the publisher wires up everything):**
```markdown
![Alt text describing the image]({local_or_wp_url})
```

**Forbidden:**
```html
<img src="X.png" srcset="X-480w.png 480w, X-768w.png 768w, X-1024w.png 1024w" alt="...">
```

**Why:** Hand-rolled `srcset` URLs point to derivative files that no upstream code generates. Every variant 404s; mobile/tablet viewports request the 480w or 768w variant first and either show a broken-image icon or empty space. WordPress's native `wp_image_add_srcset_and_sizes()` filter generates correct srcset at render time from the standard registered image sizes (300x300, 768x768, 1024x1024, 1200x800, etc.) which actually exist on disk — let it do its job.

**Production incident:** Posts 37126 and 37163 both shipped with broken srcset on every body image. Repaired by stripping the `srcset` attribute from the body (WP regenerates at render). Now caught by `render_lint` L4 + `verify_post` check 20. Source fix landed in `markdown_to_html.py` (`image_srcset=False` default) + `wp_publisher.py:229`.

---

## Rule 6 · When you MUST use raw HTML, wrap in `<!-- wp:html -->` Gutenberg blocks

For inline JSON-LD scripts, custom CTA blocks, or other escape-hatch cases:

```markdown
<!-- wp:html -->
<div class="custom-cta">
  <a href="...">Custom CTA</a>
</div>
<!-- /wp:html -->
```

The `<!-- wp:html -->` comment is a Gutenberg block marker that the WP REST API preserves verbatim. The content inside passes through to the front-end as raw HTML — not escaped. Use this sparingly; ideally only for:
- Inline `<script type="application/ld+json">` schema blocks (when the publisher's schema injector doesn't cover the schema type you need)
- Project-specific class wrappers — the publisher handles these automatically; you never write one manually. Since v3.42.0 (style tokens) the PUBLISHED class name is a per-project HMAC token, not the legacy `{slug}-pillar` form: internal artifacts keep legacy names and `wp_publisher._apply_project_styling` transforms them at the publish boundary. Never hand-write a published class name; resolve it via `python -m scripts._core.style_tokens --show {slug}` (root CLAUDE.md Rule 2).
- Embedded interactive elements (calculator iframes, custom buttons)

**Do NOT use `wp:html` blocks as a workaround for the rules above.** If you find yourself wanting `<!-- wp:html --><p class="article-signature">...</p><!-- /wp:html -->`, write the markdown italic form instead (Rule 2) and let the publisher tag it.

---

## Rule 7 · Never use GFM task-list checkboxes (`- [ ]` / `- [x]`)

The publisher's markdown-it config has **no task-list plugin**, so checkbox syntax ships as
literal bracket text to the reader:

```markdown
❌ - [ ] You need booked revenue inside 60 days.
→ renders as: <li>[ ] You need booked revenue inside 60 days.</li>   ← literal "[ ]" visible

✅ - You need booked revenue inside 60 days.
✅ - **Booked revenue inside 60 days.** Paid is the only channel that delivers that fast.
```

This bites hardest when a section spec assigns a `checklist` design component — the GitHub/editor
habit is exactly the wrong move here. Realize checklists as plain bullets, bold-led bullets, or a
numbered framework (see `references/style/visual-design-components.md` Component 5).
`render_lint` L13 hard-vetoes any leaked checkbox (caught live in the 2026-07-07 batch).

---

## Validation

Before publish, the seo-blog pipeline runs **`scripts/lint/render_lint.py`** against your `draft.md`. The lint converts your markdown to HTML using the canonical publisher config and scans for the four leak classes:

| Class | What it catches |
|---|---|
| L1 | Any escaped HTML tag (`&lt;tagname`) inside a body element — including a raw `<table>/<thead>/<tr>/<td>/<th>` (write a **markdown pipe table** instead) and a raw `<hr />` (write `---` on its own line instead). Catches violations of Rules 1, 2, 3 and the table/rule rows of the quick-reference card. |
| L2 | Literal `{#anchor-id}` inside any `<h1..h6>` — catches violations of Rule 4 |
| L3 | Unbalanced `**` markers (odd count) in body element — catches orphan-bold from Rule 1 |
| L4 | `<img srcset="...-NNNw.{ext}">` hand-rolled variant pattern — catches violations of Rule 5 |
| L5/L6 | Unresolved `[claim:cN_*]` citation markers and writer scaffold tokens (`[ORIGINAL DATA]`, `[UNIQUE INSIGHT]`, `[CAPSULE]`) leaking to the body |
| L9 | Article signature appearing BEFORE the `## References` heading — the signature is always the LAST block. **Do not author the signature at all** (the finalize stage adds it after References automatically; if you do write one it will be relocated, but don't). |
| L12/L13 | An em-dash (U+2014) in body prose (use a comma, period, or parens) / a GFM task-list checkbox leaking as literal `[ ]` or `[x]` text — catches violations of Rule 7 |
| L10 | A TOC `[…](#anchor)` link whose `#anchor` has no matching rendered heading id — usually a non-ASCII char (`µ`, `²`) in the heading. The slugifier now ASCII-folds these (`µ`→`u`), so just write headings normally and let the publisher build the anchors. |

Post-publish, `scripts/wordpress/verify_post.py` runs the same checks against the live WordPress rendered HTML (checks 06, 19, 20, 21) plus 15 other structural checks.

If the lint catches a defect, the publish phase halts and routes to the repair orchestrator. **You cannot ship an article with any L1-L4 defect.** Either fix the markdown source to match the canonical forms above, or — if you have a legitimate reason to deviate — wrap the offending HTML in `<!-- wp:html -->` blocks (Rule 6).

---

## Quick reference card

| Want to render… | Write in markdown… | NOT this |
|---|---|---|
| Bold | `**text**` | `<strong>text</strong>` or `**<strong>text</strong>**` |
| Italic | `*text*` | `<em>text</em>` |
| Article signature | `*Last reviewed... [contact](url).*` (as last italic paragraph) | `<p class="article-signature"><em>...</em></p>` |
| References | `1. Author. (Year). Title. Url` (numbered list, one per line) | `<ol><li>...</li></ol>` |
| Heading | `## Section Title` | `## Section Title {#anchor}` or `<h2>...</h2>` |
| Image | `![alt](url)` | `<img src="..." srcset="...-480w.png 480w" ...>` |
| Link | `[text](url)` | `<a href="url" target="_blank">text</a>` (publisher adds target/rel) |
| List | `1. item` / `- item` | `<ol><li>...</li></ol>` |
| Checklist | `- item` or `- **Lead.** detail` (plain/bold-led bullets) | `- [ ] item` (GFM checkbox → literal `[ ]` ships, L13 veto) |
| Code | `` `inline` `` / ` ```block``` ` | `<code>...</code>` / `<pre>...</pre>` |
| A literal HTML tag name in prose | `` `<a href>` `` (inside backticks — render-lint excises code spans, 2026-07-01) | bare `<a href>` outside backticks (L1 hard veto) |
| Table | markdown pipe table | `<table>...</table>` |
| Horizontal rule | `---` (own line) | `<hr />` |

If you don't see what you need in this table, ask the publisher (in `wp_publisher.py`) before reaching for raw HTML.
