"""
scripts/_core/file_bus.py — File-system communication bus for skills/agents.

All inter-skill / inter-agent communication MUST go through files, not
shared context. This module provides typed read/write helpers with
automatic JSON Schema validation.

Workspace layout (memory/workspace/{task_id}/):
    state.json              ← task metadata (schemas/state.schema.json)
    research.json           ← research output
    angle.json
    outline.json
    sections/0.json, 1.json, ...
    citations.json
    meta.json
    draft.md                ← markdown with frontmatter (Stage: writer|humanizer|...)
    final.md
    quality.json
    review.json
    .history/{stage}.md     ← per-stage snapshots

Why files not shared context:
    - Resumable on crash (no in-memory state lost)
    - Audit trail (every artifact persistent)
    - Manual debug-by-edit-file
    - Parallel agents don't fight over context buffer
    - Bounded main-context (orchestrator only loads what it needs)

Usage:
    from scripts._core import file_bus as fb

    task_id = fb.new_task_id()
    fb.write_state(task_id, {
        "task_id": task_id,
        "brief": {...},
        "phase": "research",
        "current_stage": "keyword-research",
        ...
    })

    state = fb.read_state(task_id)
    fb.write_artifact(task_id, "research.json", research_dict, schema="research")
    research = fb.read_artifact(task_id, "research.json", schema="research")

    md, frontmatter = fb.read_markdown_with_frontmatter(task_id, "draft.md")
    fb.write_markdown_with_frontmatter(task_id, "draft.md", md, {"Stage": "writer"})
"""
from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final


# ─── Locate workspace ──────────────────────────────────────────────

def _plugin_root() -> Path:
    """Walk up from this file to plugin root (containing VERSION + .claude-plugin/)."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "VERSION").exists() and (p / ".claude-plugin").is_dir():
            return p
        p = p.parent
    raise RuntimeError(
        f"Cannot find plugin root from {__file__}. "
        f"Expected to find VERSION + .claude-plugin/ in some ancestor."
    )


PLUGIN_ROOT: Final[Path] = _plugin_root()
WORKSPACE_ROOT: Final[Path] = PLUGIN_ROOT / "memory" / "workspace"
SCHEMAS_DIR: Final[Path] = PLUGIN_ROOT / "schemas"


# ─── Task ID ──────────────────────────────────────────────────────

def new_task_id() -> str:
    """Generate a fresh task ID: YYYYMMDD-XXXXXXXX (8 random hex chars)."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = secrets.token_hex(4)
    return f"{ts}-{suffix}"


def get_workspace(task_id: str, *, create: bool = True) -> Path:
    """Return path to a task's workspace dir; optionally create it."""
    if not re.match(r"^[a-zA-Z0-9_-]{8,32}$", task_id):
        raise ValueError(f"Invalid task_id: {task_id!r}")
    ws = WORKSPACE_ROOT / task_id
    if create:
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "sections").mkdir(exist_ok=True)
        (ws / ".history").mkdir(exist_ok=True)
    return ws


# ─── State (special-cased) ────────────────────────────────────────

# Fields that must never silently vanish from state.json across a write. All 5 are
# either schema-required (task_id/brief/phase/current_stage/created_at) or are
# orchestrator-populated data an LLM agent has no way to reconstruct
# (project_constraints: wrapper_class/mandatory_sections/differentiation_note).
# See references/orchestration/stage-tracking.md for the 2026-07-05 incident this guards.
_STATE_PROTECTED_FIELDS: Final[tuple[str, ...]] = (
    "task_id", "brief", "phase", "current_stage", "created_at", "project_constraints",
)


