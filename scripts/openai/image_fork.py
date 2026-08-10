"""
scripts/openai/image_fork.py — image-pipeline router (orchestrator "Fork B" entry).

Routes the article's image generation by project policy:
  - projects that source REAL product photos (image_brand_policy.source_real_photos, e.g.
    project-echo) → scripts.openai.real_brand_image_pipeline.run_for_workspace
  - everyone else → the canonical AI image pipeline (scripts.openai.openai_image_pipeline),
    delegated UNCHANGED (so existing projects are unaffected).

The orchestrator's image-pipeline-fork stage calls this instead of openai_image_pipeline
directly, passing --project-slug. ``decide_pipeline`` is a pure-ish policy read (unit-tested);
the delegation is integration-tested via a workspace smoke run.
"""
from __future__ import annotations

import sys


def decide_pipeline(project_slug: str) -> str:
    """Return "real_brand" if the project sources real photos, else "ai_gen"."""
    if not project_slug:
        return "ai_gen"
    try:
        from scripts._core.image_brand_policy import load_image_brand_policy
        return "real_brand" if load_image_brand_policy(project_slug).source_real_photos else "ai_gen"
    except Exception as exc:
        # Never mis-route SILENTLY: a real-photo project falling back to AI-gen is exactly the
        # Rule-7 failure this feature exists to prevent. Surface it instead of swallowing.
        print(f"[image_fork] policy read failed for {project_slug!r}; defaulting to ai_gen: {exc}",
              file=sys.stderr)
        return "ai_gen"


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import subprocess

    ap = argparse.ArgumentParser(description="Route image generation by project policy.")
    ap.add_argument("--requests-file", default="")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--task-id", default="")
    ap.add_argument("--project-slug", default="")
    ap.add_argument("--mode", default="realtime")
    ap.add_argument("--json", action="store_true")
    args, _extra = ap.parse_known_args(argv)

    route = decide_pipeline(args.project_slug)
    if route == "real_brand":
        from scripts.openai import real_brand_image_pipeline as rb
        # project_slug is guaranteed truthy here (decide_pipeline returns "ai_gen" for "")
        merged = rb.run_for_workspace(args.workspace, args.project_slug)
        print(json.dumps({"ok": True, "route": "real_brand", "count": len(merged)}, ensure_ascii=False))
        return 0

    # ai_gen → delegate to the canonical pipeline UNCHANGED (subprocess = no coupling).
    cmd = [sys.executable, "-m", "scripts.openai.openai_image_pipeline", "generate",
           "--workspace", args.workspace, "--mode", args.mode]
    if args.requests_file:
        cmd += ["--requests-file", args.requests_file]
    if args.task_id:
        cmd += ["--task-id", args.task_id]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(_main())
