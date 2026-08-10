"""scripts/image/srcset_generator.py — Generate 3 responsive image variants."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


# 4K source tier since 2026-06-10 (covers 3840x2160, sections 2880x2880).
# Derivative widths stay ≤2048 — the full-size original IS the largest srcset
# entry; browsers rarely need >2048 in content columns.
DEFAULT_WIDTHS = [480, 1024, 2048]
COVER_WIDTHS = [480, 1024, 2048]


def generate(
    input_path: Path,
    output_dir: Path | None = None,
    *,
    widths: list[int] | None = None,
    quality: int = 85,
    suffix_template: str = "{stem}-{w}w{ext}",
) -> dict[int, Path]:
    """Generate srcset variants at given widths.

    Returns dict {width: output_path}.
    """
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Pillow not installed") from e

    widths = widths or DEFAULT_WIDTHS
    output_dir = output_dir or input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    img = Image.open(input_path)
    ratio = img.height / img.width
    out_paths = {}
    ext = input_path.suffix.lower()
    fmt = "WEBP" if ext == ".webp" else ("PNG" if ext == ".png" else "JPEG")

    for w in widths:
        if w >= img.width:
            # Don't upscale; just copy
            target_h = img.height
            target_w = img.width
        else:
            target_w = w
            target_h = int(w * ratio)

        resized = img.resize((target_w, target_h), Image.LANCZOS)
        out_path = output_dir / suffix_template.format(
            stem=input_path.stem, w=w, ext=ext)
        if fmt == "WEBP":
            resized.save(out_path, "WEBP", quality=quality, method=6)
        elif fmt == "PNG":
            resized.save(out_path, "PNG", optimize=True)
        else:
            if resized.mode != "RGB":
                resized = resized.convert("RGB")
            resized.save(out_path, "JPEG", quality=quality, optimize=True)
        out_paths[w] = out_path

    return out_paths


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate srcset image variants")
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output-dir", type=Path)
    ap.add_argument("--widths", type=int, nargs="+", default=DEFAULT_WIDTHS)
    ap.add_argument("--cover", action="store_true",
                    help="Use cover widths (480/1024/2048)")
    ap.add_argument("--quality", type=int, default=85)
    args = ap.parse_args()

    if not args.input.exists():
        print(f"Not found: {args.input}", file=sys.stderr)
        return 2

    widths = COVER_WIDTHS if args.cover else args.widths
    try:
        out = generate(args.input, args.output_dir, widths=widths, quality=args.quality)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    for w, p in out.items():
        size_kb = p.stat().st_size / 1024
        print(f"  {w}w: {p}  ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
