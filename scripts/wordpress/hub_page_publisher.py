"""
scripts/wordpress/hub_page_publisher.py — WordPress hub-page publisher for weekly digest series.

Manages a configurable hub landing page (default: /weekly-digest/) that lists all published weekly digest issues.
Upserts (create or update) a WordPress PAGE (not post) at the configured slug.

WordPress PAGES use /wp/v2/pages — identical REST shape to /wp/v2/posts but
distinct endpoint.  No existing page helper existed; this is net-new.

CLI:
    python -m scripts.wordpress.hub_page_publisher --project <slug> [--status draft|publish] [--json]

Draft-first default (Rule 5a): the hub page is created as status=draft unless
--status=publish is explicitly supplied.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any, Protocol

# ─── Plugin root ──────────────────────────────────────────────────────────────

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


# ─── WPClient protocol (duck-typing for tests) ────────────────────────────────

class _WPLike(Protocol):
    """Minimal interface consumed by this module — satisfied by WPClient and test stubs."""

    def get(self, path: str, **kwargs: Any) -> Any:
        ...

    def post(self, path: str, **kwargs: Any) -> Any:
        ...

    def patch(self, path: str, **kwargs: Any) -> Any:
        ...


# ─── Pure HTML builder ────────────────────────────────────────────────────────

def build_hub_html(
    issues: list[dict[str, Any]],
    *,
    hub_title: str,
    intro: str,
    wrapper_class: str | None = None,
) -> str:
    """Build the hub page HTML for the weekly digest series.

    Pure function — no network calls, no filesystem reads.

    Args:
        issues:        List of issue dicts.  Expected keys (all optional via .get()):
                       ``date``  ISO-8601 string (used for newest-first sort),
                       ``title`` display name, ``url`` permalink, ``item_count`` int.
        hub_title:     H1 / page title inserted into the HTML output.
        intro:         Short introductory paragraph placed beneath the H1.
        wrapper_class: Optional CSS class applied to a ``<div>`` that wraps the
                       entire output.  When omitted, no wrapper div is emitted.

    Returns:
        HTML string (fragment, not a full document).
    """
    # Sort newest-first; ISO-8601 dates compare correctly as strings
    sorted_issues = sorted(issues, key=lambda i: i.get("date") or "", reverse=True)

    # ── Issue list ────────────────────────────────────────────────────────────
    if sorted_issues:
        rows: list[str] = []
        for issue in sorted_issues:
            date: str = issue.get("date") or ""
            title: str = issue.get("title") or "Untitled Issue"
            url: str = issue.get("url") or "#"
            item_count = issue.get("item_count")
            count_str = f" &mdash; {item_count} items" if item_count else ""
            rows.append(
                f'  <li class="digest-hub__issue">'
                f'<span class="digest-hub__date">{html.escape(date)}</span> '
                f'<a href="{html.escape(url, quote=True)}">{html.escape(title)}</a>'
                f'<span class="digest-hub__count">{count_str}</span>'
                f"</li>"
            )
        issue_list_html = (
            '<ul class="digest-hub__list">\n'
            + "\n".join(rows)
            + "\n</ul>"
        )
    else:
        issue_list_html = (
            '<p class="digest-hub__placeholder">'
            "The first weekly issue is coming soon."
            "</p>"
        )

    # ── JSON-LD: CollectionPage + ItemList ────────────────────────────────────
    item_list_elements: list[dict[str, Any]] = []
    for pos, issue in enumerate(sorted_issues, start=1):
        item_list_elements.append(
            {
                "@type": "ListItem",
                "position": pos,
                "url": issue.get("url") or "",
                "name": issue.get("title") or "Untitled Issue",
            }
        )

    schema: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": hub_title,
        "description": intro,
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": item_list_elements,
        },
    }
    # Escape "<" so a harvested title containing "</script>" cannot break out of
    # the ld+json block (stored-XSS / page breakage — H8). "<" is valid JSON
    # and renders identically, so the structured data is unaffected.
    jsonld_block = (
        '<script type="application/ld+json">\n'
        + json.dumps(schema, ensure_ascii=False, indent=2).replace("<", "\\u003c")
        + "\n</script>"
    )

    # ── Assemble ──────────────────────────────────────────────────────────────
    parts = [
        f"<h1>{html.escape(hub_title)}</h1>",
        f"<p>{html.escape(intro)}</p>",
        issue_list_html,
        jsonld_block,
    ]
    body = "\n".join(parts)

    if wrapper_class:
        return f'<div class="{wrapper_class}">\n{body}\n</div>'
    return body


# ─── WordPress page helpers ───────────────────────────────────────────────────

def find_page_id(wp: _WPLike, slug: str) -> int | None:
    """Find an existing WordPress page by its URL slug.

    Returns the integer page ID if found, or ``None`` only when the lookup
    DEFINITIVELY returned no match (empty list). A lookup FAILURE (network error,
    non-2xx, CF challenge) is RAISED, never swallowed — otherwise upsert would
    take it as "not found" and POST a duplicate hub page (H6).
    """
    resp = wp.get(
        "/wp/v2/pages",
        params={
            "slug": slug,
            "context": "edit",
            "status": "any",
        },
    )
    data = resp.json_data
    # A successful lookup ALWAYS returns a JSON list (possibly empty). Anything
    # else — None from a 200 with a non-JSON body (e.g. a Cloudflare "checking
    # your browser" interstitial), or an unexpected dict/error envelope — is a
    # FAILED lookup, not "no match". Returning None here would let `upsert` fall
    # through to POST and create a DUPLICATE hub page, so we raise instead (H6
    # extended to the 200-non-JSON case the audit missed).
    if not isinstance(data, list):
        raise RuntimeError(
            f"hub page lookup for slug={slug!r} returned a non-list body "
            f"({type(data).__name__}); refusing to treat it as 'not found' "
            f"(would create a duplicate page)"
        )
    if len(data) > 0:
        first = data[0]
        if isinstance(first, dict):
            pid = first.get("id")
            if isinstance(pid, int):
                return pid
    return None


def upsert_hub_page(
    wp: _WPLike,
    *,
    slug: str,
    title: str,
    html: str,
    status: str | None = None,
) -> dict[str, Any]:
    """Create or update the hub page in WordPress.

    Checks whether a page with ``slug`` already exists:
    - If yes → ``PATCH /wp/v2/pages/{id}`` (update content + title).
    - If no  → ``POST /wp/v2/pages`` (create).

    Args:
        wp:     WPClient (or compatible duck-typed stub).
        slug:   URL slug for the hub page (project ``weekly_digest.hub_page``,
                default ``weekly-digest``).
        title:  Page title sent to WordPress.
        html:   Full HTML content for the page body.
        status: WordPress post status. ``None`` (default) means: create as
                ``"draft"`` (Rule 5a: draft-first), but on UPDATE do NOT send a
                status at all — so a weekly re-run that just refreshes the issue
                list never flips an already-published hub back to draft (H5).
                Pass an explicit ``"draft"``/``"publish"`` to force the status.

    Returns:
        Dict with keys:
        - ``page_id`` (int): The WP page ID.
        - ``action``  (str): ``"updated"`` or ``"created"``.
        - ``url``     (str | None): The page permalink if returned by the API.
    """
    pid = find_page_id(wp, slug)

    if pid is not None:
        patch_body: dict[str, Any] = {"content": html, "title": title}
        if status is not None:
            patch_body["status"] = status
        resp = wp.patch(f"/wp/v2/pages/{pid}", json_body=patch_body)
        action = "updated"
    else:
        create_status = status or "draft"
        create_body: dict[str, Any] = {
            "title": title,
            "content": html,
            "status": create_status,
        }
        # A slug on a draft/pending REST create trips core create_item()'s
        # draft-slug uniquifier, which reads $prepared_post->id/->post_parent —
        # properties that never exist during a create — and PHP-warns twice.
        # The update path has no such block, so for those statuses the slug is
        # applied in a follow-up PATCH instead.
        defer_slug = create_status in ("draft", "pending")
        if not defer_slug:
            create_body["slug"] = slug
        resp = wp.post("/wp/v2/pages", json_body=create_body)
        if defer_slug:
            created = resp.json_data if isinstance(resp.json_data, dict) else {}
            new_id = created.get("id")
            if isinstance(new_id, int):
                patched = wp.patch(f"/wp/v2/pages/{new_id}", json_body={"slug": slug})
                pd = patched.json_data if isinstance(patched.json_data, dict) else {}
                # Adopt the PATCH response (fresher, slug-dependent link) only
                # when it echoes the page just created; otherwise the create
                # response stays canonical.
                if pd.get("id") == new_id:
                    resp = patched
        action = "created"

    data: dict[str, Any] = resp.json_data if isinstance(resp.json_data, dict) else {}
    page_id: int = int(data.get("id") or pid or 0)
    url: str | None = data.get("link") or None

    return {"page_id": page_id, "action": action, "url": url}


def upsert_issue_record(
    issues: list[dict[str, Any]],
    *,
    task_id: str,
    date: str,
    title: str,
    url: str,
    item_count: int,
) -> list[dict[str, Any]]:
    """Update-or-append the published issue record by ``task_id`` (H3/H7).

    The digest runner writes a stub ``{date, task_id, item_count}`` at harvest
    time (before the post exists). After publish, the orchestrator calls this
    with the LIVE post title + permalink, so the hub renders real links instead
    of every row collapsing to ``Untitled Issue -> "#"``. Keyed by ``task_id``,
    so re-running the same task updates the row in place instead of appending a
    duplicate (idempotent).
    """
    out = [dict(e) for e in issues]
    for entry in out:
        if str(entry.get("task_id") or "") == task_id:
            entry.update(
                {"date": date, "title": title, "url": url, "item_count": item_count}
            )
            return out
    out.append(
        {"task_id": task_id, "date": date, "title": title, "url": url,
         "item_count": item_count}
    )
    return out


def resolve_hub_status(
    cli_status: str | None, publish_policy_default: str | None
) -> str | None:
    """Decide the effective hub-page status (Rule 5a-compliant).

    The series hub is the user-visible artifact of the whole feature; before this
    fix there was NO path that ever published it, so ``/weekly-digest/`` stayed a
    permanent draft (404 to visitors and crawlers). H5 correctly stopped a weekly
    refresh from *clobbering* a live hub, but nothing ever *transitioned* it live.

    Resolution (most-specific first):
      1. An explicit ``--status`` always wins (operator's in-conversation choice).
      2. Else a project whose ``publish_policy.default == "publish"`` has standing
         authorization (Rule 5a project-level opt-in) — the hub mirrors the digest
         article, which already auto-publishes for that project.
      3. Else ``None``: create draft-first (Rule 5a default) and, on a refresh of
         an existing hub, leave its status untouched (H5).
    """
    if cli_status is not None:
        return cli_status
    if str(publish_policy_default or "").strip().lower() == "publish":
        return "publish"
    return None


# ─── CLI entry point ──────────────────────────────────────────────────────────

def main() -> None:
    """CLI: upsert the hub page for a project's weekly digest series."""
    parser = argparse.ArgumentParser(
        description=(
            "Upsert WordPress hub page for the weekly digest series (default: /weekly-digest/). "
            "Hub path is configurable via business-context.json. Defaults to draft status (Rule 5a)."
        )
    )
    parser.add_argument(
        "--project",
        required=True,
        metavar="SLUG",
        help="Project slug (e.g. loamwright)",
    )
    parser.add_argument(
        "--status",
        choices=["draft", "publish"],
        default=None,
        help="WordPress post status. Omit to create draft-first (Rule 5a) and, on "
             "a refresh of an existing hub, leave its current status untouched (H5).",
    )
    # Post-publish issue record (H3): record the LIVE digest post into issues.json
    # so the hub lists a real title + permalink, not "Untitled Issue".
    parser.add_argument("--task-id", default=None, help="Task ID of the issue to record")
    parser.add_argument("--issue-title", default=None, help="Published issue title")
    parser.add_argument("--issue-url", default=None, help="Published issue permalink")
    parser.add_argument("--issue-date", default=None, help="Issue date (YYYY-MM-DD)")
    parser.add_argument("--item-count", type=int, default=0, help="Item count for the issue")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit a single JSON line to stdout",
    )
    args = parser.parse_args()

    project_slug: str = args.project
    status: str | None = args.status
    json_output: bool = args.json_output

    # ── Load issues ──────────────────────────────────────────────────────────
    issues_path = PLUGIN_ROOT / "projects" / project_slug / "weekly" / "issues.json"
    issues: list[dict[str, Any]] = []
    if issues_path.exists():
        try:
            raw = json.loads(issues_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                issues = raw
        except Exception as exc:
            if not json_output:
                print(
                    f"WARNING: Could not read issues.json: {exc}",
                    file=sys.stderr,
                )

    # ── Record the just-published issue (H3/H7) under a lock, if details given ─
    # Partial issue args are a hard ERROR (2026-07-01): passing --issue-title/--issue-url
    # WITHOUT --task-id used to be silently ignored — the hub then rendered the stub row
    # as 'Untitled Issue' -> "#" with no hint why (exactly what happened on first
    # loamwright hub creation). Silent arg-dropping is the same disease as silent no-ops.
    _issue_args = {"--task-id": args.task_id, "--issue-title": args.issue_title,
                   "--issue-url": args.issue_url}
    _given = [k for k, v in _issue_args.items() if v]
    if _given and len(_given) < len(_issue_args):
        missing = [k for k, v in _issue_args.items() if not v]
        parser.error(f"partial issue record: {', '.join(_given)} given but {', '.join(missing)} "
                     f"missing — all three are required to record an issue on the hub.")
    if args.task_id and args.issue_title and args.issue_url:
        from scripts._core import file_lock

        issues = upsert_issue_record(
            issues,
            task_id=str(args.task_id),
            date=str(args.issue_date or ""),
            title=str(args.issue_title),
            url=str(args.issue_url),
            item_count=int(args.item_count or 0),
        )
        issues_path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock.locked(issues_path):
            file_lock.atomic_write_text(
                issues_path, json.dumps(issues, ensure_ascii=False, indent=2)
            )

    # ── Load business-context for hub_page config ─────────────────────────────
    bc_path = PLUGIN_ROOT / "projects" / project_slug / "business-context.json"
    hub_page_path = "/weekly-digest/"
    hub_title = "Weekly Digest"
    intro = "The latest news curated weekly."
    publish_policy_default: str | None = None

    if bc_path.exists():
        try:
            bc: dict[str, Any] = json.loads(bc_path.read_text(encoding="utf-8"))
            wd: dict[str, Any] = bc.get("weekly_digest") or {}
            hub_page_path = str(wd.get("hub_page") or hub_page_path)
            hub_title = str(wd.get("hub_title") or hub_title)
            intro = str(wd.get("intro") or intro)
            pp = bc.get("publish_policy") or {}
            if isinstance(pp, dict) and pp.get("default") is not None:
                publish_policy_default = str(pp.get("default"))
        except Exception as exc:
            if not json_output:
                print(
                    f"WARNING: Could not read business-context.json: {exc}",
                    file=sys.stderr,
                )

    # Resolve the effective status (Bug 1): explicit --status > project
    # publish_policy.default=="publish" opt-in > None (draft-first / H5-preserving).
    status = resolve_hub_status(status, publish_policy_default)

    # Derive page slug: strip leading/trailing slashes, fall back to "weekly-digest"
    page_slug = hub_page_path.strip("/") or "weekly-digest"

    # ── Build HTML ────────────────────────────────────────────────────────────
    html_content = build_hub_html(issues, hub_title=hub_title, intro=intro)

    # ── WPClient + upsert ────────────────────────────────────────────────────
    try:
        from scripts.wordpress.wp_client import WPClient  # lazy import to avoid creds load on module init

        wp = WPClient(project_slug)
    except Exception as exc:
        output: dict[str, Any] = {"success": False, "error": str(exc)}
        if json_output:
            print(json.dumps(output, ensure_ascii=False))
        else:
            print(f"ERROR: WPClient init failed: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        with wp:
            upsert_result = upsert_hub_page(
                wp,
                slug=page_slug,
                title=hub_title,
                html=html_content,
                status=status,
            )
        final: dict[str, Any] = {
            "success": True,
            "project": project_slug,
            "page_slug": page_slug,
            **upsert_result,
        }
    except Exception as exc:
        final = {
            "success": False,
            "project": project_slug,
            "page_slug": page_slug,
            "error": str(exc),
        }

    if json_output:
        print(json.dumps(final, ensure_ascii=False))
    else:
        if final.get("success"):
            action = final.get("action", "upserted")
            page_id = final.get("page_id")
            page_url = final.get("url") or ""
            print(f"Hub page {action}: id={page_id}, url={page_url}")
        else:
            print(f"ERROR: Hub page upsert failed: {final.get('error')}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
