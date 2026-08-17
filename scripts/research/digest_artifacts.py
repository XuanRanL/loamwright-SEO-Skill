"""scripts/research/digest_artifacts.py — Convert a news-digest.json into the 5 upstream
pipeline artifacts (state / research / angle / outline / image-prompts).

The weekly-digest skill calls ``write_artifacts()`` immediately after the digest runner
finishes so the orchestrator can auto-complete the research & plan stages and jump
straight to build.

CLI
---
    python -m scripts.research.digest_artifacts \\
        --task-id loamwright_wk_20260630 \\
        --project loamwright \\
        [--now 2026-06-30T00:00:00+00:00] \\
        [--json]

Reads:
    memory/workspace/{task_id}/news-digest.json
    projects/{project}/business-context.json

Writes (to memory/workspace/{task_id}/):
    state.json, research.json, angle.json, outline.json, image-prompts.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts._core.provenance import PREWRITER_WEEKLY_DIGEST

# Plugin root is 2 levels up from scripts/research/
PLUGIN_ROOT: Path = Path(__file__).resolve().parents[2]

# NOTE (2026-07-08): must stay em-dash-free — render_lint L12 hard-vetoes
# U+2014 anywhere in the draft body, and this suffix flows into the H1/seeds.
_PADDING_SUFFIX: str = " | Weekly Industry Brief"

# Words that must never END a title: a truncation that lands on one of these
# is a mid-clause cut ("… (Pew), while" ← the 2026-07-08 live H1 defect).
_TRAILING_DANGLERS: frozenset[str] = frozenset({
    "while", "and", "or", "but", "as", "with", "per", "via", "to", "of",
    "in", "on", "for", "at", "by", "from", "the", "a", "an", "is", "are",
    "vs", "versus", "plus", "amid", "after", "before", "into", "over",
    "than", "then", "when", "because", "since", "so", "that", "which", "how",
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clean_theme(theme: str) -> str:
    """Sanitize a harvest/operator-derived theme before it reaches any artifact.

    ROOT CURE (2026-07-08 weekly digest): theme_of_week flows VERBATIM into the
    H1 title, abstract_seed and tldr_seed. An em-dash-bearing theme ("… (Pew)
    — while Cloudflare …") shipped a U+2014 into all three (render_lint L12
    hard-vetoes it in the body) and then _fit_title truncated the H1 mid-clause
    to "… (Pew) — while". Em/en dashes become commas; whitespace collapses."""
    t = re.sub(r"\s*[—–]\s*", ", ", theme)
    return " ".join(t.split()).strip(" ,")


def _strip_dangling_tail(text: str) -> str:
    """Drop trailing connectives/punctuation left by a mid-clause truncation
    ("… 42% (Pew), while" → "… 42% (Pew)"). A slightly-short clean title beats
    an in-window broken one, so this runs AFTER the length fit and may drop
    the result below ``lo``."""
    words = text.split()
    while words:
        stripped = words[-1].strip(",;:()[]|&—–-").lower()
        if not stripped or stripped in _TRAILING_DANGLERS:
            words.pop()
            continue
        break
    return " ".join(words).rstrip(" ,;:|&—–-(")


def _fit_title(text: str, *, lo: int = 50, hi: int = 65) -> str:
    """Clamp *text* to the [lo, hi] character window, never ending mid-clause.

    Algorithm:
    1. If ``len(text) > hi``: truncate at the last space ≤ hi; fall back to
       hard-slice at hi when no space exists or the last space would drop
       below lo.
    2. If ``len(text) < lo``: append ``_PADDING_SUFFIX`` in a loop until
       the length reaches lo; then re-apply truncation from step 1.
    3. Strip any dangling connective/punctuation tail the truncation left
       (may legitimately land below ``lo`` — clean beats broken).
    """
    # Step 1 — truncate
    if len(text) > hi:
        candidate = text[:hi]
        sp = candidate.rfind(" ")
        text = text[:sp] if sp >= lo else text[:hi]

    # Step 2 — pad then re-truncate
    if len(text) < lo:
        extended = text
        while len(extended) < lo:
            extended += _PADDING_SUFFIX
        if len(extended) > hi:
            candidate = extended[:hi]
            sp = candidate.rfind(" ")
            extended = extended[:sp] if sp >= lo else extended[:hi]
        text = extended

    # Step 3 — never ship a dangling tail
    return _strip_dangling_tail(text)


# --- Abstract composition (2026-08-12 root cure) ----------------------------
#
# `abstract_seed` used to be `theme_of_week` — the week's HEADLINE — and
# assemble.py emits abstract_seed VERBATIM as the whole `## Abstract` body. Every
# NON-digest format gets a 545-1111 char paragraph there from the outline-architect
# LLM stage, which the pre-writer silently deletes for digests. So the Abstract is
# COMPOSED here, from prose the digest already holds (`items[].summary` is
# extract-verified), never generated: a script must not invent claims about the
# week's news.
#
# It stays in `abstract_seed` (NOT a writer section) on purpose: writer sections
# are emitted AFTER the ToC, which would push the Abstract below the fold and
# shift every `outline.sections[].index` that section_completeness_check diffs.

_ABSTRACT_WORDS_LO: int = 60
_ABSTRACT_WORDS_HI: int = 90

_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=["“‘(]?[A-Z0-9])')

# A period inside these never ends a sentence.
_ABBREVIATIONS: frozenset[str] = frozenset({
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "st.", "no.", "vs.",
    "inc.", "corp.", "ltd.", "co.", "e.g.", "i.e.", "u.s.", "u.k.", "eu.",
    "fig.", "est.", "approx.", "vol.",
})

_COUNT_WORDS: tuple[str, ...] = (
    "zero", "one", "two", "three", "four", "five", "six",
    "seven", "eight", "nine", "ten", "eleven", "twelve",
)


def _split_sentences(text: str) -> list[str]:
    """Split *text* into sentences, tolerating abbreviations and decimals.

    Decimals ("0.7% of 207,204") are safe by construction: the split needs
    whitespace after the period. Abbreviations are re-joined explicitly.
    """
    flat = " ".join((text or "").split())
    if not flat:
        return []
    out: list[str] = []
    for part in _SENTENCE_SPLIT_RE.split(flat):
        if out:
            words = out[-1].split()
            last = words[-1].lower() if words else ""
            # "Dr." / "U.S." / any single-letter initial ("J. Dean")
            if last in _ABBREVIATIONS or (len(last) == 2 and last[0].isalpha() and last[1] == "."):
                out[-1] = f"{out[-1]} {part}"
                continue
        out.append(part)
    return [s.strip() for s in out if s.strip()]


def _count_word(n: int) -> str:
    return _COUNT_WORDS[n] if 0 <= n < len(_COUNT_WORDS) else str(n)


def compose_abstract(
    items: list[dict[str, Any]],
    *,
    industry_short: str,
    lo: int = _ABSTRACT_WORDS_LO,
    hi: int = _ABSTRACT_WORDS_HI,
) -> str:
    """Compose a 60-90 word Abstract from the digest's own item summaries.

    One framing sentence (the only non-digest prose, and it states nothing that
    is not a fact about the issue itself) followed by the leading sentence of each
    story in ranked order, while the budget allows. If that lands short, each
    story's SECOND sentence is added next to its first, so the paragraph never
    jumps out of narrative order.

    Deliberately does NOT touch `theme_of_week` or `tldr_seed`: the TL;DR sits
    directly above the Abstract on the page and duplicating it wastes the slot.
    Never pads to reach *lo* — a short digest yields a short Abstract rather than
    a fabricated one.
    """
    per_item: list[list[str]] = [_split_sentences(str(it.get("summary") or "")) for it in items]
    if not any(per_item):
        return ""

    framing = (
        f"This week's {industry_short} roundup covers "
        f"{_count_word(len(items))} developments."
    )
    total = len(framing.split())

    chosen: list[list[str]] = [[] for _ in per_item]
    for i, sents in enumerate(per_item):
        if not sents:
            continue
        words = len(sents[0].split())
        # The lead story always makes it in, even if it alone overshoots `hi`:
        # verbatim factual prose beats a clause-mangling truncation.
        if chosen and any(chosen) and total + words > hi:
            break
        chosen[i].append(sents[0])
        total += words

    if total < lo:
        for i, sents in enumerate(per_item):
            if len(sents) < 2 or not chosen[i]:
                continue
            words = len(sents[1].split())
            if total + words > hi:
                continue
            chosen[i].append(sents[1])
            total += words
            if total >= lo:
                break

    body = " ".join(" ".join(c) for c in chosen if c)
    # Em/en dashes are hard-vetoed in the body by render_lint L12.
    return _clean_theme(f"{framing} {body}")


def _industry_short(bc: dict[str, Any]) -> str:
    """Return a short industry label.

    "SEO / Digital Marketing Agency" → "SEO"
    "3D Printing Filament" → "3D Printing Filament"  (no slash → as-is, full string)
    """
    industry: str = bc.get("industry", "Industry")
    if "/" in industry:
        return industry.split("/")[0].strip()
    return industry.strip()


def _slugify(text: str) -> str:
    """Lowercase, collapse non-alphanum runs to '-', strip edge dashes."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _date_from_iso(iso: str) -> str:
    """Extract the date portion (YYYY-MM-DD) from an ISO-8601 string."""
    return iso[:10] if iso else ""


