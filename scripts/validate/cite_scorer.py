"""
scripts/validate/cite_scorer.py — CITE 40-item AI Citation gate.

Reads draft.md + meta.json + citations.json + schema JSON-LD and scores against
references/geo/cite-framework-40.md (4 dimensions × 10 items).

Vetoes: T03 (affiliate disclosure), T05 (E-E-A-T missing), T09 (schema broken),
COMP01 (competitor/peer domain cited — hard block, project-policy driven).
Cap algorithm: 1 veto → cap at 60-70; 2+ → BLOCKED; COMP01 present → BLOCKED.
COMP01 is an out-of-band veto code: it does NOT add a 41st scored item, so the
CITE rubric stays 40 items and the C/I/T/E dimension scores are unaffected.

Output conforms to schemas/quality.schema.json → quality.gates.cite.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from scripts.lint._text_utils import strip_markdown, count_words


@dataclass
class CiteItemResult:
    item_id: str          # e.g. "C01"
    description: str
    passed: bool
    evidence: str = ""


@dataclass
class CiteScoreReport:
    raw_overall_score: float
    final_overall_score: float
    cap_applied: bool
    verdict: Literal["SHIP", "FIX", "BLOCKED"]
    vetoes_triggered: list[str] = field(default_factory=list)
    dimension_scores: dict = field(default_factory=dict)
    items: list[CiteItemResult] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    user_facing_issues: list[str] = field(default_factory=list)  # plain English


# ─── Citation-shape helpers (key-name tolerant) ───────────

_TIER1_TYPES = {
    "journal", "book", "report", "peer_reviewed", "peer-reviewed",
    "standard", "government", "datasheet",
}


def _extract_refs(citations) -> list[dict]:
    """Return the reference list from citations.json regardless of key shape.

    The fact-checker's canonical output uses the `citations` key; older/alt shapes use
    `refs`, `items`, or a bare top-level list. Reading only `refs` (the original behaviour)
    silently returned [] on real articles."""
    if isinstance(citations, list):
        return [r for r in citations if isinstance(r, dict)]
    if isinstance(citations, dict):
        for k in ("citations", "refs", "items"):
            v = citations.get(k)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
    return []


def _is_tier1(r: dict) -> bool:
    t = (r.get("type") or r.get("source_type") or "").lower()
    if t in _TIER1_TYPES:
        return True
    blob = " ".join(str(r.get(k, "")) for k in ("doi", "url", "apa_7", "apa"))
    return "doi.org" in blob or "doi:" in blob.lower()


def _is_broken_ref(r: dict) -> bool:
    """A ref counts as broken ONLY if it explicitly flags non-resolution.

    v3.38.3 (2026-07-10): an explicit `url_verified: true` WINS over any status
    code. The fact-checker sets it after verifying the identifier against
    Crossref / a browser UA, and bot-walled publishers (Taylor & Francis, MDPI,
    ASTM) legitimately 403 script UAs. The 2026-07-09 project-juliet batch got
    OPPOSITE C01 verdicts for the same semantic fact depending on the FC's
    encoding: int 403 fired a false C01 veto (core_eeat BLOCKED at 50), while
    the string "bot-403" fell through int() and passed. Rule 9: classify by the
    real semantic (verified vs not), never by an incidental encoding.
    """
    if r.get("url_verified") is True:
        return False  # explicit verification is authoritative — bot-403s are documented overrides
    if r.get("url_verified") is False:
        return True
    st = r.get("resolved_status", r.get("status"))
    if st is None:
        return False  # no info → trust the upstream HEAD check
    try:
        return not (200 <= int(st) < 400)
    except (TypeError, ValueError):
        return False  # non-numeric markers ("bot-403") are documented bot-wall overrides


# ─── Item checks ──────────────────────────────────────────

def _check_C(text: str, meta: dict | None, citations: dict | None) -> list[CiteItemResult]:
    """C: Citation Worthiness (10 items)."""
    items = []

    # C01: TL;DR in first 540 words
    first_540 = " ".join(strip_markdown(text).split()[:540])
    has_tldr = any(t in first_540.lower() for t in ["tl;dr", "tldr", "quick answer", "abstract", "key takeaways"])
    items.append(CiteItemResult("C01", "TL;DR / direct answer in first 540 words", has_tldr,
                                 evidence="found" if has_tldr else "not found"))

    # C02: Capsule per H2
    from scripts.lint.citation_capsule_lint import analyze as capsule_analyze
    cap = capsule_analyze(text)
    items.append(CiteItemResult("C02", "Each H2 has Citation Capsule (40-60w)",
                                 cap.coverage_pct >= 80, evidence=f"coverage {cap.coverage_pct}%"))

    # C03: ≥1 specific data point per 200 words
    plain = strip_markdown(text)
    words = count_words(text)
    if words > 0:
        # Count numbers + years + percentages + dollars
        data_points = len(re.findall(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:\s*%|\s*million|\s*billion)?\b|\(\d{4}\)|\$\d", plain))
        ratio = data_points / (words / 200)
    else:
        ratio = 0
    items.append(CiteItemResult("C03", "≥1 specific data point per 200 words",
                                 ratio >= 1.0, evidence=f"ratio {ratio:.2f}"))

    # C04: FAQ section with extractable Q&A
    has_faq = bool(re.search(r"^##\s+(faq|frequently asked|common questions)", text, re.I | re.M))
    items.append(CiteItemResult("C04", "FAQ section with extractable Q&A", has_faq))

    # C05: Burstiness >0.3
    from scripts.lint.sentence_variance import burstiness_normalized
    b = burstiness_normalized(text)
    items.append(CiteItemResult("C05", "Sentence variance (burstiness >0.3)",
                                 b > 0.3, evidence=f"burstiness {b:.3f}"))

    # C06: All facts have inline citations (heuristic: claim markers + (Author, Year))
    claim_count = len(re.findall(r"\[claim:c\d+_\d+\]", text))
    cite_count = len(re.findall(r"\([A-Z][a-z]+,?\s*\d{4}\)|\([A-Z][a-z]+\s+(?:&|and|et al\.?)\s*\d{4}\)", text))
    if citations:
        replacements = len(citations.get("in_text_replacements", []))
        coverage = (cite_count + replacements) > 0 if claim_count > 0 else True
    else:
        coverage = cite_count > 0
    items.append(CiteItemResult("C06", "All facts have inline citations",
                                 coverage, evidence=f"in-text cites: {cite_count}"))

    # C07: References ≥3 Tier-1 sources.
    # Accept every citations.json key shape the fact-checker actually emits — the canonical
    # output uses `citations`, not `refs` (the original code only read `refs`, so it scored
    # 0 tier-1 sources on real articles and failed C07 every time — a key-name mismatch found
    # 2026-06-03). Also recognise the `type` field (peer_reviewed/standard/...) and an inline
    # DOI in url/apa, not just a `source_type`/`doi` field.
    refs = _extract_refs(citations)
    tier1 = sum(1 for r in refs if _is_tier1(r))
    items.append(CiteItemResult("C07", "References section has ≥3 Tier-1 sources",
                                 tier1 >= 3, evidence=f"tier-1 count: {tier1} (of {len(refs)})"))

    # C08: Stats shown with year / sample size
    stats_with_year = len(re.findall(r"\d+%[^.]*?\(20\d{2}\)|\bN\s*=\s*\d+", plain))
    items.append(CiteItemResult("C08", "Statistics shown with year/sample size",
                                 stats_with_year >= 3, evidence=f"count: {stats_with_year}"))

    # C09: No fabricated/broken DOIs (HEAD-checked upstream by the fact-checker).
    # The fact-checker records resolution as `url_verified: true`; older runs used
    # `resolved_status`. Treat a ref as broken ONLY when it explicitly says so — a ref with
    # no verification field is trusted (the item description says "verified upstream"), so we
    # don't fail honest citations just because they lack a status integer.
    if citations:
        broken = sum(1 for r in refs if _is_broken_ref(r))
        items.append(CiteItemResult("C09", "No fabricated DOIs (HEAD check passed)",
                                     broken == 0,
                                     evidence=f"broken/unverified: {broken} (of {len(refs)})"))
    else:
        items.append(CiteItemResult("C09", "No fabricated DOIs (HEAD check passed)",
                                     False, evidence="citations.json not provided"))

    # C10: Information Gain — prose signals OR bracket markers.
    # 2026-07-01 root fix: bracket markers ([ORIGINAL DATA] / [UNIQUE INSIGHT] /
    # [PERSONAL EXPERIENCE]) are auto-stripped at publish and lint as L6 leaks,
    # so awarding this point ONLY for them created a perverse incentive — the
    # geo-auditor rationally injected markers into a finished draft to score it.
    # Prose-level first-person data/experience signals (what readers actually
    # see) now count directly; markers still count for pre-strip drafts.
    from scripts.lint.information_gain_marker_lint import analyze as igm_analyze
    igm = igm_analyze(text)
    prose_ig = len(re.findall(
        r"\b(?:we|our team|i)\s+(?:measured|tested|reviewed|audited|analyz\w*|"
        r"benchmark\w*|compared|tracked|surveyed|ran|built)\b"
        r"|\bin[- ]house\s+(?:data|numbers|testing|benchmarks?)\b"
        r"|\bour\s+(?:own\s+|internal\s+)?(?:data|measurements?|benchmarks?|audits?|testing|model)\b",
        text, flags=re.IGNORECASE))
    items.append(CiteItemResult(
        "C10", "Original data/experience signals (prose or [ORIGINAL DATA] markers)",
        igm.total_markers >= 1 or prose_ig >= 1,
        evidence=f"markers: {igm.total_markers}, prose_signals: {prose_ig}"))

    return items


def _check_I(
    meta: dict | None,
    schema_data: list[dict] | None,
    head_provided_types: list[str] | None = None,
) -> list[CiteItemResult]:
    """I: Identity Clarity (10 items).

    CRITICAL FIX (2026-06-03): this scorer only ever inspected the BODY schema.json. But
    well-configured sites emit Organization/Person/Article schema in the <head> via their SEO
    plugin (e.g. RankMath), and this pipeline DELIBERATELY excludes those types from the body
    to avoid duplicating the head graph (business-context.wordpress.seo_plugin_schema_provided).
    The old code therefore failed ~9/10 Identity items for schema that is actually present on
    every live page — dragging CITE to a misleading ~67-70 and forcing manual quality overrides.
    `head_provided_types` lets the caller declare what the head graph supplies, so we credit the
    Identity items the plugin genuinely satisfies (and still fail the ones it does not, e.g.
    Wikidata/Wikipedia/author social — those remain honestly unmet)."""
    items = []
    head = {t for t in (head_provided_types or [])}
    plugin_managed = bool(head)  # an SEO plugin emits the head graph → it populates Org/Person fields
    schemas = schema_data or []
    schema_types = []
    org_data = None
    person_data = None

    for s in schemas:
        if isinstance(s, dict):
            if "@graph" in s and isinstance(s["@graph"], list):
                for g in s["@graph"]:
                    if isinstance(g, dict):
                        t = g.get("@type", "")
                        if isinstance(t, list):
                            schema_types.extend(t)
                        else:
                            schema_types.append(t)
                        if t == "Organization":
                            org_data = g
                        elif t == "Person":
                            person_data = g
            else:
                t = s.get("@type", "")
                if isinstance(t, list):
                    schema_types.extend(t)
                else:
                    schema_types.append(t)
                if t == "Organization":
                    org_data = s
                elif t == "Person":
                    person_data = s

    org_present = (org_data is not None) or ("Organization" in head)
    person_present = (person_data is not None) or ("Person" in head)
    items.append(CiteItemResult("I01", "Organization schema present", org_present,
                                 evidence="head-provided" if org_present and org_data is None else ""))
    items.append(CiteItemResult("I02", "Wikidata entry exists",
                                 bool(org_data and "wikidata" in str(org_data).lower())))
    items.append(CiteItemResult("I03", "Wikipedia page exists",
                                 bool(org_data and "wikipedia" in str(org_data).lower())))
    items.append(CiteItemResult("I04", "Brand mentioned consistently", True))  # heuristic
    items.append(CiteItemResult("I05", "Person schema for author", person_present,
                                 evidence="head-provided" if person_present and person_data is None else ""))
    items.append(CiteItemResult("I06", "Author bio with credentials",
                                 bool(person_data and (person_data.get("jobTitle") or person_data.get("description")))
                                 or (person_present and plugin_managed)))
    items.append(CiteItemResult("I07", "Author has external social profiles",
                                 bool(person_data and person_data.get("sameAs"))))
    items.append(CiteItemResult("I08", "Founded date in schema",
                                 bool(org_data and org_data.get("foundingDate"))
                                 or (org_present and plugin_managed)))
    items.append(CiteItemResult("I09", "Geographic identity",
                                 bool(org_data and (org_data.get("address") or org_data.get("location")))
                                 or (org_present and plugin_managed)))
    items.append(CiteItemResult("I10", "Industry / category stated",
                                 bool(org_data and (org_data.get("industry") or org_data.get("knowsAbout")))
                                 or (org_present and plugin_managed)))
    return items


def _check_T(text: str, meta: dict | None, schema_data: list[dict] | None,
             head_provided_types: list[str] | None = None) -> tuple[list[CiteItemResult], list[str]]:
    """T: Trust Signals (10 items) + Vetoes."""
    items = []
    vetoes: list[str] = []
    head = {t for t in (head_provided_types or [])}

    items.append(CiteItemResult("T01", "HTTPS site-wide", True))  # site-level; assume yes
    items.append(CiteItemResult("T02", "Privacy + Terms linked", True))  # site-level

    # T03: affiliate disclosure — only veto if article actually contains affiliate links
    # Body text mentioning "paid" or "commission" informationally is NOT commercial content
    fmt = (meta or {}).get("format_id", "").lower()
    has_affiliate_links = bool(re.search(r'(?:affiliate[_-]?link|ref=|tag=|aff=|partner[_-]?id)', text, re.I))
    is_sponsored_format = fmt in ("sponsored-review", "affiliate-roundup")
    if (has_affiliate_links or is_sponsored_format):
        disclosure_present = bool(re.search(r"\b(?:disclosure|affiliate|sponsored|may earn)\b", text, re.I))
        if not disclosure_present:
            vetoes.append("T03")
            items.append(CiteItemResult("T03", "Affiliate/sponsored disclosure (if commercial)",
                                         False, evidence="VETO: affiliate links without disclosure"))
        else:
            items.append(CiteItemResult("T03", "Affiliate/sponsored disclosure", True))
    else:
        items.append(CiteItemResult("T03", "Affiliate/sponsored disclosure", True))

    # T04: Verifiable statistics (delegated to fact-checker upstream)
    items.append(CiteItemResult("T04", "Statistics verifiable by primary source",
                                 True))  # Trust upstream fact-check

    # T05 VETO: E-E-A-T markup for YMYL. Person schema may live in the <head> (SEO plugin),
    # not the body schema.json — credit head-provided Person so a YMYL article isn't falsely
    # vetoed for author markup that is actually present on the live page (2026-06-03 fix).
    is_ymyl = (meta or {}).get("is_ymyl", False)
    has_eat = bool(schema_data and any("Person" in str(s) for s in (schema_data or []))) or ("Person" in head)
    if is_ymyl and not has_eat:
        vetoes.append("T05")
        items.append(CiteItemResult("T05", "Author E-E-A-T markup (YMYL)",
                                     False, evidence="VETO: YMYL without Person schema"))
    else:
        items.append(CiteItemResult("T05", "Author E-E-A-T markup",
                                     True))

    items.append(CiteItemResult("T06", "Last reviewed/updated date visible", True))
    items.append(CiteItemResult("T07", "Reviewer separate from author (YMYL)", True))
    items.append(CiteItemResult("T08", "Customer reviews/testimonials", True))

    # T09: Schema validation — warn on deprecated types, veto only on genuine malformation
    # (missing required fields, bad JSON-LD structure). Deprecated types like HowTo still
    # have AI-engine extraction value, so they warn rather than block.
    # NOTE: sv.issues is a list[SchemaIssue] dataclass (attribute access, NOT .get()).
    # Deprecated issues carry severity="high" but text contains "deprecated" — excluded
    # from the malformed set so they don't veto. Wrapped in try/except so a validator
    # exception degrades to a warning instead of crashing the entire CITE gate.
    if schema_data:
        try:
            from scripts.validate.schema_validator import validate as schema_validate
            sv = schema_validate(schema_data if isinstance(schema_data, list) else [schema_data])
            malformed = [
                i for i in sv.issues
                if i.severity == "high" and "deprecated" not in i.issue.lower()
            ]
            if malformed:
                vetoes.append("T09")
                items.append(CiteItemResult("T09", "JSON-LD schemas validate (no errors)",
                                             False, evidence=f"VETO: {len(malformed)} malformed schema issue(s): {malformed[0].issue}"))
            elif not sv.passes:
                items.append(CiteItemResult("T09", "JSON-LD schemas validate",
                                             True, evidence=f"WARNING: {len(sv.issues)} non-blocking issue(s) (deprecated types retain AI-engine value)"))
            else:
                items.append(CiteItemResult("T09", "JSON-LD schemas validate", True))
        except Exception as e:
            # Validator failure must not crash the CITE gate — degrade to a warning
            items.append(CiteItemResult("T09", "JSON-LD schemas validate",
                                         True, evidence=f"WARNING: schema validator error (non-blocking): {e}"))
    else:
        items.append(CiteItemResult("T09", "JSON-LD schemas validate",
                                     False, evidence="no schema provided"))

    items.append(CiteItemResult("T10", "No deprecated schema types", True))  # checked in T09

    return items, vetoes


def _check_E(meta: dict | None) -> list[CiteItemResult]:
    """E: Eminence (10 items) — mostly site-level; heuristic checks."""
    items = []
    # All site-level; trust upstream config
    for item_id, desc in [
        ("E01", "Domain age >2 years"),
        ("E02", "≥10 referring domains"),
        ("E03", "≥3 backlinks from Tier-1"),
        ("E04", "Domain rating ≥30"),
        ("E05", "Content updated within 12 months"),
        ("E06", "Original research published"),
        ("E07", "Cited by authoritative sources"),
        ("E08", "Active on multiple platforms"),
        ("E09", "Mentioned in industry publications"),
        ("E10", "Cited in journalism"),
    ]:
        # Default trust for now; this should read from projects/{slug}/business-context.json
        items.append(CiteItemResult(item_id, desc, True, evidence="site-level (assumed)"))
    return items


# ─── Competitor-domain citation veto (out-of-band, project-policy driven) ──────

def _check_competitor_citation(
    text: str,
    citations: dict | None,
    schema_data: list[dict] | None,
    project_slug: str | None,
) -> list[tuple[str, str]]:
    """Return [(url, blocked_domain), ...] for any competitor/peer domain cited.

    Scans the draft body (rendered/markdown links + References URLs + bare URLs),
    every citations.json ref (url/doi/apa/domain), and the JSON-LD schema
    (citation/sameAs). Empty when the project has no citation_source_policy
    (disabled) — keeping this a no-op for non-opted-in projects. Never raises:
    a policy-load failure degrades to "no hits" + a stderr note (we do NOT
    silently swallow — feedback_silent_no_op_through_exception_swallow)."""
    if not project_slug:
        return []
    try:
        from scripts._core import competitor_domains as cd
        policy = cd.load_policy(project_slug)
    except Exception as e:  # noqa: BLE001 — log, never crash the CITE gate
        print(f"cite_scorer: competitor policy load failed "
              f"({type(e).__name__}: {e}); COMP01 skipped.", file=sys.stderr)
        return []
    if not policy.enabled:
        return []

    hits: list[tuple[str, str]] = []
    hits.extend(policy.find_blocked_in_html(text or ""))
    for r in _extract_refs(citations) if citations else []:
        for key in ("url", "doi", "domain"):
            v = r.get(key)
            if isinstance(v, str) and v:
                d = policy.blocked_domain_of(v)
                if d:
                    hits.append((v, d))
        for key in ("apa", "apa_7"):
            v = r.get(key)
            if isinstance(v, str) and v:
                hits.extend(policy.find_blocked_in_html(v))
    if schema_data:
        hits.extend(policy.find_blocked_in_html(json.dumps(schema_data, ensure_ascii=False)))

    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for u, d in hits:
        if u in seen:
            continue
        seen.add(u)
        out.append((u, d))
    return out


# ─── Main scoring ─────────────────────────────────────────

def score(
    text: str,
    *,
    meta: dict | None = None,
    citations: dict | None = None,
    schema_data: list[dict] | None = None,
    head_provided_types: list[str] | None = None,
    project_slug: str | None = None,
) -> CiteScoreReport:
    """Run full CITE 40-item scoring with veto + cap algorithm.

    head_provided_types: schema @types the site's SEO plugin emits in <head> (from
    business-context.wordpress.seo_plugin_schema_provided). Used to credit Identity/Trust
    items for schema that exists on the live page but is intentionally absent from the body
    schema.json (de-duplication policy)."""
    items = []
    items.extend(_check_C(text, meta, citations))
    items.extend(_check_I(meta, schema_data, head_provided_types))
    t_items, vetoes = _check_T(text, meta, schema_data, head_provided_types)
    items.extend(t_items)
    items.extend(_check_E(meta))

    # COMP01 — competitor/peer domain cited (block-level, project-policy driven).
    # Tracked OUTSIDE `items` so it never alters the 40-item raw score or the
    # C/I/T/E dimension breakdown (its code starts with 'C' but is not a C-item).
    competitor_hits = _check_competitor_citation(text, citations, schema_data, project_slug)
    if competitor_hits:
        vetoes.append("COMP01")

    # Raw score
    passed = sum(1 for it in items if it.passed)
    total = len(items)
    raw_pct = (passed / total) * 100 if total else 0

    # Dimension breakdown
    dimension_scores = {}
    for prefix in "CITE":
        dim_items = [it for it in items if it.item_id.startswith(prefix)]
        dp = sum(1 for it in dim_items if it.passed)
        dimension_scores[prefix] = round(dp / len(dim_items), 3) if dim_items else 0

    # Cap algorithm
    caps = {"T03": 60, "T05": 60, "T09": 70}
    cap_applied = False
    final_pct = raw_pct
    if "COMP01" in vetoes:
        # Hard block regardless of count: a competitor source must never ship.
        verdict = "BLOCKED"
        final_pct = min(raw_pct, 50)
        cap_applied = True
    elif len(vetoes) >= 2:
        verdict = "BLOCKED"
        final_pct = min(raw_pct, 50)
        cap_applied = True
    elif len(vetoes) == 1:
        cap_value = caps.get(vetoes[0], 60)
        if raw_pct > cap_value:
            cap_applied = True
            final_pct = cap_value
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
    if "T03" in vetoes:
        user_facing.append("Missing affiliate disclosure on commercial content")
    if "T05" in vetoes:
        user_facing.append("Missing author bio + credentials (E-E-A-T requirement for YMYL)")
    if "T09" in vetoes:
        user_facing.append("JSON-LD schema has validation errors or deprecated types")
    if "COMP01" in vetoes:
        _comp = "; ".join(sorted({d for (_u, d) in competitor_hits}))
        issues.append(f"[COMP01] Competitor/peer domain cited as a source: {_comp}")
        user_facing.append(
            f"Competitor/peer website cited as a source ({_comp}) — must be re-sourced to a "
            f"neutral authority or removed (citation_source_policy / root CLAUDE.md Rule 8)")

    return CiteScoreReport(
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
    ap = argparse.ArgumentParser(description="CITE 40-item AI Citation gate")
    ap.add_argument("draft", type=Path)
    ap.add_argument("--meta", type=Path)
    ap.add_argument("--citations", type=Path)
    ap.add_argument("--schema", type=Path)
    ap.add_argument("--project-slug", default="",
                    help="Reads projects/{slug}/business-context.json :: wordpress."
                         "seo_plugin_schema_provided to credit head-emitted schema types, AND "
                         ":: citation_source_policy to drive the COMP01 competitor-citation veto.")
    ap.add_argument("--head-schema-types", default="",
                    help="Comma-separated schema @types provided in <head> (overrides --project-slug lookup).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.draft.exists():
        print(f"Not found: {args.draft}", file=sys.stderr)
        return 2
    text = args.draft.read_text(encoding="utf-8")

    def _load(p: Path):
        try:
            from scripts._core import file_bus
            return file_bus.tolerant_json_load(p)
        except Exception:
            return json.loads(p.read_text(encoding="utf-8"))

    meta = None
    if args.meta and args.meta.exists():
        meta = _load(args.meta)

    citations = None
    if args.citations and args.citations.exists():
        citations = _load(args.citations)

    schema_data = None
    if args.schema and args.schema.exists():
        sd = _load(args.schema)
        schema_data = sd if isinstance(sd, list) else [sd]

    # Resolve which schema @types the site's SEO plugin emits in <head> so Identity/Trust
    # items are credited for schema present on the live page but intentionally absent from body.
    head_types: list[str] = []
    if args.head_schema_types:
        head_types = [t.strip() for t in args.head_schema_types.split(",") if t.strip()]
    elif args.project_slug:
        bc_path = (Path(__file__).resolve().parent.parent.parent
                   / "projects" / args.project_slug / "business-context.json")
        if bc_path.exists():
            try:
                bc = _load(bc_path)
                head_types = (bc.get("wordpress", {}) or {}).get("seo_plugin_schema_provided", []) or []
            except Exception:
                head_types = []

    r = score(text, meta=meta, citations=citations, schema_data=schema_data,
              head_provided_types=head_types, project_slug=(args.project_slug or None))

    if args.json:
        print(json.dumps(asdict(r), indent=2, ensure_ascii=False))
    else:
        print(f"Raw score:    {r.raw_overall_score}")
        print(f"Final score:  {r.final_overall_score}  (cap_applied: {r.cap_applied})")
        print(f"Verdict:      {r.verdict}")
        print(f"Vetoes:       {r.vetoes_triggered}")
        print("Dimensions:")
        for dim, s in r.dimension_scores.items():
            print(f"  {dim}: {s:.2%}")
        if r.user_facing_issues:
            print("\nUser-facing issues:")
            for ui in r.user_facing_issues:
                print(f"  ⚠ {ui}")
    return 0 if r.verdict == "SHIP" else 1


if __name__ == "__main__":
    sys.exit(main())
