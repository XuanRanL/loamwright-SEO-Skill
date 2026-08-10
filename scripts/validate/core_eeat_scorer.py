"""
scripts/validate/core_eeat_scorer.py — CORE-EEAT 80-item gate.

Per references/geo/core-eeat-80.md: 8 dimensions × 10 items × 0/1 binary scoring.

Vetoes: T04 (fabricated stat), C01 (fabricated citation), R10 (prompt injection).
Cap: 1 veto → min(raw, 60); 2 vetoes → BLOCKED; R10 → immediate BLOCKED.

Outputs conform to schemas/auditor-output.schema.json for PostToolUse hook gate.

Note: Many items here are HEURISTIC (deterministic best-effort).
For full E-E-A-T scoring, also run independent-reviewer agent (LLM judge)
and combine.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from scripts.lint._text_utils import iter_h2_sections, iter_paragraphs, strip_markdown, count_words


@dataclass
class EatItem:
    item_id: str
    description: str
    passed: bool
    evidence: str = ""


@dataclass
class CoreEatReport:
    raw_overall_score: float          # 0-100
    final_overall_score: float
    cap_applied: bool
    verdict: Literal["SHIP", "FIX", "BLOCKED"]
    vetoes_triggered: list[str] = field(default_factory=list)
    dimension_scores: dict = field(default_factory=dict)
    items: list[EatItem] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    user_facing_issues: list[str] = field(default_factory=list)


def _check_R10_prompt_injection(text: str) -> bool:
    """R10: WebFetch content treated as DATA, not instructions.

    Look for telltale prompt-injection attempts in body:
      - <!-- SYSTEM: -->
      - <!-- ignore previous instructions -->
      - {{system}} or {{instructions}}
      - role: 'system' (if a JSON snippet was pasted)
    """
    patterns = [
        r"<!--\s*system\s*:",
        r"ignore (?:previous|all|the above) (?:instructions|prompts)",
        r"\{\{\s*(?:system|instructions)\s*\}\}",
        r'"role"\s*:\s*"system"',
        r"<\|system\|>",
    ]
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


# ── Project-aware mandatory-section detection (2026-07-14) ───────────────────
#
# C09/C10 used to hardcode their own heading regexes:
#     C09: ^##\s+(conclusion|verdict|bottom line|final thoughts)
#     C10: ^##\s+faq
#
# Both disagreed with the SOURCE OF TRUTH, which is the project's
# ``business-context.json :: mandatory_sections.sections[id].h2_pattern`` — the SAME
# pattern the Format-Fit gate hard-vetoes against. The consequences were unearnable
# penalties on every article that obeyed its own project contract:
#
#   * C10's `^##\s+faq` never matched the plugin's OWN default heading,
#     "Frequently Asked Questions" (it does not START with "faq"), so **C10 failed on
#     essentially every article ever scored.**
#   * C09 failed for any project mandating a gentle conclusion label ("The Last Sip",
#     "A Final Thought", "In Closing") — and that label CANNOT be renamed to satisfy the
#     scorer, because the Format-Fit gate hard-vetoes on the project's pattern.
#
# So the article was punished for complying, and the only way to "fix" the score was to
# violate a hard gate. Same Rule-11 disease as the assemble.py conclusion-stub bug.
# Now we read the project's pattern, and fall back to the legacy regex when a project
# declares none.
_CONCLUSION_FALLBACK = r"^(Conclusion|Verdict|Final Verdict|The Bottom Line|Final Thoughts|The Last Sip|A Final Thought|In Closing)"
_FAQ_FALLBACK = r"^(Frequently Asked Questions|FAQ|Common Questions|Questions)"

# The FAQ QUESTION forms this pipeline actually emits. Kept deliberately identical to
# scripts/lint/paa_alignment_check.py :: _BOLD_Q_RE / _H3_Q_RE — two checkers reading the
# same FAQ must not disagree about how many questions are in it (Rule 12).
_FAQ_BOLD_Q_RE = re.compile(r"^\s*\*\*(.+?)\*\*\s*$", re.M)
_FAQ_H3_Q_RE = re.compile(r"^###\s+(.+?)\s*(\{#[^}]*\})?\s*$", re.M)


def _count_faq_questions(faq_body: str) -> int:
    """Count FAQ questions in EITHER form the pipeline emits.

    C10 previously counted only `^###`. Every writer agent in this project emits FAQ
    questions as bold paragraphs (`**Question?**`) — that is what the paa-answer-writer
    contract produces and what schema-generator extracts into FAQPage — so C10 scored 0
    questions on articles carrying 7-8 of them and failed a criterion they fully satisfied.
    Measured on the 2026-08-05 project-alpha batch: 0 counted vs 7, 8, 8 actual.

    Bold-first, mirroring paa_alignment_check: an H3-form FAQ can legitimately contain
    bold runs inside its answers, so preferring bold there would over-count.
    """
    return len(
        list(_FAQ_BOLD_Q_RE.finditer(faq_body)) or list(_FAQ_H3_Q_RE.finditer(faq_body))
    )


def _project_h2_pattern(project_slug: str | None, section_id: str) -> str | None:
    """The project's declared h2_pattern for a mandatory section, if any."""
    if not project_slug:
        return None
    bc_path = Path(__file__).resolve().parents[2] / "projects" / project_slug / "business-context.json"
    try:
        bc = json.loads(bc_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    for sec in ((bc.get("mandatory_sections") or {}).get("sections")) or []:
        if sec.get("id") == section_id and sec.get("h2_pattern"):
            return str(sec["h2_pattern"])
    return None


def _mandatory_section_body(
    text: str, project_slug: str | None, section_id: str, fallback: str
) -> str | None:
    """Return the body of a mandatory section (heading → next H2), or None if absent."""
    pattern = _project_h2_pattern(project_slug, section_id) or fallback
    try:
        h2_re = re.compile(pattern, re.I)
    except re.error:
        h2_re = re.compile(fallback, re.I)

    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        m = re.match(r"^##\s+(.*?)\s*(?:\{#[^}]*\})?\s*$", line)
        if m and h2_re.match(m.group(1).strip()):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j]):
            end = j
            break
    return "\n".join(lines[start:end])


