#!/usr/bin/env python3
"""Deploy a project's blog sidebars to its live WordPress host — the hop 2→3 tool.

WHY THIS EXISTS (Rule 13)
Blog sidebars are a THREE-hop artifact, exactly like the article CSS:

    hop 1  skill    scripts/build/blog_sidebar_generator.py + templates/*.tpl
    hop 2  project  projects/{slug}/brand/blog-sidebars.{php,css}
    hop 3  deployed the mu-plugin file on the WP host + the WPCode CSS snippet

Hop 2→3 happens once, at deploy. So **every live site keeps the sidebar code that
was current on the day it shipped, forever.** Fixing the generator changes nothing
that is already deployed, in this project or any other. Without this tool the
drift is not merely unfixed, it is undetectable — which is how project-alpha ended up
running an 11,683-byte hand-written file while its generated artifact was 12,713
bytes, on day one.

A fix to the template is therefore a THREE-part change:
  1. edit templates/blog-sidebars.*.tpl
  2. regenerate every project:  for s in projects/*; do blog_sidebar_generator $s; done
  3. redeploy every live site:  deploy_blog_sidebars {slug} --check   then --apply

WHAT --check GIVES YOU
Drift detection. It hashes hop 2 against hop 3 and tells you which sites are
stale, without touching anything. Run it before believing a template fix shipped.

TRANSPORT
The mu-plugin is a file on the host, so this needs shell access, not REST. It
shells out to the project's configured docker/ssh recipe. Sites without one are
reported as `manual` with the exact commands to run — never silently skipped.

Usage
-----
    python -m scripts.wordpress.deploy_blog_sidebars project-alpha --check
    python -m scripts.wordpress.deploy_blog_sidebars project-alpha --apply
    python -m scripts.wordpress.deploy_blog_sidebars --all --check --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _load_json(p: Path) -> dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _host_recipe(slug: str) -> dict[str, Any] | None:
    """Where and how to reach this project's WordPress filesystem.

    Read from business-context.json :: wordpress.host_access, e.g.

        "host_access": {
            "ssh": "xuanran-srv",
            "container": "examplecom-wordpress-1",
            "mu_plugins": "/var/www/html/wp-content/mu-plugins"
        }

    Absent = no shell recipe, and this tool will say so rather than guess.
    """
    bc = _load_json(PLUGIN_ROOT / "projects" / slug / "business-context.json")
    ha = (bc.get("wordpress") or {}).get("host_access")
    if not isinstance(ha, dict) or not ha.get("ssh") or not ha.get("container"):
        return None
    ha.setdefault("mu_plugins", "/var/www/html/wp-content/mu-plugins")
    return ha


def _ssh(recipe: dict[str, Any], remote_cmd: str, timeout: int = 120) -> tuple[int, str]:
    proc = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", recipe["ssh"], remote_cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _ssh_stdin(recipe: dict[str, Any], remote_cmd: str, payload: str,
               timeout: int = 120) -> tuple[int, str]:
    proc = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", recipe["ssh"], remote_cmd],
        input=payload, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _artifacts(slug: str) -> tuple[Path, Path]:
    brand = PLUGIN_ROOT / "projects" / slug / "brand"
    return brand / "blog-sidebars.php", brand / "blog-sidebars.css"


def _norm(text: str) -> str:
    """Compare content, not line-ending trivia.

    The CSS makes a round trip through WordPress, which normalises newlines. A
    hash mismatch caused purely by \\r\\n would cry drift on every single check
    and train the operator to ignore the tool — the classic way a real signal
    gets buried under a false one.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


# The CSS half does not live in a file: WPCode keeps snippet code in the wpcode
# post's post_content. Checking only the mu-plugin would let `in_sync` mean "half
# of it is in sync" — the Rule 12 mistake (a gate that answers a narrower question
# than the one it appears to answer). This probe reads the other half.
_CSS_PROBE = r"""<?php
require_once "/var/www/html/wp-load.php";
global $wpdb;
$needle = isset( $argv[1] ) ? $argv[1] : 'Blog sidebar styles';
$rows = $wpdb->get_results( $wpdb->prepare(
    "SELECT ID, post_status, post_content FROM {$wpdb->posts}"
    . " WHERE post_type = 'wpcode' AND post_title LIKE %s",
    '%' . $wpdb->esc_like( $needle ) . '%' ) );
$out = array();
foreach ( (array) $rows as $r ) {
    $c = (string) $r->post_content;
    $n = trim( str_replace( array( "\r\n", "\r" ), "\n", $c ) );
    $out[] = array(
        'id'     => (int) $r->ID,
        'status' => $r->post_status,
        'bytes'  => strlen( $c ),
        'sha'    => substr( hash( 'sha256', $n ), 0, 16 ),
    );
}
echo json_encode( $out );
"""


