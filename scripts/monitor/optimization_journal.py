"""
scripts/monitor/optimization_journal.py — close the "did the optimization actually work?" loop.

Root cause this fixes: the pipeline makes optimizations (title/meta CTR fixes, citation swaps,
rewrites) but records NOTHING about what changed and never re-checks whether it worked. Every fix
is fire-and-forget, so ROI can't be proven and the system never learns which fixes help.

This adds the missing measurement loop:
  1. record_change(...) — log each optimization with its before/after AND a baseline snapshot of
     the page/query's GSC metrics AT THE TIME of the change.
  2. verify_due(...)    — once an entry is past its check window (default T+14, also T+30), re-pull
     GSC for that query/URL and compute the delta vs baseline → verdict improved / flat / worse.

So after we change 5 titles, two weeks later this tells us which actually lifted CTR — and that
signal can feed back into which title patterns to reuse.

Skill-level logic; the journal itself is per-project: projects/{slug}/audits/optimization-journal.jsonl

    python -m scripts.monitor.optimization_journal --record --site project-juliet --post-id 30236 \
        --url https://project-juliet.example.com/best-filament-for-a1-mini-guide/ --query "best filament for a1 mini" \
        --type title --before "OLD" --after "NEW"
    python -m scripts.monitor.optimization_journal --verify --site project-juliet --window 14 --json
    python -m scripts.monitor.optimization_journal --report --site project-juliet
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.audit import gsc_fetch

CTR_IMPROVE = 1.15      # current CTR must beat baseline by this to count as "improved"
CTR_WORSE = 0.85
POS_DELTA = 1.0         # position must move at least this many spots to count


def _journal_path(slug: str) -> Path:
    return Path(f"projects/{slug}/audits/optimization-journal.jsonl")


def _gsc_metrics(slug: str, query: str, url: str, *, days: int = 28) -> dict[str, float]:
    """Current GSC metrics for a (query, page) pair, anchor-fragments collapsed."""
    bc = json.loads(Path(f"projects/{slug}/business-context.json").read_text(encoding="utf-8"))
    prop = (bc.get("analytics") or {}).get("gsc_property", "")
    g = gsc_fetch.fetch(prop, days=days, dimensions=["query", "page"], row_limit=5000)
    base = url.split("#")[0].rstrip("/")
    im = ck = wp = 0.0
    for r in g.get("rows", []):
        if r["keys"][0] == query and r["keys"][1].split("#")[0].rstrip("/") == base:
            im += r["impressions"]
            ck += r["clicks"]
            wp += r["position"] * r["impressions"]
    return {"impressions": int(im), "clicks": int(ck),
            "ctr": round(ck / im, 4) if im else 0.0,
            "position": round(wp / im, 1) if im else 0.0}


def _verdict(baseline: dict[str, float], current: dict[str, float], change_type: str) -> str:
    """Pure verdict — did the change help? CTR-focused for title/meta/citation, rank-focused else."""
    cb, cc = baseline.get("ctr", 0.0), current.get("ctr", 0.0)
    pb, pc = baseline.get("position", 0.0), current.get("position", 0.0)
    clb, clc = baseline.get("clicks", 0.0), current.get("clicks", 0.0)
    if change_type in ("title", "meta", "title+meta", "citation"):
        if clb == 0 and clc > 0:
            return "improved"
        if cb > 0:
            if cc >= cb * CTR_IMPROVE:
                return "improved"
            if cc <= cb * CTR_WORSE:
                return "worse"
        elif clc > clb:
            return "improved"
        return "flat"
    if pb and pc:
        if pc <= pb - POS_DELTA:
            return "improved"
        if pc >= pb + POS_DELTA:
            return "worse"
    return "flat"


def record_change(slug: str, *, post_id: int, url: str, change_type: str, before: str, after: str,
                  driving_query: str, baseline: dict[str, float] | None = None,
                  applied_at: str | None = None) -> dict[str, Any]:
    """Append an optimization to the project journal, snapshotting baseline GSC metrics."""
    applied_at = applied_at or datetime.now(timezone.utc).isoformat()
    if baseline is None:
        try:
            baseline = _gsc_metrics(slug, driving_query, url)
        except Exception:
            baseline = {"impressions": 0, "clicks": 0, "ctr": 0.0, "position": 0.0}
    entry = {
        "id": hashlib.sha256(f"{url}|{change_type}|{applied_at}".encode()).hexdigest()[:16],
        "post_id": post_id, "url": url, "change_type": change_type,
        "driving_query": driving_query, "before": before, "after": after,
        "applied_at": applied_at, "baseline": baseline, "verifications": [],
    }
    p = _journal_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _load(slug: str) -> list[dict[str, Any]]:
    p = _journal_path(slug)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def verify_due(slug: str, *, window_days: int = 14, now: datetime | None = None) -> dict[str, Any]:
    """Re-check entries past the window that have no verification at that window yet."""
    now = now or datetime.now(timezone.utc)
    entries = _load(slug)
    results = []
    changed = False
    for e in entries:
        applied = datetime.fromisoformat(e["applied_at"])
        age = (now - applied).days
        already = any(v["window_days"] == window_days for v in e.get("verifications", []))
        if age < window_days or already:
            continue
        try:
            cur = _gsc_metrics(slug, e["driving_query"], e["url"])
        except Exception as ex:
            results.append({"id": e["id"], "url": e["url"], "error": str(ex)[:80]})
            continue
        verdict = _verdict(e["baseline"], cur, e["change_type"])
        v = {"window_days": window_days, "checked_at": now.isoformat(),
             **cur, "verdict": verdict,
             "ctr_delta": round(cur["ctr"] - e["baseline"].get("ctr", 0.0), 4),
             "position_delta": round(cur["position"] - e["baseline"].get("position", 0.0), 1)}
        e.setdefault("verifications", []).append(v)
        changed = True
        results.append({"id": e["id"], "url": e["url"], "change_type": e["change_type"],
                        "verdict": verdict, "baseline_ctr": e["baseline"].get("ctr"),
                        "current_ctr": cur["ctr"], "clicks": cur["clicks"]})
    if changed:
        p = _journal_path(slug)
        p.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n", encoding="utf-8")
    return {"site": slug, "window_days": window_days, "checked": len(results), "results": results}


def report(slug: str) -> dict[str, Any]:
    entries = _load(slug)
    verdicts: dict[str, int] = {}
    for e in entries:
        for v in e.get("verifications", []):
            verdicts[v["verdict"]] = verdicts.get(v["verdict"], 0) + 1
    pending = sum(1 for e in entries if not e.get("verifications"))
    return {"site": slug, "total_changes": len(entries), "pending_verification": pending,
            "verdicts": verdicts,
            "changes": [{"url": e["url"], "type": e["change_type"], "applied_at": e["applied_at"][:10],
                         "latest_verdict": (e["verifications"][-1]["verdict"] if e.get("verifications") else "pending")}
                        for e in entries]}


def main() -> int:
    ap = argparse.ArgumentParser(description="Optimization journal — record + verify SEO changes")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--record", action="store_true")
    g.add_argument("--verify", action="store_true")
    g.add_argument("--report", action="store_true")
    ap.add_argument("--site", required=True)
    ap.add_argument("--post-id", type=int, default=0)
    ap.add_argument("--url"); ap.add_argument("--query", default="")
    ap.add_argument("--type", default="title"); ap.add_argument("--before", default=""); ap.add_argument("--after", default="")
    ap.add_argument("--window", type=int, default=14)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.record:
        if not args.url:
            print("--url required for --record", file=sys.stderr); return 2
        e = record_change(args.site, post_id=args.post_id, url=args.url, change_type=args.type,
                          before=args.before, after=args.after, driving_query=args.query)
        print(json.dumps(e, ensure_ascii=False, indent=2) if args.json
              else f"✓ recorded {args.type} on {args.url} (baseline ctr={e['baseline']['ctr']} pos={e['baseline']['position']})")
        return 0
    out = verify_due(args.site, window_days=args.window) if args.verify else report(args.site)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif args.verify:
        print(f"verify {args.site} @T+{args.window}: checked {out['checked']}")
        for r in out["results"]:
            print(f"  [{r.get('verdict','ERR'):8s}] {r.get('url','')[:54]}  ctr {r.get('baseline_ctr')}→{r.get('current_ctr')} clicks={r.get('clicks')}")
    else:
        print(f"journal {args.site}: {out['total_changes']} changes · pending {out['pending_verification']} · verdicts {out['verdicts'] or '(none yet)'}")
        for c in out["changes"][:20]:
            print(f"  [{c['latest_verdict']:8s}] {c['applied_at']} {c['type']:8s} {c['url'][:52]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
