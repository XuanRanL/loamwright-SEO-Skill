"""
scripts/wordpress/wp_publisher.py — End-to-end WordPress publish orchestrator.

This is the production pathway for /publish. Implements the 7-step flow
specified in SKILL-ARCHITECTURE-V3.md §17 + IMAGE-GENERATION-V3.2-SPEC.md §8:

  1. Parse draft.md frontmatter + body
  2. Resolve categories (resolve-only — never creates; unresolvable name aborts.
     Explicit opt-in: --allow-create-categories. 2026-07-11 root cure for the
     &-entity duplicate-category incident)
  3. Resolve tags (get_or_create)
  4. Upload images to Media Library (4 per article + variants)
  5. Substitute [IMAGE-SLOT-N] / placeholder URLs in body with real Media URLs
  6. Convert markdown → plain HTML (drop H1, anchor IDs, lazy loading, srcset)
  7. Create draft post → set Yoast meta → set featured image → publish

On any step failure, rolls back uploaded media (configurable).

CLI:
    python -m scripts.wordpress.wp_publisher <site-slug> --workspace <task_id>                       # creates DRAFT (default — safe)
    python -m scripts.wordpress.wp_publisher <site-slug> --workspace <task_id> --status=publish      # go live (requires explicit opt-in)
    python -m scripts.wordpress.wp_publisher <site-slug> --draft draft.md --meta meta.json
    python -m scripts.wordpress.wp_publisher <site-slug> --workspace <task_id> --dry-run

DEFAULT BEHAVIOR (2026-05-20 change): the publisher now defaults to status=draft.
Publishing live requires explicit `--status=publish` (CLI) or `status="publish"` (API).
This matches the SOP "every visible-to-others action requires user confirmation":
draft creates the post, lets a human review the live preview, then a separate
explicit step flips to publish.

Outputs:
  - final.html written to workspace/{task}/final.html
  - publish-result.json written to workspace/{task}/publish-result.json
  - projects/{slug}/.seo/change-log.json appended (7-day undo)
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from scripts._core import file_bus
from scripts._core import heading_anchor
from scripts.build.markdown_to_html import convert as md_to_html, ConvertOptions, split_frontmatter, strip_scaffold_markers
from scripts.wordpress import wp_taxonomy, wp_media
from scripts.wordpress.wp_client import WPClient, WPApiError


@dataclass
class PublishResult:
    success: bool
    post_id: int | None
    post_url: str | None
    status: str | None        # "publish" / "draft" / "private"
    media_ids: list[int] = field(default_factory=list)
    featured_media_id: int | None = None
    yoast_set: bool = False
    rankmath_set: bool = False
    seo_plugin_used: str | None = None    # "yoast" | "rankmath" | None
    duration_seconds: float = 0
    error: str | None = None
    rollback_attempted: bool = False
    rollback_succeeded: bool = False
    change_log_entry_id: str | None = None


@dataclass
class PublishInput:
    """All inputs needed for a publish operation."""
    site_slug: str
    draft_markdown: str
    meta: dict                          # title, slug, excerpt, focus_keyphrase, etc.
    images: list[dict] = field(default_factory=list)
    # Each image: {path, slot_id, alt, caption, title, is_featured, placeholder_token}
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: Literal["publish", "draft", "private"] = "draft"   # 2026-05-20: default flipped publish→draft (safe-by-default; visible-to-others actions require explicit opt-in)
    task_id: str | None = None
    defer_images: bool = False          # B flow: create draft now, attach images later
    # 2026-07-11: publish-time category CREATION is forbidden by default. The blog
    # taxonomy is curated at init (setup_categories); an unresolvable category name
    # means config/taxonomy drift and must abort the publish loudly — silently minting
    # a parentless top-level category is how the project-hotel &-entity duplicate pairs
    # were born (2026-06-16→20). Tags stay create-on-the-fly (tag_policy governs them).
    allow_create_categories: bool = False


# ─── Main orchestrator ────────────────────────────────────

def publish(
    inp: PublishInput,
    *,
    dry_run: bool = False,
    allow_http: bool = False,
    rollback_on_failure: bool = True,
    workspace_task_id: str | None = None,
) -> PublishResult:
    """Execute the full 7-step publish.

    Args:
        inp: Bundled inputs.
        dry_run: If True, skip actual WP writes; print plan only.
        allow_http: Allow http:// for local WP test sites.
        rollback_on_failure: Delete uploaded media if post creation fails.
        workspace_task_id: If set, write final.html + publish-result.json to workspace.

    Returns:
        PublishResult with success status + IDs + URL.
    """
    t_start = time.time()
    result = PublishResult(success=False, post_id=None, post_url=None, status=None)

    # ── Stage tracking (audit 2026-05-22) ─────────────────────────────
    # Record this stage in state.json::stage_history so post-hoc audits can
    # answer "did wordpress-publisher actually run for this task?". Only
    # active when workspace_task_id is set (i.e. called via --workspace mode).
    _stage_recorded = False
    if workspace_task_id:
        try:
            from scripts._core import file_bus as _fb
            _fb.record_stage_start(workspace_task_id, "wordpress-publisher", phase="publish")
            _stage_recorded = True
        except Exception as _e:
            # Stage-tracking failure must NOT block publish (it's an audit aid,
            # not a critical path), but log loudly per the silent-fallback
            # convention (audit 2026-05-22 P1):
            print(
                f"⚠ stage_history record_stage_start failed: {_e}",
                file=sys.stderr,
            )

    try:
        wp = WPClient(inp.site_slug, allow_http_for_testing=allow_http)
    except Exception as e:
        result.error = f"WPClient init failed: {e}"
        if _stage_recorded:
            try:
                from scripts._core import file_bus as _fb
                _fb.record_stage_complete(workspace_task_id, "wordpress-publisher", status="failed")
            except Exception as _e:
                print(f"⚠ stage_history record_stage_complete failed: {_e}", file=sys.stderr)
        return result

    with wp:
        # ── Step 0: Health check ────────────────────────────
        h = wp.health_check()
        if not h["wp_rest"]:
            result.error = f"WP REST not reachable: {h['info']}"
            return result
        if not h["yoast_mu_plugin"]:
            print("⚠ Yoast MU-plugin endpoint not detected. Yoast meta will be skipped.",
                  file=sys.stderr)

        # ── Step 0b: Stage-history gate (2026-05-26) ──────
        # Refuse to publish if mandatory pipeline stages are missing from
        # state.json. Prevents shipping articles that skipped fact-checker,
        # humanizer, or reviewer. Bypass with --no-stage-gate (not exposed in
        # CLI yet — only for emergency manual publishes).
        if workspace_task_id and not dry_run:
            try:
                from scripts._core import file_bus as _fb2
                _state = _fb2.read_state(workspace_task_id)
                _completed = {
                    h.get("stage") for h in _state.get("stage_history", [])
                    if h.get("status") == "completed"
                }
                _required = {"research", "build", "optimize"}
                _missing = _required - _completed
                if _missing:
                    print(
                        f"⚠ STAGE-GATE WARNING: pipeline stages not completed: {sorted(_missing)}. "
                        f"Articles shipped without these stages may lack fact-checking, "
                        f"humanization, or independent review. Proceeding anyway (warn-only "
                        f"until pipeline enforces sequential execution).",
                        file=sys.stderr,
                    )
            except Exception as _sg_err:
                print(f"⚠ stage-gate check failed (non-fatal): {_sg_err}", file=sys.stderr)

        # ── Step 0c: Pre-publish artifact gate (2026-05-26) ──────
        # Hard-block if mandatory artifacts are missing. This is the
        # enforcement layer that prevents publishing without images,
        # without render-lint, without citations. The gate checks for
        # physical file existence, not stage-history records (which
        # depend on the LLM remembering to call the tracker).
        if workspace_task_id and not dry_run:
            try:
                from scripts.pipeline.pre_publish_gate import run_gate
                _gate_report = run_gate(workspace_task_id)
                if not _gate_report["passed"]:
                    _fails = [r for r in _gate_report["results"] if r["status"] == "FAIL"]
                    _fail_summary = "; ".join(f"{r['gate']}: {r.get('reason', 'failed')}" for r in _fails)
                    result.error = (
                        f"PRE-PUBLISH GATE BLOCKED: {_gate_report['fail_count']} mandatory gate(s) failed. "
                        f"Failures: {_fail_summary}. "
                        f"Fix the failures before retrying wp_publisher."
                    )
                    print(result.error, file=sys.stderr)
                    return result
                else:
                    _warns = [r for r in _gate_report["results"] if r["status"] == "WARN"]
                    if _warns:
                        for w in _warns:
                            print(f"  ⚠ {w['gate']}: {w.get('reason', 'advisory')}", file=sys.stderr)
                    print("  Pre-publish artifact gate: all mandatory checks passed.", file=sys.stderr)
            except ImportError:
                print("⚠ pre_publish_gate not available (non-fatal)", file=sys.stderr)
            except Exception as _pg_err:
                print(f"⚠ pre-publish gate check failed (non-fatal): {_pg_err}", file=sys.stderr)

        # ── Step 1: Parse / extract ───────────────────────
        frontmatter, body = split_frontmatter(inp.draft_markdown)

        # ── Step 2: Resolve categories ─────────────────────
        # Fast path (2026-05-23d): if meta.json has pre-resolved category_ids[] from
        # the category_selector (which uses the local categories-live.json snapshot),
        # use those directly. Avoids N GET /wp/v2/categories?slug=X round-trips per
        # publish. Falls through to slow name-resolution path when ID cache is absent
        # (e.g. project hasn't run `python -m scripts.wordpress.snapshot_categories`).
        cat_terms, cat_missing = ([], [])
        pre_resolved_cat_ids = inp.meta.get("category_ids") if inp.meta else None
        if pre_resolved_cat_ids and isinstance(pre_resolved_cat_ids, list) and all(
            isinstance(x, int) for x in pre_resolved_cat_ids
        ):
            # Build minimal Term-like wrapper so downstream `[t.id for t in cat_terms]` works
            from types import SimpleNamespace
            cat_terms = [SimpleNamespace(id=cid, name=n) for cid, n in zip(
                pre_resolved_cat_ids, inp.categories or [f"id={cid}" for cid in pre_resolved_cat_ids]
            )]
            print(
                f"✓ Categories pre-resolved from snapshot: {pre_resolved_cat_ids} "
                f"(skipped {len(pre_resolved_cat_ids)} WP REST round-trips)",
                file=sys.stderr,
            )
        elif inp.categories:
            cat_terms, cat_missing = wp_taxonomy.get_or_create_terms(
                wp, inp.site_slug, "categories", inp.categories,
                create_missing=(inp.allow_create_categories and not dry_run),
            )
            if cat_missing:
                # HARD ABORT (2026-07-11): resolve-only by default. Creating here
                # mints a parentless top-level category (the &-entity dup incident);
                # proceeding without it silently drops an editorial decision. Both
                # are worse than failing loudly before any WP write happens.
                result.error = (
                    f"CATEGORY RESOLUTION FAILED: {cat_missing} not found on "
                    f"{inp.site_slug} and publish-time category creation is disabled "
                    f"(allow_create_categories=False). Fix the category name in "
                    f"meta.json, or create the term deliberately via "
                    f"`python -m scripts.wordpress.setup_categories {inp.site_slug}` / "
                    f"`python -m scripts.wordpress.wp_taxonomy {inp.site_slug} "
                    f"--resolve-categories \"...\"`, then re-run. "
                    f"(Check for stale snapshot: scripts.wordpress.snapshot_categories.)"
                )
                print(f"✗ {result.error}", file=sys.stderr)
                if _stage_recorded:
                    try:
                        from scripts._core import file_bus as _fb3
                        _fb3.record_stage_complete(
                            workspace_task_id, "wordpress-publisher", status="failed")
                    except Exception as _e:
                        print(f"⚠ stage_history record failed: {_e}", file=sys.stderr)
                return result

        # ── Step 3: Resolve tags + apply per-tag SEO meta from tags-config.json ─
        tag_terms, tag_missing = ([], [])
        if inp.tags:
            tag_terms, tag_missing = wp_taxonomy.get_or_create_terms(
                wp, inp.site_slug, "tags", inp.tags,
                create_missing=not dry_run,
            )
            if tag_missing:
                print(f"⚠ Could not resolve tags: {tag_missing}", file=sys.stderr)

            # Apply SEO spec (description + RankMath meta) from projects/{slug}/tags-config.json.
            # Strategic tags → full SEO (index + custom title + focus keyword).
            # Known noindex tags → noindex robots + axis-aware description.
            # Unknown organic tags → policy default (noindex + auto-template description).
            if not dry_run and tag_terms:
                try:
                    from scripts.wordpress.tag_seo_resolver import (
                        resolve_tag_seo_spec, apply_tag_seo, check_term_meta_writable,
                    )
                    meta_writable = check_term_meta_writable(wp)
                    seo_summary = {"strategic": 0, "noindex_known": 0, "policy_default": 0, "deferred": 0}
                    for term in tag_terms:
                        spec = resolve_tag_seo_spec(inp.site_slug, term.name)
                        tag_seo_result = apply_tag_seo(wp, term.id, spec, meta_writable)
                        src = spec.get("_source", "unknown")
                        seo_summary[src] = seo_summary.get(src, 0) + 1
                        if tag_seo_result.get("meta_deferred"):
                            seo_summary["deferred"] += 1
                    print(f"  Tag SEO applied: {seo_summary}")
                except Exception as e:
                    print(f"  ⚠ Tag SEO application failed (non-fatal): {e}", file=sys.stderr)

        # ── Step 4: Upload images (skipped in defer_images mode) ─────
        slot_to_media: dict[str, wp_media.WPMedia] = {}
        featured_id: int | None = None

        if not dry_run and not inp.defer_images:
            for img in inp.images:
                path = Path(img["path"])
                try:
                    m = wp_media.upload(
                        wp, path,
                        alt_text=img.get("alt", ""),
                        caption=img.get("caption", ""),
                        title=img.get("title", ""),
                        description=img.get("description", ""),
                        check_existing_by_filename=True,
                        # Default WebP conversion + size-cap (wp_media.DEFAULT_UPLOAD_FORMAT).
                        # Per-image opt-out via images.json "upload_format": "original"/"png"/"jpeg".
                        upload_format=img.get("upload_format", ""),
                    )
                except Exception as e:
                    result.error = f"Media upload failed for {path}: {e}"
                    return _rollback(wp, result, slot_to_media, rollback_on_failure)
                slot_to_media[img["slot_id"]] = m
                result.media_ids.append(m.id)
                if img.get("is_featured"):
                    featured_id = m.id

            # Featured fallback (2026-07-01): if NO images.json entry carried
            # is_featured (the flag doubles as a placeholder-lint exclusion hint in
            # image-prompts.json and false can propagate down — post 788 shipped
            # featured_media=0), fall back to the cover slot. A post with a cover
            # image but no featured_media is always a bug, never an intent.
            if featured_id is None and slot_to_media:
                from scripts._core.image_prompts import is_cover_slot
                for _slot, _m in slot_to_media.items():
                    if is_cover_slot(_slot):
                        featured_id = _m.id
                        print(f"  ⚠ no images.json entry marked is_featured — "
                              f"falling back to cover slot '{_slot}' (media {_m.id})",
                              file=sys.stderr)
                        break

        # ── Step 5a: Replace image placeholders in markdown body ─────
        # (Only when we have real media URLs — produces ![alt](url) which is valid MD)
        #
        # Whether to include the is_featured cover image in body placement depends
        # on the PROJECT's featured_image_inline_policy.mode:
        #   - "no_inline" (default): theme auto-renders featured_media at top, so
        #     skipping the cover from body avoids a visible duplicate.
        #   - "inline": theme does NOT auto-render featured_media (project-charlie
        #     after 2026-05-21 theme update), so cover MUST be placed inline in
        #     body, otherwise the [IMAGE-SLOT-cover] placeholder leaks as literal
        #     text (the 2026-05-21 task 085fb1ba240c bug).
        #   - "manual": operator-controlled; treat same as "inline" (placeholder
        #     in body = honor it).
        feat_inline_policy_mode = _resolve_featured_inline_policy_mode(inp.site_slug)
        if feat_inline_policy_mode in ("inline", "manual"):
            body_images = list(inp.images)  # include featured in body replacement
        else:
            body_images = [img for img in inp.images if not img.get("is_featured")]
        if slot_to_media:
            body = _replace_image_placeholders(body, slot_to_media, body_images)

        # ── Step 5b: Auto-append References section from citations.json ──────
        # If the draft does not already have a References block in ANY supported
        # shape (markdown / raw HTML / escaped HTML), append one generated from
        # citations.json. Uses the robust `_has_existing_references_block()`
        # detector — the legacy string match `"## References" not in body` was
        # caught by audit 2026-05-22 as the same weak-gate pattern that allowed
        # double-references and silent skips in past incidents.
        if workspace_task_id and not _has_existing_references_block(body):
            body = _append_references_from_citations(body, workspace_task_id)

        # ── Step 5c: Apply [claim:cN_S] → (Author, Year) inline citations ─────
        # Defense-in-depth layer 1 for the claim-marker-leak class of bug.
        # Replaces every [claim:c1_section] in body with the matching
        # (Author, Year) parenthetical derived from citations.json. If the
        # upstream assembly step (scripts/build/assemble.py:_replace_claims)
        # already ran, this is a no-op. Layer 2 = render_lint L5 detector;
        # layer 3 = verify_post check 22. See feedback_claim_marker_leak_systemic.md.
        if workspace_task_id and "[claim:" in body:
            body = _apply_in_text_citations(body, workspace_task_id)

        # ── Step 5d: Strip raw section JSON envelopes (defense-in-depth) ──
        # If the orchestrator pasted raw sections/*.json content instead of
        # extracting the markdown field via assemble.py, the body contains
        # JSON objects with keys like section_index, claims, citation_capsule,
        # self_check. Detect and remove them before markdown→HTML conversion.
        body = _strip_section_json_envelopes(body)

        # ── Step 5e: Strip writer-side scaffold annotation tokens ──
        # [ORIGINAL DATA] / [UNIQUE INSIGHT] / [PERSONAL EXPERIENCE] / ... are
        # author-internal info-gain markers. assemble.py strips them, but the
        # optimize-phase subagents (humanizer / geo-auditor) re-introduce them
        # after assembly. Strip unconditionally in the publish path so they can
        # never reach live HTML (render_lint L6; 2026-06-18 fix A). Canonical
        # regex lives in markdown_to_html.strip_scaffold_markers.
        body, _scaffold_n = strip_scaffold_markers(body)
        if _scaffold_n:
            print(
                f"⚠ wp_publisher: stripped {_scaffold_n} scaffold marker(s) "
                f"(e.g. [ORIGINAL DATA]) before publish",
                file=sys.stderr,
            )

        # ── Step 6: Convert markdown → HTML ────────────────
        opt = ConvertOptions(
            drop_h1=True,                    # WP has separate title
            add_anchor_ids=True,
            wordpress_gutenberg=False,
            image_lazy_loading=True,
            image_srcset=False,  # 2026-05-21: was True; emitted broken -480w/-768w/-1024w variants. WP regenerates srcset natively from registered sizes that actually exist. See [[feedback_markdown_pitfalls_publisher_three_bugs]].
            pretty=True,
            site_url=wp.creds.url,
        )
        html = md_to_html(body, opt)

        # ── Step 6.5: Inject HTML placeholders for defer-images mode ────
        # Done in HTML domain so markdown_it doesn't escape <figure>
        if inp.defer_images and not slot_to_media:
            html = _insert_image_placeholders_pending_html(html, inp.images)

        # ── Step 6.6: Wrap <img> tags in <figure><figcaption> using image metadata ──
        # Ensures captions render visibly under each image (plain <img> does not).
        if slot_to_media:
            _img_align, _img_lightbox = _resolve_inline_image_display(inp.site_slug)
            html = _wrap_images_in_figures(
                html, body_images, slot_to_media,
                align=_img_align, lightbox=_img_lightbox,
            )

        # ── Step 6.65: Tag structural paragraphs with safe classes ──
        # Adds class="faq-question" and class="article-signature" only when the <p>
        # truly contains a single element with no surrounding text. The article CSS
        # uses these classes instead of the :only-child pseudo-class (which ignores
        # text nodes and would otherwise misfire on every inline <em>/<strong>).
        html = _tag_structural_paragraphs(html)

        # Tag typed callouts + pull-quotes by their leading bold label / quote mark, so the
        # article CSS can style them (authors write native `> **Warning:** ...` markdown; the
        # class is added here on the rendered HTML). Mirrors _tag_structural_paragraphs.
        html = _tag_callouts_and_pullquotes(html)

        # Tag heading-adjacent component blocks (stat grid / TL;DR / At-a-Glance /
        # glossary / checklist) with stable classes via the SHARED classifier
        # scripts/_core/component_headings (2026-07-01). Class selectors make the
        # component CSS immune to anchor dedup (#by-the-numbers-2), topic-scoped
        # headings, variant phrasing ("This Week at a Glance") and localization —
        # the exact-id adjacency selectors left ALL 4 stat grids of the 2026-07-01
        # batch unstyled.
        from scripts._core.component_headings import tag_component_blocks
        html = tag_component_blocks(html)

        # ── Step 6.7: Apply project article CSS + wrapper for visual styling ──
        # Reads projects/{slug}/brand/article-css.css if present; wraps body in
        # <div class="{slug}-pillar"> and prepends inline <style>. The whole content
        # is wrapped in a single <!-- wp:html --> block so WordPress preserves it
        # verbatim (otherwise wpautop strips <p> tags from classic content).
        html = _apply_project_styling(html, inp.site_slug)

        # ── Step 6.8: Append custom JSON-LD schema blocks OUTSIDE the wrapper ──
        # If workspace/{task}/schema.json exists, append each block's ld_json as
        # <script type="application/ld+json"> AFTER the closing </div> / wp:html.
        # Custom blocks (Dataset, HowTo, FAQPage, etc.) supplement RankMath's
        # auto-generated BlogPosting + Organization + BreadcrumbList.
        if workspace_task_id:
            html = _append_custom_schema_blocks(html, workspace_task_id, site_slug=wp.site_slug)

        # Save final.html to workspace if requested
        if workspace_task_id:
            try:
                ws = file_bus.get_workspace(workspace_task_id)
                (ws / "final.html").write_text(html, encoding="utf-8")
            except Exception:
                pass  # non-blocking

        if dry_run:
            result.success = True
            result.status = "dry_run"
            print("=== DRY RUN ===")
            print(f"Title: {inp.meta.get('title')}")
            print(f"Slug: {inp.meta.get('slug')}")
            print(f"Categories: {[t.name for t in cat_terms]}")
            print(f"Tags: {[t.name for t in tag_terms]}")
            print(f"Media uploaded (skipped): {len(inp.images)}")
            print(f"HTML body: {len(html)} chars")
            print(f"Featured image: {featured_id}")
            return result

        # ── Step 7a: Create-or-Update post draft (idempotent re-publish) ─
        # Idempotency check (2026-05-23, hardened 2026-05-23b):
        # The local publish-result.json is a HINT, not a source of truth. WP is the
        # actual source of truth. So: load the hint, then VERIFY against WP via
        # GET /wp/v2/posts/{id} before deciding to PATCH. If the hint is stale
        # (post deleted manually or by cleanup), fall through to fresh-create
        # rather than 404-ing inside the PATCH path and triggering rollback.
        #
        # Without the GET verification, the bug pattern was:
        #   1. publish → publish-result.json saved, post_id=37362
        #   2. user (or repair script) deletes post 37362 from WP UI
        #   3. re-publish → publisher reads stale post_id, tries PATCH /posts/37362
        #   4. WP returns 404 → exception → rollback → no post created
        #   5. user has to manually delete publish-result.json + retry
        # With GET verification, step 3 detects the ghost and proceeds to POST.
        existing_post_id: int | None = None
        if workspace_task_id:
            try:
                from scripts._core import file_bus as _fb
                _existing_pr = _fb.read_artifact(workspace_task_id, "publish-result.json")
                if _existing_pr and isinstance(_existing_pr, dict):
                    _pid = _existing_pr.get("post_id")
                    if isinstance(_pid, int) and _pid > 0:
                        # VERIFY against WP — local hint may be stale (manual delete, rollback, etc.)
                        try:
                            wp.get(
                                f"/wp/v2/posts/{_pid}",
                                params={"context": "edit", "status": "any"},
                            )
                            # 200 OK → post exists on WP, safe to PATCH
                            existing_post_id = _pid
                            print(
                                f"↻ Idempotent re-publish detected: workspace already published as post {_pid} "
                                f"(verified on WP). Using PATCH instead of POST to preserve canonical slug "
                                f"and avoid ghost post.",
                                file=sys.stderr,
                            )
                        except Exception as _verify_err:
                            # Most likely WPNotFoundError (404). Other exceptions also fall through
                            # to fresh-create — better to publish a new post than crash mid-publish.
                            _err_kind = type(_verify_err).__name__
                            print(
                                f"  (idempotency check: local publish-result.json points at post {_pid}, "
                                f"but WP returned {_err_kind} — post was deleted or never reached WP. "
                                f"Removing stale publish-result.json and falling through to fresh CREATE.)",
                                file=sys.stderr,
                            )
                            # Delete stale local hint so future retries don't loop
                            try:
                                ws_dir = file_bus.get_workspace(workspace_task_id)
                                stale_pr = ws_dir / "publish-result.json"
                                if stale_pr.exists():
                                    stale_pr.unlink()
                            except Exception:
                                pass  # non-blocking; the GET will re-check next run
                            existing_post_id = None
            except Exception as _e:
                # Fall through to fresh-create path on any read error
                print(f"  (idempotency check: prior publish-result not readable: {type(_e).__name__})", file=sys.stderr)

        post_payload = {
            "title": inp.meta.get("title") or inp.meta.get("seo_title") or inp.meta.get("rank_math_title") or "Untitled",
            "content": html,
            "excerpt": inp.meta.get("excerpt", ""),
            "status": "draft",
            "categories": [t.id for t in cat_terms],
            "tags": [t.id for t in tag_terms],
        }
        if featured_id is not None:
            post_payload["featured_media"] = featured_id
        slug = inp.meta.get("slug", "")

        try:
            if existing_post_id is not None:
                # PATCH existing post — preserves canonical slug, no ghost
                post_payload["slug"] = slug
                r = wp.post(f"/wp/v2/posts/{existing_post_id}", json_body=post_payload)
            else:
                # First publish — POST creates new. The slug is deliberately NOT
                # in the create payload: core's REST create_item() pre-uniquifies
                # a draft slug via wp_unique_post_slug( $prepared_post->id, ... )
                # on properties that never exist during a create, emitting two
                # PHP warnings per publish. The update path has no such block,
                # so the slug is applied in an immediate follow-up request.
                r = wp.post("/wp/v2/posts", json_body=post_payload)
                if slug:
                    r = wp.post(f"/wp/v2/posts/{r.json_data['id']}", json_body={"slug": slug})
            post = r.json_data
            result.post_id = post["id"]
            result.featured_media_id = featured_id
        except WPApiError as e:
            result.error = f"Post {'update' if existing_post_id else 'creation'} failed: {e}"
            return _rollback(wp, result, slot_to_media, rollback_on_failure)

        # ── Step 7b: Set SEO meta (Yoast OR Rank Math) ─────
        if h.get("yoast_mu_plugin"):
            _set_yoast_meta(wp, result.post_id, inp.meta, result)
        elif h.get("rankmath_bridge"):
            _set_rankmath_meta(wp, result.post_id, inp.meta, featured_id, result)
        else:
            # Neither MU-plugin installed — surface a clear warning
            if h.get("seo_plugin") == "rankmath":
                print(
                    "⚠ Rank Math detected but bridge MU-plugin not installed. "
                    "SEO meta will be skipped. Install "
                    "install/wordpress-mu-plugin/xuanran-rank-math-rest-bridge.php "
                    "to wp-content/mu-plugins/ on the target site.",
                    file=sys.stderr,
                )
            elif h.get("seo_plugin") == "yoast":
                print(
                    "⚠ Yoast detected but bridge MU-plugin not installed. "
                    "SEO meta will be skipped.",
                    file=sys.stderr,
                )

        # ── Step 7c: Publish ───────────────────────────────
        if inp.status != "draft":
            try:
                r = wp.patch(f"/wp/v2/posts/{result.post_id}", json_body={"status": inp.status})
                published = r.json_data
                result.post_url = published.get("link")
                result.status = inp.status
            except WPApiError as e:
                result.error = f"Publish failed: {e}"
                return _rollback(wp, result, slot_to_media, rollback_on_failure)
        else:
            # Stayed as draft
            result.status = "draft"
            result.post_url = f"{wp.creds.url}/?p={result.post_id}&preview=true"

        # ── Step 7d: Write pending-images sidecar (defer_images mode) ───
        if inp.defer_images:
            _write_pending_images_sidecar(
                inp.site_slug, result.post_id, inp.images, inp.task_id,
            )

        # ── Step 8: change-log + workspace artifact ─────────
        result.success = True
        result.duration_seconds = round(time.time() - t_start, 2)

        # Refresh internal-links-map.md from the live inventory (Rule 6 cure,
        # 2026-07-17: every doc layer claimed "populated by the publisher" but no
        # code ever wrote it — the linker had zero blog-to-blog targets). The
        # tool only lists status=publish posts, so a draft-create is a no-op
        # refresh. Best-effort: a map-sync failure must never fail the publish.
        try:
            from scripts.wordpress.sync_links_map import sync_links_map
            sync_links_map(inp.site_slug)
        except Exception as _lm_e:
            print(f"⚠ internal-links-map sync skipped: {_lm_e}", file=sys.stderr)

        _write_change_log(inp.site_slug, result, post_payload)
        if workspace_task_id:
            try:
                ws = file_bus.get_workspace(workspace_task_id)
                (ws / "publish-result.json").write_text(
                    json.dumps(asdict(result), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass

        # ── Stage tracking completion (audit 2026-05-22) ──────────────
        if _stage_recorded:
            try:
                from scripts._core import file_bus as _fb
                _fb.record_stage_complete(
                    workspace_task_id,
                    "wordpress-publisher",
                    status="completed",
                )
            except Exception as _e:
                print(
                    f"⚠ stage_history record_stage_complete failed: {_e}",
                    file=sys.stderr,
                )

        return result


# ─── Helpers ──────────────────────────────────────────

_SECTION_ENVELOPE_KEYS = frozenset({
    "section_index", "citation_capsule", "claims", "self_check",
    "information_gain_markers", "generated_at", "agent_model",
})


def _strip_section_json_envelopes(body: str) -> str:
    """Strip raw section/*.json envelope content that leaked into the body.

    When the orchestrator skips assemble.py and pastes raw section JSON instead
    of extracting the markdown field, the body contains JSON objects with keys
    like section_index, claims, citation_capsule. We detect valid JSON objects
    containing these distinctive keys and remove them.
    """
    if '"section_index"' not in body:
        return body

    decoder = json.JSONDecoder()
    removals: list[tuple[int, int]] = []
    pos = 0
    while True:
        idx = body.find('{', pos)
        if idx == -1:
            break
        if '"section_index"' not in body[idx:idx + 200]:
            pos = idx + 1
            continue
        try:
            obj, end_idx = decoder.raw_decode(body, idx)
            if isinstance(obj, dict) and 'section_index' in obj and (
                len(set(obj.keys()) & _SECTION_ENVELOPE_KEYS) >= 2
            ):
                removals.append((idx, end_idx))
                pos = end_idx
                continue
        except (json.JSONDecodeError, ValueError):
            pass
        pos = idx + 1

    if not removals:
        return body

    result = body
    for start, end in reversed(removals):
        result = result[:start].rstrip() + '\n\n' + result[end:].lstrip()

    print(
        f"⚠ _strip_section_json_envelopes: removed {len(removals)} raw section JSON "
        f"envelope(s) from body — the orchestrator likely skipped assemble.py",
        file=sys.stderr,
    )
    return result


def _replace_image_placeholders(
    body: str,
    slot_to_media: dict[str, "wp_media.WPMedia"],
    images: list[dict],
) -> str:
    """Replace [IMAGE-SLOT-N] and placeholder:// URLs in markdown body."""
    for img in images:
        slot_id = img["slot_id"]
        if slot_id not in slot_to_media:
            continue
        media = slot_to_media[slot_id]
        # Pattern 1: [IMAGE-SLOT-cover] / [IMAGE-SLOT-section_1] etc.
        placeholder_token = f"[IMAGE-SLOT-{slot_id}]"
        if placeholder_token in body:
            alt = img.get("alt", "")
            md_img = f"![{alt}]({media.source_url})"
            body = body.replace(placeholder_token, md_img)
        # Pattern 2: ![alt](placeholder://slot-N)
        ph_url = f"placeholder://slot-{slot_id}"
        body = body.replace(ph_url, media.source_url)
    # Defense-in-depth: strip any remaining [IMAGE-SLOT-*] markers
    import re as _re_img
    body = _re_img.sub(r'\[IMAGE-SLOT-[^\]]+\]', '', body)
    return body


def _set_yoast_meta(wp, post_id, meta: dict, result) -> None:
    """Set Yoast meta via MU-plugin endpoint /yoast/v1/posts/{id}."""
    yoast_payload = {
        "focus_keyphrase": meta.get("focus_keyphrase", ""),
        "seo_title": meta.get("seo_title", meta.get("title", "")),
        "meta_description": meta.get("meta_description", meta.get("excerpt", "")),
    }
    for k_meta, k_yoast in [
        ("og_title", "opengraph_title"),
        ("og_description", "opengraph_desc"),
        ("twitter_title", "twitter_title"),
        ("twitter_description", "twitter_desc"),
        ("canonical_url", "canonical"),
    ]:
        if k_meta in meta:
            yoast_payload[k_yoast] = meta[k_meta]
    try:
        wp.post(f"/yoast/v1/posts/{post_id}", json_body=yoast_payload)
        result.yoast_set = True
        result.seo_plugin_used = "yoast"
    except WPApiError as e:
        print(f"⚠ Yoast meta set failed (non-fatal): {e}", file=sys.stderr)


def _set_rankmath_meta(wp, post_id, meta: dict, featured_media_id, result) -> None:
    """Set Rank Math meta via core /wp/v2/posts/{id} with `meta` field.

    Requires the Xuanran Rank Math REST Bridge MU-plugin installed on target site.

    Rank Math meta keys (per official RM support + register_post_meta in bridge):
      - rank_math_title             string
      - rank_math_description       string
      - rank_math_focus_keyword     string (comma-separated, NOT array!)
      - rank_math_canonical_url     string (URL)
      - rank_math_robots            array of enum strings, valid values ONLY:
                                     ["index","noindex","nofollow","noarchive",
                                      "noimageindex","nosnippet"] -- "follow" is
                                     NOT valid (implicit default; sending it 400s
                                     the whole POST, root CLAUDE.md Rule 3)
      - rank_math_advanced_robots   object {"max-snippet":"-1", ...}
      - rank_math_primary_category  int (term ID)
      - rank_math_breadcrumb_title  string
      - rank_math_pillar_content    "on" | "" (string-as-bool)
      - rank_math_facebook_*        string (OpenGraph)
      - rank_math_twitter_*         string
    """
    payload_meta: dict = {}

    # Core fields — fall back to title/excerpt if dedicated SEO fields not set
    title = meta.get("seo_title") or meta.get("title", "")
    if title:
        payload_meta["rank_math_title"] = title

    description = meta.get("meta_description") or meta.get("excerpt", "")
    if description:
        payload_meta["rank_math_description"] = description

    focus = meta.get("focus_keyphrase") or meta.get("rank_math_focus_keyword") or ""
    if isinstance(focus, list):
        # Defensive: if caller passes a list (Yoast-style), join with comma
        focus = ", ".join(str(k) for k in focus if k)
    if focus:
        payload_meta["rank_math_focus_keyword"] = focus

    if meta.get("canonical_url"):
        payload_meta["rank_math_canonical_url"] = meta["canonical_url"]

    if meta.get("breadcrumb_title"):
        payload_meta["rank_math_breadcrumb_title"] = meta["breadcrumb_title"]

    if meta.get("pillar_content"):
        payload_meta["rank_math_pillar_content"] = "on"

    # Robots — array; "follow" is not a valid enum value (it's the implicit
    # default), sending it 400s the whole POST (root CLAUDE.md Rule 3) — the
    # `valid` filter below silently drops it if a caller passes it anyway.
    robots = meta.get("robots") or meta.get("rank_math_robots")
    if isinstance(robots, list) and robots:
        valid = {"index", "noindex", "nofollow", "noarchive", "noimageindex", "nosnippet"}
        payload_meta["rank_math_robots"] = [r for r in robots if r in valid]

    # Advanced robots
    if isinstance(meta.get("advanced_robots"), dict):
        ar = meta["advanced_robots"]
        clean_ar = {
            k: str(v) for k, v in ar.items()
            if k in ("max-snippet", "max-video-preview", "max-image-preview")
        }
        if clean_ar:
            payload_meta["rank_math_advanced_robots"] = clean_ar

    # Primary category — default to first category_ids[] when unset (2026-05-26 fix)
    if isinstance(meta.get("primary_category"), int):
        payload_meta["rank_math_primary_category"] = meta["primary_category"]
    elif isinstance(meta.get("category_ids"), list) and meta["category_ids"]:
        payload_meta["rank_math_primary_category"] = meta["category_ids"][0]

    # Social — OpenGraph (Facebook)
    if meta.get("og_title"):
        payload_meta["rank_math_facebook_title"] = meta["og_title"]
    if meta.get("og_description"):
        payload_meta["rank_math_facebook_description"] = meta["og_description"]
    if meta.get("og_image"):
        payload_meta["rank_math_facebook_image"] = meta["og_image"]
    elif featured_media_id:
        # Default OG image = featured image
        payload_meta["rank_math_facebook_image_id"] = featured_media_id

    # Social — Twitter
    if meta.get("twitter_use_facebook"):
        payload_meta["rank_math_twitter_use_facebook"] = "on"
    if meta.get("twitter_card_type"):
        payload_meta["rank_math_twitter_card_type"] = meta["twitter_card_type"]
    else:
        # Sensible default for large image with summary card
        if featured_media_id or meta.get("og_image"):
            payload_meta["rank_math_twitter_card_type"] = "summary_large_image"
    if meta.get("twitter_title"):
        payload_meta["rank_math_twitter_title"] = meta["twitter_title"]
    if meta.get("twitter_description"):
        payload_meta["rank_math_twitter_description"] = meta["twitter_description"]
    if meta.get("twitter_image"):
        payload_meta["rank_math_twitter_image"] = meta["twitter_image"]

    if not payload_meta:
        return  # nothing to set

    try:
        wp.post(f"/wp/v2/posts/{post_id}", json_body={"meta": payload_meta})
        result.rankmath_set = True
        result.seo_plugin_used = "rankmath"

        # Verify round-trip: re-fetch and confirm keys landed
        r_verify = wp.get(f"/wp/v2/posts/{post_id}",
                          params={"_fields": "meta", "context": "edit"})
        saved_meta = (r_verify.json_data or {}).get("meta", {}) or {}
        missing = [k for k in payload_meta if k not in saved_meta or saved_meta[k] in ("", None, [])]
        if missing:
            print(
                f"⚠ Rank Math: {len(missing)} fields not echoed back by WP "
                f"(likely register_post_meta schema mismatch): {missing}",
                file=sys.stderr,
            )
    except WPApiError as e:
        print(f"⚠ Rank Math meta set failed (non-fatal): {e}", file=sys.stderr)


def _insert_image_placeholders_pending_html(html: str, images: list[dict]) -> str:
    """Replace literal [IMAGE-SLOT-N] tokens IN HTML output with placeholder figures.

    Runs AFTER markdown→HTML conversion. The markdown converter leaves
    [IMAGE-SLOT-N] strings untouched (no special meaning in markdown), and they
    typically end up wrapped in <p>…</p>. We replace those occurrences with
    proper HTML <figure> blocks the attach script can later find via data-slot.
    """
    import html as _html
    import re
    for img in images:
        slot_id = img.get("slot_id", "")
        alt = _html.escape(img.get("alt", ""))
        token = f"[IMAGE-SLOT-{slot_id}]"
        # Match the token whether wrapped in <p>…</p> by markdown or standalone
        figure_html = (
            f'<figure class="xuanran-pending-image" '
            f'data-slot="{_html.escape(slot_id)}" data-alt="{alt}">\n'
            f'  <div class="xuanran-image-placeholder" '
            f'style="background:#f5f5f5;padding:80px 20px;text-align:center;'
            f'color:#888;border:2px dashed #ccc;border-radius:6px;font-family:sans-serif;">'
            f'<strong>Image pending</strong><br>'
            f'<small style="opacity:0.7;">slot: {_html.escape(slot_id)}</small>'
            f'</div>\n'
            f'</figure>'
        )
        # If the token is wrapped in a paragraph alone, swallow the paragraph
        html = re.sub(
            r'<p[^>]*>\s*' + re.escape(token) + r'\s*</p>',
            figure_html,
            html,
        )
        # Otherwise plain replacement
        html = html.replace(token, figure_html)
    return html


def _insert_image_placeholders_pending(body: str, images: list[dict]) -> str:
    """Replace [IMAGE-SLOT-N] markers with visible HTML placeholders detectable later.

    The placeholder structure is:
      <figure class="xuanran-pending-image" data-slot="{slot}" data-alt="{alt}">
        <div class="xuanran-image-placeholder">
          Image pending — slot: {slot}
        </div>
      </figure>

    `attach_images_to_draft.py` finds these via data-slot attribute and replaces
    them with proper <figure><img></figure> blocks once images are ready.
    """
    import html as _html
    for img in images:
        slot_id = img.get("slot_id", "")
        alt = _html.escape(img.get("alt", ""))
        token = f"[IMAGE-SLOT-{slot_id}]"
        if token not in body:
            continue
        replacement = (
            f'\n<figure class="xuanran-pending-image" '
            f'data-slot="{_html.escape(slot_id)}" data-alt="{alt}">\n'
            f'  <div class="xuanran-image-placeholder" '
            f'style="background:#f5f5f5;padding:80px 20px;text-align:center;'
            f'color:#888;border:2px dashed #ccc;border-radius:6px;font-family:sans-serif;">'
            f'<strong>Image pending</strong><br>'
            f'<small style="opacity:0.7;">slot: {_html.escape(slot_id)}</small>'
            f'</div>\n'
            f'</figure>\n'
        )
        body = body.replace(token, replacement)
    return body


def _write_pending_images_sidecar(
    site_slug: str, post_id: int | None, images: list[dict], task_id: str | None,
) -> None:
    """Write projects/{slug}/.seo/pending-images.json so attach script knows what to do.

    Structure:
      {
        "pending": [
          {
            "post_id": 123,
            "task_id": "abc",
            "created_at": "...",
            "slots": [
              {"slot_id": "cover", "alt": "...", "image_path": null, "is_featured": true},
              ...
            ]
          }
        ]
      }
    """
    if post_id is None:
        return
    from scripts._core.file_bus import PLUGIN_ROOT
    sidecar = PLUGIN_ROOT / "projects" / site_slug / ".seo" / "pending-images.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {"pending": []}
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            if "pending" not in data:
                data["pending"] = []
        except Exception:
            data = {"pending": []}

    entry = {
        "post_id": post_id,
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "awaiting_images",
        "slots": [
            {
                "slot_id": img.get("slot_id", ""),
                "alt": img.get("alt", ""),
                "caption": img.get("caption", ""),
                "title": img.get("title", ""),
                "is_featured": img.get("is_featured", False),
                "image_path": img.get("path"),  # may be null if not yet generated
            }
            for img in images
        ],
    }
    data["pending"].append(entry)
    sidecar.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _rollback(
    wp: WPClient,
    result: PublishResult,
    slot_to_media: dict[str, "wp_media.WPMedia"],
    do_rollback: bool,
) -> PublishResult:
    """Delete uploaded media if publish failed mid-way."""
    if not do_rollback:
        return result
    result.rollback_attempted = True
    failed = 0
    for media in slot_to_media.values():
        try:
            wp_media.delete_media(wp, media.id, force=True)
        except Exception:
            failed += 1
    result.rollback_succeeded = (failed == 0)
    return result


def _write_change_log(site_slug: str, result: "PublishResult", payload: dict) -> None:
    """Append a change-log entry for 7-day undo."""
    from scripts._core.file_bus import PLUGIN_ROOT
    log_file = PLUGIN_ROOT / "projects" / site_slug / ".seo" / "change-log.json"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    entries = []
    if log_file.exists():
        try:
            entries = json.loads(log_file.read_text(encoding="utf-8"))
        except Exception:
            entries = []

    import secrets
    change_id = f"ch-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{secrets.token_hex(4)}"
    result.change_log_entry_id = change_id

    entries.append({
        "change_id": change_id,
        "action": "publish" if result.status == "publish" else "create-draft",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc).timestamp() + 7 * 86400),
        "site_slug": site_slug,
        "post_id": result.post_id,
        "post_url": result.post_url,
        "status": result.status,
        "media_ids": result.media_ids,
        "featured_media_id": result.featured_media_id,
        "rollback_data": {
            "previous_status": None,  # new post, nothing to roll back to
        },
    })

    log_file.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


# ─── CLI ──────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="WP publish orchestrator")
    ap.add_argument("site_slug")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--workspace", help="Task ID — load draft/meta/images from memory/workspace/{task}/")
    g.add_argument("--draft", type=Path, help="Direct draft.md path")
    ap.add_argument("--meta", type=Path, help="meta.json path (used with --draft)")
    ap.add_argument("--images", type=Path, help="images.json path (used with --draft)")
    ap.add_argument("--status", choices=["publish", "draft", "private"], default="draft",
                    help="Default 'draft' (safe). Use --status=publish to go live immediately — "
                         "requires explicit user confirmation per project conventions.")
    ap.add_argument("--defer-images", action="store_true",
                    help="B flow: create draft now without images, attach via attach_images_to_draft later")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-rollback", action="store_true")
    ap.add_argument("--allow-http", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--allow-create-categories", action="store_true",
                    help="Explicit opt-in: create missing categories at publish time. "
                         "OFF by default — the taxonomy is curated at init; an "
                         "unresolvable name aborts the publish (2026-07-11 root cure "
                         "for the &-entity duplicate-category incident).")
    args = ap.parse_args()

    # Load inputs
    if args.workspace:
        try:
            file_bus.read_state(args.workspace)  # validates workspace exists
            draft_md = file_bus.read_markdown_with_frontmatter(args.workspace, "draft.md")
            meta = file_bus.read_artifact(args.workspace, "meta.json")
            images = []
            images_file = file_bus.get_workspace(args.workspace, create=False) / "images.json"
            if images_file.exists():
                images = json.loads(images_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Error loading workspace: {e}", file=sys.stderr)
            return 2
        draft_text = file_bus.serialize_frontmatter(draft_md)
        task_id = args.workspace
    else:
        if not args.draft.exists():
            print(f"Not found: {args.draft}", file=sys.stderr)
            return 2
        draft_text = args.draft.read_text(encoding="utf-8")
        meta = {}
        if args.meta and args.meta.exists():
            meta = json.loads(args.meta.read_text(encoding="utf-8"))
        images = []
        if args.images and args.images.exists():
            images = json.loads(args.images.read_text(encoding="utf-8"))
        task_id = None

    inp = PublishInput(
        site_slug=args.site_slug,
        draft_markdown=draft_text,
        meta=meta,
        images=images,
        categories=meta.get("categories", []) if isinstance(meta.get("categories"), list) else [],
        tags=[t.strip() for t in (meta.get("tags") or "").split(",") if t.strip()] if isinstance(meta.get("tags"), str) else (meta.get("tags") or []),
        status=args.status,
        task_id=task_id,
        defer_images=args.defer_images,
        allow_create_categories=args.allow_create_categories,
    )

    # Defer images implies draft status (you can't publish without images)
    if args.defer_images and args.status != "draft":
        print("⚠ --defer-images forces --status=draft (cannot publish without images)", file=sys.stderr)
        inp.status = "draft"

    result = publish(
        inp, dry_run=args.dry_run, allow_http=args.allow_http,
        rollback_on_failure=not args.no_rollback,
        workspace_task_id=task_id,
    )

    if args.json:
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False, default=str))
    else:
        icon = "✓" if result.success else "✗"
        print(f"{icon} Status: {result.status}")
        print(f"  Post ID: {result.post_id}")
        print(f"  URL:     {result.post_url}")
        print(f"  Media:   {len(result.media_ids)} uploaded ({result.featured_media_id} featured)")
        print(f"  Yoast:   {'✓' if result.yoast_set else '✗'}")
        print(f"  Duration: {result.duration_seconds}s")
        if result.error:
            print(f"  ERROR: {result.error}")
            if result.rollback_attempted:
                print(f"  Rollback: {'✓' if result.rollback_succeeded else '✗ partial'}")

    return 0 if result.success else 1


# ─── Article styling + structure helpers (durable post-conversion pipeline) ─────

def _slug_to_wrapper_class(slug: str) -> str:
    """Project slug -> safe CSS class name for the article wrapper."""
    return f"{slug.lower().replace('_', '-').replace('.', '-')}-pillar"


def _load_project_article_css(site_slug: str) -> str | None:
    """Read projects/{slug}/brand/article-css.min.css if present (else article-css.css).

    Returns the CSS text (already minified if .min.css was used) or None.
    """
    repo_root = Path(__file__).resolve().parents[2]
    brand_dir = repo_root / "projects" / site_slug / "brand"
    for fname in ("article-css.min.css", "article-css.css"):
        p = brand_dir / fname
        if p.exists():
            return p.read_text(encoding="utf-8")
    return None


def _minify_css(css: str) -> str:
    """Strip /* */ comments and collapse whitespace (idempotent on already-minified)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    css = re.sub(r"\s+", " ", css).strip()
    return css


