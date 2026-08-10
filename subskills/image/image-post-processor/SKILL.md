---
name: image-post-processor
description: After batch completes, runs 4-step post-processing on each image: EXIF strip → WebP convert (q85) → srcset 3 sizes → SEO filename. Generates ImageObject schema fragment. Stage 27e.
allowed-tools: [Read, Write, Bash]
---

# Image Post Processor

Transforms raw PNG outputs from the image pipeline (any provider — openclawroot relay or official OpenAI, both return gpt-image-style PNGs) into production-ready WebP variants.

## Inputs

- `projects/{slug}/assets/images/{article-slug}/{custom_id}.png` × 4
- `workspace/{task_id}/image_prompts.json` (for alt_text_seed, filename_seed)

## 4-step pipeline (per image)

```python
import subprocess
from pathlib import Path

images_dir = Path("projects/{slug}/assets/images/{article-slug}/")
for png_file in images_dir.glob("*.png"):
    slot_id = png_file.stem
    
    # Step 1: Strip EXIF
    subprocess.run(["python", "-m", "scripts.image.exif_stripper", str(png_file)])
    
    # Step 2: WebP convert
    webp_file = png_file.with_suffix(".webp")
    subprocess.run(["python", "-m", "scripts.image.webp_converter",
                    str(png_file), "-o", str(webp_file), "-q", "85"])
    
    # Step 3: Srcset 3 sizes
    is_cover = slot_id == "cover"
    args = ["python", "-m", "scripts.image.srcset_generator",
            str(webp_file), "-o", str(images_dir)]
    if is_cover:
        args.append("--cover")  # uses 480/1024/2048
    subprocess.run(args)
    
    # (Removed 2026-06-10: the old "Step 4: compress to <200KB" --target-kb loop.
    # q85 is the single quality knob now — a hard KB cap on 2K/4K sources just
    # re-compressed them to ~q75 and undid the quality upgrade.)

    # Step 4: SEO filename rename
    article_slug = ws.parent.name  # or from state
    purpose = lookup_purpose_for_slot(slot_id)  # from image_prompts.json
    new_name = subprocess.run(["python", "-m", "scripts.image.image_seo_filename",
                                "--slug", article_slug,
                                "--purpose", purpose,
                                "--ext", ".webp"],
                               capture_output=True, text=True).stdout.strip()
    webp_file.rename(images_dir / new_name)
```

## Output

```
projects/{slug}/assets/images/{article-slug}/
├── best-fishing-rods-2026-cover.webp        (3840w)
├── best-fishing-rods-2026-cover-480w.webp
├── best-fishing-rods-2026-cover-1024w.webp
├── best-fishing-rods-2026-cover-2048w.webp
├── best-fishing-rods-2026-section-1.webp    (1024w)
├── ... (similar for sections 2, 3)
└── image_meta.json                           (per-image metadata)
```

## ImageObject schema fragment

Generated per cover image:
```json
{
  "@type": "ImageObject",
  "@id": "{url}#image-cover",
  "url": "{cdn}/best-fishing-rods-2026-cover.webp",
  "contentUrl": "{cdn}/best-fishing-rods-2026-cover.webp",
  "width": 3840,
  "height": 2160,
  "caption": "{from alt_text_seed}",
  "creator": { "@id": "{org_url}#organization" }
}
```

## Handoff

`recommended_next_skill`: `image-curator` (alt text polishing + draft injection)
