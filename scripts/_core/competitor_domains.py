"""scripts/_core/competitor_domains.py — competitor/peer-domain citation guard.

PURPOSE
───────
Single source of truth for the project-level rule:

    A competitor / peer ("同行") website must NEVER appear as a CITED SOURCE —
    not in an in-text (Author, Year) citation, not in the References list, not
    as a body outbound link, and not in a JSON-LD citation/sameAs field.

This module is the ONE executor every layer calls (researcher exclude-list,
fact-checker source filter, assemble.py reference strip, linker outbound-link
filter, schema-generator citation strip, render_lint L11, cite_scorer COMP01
veto, pre_publish_gate hard-veto, verify_post live-URL check). Centralising the
domain logic here is deliberate: the historical failure mode in this codebase is
a rule documented in markdown with NO executor (see CLAUDE.md "Rule 6"). This
file is that executor.

POLICY SOURCE
─────────────
Per-project ``business-context.json :: citation_source_policy`` block:

    "citation_source_policy": {
      "enforcement": "hard_veto",            # hard_veto | warn | off
      "exclude_competitor_domains": true,
      "scope": ["in_text_citations", "references", "outbound_links", "schema_citation"],
      "do_not_cite_domains": ["fluence.com", "gavita.com", ...],
      "competitor_brands": ["Fluence", "Gavita", ...],
      "allow_brand_mention_in_prose": true,  # brand NAMES in prose are fine
      "datasheet_exception": false,          # competitor datasheets also excluded
      "sole_source_behavior": "research_replacement"  # re-search; drop only if none
    }

When the block is absent, or ``exclude_competitor_domains`` is false, or
``enforcement`` is "off", ``load_policy`` returns a DISABLED policy whose
``is_blocked`` is always False — so every layer is a no-op for projects that
have not opted in. Backward-compatible by construction.

DOMAIN MATCHING
───────────────
Suffix match on the registrable host so that subdomains of a blocked domain are
also blocked:  ``fluence.com`` blocks ``fluence.com``, ``www.fluence.com`` and
``blog.fluence.com`` — but NOT ``notfluence.com``. A leading ``www.`` is stripped
from both the blocklist entry and the host under test. DOI hosts (doi.org) are
never blocked unless explicitly listed.

USAGE (library)
───────────────
    from scripts._core import competitor_domains as cd
    policy = cd.load_policy_for_task(task_id)        # or cd.load_policy(slug)
    if policy.is_blocked("https://blog.fluence.com/ppfd"): ...
    hits = policy.find_blocked_in_html(rendered_html)  # [(url, domain), ...]

USAGE (CLI — satisfies the cross-host --json contract and Rule 6 "real
invocation, not pseudo-code")
───────────────
    python -m scripts._core.competitor_domains --project project-charlie --json
    python -m scripts._core.competitor_domains --task 20260620-abcd --check-url URL
    python -m scripts._core.competitor_domains --task 20260620-abcd --scan-file draft.html --json

EXIT CODE (scan/check modes)
────────────────────────────
    0 — no blocked domains found (or policy disabled)
    1 — at least one blocked domain found
    2 — invalid args / file not found
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Iterable
from urllib.parse import urlsplit

try:
    from scripts._core.file_bus import PLUGIN_ROOT
except ImportError:  # allow running as a loose script
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts._core.file_bus import PLUGIN_ROOT


CANONICAL_SCOPES: Final[tuple[str, ...]] = (
    "in_text_citations",
    "references",
    "outbound_links",
    "schema_citation",
)

# href="..." / href='...' extraction for HTML scanning.
_HREF_RE: Final[re.Pattern[str]] = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
# Bare http(s) URL extraction (covers APA strings, schema "url"/"sameAs" values,
# markdown links already-rendered, etc.). Trailing punctuation is trimmed.
_BARE_URL_RE: Final[re.Pattern[str]] = re.compile(r"""https?://[^\s"'<>)\]]+""", re.IGNORECASE)


