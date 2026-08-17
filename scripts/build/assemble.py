"""scripts/build/assemble.py — Concatenate workspace artifacts into final draft.md.

Order: Frontmatter → H1 → TL;DR → Abstract → Key Takeaways → ToC → Body sections → FAQ → Conclusion → References

Inputs (workspace/{task_id}/):
    state.json
    angle.json
    outline.json
    sections/*.json
    citations.json

Outputs:
    workspace/{task_id}/draft.md   (Stage: build-done)

This is the deterministic assembly step before humanizer.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts._core import heading_anchor

from scripts._core import file_bus
from scripts.build.anchor_link_builder import process as anchor_process
from scripts.build.markdown_to_html import strip_scaffold_markers


_IMAGE_SLOT_RE = re.compile(r"\[IMAGE-SLOT-([a-z0-9_-]+)\]", re.IGNORECASE)

# Writer-side scaffold/annotation tokens ([ORIGINAL DATA] etc.) are stripped via the
# canonical markdown_to_html.strip_scaffold_markers (single source of truth, shared with
# wp_publisher's publish-path strip and render_lint's L6 pre-strip — 2026-06-18 fix A).
# Assembly strips at the source; the publisher strips again at publish to also catch
# markers the optimize-phase subagents re-introduce after assembly.


def _normalize_markdown(md: str) -> str:
    """Deterministic clean-up applied to the assembled draft before it is written.

    Two recurring writer defects, both previously hand-fixed by the operator and both
    hard-vetoed by render_lint (so they cost a full repair round if missed):

      • Scaffold/annotation tokens ([ORIGINAL DATA] etc.) — stripped (render_lint L6).
      • A heading glued to its body paragraph on one physical line, e.g.
        ``### Title {#anchor} The body starts here…`` — the markdown→HTML converter then
        leaves the literal ``{#anchor}`` inside the rendered heading (render_lint L2) and
        the body is swallowed into the H-tag. We split heading / blank line / body, and
        drop the Pandoc anchor from H3+ headings (only H2 anchors feed the TOC).
    """
    md, _ = strip_scaffold_markers(md)
    out: list[str] = []
    for ln in md.split("\n"):
        m = re.match(
            r"^(#{2,6})\s+(.*?)\s*" + heading_anchor.ANCHOR_CAPTURE_FRAGMENT
            + r"[ \t]*(\S.*)$", ln)
        if m:
            hashes, htext, anchor, body = m.groups()
            keep_anchor = f" {{#{anchor}}}" if len(hashes) == 2 else ""  # TOC only links H2
            out.append(f"{hashes} {htext}{keep_anchor}")
            out.append("")
            out.append(body.lstrip())
        else:
            out.append(ln)
    md = "\n".join(out)
    md = re.sub(r"\n{3,}", "\n\n", md)  # collapse blank-line runs left by stripping
    return md


def _load_image_prompts(task_id: str) -> list[dict]:
    """Load + normalize image-prompts.json (-> list[dict]); [] if missing.

    Shape normalization (list vs {prompts:{slot_id:...}} dict) is centralized in
    scripts/_core/image_prompts so every consumer behaves identically (2026-06-29).
    """
    from scripts._core.image_prompts import normalize_image_prompts
    try:
        data = file_bus.read_artifact(task_id, "image-prompts.json")
    except FileNotFoundError:
        return []
    return normalize_image_prompts(data)


def _inject_missing_image_placeholders(
    body: str, outline: dict, image_prompts: list[dict]
) -> str:
    """Auto-inject [IMAGE-SLOT-X] placeholders when writers omit them.

    Uses image-prompts.json as the canonical source of slot_ids.
    Matches each slot to a section via outline.sections[].image_slot or
    outline.image_slots[].position, then inserts after the section's H2
    and first paragraph if missing.
    """
    if not image_prompts:
        return body

    prompt_slot_ids = {p["slot_id"] for p in image_prompts if p.get("slot_id")}
    body_slot_ids = {m.group(1) for m in _IMAGE_SLOT_RE.finditer(body)}

    missing = prompt_slot_ids - body_slot_ids
    if not missing:
        return body

    # Build slot→section_index mapping from outline
    slot_to_section: dict[str, int] = {}
    for slot_def in outline.get("image_slots", []):
        sid = slot_def.get("slot_id", "")
        pos = slot_def.get("position", "")
        if "section_" in pos:
            try:
                idx = int(pos.split("section_")[-1].split("_")[0])
                slot_to_section[sid] = idx
            except ValueError:
                pass
        if pos == "after_abstract":
            slot_to_section[sid] = 0

    # Fallback: match by section.image_slot == true
    sections = outline.get("sections", [])
    allocated_indices = [
        s.get("index", i) for i, s in enumerate(sections)
        if s.get("image_slot") is True
    ]

    # Map prompts to sections by order when outline.image_slots is missing.
    #
    # Cover identification (2026-07-07 batch audit): the CANONICAL image-prompts
    # contract has the designer OMIT `is_featured` (the pipeline forces it later —
    # the D5 slot-id fix), so `is_featured` alone CANNOT identify the cover here.
    # Relying on it made the fallback zip pair cover→first-image-section (the
    # 2026-07-07 loamwright batch shipped [IMAGE-SLOT-cover] inside body section 4
    # of two drafts; harmless under no_inline because the publisher strips it,
    # WRONG under inline mode) and off-by-one-shifted every chart mapping.
    # Identify the cover by slot_id "cover" OR a truthy is_featured.
    def _is_cover(p: dict) -> bool:
        return bool(p.get("is_featured")) or p.get("slot_id") == "cover"

    if not slot_to_section:
        non_cover_prompts = [p for p in image_prompts if not _is_cover(p)]
        non_cover_allocated = [i for i in allocated_indices]
        for prompt, sec_idx in zip(non_cover_prompts, non_cover_allocated):
            slot_to_section[prompt["slot_id"]] = sec_idx
        # Cover goes after abstract (index 0)
        for p in image_prompts:
            if _is_cover(p):
                slot_to_section[p["slot_id"]] = 0

    lines = body.split("\n")
    injected = 0

    for slot_id in sorted(missing):
        sec_idx = slot_to_section.get(slot_id)
        if sec_idx is None:
            continue

        placeholder = f"[IMAGE-SLOT-{slot_id}]"
        target_h2 = None
        if sec_idx < len(sections):
            target_h2 = sections[sec_idx].get("h2", "")

        # Find the H2 line in the body
        h2_line_idx = None
        for i, line in enumerate(lines):
            if line.startswith("## ") and target_h2 and target_h2.lower() in line.lower():
                h2_line_idx = i
                break

        if h2_line_idx is None:
            continue

        # Insert after H2's first paragraph
        insert_at = h2_line_idx + 1
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
        while insert_at < len(lines) and lines[insert_at].strip() and not lines[insert_at].startswith("#"):
            insert_at += 1

        lines.insert(insert_at, f"\n{placeholder}\n")
        injected += 1
        print(
            f"  ↳ assemble: auto-injected {placeholder} after section '{target_h2}' "
            f"(writer omitted it)",
            file=sys.stderr,
        )

    if injected:
        print(
            f"⚠ assemble.py: auto-injected {injected} missing image placeholder(s) "
            f"from image-prompts.json",
            file=sys.stderr,
        )
    return "\n".join(lines)


def _fix_slot_id_names(body: str, image_prompts: list[dict]) -> str:
    """Rename mismatched [IMAGE-SLOT-X] to match image-prompts.json slot_ids.

    Uses fuzzy matching: if draft has [IMAGE-SLOT-hero] but prompts has
    'cover' with is_featured=true, renames hero→cover.
    """
    if not image_prompts:
        return body

    prompt_slot_ids = {p["slot_id"] for p in image_prompts if p.get("slot_id")}
    body_matches = list(_IMAGE_SLOT_RE.finditer(body))
    body_slot_ids = {m.group(1) for m in body_matches}

    orphaned = body_slot_ids - prompt_slot_ids
    unplaced = prompt_slot_ids - body_slot_ids

    if not orphaned or not unplaced:
        return body

    # Try to match orphaned→unplaced by order of appearance
    orphaned_ordered = [m.group(1) for m in body_matches if m.group(1) in orphaned]
    seen = set()
    orphaned_unique = []
    for s in orphaned_ordered:
        if s not in seen:
            seen.add(s)
            orphaned_unique.append(s)

    # Simple heuristic: "hero"/"cover_image" → the is_featured prompt
    featured_prompt = next((p["slot_id"] for p in image_prompts if p.get("is_featured")), None)
    # The cover/featured slot is positionally FIXED (injected after the Abstract by
    # _inject_missing_image_placeholders) and must NEVER be a positional-rename
    # target for a mid-body orphan. Since writers never emit [IMAGE-SLOT-cover], the
    # cover is almost always "unplaced" here, and it sorts FIRST alphabetically — so
    # the old `sorted(unplaced)[0]` fallback hijacked mid-article orphans into the
    # cover, planting it mid-article (2026-07-17). Only the explicit alias branch
    # below may map an orphan to the cover.
    cover_slots = {
        p["slot_id"] for p in image_prompts
        if p.get("slot_id") and (p.get("is_featured") or p["slot_id"] == "cover")
    }
    renames: dict[str, str] = {}

    for orphan in orphaned_unique:
        if orphan in ("hero", "cover_image", "featured", "main") and featured_prompt and featured_prompt in unplaced:
            renames[orphan] = featured_prompt
            unplaced.discard(featured_prompt)
            continue
        # Positional fallback: match by order — but never to the cover/featured slot.
        positional_targets = sorted(unplaced - cover_slots)
        if positional_targets:
            target = positional_targets[0]
            renames[orphan] = target
            unplaced.discard(target)

    for old_name, new_name in renames.items():
        old_token = f"[IMAGE-SLOT-{old_name}]"
        new_token = f"[IMAGE-SLOT-{new_name}]"
        body = body.replace(old_token, new_token)
        print(
            f"  ↳ assemble: renamed {old_token} → {new_token} "
            f"(matched to image-prompts.json)",
            file=sys.stderr,
        )

    return body


def _replace_claims(text: str, in_text_replacements: list[dict]) -> str:
    """Replace [claim:cN_S] markers with (Author, Year) citations.

    Accepts both key shapes:
      - {"from": "...", "to": "..."}  (schema canonical)
      - {"marker": "...", "replace_with": "..."}  (wp_publisher canonical)
    """
    for r in in_text_replacements or []:
        marker = r.get("from") or r.get("marker") or ""
        replacement = r.get("to") or r.get("replace_with") or ""
        if marker:
            text = text.replace(marker, replacement)
    # Adjacent markers resolving to the same source each emit their own
    # parenthetical — collapse identical neighbours (2026-07-01, shared helper).
    from scripts._core.citation_text import collapse_adjacent_duplicate_citations
    return collapse_adjacent_duplicate_citations(text)


def _build_takeaways_section(seeds: list[str]) -> str:
    """Render Key Takeaways list."""
    if not seeds:
        return ""
    items = "\n".join(f"- {s}" for s in seeds)
    return f"## Key Takeaways\n\n{items}\n"


def _build_faq_section(faq_seeds: list[str], faq_answers: dict | None = None) -> str:
    """Render FAQ section. answers is optional dict keyed by question."""
    if not faq_seeds:
        return ""
    parts = ["## FAQ"]
    for q in faq_seeds:
        parts.append(f"\n### {q}\n")
        if faq_answers and q in faq_answers:
            parts.append(f"{faq_answers[q]}\n")
        else:
            parts.append("_Answer pending; see body for related details._\n")
    return "\n".join(parts)


def _fill_toc_placeholder(modified: str, toc_markdown: str) -> str:
    """Fill the "_(auto-generated)_" placeholder INSIDE the Table of Contents
    section ONLY, then blank any leftover placeholder tokens.

    Writers use the same placeholder token in the References section (filled
    later by finalize_refs_signature from verified citations.json). A global
    .replace() used to fill that one with a TOC duplicate too — the 2026-06-09
    batch bug where all three articles' References showed a second TOC until
    finalize repaired it (and fact-checkers "helpfully" hand-patched drafts).
    """
    toc_scoped = re.sub(
        r"(^##\s*Table of Contents[^\n]*\n+)_\(auto-generated\)_",
        lambda m: m.group(1) + toc_markdown,
        modified,
        count=1,
        flags=re.M,
    )
    if toc_scoped != modified:
        modified = toc_scoped
    else:
        # No TOC-section placeholder found — fall back to first-occurrence
        # replace (the TOC placeholder always precedes the References one).
        modified = modified.replace("_(auto-generated)_", toc_markdown, 1)
    # Leftover placeholders (e.g. References) must NOT ship as literal text;
    # blank them — finalize_refs_signature rebuilds that section's content.
    return modified.replace("_(auto-generated)_", "")


def _build_references_section(refs: list[dict]) -> str:
    """Render References as APA-formatted list."""
    if not refs:
        return ""
    parts = ["## References\n"]
    for r in refs:
        parts.append(f"- {r.get('apa', r.get('refkey', ''))}")
    return "\n".join(parts) + "\n"


def _ref_blocked_domain(r: dict, policy) -> str | None:
    """Return the competitor domain a ref points at, or None."""
    for token in (r.get("url"), r.get("doi"), r.get("domain")):
        if isinstance(token, str) and token:
            d = policy.blocked_domain_of(token)
            if d:
                return d
    for key in ("apa", "apa_7"):
        v = r.get(key)
        if isinstance(v, str) and v:
            hits = policy.find_blocked_in_html(v)
            if hits:
                return hits[0][1]
    return None


def _strip_competitor_citations(task_id: str, citations: dict) -> dict:
    """Backstop (Rule 8): drop competitor/peer-domain sources from citations.json
    before they reach the References list or the in-text (Author, Year) swap.

    The PRIMARY guard is the fact-checker (it re-sources / drops competitor
    sources upstream). This fires only when a competitor ref survived into
    citations.json (hand-edit / fact-checker bug). When it fires, the matching
    in-text replacement is dropped too, so the raw [claim:…] marker is left for
    render_lint L5 to flag loudly — we never silently ship a half-stripped
    citation. Disabled-policy / load-failure → returns citations unchanged."""
    try:
        from scripts._core import competitor_domains as cd
        policy = cd.load_policy_for_task(task_id)
    except Exception as e:  # noqa: BLE001 — log, never crash assembly
        print(f"⚠ assemble: competitor policy load failed ({type(e).__name__}: {e}); "
              f"competitor strip skipped", file=sys.stderr)
        return citations
    if not policy.enabled:
        return citations

    refs_key = next(
        (k for k in ("refs", "citations", "items") if isinstance(citations.get(k), list)),
        None,
    )
    refs = citations.get(refs_key, []) if refs_key else []
    kept_refs: list[dict] = []
    rejected: list[str] = []
    blocked_tokens: set[str] = {b.lower() for b in policy.brands}
    for r in refs:
        d = _ref_blocked_domain(r, policy)
        if d:
            rejected.append(d)
            for a in (r.get("authors") or []):
                blocked_tokens.add(str(a).split(",")[0].strip().lower())
        else:
            kept_refs.append(r)

    if not rejected:
        return citations

    new = dict(citations)
    if refs_key:
        new[refs_key] = kept_refs
    itr = new.get("in_text_replacements") or []
    new_itr = []
    for rep in itr:
        to = (rep.get("to") or rep.get("replace_with") or "").lower()
        if any(tok and tok in to for tok in blocked_tokens):
            continue  # drop competitor in-text cite; raw marker → render_lint L5 flags
        new_itr.append(rep)
    new["in_text_replacements"] = new_itr
    existing = new.get("rejected_competitor_domains") or []
    new["rejected_competitor_domains"] = sorted(set(existing) | set(rejected))
    print(f"⚠ assemble: stripped {len(rejected)} competitor-domain citation(s) "
          f"({', '.join(sorted(set(rejected)))}) from References + in-text. Backstop "
          f"fired — the fact-checker should have prevented this upstream (Rule 8).",
          file=sys.stderr)
    return new


_CONCLUSION_TOKENS_FALLBACK = (
    "conclusion", "verdict", "bottom line", "final thought",
    "in closing", "in loving memory", "in memory", "final word",
    "parting thought", "a final word", "closing thought", "last word",
)


def _format_wants_conclusion(state: dict, angle: dict) -> bool:
    """Does the resolved mandatory-sections contract ask for a conclusion?

    2026-08-02 root cure: this detector's sibling ``_conclusion_h2_pattern``
    reads only tier 3 (project ``mandatory_sections.sections[]``), but the
    Format-Fit gate resolves 3-tier — and tier 2
    (``references/seo/format-mandatory-sections.json``) can say a format wants
    NO conclusion at all (weekly-digest: tldr/faq/references only). When the
    resolved contract excludes it, injecting the ``## Conclusion`` stub creates
    a PHANTOM section: the placeholder body then satisfies CORE-EEAT C09
    (heading present) and no lint checks stub prose, so it ships to review.
    Delegates to the SAME resolver the gate uses (Rule 12: one fact, one
    reader) instead of keeping a second copy of the tier logic here.
    """
    from scripts.lint.mandatory_sections_check import _load_mandatory_sections

    slug = str((state or {}).get("project_slug") or "")
    format_id = str((angle or {}).get("format_id") or "")
    try:
        ms = _load_mandatory_sections(slug, format_id or None)
    except Exception:
        return True  # resolver unavailable → legacy behavior (stub appended)
    if not ms:
        return True  # no contract at any tier → legacy behavior
    for sec in ms:
        sid = str(sec.get("id") or "").lower()
        pat = str(sec.get("h2_pattern") or "")
        if sid == "conclusion" or re.search(r"conclusion", pat, re.IGNORECASE):
            return True
    return False


def _conclusion_h2_pattern(state: dict) -> re.Pattern[str] | None:
    """Compile the ACTIVE project's conclusion h2_pattern regex, if it declares one.

    This is the same regex the Format-Fit / mandatory-sections gate enforces. Reading
    it here (rather than re-deriving "what counts as a conclusion" from a local token
    list) is what keeps the assembly stub and the gate from disagreeing — see the
    Rule-11 note at the call site.
    """
    slug = (state or {}).get("project_slug")
    if not slug:
        return None
    bc_path = Path(__file__).resolve().parents[2] / "projects" / slug / "business-context.json"
    try:
        bc = json.loads(bc_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    sections = ((bc.get("mandatory_sections") or {}).get("sections")) or []
    for sec in sections:
        if sec.get("id") == "conclusion" and sec.get("h2_pattern"):
            try:
                return re.compile(sec["h2_pattern"])
            except re.error:
                return None
    return None


def _has_conclusion_section(state: dict, sections: list[dict]) -> bool:
    """True if the body already contains a Conclusion H2 (under ANY label the project allows).

    v3.41.3: h2 values are NORMALIZED (any trailing ``{#anchor}`` stripped)
    before matching. The v3.40.0 switch to anchored ``h2_pattern`` regexes
    regressed on writer-anchored headings: ``^Conclusion$`` does not match
    ``"Conclusion {#conclusion}"``, so a REAL Conclusion went unrecognized and
    a duplicate ``_(See verdict...)_`` stub was appended (2026-07-19 batch).
    The sibling dedup checks (TOC/FAQ/References) are substring-based and were
    never affected; this was the only full-match regex on the raw h2.
    """
    h2s = [
        heading_anchor.strip_heading_anchor(s.get("h2", ""))
        for s in sections
    ]
    pattern = _conclusion_h2_pattern(state)
    if pattern is not None:
        return any(pattern.match(h) for h in h2s)
    # Fallback only for projects with no declared conclusion pattern.
    return any(
        any(tok in h.lower() for tok in _CONCLUSION_TOKENS_FALLBACK)
        for h in h2s
    )


_CLAIM_MARKER_RE = re.compile(r"\[claim:([0-9A-Za-z_]+)\]")


def _resolve_marker_collisions(sections: list[dict]) -> list[dict]:
    """Auto-rename claim markers that collide ACROSS sections.

    Parallel writers drift between the two marker conventions (cK_S vs cS_K),
    so the same literal marker string can label DIFFERENT claims in different
    section files (4 collisions in the 2026-07-17 pawnoseprint batch alone,
    hand-fixed; recurring since 2026-06-18). Left in place, the fact-checker
    verifies only one of the claims and citation-inject rewrites both
    occurrences with that one citation — a silent mis-citation.

    Repeats of a marker WITHIN one section are legitimate (the same claim cited
    twice) and are preserved. Only a marker already used by an EARLIER section
    is renamed here, to `c9{n}_{section_index}` — a namespace no writer
    convention produces — with a stderr notice so runner logs show the rewrite.
    """
    seen: dict[str, int] = {}
    renumber = 0
    for sec in sections:
        idx = sec.get("section_index", 0)
        md = sec.get("markdown", "")
        if not md:
            continue
        here = list(dict.fromkeys(_CLAIM_MARKER_RE.findall(md)))
        for slug in here:
            if slug in seen and seen[slug] != idx:
                renumber += 1
                new_slug = f"c9{renumber:02d}_{idx}"
                while new_slug in seen or f"[claim:{new_slug}]" in md:
                    renumber += 1
                    new_slug = f"c9{renumber:02d}_{idx}"
                md = md.replace(f"[claim:{slug}]", f"[claim:{new_slug}]")
                print(
                    f"⚠ assemble.py: claim-marker collision — [claim:{slug}] already "
                    f"used by section {seen[slug]}; renamed to [claim:{new_slug}] in "
                    f"section {idx} (distinct claims must carry distinct markers)",
                    file=sys.stderr,
                )
                seen[new_slug] = idx
            else:
                seen.setdefault(slug, idx)
        sec["markdown"] = md
    return sections


def assemble(task_id: str) -> Path:
    """Read all workspace artifacts, produce draft.md."""
    state = file_bus.read_state(task_id)
    angle = file_bus.read_artifact(task_id, "angle.json")
    outline = file_bus.read_artifact(task_id, "outline.json")

    # Load citations if present
    citations = None
    try:
        citations = file_bus.read_artifact(task_id, "citations.json")
    except FileNotFoundError:
        pass

    # Rule 8 backstop: strip any competitor/peer-domain source that survived into
    # citations.json before References + in-text citations are built from it.
    if citations:
        citations = _strip_competitor_citations(task_id, citations)

    # Load all sections (sorted). Supports both JSON (legacy) and MD (current) formats.
    section_files = file_bus.list_section_artifacts(task_id)
    sections = []
    for f in section_files:
        if f.suffix == ".md":
            # MD format: extract leading digits from filename
            # Handles both "3.md" and "03_why_bulk.md" patterns
            m = re.match(r"^(\d+)", f.stem)
            idx = int(m.group(1)) if m else 0
            md_text = f.read_text(encoding="utf-8").strip()
            # Derive h2 from the first heading line so the FAQ/Conclusion/References
            # dedup below (which keys on section_h2s_lower) works for .md sections.
            # Without this, h2="" → dedup never matches → duplicate seed sections ship.
            # v3.41.3: strip any writer-supplied {#anchor} so EVERY h2 consumer
            # (conclusion pattern-match, TOC/FAQ/References dedup) compares
            # against the clean heading text. Anchors are assembly-owned; the
            # canonical slug is injected later by anchor_process.
            h2_text = heading_anchor.h2_from_markdown(md_text)
            sections.append({"section_index": idx, "markdown": md_text, "h2": h2_text})
        else:
            try:
                sections.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception as e:
                print(
                    f"⚠ assemble.py: failed to parse {f.name}: {type(e).__name__}: {e} "
                    f"— section will be MISSING from assembled draft",
                    file=sys.stderr,
                )
                continue
    sections.sort(key=lambda s: s.get("section_index", 0))
    sections = _resolve_marker_collisions(sections)

    # Build markdown
    title = angle.get("title", "Untitled")
    slug = angle.get("slug_draft", "")
    primary_kw = state.get("brief", {}).get("primary_keyword", "")

    # Frontmatter
    fm: list[str] = [
        "---",
        f"title: \"{title}\"",
        f"slug: {slug}" if slug else "",
        f"focus_keyphrase: {primary_kw}" if primary_kw else "",
        "Stage: build-done",
        f"GeneratedAt: {datetime.now(timezone.utc).isoformat()}",
        f"TaskId: {task_id}",
        "---",
    ]
    fm_text = "\n".join(line for line in fm if line) + "\n\n"

    parts = [fm_text]
    parts.append(f"# {title}\n\n")

    # Check which structural sections writers already produced
    writer_h2s_lower = {
        s.get("markdown", "").split("\n")[0].lower().replace("## ", "").strip()
        for s in sections
    }

    # TL;DR (from outline tldr_seed) — only if no writer section covers it
    if outline.get("tldr_seed") and not any("tl;dr" in h or "tldr" in h for h in writer_h2s_lower):
        parts.append(f"## TL;DR\n\n{outline['tldr_seed']}\n")

    # Abstract — only if no writer section covers it
    if outline.get("abstract_seed") and not any("abstract" in h for h in writer_h2s_lower):
        parts.append(f"## Abstract\n\n{outline['abstract_seed']}\n")

    # Key Takeaways — only if no writer section covers it
    if not any("key takeaway" in h for h in writer_h2s_lower):
        parts.append(_build_takeaways_section(outline.get("takeaways_seeds", [])))

    # ToC placeholder — emit it only if NO writer TOC section exists. If a writer
    # DID ship a TOC section, we do NOT emit a second placeholder here; instead the
    # body loop below replaces that writer TOC's body with the placeholder. Either
    # way exactly one "_(auto-generated)_" placeholder ends up in the draft and is
    # filled with the correctly-anchored TOC at the anchor_process step (~line 381).
    #
    # WHY: a writer-supplied TOC is built from outline.json short anchor_ids
    # (e.g. (#faq)), but heading ids are generated by slugifying the FULL heading
    # text (e.g. #frequently-asked-questions). Shipping the writer TOC verbatim
    # left every in-page jump link broken. The TOC is a purely mechanical mirror of
    # the H2 set, so regenerating it can never lose authored prose — always do it.
    section_h2s_lower_pre = {
        s.get("markdown", "").split("\n")[0].lower().replace("## ", "").strip()
        for s in sections
    }
    has_writer_toc = any("table of contents" in h for h in section_h2s_lower_pre)
    if not has_writer_toc:
        parts.append("## Table of Contents\n\n_(auto-generated)_\n")

    # Body sections
    in_text_replacements = (citations or {}).get("in_text_replacements", [])
    for sec in sections:
        md = sec.get("markdown", "")
        md = _replace_claims(md, in_text_replacements)
        # Ensure section starts with H2
        if not md.lstrip().startswith("##"):
            md = f"## {sec.get('h2', 'Section')}\n\n{md}"
        # If this is the writer-provided TOC, discard its (stale-anchor) body and
        # substitute the auto-gen placeholder, so the freshly-built TOC with correct
        # heading anchors is injected uniformly downstream (no broken jump links).
        first_line = md.split("\n", 1)[0].lower()
        if first_line.startswith("##") and "table of contents" in first_line:
            md = "## Table of Contents\n\n_(auto-generated)_"
        parts.append(md.rstrip() + "\n")

    # Detect which structural sections already exist in body sections
    section_h2s_lower = {s.get("h2", "").lower() for s in sections}

    # FAQ — only append from outline seeds if no FAQ section exists in body
    has_faq = any("faq" in h or "frequently asked" in h for h in section_h2s_lower)
    if not has_faq:
        faq = outline.get("faq", {})
        parts.append(_build_faq_section(faq.get("seed_questions", [])))

    # Conclusion — only append placeholder if no Conclusion section in body.
    #
    # SOURCE OF TRUTH is the project's own
    # ``business-context.json :: mandatory_sections.sections[id=conclusion].h2_pattern``
    # regex — the SAME pattern the Format-Fit gate hard-vetoes against. Previously
    # this detector kept a SEPARATE hardcoded token list, which is a Rule-11
    # duplicate-source-of-truth: the two drifted, and a project whose regex allowed a
    # gentle label the token list had never heard of got an empty "## Conclusion" stub
    # appended NEXT TO its real conclusion (2026-06-18 project-hotel "A Final Thought";
    # 2026-07-14 project-bravo "The Last Sip"). Reading the project's regex means the
    # stub logic and the gate can no longer disagree about what a conclusion IS.
    #
    # The token list survives ONLY as the fallback for projects that declare no
    # mandatory_sections conclusion pattern.
    #
    # 2026-08-02 addendum: the paragraph above was true pre-3-tier. Tier 2
    # (references/seo/format-mandatory-sections.json) can now EXCLUDE the
    # conclusion for a format (weekly-digest), so the stub is gated on the
    # resolved contract via _format_wants_conclusion — otherwise the digest
    # shipped a phantom "## Conclusion" holding the literal placeholder
    # "_(See verdict in main body sections.)_" (caught only by the human
    # reviewer, three issues running).
    has_conclusion = _has_conclusion_section(state, sections)
    if not has_conclusion and _format_wants_conclusion(state, angle):
        parts.append("## Conclusion\n\n_(See verdict in main body sections.)_\n")

    # References — append if no References section in body. References is
    # mandatory in EVERY format (Rule 5), and at assembly time citations.json
    # usually does not exist yet (fact-check runs AFTER assembly), so an empty
    # refs list must still emit the heading stub: finalize_refs_signature only
    # REPLACES an existing "## References" block (it never appends), so without
    # this stub the article would ship with no References section at all.
    # 2026-07-07 root cure — the hand-created sections/NN_references.md
    # placeholder every batch operator had to rediscover is no longer needed
    # (section_completeness_check now exempts the References outline entry).
    has_references = any("references" in h for h in section_h2s_lower)
    if not has_references:
        refs_block = _build_references_section((citations or {}).get("refs", []))
        parts.append(refs_block or "## References\n\n_(auto-generated)_\n")

    draft_md = "\n".join(parts)

    # Auto-fix image placeholders: rename mismatches, inject missing
    image_prompts = _load_image_prompts(task_id)
    if image_prompts:
        draft_md = _fix_slot_id_names(draft_md, image_prompts)
        draft_md = _inject_missing_image_placeholders(draft_md, outline, image_prompts)

    # Inject anchor IDs + build proper ToC
    modified, toc = anchor_process(draft_md, include_h3_in_toc=False)
    modified = _fill_toc_placeholder(modified, toc.markdown)

    # Deterministic clean-up: strip scaffold tokens + unglue heading/body (render_lint L2/L6).
    modified = _normalize_markdown(modified)

    # Write to workspace
    ws = file_bus.get_workspace(task_id)
    draft_path = ws / "draft.md"
    draft_path.write_text(modified, encoding="utf-8")

    # Update state
    file_bus.update_state(task_id, current_stage="assemble-done")
    return draft_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble sections into draft.md")
    # Accept BOTH the positional `task_id` (legacy callers) AND `--task-id`
    # (the flag convention used by the orchestrator command template and the
    # sibling BASH stages chart-render / category-selector / finalize). The
    # orchestrator resolves "...assemble --task-id {task_id} --json", so the
    # positional must be optional here or that template hard-fails (the
    # 2026-06-03 runner-driven assembly ERROR).
    ap.add_argument("task_id", nargs="?", default=None)
    ap.add_argument("--task-id", dest="task_id_flag", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    task_id = args.task_id or args.task_id_flag
    if not task_id:
        ap.error("task_id is required (positional or --task-id)")

    try:
        draft_path = assemble(task_id)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "task_id": task_id,
            "draft_path": str(draft_path),
            "word_count": sum(1 for _ in draft_path.read_text(encoding="utf-8").split()),
        }, indent=2))
    else:
        print(f"Wrote draft to {draft_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