def write_state(task_id: str, state: dict, *, allow_field_removal: bool = False) -> None:
    """Write state.json with auto-timestamp + schema validation.

    Defense-in-depth against the 2026-07-05 incident: a subagent called `Write` on
    state.json directly, constructing the dict from only the fields it knew about, and
    silently dropped `phase`/`current_stage`/`created_at`/`project_constraints` — the
    next deterministic stage then crashed on schema validation. If a previous
    state.json exists and already has one of `_STATE_PROTECTED_FIELDS` populated, this
    now refuses (raises ValueError) a write that would remove it, UNLESS the caller
    passes `allow_field_removal=True` (for the rare deliberate case, e.g. an explicit
    task reset). `update_state()` / `record_stage_start()` / `record_stage_complete()`
    all read-merge-write the full existing file first, so they never trip this guard —
    only a caller that reconstructs `state` from a partial view and calls `write_state`
    directly can hit it, which is exactly the bug class being guarded against.
    """
    if not allow_field_removal:
        existing_path = get_workspace(task_id, create=False) / "state.json"
        if existing_path.exists():
            try:
                existing = json.loads(existing_path.read_text(encoding="utf-8"))
            except Exception:
                existing = None
            if existing:
                dropped = [
                    f for f in _STATE_PROTECTED_FIELDS
                    if existing.get(f) not in (None, {}, [], "") and f not in state
                ]
                if dropped:
                    raise ValueError(
                        f"write_state({task_id!r}) would silently drop protected field(s) "
                        f"{dropped} present in the existing state.json. This is almost always a "
                        f"bug — a full-file overwrite built from a partial view of state.json "
                        f"(see references/orchestration/stage-tracking.md). Use update_state(), "
                        f"record_stage_start(), or record_stage_complete() instead — they "
                        f"read-merge-write automatically. Pass allow_field_removal=True only if "
                        f"this removal is truly intentional."
                    )
    state = {**state, "updated_at": datetime.now(timezone.utc).isoformat()}
    if "task_id" not in state:
        state["task_id"] = task_id
    write_artifact(task_id, "state.json", state, schema="state")


def read_state(task_id: str) -> dict:
    return read_artifact(task_id, "state.json", schema="state")


def update_state(task_id: str, **fields: Any) -> dict:
    """Read, merge fields, write back."""
    state = read_state(task_id)
    state.update(fields)
    write_state(task_id, state)
    return state


# ─── Stage history (audit 2026-05-22 — wire-up) ────────────────────
#
# state.json::stage_history is the only mechanism the orchestrator (or post-hoc
# debugger) has to answer "did stage X actually run?" Without it, silently
# skipped stages (image-curator / fact-check-and-citation / assembly) produce
# no observable trace and bugs like the 2026-05-22 image-placeholder drift go
# undiagnosed until a post-publish PATCH is required.
#
# Every phase-* skill and every major subskill is expected to call
# record_stage_start + record_stage_complete (or use the context-manager
# `stage_context()`) around its work. If a skill calls neither, this is a
# convention violation that should surface in audits.

def record_stage_start(
    task_id: str,
    stage: str,
    *,
    phase: str | None = None,
) -> None:
    """Append a stage entry to state.history with status='in_progress'.

    The entry is finalized later by record_stage_complete (or failure path).
    Also updates state.current_stage (and state.phase if provided).
    """
    now = datetime.now(timezone.utc).isoformat()
    state = read_state(task_id)
    history = state.get("stage_history") or []
    # Dedup: when this stage already has an open in_progress entry (e.g. the
    # orchestrator opened it via `--action next` before running this BASH stage,
    # and the script — like wp_publisher.py — then self-records the SAME stage),
    # reuse that entry instead of appending a second one. Without this, the stage
    # appears TWICE in stage_history (the 2026-06-04 double wordpress-publisher
    # audit-trail bug). Standalone runs (no pre-opened entry) still append normally.
    existing = next(
        (h for h in reversed(history)
         if h.get("stage") == stage and h.get("status") == "in_progress"),
        None,
    )
    if existing is None:
        history.append({
            "stage": stage,
            "started_at": now,
            "completed_at": now,  # placeholder; updated on completion
            "status": "in_progress",
        })
    state["stage_history"] = history
    state["current_stage"] = stage
    if phase is not None:
        state["phase"] = phase
    write_state(task_id, state)


