"""scripts/openai — Official OpenAI gpt-image-2 + Batch API integration.

This is the OFFICIAL-OpenAI side of image generation. As of 2026-06-06 the
default PRIMARY image provider is a configurable OpenAI-compatible relay
(openclawroot) resolved by scripts/_core/image_provider.py; this package serves
as the realtime FALLBACK (and the batch path, which is official-only). The
realtime entrypoint openai_image_pipeline.py honors per-provider base_url; the
batch path here always hits the official endpoint.
"""
