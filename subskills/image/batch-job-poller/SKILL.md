---
name: batch-job-poller
description: Supplemental recovery tool for orphan official-OpenAI image batches (batch is only ever used on the official-OpenAI fallback path; the primary openclawroot relay has no Batch API). The canonical image flow (openai-image-generator) runs realtime and does not require this skill. Use only to diagnose stuck batches or download images from a batch that completed after the main pipeline gave up.
allowed-tools: [Read, Write, Bash]
disable-model-invocation: true
---

# Batch Job Poller (Supplemental — Recovery Only)

## Status (as of 2026-05-21)

This skill is **no longer part of the standard image flow**. The new
`openai-image-generator` skill consolidates submit + poll + download + realtime
fallback into a single synchronous call via `openai_image_pipeline.py`.

This skill remains for two recovery scenarios only:

### Scenario 1: Orphan batch recovery

If a prior pipeline run gave up on a batch (timeout, crash, user cancellation),
the batch may still complete in OpenAI's queue. Use this skill to:
- Poll the batch status
- Download images if `completed`
- Read error file if `failed` for root-cause diagnosis
- Mark the batch as abandoned if `expired` (24h)

Example:
```bash
# Find orphan batches across all workspaces
for status_file in memory/workspace/*/batch_status.json; do
    batch_id=$(python -c "import json,sys; print(json.load(open('$status_file'))['batch_id'])")
    python -m scripts.openai.openai_batch_image_api --json poll $batch_id
done

# Download a specific orphan batch's images
python -m scripts.openai.openai_batch_image_api download batch_xxx \
    --output-dir memory/workspace/{task_id}/images
```

### Scenario 2: Diagnose stuck or failed batches

If a current batch is reporting `failed`, get the error_file_id and read it:
```bash
python -c "
import sys
sys.path.insert(0, '.')
from scripts._core import credential_hub
import openai
client = openai.OpenAI(api_key=credential_hub.get_credential('openai'))
batch = client.batches.retrieve('batch_xxx')
if batch.error_file_id:
    print(client.files.content(batch.error_file_id).text)
"
```

The error file is JSONL — one line per failed request, with the OpenAI HTTP code
and rejected parameter name. The 2026-05-20 incident on project-charlie post 37063
turned out to be a script bug (sent `response_format`) detectable only by reading
this file.

## Why this is no longer auto-scheduled

The previous design ran this skill every 15 minutes via `hooks/scheduled.json`.
That pattern had three drawbacks:
1. 15-minute granularity meant up to 15 min of latency after batch completion
2. No fallback path if batch failed permanently
3. Multiple background pollers competing across workspaces

The unified pipeline supersedes all three by polling at 60-second granularity
inline within the article task, with a 25-minute timeout that triggers automatic
realtime fallback.

If you have a `hooks/scheduled.json` entry for this skill, it can be removed —
the inline pipeline handles standard cases. Keep the skill file for the recovery
scenarios above.

See memory: [[reference-openai-image-pipeline]], [[feedback-batch-image-default-and-polling]]
