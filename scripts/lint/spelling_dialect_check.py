"""scripts/lint/spelling_dialect_check.py — Detect English dialect drift.

Identifies whether content is en-US / en-UK / en-AU / en-CA / en-NZ based on
spelling pair frequencies. Counts drift words that don't match the target dialect.

WIRED (v3.35, 2026-07-04) as the mandatory `locale-spelling-check` orchestrator
stage — this executor existed since v5.0 but nothing ever invoked it (Rule-6 dead;
the localization-pass SKILL documented it as "TODO"). The real production value for
an AI-writing pipeline is CONSISTENCY-DRIFT detection: en-GB spellings ("colour",
"whilst", "organise") leaking from model training data into en-US articles read as
an AI tell and a trust wobble, even though spelling is not a direct ranking signal
(Mueller 2017/2021). See references/seo/serp-feature-value-2026.md §5.

Workspace mode (the wired stage):
  - resolves the target dialect from state.brief.target_market_locale (en-US
    default; non-English locales no-op PASS — dialect check n/a)
  - EXCLUDES zones where opposite-dialect spellings are legitimate: the
    References/Further Reading tail (UK journal + org titles are verbatim),
    blockquotes (quotations are verbatim), inline code/fences, markdown link
    URLs, and Capitalized mid-sentence words (proper nouns: "Labour Party",
    "Centre for Retail Research")
  - gate semantics: FAIL only at drift_count >= FAIL_THRESHOLD (systemic drift);
    1-2 residual hits surface as warnings (proper-noun/false-positive tolerance)

Dialect pairs (US ↔ UK is the main axis; AU/NZ follow UK; CA mixes both):
  color↔colour  organize↔organise  customize↔customise  realize↔realise
  center↔centre  meter↔metre  defense↔defence  honor↔honour
  catalog↔catalogue  dialog↔dialogue  program↔programme (UK in software context = program)

CLI:
    python -m scripts.lint.spelling_dialect_check --workspace {task_id} --json   # wired stage form
    python -m scripts.lint.spelling_dialect_check --input draft.md --target en-UK --json
    python -m scripts.lint.spelling_dialect_check --stdin --target en-AU
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

# Systemic-drift floor for the wired gate: below this, hits are warnings only
# (tolerates residual proper-noun false positives the zone-stripping missed).
FAIL_THRESHOLD = 3

# locale code (BCP-47-ish, as stored in business-context.location.languages[0])
# -> this module's dialect labels. Unknown/non-English -> None (no-op).
_LOCALE_TO_DIALECT = {
    "en-us": "en-US", "en_us": "en-US", "en": "en-US", "en-usa": "en-US",
    "en-gb": "en-UK", "en_gb": "en-UK", "en-uk": "en-UK",
    "en-au": "en-AU", "en_au": "en-AU",
    "en-ca": "en-CA", "en_ca": "en-CA",
    "en-nz": "en-NZ", "en_nz": "en-NZ",
}


# Format: (US_form, UK_form, regex_us, regex_uk)
DIALECT_PAIRS: list[tuple[str, str, str, str]] = [
    ("color", "colour", r"\bcolor(s|ed|ing|ful|less|ize|s|y)?\b", r"\bcolour(s|ed|ing|ful|less|ise|s|y)?\b"),
    ("organize", "organise", r"\borganiz(e|es|ed|ing|ation|ations|er|ers)\b",
                               r"\borganis(e|es|ed|ing|ation|ations|er|ers)\b"),
    ("customize", "customise", r"\bcustomiz(e|es|ed|ing|ation|able)\b", r"\bcustomis(e|es|ed|ing|ation|able)\b"),
    ("realize", "realise", r"\brealiz(e|es|ed|ing|ation)\b", r"\brealis(e|es|ed|ing|ation)\b"),
    # NOTE (v3.35 fix): the original suffix set included "is"/"es", which matched
    # "analysis"/"analyses" — SAME spelling in both dialects (surfaced as a false
    # positive the first time this script was actually wired; 6 phantom hits on a
    # real draft). Verb-only suffixes now.
    ("analyze", "analyse", r"\banalyz(e|ed|ing|er|ers)\b", r"\banalys(e|ed|ing|er|ers)\b"),
    ("recognize", "recognise", r"\brecogniz(e|es|ed|ing|able|ability)\b", r"\brecognis(e|es|ed|ing|able|ability)\b"),
    ("optimize", "optimise", r"\boptimiz(e|es|ed|ing|ation|er)\b", r"\boptimis(e|es|ed|ing|ation|er)\b"),
    ("specialize", "specialise", r"\bspecializ(e|es|ed|ing|ation)\b", r"\bspecialis(e|es|ed|ing|ation)\b"),
    ("center", "centre", r"\bcenter(s|ed|ing|piece|line)?\b", r"\bcentre(s|d|ing|piece|line)?\b"),
    ("meter", "metre", r"\b(\d+\s*)?meter(s|ed|ing)?\b", r"\b(\d+\s*)?metre(s|d|ing)?\b"),
    ("liter", "litre", r"\b(\d+\s*)?liter(s)?\b", r"\b(\d+\s*)?litre(s)?\b"),
    ("defense", "defence", r"\bdefense(s|less|ive|ively)?\b", r"\bdefence(s|less|ive|ively)?\b"),
    ("honor", "honour", r"\bhonor(s|ed|ing|able|ably|ary)?\b", r"\bhonour(s|ed|ing|able|ably|ary)?\b"),
    ("favor", "favour", r"\bfavor(s|ed|ing|ite|able|ably)?\b", r"\bfavour(s|ed|ing|ite|able|ably)?\b"),
    ("labor", "labour", r"\blabor(s|ed|ing|er|ers|ious)?\b", r"\blabour(s|ed|ing|er|ers|ious)?\b"),
    ("behavior", "behaviour", r"\bbehavior(s|al|ally)?\b", r"\bbehaviour(s|al|ally)?\b"),
    ("catalog", "catalogue", r"\bcatalog(s|ed|ing)?\b", r"\bcatalogue(s|d|ing)?\b"),
    # dialog/dialogue pair REMOVED (v3.35): "dialogue" is standard in US English too
    # (the "dialog" spelling is UI-jargon), so it cannot signal dialect drift.
    ("traveling", "travelling", r"\btraveling\b", r"\btravelling\b"),
    ("traveler", "traveller", r"\btraveler(s)?\b", r"\btraveller(s)?\b"),
    # v3.35 fix: "|d" matched the universal word "tired" as a US form.
    ("tire", "tyre", r"\btire(s)?\b", r"\btyre(s)?\b"),
    ("aluminum", "aluminium", r"\baluminum\b", r"\baluminium\b"),
    ("gray", "grey", r"\bgray(s|ed|ing|ish)?\b", r"\bgrey(s|ed|ing|ish)?\b"),
    ("plow", "plough", r"\bplow(s|ed|ing)?\b", r"\bplough(s|ed|ing)?\b"),
]

# Dialect-specific markers (date format, currency, terms)
US_ONLY = [
    r"\b(?:apartment|sidewalk|elevator|gasoline|fall\s+\d{4}|trash\s+can)\b",
    r"\$\d",  # dollar
]
UK_ONLY = [
    r"\b(?:flat|pavement|lift|petrol|autumn\s+\d{4}|dustbin|whilst)\b",
    r"£\d",   # pound
]
AU_NZ_ONLY = [
    r"\b(?:arvo|brekkie|servo|esky|sunnies)\b",
    r"AU\$|NZ\$",
]
CA_ONLY = [
    r"C\$\d",
    r"\bToonie\b",
]


@dataclass
class DialectReport:
    target_dialect: str
    detected_dialect: str = ""
    us_hits: int = 0
    uk_hits: int = 0
    drift_count: int = 0
    drift_words: list[dict] = field(default_factory=list)
    confidence: str = ""        # low | medium | high
    suggestion: str = ""


def detect_dialect(text: str) -> tuple[int, int, list[dict]]:
    """Count US vs UK spellings + return drift word list."""
    us_count = 0
    uk_count = 0
    hits: list[dict] = []

    for us_form, uk_form, us_re, uk_re in DIALECT_PAIRS:
        us_matches = re.findall(us_re, text, re.IGNORECASE)
        uk_matches = re.findall(uk_re, text, re.IGNORECASE)
        us_n = len(us_matches)
        uk_n = len(uk_matches)
        us_count += us_n
        uk_count += uk_n
        if us_n or uk_n:
            hits.append({
                "pair": f"{us_form} / {uk_form}",
                "us_count": us_n,
                "uk_count": uk_n,
            })

    return us_count, uk_count, hits


def check_drift(text: str, target_dialect: str) -> DialectReport:
    """Check if text matches target dialect."""
    us_n, uk_n, hits = detect_dialect(text)

    detected = "en-US" if us_n > uk_n * 1.5 else ("en-UK" if uk_n > us_n * 1.5 else "mixed")

    target_uses_uk_spelling = target_dialect in {"en-UK", "en-AU", "en-NZ"}
    target_uses_us_spelling = target_dialect in {"en-US"}
    # Canada mostly UK + some US

    drift_words = []
    drift_count = 0
    if target_uses_uk_spelling:
        for h in hits:
            if h["us_count"] > 0:
                drift_count += h["us_count"]
                drift_words.append({**h, "use_instead": h["pair"].split(" / ")[1]})
    elif target_uses_us_spelling:
        for h in hits:
            if h["uk_count"] > 0:
                drift_count += h["uk_count"]
                drift_words.append({**h, "use_instead": h["pair"].split(" / ")[0]})

    total = us_n + uk_n
    if total < 5:
        confidence = "low"
    elif total < 15:
        confidence = "medium"
    else:
        confidence = "high"

    suggestion = ""
    if drift_count > 0:
        suggestion = (f"Replace {drift_count} {detected} spelling(s) with {target_dialect} forms. "
                      f"See drift_words for specific replacements.")

    return DialectReport(
        target_dialect=target_dialect,
        detected_dialect=detected,
        us_hits=us_n,
        uk_hits=uk_n,
        drift_count=drift_count,
        drift_words=drift_words,
        confidence=confidence,
        suggestion=suggestion,
    )


_TAIL_H2_RE = re.compile(r"^##\s+(References|Further Reading)\b.*$", re.I | re.M)
_CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_LINK_URL_RE = re.compile(r"(\[[^\]]*\])\(([^)]+)\)")


def _strip_exempt_zones(body: str) -> str:
    """Remove text where opposite-dialect spellings are legitimate, so the gate
    only sees the pipeline's OWN prose."""
    if body.startswith("---"):
        end = body.find("\n---\n", 3)
        if end > 0:
            body = body[end + 5:]
    m = _TAIL_H2_RE.search(body)
    if m:
        body = body[: m.start()]                       # References/FR tail: verbatim titles
    body = _CODE_FENCE_RE.sub(" ", body)
    body = _INLINE_CODE_RE.sub(" ", body)
    body = _LINK_URL_RE.sub(r"\1", body)               # keep anchor text, drop URL
    body = "\n".join(ln for ln in body.split("\n")
                     if not ln.lstrip().startswith(">"))  # blockquotes: verbatim quotes
    return body