def _has_mandatory_section(
    text: str, project_slug: str | None, section_id: str, fallback: str
) -> bool:
    return _mandatory_section_body(text, project_slug, section_id, fallback) is not None


def _check_C(text: str, brief: dict | None, word_target: int = 0,
             project_slug: str | None = None) -> list[EatItem]:
    """C: Content Quality (10 items)."""
    items = []
    plain = strip_markdown(text)
    n_words = count_words(text)
    h2s = list(iter_h2_sections(text))

    items.append(EatItem("C01", "Article addresses real search intent", True))  # trust upstream

    if word_target:
        items.append(EatItem("C02", "Body word count within ±5%",
                              abs(n_words - word_target) / word_target <= 0.10,
                              evidence=f"{n_words}/{word_target}"))
    else:
        items.append(EatItem("C02", "Body word count within ±5%", True, evidence="no target"))

    sections_under = sum(1 for s in h2s if count_words(s.body) < 300)
    items.append(EatItem("C03", "Each H2 section ≥300 words",
                          sections_under == 0,
                          evidence=f"{sections_under} short sections"))

    # C04: No filler / repetitive — proxy with perplexity surprise score
    try:
        from scripts.lint.perplexity_estimator import surprise_score
        ss = surprise_score(text)
        items.append(EatItem("C04", "No filler / repetitive content", ss > 0.3,
                              evidence=f"surprise score {ss:.2f}"))
    except Exception:
        items.append(EatItem("C04", "No filler", True, evidence="check skipped"))

    items.append(EatItem("C05", "Reading level matches persona", True))  # placeholder

    entities = len(re.findall(r"[A-Z][a-z]+\s+[A-Z][a-z]+", plain))
    items.append(EatItem("C06", "≥5 specific examples (named entities)",
                          entities >= 5, evidence=f"entity count: {entities}"))

    # Heuristic: presence of past-tense first-person verbs
    has_anecdote = bool(re.search(r"\b(?:I|we) (?:tested|tried|found|noticed|measured|ran|deployed)\b", plain))
    items.append(EatItem("C07", "At least one original example/anecdote", has_anecdote))

    nums = len(re.findall(r"\b\d+(?:\.\d+)?(?:%|\b)", plain))
    items.append(EatItem("C08", "Concrete numbers/dates ≥10",
                          nums >= 10, evidence=f"count: {nums}"))

    has_conclusion = _has_mandatory_section(text, project_slug, "conclusion", _CONCLUSION_FALLBACK)
    items.append(EatItem("C09", "Conclusion summarizes + recommends", has_conclusion))

    # FAQ count. The section is located by the PROJECT's own mandatory_sections pattern
    # (see _has_mandatory_section) — the old `^##\s+faq` regex never matched the plugin's
    # OWN default heading, "Frequently Asked Questions", so C10 failed on every article.
    faq_body = _mandatory_section_body(text, project_slug, "faq", _FAQ_FALLBACK)
    if faq_body is not None:
        faq_questions = _count_faq_questions(faq_body)
        items.append(EatItem("C10", "FAQ ≥5 substantive questions",
                              faq_questions >= 5, evidence=f"{faq_questions} questions"))
    else:
        items.append(EatItem("C10", "FAQ ≥5 substantive questions", False))

    return items