def _series_kw(bc: dict[str, Any]) -> str:
    """Resolve the series keyword from business-context, with fallback."""
    wd_cfg: dict[str, Any] = bc.get("weekly_digest", {})
    kw: str = wd_cfg.get("series_keyword") or ""
    if kw:
        return kw
    industry: str = bc.get("industry", "Industry")
    return f"{industry} news this week"


# ---------------------------------------------------------------------------
# Builder functions (pure — no I/O)
# ---------------------------------------------------------------------------


def build_state(
    digest: dict[str, Any],
    bc: dict[str, Any],
    *,
    task_id: str,
    now_iso: str,
) -> dict[str, Any]:
    """Build the ``state.json`` artifact.

    Sets ``phase="plan"`` / ``current_stage="format-selector"`` so the
    orchestrator knows research is already pre-filled and picks up from
    the format-selector step.
    """
    kw = _series_kw(bc)
    locale_list: list[str] = bc.get("location", {}).get("languages", [])
    _raw_locale: str = locale_list[0] if locale_list else "en-US"
    # Sanitize to BCP-47 (e.g. "en" or "en-US"); fall back to "en-US" if the
    # value is a human-readable string like "English" or missing/empty.
    locale: str = (
        _raw_locale
        if re.match(r"^[a-z]{2}(-[A-Z]{2})?$", _raw_locale)
        else "en-US"
    )

    return {
        "task_id": task_id,
        "project_slug": bc.get("slug") or digest.get("project_slug"),
        "command": "weekly-digest",
        "phase": "plan",
        "current_stage": "format-selector",
        "created_at": now_iso,
        "updated_at": now_iso,
        "brief": {
            "keywords": [kw],
            "primary_keyword": kw,
            "word_count_target": 2200,
            "industry": bc.get("industry", ""),
            "target_market_locale": locale,
            "target_surfaces": [
                "google-aio",
                "ai-assistant-chatgpt",
                "owned",
            ],
            "image_count": 1,
            "image_quality": "high",
            "image_mode": "realtime",
        },
    }


