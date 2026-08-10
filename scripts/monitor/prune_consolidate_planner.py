"""
scripts/monitor/prune_consolidate_planner.py — the "act" half of content cleanup (plan only).

Root cause this fixes: content_audit + the refresh router DETECT cannibalization, thin, and stale
content, but nothing turns those findings into a CONSOLIDATION / PRUNING decision (which page wins,
what 301-redirects, what to noindex). This generates that plan — and ONLY a plan: consolidation and
pruning are destructive, so per the draft-first discipline (Rule 5a) this never executes anything;
a human signs off and the merge/redirect is applied separately.

Two outputs:
  - CONSOLIDATIONS — from GSC, find queries where 2+ of our pages compete; pick the winner (most
    clicks, then impressions); recommend merging the weaker page INTO it with a 301 redirect.
  - PRUNE CANDIDATES — pages content_audit flagged THIN/STALE that also have near-zero GSC traffic;
    surfaced for human review (noindex / 410). Conservative: never auto-lists a healthy/new page.

Skill-level logic; project-level plan: projects/{slug}/audits/prune-consolidate-plan.json

    python -m scripts.monitor.prune_consolidate_planner --site project-juliet --json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts.audit import gsc_fetch

MIN_IMPR = 30           # ignore long-tail noise
PRUNE_MAX_IMPR = 5      # "near-zero traffic" ceiling for prune review


@dataclass
class PrunePlan:
    site: str
    consolidations: list[dict[str, Any]] = field(default_factory=list)
    prune_candidates: list[dict[str, Any]] = field(default_factory=list)
    note: str = ("DRAFT — destructive. Consolidation/pruning is NEVER auto-executed; "
                 "a human reviews this plan and applies merges/301s/noindex separately (Rule 5a).")
    error: str | None = None


def _base(u: str) -> str:
    return u.split("#")[0].rstrip("/")


def _is_article(u: str) -> bool:
    p = urlparse(u).path.lower()
    return "/tag/" not in p and "/category/" not in p and p not in ("", "/")


def pick_winner(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Given (clicks, impressions) for two pages, return 0 if a wins else 1 (clicks, then impr)."""
    return 0 if (a[0], a[1]) >= (b[0], b[1]) else 1


def build_plan(slug: str, *, days: int = 90) -> PrunePlan:
    plan = PrunePlan(site=slug)
    try:
        bc = json.loads(Path(f"projects/{slug}/business-context.json").read_text(encoding="utf-8"))
        prop = (bc.get("analytics") or {}).get("gsc_property", "")
        if not prop:
            plan.error = "no analytics.gsc_property"
            return plan
    except Exception as e:
        plan.error = f"business-context: {e}"
        return plan

    try:
        g = gsc_fetch.fetch(prop, days=days, dimensions=["query", "page"], row_limit=5000)
    except Exception as e:
        plan.error = f"GSC: {e}"
        return plan

    # aggregate (query, base-page) metrics
    agg: dict[tuple[str, str], list[int]] = {}
    page_totals: dict[str, list[int]] = {}
    for r in g.get("rows", []):
        q, page = r["keys"][0], _base(r["keys"][1])
        if len(q) > 120:        # GSC occasionally returns brand/content blobs as "queries"; real ones are short
            continue
        if not _is_article(page):
            continue
        a = agg.setdefault((q, page), [0, 0])
        a[0] += r["clicks"]; a[1] += r["impressions"]
        t = page_totals.setdefault(page, [0, 0])
        t[0] += r["clicks"]; t[1] += r["impressions"]

    # cannibalization -> consolidation: same query on 2+ pages (each >= MIN_IMPR)
    by_query: dict[str, list[str]] = {}
    for (q, page), (ck, im) in agg.items():
        if im >= MIN_IMPR:
            by_query.setdefault(q, []).append(page)
    seen_pairs: set[tuple[str, str]] = set()
    for q, pages in by_query.items():
        if len(pages) < 2:
            continue
        pages = sorted(set(pages))
        for i in range(len(pages)):
            for j in range(i + 1, len(pages)):
                pa, pb = pages[i], pages[j]
                key = (pa, pb)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                ta, tb = tuple(page_totals[pa]), tuple(page_totals[pb])
                win = pa if pick_winner(ta, tb) == 0 else pb  # type: ignore[arg-type]
                lose = pb if win == pa else pa
                shared = [qq for qq, ps in by_query.items() if pa in ps and pb in ps]
                plan.consolidations.append({
                    "keep_url": win, "merge_url": lose,
                    "keep_metrics": {"clicks": page_totals[win][0], "impressions": page_totals[win][1]},
                    "merge_metrics": {"clicks": page_totals[lose][0], "impressions": page_totals[lose][1]},
                    "shared_queries": shared[:5],
                    "redirect": f"301: {lose} -> {win}",
                    "reason": "same-query competition (cannibalization); merge weaker into stronger + 301",
                })

    # prune candidates: content_audit THIN/STALE + near-zero GSC traffic
    ca_path = Path(f"projects/{slug}/audits/content-audit.json")
    if ca_path.exists():
        try:
            ca = json.loads(ca_path.read_text(encoding="utf-8"))
            for pf in ca.get("posts", []):
                flags = set(pf.get("flags", []))
                if not (flags & {"THIN", "STALE"}):
                    continue
                # find this post's GSC traffic by slug match
                slug_l = pf.get("slug", "")
                tot = next((t for p2, t in page_totals.items() if slug_l and slug_l in p2), [0, 0])
                if tot[1] <= PRUNE_MAX_IMPR:
                    plan.prune_candidates.append({
                        "slug": slug_l, "flags": sorted(flags),
                        "impressions": tot[1], "words": pf.get("words"),
                        "action": "review for noindex or 410",
                        "reason": "thin/stale AND near-zero traffic — low-value; human review",
                    })
        except Exception:
            pass

    out = Path(f"projects/{slug}/audits/prune-consolidate-plan.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(plan), indent=2, ensure_ascii=False), encoding="utf-8")
    return plan


def _print_human(plan: PrunePlan) -> None:
    print(f"── prune/consolidate plan · {plan.site} ──")
    if plan.error:
        print(f"  ERROR: {plan.error}")
        return
    print(f"  consolidations: {len(plan.consolidations)} · prune candidates: {len(plan.prune_candidates)}")
    for c in plan.consolidations[:12]:
        print(f"  MERGE  {c['merge_url'].split('/')[-1] or c['merge_url']}  (clk={c['merge_metrics']['clicks']}) "
              f"-> KEEP {c['keep_url'].split('/')[-1]} (clk={c['keep_metrics']['clicks']})  on {c['shared_queries'][:2]}")
    for p in plan.prune_candidates[:10]:
        print(f"  PRUNE? {p['slug']}  flags={p['flags']} impr={p['impressions']}")
    print(f"  NOTE: {plan.note}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Content consolidation / pruning PLANNER (never executes)")
    ap.add_argument("--site", required=True)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    plan = build_plan(args.site, days=args.days)
    if args.json:
        print(json.dumps(asdict(plan), indent=2, ensure_ascii=False))
    else:
        _print_human(plan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