def _is_sentence_start(text: str, pos: int) -> bool:
    """True when the match at `pos` begins a sentence/line/list item — the only
    place a Capitalized drift word still counts (elsewhere it's a proper noun)."""
    i = pos - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    if i < 0:
        return True
    return text[i] in ".!?:\n\"'“‘-*("


def _keyword_exempt_words(brief: dict) -> set[str]:
    """Words (len>=5, lowercased) of the EXACT user-supplied target keyword(s).

    v3.41.3 (Rule 1 executor half): the user's exact keyword IS the SEO target,
    typos/dialect included — 'search engine optimisation consultants' under an
    en-US project MUST keep 'optimisation' in title/H1/body. On 2026-07-19 this
    lint counted 52 intentional keyword inflections as drift and the operator
    had to flip the whole task to en-GB to pass. Same philosophy as the
    References/quotation exemptions: text the pipeline is REQUIRED to reproduce
    verbatim is not the writer's dialect drift.
    """
    kws: list[str] = []
    pk = str(brief.get("primary_keyword") or "")
    if pk:
        kws.append(pk)
    for k in brief.get("keywords") or []:
        kws.append(str(k))
    out: set[str] = set()
    for kw in kws:
        for w in re.findall(r"[A-Za-z]+", kw.lower()):
            if len(w) >= 5:
                out.add(w)
    return out


