"""
scripts/_core/batch_queue.py — Batch /article queue manager.

The user gives a list of keywords (+ optional per-row format/voice/etc.).
This script:
  1. Creates a batch_id + workspace/batches/{batch_id}/index.json
  2. Validates each entry (project exists, keyword non-empty, format known)
  3. Pre-flight: estimate total cost via cost_estimator
  4. Persists queue state for resume

Actual pipeline driving is done by the batch-article SKILL.md (Claude iterates
through pending entries, invoking L1 seo-blog SKILL for each).

This script handles:
  - enqueue: create batch from keyword list
  - status: show batch progress
  - next: find next pending entry (returns task_id + brief)
  - mark: update entry status (running / completed / failed)
  - resume: list pending entries for a batch
  - estimate: pre-flight cost across whole batch

Input formats:
  Text:    one keyword per line (extra fields after comma)
  CSV:     keyword,format,voice,word_count
  JSON:    [{"keyword":...,"format":...},...]

CLI:
    python -m scripts._core.batch_queue enqueue --project X --file kw.txt
    python -m scripts._core.batch_queue status --batch-id B
    python -m scripts._core.batch_queue next --batch-id B
    python -m scripts._core.batch_queue mark --batch-id B --task-id T --status completed
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

from scripts._core import cost_estimator, cost_ledger
from scripts._core.file_bus import PLUGIN_ROOT


EntryStatus = Literal["pending", "running", "completed", "failed", "skipped"]

_FORMAT_ENUM_SCHEMA = PLUGIN_ROOT / "schemas" / "angle.schema.json"

# Fallback only — used if the schema is unreadable. NEVER edit this by hand to add a
# format; the authoritative list is angle.schema.json :: properties.format_id.enum.
_FORMAT_FALLBACK = {
    "listicle", "how-to-guide", "pillar-page", "comparison",
    "case-study", "definition", "news-analysis", "product-review",
    "shortlist-validation", "faq-knowledge",
}


def _load_valid_formats() -> set[str]:
    """Single source of truth = angle.schema.json's format_id enum (25 formats).

    v3.41.4 root cure: this set used to be a hand-maintained 10-item literal that had
    drifted a generation behind schemas/ and templates/ (26 template files). A CSV row
    naming a real-but-unlisted format (`buyers-guide`, `encyclopedic`, `roundup`, ...)
    silently fell back to `listicle`, so the whole article was planned and written in
    the wrong format with no error anywhere — a Rule-6/Rule-12 class silent no-op.
    """
    try:
        schema = json.loads(_FORMAT_ENUM_SCHEMA.read_text(encoding="utf-8"))
        enum = schema["properties"]["format_id"]["enum"]
        if isinstance(enum, list) and enum:
            return {str(f) for f in enum}
    except (OSError, ValueError, KeyError, TypeError) as exc:  # pragma: no cover
        print(
            f"[batch_queue] WARNING: could not read format enum from "
            f"{_FORMAT_ENUM_SCHEMA} ({exc}); falling back to the built-in list.",
            file=sys.stderr,
        )
    return set(_FORMAT_FALLBACK)


VALID_FORMATS = _load_valid_formats()


@dataclass
class BatchEntry:
    task_id: str
    keyword: str
    format: str = "listicle"
    voice: str = "professional"
    purpose: str = "general"
    word_count: int = 0           # 0 = use format default
    status: EntryStatus = "pending"
    workspace_path: str = ""
    published_url: str = ""
    error: str = ""
    estimated_cost_usd: str = "0.00"
    actual_cost_usd: str = "0.00"
    started_at: str = ""
    completed_at: str = ""
    notes: str = ""


@dataclass
class Batch:
    batch_id: str
    project_slug: str
    created_at: str
    entries: list[BatchEntry] = field(default_factory=list)
    total_estimated_cost_usd: str = "0.00"
    total_actual_cost_usd: str = "0.00"
    daily_cost_cap_usd: str = "50.00"   # safety
    parallelism: int = 1                # sequential by default
    notes: str = ""


def _generate_batch_id() -> str:
    return f"batch-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"


def _generate_task_id(seq: int) -> str:
    # MUST match schemas/state.schema.json :: task_id pattern ^[a-z0-9_]{8,32}$
    # (assemble.py validates the full state against it). The pre-v3.41.0 hyphenated
    # form `art-...-001-ab` passed the runner's lenient writes, then hard-failed the
    # 2026-07-17 project-lima batch AT ASSEMBLY — every batch workspace needed a manual
    # copytree + in-place id rewrite. Underscores only; 27 chars, inside the 32 cap.
    return f"art_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{seq:03d}_{secrets.token_hex(2)}"


def _default_daily_cap() -> str:
    """Daily cap from ~/.xuanran-seo/config.yaml (cost_limits), not a hardcode.

    The old literal "50.00" ignored the operator's configured limit (100): a day
    already past $50 stalled every new batch on a phantom cap.
    """
    cap = cost_ledger._load_limits().get("daily_total_usd", Decimal("50"))
    return str(cap.quantize(Decimal("0.01")))


def _batch_dir(batch_id: str) -> Path:
    return PLUGIN_ROOT / "workspace" / "batches" / batch_id


def _load_batch(batch_id: str) -> Batch:
    index = _batch_dir(batch_id) / "index.json"
    if not index.exists():
        raise FileNotFoundError(f"Batch {batch_id} not found at {index}")
    data = json.loads(index.read_text(encoding="utf-8"))
    entries = [BatchEntry(**e) for e in data.get("entries", [])]
    return Batch(
        batch_id=data["batch_id"],
        project_slug=data["project_slug"],
        created_at=data["created_at"],
        entries=entries,
        total_estimated_cost_usd=data.get("total_estimated_cost_usd", "0.00"),
        total_actual_cost_usd=data.get("total_actual_cost_usd", "0.00"),
        daily_cost_cap_usd=data.get("daily_cost_cap_usd") or _default_daily_cap(),
        parallelism=data.get("parallelism", 1),
        notes=data.get("notes", ""),
    )


def _save_batch(batch: Batch) -> Path:
    bdir = _batch_dir(batch.batch_id)
    bdir.mkdir(parents=True, exist_ok=True)
    index = bdir / "index.json"
    payload = asdict(batch)
    index.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return index


def _parse_entries(file_path: Path) -> list[dict]:
    """Auto-detect format. Returns list of dicts with at minimum keyword."""
    text = file_path.read_text(encoding="utf-8-sig")  # handle BOM

    # Try JSON first
    text_stripped = text.strip()
    if text_stripped.startswith("["):
        try:
            return json.loads(text_stripped)
        except json.JSONDecodeError:
            pass

    # CSV (has header line with at least "keyword" column)
    first_line = text.splitlines()[0] if text else ""
    if "," in first_line and "keyword" in first_line.lower():
        import csv
        rows = list(csv.DictReader(text.splitlines()))
        return rows

    # Plain text: one keyword per line, optional comma-separated extras
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        d = {"keyword": parts[0]}
        if len(parts) > 1: d["format"] = parts[1]
        if len(parts) > 2: d["voice"] = parts[2]
        if len(parts) > 3:
            try:
                d["word_count"] = int(parts[3])
            except ValueError:
                pass
        entries.append(d)
    return entries


def enqueue(
    project_slug: str,
    *,
    file: Path | None = None,
    keywords: list[str] | None = None,
    default_format: str = "listicle",
    default_voice: str = "professional",
    parallelism: int = 1,
    notes: str = "",
) -> Batch:
    """Create a new batch from a file or inline keyword list."""
    if file:
        rows = _parse_entries(file)
    elif keywords:
        rows = [{"keyword": k} for k in keywords]
    else:
        raise ValueError("Provide --file or --keywords")

    if not rows:
        raise ValueError("No entries found")

    # Verify project exists
    if not (PLUGIN_ROOT / "projects" / project_slug).is_dir():
        raise ValueError(f"Project not found: {project_slug}")

    batch_id = _generate_batch_id()
    entries: list[BatchEntry] = []
    total_est = Decimal("0")

    for i, row in enumerate(rows, start=1):
        kw = (row.get("keyword") or "").strip()
        if not kw:
            continue
        fmt = row.get("format", default_format).strip() or default_format
        if fmt not in VALID_FORMATS:
            # Soft fallback rather than block — but NEVER silently (v3.41.4).
            print(
                f"[batch_queue] WARNING: row {i} requested unknown format "
                f"{fmt!r}; falling back to {default_format!r}. Valid: "
                f"{', '.join(sorted(VALID_FORMATS))}",
                file=sys.stderr,
            )
            fmt = default_format
        voice = row.get("voice", default_voice).strip() or default_voice
        purpose = row.get("purpose", "general").strip() or "general"
        try:
            wc = int(row.get("word_count", 0))
        except (ValueError, TypeError):
            wc = 0

        # Per-entry cost estimate
        try:
            br = cost_estimator.estimate_article(fmt=fmt, words=wc or None)
            est = br.total_usd
        except Exception:
            est = Decimal("2.50")

        entry = BatchEntry(
            task_id=_generate_task_id(i),
            keyword=kw,
            format=fmt,
            voice=voice,
            purpose=purpose,
            word_count=wc,
            estimated_cost_usd=str(est),
        )
        entries.append(entry)
        total_est += est

    batch = Batch(
        batch_id=batch_id,
        project_slug=project_slug,
        created_at=datetime.now(timezone.utc).isoformat(),
        entries=entries,
        total_estimated_cost_usd=str(total_est.quantize(Decimal("0.01"))),
        daily_cost_cap_usd=_default_daily_cap(),
        parallelism=parallelism,
        notes=notes,
    )
    _save_batch(batch)
    return batch


def status(batch_id: str) -> dict:
    """Return high-level status counts."""
    batch = _load_batch(batch_id)
    counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0, "skipped": 0}
    for e in batch.entries:
        counts[e.status] = counts.get(e.status, 0) + 1
    actual_cost = sum(
        (Decimal(e.actual_cost_usd) for e in batch.entries),
        Decimal("0"),
    )
    return {
        "batch_id": batch.batch_id,
        "project_slug": batch.project_slug,
        "total_entries": len(batch.entries),
        "counts": counts,
        "total_estimated_cost_usd": batch.total_estimated_cost_usd,
        "total_actual_cost_usd": str(actual_cost.quantize(Decimal("0.01"))),
        "created_at": batch.created_at,
    }


def next_pending(batch_id: str) -> BatchEntry | None:
    """Find next pending entry (FIFO)."""
    batch = _load_batch(batch_id)
    for e in batch.entries:
        if e.status == "pending":
            return e
    return None


def mark(
    batch_id: str, task_id: str, *,
    new_status: EntryStatus,
    workspace_path: str = "",
    published_url: str = "",
    error: str = "",
    actual_cost_usd: str = "",
) -> BatchEntry:
    """Update one entry's status."""
    batch = _load_batch(batch_id)
    now = datetime.now(timezone.utc).isoformat()
    for e in batch.entries:
        if e.task_id == task_id:
            e.status = new_status
            if workspace_path:
                e.workspace_path = workspace_path
            if published_url:
                e.published_url = published_url
            if error:
                e.error = error
            if actual_cost_usd:
                e.actual_cost_usd = actual_cost_usd
            if new_status == "running" and not e.started_at:
                e.started_at = now
            if new_status in ("completed", "failed", "skipped"):
                e.completed_at = now
            _save_batch(batch)
            return e
    raise ValueError(f"Task {task_id} not in batch {batch_id}")