def _resolve_featured_inline_policy_mode(site_slug: str) -> str:
    """Resolve featured_image_inline_policy.mode for a project.

    Order of precedence:
      1. projects/{slug}/business-context.json :: featured_image_inline_policy.mode
      2. Plugin default: "no_inline" (most WP themes auto-render featured_media)

    Returns one of: "no_inline" | "inline" | "manual"

    Audit 2026-05-22 (P1) — was previously `except Exception: pass; return default`,
    the exact silent-fallback pattern that hid the 3.3.3 NameError. Now logs
    every fallback to stderr so a future regression is visible.
    """
    try:
        from scripts._core.file_bus import PLUGIN_ROOT
        bc_path = PLUGIN_ROOT / "projects" / site_slug / "business-context.json"
        if not bc_path.exists():
            return "no_inline"  # legitimate: no project config = use default
        bc = json.loads(bc_path.read_text(encoding="utf-8"))
        policy = bc.get("featured_image_inline_policy") or {}
        mode = policy.get("mode")
        if mode in ("no_inline", "inline", "manual"):
            return mode
        # Field present but unexpected value — surface this:
        if mode is not None:
            print(
                f"⚠ _resolve_featured_inline_policy_mode: unexpected mode={mode!r} "
                f"in projects/{site_slug}/business-context.json — falling back to 'no_inline'",
                file=sys.stderr,
            )
    except Exception as e:
        print(
            f"⚠ _resolve_featured_inline_policy_mode: failed to load policy for "
            f"site_slug={site_slug!r}: {type(e).__name__}: {e} — falling back to 'no_inline'",
            file=sys.stderr,
        )
    return "no_inline"


