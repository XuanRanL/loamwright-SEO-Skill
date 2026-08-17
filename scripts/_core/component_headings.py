"""scripts/_core/component_headings.py — single source of truth: heading → visual component.

2026-07-01 root cure for the v3.31 component-binding failure class. The component
contract was split across TWO English-exact implementations — the CSS generator's
id-adjacency selectors (``h2#by-the-numbers + ul``) and the density gate's literal
regexes — which diverged on every input neither was calibrated for:

  * duplicate headings  → anchor dedup yields ``#by-the-numbers-2`` → CSS dead
    (ALL 4 stat grids in the 2026-07-01 batch shipped unstyled);
  * topic-scoped headings ("By the Numbers: 2026 Costs") → id mismatch → CSS dead
    AND density credit lost;
  * variant phrasing ("This Week at a Glance", digest 773) → id mismatch;
  * localized headings (## 数据速览) → empty slug → both layers blind.

This module is the ONE classifier both sides now consume (the same pattern that
fixed callouts via blockquote_classify): the publisher tags rendered headings +
their sibling blocks with stable classes, the CSS targets those classes, and the
density gate counts with the same classifier. Add a heading alias HERE and every
layer learns it at once.
"""
from __future__ import annotations

import html as _html
import re
from typing import Final

from scripts._core.heading_anchor import ANCHOR_INLINE_RE

# component_id -> spec.
#   phrases: canonical + alias phrases (lowercase). Matching (see classify_heading):
#     exact | prefix + separator (topic-scoped) | suffix ("This Week at a Glance").
#   sibling_tags: rendered block element(s) the component styles, immediately after
#     the heading.
#   css_class: stable class the publisher adds to that sibling block.
COMPONENTS: Final[dict[str, dict]] = {
    "stat_grid": {
        "phrases": ("by the numbers", "key stats", "数据速览"),
        "sibling_tags": ("ul",),
        "css_class": "xr-stat-grid",
    },
    "tldr": {
        "phrases": ("tl;dr", "tldr", "in short", "the bottom line", "quick answer"),
        "sibling_tags": ("p",),
        "css_class": "xr-tldr-box",
    },
    "at_a_glance": {
        "phrases": ("at a glance", "一览"),
        "sibling_tags": ("table",),
        "css_class": "xr-glance-table",
    },
    "glossary": {
        "phrases": ("glossary", "术语表"),
        "sibling_tags": ("ul",),
        "css_class": "xr-glossary-list",
    },
    # F4 fix: checklist was a "phantom component" — weighted by the density gate
    # and prescribed by the format playbook, but detected/styled by nothing.
    "checklist": {
        "phrases": ("checklist", "清单"),
        "sibling_tags": ("ul", "ol"),
        "css_class": "xr-checklist",
    },
    # CTA module (v3.34, 2026-07-04). Injected DETERMINISTICALLY by
    # scripts/optimize/cta_injector.py from business-context.json :: cta — writers
    # never hand-author it. The phrase set must cover every per-project default
    # heading the injector ships (see projects/*/business-context.json :: cta.heading).
    # Deliberately NOT counted by visual_density_check (promo is not substance;
    # its _HEADING_COMPONENT_KEYS map is explicit and excludes this id).
    #
    # Task 2 (2026-07-08): Expanded to 3 visual skins (card/quiet/banner) with
    # 21 phrases total (was 6): 12 card + 5 quiet + 4 banner. Original 5 English
    # + 1 Chinese preserved in "cta"
    # for backward compatibility — projects using static cta.heading configs
    # continue to work without migration.
    "cta": {
        "phrases": (
            "your next step",
            "where we can help",
            "work with us",
            "ready when you are",
            "talk to the factory",
            "下一步",
            "get started here",
            "the fastest way to fix this",
            "talk to a specialist",
            "see what we would find",
            "let us take a look",
            "here is what we would check first",
        ),
        "sibling_tags": ("p",),
        "css_class": "xr-cta-box",
    },
    "cta_quiet": {
        "phrases": (
            "worth a second look",
            "one more thing",
            "before you go",
            "a smaller ask",
            "if you want a second opinion",
        ),
        "sibling_tags": ("p",),
        "css_class": "xr-cta-box xr-cta-quiet",
    },
    "cta_banner": {
        "phrases": (
            "want this on your site",
            "ready to fix this together",
            "ready when you are to talk",
            "let us make this the last audit you need",
        ),
        "sibling_tags": ("p",),
        "css_class": "xr-cta-box xr-cta-banner",
    },
}

