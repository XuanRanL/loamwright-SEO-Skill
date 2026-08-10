"""scripts/image/alt_text_polisher.py — Refine raw alt_text_seed to SEO-friendly alt text.

Used by image-curator agent. Takes the rough alt_text_seed from
image_prompts.json and refines it to:
  - 60-125 chars
  - Descriptive (what's IN the image)
  - Contains primary keyword naturally (when applicable)
  - Does NOT start with "Image of..." / "Picture showing..."
  - Distinguishable from other images in same article
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass


@dataclass
class AltTextResult:
    seed: str
    polished: str
    length: int
    in_band: bool
    contains_primary: bool
    issues: list[str]


def polish(
    seed: str,
    primary_keyword: str = "",
    *,
    min_chars: int = 60,
    max_chars: int = 125,
    forbid_starters: list[str] | None = None,
    include_keyword: bool = False,
) -> AltTextResult:
    """Refine an alt text seed.

    This is a deterministic polishing step. For LLM-quality alt generation,
    use image-curator agent (which calls Claude). This handles guardrails.
    """
    forbid_starters = forbid_starters or [
        "image of ", "picture of ", "picture showing ",
        "photo of ", "graphic of ", "screenshot of ",
        "illustration of ", "image showing ", "photograph of ",
    ]

    text = (seed or "").strip()
    issues = []

    # Strip forbidden starters
    text_lower = text.lower()
    for starter in forbid_starters:
        if text_lower.startswith(starter):
            text = text[len(starter):].strip()
            text_lower = text.lower()
            # Capitalize first letter
            if text:
                text = text[0].upper() + text[1:]
            issues.append(f"Removed forbidden starter '{starter}'")
            break

    # Trim if too long; aim for max - 5 buffer
    if len(text) > max_chars:
        # Try to cut at sentence boundary
        if "." in text[:max_chars]:
            text = text[:max_chars].rsplit(".", 1)[0].strip()
        elif "," in text[:max_chars]:
            text = text[:max_chars].rsplit(",", 1)[0].strip()
        else:
            text = text[:max_chars - 3].strip() + "..."
        issues.append(f"Trimmed to ≤{max_chars} chars")

    # Add keyword if requested and not present
    primary_lower = (primary_keyword or "").lower()
    contains_primary = bool(primary_lower) and primary_lower in text.lower()
    if include_keyword and primary_keyword and not contains_primary:
        # Try to inject keyword naturally
        if len(text) + len(primary_keyword) + 10 <= max_chars:
            text = f"{text} — {primary_keyword}"
            contains_primary = True
            issues.append("Appended primary keyword")

    # Pad if too short (rare; usually means seed was bad)
    if len(text) < min_chars:
        issues.append(f"Below min ({len(text)} < {min_chars} chars); consider regenerating")

    in_band = min_chars <= len(text) <= max_chars

    return AltTextResult(
        seed=seed,
        polished=text,
        length=len(text),
        in_band=in_band,
        contains_primary=contains_primary,
        issues=issues,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Polish image alt text seed")
    ap.add_argument("--seed", required=True)
    ap.add_argument("--primary-keyword", default="")
    ap.add_argument("--include-keyword", action="store_true")
    ap.add_argument("--min", type=int, default=60)
    ap.add_argument("--max", type=int, default=125)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = polish(
        args.seed, args.primary_keyword,
        min_chars=args.min, max_chars=args.max,
        include_keyword=args.include_keyword,
    )

    if args.json:
        print(json.dumps(asdict(r), indent=2, ensure_ascii=False))
    else:
        print(f"Polished: {r.polished}")
        print(f"Length: {r.length} (band {args.min}-{args.max}: {r.in_band})")
        print(f"Primary keyword: {r.contains_primary}")
        if r.issues:
            for i in r.issues:
                print(f"  • {i}")
    return 0 if r.in_band else 1


if __name__ == "__main__":
    sys.exit(main())