def _resolve_inline_image_display(site_slug: str) -> tuple[str, bool]:
    """Resolve body-image display policy: (align, lightbox).

    Reads projects/{slug}/business-context.json :: image_pipeline_policy:
      - inline_image_align: "default" | "wide" | "full"   (default "default")
      - inline_image_lightbox: bool                        (default False)

    Default = pre-2026-06-29 behaviour (centered size-large, no lightbox), so a
    project is unaffected unless it explicitly opts in. Logs every fallback to
    stderr (same anti-silent-no-op discipline as _resolve_featured_inline_policy_mode).
    """
    align, lightbox = "default", False
    try:
        from scripts._core.file_bus import PLUGIN_ROOT
        bc_path = PLUGIN_ROOT / "projects" / site_slug / "business-context.json"
        if not bc_path.exists():
            return align, lightbox  # legitimate: no project config = use default
        bc = json.loads(bc_path.read_text(encoding="utf-8"))
        policy = bc.get("image_pipeline_policy") or {}
        a = policy.get("inline_image_align")
        if a in ("default", "wide", "full"):
            align = a
        elif a is not None:
            print(
                f"⚠ _resolve_inline_image_display: unexpected inline_image_align={a!r} "
                f"for site_slug={site_slug!r} — using 'default'",
                file=sys.stderr,
            )
        lightbox = bool(policy.get("inline_image_lightbox", False))
    except Exception as e:
        print(
            f"⚠ _resolve_inline_image_display: failed for site_slug={site_slug!r}: "
            f"{type(e).__name__}: {e} — using defaults",
            file=sys.stderr,
        )
    return align, lightbox