def build_research(
    digest: dict[str, Any],
    bc: dict[str, Any],
) -> dict[str, Any]:
    """Build the ``research.json`` artifact.

    SERP / competitor analysis stages are ``--action skip``'d by the weekly
    skill, so ``competitor_titles`` and ``serp_features`` are empty lists.
    The digest items themselves carry all the facts the writer needs.

    NOTE — ``competitor_titles: []`` is intentional and correct for digests.
    Digests have no competitors; the digest's ``research.json`` is consumed
    by the orchestrator (which only needs the keys present and non-empty JSON)
    and is written via plain Python, bypassing the PostToolUse schema-validate
    hook.  It is therefore NOT gated against ``research.schema.json``'s
    ``minItems:3`` rule — and must NOT be "fixed" by fabricating competitor
    titles or weakening the shared schema.
    """
    kw = _series_kw(bc)
    return {
        "primary_keyword": kw,
        "intent": "informational",
        "competitor_titles": [],
        "serp_features": [],
        "digest_items": digest.get("items", []),
        "theme_of_week": _clean_theme(digest.get("theme_of_week", "")),
        "generated_by": "weekly-digest-prewriter",
    }


_TASK_ID_DATE_RE = re.compile(r"_wk_(\d{8})$")

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _issue_date_from_task_id(task_id: str | None) -> str:
    """``{slug}_wk_YYYYMMDD`` → ``YYYY-MM-DD`` — the AUTHORITATIVE issue date.

    2026-08-02 root cure: the slug/title date used to come from
    ``digest.generated_at`` (harvest wall-clock). The 07-22 issue harvested at
    01:57 UTC the next day and shipped slug ``seo-weekly-2026-07-23`` — the
    off-by-one was hand-patched in the artifact, never in code. The task id
    encodes the issue date and cannot drift with the clock.
    """
    m = _TASK_ID_DATE_RE.search(task_id or "")
    if not m:
        return ""
    d = m.group(1)
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def _pretty_issue_date(date_iso: str) -> str:
    """``2026-08-02`` → ``August 2 2026`` (series title convention)."""
    try:
        y, mo, dd = (int(x) for x in date_iso.split("-"))
        return f"{_MONTHS[mo - 1]} {dd} {y}"
    except (ValueError, IndexError):
        return ""


