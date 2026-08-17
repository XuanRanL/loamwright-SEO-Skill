"""scripts/wordpress/verify_post.py — Strong post-verification checks.

Replaces the inline 13-point string-match heuristic with structural HTML
parsing + cross-reference against the publisher's own output. Built after
the 2026-05-21 task 085fb1ba240c session surfaced THREE separate cases
where the original 13-point check returned PASS but the post was actually
broken:

  - `[IMAGE-SLOT-cover]` leaked as literal text in rendered HTML (the
    string-match for `class="project-charlie-pillar"` PASSED because the
    selector appears in the inline `<style>` block, not because the
    wrapper element was actually placed correctly).
  - The cover image was deduped to a stale prior-article media (wrong
    visual content), but the check only counted "WP image URLs present"
    without confirming the IDs match this run's media uploads.
  - The References HTML block was escaped to entities by markdown-it
    (`&lt;h2 id="references"&gt;`), but `class="article-signature"` was
    found via the same CSS-selector-in-style false positive.

This script does it right: parses the actual rendered HTML structurally
(regex/element-anchored checks, not a plain substring search), asserts
element presence not string match, and accepts optional cross-references
to a publisher-result JSON to confirm media-ID freshness (no stale-dedup
leak).

Usage:
    python -m scripts.wordpress.verify_post project-charlie 37146 \
        [--publish-result PATH]   # path to wp_publisher --json output
        [--workspace TASK_ID]     # alternative source for publish-result
        [--json]                  # machine-readable output

Exit codes:
    0 — all checks passed
    1 — one or more checks failed (post needs repair)
    2 — could not retrieve post (auth / network)
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Allow standalone invocation OR module-style
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.wordpress.wp_client import WPClient  # noqa: E402
from scripts._core import file_bus  # noqa: E402


# ─── Result types ────────────────────────────────────────────────────


@dataclass
class CheckResult:
    id: str
    label: str
    passed: bool
    detail: str = ""
    severity: str = "fail"   # 'fail' (must pass) | 'warn' (informational)


@dataclass
class VerifyResult:
    site_slug: str
    post_id: int
    post_status: str
    overall_pass: bool
    fail_count: int
    warn_count: int
    pass_count: int
    checks: list[CheckResult] = field(default_factory=list)
    preview_url: str = ""
    live_url: str = ""


# ─── Helpers ─────────────────────────────────────────────────────────


def _strip_inline_style_blocks(html: str) -> str:
    """Return HTML with <style>...</style> blocks removed.

    Used so string searches don't false-positive against CSS selectors
    that look like the body element they're supposed to detect (e.g.
    `.project-charlie-pillar` in inline <style> shouldn't satisfy a check
    for the body wrapper class).
    """
    return re.sub(r"<style\b[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)


def _strip_jsonld_scripts(html: str) -> str:
    """Return HTML with <script type=application/ld+json> blocks removed.

    Used so the count of `wp-image-NNN` references doesn't accidentally
    pick up image IDs that only appear inside JSON-LD schema metadata.
    """
    return re.sub(
        r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>.*?</script>',
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _body_html(rendered_html: str) -> str:
    """Return the HTML with style+jsonld stripped for body-content checks."""
    return _strip_jsonld_scripts(_strip_inline_style_blocks(rendered_html))


# ─── Individual checks ───────────────────────────────────────────────


def check_http_ok(post: dict | None) -> CheckResult:
    return CheckResult(
        id="01_rest_200",
        label="REST GET returned 200 and post payload",
        passed=bool(post),
    )


def check_wrapper_in_body(html: str, slug: str) -> CheckResult:
    """Wrapper class must appear as an actual element class, not just in CSS."""
    from scripts._core import style_tokens

    body = _body_html(html)
    cls = style_tokens.wrapper_class(slug)
    # Must appear as an element attribute, not in a CSS selector
    pat = rf'class=["\'](?:[^"\']*\s)?{re.escape(cls)}(?:\s[^"\']*)?["\']'
    present = bool(re.search(pat, body))
    return CheckResult(
        id="02_wrapper_class_in_body_element",
        label=f"class=\"{cls}\" present on an actual body element (not just in inline <style>)",
        passed=present,
        detail="" if present else f"no element with class={cls} found in body HTML (style block stripped before check)",
    )


def check_scoped_css_inline(html: str, slug: str) -> CheckResult:
    """The inline <style> block must contain at least one rule scoped to the wrapper."""
    from scripts._core import style_tokens

    style_blocks = re.findall(r"<style\b[^>]*>(.*?)</style>", html, flags=re.DOTALL | re.IGNORECASE)
    scope = f".{style_tokens.wrapper_class(slug)}"
    found = any(scope in s for s in style_blocks)
    return CheckResult(
        id="03_scoped_css_inline",
        label=f"inline <style> contains rules scoped to {scope}",
        passed=found,
    )


def check_image_count(html: str, min_count: int = 4, featured_set: bool = False) -> CheckResult:
    body = _body_html(html)
    count = len(re.findall(
        r"wp-content/uploads/[^\s\"'<>]+\.(?:png|jpe?g|webp|gif|svg|avif)",
        body, flags=re.IGNORECASE,
    ))
    # no_inline policy (e.g. weekly digest + WoodMart): the sole cover is the
    # featured image, theme-rendered at the top of the single-post page and NOT
    # present in REST content.rendered (this HTML). Body image count is then a
    # legitimate 0 while the post still renders exactly one real uploaded image.
    # Count the featured image toward the total ONLY when the body carries none,
    # so articles with inline body images are unaffected and can never over-count.
    # (2026-07-08 weekly-digest false-failure: cover-only digest failed 04 with 0
    # despite featured_media being correctly set — check 18 passed, check 04 did not.)
    featured_counted = 1 if (featured_set and count == 0) else 0
    count += featured_counted
    suffix = " (incl. theme-rendered featured image)" if featured_counted else ""
    return CheckResult(
        id="04_image_count",
        label=f"WP-uploaded images rendered (target ≥{min_count})",
        passed=count >= min_count,
        detail=f"counted {count} (target ≥{min_count}){suffix}",
    )


def check_no_placeholder_leakage(html: str) -> CheckResult:
    """No `[IMAGE-SLOT-...]` literal text should survive into rendered HTML.

    Caught the 2026-05-21 bug where the publisher's defensive is_featured
    skip left the cover placeholder as literal text in the body.
    """
    body = _body_html(html)
    leftovers = re.findall(r"\[IMAGE-SLOT-[^\]]+\]", body)
    return CheckResult(
        id="05_no_image_slot_placeholder_leak",
        label="no [IMAGE-SLOT-…] literal placeholders remain in body",
        passed=not leftovers,
        detail="" if not leftovers else f"leaked: {leftovers}",
    )


def check_no_escaped_html_leak(html: str) -> CheckResult:
    """L1 — Any `&lt;tagname` escape inside reader-visible body element text.

    Generalized 2026-05-21 from a 2-pattern allowlist (h2, p.article-signature)
    to a class-based detector. Scans <li> / <p> / <td> / <th> / <figcaption> /
    <blockquote> for `&lt;[a-z]+` literals that survive html=False escaping
    when a writer puts raw HTML tags inside markdown body text.

    See [[feedback_markdown_pitfalls_publisher_three_bugs]].

    2026-07-05 fix (two parts, both closing a Rule-11 fan-out gap where this
    check reimplemented render_lint.py's L1 detector with subtly different,
    independently-drifted logic):

    1. Excise <code>/<pre> spans before scanning, using the SAME `_CODE_SPAN_RE`
       pattern render_lint.py's L1 detector uses (imported, not reimplemented,
       so the two checks can never drift apart again). A markdown backtick code
       span like `` `<link rel="alternate" hreflang>` `` legitimately renders as
       `<code>&lt;link ...&gt;</code>` — that is correct, intentional display of
       a literal tag name, not a leak. Before this fix, render_lint (a
       pre-publish gate) correctly passed this content while THIS check failed
       the identical content on the live post, forcing an unnecessary manual
       rewrite of legitimate prose during the 2026-07-05 batch.
    2. Reuse render_lint.py's `_ESCAPED_TAG_RE` instead of this function's own,
       narrower `&lt;tag[\\s>/]` pattern. The local pattern required a RAW
       boundary character (space/>//) right after the tag name, so it silently
       missed a fully-escaped self-closing leak like `&lt;strong&gt;` (no raw
       boundary char exists — the closing `>` is ALSO escaped to `&gt;`).
       `_ESCAPED_TAG_RE` already accepts `&gt;` as a valid boundary and is the
       one render_lint actually ships with; importing it fixes a real
       false-negative (this check could not detect the exact "raw `<strong>`
       left in markdown" leak its own docstring says it exists to catch) and
       removes the second copy of the same contract.
    """
    from scripts.lint.render_lint import _CODE_SPAN_RE, _ESCAPED_TAG_RE

    body = _body_html(html)
    body_elem = re.compile(
        r"<(li|p|td|th|figcaption|blockquote|dd)\b[^>]*>(.*?)</\1>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    leaks: list[str] = []
    for m in body_elem.finditer(body):
        tag = m.group(1).lower()
        inner = _CODE_SPAN_RE.sub(" ", m.group(2))
        esc_m = _ESCAPED_TAG_RE.search(inner)
        if esc_m:
            sample = re.sub(r"\s+", " ", inner).strip()[:80]
            leaks.append(f"<{tag}> contains {esc_m.group(0)!r}: {sample!r}")
            if len(leaks) >= 3:
                break
    return CheckResult(
        id="06_no_escaped_html_leak",
        label="no &lt;tagname HTML escapes in body content (generic L1 leak detector)",
        passed=not leaks,
        detail="; ".join(leaks),
    )


def check_no_pandoc_anchor_leak(html: str) -> CheckResult:
    """L2 — Literal `{#anchor-id}` Pandoc syntax inside any heading text.

    Added 2026-05-21 after the 7w0gl0260521 incident where every H2 shipped
    with a visible `{#electrical-budget}` / `{#tco}` / etc. literal because
    markdown-it-py base doesn't parse the Pandoc attribute syntax.
    """
    body = _body_html(html)
    heading_re = re.compile(r"<(h[1-6])\b[^>]*>(.*?)</\1>", flags=re.IGNORECASE | re.DOTALL)
    leaks: list[str] = []
    for m in heading_re.finditer(body):
        tag = m.group(1).lower()
        inner_text = re.sub(r"<[^>]+>", "", m.group(2))
        leak = re.search(r"\{#[a-zA-Z0-9_-]+\}", inner_text)
        if leak:
            sample = re.sub(r"\s+", " ", inner_text).strip()[:80]
            leaks.append(f"<{tag}> has {leak.group(0)!r}: {sample!r}")
            if len(leaks) >= 3:
                break
    return CheckResult(
        id="19_no_pandoc_anchor_leak",
        label="no literal {#anchor-id} inside heading text (L2 — markdown-it base doesn't parse Pandoc)",
        passed=not leaks,
        detail="; ".join(leaks),
    )


def check_no_hand_rolled_srcset(html: str) -> CheckResult:
    """L4 — `<img srcset="...-NNNw.{ext}">` pattern points to files no pipeline code creates.

    Added 2026-05-21 after Bug 3. The publisher's image post-processor (mythical —
    never actually built) was referenced by srcset URL emission; every variant 404s.
    Fixed at source in `scripts/build/markdown_to_html.py` (default flipped + call site
    patched), this check is the defense-in-depth tripwire if either revert.
    """
    body = _body_html(html)
    pattern = re.compile(
        r'<img[^>]*srcset="[^"]*-\d+w\.(?:png|jpe?g|webp)',
        flags=re.IGNORECASE,
    )
    leaks: list[str] = []
    for m in pattern.finditer(body):
        sample = m.group(0)[:120]
        leaks.append(sample)
        if len(leaks) >= 3:
            break
    return CheckResult(
        id="20_no_hand_rolled_srcset",
        label="no hand-rolled <img srcset=...-NNNw.ext> (L4 — variants don't exist on disk)",
        passed=not leaks,
        detail="; ".join(leaks),
    )


def check_no_orphan_markdown_bold(html: str) -> CheckResult:
    """L3 — Odd `**` token count inside any body element ⇒ orphan marker.

    Catches the 2026-05-21 Bug 1 family: writer wrote `**<strong>X</strong>` with
    no closing `**`, markdown-it couldn't pair across the escaped raw HTML, so the
    `**` printed literally. Generalizes to any unbalanced bold marker.
    """
    body = _body_html(html)
    body_elem = re.compile(
        r"<(li|p|td|th|figcaption|blockquote|dd)\b[^>]*>(.*?)</\1>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    leaks: list[str] = []
    for m in body_elem.finditer(body):
        tag = m.group(1).lower()
        inner = m.group(2)
        # Skip <pre>/<code> contexts where `**` is intentional literal
        if re.search(r"<(pre|code)\b", inner, flags=re.IGNORECASE):
            continue
        n_markers = inner.count("**")
        if n_markers and n_markers % 2 != 0:
            sample = re.sub(r"<[^>]+>", "", inner)
            sample = re.sub(r"\s+", " ", sample).strip()[:80]
            leaks.append(f"<{tag}> has {n_markers} `**` (odd → orphan): {sample!r}")
            if len(leaks) >= 3:
                break
    return CheckResult(
        id="21_no_orphan_markdown_bold",
        label="no unbalanced `**` markdown-bold markers in body (L3 — odd count = orphan)",
        passed=not leaks,
        detail="; ".join(leaks),
    )


def check_expected_stages_recorded(
    task_id: str | None,
    expected_stages: tuple[str, ...] = ("wordpress-publisher",),
) -> CheckResult:
    """Audit 2026-05-22 — verify orchestration stages actually recorded execution.

    Reads memory/workspace/{task_id}/state.json::stage_history and checks that
    every expected stage has an entry with status='completed' (or 'in_progress'
    if the publish is mid-flight). Missing entries are flagged as informational
    warnings — these mean a stage was silently skipped (the bug class that
    produced the 2026-05-22 image-curator drift and the 3.3.3 schema-policy
    NameError).

    This is an INFORMATIONAL check, not a hard pass/fail — passing publish
    without `image-pipeline` recorded just means the project doesn't generate
    images. Only `wordpress-publisher` is treated as definitionally required.

    See references/orchestration/stage-tracking.md for the convention.
    """
    if not task_id:
        return CheckResult(
            id="26_expected_stages_recorded",
            label="orchestration stages recorded in state.json::stage_history",
            passed=True,  # can't check without workspace context
            detail="skipped (no --workspace task_id provided)",
        )
    try:
        # Lazy import — verify_post should still work if file_bus has issues
        from scripts._core import file_bus as _fb
        history = _fb.list_stages_run(task_id)
    except Exception as e:
        return CheckResult(
            id="26_expected_stages_recorded",
            label="orchestration stages recorded in state.json::stage_history",
            passed=False,
            detail=f"could not read stage_history: {e}",
        )

    if not history:
        return CheckResult(
            id="26_expected_stages_recorded",
            label="orchestration stages recorded in state.json::stage_history",
            passed=False,
            detail=(
                "EMPTY stage_history — orchestration never recorded any stage. "
                "Indicates either (a) the orchestrator skipped recording entirely "
                "OR (b) all stages crashed before completion. See "
                "references/orchestration/stage-tracking.md for the convention."
            ),
        )

    recorded_stages = {e.get("stage"): e.get("status") for e in history}
    missing = [s for s in expected_stages if s not in recorded_stages]
    if missing:
        return CheckResult(
            id="26_expected_stages_recorded",
            label="orchestration stages recorded in state.json::stage_history",
            passed=False,
            detail=(
                f"missing expected stages: {missing}. recorded so far: "
                f"{sorted(recorded_stages.keys())}. Either the stage truly "
                "wasn't invoked (silent skip = bug) OR the stage didn't call "
                "file_bus.record_stage_start (forgot the convention)."
            ),
        )

    failed_or_in_progress = [
        s for s in expected_stages
        if recorded_stages.get(s) in ("failed", "in_progress")
    ]
    return CheckResult(
        id="26_expected_stages_recorded",
        label="orchestration stages recorded in state.json::stage_history",
        passed=not failed_or_in_progress,
        detail=(
            f"all expected stages recorded: {sorted(expected_stages)} | "
            f"stage statuses: "
            + ", ".join(f"{k}={v}" for k, v in recorded_stages.items())
            + (
                f" | FAILED/STUCK: {failed_or_in_progress}"
                if failed_or_in_progress
                else ""
            )
        ),
    )


def check_geo_anchor_density(
    html: str,
    location_anchor: dict | None,
    title_text: str = "",
) -> CheckResult:
    """Check 27 (v5.0 Stage D, 2026-05-22) — verify location_anchor is densely
    referenced in body when state.brief.local_mode=true.

    Required occurrence:
        - H1 title: location's canonical OR name_full appears
        - At least 3 H2 headings reference the location
        - Body content: ≥ 10 mentions total (in any element)

    H1 source (2026-07-01 fix): the publisher converts with ``drop_h1=True``
    (WP renders the post TITLE as the page H1), so REST ``content.rendered``
    NEVER contains an ``<h1>`` — the old body-only scan made this sub-check
    structurally dead for every pipeline post (draft 818 false-failed 22/23
    with "Phoenix" in the title). The REST ``title.rendered`` passed via
    ``title_text`` IS the page H1; a body ``<h1>`` is only the fallback for
    ad-hoc content that carries its own.

    Failure here means the writer produced generic content without anchoring it
    to the location — a doorway-page risk AND a poor reader/SEO experience.

    Informational ("warn" status) when location_anchor.type == "near_me" since
    "near me" queries don't have a specific anchor to reference.
    """
    if not location_anchor:
        return CheckResult(
            id="27_geo_anchor_density",
            label="location_anchor referenced densely in body (H1 + ≥3 H2 + ≥10 body)",
            passed=True,
            detail="skipped (local_mode=false or no location_anchor)",
        )

    if location_anchor.get("type") == "near_me":
        return CheckResult(
            id="27_geo_anchor_density",
            label="location_anchor referenced densely in body",
            passed=True,
            detail="skipped (location_anchor.type=near_me — no specific anchor)",
            severity="warn",
        )

    canonical = location_anchor.get("canonical", "")
    name_full = location_anchor.get("name_full", "")
    containing_state = location_anchor.get("containing_state", "")

    # All forms to check. Short code forms (ON, BC, IN, OR, …) must match
    # CASE-SENSITIVELY — v3.40.0 fix: with global anchors, containing_state="ON"
    # under IGNORECASE matched every English "on" and made this check a fake
    # gate (same latent bug existed for US collision codes IN/OR).
    forms = [f for f in (canonical, name_full, containing_state) if f]
    if not forms:
        return CheckResult(
            id="27_geo_anchor_density",
            label="location_anchor referenced densely in body",
            passed=False,
            detail="location_anchor has no canonical/name_full to check against",
        )

    def _form_hits(form: str, text: str) -> int:
        flags = 0 if len(form) <= 3 else re.IGNORECASE
        return len(re.findall(rf"\b{re.escape(form)}\b", text, flags))

    body = _body_html(html)

    # H1 check — the REST title is the theme-rendered H1 (drop_h1=True publisher
    # invariant); fall back to a literal body <h1> only when no title was passed.
    h1_text = title_text or ""
    if not h1_text:
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", body, flags=re.IGNORECASE | re.DOTALL)
        if h1_match:
            h1_text = h1_match.group(1)
    h1_has_loc = bool(h1_text) and any(_form_hits(f, h1_text) for f in forms)

    # H2 count
    h2_matches = re.findall(r"<h2[^>]*>(.*?)</h2>", body, flags=re.IGNORECASE | re.DOTALL)
    h2_with_loc = sum(
        1 for h in h2_matches if any(_form_hits(f, h) for f in forms)
    )

    # Body count (in any element; loose)
    total_count = 0
    for f in forms:
        total_count += _form_hits(f, body)

    # Verdict
    h1_ok = h1_has_loc
    h2_ok = h2_with_loc >= 3
    body_ok = total_count >= 10

    passed = h1_ok and h2_ok and body_ok
    failures = []
    if not h1_ok:
        failures.append("H1 missing location")
    if not h2_ok:
        failures.append(f"only {h2_with_loc}/3 required H2s reference location")
    if not body_ok:
        failures.append(f"only {total_count}/10 required body mentions")

    return CheckResult(
        id="27_geo_anchor_density",
        label="location_anchor referenced densely (H1 + ≥3 H2 + ≥10 body)",
        passed=passed,
        detail=(
            f"H1={'✓' if h1_ok else '✗'}, "
            f"H2={h2_with_loc}/3, "
            f"body={total_count}/10. "
            + ("; ".join(failures) if failures else "All thresholds met.")
        ),
    )


def check_no_claim_marker_leak(html: str) -> CheckResult:
    """L5 — Unresolved `[claim:cN_section_id]` writer-emitted markers in body.

    Added 2026-05-22 after the b03255396849 task shipped 40 raw markers to live
    in post 37193. Writers emit `[claim:c1_abstract]` style markers; the
    fact-check-and-citation + assembly pipeline is supposed to swap them for
    `(Author, Year)` APA in-text citations. A leak means those stages were
    silently skipped (which is the silent-default for the legacy orchestrator).

    Defense layer 3 of 3 (L1=wp_publisher._apply_in_text_citations,
    L2=render_lint detect_L5_claim_marker_leak, L3=this check). See
    feedback_claim_marker_leak_systemic.md.
    """
    body = _body_html(html)
    pattern = re.compile(
        r"\[claim:[a-z0-9_]+(?:\s*,\s*c[0-9]+_[a-z0-9_]+)*\]",
        flags=re.IGNORECASE,
    )
    leaks: list[str] = []
    for m in pattern.finditer(body):
        leaks.append(m.group(0)[:120])
        if len(leaks) >= 5:
            break
    ok = not leaks
    return CheckResult(
        id="22_no_claim_marker_leak",
        label="no unresolved [claim:cN_section] markers in body (L5 — fact-check + assembly never swapped to APA inline)",
        passed=ok,
        detail=("first leaks: " + "; ".join(leaks)) if leaks else "",
    )


def check_references_h2_real(html: str) -> CheckResult:
    """References H2 must be an actual element, not just a string occurrence."""
    body = _body_html(html)
    has_h2 = bool(re.search(
        r'<h2[^>]*(?:id=["\']references["\'])?[^>]*>\s*References\s*</h2>',
        body, flags=re.IGNORECASE,
    ))
    return CheckResult(
        id="09_h2_references_element",
        label="<h2>References</h2> is an actual element in body",
        passed=has_h2,
    )


def check_references_ol_followed(html: str, min_li: int = 3) -> CheckResult:
    """An <ol> with ≥min_li <li> entries must follow the References H2."""
    body = _body_html(html)
    m = re.search(
        r'<h2[^>]*>\s*References\s*</h2>(.*?)(?:<h2[^>]|\Z)',
        body, flags=re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return CheckResult(
            id="10_references_ol_count",
            label=f"<ol> with ≥{min_li} link-resolvable <li> follows References H2",
            passed=False,
            detail="no References H2 found to anchor the OL search",
        )
    section = m.group(1)
    ol_m = re.search(r'<ol\b[^>]*>(.*?)</ol>', section, flags=re.DOTALL | re.IGNORECASE)
    if not ol_m:
        return CheckResult(
            id="10_references_ol_count",
            label=f"<ol> with ≥{min_li} link-resolvable <li> follows References H2",
            passed=False,
            detail="no <ol> found after References H2",
        )
    li_count = len(re.findall(r'<li\b', ol_m.group(1)))
    has_links = '<a ' in ol_m.group(1).lower() or '<a\t' in ol_m.group(1).lower()
    ok = li_count >= min_li and has_links
    return CheckResult(
        id="10_references_ol_count",
        label=f"<ol> with ≥{min_li} link-resolvable <li> follows References H2",
        passed=ok,
        detail=f"found {li_count} <li>, has <a> links: {has_links}",
    )


def check_article_signature_real(html: str, site_slug: str = "") -> CheckResult:
    """The signature <p> must be an actual element in body (token-resolved)."""
    from scripts._core import style_tokens

    body = _body_html(html)
    cls = style_tokens.class_for(site_slug, "article-signature") if site_slug else "article-signature"
    def _has(c: str) -> bool:
        return bool(re.search(
            rf'<p[^>]*class=["\'](?:[^"\']*\s)?{re.escape(c)}(?:\s[^"\']*)?["\']',
            body, flags=re.IGNORECASE,
        ))
    has_p = _has(cls)
    detail = ""
    if not has_p and cls != "article-signature" and _has("article-signature"):
        detail = "legacy 'article-signature' found — post predates style-token migration (run reinject_style_tokens)"
    return CheckResult(
        id="11_article_signature_element",
        label=f"<p class='{cls}'> is an actual element in body",
        passed=has_p,
        detail=detail,
    )


def check_status(post: dict, expected: str | None = None) -> CheckResult:
    status = post.get("status", "")
    if expected:
        return CheckResult(
            id="12_status",
            label=f"status == {expected}",
            passed=(status == expected),
            detail=f"actual: {status}",
        )
    return CheckResult(
        id="12_status",
        label="status is one of {draft, publish, private}",
        passed=status in ("draft", "publish", "private"),
        detail=f"actual: {status}",
    )


def check_categories_not_uncategorized(post: dict) -> CheckResult:
    cats = post.get("categories") or []
    ok = bool(cats) and cats != [1]
    return CheckResult(
        id="13_categories_resolved",
        label="categories not [Uncategorized=1] only",
        passed=ok,
        detail=f"got {cats}",
    )


def check_rankmath_meta(post: dict, expect_robots_index: bool = True, head_html: str | None = None) -> CheckResult:
    """Verify RankMath meta is correctly EMITTED in the rendered head (the SEO-relevant signal).

    2026-05-21 refactor: previously checked `post.meta.rank_math_*` from REST. That field is
    sometimes empty even when RankMath is working correctly — the WP-REST `meta` exposure
    depends on the MU bridge plugin's auth_callback returning truthy, AND the keys being
    explicitly registered with `show_in_rest=true`. If the bridge is misconfigured, every
    post fails the check despite RankMath rendering perfect <title>/<meta>/<link> in <head>.

    What actually matters for SEO: does the rendered <head> have a proper <title>, meta
    description, canonical link, and robots meta? Those are the signals Google reads, not
    the WP-REST meta-key exposure.

    Resolution order:
      1. If head_html is provided, scan it for <title>, <meta name="description">,
         <link rel="canonical">, <meta name="robots"> — pass if all present
      2. Fall back to REST meta check (legacy behavior for backward compat)
    """
    issues = []
    if head_html:
        # Primary path: verify rendered head
        title_m = re.search(r'<title>([^<]+)</title>', head_html)
        if not title_m or not title_m.group(1).strip():
            issues.append("<title> missing or empty in rendered head")
        canonical_m = re.search(r'<link\s+rel=["\']canonical["\']\s+href=["\']([^"\']+)["\']', head_html)
        if not canonical_m:
            issues.append("<link rel='canonical'> missing in rendered head")
        desc_m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', head_html)
        if not desc_m or not desc_m.group(1).strip():
            issues.append("<meta name='description'> missing or empty")
        if expect_robots_index:
            robots_m = re.search(r'<meta\s+name=["\']robots["\']\s+content=["\']([^"\']+)["\']', head_html)
            robots_content = robots_m.group(1) if robots_m else ""
            if "noindex" in robots_content:
                issues.append(f"robots meta has noindex (got: {robots_content!r})")
            # Note: many SEO setups omit "index" word since it's the default;
            # only fail if explicit noindex is present.
        detail = f"rendered head check — {'; '.join(issues) if issues else 'title/canonical/description/robots all present'}"
    else:
        # Fallback: legacy REST meta check
        meta = post.get("meta", {})
        if not meta.get("rank_math_title"):
            issues.append("rank_math_title missing in REST meta")
        if not meta.get("rank_math_canonical_url"):
            issues.append("rank_math_canonical_url missing in REST meta")
        if not meta.get("rank_math_focus_keyword"):
            issues.append("rank_math_focus_keyword missing in REST meta")
        if expect_robots_index:
            robots = meta.get("rank_math_robots") or []
            if "index" not in robots:
                issues.append(f"rank_math_robots missing 'index' (got {robots}) in REST meta")
        detail = f"REST meta check (no head fetched — draft post) — {'; '.join(issues) if issues else 'all set'}"
    return CheckResult(
        id="07_rankmath_meta",
        label="RankMath meta correctly emitted (rendered head: title + canonical + description + robots)",
        passed=not issues,
        detail=detail,
    )


def _fetch_live_head(post: dict, wp) -> str | None:
    """Fetch the rendered live page and return only the <head> section as a string.

    Returns None if:
      - post status is not 'publish' (preview URL requires login session, not just app password)
      - the live URL is empty
      - the live URL returns non-200

    Uses cache-buster query string to bypass FlyingPress / Cloudflare edge cache so the
    verification reflects the freshest schema (e.g. RankMath setting toggles that just landed).
    Carries the Cloudflare bypass header from the WP client if configured.
    """
    import time
    live_url = post.get("link") or ""
    status = post.get("status", "")
    if not live_url or status != "publish":
        return None
    headers = {"User-Agent": "xuanran-seo-verify/3.3.2"}
    # Reuse the WP client's CF bypass token if loaded (respect per-project header name)
    cf_token = getattr(wp, "_cf_bypass_token", None)
    cf_header = "X-Xuanran-SEO-Token"
    if cf_token is None:
        try:
            from scripts.wordpress.wp_client import _load_cf_bypass_token
            cf_token, cf_header = _load_cf_bypass_token(wp.site_slug)
        except Exception:
            cf_token = None
    if cf_token:
        headers[cf_header] = cf_token
    # Cache-buster forces FlyingPress to bypass its disk cache
    bust_url = f"{live_url}{'&' if '?' in live_url else '?'}_v={int(time.time())}"
    try:
        import httpx
        r = httpx.get(bust_url, headers=headers, timeout=30, follow_redirects=True)
        if r.status_code != 200:
            return None
        html = r.text
        head_end = html.find("</head>")
        return html[:head_end] if head_end > 0 else None
    except Exception:
        return None


def _extract_jsonld_types(html_region: str) -> tuple[int, set[str]]:
    """Return (block_count, type_set) for one HTML region (head or body).

    Handles three common JSON-LD shapes:
      (a) `{"@type": "X", ...}` — single object
      (b) `{"@graph": [{"@type": "X"}, {"@type": "Y"}]}` — RankMath / Yoast pattern
      (c) `[{"@type": "X"}, ...]` — bare array
    """
    blocks = re.findall(
        r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_region, flags=re.DOTALL | re.IGNORECASE,
    )
    types: set[str] = set()
    for s in blocks:
        try:
            parsed = json.loads(s.strip())
        except Exception:
            continue
        # Walk @graph or top-level
        items: list = []
        if isinstance(parsed, dict):
            if "@graph" in parsed and isinstance(parsed["@graph"], list):
                items = parsed["@graph"]
            else:
                items = [parsed]
        elif isinstance(parsed, list):
            items = parsed
        for it in items:
            if isinstance(it, dict) and "@type" in it:
                t = it["@type"]
                if isinstance(t, list):
                    types.update(t)
                else:
                    types.add(t)
    return len(blocks), types


def check_jsonld_schemas(
    body_html: str,
    *,
    head_html: str | None = None,
    min_total_blocks: int = 2,
    require_types: list[str] | None = None,
) -> CheckResult:
    """Scan both <head> and <body> for JSON-LD; require_types satisfied if ANY context has it.

    2026-05-21 fix: previously only scanned `body_html` (the WP REST `content.rendered`
    field), which silently missed RankMath / Yoast's head schema. Result: misleading
    false-alarms on posts where the SEO plugin handled BlogPosting + Organization +
    Person + WebPage + WebSite + ImageObject + BreadcrumbList in head, and the
    publisher only added supplementals (FAQPage / ItemList / etc.) in body. This
    refactor scans both contexts and reports them separately for diagnosis.

    Args:
      body_html: Rendered post content (WP REST `content.rendered`).
      head_html: Full HTML <head> section, fetched separately from the live URL
                 (None for drafts where live URL isn't accessible).
      min_total_blocks: Minimum head+body block count combined.
      require_types: List of @type values that must appear in head OR body.
    """
    require_types = require_types or []
    head_count, head_types = (0, set()) if head_html is None else _extract_jsonld_types(head_html)
    body_count, body_types = _extract_jsonld_types(body_html)
    all_types = head_types | body_types
    total_blocks = head_count + body_count
    missing = [t for t in require_types if t not in all_types]
    ok = total_blocks >= min_total_blocks and not missing
    head_summary = "(head not fetched)" if head_html is None else f"head={head_count}b types={sorted(head_types)}"
    detail = (
        f"{head_summary} | body={body_count}b types={sorted(body_types)}"
        + (f" | missing={missing}" if missing else "")
    )
    return CheckResult(
        id="17_jsonld_blocks",
        label=f"≥{min_total_blocks} JSON-LD blocks (head+body); required types: {require_types or 'none'}",
        passed=ok,
        detail=detail,
    )


def check_media_fresh_no_dedup(post: dict, publish_result: dict | None) -> CheckResult:
    """If a publish-result is provided, the post's image URLs must reference
    media IDs that came from THIS run's upload (not deduped to prior-article
    media). Catches the 2026-05-21 stale-cover bug.
    """
    if not publish_result:
        return CheckResult(
            id="15_no_stale_dedup",
            label="all images in body match this run's uploaded media_ids (publish-result cross-reference)",
            passed=True,
            severity="warn",
            detail="(skipped — no publish-result.json provided)",
        )
    rendered = post.get("content", {}).get("rendered", "")
    body = _body_html(rendered)
    ids_in_body = set(int(x) for x in re.findall(r"wp-image-(\d+)", body))
    expected_ids = set(publish_result.get("media_ids") or [])
    featured_id = publish_result.get("featured_media_id")
    if featured_id:
        expected_ids.add(int(featured_id))
    stale = ids_in_body - expected_ids - {0}
    if stale:
        return CheckResult(
            id="15_no_stale_dedup",
            label="all images in body match this run's uploaded media_ids",
            passed=False,
            detail=f"body references unexpected media IDs (likely stale dedup): {sorted(stale)}; expected from this run: {sorted(expected_ids)}",
        )
    return CheckResult(
        id="15_no_stale_dedup",
        label="all images in body match this run's uploaded media_ids",
        passed=True,
    )


def check_featured_media_set(post: dict) -> CheckResult:
    fm = post.get("featured_media") or 0
    return CheckResult(
        id="18_featured_media",
        label="featured_media is set (non-zero)",
        passed=fm > 0,
        detail=f"featured_media={fm}",
    )


def check_keyword_density(html: str, primary_keyword: str | None,
                          hard_max_pct: float = 1.5,
                          informational_min_pct: float = 0.4) -> CheckResult:
    """Soft-gate density check: hard-fail ONLY above hard_max_pct (1.5%
    default = over-optimization); warn below informational_min_pct (0.4%
    default = under-optimized but not a publish blocker).

    Policy rationale (Moz 2025 evidence in references/seo/citation-capsules-princeton.md):
      - Density >1.3% costs 4.2 ranking positions on average
      - Density >2% triggers spam filters
      - Density <0.8% has NO documented penalty (Google's BERT/MUM handles
        semantic variants — "1000W LED grow lamp" ≈ "1000W LED grow light")

    So the asymmetric policy: hard veto only at the upper end; under-optimization
    is informational only. Reflects the actual asymmetry of the SERP penalty curve.
    """
    if not primary_keyword:
        return CheckResult(
            id="16_keyword_density",
            label="primary keyword density (soft-gate: hard-fail >1.5% only)",
            passed=True, severity="warn",
            detail="(skipped — no --primary-keyword provided)",
        )
    # Strip HTML tags + style/script to count only visible body text
    plain = _body_html(html)
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = re.sub(r"&[a-z]+;|&#\d+;", " ", plain)  # entities
    words = re.findall(r"\b\w+\b", plain, flags=re.UNICODE)
    total = len(words)
    if total == 0:
        return CheckResult(
            id="16_keyword_density",
            label="primary keyword density (soft-gate: hard-fail >1.5% only)",
            passed=False, detail="no body words counted",
        )
    # Match the same plural-aware whole-word pattern as scripts/lint/keyword_density.py
    parts = primary_keyword.strip().split()
    if not parts:
        return CheckResult(
            id="16_keyword_density",
            label="primary keyword density (soft-gate: hard-fail >1.5% only)",
            passed=False, detail="empty primary keyword",
        )
    head = " ".join(re.escape(p) for p in parts[:-1])
    last = re.escape(parts[-1])
    pattern = (rf"\b{head}\s+{last}(?:s|es)?\b" if head else rf"\b{last}(?:s|es)?\b")
    count = len(re.findall(pattern, plain, flags=re.IGNORECASE))
    density_pct = round(count / total * 100, 3) if total > 0 else 0

    if density_pct > hard_max_pct:
        return CheckResult(
            id="16_keyword_density",
            label=f"primary keyword density (hard veto >{hard_max_pct}%, target 0.5-1.0%)",
            passed=False, severity="fail",
            detail=f"density={density_pct}% (count={count} / {total} words) — OVER-OPTIMIZED. Edit to ≤1.5% before publish.",
        )
    if density_pct < informational_min_pct:
        return CheckResult(
            id="16_keyword_density",
            label=f"primary keyword density (soft warning <{informational_min_pct}%)",
            passed=True, severity="warn",
            detail=f"density={density_pct}% (count={count} / {total} words) — under target band 0.5-1.0%. Not a publish blocker; Google's BERT handles semantic variants. Consider lifting on next edit for stronger exact-match signal.",
        )
    return CheckResult(
        id="16_keyword_density",
        label="primary keyword density within soft target band",
        passed=True,
        detail=f"density={density_pct}% (count={count} / {total} words) — within target",
    )


def check_no_competitor_domain_links(html: str, site_slug: str) -> CheckResult:
    """Check 28 — no competitor/peer domain appears as a cited source on the LIVE page.

    Scans rendered HTML (anchors + bare URLs in the References list, body links,
    and any inline JSON-LD) against the project's
    citation_source_policy.do_not_cite_domains via competitor_domains.py. This is
    the final, post-publish line of defense (root CLAUDE.md Rule 8). When the
    project has no policy, the check is skipped (PASS) — backward compatible.
    """
    cid, label = "28_no_competitor_links", "no competitor/peer domain cited as a source"
    try:
        from scripts._core import competitor_domains as cd
        policy = cd.load_policy(site_slug)
    except Exception as e:  # never let the guard crash verification
        return CheckResult(id=cid, label=label, passed=True, severity="warn",
                           detail=f"competitor policy load failed (non-blocking): {e}")
    if not policy.enabled:
        return CheckResult(id=cid, label=label, passed=True,
                           detail="no citation_source_policy for this project (skipped)")
    hits = policy.find_blocked_in_html(html)
    if hits:
        shown = ", ".join(sorted({d for (_u, d) in hits}))
        sample = "; ".join(u for (u, _d) in hits[:3])
        return CheckResult(
            id=cid, label=label, passed=False,
            detail=f"{len(hits)} competitor-domain link(s) on live page ({shown}). "
                   f"e.g. {sample}. Re-source to a neutral authority or remove "
                   f"(citation_source_policy / root CLAUDE.md Rule 8).",
        )
    return CheckResult(id=cid, label=label, passed=True,
                       detail=f"clean — scanned against {len(policy.domains)} blocked domain(s)")


# WooCommerce renders a `[products ...]` shortcode into a product grid whose
# markup carries one of these markers (tolerant any-of, per Task 5): the classic
# shortcode loop emits `<ul class="products columns-N">`, the block editor emits
# `wc-block-grid` (or the deprecated `wc-block-grid__products` wrapper), and the
# shortcode's own wrapper div carries `class="woocommerce columns-N"`. Every
# alternative below is a GRID indicator specifically — NOT bare site chrome.
#
# v3.38.1 hardening (Finding 1, probe-proven): a bare `woocommerce` token is
# NOT an alternative here anymore. Every real WooCommerce site carries that
# token site-wide regardless of whether any particular shortcode rendered
# anything — body class `woocommerce-active`, the header cart widget, `<link
# id="woocommerce-general-css">` — so the old bare-token check false-PASSED
# an EMPTY product grid (shortcode expanded to nothing, e.g. an empty/
# out-of-stock category). `woocommerce\s+columns-` requires the token to be
# immediately followed by whitespace then `columns-`, which only the grid
# wrapper's own class attribute produces (chrome tokens like
# `woocommerce-active` / `woocommerce-general-css` are hyphen-joined, not
# whitespace-joined, so they don't match).
_WOOCOMMERCE_GRID_RE = re.compile(
    r'wc-block-grid'
    r'|class=["\'](?:[^"\']*\s)?products\b'
    r'|woocommerce\s+columns-',
    flags=re.IGNORECASE,
)


def _post_cta_window(body: str, cta_class: str = "xr-cta-box") -> str | None:
    """Return the substring of `body` starting at the first CTA-tagged
    paragraph, or None if no such paragraph is found (Finding 1, v3.38.1).

    Site-wide WooCommerce chrome (body class, header cart widget, stylesheet
    `<link>`) makes a bare `woocommerce` token appear on EVERY page of a real
    WooCommerce site regardless of whether the CTA's own product grid actually
    rendered — and a related-products widget elsewhere on the page can carry
    real grid markup that has nothing to do with this CTA. Scoping the grid
    search to content AT/AFTER the CTA paragraph excludes both: the grid the
    shortcode produces renders immediately after the CTA's intro paragraph
    (see cta_injector._build_block), so anything before that offset is either
    chrome or an unrelated widget, not evidence this shortcode expanded.
    Callers only reach this when the tagged-block count check above already
    confirmed at least one `xr-cta-box` exists, so None is not expected in
    practice — callers must still handle it defensively.
    """
    m = re.search(
        rf'<p[^>]*class=["\'](?:[^"\']*\s)?{re.escape(cta_class)}(?:\s[^"\']*)?["\']',
        body, flags=re.IGNORECASE,
    )
    if not m:
        return None
    return body[m.start():]


def _extract_cta_hrefs(body_html: str, cta_class: str = "xr-cta-box") -> list[str]:
    """Every href inside a tagged CTA <p> block, in document order."""
    hrefs = []
    for p_match in re.finditer(
        rf'<p[^>]*class=["\'](?:[^"\']*\s)?{re.escape(cta_class)}(?:\s[^"\']*)?["\'][^>]*>(.*?)</p>',
        body_html, flags=re.IGNORECASE | re.DOTALL,
    ):
        for href_match in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\']', p_match.group(1)):
            hrefs.append(href_match.group(1))
    return hrefs


def _cta_url_matches_brief(hrefs: list[str], expected_url: str | None) -> bool:
    if not expected_url or not hrefs:
        return False
    return any(h.rstrip("/") == expected_url.rstrip("/") for h in hrefs)


def _plain_text(fragment: str) -> str:
    """Tag-strip + entity-unescape + whitespace-collapse + casefold, for
    content-identity comparison between authored CTA copy and rendered HTML."""
    import html as _html

    txt = re.sub(r"<[^>]+>", " ", fragment)
    txt = _html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip().casefold()


def _markdown_to_plain(md: str) -> str:
    """Markdown CTA copy → the plain text WordPress renders: drop bold markers,
    reduce links to their anchor text, then normalize like _plain_text."""
    txt = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md)
    txt = txt.replace("**", "")
    return re.sub(r"\s+", " ", txt).strip().casefold()


def check_cta_not_duplicated(html: str, workspace_task_id: str | None) -> CheckResult:
    """Check 30 — the CTA content appears at most ONCE per registered placement
    on the live page (2026-08-17).

    Why check 29 alone is not enough: it counts TOKEN-TAGGED blocks (>= applied),
    so it is structurally blind to an extra UNTAGGED copy. Found live on post
    38418: a mid-repair heading rename made the injected block invisible to the
    injector's classification-based idempotency, the driver re-injected, and the
    page shipped with the identical paragraph + WooCommerce grid twice — one
    styled, one bare — while checks 29/visual-density stayed green. This check
    keys on CONTENT identity (the registered cta-draft.json copy), which no
    rename can hide."""
    cid, label = "30_cta_not_duplicated", "CTA content not duplicated on the live page"
    if not workspace_task_id:
        return CheckResult(id=cid, label=label, passed=True,
                           detail="no workspace given (skipped)")
    try:
        draft_path = (Path(__file__).resolve().parents[2]
                      / "memory" / "workspace" / workspace_task_id / "cta-draft.json")
        if not draft_path.exists():
            return CheckResult(id=cid, label=label, passed=True,
                               detail="no cta-draft.json (skipped)")
        blocks = json.loads(draft_path.read_text(encoding="utf-8")).get("blocks") or {}
    except Exception as e:  # unreadable artifact is not a live-page verdict
        return CheckResult(id=cid, label=label, passed=True, severity="warn",
                           detail=f"cta-draft.json unreadable (non-blocking): {e}")
    if not isinstance(blocks, dict) or not blocks:
        return CheckResult(id=cid, label=label, passed=True,
                           detail="no registered CTA blocks (skipped)")

    haystack = _plain_text(_body_html(html))
    dupes: list[str] = []
    for placement, blk in blocks.items():
        if not isinstance(blk, dict):
            continue
        needle = _markdown_to_plain(str(blk.get("text") or ""))[:160]
        if len(needle) < 40:  # too short to be a reliable identity
            continue
        n = haystack.count(needle)
        if n > 1:
            dupes.append(f"placement '{placement}': copy appears {n}× (expected 1)")
    if dupes:
        return CheckResult(
            id=cid, label=label, passed=False,
            detail="; ".join(dupes) + " — a duplicate CTA block is live (one copy is "
                   "likely under a renamed/untagged heading). Delete the unregistered "
                   "copy from draft.md, re-publish, re-verify.",
        )
    return CheckResult(id=cid, label=label, passed=True,
                       detail=f"{len(blocks)} registered placement(s), no content duplication")


def check_cta_module_rendered(html: str, workspace_task_id: str | None,
                              site_slug: str = "") -> CheckResult:
    """Check 29 — the designed CTA module is class-tagged on the live page (v3.34).

    The cta-injection stage wrote `### {heading}` + a paragraph; wp_publisher's
    component tagger (scripts/_core/component_headings, id 'cta') must have turned
    that into `<p class="xr-cta-box">`. A 200 page whose CTA lost its class is a
    silent failure of the same family as Rule 2's unwrapped CSS. Skipped (PASS)
    when the workspace has no cta result or applied no placements."""
    from scripts._core import style_tokens

    cta_cls = style_tokens.class_for(site_slug, "xr-cta-box") if site_slug else "xr-cta-box"
    cid, label = "29_cta_module_rendered", f"CTA module rendered with class={cta_cls}"
    if not workspace_task_id:
        return CheckResult(id=cid, label=label, passed=True,
                           detail="no workspace given (skipped)")
    try:
        result_path = (Path(__file__).resolve().parents[2]
                       / "memory" / "workspace" / workspace_task_id
                       / "cta-injection-result.json")
        if not result_path.exists():
            return CheckResult(id=cid, label=label, passed=True,
                               detail="no cta-injection-result.json (stage predates v3.34 or never ran — skipped)")
        data = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as e:  # never let the guard crash verification
        return CheckResult(id=cid, label=label, passed=True, severity="warn",
                           detail=f"cta result unreadable (non-blocking): {e}")
    # Defense in depth (2026-07-08): `placements_applied` is derived by
    # re-classifying the post-injection body — a classification gap (the v3.38.0
    # cta_banner/cta_quiet skin-id miss) left it [] even though a CTA WAS
    # injected, and this check then silently skipped while a duplicated CTA
    # shipped. `newly_injected` is written unconditionally at injection time, so
    # union both: if EITHER says a CTA went in, this check must verify it.
    applied = (data.get("placements_applied") or []) or (data.get("newly_injected") or [])
    if not data.get("enabled") or not applied:
        return CheckResult(id=cid, label=label, passed=True,
                           detail="cta disabled or no placements applied (skipped)")
    body = _body_html(html)
    tagged = len(re.findall(
        rf'<p[^>]*class=["\'](?:[^"\']*\s)?{re.escape(cta_cls)}(?:\s[^"\']*)?["\']',
        body, flags=re.IGNORECASE,
    ))
    if tagged < len(applied):
        return CheckResult(
            id=cid, label=label, passed=False,
            detail=f"cta-injection applied {applied} but only {tagged} <p class='{cta_cls}'> "
                   f"found in rendered body — heading not classified (check "
                   f"scripts/_core/component_headings COMPONENTS['cta']) or block stripped at publish.",
        )

    # Brief-driven sub-checks (v3.37/v3.38): if this article used the new
    # cta-brief.json path, run the brief-specific enforcement. A missing or
    # unparseable brief degrades to the plain "tagged CTA rendered" pass below.
    brief_path = (Path(__file__).resolve().parents[2]
                  / "memory" / "workspace" / workspace_task_id / "cta-brief.json")
    if brief_path.exists():
        try:
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
        except Exception:
            brief = None
        if isinstance(brief, dict):
            # ── ecommerce shortcode sub-check (v3.38.0) ──────────────────────
            # When the brief resolved a WooCommerce products shortcode, the live
            # page must NOT still contain the literal `[products` (unexpanded =
            # broken) and MUST carry the product-grid markup WooCommerce emits.
            # Runs only when a non-null shortcode is present; a fallback-mode
            # brief (null shortcode) skips straight to the target_url sub-check.
            rp = brief.get("resolved_products")
            shortcode = rp.get("shortcode") if isinstance(rp, dict) else None
            shortcode_present = isinstance(shortcode, str) and bool(shortcode.strip())
            if shortcode_present:
                # Scope BOTH sub-checks to content AT/AFTER the CTA paragraph
                # (Finding 1, v3.38.1) — see _post_cta_window. Falls back to the
                # whole body only in the practically-unreachable case where no
                # xr-cta-box was found (the `tagged < len(applied)` gate above
                # already fails first whenever that's true).
                window = _post_cta_window(body, cta_cls)
                if window is None:
                    window = body
                if "[products" in window:
                    return CheckResult(
                        id=cid, label=label, passed=False,
                        detail="cta-brief.json resolved a WooCommerce [products ...] shortcode "
                               "but the LITERAL '[products' text is still present in the rendered "
                               "body at/after the CTA — the shortcode never expanded (WooCommerce "
                               "inactive, or the shortcode was HTML-escaped/wrapped/placed inline "
                               "in a <p> at publish). The product grid IS the ecommerce CTA's "
                               "conversion element; an unexpanded shortcode ships nothing.",
                    )
                if not _WOOCOMMERCE_GRID_RE.search(window):
                    return CheckResult(
                        id=cid, label=label, passed=False,
                        detail="cta-brief.json resolved a WooCommerce [products ...] shortcode but "
                               "no product-grid markup (class=\"products\" / wc-block-grid / "
                               "woocommerce columns-N) was found in the rendered body at/after the "
                               "CTA — the shortcode expanded to nothing (empty/out-of-stock "
                               "category, or a WooCommerce error). Site-wide WooCommerce chrome "
                               "elsewhere on the page does not count (scoped to post-CTA content).",
                    )

            # ── URL-correctness sub-check (v3.37) — applies only when set ─────
            # confirm the rendered link points at the service the brief resolved.
            # target_url is null for catalog-category ecommerce briefs (no
            # permalink), so this sub-check simply does not run there. Belt
            # and suspenders (v3.38 review, defense-in-depth): even if a
            # future brief-shape drift ever wrote a non-null target_url
            # alongside a resolved shortcode, this sub-check must NOT run —
            # a shortcode-bearing CTA renders a product grid with no href by
            # design, and a resolved_products.shortcode always wins.
            expected_url = brief.get("target_url")
            if expected_url is not None and not isinstance(expected_url, str):
                # cta_brief_builder.py performs no schema validation before writing
                # target_url — it's a straight passthrough from business-context.json.
                # A non-string value (e.g. an int) would crash _cta_url_matches_brief's
                # .rstrip("/") call. Never let the guard crash verification: degrade
                # this sub-check to a non-blocking warning instead.
                return CheckResult(
                    id=cid, label=label, passed=True, severity="warn",
                    detail=f"cta-brief.json target_url is not a string ({expected_url!r}); "
                           f"skipping URL-correctness sub-check (non-blocking).",
                )
            if expected_url and not shortcode_present:
                hrefs = _extract_cta_hrefs(body, cta_cls)
                if not _cta_url_matches_brief(hrefs, expected_url):
                    return CheckResult(
                        id=cid, label=label, passed=False,
                        detail=f"CTA rendered but links to {hrefs} — cta-brief.json resolved "
                               f"target_url={expected_url!r}. A mismatch here means the LLM-authored "
                               f"CTA block linked to the wrong URL. Check 29 is the enforcement point "
                               f"for routing correctness; fix the CTA block (or re-run cta-writer) and "
                               f"republish.",
                    )

    return CheckResult(id=cid, label=label, passed=True,
                       detail=f"{tagged} tagged CTA block(s) for {len(applied)} applied placement(s)")


# ─── Main verification ───────────────────────────────────────────────


def verify_post(
    site_slug: str,
    post_id: int,
    *,
    publish_result: dict | None = None,
    expected_status: str | None = None,
    expect_robots_index: bool = True,
    required_schema_types: list[str] | None = None,
    min_image_count: int = 4,
    min_references_li: int = 3,
    primary_keyword: str | None = None,
    workspace_task_id: str | None = None,
) -> VerifyResult:
    """Run the full structural verification suite against a live WP post."""
    wp = WPClient(site_slug)
    with wp:
        try:
            r = wp.get(f"/wp/v2/posts/{post_id}?context=edit")
            post = r.json_data
        except Exception as e:
            return VerifyResult(
                site_slug=site_slug, post_id=post_id, post_status="?",
                overall_pass=False, fail_count=1, warn_count=0, pass_count=0,
                checks=[CheckResult(
                    id="00_fetch", label="GET /wp/v2/posts/{id}",
                    passed=False, detail=str(e),
                )],
            )

    rendered = post.get("content", {}).get("rendered", "")

    # Format-aware image target (2026-07-01): the flat default of 4 false-warned on
    # the weekly digest (1 chart by design → "counted 0/1, target ≥4"). When a
    # workspace is given, the honest target is what the pipeline actually produced:
    # len(images.json), floored at 1.
    if workspace_task_id:
        try:
            _imgs_path = (
                Path(__file__).resolve().parents[2]
                / "memory" / "workspace" / workspace_task_id / "images.json"
            )
            if _imgs_path.exists():
                _imgs = json.loads(_imgs_path.read_text(encoding="utf-8"))
                if isinstance(_imgs, dict):
                    _imgs = _imgs.get("images", [])
                if isinstance(_imgs, list) and _imgs:
                    min_image_count = max(1, len(_imgs))
        except Exception:
            pass  # fall back to the caller-provided target

    checks: list[CheckResult] = []
    checks.append(check_http_ok(post))
    # Fetch the live page <head> ONCE — used by both check_rankmath_meta (07) and
    # check_jsonld_schemas (17). RankMath emits title/canonical/description/robots/schema
    # all in <head>, so verifying rendered head is more reliable than verifying REST
    # meta-key exposure (which depends on MU bridge plugin auth_callback behaviour).
    head_html = _fetch_live_head(post, wp)
    checks.append(check_wrapper_in_body(rendered, site_slug))
    checks.append(check_scoped_css_inline(rendered, site_slug))
    checks.append(check_image_count(
        rendered, min_count=min_image_count,
        featured_set=bool(post.get("featured_media")),
    ))
    checks.append(check_no_placeholder_leakage(rendered))
    checks.append(check_no_escaped_html_leak(rendered))
    checks.append(check_no_pandoc_anchor_leak(rendered))
    checks.append(check_no_hand_rolled_srcset(rendered))
    checks.append(check_no_orphan_markdown_bold(rendered))
    checks.append(check_no_claim_marker_leak(rendered))
    checks.append(check_rankmath_meta(post, expect_robots_index=expect_robots_index, head_html=head_html))
    checks.append(check_references_h2_real(rendered))
    checks.append(check_references_ol_followed(rendered, min_li=min_references_li))
    checks.append(check_article_signature_real(rendered, site_slug))
    checks.append(check_status(post, expected=expected_status))
    checks.append(check_categories_not_uncategorized(post))
    checks.append(check_jsonld_schemas(
        rendered, head_html=head_html, min_total_blocks=2,
        require_types=required_schema_types or [],
    ))
    checks.append(check_featured_media_set(post))
    checks.append(check_media_fresh_no_dedup(post, publish_result))
    checks.append(check_keyword_density(rendered, primary_keyword=primary_keyword))
    checks.append(check_expected_stages_recorded(workspace_task_id))

    # Check 27 — local-SEO geo anchor density (only fires when state.brief.local_mode=true)
    _location_anchor = None
    if workspace_task_id:
        try:
            from scripts._core import file_bus as _fb
            _state = _fb.read_state(workspace_task_id)
            if _state.get("brief", {}).get("local_mode"):
                _location_anchor = _state["brief"].get("location_anchor")
        except Exception as _e:
            print(f"⚠ verify_post: failed to read state for geo_anchor check: {_e}", file=sys.stderr)
    checks.append(check_geo_anchor_density(
        rendered,
        _location_anchor,
        title_text=(post.get("title", {}) or {}).get("rendered", ""),
    ))

    # Check 28 — competitor/peer domain cited as a source on the live page (Rule 8).
    checks.append(check_no_competitor_domain_links(rendered, site_slug))

    # Check 29 — CTA module rendered live (v3.34): when the cta-injection stage
    # applied placements, the publisher must have class-tagged the block(s).
    checks.append(check_cta_module_rendered(rendered, workspace_task_id, site_slug))

    # Check 30 — CTA content not DUPLICATED live (2026-08-17): check 29 counts
    # tagged blocks (>= applied) and is blind to an extra untagged copy under a
    # renamed heading; this one keys on content identity.
    checks.append(check_cta_not_duplicated(rendered, workspace_task_id))

    fail_count = sum(1 for c in checks if not c.passed and c.severity == "fail")
    warn_count = sum(1 for c in checks if not c.passed and c.severity == "warn")
    pass_count = sum(1 for c in checks if c.passed)

    return VerifyResult(
        site_slug=site_slug, post_id=post_id,
        post_status=post.get("status", ""),
        overall_pass=fail_count == 0,
        fail_count=fail_count, warn_count=warn_count, pass_count=pass_count,
        checks=checks,
        preview_url=f"{wp.creds.url}/?p={post_id}&preview=true",
        live_url=post.get("link", ""),
    )


# ─── CLI ─────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify a published WP post against structural quality checks")
    ap.add_argument("site_slug")
    ap.add_argument("post_id", type=int)
    ap.add_argument("--publish-result", type=Path,
                    help="Path to wp_publisher --json output (enables media-freshness check)")
    ap.add_argument("--workspace", help="Task ID — load publish-result from memory/workspace/{task}/publish-result.json")
    ap.add_argument("--expected-status", choices=["draft", "publish", "private"])
    ap.add_argument("--no-index", action="store_true",
                    help="Disable expectation that rank_math_robots includes 'index'")
    ap.add_argument("--require-schema-type", action="append", default=[],
                    help="Required schema.org @type (repeatable). E.g. --require-schema-type FAQPage")
    ap.add_argument("--min-images", type=int, default=4)
    ap.add_argument("--min-references-li", type=int, default=3)
    ap.add_argument("--primary-keyword",
                    help="Primary focus keyword for density check (auto-loaded from meta.json if --workspace set)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", type=Path, default=None,
                    help="Write JSON result to this file (for orchestrator artifact tracking)")
    args = ap.parse_args()

    publish_result = None
    primary_keyword = args.primary_keyword
    if args.publish_result and args.publish_result.exists():
        publish_result = json.loads(args.publish_result.read_text(encoding="utf-8"))
    elif args.workspace:
        try:
            ws = file_bus.get_workspace(args.workspace, create=False)
            pr_path = ws / "publish-result.json"
            if pr_path.exists():
                publish_result = json.loads(pr_path.read_text(encoding="utf-8"))
            # Auto-load primary keyword from meta.json if not explicitly passed
            if not primary_keyword:
                meta_path = ws / "meta.json"
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    primary_keyword = (
                        meta.get("focus_keyphrase")
                        or meta.get("focus_keyword")
                        or meta.get("primary_keyword")
                    )
        except Exception:
            pass

    result = verify_post(
        args.site_slug, args.post_id,
        publish_result=publish_result,
        expected_status=args.expected_status,
        expect_robots_index=not args.no_index,
        required_schema_types=args.require_schema_type,
        min_image_count=args.min_images,
        min_references_li=args.min_references_li,
        primary_keyword=primary_keyword,
        workspace_task_id=args.workspace,
    )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    else:
        print(f"POST {result.post_id} on {result.site_slug} (status={result.post_status})")
        print(f"  preview: {result.preview_url}")
        print(f"  live:    {result.live_url or '(not published yet)'}")
        print()
        for c in result.checks:
            icon = "✓" if c.passed else ("⚠" if c.severity == "warn" else "✗")
            detail = f" — {c.detail}" if c.detail else ""
            print(f"  {icon} [{c.id}] {c.label}{detail}")
        print()
        print(f"  --> {result.pass_count} pass, {result.fail_count} fail, {result.warn_count} warn")
        if result.overall_pass:
            print("  OVERALL: PASS")
        else:
            print("  OVERALL: FAIL — fix issues above before declaring publish complete")

    return 0 if result.overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
