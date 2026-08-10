# Deferred-Image Publish Flow (B Workflow)

This document describes the **B workflow** for `/publish`: create WP draft immediately
without images, then asynchronously attach images once batch generation finishes.

**Use this when**: you're publishing many articles in a wave (10+ at a time) and don't
want image generation to block draft creation.

**Don't use this when**: single-article precision edits where you want one clean
"images ready → draft published" moment.

## The flow

```
┌──────────────────────────────────────────────────────────────┐
│ Phase 1: Draft creation (fast — seconds)                     │
│                                                              │
│  draft.md → wp_publisher.py --defer-images                  │
│    → WP draft created with HTML placeholder figures          │
│    → projects/{slug}/.seo/pending-images.json sidecar       │
│    → Status: "awaiting_images"                              │
└──────────────────────────────────────────────────────────────┘
                          ↓
                ─────────────────────────
                ↓                         ↓
┌──────────────────────────┐   ┌──────────────────────────┐
│ Phase 2a: Generate       │   │ Phase 2b: Reviewer        │
│ images (slow — minutes)  │   │ checks text content      │
│                          │   │ (parallel, optional)     │
│ Provider chain (realtime │   │                          │
│ relay→OpenAI fallback):  │   │ Drafts visible in WP     │
│   generate → b64         │   │ admin with placeholders. │
│ → save to disk           │   │ Can edit/refine text     │
│                          │   │ before images attach.    │
│ Update sidecar slot's    │   │                          │
│ image_path = ...         │   │                          │
└──────────────────────────┘   └──────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│ Phase 3: Attach (automatic — seconds per article)            │
│                                                              │
│  attach_images_to_draft.py --watch  (or --all)              │
│    → Upload images to Media Library (with alt/caption/title) │
│    → PATCH draft body: replace placeholders with real <figure>│
│    → Set featured image                                      │
│    → Sidecar status → "attached"                            │
│    → (Optional webhook notification)                         │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│ Phase 4: Human review + publish (manual)                     │
│                                                              │
│  Reviewer logs into WP, opens each draft, verifies:          │
│    - text content OK                                         │
│    - images are appropriate (YMYL check)                     │
│    - featured image is correct                               │
│    - no competitor logos in images                           │
│  Clicks "Publish" in WP admin.                               │
└──────────────────────────────────────────────────────────────┘
```

## Commands

### Phase 1: Create deferred draft

```bash
# From a workspace task
python -m scripts.wordpress.wp_publisher project-charlie \
    --workspace <task_id> \
    --status=draft \
    --defer-images

# From explicit files
python -m scripts.wordpress.wp_publisher project-charlie \
    --draft draft.md \
    --meta meta.json \
    --images images.json \
    --status=draft \
    --defer-images
```