def registrable_host(url_or_host: str) -> str:
    """Return the lowercased host with a single leading ``www.`` stripped.

    Accepts a full URL ("https://www.Fluence.com/x?y") or a bare host
    ("www.Fluence.com"). Port and userinfo are dropped. Returns "" when no host
    can be parsed.
    """
    if not url_or_host:
        return ""
    s = url_or_host.strip()
    # urlsplit needs the netloc to start with "//" to populate .hostname. Full
    # URLs already have it after the scheme; for a bare host (or a "//host"
    # fragment) we normalize to exactly one leading "//".
    if "://" in s:
        host = urlsplit(s).hostname or ""
    else:
        host = urlsplit("//" + s.lstrip("/")).hostname or ""
    host = host.lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def _normalize_blocklist(domains: Iterable[str]) -> frozenset[str]:
    out: set[str] = set()
    for d in domains or ():
        h = registrable_host(str(d))
        if h:
            out.add(h)
    return frozenset(out)


@dataclass(frozen=True)
class CompetitorPolicy:
    """Resolved competitor-citation policy for one project."""
    enabled: bool = False
    enforcement: str = "off"                 # hard_veto | warn | off
    domains: frozenset[str] = frozenset()
    scope: tuple[str, ...] = ()
    brands: tuple[str, ...] = ()
    allow_brand_mention_in_prose: bool = True
    datasheet_exception: bool = False
    sole_source_behavior: str = "research_replacement"
    project_slug: str | None = None

    # ── matching ──────────────────────────────────────────────────────────
    def is_blocked(self, url_or_host: str) -> bool:
        """True iff the URL's host is on (or a subdomain of) the blocklist."""
        if not self.enabled or not self.domains:
            return False
        host = registrable_host(url_or_host)
        if not host:
            return False
        return any(host == d or host.endswith("." + d) for d in self.domains)

    def blocked_domain_of(self, url_or_host: str) -> str | None:
        """Return the blocklist entry that matched, or None."""
        if not self.enabled or not self.domains:
            return None
        host = registrable_host(url_or_host)
        if not host:
            return None
        for d in self.domains:
            if host == d or host.endswith("." + d):
                return d
        return None

    def scope_enabled(self, scope_name: str) -> bool:
        """Whether enforcement applies to the given surface."""
        if not self.enabled:
            return False
        # Empty scope (opted in but unspecified) == all canonical surfaces.
        if not self.scope:
            return scope_name in CANONICAL_SCOPES
        return scope_name in self.scope

    def find_blocked_in_urls(self, urls: Iterable[str]) -> list[tuple[str, str]]:
        """Return [(url, matched_domain), ...] for every blocked URL."""
        hits: list[tuple[str, str]] = []
        for u in urls:
            d = self.blocked_domain_of(u)
            if d:
                hits.append((u, d))
        return hits

    def find_blocked_in_html(self, html: str) -> list[tuple[str, str]]:
        """Scan rendered HTML/text for blocked URLs.

        Looks at both ``href="..."`` attribute targets and bare ``http(s)://``
        URLs (so APA reference strings and JSON-LD url/sameAs values are caught
        even when not wrapped in an anchor). De-duplicated, source order.
        """
        if not self.enabled or not self.domains:
            return []
        seen: set[str] = set()
        candidates: list[str] = []
        for m in _HREF_RE.finditer(html or ""):
            candidates.append(m.group(1))
        for m in _BARE_URL_RE.finditer(html or ""):
            candidates.append(m.group(0).rstrip(".,;:"))
        hits: list[tuple[str, str]] = []
        for u in candidates:
            if u in seen:
                continue
            seen.add(u)
            d = self.blocked_domain_of(u)
            if d:
                hits.append((u, d))
        return hits

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "enforcement": self.enforcement,
            "domains": sorted(self.domains),
            "scope": list(self.scope) if self.scope else list(CANONICAL_SCOPES),
            "brands": list(self.brands),
            "allow_brand_mention_in_prose": self.allow_brand_mention_in_prose,
            "datasheet_exception": self.datasheet_exception,
            "sole_source_behavior": self.sole_source_behavior,
            "project_slug": self.project_slug,
        }


_DISABLED: Final[CompetitorPolicy] = CompetitorPolicy()


def _load_business_context(project_slug: str) -> dict | None:
    bc = PLUGIN_ROOT / "projects" / project_slug / "business-context.json"
    if not bc.exists():
        return None
    raw = bc.read_text(encoding="utf-8").lstrip("﻿")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(
            f"competitor_domains: could not parse {bc} ({e}); treating as no policy.",
            file=sys.stderr,
        )
        return None


