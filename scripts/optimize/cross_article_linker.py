"""
scripts/optimize/cross_article_linker.py — Portfolio-scope internal link orchestrator.

The per-article `linker` agent only sees ONE article. This script sees ALL
articles in a project and finds:
  1. Article A mentions concept X, article B is the canonical X → add link A→B
  2. Spoke article links missing to its pillar
  3. Pillar article has no spoke roundup link
  4. Definition article isn't linked from any tutorial that uses the term
  5. Recent article supersedes older one on same topic → add redirect-style link

Similarity: TF-IDF over (title + abstract + H2 headings). No embeddings —
keep dependencies minimal. For 100-1000 articles this is fast enough (<5s).

Output: projects/{slug}/cross-link-suggestions-{date}.json
  - List of (source_url, target_url, anchor_text, location_hint, confidence)
  - Apply mode (--apply): edits via WP REST PATCH, logs to change-log

CLI:
    python -m scripts.optimize.cross_article_linker --site my-site
    python -m scripts.optimize.cross_article_linker --site my-site --min-confidence 0.6
    python -m scripts.optimize.cross_article_linker --site my-site --apply
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from scripts._core.file_bus import PLUGIN_ROOT


STOP = frozenset("""
a an the and or but if then so as of in on at to for with from by about
is are was were be been being am this that these those it its
we us our you your they them their he him his she her i me my
will would could should may might can must do does did done
have has had not no nor only just very more most some any all
""".split())


@dataclass
class Article:
    slug: str
    url: str
    title: str = ""
    abstract: str = ""
    primary_keyword: str = ""
    h2_headings: list[str] = field(default_factory=list)
    format: str = ""
    is_pillar: bool = False
    is_spoke_of: str = ""             # pillar slug if this is a spoke
    published_at: str = ""
    body_path: str = ""
    existing_internal_links: list[str] = field(default_factory=list)


@dataclass
class LinkSuggestion:
    source_url: str
    source_slug: str
    target_url: str
    target_slug: str
    anchor_text: str
    location_hint: str            # which H2 section the anchor falls in
    confidence: float             # 0-1
    reason: str                   # "pillar-spoke" / "topic-overlap" / "term-definition"


def _tokens(text: str) -> list[str]:
    """Simple tokenizer for TF-IDF."""
    return [
        t.lower() for t in re.findall(r"\b[a-zA-Z][a-zA-Z0-9-]{2,}\b", text or "")
        if t.lower() not in STOP and len(t) > 2
    ]


def _load_articles(site_slug: str) -> list[Article]:
    """Read all published articles + per-article features."""
    arts_dir = PLUGIN_ROOT / "projects" / site_slug / "articles"
    if not arts_dir.is_dir():
        return []

    articles: list[Article] = []
    for d in sorted(arts_dir.iterdir()):
        if not d.is_dir():
            continue
        log = d / "publish-log.json"
        if not log.exists():
            continue
        try:
            log_data = json.loads(log.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        art = Article(
            slug=d.name,
            url=log_data.get("post_url", ""),
            title=log_data.get("title", ""),
            primary_keyword=log_data.get("primary_keyword", ""),
            published_at=log_data.get("published_at", ""),
        )

        # Load features if present
        feat = d / "features.json"
        if feat.exists():
            try:
                fdata = json.loads(feat.read_text(encoding="utf-8"))
                art.format = fdata.get("format", "")
                art.h2_headings = fdata.get("h2_headings", [])
                art.abstract = fdata.get("abstract", "")
                art.existing_internal_links = fdata.get("internal_links", [])
                art.is_pillar = fdata.get("format") == "pillar-page"
                art.is_spoke_of = fdata.get("spoke_of", "")
            except (OSError, json.JSONDecodeError):
                pass

        # Load body if present
        for body_file in ("final.md", "draft.md"):
            bp = d / body_file
            if bp.exists():
                art.body_path = str(bp)
                break

        if art.url:
            articles.append(art)

    return articles


def _build_tfidf(articles: list[Article]) -> tuple[list[dict], dict]:
    """Compute TF-IDF per article. Returns (per-article term vectors, idf dict)."""
    docs = []
    for a in articles:
        text = " ".join(filter(None, [
            a.title, a.primary_keyword, a.abstract, " ".join(a.h2_headings)
        ]))
        docs.append(_tokens(text))

    # IDF
    doc_count = len(docs)
    df: Counter = Counter()
    for tokens in docs:
        for term in set(tokens):
            df[term] += 1
    idf = {term: math.log((doc_count + 1) / (cnt + 1)) + 1 for term, cnt in df.items()}

    # TF-IDF per doc
    vectors = []
    for tokens in docs:
        tf = Counter(tokens)
        max_tf = max(tf.values()) if tf else 1
        v = {term: (count / max_tf) * idf.get(term, 0) for term, count in tf.items()}
        vectors.append(v)

    return vectors, idf


def _cosine(v1: dict, v2: dict) -> float:
    if not v1 or not v2:
        return 0.0
    common = set(v1) & set(v2)
    if not common:
        return 0.0
    dot = sum(v1[t] * v2[t] for t in common)
    n1 = math.sqrt(sum(x*x for x in v1.values()))
    n2 = math.sqrt(sum(x*x for x in v2.values()))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


def _find_anchor_in_body(body: str, target_keyword: str) -> tuple[str, str] | None:
    """Find a natural anchor in body where target_keyword (or variants) appears.

    Returns (anchor_text, location_hint H2 section name) or None.
    """
    if not body or not target_keyword:
        return None

    # Try exact match
    keyword_lower = target_keyword.lower()
    body_lower = body.lower()
    idx = body_lower.find(keyword_lower)
    if idx == -1:
        # Try partial: first two words
        parts = target_keyword.split()
        if len(parts) >= 2:
            short = " ".join(parts[:2]).lower()
            idx = body_lower.find(short)
            if idx == -1:
                return None
            anchor_match = body[idx:idx + len(short)]
        else:
            return None
    else:
        anchor_match = body[idx:idx + len(target_keyword)]

    # Find which H2 this falls under
    # Scan for last H2 before idx
    h2_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    location = "intro"
    for m in h2_pattern.finditer(body):
        if m.start() < idx:
            location = m.group(1).strip()
        else:
            break

    # Don't suggest anchor in headings or References
    if location.lower() in ("references", "conclusion"):
        return None

    return anchor_match, location


def _is_already_linked(source: Article, target_url: str) -> bool:
    return target_url in (source.existing_internal_links or [])


def find_suggestions(
    site_slug: str,
    *,
    min_confidence: float = 0.5,
    max_suggestions_per_article: int = 5,
) -> list[LinkSuggestion]:
    """Run the cross-article link orchestrator."""
    articles = _load_articles(site_slug)
    if len(articles) < 2:
        return []

    vectors, _idf = _build_tfidf(articles)

    suggestions: list[LinkSuggestion] = []

    for i, src in enumerate(articles):
        per_source_count = 0
        body = ""
        if src.body_path:
            try:
                body = Path(src.body_path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                body = ""
        if not body:
            continue

        # Score all other articles as potential targets
        candidates = []
        for j, tgt in enumerate(articles):
            if i == j:
                continue
            if _is_already_linked(src, tgt.url):
                continue

            base_score = _cosine(vectors[i], vectors[j])

            # Boosts
            reason = "topic-overlap"
            boost = 0.0
            # Pillar-spoke boost
            if src.is_spoke_of and src.is_spoke_of == tgt.slug:
                boost += 0.3
                reason = "pillar-target"
            elif tgt.is_spoke_of and tgt.is_spoke_of == src.slug:
                boost += 0.3
                reason = "spoke-link"
            # Definition target boost
            if tgt.format == "definition" and tgt.primary_keyword:
                if tgt.primary_keyword.lower() in body.lower():
                    boost += 0.2
                    reason = "term-definition"

            confidence = min(1.0, base_score + boost)
            if confidence < min_confidence:
                continue
            candidates.append((confidence, tgt, reason))

        candidates.sort(reverse=True, key=lambda x: x[0])

        for confidence, tgt, reason in candidates:
            if per_source_count >= max_suggestions_per_article:
                break
            anchor_info = _find_anchor_in_body(body, tgt.primary_keyword or tgt.title)
            if not anchor_info:
                continue
            anchor_text, location = anchor_info
            suggestions.append(LinkSuggestion(
                source_url=src.url,
                source_slug=src.slug,
                target_url=tgt.url,
                target_slug=tgt.slug,
                anchor_text=anchor_text,
                location_hint=location,
                confidence=round(confidence, 3),
                reason=reason,
            ))
            per_source_count += 1

    return suggestions


def save_suggestions(site_slug: str, suggestions: list[LinkSuggestion]) -> Path:
    out_dir = PLUGIN_ROOT / "projects" / site_slug / "audits"
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    out_path = out_dir / f"cross-link-suggestions-{today}.json"
    out_path.write_text(json.dumps({
        "site_slug": site_slug,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suggestion_count": len(suggestions),
        "suggestions": [asdict(s) for s in suggestions],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Portfolio cross-article link orchestrator")
    ap.add_argument("--site", required=True)
    ap.add_argument("--min-confidence", type=float, default=0.5)
    ap.add_argument("--max-per-article", type=int, default=5)
    ap.add_argument("--apply", action="store_true",
                    help="Apply suggestions via WP REST PATCH (TODO; for now writes JSON only)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    suggestions = find_suggestions(
        args.site, min_confidence=args.min_confidence,
        max_suggestions_per_article=args.max_per_article,
    )

    if not suggestions:
        print("No suggestions found.", file=sys.stderr)
        print("(Need ≥2 published articles with features.json for the site.)")
        return 1

    out_path = save_suggestions(args.site, suggestions)

    if args.json:
        print(json.dumps({
            "site_slug": args.site,
            "suggestion_count": len(suggestions),
            "output_path": str(out_path),
        }, indent=2))
    else:
        print(f"━━ Cross-article link suggestions: {args.site} ━━━━━━━━━")
        print(f"  Articles analyzed:    {len(_load_articles(args.site))}")
        print(f"  Suggestions:          {len(suggestions)}")
        print(f"  Output:               {out_path}")
        print()
        print("  Top 10 suggestions (by confidence):")
        for s in sorted(suggestions, key=lambda x: -x.confidence)[:10]:
            print(f"    [{s.confidence:.2f}] [{s.reason:<18s}]")
            print(f"      {s.source_slug}")
            print(f"      → {s.target_slug}  (anchor: '{s.anchor_text}', loc: {s.location_hint})")

    if args.apply:
        print("\n--apply not yet implemented for cross-link orchestrator.")
        print("Suggestions saved; manual application via WP admin OR review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
