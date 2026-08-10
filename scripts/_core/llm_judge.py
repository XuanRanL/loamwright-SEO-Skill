"""
scripts/_core/llm_judge.py — External LLM judge for quality gates and evals.

Default model: Gemini 2.5 Flash (cheap, fast) for judging.
Configurable via ~/.xuanran-seo/config.yaml:models.anthropic_judge or .gemini_judge.

Two main use cases:
  1. Per-skill evals (run after each skill development)
  2. Quality gate LLM dimensions (CORE-EEAT content/relevance, CITE eminence, etc.)

Why an external judge:
  - Avoid self-bias (claude-opus-4-7 generating + judging = optimistic)
  - Cheaper model = run frequently
  - Independent perspective

Usage (Python):
    from scripts._core.llm_judge import judge, JudgeResult

    result = judge(
        prompt="Original task...",
        output="Generated article markdown...",
        criteria=[
            "Article contains primary keyword 4-8 times in body",
            "AT LEAST 2 markdown tables, with one in front 50%",
            "No banned phrases from a known AI-tell list",
        ],
        model="gemini-2.5-flash",  # or "claude-haiku-4-5"
    )
    # result.score (0-100), result.per_criterion {idx: pass/fail}, result.rationale

Usage (CLI):
    python -m scripts._core.llm_judge \\
        --prompt-file task.txt --output-file draft.md \\
        --criteria "claim 1" "claim 2" \\
        --model gemini-2.5-flash \\
        --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Final, Literal

from scripts._core import credential_hub, cost_ledger


DEFAULT_JUDGE_MODEL: Final[str] = "gemini-2.5-flash"


_JUDGE_SYSTEM_PROMPT: Final[str] = """You are an impartial quality judge for SEO blog content.

Your job: evaluate whether a generated article meets a list of specific, objective criteria.

For each criterion:
  - Decide pass (True) or fail (False)
  - Provide one-sentence evidence with line/quote
  - Be strict — pass only if clearly met

Output STRICT JSON with this structure:
{
  "per_criterion": [
    {"index": 0, "criterion": "...", "passed": true, "evidence": "..."},
    ...
  ],
  "score_0_100": <integer>,
  "rationale": "<2-3 sentence overall summary>",
  "would_change": ["...", "..."]
}

DO NOT output anything else. No markdown wrapping, no preamble. Pure JSON.
"""


# ─── Data types ────────────────────────────────────────────────

@dataclass
class JudgeCriterion:
    index: int
    criterion: str
    passed: bool
    evidence: str


@dataclass
class JudgeResult:
    score: int                    # 0-100
    rationale: str
    per_criterion: list[JudgeCriterion] = field(default_factory=list)
    would_change: list[str] = field(default_factory=list)
    model: str = ""
    cost_usd: str = "0"

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.per_criterion)


# ─── Core API ──────────────────────────────────────────────────

def judge(
    *,
    prompt: str,
    output: str,
    criteria: list[str],
    model: str = DEFAULT_JUDGE_MODEL,
    task_id: str | None = None,
) -> JudgeResult:
    """Judge an output against criteria using an external LLM.

    Args:
        prompt: The original task / instruction given to the generator.
        output: The generated text to judge.
        criteria: List of objective conditions (each ≤200 chars).
        model: Judge model ID. Default gemini-2.5-flash for cost.
        task_id: For cost ledger correlation.

    Returns:
        JudgeResult.

    Raises:
        ValueError: If criteria empty or output empty.
        RuntimeError: If judge model returns unparseable JSON.
    """
    if not criteria:
        raise ValueError("criteria list must not be empty")
    if not output.strip():
        raise ValueError("output must not be empty")

    criteria_block = "\n".join(f"  [{i}] {c}" for i, c in enumerate(criteria))

    user_msg = f"""TASK GIVEN TO GENERATOR (for context):
\"\"\"
{prompt[:3000]}
\"\"\"

GENERATED OUTPUT TO JUDGE:
\"\"\"
{output[:30000]}
\"\"\"

CRITERIA TO CHECK:
{criteria_block}

