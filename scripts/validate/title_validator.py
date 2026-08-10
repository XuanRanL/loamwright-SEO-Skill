"""
scripts/validate/title_validator.py — register-aware, evidence-based SEO title validator.

REWRITTEN 2026-06-16. Basis: docs/title-optimization-plan-2026-06-16.md +
auto-memory reference_title_optimization_evidence_2026_06_16.md (deep-research
run wf_adbc50a2-331, 19 claims confirmed / 6 killed).

This validator checks the **`seo_title`** — the short string that lands in the indexed
`<title>` / `rank_math_title` / `og:title`. The longer human **H1** (the WordPress post
`title` field) is validated only for *alignment* with the seo_title, not against the same
length/format rules.

What changed vs the 2024 formula (and why):

  * Power word is NO LONGER mandatory. The strongest causal evidence (Nature Human Behaviour
    2023, 22,743 RCTs) shows positive "power words" slightly DECREASE CTR; the old "≥1 power
    word" hard gate was unsupported and tonally wrong for grief/B2B. Now register-gated:
    optional (default), discouraged (B2B → warn), or banned (grief → fail). The anti-spam
    ceiling (>2 power words = fail) is kept.

  * Digit is NO LONGER mandatory. The "+36% CTR" basis did not survive verification. A digit
    is now optional; and when it IS in the seo_title it MUST also appear in the H1 — Zyppy
    found Google preserves a number in the displayed title 97.3% of the time when it is in
    BOTH fields, vs stripping it otherwise.

  * Length recalibrated to the 51–60 sweet spot (Zyppy): hard-fail >65 or <30, warn 61–65.
    (Truncation is really a ~600px pixel budget; chars are a proxy.)

  * NEW gates: H1↔seo_title alignment, parenthesized/bracketed year-suffix rewrite-risk flag,
    register-specific banned terms (hype words for B2B; commercial superlatives + urgency for
    grief), and a light clickbait-phrase flag.

  * KEPT: primary keyword present (softened — >1 warns instead of failing), sentence case.

CLI:
    python -m scripts.validate.title_validator "1000 watt LED grow light: real draw vs equivalent" \
        --primary "1000 watt led grow light" --register b2b_technical --json
    python -m scripts.validate.title_validator "7 best ... tested" --primary "..." \
        --register b2b_technical --h1 "The 7 best ... for 2026 ..." --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path


# --------------------------------------------------------------------------- #
# Power Word library (loaded from references/seo/power-words.md, inline fallback)
# --------------------------------------------------------------------------- #
POWER_WORDS_DEFAULT = {
    # Authority
    "proven", "expert", "data-backed", "research-based", "certified",
    "tested", "verified", "documented", "audited",
    # Action
    "step-by-step", "actionable", "practical", "hands-on", "quick",
    "instant", "easy", "simple", "effective",
    # Result
    "high-impact", "results-focused", "time-saving", "cost-cutting",
    "revenue-boosting", "conversion-lifting", "profitable", "productive",
    "game-changing",
    # Emotion (sparingly)
    "effortless", "guaranteed", "bulletproof", "surprising", "eye-opening",
    "mind-blowing", "brilliant", "powerful", "smart",
    # Specificity
    "complete", "comprehensive", "ultimate", "definitive", "all-inclusive",
    "total", "full", "master", "advanced",
}

# Register-specific banned vocabularies (HARD fail when matched in that register).
HYPE_WORDS = frozenset({
    "amazing", "revolutionary", "game-changing", "game-changer", "mind-blowing",
    "unbelievable", "insane", "epic", "must-have", "jaw-dropping",
})
URGENCY_WORDS = frozenset({
    "now", "hurry", "limited", "last chance", "act fast", "don't miss",
    "today only", "while supplies last",
})
# Commercial / superlative / hard-sell terms that are tonally wrong for grief content.
GRIEF_COMMERCIAL = frozenset({
    "best", "top", "cheapest", "deal", "sale", "ranked", "guaranteed",
    "#1", "discount", "bargain", "review",
})

# Light clickbait phrases (soft WARNING, not a hard fail).
CLICKBAIT_PHRASES = frozenset({
    "you won't believe", "this one trick", "this simple trick",
    "what happens next", "will shock you", "doctors hate", "the secret to",
})


@dataclass(frozen=True)
class RegisterProfile:
    """Per-register title policy. `power_word_policy` / `digit_policy` are one of the
    documented enums; `banned_terms` are HARD-fail when present."""
    power_word_policy: str   # "optional" | "discouraged" | "banned"
    digit_policy: str        # "optional" | "encouraged" | "discouraged"
    banned_terms: frozenset[str]


REGISTER_PROFILES: dict[str, RegisterProfile] = {
    "default": RegisterProfile("optional", "optional", frozenset()),
    "b2b_technical": RegisterProfile("discouraged", "encouraged", HYPE_WORDS),
    "b2b_procurement": RegisterProfile("discouraged", "encouraged", HYPE_WORDS),
    "dtc_celebration": RegisterProfile("optional", "optional", HYPE_WORDS | URGENCY_WORDS),
    "dtc_grief": RegisterProfile(
        "banned", "discouraged", HYPE_WORDS | URGENCY_WORDS | GRIEF_COMMERCIAL
    ),
    "ecommerce": RegisterProfile("optional", "optional", frozenset()),
}


@dataclass
class TitleCheckResult:
    title: str
    primary_keyword: str
    register: str
    length: int
    in_length_band: bool
    length_warn: bool                      # 61–65 chars (approaching truncation)
    keyword_count: int
    keyword_present: bool
    power_words_found: list[str]
    power_word_policy_ok: bool
    digit_count: int
    digit_policy_ok: bool
    digit_in_h1: bool | None               # None when no digit or no H1 supplied
    h1_keyword_aligned: bool | None        # None when no H1 supplied
    is_title_case_whole: bool
    not_title_case: bool
    punctuation_risk: list[str]
    banned_terms_found: list[str]
    clickbait_terms_found: list[str]
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    all_passed: bool = False


def _plugin_root() -> Path | None:
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "VERSION").exists() and (p / ".claude-plugin").is_dir():
            return p
        p = p.parent
    return None


def load_power_words() -> set[str]:
    """Load power words from references/seo/power-words.md, fallback to inline."""
    plugin = _plugin_root()
    if plugin:
        ref = plugin / "references" / "seo" / "power-words.md"
        if ref.exists():
            try:
                text = ref.read_text(encoding="utf-8")
                found: set[str] = set()
                # Scrape ONLY the first cell of a markdown table row ("| **Word** | ... |").
                # Prose bold in the surrounding copy (e.g. **OPTIONAL**, **HARD-BANNED**,
                # **Source**) must NOT be loaded — otherwise ordinary words get treated as
                # power words and wrongly hard-fail the dtc_grief register. (Audit B1, 2026-06-16.)
                for m in re.finditer(r"^\|\s*\*\*([^*|]+?)\*\*\s*\|", text, re.MULTILINE):
                    found.add(m.group(1).strip().lower())
                if found:
                    return found
            except Exception as exc:  # pragma: no cover - diagnostic only
                print(f"[title_validator] power-words.md parse failed: {exc}",
                      file=sys.stderr)
    return set(POWER_WORDS_DEFAULT)


def infer_register(voice_default: dict[str, object] | None) -> str:
    """Map a project's business-context.json :: voice_default to a register key.

    NOTE: tender/emotional brands (e.g. project-hotel) return 'dtc_celebration' as the SAFE
    default. Memorial / pet-loss / grief articles must override to 'dtc_grief' per-article,
    because a single project can span both registers.
    """
    if not voice_default:
        return "default"
    pair = voice_default.get("pair")
    if isinstance(pair, list):
        text = " ".join(str(x) for x in pair)
    elif isinstance(pair, str):
        text = pair
    else:
        text = ""
    t = text.lower()
    if "procurement" in t or "buyer" in t:
        return "b2b_procurement"
    if any(w in t for w in ("tender", "emotional", "grief", "memorial", "artisan", "gentle")):
        return "dtc_celebration"
    if any(w in t for w in ("technical", "professional", "authoritative", "manufacturing", "b2b")):
        return "b2b_technical"
    if any(w in t for w in ("ecommerce", "commerce", "retail", "shop", "product")):
        return "ecommerce"
    return "default"


def _find_power_words(title_lower: str, power_words: set[str]) -> list[str]:
    found: list[str] = []
    for pw in sorted(power_words, key=len, reverse=True):
        if not pw:
            continue
        if " " in pw or "-" in pw:
            if pw in title_lower and not any(pw in p for p in found if p != pw):
                found.append(pw)
        elif re.search(rf"\b{re.escape(pw)}\b", title_lower):
            found.append(pw)
    return list(dict.fromkeys(found))


def _term_present(title_lower: str, term: str) -> bool:
    term = term.lower()
    if re.fullmatch(r"#\d+", term):  # "#1" must not match "#10"/"#15" (audit S1)
        return re.search(re.escape(term) + r"(?!\d)", title_lower) is not None
    if re.fullmatch(r"[a-z0-9\-]+", term):
        return re.search(rf"\b{re.escape(term)}\b", title_lower) is not None
    return term in title_lower


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+", text))


def _count_numbers(text: str) -> set[str]:
    """Standalone count-style integers (the '7' in '7 best ...'), EXCLUDING numbers that are
    part of a spec / dimension / version token (5x5, V4.0, 12V, 400-500 nm, 2.7 µmol/J). Only
    count-style numbers are subject to the H1 number-preservation rule; spec numbers belong to
    the entity/keyword (checked separately) and routinely differ in surface form between the
    seo_title and the H1, so enforcing them caused false hard-fails. (Audit B2, 2026-06-16.)"""
    out: set[str] = set()
    glue = "xX×/.-"
    for m in re.finditer(r"\d+", text):
        s, e = m.start(), m.end()
        before = text[s - 1] if s > 0 else " "
        after = text[e] if e < len(text) else " "
        if before in glue or after in glue or before.isalpha() or after.isalpha():
            continue
        out.add(m.group())
    return out


def check(
    title: str,
    primary_keyword: str,
    *,
    register: str = "default",
    h1: str | None = None,
    min_length: int = 30,
    soft_max: int = 60,
    max_length: int = 65,
    power_words: set[str] | None = None,
) -> TitleCheckResult:
    """Validate a `seo_title`. See module docstring for the rule rationale.

    `title` is the seo_title (short, SERP-bound). `h1` (optional) is the longer post title;
    when supplied, alignment between the two is checked (Zyppy number-preservation lever).
    """
    if power_words is None:
        power_words = load_power_words()
    profile = REGISTER_PROFILES.get(register, REGISTER_PROFILES["default"])

    title = title.strip()
    primary_keyword = primary_keyword.strip()
    title_lower = title.lower()
    length = len(title)

    issues: list[str] = []
    warnings: list[str] = []

    # --- 1. Length ------------------------------------------------------- #
    in_length_band = min_length <= length <= max_length
    length_warn = soft_max < length <= max_length
    if length > max_length:
        issues.append(
            f"seo_title too long: {length} chars (>{max_length}). Google rewrites "
            f">{soft_max}-char titles >76% of the time; aim 51–60. Move detail to the H1."
        )
    elif length < min_length:
        issues.append(f"seo_title too short: {length} chars (need ≥{min_length}).")
    elif length_warn:
        warnings.append(
            f"seo_title is {length} chars — in the 61–65 warn band; trim toward 51–60 "
            f"to avoid SERP truncation/rewrite."
        )

    # --- 2. Primary keyword (present; >1 warns) -------------------------- #
    if primary_keyword:
        keyword_count = len(
            re.compile(rf"\b{re.escape(primary_keyword)}\b", re.IGNORECASE).findall(title)
        )
    else:
        keyword_count = 0
    keyword_present = keyword_count >= 1
    if not keyword_present:
        issues.append(f"Primary keyword '{primary_keyword}' MISSING from seo_title.")
    elif keyword_count > 1:
        warnings.append(
            f"Primary keyword '{primary_keyword}' appears {keyword_count}× — once is enough."
        )

    # --- 3. Power words (register-gated; >2 always fails) ---------------- #
    power_words_found = _find_power_words(title_lower, power_words)
    power_word_policy_ok = True
    if len(power_words_found) > 2:
        power_word_policy_ok = False
        issues.append(f"Too many power words: {power_words_found} (max 2; spammy/AI-tell).")
    elif power_words_found:
        if profile.power_word_policy == "banned":
            power_word_policy_ok = False
            issues.append(
                f"Power word(s) {power_words_found} are BANNED in the '{register}' register "
                f"(tonally wrong for this content)."
            )
        elif profile.power_word_policy == "discouraged":
            warnings.append(
                f"Power word(s) {power_words_found} — discouraged in '{register}'; let "
                f"specificity be the authority signal (positive power words can slightly "
                f"lower CTR per Nature 2023)."
            )

    # --- 4. Digit (optional; alignment with H1 when present) ------------- #
    title_numbers = _count_numbers(title)   # only count-style numbers (audit B2)
    digit_count = len(re.findall(r"\d+", title))
    digit_policy_ok = True
    if digit_count and profile.digit_policy == "discouraged":
        warnings.append(
            f"seo_title contains a number — discouraged in '{register}'; if kept, frame it "
            f"gently (e.g. 'a few gentle ideas'), never 'Top N / Ranked'."
        )

    digit_in_h1: bool | None = None
    h1_keyword_aligned: bool | None = None
    if h1 is not None:
        h1_numbers = _numbers(h1)
        # H1 keyword alignment (warning)
        if primary_keyword:
            h1_keyword_aligned = bool(
                re.search(rf"\b{re.escape(primary_keyword)}\b", h1, re.IGNORECASE)
            )
            if not h1_keyword_aligned:
                warnings.append(
                    "H1 does not contain the primary keyword — align it with the seo_title "
                    "to reduce Google's title rewriting (61.6% → 20.6% when aligned)."
                )
        # Number preservation (hard fail): every seo_title number must be in the H1.
        if title_numbers:
            missing = title_numbers - h1_numbers
            digit_in_h1 = not missing
            if missing:
                digit_policy_ok = False
                issues.append(
                    f"Number(s) {sorted(missing)} in the seo_title are absent from the H1. "
                    f"Google keeps a number in the displayed title 97.3% of the time only "
                    f"when it is in BOTH the title and H1 — otherwise it gets stripped."
                )

    # --- 5. Sentence case (kept; AI-tell / house style) ------------------ #
    words = re.findall(r"\b[A-Za-z][a-z']*\b", title)
    if len(words) >= 4:
        title_case_count = sum(1 for w in words if w[0].isupper() and len(w) > 2)
        is_title_case_whole = title_case_count >= len(words) * 0.75
    else:
        is_title_case_whole = False
    not_title_case = not is_title_case_whole
    if is_title_case_whole:
        # House-style preference, NOT a hard veto — no CTR evidence for sentence vs Title case,
        # and many legitimate brand corpora are Title Case. Surfaced as a warning only.
        warnings.append("seo_title is in Title Case; sentence case is the house preference "
                        "(style only — not a CTR factor).")

    # --- 6. Punctuation rewrite-risk (warn) ------------------------------ #
    punctuation_risk: list[str] = []
    if re.search(r"\((?:19|20)\d{2}\)", title):
        punctuation_risk.append("parenthesized-year")
        warnings.append(
            "Parenthesized year e.g. '(2026)' — parentheses are changed by Google ~61.9% of "
            "the time. Prefer integrating the year into the H1, not the seo_title."
        )
    if re.search(r"\[(?:19|20)\d{2}\]", title):
        punctuation_risk.append("bracketed-year")
        warnings.append(
            "Bracketed year e.g. '[2026]' — brackets are changed ~77.6% of the time. Move it "
            "to the H1 or drop it from the seo_title."
        )
    if "[" in title and "bracketed-year" not in punctuation_risk:
        punctuation_risk.append("brackets")
        warnings.append("Square brackets raise Google's rewrite likelihood (~77.6%).")

    # --- 7. Register banned terms (HARD fail) ---------------------------- #
    banned_terms_found = [t for t in sorted(profile.banned_terms)
                          if _term_present(title_lower, t)]
    if banned_terms_found:
        issues.append(
            f"Banned term(s) for '{register}' register: {banned_terms_found}."
        )

    # --- 8. Clickbait phrases (warn) ------------------------------------- #
    clickbait_terms_found = [p for p in sorted(CLICKBAIT_PHRASES) if p in title_lower]
    if clickbait_terms_found:
        warnings.append(
            f"Clickbait phrasing {clickbait_terms_found} — a curiosity gap the body doesn't "
            f"close is both a quality-rater risk and a Google 'inaccurate title' rewrite trigger."
        )

    all_passed = not issues

    return TitleCheckResult(
        title=title, primary_keyword=primary_keyword, register=register,
        length=length, in_length_band=in_length_band, length_warn=length_warn,
        keyword_count=keyword_count, keyword_present=keyword_present,
        power_words_found=power_words_found, power_word_policy_ok=power_word_policy_ok,
        digit_count=digit_count, digit_policy_ok=digit_policy_ok,
        digit_in_h1=digit_in_h1, h1_keyword_aligned=h1_keyword_aligned,
        is_title_case_whole=is_title_case_whole, not_title_case=not_title_case,
        punctuation_risk=punctuation_risk, banned_terms_found=banned_terms_found,
        clickbait_terms_found=clickbait_terms_found,
        issues=issues, warnings=warnings, all_passed=all_passed,
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Register-aware SEO title validator (validates the seo_title)."
    )
    ap.add_argument("title", help="The seo_title to validate (the short SERP <title>).")
    ap.add_argument("--primary", required=True, help="Primary keyword (must appear in the title).")
    ap.add_argument("--register", default="default", choices=sorted(REGISTER_PROFILES),
                    help="Brand/content register (gates power-word/digit/banned-term rules).")
    ap.add_argument("--h1", default=None,
                    help="Optional H1 / post title to check seo_title↔H1 alignment.")
    ap.add_argument("--min-length", type=int, default=30)
    ap.add_argument("--soft-max", type=int, default=60)
    ap.add_argument("--max-length", type=int, default=65)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = check(
        args.title, args.primary, register=args.register, h1=args.h1,
        min_length=args.min_length, soft_max=args.soft_max, max_length=args.max_length,
    )

    if args.json:
        out = asdict(r)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        verdict = "✓ PASS" if r.all_passed else "✗ FAIL"
        print(f"seo_title: {r.title}")
        print(f"           (length: {r.length}, register: {r.register})")
        print(f"Primary keyword: '{r.primary_keyword}'  count: {r.keyword_count}")
        print()
        checks = [
            (r.in_length_band, f"Length {args.min_length}-{args.max_length} (target 51–60)"),
            (r.keyword_present, "Primary keyword present"),
            (r.power_word_policy_ok, f"Power-word policy OK ({r.power_words_found or 'none'})"),
            (r.digit_policy_ok, f"Digit policy OK (count: {r.digit_count})"),
            (r.not_title_case, "Sentence case (not Title Case)"),
            (not r.banned_terms_found, f"No banned terms ({r.banned_terms_found or 'none'})"),
        ]
        for ok, label in checks:
            print(f"  {'✓' if ok else '✗'} {label}")
        if r.digit_in_h1 is not None:
            print(f"  {'✓' if r.digit_in_h1 else '✗'} Numbers preserved in H1")
        print()
        print(f"Verdict: {verdict}")
        if r.issues:
            print("\nIssues (hard):")
            for i in r.issues:
                print(f"  ✗ {i}")
        if r.warnings:
            print("\nWarnings (soft):")
            for w in r.warnings:
                print(f"  ! {w}")
    return 0 if r.all_passed else 1


# Backwards-compat alias: a couple of older call sites referenced `validate`.
validate = check
_ = replace  # re-exported dataclasses helper (kept for downstream importers)


if __name__ == "__main__":
    sys.exit(main())