def _has_existing_references_block(body: str) -> bool:
    """Detect if the body already contains a References section in ANY supported shape.

    Patterns we accept as already-present (so we don't double-append):
      - Markdown `## References` (any case) at line start
      - Raw HTML `<h2 ...>References</h2>` or `<h2 id="references">...</h2>`
      - Pre-rendered References block written by upstream (e.g. references.md
        included in the assembly step contains the HTML `<h2 id="references">`
        wrapper that markdown-it will pass through if html=True OR escape if
        html=False — we detect both pre-escape AND post-escape forms here).

    This prevents the 2026-05-21 task 085fb1ba240c bug where upstream had
    embedded HTML references but the markdown-it html=False default escaped
    them and the legacy detection only looked for `## References` text — so
    the auto-append silently skipped, leaving the post with NO References.
    """
    # Markdown form (with optional Pandoc anchor {#references} suffix from assembly)
    if re.search(r"^##+\s*References\s*(?:" + heading_anchor.ANCHOR_FRAGMENT + r")?\s*$",
                 body, re.MULTILINE | re.IGNORECASE):
        return True
    # Raw HTML form (most common when upstream produces references.md as HTML)
    if re.search(r"<h2[^>]*>\s*References\s*</h2>", body, re.IGNORECASE):
        return True
    # Escaped HTML form (caught by markdown-it html=False) — same H2 escaped
    if re.search(r"&lt;h2[^&]*?&gt;\s*References\s*&lt;/h2&gt;", body, re.IGNORECASE):
        return True
    return False


