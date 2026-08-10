"""scripts/openai/openai_image_pipeline.py — Unified image-generation pipeline.

This is the canonical entrypoint for generating article images. Replaces the
ad-hoc realtime fallback pattern (every operator writing their own one-off
realtime_images.py) with a single tool.

PROVIDER MODEL (2026-06-06): realtime routes through a configurable provider
chain (scripts/_core/image_provider.py) — a PRIMARY relay (openclawroot, an
OpenAI-compatible gateway; faster/cheaper; token-billed; NO Batch API) with an
automatic per-slot FALLBACK to official OpenAI. Mode defaults to realtime
(config.yaml :: image.default_mode); the canonical orchestrator passes
--mode realtime. Behaviour by mode:

  realtime : provider chain (relay primary → official fallback), parallel max_workers=4
  auto     : OFFICIAL OpenAI Batch first → realtime fallback (bypasses the relay
             as primary — legacy; avoid unless you specifically want official batch)
  batch    : OFFICIAL OpenAI Batch only, no fallback (overnight bulk)

  In all paths: writes wp_publisher-compatible images.json + an audit trail.

Design context: 2026-05-21 research established realtime-parallel as the default
(batch's 1-24h wait is unacceptable for interactive runs); 2026-06-06 added the
relay primary + official fallback. The batch flow (openai_batch_image_api.py) is
official-only and reached only via mode=auto/batch.
  - 24h "validating" stalls are a real, documented OpenAI service issue
    (community threads Sep 2025, Oct 2025, Mar-Apr 2026)
  - Typical image-batch completion is 2-15 min when the service is healthy
  - The "stuck in validating → fall back to realtime" pattern from the last 24h
    was operator-driven and produced ~$1 in unnecessary realtime cost
  - Need: a tool that PATIENT-POLLS batch but EVENTUALLY falls back, automatically

CLI:
    python -m scripts.openai.openai_image_pipeline generate \
        --requests-file PATH \
        --workspace PATH \
        [--task-id STR] \
        [--mode auto|batch|realtime]  (default: config image.default_mode, else realtime)
        [--max-wait-minutes N]        (default: 25)
        [--poll-interval-seconds N]   (default: 60)
        [--no-fallback]               (batch-only, no realtime backup)
        [--allow-partial]             (write images.json even with missing slots)
        [--dry-run]
        [--json]

Input file (image_prompts.json or equivalent):
    [
      {
        "slot": "cover",                  # required, becomes custom_id + filename
        "prompt": "...",                  # required
        "size": "1536x1024",              # default 1024x1024
        "quality": "high",                # default high
        "alt": "...",                     # used in images.json
        "caption": "...",                 # used in images.json (optional)
        "title": "...",                   # used in images.json (optional)
        "is_featured": false              # default true for slot=='cover'
      },
      ...
    ]

Output files in workspace dir:
    images/{slot}.png × N
    images_manifest.json         # detailed audit (mode used, per-slot cost, errors)
    images.json                  # wp_publisher-compatible (slot_id, path, alt, ...)
    batch_status.json            # last poll result (for resume)
    image_pipeline.log           # chronological log lines

Exit codes:
    0 — all requested images generated (possibly via mixed batch+realtime)
    1 — partial failure (use --allow-partial to suppress)
    2 — total failure (no images generated)
    3 — config / input error (before any API call)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import re
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

# Make sure we can import scripts._core when run as a file (not -m)
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts._core import cost_ledger
from scripts._core.image_prompts import is_cover_slot as _core_is_cover_slot
from scripts.openai.openai_batch_image_api import (
    BatchImageRequest,
    BatchStatus,
    submit_batch,
    poll_status,
    download_results,
)


# ─── Constants ──────────────────────────────────────────────────────

# Terminal batch states (we should NOT keep polling these)
BATCH_TERMINAL_FAILURE = {"failed", "expired", "cancelled"}
BATCH_TERMINAL_SUCCESS = {"completed"}
BATCH_TRANSIENT = {"validating", "in_progress", "finalizing", "cancelling"}

DEFAULT_MAX_WAIT_MINUTES = 25
DEFAULT_POLL_INTERVAL_SECONDS = 60
# 4K defaults since 2026-06-10 (chatgpt-code primary, 2K/4K same credit price).
# gpt-image-2 caps total pixels at 8,294,400 (= 3840x2160 exactly), so the max
# square is 2880x2880 — NOT 3840x3840.
DEFAULT_SIZE = "2880x2880"
DEFAULT_QUALITY = "high"

# 4K tier table (aspect_ratio → size). Every value is a multiple of 16, long edge
# ≤ 3840, total pixels ≤ gpt-image-2's 8,294,400 hard cap (16:9 and 1:1 sit AT it).
_AR_TO_4K: dict[str, str] = {
    "16:9": "3840x2160", "4:3": "3264x2448", "3:2": "3456x2304",
    "1:1": "2880x2880", "9:16": "2160x3840", "2:3": "2304x3456",
    "3:4": "2448x3264",
}
# Photo slots MUST ship at 4K. Any photo whose long edge is below this is a legacy
# sub-4K request (1024 / 1536) that would silently downgrade the image, so it gets
# snapped up to the nearest 4K tier. (2160 = the short edge of the 16:9 tier — the
# smallest long-edge among the 4K tiers, so genuine 4K sizes always clear it.)
_MIN_LONG_EDGE_4K = 2160


def _enforce_4k_floor(size: str, aspect_ratio: str | None = None) -> str:
    """Snap a sub-4K *photo* size up to the nearest 4K tier.

    The 4K defaults (2026-06-10) are only the fallback used when no size is given;
    an explicit legacy size (1024x1024 / 1536x1024) emitted by image-prompt-designer
    would otherwise win and silently downgrade the photo (the 2026-06-15 audit found
    ~4/6 recent articles shipping 1024/1536 photos for exactly this reason). This
    floor guarantees every photo ships at 4K regardless of what the designer wrote.
    Chart slots never reach here (filtered out before _adapt_entry), so charts are
    unaffected. No-ops on unparseable input — never blocks generation on a tooling gap.
    """
    try:
        w, h = (int(p) for p in str(size).lower().split("x"))
    except Exception:
        return size
    if max(w, h) >= _MIN_LONG_EDGE_4K:
        return size  # already 4K-class — respect it
    # Prefer the declared aspect ratio's tier; else snap by the size's own ratio.
    if aspect_ratio and aspect_ratio in _AR_TO_4K:
        return _AR_TO_4K[aspect_ratio]
    ratio = (w / h) if h else 1.0
    return min(
        _AR_TO_4K.values(),
        key=lambda s: abs((int(s.split("x")[0]) / int(s.split("x")[1])) - ratio),
    )


def _verify_saved_dimensions(img_path: Path, expected_size: str, provider: str) -> None:
    """Hard-verify the saved file's pixel dimensions match the requested size.

    Relays can return HTTP success with silently-degraded resolution (openclawroot
    serves 1672x941 for ANY custom size, verified 2026-06-09). A mismatch must
    fail the slot so the provider chain falls through to one that honors the size.
    Raises RuntimeError on mismatch; no-ops if Pillow is unavailable or the
    expected size is unparseable (never blocks generation on tooling gaps).
    """
    try:
        exp_w, exp_h = (int(p) for p in expected_size.lower().split("x"))
    except Exception:
        return
    try:
        from PIL import Image
        with Image.open(img_path) as im:
            actual_w, actual_h = im.size
    except ImportError:
        print("⚠ Pillow unavailable — skipping saved-dimension verification", file=sys.stderr)
        return
    except Exception as e:
        raise RuntimeError(f"saved image unreadable for dimension check: {e}") from e
    if (actual_w, actual_h) != (exp_w, exp_h):
        raise RuntimeError(
            f"dimension mismatch from provider={provider}: requested {expected_size}, "
            f"got {actual_w}x{actual_h} (silent degradation — failing slot over to next provider)"
        )


# ─── Vertex AI (Gemini 3 Pro Image / Nano Banana Pro) provider ──────
# NOT OpenAI-compatible: uses Vertex express generateContent + imageConfig and
# returns the image in candidates[].content.parts[].inlineData. Always requests
# the 4K tier (~16MP) then downscales to the pipeline's requested pixel size so
# the exact-match dimension gate passes and WebP/file sizes stay sane. The AQ.
# key authenticates via the x-goog-api-key header (Vertex express only — it is
# rejected by AI Studio generativelanguage). See memory
# reference_vertex_gemini_4k_image_recipe.

# Gemini imageConfig supported aspect ratios → ratio value, for nearest-match.
_GEMINI_ASPECTS: list[tuple[float, str]] = [
    (1 / 1, "1:1"), (16 / 9, "16:9"), (9 / 16, "9:16"), (4 / 3, "4:3"),
    (3 / 4, "3:4"), (3 / 2, "3:2"), (2 / 3, "2:3"), (21 / 9, "21:9"),
]


def _size_to_gemini_imageconfig(size: str, image_size: str = "4K") -> tuple[str, str]:
    """Map a pixel 'WxH' to (aspectRatio, imageSize) for Gemini imageConfig.

    imageSize is always the 4K tier (Nano Banana Pro 4K ≈ 16MP); the exact
    requested pixels are produced by a post-generation downscale. aspectRatio is
    the supported tier nearest the requested W:H. Unparseable size → 16:9 4K.
    """
    try:
        w, h = (int(x) for x in str(size).lower().split("x"))
        ratio = w / h
    except Exception:
        return ("16:9", image_size)
    best = min(_GEMINI_ASPECTS, key=lambda t: abs(t[0] - ratio))
    return (best[1], image_size)


def _downscale_to_size(img_bytes: bytes, target_size: str) -> bytes:
    """Resize generated image bytes to EXACTLY target_size ('WxH').

    Gemini's 4K tier returns ~16MP at a slightly-wider-than-target ratio
    (16:9 4K = 5504x3072 = 1.792:1 vs UHD 3840x2160 = 1.778:1). Center-crop to
    the target aspect first (no distortion), then Lanczos-downscale to exact
    target pixels. No-op (returns input) if PIL is unavailable, the target is
    unparseable, or the image already matches — never fails generation on a
    tooling gap.
    """
    try:
        tw, th = (int(x) for x in str(target_size).lower().split("x"))
    except Exception:
        return img_bytes
    try:
        import io
        from PIL import Image
    except ImportError:
        print("⚠ Pillow unavailable — skipping vertex downscale", file=sys.stderr)
        return img_bytes
    with Image.open(io.BytesIO(img_bytes)) as im:
        im = im.convert("RGB")
        w, h = im.size
        if (w, h) == (tw, th):
            return img_bytes
        target_ratio, src_ratio = tw / th, w / h
        if src_ratio > target_ratio:        # too wide → crop width
            new_w = int(round(h * target_ratio))
            left = (w - new_w) // 2
            im = im.crop((left, 0, left + new_w, h))
        elif src_ratio < target_ratio:      # too tall → crop height
            new_h = int(round(w / target_ratio))
            top = (h - new_h) // 2
            im = im.crop((0, top, w, top + new_h))
        im = im.resize((tw, th), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()


def _generate_vertex_gemini(prov: Any, spec: ImagePromptSpec) -> bytes:
    """Generate ONE image via Vertex AI express mode (Gemini 3 Pro Image).

    Returns PNG bytes already downscaled to spec.size. Raises on HTTP error or a
    response with no image (e.g. safety block) so the provider loop falls over to
    the official-OpenAI fallback. Transient errors (5xx/429/timeout) are matched
    by the caller's _is_transient_error for the one-shot same-provider retry.
    """
    import httpx
    aspect, image_size = _size_to_gemini_imageconfig(spec.size)
    base = (prov.base_url or
            "https://aiplatform.googleapis.com/v1/publishers/google/models").rstrip("/")
    url = f"{base}/{prov.model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": spec.prompt}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": aspect, "imageSize": image_size},
        },
    }
    headers = {"x-goog-api-key": prov.api_key, "Content-Type": "application/json"}
    resp = httpx.post(url, headers=headers, json=body, timeout=300.0)
    if resp.status_code >= 400:
        msg = f"vertex-gemini HTTP {resp.status_code}: {resp.text[:300]}"
        # 429 (RESOURCE_EXHAUSTED, incl. dynamic-shared-quota contention) and 5xx
        # are transient → surface as _TransientImageError so the caller retries the
        # SAME provider with patient backoff instead of leaking the slot to the
        # paid OpenAI fallback. Honor google.rpc.RetryInfo.retryDelay when present
        # (this Express key usually returns empty details[] → truncated-exp backoff).
        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            raise _TransientImageError(msg, retry_after=_parse_retry_delay(resp.text))
        raise RuntimeError(msg)
    data = resp.json()
    cand = (data.get("candidates") or [{}])[0]
    parts = ((cand.get("content") or {}).get("parts") or [])
    for p in parts:
        inline = p.get("inlineData") or p.get("inline_data")
        if inline and inline.get("data"):
            return _downscale_to_size(base64.b64decode(inline["data"]), spec.size)
    raise RuntimeError(
        f"vertex-gemini returned no image (finishReason={cand.get('finishReason')}, "
        f"promptFeedback={data.get('promptFeedback')})"
    )


# ── Transient-failure handling + patient retry (v3.18.0, 2026-06-18) ──────────
#
# Root cause of the 2026-06-18 Gemini→OpenAI fallback: Vertex AI **Express mode**
# serves the preview image model `gemini-3-pro-image-preview` on Google's
# **dynamic shared quota** (DSQ). Firing the per-article photo slots in PARALLEL
# bursts the per-minute capacity → instant HTTP 429 RESOURCE_EXHAUSTED. The old
# logic did ONE 60s retry then leaked the slot to the paid OpenAI fallback.
#
# Empirically (2026-06-18 probe on the live key): a SERIAL request → 200 OK; a
# burst of 3 concurrent → 1×200 + 2×429. The 429 body carries empty details[]
# (no RetryInfo, no Retry-After header) → pure truncated-exponential backoff.
# Google's guidance for DSQ 429: serialize + honor RetryInfo.retryDelay +
# truncated-exp backoff (cap ~60s) + jitter + retry to a wall-clock deadline.
# With hours of pipeline budget we retry patiently and (almost) never fall back.
# Tunable via env (XS_VERTEX_*/XS_IMAGE_*) for ops without a code change.

class _TransientImageError(RuntimeError):
    """A retryable image-gen failure (429/5xx). Carries an optional server-advised
    retry delay (seconds) parsed from google.rpc.RetryInfo.retryDelay."""
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


# String markers for OpenAI/relay providers that raise plain exceptions (the SDK
# gives no structured 429). Dimension-mismatch is deliberately absent
# (deterministic degradation — retrying just wastes a paid generation).
_RETRYABLE_MARKERS = ("524", "502", "503", "504", "429", "timeout", "timed out",
                      "resource exhausted", "connection error", "connection reset")


def _is_transient_error(e: Exception) -> bool:
    if isinstance(e, _TransientImageError):
        return True
    s = str(e).lower()
    return any(m in s for m in _RETRYABLE_MARKERS)


def _parse_retry_delay(resp_text: str) -> float | None:
    """Extract the server-advised retry delay (seconds) from a Google 429 body.

    Prefers google.rpc.RetryInfo.retryDelay ("53s"/"1.5s") in error.details[];
    falls back to a regex on the human message ("Please retry in 53.0s"). Returns
    None when neither is present (this Express key usually returns empty details).
    """
    try:
        data = json.loads(resp_text)
        for d in (data.get("error", {}).get("details") or []):
            if str(d.get("@type", "")).endswith("google.rpc.RetryInfo"):
                rd = d.get("retryDelay")
                if isinstance(rd, str) and rd.endswith("s"):
                    return float(rd[:-1])
    except Exception:
        pass
    m = re.search(r"retry in ([\d.]+)s", resp_text)
    return float(m.group(1)) if m else None


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


@dataclass(frozen=True)
class _RetryPolicy:
    """Per-provider patient-retry parameters (truncated exponential backoff)."""
    max_attempts: int      # total attempts on this provider before falling over
    deadline_s: float      # wall-clock budget for all attempts on this provider
    base_backoff_s: float
    multiplier: float
    max_backoff_s: float
    jitter_s: float


# Vertex (DSQ preview image model): patient. With a long pipeline window we'd
# rather wait minutes on the free, true-4K primary than fall to the paid OpenAI
# fallback. Serialization (below) prevents most 429s; this catches the rest.
_VERTEX_RETRY = _RetryPolicy(
    max_attempts=_env_int("XS_VERTEX_RETRY_MAX_ATTEMPTS", 10),
    deadline_s=_env_float("XS_VERTEX_RETRY_DEADLINE_S", 900.0),
    base_backoff_s=_env_float("XS_VERTEX_RETRY_BASE_S", 20.0),
    multiplier=1.8,
    max_backoff_s=_env_float("XS_VERTEX_RETRY_MAX_BACKOFF_S", 90.0),
    jitter_s=5.0,
)
# OpenAI/relay providers: light (legacy single-retry intent; they rarely 429 and
# the fallback is a last resort, so don't dawdle here).
_DEFAULT_RETRY = _RetryPolicy(
    max_attempts=_env_int("XS_IMAGE_RETRY_MAX_ATTEMPTS", 2),
    deadline_s=_env_float("XS_IMAGE_RETRY_DEADLINE_S", 180.0),
    base_backoff_s=_env_float("XS_IMAGE_RETRY_BASE_S", 60.0),
    multiplier=2.0,
    max_backoff_s=60.0,
    jitter_s=2.0,
)


def _retry_policy_for(prov: Any) -> _RetryPolicy:
    return _VERTEX_RETRY if getattr(prov, "protocol", "openai") == "vertex_gemini" else _DEFAULT_RETRY


def _compute_backoff(policy: _RetryPolicy, attempt: int, retry_after: float | None) -> float:
    """Truncated exponential backoff = MAX(server-advised delay, local exp term)
    + jitter. `attempt` is 1-based (the attempt that just failed)."""
    exp = min(policy.base_backoff_s * (policy.multiplier ** (attempt - 1)), policy.max_backoff_s)
    base = max(float(retry_after or 0.0), exp)
    return base + random.uniform(0.0, policy.jitter_s)


# ── Vertex request throttle: serialize + pace to avoid DSQ burst-429s ─────────
# The single biggest lever (empirically: serial→200, burst→429). Only ONE Vertex
# generateContent is in flight at a time by default, with a minimum interval
# between starts. Other providers (the OpenAI fallback) are unaffected and still
# run in parallel.
_VERTEX_CONCURRENCY = max(1, _env_int("XS_VERTEX_CONCURRENCY", 1))
_VERTEX_MIN_INTERVAL_S = _env_float("XS_VERTEX_MIN_INTERVAL_S", 8.0)
_vertex_sem = threading.BoundedSemaphore(_VERTEX_CONCURRENCY)
_vertex_pace_lock = threading.Lock()
_vertex_last_start = [0.0]


@contextmanager
def _vertex_throttle():
    """Serialize + pace Vertex calls. Held only around the HTTP call, NOT around
    the retry backoff sleep, so a backing-off thread frees the slot for another."""
    _vertex_sem.acquire()
    try:
        with _vertex_pace_lock:
            wait = _vertex_last_start[0] + _VERTEX_MIN_INTERVAL_S - time.time()
            if wait > 0:
                time.sleep(wait)
            _vertex_last_start[0] = time.time()
        yield
    finally:
        _vertex_sem.release()


# ─── Auto-generate image metadata from prompt when fields are missing ──

def _alt_from_prompt(prompt: str) -> str:
    """Extract first sentence (up to 125 chars) as alt text fallback."""
    first_sentence = prompt.split(".")[0].strip()
    if len(first_sentence) > 125:
        first_sentence = first_sentence[:122] + "..."
    return first_sentence

def _caption_from_prompt(prompt: str) -> str:
    """Extract first sentence as caption fallback."""
    return prompt.split(".")[0].strip()


def _seo_filename_fallback(workspace_dir: Path, slot: str, task_id: str) -> str:
    """SEO-stem filename for specs missing filename_seed (v3.36.0 root cure).

    Prefer the article slug so the WP media filename is an SEO stem AND unique
    per article (slugs are unique per post). Order: meta.json::slug (the final
    publish slug) -> angle.json::slug_draft -> legacy '{task_id}_{slot}'."""
    for fname, key in (("meta.json", "slug"), ("angle.json", "slug_draft")):
        try:
            data = json.loads((workspace_dir / fname).read_text(encoding="utf-8"))
            slug = str((data or {}).get(key) or "").strip()
            if slug:
                return f"{slug}-{slot}"
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            continue
    return f"{task_id}_{slot}" if task_id else slot

def _title_from_filename(seed: str) -> str:
    """Convert filename_seed to title case."""
    return seed.replace("-", " ").replace("_", " ").title()

def _desc_from_prompt(prompt: str) -> str:
    """Use first two sentences of prompt as description fallback."""
    parts = prompt.split(".")
    return ". ".join(s.strip() for s in parts[:2] if s.strip()) + "."


# ─── Data classes ────────────────────────────────────────────────────


@dataclass
class ImagePromptSpec:
    """Canonical input record. Accepts both 'slot' and 'custom_id' as the ID field."""
    slot: str
    prompt: str
    size: str = DEFAULT_SIZE
    quality: str = DEFAULT_QUALITY
    alt: str = ""
    caption: str = ""
    title: str = ""
    description: str = ""
    is_featured: bool = False
    filename: str | None = None    # If None, derived from slot

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ImagePromptSpec":
        # Accept slot_id OR slot OR custom_id (slot_id is the canonical key from outline/prompts)
        slot = d.get("slot_id") or d.get("slot") or d.get("custom_id")
        if not slot:
            raise ValueError(f"image prompt entry missing 'slot' or 'custom_id': {d!r}")
        return cls(
            slot=slot,
            prompt=d["prompt"],
            # 4K floor at the canonical constructor so EVERY photo path is covered —
            # including the QA regeneration path (image_regen_slots.py calls from_dict
            # directly, bypassing _adapt_entry). Idempotent: already-4K sizes pass
            # through untouched. Charts never reach from_dict (filtered upstream).
            size=_enforce_4k_floor(d.get("size") or DEFAULT_SIZE, d.get("aspect_ratio")),
            quality=d.get("quality", DEFAULT_QUALITY),
            alt=d.get("alt") or d.get("alt_skeleton") or _alt_from_prompt(d["prompt"]),
            caption=d.get("caption") or _caption_from_prompt(d["prompt"]),
            # `filename_seed` OR `filename`: _adapt_entry RENAMES the designer's
            # `filename_seed` to `filename` before this runs, so reading only
            # `filename_seed` fell through to the slot id and produced titles like
            # "Cover" / "Section 7". WordPress derives the attachment slug from the
            # title, so that shipped media slugs `cover-4` / `section-6` with zero
            # keyword value, fleet-wide, until hand-corrected (found 2026-08-05 on
            # project-alpha posts 37894/37908). The slot id remains the last resort.
            title=d.get("title")
            or _title_from_filename(d.get("filename_seed") or d.get("filename") or slot),
            description=d.get("description") or _desc_from_prompt(d["prompt"]),
            # The COVER is ALWAYS the featured image, even when image-prompts.json
            # carries an explicit is_featured:false (2026-07-01). That flag has a
            # second meaning to the D4/D5 placeholder lint, so designers legitimately
            # write false on the cover — copying it verbatim shipped post 788 with
            # featured_media=0 (wp_publisher has no fallback). Cover detection uses
            # the shared suffix-aware helper (cover / slot-cover / *-cover).
            is_featured=bool(d.get("is_featured")) or _core_is_cover_slot(slot),
            filename=d.get("filename") or d.get("filename_seed"),
        )

    def to_batch_request(self) -> BatchImageRequest:
        return BatchImageRequest(
            custom_id=self.slot,
            prompt=self.prompt,
            size=self.size,
            quality=self.quality,
            n=1,
            output_format="png",
        )


@dataclass
class SlotResult:
    """Per-slot outcome from the pipeline."""
    slot: str
    success: bool
    source: Literal["batch", "realtime", "skipped", "failed"] = "failed"
    image_path: str | None = None
    size_bytes: int = 0
    elapsed_seconds: float = 0
    cost_usd: float = 0
    error: str | None = None


@dataclass
class PipelineResult:
    """Top-level pipeline outcome."""
    task_id: str | None
    mode_requested: str
    mode_used: Literal["batch_only", "realtime_only", "batch_with_realtime_fallback", "no_op_dry_run"]
    total_slots: int
    success_slots: int
    failed_slots: int
    total_cost_usd: float
    total_elapsed_seconds: float
    batch_id: str | None = None
    batch_final_status: str | None = None
    fallback_triggered: bool = False
    fallback_reason: str | None = None
    slots: list[SlotResult] = field(default_factory=list)
    log_path: str | None = None


# ─── Logging ────────────────────────────────────────────────────────


class PipelineLogger:
    """Append-only chronological log. Writes to image_pipeline.log + stderr."""
    def __init__(self, workspace_dir: Path, json_mode: bool = False):
        self.path = workspace_dir / "image_pipeline.log"
        self.json_mode = json_mode
        # Ensure log starts fresh OR appends — use append so resumes preserve history
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, msg: str, level: str = "INFO") -> None:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        line = f"[{ts}] {level:5s} {msg}"
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        if not self.json_mode:
            print(line, file=sys.stderr, flush=True)


# ─── Realtime fallback ──────────────────────────────────────────────


def _watermark_after_save(img_path: Path, out_dir: Path, spec: Any, log: Any) -> None:
    """Apply the project's configured brand watermark to a just-saved image.

    Self-contained + fail-safe: derives project_slug from {workspace}/state.json
    (out_dir is {workspace}/images), reads the watermark config from the project's
    brand-guideline.yaml, and applies it. Any error is logged, never fatal — a
    missing watermark must not fail image generation.
    """
    try:
        import json as _json
        from scripts.openai.image_watermark import apply_from_project
        ws = out_dir.parent
        state_p = ws / "state.json"
        slug = ""
        if state_p.exists():
            slug = (_json.loads(state_p.read_text(encoding="utf-8")) or {}).get("project_slug") or ""
        if slug and apply_from_project(img_path, slug, is_featured=getattr(spec, "is_featured", False)):
            log.log(f"watermark applied slot={getattr(spec, 'slot', '?')}")
    except Exception as e:  # noqa: BLE001 — watermark is best-effort, never fatal
        log.log(f"watermark skipped slot={getattr(spec, 'slot', '?')} err={type(e).__name__}: {e}", level="WARN")


def generate_realtime_one(
    clients: list[tuple[Any, Any]], spec: ImagePromptSpec, out_dir: Path, log: PipelineLogger
) -> SlotResult:
    """Call images.generate for ONE slot, trying each provider in order.

    `clients` is an ordered list of (ImageProvider, openai.OpenAI client) tuples
    — primary first, fallbacks after (see scripts/_core/image_provider.py). On an
    exception from the primary, the next provider is tried automatically. This is
    the "configurable primary + official OpenAI fallback" design (2026-06-06):
    we get the relay's speed/cost while keeping a retreat path if it
    degrades/bans/disappears.

    Returns a SlotResult with cost/error/path populated.
    """
    last_err: Exception | None = None
    n = len(clients)
    # Per-provider PATIENT retry: a transient failure (429/5xx) retries the SAME
    # provider with truncated-exponential backoff until its policy's max_attempts
    # OR wall-clock deadline is hit, ONLY THEN falling over to the next provider.
    # Vertex (DSQ preview model) gets a patient policy + serialization; OpenAI/relay
    # gets a light policy. This keeps cheap free Gemini from leaking to paid OpenAI
    # on a transient 429 burst (the 2026-06-18 incident).
    for i, (prov, client) in enumerate(clients):
        is_vertex = getattr(prov, "protocol", "openai") == "vertex_gemini"
        policy = _retry_policy_for(prov)
        deadline = time.time() + policy.deadline_s
        attempt = 0
        while True:
            attempt += 1
            t0 = time.time()
            try:
                if is_vertex:
                    # Vertex AI express (Gemini 3 Pro Image): own wire protocol;
                    # returns PNG bytes already downscaled to spec.size. Serialize
                    # + pace via the throttle to avoid DSQ burst-429s.
                    with _vertex_throttle():
                        img_bytes = _generate_vertex_gemini(prov, spec)
                else:
                    resp = client.images.generate(
                        model=prov.model,    # model id is per-provider/config now (not hardcoded)
                        prompt=spec.prompt,
                        size=spec.size,
                        quality=spec.quality,
                        n=1,
                        output_format="png",
                    )
                    b64 = resp.data[0].b64_json
                    if not b64:
                        raise RuntimeError("API returned no b64_json")
                    img_bytes = base64.b64decode(b64)
                # Save with the SEO-friendly filename when provided, falling back to
                # slot.png. This avoids wp_media.upload(check_existing_by_filename=True)
                # deduping the cover to a stale prior-article media because the local
                # file was named generically (the 2026-05-21 task 085fb1ba240c bug).
                filename_stem = (spec.filename or spec.slot).strip() or spec.slot
                img_path = out_dir / f"{filename_stem}.png"
                img_path.write_bytes(img_bytes)
                # Hard gate BEFORE watermark/cost: a relay that silently degrades
                # resolution must fail this provider attempt so the loop falls
                # through to the next provider (2026-06-10, openclawroot 1672x941).
                _verify_saved_dimensions(img_path, spec.size, prov.name)
                _watermark_after_save(img_path, out_dir, spec, log)
                elapsed = time.time() - t0
                # Cost estimate: keyed to "gpt-image-2" official per-image table
                # regardless of which provider served (2026-06-06 decision — the relay
                # bills by token; we deliberately over-estimate with the official
                # table so the cost guard stays conservative).
                # Isolated try/except: an estimator gap must NEVER fail a slot whose
                # image already generated (pre-2026-06-10 this raised inside the
                # provider loop → double-billed the slot via pointless fallback).
                if is_vertex:
                    # Vertex bills the Google account, not OpenAI — record $0 so the
                    # OpenAI cost guard/ledger isn't polluted with gpt-image rates.
                    # (Gemini 3 Pro Image 4K ≈ 2000 tokens, an order of magnitude
                    # below OpenAI's ~$1.67/image official rate.)
                    cost = 0.0
                else:
                    try:
                        est = cost_ledger.estimate(
                            "gpt-image-2",
                            image_quality=spec.quality, image_size=spec.size,
                            image_count=1, batch_mode=False,
                        )
                        cost = float(est.estimated_usd)
                    except Exception as est_err:
                        log.log(f"cost estimate unavailable for {spec.quality}/{spec.size} "
                                f"({est_err}) — recording $0", level="WARN")
                        cost = 0.0
                tag = f" provider={prov.name}" + (" (fallback)" if i > 0 else "")
                retag = f" (attempt {attempt})" if attempt > 1 else ""
                log.log(f"realtime OK slot={spec.slot}{tag}{retag} {elapsed:.1f}s {len(img_bytes):,}B ${cost:.4f}")
                return SlotResult(
                    slot=spec.slot, success=True, source="realtime",
                    image_path=str(img_path), size_bytes=len(img_bytes),
                    elapsed_seconds=round(elapsed, 2), cost_usd=cost,
                )
            except Exception as e:
                elapsed = time.time() - t0
                last_err = e
                # Retry the SAME provider while it's a transient error AND we still
                # have attempts + wall-clock budget. The throttle is released (the
                # `with` above has exited), so a sibling slot can use Vertex while
                # this one backs off.
                if _is_transient_error(e) and attempt < policy.max_attempts and time.time() < deadline:
                    backoff = _compute_backoff(policy, attempt, getattr(e, "retry_after", None))
                    remaining = deadline - time.time()
                    backoff = max(0.0, min(backoff, remaining))
                    log.log(
                        f"realtime RETRY slot={spec.slot} provider={prov.name} "
                        f"attempt={attempt}/{policy.max_attempts} {elapsed:.1f}s transient "
                        f"err={e} — retrying same provider in {backoff:.0f}s "
                        f"(deadline in {remaining:.0f}s)",
                        level="WARN",
                    )
                    if backoff > 0:
                        time.sleep(backoff)
                    continue
                # Exhausted (or non-transient) → fall over to the next provider.
                has_next = i < n - 1
                nxt = clients[i + 1][0].name if has_next else None
                reason = ("transient retries exhausted" if _is_transient_error(e) else "non-transient")
                log.log(
                    f"realtime {'WARN' if has_next else 'FAIL'} slot={spec.slot} "
                    f"provider={prov.name} {elapsed:.1f}s {reason} err={e}"
                    + (f" → falling back to {nxt}" if has_next else ""),
                    level="WARN" if has_next else "ERROR",
                )
                break  # advance to the next provider in the outer for-loop
    return SlotResult(
        slot=spec.slot, success=False, source="failed",
        elapsed_seconds=0,
        error=f"all {n} provider(s) failed; last error: {last_err}",
    )


def generate_realtime_all(
    specs: list[ImagePromptSpec], out_dir: Path, log: PipelineLogger,
    *, max_workers: int = 4,
) -> list[SlotResult]:
    """Run realtime generation for every spec — IN PARALLEL up to `max_workers`.

    Each gpt-image-1 realtime call is ~150s. Serial-of-4 = ~10–14 min wall.
    Parallel-of-4 = ~150s wall = 5x speedup, with negligible 429/rate-limit
    risk at standard tier limits (5+ concurrent image requests permitted).

    Order of returned results matches order of input specs (we restore order
    after as_completed() finishes).

    Providers are resolved from config (scripts/_core/image_provider.py): a
    configurable primary (e.g. the openclawroot relay) plus an official OpenAI
    fallback. Each slot tries the primary, then falls back automatically.
    """
    import openai
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from scripts._core import image_provider

    providers = image_provider.resolve_providers(log=log)
    if not providers:
        log.log(
            "realtime: NO image providers resolved (no primary + no official "
            "fallback credential). Failing all slots.",
            level="ERROR",
        )
        return [
            SlotResult(slot=s.slot, success=False, source="failed",
                       error="no image-provider credentials configured "
                             "(set openclawroot.key/OPENCLAWROOT_API_KEY or openai.key/OPENAI_API_KEY)")
            for s in specs
        ]

    clients: list[tuple[Any, Any]] = []
    for p in providers:
        if getattr(p, "protocol", "openai") == "vertex_gemini":
            # Vertex provider is not OpenAI-compatible — no SDK client; the
            # generate branch in generate_realtime_one handles it via httpx.
            clients.append((p, None))
            continue
        kwargs: dict[str, Any] = {"api_key": p.api_key}
        if p.base_url:
            kwargs["base_url"] = p.base_url
        clients.append((p, openai.OpenAI(**kwargs)))

    out_dir.mkdir(parents=True, exist_ok=True)
    workers = min(len(specs), max(1, max_workers))
    chain = " → ".join(f"{p.name}[{p.model}]" for p, _ in clients)
    log.log(
        f"realtime engaged for {len(specs)} slot(s) [parallel max_workers={workers}] "
        f"providers: {chain} :: slots={[s.slot for s in specs]}"
    )

    results_by_slot: dict[str, SlotResult] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(generate_realtime_one, clients, s, out_dir, log): s for s in specs}
        for fut in as_completed(futures):
            r = fut.result()
            results_by_slot[r.slot] = r
    return [results_by_slot[s.slot] for s in specs]


# ─── Batch flow with polling ────────────────────────────────────────


def submit_and_wait(
    specs: list[ImagePromptSpec],
    workspace_dir: Path,
    *,
    task_id: str | None,
    max_wait_minutes: int,
    poll_interval_seconds: int,
    log: PipelineLogger,
) -> tuple[BatchStatus | None, str]:
    """Submit batch, poll until terminal state OR timeout.

    Returns (final_status, terminal_reason). terminal_reason is one of:
        'completed', 'failed', 'expired', 'cancelled', 'timeout', 'submit_error'
    """
    requests = [s.to_batch_request() for s in specs]
    try:
        status = submit_batch(requests, workspace_dir=workspace_dir, task_id=task_id)
    except Exception as e:
        log.log(f"batch submit FAILED: {e}", level="ERROR")
        return None, "submit_error"
    log.log(f"batch submitted id={status.batch_id} status={status.status} requests={status.total_requests}")

    deadline = time.time() + (max_wait_minutes * 60)
    poll_count = 0
    last_status = status.status
    while True:
        if time.time() > deadline:
            log.log(f"batch TIMEOUT after {max_wait_minutes}m (last status: {last_status})", level="WARN")
            return status, "timeout"

        time.sleep(poll_interval_seconds)
        poll_count += 1
        try:
            status = poll_status(status.batch_id)
        except Exception as e:
            log.log(f"poll error (will retry): {e}", level="WARN")
            continue

        # Persist latest status for resume
        try:
            (workspace_dir / "batch_status.json").write_text(
                json.dumps(asdict(status), indent=2), encoding="utf-8"
            )
        except Exception:
            pass

        if status.status != last_status:
            log.log(f"batch state {last_status} → {status.status} "
                    f"(poll #{poll_count}, completed={status.completed_requests}/{status.total_requests})")
            last_status = status.status
        else:
            log.log(f"batch poll #{poll_count} status={status.status} "
                    f"completed={status.completed_requests}/{status.total_requests}", level="DEBUG")

        if status.status in BATCH_TERMINAL_SUCCESS:
            log.log(f"batch COMPLETED total={status.total_requests} "
                    f"success={status.completed_requests} failed={status.failed_requests}")
            return status, "completed"
        if status.status in BATCH_TERMINAL_FAILURE:
            log.log(f"batch terminal FAILURE state={status.status}", level="ERROR")
            return status, status.status


def download_batch_to_slots(
    batch_id: str, out_dir: Path, specs_by_slot: dict[str, ImagePromptSpec],
    log: PipelineLogger,
) -> list[SlotResult]:
    """Download completed batch and convert to SlotResult per slot."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results = download_results(batch_id, out_dir)
    out: list[SlotResult] = []
    for r in results:
        cid = r["custom_id"]
        spec = specs_by_slot.get(cid)
        quality = spec.quality if spec else DEFAULT_QUALITY
        size = spec.size if spec else DEFAULT_SIZE
        if r["success"]:
            try:
                img_bytes = Path(r["image_path"]).read_bytes()
                size_b = len(img_bytes)
            except Exception:
                size_b = 0
            # Same hard gate as realtime: wrong-size batch output marks the slot
            # failed so the realtime fallback regenerates it (2026-06-10).
            try:
                _verify_saved_dimensions(Path(r["image_path"]), size, "batch")
            except RuntimeError as dim_err:
                out.append(SlotResult(slot=cid, success=False, source="failed",
                                      error=str(dim_err)))
                log.log(f"batch slot FAILED slot={cid} err={dim_err}", level="ERROR")
                continue
            # Rename batch-downloaded {custom_id}.png → {filename_seed}.png so
            # wp_media.upload(check_existing_by_filename=True) doesn't dedup the
            # cover to a stale prior-article media (the 2026-05-21 task
            # 085fb1ba240c bug). download_results saves as cid.png by design;
            # we rename post-save when spec.filename is provided.
            saved_path = r["image_path"]
            if spec and spec.filename and spec.filename.strip() and spec.filename != cid:
                target = out_dir / f"{spec.filename.strip()}.png"
                try:
                    Path(r["image_path"]).rename(target)
                    saved_path = str(target)
                except Exception as e:
                    log.log(f"batch rename failed (continuing with original) "
                            f"slot={cid} err={e}", level="WARN")
            # Cost at batch rate (50% off realtime); estimator gaps never fail
            # an already-downloaded slot (2026-06-10).
            try:
                est = cost_ledger.estimate(
                    "gpt-image-2", image_quality=quality, image_size=size,
                    image_count=1, batch_mode=True,
                )
                slot_cost = float(est.estimated_usd)
            except Exception as est_err:
                log.log(f"cost estimate unavailable for {quality}/{size} "
                        f"({est_err}) — recording $0", level="WARN")
                slot_cost = 0.0
            out.append(SlotResult(
                slot=cid, success=True, source="batch",
                image_path=saved_path, size_bytes=size_b,
                cost_usd=slot_cost,
            ))
            log.log(f"batch OK slot={cid} ${slot_cost:.4f}")
        else:
            err = r.get("error")
            err_str = json.dumps(err) if isinstance(err, dict) else str(err)
            out.append(SlotResult(
                slot=cid, success=False, source="failed", error=err_str,
            ))
            log.log(f"batch slot FAILED slot={cid} err={err_str}", level="ERROR")
    # Detect slots that batch didn't return at all (rare but possible)
    returned = {r.slot for r in out}
    for slot in specs_by_slot:
        if slot not in returned:
            out.append(SlotResult(slot=slot, success=False, source="failed",
                                  error="missing from batch output"))
            log.log(f"batch slot MISSING from output slot={slot}", level="ERROR")
    return out


