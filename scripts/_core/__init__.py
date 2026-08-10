"""scripts/_core — shared utilities used across all skills and scripts.

Public API:
    credential_hub   — Resolve API keys from env / files / OS keychain
    ssrf_guard       — validate_url() to block SSRF / private IP / metadata endpoints
    cost_ledger      — Estimate, check budget, log, summarize API costs
    llm_judge        — External LLM judge for quality gates and evals
    file_bus         — workspace/{task_id}/ artifact read/write with schema validation
    manifest_consistency_check  — Keep VERSION in sync across all manifests
"""

from . import (
    credential_hub,
    ssrf_guard,
    cost_ledger,
    llm_judge,
    file_bus,
    manifest_consistency_check,
)

__all__ = [
    "credential_hub",
    "ssrf_guard",
    "cost_ledger",
    "llm_judge",
    "file_bus",
    "manifest_consistency_check",
]