def record_stage_complete(
    task_id: str,
    stage: str,
    *,
    status: str = "completed",
    cost_usd: float | None = None,
) -> None:
    """Finalize the most-recent in-progress entry for `stage`.

    status: "completed" | "failed" | "skipped"
    cost_usd: optional cost ledger value to record on the entry.
    """
    if status not in ("completed", "failed", "skipped"):
        raise ValueError(f"invalid stage status: {status!r}")
    now = datetime.now(timezone.utc).isoformat()
    state = read_state(task_id)
    history = state.get("stage_history") or []
    # Find the most recent in_progress entry for this stage
    for entry in reversed(history):
        if entry.get("stage") == stage and entry.get("status") == "in_progress":
            entry["completed_at"] = now
            entry["status"] = status
            if cost_usd is not None:
                entry["cost_usd"] = float(cost_usd)
            break
    else:
        # No matching in_progress entry — append a synthetic one (defensive:
        # caller didn't call record_stage_start first, but we still want a
        # record so the audit isn't blind)
        history.append({
            "stage": stage,
            "started_at": now,
            "completed_at": now,
            "status": status,
            **({"cost_usd": float(cost_usd)} if cost_usd is not None else {}),
        })
    state["stage_history"] = history
    write_state(task_id, state)


def has_stage_run(task_id: str, stage: str, *, status: str | None = "completed") -> bool:
    """Did the named stage complete (or any status) for this task?

    Used by post-hoc validators ("was image-curator actually invoked?") and by
    downstream stages that gate on a predecessor.
    """
    try:
        state = read_state(task_id)
    except FileNotFoundError:
        return False
    history = state.get("stage_history") or []
    if status is None:
        return any(e.get("stage") == stage for e in history)
    return any(e.get("stage") == stage and e.get("status") == status for e in history)


def list_stages_run(task_id: str) -> list[dict]:
    """Return the full stage_history list (or empty if none recorded)."""
    try:
        state = read_state(task_id)
    except FileNotFoundError:
        return []
    return state.get("stage_history") or []


class stage_context:
    """Context manager: record_stage_start on enter, record_stage_complete on exit.

    Usage:
        with stage_context(task_id, "image-curator", phase="publish") as ctx:
            ...
            ctx.cost_usd = 0.05  # optional

    On exception, records status="failed" and re-raises.
    """
    def __init__(self, task_id: str, stage: str, *, phase: str | None = None):
        self.task_id = task_id
        self.stage = stage
        self.phase = phase
        self.cost_usd: float | None = None

    def __enter__(self):
        record_stage_start(self.task_id, self.stage, phase=self.phase)
        return self

    def __exit__(self, exc_type, exc, tb):
        status = "failed" if exc is not None else "completed"
        record_stage_complete(
            self.task_id, self.stage, status=status, cost_usd=self.cost_usd
        )
        return False  # don't swallow exceptions


# ─── Generic JSON artifact ──────────────────────────────────────

