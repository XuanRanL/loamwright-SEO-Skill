"""scripts/image/image_seo_filename.py — Generate SEO-friendly image filenames."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def seo_filename(
    article_slug: str,
    purpose: str,
    *,
    width: int | None = None,
    extension: str = ".webp",
    max_length: int = 80,
) -> str:
    """Build SEO-friendly filename.

    Examples:
      seo_filename("best-fishing-rods-2026", "cover")
        → "best-fishing-rods-2026-cover.webp"
      seo_filename("best-fishing-rods-2026", "gloomis-nrx-rod", width=1024)
        → "best-fishing-rods-2026-gloomis-nrx-rod-1024w.webp"
    """
    def slugify(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"\s+", "-", s)
        s = re.sub(r"-+", "-", s).strip("-")
        return s

    article_part = slugify(article_slug)[:30]
    purpose_part = slugify(purpose)[:30]
    width_part = f"-{width}w" if width else ""
    ext = extension if extension.startswith(".") else f".{extension}"

    base = f"{article_part}-{purpose_part}{width_part}"
    if len(base) + len(ext) > max_length:
        budget = max_length - len(ext) - len(width_part) - len(purpose_part) - 2
        if budget > 5:
            article_part = article_part[:budget]
            base = f"{article_part}-{purpose_part}{width_part}"
        else:
            base = base[: max_length - len(ext)]
    return base + ext


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate SEO image filename")
    ap.add_argument("--slug", required=True, help="Article slug")
    ap.add_argument("--purpose", required=True, help="Image purpose (e.g. 'cover', 'methodology')")
    ap.add_argument("--width", type=int, help="srcset width if any")
    ap.add_argument("--ext", default=".webp")
    ap.add_argument("--max", type=int, default=80)
    args = ap.parse_args()

    print(seo_filename(args.slug, args.purpose, width=args.width,
                        extension=args.ext, max_length=args.max))
    return 0


if __name__ == "__main__":
    sys.exit(main())
