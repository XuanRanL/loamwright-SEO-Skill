#!/usr/bin/env python3
"""scripts/openai/image_watermark.py — stamp a crisp brand watermark onto images.

WHY a post-process overlay (not an AI-rendered watermark): generative image models
render text inconsistently — the same limitation that produces empty/garbled labels.
A PIL overlay guarantees a correctly-spelled, consistently-placed, legible brand mark
every time. Driven by the project's brand-guideline.yaml so each project controls its
own watermark (project-level choice) using one shared utility (skill-level capability).

brand-guideline.yaml schema (all optional except enabled/text):
    watermark:
      enabled: true
      text: "Project Juliet"
      position: bottom-right        # bottom-right|bottom-left|top-right|top-left|bottom-center
      opacity: 0.6                  # 0..1
      color: "#FFFFFF"              # text color
      font_size_frac: 0.034         # of image width
      margin_frac: 0.028            # of image width
      shadow: true                  # subtle dark shadow for legibility on any background
      apply_to: all                 # all|sections (sections = skip is_featured covers)

Usage:
    python -m scripts.openai.image_watermark <image.png> --text "Project Juliet"
    python -m scripts.openai.image_watermark <image.png> --project project-juliet
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

# Portable bold-font candidates (Windows / Linux / macOS). First hit wins.
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\seguisb.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]

_POSITIONS = {"bottom-right", "bottom-left", "top-right", "top-left", "bottom-center"}


def _hex_to_rgb(s: str) -> tuple[int, int, int]:
    s = (s or "#FFFFFF").lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except (ValueError, IndexError):
        return (255, 255, 255)


def _load_font(px: int):
    from PIL import ImageFont
    for cand in _FONT_CANDIDATES:
        if Path(cand).exists():
            try:
                return ImageFont.truetype(cand, px)
            except Exception:
                continue
    # last resort: PIL bitmap default (not scalable, but never crashes)
    return ImageFont.load_default()


def apply_watermark(
    image_path: str | Path,
    text: str,
    *,
    position: str = "bottom-right",
    opacity: float = 0.6,
    color: str = "#FFFFFF",
    font_size_frac: float = 0.034,
    margin_frac: float = 0.028,
    shadow: bool = True,
    out_path: str | Path | None = None,
) -> Path:
    """Composite a semi-transparent text watermark onto an image. Returns saved path."""
    from PIL import Image, ImageDraw

    p = Path(image_path)
    img = Image.open(p).convert("RGBA")
    W, H = img.size
    if position not in _POSITIONS:
        position = "bottom-right"

    font_px = max(12, int(W * float(font_size_frac)))
    margin = max(8, int(W * float(margin_frac)))
    font = _load_font(font_px)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Measure text
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        tw, th = r - l, b - t
    except Exception:
        tw, th = draw.textlength(text, font=font), font_px

    if position == "bottom-right":
        x, y = W - tw - margin, H - th - margin - int(th * 0.4)
    elif position == "bottom-left":
        x, y = margin, H - th - margin - int(th * 0.4)
    elif position == "top-right":
        x, y = W - tw - margin, margin
    elif position == "top-left":
        x, y = margin, margin
    else:  # bottom-center
        x, y = (W - tw) // 2, H - th - margin - int(th * 0.4)

    a = max(0, min(255, int(255 * float(opacity))))
    rgb = _hex_to_rgb(color)
    if shadow:
        off = max(1, font_px // 22)
        draw.text((x + off, y + off), text, font=font, fill=(0, 0, 0, int(a * 0.55)))
    draw.text((x, y), text, font=font, fill=(rgb[0], rgb[1], rgb[2], a))

    out = Image.alpha_composite(img, overlay).convert("RGB")
    dst = Path(out_path) if out_path else p
    # preserve PNG; if source was something else, save as PNG to dst suffix
    fmt = "PNG" if dst.suffix.lower() == ".png" else None
    out.save(dst, format=fmt) if fmt else out.save(dst)
    return dst


def load_watermark_config(project_slug: str) -> dict[str, Any] | None:
    """Read projects/{slug}/brand-guideline.yaml :: watermark. Returns None if absent/disabled."""
    if not project_slug:
        return None
    bg = PLUGIN_ROOT / "projects" / project_slug / "brand-guideline.yaml"
    if not bg.exists():
        return None
    try:
        import yaml
        data = yaml.safe_load(bg.read_text(encoding="utf-8")) or {}
    except Exception as e:
        print(f"  watermark: could not parse {bg}: {e}", file=sys.stderr)
        return None
    wm = data.get("watermark")
    if not isinstance(wm, dict) or not wm.get("enabled"):
        return None
    return wm


def apply_from_project(
    image_path: str | Path,
    project_slug: str,
    *,
    is_featured: bool = False,
) -> bool:
    """Apply the project's configured watermark to an image. Returns True if applied."""
    wm = load_watermark_config(project_slug)
    if not wm:
        return False
    if wm.get("apply_to", "all") == "sections" and is_featured:
        return False
    apply_watermark(
        image_path,
        text=wm.get("text", "Project Juliet"),
        position=wm.get("position", "bottom-right"),
        opacity=float(wm.get("opacity", 0.6)),
        color=wm.get("color", "#FFFFFF"),
        font_size_frac=float(wm.get("font_size_frac", 0.034)),
        margin_frac=float(wm.get("margin_frac", 0.028)),
        shadow=bool(wm.get("shadow", True)),
    )
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Stamp a brand watermark onto an image")
    ap.add_argument("image", type=Path)
    ap.add_argument("--text", default=None, help="watermark text (overrides project)")
    ap.add_argument("--project", default=None, help="project slug → read brand-guideline.yaml watermark")
    ap.add_argument("--position", default="bottom-right")
    ap.add_argument("--opacity", type=float, default=0.6)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--is-featured", action="store_true")
    args = ap.parse_args()

    if args.text:
        out = apply_watermark(args.image, args.text, position=args.position,
                              opacity=args.opacity, out_path=args.out)
        print(f"watermarked: {out}")
    elif args.project:
        applied = apply_from_project(args.image, args.project, is_featured=args.is_featured)
        print(f"watermark {'applied' if applied else 'skipped (not enabled / cover excluded)'}: {args.image}")
    else:
        ap.error("provide --text or --project")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