# ─── Orchestration ──────────────────────────────────────────────────


def _join_stage_already_completed(task_id: str) -> bool:
    """True when state.json::stage_history already has a COMPLETED
    'image-pipeline-join' entry.

    Guard for the generate_images self-record: the first full pipeline run owns
    the canonical join stage record; regen invocations (image_regen_slots via
    image-visual-qa) must not append a duplicate completed pair. An OPEN
    in_progress entry does NOT count — file_bus.record_stage_start correctly
    reuses those. Fail-open (False) on any read error so a corrupt state file
    never blocks image generation itself.
    """
    try:
        from scripts._core import file_bus as _fb
        state = _fb.read_state(task_id)
        return any(
            h.get("stage") == "image-pipeline-join" and h.get("status") == "completed"
            for h in state.get("stage_history") or []
        )
    except Exception:
        return False


def generate_images(
    specs: list[ImagePromptSpec],
    workspace_dir: Path,
    *,
    task_id: str | None,
    mode: Literal["auto", "batch", "realtime"] = "realtime",
    max_wait_minutes: int = DEFAULT_MAX_WAIT_MINUTES,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    fallback_enabled: bool = True,
    dry_run: bool = False,
    json_mode: bool = False,
) -> PipelineResult:
    """Top-level orchestration.

    Strategy:
      - mode=batch     : submit batch, wait, download, never fallback
      - mode=realtime  : skip batch entirely, run realtime for all slots
      - mode=auto      : try batch → if terminal failure / timeout → realtime
                         fallback. Batch partial-success → realtime ONLY for
                         failed slots.
    """
    workspace_dir.mkdir(parents=True, exist_ok=True)
    log = PipelineLogger(workspace_dir, json_mode=json_mode)
    log.log(f"=== image pipeline start: mode={mode} slots={len(specs)} dry_run={dry_run} ===")

    # ── Stage tracking (audit 2026-05-22) ─────────────────────────────
    # Record this stage in state.json::stage_history so post-hoc audits can
    # answer "did image generation run?" Only active when task_id is set.
    #
    # Idempotency (2026-07-07 batch audit): this function is ALSO the engine under
    # image_regen_slots.py (the image-visual-qa regen path). A regen run used to
    # append a SECOND completed "image-pipeline-join" pair to stage_history —
    # file_bus.record_stage_start dedups only OPEN in_progress entries, not
    # completed ones. Duplicate entries are precisely the signal operators were
    # told to trust after the 2026-07-07 double-publish postmortem ("read
    # stage_history to check progress"), so benign duplicates are not acceptable
    # noise. Record the canonical join stage only while it has never completed;
    # regen/re-run invocations skip the record.
    _stage_recorded = False
    if task_id and not dry_run:
        try:
            from scripts._core import file_bus as _fb
            # Canonical orchestrator stage name (2026-06-04 audit RC-C): was
            # "image-pipeline", which mismatched the orchestrator's
            # "image-pipeline-join" -> a stray record + the canonical join unstamped.
            if _join_stage_already_completed(task_id):
                log.log("stage_history: image-pipeline-join already completed — "
                        "not re-recording (regen/re-run invocation)")
            else:
                _fb.record_stage_start(task_id, "image-pipeline-join", phase="publish")
                _stage_recorded = True
        except Exception as _e:
            log.log(f"stage_history record_stage_start failed: {_e}", level="WARN")

    out_dir = workspace_dir / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Ensure every spec has a unique filename to prevent cross-article dedup.
    # If filename is still None/empty after from_dict, derive an SEO stem from the
    # article slug (v3.36.0). The 2026-07-06 near-me cover shipped to the media
    # library as '{task_id}_cover.png' because the designer omitted filename_seed
    # and the old fallback used the raw task id — unique, but not an SEO stem.
    # meta.json::slug (final) is preferred, then angle.json::slug_draft; the
    # task_id fallback remains for workspaces without either.
    for s in specs:
        if not s.filename or not s.filename.strip():
            s.filename = _seo_filename_fallback(workspace_dir, s.slot, task_id)

    specs_by_slot = {s.slot: s for s in specs}
    t_start = time.time()

    # Pre-flight cost check (worst case: full realtime)
    worst_case_cost = 0.0
    for s in specs:
        est = cost_ledger.estimate(
            "gpt-image-2", image_quality=s.quality, image_size=s.size,
            image_count=1, batch_mode=False,
        )
        worst_case_cost += float(est.estimated_usd)
    log.log(f"worst-case cost estimate (all realtime): ${worst_case_cost:.4f}")
    decision = cost_ledger.check(worst_case_cost, scope="per_article")
    if decision == "blocked":
        log.log(f"BLOCKED by cost_ledger.check: ${worst_case_cost:.4f} > per_article budget",
                level="ERROR")
        return PipelineResult(
            task_id=task_id, mode_requested=mode, mode_used="no_op_dry_run",
            total_slots=len(specs), success_slots=0, failed_slots=len(specs),
            total_cost_usd=0, total_elapsed_seconds=0,
            fallback_reason="cost_ledger_blocked",
            log_path=str(log.path),
        )

    if dry_run:
        log.log("DRY RUN — no API calls made")
        return PipelineResult(
            task_id=task_id, mode_requested=mode, mode_used="no_op_dry_run",
            total_slots=len(specs), success_slots=0, failed_slots=0,
            total_cost_usd=0, total_elapsed_seconds=round(time.time() - t_start, 2),
            log_path=str(log.path),
        )

    slot_results: list[SlotResult] = []
    batch_id: str | None = None
    batch_final_status: str | None = None
    fallback_triggered = False
    fallback_reason: str | None = None
    mode_used: str

    # ─ Path 1: realtime only ─
    if mode == "realtime":
        slot_results = generate_realtime_all(specs, out_dir, log)
        mode_used = "realtime_only"

    # ─ Path 2 / 3: batch (alone or with fallback) ─
    else:
        status, reason = submit_and_wait(
            specs, workspace_dir,
            task_id=task_id,
            max_wait_minutes=max_wait_minutes,
            poll_interval_seconds=poll_interval_seconds,
            log=log,
        )
        if status:
            batch_id = status.batch_id
            batch_final_status = status.status

        if reason == "completed":
            # Download what batch produced
            slot_results = download_batch_to_slots(batch_id, out_dir, specs_by_slot, log)
            # Identify failed slots for partial-fallback
            failed_slots = [r.slot for r in slot_results if not r.success]
            if failed_slots and fallback_enabled and mode == "auto":
                log.log(f"batch had {len(failed_slots)} failed slot(s); engaging realtime fallback for: {failed_slots}")
                fallback_triggered = True
                fallback_reason = "batch_partial_success"
                fallback_specs = [specs_by_slot[slot] for slot in failed_slots]
                fallback_results = generate_realtime_all(fallback_specs, out_dir, log)
                # Replace failed slot_results with realtime results
                replaced_ids = {r.slot for r in fallback_results}
                slot_results = [
                    r for r in slot_results if r.slot not in replaced_ids
                ] + fallback_results
                mode_used = "batch_with_realtime_fallback"
            else:
                mode_used = "batch_only"
                if failed_slots and not fallback_enabled:
                    log.log(f"{len(failed_slots)} slot(s) failed; fallback disabled (--no-fallback)",
                            level="WARN")
                if failed_slots and mode == "batch":
                    log.log(f"{len(failed_slots)} slot(s) failed; mode=batch (no fallback)",
                            level="WARN")
        else:
            # Batch failed terminally or timed out
            if mode == "batch" or not fallback_enabled:
                # Don't fall back — return failure
                slot_results = [SlotResult(
                    slot=s.slot, success=False, source="failed",
                    error=f"batch terminal state: {reason}",
                ) for s in specs]
                mode_used = "batch_only"
                log.log(f"batch terminal {reason}; fallback disabled; failing", level="ERROR")
            else:
                # auto mode + fallback enabled — engage realtime for ALL slots
                fallback_triggered = True
                fallback_reason = reason
                log.log(f"batch terminal '{reason}'; engaging full realtime fallback")
                slot_results = generate_realtime_all(specs, out_dir, log)
                mode_used = "batch_with_realtime_fallback"

    # ─ Compose final result ─
    total_cost = sum(r.cost_usd for r in slot_results)
    success_count = sum(1 for r in slot_results if r.success)
    elapsed = time.time() - t_start

    # Cost log (post-hoc, actual)
    try:
        cost_ledger.log(
            total_cost, model="gpt-image-2",
            endpoint="image_pipeline",
            task_id=task_id,
            extra={
                "mode_used": mode_used,
                "batch_id": batch_id, "batch_final_status": batch_final_status,
                "fallback_triggered": fallback_triggered,
                "fallback_reason": fallback_reason,
                "success_slots": success_count, "total_slots": len(specs),
                "per_slot_costs": {r.slot: r.cost_usd for r in slot_results},
            },
        )
    except Exception as e:
        log.log(f"cost_ledger.log failed (non-blocking): {e}", level="WARN")

    result = PipelineResult(
        task_id=task_id,
        mode_requested=mode,
        mode_used=mode_used,  # type: ignore[arg-type]
        total_slots=len(specs),
        success_slots=success_count,
        failed_slots=len(specs) - success_count,
        total_cost_usd=round(total_cost, 4),
        total_elapsed_seconds=round(elapsed, 2),
        batch_id=batch_id,
        batch_final_status=batch_final_status,
        fallback_triggered=fallback_triggered,
        fallback_reason=fallback_reason,
        slots=slot_results,
        log_path=str(log.path),
    )

    # Write artifacts
    write_artifacts(workspace_dir, specs_by_slot, result)
    log.log(f"=== image pipeline end: {success_count}/{len(specs)} success "
            f"${total_cost:.4f} {elapsed:.1f}s mode_used={mode_used} ===")

    # ── Stage tracking completion (audit 2026-05-22) ──────────────────
    if _stage_recorded:
        try:
            from scripts._core import file_bus as _fb
            # status = completed if ALL slots succeeded, else failed (partial = failed)
            stage_status = "completed" if success_count == len(specs) else "failed"
            _fb.record_stage_complete(
                task_id, "image-pipeline-join",
                status=stage_status,
                cost_usd=total_cost,
            )
        except Exception as _e:
            log.log(f"stage_history record_stage_complete failed: {_e}", level="WARN")

    return result