_SEPARATORS: Final[tuple[str, ...]] = (":", " -", " —", " –", "|")


def _normalize(text: str) -> str:
    """Heading text → matchable form: strip tags/anchors/entities/numbering, lower."""
    t = re.sub(r"<[^>]+>", "", text)
    t = ANCHOR_INLINE_RE.sub("", t)
    t = _html.unescape(t)
    t = re.sub(r"^\s*\d+[.)]\s*", "", t)
    return " ".join(t.split()).strip().lower()


def classify_heading(text: str) -> str | None:
    """Return the component_id a heading denotes, else None.

    Match rules per phrase p (all on normalized text t):
      * t == p                                   ("By the Numbers")
      * t startswith p + separator                ("By the Numbers: 2026 Costs")
      * t endswith " " + p                        ("This Week at a Glance")
    """
    t = _normalize(text)
    if not t:
        return None
    for comp_id, spec in COMPONENTS.items():
        for p in spec["phrases"]:
            if t == p:
                return comp_id
            if t.startswith(p) and t[len(p):len(p) + 2].strip()[:1] in {":", "-", "—", "–", "|"}:
                return comp_id
            if t.endswith(" " + p):
                return comp_id
    return None


def css_class_for(comp_id: str) -> str:
    return str(COMPONENTS[comp_id]["css_class"])


def sibling_tags_for(comp_id: str) -> tuple[str, ...]:
    return tuple(COMPONENTS[comp_id]["sibling_tags"])


# Rendered-HTML tagger (used by wp_publisher after markdown→HTML; regex is safe
# because the body is our own markdown-it output, not arbitrary HTML).
# Heading inner text is tempered ((?!</h[23]).)* — it must not cross ANY h2/h3
# closing tag. With a bare DOTALL (.*?), a heading whose immediate sibling is
# not in (ul|ol|p|table) (e.g. <h2>…</h2><blockquote>) made the engine
# backtrack h_text past the heading's own </h2> to the NEXT </h2> in the
# document; that giant failed-then-matched span consumed every heading inside
# it, so blocks that SHOULD be tagged (the 2026-08-08 project-alpha CTA, any
# component following such a section) were silently skipped (verify check 29).
_HEADING_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"(<h([23])\b[^>]*>)((?:(?!</h[23]).)*?)(</h\2>)(\s*)(<(ul|ol|p|table)\b)([^>]*>)",
    re.IGNORECASE | re.DOTALL,
)


def tag_component_blocks(html: str) -> str:
    """Add stable component classes to rendered heading-adjacent blocks.

    ``<h2>By the Numbers: 2026 Costs</h2><ul>`` → ``<ul class="xr-stat-grid">``
    Idempotent: an already-classed sibling is left untouched. Heading level h2 OR
    h3 both qualify (writers legitimately nest stat grids as h3 inside sections).
    """
    def _tag(m: "re.Match[str]") -> str:
        h_open, _lvl, h_text, h_close, gap, sib_open, sib_tag, sib_rest = (
            m.group(1), m.group(2), m.group(3), m.group(4), m.group(5),
            m.group(6), m.group(7), m.group(8),
        )
        comp_id = classify_heading(h_text)
        if not comp_id or sib_tag.lower() not in sibling_tags_for(comp_id):
            return m.group(0)
        cls = css_class_for(comp_id)
        if re.search(r'class\s*=', sib_rest):
            if cls in sib_rest:
                return m.group(0)
            new_rest = re.sub(r'class\s*=\s*"([^"]*)"', rf'class="\1 {cls}"', sib_rest, count=1)
        else:
            new_rest = f' class="{cls}"' + sib_rest
        return f"{h_open}{h_text}{h_close}{gap}{sib_open}{new_rest}"

    return _HEADING_BLOCK_RE.sub(_tag, html)
