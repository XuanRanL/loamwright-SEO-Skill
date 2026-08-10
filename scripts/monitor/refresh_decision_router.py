"""
scripts/monitor/refresh_decision_router.py — turn monitoring data into a prioritized,
signal-typed optimization plan that routes each opportunity to the MINIMAL sufficient
existing skill.

Why this exists (root cause)
----------------------------
The post-publish feedback loop was only described in prose (skills/phase-monitor/SKILL.md +
content-refresher) — there was NO dispatcher. Monitoring surfaced opportunities but a human had
to read the report and manually pick `/rewrite` (full) for everything. This module is the
missing decision layer: it reads first-party GSC data, DIAGNOSES each opportunity by signal type
(using 2026 SEO/GEO thresholds), and emits a prioritized plan naming the smallest sufficient
existing skill — so the same site never gets a full $0.45 rewrite when a $0.02 title fix is all
it needs, and a tag-page "content gap" gets a NEW article instead of a pointless refresh.

Design principles (from the architecture review):
  - REUSE existing skills, never duplicate them. This router only DIAGNOSES + ROUTES.
  - Match scope to the smallest sufficient skill (the rewrite SKILL already codifies this).
  - DRAFT-FIRST / human-in-the-loop: this writes a PLAN, it never mutates or republishes a live
    post. Executing each action stays a separate, gated step (the existing skills, draft-first).

Signals & actions (grounded in 2026 research — see the spec):
  CONTENT_GAP   tag/category archive ranks for a query (no dedicated article) -> CREATE article
  PAGE2_DEPTH   real article pos 11-20, high impressions, ~0 clicks          -> rewrite (depth)
  LOW_CTR       real article top-10 but CTR < ~half the position benchmark    -> meta-builder
  DEEP_WEAK     real article pos > 20, high impressions                       -> rewrite (full)
  NOT_IN_AI     query triggers AI Overview/Mode, our domain not cited         -> ai-overview-recovery
  CANNIBALIZE   2+ of our pages rank for the same query                       -> consolidate (audit)

Output: projects/{slug}/audits/refresh-plan.json (+ human report). Skill-level logic, project-level
output.

    python -m scripts.monitor.refresh_decision_router --site project-charlie --json
    python -m scripts.monitor.refresh_decision_router --all --no-ai
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts.audit import gsc_fetch

# 2026 organic CTR-by-position benchmark (First Page Sage, averaged; standard SERP).
# A top-10 page clicking far below this is an "under-clicking" (title/meta) problem, not content.
_CTR_BENCHMARK: dict[int, float] = {
    1: 39.8, 2: 18.7, 3: 10.2, 4: 7.2, 5: 5.1, 6: 4.4, 7: 3.0, 8: 2.1, 9: 1.9, 10: 1.6,
}
_CTR_UNDERPERFORM_RATIO = 0.5     # flag LOW_CTR when actual < expected * this
_DEFAULT_MIN_IMPRESSIONS = 30     # ignore long-tail noise below this over the window
_PAGE2_LOW, _PAGE2_HIGH = 10.0, 20.5   # "striking distance" — biggest lift per effort

# Action routing: signal -> (skill, mode, scope, weight). weight ranks priority vs impressions.
_ROUTES: dict[str, dict[str, Any]] = {
    "CONTENT_GAP": {"action": "create_article", "skill": "seo-blog (/article)", "mode": "new",
                    "scope": "create", "weight": 0.9,
                    "note": "demand validated by archive ranking; check cannibalization first"},
    "PAGE2_DEPTH": {"action": "optimize", "skill": "rewrite", "mode": "full",
                    "scope": "depth/information-gain", "weight": 1.0,
                    "note": "closest to page 1 — add depth + internal links + intent match"},
    "LOW_CTR": {"action": "optimize", "skill": "meta-builder", "mode": "title+meta",
                "scope": "surgical", "weight": 0.85,
                "note": "ranks top-10 but under-clicked — rewrite title/meta only (needs live-post wrapper)"},
    "DEEP_WEAK": {"action": "optimize", "skill": "rewrite", "mode": "full",
                  "scope": "comprehensive", "weight": 0.45,
                  "note": "ranks beyond page 2 — needs substantial work"},
    "NOT_IN_AI": {"action": "optimize", "skill": "ai-overview-recovery", "mode": "geo",
                  "scope": "GEO restructure", "weight": 0.7,
                  "note": "answer-first 40-60w + quotable 120-180w passages + stats + schema"},
    "CANNIBALIZE": {"action": "consolidate", "skill": "rewrite (audit) + manual 301", "mode": "merge",
                    "scope": "structural", "weight": 0.6,
                    "note": "same intent -> merge into stronger URL; different angle -> differentiate"},
}


@dataclass
class Action:
    signal: str
    target_url: str           # the page to fix, or "(new article)" for content gaps
    driving_query: str
    impressions: int
    clicks: int
    position: float
    recommended_skill: str
    mode: str
    scope: str
    rationale: str
    priority: float = 0.0


@dataclass
class SitePlan:
    site: str
    days: int
    generated_for_impressions_min: int
    action_count: int = 0
    actions: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str | None = None


# ── AIO-loss confirmation guard (v3.35, 2026-07-04) ─────────────────────────
# Ahrefs 2025 ("AI Overviews Change Every 2 Days"): consecutive AIO renders of
# the same query share only ~54.5% of cited URLs — ~45% of citations churn per
# re-run. A single uncited probe is therefore NOISE, not a loss. The router now
# requires the domain to be uncited in TWO consecutive probes at least
# _AIO_CONFIRM_HOURS apart before emitting NOT_IN_AI (and burning an
# ai-overview-recovery run on churn).
_AIO_CONFIRM_HOURS = 48
_AIO_OBS_KEEP = 6  # observations retained per query


def _aio_obs_path(slug: str) -> Path:
    return Path(f"projects/{slug}/audits/aio-observations.json")


def _confirm_aio_loss(slug: str, query: str, uncited_now: bool,
                      obs_path: Path | None = None) -> tuple[bool, str]:
    """Record this probe observation and return (confirmed, reason).

    Confirmed only when the MOST RECENT prior observation was also uncited and
    is >= _AIO_CONFIRM_HOURS old (a cited probe in between resets the clock —
    an unstable citation is churn, not a loss)."""
    from datetime import datetime, timezone

    path = obs_path or _aio_obs_path(slug)
    obs: dict[str, list[dict[str, Any]]] = {}
    if path.exists():
        try:
            obs = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            obs = {}
    history = obs.get(query, [])
    now = datetime.now(timezone.utc)

    confirmed = False
    reason = ""
    if uncited_now:
        if history:
            last = history[-1]
            try:
                last_at = datetime.fromisoformat(str(last.get("at")))
                age_h = (now - last_at).total_seconds() / 3600
            except (TypeError, ValueError):
                age_h = 0.0
            if last.get("uncited") and age_h >= _AIO_CONFIRM_HOURS:
                confirmed = True
                reason = (f"uncited in 2 consecutive probes {age_h:.0f}h apart "
                          f"(>= {_AIO_CONFIRM_HOURS}h) — stable loss, not churn")
            elif last.get("uncited"):
                reason = (f"uncited again but only {age_h:.0f}h since the prior probe "
                          f"(< {_AIO_CONFIRM_HOURS}h) — re-probe later to confirm")
            else:
                reason = ("first uncited probe after a cited one — AIO citations churn "
                          "~45% per render (Ahrefs 2025); needs a 2nd uncited probe "
                          f">= {_AIO_CONFIRM_HOURS}h later")
        else:
            reason = ("first observation recorded; needs a 2nd uncited probe "
                      f">= {_AIO_CONFIRM_HOURS}h later before NOT_IN_AI fires")

    history.append({"at": now.isoformat(), "uncited": uncited_now})
    obs[query] = history[-_AIO_OBS_KEEP:]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obs, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # observation persistence must never break plan generation
    return confirmed, reason


def _base_url(url: str) -> str:
    """Strip the #anchor fragment. GSC reports table-of-contents anchors (/post/#section) as
    separate 'pages'; collapsing them keeps one article = one opportunity (no double-count)."""
    return url.split("#", 1)[0]


def _page_kind(url: str) -> str:
    p = urlparse(url).path.lower()
    if "/tag/" in p:
        return "tag"
    if "/category/" in p or "/product-category/" in p:
        return "category"
    if p in ("", "/"):
        return "home"
    return "article"


def _expected_ctr(position: float) -> float:
    return _CTR_BENCHMARK.get(int(round(position)), 1.0)


def _classify(query: str, url: str, impr: int, clicks: int, pos: float) -> str | None:
    """Return the signal for one (query, page) row, or None if healthy / not actionable."""
    kind = _page_kind(url)
    if kind in ("tag", "category"):
        return "CONTENT_GAP"          # an archive shouldn't be the asset ranking a real query
    if kind == "home":
        return None
    if pos <= 10:
        actual_ctr = (clicks / impr * 100.0) if impr else 0.0
        if actual_ctr < _expected_ctr(pos) * _CTR_UNDERPERFORM_RATIO:
            return "LOW_CTR"
        return None                   # ranking + clicking acceptably -> leave it
    if _PAGE2_LOW < pos <= _PAGE2_HIGH:
        return "PAGE2_DEPTH"
    return "DEEP_WEAK"


def diagnose_site(slug: str, *, days: int = 28, min_impressions: int = _DEFAULT_MIN_IMPRESSIONS,
                  include_ai: bool = True) -> SitePlan:
    """Read GSC query+page data for a project and produce a prioritized optimization plan."""
    plan = SitePlan(site=slug, days=days, generated_for_impressions_min=min_impressions)
    try:
        bc = json.loads(Path(f"projects/{slug}/business-context.json").read_text(encoding="utf-8"))
        gsc_property = (bc.get("analytics") or {}).get("gsc_property")
        domain = urlparse(bc.get("site_url", "")).netloc.lower().lstrip("www.")
        if not gsc_property:
            plan.error = "no analytics.gsc_property in business-context"
            return plan
    except Exception as e:
        plan.error = f"business-context: {e}"
        return plan

    try:
        g = gsc_fetch.fetch(gsc_property, days=days, dimensions=["query", "page"], row_limit=5000)
    except Exception as e:
        plan.error = f"GSC fetch: {e}"
        return plan
    # Collapse anchor fragments to the base URL and AGGREGATE, so one article is one opportunity
    # (impression-weighted position), then apply the impressions threshold to the aggregated total.
    agg: dict[tuple[str, str], list[float]] = {}
    for row in g.get("rows", []):
        q = row["keys"][0]
        page = _base_url(row["keys"][1])
        impr, clk, pos = row.get("impressions", 0), row.get("clicks", 0), row.get("position", 0.0)
        rec = agg.setdefault((q, page), [0.0, 0.0, 0.0])
        rec[0] += impr
        rec[1] += clk
        rec[2] += pos * impr
    # apply the impressions threshold to the aggregated total; build a typed map + cannibalization set
    totals: dict[tuple[str, str], tuple[int, int, float]] = {}
    by_query: dict[str, set[str]] = {}
    for (q_, page_), (im, ck, wp) in agg.items():
        if im < min_impressions:
            continue
        totals[(q_, page_)] = (int(im), int(ck), (wp / im) if im else 0.0)
        by_query.setdefault(q_, set()).add(page_)
    cannibal_queries = {q for q, pages in by_query.items() if len(pages) >= 2}

    actions: list[Action] = []
    for (q, page), (impr, clicks, pos) in totals.items():
        signal = "CANNIBALIZE" if q in cannibal_queries and _page_kind(page) == "article" else _classify(q, page, impr, clicks, pos)
        if not signal:
            continue
        route = _ROUTES[signal]
        target = "(new article)" if signal == "CONTENT_GAP" else page
        actions.append(Action(
            signal=signal, target_url=target, driving_query=q,
            impressions=impr, clicks=clicks, position=round(pos, 1),
            recommended_skill=route["skill"], mode=route["mode"], scope=route["scope"],
            rationale=route["note"],
            priority=round(impr * float(route["weight"]), 1),
        ))

    # AI-citation signal: for the single highest-impression actionable query, is our domain cited?
    # v3.35: churn-guarded — a single uncited probe records an observation; NOT_IN_AI
    # fires only on 2 consecutive uncited probes >= 48h apart (Ahrefs: ~45% of AIO
    # citations swap per render, so one snapshot is noise).
    if include_ai and actions:
        try:
            from scripts.fetch import serpapi_query
            top = max(actions, key=lambda a: a.impressions)
            aio = serpapi_query.ai_overview(top.driving_query, params={"gl": "us", "hl": "en"}, use_cache=True)
            block = aio.get("ai_overview") if isinstance(aio.get("ai_overview"), dict) else {}
            refs = block.get("references", []) if isinstance(block, dict) else []
            if refs:
                uncited_now = not any(domain in (ref.get("link") or "") for ref in refs)
                confirmed, confirm_reason = _confirm_aio_loss(slug, top.driving_query, uncited_now)
                if uncited_now and confirmed:
                    route = _ROUTES["NOT_IN_AI"]
                    actions.append(Action(
                        signal="NOT_IN_AI", target_url=top.target_url, driving_query=top.driving_query,
                        impressions=top.impressions, clicks=top.clicks, position=top.position,
                        recommended_skill=route["skill"], mode=route["mode"], scope=route["scope"],
                        rationale=(f"AI Overview cites {len(refs)} sources for this query, none ours; "
                                   f"{confirm_reason}; " + route["note"]),
                        priority=round(top.impressions * float(route["weight"]), 1),
                    ))
                elif uncited_now:
                    plan.notes.append(
                        f"AIO uncited for {top.driving_query!r} but NOT yet confirmed: {confirm_reason}")
        except Exception:
            pass

    # de-dupe: keep the single highest-priority action per target page
    best: dict[str, Action] = {}
    for a in actions:
        key = f"{a.target_url}|{a.driving_query if a.signal == 'CONTENT_GAP' else ''}"
        if key not in best or a.priority > best[key].priority:
            best[key] = a
    ranked = sorted(best.values(), key=lambda a: a.priority, reverse=True)
    plan.actions = [asdict(a) for a in ranked]
    plan.action_count = len(ranked)

    # persist (project-level output)
    out = Path(f"projects/{slug}/audits/refresh-plan.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(plan), indent=2, ensure_ascii=False), encoding="utf-8")
    return plan


def _print_human(plan: SitePlan) -> None:
    print(f"── refresh plan · {plan.site} · last {plan.days}d (min {plan.generated_for_impressions_min} impr) ──")
    if plan.error:
        print(f"  ERROR: {plan.error}")
        return
    if not plan.actions:
        print("  no actionable opportunities (everything healthy or below threshold)")
        return
    for a in plan.actions[:15]:
        tgt = a["target_url"].replace("https://", "").replace("http://", "")
        print(f"  [{a['signal']:12s}] P{a['priority']:>7.0f}  {a['recommended_skill']:24s}"
              f"  {a['driving_query'][:34]!r:36s} pos={a['position']} impr={a['impressions']} clk={a['clicks']}")
        print(f"      → {tgt[:70]}")
        print(f"        {a['rationale']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnose monitoring data into a prioritized optimization plan")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--site")
    grp.add_argument("--all", action="store_true")
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--min-impressions", type=int, default=_DEFAULT_MIN_IMPRESSIONS)
    ap.add_argument("--no-ai", action="store_true", help="skip the SerpApi AI-citation check (saves quota)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    slugs = ([os.path.basename(os.path.dirname(p)) for p in sorted(glob.glob("projects/*/business-context.json"))]
             if args.all else [args.site])
    plans = [diagnose_site(s, days=args.days, min_impressions=args.min_impressions,
                           include_ai=not args.no_ai) for s in slugs]

    if args.json:
        print(json.dumps([asdict(p) for p in plans] if args.all else asdict(plans[0]),
                         indent=2, ensure_ascii=False))
    else:
        for p in plans:
            _print_human(p)
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