def list_batches() -> list[dict]:
    """All batches across all projects."""
    batches_dir = PLUGIN_ROOT / "workspace" / "batches"
    if not batches_dir.is_dir():
        return []
    out = []
    for d in sorted(batches_dir.iterdir(), reverse=True):
        if not (d / "index.json").exists():
            continue
        try:
            out.append(status(d.name))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch /article queue manager")
    sub = ap.add_subparsers(dest="cmd", required=True)

    enq = sub.add_parser("enqueue")
    enq.add_argument("--project", required=True)
    enq.add_argument("--file", type=Path)
    enq.add_argument("--keywords", help="Comma-separated keywords")
    enq.add_argument("--format", default="listicle")
    enq.add_argument("--voice", default="professional")
    enq.add_argument("--parallelism", type=int, default=1)

    st = sub.add_parser("status")
    st.add_argument("--batch-id", required=True)

    nx = sub.add_parser("next")
    nx.add_argument("--batch-id", required=True)

    mk = sub.add_parser("mark")
    mk.add_argument("--batch-id", required=True)
    mk.add_argument("--task-id", required=True)
    mk.add_argument("--status", required=True,
                    choices=["pending", "running", "completed", "failed", "skipped"])
    mk.add_argument("--workspace-path", default="")
    mk.add_argument("--published-url", default="")
    mk.add_argument("--error", default="")
    mk.add_argument("--actual-cost-usd", default="")

    lst = sub.add_parser("list")

    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd == "enqueue":
        kws = [k.strip() for k in (args.keywords or "").split(",") if k.strip()] or None
        try:
            b = enqueue(args.project, file=args.file, keywords=kws,
                        default_format=args.format, default_voice=args.voice,
                        parallelism=args.parallelism)
        except (ValueError, FileNotFoundError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(asdict(b), indent=2, ensure_ascii=False))
        else:
            print(f"━━ Batch created ━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print(f"  Batch ID:        {b.batch_id}")
            print(f"  Project:         {b.project_slug}")
            print(f"  Entries:         {len(b.entries)}")
            print(f"  Est. total cost: ${b.total_estimated_cost_usd}")
            print(f"  Parallelism:     {b.parallelism}")
            print(f"  Index:           {_batch_dir(b.batch_id) / 'index.json'}")
            print()
            print("  First 5 entries:")
            for e in b.entries[:5]:
                print(f"    {e.task_id}  [{e.format:14s}]  ${e.estimated_cost_usd}  {e.keyword}")
            if len(b.entries) > 5:
                print(f"    ... and {len(b.entries)-5} more")
        return 0

    if args.cmd == "status":
        try:
            s = status(args.batch_id)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(s, indent=2, ensure_ascii=False))
        else:
            print(f"━━ Batch {s['batch_id']} ━━━━━━━━━━━━━━━━━━━━━")
            print(f"  Project:    {s['project_slug']}")
            print(f"  Entries:    {s['total_entries']}")
            for k, v in s['counts'].items():
                icon = {"completed": "✓", "running": "▸", "pending": "○",
                        "failed": "✗", "skipped": "·"}.get(k, " ")
                print(f"    {icon} {k:<10s} {v}")
            print(f"  Cost:       ${s['total_actual_cost_usd']} / ${s['total_estimated_cost_usd']} est")
        return 0

    if args.cmd == "next":
        try:
            e = next_pending(args.batch_id)
        except FileNotFoundError as err:
            print(f"Error: {err}", file=sys.stderr)
            return 1
        if e is None:
            print("(no pending entries)", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(asdict(e), indent=2, ensure_ascii=False))
        else:
            print(f"Next pending: {e.task_id}  [{e.format}]  '{e.keyword}'")
        return 0

    if args.cmd == "mark":
        try:
            e = mark(args.batch_id, args.task_id,
                     new_status=args.status,
                     workspace_path=args.workspace_path,
                     published_url=args.published_url,
                     error=args.error,
                     actual_cost_usd=args.actual_cost_usd)
        except (ValueError, FileNotFoundError) as err:
            print(f"Error: {err}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(asdict(e), indent=2, ensure_ascii=False))
        else:
            print(f"✓ {e.task_id} → {e.status}")
        return 0

    if args.cmd == "list":
        batches = list_batches()
        if args.json:
            print(json.dumps(batches, indent=2, ensure_ascii=False))
        else:
            print(f"Found {len(batches)} batch(es):")
            for b in batches:
                c = b["counts"]
                print(f"  {b['batch_id']}  {b['project_slug']:20s}  "
                      f"{c['completed']}/{b['total_entries']} done  "
                      f"${b['total_actual_cost_usd']} / ${b['total_estimated_cost_usd']}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
