---
name: phase-publish
description: Run Phase Publish — image generation sub-pipeline (provider-pluggable: relay primary + official OpenAI fallback, realtime-forced) + WordPress publish with RankMath meta + IndexNow ping. Use when draft has passed all quality gates and is ready for live publication. Triggered by /seo-blog publish, /publish, "post this to WordPress", "go live".
allowed-tools: [Read, Write, Bash, Task]
disable-model-invocation: true
---

# Phase Publish Orchestrator

Image generation + WordPress upload + indexing notification + monitor registration.

> **Critical**: `disable-model-invocation: true` — only triggered explicitly by user or upstream skill. Cannot be auto-invoked. Prevents accidental publishing.

## Inputs

Required in `workspace/{task_id}/`:
- `draft.md` with frontmatter `Stage: optimized`
- `meta.json`
- `quality.json` with `overall_passed: true`
- `review.json` with `score >= target_score`

Required in `~/.xuanran-seo/credentials/wordpress/<slug>.json`:
- `{ url, username, app_password }`

## Stage 1: Image Sub-Pipeline (5 sub-stages, 1-34 min total)

```
Stage 27a: image-slot-allocator    (~2 sec, no LLM)
  Decide brief.image_count slots (default 6, max 8 — scripts/_core/image_policy.py): 1 cover (16:9) + the rest section images (16:9/4:3)
  Format-aware H2 selection (per BLOG-FORMATS-2026-CATALOG §2.2)
  Output: image_slots.json

Stage 27b: image-prompt-designer    (~15 sec, LLM)
  Read brand-identity.json (colors), brand-voice.md (aesthetic)
  Generate shared Art Direction Prefix (Strategy A visual consistency)
  Design 9-field prompt per slot
  Output: image_prompts.json

Stage 27c: openai-image-generator  (~1-3 min realtime, parallel max_workers=4)
  Routes to the provider chain (scripts/_core/image_provider.py):
    primary  = openclawroot relay  (realtime only — relays have NO Batch API)
    fallback = official OpenAI      (auto-tried PER-SLOT if the relay fails)
  Calls images.generate per slot, saves PNGs, writes images.json.
  Mode is FORCED realtime (config.yaml :: image.default_mode). Do NOT use
  --mode auto/batch here: that bypasses the relay (batch is official-only) and
  reproduces the 2026-05-21 "worst-of-both-worlds" wait.

Stage 27d: batch-job-poller         (SUPPLEMENTAL — only if an official-OpenAI
  batch was ever submitted; the canonical realtime flow does not need it)
  GET /v1/batches/{id} → status; download output_file when completed

Stage 27e: image-post-processor    (~10 sec, no LLM)
  EXIF strip + WebP convert + srcset 3 sizes + compress <200KB + SEO filename
  Generate ImageObject schema fragment

Stage 27f: image-curator            (~10 sec, LLM)
  Polish alt text per image (≤125 chars, keyword-natural)
  Generate optional captions
  Replace [IMAGE-SLOT-N] placeholders in draft.md
  Inject ImageObject into schema @graph
  Update frontmatter Stage: images-injected
```

**Cost**: provider-dependent. At 4K high the ledger books ~$1.67/image → ~$10/article at the default 6 images (~$13.4 at the max 8). The relay (openclawroot) is token-billed and typically cheaper, but cost_ledger deliberately over-estimates it with the official per-image table (conservative cost guard, see scripts/_core/image_provider.py).

## Stage 2: WordPress Publish (~30 sec)

`scripts/wordpress/wp_publisher.py` (the canonical publisher — `scripts/publish/` holds
only change_log/gsc/indexnow helpers). Categories are **resolve-only** at publish: an
unresolvable name aborts before any WP write (create deliberately at init via
`scripts.wordpress.setup_categories`, or opt in with `--allow-create-categories`):