def _load_citation_entries(citations_data: dict) -> list[dict]:
    """Normalize citations.json into a flat list of {apa, url, doi, markers} dicts.

    Accepts MULTIPLE legacy/intended shapes (defense-in-depth — audit 2026-05-22
    P4 surfaced that fact-check-and-citation SKILL.md documented `references`
    as the top-level key but the publisher accepted only `refs/citations/items`,
    so any correctly-doc-compliant fact-checker output silently loaded ZERO
    citations):
      - `{"refs": [{"apa": "...", "url": "..."}, ...]}`           (legacy)
      - `{"citations": [{"apa_7": "...", "url": "..."}, ...]}`     (canonical, fact-checker)
      - `{"references": [...]}`                                    (per old SKILL.md doc)
      - `{"items": [...]}`                                         (alt)
      - Top-level list: `[...]`

    `markers` is the per-citation `claim_markers_resolved[]` array (list of
    marker IDs like 'c1_abstract' that point at this citation). Used by
    _apply_in_text_citations to derive the [claim:cN_S] → (Author, Year) map.
    """
    entries = (
        citations_data.get("refs")
        or citations_data.get("citations")
        or citations_data.get("references")
        or citations_data.get("items")
        or (citations_data if isinstance(citations_data, list) else [])
        or []
    )
    out = []
    for r in entries:
        if not isinstance(r, dict):
            continue
        apa = (r.get("apa") or r.get("apa_7") or r.get("apa7") or r.get("citation") or "").strip()
        url = (r.get("url") or r.get("source_url") or "").strip()
        doi = (r.get("doi") or "").strip()
        markers = r.get("claim_markers_resolved") or r.get("markers") or []
        if not isinstance(markers, list):
            markers = []
        if apa or url:
            out.append({"apa": apa, "url": url, "doi": doi, "markers": markers})
    return out


