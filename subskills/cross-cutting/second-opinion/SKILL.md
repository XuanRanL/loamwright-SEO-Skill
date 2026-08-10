---
name: second-opinion
description: Cross-model audit via Gemini (review / challenge / consult modes). Defends against same-model self-bias. Used before high-impact decisions (publish gate, /init final review).
allowed-tools: [Read, Bash]
---

# Second Opinion

Independent judgment from a different model (Gemini) than the one that produced content (Claude).

## 3 modes

### review
Same as quality-gate but using different model. Pass/fail gate.
```bash
python -m scripts._core.llm_judge --prompt-file task.txt --output-file draft.md \
    --criteria "criterion1" "criterion2" --model gemini-2.5-flash --json
```

### challenge
Adversarial: "find what's wrong with this article".
Used when an article passed all quality gates but feels suspicious.

### consult
Open-ended Q&A: "Is this strategy / decision right?"

## When to use
- Pre-publish (with target_score=95+): supplemental review
- Repair Round 5 (from-scratch): get challenge view before accepting
- /init Stage 11 synthesis: consult on whether the project profile is accurate
- /article when target_surfaces includes AI engines (use the actual engine to judge)

## Cost
Cheaper than the main Claude Opus call. Gemini 2.5 Flash = $0.30/$2.50 per M tokens.
Typical review = $0.01-0.05.

## See also
- `scripts/_core/llm_judge.py` (the underlying tool)