def write_artifact(
    task_id: str,
    name: str,
    data: dict | list,
    *,
    schema: str | None = None,
) -> None:
    """Write a JSON artifact to workspace, optionally validating against a schema.

    Args:
        task_id: Workspace identifier.
        name: Relative filename, e.g. "research.json" or "sections/0.json"
        data: JSON-serializable value.
        schema: Schema basename (e.g. "research") to validate against.
            Validation file is schemas/{schema}.schema.json. If validation fails, raises.
    """
    ws = get_workspace(task_id)
    out = ws / name
    out.parent.mkdir(parents=True, exist_ok=True)

    if schema:
        _validate(data, schema)

    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def tolerant_json_load(path: Path, *, heal: bool = True) -> Any:
    """Parse a JSON file that may carry leading BOM or trailing junk, and self-heal.

    Root cause this defends against (2026-06-03 batch): subagents occasionally append
    their tool-call wrapper text (e.g. ``</content></invoke>``) AFTER the closing brace
    of a JSON artifact they Write directly. A strict ``json.loads`` then raises
    "Extra data", which silently fails the orchestrator's stage-verify and the
    pre-publish gate even though the JSON payload itself is perfectly valid.

    Strategy: strip a UTF-8 BOM, then use ``JSONDecoder().raw_decode`` to read the FIRST
    complete JSON value and ignore anything after it. When trailing junk was found and
    ``heal=True``, rewrite the file with the clean payload so every later (strict) reader
    sees valid JSON. This is the single chokepoint used by read_artifact, the orchestrator
    artifact validator, and the pre-publish gate, so one fix heals the whole pipeline.

    Raises json.JSONDecodeError if no valid JSON value can be decoded at all.
    """
    raw = path.read_text(encoding="utf-8")
    stripped = raw.lstrip("﻿")  # drop BOM if present
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        # Fall back: decode the leading value, discard trailing junk.
        obj, end = json.JSONDecoder().raw_decode(stripped.lstrip())
        if heal:
            try:
                path.write_text(
                    json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            except OSError:
                pass  # healing is best-effort; never let a write error mask the parse
        return obj


def read_artifact(
    task_id: str,
    name: str,
    *,
    schema: str | None = None,
) -> Any:
    """Read a JSON artifact, optionally validating. Tolerant of BOM / trailing junk."""
    ws = get_workspace(task_id, create=False)
    src = ws / name
    if not src.exists():
        raise FileNotFoundError(f"Artifact not found: {src}")
    data = tolerant_json_load(src)
    if schema:
        _validate(data, schema)
    return data


def artifact_exists(task_id: str, name: str) -> bool:
    ws = get_workspace(task_id, create=False)
    return (ws / name).exists()


def list_section_artifacts(task_id: str) -> list[Path]:
    """Return section files from workspace. Accepts NN.json, NN_slug.json, NN.md, NN_slug.md.

    Deduplicates by leading index: if both 3.json and 03_slug.md exist,
    prefer the .json (it has the richer envelope with section_index + markdown).
    """
    import re as _re
    ws = get_workspace(task_id, create=False)
    sections_dir = ws / "sections"
    if not sections_dir.exists():
        return []
    all_files = list(sections_dir.glob("*.json")) + list(sections_dir.glob("*.md"))
    seen_indices: dict[int, Path] = {}
    for f in all_files:
        m = _re.match(r"^(\d+)", f.stem)
        if not m:
            continue
        idx = int(m.group(1))
        if idx in seen_indices:
            if f.suffix == ".json":
                seen_indices[idx] = f
        else:
            seen_indices[idx] = f
    return [seen_indices[k] for k in sorted(seen_indices)]


# ─── Markdown with frontmatter ──────────────────────────────────

_FM_RE: Final[re.Pattern[str]] = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL
)


@dataclass
class MarkdownDoc:
    """A markdown document with optional YAML frontmatter."""
    body: str
    frontmatter: dict


def parse_frontmatter(text: str) -> MarkdownDoc:
    """Parse `---\\n yaml \\n---\\n body` style frontmatter."""
    if text.startswith('﻿'):
        text = text[1:]
    m = _FM_RE.match(text)
    if not m:
        return MarkdownDoc(body=text, frontmatter={})

    fm_text = m.group(1)
    body = m.group(2)

    # Parse YAML if available; else use simple key:value parser
    try:
        import yaml
        fm = yaml.safe_load(fm_text) or {}
    except ImportError:
        fm = _simple_yaml_parse(fm_text)

    if not isinstance(fm, dict):
        fm = {}
    return MarkdownDoc(body=body, frontmatter=fm)


