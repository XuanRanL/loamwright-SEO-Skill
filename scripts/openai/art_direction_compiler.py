"""scripts/openai/art_direction_compiler.py — Strategy A: build shared Art Direction Prefix
+ compile per-image prompts.

Per IMAGE-GENERATION-V3.2-SPEC.md §4. All of an article's images share the same Art Direction
to ensure visual consistency, while individual subjects/composition vary.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ArtDirection:
    visual_style: str
    color_signature: str
    lighting: str
    mood: str
    camera_specs: str
    universal_negatives: str


def build_art_direction(
    *,
    primary_color_hex: str = "#000000",
    secondary_color_hex: str = "#FFFFFF",
    accent_color_hex: str = "",
    format_id: str | None = None,
    voice_pair: str = "professional × general",
    industry: str = "general",
) -> ArtDirection:
    """Construct the Art Direction Prefix shared across all of the article's images."""

    # Map format → visual style
    style_by_format = {
        "listicle": "editorial documentary photography, National Geographic 2026 aesthetic",
        "how-to-guide": "clean instructional photography with subtle stylization",
        "pillar-page": "concept abstract photography with motion and depth",
        "comparison": "split-screen comparison composition, balanced lighting",
        "product-review": "premium product photography with subtle lifestyle context",
        "case-study": "documentary photography, behind-the-scenes authenticity",
        "definition": "explanatory illustration style, clean and informative",
        "data-research": "infographic photography with data-rich elements",
        "news-analysis": "photojournalism style, editorial integrity",
        "personal-story": "first-person perspective, vintage film texture",
        "opinion": "conceptual photography with thoughtful composition",
        "interview": "portrait photography, engaging eye contact",
        "shortlist-validation": "minimal photography, clean isolated subjects",
    }
    visual = style_by_format.get(format_id or "", "editorial documentary photography")

    # Map industry → atmosphere baseline
    industry_lighting = {
        "saas": "natural office lighting with warm desk lamp accents",
        "ecommerce": "bright product photography lighting, slight warm tone",
        "fishing": "golden hour natural daylight, outdoor",
        "fitness": "studio lighting, energetic, contrasty",
        "food": "warm kitchen lighting, appetizing tones",
        "tech": "modern, cool blue accents, clean",
        "health": "soft natural lighting, calm and reassuring",
        "general": "soft natural daylight or golden hour",
    }
    lighting = industry_lighting.get(industry.lower(), "natural daylight or golden hour")

    color_sig = (
        f"primary {primary_color_hex} brand color, secondary {secondary_color_hex}, "
        f"accent {accent_color_hex or 'natural earth tones'}"
    )

    mood_by_voice = {
        "professional": "competent, focused, aspirational",
        "casual": "approachable, warm, relaxed",
        "warm": "empathetic, inviting, conversational",
        "blunt": "direct, no-nonsense, clear",
        "technical": "precise, detailed, expert",
    }
    voice = voice_pair.split("×")[0].strip()
    mood = mood_by_voice.get(voice, "competent, focused")

    camera = "35mm lens, f/4-f/5.6 aperture, shutter 1/500-1/1000"

    universal_negatives = (
        "no text overlays, no watermarks, no captions on image, no stock-photo cliches, "
        "no overly polished commercial look, no AI face tells (extra fingers, melted features), "
        "no logos other than subject's natural gear, no inconsistent lighting"
    )

    return ArtDirection(
        visual_style=visual,
        color_signature=color_sig,
        lighting=lighting,
        mood=mood,
        camera_specs=camera,
        universal_negatives=universal_negatives,
    )


def compile_prompt(prompt_obj: dict, art_direction: ArtDirection) -> str:
    """Compile single-image prompt: Art Direction Prefix + per-slot specifics.

    prompt_obj fields:
        subject, composition, lighting_note, mood_note, negative_prompt
    """
    parts = [
        "[ART DIRECTION — applies to all images in this article]",
        f"Visual style: {art_direction.visual_style}",
        f"Color signature: {art_direction.color_signature}",
        f"Lighting baseline: {art_direction.lighting}",
        f"Mood: {art_direction.mood}",
        f"Camera: {art_direction.camera_specs}",
        f"Universal negatives: {art_direction.universal_negatives}",
        "",
        "[THIS IMAGE]",
        f"Subject: {prompt_obj.get('subject', '')}",
    ]
    if prompt_obj.get("composition"):
        parts.append(f"Composition: {prompt_obj['composition']}")
    if prompt_obj.get("lighting_note"):
        parts.append(f"Specific lighting note: {prompt_obj['lighting_note']}")
    if prompt_obj.get("mood_note"):
        parts.append(f"Specific mood: {prompt_obj['mood_note']}")
    if prompt_obj.get("negative_prompt"):
        parts.append(f"Additional negatives: {prompt_obj['negative_prompt']}")

    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--primary-color", default="#000000")
    ap.add_argument("--secondary-color", default="#FFFFFF")
    ap.add_argument("--accent-color", default="")
    ap.add_argument("--format-id")
    ap.add_argument("--voice-pair", default="professional × general")
    ap.add_argument("--industry", default="general")
    ap.add_argument("--prompts-file", type=Path,
                    help="JSON file with list of per-image prompt objects")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ad = build_art_direction(
        primary_color_hex=args.primary_color,
        secondary_color_hex=args.secondary_color,
        accent_color_hex=args.accent_color,
        format_id=args.format_id,
        voice_pair=args.voice_pair,
        industry=args.industry,
    )

    if args.prompts_file and args.prompts_file.exists():
        prompts = json.loads(args.prompts_file.read_text(encoding="utf-8"))
        compiled = [
            {"compiled_prompt": compile_prompt(p, ad), **p}
            for p in prompts
        ]
        if args.json:
            print(json.dumps({
                "art_direction": ad.__dict__,
                "compiled": compiled,
            }, indent=2, ensure_ascii=False))
        else:
            for i, c in enumerate(compiled):
                print(f"=== Image {i+1} ===")
                print(c["compiled_prompt"])
                print()
    else:
        if args.json:
            print(json.dumps(ad.__dict__, indent=2, ensure_ascii=False))
        else:
            print("Art Direction Prefix:")
            for k, v in ad.__dict__.items():
                print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