def build_angle(
    digest: dict[str, Any],
    bc: dict[str, Any],
    task_id: str | None = None,
) -> dict[str, Any]:
    """Build the ``angle.json`` artifact.

    Series conventions (encoded here since 2026-08-02 — previously they lived
    only as data in ``projects/{slug}/weekly/issues.json`` and every run needed
    hand-correction): title ``{IND} Weekly, {Month D YYYY}: {hook}``, slug
    ``{ind}-weekly-YYYY-MM-DD`` from the task id's issue date. Both ``slug``
    (orchestrator contract) and ``slug_draft`` (assemble reader) are emitted.
    """
    ind_short = _industry_short(bc)
    theme: str = _clean_theme(digest.get("theme_of_week", "Weekly News"))
    generated_at: str = digest.get("generated_at", "")
    date_str = _issue_date_from_task_id(task_id) or _date_from_iso(generated_at)
    pretty = _pretty_issue_date(date_str)

    raw_title = (
        f"{ind_short} Weekly, {pretty}: {theme}" if pretty
        else f"{ind_short} Weekly: {theme}"
    )
    title = _fit_title(raw_title)

    slug_raw = f"{_slugify(ind_short)}-weekly-{date_str}"
    slug = slug_raw[:40].rstrip("-")  # schema maxLength 40

    angle: dict[str, Any] = {
        "title": title,
        "format_id": "weekly-digest",
        "angle": "trends",
        "modifiers": [
            "tldr-first",
            "citation-capsules-per-h2",
            "info-gain-prose",
        ],
        "template_path": "templates/weekly-digest.md",
        "slug": slug,
        "slug_draft": slug,
        "seo_title": title,
        "h1": raw_title if 50 <= len(raw_title) <= 65 else title,
    }
    if generated_at:
        angle["generated_at"] = generated_at
    return angle