# ──────────────────────────────────────────────────────────────────
# In-text citation replacement (L1 of 5-layer defense for [claim:cN_S]
# marker leak; see feedback_claim_marker_leak_systemic.md). Two-source
# strategy: explicit in_text_replacements[] wins; otherwise derive from
# claim_markers_resolved[] + APA-7 first-author + year.
# ──────────────────────────────────────────────────────────────────

# Recognize a [claim:c1_abstract] or [claim:c1_abstract, c8_ppfd_math] marker.
# Section IDs are often emitted in mixed case by writer agents (e.g. 'c1_S2',
# 'c3_AbstractDef'). IGNORECASE keeps the matcher in sync with render_lint's
# detector and the lookup-side .lower() normalisation in _build_in_text_replacement_map.
_CLAIM_MARKER_RE = re.compile(r"\[claim:([a-z0-9_]+(?:\s*,\s*c[0-9]+_[a-z0-9_]+)*)\]", re.IGNORECASE)
# Inside the [claim:...] group, individual marker IDs look like c1_abstract
_CLAIM_ID_RE = re.compile(r"c\d+_[a-z0-9_]+", re.IGNORECASE)


def _extract_first_author_year(apa: str) -> tuple[str, str] | None:
    """Parse an APA-7 string into (FirstAuthor surname, Year) for inline citation.

    Examples that should parse:
      'Chandra, S., Lata, H., ... (2008). Title. ...' → ('Chandra', '2008')
      'Mitchell, J. F., & Bugbee, B. (2021). ...'    → ('Mitchell & Bugbee', '2021')
      'DesignLights Consortium. (2023). ...'         → ('DesignLights Consortium', '2023')
      'Royal Queen Seeds. (2024). ...'               → ('Royal Queen Seeds', '2024')

    Returns None if it can't parse confidently.
    """
    if not apa:
        return None
    # Match the year inside the first parenthesis even when it carries a month or
    # a disambiguation suffix: '(2021)', '(2021, June)', '(2021, June 5)', '(2021a)'.
    # The old '\((\d{4})\)' only matched a bare 4-digit year, so any APA date with a
    # month (common for industry / standards / web sources, e.g. 'AgSafe BC. (2021, June).')
    # failed to parse → every claim marker pointing at that citation was left
    # unswapped and leaked to render_lint L5 (the 2026-06-03 uvplant incident).
    m_year = re.search(r"\((\d{4})[a-z]?(?:,\s*[^)]*)?\)", apa)
    if m_year:
        year = m_year.group(1)
        year_start = m_year.start()
    else:
        # APA 'no date' form, common on vendor spec sheets: 'Photontek. (n.d.). ...'.
        # Without this, every claim marker citing a datasheet (n.d.) leaked unswapped
        # to render_lint L5 (2026-06-03 cannabisgl incident). Inline form -> '(Author, n.d.)'.
        m_nd = re.search(r"\(\s*n\.?\s*d\.?\s*\)", apa, re.IGNORECASE)
        if not m_nd:
            return None
        year = "n.d."
        year_start = m_nd.start()
    # Keep the trailing period on initials (e.g. 'Bugbee, B.') so the author
    # regex can match it; just strip trailing whitespace.
    head = apa[: year_start].rstrip()
    if not head:
        return None
    # Three patterns to recognise:
    #   'Surname, Initials., Surname2, Initials., & Surname3, Initials.'  (multi-author)
    #   'Surname, Initials., & Surname2, Initials.'                       (two authors)
    #   'Surname, Initials.'                                              (one author)
    #   'Organization Name' (or 'Organization Name. ')                    (no comma+initial)
    # Count author entries via the 'Surname, Initial.' regex. Each match =
    # 1 author. This is more robust than splitting on '&' because peer-reviewed
    # APA-7 uses 'A, B, C, & D' with the ampersand only before the LAST author.
    AUTHOR_ENTRY_RE = re.compile(r"([A-Z][A-Za-z\-']+),\s+([A-Z]\.\s*)+")
    author_matches = AUTHOR_ENTRY_RE.findall(head)
    surnames = [m[0] for m in author_matches]

    if not surnames:
        # No 'Surname, Initials.' pattern found — treat the whole head as an
        # organization name (e.g. 'DesignLights Consortium', 'Royal Queen Seeds').
        org = head.split(",", 1)[0].strip() if "," in head else head
        author_label = org.rstrip(".").strip()
        return author_label, year

    if len(surnames) == 1:
        author_label = surnames[0]
    elif len(surnames) == 2:
        author_label = f"{surnames[0]} & {surnames[1]}"
    else:
        # APA-7: 3+ authors = 'FirstSurname et al.' in in-text citations
        author_label = f"{surnames[0]} et al."
    return author_label, year


def _build_in_text_replacement_map(citations_data: dict) -> dict[str, str]:
    """Build {marker_id: '(Author, Year)'} from citations.json.

    Priority order:
      1. Explicit `in_text_replacements: [{marker, replace_with}, ...]` if present
      2. Derived from each citation's `claim_markers_resolved[]` + APA first-author + year
    """
    out: dict[str, str] = {}
    # Source 1: explicit list (canonical, fact-checker subskill output)
    explicit = citations_data.get("in_text_replacements") or []
    if isinstance(explicit, list):
        for r in explicit:
            if not isinstance(r, dict):
                continue
            # Accept BOTH canonical {marker, replace_with} AND the {from, to}
            # shape some fact-checker subagents emit (docstring in citation_inject
            # promised from/to support but this builder never read those keys →
            # 24/64 markers silently left unresolved on the 2026-06-14 batch).
            marker = (r.get("marker") or r.get("from") or "").strip()
            has_repl_key = any(k in r for k in ("replace_with", "replacement", "to"))
            repl = (r.get("replace_with") or r.get("replacement") or r.get("to") or "").strip()
            # An EXPLICIT empty replacement ('') is a DELIBERATE strip: the
            # fact-checker marked the claim author-experience and wants the marker
            # removed. Record it as '' so downstream deletes the marker cleanly
            # instead of treating it as unresolved and leaving it to leak
            # (2026-06-29 fix; the old `if marker and repl` dropped empty-to
            # entries -> ~12 stragglers per article hand-stripped before render_lint).
            if marker and (repl or has_repl_key):
                # Normalize marker to bare ID (strip leading '[claim:' and trailing ']' if present)
                m = _CLAIM_ID_RE.search(marker)
                if m:
                    out[m.group(0).lower()] = repl
    # Source 2: derive from per-citation claim_markers_resolved + APA parsing
    refs = _load_citation_entries(citations_data)
    for r in refs:
        parsed = _extract_first_author_year(r["apa"])
        if not parsed:
            continue
        author, year = parsed
        inline = f"({author}, {year})"
        for marker_id in r["markers"]:
            mid = str(marker_id).strip().lower()
            # Fact-checker subagents sometimes emit 'claim:cN_x' instead of the
            # bare 'cN_x' contract (2026-06-09 batch: 47 markers silently
            # unmatched until pre_publish_gate caught them). Draft-side IDs are
            # always bare, so normalize here — this map builder is the single
            # source both citation_inject and the publisher L1 defense consume.
            if mid.startswith("claim:"):
                mid = mid[len("claim:"):].strip()
            if mid and mid not in out:
                out[mid] = inline
    return out


