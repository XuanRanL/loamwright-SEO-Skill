"""scripts/lint — deterministic text/markdown linters.

All linters expose a uniform `lint(text: str, **kwargs) -> LintReport` API
and a CLI with `--json` output. Used by:
  - section-drafter self_check
  - quality-gate-ai-slop
  - PostToolUse hook (post-section-write validation)
  - per-skill evals

Linters in this package:
  banned_word_lint           — 30+ banned words with substitution suggestions
  ai_tells_detector          — 43 patterns from humanizer-skill catalog
  em_dash_audit              — U+2014 zero-tolerance
  curly_quote_audit          — smart quotes / typographic AI tells
  sentence_variance          — burstiness (stddev/mean of sentence length)
  perplexity_estimator       — vocab diversity heuristic
  keyword_density            — primary 0.8-1.3% / secondary 0.3-0.7% bands
  markdown_structure_check   — unique ToC/Takeaways/References + end-at-refs
  citation_capsule_lint      — each H2 has 40-60 word AI-quotable block
  information_gain_marker_lint — RETIRED 2026-07-14 (bracket markers forbidden; kept only as cite_scorer's pre-strip counter — info gain is plain prose, scored by core_eeat_scorer O01/O02)
"""