def build_outline(
    digest: dict[str, Any],
    bc: dict[str, Any],
) -> dict[str, Any]:
    """Build the ``outline.json`` artifact.

    Section order:
    1. TL;DR          (word_budget 150 — schema minimum)
    2–N. One section per digest item; first item = "Big Story" at 400 words,
         rest at 180.  Each carries ``digest_cluster_id`` so the writer
         knows which digest item + source to cite.
    N+1. FAQ
    N+2. References
    """
    items: list[dict[str, Any]] = digest.get("items", [])
    if not items:
        raise ValueError("weekly-digest has 0 items; refusing to build an empty digest")
    theme: str = _clean_theme(digest.get("theme_of_week", "Weekly industry news roundup"))
    ind_short = _industry_short(bc)

    # -- takeaways_seeds (schema: minItems 4, maxItems 7) --
    takeaways: list[str] = [it["headline"] for it in items[:7]]
    pad_phrases = [
        f"Stay current with this week's top {ind_short} developments",
        f"Key trend: {theme[:60]}",
        "Check the References section for all primary sources",
        "Industry shifts demand weekly monitoring",
    ]
    for phrase in pad_phrases:
        if len(takeaways) >= 4:
            break
        takeaways.append(phrase)
    takeaways = takeaways[:7]

    # -- sections --
    sections: list[dict[str, Any]] = []
    idx = 0

    # Cap items to prevent outline from exceeding schema maxItems:15
    # (TL;DR + items + FAQ + References must stay ≤ 15)
    max_items = bc.get("weekly_digest", {}).get("items_per_issue", 7)
    items = items[: min(max_items, 12)]

    # TL;DR
    sections.append(
        {
            "index": idx,
            "h2": "TL;DR",
            "word_budget": 150,
            "section_intent": (
                "Pre-abstract briefing — this week's top stories in under 150 words "
                "for time-pressed readers"
            ),
            "citation_capsule_required": False,
        }
    )
    idx += 1

    # One section per digest item
    for i, item in enumerate(items):
        h2: str = item["headline"]
        cid: str = item["cluster_id"]
        is_big = i == 0
        sections.append(
            {
                "index": idx,
                "h2": h2,
                "anchor_id": _slugify(h2)[:60],
                "word_budget": 400 if is_big else 180,
                "section_intent": (
                    "Big story deep-dive — significance, context, and practitioner impact"
                    if is_big
                    else "Supporting story — concise factual report with citation capsule"
                ),
                "digest_cluster_id": cid,
                "citation_capsule_required": True,
                # Positional marker, NOT cluster_id-derived (2026-08-02 root
                # cure): a hand-curated id like "hc1" produced [claim:hc1_src],
                # which citations.schema.json rejects and citation_inject only
                # rescued by silently truncating to "c1_src" — and a follow-up
                # id "fu_c3" truncates to the PARENT story's "c3_src" (real
                # collision). c{position} is schema-legal by construction.
                "claim_markers": [f"c{i + 1}_src"],
            }
        )
        idx += 1

    # FAQ
    sections.append(
        {
            "index": idx,
            "h2": "FAQ",
            "word_budget": 300,
            "section_intent": (
                "Answer common reader questions surfaced by this week's themes"
            ),
            "citation_capsule_required": False,
        }
    )
    idx += 1

    # References
    sections.append(
        {
            "index": idx,
            "h2": "References",
            "word_budget": 200,
            "section_intent": (
                "APA-7 formatted citations for all primary sources cited in this digest"
            ),
            "citation_capsule_required": False,
        }
    )

    # -- FAQ seed questions (5 minimum per schema) --
    first_headline = items[0]["headline"] if items else theme
    seed_questions: list[str] = [
        f"What happened with {first_headline[:60]}?",
        f"How does this week's {ind_short} news affect my strategy?",
        f"What does '{theme[:50]}' mean in practice?",
        "Which story had the biggest industry impact this week?",
        "What should I do differently based on this week's developments?",
    ]
    for it in items[1:]:
        seed_questions.append(f"What does the '{it['headline'][:60]}' story mean?")
    seed_questions = seed_questions[:15]

    total_budget = sum(s["word_budget"] for s in sections)

    # 2026-08-12 root cure: a real Abstract, composed from the digest's own
    # extract-verified summaries. `theme` is the last-resort fallback only when
    # every item shipped an empty summary (it is what used to ship ALWAYS).
    abstract = compose_abstract(items, industry_short=ind_short) or theme

    return {
        "abstract_seed": abstract,
        "tldr_seed": f"This week in {ind_short}: {theme}",
        "takeaways_seeds": takeaways,
        "sections": sections,
        "faq": {
            "count": 5,
            "seed_questions": seed_questions[:5],
        },
        "image_slots": [{"slot_id": "cover", "kind": "photo"}],
        "tables_required": [],
        "total_word_budget": total_budget,
        "expected_h2_count": len(sections),
        "generated_by": "weekly-digest-prewriter",
    }