def serialize_frontmatter(doc: MarkdownDoc) -> str:
    """Serialize back to `---\\n yaml \\n---\\n body` form."""
    if not doc.frontmatter:
        return doc.body
    try:
        import yaml
        fm_text = yaml.safe_dump(doc.frontmatter, sort_keys=False, allow_unicode=True).strip()
    except ImportError:
        fm_text = "\n".join(f"{k}: {v}" for k, v in doc.frontmatter.items())
    return f"---\n{fm_text}\n---\n{doc.body}"


def read_markdown_with_frontmatter(task_id: str, name: str) -> MarkdownDoc:
    ws = get_workspace(task_id, create=False)
    p = ws / name
    if not p.exists():
        raise FileNotFoundError(p)
    return parse_frontmatter(p.read_text(encoding="utf-8"))


def write_markdown_with_frontmatter(
    task_id: str, name: str, body: str, frontmatter: dict | None = None
) -> None:
    ws = get_workspace(task_id)
    p = ws / name
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = MarkdownDoc(body=body, frontmatter=frontmatter or {})
    p.write_text(serialize_frontmatter(doc), encoding="utf-8")


def update_stage(task_id: str, draft_name: str, new_stage: str) -> None:
    """Convenience: update the `Stage:` frontmatter field of a draft file."""
    doc = read_markdown_with_frontmatter(task_id, draft_name)
    doc.frontmatter["Stage"] = new_stage
    doc.frontmatter["StageUpdatedAt"] = datetime.now(timezone.utc).isoformat()
    write_markdown_with_frontmatter(task_id, draft_name, doc.body, doc.frontmatter)


def snapshot_history(task_id: str, source_name: str, stage_label: str) -> Path:
    """Copy a workspace file to .history/{stage}-{timestamp}.{ext}"""
    ws = get_workspace(task_id)
    src = ws / source_name
    if not src.exists():
        raise FileNotFoundError(src)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = src.suffix or ".bin"
    dst = ws / ".history" / f"{stage_label}-{ts}{suffix}"
    dst.write_bytes(src.read_bytes())
    return dst


# ─── Archival ──────────────────────────────────────────────────

def archive_task(task_id: str) -> Path:
    """Move workspace/{task_id} → workspace/.archived/{YYYY-MM}/{task_id}."""
    ws = get_workspace(task_id, create=False)
    if not ws.exists():
        raise FileNotFoundError(ws)
    archive_root = WORKSPACE_ROOT / ".archived" / datetime.now(timezone.utc).strftime("%Y-%m")
    archive_root.mkdir(parents=True, exist_ok=True)
    dst = archive_root / task_id
    if dst.exists():
        raise FileExistsError(f"Archive target already exists: {dst}")
    ws.rename(dst)
    return dst


# ─── Schema validation ─────────────────────────────────────────

def _validate(data: Any, schema_name: str) -> None:
    """Validate `data` against schemas/{schema_name}.schema.json. Raises on failure."""
    schema_file = SCHEMAS_DIR / f"{schema_name}.schema.json"
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema not found: {schema_file}")
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import ValidationError
    except ImportError as e:
        raise RuntimeError(
            "jsonschema package required for validation: pip install jsonschema"
        ) from e

    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema).validate(data)
    except ValidationError as e:
        # Provide context about what artifact failed
        raise ValueError(
            f"Schema validation failed against {schema_name}: {e.message}\n"
            f"  Path: {' / '.join(str(p) for p in e.absolute_path)}\n"
            f"  Schema path: {' / '.join(str(p) for p in e.schema_path)}"
        ) from e


# ─── Simple YAML fallback (no PyYAML) ──────────────────────────

def _simple_yaml_parse(text: str) -> dict:
    """Minimal YAML parser for frontmatter: only key: value pairs."""
    result: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if v.lower() in ("true", "yes"):
            result[k] = True
        elif v.lower() in ("false", "no"):
            result[k] = False
        elif v.lower() in ("null", "~", ""):
            result[k] = None
        else:
            try:
                result[k] = int(v)
            except ValueError:
                try:
                    result[k] = float(v)
                except ValueError:
                    result[k] = v
    return result
