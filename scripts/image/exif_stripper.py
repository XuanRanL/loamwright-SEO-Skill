"""scripts/image/exif_stripper.py — Strip EXIF metadata from images (privacy)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def strip(input_path: Path, output_path: Path | None = None) -> Path:
    """Strip all EXIF + IPTC + XMP metadata.

    Pillow approach: load → save without EXIF preservation.
    """
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Pillow not installed") from e

    if not output_path:
        output_path = input_path

    img = Image.open(input_path)
    # Create new image without metadata
    data = list(img.getdata())
    new_img = Image.new(img.mode, img.size)
    new_img.putdata(data)
    # Save without exif parameter
    fmt = (input_path.suffix.lower().lstrip(".") or "png").upper()
    if fmt == "JPG":
        fmt = "JPEG"
    new_img.save(output_path, format=fmt)
    return output_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Strip EXIF metadata")
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="If not given, overwrites input")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"Not found: {args.input}", file=sys.stderr)
        return 2
    try:
        out = strip(args.input, args.output)
        print(f"Stripped EXIF: {out}")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