Return strict JSON per the schema in your system prompt."""

    # Cost estimate
    est_in = (len(_JUDGE_SYSTEM_PROMPT) + len(user_msg)) // 4   # ~chars/4 = tokens approx
    est_out = 800
    est = cost_ledger.estimate(model, in_tokens=est_in, out_tokens=est_out)

    raw_response, actual_in, actual_out = _call_judge(model, _JUDGE_SYSTEM_PROMPT, user_msg)

    # Parse strict JSON
    try:
        # Tolerant: strip fences if present (despite instructions)
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Judge model returned unparseable JSON: {e}\n\nRaw response (first 500 chars):\n{raw_response[:500]}"
        ) from e

    # Build result
    per = [
        JudgeCriterion(
            index=int(item.get("index", i)),
            criterion=item.get("criterion", criteria[i] if i < len(criteria) else ""),
            passed=bool(item.get("passed", False)),
            evidence=str(item.get("evidence", "")),
        )
        for i, item in enumerate(data.get("per_criterion", []))
    ]

    score = int(data.get("score_0_100", 0))
    score = max(0, min(100, score))

    result = JudgeResult(
        score=score,
        rationale=str(data.get("rationale", "")),
        per_criterion=per,
        would_change=[str(s) for s in data.get("would_change", [])],
        model=model,
        cost_usd=str(est.estimated_usd),
    )

    # Log cost (using estimate since most judges don't return exact token counts)
    cost_ledger.log(
        est,
        endpoint="messages.judge",
        task_id=task_id,
        extra={"judge_criteria_count": len(criteria), "judge_score": result.score},
    )

    return result


# ─── Provider-specific judge calls ─────────────────────────────────

def _call_judge(model: str, system: str, user: str) -> tuple[str, int, int]:
    """Dispatch to provider SDK. Returns (raw_text, in_tokens_actual, out_tokens_actual)."""
    if model.startswith("claude-"):
        return _call_anthropic(model, system, user)
    if model.startswith("gemini-"):
        return _call_gemini(model, system, user)
    raise ValueError(f"Unknown judge model: {model}")


def _call_anthropic(model: str, system: str, user: str) -> tuple[str, int, int]:
    """Call Claude API for judging."""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("anthropic SDK not installed: pip install anthropic") from e

    api_key = credential_hub.get_credential("anthropic")
    client = anthropic.Anthropic(api_key=api_key)

    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = resp.content[0].text if resp.content else ""
    in_t = resp.usage.input_tokens if hasattr(resp, "usage") else 0
    out_t = resp.usage.output_tokens if hasattr(resp, "usage") else 0
    return text, in_t, out_t


def _call_gemini(model: str, system: str, user: str) -> tuple[str, int, int]:
    """Call Gemini API for judging."""
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise RuntimeError(
            "google-genai SDK not installed: pip install google-genai "
            "(NOT the deprecated google-generativeai)"
        ) from e

    api_key = credential_hub.get_credential("gemini")
    client = genai.Client(api_key=api_key)

    resp = client.models.generate_content(
        model=model,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            max_output_tokens=2000,
            temperature=0.1,  # low temp for consistent judging
        ),
    )
    text = resp.text or ""
    # Gemini usage_metadata exposes prompt_token_count / candidates_token_count
    in_t = getattr(resp, "usage_metadata", None)
    out_t = 0
    if in_t:
        out_t = getattr(in_t, "candidates_token_count", 0)
        in_t = getattr(in_t, "prompt_token_count", 0)
    return text, in_t or 0, out_t


# ─── CLI ─────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="LLM Judge CLI")
    ap.add_argument("--prompt-file", required=True, type=Path)
    ap.add_argument("--output-file", required=True, type=Path)
    ap.add_argument("--criteria", nargs="+", required=True)
    ap.add_argument("--model", default=DEFAULT_JUDGE_MODEL)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--task-id")
    args = ap.parse_args()

    prompt = args.prompt_file.read_text(encoding="utf-8")
    output = args.output_file.read_text(encoding="utf-8")

    try:
        result = judge(
            prompt=prompt, output=output,
            criteria=args.criteria, model=args.model,
            task_id=args.task_id,
        )
    except (ValueError, RuntimeError) as e:
        print(f"Judge error: {e}", file=sys.stderr)
        return 2

    if args.json:
        result_dict = {
            "score": result.score,
            "rationale": result.rationale,
            "all_passed": result.all_passed,
            "per_criterion": [asdict(c) for c in result.per_criterion],
            "would_change": result.would_change,
            "model": result.model,
            "cost_usd": result.cost_usd,
        }
        print(json.dumps(result_dict, indent=2))
    else:
        print(f"Score: {result.score}/100  (all_passed={result.all_passed})")
        print(f"Model: {result.model}  Cost: ${result.cost_usd}")
        print()
        for c in result.per_criterion:
            icon = "✓" if c.passed else "✗"
            print(f"  {icon} [{c.index}] {c.criterion[:80]}")
            if c.evidence:
                print(f"      → {c.evidence[:120]}")
        print(f"\nRationale: {result.rationale}")
        if result.would_change:
            print("\nWould change:")
            for s in result.would_change:
                print(f"  - {s}")

    return 0 if result.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