def _remote_css(recipe: dict[str, Any], slug: str, title_needle: str) -> dict[str, Any] | None:
    """Hash of the deployed CSS snippet, or None if it cannot be read."""
    container = recipe["container"]
    probe = f"/tmp/_{slug}_cssprobe.php"
    rc, out = _ssh_stdin(
        recipe,
        f"cat > {probe} && docker cp {probe} {container}:{probe} && "
        f"docker exec {container} php {probe} {title_needle!r}; "
        f"rm -f {probe}",
        _CSS_PROBE,
    )
    if rc != 0:
        return None
    start = out.find("[")
    if start < 0:
        return None
    try:
        rows = json.loads(out[start:out.rfind("]") + 1])
    except json.JSONDecodeError:
        return None
    live = [r for r in rows if r.get("status") == "publish"]
    return (live or rows or [None])[0]


def _widget_id_bases(php: str) -> set[str]:
    """The id_bases a mu-plugin registers — the keys WordPress stores against."""
    return set(re.findall(r"parent::__construct\(\s*'([^']+)'", php))


def _sidebar_ids(php: str) -> list[str]:
    return re.findall(r"'id'\s*=>\s*'([^']+)'", php)


_ASSIGNED_PROBE = r"""<?php
require_once "/var/www/html/wp-load.php";
$w = get_option( 'sidebars_widgets' );
$out = array();
foreach ( explode( ',', $argv[1] ) as $s ) {
    $out[ $s ] = empty( $w[ $s ] ) ? array() : array_values( (array) $w[ $s ] );
}
echo json_encode( $out );
"""


def _orphan_check(recipe: dict[str, Any], slug: str, new_php: str) -> dict[str, Any]:
    """Would installing `new_php` strand widgets the operator already placed?

    A mu-plugin swap is verified by reading the FILE back, and the file is always
    fine. What breaks is the DATA: `sidebars_widgets` still points at id_bases the
    new file no longer registers, so those widgets vanish from the rendered page
    with no error anywhere. This is Rule 4's lesson ("200 is not 'renders
    correctly'") applied to a deploy instead of a publish — verify the effect, not
    the transfer.
    """
    ids = _sidebar_ids(new_php)
    if not ids:
        return {"checked": False}
    probe = f"/tmp/_{slug}_assigned.php"
    rc, out = _ssh_stdin(
        recipe,
        f"cat > {probe} && docker cp {probe} {recipe['container']}:{probe} && "
        f"docker exec {recipe['container']} php {probe} {','.join(ids)!r}; rm -f {probe}",
        _ASSIGNED_PROBE,
    )
    start = out.find("{")
    if rc != 0 or start < 0:
        return {"checked": False, "reason": "could not read sidebars_widgets"}
    try:
        assigned = json.loads(out[start:out.rfind("}") + 1])
    except json.JSONDecodeError:
        return {"checked": False, "reason": "unparseable widget map"}

    registered = _widget_id_bases(new_php)
    orphans: list[str] = []
    for sidebar, widgets in assigned.items():
        for inst in widgets:
            base = re.sub(r"-\d+$", "", str(inst))
            # Core widgets (categories, text…) are not ours to register.
            if base.startswith(tuple(f"{p}_" for p in {b.split("_")[0] for b in registered})) \
                    and base not in registered:
                orphans.append(f"{sidebar}:{inst}")
    return {"checked": True, "orphans": orphans, "registered": sorted(registered)}


