---
name: openai-image-generator
description: Generate all 4 article images via the unified openai_image_pipeline (provider-aware: Vertex Gemini 3 Pro Image 4K primary + official OpenAI fallback, realtime-forced). Single-call pipeline replaces the prior submit→wait→download multi-stage pattern. Stage 27c+27d combined.
allowed-tools: [Read, Write, Bash]
---

# OpenAI Image Generator

Generates all 4 article images using the canonical `openai_image_pipeline.py` script.
This skill consolidates what used to be Stage 27c (submit) + Stage 27d (poll) into a
single call.

The pipeline routes to the configured PROVIDER CHAIN (scripts/_core/image_provider.py):
since 2026-06-17 the primary is **vertex-gemini** — Google Vertex AI express mode
serving **Gemini 3 Pro Image (Nano Banana Pro)** at true 4K (~16MP, downscaled to the
requested pixel size), ~10x cheaper than OpenAI with better text rendering. The fallback
is official OpenAI (`gpt-image-2`, honest 4K, ~$1.67/img). Every newapi gpt-image-2 relay
(chatgpt-code / openclawroot / llmtoken / yunxiangpnv) was DISABLED on 2026-06-17 after
all were found to silently degrade 4K to ~1.5MP (shared "GPT-Image-2-4k distributor"
upstream). Mode is FORCED realtime (config.yaml :: image.default_mode: realtime; neither
Vertex nor relays support the OpenAI Batch API). Each slot tries the primary, then
auto-falls-back to official OpenAI on failure. Writes wp_publisher-compatible images.json.

The vertex-gemini provider is NOT OpenAI-compatible — it uses Vertex express
`generateContent` + `generationConfig.imageConfig` (aspectRatio + imageSize="4K") with an
`AQ.`-prefix API key via the `x-goog-api-key` header, handled by a dedicated branch
(`openai_image_pipeline._generate_vertex_gemini`). Set up via `config.yaml ::
image.providers` with `protocol: vertex_gemini`. See memory
[[reference-vertex-gemini-4k-image-recipe]].

## Why realtime + provider chain (vs the old batch-first pattern)

The old `submit` → `awaiting-images` → scheduled poller (batch-first) flow had failure modes:
1. Operator polled once at +5 min, saw `validating`, abandoned.
2. Batch API genuinely failed (HTTP 400 / expired) but the poller had no fallback.
3. `--mode auto` against a relay-primary setup is the worst case: it tries official
   batch FIRST (bypassing the relay), waits ~25 min, then falls back to realtime.

The provider chain + forced realtime addresses all three:
- Relay primary served via realtime (~1-3 min, parallel max_workers=4)
- Per-slot automatic fallback to official OpenAI on any relay error
- No 25-min batch wait; batch is reserved for the official-OpenAI fallback only

See memory: [[reference-openai-image-pipeline]], [[reference_openclawroot_image_provider]], [[feedback-batch-image-default-and-polling]]

## Inputs

- `workspace/{task_id}/image-prompts.json` (from image-prompt-designer)
- `state.brief.image_quality` (default "high")
- `state.brief.image_mode` (default "realtime" — relay primary has no Batch API; "batch"/"auto" force the official-OpenAI path and bypass the relay)

## Workflow (canonical — single call)

```bash
# Build pipeline input from image-prompts.json (the prompt designer's output).
# Use the shared normalizer so list AND dict-keyed shapes both work (2026-06-29).
python -c "
import json
from scripts._core.image_prompts import load_image_prompts
entries = load_image_prompts('memory/workspace/{task_id}/image-prompts.json')
specs = []
for p in entries:
    specs.append({
        'slot': p.get('slot_id') or p.get('slot') or p.get('custom_id'),
        'prompt': p.get('compiled_prompt') or p.get('full_prompt') or p.get('prompt'),
        'size': p.get('size', '2880x2880'),
        'quality': p.get('quality', 'high'),
        'alt': p.get('alt') or p.get('alt_skeleton', ''),
        'caption': p.get('caption', ''),
        'title': p.get('title', ''),
        'is_featured': p.get('is_featured', p.get('slot_id') == 'cover'),
    })
json.dump(specs, open('memory/workspace/{task_id}/image_pipeline_input.json', 'w'), indent=2)
"

# Run the pipeline (realtime = relay primary + official OpenAI fallback).
# Omitting --mode lets it read config.yaml :: image.default_mode (= realtime).
python -m scripts.openai.openai_image_pipeline generate \
    --requests-file memory/workspace/{task_id}/image_pipeline_input.json \
    --workspace memory/workspace/{task_id} \
    --task-id {task_id} \
    --mode realtime \
    --json
```

Mode flags (rarely overridden — realtime is canonical):
- `--mode realtime` — relay primary + official OpenAI fallback (DEFAULT, the only mode that uses the relay)
- `--mode batch --no-fallback` — official-OpenAI-ONLY overnight batch (skips the relay entirely; relays have no Batch API)
- `--mode auto` — official batch first, realtime fallback (legacy; bypasses the relay as primary — avoid)

## Output

Always written to workspace, regardless of mode:
- `images/{slot}.png` × N (PNG files)
- `images.json` (wp_publisher input — slot_id, path, alt, caption, title, is_featured, source)
- `images_manifest.json` (audit — mode used, batch_id, fallback reason, per-slot cost)
- `batch_status.json` (latest poll result — present only if batch was attempted)
- `image_pipeline.log` (chronological log lines)

Frontmatter update on draft.md: `Stage: images-ready` (skip the prior `awaiting-images`
intermediate state — pipeline finishes synchronously)

## Cost

| Mode used | brief.image_count images @ 4K high (default 6; 3840x2160 cover / 2880x2880 sections) |
|---|---|
| All batch (best case) | ~$0.33 |
| Partial fallback (1 slot) | ~$0.41 |
| Full realtime fallback / pure realtime | ~$0.66 |

Per-slot estimate from `cost_ledger.py`: 4K sizes pixel-scale the 1024x1024 high baseline ($0.211) — every 4K tier is ~8.29M px ~= $1.67/image, ~$10/article at the default 6 images (~$6.7 at 4, ~$13.4 at the max 8). Deliberate over-estimates at official rates; the chatgpt-code relay bills credits (2K/4K same price), much lower.

## When to use the OLD submit→poll pattern instead

Almost never. The pipeline supersedes it. The old `openai_batch_image_api submit` +
`batch-job-poller` skill flow is retained for:
- Diagnostic / debugging (inspecting batch state without committing to download)
- Recovering an orphan batch from a prior failed pipeline run (see batch-job-poller SKILL)
- Submitting many batches across multiple articles in parallel where you don't want to
  block on each one

## Handoff

Article moves directly to `images-ready` state. The next skill (image-post-processor)
picks up `images.json` and the PNGs in `images/`.
