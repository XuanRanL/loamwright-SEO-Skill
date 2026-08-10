"""scripts/image/webp_converter.py — Convert PNG/JPEG to WebP (default q85).

--target-kb is an OPTIONAL cap (off by default since 2026-06-10): the old
always-on <200KB step re-compressed 2K/4K sources to ~q75 and undid the
quality upgrade. Pass it explicitly only when a hard size budget matters.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def convert(input_path: Path, output_path: Path | None = None,
             *, quality: int = 85, lossless: bool = False) -> Path:
    """Convert image to WebP."""
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Pillow not installed") from e

    if not output_path:
        output_path = input_path.with_suffix(".webp")

    img = Image.open(input_path)
    # lossless is honored for BOTH branches (pre-2026-06-10 the RGB branch
    # silently dropped it — --lossless on a plain RGB PNG produced lossy q80).
    # In lossless mode PIL reinterprets `quality` as compression effort 0-100.
    # WebP hard limit is 16383px/edge, so 2K/4K sources are well within range.
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        # Keep alpha
        img.save(output_path, "WEBP", quality=quality, lossless=lossless, method=6)
    else:
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(output_path, "WEBP", quality=quality, lossless=lossless, method=6)
    return output_path


def compress_to_target(path: Path, *, target_kb: int = 200, min_quality: int = 60) -> int:
    """Lower quality until file size ≤ target_kb. Returns final quality used."""
    try:
        from PIL import Image
    except ImportError:
        return 0
    img = Image.open(path)
    quality = 90
    while quality >= min_quality:
        if img.mode in ("RGBA", "LA"):
            img.save(path, "WEBP", quality=quality, method=6)
        else:
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(path, "WEBP", quality=quality, method=6)
        size_kb = path.stat().st_size / 1024
        if size_kb <= target_kb:
            return quality
        quality -= 5
    return min_quality


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert image to WebP")
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    # Default q85 since 2026-06-10 (4K migration): a 3840x2160 q85 cover lands
    # ~268KB with better per-pixel fidelity than 2K q90 (resolution dilutes the
    # quantization error). Measured mean-abs-diff 1.01/255 vs source.
    ap.add_argument("-q", "--quality", type=int, default=85)
    ap.add_argument("--lossless", action="store_true")
    ap.add_argument("--target-kb", type=int, help="Compress to this target")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"Not found: {args.input}", file=sys.stderr)
        return 2

    try:
        out = convert(args.input, args.output, quality=args.quality, lossless=args.lossless)
        if args.target_kb:
            final_q = compress_to_target(out, target_kb=args.target_kb)
            print(f"Compressed at quality={final_q}", file=sys.stderr)
        size_kb = out.stat().st_size / 1024
        print(f"Wrote {out} ({size_kb:.1f} KB)")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