def _apply_in_text_citations(body: str, workspace_task_id: str) -> str:
    """Replace [claim:c1_S] markers in markdown body with (Author, Year) inline
    citations derived from citations.json.

    Defense-in-depth Layer 1 of 3 (lint=L2, verify=L3). Even if the upstream
    fact-check-and-citation + assembly stages were skipped, this stage catches
    the leak before markdown→HTML conversion.

    For each `[claim:c1_abstract, c8_ppfd_math]` group:
      - Resolve each c-ID to its (Author, Year) via the marker map
      - Join resolved citations with '; ' inside a single parenthetical
      - Replace the whole [claim:...] group with that parenthetical

    Unresolved markers (no matching citation) are stripped entirely with a
    stderr warning, rather than left in the body — leaving them would defeat
    the purpose of the defense layer.

    Safe to run on bodies that have zero markers (no-op).
    """
    if "[claim:" not in body:
        return body
    try:
        ws = file_bus.get_workspace(workspace_task_id) if workspace_task_id else None
        citations_path = (ws / "citations.json") if ws else None
        if not citations_path or not citations_path.exists():
            # No citations data: strip markers as last-resort safety net
            cleaned = _CLAIM_MARKER_RE.sub("", body)
            print("⚠ in-text citation: citations.json missing — stripped raw [claim:...] markers", file=sys.stderr)
            return cleaned
        data = json.loads(citations_path.read_text(encoding="utf-8"))
        marker_map = _build_in_text_replacement_map(data)
    except Exception as e:
        print(f"⚠ in-text citation: failed to build map ({e}) — stripping markers", file=sys.stderr)
        return _CLAIM_MARKER_RE.sub("", body)

    if not marker_map:
        # No data to resolve with — strip raw markers
        print("⚠ in-text citation: no resolvable markers in citations.json — stripping raw [claim:...] markers", file=sys.stderr)
        return _CLAIM_MARKER_RE.sub("", body)

    unresolved: list[str] = []
    resolved_count = 0

    def _replace(m: "re.Match[str]") -> str:
        nonlocal resolved_count
        inner = m.group(1)
        ids = [s.strip().lower() for s in _CLAIM_ID_RE.findall(inner)]
        if not ids:
            return ""
        resolved = []
        for mid in ids:
            if mid in marker_map:
                resolved.append(marker_map[mid])
            else:
                unresolved.append(mid)
        if not resolved:
            return ""
        # Dedupe while preserving order
        seen, deduped = set(), []
        for r in resolved:
            if r not in seen:
                seen.add(r)
                deduped.append(r)
        resolved_count += 1
        # If only one citation, drop the outer parens-around-parens; otherwise '(A; B; C)'
        if len(deduped) == 1:
            return " " + deduped[0]
        inner_text = "; ".join(c.strip("()") for c in deduped)
        return f" ({inner_text})"

    new_body = _CLAIM_MARKER_RE.sub(_replace, body)
    # Adjacent markers resolving to the same source each emit their own
    # parenthetical — collapse identical neighbours (2026-07-01, shared helper).
    from scripts._core.citation_text import collapse_adjacent_duplicate_citations
    new_body = collapse_adjacent_duplicate_citations(new_body)
    # Cleanup: collapse 'space + space' from the leading-space replacement pattern,
    # and 'space + punctuation' artefacts
    new_body = re.sub(r" {2,}", " ", new_body)
    new_body = re.sub(r" ([.,;:!?])", r"\1", new_body)
    if unresolved:
        uniq = sorted(set(unresolved))
        print(f"⚠ in-text citation: {len(uniq)} unresolved markers stripped: {uniq[:10]}{'…' if len(uniq) > 10 else ''}", file=sys.stderr)
    print(f"✓ in-text citation: {resolved_count} marker group(s) resolved → (Author, Year) inline", file=sys.stderr)
    return new_body


def _append_references_from_citations(body: str, workspace_task_id: str) -> str:
    """If draft body has no References section, append one built from citations.json.

    Reads memory/workspace/{task_id}/citations.json. Supports multiple shapes
    (refs/citations/items/list — see _load_citation_entries). Detects existing
    References in markdown, raw HTML, OR escaped HTML form (see
    _has_existing_references_block).

    Returns body unchanged if a References block already exists, or if no
    citations file is found, or if the file has no usable entries.
    """
    # Skip if References already present in any form
    if _has_existing_references_block(body):
        return body
    try:
        ws = file_bus.get_workspace(workspace_task_id)
        citations_path = ws / "citations.json"
        if not citations_path.exists():
            return body
        data = json.loads(citations_path.read_text(encoding="utf-8"))
        refs = _load_citation_entries(data)
        if not refs:
            return body

        lines = ["", "## References", ""]
        for r in refs:
            apa = r["apa"]
            url = r["url"]
            doi = r["doi"]
            link = doi or url
            if not apa and link:
                apa = link  # last-resort: use URL as label
            if not apa:
                continue
            if link and link not in apa:
                lines.append(f"{len(lines) - 2}. {apa} [{link}]({link})")
            else:
                lines.append(f"{len(lines) - 2}. {apa}")
        # Renumber properly (1-based)
        out = []
        n = 0
        for line in lines:
            m = re.match(r"^\d+\.\s+(.*)$", line)
            if m:
                n += 1
                out.append(f"{n}. {m.group(1)}")
            else:
                out.append(line)
        return body.rstrip() + "\n\n---\n" + "\n".join(out) + "\n"
    except Exception as e:
        print(f"⚠ Could not append references: {e}", file=sys.stderr)
        return body


def _load_seo_plugin_provided_types(site_slug: str) -> set[str]:
    """Return the set of @type values the project's SEO plugin already emits in <head>.

    Reads `projects/{slug}/business-context.json :: wordpress.seo_plugin_schema_provided`.
    The publisher uses this list to SKIP duplicating those types in body <script> blocks
    when writing custom schema from workspace/{task}/schema.json. Prevents:
      - Duplicate BreadcrumbList (RankMath PRO + our schema-generator both emitting one)
      - Duplicate BlogPosting / Organization / Person etc. (rare but possible)

    Returns an empty set if the file is missing, malformed, or the key absent — that
    behavior preserves the legacy "publisher emits whatever schema.json contains"
    semantics for projects that haven't declared the policy yet.

    See [[reference_rankmath_seo_plugin_schema_provided]] for the canonical project-charlie
    list (8 types: Article, BlogPosting, Organization, Person, WebPage, WebSite,
    ImageObject, BreadcrumbList).
    """
    try:
        # PLUGIN_ROOT is exported by file_bus — re-use that resolved path.
        bc_path = file_bus.PLUGIN_ROOT / "projects" / site_slug / "business-context.json"
        if not bc_path.exists():
            return set()
        data = json.loads(bc_path.read_text(encoding="utf-8"))
        wp = data.get("wordpress", {})
        provided = wp.get("seo_plugin_schema_provided", [])
        return {t for t in provided if isinstance(t, str)}
    except Exception as e:
        # Defensive: don't crash the publish flow on policy-load errors; log + continue.
        import sys
        print(f"⚠ _load_seo_plugin_provided_types({site_slug}) error: {e}", file=sys.stderr)
        return set()


def _ld_block_types(ld: dict) -> set[str]:
    """Extract all @type values from a single JSON-LD block (handles @graph wrappers)."""
    types: set[str] = set()
    if not isinstance(ld, dict):
        return types
    if "@graph" in ld and isinstance(ld["@graph"], list):
        for it in ld["@graph"]:
            if isinstance(it, dict) and "@type" in it:
                t = it["@type"]
                if isinstance(t, list):
                    types.update(t)
                else:
                    types.add(t)
    elif "@type" in ld:
        t = ld["@type"]
        if isinstance(t, list):
            types.update(t)
        else:
            types.add(t)
    return types


def _append_custom_schema_blocks(html: str, workspace_task_id: str, site_slug: str | None = None) -> str:
    """Append inline JSON-LD <script> blocks from workspace/{task}/schema.json.

    Placement: AFTER the closing `</div>` + `<!-- /wp:html -->` of the project
    CSS wrapper. Schema scripts live OUTSIDE the wrapper so the styled <div>
    doesn't accidentally hide them with CSS reset rules.

    Expected schema.json shapes (auto-detected):
      - {"blocks": [{"block_name": "...", "ld_json": {...}}, ...]}  (canonical)
      - {"schemas": [...]}  (alt key)
      - Top-level list of ld_json objects: [{"@context": ..., "@type": ...}, ...]
      - {"jsonld": [...]} (alt key)

    Filtering (added 2026-05-21): if `site_slug` is provided and the project's
    `business-context.json :: wordpress.seo_plugin_schema_provided` declares
    types the SEO plugin emits natively in <head> (e.g. BreadcrumbList for
    project-charlie+RankMath Pro with breadcrumbs enabled), those types are SKIPPED
    from body emission to prevent duplication. The publisher logs each skipped
    block_name for audit.

    If the file is missing, empty, or malformed, returns html unchanged with
    a non-fatal warning. The 2026-05-21 project-charlie 085fb1ba240c task surfaced
    this gap — schema.json existed and was perfectly valid, but the publisher
    had no stage that consumed it, so all 4 custom blocks (Dataset, HowTo×2,
    FAQPage) had to be PATCHed in via REST after the fact.
    """
    try:
        ws = file_bus.get_workspace(workspace_task_id)
        schema_path = ws / "schema.json"
        if not schema_path.exists():
            return html
        data = json.loads(schema_path.read_text(encoding="utf-8"))

        # Normalize to flat list of ld_json dicts
        ld_list: list[dict] = []
        if isinstance(data, list):
            ld_list = [d for d in data if isinstance(d, dict)]
        elif isinstance(data, dict):
            for key in ("blocks", "schemas", "jsonld", "json_ld"):
                arr = data.get(key)
                if isinstance(arr, list):
                    for entry in arr:
                        if isinstance(entry, dict):
                            # Entry might be {ld_json: {...}} wrapper OR ld_json directly
                            if "ld_json" in entry and isinstance(entry["ld_json"], dict):
                                ld_list.append(entry["ld_json"])
                            elif "@context" in entry or "@type" in entry:
                                ld_list.append(entry)
                    if ld_list:
                        break
            # Fallback: a top-level combined object like
            # {"@context": ..., "@graph": [ {FAQPage}, {Dataset} ]} or a single
            # {"@context": ..., "@type": ...} block. The schema-validator subagent
            # commonly emits the @graph form; the loop above misses it because there
            # is no blocks/schemas/jsonld key. Split each @graph member into its own
            # <script> tag (verify_post check 17 counts script tags, not @graph
            # members inside one tag — a merged @graph under-counts as 1 block).
            if not ld_list and isinstance(data, dict) and "@graph" in data:
                graph = data.get("@graph")
                if isinstance(graph, list):
                    ctx = data.get("@context")
                    ld_list = [
                        {"@context": ctx, **item} if ctx and "@context" not in item else item
                        for item in graph
                        if isinstance(item, dict)
                    ]
            if not ld_list and isinstance(data, dict) and (
                "@type" in data or "@context" in data
            ):
                ld_list = [data]

        if not ld_list:
            return html

        # Filter out @types the SEO plugin already provides in <head>
        skip_types = _load_seo_plugin_provided_types(site_slug) if site_slug else set()
        if skip_types:
            filtered: list[dict] = []
            skipped: list[tuple[str, list[str]]] = []  # (block_name, types) for audit log
            for entry_idx, ld in enumerate(ld_list):
                block_types = _ld_block_types(ld)
                # Skip the block ONLY if EVERY type in it is provided by the SEO plugin.
                # Heuristic: if all types are SEO-plugin-provided, skip; if any type isn't, keep.
                if block_types and block_types.issubset(skip_types):
                    name = ld.get("@type") if isinstance(ld.get("@type"), str) else f"block_{entry_idx}"
                    skipped.append((str(name), sorted(block_types)))
                    continue
                filtered.append(ld)
            if skipped:
                print(
                    f"⓪ schema-injector: skipped {len(skipped)} block(s) already provided by "
                    f"SEO plugin (seo_plugin_schema_provided): "
                    + "; ".join(f"{n}({','.join(t)})" for n, t in skipped),
                    file=sys.stderr,
                )
            ld_list = filtered

        if not ld_list:
            return html

        # Build the script blocks (compact JSON, no extra whitespace)
        script_blocks = []
        for ld in ld_list:
            ld_str = json.dumps(ld, ensure_ascii=False, separators=(",", ":"))
            script_blocks.append(f'<script type="application/ld+json">{ld_str}</script>')

        # Append AFTER the </div> + <!-- /wp:html --> closing marker if present,
        # otherwise just append at the end.
        injection = "\n\n" + "\n".join(script_blocks) + "\n"
        return html.rstrip() + injection
    except Exception as e:
        print(f"⚠ Could not append custom schema blocks: {e}", file=sys.stderr)
        return html


