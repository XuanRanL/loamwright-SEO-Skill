"""
scripts/openai/product_photo_editor.py — re-scene a REAL product photo, preserve the pack.

Pure, unit-tested logic:
  - build_edit_prompt: instructs the edit model to keep the real product unchanged, set the
    new scene, and apply the PROJECT's policy (product_noun, ymyl_clause, style_clause come
    from config — this builder carries no vertical-specific wording) + the people choice.
  - build_center_mask: a geometric preserve-mask (opaque center = keep the product,
    transparent edges = edit the background) — used when pixel-locking the real pack via
    the relay's /v1/images/edits (mask param is honored).
  - fit_to_tier: the chatgpt-code /edits endpoint always returns ~1254² square regardless
    of requested size, so we center-crop to the target aspect and Lanczos-resize to the
    exact 4K tier dimensions ourselves.

Network wrappers (edit_relay / edit_vertex) are thin and validated by live --smoke runs.
"""
from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw

_LANCZOS = Image.Resampling.LANCZOS


_DEFAULT_STYLE_CLAUSE = (
    "Premium editorial product still-life, photorealistic, soft reflection, shallow depth of field."
)


def build_edit_prompt(
    scene: str,
    brand: str = "",
    preserve: bool = True,
    people: bool = False,
    *,
    product_noun: str = "product",
    ymyl_clause: str = "",
    style_clause: str = "",
) -> str:
    """Build the /edits prompt: keep the real product, set the scene, apply project policy.

    Domain-neutral by default. A project supplies ``product_noun`` (e.g. "age-restricted product pack"),
    its house ``style_clause`` (art direction), and any ``ymyl_clause`` constraints — so this
    skill-level builder carries no vertical-specific (e.g. vertical/YMYL) wording.
    """
    parts: list[str] = []
    if preserve:
        noun = product_noun.strip() or "product"
        subject = f"the {brand.strip()} {noun}" if brand.strip() else f"the {noun}"
        parts.append(
            f"Keep {subject} EXACTLY as-is — its real brand logo, characters, colours and printed "
            f"text must stay completely unchanged and perfectly legible. Only replace the "
            f"surrounding scene/background."
        )
    else:
        parts.append("Re-scene this product photo.")
    parts.append(f"New scene: {scene.strip()}.")
    parts.append(style_clause.strip() or _DEFAULT_STYLE_CLAUSE)
    parts.append("A person may appear naturally in the scene." if people else "No people.")
    if ymyl_clause.strip():
        parts.append(ymyl_clause.strip())
    parts.append("No added text overlays; no competing retailer logos.")
    return " ".join(parts)


def build_center_mask(size: tuple[int, int], keep_box_frac: float = 0.6) -> Image.Image:
    """Return an RGBA mask: opaque center box (=keep) over a transparent field (=edit).

    OpenAI /edits semantics: transparent (alpha 0) areas are edited, opaque areas kept.
    So the product (centered) is opaque and the background is transparent.
    """
    w, h = size
    mask = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    box_w, box_h = int(w * keep_box_frac), int(h * keep_box_frac)
    x0, y0 = (w - box_w) // 2, (h - box_h) // 2
    ImageDraw.Draw(mask).rectangle([x0, y0, x0 + box_w, y0 + box_h], fill=(255, 255, 255, 255))
    return mask