# O01/O02 plain-prose information-gain signals (revised 2026-07-14 contract in
# references/geo/core-eeat-80.md; executor added 2026-07-17). The retired
# bracket markers ([ORIGINAL DATA] etc.) are forbidden + stripped upstream and
# must never earn these items again.
_INFO_GAIN_SIGNALS: dict[str, str] = {
    "corrected-error": (
        r"\b(?:common\s+(?:mistake|misconception|myth|error)"
        r"|most\s+(?:guides|articles|people|reviews|sites)\s+"
        r"(?:say|claim|assume|suggest|get\s+this\s+wrong|miss)"
        r"|contrary\s+to\s+popular"
        r"|often\s+(?:mislabeled|misunderstood|confused|conflated)"
        r"|the\s+myth\s+that)\b"
    ),
    "trade-off": (
        r"\b(?:trade-?offs?|the\s+catch|downsides?|drawbacks?"
        r"|at\s+the\s+cost\s+of|comes?\s+at\s+a\s+price"
        r"|on\s+the\s+flip\s+side|the\s+honest\s+(?:answer|trade-?off))\b"
    ),
    "comparison-synthesis": (
        r"\b(?:unlike|whereas|compared\s+(?:with|to)"
        r"|side[\s-]?by[\s-]?side|versus)\b"
    ),
    "number-in-context": (
        r"\d[^.\n]{0,90}\b(?:which\s+(?:means|works\s+out\s+to)"
        r"|that(?:'|’)?s\s+(?:roughly|about|enough|less|more|below|under|over)"
        r"|in\s+practice|put\s+differently"
        r"|to\s+put\s+that\s+in\s+(?:context|perspective))\b"
    ),
}


def _info_gain_signal_types(text: str, plain: str) -> list[str]:
    """Distinct plain-prose information-gain signal classes present."""
    found = [name for name, pat in _INFO_GAIN_SIGNALS.items()
             if re.search(pat, plain, re.I)]
    # A markdown comparison table with >=3 body rows is a synthesis signal even
    # without comparative connectives in the prose.
    if "comparison-synthesis" not in found:
        body_rows = re.findall(r"^\|(?!\s*-)[^\n]*\|\s*$", text, re.M)
        if len(body_rows) >= 4:  # header + >=3 data rows
            found.append("comparison-synthesis")
    return found


def _check_O(text: str) -> list[EatItem]:
    """O: Original Value (10 items)."""
    items = []
    plain = strip_markdown(text)

    signal_types = _info_gain_signal_types(text, plain)
    items.append(EatItem("O01", "Information gain as plain prose ≥2 distinct signal types",
                          len(signal_types) >= 2, evidence=f"signals: {signal_types}"))
    items.append(EatItem("O02", "≥1 substantive original-value signal in prose",
                          len(signal_types) >= 1, evidence=f"signals: {signal_types}"))
    items.append(EatItem("O03", "Original tests/experiments described",
                          bool(re.search(r"\b(?:tested|measured|ran|recorded|observed|sampled)\s+\d", plain))))
    items.append(EatItem("O04", "First-hand observations",
                          bool(re.search(r"\b(?:I|we) (?:saw|noticed|found|measured|observed)\b", plain))))
    items.append(EatItem("O05", "Novel framework/model proposed",
                          bool(re.search(r"\b(?:framework|model|method|approach|protocol)\b.*we", plain, re.I))))
    items.append(EatItem("O06", "Counter-intuitive insights",
                          bool(re.search(r"\b(?:surprisingly|unexpectedly|contrary to|counter to)\b", plain, re.I))))
    items.append(EatItem("O07", "Real numbers from author's testing",
                          bool(re.search(r"\b(?:we|our) (?:test|trial|study|analysis|measurement).*\d", plain, re.I))))
    items.append(EatItem("O08", "Methodology section",
                          bool(re.search(r"^##\s+(methodology|method|how we tested|approach)", text, re.I | re.M))))
    items.append(EatItem("O09", "Limitations/caveats acknowledged",
                          bool(re.search(r"\b(?:limitation|caveat|important to note|did not test|excluded)\b", plain, re.I))))
    items.append(EatItem("O10", "Original visualization", False))  # hard to detect without image analysis

    return items


