"""scripts/_core/local_intent_runner.py — Orchestration wrapper for local-intent detection.

PURPOSE
─────────
Single-command entry point that the seo-blog L1 orchestrator (or any wrapper)
invokes via Bash to:
  1. Read project's business-context.json :: location.local_seo_mode
  2. If != "off", run _detect_local_intent.py on the keyword
  3. Write the result into state.json :: brief.local_mode + brief.location_anchor
  4. Echo a summary JSON to stdout for Claude to parse

WHY THIS EXISTS (audit 2026-05-22 P1 — wiring gap)
──────────────────────────────────────────────────
v5.0 originally had detection logic in pseudo-code inside skills/seo-blog/SKILL.md.
Wiring audit found: pseudocode in markdown doesn't execute unless Claude reads
and follows it manually — easy to drift. This script gives a Python entry point
that ALWAYS executes and ALWAYS writes the state.json correctly. Same root cause
as v3.3.3 NameError class: "feature defined in markdown but no executor invokes it".

CLI
───
    python -m scripts._core.local_intent_runner \\
        --task-id TASK_ID \\
        --project-slug SLUG \\
        --keyword "1000W LED grow light Oklahoma" \\
        [--json]

The script ALWAYS exits 0 and writes the state.json (whether local_mode=true or
false). Failure to write state.json is an error (exit 1).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict


def _load_business_context(project_slug: str | None) -> dict:
    """Read projects/{slug}/business-context.json. Empty dict if absent."""
    if not project_slug:
        return {}
    try:
        from scripts._core.file_bus import PLUGIN_ROOT
    except Exception:
        # Fallback when file_bus's lazy import fails
        return {}
    bc_path = PLUGIN_ROOT / "projects" / project_slug / "business-context.json"
    if not bc_path.exists():
        return {}
    try:
        return json.loads(bc_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(
            f"⚠ local_intent_runner: failed to read business-context.json "
            f"for {project_slug!r}: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return {}


# target_markets tokens → ISO2 country codes (None = no bias contribution).
# "worldwide"/"eu" style tokens deliberately contribute nothing: detection is
# GLOBAL by default (v3.40.0); the bias only steers cross-country ambiguity.
_MARKET_TOKEN_MAP: dict[str, str | None] = {
    "us": "US", "usa": "US", "united states": "US",
    "uk": "GB", "gb": "GB", "united kingdom": "GB",
    "ca": "CA", "canada": "CA",
    "au": "AU", "australia": "AU",
    "eu": None, "europe": None, "worldwide": None, "global": None,
    "asia-export": None, "overseas-chinese-expat": None,
}


def derive_project_countries(bc: dict) -> list[str] | None:
    """ISO2 target-market countries from business-context :: location.

    Prefers location.target_markets; falls back to location.country (so a
    US-only project like project-charlie keeps its US bias). Returns None when the
    project is worldwide / has no usable signal — detection then runs unbiased.
    """
    loc = bc.get("location") or {}
    markets = [str(t).strip().lower() for t in (loc.get("target_markets") or [])]
    if any(t in ("worldwide", "global") for t in markets):
        # Declared-worldwide project: named markets are emphasis, not a fence —
        # never bias cross-country disambiguation for these.
        return None
    out: list[str] = []
    for t in markets:
        if t in _MARKET_TOKEN_MAP:
            iso = _MARKET_TOKEN_MAP[t]
            if iso and iso not in out:
                out.append(iso)
        elif len(t) == 2 and t.isalpha():
            iso = t.upper()
            if iso not in out:
                out.append(iso)
    if not out:
        country = str(loc.get("country") or "").strip().upper()
        if len(country) == 2 and country.isalpha():
            out.append(country)
    return out or None


def run(
    task_id: str,
    project_slug: str | None,
    keyword: str,
    *,
    allow_spacy: bool = False,
    countries_override: list[str] | None = None,
) -> dict:
    """Orchestrate detection + state.json write. Returns the result dict.

    Result shape:
        {
            "local_mode": bool,
            "location_anchor": dict | null,
            "tier_used": int | null,
            "skipped_reason": str | null,    # when local_seo_mode=off
            "ambiguous": bool,
            "disambiguation_options": list,
        }
    """
    bc = _load_business_context(project_slug)
    loc_mode = (bc.get("location") or {}).get("local_seo_mode", "off")

    out: dict = {
        "task_id": task_id,
        "project_slug": project_slug,
        "keyword": keyword,
        "local_mode": False,
        "location_anchor": None,
        "tier_used": None,
        "skipped_reason": None,
        "ambiguous": False,
        "disambiguation_options": [],
        "project_countries": None,
        "notes": [],
    }

    if loc_mode == "off":
        out["skipped_reason"] = "business-context.json :: location.local_seo_mode = 'off'"
    else:
        from scripts.research._detect_local_intent import detect_local_intent
        service_states = (
            (bc.get("location") or {}).get("service_areas", {}).get("primary_states") or None
        )
        project_countries = countries_override or derive_project_countries(bc)
        out["project_countries"] = project_countries
        det = detect_local_intent(
            keyword,
            project_service_area_states=service_states,
            project_countries=project_countries,
            allow_spacy=allow_spacy,
        )
        out["local_mode"] = det.local_mode
        out["tier_used"] = det.tier_used
        out["notes"] = det.notes
        if det.location_anchor:
            out["location_anchor"] = asdict(det.location_anchor)
            out["ambiguous"] = det.location_anchor.ambiguous
            out["disambiguation_options"] = det.location_anchor.disambiguation_options

    # Write to state.json brief.* fields
    try:
        from scripts._core import file_bus as fb
        state = fb.read_state(task_id)
        brief = state.get("brief", {})
        brief["local_mode"] = out["local_mode"]
        brief["location_anchor"] = out["location_anchor"]
        state["brief"] = brief
        fb.write_state(task_id, state)
        out["state_json_updated"] = True
    except Exception as e:
        out["state_json_updated"] = False
        out["state_json_error"] = f"{type(e).__name__}: {e}"
        print(
            f"⚠ local_intent_runner: state.json write failed for task {task_id!r}: "
            f"{type(e).__name__}: {e}",
            file=sys.stderr,
        )

    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Local-intent detection wrapper for seo-blog orchestrator")
    p.add_argument("--task-id", required=True)
    p.add_argument("--project-slug", default=None)
    p.add_argument("--keyword", required=True)
    p.add_argument("--allow-spacy", action="store_true")
    p.add_argument(
        "--countries",
        help="Comma-separated ISO2 codes overriding the project-derived "
             "target-market country bias (e.g. 'CA,GB')",
    )
    p.add_argument("--json", action="store_true", help="emit JSON to stdout (machine-readable)")
    args = p.parse_args()

    # Defense-in-depth: this is the one local-intent call site the LLM invokes
    # with `--project-slug {active_project_slug or ''}` (SKILL.md). If it arrives
    # empty, resolve env-first (XS_ACTIVE_PROJECT) rather than the shared file, so
    # a parallel session can't have its slug clobbered by another session.
    project_slug = args.project_slug
    if not (project_slug or "").strip():
        try:
            from scripts._core import active_project
            project_slug = active_project.get_active_project()
        except Exception:
            project_slug = None

    result = run(
        task_id=args.task_id,
        project_slug=project_slug,
        keyword=args.keyword,
        allow_spacy=args.allow_spacy,
        countries_override=(
            [c.strip().upper() for c in args.countries.split(",")]
            if args.countries else None
        ),
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"keyword:      {args.keyword!r}")
        print(f"local_mode:   {result['local_mode']}")
        if result["skipped_reason"]:
            print(f"  skipped: {result['skipped_reason']}")
        elif result["location_anchor"]:
            la = result["location_anchor"]
            print(f"  location:   {la.get('name_full', la.get('canonical'))} (type={la.get('type')}, tier={result['tier_used']})")
            if result["ambiguous"]:
                print(f"  AMBIGUOUS: {result['disambiguation_options'][:3]}")
        print(f"state.json updated: {result['state_json_updated']}")
    return 0 if result.get("state_json_updated") or args.task_id == "DRY_RUN" else 1


if __name__ == "__main__":
    sys.exit(main())