```python
1. Upload every generated image to Media Library (multipart)
   - cover → featured_media
   - sections → inline references in body
   - All srcset variants uploaded
   - REQUIRED 4 metadata fields per upload: title + alt_text + caption + description
   
2. markdown_to_html(body) with anchor links resolved

3. PROJECT CSS INJECTION (required — see HARD RULE below)
   IF projects/{slug}/brand/article-css.css exists:
       css = projects/{slug}/brand/article-css.min.css (prefer minified)
       wrapper_class = read leading selector from CSS file
                       (internal name, typically "{slug}-pillar")
       # PUBLISHED name may differ: style_tokens rewrites it at the publish
       # boundary. Resolve with scripts._core.style_tokens, never hand-write.
       body_html = wrap_with_gutenberg_css_block(body_html, css, wrapper_class)
       # Append any trailing inline JSON-LD AFTER the closing wrapper
   
4. POST /wp-json/wp/v2/posts (status: **draft** — DEFAULT, do NOT publish yet)
   - title, slug, content (now CSS-wrapped), excerpt, categories, tags
   - featured_media = cover media_id
   - `status: "draft"` unless user explicitly opted in to publish-on-create (see step 8)
   - Returns post_id + preview URL

5. RankMath / Yoast meta via canonical bridge:
   - PREFERRED:  POST /wp-json/wp/v2/posts/{id} with body {"meta": {rank_math_*: ...}}
                 (works because the MU-plugin xuanran-rank-math-rest-bridge.php
                  registers RankMath keys with REST schema)
   - DEPRECATED: POST /xuanran/v1/rank-math-bridge (route returns 404 — only GET exists now)
   - Note: rank_math_robots enum is ["index","noindex","nofollow","noarchive","noimageindex","nosnippet"]
           — "follow" is NOT valid and will 400. Use ["index"] (follow is implicit default).

6. Inline JSON-LD for FAQPage / ItemList / BreadcrumbList — these are NOT 
   generated by RankMath's free tier; append as <script type="application/ld+json">
   to the post body OUTSIDE the CSS wrapper.

7. VERIFY against the PREVIEW URL (`/?p={id}&preview=true` works for drafts via authenticated session); confirm:
   - HTTP 200 (not 500 from malformed schema/HTML)
   - the project's wrapper class present in rendered HTML — resolve the PUBLISHED
     name with `python -m scripts._core.style_tokens --show {slug}` (tokenized
     projects ship `mwxiod-1ymm61`, NOT `{slug}-pillar`; grepping for the legacy
     name is a check that cannot pass). `verify_post.py` already resolves it for you.
   - All image source URLs render (count = brief.image_count)
   - At least one JSON-LD block contains expected schema types
   - `<h2>References</h2>` (or `<h2 id="references">`) present with ≥3 `<li>` link-resolvable entries
   - `<p class="article-signature">` paragraph present near end of body
   - Order: any `<h2>Further Reading</h2>` appears BEFORE `<h2>References</h2>`
   - NO competitor/peer domain cited anywhere (References, body links, JSON-LD) — Rule 8.
     `verify_post.py` check 28 enforces this on the live URL; or run directly:
     `python -m scripts._core.competitor_domains --task {tid} --scan-file {final.html}` (exit 1 = a competitor leaked)

8. ✋ **CHECKPOINT: publish handoff (HARD RULE 5a — see root CLAUDE.md)**
   Default is to STOP here. Report to user:
       - post_id, preview URL, verification results, cost summary
   Wait for user to confirm "publish" / "go live" / equivalent.
   Skip the wait ONLY when one of these is true:
       (a) `business-context.json :: publish_policy.default == "publish"` (project pre-authorized auto-publish)
       (b) Original user request used explicit publish-imperative language ("publish", "go live", "上线", "发布到线上")
       (c) CLI invocation included `--status=publish`
   The phrase "post it" is ambiguous (could mean "create the post") and does NOT satisfy (b).

9. ON CONFIRMATION (or pre-authorized): run THE flip executor — one command owns
   the whole PATCH → live-URL re-verify → indexing re-run sequence (v3.42.16;
   before this, the three sub-steps were a checklist duplicated across three
   SKILL.md files with no executor and no verification — Rule 6/11/14):

       python -m scripts.wordpress.flip_post_live {project_slug} --workspace {task_id} --json

   Exit 0 = flipped + live-verified + submitted to IndexNow. Exit 2 = flipped and
   live-verified but the URL was NOT submitted (no_credentials / transport —
   resolve and re-run indexing_notify; never ignore silently). Exit 1 = hard
   failure (PATCH failed or live verification failed — the post needs fixing;
   the flip is NOT complete). The full evidence lands in the workspace as
   flip-result.json + verify-live-result.json (the draft-phase verify-result.json
   is pipeline history and is deliberately not overwritten).
   Never hand-run the PATCH + re-verify + indexing steps separately again.
```

### HARD RULE — Project article CSS is mandatory

Every project that defines `projects/{slug}/brand/article-css.css` MUST have it injected into every new article at publish. The wrapper class MUST equal the CSS scope. The verification step above is non-optional — a publish that returns HTTP 200 with the wrapper missing is a silent failure (rules orphan; article ships unstyled).

Pattern reference: see `skills/seo-blog/SKILL.md` Hard Rules section for the canonical 3-block Gutenberg wrapping pattern.

## Stage 3: Indexing & Monitor Registration

```
30. indexing-notifier  (REAL runner stage since v3.42.12 — runs after verify-post)
    - Executor: python -m scripts.publish.indexing_notify {project_slug} --workspace {task_id} --json
    - Draft post → outcome=skipped_draft (Rule 5a; the post-flip re-run in step 9 submits)
    - GSC URL Inspection stays MANUAL (per-site OAuth + strict quotas; see
      subskills/publish/indexing-notifier/SKILL.md)

31. change-log writer
    - projects/{slug}/change-log.json append entry
    - 7-day undo enabled (rollback_data = previous state)

32. monitor registration
    - Register T+7/14/30/90 callbacks
    - rank-tracker / ai-visibility-tracker / drift-detector
```

## Output

- Live WordPress URL
- `projects/{slug}/change-log.json` updated
- `memory/workspace/{task}/` archived after publish success

## Failure modes

| Failure | Action |
|---|---|
| OpenAI Batch fail (content policy) | LLM revise prompt → resubmit single image only |
| Batch expired 24h (rare) | Auto fallback to realtime API |
| WP Media upload 401 | Halt + alert user (credential issue) |
| WP REST returns 500 | Retry 2× exponential; on 3rd fail halt |
| Yoast endpoint 404 | Warn MU-plugin not installed, publish without Yoast meta |
| IndexNow fails | Log + continue (non-blocking) |

## Rollback

User can run `/forget-project --partial <task_id>` within 7 days to:
- Mark WP post as draft
- Remove from Monitor callbacks
- Keep workspace artifacts for audit

## See also

- `IMAGE-GENERATION-V3.2-SPEC.md` (in plugin docs)
- `subskills/publish/wordpress-publisher/SKILL.md`
- `subskills/publish/indexing-notifier/SKILL.md`
- `install/wordpress-mu-plugin/seo-machine-yoast-rest.php`