# --- Cover negative prompt (2026-08-12 root cure) ---------------------------
#
# `build_image_prompts` never received `bc`, so it structurally COULD NOT read
# project config, and every issue ever produced shipped `negative_prompt: None`.
# Meanwhile projects/{slug}/brand-guideline.yaml already carried
# `negative_prompt_baseline` (forbidding third-party logos AND empty label chips)
# with no reader on this path — and a third-party logo rendered into the cover on
# 2026-08-02, 08-06 and 08-12, each costing a ~$1.67 regeneration round that the
# vision-QA agent closed by hand-writing negatives the config already contained.
#
# The consumer is live: openai_image_pipeline._adapt_entry appends
# "\n\nAVOID: {negative_prompt}" to the prompt it sends, and
# art_direction_compiler.compile_prompt appends it as "Additional negatives".

_BRAND_BAN_CLAUSE: str = (
    "no third-party brand logos, wordmarks, product chrome or on-screen brand "
    "names on walls, screens, mugs, clothing or signage, and none in reflections "
    "or shadows"
)

_LEGIBLE_UI_CLAUSE: str = (
    "no empty or placeholder label chips: every depicted UI label, axis tick, KPI "
    "tile and legend must carry a legible, plausible value"
)

# Guardrail against a pathological digest, not a curation rule.
_MAX_BANNED_ENTITIES: int = 40


def _brand_guideline_text_fallback(text: str) -> dict[str, Any]:
    """Minimal reader for the few keys we need when PyYAML is unimportable.

    Handles exactly the shape `scripts/build/*` generates: a top-level folded
    scalar `negative_prompt_baseline: >` plus two nested booleans. Anything it
    cannot find is simply absent — never guessed.
    """
    out: dict[str, Any] = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^negative_prompt_baseline:\s*([>|][-+]?)?\s*(.*)$", line)
        if not m:
            continue
        inline = m.group(2).strip()
        if inline and not m.group(1):
            out["negative_prompt_baseline"] = inline.strip("'\"")
        else:
            body: list[str] = []
            for nxt in lines[i + 1:]:
                if not nxt.strip():
                    if body:
                        break
                    continue
                if not nxt[:1].isspace():
                    break
                body.append(nxt.strip())
            if body:
                out["negative_prompt_baseline"] = " ".join(body)
        break

    for key, section in (
        ("forbid_third_party_brands", "packaging_branding"),
        ("forbid_empty_label_chips", "realism"),
    ):
        m2 = re.search(rf"^\s+{key}:\s*(true|false)\b", text, re.M | re.I)
        if m2:
            sect = out.setdefault(section, {})
            if isinstance(sect, dict):
                sect[key] = m2.group(1).lower() == "true"

    m3 = re.search(r'^\s+label_text:\s*["\']?([^"\'#\n]+)', text, re.M)
    if m3:
        sect = out.setdefault("packaging_branding", {})
        if isinstance(sect, dict):
            sect["label_text"] = m3.group(1).strip()
    return out


def load_brand_guideline(slug: str, *, plugin_root: Path | None = None) -> dict[str, Any]:
    """Read ``projects/{slug}/brand-guideline.yaml`` defensively.

    Missing file, unreadable file, malformed YAML and an unimportable PyYAML all
    degrade to a partial/empty dict — never an exception. The pre-writer runs
    before any agent and must not be able to abort the weekly issue over config.
    """
    if not slug:
        return {}
    root = Path(plugin_root) if plugin_root is not None else PLUGIN_ROOT
    path = root / "projects" / slug / "brand-guideline.yaml"
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        import yaml  # type: ignore[import-untyped]  # optional dependency

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:  # ImportError, ScannerError, … — fall through to text mode
        pass
    return _brand_guideline_text_fallback(text)