def _is_keyword_inflection(token: str, exempt_words: set[str]) -> bool:
    """True when token is a keyword word or a direct inflection of one
    (shared prefix >= 6 chars covers optimisation/optimise/optimising)."""
    t = token.lower()
    for w in exempt_words:
        if t == w:
            return True
        n = min(len(t), len(w))
        if n >= 6 and t[:6] == w[:6] and t[: min(n, 7)] == w[: min(n, 7)]:
            return True
    return False


def _count_drift_gate(
    text: str, target_dialect: str, exempt_words: set[str] | None = None,
) -> tuple[int, list[dict]]:
    """Gate-grade drift count: opposite-dialect matches from DIALECT_PAIRS, with a
    proper-noun exemption (Capitalized mid-sentence words like 'Labour Party' or
    'Centre for Retail Research' don't count) and a target-keyword exemption
    (v3.41.3 — see _keyword_exempt_words). en-CA is a mixed dialect — no gate."""
    target_us = target_dialect == "en-US"
    target_uk = target_dialect in {"en-UK", "en-AU", "en-NZ"}
    if not (target_us or target_uk):
        return 0, []
    exempt_words = exempt_words or set()
    drift = 0
    words: list[dict] = []
    for us_form, uk_form, us_re, uk_re in DIALECT_PAIRS:
        wrong_re = uk_re if target_us else us_re
        use_instead = us_form if target_us else uk_form
        n = 0
        samples: list[str] = []
        for m in re.finditer(wrong_re, text, re.IGNORECASE):
            token = m.group(0)
            if token[:1].isupper() and not _is_sentence_start(text, m.start()):
                continue  # proper noun (mid-sentence Capitalized)
            if exempt_words and _is_keyword_inflection(token, exempt_words):
                continue  # the exact SEO target's own spelling (Rule 1)
            n += 1
            if len(samples) < 3:
                samples.append(token)
        if n:
            drift += n
            words.append({"pair": f"{us_form} / {uk_form}", "counted": n,
                          "use_instead": use_instead, "samples": samples})
    return drift, words


