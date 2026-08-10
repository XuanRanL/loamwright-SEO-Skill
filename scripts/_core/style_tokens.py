#!/usr/bin/env python3
"""Per-project style tokens — de-fingerprint the published output.

WHY (2026-08-01, open-source release)
-------------------------------------
Every post this plugin publishes used to carry the same class names
(``xr-cta-box``, ``article-signature``, ``{slug}-pillar`` …). Once the plugin
is public, that fixed vocabulary is a cross-site fingerprint: one regex finds
every adopter's site — and the maintainer's own fleet with them. This module
gives every (operator, project) pair its own unpredictable class vocabulary.

DESIGN — deterministic HMAC derivation, never LLM-generated
-----------------------------------------------------------
    salt              32 random bytes at ~/.xuanran-seo/credentials/.style-salt
                      (per-operator secret; created once under a file lock;
                      NEVER in the repo — with the mechanism public, the salt
                      is what keeps derived names unpredictable)
    prefix            b36(HMAC(salt, slug))[:6], first char forced alphabetic
    token(legacy)     f"{prefix}-" + b36(HMAC(salt, f"{slug}:{legacy}"))[:6]

Identifiers need no creativity, only unpredictability + reproducibility —
exactly what HMAC gives and an LLM cannot (Rule 6/9: runtime layers are
deterministic executors). LLM wording variants belong in project CONFIG,
generated once at /init and only ever read at runtime.

BOUNDARY MODEL — internal names stay legacy
-------------------------------------------
Drafts, lints, gates, agent contracts all keep the legacy vocabulary. The
mapping is applied ONLY where content meets the outside world:

    wp_publisher._apply_project_styling      body + inline CSS at publish
    verify_post                              expected names on the live URL
    reinject_* fleet tools                   live-post surgery
    attach_images_to_draft                   pending-image figure lookup

A project is "tokenized" iff ``projects/{slug}/brand/style-tokens.json``
exists (created by ``--generate``, called from /init step 11.9 or manually).
No file → every function returns/matches the legacy names → zero behavior
change for existing installs.

USAGE
-----
    python -m scripts._core.style_tokens --generate {slug} [--force] [--json]
    python -m scripts._core.style_tokens --show {slug} [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SALT_PATH = Path.home() / ".xuanran-seo" / "credentials" / ".style-salt"

# Legacy names that are NOT xr-* but are part of the published fingerprint.
LEGACY_SPECIAL: tuple[str, ...] = (
    "article-signature",
    "faq-question",
    "xuanran-pending-image",
    "xuanran-image-placeholder",
)

# Known xr-* component classes (generate() also scans the project CSS, so
# strays are caught there; transform() additionally derives on the fly).
LEGACY_XR: tuple[str, ...] = (
    "xr-cta-box", "xr-cta-banner", "xr-cta-quiet",
    "xr-stat-grid", "xr-checklist", "xr-glossary-list",
    "xr-card", "xr-card-kt", "xr-card-toc",
    "xr-accent", "xr-heading", "xr-border", "xr-strong",
    "xr-link", "xr-text", "xr-text-muted",
)

_B36 = "0123456789abcdefghijklmnopqrstuvwxyz"
_XR_STRAY_RE = re.compile(r"xr-[a-z0-9][a-z0-9-]*")


def legacy_wrapper_class(slug: str) -> str:
    """Mirror wp_publisher._slug_to_wrapper_class exactly (Rule 2 contract)."""
    return f"{slug.lower().replace('_', '-').replace('.', '-')}-pillar"


def tokens_path(slug: str) -> Path:
    return PLUGIN_ROOT / "projects" / slug / "brand" / "style-tokens.json"


def enabled(slug: str) -> bool:
    return tokens_path(slug).exists()


def ensure_salt() -> bytes:
    """Read the operator salt, creating it once (locked — Rule 7)."""
    if SALT_PATH.exists():
        return bytes.fromhex(SALT_PATH.read_text(encoding="utf-8").strip())
    from scripts._core.file_lock import locked

    with locked(SALT_PATH):
        if SALT_PATH.exists():  # lost the race — another session created it
            return bytes.fromhex(SALT_PATH.read_text(encoding="utf-8").strip())
        SALT_PATH.parent.mkdir(parents=True, exist_ok=True)
        salt = secrets.token_bytes(32)
        SALT_PATH.write_text(salt.hex() + "\n", encoding="utf-8")
        return salt


def _b36(digest: bytes, length: int) -> str:
    n = int.from_bytes(digest, "big")
    out: list[str] = []
    while len(out) < length:
        n, rem = divmod(n, 36)
        out.append(_B36[rem])
    return "".join(out)


def _hmac(salt: bytes, msg: str) -> bytes:
    return hmac.new(salt, msg.encode("utf-8"), hashlib.sha256).digest()


def derive_prefix(salt: bytes, slug: str) -> str:
    raw = _b36(_hmac(salt, slug), 6)
    if raw[0].isdigit():  # CSS identifiers must not start with a digit
        raw = _B36[10 + int(raw[0])] + raw[1:]
    return raw


def derive_token(salt: bytes, slug: str, legacy_name: str) -> str:
    prefix = derive_prefix(salt, slug)
    return f"{prefix}-{_b36(_hmac(salt, f'{slug}:{legacy_name}'), 6)}"


def _scan_css_classes(slug: str) -> set[str]:
    base = PLUGIN_ROOT / "projects" / slug / "brand"
    found: set[str] = set()
    for name in ("article-css.css", "article-css.min.css"):
        p = base / name
        if p.exists():
            found.update(_XR_STRAY_RE.findall(p.read_text(encoding="utf-8")))
    return found


def generate(slug: str, force: bool = False) -> dict[str, Any]:
    """Materialize the full legacy→token map for a project (idempotent)."""
    path = tokens_path(slug)
    if path.exists() and not force:
        raise SystemExit(f"{path} already exists (use --force to regenerate)")
    salt = ensure_salt()
    legacy_names = sorted(
        {*LEGACY_SPECIAL, *LEGACY_XR, *_scan_css_classes(slug),
         legacy_wrapper_class(slug)}
    )
    mapping = {name: derive_token(salt, slug, name) for name in legacy_names}
    if len(set(mapping.values())) != len(mapping):  # astronomically unlikely
        raise SystemExit(f"token collision for {slug} — report this")
    doc: dict[str, Any] = {
        "version": 1,
        "slug": slug,
        "prefix": derive_prefix(salt, slug),
        "map": mapping,
        "salt_fp": hashlib.sha256(salt).hexdigest()[:12],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return doc


def load_map(slug: str) -> dict[str, str] | None:
    """legacy→token map, or None when the project is not tokenized."""
    path = tokens_path(slug)
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in doc.get("map", {}).items()}


def class_for(slug: str, legacy_name: str) -> str:
    """Resolve one class name: token when tokenized, else the legacy name."""
    mapping = load_map(slug)
    if mapping is None:
        return legacy_name
    tok = mapping.get(legacy_name)
    if tok is None:  # stray not in the file — derive (same pure function)
        tok = derive_token(ensure_salt(), slug, legacy_name)
    return tok


def wrapper_class(slug: str) -> str:
    return class_for(slug, legacy_wrapper_class(slug))


def match_alternation(slug: str, legacy_name: str) -> str:
    """Regex fragment matching legacy OR token form (mixed-state fleet tools)."""
    token = class_for(slug, legacy_name)
    if token == legacy_name:
        return re.escape(legacy_name)
    return f"(?:{re.escape(legacy_name)}|{re.escape(token)})"


def transform(text: str, slug: str) -> str:
    """Rewrite every legacy class name in HTML/CSS text to the project token.

    No-op for non-tokenized projects. Word-boundary safe: ``xr-card`` never
    matches inside ``xr-card-kt`` (the trailing guard rejects a following
    ``[\\w-]``), and CSS selectors (``.xr-card``) match like attributes.
    """
    mapping = load_map(slug)
    if mapping is None:
        return text
    salt = ensure_salt()
    known = sorted(mapping, key=len, reverse=True)
    pattern = re.compile(
        r"(?<![\w-])("
        + "|".join(re.escape(k) for k in known)
        + r"|xr-[a-z0-9][a-z0-9-]*)(?![\w-])"
    )

    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        return mapping.get(name) or derive_token(salt, slug, name)

    return pattern.sub(repl, text)


def reverse_transform(text: str, slug: str) -> str:
    """Token→legacy (for --revert). Uses the file map inverted."""
    mapping = load_map(slug)
    if mapping is None:
        return text
    inverse = {v: k for k, v in mapping.items()}
    pattern = re.compile(
        r"(?<![\w-])("
        + "|".join(re.escape(t) for t in sorted(inverse, key=len, reverse=True))
        + r")(?![\w-])"
    )
    return pattern.sub(lambda m: inverse[m.group(1)], text)


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-project style-token manager")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--generate", metavar="SLUG")
    g.add_argument("--show", metavar="SLUG")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--json", action="store_true", dest="as_json")
    a = ap.parse_args()

    if a.generate:
        doc = generate(a.generate, force=a.force)
        if a.as_json:
            print(json.dumps(doc, indent=2, ensure_ascii=False))
        else:
            print(f"[style-tokens] {a.generate}: prefix={doc['prefix']} "
                  f"({len(doc['map'])} classes) → {tokens_path(a.generate)}")
        return 0

    mapping = load_map(a.show)
    if mapping is None:
        print(f"[style-tokens] {a.show}: NOT tokenized (legacy names in use)")
        return 1
    if a.as_json:
        print(json.dumps(mapping, indent=2, ensure_ascii=False))
    else:
        for k, v in sorted(mapping.items()):
            print(f"  {k:<28} → {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
