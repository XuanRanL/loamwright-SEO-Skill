"""scripts/lint/render_lint.py — Pre-publish render-and-inspect leak detector.

PURPOSE
─────────
Catches the class of bugs where markdown-it-py + html=False silently produces
visible broken-looking HTML in the rendered post body. Replaces the historical
hand-curated allowlist approach in verify_post.check_06 with a generic
classifier of failure modes.

Run BEFORE wp_publisher pushes to WordPress. Run AGAIN after publish via the
parallel post-publish checks in verify_post.py for defense in depth.

DETECTED LEAK CLASSES
─────────────────────
  L1  HTML-escape-in-body
      Pattern: `&lt;/?tagname(&gt;|\\s|/>)` inside reader-visible content
      elements (`<li>`, `<p>`, `<td>`, `<th>`, `<figcaption>`, `<dd>`).
      Example: '<li>**&lt;strong&gt;The 700 watt class…</li>'
      Cause: writer used raw HTML tag (<strong>, <em>, <span>, …) inside
      markdown body; html=False escaped it; result reads as broken HTML
      to the reader.
      The regex deliberately includes `&gt;` as a boundary so escaped tag
      closes (like `&lt;strong&gt;`) match, while still rejecting mathematical
      uses like `&lt; 5` (followed by space + digit, no `&gt;` close).

  L2  Pandoc-anchor-leak
      Pattern: `\\{#[a-zA-Z0-9_-]+\\}` anywhere in heading text content.
      Example: '<h2>Electrical Budget {#electrical-budget}</h2>'
      Cause: writer used '## Title {#id}' Pandoc syntax; base markdown-it-py
      doesn't parse it; literal text leaks into heading.
      (As of 2026-05-21, markdown_to_html._add_anchor_ids STRIPS this before
      slug generation — but the lint stays as belt-and-suspenders if the
      stripper is ever removed or bypassed.)

  L3  Orphan-bold-marker
      Pattern: `^\\s*\\*\\*[^*]` or `[^*]\\*\\*\\s*$` inside any list item or
      paragraph text where the paragraph does NOT contain a closing/opening
      `**` to pair against.
      Example: '<li>**The 700 watt class without CO2</li>' (no closing **)
      Cause: writer wrote unbalanced markdown bold; renders as literal *
      asterisks instead of bold.

  L5  Claim-marker-leak
      ⇒ Writer agents emit [claim:cN_section_id] markers that the fact-check
        + assembly stages are supposed to swap for (Author, Year) APA inline
        citations. Leakage of the raw marker into rendered HTML = those stages
        were silently skipped.
      Example: '<p>...PPFD saturates 500-700 [claim:c1_abstract]...'

  L7  Frontmatter-metadata-leak
      Pattern: YAML frontmatter keys (primary_keyword:, Stage:, task_id:,
      word_count_target:, focus_keyphrase:) visible in body text.
      Cause: UTF-8 BOM at byte 0 of draft.md breaks the ^--- regex in
      split_frontmatter(), so the entire YAML block passes through as body.
      WordPress wptexturize converts --- to em-dash — on render.

  L8  Section-JSON-envelope-leak
      Pattern: section/*.json envelope keys ("section_index", "citation_capsule",
      "claims", "self_check", "information_gain_markers", "needs_source",
      "hint_query") visible in body text.
      Cause: orchestrator pasted raw section JSON instead of extracting
      the markdown field via assemble.py.

  L4  Broken-srcset-pattern
      Pattern: `<img[^>]*srcset="[^"]*-\\d+w\\.(?:png|jpe?g|webp)`
      Cause: hand-rolled srcset emission referencing files no upstream code
      generates. Triggers Bug 3 from the 2026-05-21 incident.

  L11 Competitor-domain-cited  (added 2026-06-20, project-aware)
      ⇒ A competitor / peer ("同行") domain appears as a cited source — in an
        <a href> (References list or body outbound link) or as a bare URL in an
        APA reference string. Resolved against the active project's
        business-context.json :: citation_source_policy.do_not_cite_domains via
        scripts/_core/competitor_domains.py. Skipped entirely when the project
        has no policy (backward compatible). Brand NAMES in prose are NOT
        flagged — only URLs pointing at competitor domains.
      Example: '<li>Fluence (2024). PPFD guide. https://fluence-led.com/...</li>'
      See root CLAUDE.md Rule 8.

USAGE
─────
  # Lint a draft.md before publish:
  python -m scripts.lint.render_lint --draft memory/workspace/{task}/draft.md
  python -m scripts.lint.render_lint --workspace {task_id}

  # JSON output (used by the seo-blog gate orchestrator):
  python -m scripts.lint.render_lint --workspace {task_id} --json

EXIT CODE
─────────
  0 — no leaks detected
  1 — at least one leak detected
  2 — invalid args / file not found / convert() error

PHILOSOPHY
──────────
This lint detects FAILURE CLASSES, not specific past incidents. Adding a new
forbidden pattern to verify_post.check_06's hand-curated allowlist after every
incident is whack-a-mole. This file classifies, so the next previously-unseen
markdown-it edge case is also caught.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable


# ── Detection regexes ───────────────────────────────────────────────────────

# L1: HTML-escape-in-body — find escaped tag opener inside content elements.
# Match &lt; (or &lt;/) followed by tagname followed by &gt; OR whitespace OR `/>`.
# Critically includes `&gt;` boundary so `&lt;strong&gt;` matches; excludes mathematical
# `&lt; 5` (where the char after `&lt;` is space + digit) to avoid false positives.
_ESCAPED_TAG_RE = re.compile(r"&lt;/?[a-zA-Z][a-zA-Z0-9]*(?:&gt;|[\s>/])")

# L2: Pandoc anchor leak — {#id} in any heading text
_PANDOC_LEAK_RE = re.compile(r"\{#[a-zA-Z0-9_-]+\}")

# L3: Orphan/unbalanced bold — odd number of ** in a single paragraph/li
_BOLD_MARKER_RE = re.compile(r"\*\*")

# L4: Hand-rolled srcset variant — references -NNNw.{png,jpg,jpeg,webp}
_BROKEN_SRCSET_RE = re.compile(
    r"<img[^>]*srcset=\"[^\"]*-\d+w\.(?:png|jpe?g|webp)",
    flags=re.IGNORECASE,
)

# Content elements whose .text is reader-visible body content
_BODY_ELEMENT_TAGS = ("li", "p", "td", "th", "figcaption", "dd", "blockquote")
_BODY_ELEMENT_RE = re.compile(
    r"<(" + "|".join(_BODY_ELEMENT_TAGS) + r")\b[^>]*>(.*?)</\1>",
    flags=re.IGNORECASE | re.DOTALL,
)
_HEADING_RE = re.compile(
    r"<(h[1-6])\b[^>]*>(.*?)</\1>",
    flags=re.IGNORECASE | re.DOTALL,
)

# <code>/<pre> segments are excised before the L1 scan — escaped tag names inside
# rendered code spans are legitimate display, not a leak (2026-07-01).
_CODE_SPAN_RE = re.compile(
    r"<(pre|code)\b[^>]*>.*?</\1>",
    flags=re.IGNORECASE | re.DOTALL,
)


# ── Result types ────────────────────────────────────────────────────────────

@dataclass
class Defect:
    """A single detected leak."""
    leak_class: str          # 'L1'…'L11' (see module docstring)
    label: str
    element_tag: str         # 'li' / 'h2' / 'img' / etc.
    element_excerpt: str     # ≤200 chars of the surrounding context
    detail: str              # what was wrong


@dataclass
class LintResult:
    """Output of a single render_lint run."""
    passed: bool
    defect_count: int
    defects: list[Defect] = field(default_factory=list)
    rendered_html_len: int = 0
    source_path: str = ""
    # 2026-06-18 fix A: count of scaffold markers ([ORIGINAL DATA] etc.) that
    # were auto-stripped in memory before linting (mirrors the publish-path
    # strip). >0 means the optimize phase re-introduced markers — observable
    # signal, but NOT a hard veto, because the publisher strips them too.
    scaffold_markers_autostripped: int = 0

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "defect_count": self.defect_count,
            "defects": [asdict(d) for d in self.defects],
            "rendered_html_len": self.rendered_html_len,
            "source_path": self.source_path,
            "leak_classes": sorted({d.leak_class for d in self.defects}),
            "scaffold_markers_autostripped": self.scaffold_markers_autostripped,
        }


# ── Detectors ───────────────────────────────────────────────────────────────

def _excerpt(text: str, max_len: int = 180) -> str:
    """Trim + collapse whitespace + truncate for human reading."""
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def detect_L1_html_escape_in_body(html: str) -> list[Defect]:
    """L1 — Any &lt;tagname …&gt; inside reader-visible body content.

    Content inside <code>/<pre> is EXCISED before scanning (2026-07-01): an inline
    code span like `` `<a href>` `` renders as <code>&lt;a href&gt;</code>, which is
    legitimate, intentional display of a tag name — not a markdown leak. Only the
    remaining (non-code) text of the element is scanned, so a real raw-`<strong>`
    leak elsewhere in the same element still fires.
    """
    defects: list[Defect] = []
    for m in _BODY_ELEMENT_RE.finditer(html):
        tag = m.group(1).lower()
        inner = _CODE_SPAN_RE.sub(" ", m.group(2))
        for esc_m in _ESCAPED_TAG_RE.finditer(inner):
            defects.append(Defect(
                leak_class="L1",
                label="escaped HTML tag in body element text",
                element_tag=tag,
                element_excerpt=_excerpt(inner),
                detail=f"escaped tag literal {esc_m.group(0)!r} inside <{tag}>",
            ))
            break  # one defect per element is enough
    return defects


def detect_L2_pandoc_anchor_leak(html: str) -> list[Defect]:
    """L2 — Literal {#anchor-id} inside any heading text."""
    defects: list[Defect] = []
    for m in _HEADING_RE.finditer(html):
        tag = m.group(1).lower()
        inner = m.group(2)
        # Strip inner tags for clean text-only check
        text = re.sub(r"<[^>]+>", "", inner)
        for leak in _PANDOC_LEAK_RE.findall(text):
            defects.append(Defect(
                leak_class="L2",
                label="Pandoc/Kramdown anchor literal inside heading text",
                element_tag=tag,
                element_excerpt=_excerpt(text),
                detail=f"literal anchor syntax {leak!r} visible in heading",
            ))
            break
    return defects


def detect_L3_unbalanced_markdown_bold(html: str) -> list[Defect]:
    """L3 — Odd number of `**` markers in a single body element.

    An even count of '**' tokens in one element means closed bold pairs. An odd
    count means orphan markers that print literally. Heuristic: only flag
    elements that contain BOTH an asterisk-pair and OTHER content (not pure code).
    """
    defects: list[Defect] = []
    for m in _BODY_ELEMENT_RE.finditer(html):
        tag = m.group(1).lower()
        inner = m.group(2)
        # Skip if inside <pre> / <code> — markdown bold is intentional literal there
        if re.search(r"<(pre|code)\b", inner, flags=re.IGNORECASE):
            continue
        marker_count = len(_BOLD_MARKER_RE.findall(inner))
        if marker_count == 0:
            continue
        if marker_count % 2 != 0:
            # Strip tags for excerpt
            text = re.sub(r"<[^>]+>", "", inner)
            defects.append(Defect(
                leak_class="L3",
                label="unbalanced markdown bold marker (**)",
                element_tag=tag,
                element_excerpt=_excerpt(text),
                detail=f"{marker_count} `**` markers in element (odd → orphan)",
            ))
    return defects


def detect_L4_broken_srcset_pattern(html: str) -> list[Defect]:
    """L4 — Hand-rolled srcset referencing -NNNw.{ext} variants."""
    defects: list[Defect] = []
    for m in _BROKEN_SRCSET_RE.finditer(html):
        defects.append(Defect(
            leak_class="L4",
            label="hand-rolled srcset variant pattern (-NNNw.ext)",
            element_tag="img",
            element_excerpt=_excerpt(m.group(0), max_len=220),
            detail="srcset references derivative widths that no pipeline code generates; "
                   "every URL likely 404s on the live site",
        ))
    return defects


# L5: Claim-marker leak — '[claim:c1_section_id]' or '[claim:c1_a, c2_b]'
# in rendered body. Writers emit these markers; fact-check-and-citation +
# assembly are supposed to swap them to '(Author, Year)' inline citations.
# If they leak to rendered HTML, the upstream pipeline silently skipped the
# in-text-citation step. Defense layer 2 of 3 for the systemic claim-marker
# leak class (see feedback_claim_marker_leak_systemic.md).
# Expanded 2026-05-23: original regex matched [claim:cN_section] strictly but
# writer subagents have been observed emitting variants like [claim:c1_1] (no
# 's' prefix), [claim:c5_s4_1] (extra trailing _N), [claim:c2_S3] (uppercase S).
# Expanded again 2026-08-02: the digest run produced [claim:hc1_src] (marker id
# derived from a hand-curated cluster_id) — the old `c\d+`-anchored shape was
# INVISIBLE to this detector, so the "loud, recoverable gate failure" safety
# net citation_inject relies on did not exist for non-c-prefixed ids. Any
# bracketed [claim:...] id is a leak; there is no legitimate rendered form.
_CLAIM_MARKER_LEAK_RE = re.compile(
    r"\[claim:[a-z0-9_]+(?:\s*,\s*[a-z0-9_]+)*\]",
    re.IGNORECASE,
)


def detect_L5_claim_marker_leak(html: str) -> list[Defect]:
    """L5 — Unresolved [claim:cN_section_id] markers in rendered body.

    Catches all known variants:
      [claim:c1_s2]           — canonical
      [claim:c1_1]            — variant without 's' prefix
      [claim:c5_s4_1]         — variant with trailing suffix
      [claim:c1_S2]           — uppercase variant
      [claim:c1_s2, c2_s3]    — multi-marker
    """
    defects: list[Defect] = []
    for m in _CLAIM_MARKER_LEAK_RE.finditer(html):
        defects.append(Defect(
            leak_class="L5",
            label="unresolved [claim:cN_section] marker (writer-emitted, never swapped to APA inline)",
            element_tag="body",
            element_excerpt=_excerpt(m.group(0), max_len=160),
            detail="fact-check-and-citation + assembly steps were skipped; the marker should "
                   "have been swapped to '(Author, Year)' before render. Fix: rerun the "
                   "publish path so wp_publisher._apply_in_text_citations engages, OR "
                   "ensure citations.json has citations[].claim_markers_resolved[] entries "
                   "that point at this marker.",
        ))
    return defects


# L6 (added 2026-05-23): Writer-side scaffold/annotation markers leak.
# Writer subagent prompts instruct authors to annotate sections containing
# original data, unique insight, or personal experience for AI-search judges.
# These bracketed tokens are meant to be internal signals only, but they leak
# verbatim to rendered HTML if no upstream step strips them. The 2026-05-22
# 5-article project-charlie batch shipped 12 such leaks across 3 of 5 articles
# before being caught post-hoc by the reviewer subagent.
# See feedback_render_lint_missing_scaffold_marker_class.md
_SCAFFOLD_MARKER_LEAK_RE = re.compile(
    r"\[(?:ORIGINAL DATA|UNIQUE INSIGHT|PERSONAL EXPERIENCE|CAPSULE|EXAMPLE|CITATION CAPSULE|INFO GAIN)\]"
)


# L7: Frontmatter metadata leak — YAML keys that should never appear in rendered body.
# These are distinctive enough to avoid false positives in normal prose.
_FRONTMATTER_KEY_LEAK_RE = re.compile(
    r'\b(?:primary_keyword|focus_keyphrase|word_count_target|task_id|GeneratedAt|TaskId)\s*:',
    re.IGNORECASE,
)


def detect_L7_frontmatter_leak(html: str) -> list[Defect]:
    """L7 — YAML frontmatter keys visible in rendered body text.

    Detects the specific failure mode where UTF-8 BOM breaks frontmatter
    stripping and the entire YAML block renders as body paragraphs.
    """
    defects: list[Defect] = []
    for m in _BODY_ELEMENT_RE.finditer(html):
        tag = m.group(1).lower()
        inner = m.group(2)
        text = re.sub(r"<[^>]+>", "", inner)
        for leak in _FRONTMATTER_KEY_LEAK_RE.finditer(text):
            defects.append(Defect(
                leak_class="L7",
                label="YAML frontmatter key leaked into body (BOM-broken split_frontmatter)",
                element_tag=tag,
                element_excerpt=_excerpt(text),
                detail=f"frontmatter key {leak.group(0)!r} visible in <{tag}>; "
                       f"likely caused by UTF-8 BOM at byte 0 breaking ^--- regex",
            ))
            break
    return defects


# L8: Section JSON envelope leak — raw section/*.json metadata in body text.
_SECTION_JSON_KEY_LEAK_RE = re.compile(
    r'"(?:section_index|citation_capsule|claims|self_check|information_gain_markers|needs_source|hint_query)"\s*:',
)


def detect_L8_section_json_leak(html: str) -> list[Defect]:
    """L8 — Raw section JSON envelope keys visible in rendered body.

    Detects the failure mode where the orchestrator pasted raw sections/*.json
    content instead of extracting the markdown field via assemble.py.
    """
    defects: list[Defect] = []
    for m in _BODY_ELEMENT_RE.finditer(html):
        tag = m.group(1).lower()
        inner = m.group(2)
        text = re.sub(r"<[^>]+>", "", inner)
        for leak in _SECTION_JSON_KEY_LEAK_RE.finditer(text):
            defects.append(Defect(
                leak_class="L8",
                label="raw section JSON envelope leaked into body (orchestrator skipped assemble.py)",
                element_tag=tag,
                element_excerpt=_excerpt(text),
                detail=f"section envelope key {leak.group(0)!r} visible in <{tag}>; "
                       f"orchestrator likely pasted raw section JSON instead of extracting markdown field",
            ))
            break
    return defects


def detect_L6_scaffold_marker_leak(html: str) -> list[Defect]:
    """L6 — Writer-side scaffold/annotation markers leaked to rendered HTML.

    These tokens (e.g. [ORIGINAL DATA], [UNIQUE INSIGHT]) are author-internal
    annotations meant to signal information-gain content to fact-checker /
    reviewer subagents. They are NOT meant to render to readers.
    """
    defects: list[Defect] = []
    for m in _SCAFFOLD_MARKER_LEAK_RE.finditer(html):
        defects.append(Defect(
            leak_class="L6",
            label="writer-side scaffold/annotation marker leaked to rendered body",
            element_tag="body",
            element_excerpt=_excerpt(m.group(0), max_len=120),
            detail="Marker tokens like [ORIGINAL DATA] / [UNIQUE INSIGHT] / [PERSONAL EXPERIENCE] "
                   "are internal annotations from writer subagent prompts. As of 2026-06-03 they are "
                   "stripped deterministically in scripts/build/assemble.py :: _normalize_markdown "
                   "(which also unglues heading/body for L2). This lint remains the safety net: if you "
                   "see this defect, assembly was bypassed or a marker was introduced after assembly. "
                   "Cleanup: re.sub(r'\\s*\\[(?:ORIGINAL DATA|UNIQUE INSIGHT|PERSONAL EXPERIENCE|CAPSULE)\\]\\s*', ' ', body)",
        ))
    return defects


def detect_L9_signature_before_references(html: str) -> list[Defect]:
    """L9 — Article signature appears BEFORE References heading.

    The canonical order is: Conclusion → References → <hr/> → Signature.
    When the signature is before References, the publisher's auto-tagger
    may fail to apply class="article-signature" (distance guard), and
    the visual order is wrong for readers.
    """
    defects: list[Defect] = []
    # NOTE: the span between <em> and "Last reviewed" is bounded with [^<]* (not
    # .*?) so the pattern cannot greedily span from an EARLIER italic node (e.g. a
    # *Caption:* table caption rendered as <p><em>...</em></p>) all the way down to
    # the real signature's </em></p>. Without this bound, any article with an italic
    # caption before the signature produced a false-positive L9 (signature appears
    # to start at the caption's offset, which is before References). Fixed 2026-06-14.
    sig_pattern = re.compile(r'<p[^>]*>\s*<em>[^<]*Last reviewed and updated.*?</em>\s*</p>', re.DOTALL | re.IGNORECASE)
    ref_pattern = re.compile(r'<h2[^>]*>\s*References\s*</h2>', re.IGNORECASE)
    sig_match = sig_pattern.search(html)
    ref_match = ref_pattern.search(html)
    if sig_match and ref_match and sig_match.start() < ref_match.start():
        defects.append(Defect(
            leak_class="L9",
            label="article signature appears before References heading",
            element_tag="p",
            element_excerpt=_excerpt(sig_match.group(0), max_len=120),
            detail="Signature must come AFTER References. Canonical order: "
                   "Conclusion → ## References → <hr/> → *Last reviewed...*. "
                   "Move the signature paragraph below the References <ol> block.",
        ))
    return defects


_INPAGE_LINK_RE = re.compile(r'<a\b[^>]*\bhref="#([^"]+)"', re.IGNORECASE)
_ID_ATTR_RE = re.compile(r'\bid="([^"]+)"', re.IGNORECASE)


def detect_L10_broken_inpage_anchor(html: str) -> list[Defect]:
    """L10 — an in-page jump link (e.g. a Table-of-Contents entry) points at a
    heading id that does not exist in the body.

    Root cause this guards against: a writer-supplied TOC built from outline.json
    short anchor_ids (e.g. href="#faq") never matches the heading ids, which are
    full-text slugs (id="frequently-asked-questions"). assemble.py now regenerates
    the TOC from real heading anchors, but this gate is the belt-and-suspenders:
    ANY broken in-page anchor is a hard veto, regardless of how it got there.
    """
    defects: list[Defect] = []
    targets = [m.group(1) for m in _INPAGE_LINK_RE.finditer(html)]
    ids = {m.group(1) for m in _ID_ATTR_RE.finditer(html)}
    seen: set[str] = set()
    for t in targets:
        if not t or t in ids or t in seen:
            continue
        seen.add(t)
        defects.append(Defect(
            leak_class="L10",
            label="in-page jump link points at a non-existent heading id",
            element_tag="a",
            element_excerpt=f'href="#{_excerpt(t, max_len=120)}"',
            detail=f'TOC/jump link href="#{t}" has no matching id="{t}" in the body. '
                   "Writer TOC likely used outline short anchor_ids while heading ids "
                   "are full-text slugs. Re-run assemble.py (TOC is auto-regenerated "
                   "from real heading anchors).",
        ))
    return defects


def detect_L11_competitor_domain(html: str, policy=None) -> list[Defect]:
    """L11 — a competitor/peer domain appears as a cited source.

    Project-aware: ``policy`` is a scripts._core.competitor_domains.CompetitorPolicy.
    When it is None or disabled (project has no citation_source_policy), this
    detector is a no-op — keeping render_lint fully backward compatible for
    projects that have not opted in. Only URLs are inspected, never prose, so a
    competitor brand NAME in a comparison sentence is never flagged.
    """
    if policy is None or not getattr(policy, "enabled", False):
        return []
    defects: list[Defect] = []
    for url, domain in policy.find_blocked_in_html(html):
        defects.append(Defect(
            leak_class="L11",
            label="competitor/peer domain cited as a source",
            element_tag="a",
            element_excerpt=_excerpt(url, max_len=160),
            detail=f"URL points at competitor domain {domain!r} (project blocklist "
                   f"citation_source_policy.do_not_cite_domains). A competitor must never "
                   f"appear in an in-text citation, the References list, an outbound link, "
                   f"or JSON-LD citation/sameAs. Re-source to a neutral authority "
                   f"(peer-reviewed / .gov / .edu / standards body / supplier datasheet) "
                   f"or drop the claim. See root CLAUDE.md Rule 8.",
        ))
    return defects


_REFERENCES_H2_RE = re.compile(r'<h2[^>]*>\s*References\s*</h2>', re.IGNORECASE)
_VERBATIM_CONTAINER_RE = re.compile(
    r'<blockquote\b.*?</blockquote>|<pre\b.*?</pre>|<code\b.*?</code>',
    re.DOTALL | re.IGNORECASE,
)


def detect_L12_em_dash_in_prose(html: str) -> list[Defect]:
    """L12 — an em-dash (U+2014) in editable body prose.

    WHY (2026-07-07 batch): the zero-em-dash house rule is enforced at write time
    (writer self_check) and by the humanizer — but humanizer runs BEFORE
    meta/schema/linker/geo/visual-designer/cta, and the only blocking downstream
    adjudication read the STALE humanizer-report (pre_publish_gate check_humanizer),
    so a post-humanizer stage could introduce an em-dash with no gate catching it
    (the geo-auditor did exactly that in the 2026-07-07 batch; caught only by hand).
    render_lint runs after every draft-editing stage and its `passed` flag is
    already hard-enforced, so this is the deterministic backstop.

    Scope guards (verbatim external text is NOT ours to restyle):
      - everything from the References H2 onward is excluded (APA titles of real
        papers may legitimately contain em-dashes; the signature follows References)
      - blockquote / pre / code contents are excluded (quotations + code are verbatim)
    """
    ref = _REFERENCES_H2_RE.search(html)
    scope = html[: ref.start()] if ref else html
    scope = _VERBATIM_CONTAINER_RE.sub("", scope)
    defects: list[Defect] = []
    for m in re.finditer("—", scope):
        start = max(0, m.start() - 60)
        end = min(len(scope), m.end() + 60)
        defects.append(Defect(
            leak_class="L12",
            label="em-dash (U+2014) in editable body prose",
            element_tag="",
            element_excerpt=_excerpt(scope[start:end], max_len=140),
            detail="House style bans em-dashes in our prose (references/style/"
                   "em-dash-prohibition.md). Writers and the humanizer enforce zero, "
                   "but a post-humanizer stage (geo/linker/visual-designer/capsule) "
                   "can re-introduce one. Replace with a comma, period, or parens. "
                   "Verbatim quotations (blockquotes) and References are exempt.",
        ))
    return defects


_GFM_CHECKBOX_LI_RE = re.compile(r'<li[^>]*>\s*\[(?: |x|X)\]', re.IGNORECASE)


def detect_L13_gfm_checkbox_leak(html: str) -> list[Defect]:
    """L13 — a GFM task-list checkbox leaked as literal "[ ]" / "[x]" text.

    The publisher's markdown-it instance ("gfm-like" + table/strikethrough) has NO
    tasklists plugin, so `- [ ] **Step 1**` renders as `<li>[ ] <strong>...` with
    the bracket token visible to readers (confirmed live against the canonical
    converter, 2026-07-07). templates/checklist.md no longer prescribes the
    syntax, but writers can emit it from habit — this is the deterministic gate.
    Fix: plain bold-led list items ("- **Step 1: ...**").
    """
    defects: list[Defect] = []
    for m in _GFM_CHECKBOX_LI_RE.finditer(html):
        start = m.start()
        defects.append(Defect(
            leak_class="L13",
            label="GFM task-list checkbox leaked as literal text",
            element_tag="li",
            element_excerpt=_excerpt(html[start:start + 140], max_len=140),
            detail="markdown-it has no tasklists plugin; `- [ ]` ships a literal "
                   "\"[ ]\" to readers. Rewrite the item as a plain bold-led list "
                   "entry: `- **Step N: ...**` (see templates/checklist.md).",
        ))
    return defects


# ── Orchestrator ────────────────────────────────────────────────────────────

def lint_rendered_html(html: str, source_path: str = "", *, policy=None) -> LintResult:
    """Run all leak detectors against a rendered-HTML string.

    ``policy`` (optional) is a competitor_domains.CompetitorPolicy enabling the
    project-aware L11 competitor-domain check. Omit/None → L11 is skipped.
    """
    all_defects: list[Defect] = []
    all_defects += detect_L1_html_escape_in_body(html)
    all_defects += detect_L2_pandoc_anchor_leak(html)
    all_defects += detect_L3_unbalanced_markdown_bold(html)
    all_defects += detect_L4_broken_srcset_pattern(html)
    all_defects += detect_L5_claim_marker_leak(html)
    all_defects += detect_L6_scaffold_marker_leak(html)
    all_defects += detect_L7_frontmatter_leak(html)
    all_defects += detect_L8_section_json_leak(html)
    all_defects += detect_L9_signature_before_references(html)
    all_defects += detect_L10_broken_inpage_anchor(html)
    all_defects += detect_L11_competitor_domain(html, policy)
    all_defects += detect_L12_em_dash_in_prose(html)
    all_defects += detect_L13_gfm_checkbox_leak(html)
    return LintResult(
        passed=not all_defects,
        defect_count=len(all_defects),
        defects=all_defects,
        rendered_html_len=len(html),
        source_path=source_path,
    )


def _resolve_competitor_policy(draft_path: Path):
    """Best-effort load of the competitor policy for a draft's task workspace.

    Resolves the task_id from the workspace dir name → project_slug from
    state.json → policy. Any failure (loose draft, no state, no policy) returns a
    disabled policy so L11 silently no-ops. Never raises.
    """
    try:
        from scripts._core import competitor_domains as cd
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        try:
            from scripts._core import competitor_domains as cd
        except Exception:
            return None
    try:
        return cd.load_policy_for_task(draft_path.parent.name)
    except Exception as e:
        print(f"render_lint: competitor policy load failed ({type(e).__name__}: {e}); "
              f"L11 skipped.", file=sys.stderr)
        return None


def _apply_citations_for_lint(body: str, workspace_dir: Path) -> str:
    """Pre-apply the publisher's citation swap IN MEMORY for the lint check.

    Reuses the canonical `wp_publisher._apply_in_text_citations` so the lint
    sees exactly what the publisher will ship. Without this, render_lint
    fires L5 false-positives on every draft that contains `[claim:cN_S]`
    markers — because the swap happens INSIDE the publisher at publish time,
    not in draft.md.

    No file is written; the swap is for the lint check only.

    Architecture note (2026-05-23 hardening):
    Resolves the time-of-check vs time-of-use mismatch in the pipeline:
    lint runs BEFORE publish, but the canonical swap runs DURING publish.
    Pre-applying the swap in lint memory makes lint see post-swap content
    while preserving the publish-time swap as the single source of truth.
    """
    if "[claim:" not in body:
        return body  # fast path: no markers to swap

    citations_path = workspace_dir / "citations.json"
    if not citations_path.exists():
        return body  # no citations file → publisher will strip markers; lint will flag → correct

    # Reuse publisher's swap logic verbatim
    try:
        from scripts.wordpress.wp_publisher import _apply_in_text_citations
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from scripts.wordpress.wp_publisher import _apply_in_text_citations

    workspace_task_id = workspace_dir.name
    try:
        return _apply_in_text_citations(body, workspace_task_id)
    except Exception as e:
        print(
            f"render_lint: pre-swap failed ({type(e).__name__}: {e}); linting raw body. "
            f"L5 may fire false-positives if publisher would have resolved them.",
            file=sys.stderr,
        )
        return body


def lint_draft_file(
    draft_path: Path,
    *,
    apply_citations: bool = True,
    apply_scaffold_strip: bool = True,
) -> LintResult:
    """Convert a draft.md → HTML using the canonical publisher pipeline, then lint.

    Args:
        draft_path: Path to draft.md
        apply_citations: If True (default), pre-apply citations.json's marker swap
            in memory before linting. Mirrors what wp_publisher does at publish
            time. Disable with --no-apply-citations to lint raw markers.
        apply_scaffold_strip: If True (default), pre-strip writer-side scaffold
            markers ([ORIGINAL DATA] etc.) in memory before linting. Mirrors the
            unconditional strip wp_publisher does at publish time (2026-06-18 fix
            A), so a post-optimize re-leak no longer hard-fails the L6 gate. The
            count is recorded on the result; disable to make L6 fire (the
            detector remains a genuine safety net).
    """
    try:
        from scripts.build.markdown_to_html import (
            convert, ConvertOptions, split_frontmatter, strip_scaffold_markers,
        )
    except ImportError:
        # Allow running from within the package dir
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from scripts.build.markdown_to_html import (
            convert, ConvertOptions, split_frontmatter, strip_scaffold_markers,
        )

    raw = draft_path.read_text(encoding="utf-8")
    _, body = split_frontmatter(raw)
    raw_body = body   # capture BEFORE the in-memory citation strip (for the raw L5 scan)

    # Pre-apply citations.json swap if requested (resolves time-of-check mismatch)
    if apply_citations:
        ws_dir = draft_path.parent
        if (ws_dir / "citations.json").exists():
            body = _apply_citations_for_lint(body, ws_dir)

    # Pre-strip scaffold markers in memory (mirrors wp_publisher publish-path
    # strip) so the optimize-phase re-leak does not hard-fail the gate.
    scaffold_stripped = 0
    if apply_scaffold_strip:
        body, scaffold_stripped = strip_scaffold_markers(body)

    # Use the SAME ConvertOptions wp_publisher.py uses, post-2026-05-21 fixes.
    opt = ConvertOptions(
        drop_h1=True,
        add_anchor_ids=True,
        wordpress_gutenberg=False,
        image_lazy_loading=True,
        image_srcset=False,   # matches wp_publisher.py:229 (2026-05-21 fix)
        pretty=True,
    )
    html = convert(body, opt)
    policy = _resolve_competitor_policy(draft_path)
    result = lint_rendered_html(html, source_path=str(draft_path), policy=policy)
    result.scaffold_markers_autostripped = scaffold_stripped

    # Raw claim-marker leak (2026-06-29). The apply_citations strip above hides any
    # [claim:...] marker from the HTML L5 detector, so on its own L5 is a FAKE hard
    # veto: it can only fire when citations.json is entirely absent. But once
    # citation-inject has RUN (its result file exists), a [claim:...] still in the
    # draft artifact is a genuine leak citation_inject failed to resolve (e.g. the
    # empty-`to` author-experience strip bug). Scan the RAW body so this is caught as
    # a real hard veto — making good on L5's own promise. No false positives: a clean
    # inject leaves zero markers in raw_body, and pre-inject drafts are skipped.
    if (draft_path.parent / "citation-inject-result.json").exists():
        raw_leaks = detect_L5_claim_marker_leak(raw_body)
        seen = {(d.leak_class, d.element_excerpt) for d in result.defects}
        added = [d for d in raw_leaks if (d.leak_class, d.element_excerpt) not in seen]
        if added:
            result.defects.extend(added)
            result.defect_count = len(result.defects)
            result.passed = result.defect_count == 0
    return result


# ── CLI ─────────────────────────────────────────────────────────────────────

def _print_human(result: LintResult) -> None:
    print(f"render_lint :: {result.source_path}")
    print(f"  rendered HTML: {result.rendered_html_len} chars")
    print(f"  defects: {result.defect_count}")
    if not result.defects:
        print("  ✓ PASS — no leaks detected")
        return
    print("  ✗ FAIL — leaks detected:")
    by_class: dict[str, list[Defect]] = {}
    for d in result.defects:
        by_class.setdefault(d.leak_class, []).append(d)
    for lc in sorted(by_class):
        items = by_class[lc]
        print(f"    [{lc}] {len(items)} defect(s):")
        for d in items[:5]:  # show first 5 per class
            print(f"       • {d.label} in <{d.element_tag}>: {d.detail}")
            print(f"         excerpt: {d.element_excerpt}")
        if len(items) > 5:
            print(f"       ... and {len(items) - 5} more {lc} defect(s)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pre-publish markdown-render leak detector")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--draft", type=Path, help="Path to draft.md")
    src.add_argument(
        "--workspace",
        type=str,
        help="Task ID → read memory/workspace/{task}/draft.md",
    )
    ap.add_argument("--out", type=Path, help="Write JSON result to this path")
    ap.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    ap.add_argument(
        "--no-apply-citations",
        action="store_true",
        help="Skip the in-memory citations.json swap (default: auto-apply if citations.json exists in the workspace). "
             "Use this to lint truly raw markers — e.g. before fact-check has run.",
    )
    ap.add_argument(
        "--no-apply-scaffold-strip",
        action="store_true",
        help="Skip the in-memory scaffold-marker strip (default: auto-strip [ORIGINAL DATA] etc., mirroring the "
             "publish-path strip). Use this to make the L6 detector fire on raw scaffold markers.",
    )
    args = ap.parse_args(argv)

    if args.workspace:
        plugin_root = Path(__file__).resolve().parents[2]
        draft_path = plugin_root / "memory" / "workspace" / args.workspace / "draft.md"
    else:
        draft_path = args.draft

    if not draft_path.exists():
        print(f"draft not found: {draft_path}", file=sys.stderr)
        return 2

    try:
        result = lint_draft_file(
            draft_path,
            apply_citations=not args.no_apply_citations,
            apply_scaffold_strip=not args.no_apply_scaffold_strip,
        )
    except Exception as e:
        print(f"render_lint failed: {e}", file=sys.stderr)
        return 2

    payload = result.to_dict()

    # Optional artifact write into workspace
    if args.workspace:
        workspace_dir = Path(__file__).resolve().parents[2] / "memory" / "workspace" / args.workspace
        if workspace_dir.exists():
            (workspace_dir / "render-lint.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8",
            )
    if args.out:
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_human(result)

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
