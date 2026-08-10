"""scripts/build/category_selector.py — Per-article category selection (root-cause fix 2026-05-23c).

PROBLEM
─────────
Before this script existed, every article published by the project-charlie pipeline
went into the same single category (144 LED Buyer Guides). Audit of the last 13
posts showed 100% concentration in that one category, when at least 3 sibling
categories (LED & HPS Comparisons, LED Technology Deep Dives, HPS-to-LED Retrofit)
should have received some content.

ROOT CAUSE (per Rule 6 of CLAUDE.md "markdown is NOT an executor")
─────────────────────────────────────────────────────────────────
The meta-builder SKILL.md documented this logic in pseudo-code:

    # Pick from research.topic_clusters or business-context.default_categories
    categories = business_context.default_categories or [derive_from_content]

The `[derive_from_content]` branch was never implemented anywhere in scripts/.
With no executor, every article fell through to `business_context.default_categories`
which is a single static list. The orchestrator then silently copied that list
into meta.json. wp_publisher accepted it without challenge.

This file IS the executor. The seo-blog SKILL.md Plan phase now invokes it
between outline-architect and Phase Optimize so meta.json gets properly-scored
categories before the publisher reads it.

HOW IT WORKS
─────────────
Deterministic signal-based scoring. NO LLM call.

For each candidate category in the project's `categories-config.json`, evaluates:
  - format_id_match: does angle.format_id match any of the listed formats?
  - product_h3_min: does the body contain ≥N product-style H3s? (signal for comparison content)
  - body_keywords_any: does the body contain ANY of the listed keywords?
  - body_keywords_all: does the body contain ALL of the listed keywords?
  - title_keywords_any: does meta.title contain ANY of the listed keywords?

DEFAULT SEMANTICS: ANY signal match triggers the category (OR logic).
This is the correct semantics for cross-cutting categorization — e.g. a
"comparison" category should trigger if EITHER format=comparison OR body has
3+ product H3s OR body has comparison vocabulary. Requiring all three blocks
the cross-cuts and is the root cause of the original "all → single category"
bug we're fixing.

Override per-category by setting `trigger_logic: "all"` if you want stricter
behavior (e.g. System Pillars needs ALL of [fixture, electrical, ventilation]
to qualify as multi-subsystem pillar content).

The project's `business-context.json :: default_categories` are ALWAYS included
as fallback (preserves existing behavior on projects without signals defined).

BACKWARDS-COMPATIBLE
────────────────────
Projects without `auto_select_signals` defined on any category fall through to
the existing behavior (default-only). Add signals incrementally per category
when ready.

USAGE
──────
    # Reads workspace/{task_id}/{draft.md, angle.json, meta.json},
    # plus projects/{slug}/{categories-config.json, business-context.json}.
    # Writes updated meta.json with refined categories[] in place.
    python -m scripts.build.category_selector --task-id {task_id} --project-slug {slug}

    # Dry-run: show recommendation without modifying meta.json
    python -m scripts.build.category_selector --task-id {task_id} --project-slug {slug} --dry-run --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class CategoryDecision:
    """One category that the selector recommends."""
    slug: str
    name: str
    reason: str             # human-readable trigger that matched
    is_default: bool        # came from business-context.json default_categories
    signals_matched: list[str] = field(default_factory=list)
    score: float = 0.0      # higher = stronger match (for capping)
    parent: str | None = None  # parent slug from config (for the deepest-node depth rule)


@dataclass
class SelectorResult:
    task_id: str
    project_slug: str
    recommended_categories: list[CategoryDecision]
    rejected_categories: list[dict]   # candidates that didn't match, with reasons
    meta_updated: bool
    detail: str

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "project_slug": self.project_slug,
            "recommended_categories": [asdict(c) for c in self.recommended_categories],
            "rejected_categories": self.rejected_categories,
            "meta_updated": self.meta_updated,
            "detail": self.detail,
        }


# ─── Live-snapshot normalization (2026-07-01) ───────────────────────────────

def _normalize_live_snapshot(raw: dict | None) -> dict | None:
    """Normalize categories-live.json into the canonical snapshot shape.

    TWO producers write this file with DIFFERENT schemas:
    - `scripts/wordpress/snapshot_categories.py` → {categories_by_id, name_to_id, slug_to_id}
    - `scripts/wordpress/setup_categories.py` ("applied" format) → {applied_at, categories:[...]}

    Consumers (the ID-attach below, the weekly-digest name/slug pin) were written
    against the FIRST shape only, so a project whose file came from setup_categories
    (loamwright) got a permanent silent no-op: `category_ids` never attached, every
    publish fell to the slow name/slug path (which mis-resolved post 788 into the
    "Digital PR" subcategory). Deriving the canonical maps from the applied format
    cures the class for every project, whichever tool produced the file.
    """
    import html
    if not isinstance(raw, dict):
        return raw
    if isinstance(raw.get("name_to_id"), dict) and isinstance(raw.get("categories_by_id"), dict):
        return raw
    # v3.41.2: ALSO accept the wp/v2/categories REST shape ({..., terms:[...]},
    # the project-lima-style snapshot). Pre-fix this fell to the bare-shapes branch
    # below, which guarantees slug_to_id but NEVER derives name_to_id /
    # categories_by_id — so every name-based consumer (the digest name/slug pin,
    # the preserve-meta step) silently no-opped on projects with that snapshot.
    cats = raw.get("categories")
    if not isinstance(cats, list):
        cats = raw.get("terms")
    if not isinstance(cats, list):
        # Hand-authored / bare shapes. Guarantee a usable slug_to_id so the
        # slug-based ID-attach works for every project regardless of schema.
        if not isinstance(raw.get("slug_to_id"), dict):
            derived = _derive_slug_to_id_any(raw)
            if derived:
                out = dict(raw)
                out["slug_to_id"] = derived
                return out
        return raw
    categories_by_id: dict[str, dict] = {}
    name_to_id: dict[str, int] = {}
    slug_to_id: dict[str, int] = {}
    for c in cats:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if not isinstance(cid, int) or isinstance(cid, bool):
            continue
        name = html.unescape(str(c.get("name") or "")).strip()
        slug = str(c.get("slug") or "").strip()
        categories_by_id[str(cid)] = {"name": name, "slug": slug,
                                      "parent": c.get("parent") or c.get("parent_id") or 0}
        if name:
            name_to_id.setdefault(name, cid)
        if slug:
            slug_to_id.setdefault(slug, cid)
    out = dict(raw)
    out["categories_by_id"] = categories_by_id
    out["name_to_id"] = name_to_id
    out["slug_to_id"] = slug_to_id
    return out


def _derive_slug_to_id_any(raw: dict) -> dict[str, int]:
    """Best-effort slug→id from ANY hand-authored categories-live.json shape.

    The portfolio has ~6 distinct snapshot schemas (2026-07-17 survey):
    canonical {categories_by_id, name_to_id, slug_to_id}; setup "applied"
    {categories:[...]}; hand {generated_at, slug_to_id}; project-lima
    {captured_at, ..., slug_to_id, terms}; a bare {slug:int} flat map; and
    project-foxtrot/project-mike {slug:{id,parent,...}} object maps. The ID-attach resolves
    by SLUG, so every one of these carries enough to attach an id — as long as
    we can find the slug→id relation. This finds it regardless of wrapper keys.
    """
    out: dict[str, int] = {}
    for k, v in raw.items():
        if not isinstance(k, str):
            continue
        if isinstance(v, int) and not isinstance(v, bool):
            out[k] = v  # {slug: id} flat map
        elif isinstance(v, dict) and isinstance(v.get("id"), int) and not isinstance(v.get("id"), bool):
            out[k] = v["id"]  # {slug: {id, parent, ...}} object map
    return out


def _lookup_name_id(name_to_id: dict, name: str) -> int | None:
    """Exact name→id lookup with an HTML-entity/case/whitespace-tolerant fallback."""
    import html
    if name in name_to_id:
        return name_to_id[name]
    norm = " ".join(html.unescape(name).split()).lower()
    for k, v in name_to_id.items():
        if " ".join(html.unescape(str(k)).split()).lower() == norm:
            return v
    return None


# ─── Signal evaluators ──────────────────────────────────────────────────────

def _normalize_body(body: str) -> str:
    """Lowercase + strip frontmatter for keyword matching."""
    # Strip YAML frontmatter if present
    if body.startswith("---\n"):
        end = body.find("\n---\n", 4)
        if end != -1:
            body = body[end + 5:]
    return body.lower()


def _count_product_h3s(body: str) -> int:
    """Count H3s that look like '### #N Product Name' or '### Product Name (~$NNN)' patterns.

    Heuristic for buyer-guide listicles — indicates multi-product comparison content.
    """
    # Match H3s with numbered list markers (#1, #2, #3 — typical listicle format)
    numbered = re.findall(r"^###\s*#\d+\b", body, flags=re.MULTILINE)
    # Match H3s with price markers (~$199, $429, etc) — typical product H3 pattern
    priced = re.findall(r"^###\s+[^\n]*\(\s*~?\$\d+", body, flags=re.MULTILINE)
    return max(len(numbered), len(priced))


def _eval_format_id_match(signals: dict, angle: dict) -> tuple[bool, str, int]:
    """Returns (passed, message, match_count). match_count is 1 if format matches, 0 otherwise."""
    needed = signals.get("format_id_match", [])
    if not needed:
        return True, "", 0  # not specified → vacuously satisfied, no contribution
    fmt = (angle.get("format_id") or angle.get("format") or "").lower()
    if fmt in [s.lower() for s in needed]:
        return True, f"format_id={fmt} ∈ {needed}", 1
    return False, f"format_id={fmt} not in {needed}", 0


def _eval_product_h3_min(signals: dict, body_lower: str, body_raw: str) -> tuple[bool, str, int]:
    """Returns (passed, message, excess). excess = max(0, actual-needed) measures how clearly it exceeds the bar."""
    needed = signals.get("product_h3_min")
    if needed is None:
        return True, "", 0
    actual = _count_product_h3s(body_raw)
    if actual >= needed:
        # Excess over threshold counts as strength: 7 product H3s is stronger evidence than 3
        return True, f"product_h3_count={actual} ≥ {needed}", max(1, actual - needed + 1)
    return False, f"product_h3_count={actual} < {needed}", 0


def _eval_body_keywords_any(signals: dict, body_lower: str) -> tuple[bool, str, int]:
    """Returns (passed, message, match_count). match_count = number of distinct keywords found.

    Respects optional `body_keywords_any_min_matches` (default 1) to require a higher bar.
    Use for categories like LED Technology Deep Dives where one diode-name mention isn't
    enough — the article must be PRIMARILY about chip/driver/spectrum technology.
    """
    keywords = signals.get("body_keywords_any", [])
    if not keywords:
        return True, "", 0
    min_matches = signals.get("body_keywords_any_min_matches", 1)
    matched = [k for k in keywords if k.lower() in body_lower]
    if len(matched) >= min_matches:
        return True, f"matched body_keywords_any ({len(matched)}≥{min_matches}): {matched[:3]}", len(matched)
    if matched:
        return False, f"only {len(matched)} body_keywords_any matched (need ≥{min_matches}): {matched}", 0
    return False, f"no body_keywords_any matched (looked for {keywords[:5]})", 0


def _eval_body_keywords_all(signals: dict, body_lower: str) -> tuple[bool, str, int]:
    """Returns (passed, message, match_count). match_count = number of keywords required (full set)."""
    keywords = signals.get("body_keywords_all", [])
    if not keywords:
        return True, "", 0
    missing = [k for k in keywords if k.lower() not in body_lower]
    if not missing:
        return True, f"all body_keywords_all matched ({len(keywords)})", len(keywords)
    return False, f"missing body_keywords_all: {missing}", 0


def _eval_title_keywords_any(signals: dict, title_lower: str) -> tuple[bool, str, int]:
    """Returns (passed, message, match_count). match_count = number of title-keyword matches."""
    keywords = signals.get("title_keywords_any", [])
    if not keywords:
        return True, "", 0
    matched = [k for k in keywords if k.lower() in title_lower]
    if matched:
        return True, f"matched title_keywords_any: {matched[:3]}", len(matched)
    return False, "no title_keywords_any matched", 0


# ─── Main selection ─────────────────────────────────────────────────────────

# Per-signal-type confidence weights. Higher = stronger evidence.
# Rationale:
#   - format_id_match is editorial intent declared upstream → highest weight
#   - product_h3_min is structural evidence (counted, not guessed) → high
#   - title_keywords_any is in the title → high specificity
#   - body_keywords_any is the weakest evidence (a single keyword mention
#     can trigger; lots of cross-cutting incidental hits possible)
_SIGNAL_WEIGHTS = {
    "format_id_match": 3.0,
    "product_h3_min": 3.0,
    "title_keywords_any": 2.0,
    "body_keywords_all": 2.0,
    "body_keywords_any": 1.0,
}


def select_categories(
    task_id: str,
    project_slug: str | None,
    *,
    apply_to_meta: bool = True,
    max_categories: int | None = None,
    preserve_meta: bool = True,
) -> SelectorResult:
    """Run the per-article category selection.

    max_categories cap precedence: explicit argument > business-context.json ::
    `category_policy.max_per_article` > sensible default of 3. Projects with rich
    cross-cutting content (system pillars + comparisons + retrofit + tech) should
    set 4-5; pure single-axis sites stay at 3.

    preserve_meta (v3.41.2, default True): meta-builder's live-resolvable
    categories[] are PRESERVED and the selector's scored candidates fill the
    remaining cap slots, instead of replacing the list wholesale. The selector
    scores body keywords; it cannot see format/intent, which is exactly what the
    meta-builder encodes (a buyers-guide belongs in the buyer-guides category even
    when slope-safety prose out-scores it). Replace-not-merge dropped the most apt
    category on 4 real articles (project-foxtrot 2026-07-14; all 3 project-lima 2026-07-18,
    including pricing-cost dropped from a PRICING article). `--replace-meta`
    restores the old behavior for deliberate re-categorization runs.
    """
    workspace = PLUGIN_ROOT / "memory" / "workspace" / task_id
    if not workspace.exists():
        return SelectorResult(
            task_id=task_id, project_slug=project_slug or "",
            recommended_categories=[], rejected_categories=[],
            meta_updated=False, detail=f"workspace not found: {workspace}",
        )

    # Read project config (if project_slug provided)
    default_categories: list[str] = []
    categories_config: list[dict] = []
    project_max: int | None = None
    live_snapshot: dict | None = None
    digest_category_id: int | None = None
    if project_slug:
        cc_path = PLUGIN_ROOT / "projects" / project_slug / "categories-config.json"
        bc_path = PLUGIN_ROOT / "projects" / project_slug / "business-context.json"
        live_path = PLUGIN_ROOT / "projects" / project_slug / "categories-live.json"
        if cc_path.exists():
            cc = json.loads(cc_path.read_text(encoding="utf-8"))
            categories_config = cc.get("categories", [])
        if bc_path.exists():
            bc = json.loads(bc_path.read_text(encoding="utf-8"))
            wp_cfg = bc.get("wordpress", {})
            default_categories = wp_cfg.get("default_categories", [])
            cp = bc.get("category_policy", {})
            project_max = cp.get("max_per_article")
            # Weekly-digest series has its own dedicated WP category (H1 / Rule 6).
            _wd = bc.get("weekly_digest") or {}
            _cid = _wd.get("category_id")
            # bool is an int subclass: `isinstance(True, int)` is True and
            # `int(True) == 1`, so a malformed `"category_id": true` would silently
            # pin category 1 (Uncategorized) — the exact bug H1 fixed. Exclude bool.
            if _wd.get("enabled") and isinstance(_cid, int) and not isinstance(_cid, bool):
                digest_category_id = int(_cid)
        # Load WP-live snapshot to attach IDs to recommendations (no WP round-trip needed
        # at publish time). Regenerate via `python -m scripts.wordpress.snapshot_categories`.
        if live_path.exists():
            try:
                live_snapshot = _normalize_live_snapshot(
                    json.loads(live_path.read_text(encoding="utf-8"))
                )
            except Exception:
                live_snapshot = None

    # Resolve cap: explicit arg > project override > default 3
    if max_categories is None:
        max_categories = project_max if isinstance(project_max, int) else 3

    # Read workspace artifacts
    angle: dict = {}
    angle_path = workspace / "angle.json"
    if angle_path.exists():
        angle = json.loads(angle_path.read_text(encoding="utf-8"))

    meta: dict = {}
    meta_path = workspace / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # ── Weekly-digest dedicated-category pin (H1 / Rule 6) ────────────────────
    # A weekly digest goes to its own series category (weekly_digest.category_id),
    # not content-derived categories. This is the executor behind SKILL.md's
    # "publisher targets the digest category" claim, which previously had NONE —
    # so digests silently fell through to Uncategorized (id 1). Pin the dedicated
    # category and short-circuit the content-derived selection.
    # H5: a project that ENABLED the weekly digest but forgot (or mistyped)
    # category_id would silently fall through to the content-derived path and land
    # in Uncategorized — warn loudly instead of reproducing the original symptom.
    if angle.get("format_id") == "weekly-digest" and digest_category_id is None:
        print(
            "⚠ category_selector: this article is a weekly-digest but no valid "
            "integer weekly_digest.category_id is configured in "
            "business-context.json — it will fall back to the content-derived "
            "category (likely Uncategorized). Set weekly_digest.category_id.",
            file=sys.stderr,
        )

    if angle.get("format_id") == "weekly-digest" and digest_category_id is not None:
        # The category NAME/slug are PROJECT state, not skill state — derive them
        # from the project's WP live snapshot (categories-live.json) so the pinned
        # meta['categories'] matches the ACTUAL WordPress category the ID points to
        # (it may be "SEO News", "Industry Weekly", etc., not literally "Weekly
        # Digest"). Generic fallback keeps this skill code client-agnostic when no
        # snapshot is present (project/skill separation).
        digest_cat_name = "Weekly Digest"
        digest_cat_slug = "weekly-digest"
        if isinstance(live_snapshot, dict):
            _by_id = live_snapshot.get("categories_by_id") or {}
            _entry = _by_id.get(str(digest_category_id)) if isinstance(_by_id, dict) else None
            if isinstance(_entry, dict):
                digest_cat_name = str(_entry.get("name") or digest_cat_name)
                digest_cat_slug = str(_entry.get("slug") or digest_cat_slug)
        decision = CategoryDecision(
            slug=digest_cat_slug,
            name=digest_cat_name,
            reason=f"weekly_digest.category_id={digest_category_id} (dedicated series category)",
            is_default=True,
            signals_matched=["weekly_digest"],
        )
        meta_updated = False
        if apply_to_meta and meta_path.exists():
            want_ids = [digest_category_id]
            # Pin the ID AND ensure the NAME list is non-empty: the mandatory
            # pre_publish_gate.check_meta FAILs (and blocks publish) when
            # meta['categories'] is empty, even though category_ids is what the
            # publisher actually assigns. Pinning only IDs left names empty and
            # hard-blocked the digest (Bug H2). Don't clobber an existing name list.
            need_names = not meta.get("categories")
            if meta.get("category_ids") != want_ids or need_names:
                meta["category_ids"] = want_ids
                if need_names:
                    meta["categories"] = [decision.name]
                meta_path.write_text(
                    json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                meta_updated = True
        return SelectorResult(
            task_id=task_id,
            project_slug=project_slug or "",
            recommended_categories=[decision],
            rejected_categories=[],
            meta_updated=meta_updated,
            detail=f"weekly-digest dedicated category pinned (id={digest_category_id})",
        )

    draft_path = workspace / "draft.md"
    if not draft_path.exists():
        return SelectorResult(
            task_id=task_id, project_slug=project_slug or "",
            recommended_categories=[], rejected_categories=[],
            meta_updated=False, detail=f"draft.md not found in {workspace}",
        )
    body_raw = draft_path.read_text(encoding="utf-8")
    body_lower = _normalize_body(body_raw)
    title_lower = (meta.get("title") or angle.get("title") or "").lower()

    # ── Build the decision set ────────────────────────────────────────────

    # Index by name for default-categories lookup
    by_name = {c["name"]: c for c in categories_config if "name" in c}

    recommended: list[CategoryDecision] = []
    rejected: list[dict] = []
    seen_slugs: set[str] = set()

    # Step 1 — always include project default_categories (preserves backwards-compat)
    for default_name in default_categories:
        cat = by_name.get(default_name)
        if cat:
            slug = cat.get("slug", default_name.lower().replace(" ", "-"))
            if slug not in seen_slugs:
                recommended.append(CategoryDecision(
                    slug=slug, name=default_name,
                    reason="project default (always included)",
                    is_default=True, signals_matched=["is_default"],
                ))
                seen_slugs.add(slug)
        else:
            # Default name not in categories-config — include with bare name
            recommended.append(CategoryDecision(
                slug=default_name.lower().replace(" ", "-").replace("&", "and"),
                name=default_name,
                reason="project default (not found in categories-config — bare include)",
                is_default=True, signals_matched=["is_default"],
            ))
            seen_slugs.add(default_name.lower())

    # Step 1b — preserve the meta-builder's deliberate, live-resolvable picks
    # (v3.41.2 root cure). The scorer below sees BODY KEYWORDS only; the
    # meta-builder chose from format + intent, a signal this function cannot
    # reconstruct. Before this step, any recommendation REPLACED meta wholesale
    # (step 3), which dropped the most apt category on 4 real articles
    # (project-foxtrot 2026-07-14; all 3 project-lima 2026-07-18 — a pricing article lost
    # pricing-cost to parts-wear body keywords). Preserved picks occupy cap
    # slots FIRST; scored candidates fill what remains. Names that do not
    # resolve in the live snapshot are NOT preserved (stale/junk names still
    # fall away, keeping the 2026-07-01 hand-authored-names safety intact).
    if preserve_meta:
        _by_id = (live_snapshot or {}).get("categories_by_id") or {}
        _name_to_id = (live_snapshot or {}).get("name_to_id") or {}
        for _name in list(meta.get("categories") or []):
            _cid = _lookup_name_id(_name_to_id, str(_name))
            if not isinstance(_cid, int):
                continue  # unresolvable on the live site — do not preserve
            _entry = _by_id.get(str(_cid)) if isinstance(_by_id, dict) else None
            _slug = str((_entry or {}).get("slug") or "").strip() or (
                str(_name).lower().replace(" ", "-").replace("&", "and"))
            if _slug in seen_slugs:
                continue
            recommended.append(CategoryDecision(
                slug=_slug,
                name=str((_entry or {}).get("name") or _name),
                reason=("meta-builder pick preserved (format/intent signal the "
                        "body-keyword scorer cannot see; v3.41.2)"),
                is_default=False,
                signals_matched=["meta_builder_preserved"],
            ))
            seen_slugs.add(_slug)

    # Step 2 — evaluate each category's auto_select_signals
    # Default semantics: ANY non-vacuous signal that passes → category triggered.
    # Override per-category with `trigger_logic: "all"` for strict AND semantics
    # (only one use case: multi-subsystem System Pillars needs to satisfy all of
    # fixture+electrical+ventilation to count as integrated-system content).
    candidate_decisions: list[CategoryDecision] = []
    for cat in categories_config:
        slug = cat.get("slug")
        name = cat.get("name")
        signals = cat.get("auto_select_signals")
        if not signals or not slug or not name:
            continue
        if slug in seen_slugs:
            continue  # already included as default

        trigger_logic = (signals.get("trigger_logic") or "any").lower()

        # Evaluate each signal type. Each returns (passed, msg, match_count).
        evals = [
            ("format_id_match", _eval_format_id_match(signals, angle)),
            ("product_h3_min", _eval_product_h3_min(signals, body_lower, body_raw)),
            ("body_keywords_any", _eval_body_keywords_any(signals, body_lower)),
            ("body_keywords_all", _eval_body_keywords_all(signals, body_lower)),
            ("title_keywords_any", _eval_title_keywords_any(signals, title_lower)),
        ]
        non_vacuous = [(sig_type, ok, msg, count) for sig_type, (ok, msg, count) in evals if msg]
        if not non_vacuous:
            continue

        matched = [(sig_type, msg, count) for sig_type, ok, msg, count in non_vacuous if ok]
        failed = [(sig_type, msg) for sig_type, ok, msg, _ in non_vacuous if not ok]

        if trigger_logic == "all":
            triggered = bool(matched) and not failed
        else:  # "any" — default
            triggered = bool(matched)

        if triggered:
            # Score = sum of (match_count × type_weight) so 3 keyword matches outscore 1
            score = sum(count * _SIGNAL_WEIGHTS.get(sig_type, 1.0) for sig_type, _, count in matched)
            candidate_decisions.append(CategoryDecision(
                slug=slug, name=name,
                reason=f"[{trigger_logic}] " + "; ".join(msg for _, msg, _ in matched),
                is_default=False,
                signals_matched=[f"{sig_type}({count}): {msg}" for sig_type, msg, count in matched],
                score=score,
                parent=(cat.get("parent") or None),
            ))
        else:
            reject_reason = "; ".join(msg for _, msg in failed) if failed else "no signals matched"
            rejected.append({
                "slug": slug, "name": name,
                "reason": f"[{trigger_logic}] {reject_reason}",
            })

    # Step 2b — rank candidates by score (descending), cap at max_categories
    # (default 3) MINUS the defaults already included. Defaults always survive.
    candidate_decisions.sort(key=lambda d: d.score, reverse=True)
    slots_remaining = max(0, max_categories - len(recommended))
    accepted = candidate_decisions[:slots_remaining]
    over_cap = candidate_decisions[slots_remaining:]

    # Step 2c-depth — the "deepest relevant node" contract (2026-07-17). Each
    # ACCEPTED pick descends to its deepest matched descendant: if the winning
    # category also has a matched child, the child (same relevance, more specific)
    # represents the article. This cures the case where a top-level category with
    # a broad keyword list out-scores its own child (project-bravo flowerset: parent
    # "Teaware & Care" beat its child "Teaware Guides"). Crucially it descends the
    # WINNER within its own branch — it never drops a parent and lets an UNRELATED
    # childless top-level bubble up (which a naive "drop all parents" rule did,
    # promoting "Gifting" onto a hibiscus buyer's guide).
    _by_slug = {d.slug: d for d in candidate_decisions}
    _children_of: dict[str, list] = {}
    for d in candidate_decisions:
        if d.parent and d.parent in _by_slug:
            _children_of.setdefault(d.parent, []).append(d)

    def _deepest_matched(dec):
        seen_local = {dec.slug}
        while True:
            kids = [k for k in _children_of.get(dec.slug, []) if k.slug not in seen_local]
            if not kids:
                return dec
            dec = max(kids, key=lambda c: c.score)
            seen_local.add(dec.slug)

    if accepted:
        descended = []
        for d in accepted:
            deep = _deepest_matched(d)
            if deep.slug != d.slug:
                rejected.append({
                    "slug": d.slug, "name": d.name,
                    "reason": (f"score={d.score:.1f} superseded by its deeper relevant node "
                               f"'{deep.slug}' (deepest-node rule)"),
                })
            if deep.slug not in {x.slug for x in descended}:
                descended.append(deep)
        accepted = descended
    for d in over_cap:
        rejected.append({
            "slug": d.slug, "name": d.name,
            "reason": f"score={d.score:.1f} dropped (over max_categories={max_categories} cap; "
                      f"kept top {slots_remaining} non-default categor{'y' if slots_remaining == 1 else 'ies'})",
        })
    for d in accepted:
        recommended.append(d)
        seen_slugs.add(d.slug)

    # Step 3 — update meta.json if requested. Also attach resolved WP IDs from
    # the local snapshot so wp_publisher can skip name→ID GETs at publish time.
    #
    # 2026-07-01: the ID-attach now ALSO runs when the selector recommends nothing
    # but meta.json already carries hand-authored categories[] — previously those
    # articles never got category_ids and fell to the publisher's slow name/slug
    # resolution (the path that put post 788 in the wrong subcategory).
    meta_updated = False
    if apply_to_meta and meta_path.exists() and (recommended or meta.get("categories")):
        meta_changed = False
        slug_to_id = (live_snapshot or {}).get("slug_to_id") or {}

        if recommended:
            # The selector is CHANGING the category. Names and IDs MUST move
            # together or not at all — writing new names while leaving the old
            # category_ids in place is the recurring name↔id divergence bug
            # (2026-07-17: it produced meta.categories=["Teaware & Care"] with
            # category_ids=[143] on 3/3 project-bravo articles, masked only
            # because wp_publisher prefers the id). Resolve ids BY SLUG (works
            # across every categories-live.json shape) and apply atomically.
            new_cats = [c.name for c in recommended]
            new_ids_opt = [slug_to_id.get(c.slug) for c in recommended]
            all_resolved = new_ids_opt and all(isinstance(i, int) for i in new_ids_opt)
            if all_resolved:
                if meta.get("categories") != new_cats:
                    meta["categories"] = new_cats
                    meta_changed = True
                if meta.get("category_ids") != new_ids_opt:
                    meta["category_ids"] = new_ids_opt
                    meta_changed = True
            else:
                # Cannot resolve every pick to an id → DO NOT touch meta. Leave
                # the meta-builder's deliberate, already-consistent categories +
                # category_ids intact rather than write a self-contradictory pair.
                unresolved = [c.slug for c, i in zip(recommended, new_ids_opt)
                              if not isinstance(i, int)]
                print(
                    f"⚠ category_selector: {len(unresolved)} recommended slug(s) not "
                    f"in the live snapshot: {unresolved}. Leaving meta.categories / "
                    f"category_ids UNCHANGED (refusing to write a name without a "
                    f"matching id). Refresh with "
                    f"`python -m scripts.wordpress.snapshot_categories {project_slug}`.",
                    file=sys.stderr,
                )
        else:
            # No recommendation — attach ids to hand-authored existing names only.
            # This never changes names, so it cannot create a divergence.
            new_cats = list(meta.get("categories") or [])
            name_to_id = (live_snapshot or {}).get("name_to_id") or {}
            cat_ids_opt = [_lookup_name_id(name_to_id, n) for n in new_cats]
            cat_ids = [i for i in cat_ids_opt if isinstance(i, int)]
            if cat_ids and len(cat_ids) == len(new_cats) and meta.get("category_ids") != cat_ids:
                # Only attach when EVERY name resolved (a partial attach would
                # itself be a divergence). Otherwise leave meta as the operator set it.
                meta["category_ids"] = cat_ids
                meta_changed = True

        if meta_changed:
            meta_path.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8",
            )
            meta_updated = True

    detail = (
        f"{len(recommended)} categor{'y' if len(recommended) == 1 else 'ies'} recommended"
        f" ({len([c for c in recommended if c.is_default])} default + "
        f"{len([c for c in recommended if not c.is_default])} signal-matched);"
        f" {len(rejected)} candidate(s) rejected"
    )

    return SelectorResult(
        task_id=task_id,
        project_slug=project_slug or "",
        recommended_categories=recommended,
        rejected_categories=rejected,
        meta_updated=meta_updated,
        detail=detail,
    )


# ─── CLI ────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task-id", required=True, help="Workspace task ID")
    ap.add_argument(
        "--project-slug",
        required=False,
        help="Project slug (e.g. project-charlie). If omitted, attempts to read from state.json",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show recommendation without modifying meta.json",
    )
    ap.add_argument("--json", action="store_true", help="Emit JSON result to stdout")
    ap.add_argument(
        "--max-categories",
        type=int,
        default=None,
        help="Cap on total categories per article (defaults + signal-matched combined). "
             "If omitted: respects `category_policy.max_per_article` in project's "
             "business-context.json, else falls back to 3. "
             "Defaults are always kept; signal-matched are ranked by score and capped to fit.",
    )
    ap.add_argument(
        "--replace-meta",
        action="store_true",
        help="Restore the pre-v3.41.2 behavior: the selector's picks REPLACE the "
             "meta-builder's categories wholesale instead of preserving them and "
             "filling remaining cap slots. Use only for deliberate re-categorization.",
    )
    args = ap.parse_args(argv)

    # Auto-derive project_slug from state.json if not provided
    project_slug = args.project_slug
    if not project_slug:
        state_path = PLUGIN_ROOT / "memory" / "workspace" / args.task_id / "state.json"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                project_slug = state.get("project_slug")
            except Exception:
                pass

    result = select_categories(
        task_id=args.task_id,
        project_slug=project_slug,
        apply_to_meta=not args.dry_run,
        max_categories=args.max_categories,
        preserve_meta=not args.replace_meta,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        flag = "DRY-RUN" if args.dry_run else ("UPDATED" if result.meta_updated else "NO-CHANGE")
        print(f"category_selector :: {flag} :: task={args.task_id} project={project_slug}")
        print(f"  {result.detail}")
        for c in result.recommended_categories:
            tag = "[default]" if c.is_default else "[signal]"
            print(f"  ✓ {tag} {c.name} ({c.slug}) — {c.reason}")
        if result.rejected_categories:
            print("  Rejected:")
            # Distinct loop var (rejected_categories is list[dict], not the
            # CategoryDecision list above) — avoids a misleading type collision.
            for rc in result.rejected_categories[:5]:
                print(f"  ✗ {rc['name']} ({rc['slug']}) — {rc['reason']}")
            if len(result.rejected_categories) > 5:
                print(f"     ... and {len(result.rejected_categories) - 5} more")

    # Write a DISTINCT evidence artifact so the orchestrator can prove this stage
    # actually RAN. This stage mutates meta.json IN PLACE, so meta.json's mere
    # existence (it is created by meta-builder one stage earlier) is NOT proof
    # that category selection executed. The orchestrator's _stage_complete used
    # expected_outputs=["meta.json"] as the completion signal, so it concluded
    # the stage was already done and silently skipped it — reproducing the
    # "every article lands in the single default category (144)" bug on
    # 2026-06-03. The orchestrator's category-selector Stage now declares
    # evidence_artifact="category-selection-result.json", so it will only treat
    # the stage as complete once this file exists.
    try:
        ws_dir = PLUGIN_ROOT / "memory" / "workspace" / args.task_id
        if ws_dir.exists():
            evidence = result.to_dict()
            evidence["_generated_by"] = "category-selector"
            (ws_dir / "category-selection-result.json").write_text(
                json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # never let evidence-write failure mask a successful selection
        print(f"category_selector :: WARN could not write evidence artifact: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
