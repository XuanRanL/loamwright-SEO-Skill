"""scripts/lint/brand_fact_check.py — first-person company-fact consistency lint.

WHY THIS EXISTS (root cure, 2026-07-06, v3.36.0)
================================================
The 2026-07-06 loamwright batch fabricated the agency's OWN tenure three times in
one run — "After five years running Loamwright" (real: 6 years), "After ten years
running local SEO for other shops", "From a decade of client intakes" — and one of
the three shipped into a draft post before a human caught it. Root cause: no layer
supplies `business-context.json :: company` facts to the writer/humanizer/geo
agents, and `agents/writer.md`'s fabrication red line covers EXTERNAL sources and
statistics only — self-referential "experience" numbers slipped through every gate
(fact-checkers treat them as author-experience and strip the claim markers; GEO
scoring actively REWARDS experience phrasing, so the optimize phase pushes agents
toward inventing exactly these numbers).

Same disease family as CLAUDE.md Rules 6/8/9: an instruction existed ("never
fabricate"), but no executor enforced the one category the instruction didn't
name. This lint is that executor.

WHAT IT CHECKS (deliberately conservative — precision over recall)
==================================================================
Only sentences that are SELF-referential (contain a first-person token I/we/my/
our/us, or the brand name) are examined, so third-party advice like "the named
owner should have five plus years running paid media" can never false-fire.

  B1 tenure   : "<N> years running/operating/…", "a decade of …" vs
                company.years_operating. Exact-N mismatch = violation.
                "N+ / N plus years" is allowed when N <= actual (a true floor).
  B2 team     : "team of <N>" vs company.team_size (±30%, min ±2 tolerance).
  B3 clients  : "served/worked with/helped <N>(+) brands|clients|companies|
                businesses" vs company.brands_served — flags OVERCLAIM only
                (N > actual floor); understatement is safe.

No `company` block in business-context.json → no-op PASS (opt-in by having the
facts on file, same backward-compat contract as the other per-project policies).

Output: workspace/brand-fact-lint.json {passed, violations[], ...}; exit 1 on any
violation. Wired as the mandatory `brand-fact-check` orchestrator stage +
run_pipeline gate + pre_publish_gate check (v3.36.0).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

_WORD_NUMS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "a decade": 10, "two decades": 20, "a dozen": 12,
}

# Sentence-initial capitals (We/My/Our) must match; 'us' stays lowercase-only so
# the country abbreviation "US" can never make a third-party sentence look
# self-referential ("agencies in the US charge...").
_FIRST_PERSON_RE = re.compile(r"\b(I|[Ww]e|[Mm]y|[Oo]ur)\b|\bus\b")

# Tenure: "<num>(+|plus)? years (of)? <tenure-verb...>"  — the verb anchor keeps
# durations like "12-month contract" / "3 to 6 months" / bare "five years ago" out.
_TENURE_RE = re.compile(
    r"(?i)\b(?P<num>\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|fifteen|twenty)\s*(?P<plus>\+|plus)?\s+years?\s+(?:of\s+)?"
    r"(?:running|operating|building|leading|doing|serving|consulting|"
    r"in\s+business|at\s+\w)"
)
_DECADE_RE = re.compile(r"(?i)\b(?P<dec>a\s+decade|two\s+decades)\s+of\s+\w+")
_TEAM_RE = re.compile(r"(?i)\bteam\s+of\s+(?P<num>\d{1,3})\b")
_SERVED_RE = re.compile(
    r"(?i)\b(?:served|worked\s+with|helped|partnered\s+with)\s+"
    r"(?:over\s+|more\s+than\s+)?(?P<num>\d{2,6})\s*(?P<plus>\+)?\s*"
    r"(?:brands|clients|companies|businesses)\b"
)
# NOTE (v3.38.0 fix — CTA-1 audit finding): this pattern must NOT carry a
# blanket (?i) flag. With (?i) applied to the whole expression, the NAME
# group's [A-Z][a-z]+ becomes case-INsensitive, so it happily matches a
# lowercase phrase like "our agency" as if it were a capitalized person name.
# Because finditer() never backtracks into text already consumed by a match,
# that false "name" (e.g. in "At our agency, Lewei Zhang, our Head of Sales,
# will review your site.") swallows the leading clause and its OWN trailing
# comma, so the search resumes AFTER "Lewei Zhang," — the real name+wrong-role
# pair is never re-examined and the fabrication silently passes (see
# memory/research/audit_cta_wiring_2026_07_09.json finding CTA-1). The NAME
# group below is therefore matched WITHOUT (?i) (true capitalization required
# via explicit [A-Z]/[a-z] ranges); only the ROLE-adjacent literals ("our",
# "will"/"can"/"has") tolerate case variation via inline (?i:...) groups,
# since role comparison is done downstream by _role_matches() on lowercased
# tokens and never needs the regex itself to be case-insensitive.
_TEAM_MEMBER_MENTION_RE = re.compile(
    r"\b(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?),\s+(?:(?i:our)\s+)?"
    r"(?P<role>[A-Za-z][A-Za-z &/]{2,50}?)(?:,|(?i:\s+will|\s+can|\s+has))"
)
# A case-study proof point's own `period` field ("90 days", "16 months") is a
# legitimate number that may appear in the same sentence as the metric — strip
# it before comparing digits so it can never be mistaken for (or coincidentally
# mask) a fabricated metric number.
_TIME_UNIT_NUM_RE = re.compile(
    r"(?i)\d[\d,]*\s*(?:day|days|week|weeks|month|months|year|years|hour|hours)\b"
)
# Markdown image/link markup and bare URLs carry incidental digits that are NOT
# claim numbers — an avatar upload path like
# ![Lewei Zhang](https://.../uploads/2026/06/james-founder.jpg) contributes
# "2026"/"06", and a dated blog URL its year. A founder-avatar CTA banner that
# legitimately quotes a real proof metric ("2 to 45 daily clicks in 90 days")
# was hard-vetoed on those URL digits (2026-07-08). Strip this markup before the
# blanket digit scan so only prose numbers are compared to the proof metric.
_URL_NOISE_RE = re.compile(r"!?\[[^\]]*\]\([^)]*\)|https?://\S+")

# Words too common to anchor a case-study subject (see the proof-point check's
# comment block for the full reasoning). Module-level since v3.38.3 (the
# any-match restructure hoisted it out of the per-proof-point loop).
_GENERIC_SUBJECT_WORDS = frozenset({
    "site", "sites", "page", "pages", "website", "websites", "web",
    "online", "store", "stores", "shop", "shops", "company",
    "business", "businesses", "brand", "brands", "client", "clients",
    "team", "group", "project",
})


def _first_int(text: Any) -> int | None:
    if isinstance(text, (int, float)):
        return int(text)
    if not isinstance(text, str):
        return None
    m = re.search(r"\d{1,6}", text)
    return int(m.group(0)) if m else None


def load_company_facts(project_slug: str, bc_file: Path | None = None) -> dict | None:
    """Return parsed company facts, or None when the project declares none."""
    p = bc_file or (PLUGIN_ROOT / "projects" / project_slug / "business-context.json")
    if not p.exists():
        return None
    try:
        bc = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    company = bc.get("company")
    if not isinstance(company, dict) or not company:
        return None
    return {
        "brand_name": bc.get("brand_name") or project_slug,
        "years_operating": _first_int(company.get("years_operating")),
        "team_size": _first_int(company.get("team_size")),
        "brands_served": _first_int(company.get("brands_served")),
        "founder": company.get("founder"),
        "team": company.get("team") or [],
        "proof_points": company.get("proof_points") or [],
    }


def _strip_noise(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def _sentences(body: str) -> list[tuple[int, str]]:
    """(1-based line, sentence) pairs — line = where the sentence starts."""
    out: list[tuple[int, str]] = []
    for i, line in enumerate(body.splitlines(), start=1):
        for sent in re.split(r"(?<=[.!?])\s+", line):
            if sent.strip():
                out.append((i, sent.strip()))
    return out


def _is_self_sentence(sentence: str, brand_name: str) -> bool:
    if _FIRST_PERSON_RE.search(sentence):
        return True
    return bool(brand_name) and brand_name.lower() in sentence.lower()


def _parse_num(raw: str) -> int | None:
    raw = raw.strip().lower()
    if raw.isdigit():
        return int(raw)
    return _WORD_NUMS.get(raw)


# Low-signal connector words stripped before comparing role titles as token
# sets — "&"/"/" are already separators via the tokenizer's alnum-only regex,
# but "and"/"of"/"the"/"our" still need explicit removal ("Head of Sales" vs
# "Content & Digital PR Lead" must not accidentally share "of"-adjacent noise).
_ROLE_STOPWORDS = {"and", "the", "of", "our", "a", "an"}


def _role_tokens(role: str) -> set[str]:
    """Lowercase word-token set for a job-title string.

    Splits on whitespace and separators like '&' / '/' / ',' (anything
    non-alphanumeric), then drops _ROLE_STOPWORDS.
    """
    words = re.findall(r"[a-z0-9]+", role.lower())
    return {w for w in words if w not in _ROLE_STOPWORDS}


def _role_matches(claimed_role: str, real_role: str) -> bool:
    """True when claimed_role is an accurate rendering of real_role.

    Uses token-SET containment rather than a strict bidirectional substring
    check, so a natural shortening of a real compound title — e.g. "Technical
    SEO Lead" for the real "Technical SEO & Web Dev Lead" — is recognized as
    correct: {technical, seo, lead} ⊆ {technical, seo, web, dev, lead}.

    A genuinely wrong role ("Head of Sales") shares no meaningful tokens with
    a real title like "Technical SEO & Web Dev Lead" and is not a subset in
    either direction, so it still fires as a violation.

    Kept bidirectional (claimed ⊆ real OR real ⊆ claimed) to preserve the
    original check's intent of also tolerating a claim that restates the full
    real title plus incidental extra wording.
    """
    claimed_tokens = _role_tokens(claimed_role)
    real_tokens = _role_tokens(real_role)
    if not claimed_tokens or not real_tokens:
        # Degenerate capture (e.g. pure punctuation/stopwords) — nothing
        # meaningful to compare, so don't false-fire on it.
        return True
    return claimed_tokens.issubset(real_tokens) or real_tokens.issubset(claimed_tokens)


def lint_brand_facts(body: str, facts: dict) -> list[dict]:
    violations: list[dict] = []
    brand = str(facts.get("brand_name") or "")
    years = facts.get("years_operating")
    team = facts.get("team_size")
    served = facts.get("brands_served")

    for line_no, sent in _sentences(_strip_noise(body)):
        if not _is_self_sentence(sent, brand):
            continue

        if years is not None:
            for m in _TENURE_RE.finditer(sent):
                n = _parse_num(m.group("num"))
                if n is None:
                    continue
                plus = bool(m.group("plus"))
                ok = (n == years) or (plus and n <= years)
                if not ok:
                    violations.append({
                        "type": "tenure", "line": line_no,
                        "excerpt": sent[:220], "found": n,
                        "expected": years,
                        "detail": (f"first-person tenure claim '{m.group(0)}' says {n} "
                                   f"year(s) but business-context.company.years_operating "
                                   f"is {years}. State the real tenure or drop the number."),
                    })
            for m in _DECADE_RE.finditer(sent):
                n = _WORD_NUMS[m.group("dec").lower().replace("  ", " ")]
                if n != years:
                    violations.append({
                        "type": "tenure", "line": line_no,
                        "excerpt": sent[:220], "found": n,
                        "expected": years,
                        "detail": (f"first-person tenure claim '{m.group(0)}' implies "
                                   f"{n} years but company.years_operating is {years}."),
                    })

        if team is not None:
            for m in _TEAM_RE.finditer(sent):
                n = int(m.group("num"))
                tol = max(2, round(team * 0.3))
                if abs(n - team) > tol:
                    violations.append({
                        "type": "team_size", "line": line_no,
                        "excerpt": sent[:220], "found": n, "expected": team,
                        "detail": (f"first-person team-size claim 'team of {n}' vs "
                                   f"company.team_size ~{team} (tolerance ±{tol})."),
                    })

        if served is not None:
            for m in _SERVED_RE.finditer(sent):
                n = int(m.group("num"))
                if n > served:
                    violations.append({
                        "type": "clients_served", "line": line_no,
                        "excerpt": sent[:220], "found": n, "expected": served,
                        "detail": (f"first-person client-count claim exceeds the "
                                   f"documented floor company.brands_served ({served}+)."),
                    })

    team = {m["name"]: m.get("role", "") for m in facts.get("team", [])}
    proof_points = facts.get("proof_points", [])

    for line_no, sent in _sentences(_strip_noise(body)):
        for m in _TEAM_MEMBER_MENTION_RE.finditer(sent):
            name, claimed_role = m.group("name"), m.group("role").strip()
            if name not in team:
                continue  # not a name we track; not our concern
            real_role = team[name]
            if real_role and not _role_matches(claimed_role, real_role):
                violations.append({
                    "type": "team_member", "line": line_no,
                    "excerpt": sent[:220], "found": claimed_role, "expected": real_role,
                    "detail": (f"'{name}' is described as '{claimed_role}' but "
                               f"business-context.company.team lists their role as "
                               f"'{real_role}'."),
                })

        # Only check sentences that reference a specific case study's subject.
        # NOTE: anchor on any distinctive (>=4 char) subject word, not just
        # subject.split()[0] — a leading abbreviation like "B2B" in
        # "B2B filament manufacturer" almost never appears verbatim in body
        # prose ("a filament manufacturer"), so a first-word-only anchor
        # silently skips every real sentence and never fires.
        # Generic words are too common to anchor a case-study subject: a
        # news digest that merely mentions "publisher websites" or "an
        # online store" must NOT be matched to an "Ecommerce site" case
        # study. Anchor only on DISTINCTIVE subject words, and match on
        # WORD BOUNDARIES (not substrings) so "site" cannot match inside
        # "websites"/"sites" (the 2026-07-08 weekly-digest false positive:
        # the Define Media Group "64 publisher websites" news stat was
        # flagged against the "Ecommerce site" proof point).
        #
        # v3.38.3 ANY-MATCH root cure (2026-07-09 loamwright batch false
        # positive): when SEVERAL proof points share an anchor word (loamwright
        # has TWO ecommerce case studies: "Ecommerce site" 128K clicks/16mo and
        # "New ecommerce store" 0→14.3K/7mo), a sentence citing the FIRST one's
        # numbers verbatim was still flagged against the SECOND (the old loop
        # checked each candidate independently and any single mismatch fired).
        # The check now collects every subject-anchored candidate first and
        # flags ONLY when the sentence's numbers are consistent with NONE of
        # them — citing any one real proof point verbatim always passes.
        candidates: list[tuple[dict, str, list[str]]] = []
        for pp in proof_points:
            if pp.get("type") != "case_study" or not pp.get("metric"):
                continue
            subject = str(pp.get("subject", ""))
            metric_numbers = re.findall(r"\d[\d,]*", str(pp["metric"]))
            if not subject or not metric_numbers:
                continue
            subject_words = [w for w in re.findall(r"[A-Za-z]+", subject.lower())
                              if len(w) >= 4 and w not in _GENERIC_SUBJECT_WORDS]
            if subject_words and not any(
                re.search(rf"\b{re.escape(w)}\b", sent.lower()) for w in subject_words
            ):
                continue
            candidates.append((pp, subject, metric_numbers))
        # Only a SELF-referential sentence (first-person, or one that names the
        # brand) can be a fabricated proof-point CLAIM — the lint's documented
        # scope (module docstring). Without this guard the check fired on any
        # non-self sentence that merely shared a case-study subject word plus a
        # number (e.g. an ecommerce-topic article's citation years / an HTTP 301
        # / a References title), producing false positives on every ecommerce
        # article. A real fabricated claim ("we grew an ecommerce client 300%")
        # is self-referential and is still caught.
        if candidates and _is_self_sentence(sent, brand):
            _scan_sent = _TIME_UNIT_NUM_RE.sub("", _URL_NOISE_RE.sub(" ", sent))
            sent_numbers = re.findall(r"\d[\d,]*", _scan_sent)
            if sent_numbers:
                scored = sorted(
                    ((len([n for n in sent_numbers
                           if n not in metric_numbers and len(n) > 1]),
                      pp, subject, metric_numbers)
                     for pp, subject, metric_numbers in candidates),
                    key=lambda t: t[0],
                )
                best_mismatch_count, best_pp, best_subject, best_metric = scored[0]
                if best_mismatch_count > 0:
                    violations.append({
                        "type": "proof_point", "line": line_no,
                        "excerpt": sent[:220], "found": sent_numbers,
                        "expected": best_metric,
                        "candidates_checked": [s for _, _, s, _ in scored],
                        "detail": (f"sentence cites number(s) {sent_numbers} but no "
                                   f"documented case study matches — closest is "
                                   f"'{best_subject}' ('{best_pp['metric']}'). All "
                                   f"anchored candidates checked: "
                                   f"{[s for _, _, s, _ in scored]} — verify before "
                                   f"shipping."),
                    })

    return violations


def run(draft_path: Path, project_slug: str, bc_file: Path | None = None) -> dict:
    facts = load_company_facts(project_slug, bc_file=bc_file) if (project_slug or bc_file) else None
    if facts is None:
        return {
            "passed": True,
            "company_facts_present": False,
            "violations": [],
            "_note": ("no business-context.company facts for this project — lint is a "
                      "no-op PASS (opt in by adding company.years_operating etc.)"),
        }
    body = draft_path.read_text(encoding="utf-8")
    violations = lint_brand_facts(body, facts)
    return {
        "passed": not violations,
        "company_facts_present": True,
        "checked": {k: facts.get(k) for k in
                    ("years_operating", "team_size", "brands_served", "brand_name")},
        "violations": violations,
        "_note": ("first-person company-fact consistency vs business-context.company "
                  "(v3.36.0 root cure for the 2026-07-06 tenure fabrications)"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="First-person company-fact consistency lint")
    ap.add_argument("--workspace", help="task id (resolves draft + project from state.json)")
    ap.add_argument("--draft", help="explicit draft.md path (with --project-slug or --bc-file)")
    ap.add_argument("--project-slug", default="")
    ap.add_argument("--bc-file", help="explicit business-context.json (tests/overrides)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", help="also write the JSON report here")
    args = ap.parse_args()

    if args.workspace:
        ws = PLUGIN_ROOT / "memory" / "workspace" / args.workspace
        draft = ws / "draft.md"
        slug = args.project_slug
        if not slug:
            try:
                slug = json.loads((ws / "state.json").read_text(encoding="utf-8")).get(
                    "project_slug", "")
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                slug = ""
    else:
        if not args.draft:
            print("--workspace or --draft required", file=sys.stderr)
            return 2
        draft = Path(args.draft)
        slug = args.project_slug

    if not draft.exists():
        print(f"draft not found: {draft}", file=sys.stderr)
        return 2

    report = run(draft, slug, bc_file=Path(args.bc_file) if args.bc_file else None)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"brand_fact_check: {'PASS' if report['passed'] else 'FAIL'}"
              f" ({len(report['violations'])} violation(s))")
        for v in report["violations"]:
            print(f"  [{v['type']}] L{v['line']}: found {v['found']} vs expected "
                  f"{v['expected']} — {v['excerpt'][:120]}")
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