def _section(cfg: dict[str, Any], key: str) -> dict[str, Any]:
    val = cfg.get(key)
    return val if isinstance(val, dict) else {}


def issue_entities(digest: dict[str, Any], *, exclude: tuple[str, ...] = ()) -> list[str]:
    """Every named entity in THIS issue, deduped, first-mention order.

    Derived from ``items[].entities`` on purpose — a hardcoded platform list
    would go stale the first week a new engine ships.
    """
    skip = {e.strip().lower() for e in exclude if e}
    seen: set[str] = set()
    out: list[str] = []
    for item in digest.get("items", []) or []:
        for raw in item.get("entities", []) or []:
            name = " ".join(str(raw).split())
            key = name.lower()
            if not name or key in seen or key in skip:
                continue
            seen.add(key)
            out.append(name)
    return out[:_MAX_BANNED_ENTITIES]


def build_negative_prompt(
    digest: dict[str, Any],
    bg: dict[str, Any],
    *,
    bc: dict[str, Any] | None = None,
) -> str:
    """Compose the cover slot's negative prompt from project config + this issue.

    Three layers: the project's ``negative_prompt_baseline`` verbatim, a
    format-level ban on third-party marks, and the entities THIS issue names.
    ``packaging_branding.forbid_third_party_brands: false`` (a deliberate project
    contract — project-echo depicts real brands as the subject) suppresses the last two.
    """
    parts: list[str] = []

    baseline = " ".join(str(bg.get("negative_prompt_baseline") or "").split()).strip()
    if baseline:
        parts.append(baseline)

    packaging = _section(bg, "packaging_branding")
    realism = _section(bg, "realism")

    if packaging.get("forbid_third_party_brands") is not False:
        parts.append(_BRAND_BAN_CLAUSE)
        own = (
            str(packaging.get("label_text") or ""),
            str((bc or {}).get("brand_name") or ""),
            str(_section(bc or {}, "company").get("name") or ""),
        )
        named = issue_entities(digest, exclude=own)
        if named:
            parts.append(
                "specifically no logo, wordmark or rendered name reading: "
                + ", ".join(named)
            )

    if realism.get("forbid_empty_label_chips") is True:
        parts.append(_LEGIBLE_UI_CLAUSE)

    # Clause separator is "; " EXCEPT after a part that already ends a sentence —
    # the brand-guideline baseline is carried verbatim (trailing period included),
    # and "hands.; no third-party…" is not what anyone wrote.
    text = ""
    for part in parts:
        if not text:
            text = part
        elif text.endswith((".", "!", "?")):
            text = f"{text} {part}"
        else:
            text = f"{text}; {part}"
    return text


def build_image_prompts(
    digest: dict[str, Any],
    *,
    task_id: str,
    bc: dict[str, Any] | None = None,
    plugin_root: Path | None = None,
) -> dict[str, Any]:
    """Build the ``image-prompts.json`` artifact.

    Returns a single ``cover`` photo slot.  No chart slots are emitted — the
    chart-render step no-ops when there are no chart slots.

    *bc* is optional only for backward compatibility with existing callers; when
    it is absent the project slug still resolves from ``digest['project_slug']``,
    so the brand-guideline is read either way.
    """
    theme: str = _clean_theme(digest.get("theme_of_week", "Weekly industry news"))
    items: list[dict[str, Any]] = digest.get("items", [])
    headline: str = items[0]["headline"] if items else theme
    generated_at: str = digest.get("generated_at", "")

    slug: str = str((bc or {}).get("slug") or digest.get("project_slug") or "").strip()
    brand_guideline = load_brand_guideline(slug, plugin_root=plugin_root)
    negative_prompt = build_negative_prompt(digest, brand_guideline, bc=bc)

    return {
        "task_id": task_id,
        "designed_at": generated_at,
        "style_preset": "editorial-photo",
        "art_direction_prefix": (
            "Clean editorial photo, no text overlays, high detail, realistic lighting"
        ),
        "prompts": [
            {
                "slot_id": "cover",
                "kind": "photo",
                "aspect_ratio": "16:9",
                "quality": "high",
                "purpose": "Article cover image representing this week's top story",
                "subject": headline,
                "full_prompt": (
                    f"Editorial photo: {headline}. "
                    "Professional news-style composition, clean background, "
                    "high contrast, absolutely no text or overlays."
                ),
                # Consumed by openai_image_pipeline._adapt_entry ("AVOID: …") and
                # art_direction_compiler.compile_prompt ("Additional negatives").
                "negative_prompt": negative_prompt,
                "alt_text_seed": f"Cover photo for: {theme}",
                "filename_seed": f"{task_id}-cover",
            }
        ],
    }