def write_artifacts(
    workspace_dir: Path,
    specs_by_slot: dict[str, ImagePromptSpec],
    result: PipelineResult,
) -> None:
    """Write images_manifest.json (audit) + images.json (wp_publisher input)."""
    # images_manifest.json — full audit
    manifest = {
        "task_id": result.task_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode_requested": result.mode_requested,
        "mode_used": result.mode_used,
        "total_slots": result.total_slots,
        "success_slots": result.success_slots,
        "failed_slots": result.failed_slots,
        "total_cost_usd": result.total_cost_usd,
        "total_elapsed_seconds": result.total_elapsed_seconds,
        "batch_id": result.batch_id,
        "batch_final_status": result.batch_final_status,
        "fallback_triggered": result.fallback_triggered,
        "fallback_reason": result.fallback_reason,
        "log_path": result.log_path,
        "slots": [asdict(r) for r in result.slots],
    }
    (workspace_dir / "images_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # images.json — wp_publisher input format
    wp_images = []
    for r in result.slots:
        if not r.success or not r.image_path:
            continue
        spec = specs_by_slot.get(r.slot)
        if not spec:
            continue
        filename = spec.filename or f"{r.slot}.png"
        # v3.41.3: resolve to ABSOLUTE — the contract (agents/image-visual-qa.md)
        # says absolute PNG paths, but a QA-agent invocation with a relative
        # --workspace stored "memory\\workspace\\..." verbatim on 2026-07-19 and
        # only published because wp_publisher happened to run from repo root.
        _abs_path = str(Path(r.image_path).resolve()) if r.image_path else r.image_path
        wp_images.append({
            "slot_id": spec.slot,
            "path": _abs_path,
            "filename": filename,
            "alt": spec.alt,
            "caption": spec.caption,
            "title": spec.title or spec.slot.replace("_", " ").title(),
            "description": spec.description,
            "is_featured": spec.is_featured,
            "source": r.source,
        })
    # MERGE (upsert by slot_id) rather than overwrite, so chart slots already
    # rendered by render_data_charts.py (source="chart_render") survive. The photo
    # pipeline only owns photo slots; clobbering would drop the data charts.
    images_path = workspace_dir / "images.json"
    if images_path.exists():
        try:
            prior = json.loads(images_path.read_text(encoding="utf-8"))
            prior_list = prior if isinstance(prior, list) else prior.get("images", [])
        except (json.JSONDecodeError, UnicodeDecodeError):
            prior_list = []
        by_slot = {e["slot_id"]: e for e in prior_list if isinstance(e, dict) and e.get("slot_id")}
        for e in wp_images:
            by_slot[e["slot_id"]] = e  # this run's photo wins for its slot
        wp_images = list(by_slot.values())
    images_path.write_text(
        json.dumps(wp_images, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ─── CLI ────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(
        description="OpenAI image generation pipeline with batch + realtime fallback"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    gen = sub.add_parser("generate", help="Generate images from a prompts file")
    gen.add_argument("--requests-file", type=Path, required=True,
                     help="Path to image_prompts.json (or image_batch_requests.json — compat)")
    gen.add_argument("--workspace", type=Path, required=True,
                     help="Workspace directory (images written to workspace/images/)")
    gen.add_argument("--task-id", default=None,
                     help="Task ID for cost ledger / telemetry")
    gen.add_argument("--mode", choices=["auto", "batch", "realtime"], default=None,
                     help="auto=batch with realtime fallback; batch=batch only, no "
                          "fallback; realtime=skip batch (provider primary+fallback). "
                          "Default: config.yaml image.default_mode, else 'realtime'.")
    gen.add_argument("--max-wait-minutes", type=int, default=DEFAULT_MAX_WAIT_MINUTES,
                     help=f"Max minutes to wait for batch (default: {DEFAULT_MAX_WAIT_MINUTES})")
    gen.add_argument("--poll-interval-seconds", type=int, default=DEFAULT_POLL_INTERVAL_SECONDS,
                     help=f"Seconds between batch polls (default: {DEFAULT_POLL_INTERVAL_SECONDS})")
    gen.add_argument("--no-fallback", action="store_true",
                     help="Disable realtime fallback (batch-only behaviour)")
    gen.add_argument("--allow-partial", action="store_true",
                     help="Exit 0 even if some slots failed (default: exit 1 on any failure)")
    gen.add_argument("--dry-run", action="store_true",
                     help="Show what would be done; no API calls")
    gen.add_argument("--json", action="store_true",
                     help="Emit JSON result to stdout (machine-readable)")

    args = ap.parse_args()

    if args.cmd == "generate":
        # Race-guard (added 2026-05-23 per feedback_image_pipeline_serial_not_parallel.md):
        # image-prompt-designer subagent and this pipeline must run SEQUENTIALLY, not
        # in parallel. If the orchestrator forks both as background tasks, this pipeline
        # can start before the designer has finished writing its file — consuming
        # incomplete/stale prompts. The fix: check file age. If <5 seconds old, the
        # designer is likely still writing. Either wait briefly, or fail explicitly
        # so the caller can fix sequencing.
        if not args.requests_file.exists():
            print(
                f"Race-guard: requests file does not exist: {args.requests_file}\n"
                f"  This usually means image-prompt-designer has not finished yet, or was never run.\n"
                f"  Designer must complete BEFORE this pipeline starts (see memory: "
                f"feedback_image_pipeline_serial_not_parallel.md).",
                file=sys.stderr,
            )
            return 3
        import time as _time
        _file_age = _time.time() - args.requests_file.stat().st_mtime
        if _file_age < 5.0:
            print(
                f"⚠ Race-guard: requests file is only {_file_age:.1f}s old. "
                f"image-prompt-designer may still be writing. Waiting 6s for completion...",
                file=sys.stderr,
            )
            _time.sleep(6.0 - _file_age)

        # Load specs — accept multiple top-level shapes for compatibility:
        #   (1) Bare list:       [{slot, prompt, ...}, ...]
        #   (2) Wrapped:         {"prompts": [...]}    (image-prompt-designer output)
        #   (3) Alt-wrapped:     {"requests": [...]}   or {"items": [...]}
        #   (4) Single dict:     {slot, prompt, ...}   (single-image case)
        try:
            raw = json.loads(args.requests_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Failed to read requests file: {e}", file=sys.stderr)
            return 3
        # Normalize the various shapes to a flat list of dicts
        if isinstance(raw, list):
            entries = raw
        elif isinstance(raw, dict):
            entries = (
                raw.get("prompts")
                or raw.get("requests")
                or raw.get("items")
                or raw.get("specs")
                or []
            )
            if not entries and ("slot" in raw or "custom_id" in raw) and "prompt" in raw:
                entries = [raw]  # single-spec dict
        else:
            print(f"Failed to parse image specs: unsupported top-level type {type(raw).__name__}", file=sys.stderr)
            return 3
        if not isinstance(entries, list):
            print(f"Failed to parse image specs: expected list, got {type(entries).__name__}", file=sys.stderr)
            return 3

        # Skip chart/data slots — those are rendered locally by
        # scripts/build/render_data_charts.py (real labeled charts), not gpt-image.
        # The photo pipeline owns only kind!="chart" slots.
        _chart_slots = [e.get("slot_id") or e.get("slot") for e in entries
                        if isinstance(e, dict) and str(e.get("kind", "photo")).lower() == "chart"]
        entries = [e for e in entries
                   if not (isinstance(e, dict) and str(e.get("kind", "photo")).lower() == "chart")]
        if _chart_slots:
            print(f"  (skipping {len(_chart_slots)} chart slot(s) — rendered by render_data_charts: {_chart_slots})",
                  file=sys.stderr)
        if not entries:
            # All slots were charts → nothing for the photo pipeline to do. This is
            # a SUCCESS (charts handled upstream), not the "No image specs" error.
            print(json.dumps({"task_id": args.task_id, "success_slots": 0, "total_slots": 0,
                              "mode_used": "skipped_all_charts", "note": "all slots are charts; handled by render_data_charts"})
                  if args.json else "  All slots are charts; photo pipeline has nothing to generate.")
            return 0

        # Convert entries that use the image-prompt-designer's richer schema
        # (full_prompt + negative_prompt + slot_id + aspect_ratio + filename_seed)
        # into the flat ImagePromptSpec shape.
        def _adapt_entry(d: dict) -> dict:
            if not isinstance(d, dict):
                return d
            # If it already looks flat (has 'prompt' + ('slot_id' or 'slot' or 'custom_id')), pass through
            if "prompt" in d and ("slot_id" in d or "slot" in d or "custom_id" in d):
                return d
            # Designer schema → adapt
            slot = d.get("slot_id") or d.get("slot") or d.get("custom_id")
            prompt = d.get("full_prompt") or d.get("prompt") or ""
            neg = d.get("negative_prompt") or ""
            if neg and "AVOID:" not in prompt:
                prompt = f"{prompt}\n\nAVOID: {neg}"
            ar = d.get("aspect_ratio") or d.get("ratio")
            # 4K tiers since 2026-06-10 (see _AR_TO_4K). When the designer gives no
            # explicit size we map its aspect_ratio to a 4K tier; else fall back to
            # the 4K DEFAULT_SIZE.
            size = d.get("size") or (_AR_TO_4K.get(ar) if ar else None) or DEFAULT_SIZE
            _quality_aliases = {"hd": "high", "standard": "medium", "low": "low"}
            _size_aliases = {"1792x1024": "1536x1024", "1024x1792": "1024x1536"}
            raw_quality = d.get("quality", DEFAULT_QUALITY)
            quality = _quality_aliases.get(raw_quality, raw_quality)
            size = _size_aliases.get(size, size)
            # 4K floor: snap any legacy sub-4K size (1024/1536) up to its 4K tier so
            # an explicit small `size` from the designer can't silently downgrade the
            # photo (2026-06-15 audit fix). Charts are already filtered out above.
            size = _enforce_4k_floor(size, ar)
            return {
                "slot": slot,
                "custom_id": d.get("custom_id") or slot,
                "prompt": prompt,
                "size": size,
                "quality": quality,
                "alt": d.get("alt_text_seed") or d.get("alt", ""),
                "caption": d.get("caption", ""),
                "title": d.get("title", ""),
                "description": d.get("description", ""),
                "filename": d.get("filename_seed") or d.get("filename"),
                # Cover is always featured (see ImagePromptSpec.from_dict, 2026-07-01).
                "is_featured": bool(d.get("is_featured")) or _core_is_cover_slot(slot),
            }

        try:
            specs = [ImagePromptSpec.from_dict(_adapt_entry(d)) for d in entries]
        except Exception as e:
            print(f"Failed to parse image specs: {e}", file=sys.stderr)
            return 3
        if not specs:
            print("No image specs in requests file", file=sys.stderr)
            return 3

        # Resolve mode: explicit --mode wins; else config.yaml image.default_mode
        # (which falls back to 'realtime'). Relays don't support the Batch API,
        # so realtime is the correct default for the configurable-primary setup.
        from scripts._core import image_provider as _ip
        run_mode = args.mode or _ip.default_mode()

        result = generate_images(
            specs, args.workspace,
            task_id=args.task_id,
            mode=run_mode,
            max_wait_minutes=args.max_wait_minutes,
            poll_interval_seconds=args.poll_interval_seconds,
            fallback_enabled=not args.no_fallback,
            dry_run=args.dry_run,
            json_mode=args.json,
        )

        if args.json:
            print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        else:
            print("\n=== RESULT ===")
            print(f"Mode requested:  {result.mode_requested}")
            print(f"Mode used:       {result.mode_used}")
            print(f"Slots success:   {result.success_slots}/{result.total_slots}")
            print(f"Total cost:      ${result.total_cost_usd:.4f}")
            print(f"Total time:      {result.total_elapsed_seconds:.1f}s")
            print(f"Batch ID:        {result.batch_id or '(none)'}")
            print(f"Batch status:    {result.batch_final_status or '(n/a)'}")
            print(f"Fallback:        {'yes — ' + (result.fallback_reason or '') if result.fallback_triggered else 'no'}")
            print(f"Log:             {result.log_path}")
            print("\nPer-slot:")
            for r in result.slots:
                icon = "✓" if r.success else "✗"
                source = r.source.ljust(8)
                detail = (f"{r.image_path} ({r.size_bytes:,}B) ${r.cost_usd:.4f}"
                          if r.success else r.error)
                print(f"  {icon} {r.slot.ljust(28)} {source} {detail}")

        if result.failed_slots == 0:
            return 0
        if result.success_slots == 0:
            return 2
        return 0 if args.allow_partial else 1

    return 3


if __name__ == "__main__":
    sys.exit(main())
