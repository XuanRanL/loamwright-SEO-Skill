#!/usr/bin/env python3
"""scripts/build/finalize_refs_signature.py — post-fact-check draft finalizer.

Closes two structural gaps that previously forced manual operator patching every run
(root-caused 2026-06-03):

  1. assemble.py builds the draft's "## References" block BEFORE fact-check runs, so it
     contains the writer's pre-verification references — which routinely include
     hallucinated authors/DOIs that the fact-checker later corrects ONLY in citations.json
     and the section file, never back into the already-assembled draft.md. This stage
     rebuilds the draft References block from the VERIFIED citations.json, so the published
     article always shows the corrected, link-resolvable sources.

  2. The writer agents are forbidden from authoring the article signature, and wp_publisher
     only TAGS an existing <p><em>…</em></p> — it never GENERATES one. So nobody owned the
     signature, and a draft could ship without it (verify_post check 11 fail). This stage
     auto-generates the canonical "Last reviewed and updated…" signature when missing.

Runs as a BASH pipeline stage AFTER fact-check-and-citation + citation-inject, BEFORE the
humanizer (which preserves both). Idempotent: References are replaced (not appended) and the
signature is only added when absent.

Usage:
    python -m scripts.build.finalize_refs_signature --task-id {tid} --project-slug {slug} [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
WS_ROOT = PLUGIN_ROOT / "memory" / "workspace"


def _ws(task_id: str) -> Path:
    return WS_ROOT / task_id


def _load(path: Path):
    try:
        from scripts._core import file_bus
        return file_bus.tolerant_json_load(path)
    except Exception:
        return json.loads(path.read_text(encoding="utf-8"))


def _make_clickable(apa: str) -> str:
    """If the APA string ends with a bare URL/DOI, wrap it as a markdown link."""
    txt = apa.strip()
    if "](" in txt:  # already has a markdown link
        return txt
    m = re.search(r"(https?://\S+)", txt)
    if m:
        url = m.group(1).rstrip(").,;")
        txt = txt.replace(url, f"[{url}]({url})")
    return txt


def rebuild_references(apa_entries: list[str]) -> str:
    lines = ["## References {#references}", ""]
    for i, apa in enumerate(apa_entries, 1):
        lines.append(f"{i}. {_make_clickable(apa)}")
    return "\n".join(lines) + "\n"


def _signature_template(project_slug: str) -> str | None:
    """Return the project's verbatim signature template, if it declares one.

    `business-context.json :: article_signature.markdown_template` lets a project
    author its signature in its OWN voice instead of accepting the generic
    "Author: X. For tailored guidance, contact our team." shape assembled from
    {author, contact_url, cta_clause}. Before 2026-07-14 nothing read this field,
    so every project that set it silently shipped the generic sentence anyway
    (a Rule-6 wiring gap: the config existed, the executor did not).

    The month placeholder is accepted in either casing convention projects use in
    the wild (`{Month Year}` and `{month_year}`) — a template whose placeholder is
    left unsubstituted would ship the literal braces to a live post.

    Em-dashes (U+2014) are downgraded to a full stop: render_lint L12 hard-vetoes
    them, and several project templates predate that red line. The clause that
    followed the dash is re-capitalised so the result reads as a sentence.
    """
    if not project_slug:
        return None
    bc_path = PLUGIN_ROOT / "projects" / project_slug / "business-context.json"
    if not bc_path.exists():
        return None
    try:
        bc = _load(bc_path)
    except Exception:
        return None
    tpl = ((bc.get("article_signature") or {}).get("markdown_template") or "").strip()
    if not tpl:
        return None
    month_year = datetime.now(timezone.utc).strftime("%B %Y")
    for token in ("{Month Year}", "{month_year}", "{MONTH YEAR}"):
        tpl = tpl.replace(token, month_year)
    # L12: no em-dash may reach the draft, whatever the template says. Re-capitalise
    # the following clause so "… [Talk to us](…) — real people" reads as a sentence.
    tpl = re.sub(r"\s*—\s*(\w)", lambda m: ". " + m.group(1).upper(), tpl)
    if "{" in tpl and "}" in tpl:
        # An unknown placeholder survived; the generic builder is safer than
        # shipping literal braces to a live post.
        return None
    return tpl


def _signature_spec(project_slug: str) -> tuple[str, str, str]:
    """Return (author, contact_url, cta_clause) for the article signature.

    Resolution order (project-agnostic, no hardcoded brand):
      1. projects/{slug}/business-context.json :: article_signature {author, contact_url, cta_clause}
      2. brand-config.json brand_name + business-context anchor_links contact URL
      3. generic fallback
    """
    author = "our editorial team"
    contact_url = "/contact/"
    cta_clause = "tailored guidance"
    if not project_slug:
        return author, contact_url, cta_clause
    proj = PLUGIN_ROOT / "projects" / project_slug
    bc_path = proj / "business-context.json"
    if bc_path.exists():
        try:
            bc = _load(bc_path)
        except Exception:
            bc = {}
        sig = bc.get("article_signature") or {}
        if sig.get("author"):
            author = sig["author"]
        if sig.get("contact_url"):
            contact_url = sig["contact_url"]
        if sig.get("cta_clause"):
            cta_clause = sig["cta_clause"]
        # derive a contact url from anchor_links if not explicitly set
        if contact_url == "/contact/":
            for link in bc.get("anchor_links", []):
                if "contact" in link:
                    contact_url = link
                    break
        if author == "our editorial team":
            # try brand-config for a friendly brand name
            for bc_file in (proj / "brand" / "brand-config.json", proj / "brand-config.json"):
                if bc_file.exists():
                    try:
                        brand = _load(bc_file)
                        if brand.get("brand_name"):
                            author = f"{brand['brand_name']} team"
                            break
                    except Exception:
                        pass
    return author, contact_url, cta_clause


def finalize(task_id: str, project_slug: str = "") -> dict:
    ws = _ws(task_id)
    draft_p = ws / "draft.md"
    cit_p = ws / "citations.json"
    if not draft_p.exists():
        return {"_generated_by": "finalize-refs-signature", "error": "draft.md missing"}
    draft = draft_p.read_text(encoding="utf-8")

    # 1. rebuild References from VERIFIED citations.json
    refs_rebuilt = False
    refs_count = 0
    if cit_p.exists():
        cit = _load(cit_p)
        entries = cit.get("citations", cit.get("refs", cit.get("items", []))) if isinstance(cit, dict) else cit
        apa = [e.get("apa_7") or e.get("apa") for e in entries if isinstance(e, dict) and (e.get("apa_7") or e.get("apa"))]
        refs_count = len(apa)
        if apa:
            new_refs = rebuild_references(apa)
            # Replace from "## References" up to the signature <hr>, next H2, or EOF.
            m = re.search(r"^##\s*References\b.*?(?=\n##\s|\n---\s*\n|\Z)", draft, re.S | re.M)
            if m:
                draft = draft[: m.start()] + new_refs + draft[m.end():]
                refs_rebuilt = True

    # 2. Ensure exactly ONE article signature, ALWAYS placed AFTER References (the
    # last block in the doc). Writers are forbidden from authoring it, but if one
    # slips in — e.g. inside the Conclusion, BEFORE References — we strip every
    # occurrence here and re-append a single signature at EOF. This prevents the
    # render_lint L9 "signature-before-References" defect (the 2026-06-04
    # seed-starting incident) instead of merely adding-when-absent.
    out_lines: list[str] = []
    existing_sig: str | None = None
    # Raw-HTML signature variants (e.g. a fact-checker hand-built
    # '<p class="article-signature"><em>Last reviewed…</em></p>') are dropped
    # entirely rather than captured: markdown-it with html=False would escape
    # them into visible text (render_lint L1), and keeping them produced the
    # 2026-06-09 duplicate-signature bug. Only the canonical markdown-italic
    # form is treated as "the" signature wording worth preserving.
    _html_sig_re = re.compile(
        r"^<p\s+class=[\"']article-signature[\"']>.*</p>\s*$", re.I,
    )
    for ln in draft.split("\n"):
        stripped = ln.strip()
        if _html_sig_re.match(stripped) or (
            stripped.startswith("<em>Last reviewed and updated:") and stripped.endswith("</em>")
        ):
            # drop HTML variant + peel back its '---' separator
            while out_lines and out_lines[-1].strip() == "":
                out_lines.pop()
            if out_lines and out_lines[-1].strip() == "---":
                out_lines.pop()
            while out_lines and out_lines[-1].strip() == "":
                out_lines.pop()
            continue
        if stripped.startswith("*Last reviewed and updated:") and stripped.endswith("*"):
            existing_sig = stripped  # capture the writer's wording, drop it from the body
            # peel back a preceding '---' separator + surrounding blank lines
            while out_lines and out_lines[-1].strip() == "":
                out_lines.pop()
            if out_lines and out_lines[-1].strip() == "---":
                out_lines.pop()
            while out_lines and out_lines[-1].strip() == "":
                out_lines.pop()
            continue
        out_lines.append(ln)
    draft = "\n".join(out_lines).rstrip()

    sig_relocated = existing_sig is not None
    sig_added = False
    sig_text = existing_sig
    if sig_text is None:
        sig_text = _signature_template(project_slug)
        if sig_text is None:
            author, contact_url, cta_clause = _signature_spec(project_slug)
            month_year = datetime.now(timezone.utc).strftime("%B %Y")
            sig_text = (
                f"*Last reviewed and updated: {month_year}. Author: {author}. "
                f"For {cta_clause}, [contact our team]({contact_url}).*"
            )
        sig_added = True
    draft = draft.rstrip() + f"\n\n---\n\n{sig_text}\n"

    draft_p.write_text(draft, encoding="utf-8")
    return {
        "_generated_by": "finalize-refs-signature",
        "task_id": task_id,
        "references_rebuilt": refs_rebuilt,
        "references_count": refs_count,
        "signature_appended": sig_added,
        "signature_relocated": sig_relocated,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Finalize draft References + article signature")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--project-slug", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = finalize(args.task_id, args.project_slug)
    # Rule 12 (2026-07-17): the artifact must carry its own verdict — an error
    # payload used to auto-satisfy the stage because only existence was checked.
    result["passed"] = "error" not in result
    out = _ws(args.task_id) / "finalize-result.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"  references_rebuilt={result.get('references_rebuilt')} "
              f"({result.get('references_count')}) | signature_appended={result.get('signature_appended')}")
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
