"""scripts/build/slug_generator.py — SEO slug generator (kebab-case, ≤40 chars, contains primary keyword)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "of", "in", "on", "at", "to",
    "for", "with", "from", "by", "as", "this", "that", "these", "those",
}


@dataclass
class SlugResult:
    slug: str
    length: int
    contains_primary: bool
    stopwords_removed: list[str]
    in_band: bool


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"['']s\b", "s", s)            # apostrophe-s → s
    s = re.sub(r"&", "and", s)
    s = re.sub(r"[^\w\s-]", "", s)            # strip non-word
    s = re.sub(r"\s+", "-", s)                # space → hyphen
    s = re.sub(r"-+", "-", s)                 # collapse
    return s.strip("-")


def generate(
    title: str,
    primary_keyword: str,
    *,
    max_length: int = 40,
    remove_stopwords: bool = True,
) -> SlugResult:
    """Generate SEO slug from title + primary keyword.

    Strategy:
      1. Slugify title
      2. If too long (> max_length), remove stopwords
      3. If still too long, truncate (but preserve primary_keyword tokens)
      4. If primary_keyword tokens missing, prepend them
    """
    primary_tokens = slugify(primary_keyword).split("-")
    primary_set = set(t for t in primary_tokens if t)

    slug = slugify(title)
    tokens = slug.split("-")
    removed: list[str] = []

    # Always keep primary keyword tokens; remove stopwords first if too long
    if remove_stopwords and len("-".join(tokens)) > max_length:
        new_tokens = []
        for t in tokens:
            if t in STOPWORDS and t not in primary_set:
                removed.append(t)
            else:
                new_tokens.append(t)
        tokens = new_tokens

    # Truncate from end if still too long, but preserve primary
    while len("-".join(tokens)) > max_length and len(tokens) > 1:
        # Try removing last token (unless it's in primary set)
        if tokens[-1] not in primary_set:
            tokens.pop()
        else:
            # Remove a non-primary token from middle
            for i in range(len(tokens) - 1, -1, -1):
                if tokens[i] not in primary_set:
                    tokens.pop(i)
                    break
            else:
                break  # all are primary

    # If primary keyword tokens missing entirely, prepend
    final_set = set(tokens)
    missing = [t for t in primary_tokens if t and t not in final_set]
    if missing:
        # Insert missing at start, respecting length
        prefix = "-".join(missing)
        candidate = f"{prefix}-{'-'.join(tokens)}"
        if len(candidate) <= max_length:
            tokens = candidate.split("-")
        else:
            # Replace from end until fits
            while len(candidate) > max_length and tokens:
                tokens.pop()
                candidate = f"{prefix}-{'-'.join(tokens)}" if tokens else prefix
            tokens = candidate.split("-")

    final_slug = "-".join(t for t in tokens if t)[:max_length]
    final_slug = final_slug.rstrip("-")

    contains_primary = all(t in final_slug for t in primary_tokens if t)
    in_band = bool(final_slug) and len(final_slug) <= max_length

    return SlugResult(
        slug=final_slug,
        length=len(final_slug),
        contains_primary=contains_primary,
        stopwords_removed=removed,
        in_band=in_band,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--primary", required=True, help="Primary keyword")
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument("--keep-stopwords", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = generate(args.title, args.primary, max_length=args.max,
                 remove_stopwords=not args.keep_stopwords)

    if args.json:
        print(json.dumps(asdict(r), indent=2, ensure_ascii=False))
    else:
        print(f"Slug:        {r.slug}")
        print(f"Length:      {r.length}/{args.max}")
        print(f"Primary in:  {r.contains_primary}")
        print(f"Removed:     {r.stopwords_removed}")
    return 0 if r.in_band and r.contains_primary else 1


if __name__ == "__main__":
    sys.exit(main())
