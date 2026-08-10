"""scripts/_core/provenance.py — SINGLE source of truth for `_generated_by` provenance.

v3.41.3 root cure (2026-07-19 contract-gap audit): the orchestrator's
``_PROVENANCE_REQUIRED`` and pre_publish_gate's ``PROVENANCE_REQUIREMENTS``
were two hand-maintained dicts that shared only 3 of 7 entries — the
orchestrator gated geo-audit/visual-design-report/cta-draft but not
image-qa-report; the gate did the reverse. Same Rule-12 disease as the
render-lint/check-06 split: two places checking "the same fact" drifted apart.
Both now import THIS dict. The linker's internal-link-report.json — whose
dispatch prompt demanded ``_generated_by`` that nothing enforced — is included
so the demand is real.

Rule 11: every artifact listed here MUST have its accepted value stated in the
owning ``agents/<name>.md`` (and the dispatching prompt). Pinned by
``tests/test_provenance_contract_fanout.py``.
"""
from __future__ import annotations

# artifact filename -> accepted _generated_by values
PROVENANCE_REQUIRED: dict[str, list[str]] = {
    "fact-check.json": ["fact-checker-subagent", "fact-checker-agent-v2"],
    "humanizer-report.json": ["humanizer-subagent"],
    "review.json": ["reviewer-subagent", "independent-reviewer"],
    "geo-audit.json": ["geo-auditor-subagent", "geo-auditor"],
    "visual-design-report.json": ["visual-designer-subagent"],
    "cta-draft.json": ["cta-writer-subagent"],
    "image-qa-report.json": ["image-visual-qa-subagent"],
    "internal-link-report.json": ["linker-subagent"],
}

# artifact filename -> the agent definition file that owns producing it
# (used by the fan-out regression test; keep in sync when adding entries).
PROVENANCE_OWNING_AGENT: dict[str, str] = {
    "fact-check.json": "agents/fact-checker.md",
    "humanizer-report.json": "agents/humanizer.md",
    "review.json": "agents/reviewer.md",
    "geo-audit.json": "agents/geo-auditor.md",
    "visual-design-report.json": "agents/visual-designer.md",
    "cta-draft.json": "agents/cta-writer.md",
    "image-qa-report.json": "agents/image-visual-qa.md",
    "internal-link-report.json": "agents/linker.md",
}
