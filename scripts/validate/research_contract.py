"""scripts/validate/research_contract.py — research.json contract checker + normalizer.

WHY THIS EXISTS (root cure, 2026-07-06, v3.36.0)
================================================
Researcher subagents consolidate research.json via scripts (Bash-side writes), which
BYPASSES the Write/Edit-hook jsonschema validation. The v3.35.3 canonical-shape floor
in orchestrator._artifact_valid correctly REJECTS a drifted file at the research stage
(observed live: task loamdmanearme0706 shipped `intent` as a dict, `competitor_content`
instead of `competitor_titles`, `keyword_expansion.from_paa` instead of `paa`, and raw
SerpApi feature keys `ads`/`related_questions`/`local_results` in serp_features) — but
until now the only cure was hand-surgery on the JSON. Same disease family as CLAUDE.md
Rules 3/6/9: a layer of indirection (the researcher's improvised shape) silently
mismatches the canonical contract, and nothing deterministic closed the gap.

This module is the ONE executor for that gap:
  --check : full jsonschema validation against schemas/research.schema.json, PLUS a
            canonical-vocabulary lint on serp_features (raw SerpApi keys are named
            with their exact canonical replacement).
  --fix   : deterministic, provenance-stamped normalization of the KNOWN variant
            families (no LLM judgment, no content invention):
              • serp_features raw SerpApi keys → canonical enum via SERPAPI_TO_CANONICAL
              • intent dict → intent enum string (extracted from the dict's text) with
                the original preserved under intent_detail
              • competitor_content.top_organic_snapshot[] → competitor_titles[]
              • keyword_expansion.from_paa[] → paa[]
              • keyword_expansion.from_related_searches[] → semantic_clusters[]
              • serp_ground_truth / competitor_analysis / key_themes (the 2026-07-06
                loamwpseo variant family) → canonical keys where unambiguous
            Every applied mapping is recorded in _normalizations[]; the file gains
            _normalized_by: "research_contract --fix".

Wiring:
  • run_pipeline.advance() self-heals ONCE with --fix when the research stage's
    output verification fails (the exact seam that previously returned a dead-end
    ERROR and forced manual surgery).
  • agents/researcher.md + the orchestrator research/serp-analysis dispatch prompts
    instruct the researcher to run `--fix --json` as the LAST consolidation step.

Exit codes: 0 = valid (or fixed to valid), 1 = invalid (unfixable parts remain),
            2 = bad arguments / file missing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent

# Raw SerpApi structured-response keys → canonical schema enum values.
# Single source of truth for the mapping (referenced by agents/researcher.md and the
# orchestrator dispatch prompts — Rule 11: if you change this dict, grep those layers).
SERPAPI_TO_CANONICAL: dict[str, str] = {
    "ads": "paid_ads",
    "paid_ads": "paid_ads",
    "related_questions": "paa_box",
    "people_also_ask": "paa_box",
    "paa": "paa_box",
    "local_results": "local_pack",
    "local_map": "local_pack",
    "local_pack": "local_pack",
    "inline_videos": "video_carousel",
    "video_carousel": "video_carousel",
    "answer_box": "featured_snippet",
    "featured_snippet": "featured_snippet",
    "sitelinks": "site_links",
    "site_links": "site_links",
    "inline_images": "inline_images",
    "image_pack": "image_pack",
    "shopping_results": "shopping_results",
    "shopping": "shopping",
    "knowledge_graph": "knowledge_graph",
    "knowledge_panel": "knowledge_panel",
    "top_stories": "top_stories",
    "news": "news",
    "related_searches": "related_searches",
    "discussions_and_forums": "discussions_and_forums",
    "directory_results": "directory_results",
    "reddit_top_results": "reddit_top_results",
    "ai_overview": "ai_overview",
    "video": "video",
}

_INTENT_ENUM = ("informational", "commercial", "transactional", "navigational")


def _load_schema() -> dict:
    p = PLUGIN_ROOT / "schemas" / "research.schema.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _canonical_enum() -> set[str]:
    schema = _load_schema()
    return set(schema["properties"]["serp_features"]["items"]["enum"])


def _validate(data: dict) -> list[str]:
    """Full jsonschema validation; returns human-readable error list (empty = valid)."""
    errors: list[str] = []
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - jsonschema is a hard dep of the plugin
        errors.append("jsonschema not importable — cannot validate")
        return errors
    schema = _load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(x) for x in err.path) or "(root)"
        errors.append(f"{path}: {err.message[:200]}")
    return errors


# ── deterministic fixers (each returns a note string when it changed something) ──

def _fix_serp_features(data: dict) -> str | None:
    feats = data.get("serp_features")
    if not isinstance(feats, list):
        return None
    canonical = _canonical_enum()
    out: list[str] = []
    changed = False
    dropped: list[str] = []
    for f in feats:
        if not isinstance(f, str):
            changed = True
            dropped.append(repr(f))
            continue
        mapped = SERPAPI_TO_CANONICAL.get(f.strip().lower())
        if mapped is None:
            if f in canonical:
                mapped = f
            else:
                changed = True
                dropped.append(f)
                continue
        if mapped != f:
            changed = True
        if mapped not in out:
            out.append(mapped)
    if len(out) != len(feats):
        changed = True
    if not changed:
        return None
    data["serp_features"] = out
    note = f"serp_features normalized to canonical vocabulary ({out})"
    if dropped:
        note += f"; dropped unmappable entries {dropped}"
    return note


def _pick_intent_from_text(text: str) -> str | None:
    """Choose the enum word that appears EARLIEST in the text (positional, not
    enum-order — a dict like {'primary': 'commercial ...', 'secondary':
    'informational ...'} must resolve to 'commercial')."""
    hits = [(text.find(e), e) for e in _INTENT_ENUM if e in text]
    return min(hits)[1] if hits else None


def _fix_intent(data: dict) -> str | None:
    intent = data.get("intent")
    if isinstance(intent, str) and intent in _INTENT_ENUM:
        return None
    picked: str | None = None
    # A 'primary' field is authoritative when present (the observed variant shape).
    if isinstance(intent, dict) and isinstance(intent.get("primary"), str):
        picked = _pick_intent_from_text(intent["primary"].lower())
    if picked is None:
        blob = json.dumps(intent, ensure_ascii=False).lower() if intent is not None else ""
        picked = _pick_intent_from_text(blob)
        if picked is None and any(w in blob for w in ("buy", "vendor", "hire")):
            picked = "commercial"  # 'hire-decision / vendor selection' phrasings
    if picked is None:
        return None  # unfixable — leave for --check to report
    if isinstance(intent, (dict, list)):
        data["intent_detail"] = intent
    data["intent"] = picked
    return f"intent coerced to enum string '{picked}' (original preserved in intent_detail)"


def _fix_competitor_titles(data: dict) -> str | None:
    ct = data.get("competitor_titles")
    if isinstance(ct, list) and ct:
        return None
    # Variant family A (2026-07-06 loamdmanearme): competitor_content.top_organic_snapshot
    # Variant family B (2026-07-06 loamwpseo): competitor_analysis[] with title/url
    candidates: list[dict] = []
    cc = data.get("competitor_content")
    if isinstance(cc, dict) and isinstance(cc.get("top_organic_snapshot"), list):
        candidates = [c for c in cc["top_organic_snapshot"] if isinstance(c, dict)]
    elif isinstance(data.get("competitor_analysis"), list):
        candidates = [c for c in data["competitor_analysis"] if isinstance(c, dict)]
    if not candidates:
        return None
    titles = []
    for c in candidates:
        title, url = c.get("title"), c.get("url")
        if not (title and url):
            continue
        entry: dict[str, Any] = {"title": title, "url": url}
        host = url.split("/")[2] if "://" in url else ""
        if host:
            entry["domain"] = host
        if c.get("is_competitor_do_not_cite"):
            entry["content_gap"] = (
                "competitor/do-not-cite domain (Rule 8) — analysis only, never a source"
            )
        titles.append(entry)
    if not titles:
        return None
    data["competitor_titles"] = titles
    return f"competitor_titles built from variant competitor keys ({len(titles)} entries)"


def _fix_paa_and_clusters(data: dict) -> str | None:
    ke = data.get("keyword_expansion")
    if not isinstance(ke, dict):
        return None
    notes = []
    if not data.get("paa") and isinstance(ke.get("from_paa"), list) and ke["from_paa"]:
        data["paa"] = [q for q in ke["from_paa"] if isinstance(q, str)]
        notes.append(f"paa built from keyword_expansion.from_paa ({len(data['paa'])})")
    if (not data.get("semantic_clusters")
            and isinstance(ke.get("from_related_searches"), list) and ke["from_related_searches"]):
        data["semantic_clusters"] = [q for q in ke["from_related_searches"] if isinstance(q, str)]
        notes.append("semantic_clusters built from keyword_expansion.from_related_searches")
    return "; ".join(notes) if notes else None


def fix_research(data: dict) -> tuple[dict, list[str]]:
    """Apply all deterministic normalizations in place; return (data, notes)."""
    notes: list[str] = []
    for fixer in (_fix_intent, _fix_competitor_titles, _fix_paa_and_clusters,
                  _fix_serp_features):
        note = fixer(data)
        if note:
            notes.append(note)
    if notes:
        data["_normalized_by"] = "research_contract --fix"
        data.setdefault("_normalizations", []).extend(notes)
    return data, notes


def run(path: Path, do_fix: bool) -> dict:
    if not path.exists():
        return {"passed": False, "error": f"not found: {path}", "exit": 2}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"passed": False, "error": f"unparseable JSON: {e}", "exit": 1}
    notes: list[str] = []
    if do_fix:
        data, notes = fix_research(data)
        if notes:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    errors = _validate(data)
    return {
        "passed": not errors,
        "file": str(path),
        "fixed": bool(notes),
        "normalizations": notes,
        "schema_errors": errors,
        "exit": 0 if not errors else 1,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="research.json contract checker/normalizer")
    ap.add_argument("--workspace", help="task id (resolves memory/workspace/{tid}/research.json)")
    ap.add_argument("--file", help="explicit path to a research.json")
    ap.add_argument("--fix", action="store_true", help="apply deterministic normalizations in place")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.file:
        path = Path(args.file)
    elif args.workspace:
        path = PLUGIN_ROOT / "memory" / "workspace" / args.workspace / "research.json"
    else:
        print("--workspace or --file required", file=sys.stderr)
        return 2

    result = run(path, do_fix=args.fix)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        status = "VALID" if result["passed"] else "INVALID"
        print(f"research_contract: {status} ({result.get('file')})")
        for n in result.get("normalizations", []):
            print(f"  fixed: {n}")
        for e in result.get("schema_errors", []):
            print(f"  error: {e}")
    return int(result.get("exit", 1))


if __name__ == "__main__":
    sys.exit(main())
