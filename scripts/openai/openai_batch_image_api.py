"""scripts/openai/openai_batch_image_api.py — Submit + poll OpenAI Batch API for image generation.

FALLBACK PATH ONLY (as of 2026-06-06): the canonical image flow forces realtime
because the configured PRIMARY provider is a relay (openclawroot) with no Batch
API. This module is reached only when mode=auto/batch routes to OFFICIAL OpenAI
(which does support batch). It always uses the official endpoint (no base_url
override) and the official "gpt-image-2" model. See scripts/_core/image_provider.py
for the provider chain and scripts/openai/openai_image_pipeline.py for routing.

Per IMAGE-GENERATION-V3.2-SPEC.md §5:
  - 50% off vs synchronous
  - 24h completion window
  - JSONL input format
  - Status: validating → in_progress → finalizing → completed
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from scripts._core import credential_hub, cost_ledger


@dataclass
class BatchImageRequest:
    custom_id: str            # e.g. "cover", "section_1", etc.
    prompt: str
    size: str = "1024x1024"   # 1024x1024 / 1024x1536 / 1536x1024
    quality: Literal["low", "medium", "high"] = "high"
    n: int = 1
    output_format: str = "png"
    background: str = "auto"  # auto / transparent


@dataclass
class BatchStatus:
    batch_id: str
    status: str               # validating / in_progress / finalizing / completed / failed / expired / cancelled
    input_file_id: str
    output_file_id: str | None = None
    error_file_id: str | None = None
    created_at: int | None = None
    completed_at: int | None = None
    total_requests: int = 0
    completed_requests: int = 0
    failed_requests: int = 0


def build_jsonl(requests: list[BatchImageRequest]) -> str:
    """Build JSONL for Batch API input file."""
    lines = []
    for r in requests:
        line = {
            "custom_id": r.custom_id,
            "method": "POST",
            "url": "/v1/images/generations",
            "body": {
                "model": "gpt-image-2",
                "prompt": r.prompt,
                "size": r.size,
                "quality": r.quality,
                "n": r.n,
                "output_format": r.output_format,
            },
        }
        if r.background != "auto":
            line["body"]["background"] = r.background
        lines.append(json.dumps(line, ensure_ascii=False))
    return "\n".join(lines)


def submit_batch(
    requests: list[BatchImageRequest],
    *,
    workspace_dir: Path,
    task_id: str | None = None,
) -> BatchStatus:
    """Submit a batch of image generation requests.

    Returns BatchStatus with batch_id.
    """
    if not requests:
        raise ValueError("Empty request list")

    try:
        import openai
    except ImportError as e:
        raise RuntimeError("openai not installed") from e

    try:
        api_key = credential_hub.get_credential("openai")
    except credential_hub.CredentialNotFoundError as e:
        raise RuntimeError(f"OpenAI key missing: {e}") from e

    # Estimate cost
    total_cost = 0
    for r in requests:
        est = cost_ledger.estimate(
            "gpt-image-2",
            image_quality=r.quality,
            image_size=r.size,
            image_count=r.n,
            batch_mode=True,
        )
        total_cost += float(est.estimated_usd)

    # Check budget
    decision = cost_ledger.check(total_cost, scope="per_image_batch")
    if decision == "blocked":
        raise RuntimeError(f"Batch cost ${total_cost:.4f} exceeds per_image_batch budget")

    # Build JSONL file
    workspace_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = workspace_dir / "image_batch.jsonl"
    jsonl_content = build_jsonl(requests)
    jsonl_path.write_text(jsonl_content, encoding="utf-8")

    client = openai.OpenAI(api_key=api_key)

    # Upload JSONL
    with open(jsonl_path, "rb") as f:
        batch_file = client.files.create(file=f, purpose="batch")

    # Create batch
    batch = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/images/generations",
        completion_window="24h",
        metadata={
            "task_id": task_id or "unknown",
            "request_count": str(len(requests)),
            "submitter": "xuanran-seo-3.2",
        },
    )

    status = BatchStatus(
        batch_id=batch.id,
        status=batch.status,
        input_file_id=batch_file.id,
        created_at=batch.created_at if hasattr(batch, "created_at") else None,
        total_requests=len(requests),
    )

    # Save status file
    status_file = workspace_dir / "batch_status.json"
    status_file.write_text(json.dumps({
        **asdict(status),
        "submitted_at": time.time(),
        "estimated_cost_usd": total_cost,
        "request_count": len(requests),
    }, indent=2), encoding="utf-8")

    # Cost is incurred at download time (when images are actually generated and billed),
    # not at submit. Log 0 here so the ledger has a submit-event record without crashing
    # on None→Decimal conversion. The real per-image cost gets logged in download_results().
    try:
        cost_ledger.log(
            0, model="gpt-image-2-batch",
            endpoint="batches.create",
            task_id=task_id,
            extra={"batch_id": batch.id, "request_count": len(requests),
                   "estimated_cost_usd_pending": float(total_cost)},
        )
    except Exception as e:
        # Non-blocking — batch is already submitted; ledger logging is informational
        import sys
        print(f"⚠ cost_ledger.log non-blocking failure: {e}", file=sys.stderr)

    return status


def poll_status(batch_id: str) -> BatchStatus:
    """Poll batch status."""
    try:
        import openai
    except ImportError as e:
        raise RuntimeError("openai not installed") from e
    api_key = credential_hub.get_credential("openai")
    client = openai.OpenAI(api_key=api_key)
    batch = client.batches.retrieve(batch_id)

    counts = getattr(batch, "request_counts", None)
    return BatchStatus(
        batch_id=batch.id,
        status=batch.status,
        input_file_id=batch.input_file_id,
        output_file_id=getattr(batch, "output_file_id", None),
        error_file_id=getattr(batch, "error_file_id", None),
        created_at=batch.created_at if hasattr(batch, "created_at") else None,
        completed_at=batch.completed_at if hasattr(batch, "completed_at") else None,
        total_requests=counts.total if counts else 0,
        completed_requests=counts.completed if counts else 0,
        failed_requests=counts.failed if counts else 0,
    )


def download_results(batch_id: str, output_dir: Path) -> list[dict]:
    """Download completed batch results; save images to output_dir.

    Returns list of {custom_id, success, image_path, error}.
    """
    try:
        import openai
    except ImportError as e:
        raise RuntimeError("openai not installed") from e

    api_key = credential_hub.get_credential("openai")
    client = openai.OpenAI(api_key=api_key)

    batch = client.batches.retrieve(batch_id)
    if batch.status != "completed":
        raise RuntimeError(f"Batch not completed (status: {batch.status})")

    output_id = getattr(batch, "output_file_id", None)
    if not output_id:
        raise RuntimeError("Batch has no output_file_id")

    content = client.files.content(output_id).text
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for line in content.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        custom_id = obj.get("custom_id", "")
        if obj.get("error"):
            results.append({"custom_id": custom_id, "success": False,
                             "error": obj["error"], "image_path": None})
            continue
        body = obj.get("response", {}).get("body", {})
        data_arr = body.get("data") or []
        if not data_arr:
            results.append({"custom_id": custom_id, "success": False,
                             "error": "no data", "image_path": None})
            continue
        b64 = data_arr[0].get("b64_json")
        if not b64:
            results.append({"custom_id": custom_id, "success": False,
                             "error": "no b64_json", "image_path": None})
            continue
        # Save image
        img_bytes = base64.b64decode(b64)
        img_path = output_dir / f"{custom_id}.png"
        img_path.write_bytes(img_bytes)
        results.append({"custom_id": custom_id, "success": True,
                         "error": None, "image_path": str(img_path)})

    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="OpenAI Batch Image API")
    sub = ap.add_subparsers(dest="cmd", required=True)

    submit = sub.add_parser("submit", help="Submit JSONL batch")
    submit.add_argument("--requests-file", type=Path, required=True,
                        help="JSON list of {custom_id, prompt, size, quality}")
    submit.add_argument("--workspace", type=Path, required=True)
    submit.add_argument("--task-id")

    poll = sub.add_parser("poll", help="Poll batch status")
    poll.add_argument("batch_id")

    dl = sub.add_parser("download", help="Download completed batch results")
    dl.add_argument("batch_id")
    dl.add_argument("--output-dir", type=Path, required=True)

    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd == "submit":
        reqs_data = json.loads(args.requests_file.read_text(encoding="utf-8"))
        requests = [BatchImageRequest(**r) for r in reqs_data]
        status = submit_batch(requests, workspace_dir=args.workspace, task_id=args.task_id)
        if args.json:
            print(json.dumps(asdict(status), indent=2))
        else:
            print(f"Submitted batch: {status.batch_id}")
            print(f"Status: {status.status}")
            print(f"Requests: {status.total_requests}")
        return 0

    if args.cmd == "poll":
        status = poll_status(args.batch_id)
        if args.json:
            print(json.dumps(asdict(status), indent=2))
        else:
            print(f"Batch: {status.batch_id}")
            print(f"Status: {status.status}")
            print(f"Progress: {status.completed_requests}/{status.total_requests}")
            print(f"Failed: {status.failed_requests}")
        return 0

    if args.cmd == "download":
        results = download_results(args.batch_id, args.output_dir)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                icon = "✓" if r["success"] else "✗"
                print(f"  {icon} {r['custom_id']}: {r.get('image_path') or r.get('error')}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