def fit_to_tier(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Center-crop ``img`` to the target aspect, then resize to exactly (target_w, target_h)."""
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        # source too wide → crop the sides
        new_w = max(1, int(round(src_h * target_ratio)))
        new_h = src_h
    else:
        # source too tall (or equal) → crop top/bottom
        new_w = src_w
        new_h = max(1, int(round(src_w / target_ratio)))
    left = (src_w - new_w) // 2
    top = (src_h - new_h) // 2
    cropped = img.crop((left, top, left + new_w, top + new_h))
    return cropped.resize((target_w, target_h), _LANCZOS)


# Gemini imageConfig supported aspect ratios; anything else falls back to square.
_GEMINI_ASPECTS = frozenset({"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"})


def vertex_aspect(aspect: str) -> str:
    """Map a requested aspect to a Gemini imageConfig aspectRatio (default square)."""
    a = aspect.strip()
    return a if a in _GEMINI_ASPECTS else "1:1"


# ─── Network wrappers (thin; validated by live --smoke runs) ───────────────────


def _resolve_relay() -> tuple[str, str, str]:
    """Return (base_url, model, api_key) for the OpenAI-compatible edit relay from config."""
    from scripts._core import image_provider
    for p in image_provider.resolve_providers():
        if p.protocol == "openai" and p.base_url:
            return p.base_url, p.model, p.api_key
    raise RuntimeError("no OpenAI-compatible image relay with a base_url found in config.yaml :: image.providers")


def edit_relay(
    image_bytes: bytes,
    prompt: str,
    *,
    mask_bytes: bytes | None = None,
    size: str = "1024x1024",
    timeout: float = 240.0,
) -> bytes:
    """Call the relay's /v1/images/edits (image-to-image). Returns edited PNG bytes.

    NOTE: the chatgpt-code relay returns ~1254² square regardless of ``size``; callers
    must fit_to_tier() the result. The mask param IS honored (opaque=keep, transparent=edit).
    """
    import base64
    import httpx
    base_url, model, api_key = _resolve_relay()
    files: dict[str, tuple[str, bytes, str]] = {"image": ("product.png", image_bytes, "image/png")}
    if mask_bytes is not None:
        files["mask"] = ("mask.png", mask_bytes, "image/png")
    data = {"model": model, "prompt": prompt, "n": "1", "size": size}
    with httpx.Client(timeout=timeout) as client:
        r = client.post(f"{base_url.rstrip('/')}/images/edits",
                        headers={"Authorization": f"Bearer {api_key}"}, files=files, data=data)
    r.raise_for_status()
    j = r.json()
    b64 = j["data"][0]["b64_json"]
    return base64.b64decode(b64)


def _resolve_vertex() -> Any:
    """Return the vertex_gemini provider from config, or None."""
    from scripts._core import image_provider
    for p in image_provider.resolve_providers():
        if p.protocol == "vertex_gemini":
            return p
    return None


def edit_vertex(
    image_bytes: bytes,
    prompt: str,
    *,
    aspect: str = "1:1",
    image_size: str = "4K",
    timeout: float = 300.0,
) -> bytes:
    """Edit (re-scene) via Vertex Gemini — native TRUE 4K, best brand-text fidelity.

    Gemini image editing is conversational: the input image is passed as an inlineData
    part alongside the instruction; the real pack is preserved by the prompt. chatgpt-code
    relays degrade to ~1.5MP, so Vertex is the primary edit engine for real 4K.
    """
    import base64
    import httpx
    prov = _resolve_vertex()
    if prov is None:
        raise RuntimeError("no vertex_gemini provider configured in config.yaml :: image.providers")
    base = (prov.base_url or "https://aiplatform.googleapis.com/v1/publishers/google/models").rstrip("/")
    url = f"{base}/{prov.model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [
            {"text": prompt},
            {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(image_bytes).decode()}},
        ]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": vertex_aspect(aspect), "imageSize": image_size},
        },
    }
    resp = httpx.post(url, headers={"x-goog-api-key": prov.api_key, "Content-Type": "application/json"},
                      json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    cand = (data.get("candidates") or [{}])[0]
    for p in ((cand.get("content") or {}).get("parts") or []):
        inline = p.get("inlineData") or p.get("inline_data")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"])
    raise RuntimeError(f"vertex returned no image (finishReason={cand.get('finishReason')})")


def rescene_product(
    image_bytes: bytes,
    scene: str,
    brand: str = "",
    *,
    preserve: bool = True,
    people: bool = False,
    use_mask: bool = False,
    mask_keep_frac: float = 0.62,
    aspect: str = "1:1",
    engine: str = "auto",
    product_noun: str = "product",
    ymyl_clause: str = "",
    style_clause: str = "",
) -> bytes:
    """Re-scene a real product photo, keeping the pack. Returns edited PNG bytes.

    engine (config-switchable via image_sourcing_policy.editing_real_photos.edit_engine):
      - "auto"/"vertex" → Vertex true-4K PRIMARY, chatgpt-code relay FALLBACK (current default;
        chatgpt-code relays now degrade to ~1.5MP / no 4K).
      - "relay"         → chatgpt-code relay PRIMARY, Vertex FALLBACK (use once relay 4K returns).
      - "vertex_only" / "relay_only" → no fallback.
    """
    import io
    prompt = build_edit_prompt(
        scene, brand=brand, preserve=preserve, people=people,
        product_noun=product_noun, ymyl_clause=ymyl_clause, style_clause=style_clause,
    )
    eng = (engine or "auto").strip().lower()

    def _via_vertex() -> bytes:
        return edit_vertex(image_bytes, prompt, aspect=aspect)

    def _via_relay() -> bytes:
        mask_bytes: bytes | None = None
        if use_mask:
            im = Image.open(io.BytesIO(image_bytes))
            mask = build_center_mask(im.size, mask_keep_frac)
            buf = io.BytesIO()
            mask.save(buf, "PNG")
            mask_bytes = buf.getvalue()
        return edit_relay(image_bytes, prompt, mask_bytes=mask_bytes)

    if eng == "vertex_only":
        return _via_vertex()
    if eng == "relay_only":
        return _via_relay()
    if eng == "relay":
        try:
            return _via_relay()
        except Exception:
            return _via_vertex()
    # "auto" / "vertex": Vertex primary, relay fallback
    try:
        return _via_vertex()
    except Exception:
        return _via_relay()