def check(slug: str) -> dict[str, Any]:
    """Compare hop 2 against hop 3 without changing anything."""
    php_p, css_p = _artifacts(slug)
    out: dict[str, Any] = {"slug": slug, "action": "check"}

    if not php_p.exists():
        out.update(status="not_generated",
                   detail="run: python -m scripts.build.blog_sidebar_generator " + slug)
        return out

    local_php = php_p.read_text(encoding="utf-8")
    out["local_sha"] = _sha(local_php)
    out["local_bytes"] = len(local_php.encode("utf-8"))

    recipe = _host_recipe(slug)
    if not recipe:
        out.update(status="manual",
                   detail=("no wordpress.host_access in business-context.json — cannot reach "
                           "the host. Add {ssh, container} or deploy by hand."))
        return out

    # Probe the transport FIRST. Reporting "not_deployed" when the truth is
    # "could not connect" is the Rule-12 mistake in miniature: a content verdict
    # returned for what was actually a transport failure. On Windows this bites
    # immediately — only PowerShell's native ssh reaches the agent key, so the
    # same call from Git Bash fails and would otherwise read as a missing file.
    rc_probe, probe = _ssh(recipe, f"docker exec {recipe['container']} true")
    if rc_probe != 0:
        out.update(status="unreachable", remote_sha=None,
                   detail=(f"cannot reach {recipe['ssh']}/{recipe['container']}: "
                           f"{probe.strip()[:200] or 'ssh returned ' + str(rc_probe)}. "
                           f"On Windows run this from PowerShell — Git Bash cannot reach "
                           f"the ssh agent key."))
        return out

    target = f"{recipe['mu_plugins']}/{slug}-blog-sidebars.php"
    rc, body = _ssh(recipe, f"docker exec {recipe['container']} cat {target} 2>/dev/null")
    if rc != 0 or not body.strip():
        out.update(status="not_deployed", remote_sha=None,
                   detail=f"{target} absent on host (transport verified working)")
        return out

    out["remote_sha"] = _sha(body)
    out["remote_bytes"] = len(body.encode("utf-8"))
    php_ok = out["remote_sha"] == out["local_sha"]

    # ---- the other half: the CSS snippet
    css_ok = True
    if css_p.exists():
        out["css_local_sha"] = _sha(_norm(css_p.read_text(encoding="utf-8")))
        snip = _remote_css(recipe, slug, _css_title(slug))
        if snip is None:
            out["css_status"] = "unreadable"
            css_ok = False
        elif snip.get("sha") != out["css_local_sha"]:
            out["css_status"] = "DRIFTED"
            out["css_remote_sha"] = snip.get("sha")
            out["css_snippet_id"] = snip.get("id")
            css_ok = False
        else:
            out["css_status"] = "in_sync"
            out["css_snippet_id"] = snip.get("id")

    out["status"] = "in_sync" if (php_ok and css_ok) else "DRIFTED"
    if not php_ok and css_ok:
        out["detail"] = "mu-plugin drifted; CSS snippet matches"
    elif php_ok and not css_ok:
        out["detail"] = f"mu-plugin matches; CSS snippet {out.get('css_status')}"
    return out


def _css_title(slug: str) -> str:
    """How the CSS snippet is named on the host.

    Overridable per project because the operator names snippets by hand in the
    WPCode UI; a wrong guess here must surface as `unreadable`, not as a silent
    pass.
    """
    bc = _load_json(PLUGIN_ROOT / "projects" / slug / "business-context.json")
    sb = bc.get("blog_sidebars") or {}
    return sb.get("css_snippet_title") or "Blog sidebar styles"