Note: `--defer-images` forces `--status=draft` (you can't publish without images).

### Phase 3: Attach images

```bash
# Attach for one specific post
python -m scripts.wordpress.attach_images_to_draft project-charlie --post-id 123

# Process every pending entry that has images on disk
python -m scripts.wordpress.attach_images_to_draft project-charlie --all

# Watch mode: poll every 60s and attach as soon as ready (for batch operations)
python -m scripts.wordpress.attach_images_to_draft project-charlie --watch --interval 60

# Dry run (no actual WP changes)
python -m scripts.wordpress.attach_images_to_draft project-charlie --all --dry-run
```

## File schemas

### images.json (input to wp_publisher)

In `--defer-images` mode, `path` can be **null** (image not yet generated):

```json
[
  {
    "slot_id": "cover",
    "alt": "Commercial cannabis grow room with LED grow lights",
    "caption": "Figure 1: 4x6 ft flower room using project-charlie S05",
    "title": "project-charlie S05 commercial cannabis cultivation",
    "is_featured": true,
    "path": null
  },
  {
    "slot_id": "section_1",
    "alt": "...",
    "path": null
  }
]
```

Once images are generated, the **caller** must update `image_path` in the sidecar:

### pending-images.json (sidecar)

`projects/{slug}/.seo/pending-images.json`:

```json
{
  "pending": [
    {
      "post_id": 123,
      "task_id": "abc-xyz",
      "created_at": "2026-05-19T08:00:00Z",
      "status": "awaiting_images",
      "slots": [
        {
          "slot_id": "cover",
          "alt": "...",
          "caption": "...",
          "is_featured": true,
          "image_path": "/path/to/projects/project-charlie/assets/images/article-slug/cover.webp"
        },
        ...
      ]
    }
  ]
}
```

Once attached:

```json
{
  "post_id": 123,
  "status": "attached",
  "attached_at": "2026-05-19T08:42:00Z",
  "media_ids": [456, 457, 458, 459],
  "featured_media_id": 456,
  "slots": [...]
}
```

## How `wp_publisher --defer-images` modifies the draft body

In the markdown body, `[IMAGE-SLOT-cover]` becomes:

```html
<figure class="xuanran-pending-image" data-slot="cover" data-alt="...">
  <div class="xuanran-image-placeholder"
       style="background:#f5f5f5;padding:80px 20px;text-align:center;
              color:#888;border:2px dashed #ccc;border-radius:6px;
              font-family:sans-serif;">
    <strong>Image pending</strong><br>
    <small style="opacity:0.7;">slot: cover</small>
  </div>
</figure>
```

This renders cleanly in WP admin preview (reviewer can read content without raw
`[IMAGE-SLOT-cover]` text littering the article) AND is unambiguously matchable
by `attach_images_to_draft.py` via the `data-slot` attribute.

## How `attach_images_to_draft` replaces placeholders

After upload, the placeholder becomes:

```html
<figure class="wp-block-image size-large">
  <img src="https://project-charlie.example.com/wp-content/uploads/.../cover.webp"
       srcset="...medium 600w, ...large 1024w, ...full 1536w"
       sizes="(max-width: 768px) 100vw, 768px"
       alt="Commercial cannabis grow room with LED grow lights"
       loading="lazy" width="1536" height="1024" />
  <figcaption>Figure 1: 4x6 ft flower room using project-charlie S05</figcaption>
</figure>
```

WordPress `wp-block-image` class ensures Gutenberg compatibility.

## Featured image strategy

The slot with `is_featured: true` in `pending-images.json` becomes the WP featured
image. By convention, this is the `cover` slot.

If multiple slots have `is_featured: true`, only the FIRST is honored.

If no slot has `is_featured`, no featured image is set (you can set it manually
in WP admin).

## Cannabis / grow-light specific gotchas

When generating images for project-charlie articles, the **image prompt designer**
must inject these negative prompts (already in
`references/image/negative-prompts.md`):

- No competitor logos (Fluence, Gavita, Mars Hydro, Spider Farmer, Photontek,
  ChilLED, HLG, California LightWorks, Growers Choice, Black Dog, BIOS, TSRgrow)
- No dried cannabis bud / joint / consumption imagery (YMYL legal risk)
- No real recognizable human faces (privacy + talent release)
- Prefer wide cultivation room shots with fixtures in context (not flowering
  bud close-ups)

## Watching for completion (orchestration)

In a typical batch run for 10 articles:

```bash
# 1. Submit OpenAI batch (40 images for 10 articles)
python -m scripts.openai.openai_batch_image_api submit ...

# 2. Create all 10 drafts deferred (fast)
for task in task_*; do
  python -m scripts.wordpress.wp_publisher project-charlie \
    --workspace $task --status=draft --defer-images
done

# 3. Poll for batch completion + auto-attach when ready
python -m scripts.wordpress.attach_images_to_draft project-charlie \
    --watch --interval 120

# 4. (separately, when you have time) Log into WP admin → review → publish
```

You can run step 3 in the background; when batch finishes (1-24h depending on
load), it auto-detects ready images and attaches them, leaving you with 10
publish-ready drafts.

## Idempotency

- Re-running `attach_images_to_draft --post-id N` on an already-attached entry
  is a no-op (sidecar `status="attached"` is skipped).
- Re-running with new images for the same slot would NOT re-upload (Media Library
  dedup via `check_existing_by_filename=True`), but WOULD re-PATCH the body if
  you delete the sidecar entry's `status` field. Don't do this lightly.

## Failure modes

| Failure | Behavior |
|---|---|
| Image file missing on disk | Sidecar entry stays `awaiting_images`; `--watch` retries each interval |
| WP upload fails for ONE slot | That slot's `failed_slot_ids` populated; other slots still attached (partial success) |
| WP PATCH fails | All uploads done, but body not updated. Re-run attaches (Media Library dedup prevents duplicates) |
| WP draft deleted in admin | `attach` returns 404 on fetch; entry stays in sidecar (clean up manually) |

## See also

- `scripts/wordpress/wp_publisher.py` — Phase 1 draft creation
- `scripts/wordpress/attach_images_to_draft.py` — Phase 3 attach
- `scripts/wordpress/wp_media.py` — Media Library API
- `references/image/negative-prompts.md` — Cannabis competitor exclusions
- `agents/image-curator.md` — Per-image alt text + caption polishing