# ---------------------------------------------------------------------------
# I/O wrapper
# ---------------------------------------------------------------------------


def write_artifacts(
    digest: dict[str, Any],
    bc: dict[str, Any],
    *,
    task_id: str,
    ws_dir: Path,
    now_iso: str,
    plugin_root: Path | None = None,
) -> list[str]:
    """Write all 5 pipeline artifacts to *ws_dir*.

    Creates *ws_dir* if it does not exist.  Writes are plain Python file I/O
    (not through the PostToolUse schema-validate hook).

    Every artifact is stamped ``_generated_by: "weekly-digest-prewriter"``:
    ``outline.json`` and ``image-prompts.json`` are OWNED by real LLM stages
    (outline-architect / image-prompt-designer) that this pre-write skips, and
    without the stamp that skip is invisible — on 2026-08-12 both stages recorded
    "completed" 3ms apart with nothing dispatched. See
    ``scripts/_core/provenance.py`` (``PROVENANCE_ADVISORY``, ``--check``).

    Returns:
        List of absolute path strings for each written file.
    """
    ws = Path(ws_dir)
    ws.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, Any] = {
        "state.json": build_state(digest, bc, task_id=task_id, now_iso=now_iso),
        "research.json": build_research(digest, bc),
        "angle.json": build_angle(digest, bc, task_id=task_id),
        "outline.json": build_outline(digest, bc),
        "image-prompts.json": build_image_prompts(
            digest, task_id=task_id, bc=bc, plugin_root=plugin_root
        ),
    }

    paths: list[str] = []
    for name, data in artifacts.items():
        if isinstance(data, dict):
            data["_generated_by"] = PREWRITER_WEEKLY_DIGEST
        p = ws / name
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        paths.append(str(p))
    return paths


# ---------------------------------------------------------------------------
# CLI entry point (addendum requirement for Task 7 / /weekly skill)
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI: load news-digest.json + business-context.json and write 5 artifacts."""
    parser = argparse.ArgumentParser(
        description=(
            "Convert memory/workspace/{task-id}/news-digest.json into the 5 "
            "upstream pipeline artifacts."
        )
    )
    parser.add_argument("--task-id", required=True, help="Task ID (matches workspace dir)")
    parser.add_argument("--project", required=True, help="Project slug")
    parser.add_argument(
        "--now",
        default=None,
        help="ISO-8601 timestamp to use as 'now' (default: UTC now)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print result as a JSON object",
    )
    args = parser.parse_args()

    now_iso: str = args.now or datetime.now(timezone.utc).isoformat()
    ws_dir: Path = PLUGIN_ROOT / "memory" / "workspace" / args.task_id
    digest_path: Path = ws_dir / "news-digest.json"
    bc_path: Path = PLUGIN_ROOT / "projects" / args.project / "business-context.json"

    digest: dict[str, Any] = json.loads(digest_path.read_text(encoding="utf-8"))
    bc: dict[str, Any] = json.loads(bc_path.read_text(encoding="utf-8"))

    paths = write_artifacts(digest, bc, task_id=args.task_id, ws_dir=ws_dir, now_iso=now_iso)

    result: dict[str, Any] = {
        "status": "ok",
        "task_id": args.task_id,
        "written": paths,
    }
    if args.json_output:
        sys.stdout.write(json.dumps(result) + "\n")
    else:
        for p in paths:
            print(p)


if __name__ == "__main__":
    main()