def check_workspace(task_id: str) -> dict:
    """Wired-stage entry: resolve locale from state.json, lint the exempt-zone-
    stripped draft, apply the systemic-drift threshold. Returns a gate dict with
    a `passed` flag (the orchestrator's _PASS_FLAG_REQUIRED contract)."""
    ws = PLUGIN_ROOT / "memory" / "workspace" / task_id
    result: dict = {
        "passed": True, "task_id": task_id, "target_dialect": None,
        "locale": None, "drift_count": 0, "drift_words": [],
        "warnings": [], "notes": [], "fail_threshold": FAIL_THRESHOLD,
        "_generated_by": "locale-spelling-check",
    }
    draft = ws / "draft.md"
    if not draft.exists():
        result["passed"] = False
        result["notes"].append("draft.md not found")
        return result
    locale = "en-US"
    brief: dict = {}
    try:
        state = json.loads((ws / "state.json").read_text(encoding="utf-8"))
        brief = state.get("brief", {}) or {}
        locale = str(brief.get("target_market_locale") or "en-US")
    except Exception:
        result["notes"].append("state.json unreadable — defaulting to en-US")
    result["locale"] = locale
    dialect = _LOCALE_TO_DIALECT.get(locale.strip().lower())
    if dialect is None:
        result["notes"].append(
            f"locale {locale!r} is not an English dialect this lint models — no-op PASS")
        return result
    result["target_dialect"] = dialect
    if dialect == "en-CA":
        result["notes"].append("en-CA is a mixed US/UK dialect — gate not applicable, PASS")
        return result

    text = _strip_exempt_zones(draft.read_text(encoding="utf-8"))
    _exempt = _keyword_exempt_words(brief)
    if _exempt:
        result["notes"].append(
            f"target-keyword exemption active for inflections of: {sorted(_exempt)}")
    drift_count, drift_words = _count_drift_gate(text, dialect, _exempt)
    result["drift_count"] = drift_count
    result["drift_words"] = drift_words
    if 0 < drift_count < FAIL_THRESHOLD:
        result["warnings"].append(
            f"{drift_count} opposite-dialect spelling(s) below the systemic "
            f"threshold ({FAIL_THRESHOLD}) — isolated slips; "
            f"fix opportunistically: {[d['pair'] for d in drift_words]}")
    elif drift_count >= FAIL_THRESHOLD:
        result["passed"] = False
        result["notes"].append(
            f"{drift_count} opposite-dialect spellings for target {dialect} — "
            f"systemic drift (AI-tell). Replace via drift_words[].use_instead; "
            f"quotations/References/proper nouns were already exempted.")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="English dialect drift detector")
    ap.add_argument("--input", type=Path)
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--workspace", default=None,
                    help="Task ID — wired-stage mode: locale from state.json, exempt "
                         "zones stripped, threshold gate, writes locale-spelling-lint.json")
    ap.add_argument("--target", default="en-US",
                    choices=["en-US", "en-UK", "en-AU", "en-CA", "en-NZ"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if args.workspace:
        result = check_workspace(args.workspace)
        out = args.out or (PLUGIN_ROOT / "memory" / "workspace" / args.workspace
                           / "locale-spelling-lint.json")
        try:
            out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            flag = "OK" if result["passed"] else "FAIL"
            print(f"  [{flag}] locale-spelling: target={result['target_dialect']} "
                  f"drift={result['drift_count']} (threshold {FAIL_THRESHOLD})")
            for n in result["notes"] + result["warnings"]:
                print(f"    - {n}")
        return 0 if result["passed"] else 1

    if args.stdin:
        text = sys.stdin.read()
    elif args.input:
        if not args.input.exists():
            print(f"File not found: {args.input}", file=sys.stderr)
            return 1
        text = args.input.read_text(encoding="utf-8")
    else:
        print("Need --input, --stdin, or --workspace", file=sys.stderr)
        return 2

    report = check_drift(text, args.target)

    if args.json:
        print(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    else:
        print(f"Target dialect:  {report.target_dialect}")
        print(f"Detected:        {report.detected_dialect}  (confidence: {report.confidence})")
        print(f"US hits:         {report.us_hits}")
        print(f"UK hits:         {report.uk_hits}")
        print(f"Drift count:     {report.drift_count}")
        if report.drift_words:
            print("\nDrift words:")
            for d in report.drift_words[:10]:
                print(f"  {d['pair']:30s}  → use: {d.get('use_instead', '?')}")
        if report.suggestion:
            print(f"\n{report.suggestion}")
    return 0 if report.drift_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
