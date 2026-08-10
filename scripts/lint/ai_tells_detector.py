"""
scripts/lint/ai_tells_detector.py — Detect 43 AI-writing patterns.

Patterns source: references/style/ai-tells-43.md (loaded if exists),
fallback to inline DEFAULT_AI_PATTERNS (43 patterns from humanizer-skill).

Each pattern has 6 fields:
  - id (P1-P43)
  - name
  - definition (1-line)
  - trigger_regex (the actual detector)
  - example_ai (what AI writes)
  - example_human (the rewrite)

Categories (from BLOG-FORMATS-2026-CATALOG.md §3.13):
  - CONTENT (P1-P8): significance inflation, name-dropping, -ing phrases,
                     promotional, vague attributions, formulaic challenges,
                     AI vocab, copula avoidance
  - LANGUAGE/STYLE (P9-P18): negative parallelisms, rule-of-three,
                              synonym cycling, false ranges, em-dashes,
                              bold overuse, structured-list syndrome,
                              title-case headings, curly quotes, formal register
  - COMMUNICATION (P19-P21): chatbot artifacts, knowledge-cutoff disclaimers,
                              sycophantic tone
  - FILLER (P22-P30): filler phrases, hedging stacks, generic conclusions,
                      hallucination markers, perfect/error alternation,
                      question titles, markdown bleeding, comprehensive openings,
                      uniform sentence length
  - EMERGING 2026 (P31-P37): elegant variation, "we will explore" leak,
                              placeholder text, chatbot reference markup,
                              utm_source=chatgpt.com, register shift,
                              source-listing as content
  - COMMUNITY 2026 (P38-P43): reshuffling immunity, "Whether you prefer" closings,
                               symbolic gloss, infomercial hooks, erratic bolding,
                               Treadmill Effect

Used by:
  - quality-gate-ai-slop (computes patterns_hit count)
  - section-drafter self_check
  - humanizer skill (locates patterns to rewrite)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from scripts.lint._text_utils import find_all_with_line


@dataclass(frozen=True)
class AIPattern:
    id: str            # e.g. "P14"
    name: str
    category: str
    trigger: re.Pattern[str]
    fix_hint: str


# ─── 43 patterns (compiled at import time) ────────────────────────

def _make_pattern(s: str, flags: int = re.IGNORECASE) -> re.Pattern[str]:
    return re.compile(s, flags)


DEFAULT_AI_PATTERNS: Final[list[AIPattern]] = [
    # ── CONTENT ────────────────────────────────────────────────
    AIPattern("P1", "Significance inflation", "content",
              _make_pattern(r"\b(?:cannot be (?:over)?stated|of (?:utmost|paramount) importance|game[- ]?changer|paradigm[- ]?shift)\b"),
              "Replace with specific impact (numbers, before/after)"),
    AIPattern("P2", "Name-dropping w/o substance", "content",
              _make_pattern(r"\b(?:industry leaders?|top experts?|leading researchers?|renowned authorities)\b(?![^.]*\bsuch as\b)"),
              "Name the specific people/orgs, or remove the claim"),
    AIPattern("P3", "Shallow -ing phrases", "content",
              _make_pattern(r"\b(?:ensuring|allowing|enabling|providing|delivering|offering|creating) (?:a|an|the) \w+ (?:experience|solution|approach|strategy)\b"),
              "Cut the -ing phrase; state the concrete result"),
    AIPattern("P4", "Promotional/sales language", "content",
              _make_pattern(r"\b(?:industry[- ]?leading|state[- ]?of[- ]?the[- ]?art|best[- ]?in[- ]?class|world[- ]?class|premier|premium)\b"),
              "Replace with specific differentiator backed by data"),
    AIPattern("P5", "Vague attributions", "content",
              _make_pattern(r"\b(?:studies (?:have )?(?:shown|suggested)|experts (?:say|agree|believe)|research indicates|it is (?:widely )?(?:known|believed))\b"),
              "Cite specific study/expert with year and source"),
    AIPattern("P6", "Formulaic challenges", "content",
              _make_pattern(r"\b(?:in (?:today|this)['']s (?:fast[- ]?paced |digital |modern )?(?:world|landscape|environment|era))\b"),
              "Use specific year or just delete"),
    AIPattern("P7", "AI vocabulary cluster", "content",
              _make_pattern(r"\b(?:multifaceted|tapestry|landscape|intricate|comprehensive|delve|leverage|robust|seamless|foster|harness|paradigm|nestled)\b"),
              "Replace per references/style/banned-words.md"),
    AIPattern("P8", "Copula avoidance (be → exist/serve as)", "content",
              _make_pattern(r"\b(?:serves as|exists as|functions as|stands as) (?:a|an|the) \w+\b"),
              "Use plain 'is/are' instead"),
    # ── LANGUAGE / STYLE ──────────────────────────────────────
    AIPattern("P9", "Negative parallelism (not just X but also Y)", "language",
              _make_pattern(r"\bnot (?:just|only|merely|simply) [^,]*?,?\s*but (?:also )?\b"),
              "State the positive directly; drop the rhetorical 'not just'"),
    AIPattern("P10", "Rule-of-three lists (a, b, and c)", "language",
              _make_pattern(r"\b(\w+),\s+(\w+),\s+(?:and|&)\s+(\w+)\b(?=[.!?\s])"),
              "Break the rhythm with 2 or 4 items, or longer phrases"),
    AIPattern("P11", "Elegant variation (synonym cycling)", "language",
              # Hard to detect generically; this is a placeholder for the pattern category
              _make_pattern(r"\b(?:utilize|utilizes|utilization|employ|employed|employs)\b"),
              "Use 'use' consistently; vary structure, not vocabulary"),
    AIPattern("P12", "False range (X to Y where Y < X)", "language",
              _make_pattern(r"\bfrom (?:basic|simple|beginners?) to (?:complex|advanced|experts?)\b"),
              "Make the range specific or remove the spectrum framing"),
    AIPattern("P13", "Em-dash overuse (>3/article)", "language",
              _make_pattern(r"—"),
              "Replace with comma, parens, or full stop"),
    AIPattern("P14", "Bold/asterisk overuse", "language",
              _make_pattern(r"\*\*[^*\n]+\*\*"),
              "Use bold sparingly (≤2 per H2 section)"),
    AIPattern("P15", "Structured-list syndrome (every paragraph a list)", "language",
              _make_pattern(r"(?:^[*\-+]\s.+\n){5,}", re.MULTILINE),
              "Break list into prose paragraphs occasionally"),
    AIPattern("P16", "Title-Case Subheadings", "language",
              _make_pattern(r"^#{2,4}\s+(?:[A-Z][a-z]+\s+){3,}[A-Z]\w*$", re.MULTILINE),
              "Use sentence case (Capitalize first word + proper nouns only)"),
    AIPattern("P17", "Curly typographic quotes", "language",
              _make_pattern(r"[‘’“”]"),
              "Replace with straight ASCII quotes (ChatGPT tell)"),
    AIPattern("P18", "Formal register shift mid-paragraph", "language",
              _make_pattern(r"\b(?:utilize|commence|terminate|endeavor|facilitate)\b"),
              "Use 'use/start/end/try/help' for casual register"),
    # ── COMMUNICATION ─────────────────────────────────────────
    AIPattern("P19", "Chatbot artifacts (I'd be happy to / As an AI / Sure!)", "communication",
              _make_pattern(r"\b(?:as an ai|i['']m an ai|i['']d be (?:happy|glad)|sure[!,]\s|certainly[!,]\s|absolutely[!,]\s|of course[!,]\s)"),
              "Remove conversational AI artifacts entirely"),
    AIPattern("P20", "Knowledge-cutoff disclaimer", "communication",
              _make_pattern(r"\bas of (?:my (?:last|knowledge) (?:update|cutoff))\b"),
              "State a real date or remove the hedge"),
    AIPattern("P21", "Sycophantic tone", "communication",
              _make_pattern(r"\b(?:great (?:question|point)|excellent (?:question|observation)|that['']s (?:absolutely )?correct)\b"),
              "Get to the substance directly"),
    # ── FILLER ────────────────────────────────────────────────
    AIPattern("P22", "Filler phrases ('it's important to note')", "filler",
              _make_pattern(r"\bit['']s (?:important|worth) (?:to (?:note|mention)|noting|mentioning)\b"),
              "Delete; just state the fact"),
    AIPattern("P23", "Hedging stacks (might possibly potentially)", "filler",
              _make_pattern(r"\b(?:might|may|could|can|possibly|potentially|perhaps)\s+(?:might|may|possibly|potentially|perhaps)\b"),
              "One hedge max; or commit to a claim"),
    AIPattern("P24", "Generic positive conclusion", "filler",
              _make_pattern(r"\bby (?:embracing|adopting|implementing|utilizing) (?:these|this|the)\b[^.]*?\b(?:strategies|approaches|principles)\b"),
              "End with specific next action, not generic encouragement"),
    AIPattern("P25", "Hallucination markers (research has shown)", "filler",
              _make_pattern(r"\b(?:research (?:has )?(?:shown|demonstrated|indicated)|studies (?:have )?suggested)\b(?![^.]*\b(?:20\d{2}|et al)\b)"),
              "Add (Author, Year) citation or delete the claim"),
    AIPattern("P26", "Perfect/error alternation (no genuine errors)", "filler",
              _make_pattern(r"^\s*\d+\.\s+[A-Z][^\n]{20,200}\n\s*\d+\.\s+[A-Z][^\n]{20,200}\n\s*\d+\.\s+[A-Z][^\n]{20,200}",
                            re.MULTILINE),
              "Break the perfect-list rhythm with a fragment or aside"),
    AIPattern("P27", "Question-format titles", "filler",
              # NOTE: [^?\n] (not [^?]) keeps the match on a SINGLE heading line.
              # The old [^?] matched across newlines, so a "## How to ..." heading with
              # no "?" still matched a "?" many lines later (e.g. an FAQ question), a false
              # positive. A genuine question heading must end in "?" on its own line.
              # Count-thresholded in lint(): 1-2 question headings are fine for SEO/snippets;
              # only 3+ is the AI-style tell (see _COUNT_THRESHOLDS + the fix_hint below).
              _make_pattern(r"^#{1,3}\s+(?:What|How|Why|Can|Should|Is|Are|Do|Does)\b[^?\n]*\?\s*$", re.MULTILINE),
              "OK in moderation but >3 in one article is AI-style"),
    AIPattern("P28", "Markdown bleeding into prose", "filler",
              _make_pattern(r"(?:^|\s)\*{1,3}\w"),
              "Asterisk in middle of prose; either escape or remove"),
    AIPattern("P29", "Comprehensive overview opening", "filler",
              _make_pattern(r"\b(?:this (?:article|guide|post) (?:will|provides|offers|explores)|in this (?:article|guide|post))\b"),
              "Open with a hook, not a meta-description"),
    AIPattern("P30", "Uniform sentence length (≥3 sentences within ±3 words)", "filler",
              # This is a meta-detector; uses sentence_variance.py for the actual measure
              _make_pattern(r"$.^"),  # never matches via regex
              "See sentence_variance.py for the burstiness metric"),
    # ── EMERGING 2026 ─────────────────────────────────────────
    AIPattern("P31", "Phrase-level elegant variation", "emerging",
              _make_pattern(r"\b(?:in essence|in other words|put simply|essentially|fundamentally|basically)\b"),
              "Pick one and stick with it; usually 'or' suffices"),
    AIPattern("P32", "We will explore / examine / dive into", "emerging",
              _make_pattern(r"\b(?:we['']ll|we will) (?:explore|examine|dive into|cover|look at|discuss)\b"),
              "Just start exploring; don't announce it"),
    AIPattern("P33", "Placeholder text in published copy", "emerging",
              _make_pattern(r"\[(?:insert|TODO|placeholder|FIXME)[^\]]*\]"),
              "Remove placeholders before publish"),
    AIPattern("P34", "ChatGPT reference markup", "emerging",
              _make_pattern(r"(?:cite\s*turn\d+search\d+|oai_citation|citeturn\d)"),
              "NEAR-DEFINITIVE AI evidence — remove immediately"),
    AIPattern("P35", "utm_source=chatgpt.com", "emerging",
              _make_pattern(r"utm_source=(?:chatgpt|openai|claude|perplexity)"),
              "NEAR-DEFINITIVE AI evidence — review URL sourcing"),
    AIPattern("P36", "Register shift (formal → casual mid-sentence)", "emerging",
              _make_pattern(r"\butilize\b[^.]*?\b(?:gonna|wanna|kinda)\b"),
              "Pick a register and stay there"),
    AIPattern("P37", "Source-listing as content", "emerging",
              _make_pattern(r"^\s*(?:Source:|Sources:)\s*\d+\.", re.MULTILINE),
              "Integrate sources via in-text citations, not bullet lists"),
    # ── COMMUNITY 2026 ────────────────────────────────────────
    AIPattern("P38", "Paragraph-reshuffling immunity (filler-heavy)", "community",
              # Meta-detector; placeholder
              _make_pattern(r"$.^"),
              "Hard to detect; check if reordering paragraphs changes meaning"),
    AIPattern("P39", "Whether-you-prefer closing summary", "community",
              _make_pattern(r"\bwhether you[''']?re (?:a |an )?\w+(?:,| or)? (?:a |an )?\w+\b"),
              "End with a single recommendation, not an audience matrix"),
    AIPattern("P40", "Symbolic gloss (represents / symbolizes)", "community",
              _make_pattern(r"\b(?:represents|symbolizes|stands for|embodies) (?:a |an |the )\w+ (?:approach|paradigm|philosophy|ethos|spirit)\b"),
              "Be concrete: what does it actually do?"),
    AIPattern("P41", "Infomercial hooks (The catch? The kicker?)", "community",
              _make_pattern(r"\b(?:the (?:catch|kicker|twist|best part|secret))[?]\b", re.IGNORECASE),
              "Just state the fact; don't tease it"),
    AIPattern("P42", "Erratic inline bolding (3+ per paragraph)", "community",
              _make_pattern(r"(?:\*\*[^*]+\*\*[^\n]*?){3,}", re.MULTILINE),
              "Use bold for scanning anchors only; not emphasis sprinkles"),
    AIPattern("P43", "Treadmill Effect (long form, low info)", "community",
              # Meta-detector
              _make_pattern(r"$.^"),
              "Audit info density: 500w with ≤100w new = treadmill"),
]


# ─── Lint ─────────────────────────────────────────────────────

@dataclass
class AITellHit:
    pattern_id: str
    pattern_name: str
    category: str
    line: int
    column: int
    matched_text: str
    context: str
    fix_hint: str


# ─── Structural-section awareness (2026-05-28) ─────────────────────
#
# WHY: the AI-Slop score = 4 × (distinct pattern types hit). Several patterns
# fire on the MANDATORY structural sections that every article in this plugin is
# REQUIRED to have (Key Takeaways, Table of Contents, References, Further Reading):
#   - P15 structured-list syndrome  → Key Takeaways IS a list; the TOC IS a list
#   - P26 perfect/error alternation → the References <ol> IS a perfect list
#   - P28 markdown bleeding (*x*)   → APA-7 reference TITLES are correctly italic
#   - P14/P42 bold overuse          → Key Takeaways bullets REQUIRE a bold lead clause
#   - P10 rule-of-three             → 3-item author lists / takeaway clauses are normal here
# Counting these as "AI tells" is a false positive: they are the prescribed format,
# not a writing smell. Before this fix, a clean article scored ~21-33 purely from
# these structural hits, forcing manual repair (stripping the required bold, swapping
# citations whose URL contained a flagged word, etc.) on every single article.
#
# FIX: suppress those specific pattern IDs ONLY inside the named structural sections
# (identified by their H2 heading, extent = until the next H2). Body prose is fully
# unaffected — a real P15/P28/P10 in a content section still fires.
# The "format-driven" pattern set: list structure (P15), perfect list (P26),
# bold lead clauses (P14/P42), markdown emphasis incl. APA-7 italic titles (P28),
# and short 3-item clauses (P10). Inside the mandatory structural sections these are
# the PRESCRIBED format, not a writing smell, so suppress the whole set uniformly.
# (Prose-AI-tell patterns like P1/P29 don't occur in list/citation sections, so a
# uniform set is safe there — it won't hide a real tell.)
_FORMAT_PATTERNS: Final[frozenset[str]] = frozenset({"P10", "P14", "P15", "P26", "P28", "P42"})

# ── VERBATIM-QUOTATION ZONES (2026-07-14) ────────────────────────────────────
# References / Further Reading additionally suppress **P7 (AI vocabulary cluster)**.
#
# WHY: an APA-7 entry quotes a source's TITLE verbatim, and real paper titles contain
# P7's vocabulary. The trigger case: Heckman et al. (2010), "Caffeine ... in foods: A
# COMPREHENSIVE review on consumption, functionality, safety, and regulatory matters"
# (J. Food Science) — a very widely cited caffeine reference. "comprehensive" is P7.
#
# The old comment above asserted "P7 doesn't occur in citation sections", and that
# assumption was simply wrong. The consequence was perverse: P7 imposed a permanent
# +4 ai_slop floor that NO humanizer could clear, because the only edit available is
# to alter a cited title — i.e. to FALSIFY A CITATION to satisfy a style linter. We
# will not build an incentive to falsify sources. A verbatim quotation is not our
# prose and must never be scored as our prose.
#
# Scope is deliberately narrow: ONLY the reference-list zones, where the text is
# quoted from sources. P7 in body prose, FAQ, or Key Takeaways is still a real tell
# and still fires.
_CITATION_PATTERNS: Final[frozenset[str]] = _FORMAT_PATTERNS | {"P7"}
_STRUCTURAL_SUPPRESS: Final[list[tuple[re.Pattern[str], frozenset[str]]]] = [
    (re.compile(r"\bkey\s+takeaways\b", re.I),        _FORMAT_PATTERNS),
    (re.compile(r"\btable\s+of\s+contents\b", re.I),  _FORMAT_PATTERNS),
    (re.compile(r"\breferences\b", re.I),             _CITATION_PATTERNS),
    (re.compile(r"\bfurther\s+reading\b", re.I),      _CITATION_PATTERNS),
    # FAQ is a hard_veto mandatory structural section (same class as Key Takeaways /
    # TOC). Its prescribed Q&A format authors each question as a bold paragraph
    # (**Question?**) so wp_publisher can tag <p><strong>Q</strong></p> with
    # class="faq-question". That bold is the required format, not a writing smell, so
    # the bold-driven trio (P14/P28/P42) is a false positive here exactly as it is in
    # Key Takeaways. Suppress the same _FORMAT_PATTERNS set inside the FAQ section.
    (re.compile(r"\bfrequently\s+asked\s+questions\b", re.I), _FORMAT_PATTERNS),
    (re.compile(r"^faq$", re.I),                              _FORMAT_PATTERNS),
    # v3.31 visual-design blocks (2026-07-01): these components PRESCRIBE bold-led
    # stat items (`- **$509** label`), bold definition terms (`**Term**: def`), and
    # short clauses — the same format class as Key Takeaways. Without these entries
    # every v3.31-designed article carried a false P10/P14/P15/P26/P28/P42 floor the
    # humanizer could not clear without de-designing frozen blocks or renaming frozen
    # headings (observed on all 3 articles of the 2026-07-01 loamwright batch).
    (re.compile(r"\bby\s+the\s+numbers\b", re.I),             _FORMAT_PATTERNS),
    (re.compile(r"\bglossary\b", re.I),                       _FORMAT_PATTERNS),
    (re.compile(r"\btl;?dr\b", re.I),                         _FORMAT_PATTERNS),
    (re.compile(r"\bat\s+a\s+glance\b", re.I),                _FORMAT_PATTERNS),
]

# ── CTA CONVERSION BLOCKS (v3.41.3, 2026-07-19) ──────────────────────────────
# The injected CTA card is CONFIG-AUTHORED machine text (business-context.cta →
# cta-writer → cta_injector), already verified by three dedicated executors
# (cta-tone-check, cta-diversity-check, verify_post check 29) — and the ONLY
# repair agent (humanizer) is FORBIDDEN from editing it. Scoring it here
# manufactured an unfixable gate failure on 2026-07-19: cta_injector's
# sanitize_copy deliberately curls apostrophes to U+2019 (project-charlie-class WAF
# bypass), then P17 fired on the curl and ai_slop crossed the <20 gate with no
# agent allowed to touch the text. Same category error as scoring By-the-Numbers
# (2026-07-01) or References titles (2026-07-14): machine-prescribed text is not
# the writer's prose. Suppress the format set + P17 (curly quotes) + P13
# (em-dash count; the injector rewrites em-dashes anyway and render_lint L12
# still hard-vetoes them article-wide, so nothing real is hidden).
# CTA headings are identified through scripts/_core/component_headings.
# classify_heading — the SAME registry the injector and publisher use — never a
# duplicated phrase list here (Rule 11).
_CTA_PATTERNS: Final[frozenset[str]] = _FORMAT_PATTERNS | {"P13", "P17"}

# Patterns that are only an AI-tell ABOVE a count threshold (per their own fix_hint).
# A single question-format heading is great for SEO / featured snippets; the tell is
# the AI habit of making EVERY heading a question. P27's hint already says ">3 ... is AI-style".
_COUNT_THRESHOLDS: Final[dict[str, int]] = {"P27": 3}

# Widened H2→H2-H4 (2026-07-07): the structural allowlist keyed off H2 headings only,
# so a stat_grid nested as "### By the Numbers" inside a normal content section fell
# through every suppression (observed as a false P15 floor on the 2026-07-07 batch —
# the 2026-07-05 _BOLD_LED_LINE patch only covered the bold trio, not P15/P10/P26).
# Captures (level_hashes, heading_text); extent logic uses the level so a child H3
# block ends at the next H2/H3, while a parent H2 block (e.g. FAQ with ### question
# subheadings) still runs to the next H2 — child headings do NOT truncate it.
_HEADING_LINE: Final[re.Pattern[str]] = re.compile(r"^(#{2,4})\s+(.*?)\s*(?:\{#[^}]*\})?\s*$")
_H2_LINE: Final[re.Pattern[str]] = _HEADING_LINE  # back-compat alias

# ─── Bold-led list item exemption (2026-07-05) ──────────────────────
#
# WHY: the H2-heading-text allowlist above (_STRUCTURAL_SUPPRESS) only exempts the
# bold-driven trio (P14/P28/P42) when the ENCLOSING H2's heading text literally
# matches one of ~9 fixed phrases (Key Takeaways, By the Numbers, Glossary, ...).
# But references/style/visual-design-components.md sanctions the SAME bold-led
# format for components that live under arbitrary content H2s and take several
# native-markdown shapes, not just a list item:
#   - Component 5 "checklist" list items:        "- **Label** ..."
#   - Component 7 callout blockquotes:            "> **Warning:** ..."
#   - Component 2 "stat_grid" nested as an H3 sub-block inside a normal content
#     section (not its own H2): "### By the numbers" + "- **N** ..."
#   - Field-label paragraphs (JD-template style):  "**Title:** ..."
# The heading-text allowlist can only ever cover the fixed phrases someone
# remembered to add — a 2026-07-04 hiring-guide article using
# `design_components: ["checklist", "callout"]` on H2s titled "Red flags: ..." /
# "A copy-paste ... job description template" and a stat_grid nested as "### By
# the numbers" under a normal content H2 all fell straight through the
# allowlist, producing a false AI-slop floor the humanizer could not clear
# without gutting formatting the format policy itself mandates (same root cause
# as the 2026-07-01 By-the-Numbers/Glossary fix above, one layer deeper). The
# STRUCTURAL SHAPE (bold is the first visible token on the line, optionally after
# a list/blockquote marker) is what makes the bold legitimate, not which heading
# sits above it or whether it is wrapped in "-"/">" — so exempt by shape.
# This does NOT touch prose paragraphs (P14/P28/P42's real target: bold sprinkled
# mid-sentence, not at the start of a line, inside flowing text).
# The optional `\[[ xX]\]\s+` token (2026-07-07): GFM task-list items
# ("- [ ] **Step 1: ...**") are the same bold-led checklist shape, but the
# checkbox token sat between the list marker and the bold run so the exemption
# never fired — 27 of 43 hits on one 2026-07-07 batch article were this false
# positive. (templates/checklist.md no longer prescribes GFM checkboxes — the
# publisher's markdown-it has no tasklists plugin so "[ ]" leaks literally, see
# render_lint L13 — but writers can still emit the syntax from habit.)
_BOLD_LED_LINE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:(?:[-*+]|\d+\.)\s+(?:\[[ xX]\]\s+)?|>\s+)?\*\*[^*\n]+\*\*"
)
_BOLD_TRIO: Final[frozenset[str]] = frozenset({"P14", "P28", "P42"})

# Balanced-ITALIC exemption for P28 (2026-07-17). P28 ("markdown bleeding into
# prose") targets asterisks SHOWING to a reader — escape chars / orphan markers.
# But its regex `(?:^|\s)\*{1,3}\w` matches the OPENER of ANY emphasis run, so a
# correct `*Hibiscus sabdariffa*` binomial counts as a hit. Because P28 feeds
# ai_slop_score, that made STRIPPING correct ICN italics worth -4 pts (the
# humanizer did exactly that on a sibling article). A closed *italic* pair in
# markdown SOURCE is correct, not a leak.
# SCOPED TO ITALIC (single `*`) DELIBERATELY: mid-sentence **bold** overuse is a
# real AI-tell the trio (P14/P28/P42) is meant to catch, so a line containing any
# `**bold**` is NOT exempted; only lines whose asterisks are all closed ITALIC
# runs are. Genuine orphan/unclosed `*` still fires (render_lint L3 backs this up
# on rendered HTML).
_ITALIC_PAIR: Final[re.Pattern[str]] = re.compile(r"\*[^*\n]+\*")


def _line_is_italic_only_balanced(line: str) -> bool:
    """True when the line has no bold and every asterisk is a closed *italic* run."""
    if "**" in line:
        return False
    return "*" not in _ITALIC_PAIR.sub("", line)


def _structural_suppression_map(text: str) -> dict[int, frozenset[str]]:
    """Map each 1-based line number that falls inside a mandatory structural section
    to the set of pattern IDs that should be suppressed there. Lines are 1-based to
    match find_all_with_line()."""
    lines = text.split("\n")
    headings: list[tuple[int, int, str]] = []  # (0-based line index, level, heading text)
    for i, ln in enumerate(lines):
        m = _HEADING_LINE.match(ln)
        if m:
            headings.append((i, len(m.group(1)), m.group(2).strip()))
    out: dict[int, frozenset[str]] = {}
    from scripts._core.component_headings import classify_heading
    for idx, (i, level, htext) in enumerate(headings):
        sup: set[str] = set()
        for pat, ids in _STRUCTURAL_SUPPRESS:
            if pat.search(htext):
                sup |= ids
        # v3.41.3: injected CTA blocks (any heading the component registry
        # classifies as a cta* skin) suppress _CTA_PATTERNS — see the block
        # comment above _CTA_PATTERNS for the 2026-07-19 deadlock this cures.
        _cid = classify_heading(htext)
        if _cid and _cid.startswith("cta"):
            sup |= _CTA_PATTERNS
        if not sup:
            continue
        # Extent ends at the next heading of the SAME OR HIGHER level: an H2 block
        # (e.g. FAQ) spans across its own ### subheadings; a nested "### By the
        # Numbers" block ends at the next H2/H3. Nested extents UNION (not clobber)
        # so a child block inside a suppressed parent keeps both suppression sets.
        end_excl_1b = len(lines) + 1
        for j in range(idx + 1, len(headings)):
            if headings[j][1] <= level:
                end_excl_1b = headings[j][0] + 1
                break
        frozen = frozenset(sup)
        for ln_1b in range(i + 1, end_excl_1b):
            out[ln_1b] = out.get(ln_1b, frozenset()) | frozen
    return out


def lint(
    text: str,
    patterns: list[AIPattern] | None = None,
    *,
    apply_structural_suppression: bool = True,
) -> list[AITellHit]:
    """Detect AI patterns in text. Returns sorted by line.

    apply_structural_suppression (default True): drop false-positive hits that fall
    inside mandatory structural sections (Key Takeaways / TOC / References / Further
    Reading) where the flagged pattern is the prescribed format, and apply count
    thresholds (e.g. P27 question headings only count at 3+). Pass False to get the
    raw, unfiltered hit list (e.g. for debugging the detector itself).
    """
    if patterns is None:
        patterns = DEFAULT_AI_PATTERNS

    hits: list[AITellHit] = []
    for p in patterns:
        # Skip placeholder regexes
        if p.trigger.pattern == "$.^":
            continue
        for m in find_all_with_line(p.trigger, text):
            hits.append(AITellHit(
                pattern_id=p.id, pattern_name=p.name, category=p.category,
                line=m.line, column=m.column,
                matched_text=m.text, context=m.context,
                fix_hint=p.fix_hint,
            ))

    if apply_structural_suppression:
        supmap = _structural_suppression_map(text)
        if supmap:
            hits = [h for h in hits if h.pattern_id not in supmap.get(h.line, frozenset())]
        # Bold-led line exemption: drop P14/P28/P42 hits whose match starts on a
        # line that opens on a bold run ("- **Label** ...", "> **Warning:** ...",
        # "**Title:** ..."), regardless of which H2/H3 heading is above it.
        # See _BOLD_LED_LINE docstring above for the rationale.
        text_lines = text.split("\n")
        def _is_bold_led_line(line_no: int) -> bool:
            # P28's regex allows a leading \s (including \n) before the asterisks, so a
            # hit reported on a blank line actually belongs to the bold run that opens
            # the NEXT line ("...\n\n**Title:** ..." reports on the blank line). Check
            # both the reported line and the line immediately after it.
            for idx in (line_no - 1, line_no):
                if 0 <= idx < len(text_lines) and _BOLD_LED_LINE.match(text_lines[idx]):
                    return True
            return False
        hits = [
            h for h in hits
            if not (h.pattern_id in _BOLD_TRIO and _is_bold_led_line(h.line))
        ]
        # P28 balanced-ITALIC exemption: a closed *italic* run (scientific binomial,
        # emphasized term) is not markdown bleed. Drop P28 hits whose line is
        # italic-only-balanced (bold-bearing lines and genuine orphan markers still
        # fire). P28's opener regex can report on the blank line before a run, so
        # a hit is exempt only if BOTH its line and the line after it are clean.
        def _italic_only_at(line_no: int) -> bool:
            for idx in (line_no - 1, line_no):
                if 0 <= idx < len(text_lines) and not _line_is_italic_only_balanced(text_lines[idx]):
                    return False
            return True
        hits = [
            h for h in hits
            if not (h.pattern_id == "P28" and _italic_only_at(h.line))
        ]
        # Count thresholds: drop a pattern entirely if it occurs fewer than N times.
        if _COUNT_THRESHOLDS:
            counts: dict[str, int] = {}
            for h in hits:
                counts[h.pattern_id] = counts.get(h.pattern_id, 0) + 1
            hits = [
                h for h in hits
                if h.pattern_id not in _COUNT_THRESHOLDS
                or counts[h.pattern_id] >= _COUNT_THRESHOLDS[h.pattern_id]
            ]

    hits.sort(key=lambda h: (h.line, h.column))
    return hits


def patterns_hit_count(text: str) -> int:
    """Used by AI-Slop score formula: count distinct pattern types hit (not occurrences)."""
    return len({h.pattern_id for h in lint(text)})


# ─── CLI ─────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="43 AI-pattern detector")
    ap.add_argument("file", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--category", help="Filter by category (content/language/communication/filler/emerging/community)")
    ap.add_argument("--max-display", type=int, default=80)
    args = ap.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 2

    text = args.file.read_text(encoding="utf-8")
    hits = lint(text)
    if args.category:
        hits = [h for h in hits if h.category == args.category]

    if args.json:
        distinct_patterns = sorted({h.pattern_id for h in hits})
        out = {
            "file": str(args.file),
            "hits_count": len(hits),
            "distinct_patterns_hit": len(distinct_patterns),
            "distinct_pattern_ids": distinct_patterns,
            "passed": len(hits) == 0,
            "hits": [asdict(h) for h in hits[:args.max_display]],
            "truncated": len(hits) > args.max_display,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"File: {args.file}")
        print(f"Hits: {len(hits)}  (distinct patterns: {len({h.pattern_id for h in hits})})")
        if hits:
            print()
            for h in hits[:args.max_display]:
                print(f"  {h.pattern_id} [{h.category}]  line {h.line}:{h.column}  '{h.matched_text}'")
                print(f"    → {h.fix_hint}")
                print(f"    context: …{h.context[:100]}…")
                print()
    return 0 if not hits else 1


if __name__ == "__main__":
    sys.exit(main())