def _wrap_images_in_figures(html: str, body_images: list[dict],
                            slot_to_media: dict[str, "wp_media.WPMedia"],
                            *, align: str = "default", lightbox: bool = False) -> str:
    """Wrap each <img> in the HTML with <figure class="wp-block-image"><figcaption>.

    Uses image metadata from body_images: alt, caption, title, description.
    Skips images already inside a <figure>. Images that aren't in slot_to_media
    are left as plain <img> (defensive).

    align: "default" | "wide" | "full" — Gutenberg block alignment for body
        figures. "wide"/"full" let the theme render the image past the content
        column (where the theme supports it), so the browser picks a higher
        srcset candidate (1536/2048) instead of the 768 medium_large derivative.
        Default keeps the pre-2026-06-29 centered size-large behaviour, so other
        projects are unaffected unless they opt in via business-context.
    lightbox: when True, enable WordPress core's native "expand on click"
        lightbox (WP 6.4+) so readers can view the full-resolution original.
    """
    # Build src -> img-dict map for lookup
    url_to_img = {}
    for img in body_images:
        slot_id = img.get("slot_id")
        if slot_id in slot_to_media:
            url_to_img[slot_to_media[slot_id].source_url] = (img, slot_to_media[slot_id])

    # Replace <img ...> not already wrapped in <figure>
    def repl(match: "re.Match[str]") -> str:
        full_tag = match.group(0)
        src_m = re.search(r'src="([^"]+)"', full_tag)
        if not src_m:
            return full_tag
        src = src_m.group(1)
        if src not in url_to_img:
            return full_tag
        img_dict, media = url_to_img[src]
        mid = media.id
        cap = _html.escape(img_dict.get("caption", ""))
        # Preserve any existing class/loading/decoding from the <img>
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', full_tag))
        # Standardize attributes
        attrs["src"] = src
        attrs["alt"] = img_dict.get("alt", attrs.get("alt", ""))
        attrs["loading"] = attrs.get("loading", "lazy")
        attrs["decoding"] = attrs.get("decoding", "async")
        cls = attrs.get("class", "").strip()
        if f"wp-image-{mid}" not in cls:
            cls = (cls + f" wp-image-{mid}").strip()
        attrs["class"] = cls
        attrs_str = " ".join(f'{k}="{_html.escape(str(v))}"' for k, v in attrs.items())
        cap_html = f'<figcaption class="wp-element-caption">{cap}</figcaption>' if cap else ""
        block_attrs: dict[str, object] = {
            "id": mid, "sizeSlug": "large", "linkDestination": "none",
        }
        fig_class = "wp-block-image size-large"
        if align in ("wide", "full"):
            block_attrs["align"] = align
            fig_class = f"wp-block-image align{align} size-large"
        if lightbox:
            block_attrs["lightbox"] = {"enabled": True}
        block_json = json.dumps(block_attrs, separators=(",", ":"))
        return (
            f'<!-- wp:image {block_json} -->\n'
            f'<figure class="{fig_class}"><img {attrs_str} />{cap_html}</figure>\n'
            f'<!-- /wp:image -->'
        )

    # Only match <img> tags NOT already inside <figure>...</figure>
    # Use lookbehind-free approach: process line-by-line, skip <img> inside <figure>...</figure>
    out_parts = []
    i = 0
    while i < len(html):
        fig_open = html.find("<figure", i)
        if fig_open == -1:
            out_parts.append(re.sub(r'<img[^>]+>', repl, html[i:]))
            break
        fig_close = html.find("</figure>", fig_open)
        if fig_close == -1:
            out_parts.append(re.sub(r'<img[^>]+>', repl, html[i:]))
            break
        out_parts.append(re.sub(r'<img[^>]+>', repl, html[i:fig_open]))
        out_parts.append(html[fig_open:fig_close + len("</figure>")])
        i = fig_close + len("</figure>")
    return "".join(out_parts)


def _tag_structural_paragraphs(html: str) -> str:
    """Add class attributes to paragraphs that contain ONLY a single element
    (no surrounding text), so the article CSS can style them safely without
    relying on the :only-child pseudo-class.

    The CSS `:only-child` selector only counts ELEMENT siblings, so a rule like
    `p > em:only-child { display: block }` matches `<p>text <em>X</em> text</p>`
    too — text nodes are invisible to that pseudo-class. This wreaks havoc on
    inline italics. Instead, this function inspects each <p> at HTML-generation
    time (when text nodes ARE distinguishable) and adds explicit classes:

      • <p class="faq-question">  — paragraph that is exactly <p><strong>X</strong></p>
                                    and appears after a <h2 id="faq"> H2
      • <p class="article-signature"> — the last <p> in the document that is
                                        exactly <p><em>X</em></p>

    Other paragraphs are left untouched. The CSS rules for these classes
    intentionally do NOT use display:block — they style via text-align,
    font-size, and color only.
    """
    # Find FAQ region: from "<h2 id=\"faq\"" to end (or next H2 / </div>).
    faq_open = re.search(r'<h2[^>]*id="faq"[^>]*>', html)
    if faq_open:
        start = faq_open.end()
        rest = html[start:]
        next_h2 = re.search(r'<h[12][^>]*id="(?!faq)', rest)
        end_rel = next_h2.start() if next_h2 else len(rest)
        faq_region = rest[:end_rel]

        # FAQ Q's are typically authored in markdown as:
        #   **Question?**
        #   Answer paragraph.
        # With breaks:False (our default), markdown-it collapses single newlines, so this
        # becomes ONE <p> tag containing <strong>Q</strong> + answer text. We split it
        # into two paragraphs and tag the first with class="faq-question".
        def split_qa(m: "re.Match[str]") -> str:
            q_tag = m.group(1)  # <strong>...</strong>
            answer = m.group(2).strip()  # remaining text
            if not answer:
                return f'<p class="faq-question">{q_tag}</p>'
            return f'<p class="faq-question">{q_tag}</p>\n<p>{answer}</p>'

        # Match <p><strong>Question</strong>RemainingText</p>
        # The (?:[^<]|<(?!/p>))*? is conservative — allows any non-tag text or inline tags
        # but doesn't cross paragraph boundary.
        new_region = re.sub(
            r'<p>\s*(<strong>[^<]+?</strong>)\s*((?:[^<]|<(?!/p>))*?)\s*</p>',
            split_qa,
            faq_region,
        )
        html = html[:start] + new_region + rest[end_rel:]

    # Tag the article signature: the LAST <p> that contains only <em>...</em>.
    # The <em> may contain nested inline elements (e.g., <a href="...">contact</a>),
    # so the content pattern accepts any chars except a closing </em>.
    matches = list(re.finditer(
        r'<p>\s*(<em>(?:(?!</em>).)+?</em>)\s*</p>',
        html,
        flags=re.DOTALL,
    ))
    if matches:
        last = matches[-1]
        # Only apply when it's near the end of the body — within last 15000 chars.
        # The threshold was 2500 but that missed signatures when References
        # + JSON-LD blocks push them further from the absolute end (2026-05-26 fix).
        if last.start() >= len(html) - 15000:
            html = (
                html[:last.start()]
                + f'<p class="article-signature">{last.group(1)}</p>'
                + html[last.end():]
            )
    return html


def _tag_callouts_and_pullquotes(html: str) -> str:
    """Add typed classes to rendered <blockquote>s so the article CSS styles callouts + pull-quotes.

    Authors cannot write classes (body renders html:False), so we detect on the RENDERED HTML,
    exactly like _tag_structural_paragraphs. Classification uses the SHARED source of truth
    `scripts._core.blockquote_classify.classify` — the SAME logic the visual-density gate uses,
    so the component the gate counts is exactly the component the CSS styles (BUG 3 fix):
      • first <p> starts with <strong>Label:</strong> for a known callout keyword -> callout
      • first <p> starts with the heavy quote mark ❝ -> pull-quote
      • anything else (incl. a normal straight/curly quotation) -> left a plain blockquote
    """
    from scripts._core.blockquote_classify import classify

    def tag(m: "re.Match[str]") -> str:
        inner = m.group(1)
        pm = re.match(r"\s*<p>\s*(.*?)</p>", inner, re.DOTALL)
        head = pm.group(1) if pm else inner.strip()
        kind = classify(head)
        if kind.startswith("callout-"):
            return f'<blockquote class="callout {kind}">{inner}</blockquote>'
        if kind == "pull_quote":
            return f'<blockquote class="pull-quote">{inner}</blockquote>'
        return m.group(0)

    return re.sub(r"<blockquote>(.*?)</blockquote>", tag, html, flags=re.DOTALL)


def _apply_project_styling(html: str, site_slug: str) -> str:
    """Wrap article body in <div class="{slug}-pillar">, prepend project CSS as
    inline <style>, and wrap the whole thing in a single <!-- wp:html --> block.

    The wp:html wrapper is critical: WordPress treats its contents as raw HTML
    and preserves <p>, <figure>, <style>, custom classes verbatim. Without it,
    classic-content sanitization strips <p> tags assuming wpautop will re-add
    them (which it doesn't always do in hybrid block/classic content).

    If no project article-css.css exists, the function still wraps in the slug
    class so themes / future CSS can target it consistently.
    """
    from scripts._core import style_tokens

    wrapper_class = _slug_to_wrapper_class(site_slug)
    css = _load_project_article_css(site_slug)
    style_block = ""
    if css:
        css_min = _minify_css(css) if "/*" in css or "  " in css else css
        style_block = f"<style>{css_min}</style>\n"

    inner = f'<div class="{wrapper_class}">\n{html}\n</div>'
    wrapped = f"<!-- wp:html -->\n{style_block}{inner}\n<!-- /wp:html -->"
    # De-fingerprint boundary (2026-08-01): internal artifacts keep the legacy
    # class vocabulary; the published body + inline CSS get the per-project
    # token names. No-op unless projects/{slug}/brand/style-tokens.json exists.
    return style_tokens.transform(wrapped, site_slug)


if __name__ == "__main__":
    sys.exit(main())