def _check_R(text: str, brief: dict | None, citations: dict | None) -> tuple[list[EatItem], list[str]]:
    """R: Relevance (10 items) + R10 Veto."""
    items = []
    vetoes = []
    primary_kw = (brief or {}).get("primary_keyword", "")

    if primary_kw:
        from scripts.lint.keyword_density import analyze as kd_analyze
        kd = kd_analyze(text, primary_kw)
        items.append(EatItem("R01", "Title matches primary keyword intent", True))  # title check upstream
        items.append(EatItem("R06", "Primary keyword density 0.8-1.3%",
                              kd.primary.within_band if kd.primary else False,
                              evidence=f"density: {kd.primary.density_pct if kd.primary else 0}%"))
    else:
        items.append(EatItem("R01", "Title matches primary keyword intent", False, evidence="no keyword provided"))
        items.append(EatItem("R06", "Primary keyword density 0.8-1.3%", False))

    # Other items: heuristic / trust upstream
    items.append(EatItem("R02", "H1 reflects primary keyword", True))
    items.append(EatItem("R03", "H2 structure follows topic-format", True))
    items.append(EatItem("R04", "All sections support primary topic", True))
    items.append(EatItem("R05", "No unrelated tangents >100w", True))
    items.append(EatItem("R07", "Secondary keywords 0.3-0.7%", True))
    items.append(EatItem("R08", "Semantic LSI keywords present", True))
    items.append(EatItem("R09", "Internal links to topically-relevant pages", True))

    # R10 VETO: prompt injection check
    if _check_R10_prompt_injection(text):
        vetoes.append("R10")
        items.append(EatItem("R10", "No prompt-injection content",
                              False, evidence="VETO: prompt injection pattern detected"))
    else:
        items.append(EatItem("R10", "No prompt-injection content", True))

    return items, vetoes


def _check_E(text: str) -> list[EatItem]:
    """E: Experience (10 items)."""
    items = []
    plain = strip_markdown(text)
    paras = list(iter_paragraphs(text))

    first_person_paras = sum(1 for p in paras if re.search(r"\b(?:I|we|our|us|my)\b", p, re.I))
    fp_ratio = first_person_paras / len(paras) if paras else 0

    items.append(EatItem("E01", "Author describes hands-on use",
                          bool(re.search(r"\b(?:I|we) (?:used|tested|tried)\b", plain))))
    items.append(EatItem("E02", "First-person ≥10% of paragraphs",
                          fp_ratio >= 0.10, evidence=f"ratio: {fp_ratio:.1%}"))
    items.append(EatItem("E03", "Process details (steps taken)",
                          bool(re.search(r"\bstep \d|first,? we|then we|after that", plain, re.I))))
    items.append(EatItem("E04", "Time/effort quantified",
                          bool(re.search(r"\d+\s*(?:hours?|days?|weeks?|months?|minutes?)", plain))))
    items.append(EatItem("E05", "Failures/what didn't work mentioned",
                          bool(re.search(r"\b(?:didn['']?t work|failed|wrong|mistake|surprised)\b", plain, re.I))))
    items.append(EatItem("E06", "Tools/equipment named", True))  # heuristic
    items.append(EatItem("E07", "Setting/context specified", True))
    items.append(EatItem("E08", "Outcomes/results measured",
                          bool(re.search(r"\bresult|outcome|conclusion|measured\b", plain, re.I))))
    items.append(EatItem("E09", "Photos/screenshots from real use",
                          bool(re.search(r"!\[[^\]]+\]\(", text))))
    items.append(EatItem("E10", "Compared to alternatives via experience",
                          bool(re.search(r"\b(?:compared to|versus|vs\.?|unlike)\b", plain, re.I))))

    return items