def policy_from_config(cfg: dict | None, *, project_slug: str | None = None) -> CompetitorPolicy:
    """Build a CompetitorPolicy from a raw citation_source_policy dict.

    A null/empty config, ``exclude_competitor_domains: false``, or
    ``enforcement: "off"`` all yield a disabled policy.
    """
    if not cfg:
        return CompetitorPolicy(enabled=False, enforcement="off", project_slug=project_slug)
    enforcement = str(cfg.get("enforcement", "hard_veto")).lower()
    exclude = bool(cfg.get("exclude_competitor_domains", True))
    if not exclude or enforcement == "off":
        return CompetitorPolicy(enabled=False, enforcement="off", project_slug=project_slug)
    domains = _normalize_blocklist(cfg.get("do_not_cite_domains", []))
    scope_raw = cfg.get("scope") or []
    scope = tuple(s for s in scope_raw if s in CANONICAL_SCOPES)
    return CompetitorPolicy(
        enabled=True,
        enforcement=enforcement,
        domains=domains,
        scope=scope,
        brands=tuple(cfg.get("competitor_brands", []) or ()),
        allow_brand_mention_in_prose=bool(cfg.get("allow_brand_mention_in_prose", True)),
        datasheet_exception=bool(cfg.get("datasheet_exception", False)),
        sole_source_behavior=str(cfg.get("sole_source_behavior", "research_replacement")),
        project_slug=project_slug,
    )


def load_policy(project_slug: str | None = None) -> CompetitorPolicy:
    """Resolve the competitor policy for a project.

    When ``project_slug`` is None, falls back to the active project
    (env-first, per scripts/_core/active_project.py — Rule 7 safe).
    """
    if not project_slug:
        try:
            from scripts._core.active_project import get_active_project
            project_slug = get_active_project()
        except Exception:
            project_slug = None
    if not project_slug:
        return _DISABLED
    cfg = _load_business_context(project_slug)
    policy_cfg = (cfg or {}).get("citation_source_policy")
    return policy_from_config(policy_cfg, project_slug=project_slug)


def load_policy_for_task(task_id: str) -> CompetitorPolicy:
    """Resolve the competitor policy from a task's state.json::project_slug.

    Falls back to the active project when state.json is missing or has no slug.
    This is the entry point lint / verify / assemble use, since they operate on
    a workspace, not a project.
    """
    slug: str | None = None
    try:
        from scripts._core import file_bus as fb
        state = fb.read_state(task_id)
        slug = state.get("project_slug") or (state.get("brief") or {}).get("project_slug")
    except Exception:
        slug = None
    return load_policy(slug)


# ── CLI ──────────────────────────────────────────────────────────────────────

def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        pol = payload.get("policy", {})
        print(f"competitor_domains :: project={pol.get('project_slug')} "
              f"enabled={pol.get('enabled')} enforcement={pol.get('enforcement')}")
        print(f"  blocklist ({len(pol.get('domains', []))}): {', '.join(pol.get('domains', [])) or '—'}")
        if "hits" in payload:
            hits = payload["hits"]
            if not hits:
                print("  ✓ no blocked competitor domains found")
            else:
                print(f"  ✗ {len(hits)} blocked competitor domain reference(s):")
                for h in hits:
                    print(f"     • {h['matched_domain']}  ←  {h['url']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Competitor/peer-domain citation guard")
    who = ap.add_mutually_exclusive_group()
    who.add_argument("--project", type=str, help="Project slug")
    who.add_argument("--task", type=str, help="Task ID → resolve project from state.json")
    ap.add_argument("--check-url", type=str, help="Test a single URL against the blocklist")
    ap.add_argument("--scan-file", type=Path, help="Scan an HTML/markdown/text file for blocked URLs")
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    args = ap.parse_args(argv)

    policy = (
        load_policy_for_task(args.task) if args.task else load_policy(args.project)
    )
    payload: dict = {"policy": policy.to_dict()}

    rc = 0
    if args.check_url:
        d = policy.blocked_domain_of(args.check_url)
        hits = [{"url": args.check_url, "matched_domain": d}] if d else []
        payload["hits"] = hits
        rc = 1 if hits else 0
    elif args.scan_file:
        if not args.scan_file.exists():
            print(f"file not found: {args.scan_file}", file=sys.stderr)
            return 2
        text = args.scan_file.read_text(encoding="utf-8", errors="replace")
        hits = [{"url": u, "matched_domain": d} for (u, d) in policy.find_blocked_in_html(text)]
        payload["hits"] = hits
        rc = 1 if hits else 0

    _emit(payload, args.json)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