def apply(slug: str, force: bool = False) -> dict[str, Any]:
    """Push hop 2 to hop 3, verify the readback, then purge correctly."""
    php_p, css_p = _artifacts(slug)
    out: dict[str, Any] = {"slug": slug, "action": "apply"}

    if not php_p.exists():
        out.update(status="not_generated",
                   detail="run the generator first")
        return out

    recipe = _host_recipe(slug)
    if not recipe:
        out.update(status="manual", detail=_manual_steps(slug, php_p, css_p))
        return out

    local_php = php_p.read_text(encoding="utf-8")
    container = recipe["container"]
    target = f"{recipe['mu_plugins']}/{slug}-blog-sidebars.php"
    staging = f"/tmp/{slug}-blog-sidebars.php"

    # 1 · copy to the host, then into the container
    proc = subprocess.run(
        ["scp", "-o", "ConnectTimeout=20", str(php_p), f"{recipe['ssh']}:{staging}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )
    if proc.returncode != 0:
        out.update(status="failed", detail=f"scp failed: {proc.stderr.strip()[:300]}")
        return out

    # 2 · lint on the host BEFORE installing. A broken mu-plugin is a white screen.
    rc, lint = _ssh(recipe,
        f"docker cp {staging} {container}:/tmp/_sbcheck.php && "
        f"docker exec {container} php -l /tmp/_sbcheck.php")
    if rc != 0 or "No syntax errors" not in lint:
        out.update(status="failed", detail=f"php -l refused the file: {lint.strip()[:300]}")
        return out
    out["lint"] = "ok"

    # 3 · would this swap strand widgets the operator already placed?
    orph = _orphan_check(recipe, slug, local_php)
    out["orphan_check"] = orph
    if orph.get("orphans") and not force:
        out.update(status="refused", detail=(
            "installing this file would orphan already-assigned widgets: "
            + ", ".join(orph["orphans"])
            + f". The new file registers {orph['registered']}. Either align the "
              "id_base in templates/blog-sidebars.php.tpl (an id_base is a data "
              "contract, not a label) or re-assign the widgets after deploying "
              "with --force."))
        return out

    # 4 · install + fix ownership (docker cp lands root-owned, which breaks reads)
    rc, res = _ssh(recipe,
        f"docker cp {staging} {container}:{target} && "
        f"docker exec -u root {container} chown www-data:www-data {target} && "
        f"docker exec -u root {container} chmod 644 {target} && "
        f"docker exec {container} sha256sum {target}")
    if rc != 0:
        out.update(status="failed", detail=f"install failed: {res.strip()[:300]}")
        return out

    # 5 · byte-level readback. A silently mangled deploy is worse than a failed one.
    rc, body = _ssh(recipe, f"docker exec {container} cat {target}")
    if rc != 0 or _sha(body) != _sha(local_php):
        out.update(status="failed",
                   detail="readback differs from source — file NOT verified on host")
        return out
    out["verified"] = True
    out["remote_sha"] = _sha(body)

    out["css_next_step"] = (
        f"CSS is a WPCode snippet, not a file: paste {css_p} into the 'Blog sidebar styles' "
        f"CSS snippet (Site Wide Header) and rebuild the snippet cache with "
        f"wpcode()->cache->cache_all_loaded_snippets(). NEVER delete_option('wpcode_snippets')."
    )
    out["opcache_note"] = (
        "OPcache typically runs validate_timestamps=On revalidate_freq=60. Wait out that "
        "window BEFORE purging the page cache, or pages regenerate against the old compiled file."
    )
    out["status"] = "deployed"
    return out


def _manual_steps(slug: str, php_p: Path, css_p: Path) -> str:
    return (
        f"1) copy {php_p} to wp-content/mu-plugins/{slug}-blog-sidebars.php "
        f"(chown www-data:www-data, chmod 644)\n"
        f"2) php -l it on the host first\n"
        f"3) paste {css_p} into a WPCode CSS snippet, location Site Wide Header\n"
        f"4) add the class prefix to any Remove-Unused-CSS safelist\n"
        f"5) rebuild the snippet cache via the plugin's own API; never delete_option()\n"
        f"6) wait out the OPcache window, then purge the page cache\n"
        f"7) screenshot the result — grepping HTML for a class name proves nothing"
    )


def all_slugs() -> list[str]:
    root = PLUGIN_ROOT / "projects"
    if not root.is_dir():
        return []
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and (p / "brand" / "blog-sidebars.php").exists()
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy blog sidebars to a live host (hop 2->3)")
    ap.add_argument("slug", nargs="?", help="project slug; omit with --all")
    ap.add_argument("--all", action="store_true", help="every project that has generated sidebars")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="report drift, change nothing")
    g.add_argument("--apply", action="store_true", help="push hop 2 to hop 3")
    ap.add_argument("--force", action="store_true",
                    help="install even if assigned widgets would be orphaned")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    slugs = all_slugs() if a.all else ([a.slug] if a.slug else [])
    if not slugs:
        print("no project selected (pass a slug or --all)", file=sys.stderr)
        return 2

    results = [check(s) if a.check else apply(s, force=a.force) for s in slugs]

    if a.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{r['slug']}: {r['status']}")
            for k in ("local_bytes", "remote_bytes", "local_sha", "remote_sha",
                      "css_status", "css_snippet_id", "css_local_sha", "css_remote_sha",
                      "orphan_check", "detail", "css_next_step", "opcache_note"):
                if r.get(k):
                    print(f"    {k}: {r[k]}")

    return resolve_exit(results)


def resolve_exit(results: list[dict[str, Any]]) -> int:
    """Exit code for a run: 0 ONLY when every result is verified ``in_sync``.

    v3.42.14 root cure (2026-08-12 release audit, top-ranked inert check). The
    old mapping was a BLOCKLIST — ``("DRIFTED", "failed", "unreachable",
    "refused")`` — so every status it did not enumerate exited 0. That included
    ``not_deployed`` ("the mu-plugin is absent on the host, transport verified
    working"): MAXIMUM drift, and the literal project-alpha scenario this module's
    own docstring cites as its reason to exist. ``manual`` and
    ``not_generated`` also read as success. A blocklist of bad states is how a
    NEW bad state ships as a green check; the allowlist inverts the default so
    an unanticipated status fails loudly instead of silently passing
    (Rule 12/14: "I could not verify it" is never "it matches").

    The status string in the report still distinguishes transport
    (``unreachable``) from content (``not_deployed``/``DRIFTED``) per Rule 13 —
    the exit code is deliberately binary to match the fleet-wide
    ``hop3_drift.check_exit_code`` contract (unreadable and drifted are both
    non-zero).
    """
    return 0 if all(r.get("status") == "in_sync" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