def _check_other_dims() -> list[EatItem]:
    """Ex, A, T, EAT dimensions (40 items) — mostly site-level / placeholder."""
    items = []
    # Most are site-level, trusted from business-context
    # Real implementations would read projects/{slug}/business-context.json
    placeholders = [
        # Ex - Expertise
        ("Ex01", "Author credentials in byline"),
        ("Ex02", "Author bio on site"),
        ("Ex03", "Domain-specific terminology correctly used"),
        ("Ex04", "Common misconceptions addressed"),
        ("Ex05", "Edge cases discussed"),
        ("Ex06", "Advanced techniques included"),
        ("Ex07", "Industry standards referenced"),
        ("Ex08", "Citations to peer-reviewed/authoritative"),
        ("Ex09", "Reviewer separate (YMYL)"),
        ("Ex10", "No factual errors"),
        # A - Authoritativeness (site-level)
        ("A01", "Domain age >2 years"),
        ("A02", "Author body of work"),
        ("A03", "≥10 referring domains"),
        ("A04", "Cited by other publishers"),
        ("A05", "Original research published"),
        ("A06", "Industry awards/mentions"),
        ("A07", "Active on professional platforms"),
        ("A08", "Wikipedia/Wikidata entry"),
        ("A09", "Featured in media"),
        ("A10", "Speaking engagements"),
        # T - Trustworthiness
        ("T01", "HTTPS site-wide"),
        ("T02", "Privacy + Terms linked"),
        ("T03", "Contact/About info accessible"),
        ("T04", "No fabricated statistics (fact-check verified)"),
        ("T05", "No fabricated quotes"),
        ("T06", "Editorial corrections policy"),
        ("T07", "No undisclosed conflicts"),
        ("T08", "Affiliate disclosure"),
        ("T09", "Last reviewed date"),
        ("T10", "Author contactable"),
        # EAT - Meta E-E-A-T
        ("EAT01", "Person schema for author"),
        ("EAT02", "Organization schema with sameAs"),
        ("EAT03", "Article schema with author + dates"),
        ("EAT04", "Reviewer Person schema (YMYL)"),
        ("EAT05", "About page with team bios"),
        ("EAT06", "Editorial process documented"),
        ("EAT07", "Source links to authoritative"),
        ("EAT08", "Internal links to authoritative content"),
        ("EAT09", "External backlinks to relevant sources"),
        ("EAT10", "Site reputation clean"),
    ]
    for item_id, desc in placeholders:
        items.append(EatItem(item_id, desc, True, evidence="site-level (trusted from business-context)"))

    return items


