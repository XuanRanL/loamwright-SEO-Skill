"""scripts/fetch/community_search.py — fetch community (Reddit/X) posts via Tavily.

Wraps ``scripts.fetch.tavily_search`` with ``include_domains`` so it reuses the
Tavily key-pool, 72h cache, and cost_ledger logging. This is NOT the official
Reddit/X API (approval-gated + commercial pricing); it is the same Tavily search
the rest of the pipeline uses, scoped to community domains.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Literal

from scripts.fetch import tavily_search

SOURCE_DOMAINS: dict[str, list[str]] = {
    "reddit": ["reddit.com"],
    "x": ["x.com", "twitter.com"],
}


@dataclass
class CommunityPost:
    url: str
    title: str
    content: str
    score: float
    source: str
    published_date: str | None = None
    raw_content: str | None = None


@dataclass
class CommunitySearchResponse:
    query: str
    source: str
    posts: list[CommunityPost] = field(default_factory=list)
    cost_credits: int = 0
    cached: bool = False


def search_community(
    query: str,
    *,
    source: Literal["reddit", "x"],
    max_results: int = 10,
    task_id: str | None = None,
) -> CommunitySearchResponse:
    """Search a community surface (reddit/x) via Tavily include_domains."""
    if source not in SOURCE_DOMAINS:
        raise ValueError(
            f"source must be one of {sorted(SOURCE_DOMAINS)}, got {source!r}"
        )
    resp = tavily_search.search(
        query,
        include_domains=SOURCE_DOMAINS[source],
        max_results=max_results,
        depth="advanced",
        task_id=task_id,
    )
    posts = [
        CommunityPost(
            url=r.url,
            title=r.title,
            content=r.content,
            score=r.score,
            source=source,
            published_date=r.published_date,
            raw_content=r.raw_content,
        )
        for r in resp.results
    ]
    return CommunitySearchResponse(
        query=query,
        source=source,
        posts=posts,
        cost_credits=resp.cost_credits,
        cached=resp.cached,
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fetch Reddit/X posts via Tavily include_domains"
    )
    ap.add_argument("query")
    ap.add_argument("--source", choices=sorted(SOURCE_DOMAINS), required=True)
    ap.add_argument("--max", type=int, default=10)
    ap.add_argument("--task-id")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    resp = search_community(
        args.query, source=args.source, max_results=args.max, task_id=args.task_id
    )
    if args.json:
        print(
            json.dumps(
                {
                    "query": resp.query,
                    "source": resp.source,
                    "posts": [asdict(p) for p in resp.posts],
                    "cost_credits": resp.cost_credits,
                    "cached": resp.cached,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"{resp.source}: {len(resp.posts)} posts ({resp.cost_credits} credits)")
        for i, p in enumerate(resp.posts, 1):
            print(f"  [{i}] {p.title}  {p.url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
