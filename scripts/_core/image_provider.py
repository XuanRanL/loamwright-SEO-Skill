"""
scripts/_core/image_provider.py — Image-generation provider resolution.

Resolves an ORDERED list of image-generation providers (primary first, then
fallbacks) so the realtime pipeline can try a cheap/fast primary provider and
automatically fall back to the official OpenAI endpoint on failure.

Why this exists (2026-06-06 decision):
  - A third-party OpenAI-compatible gateway (openclawroot.com) tested as a
    drop-in, faster, cheaper realtime image source for project-charlie-style blog
    images. But third-party "relay" gateways carry real operational risk
    (sudden shutdown, key bans, silent model degradation). So the architecture
    is "configurable primary + official OpenAI fallback", NOT a hard swap.
  - Until now base_url was un-overridable (openai_image_pipeline.py only ever
    passed api_key) and the image model id was hardcoded "gpt-image-2" — both
    violate CLAUDE.md "Don't hardcode model IDs / read from config".

Config (~/.xuanran-seo/config.yaml):
    image:
      default_mode: realtime          # auto | batch | realtime  (realtime forced for relay; batch unsupported by relays)
      model: gpt-image-2              # default model id for any provider that doesn't override
      providers:                       # ORDERED — first is primary, rest are fallbacks
        - name: vertex-gemini          # PRIMARY (2026-06-17) — true 4K, ~10x cheaper than OpenAI
          protocol: vertex_gemini      # NOT OpenAI-compatible (generateContent + imageConfig)
          base_url: https://aiplatform.googleapis.com/v1/publishers/google/models
          credential: vertex-gemini    # AQ. key via x-goog-api-key (file vertex-gemini.key / env VERTEX_GEMINI_API_KEY)
          model: gemini-3-pro-image-preview   # MUST be -preview; bare id ignores imageSize=4K
        - name: openai-official
          base_url:                    # null/empty => official OpenAI default endpoint
          credential: openai
          model: gpt-image-2

Provider `protocol` (per-entry, default "openai"):
  - "openai"        — OpenAI-compatible /v1/images/generations (official + all relays)
  - "vertex_gemini" — Vertex AI express generateContent + imageConfig (Gemini 3
                      Pro Image). Always requests the 4K tier (~16MP) then the
                      pipeline downscales to the requested pixel size. See
                      openai_image_pipeline._generate_vertex_gemini.

Backward-compatibility: if config.yaml has no usable `image.providers`, this
resolves to a SINGLE provider = official OpenAI (base_url=None) using the
existing `openai` credential — i.e. exactly the pre-2026-06-06 behavior.

Fail-safe philosophy (per memory feedback_silent_no_op_through_exception_swallow):
  Every swallowed exception is logged to stderr (and the optional pipeline log),
  never silently dropped. A provider whose credential is missing is SKIPPED with
  a warning, not silently included with an empty key.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from scripts._core import credential_hub

XS_HOME: Final[Path] = Path.home() / ".xuanran-seo"
CONFIG_FILE: Final[Path] = XS_HOME / "config.yaml"

DEFAULT_IMAGE_MODEL: Final[str] = "gpt-image-2"
_VALID_MODES: Final[frozenset[str]] = frozenset({"auto", "batch", "realtime"})
# 2026-06-06 decision: realtime is the de-facto default (orchestrator already
# passes --mode realtime) AND relays don't support the Batch API, so realtime is
# the forced code-level default when config doesn't say otherwise.
DEFAULT_MODE: Final[str] = "realtime"


@dataclass(frozen=True)
class ImageProvider:
    """One resolvable image-generation endpoint."""
    name: str
    base_url: str | None   # None => OpenAI SDK default endpoint
    api_key: str
    model: str
    # Wire protocol. "openai" = OpenAI-compatible /v1/images/generations (the
    # default; official OpenAI + every relay). "vertex_gemini" = Google Vertex
    # AI express-mode generateContent + imageConfig (Gemini 3 Pro Image / Nano
    # Banana Pro true 4K) — NOT OpenAI-compatible; handled by a dedicated branch
    # in openai_image_pipeline._generate_vertex_gemini.
    protocol: str = "openai"


def _warn(msg: str, log: Any | None) -> None:
    """Log a non-fatal warning to stderr AND the optional pipeline logger.

    Never swallow silently — the 2026-05-22 silent-no-op incident
    (feedback_silent_no_op_through_exception_swallow) was caused by a broad
    `except: return set()` that hid a NameError for weeks.
    """
    print(f"⚠ image_provider: {msg}", file=sys.stderr, flush=True)
    if log is not None:
        try:
            log.log(f"image_provider: {msg}", level="WARN")
        except Exception:
            pass


def _load_image_config(log: Any | None = None) -> dict:
    """Return the `image:` section of config.yaml as a dict ({} if absent/broken)."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        import yaml
        data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("image"), dict):
            return data["image"]
    except Exception as e:  # noqa: BLE001 — config is best-effort; log, never crash gen
        _warn(
            f"config.yaml image section load failed: {type(e).__name__}: {e} "
            f"— falling back to built-in default (official OpenAI)",
            log,
        )
    return {}