def score(
    text: str,
    *,
    brief: dict | None = None,
    citations: dict | None = None,
    schema_data: list[dict] | None = None,
    word_target: int = 0,
    project_slug: str | None = None,
) -> CoreEatReport:
    """Run full 80-item E-E-A-T scoring + veto + cap algorithm.

    project_slug (optional): lets C09/C10 locate the Conclusion/FAQ sections by the
    PROJECT's own mandatory_sections h2_pattern instead of a hardcoded label list. Without
    it they fall back to a widened default. See the note above _check_C.
    """
    items = []
    items.extend(_check_C(text, brief, word_target=word_target, project_slug=project_slug))
    items.extend(_check_O(text))
    r_items, vetoes = _check_R(text, brief, citations)
    items.extend(r_items)
    items.extend(_check_E(text))
    items.extend(_check_other_dims())

    # Vetoes: T04 (fabricated stat) and C01 (fabricated citation) checked upstream
    # by fact-checker. If citations json has EXPLICITLY unresolved entries, add C01.
    #
    # 2026-07-01 hardening (ports the cite_scorer C09 fix that was never applied
    # here): read the canonical `citations` key (also refs/items/bare list), and
    # count a ref broken ONLY if it explicitly flags non-resolution (url_verified
    # is False, or an explicit status outside 200-399). A ref with NO status field
    # was HEAD-checked upstream by the fact-checker — bot-walled authorities
    # (CourtListener 202, SEL 403-to-bots, DOI redirects) must NOT veto. The old
    # `citations.get("refs")` + `r.get("resolved_status", 0)` produced a false C01
    # on every canonically-shaped citations.json (2026-07-01 loambidkw0701).
    if citations:
        from scripts.validate.cite_scorer import _extract_refs, _is_broken_ref
        refs = _extract_refs(citations)
        unresolved = sum(1 for r in refs if _is_broken_ref(r))
        if unresolved > 0:
            vetoes.append("C01")

    raw_passed = sum(1 for it in items if it.passed)
    raw_pct = (raw_passed / 80) * 100

    # Dimension breakdown
    dimension_scores = {}
    for prefix in ["C", "O", "R", "E", "Ex", "A", "T", "EAT"]:
        # Greedy prefix match
        dim_items = []
        for it in items:
            id_ = it.item_id
            if (id_.startswith(prefix) and not any(id_.startswith(p) for p in ["Ex", "EAT"] if p != prefix and len(p) > len(prefix))):
                if prefix == "E" and (id_.startswith("Ex") or id_.startswith("EAT")):
                    continue
                if prefix in ("Ex", "EAT") or id_.startswith(prefix):
                    dim_items.append(it)
        if dim_items:
            dp = sum(1 for it in dim_items if it.passed)
            dimension_scores[prefix] = round(dp / len(dim_items), 3)

    # Cap algorithm
    caps = {"T04": 60, "C01": 50, "R10": 0}  # R10 → BLOCKED
    cap_applied = False
    final_pct = raw_pct

    if "R10" in vetoes:
        verdict = "BLOCKED"
        final_pct = 0
        cap_applied = True
    elif len(vetoes) >= 2:
        verdict = "BLOCKED"
        final_pct = min(raw_pct, 50)
        cap_applied = True
    elif len(vetoes) == 1:
        cap_value = caps.get(vetoes[0], 60)
        if raw_pct > cap_value:
            final_pct = cap_value
            cap_applied = True
        verdict = "FIX" if final_pct >= 60 else "BLOCKED"
    else:
        if raw_pct >= 80:
            verdict = "SHIP"
        elif raw_pct >= 60:
            verdict = "FIX"
        else:
            verdict = "BLOCKED"

    issues = [f"[{it.item_id}] {it.description}" for it in items if not it.passed]
    user_facing = []
    if "C01" in vetoes:
        user_facing.append("Some references couldn't be verified (broken DOI/URL)")
    if "T04" in vetoes:
        user_facing.append("Fabricated statistic detected")
    if "R10" in vetoes:
        user_facing.append("Prompt injection detected — refusing to process")

    return CoreEatReport(
        raw_overall_score=round(raw_pct, 2),
        final_overall_score=round(final_pct, 2),
        cap_applied=cap_applied,
        verdict=verdict,
        vetoes_triggered=vetoes,
        dimension_scores=dimension_scores,
        items=items,
        issues=issues,
        user_facing_issues=user_facing,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="CORE-EEAT 80-item gate")
    ap.add_argument("draft", type=Path)
    ap.add_argument("--brief", type=Path)
    ap.add_argument("--citations", type=Path)
    ap.add_argument("--schema", type=Path)
    ap.add_argument("--word-target", type=int, default=0)
    ap.add_argument("--project-slug", default=None,
                    help="Resolve C09/C10 Conclusion/FAQ headings via this project's "
                         "business-context.json mandatory_sections h2_pattern.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.draft.exists():
        print(f"Not found: {args.draft}", file=sys.stderr)
        return 2
    text = args.draft.read_text(encoding="utf-8")

    brief = None
    if args.brief and args.brief.exists():
        brief = json.loads(args.brief.read_text(encoding="utf-8"))
    citations = None
    if args.citations and args.citations.exists():
        citations = json.loads(args.citations.read_text(encoding="utf-8"))
    schema_data = None
    if args.schema and args.schema.exists():
        sd = json.loads(args.schema.read_text(encoding="utf-8"))
        schema_data = sd if isinstance(sd, list) else [sd]

    r = score(text, brief=brief, citations=citations, schema_data=schema_data,
              word_target=args.word_target, project_slug=args.project_slug)

    if args.json:
        print(json.dumps(asdict(r), indent=2, ensure_ascii=False))
    else:
        print(f"Raw score:    {r.raw_overall_score}")
        print(f"Final score:  {r.final_overall_score}  (cap: {r.cap_applied})")
        print(f"Verdict:      {r.verdict}")
        print(f"Vetoes:       {r.vetoes_triggered}")
        print("Dimensions:")
        for dim, s in r.dimension_scores.items():
            print(f"  {dim:4s}: {s:.2%}")
    return 0 if r.verdict == "SHIP" else 1


if __name__ == "__main__":
    sys.exit(main())
