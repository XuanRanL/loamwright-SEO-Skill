"""
scripts/monitor/gsc_csv_ingest.py — Ingest Google Search Console CSV export.

GSC exports are the simplest path for personal use — no OAuth dance, no API keys.
User flow:
  1. GSC → Performance → set date range → Export → CSV (UTF-8 BOM, often)
  2. drop CSV into projects/{slug}/metrics/raw/
  3. python -m scripts.monitor.gsc_csv_ingest --site my-site --csv path.csv

CSV columns expected (any order, GSC standard):
  Query, Page, Clicks, Impressions, CTR, Position
  OR Pages: Page, Clicks, Impressions, CTR, Position
  OR Queries: Query, Clicks, Impressions, CTR, Position

Output:
  projects/{slug}/metrics/gsc-{date_range}.json
  + memory/metrics-index.json (cross-project rollup)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from scripts._core.file_bus import PLUGIN_ROOT


@dataclass
class GscEntry:
    page: str = ""
    query: str = ""
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0


@dataclass
class IngestResult:
    site_slug: str
    csv_path: str
    rows_total: int
    rows_with_url: int
    rows_with_query: int
    unique_urls: int
    unique_queries: int
    date_range: str = ""
    by_url: dict[str, dict] = field(default_factory=dict)
    by_query: dict[str, dict] = field(default_factory=dict)
    output_path: str = ""


def _parse_pct(s: str) -> float:
    """Parse '12.34%' or '0.1234' or '12.34'."""
    if not s:
        return 0.0
    s = s.strip().replace(",", "")
    if s.endswith("%"):
        try:
            return float(s.rstrip("%")) / 100.0
        except ValueError:
            return 0.0
    try:
        v = float(s)
        return v / 100.0 if v > 1.0 else v
    except ValueError:
        return 0.0


def _parse_int(s: str) -> int:
    if not s:
        return 0
    try:
        return int(float(s.replace(",", "").strip()))
    except ValueError:
        return 0


def _parse_float(s: str) -> float:
    if not s:
        return 0.0
    try:
        return float(s.replace(",", "").strip())
    except ValueError:
        return 0.0


def _detect_dialect(content: str) -> str:
    """GSC CSVs sometimes use tabs. Detect."""
    first_line = content.splitlines()[0] if content else ""
    if "\t" in first_line and "," not in first_line:
        return "\t"
    return ","


def parse_gsc_csv(csv_path: Path) -> tuple[list[GscEntry], dict]:
    """Read GSC CSV, return (entries, metadata)."""
    raw = csv_path.read_bytes()
    # Strip BOM
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    text = raw.decode("utf-8", errors="replace")
    delim = _detect_dialect(text)

    reader = csv.DictReader(text.splitlines(), delimiter=delim)
    fields_lower = {f.lower(): f for f in (reader.fieldnames or [])}

    # Map possible column names
    col_query = fields_lower.get("query") or fields_lower.get("top queries")
    col_page = fields_lower.get("page") or fields_lower.get("top pages") or fields_lower.get("landing page")
    col_clicks = fields_lower.get("clicks")
    col_imp = fields_lower.get("impressions")
    col_ctr = fields_lower.get("ctr") or fields_lower.get("click-through rate")
    col_pos = fields_lower.get("position") or fields_lower.get("average position")

    entries: list[GscEntry] = []
    for row in reader:
        if not any(row.values()):
            continue
        entry = GscEntry(
            page=row.get(col_page, "") if col_page else "",
            query=row.get(col_query, "") if col_query else "",
            clicks=_parse_int(row.get(col_clicks, "0") if col_clicks else "0"),
            impressions=_parse_int(row.get(col_imp, "0") if col_imp else "0"),
            ctr=_parse_pct(row.get(col_ctr, "0") if col_ctr else "0"),
            position=_parse_float(row.get(col_pos, "0") if col_pos else "0"),
        )
        if entry.clicks == 0 and entry.impressions == 0:
            continue
        entries.append(entry)

    meta = {
        "columns_detected": list(fields_lower.values()),
        "delimiter": "tab" if delim == "\t" else "comma",
        "entry_count": len(entries),
    }
    return entries, meta


def aggregate(entries: list[GscEntry]) -> tuple[dict, dict]:
    """Roll up per-URL and per-query."""
    by_url: dict[str, dict] = {}
    by_query: dict[str, dict] = {}

    for e in entries:
        if e.page:
            if e.page not in by_url:
                by_url[e.page] = {
                    "page": e.page, "clicks": 0, "impressions": 0,
                    "position_sum": 0.0, "position_count": 0, "queries": [],
                }
            d = by_url[e.page]
            d["clicks"] += e.clicks
            d["impressions"] += e.impressions
            if e.position > 0:
                d["position_sum"] += e.position * max(e.impressions, 1)
                d["position_count"] += max(e.impressions, 1)
            if e.query and len(d["queries"]) < 20:
                d["queries"].append({"q": e.query, "clicks": e.clicks, "pos": e.position})

        if e.query:
            if e.query not in by_query:
                by_query[e.query] = {
                    "query": e.query, "clicks": 0, "impressions": 0,
                    "position_sum": 0.0, "position_count": 0, "pages": [],
                }
            d = by_query[e.query]
            d["clicks"] += e.clicks
            d["impressions"] += e.impressions
            if e.position > 0:
                d["position_sum"] += e.position * max(e.impressions, 1)
                d["position_count"] += max(e.impressions, 1)
            if e.page and len(d["pages"]) < 10:
                d["pages"].append({"page": e.page, "clicks": e.clicks, "pos": e.position})

    # Finalize position averages (impression-weighted)
    for d in by_url.values():
        d["avg_position"] = (
            round(d["position_sum"] / d["position_count"], 2)
            if d["position_count"] else 0.0
        )
        d["ctr"] = round(d["clicks"] / d["impressions"], 4) if d["impressions"] else 0.0
        del d["position_sum"], d["position_count"]
    for d in by_query.values():
        d["avg_position"] = (
            round(d["position_sum"] / d["position_count"], 2)
            if d["position_count"] else 0.0
        )
        d["ctr"] = round(d["clicks"] / d["impressions"], 4) if d["impressions"] else 0.0
        del d["position_sum"], d["position_count"]

    return by_url, by_query


def ingest(site_slug: str, csv_path: Path, date_range: str = "") -> IngestResult:
    """Main ingest. Writes to projects/{slug}/metrics/gsc-{date}.json."""
    entries, meta = parse_gsc_csv(csv_path)
    by_url, by_query = aggregate(entries)

    if not date_range:
        date_range = datetime.now().strftime("%Y%m%d")

    out_dir = PLUGIN_ROOT / "projects" / site_slug / "metrics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"gsc-{date_range}.json"

    result = IngestResult(
        site_slug=site_slug,
        csv_path=str(csv_path),
        rows_total=meta["entry_count"],
        rows_with_url=sum(1 for e in entries if e.page),
        rows_with_query=sum(1 for e in entries if e.query),
        unique_urls=len(by_url),
        unique_queries=len(by_query),
        date_range=date_range,
        by_url=by_url,
        by_query=by_query,
        output_path=str(out_path),
    )

    out_path.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False),
                        encoding="utf-8")

    # Update metrics index
    index_path = PLUGIN_ROOT / "memory" / "metrics-index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    idx: dict = {}
    if index_path.exists():
        try:
            idx = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            idx = {}
    sites = idx.setdefault("sites", {})
    site = sites.setdefault(site_slug, {"ingests": []})
    site["ingests"].append({
        "date_range": date_range, "path": str(out_path),
        "rows": meta["entry_count"], "unique_urls": len(by_url),
        "ingested_at": datetime.utcnow().isoformat() + "Z",
    })
    site["latest_ingest"] = date_range
    index_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest GSC CSV export")
    ap.add_argument("--site", required=True)
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--date-range", default="",
                    help="e.g. 2026-04-01_2026-04-30; default: today's date")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.csv.exists():
        print(f"CSV not found: {args.csv}", file=sys.stderr)
        return 1

    r = ingest(args.site, args.csv, args.date_range)

    if args.json:
        # Compact for JSON output — drop by_url/by_query detail
        summary = {
            "site_slug": r.site_slug,
            "rows_total": r.rows_total,
            "unique_urls": r.unique_urls,
            "unique_queries": r.unique_queries,
            "date_range": r.date_range,
            "output_path": r.output_path,
        }
        print(json.dumps(summary, indent=2))
    else:
        print(f"━━ GSC ingest complete ━━━━━━━━━━━━━━━━━━━━━")
        print(f"  Site:         {r.site_slug}")
        print(f"  CSV:          {r.csv_path}")
        print(f"  Rows:         {r.rows_total}")
        print(f"  Unique URLs:  {r.unique_urls}")
        print(f"  Unique queries: {r.unique_queries}")
        print(f"  Date range:   {r.date_range}")
        print(f"  Output:       {r.output_path}")
        # Top 5 winners
        winners = sorted(r.by_url.values(), key=lambda x: -x["clicks"])[:5]
        if winners:
            print()
            print("  Top 5 URLs by clicks:")
            for w in winners:
                print(f"    {w['clicks']:5d} clicks, pos {w['avg_position']:.1f}  {w['page'][:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
