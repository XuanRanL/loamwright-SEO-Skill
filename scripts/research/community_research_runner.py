"""Community research runner — fetch Reddit/X, classify signal/claim, verify claims,
emit community-research.json. This is the REAL executor that replaces the Rule 6
dead-code scaffold in scripts/analysis/social_research_aggregator.py.

Signals (real language / pain points / questions / contrarian views / success
stories) feed the writer + PAA freely. Claims are quarantined and only stated as
fact when an authoritative source corroborates them — and that authoritative
source, never the community URL, is what gets cited (the iron rule).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Optional

from scripts.analysis.social_research_aggregator import (
    InsightType,
    SocialResearchAggregator,
)
from scripts.fetch.community_search import CommunitySearchResponse, search_community
from scripts.research.community_claim_verifier import (
    AuthoritativeHit,
    classify,
    default_authoritative_lookup,
    verify_claim,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_QUERY_SUFFIXES = [
    "",
    "experience OR results",
    "tested OR experiment OR data",
    "advice OR help",
    "recommendation OR review OR vs",
]


def build_queries(topic: str, source: str) -> list[str]:
    """Five angled queries per source (general / experience / experimental /
    help / comparison). ``source`` is accepted for future per-source tuning."""
    return [f"{topic} {sfx}".strip() for sfx in _QUERY_SUFFIXES]


def _engagement(score: float) -> str:
    return "high" if score >= 0.85 else "medium" if score >= 0.6 else "low"


def run_community_research(
    topic: str,
    *,
    sources: list[str],
    task_id: Optional[str],
    authoritative_lookup: Callable[[str], Optional[AuthoritativeHit]],
    search_fn: Callable[..., CommunitySearchResponse] = search_community,
    max_results: int = 8,
) -> dict[str, object]:
    signals: dict[str, list[str]] = {
        "real_language": [],
        "pain_points": [],
        "questions": [],
        "contrarian_views": [],
        "success_stories": [],
    }
    claims: list[dict[str, object]] = []
    threads = 0
    seen_claims: set[str] = set()
    aggregator = SocialResearchAggregator()

    for source in sources:
        for q in build_queries(topic, source):
            resp = search_fn(q, source=source, max_results=max_results, task_id=task_id)
            for post in resp.posts:
                threads += 1
                text = (post.content or post.title).strip()
                if not text:
                    continue
                if classify(text) == "signal":
                    itype = aggregator.categorize_insight(text)
                    if itype == InsightType.QUESTION:
                        signals["questions"].append(text)
                    elif itype == InsightType.PAIN_POINT:
                        signals["pain_points"].append(text)
                    elif itype == InsightType.SUCCESS_STORY:
                        signals["success_stories"].append(text)
                    elif itype == InsightType.DEBATE:
                        signals["contrarian_views"].append(text)
                    signals["real_language"].append(text[:200])
                else:
                    if text in seen_claims:
                        continue
                    seen_claims.add(text)
                    consensus = sum(
                        1
                        for p in resp.posts
                        if text[:40].lower() in (p.content or "").lower()
                    )
                    try:
                        verdict = verify_claim(
                            text,
                            post.url,
                            source,
                            consensus=consensus,
                            engagement=_engagement(post.score),
                            author_credibility="low",
                            authoritative_lookup=authoritative_lookup,
                        )
                    except Exception as e:  # noqa: BLE001 — one bad claim must not
                        # kill the whole community pass (2026-07-01: a single
                        # >400-char claim query crashed every batch's community
                        # research). Degrade to skipping this claim, keep going.
                        print(
                            f"⚠ community_research: verify_claim failed for one claim "
                            f"({type(e).__name__}: {str(e)[:120]}) — skipping it",
                            file=sys.stderr,
                        )
                        continue
                    if verdict.writer_guidance == "drop":
                        continue
                    claims.append(
                        {
                            "text": verdict.text,
                            "source_url": verdict.source_url,  # provenance only
                            "source": verdict.source,
                            "verdict": verdict.verdict,
                            "dimensions": verdict.dimensions,
                            "authoritative_source": (
                                {
                                    "title": verdict.authoritative_source.title,
                                    "url": verdict.authoritative_source.url,
                                    "apa": verdict.authoritative_source.apa,
                                }
                                if verdict.authoritative_source
                                else None
                            ),
                            "writer_guidance": verdict.writer_guidance,
                        }
                    )

    for k in signals:
        signals[k] = list(dict.fromkeys(signals[k]))[:15]

    return {
        "sources_queried": sources,
        "threads_analyzed": threads,
        "signals": signals,
        "claims": claims,
    }


def write_artifact(
    payload: dict[str, object], task_id: str, workspace_root: Path | None = None
) -> Path:
    root = workspace_root or (_REPO_ROOT / "memory" / "workspace")
    out_dir = root / task_id / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "community-research.json"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path


def merge_into_research(
    payload: dict[str, object], research_json_path: Path
) -> None:
    data: dict[str, object] = (
        json.loads(research_json_path.read_text(encoding="utf-8"))
        if research_json_path.exists()
        else {}
    )
    data["community_insights"] = payload
    research_json_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Run community (Reddit/X) research")
    ap.add_argument("--topic", required=True)
    ap.add_argument("--task-id")
    ap.add_argument("--sources", default="reddit,x")
    ap.add_argument("--max", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = run_community_research(
        args.topic,
        sources=[s.strip() for s in args.sources.split(",") if s.strip()],
        task_id=args.task_id,
        authoritative_lookup=default_authoritative_lookup(args.task_id),
        max_results=args.max,
    )
    if args.task_id:
        art = write_artifact(out, args.task_id)
        research_path = art.parent.parent / "research.json"
        if research_path.exists():
            merge_into_research(out, research_path)

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        signals_obj = out["signals"]
        claims_obj = out["claims"]
        sig_n = (
            sum(len(v) for v in signals_obj.values())
            if isinstance(signals_obj, dict)
            else 0
        )
        n_claims = len(claims_obj) if isinstance(claims_obj, list) else 0
        print(
            f"sources={out['sources_queried']} threads={out['threads_analyzed']} "
            f"signals={sig_n} claims={n_claims}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
