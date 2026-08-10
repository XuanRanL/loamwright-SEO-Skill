"""
scripts/_core/serpapi_engines.py — SerpApi engine registry + on-demand selector.

SerpApi exposes ~110 engines through one endpoint. They are ALL already callable via
`scripts/fetch/serpapi_query.py --engine X` (the wrapper is engine-agnostic). The problem this
module solves is NOT "add engines" — it is "let the pipeline pick the right 2-4 engines for an
article's vertical/intent WITHOUT bloating agent prompts with a 110-line list".

Design:
  - This registry is DATA (not prompt): each curated, SEO-relevant engine maps to its real query
    param (verified live, not guessed), category, SEO use, and the verticals/intents that should
    trigger it.
  - `suggest(vertical, intent, surfaces)` is a DETERMINISTIC selector that returns a short list —
    universal core/GEO engines always, plus the vertical/intent/surface-specific ones. The agent
    calls it, then runs `serpapi_query` for the handful returned, instead of reasoning over all 110.
  - `query_param_for(engine)` is the single source of truth for per-engine query-param names
    (serpapi_query imports it), so the youtube=`search_query` / amazon=`k` / yahoo=`p` quirks live
    in one place.

Uncurated engines (flights, hotels, app reviews, ads, …) are intentionally omitted from routing —
they're still callable with `--engine`, they just don't auto-fire for content SEO. Add an entry
here to bring an engine into on-demand routing.

CLI:
    python -m scripts._core.serpapi_engines --list [--category core] [--json]
    python -m scripts._core.serpapi_engines --suggest --vertical ecommerce --intent commercial --surfaces youtube --json
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Final

# category: core | geo | authority | freshness | video | ecommerce | local | visual | qa | niche | intl
# verticals: ["*"] = universal; otherwise tags matched against the article's vertical/intent.
# param:  the REAL query-param name (verified live 2026-06-26 where noted); default "q".
# needs:  an additional required param the caller must supply (e.g. a location).
ENGINES: Final[dict[str, dict[str, Any]]] = {
    # ── CORE (every article) ──
    "google":                 {"param": "q", "cat": "core", "verticals": ["*"], "seo": "Organic positions + PAA (related_questions) + related_searches + answer_box + inline AI Overview"},
    "google_autocomplete":    {"param": "q", "cat": "core", "verticals": ["*"], "seo": "Keyword-expansion suggestions straight from Google"},
    "google_trends":          {"param": "q", "cat": "core", "verticals": ["*"], "seo": "Seasonality + rising/breakout queries (interest_over_time; --param data_type=TIMESERIES)"},
    "google_related_questions": {"param": "q", "cat": "core", "verticals": ["*"], "seo": "Deeper People-Also-Ask expansion"},
    # ── GEO / AI-answer visibility (the agency's core mission) ──
    "ai_overview":            {"param": "q", "cat": "geo", "verticals": ["*"], "seo": "Google AI Overview + its cited sources (convenience engine: inline + auto page_token follow)"},
    "google_ai_mode":         {"param": "q", "cat": "geo", "verticals": ["*"], "seo": "Google AI Mode answer: text_blocks + references (cited sources) + reconstructed_markdown"},
    "bing":                   {"param": "q", "cat": "geo", "verticals": ["*"], "seo": "Bing SERP (Copilot-adjacent surface)"},
    "duckduckgo":             {"param": "q", "cat": "geo", "verticals": ["*"], "seo": "DuckDuckGo SERP (independent index)"},
    # ── FRESHNESS ──
    "google_news":            {"param": "q", "cat": "freshness", "verticals": ["*"], "seo": "News results with dates → recency / newsworthiness angle"},
    # ── AUTHORITY ──
    "google_scholar":         {"param": "q", "cat": "authority", "verticals": ["health", "science", "finance", "legal", "b2b", "manufacturing"], "seo": "Academic ranking + 'cited by N' counts (complements mcp__semantic-scholar/pubmed)"},
    "google_patents":         {"param": "q", "cat": "authority", "verticals": ["manufacturing", "tech", "science"], "seo": "Patents / prior art (overlaps mcp__us-gov USPTO — pick one)"},
    # ── VIDEO ──
    "youtube":                {"param": "search_query", "cat": "video", "verticals": ["*"], "surface": "youtube", "seo": "YouTube video competitors / results (video_results)"},
    "google_videos":          {"param": "q", "cat": "video", "verticals": ["*"], "seo": "Video pack in Google SERP (is the SERP video-heavy?)"},
    # ── ECOMMERCE (commercial/transactional intent or product verticals) ──
    "google_shopping":        {"param": "q", "cat": "ecommerce", "verticals": ["ecommerce", "product-review", "buying-guide"], "seo": "Shopping results + prices + filters"},
    "amazon":                 {"param": "k", "cat": "ecommerce", "verticals": ["ecommerce", "product-review"], "seo": "Amazon product results (param `k`)"},
    "walmart":                {"param": "query", "cat": "ecommerce", "verticals": ["ecommerce", "product-review"], "seo": "Walmart products (param `query`)"},
    "ebay":                   {"param": "_nkw", "cat": "ecommerce", "verticals": ["ecommerce", "product-review"], "seo": "eBay listings (param `_nkw`)"},
    "home_depot":             {"param": "q", "cat": "ecommerce", "verticals": ["ecommerce", "home-diy"], "seo": "Home Depot products"},
    # ── LOCAL ──
    "google_local":           {"param": "q", "cat": "local", "verticals": ["local", "service-area-business"], "needs": "location", "seo": "Local pack (local_results) — pass --param location=\"City, State\""},
    "google_maps":            {"param": "q", "cat": "local", "verticals": ["local", "service-area-business"], "needs": "ll", "seo": "Maps places — pass --param ll=\"@lat,lng,zoom\""},
    "yelp":                   {"param": "find_desc", "cat": "local", "verticals": ["local", "hospitality"], "needs": "find_loc", "seo": "Yelp businesses (params `find_desc` + `find_loc`)"},
    "tripadvisor":            {"param": "q", "cat": "local", "verticals": ["travel", "hospitality"], "seo": "TripAdvisor places / reviews"},
    # ── VISUAL (image SEO + real-photo provenance) ──
    "google_images":          {"param": "q", "cat": "visual", "verticals": ["*"], "seo": "Image SERP results (image SEO competitors)"},
    "google_reverse_image":   {"param": "image_url", "cat": "visual", "verticals": ["*"], "seo": "Where an image appears online — real-photo provenance / find the original source"},
    "google_lens":            {"param": "url", "cat": "visual", "verticals": ["*"], "seo": "Visual matches for an image"},
    # ── QA / community ──
    "google_forums":          {"param": "q", "cat": "qa", "verticals": ["*"], "seo": "Forum / Reddit discussions surfaced in the SERP"},
    # ── NICHE verticals (load ONLY for that vertical) ──
    "google_finance":         {"param": "q", "cat": "niche", "verticals": ["finance"], "seo": "Stock / ticker data (q = ticker)"},
    "google_jobs":            {"param": "q", "cat": "niche", "verticals": ["careers", "hr"], "seo": "Job listings"},
    "google_events":          {"param": "q", "cat": "niche", "verticals": ["events", "local"], "seo": "Local events"},
    "google_play":            {"param": "q", "cat": "niche", "verticals": ["apps", "mobile"], "seo": "Google Play app results"},
    "apple_app_store":        {"param": "term", "cat": "niche", "verticals": ["apps", "mobile"], "seo": "Apple App Store app results (param `term`)"},
    # ── INTERNATIONAL SERPs (non-US target markets) ──
    "naver":                  {"param": "query", "cat": "intl", "verticals": ["intl-kr"], "seo": "Naver (Korea) SERP — also has an AI overview (param `query`)"},
    "baidu":                  {"param": "q", "cat": "intl", "verticals": ["intl-cn"], "seo": "Baidu (China) SERP"},
    "yandex":                 {"param": "text", "cat": "intl", "verticals": ["intl-ru"], "seo": "Yandex (Russia) SERP (param `text`)"},
    "yahoo":                  {"param": "p", "cat": "intl", "verticals": ["intl-jp"], "seo": "Yahoo SERP (param `p`)"},
}

_UNIVERSAL_CATS: Final[frozenset[str]] = frozenset({"core", "geo"})


def query_param_for(engine: str) -> str:
    """The real query-param name for an engine (default 'q'). Single source of truth."""
    param: str = ENGINES.get(engine, {}).get("param", "q")
    return param


def suggest(
    vertical: str | None = None,
    intent: str | None = None,
    surfaces: list[str] | None = None,
) -> list[dict[str, str]]:
    """Deterministically shortlist the engines worth calling for one article.

    Always returns the universal core + GEO engines; adds vertical-, surface- and
    intent-specific engines on top. The agent then runs serpapi_query for the few returned
    rather than reasoning over all ~110 engines.
    """
    surf = set(surfaces or [])
    intent = (intent or "").lower()
    out: list[dict[str, str]] = []
    for eid, m in ENGINES.items():
        verticals = m["verticals"]
        why: str | None = None
        if m["cat"] in _UNIVERSAL_CATS and "*" in verticals:
            why = "universal (core/GEO)"
        elif vertical and vertical in verticals:
            why = f"vertical={vertical}"
        elif m.get("surface") and m["surface"] in surf:
            why = f"surface={m['surface']}"
        elif m["cat"] == "ecommerce" and intent in ("commercial", "transactional", "product"):
            why = f"intent={intent}"
        elif m["cat"] == "freshness" and intent in ("news", "trending", "informational"):
            why = "freshness"
        if why:
            out.append({"engine": eid, "param": m["param"], "why": why, "use": m["seo"],
                        **({"needs": m["needs"]} if m.get("needs") else {})})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="SerpApi engine registry + selector")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="List curated engines")
    g.add_argument("--suggest", action="store_true", help="Shortlist engines for an article")
    ap.add_argument("--category", help="Filter --list by category")
    ap.add_argument("--vertical", help="Article vertical (e.g. ecommerce, local, finance, manufacturing)")
    ap.add_argument("--intent", help="Search intent (informational/commercial/transactional/news)")
    ap.add_argument("--surfaces", help="Comma-separated target surfaces (e.g. youtube)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.list:
        rows = [{"engine": e, **{k: m[k] for k in ("param", "cat", "seo")}, "verticals": m["verticals"]}
                for e, m in ENGINES.items() if not args.category or m["cat"] == args.category]
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            for r in rows:
                print(f"  {r['engine']:24s} [{r['cat']:9s}] param={r['param']:12s} {r['seo']}")
        return 0

    picks = suggest(args.vertical, args.intent,
                    args.surfaces.split(",") if args.surfaces else None)
    if args.json:
        print(json.dumps(picks, indent=2, ensure_ascii=False))
    else:
        print(f"Suggested engines ({len(picks)}) for vertical={args.vertical} intent={args.intent} surfaces={args.surfaces}:")
        for p in picks:
            extra = f"  (needs {p['needs']})" if p.get("needs") else ""
            print(f"  --engine {p['engine']:22s} [{p['why']}]{extra}  {p['use']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