def default_mode(log: Any | None = None) -> str:
    """Resolve the default generation mode (auto|batch|realtime).

    Honors config.yaml :: image.default_mode, then the pre-existing
    image.pipeline_mode key (which was documented "consumed by
    openai_image_pipeline.py" but in fact never read — the CLI default was
    hardcoded 'auto'. Reading it here finally makes that config take effect).
    Falls back to DEFAULT_MODE ('realtime').
    """
    img = _load_image_config(log)
    for key in ("default_mode", "pipeline_mode"):
        raw = img.get(key)
        mode = str(raw).strip().lower() if raw is not None else ""
        if mode in _VALID_MODES:
            return mode
    return DEFAULT_MODE


def resolve_providers(log: Any | None = None) -> list[ImageProvider]:
    """Return the ordered provider list (primary first, fallbacks after).

    - Reads config.yaml :: image.providers (ordered).
    - Each entry resolves its credential via credential_hub; entries whose
      credential is missing are SKIPPED with a stderr warning (so a missing
      official-fallback key doesn't break a working primary, and vice-versa).
    - If no provider resolves from config, falls back to a single official
      OpenAI provider (pre-2026-06-06 behavior). If even that key is missing,
      returns [] and the caller fails the slots with a clear error.
    """
    img = _load_image_config(log)
    default_model = str(img.get("model") or DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    entries = img.get("providers")

    providers: list[ImageProvider] = []
    if isinstance(entries, list) and entries:
        for e in entries:
            if not isinstance(e, dict):
                _warn(f"provider entry is not a mapping, skipping: {e!r}", log)
                continue
            name = str(e.get("name") or "unnamed").strip() or "unnamed"
            raw_base = e.get("base_url")
            base_url = raw_base.strip() if isinstance(raw_base, str) and raw_base.strip() else None
            cred_name = str(e.get("credential") or "openai").strip() or "openai"
            model = str(e.get("model") or default_model).strip() or default_model
            protocol = str(e.get("protocol") or "openai").strip().lower() or "openai"
            try:
                api_key = credential_hub.get_credential(cred_name)
            except Exception as ex:  # noqa: BLE001 — missing cred => skip this provider, keep others
                _warn(
                    f"provider {name!r}: credential {cred_name!r} unavailable "
                    f"({type(ex).__name__}: {ex}); skipping",
                    log,
                )
                continue
            providers.append(ImageProvider(
                name=name, base_url=base_url, api_key=api_key, model=model, protocol=protocol,
            ))

    # Backward-compat / safety net: nothing usable from config => official OpenAI only.
    if not providers:
        try:
            api_key = credential_hub.get_credential("openai")
            providers.append(
                ImageProvider(name="openai-official", base_url=None, api_key=api_key, model=default_model)
            )
        except Exception as ex:  # noqa: BLE001
            _warn(
                f"no providers resolved from config AND official 'openai' key missing "
                f"({type(ex).__name__}: {ex}) — realtime generation will fail",
                log,
            )

    return providers
