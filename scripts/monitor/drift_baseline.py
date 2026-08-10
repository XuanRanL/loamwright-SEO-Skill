"""scripts/monitor/drift_baseline.py — SQLite SHA-256 snapshot of published page.

After publish, capture a content snapshot for drift detection.
Per `subskills/monitor/drift-detector/SKILL.md` 17-rule diff pattern.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.fetch.fetch_page import fetch
from scripts.fetch.parse_html import parse


@dataclass
class Baseline:
    url: str
    snapshot_sha: str
    captured_at: float
    title: str
    description: str
    word_count: int
    h1_count: int
    h2_count: int
    h3_count: int
    schema_types: list[str]
    internal_link_count: int
    external_link_count: int
    image_count: int
    canonical: str
    robots_meta: str
    site_slug: str


def _db_path(plugin_root: Path, site_slug: str) -> Path:
    db = plugin_root / "projects" / site_slug / ".seo" / "baselines" / "drift.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    return db


def _ensure_db(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            snapshot_sha TEXT NOT NULL,
            captured_at REAL NOT NULL,
            title TEXT, description TEXT,
            word_count INTEGER, h1_count INTEGER, h2_count INTEGER, h3_count INTEGER,
            schema_types TEXT, internal_link_count INTEGER, external_link_count INTEGER,
            image_count INTEGER, canonical TEXT, robots_meta TEXT,
            raw_html_hash TEXT,
            UNIQUE(url, snapshot_sha)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_url ON snapshots(url)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_captured ON snapshots(captured_at)")


def capture(site_slug: str, url: str) -> Baseline:
    """Fetch the URL and store a baseline snapshot."""
    plugin = _plugin_root()
    db_file = _db_path(plugin, site_slug)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # Fetch page
    res = fetch(url)
    if res.status != 200:
        raise RuntimeError(f"Fetch failed for {url}: status {res.status}, error {res.error}")
    page = parse(res.body, base_url=url)

    # SHA of normalized content (strip whitespace runs)
    normalized = " ".join(page.body_text.split())
    sha = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    baseline = Baseline(
        url=res.url_final,
        snapshot_sha=sha,
        captured_at=time.time(),
        title=page.meta.title,
        description=page.meta.description,
        word_count=page.word_count,
        h1_count=len(page.h1),
        h2_count=len(page.h2),
        h3_count=len(page.h3),
        schema_types=page.schema_types,
        internal_link_count=sum(1 for l in page.links if not l.is_external),
        external_link_count=sum(1 for l in page.links if l.is_external),
        image_count=len(page.images),
        canonical=page.meta.canonical,
        robots_meta=page.meta.robots,
        site_slug=site_slug,
    )

    with sqlite3.connect(db_file) as db:
        _ensure_db(db)
        db.execute("""
            INSERT OR IGNORE INTO snapshots
            (url, snapshot_sha, captured_at, title, description,
             word_count, h1_count, h2_count, h3_count,
             schema_types, internal_link_count, external_link_count,
             image_count, canonical, robots_meta, raw_html_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            baseline.url, baseline.snapshot_sha, baseline.captured_at,
            baseline.title, baseline.description,
            baseline.word_count, baseline.h1_count, baseline.h2_count, baseline.h3_count,
            json.dumps(baseline.schema_types),
            baseline.internal_link_count, baseline.external_link_count,
            baseline.image_count, baseline.canonical, baseline.robots_meta,
            sha,
        ))
        db.commit()

    return baseline


def get_latest(site_slug: str, url: str) -> Baseline | None:
    """Retrieve most recent baseline for a URL."""
    plugin = _plugin_root()
    db_file = _db_path(plugin, site_slug)
    if not db_file.exists():
        return None
    with sqlite3.connect(db_file) as db:
        _ensure_db(db)
        row = db.execute(
            "SELECT url, snapshot_sha, captured_at, title, description, "
            "word_count, h1_count, h2_count, h3_count, schema_types, "
            "internal_link_count, external_link_count, image_count, canonical, robots_meta "
            "FROM snapshots WHERE url = ? ORDER BY captured_at DESC LIMIT 1",
            (url,),
        ).fetchone()
    if not row:
        return None
    return Baseline(
        url=row[0], snapshot_sha=row[1], captured_at=row[2],
        title=row[3], description=row[4], word_count=row[5],
        h1_count=row[6], h2_count=row[7], h3_count=row[8],
        schema_types=json.loads(row[9]),
        internal_link_count=row[10], external_link_count=row[11],
        image_count=row[12], canonical=row[13], robots_meta=row[14],
        site_slug=site_slug,
    )


def list_history(site_slug: str, url: str, *, limit: int = 20) -> list[dict]:
    plugin = _plugin_root()
    db_file = _db_path(plugin, site_slug)
    if not db_file.exists():
        return []
    with sqlite3.connect(db_file) as db:
        _ensure_db(db)
        rows = db.execute(
            "SELECT captured_at, snapshot_sha, word_count, h2_count "
            "FROM snapshots WHERE url = ? ORDER BY captured_at DESC LIMIT ?",
            (url, limit),
        ).fetchall()
    return [
        {"captured_at": r[0], "sha": r[1][:12], "word_count": r[2], "h2_count": r[3]}
        for r in rows
    ]


def _plugin_root() -> Path:
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "VERSION").exists() and (p / ".claude-plugin").is_dir():
            return p
        p = p.parent
    raise RuntimeError("Cannot find plugin root")


def main() -> int:
    ap = argparse.ArgumentParser(description="Drift baseline (SHA-256 snapshot)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    cap = sub.add_parser("capture")
    cap.add_argument("--site", required=True)
    cap.add_argument("--url", required=True)

    g = sub.add_parser("get", help="Get latest baseline")
    g.add_argument("--site", required=True)
    g.add_argument("--url", required=True)

    h = sub.add_parser("history")
    h.add_argument("--site", required=True)
    h.add_argument("--url", required=True)
    h.add_argument("--limit", type=int, default=20)

    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd == "capture":
        try:
            b = capture(args.site, args.url)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(asdict(b), indent=2, ensure_ascii=False))
        else:
            print(f"Captured baseline for {b.url}")
            print(f"  SHA: {b.snapshot_sha[:16]}")
            print(f"  Word count: {b.word_count}")
            print(f"  H2: {b.h2_count}  H3: {b.h3_count}")
            print(f"  Schema: {b.schema_types}")
        return 0

    if args.cmd == "get":
        b = get_latest(args.site, args.url)
        if not b:
            print(f"No baseline for {args.url}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(asdict(b), indent=2, ensure_ascii=False))
        else:
            print(f"Latest baseline for {b.url}:")
            print(f"  Captured: {time.strftime('%Y-%m-%d %H:%M', time.gmtime(b.captured_at))}")
            print(f"  SHA: {b.snapshot_sha[:16]}")
            print(f"  Words: {b.word_count}  H2: {b.h2_count}")
        return 0

    if args.cmd == "history":
        h = list_history(args.site, args.url, limit=args.limit)
        if args.json:
            print(json.dumps(h, indent=2))
        else:
            print(f"History for {args.url}:")
            for entry in h:
                ts = time.strftime("%Y-%m-%d %H:%M", time.gmtime(entry["captured_at"]))
                print(f"  {ts}  sha={entry['sha']}  words={entry['word_count']}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
