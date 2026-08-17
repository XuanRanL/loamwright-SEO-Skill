from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from scripts._core.file_lock import atomic_write_text, locked
from scripts._core.news_item import NewsItem, canonical_url, dedup_key, domain_of, make_item

# Resolve plugin root relative to this file so paths work both from cwd and from
# an installed plugin cache (Rule 7 — env-pinned; never cwd-relative for state files).
PLUGIN_ROOT = Path(__file__).resolve().parents[2]

Cluster = dict[str, Any]


# ---------------------------------------------------------------------------
# Core helpers (Plan 1 — unchanged)
# ---------------------------------------------------------------------------

def _published_dt(item: NewsItem) -> datetime:
    """Parse an item's published_at to a tz-aware UTC datetime; oldest-possible on failure."""
    try:
        dt = datetime.fromisoformat(item["published_at"])
    except (ValueError, KeyError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def cluster_items(items: list[NewsItem]) -> list[Cluster]:
    groups: dict[str, list[NewsItem]] = {}
    for it in items:
        groups.setdefault(dedup_key(it), []).append(it)
    clusters: list[Cluster] = []
    for i, (_, members) in enumerate(groups.items()):
        members_sorted = sorted(members, key=_published_dt, reverse=True)
        domains = {m["source_domain"] for m in members_sorted}
        clusters.append(
            {
                "cluster_id": f"c{i+1}",
                "head": members_sorted[0],
                "members": members_sorted,
                "corroboration": len(domains),
            }
        )
    return clusters


_ACTIVE_FOLLOWUP = {"developing", "unconfirmed", "watch"}

_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have how in is it its of on or "
    "that the this to was what when where who why will with your you new says "
    "said after over under more most 2024 2025 2026 2027".split()
)


def _story_tokens(headline: str) -> frozenset[str]:
    """Significant lowercase tokens of a headline, for cross-week story identity."""
    words = re.findall(r"[a-z0-9]+", str(headline or "").lower())
    return frozenset(w for w in words if len(w) > 2 and w not in _STOPWORDS)


def resolve_recurrences(
    covered: list[dict[str, Any]],
    clusters: list[Cluster],
    *,
    window_weeks: int,
    today: str,
    similarity: float = 0.5,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Auto-mark previously-reported stories that RECUR with fresh coverage (2026-07-01).

    Root cure for the inert follow-up state machine: the active statuses
    ("developing"/"unconfirmed"/"watch") were only ever READ — no executor wrote
    them, so the entire follow-up subsystem was dormant unless an operator
    hand-edited covered.json. A story is a recurrence when a fresh cluster's
    headline shares >= ``similarity`` Jaccard token overlap with a covered entry
    from an EARLIER issue inside the follow-up window, under a DIFFERENT
    canonical URL (same-URL re-appearances are already handled by
    cross_week_filter/build_covered_update). Such entries are promoted to
    "developing" so select_followups/_emit_followups/resolve_issue_budget — the
    already-built machinery — finally receive input.

    Returns (updated_covered, list_of_promoted_urls). Pure; caller persists.
    """
    try:
        cutoff = (datetime.fromisoformat(today) - timedelta(weeks=window_weeks)).date().isoformat()
    except ValueError:
        cutoff = today
    fresh: list[tuple[frozenset[str], str]] = []
    for cl in clusters:
        head = cl.get("head") or {}
        toks = _story_tokens(head.get("headline", ""))
        if toks:
            fresh.append((toks, canonical_url(head.get("url", ""))))
    promoted: list[str] = []
    out: list[dict[str, Any]] = []
    for entry in covered:
        e = dict(entry)
        issued = str(e.get("issue_date") or "")
        if (
            e.get("status") == "reported"
            and cutoff <= issued < today          # earlier issue, inside window
        ):
            etoks = _story_tokens(e.get("headline", ""))
            eurl = str(e.get("canonical_url") or "")
            if etoks:
                for toks, curl in fresh:
                    if curl and curl != eurl:
                        inter = len(etoks & toks)
                        # Overlap coefficient (∩ / min), not Jaccard: a recurring
                        # story's fresh headline REPHRASES the old one ("…rolling
                        # out" → "…rollout expands"), so union-normalising punishes
                        # exactly the inputs we must match. Require ≥3 shared
                        # significant tokens so short headlines can't false-match.
                        denom = min(len(etoks), len(toks)) or 1
                        if inter >= 3 and inter / denom >= similarity:
                            e["status"] = "developing"
                            e["recurred_at"] = today
                            promoted.append(eurl)
                            break
        out.append(e)
    return out, promoted


def expire_and_prune_covered(
    covered: list[dict[str, Any]],
    *,
    window_weeks: int,
    retention_weeks: int,
    today: str,
) -> list[dict[str, Any]]:
    """Close aged-out active entries + bound the ledger (2026-07-01).

    - An active-status entry older than the follow-up window can never be
      emitted again (select_followups' cutoff) — without this it stayed a
      permanent zombie. It is closed back to "reported".
    - Entries older than ``retention_weeks`` are dropped entirely so
      covered.json cannot grow unboundedly.
    """
    try:
        base = datetime.fromisoformat(today)
    except ValueError:
        return covered
    window_cutoff = (base - timedelta(weeks=window_weeks)).date().isoformat()
    retain_cutoff = (base - timedelta(weeks=retention_weeks)).date().isoformat()
    out: list[dict[str, Any]] = []
    for entry in covered:
        e = dict(entry)
        issued = str(e.get("issue_date") or "")
        if issued and issued < retain_cutoff:
            continue  # pruned
        if e.get("status") in _ACTIVE_FOLLOWUP and issued and issued < window_cutoff:
            e["status"] = "reported"
            e["expired_at"] = today
        out.append(e)
    return out


def week_key(date_str: str) -> str:
    """ISO-week key ('2026-W27') of a YYYY-MM-DD date string; '' if unparseable."""
    try:
        d = datetime.fromisoformat(date_str[:10])
    except ValueError:
        return ""
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def find_issue_in_week(issues: list[dict[str, Any]], today: str) -> dict[str, Any] | None:
    """Return an existing issue record from the SAME ISO week as ``today``, else None.

    Week-level idempotency (2026-07-01): task ids are DATE-stamped, so a Monday
    run and a Wednesday run in the same week previously produced two drafts, two
    issues.json rows and two hub rows with no guard at all.
    """
    wk = week_key(today)
    if not wk:
        return None
    for rec in issues:
        d = str(rec.get("issue_date") or rec.get("date") or "")
        if d and week_key(d) == wk:
            return rec
    return None


def cross_week_filter(clusters: list[Cluster], covered: list[dict[str, Any]]) -> list[Cluster]:
    status_by_url = {c.get("canonical_url"): c.get("status") for c in covered}
    out: list[Cluster] = []
    for cl in clusters:
        url = canonical_url(cl["head"]["url"])
        status = status_by_url.get(url)
        if status is None or status in _ACTIVE_FOLLOWUP:
            out.append(cl)  # new, or a developing story worth re-reporting
    return out


def select_followups(covered: list[dict[str, Any]], window_weeks: int, now_iso: str) -> list[dict[str, Any]]:
    now = datetime.fromisoformat(now_iso)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = now - timedelta(weeks=window_weeks)
    out: list[dict[str, Any]] = []
    for c in covered:
        if c.get("status") not in _ACTIVE_FOLLOWUP:
            continue
        try:
            issued = datetime.fromisoformat(c["issue_date"])
            issued = issued.replace(tzinfo=timezone.utc) if issued.tzinfo is None else issued.astimezone(timezone.utc)
        except Exception:
            continue
        if issued >= cutoff:
            out.append(c)
    return out


def _is_blocked(domain: str, do_not_cite: list[str]) -> bool:
    """Check if domain is blocked by suffix matching."""
    d = domain.lower()
    return any(d == b.lower() or d.endswith("." + b.lower()) for b in do_not_cite)


# Community/aggregator domains: valid signal sources but never cited directly.
_AGGREGATOR_DOMAINS: list[str] = [
    "reddit.com",
    "news.ycombinator.com",
    "x.com",
    "twitter.com",
]

# Signal connectors: produce signal, never citeable digest heads (even if external domain).
_SIGNAL_CONNECTORS: set[str] = {"hackernews", "community"}


# Evergreen/how-to detection (2026-08-02 root cure). The Tier-B researcher
# prompt has always said "news EVENTS only … how-to guides are NOT digest
# material", but that rule had NO executor on the Tier-A (RSS/NewsAPI/GDELT)
# path — a Rule-6 violation through which "Why every SEO team now needs a
# social topical map" shipped as a news story in issue #5 (and near-identical
# picks in issues #3/#4). Patterns are deliberately HIGH-PRECISION anchored
# shapes: a news headline that merely contains "guide" mid-sentence survives.
_EVERGREEN_TITLE_RES: list[re.Pattern[str]] = [
    re.compile(r"^how\s+to\b", re.IGNORECASE),
    re.compile(r"^why\s+(you|your|every|we)\b", re.IGNORECASE),
    re.compile(r"^what\s+(is|are)\b", re.IGNORECASE),
    re.compile(r"^\d+\s+(ways|tips|steps|reasons|examples|best|mistakes)\b", re.IGNORECASE),
    re.compile(r"^(a|the)?\s*(ultimate|complete|definitive|essential|beginner'?s?)\s+guide\b", re.IGNORECASE),
    re.compile(r"\bstep-by-step\b", re.IGNORECASE),
]


def _is_evergreen_headline(headline: str) -> bool:
    return any(rx.search(headline or "") for rx in _EVERGREEN_TITLE_RES)


def evergreen_filter(clusters: list[Cluster]) -> tuple[list[Cluster], list[str]]:
    """Drop evergreen/how-to/guide clusters; return (kept, dropped_headlines).

    Dropped headlines are surfaced by the caller (no-silent-caps rule): they go
    into the runner's JSON result so the operator can see what was excluded and
    override by hand-curation if a drop was wrong.
    """
    kept: list[Cluster] = []
    dropped: list[str] = []
    for cl in clusters:
        headline = str(cl["head"].get("headline") or "")
        if _is_evergreen_headline(headline):
            dropped.append(headline)
        else:
            kept.append(cl)
    return kept, dropped


def finalize_issue(
    items_new: list[dict[str, Any]], followups: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], str]:
    """Assemble the final issue order and theme (2026-08-02 root cure).

    Fresh ranked items LEAD; follow-ups APPEND at the tail — they are brief
    updates on prior coverage (the template's late "Follow-ups" section), never
    the issue's headline story. Pre-cure, follow-ups were prepended and
    theme_of_week re-derived from items[0], so ANY surviving follow-up made
    last-month's story the theme/H1 — mathematically guaranteed, and exactly
    what shipped three issues running (#3/#4/#5).

    Theme = first ``kind == "new"`` item's headline; an all-follow-up issue
    falls back to the first follow-up so the theme is never "" (D2).
    """
    items = list(items_new) + list(followups)
    theme = ""
    if items:
        first_new = next((it for it in items if it.get("kind") == "new"), items[0])
        theme = str(first_new.get("headline") or "")
    return items, theme


def aggregator_filter(clusters: list[Cluster]) -> list[Cluster]:
    """Drop clusters where ALL members are aggregator/community domains or signal connectors.

    If some members are from citeable (non-aggregator, non-signal) sources, reassign head to
    the most-recent citeable member and keep only citeable members.  Aggregator
    clusters carry zero citation value — a reddit/HN-only story has no
    authoritative origin to cite.  Signal connectors (HN, community) are never
    citeable as digest heads even if they carry an external domain.
    """
    kept: list[Cluster] = []
    for cl in clusters:
        citeable = [
            m for m in cl["members"]
            if not _is_blocked(m["source_domain"], _AGGREGATOR_DOMAINS)
            and m.get("connector") not in _SIGNAL_CONNECTORS
        ]
        if not citeable:
            continue  # aggregator-only or signal-only cluster -> drop silently
        citeable_sorted = sorted(citeable, key=_published_dt, reverse=True)
        kept.append({
            **cl,
            "head": citeable_sorted[0],
            "members": citeable,
            "corroboration": len({m["source_domain"] for m in citeable}),
        })
    return kept


def competitor_filter(
    clusters: list[Cluster], do_not_cite: list[str]
) -> tuple[list[Cluster], list[str]]:
    """Drop clusters where ALL members are from blocked domains.

    If some members are clean, reassign head to most-recent clean member.
    Returns (kept_clusters, sorted(rejected_domains)).
    """
    if not do_not_cite:
        return clusters, []
    kept: list[Cluster] = []
    rejected: set[str] = set()
    for cl in clusters:
        clean = [m for m in cl["members"] if not _is_blocked(m["source_domain"], do_not_cite)]
        for m in cl["members"]:
            if _is_blocked(m["source_domain"], do_not_cite):
                rejected.add(m["source_domain"])
        if not clean:
            continue  # entire cluster is competitor-sourced -> drop
        # ROBUST: sort by _published_dt, not lambda m: m["published_at"]
        clean_sorted = sorted(clean, key=_published_dt, reverse=True)
        kept.append({**cl, "head": clean_sorted[0], "members": clean,
                     "corroboration": len({m["source_domain"] for m in clean})})
    return kept, sorted(rejected)


def _relevance(cl: Cluster, terms: list[str]) -> float:
    """Score project-term overlap in headline + summary (token-based).

    2026-08-02 root cure: the original whole-phrase substring match scored 0.0
    for EVERY real item whenever project terms are sentence-shaped (loamwright's
    ``content_strategy.primary_clusters`` are lines like "Generative Engine
    Optimization (GEO) — flagship differentiator"), while the no-terms fallback
    returned 0.5 — so a project that configured terms ranked every item strictly
    LOWER than one that configured none. Tokenizing both sides (via
    ``_story_tokens``, stopword-filtered) makes the 0.20 relevance weight a real
    signal instead of a constant 0.
    """
    if not terms:
        return 0.5
    text_tokens = _story_tokens(
        cl["head"]["headline"] + " " + cl["head"]["summary_raw"]
    )

    # Score each configured term INDEPENDENTLY and keep the best.
    #
    # Two things were wrong before, and the second is the deeper one.
    #
    # 1. The denominator was the UNION of every term's tokens, so adding a topic
    #    cluster to a project's config lowered the score of every item — a
    #    ranking signal that gets worse the more you tell it. Taking a max over
    #    per-term coverage is monotone by construction: a new cluster can only
    #    add a way to match.
    #
    # 2. A coverage FRACTION was being compared against the 0.5 constant returned
    #    for unconfigured projects. Those are different scales. Real cluster
    #    lines read "Generative Engine Optimization (GEO) — flagship
    #    differentiator", so a perfectly on-topic headline covers maybe a third of
    #    one term's tokens and still lands under 0.5. That is why the original
    #    pathology — configured projects ranking strictly below unconfigured ones
    #    — survived the 2026-08-02 "root cure" that only tokenized the inputs.
    #
    # So the configured path now spans the full range around the neutral point:
    #   nothing matched      -> 0.0   (definitely off-topic; worse than unknown)
    #   no terms configured  -> 0.5   (unknown)
    #   anything matched     -> 0.5..1.0 (never worse than unknown)
    # A match must be DISTINCTIVE, not incidental. Short terms are hypersensitive:
    # "Local SEO" is two tokens, so the single common English word "local" in
    # "Local bakery wins county pie contest" covers half of it and would score the
    # bakery story 0.75 — above the neutral baseline, on an SEO agency's digest.
    # A multi-token term therefore needs at least two overlapping tokens. This is
    # the same failure and the same cure as the CTA category matcher, where a
    # one-token category scored a perfect 1.0 off one incidental article word.
    # 2026-08-12 note — this SCORER is correct; the bug was in what it is FED.
    #
    # The >=2-overlap rule below is a real safety property: a single common word
    # ("local" in "Local bakery wins county pie contest") must not match the
    # service line "Local SEO". Two tests pin it, in both directions.
    #
    # What was broken is the TERM SOURCE. The runner fed
    # `content_strategy.primary_clusters` — a project's SERVICE-LINE labels
    # ("Technical SEO", "Local SEO", "Enterprise SEO") — into a NEWS-relevance
    # scorer. Those describe what the agency SELLS, not the vocabulary its
    # industry news is written in, so real headlines ("Search Console's
    # generative AI report goes live", "Stack Overflow questions down 99%")
    # share at most one incidental token with them. Measured on the seven
    # hand-curated, unambiguously on-topic items of the 2026-08-12 loamwright
    # issue: 6 of 7 scored 0.0 — the "worse than unknown" verdict — which is why
    # the ranker has needed full hand-curation for five consecutive issues.
    #
    # The cure is `_digest_relevance_terms()`: prefer a project's
    # `weekly_digest.relevance_terms` (news vocabulary, project level, where
    # topic vocabulary belongs) and fall back to primary_clusters only when a
    # project has not supplied one. Tuning the arithmetic here instead would
    # have traded a false-negative for a false-positive and broken the guard.
    best_coverage = 0.0
    usable = 0
    for t in terms:
        tt = _story_tokens(t)
        if not tt:
            continue
        usable += 1
        overlap = len(tt & text_tokens)
        if len(tt) > 1 and overlap < 2:
            continue
        best_coverage = max(best_coverage, overlap / len(tt))
    if not usable:
        return 0.5
    if best_coverage <= 0.0:
        return 0.0
    return min(1.0, 0.5 + 0.5 * best_coverage)


def _digest_relevance_terms(bc: dict[str, Any]) -> list[str]:
    """Resolve the term list the digest ranker scores relevance against.

    Prefers ``weekly_digest.relevance_terms`` — short NEWS-topic phrases in the
    vocabulary the industry actually writes in ("AI Overviews", "algorithm
    update", "Search Console"). Falls back to ``content_strategy.primary_clusters``
    so projects that have not supplied one keep their previous behaviour.

    Why this exists: primary_clusters are SERVICE-LINE labels. Scoring news
    against them is a category error that made 6 of 7 genuinely on-topic items
    score 0.0 on the 2026-08-12 issue. Term vocabulary is a per-project fact, so
    it lives in project config; the skill only decides which field to read.
    """
    wd = bc.get("weekly_digest") or {}
    terms = wd.get("relevance_terms")
    if isinstance(terms, list) and any(str(t).strip() for t in terms):
        return [str(t) for t in terms if str(t).strip()]
    return (bc.get("content_strategy") or {}).get("primary_clusters") or []


def rank_clusters(
    clusters: list[Cluster],
    *,
    now_iso: str,
    project_terms: list[str],
    authority_domains: list[str] | None = None,
) -> list[Cluster]:
    """Write significance score and return clusters sorted descending.

    Significance = 0.30*recency + 0.25*corroboration_norm + 0.20*relevance
                 + 0.15*authority + 0.10*raw_score_norm

    authority is 1.0 when the head's source_domain matches any entry in
    authority_domains (suffix match via _is_blocked), else 0.5.  When
    authority_domains is None or empty, authority is 0.5 for all clusters
    (neutral, backward-compatible).
    """
    # ROBUST: guard now with timezone safeguards
    now = datetime.fromisoformat(now_iso)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    max_corr = max((c["corroboration"] for c in clusters), default=1) or 1
    max_raw = max((abs(c["head"].get("raw_score") or 0.0) for c in clusters), default=0.0)

    for c in clusters:
        # ROBUST: compute recency from _published_dt, not parse string directly
        age_days = max(0.0, (now - _published_dt(c["head"])).total_seconds() / 86400.0)
        recency = max(0.0, 1.0 - age_days / 7.0)

        corr = c["corroboration"] / max_corr
        rel = _relevance(c, project_terms)
        raw = (abs(c["head"].get("raw_score") or 0.0) / max_raw) if max_raw else 0.0
        head_domain: str = c["head"].get("source_domain", "")
        authority = (
            1.0 if (authority_domains and _is_blocked(head_domain, authority_domains)) else 0.5
        )
        c["significance"] = round(
            0.30 * recency + 0.25 * corr + 0.20 * rel + 0.15 * authority + 0.10 * raw, 4
        )

    return sorted(clusters, key=lambda c: c["significance"], reverse=True)


def build_digest(
    clusters: list[Cluster],
    *,
    project_slug: str,
    series_keyword: str,
    lookback_days: int,
    now_iso: str,
    rejected: list[str],
    connectors_run: list[dict[str, Any]],
    items_per_issue: int,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for cl in clusters[:items_per_issue]:
        head = cl["head"]
        seen_domains = {head["source_domain"]}
        corroborating: list[dict[str, str]] = []
        for m in cl["members"]:
            if m["source_domain"] in seen_domains:
                continue
            seen_domains.add(m["source_domain"])
            corroborating.append({"name": m["source_name"], "url": m["url"]})
        items.append(
            {
                "cluster_id": cl["cluster_id"],
                "kind": "new",
                "headline": head["headline"],
                "canonical_source": {
                    "name": head["source_name"],
                    "url": head["url"],
                    "domain": head["source_domain"],
                },
                "corroborating_sources": corroborating,
                "published_at": head["published_at"],
                "summary": head["summary_raw"],
                "suggested_angle": "",
                "significance": cl.get("significance", 0.0),
                "entities": head.get("entities", []),
                "topic_tags": head.get("topic_tags", []),
                "enrichment": None,
                "follow_up_of": None,
            }
        )
    theme = items[0]["headline"] if items else ""
    return {
        "generated_at": now_iso,
        "project_slug": project_slug,
        "lookback_days": lookback_days,
        "series_keyword": series_keyword,
        "theme_of_week": theme,
        "items": items,
        "rejected_competitor_domains": rejected,
        "connectors_run": connectors_run,
    }


def _connector_on(conns: dict[str, Any], name: str) -> bool:
    """Check if a connector is present, non-null, a dict, and not explicitly disabled."""
    cfg = conns.get(name)
    return isinstance(cfg, dict) and bool(cfg.get("enabled", True))


def _authority_domains_from_config(cfg: dict[str, Any]) -> list[str]:
    """Derive authority domains from project weekly_digest config (RSS feeds + NewsAPI domains + explicit override).

    Returns sorted list of hostnames. Extracts hostnames from RSS feed URLs (with www. prefix stripped),
    adds any configured newsapi.domains, and includes any explicit authority_domains override from config.
    No built-in vertical-specific domains — authority is project-derived only.
    """
    doms: set[str] = set()
    conns = cfg.get("connectors") or {}

    # RSS feed hostnames
    rss_cfg = conns.get("rss")
    if isinstance(rss_cfg, dict):
        feeds = rss_cfg.get("feeds") or []
        for feed_url in feeds:
            try:
                netloc = urlparse(str(feed_url)).netloc.lower()
                if netloc.startswith("www."):
                    netloc = netloc[4:]
                if netloc:
                    doms.add(netloc)
            except Exception:
                pass

    # NewsAPI domains
    newsapi_cfg = conns.get("newsapi")
    if isinstance(newsapi_cfg, dict):
        newsapi_doms = newsapi_cfg.get("domains") or []
        for d in newsapi_doms:
            if d:
                doms.add(str(d).lower().strip())

    # Optional explicit project override
    for d in cfg.get("authority_domains") or []:
        if d:
            doms.add(str(d).lower().strip())

    return sorted(doms)


# ---------------------------------------------------------------------------
# Plan 2 — new helpers
# ---------------------------------------------------------------------------

def _load_extra_items(path: str | None) -> list[NewsItem]:
    """Load Tier-B NewsItems from a JSON file path.

    Accepts a bare list or ``{items: [...]}`` envelope.  Tolerates missing or
    malformed files and entries — never raises.
    """
    if not path:
        return []
    try:
        p = Path(path)
        if not p.exists():
            return []
        raw: Any = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            entries: list[Any] = raw
        elif isinstance(raw, dict):
            entries = list(raw.get("items") or [])
        else:
            return []
        items: list[NewsItem] = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            url: str = str(e.get("url") or "").strip()
            headline: str = str(e.get("headline") or "").strip()
            if not url or not headline:
                continue
            try:
                rs: float | None = None
                raw_rs = e.get("raw_score")
                if raw_rs is not None:
                    rs = float(raw_rs)
                items.append(
                    make_item(
                        headline=headline,
                        url=url,
                        source_name=str(e.get("source_name") or domain_of(url) or "unknown"),
                        published_at=str(
                            e.get("published_at") or datetime.now(timezone.utc).isoformat()
                        ),
                        summary_raw=str(e.get("summary_raw") or ""),
                        connector=str(e.get("connector") or "extra"),
                        raw_score=rs,
                        entities=list(e.get("entities") or []),
                        topic_tags=list(e.get("topic_tags") or []),
                    )
                )
            except Exception:
                continue
        return items
    except Exception:
        return []


def _emit_followups(
    covered: list[dict[str, Any]],
    window_weeks: int,
    now_iso: str,
) -> list[dict[str, Any]]:
    """Shape active watch-list items into follow-up digest-item dicts.

    Does NOT re-query for new developments — that is the researcher's job.
    Returns items with ``kind="follow_up"`` that ``finalize_issue`` APPENDS
    after the fresh items (2026-08-02) so the writer frames them as brief
    "continuing story" updates at the tail of the issue.
    """
    active = select_followups(covered, window_weeks, now_iso)
    items: list[dict[str, Any]] = []
    for c in active:
        cid: str = str(c.get("cluster_id") or "")
        url: str = str(c.get("canonical_url") or "")
        d: str = domain_of(url) if url else ""
        name: str = str(c.get("source_name") or d or "unknown")
        raw_date: str = str(c.get("issue_date") or now_iso[:10])
        # Ensure we always emit a valid ISO timestamp
        published_at = raw_date + "T00:00:00+00:00" if len(raw_date) == 10 else raw_date
        items.append(
            {
                "cluster_id": f"fu_{cid}" if cid else "fu_unknown",
                "kind": "follow_up",
                "follow_up_of": cid if cid else None,
                "headline": str(c.get("headline") or ""),
                "canonical_source": {
                    "name": name,
                    "url": url,
                    "domain": d,
                },
                "corroborating_sources": [],
                "published_at": published_at,
                "summary": "Follow-up on last week's developing story.",
                "suggested_angle": "",
                "significance": 0.5,
                "entities": list(c.get("entities") or []),
                "topic_tags": list(c.get("topic_tags") or []),
                "enrichment": None,
            }
        )
    return items


def _load_covered(slug: str) -> list[dict[str, Any]]:
    """Read ``projects/{slug}/weekly/covered.json``; returns [] on any error."""
    path = PLUGIN_ROOT / "projects" / slug / "weekly" / "covered.json"
    try:
        if not path.exists():
            return []
        data: Any = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_covered(slug: str, entries: list[dict[str, Any]]) -> None:
    """Atomically write covered.json under a cross-process lock (Rule 7)."""
    path = PLUGIN_ROOT / "projects" / slug / "weekly" / "covered.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path):
        atomic_write_text(path, json.dumps(entries, ensure_ascii=False, indent=2))


def _update_covered(
    slug: str, mutate: "Callable[[list[dict[str, Any]]], list[dict[str, Any]]]"
) -> None:
    """Race-safe read-modify-write of covered.json (Rule 7, D3).

    Reads the on-disk list INSIDE the lock, passes it to ``mutate`` (which
    returns the new list), then atomically replaces the file — so two concurrent
    runs for the SAME project (e.g. a scheduled run overlapping a manual one)
    cannot lose each other's update.
    """
    path = PLUGIN_ROOT / "projects" / slug / "weekly" / "covered.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path):
        existing: list[dict[str, Any]] = []
        if path.exists():
            try:
                data: Any = json.loads(path.read_text(encoding="utf-8"))
                existing = data if isinstance(data, list) else []
            except Exception:
                existing = []
        new_list = mutate(existing)
        atomic_write_text(path, json.dumps(new_list, ensure_ascii=False, indent=2))


def build_covered_update(
    existing: list[dict[str, Any]],
    published_clusters: list[Cluster],
    *,
    today: str,
) -> list[dict[str, Any]]:
    """Merge the ACTUALLY-PUBLISHED clusters into the covered ledger (D1/D2).

    Only clusters in ``published_clusters`` are recorded — passing
    ``ranked[:keep]`` (the items that survived follow-up truncation) is what
    prevents the D1 data-loss bug where ranked-but-unpublished clusters were
    recorded as "reported" and then suppressed forever.

    A published cluster whose canonical URL already exists in the ledger is
    PROMOTED in place (status -> "reported", issue_date -> today) rather than
    duplicated — so a developing story that recurs is closed out, not re-listed
    week after week (D2).
    """
    by_url: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for c in existing:
        u = str(c.get("canonical_url") or "")
        by_url[u] = dict(c)
        order.append(u)
    for cl in published_clusters:
        head = cl["head"]
        curl = canonical_url(head["url"])
        if curl in by_url:
            by_url[curl]["status"] = "reported"
            by_url[curl]["issue_date"] = today
        else:
            by_url[curl] = {
                "cluster_id": cl.get("cluster_id", ""),
                "canonical_url": curl,
                "headline": head.get("headline", ""),
                "source_name": head.get("source_name", ""),
                "status": "reported",
                "issue_date": today,
            }
            order.append(curl)
    return [by_url[u] for u in order]


def dedup_followups(
    followups: list[dict[str, Any]], exclude_urls: set[str]
) -> list[dict[str, Any]]:
    """Drop follow-ups whose story also appears in this week's fresh harvest (D2).

    Compares both the raw and canonicalised follow-up URL against ``exclude_urls``
    so a story present in ``ranked`` is reported as a fresh "new" item (with real
    new content) instead of duplicated as a stale "continuing story".
    """
    out: list[dict[str, Any]] = []
    for f in followups:
        url = str((f.get("canonical_source") or {}).get("url") or "")
        if url in exclude_urls or canonical_url(url) in exclude_urls:
            continue
        out.append(f)
    return out


#: Default ceiling on how many of an issue's slots continuing stories may take.
#: Overridable per project via ``weekly_digest.max_followups_per_issue``.
DEFAULT_MAX_FOLLOWUPS_PER_ISSUE = 2


def close_published_followups(
    rows: list[dict[str, Any]],
    published_followups: list[dict[str, Any]],
    *,
    today: str,
) -> list[dict[str, Any]]:
    """Mark every follow-up ACTUALLY published this issue as ``reported``.

    2026-08-12 root cure. ``build_covered_update`` records only the FRESH
    clusters (the D1 fix), so a story published as a *continuing story* kept
    ``status: "developing"`` and was re-emitted by ``_emit_followups`` every
    week until ``expire_and_prune_covered`` aged it out at
    ``follow_up_window_weeks``. Measured on the live loamwright ledger: the same
    three entries were emitted on 08-06 AND 08-12 and would have been emitted a
    third time on 08-19 — each carrying an empty summary and a hardcoded 0.5
    significance, displacing real reporting three weeks running.

    A story that has now been told is reported, not developing. Genuinely new
    developments re-enter through ``resolve_recurrences`` on a fresh URL, which
    is the correct door.
    """
    if not published_followups:
        return rows
    closed: set[str] = set()
    for fu in published_followups:
        # Follow-up ITEMS (from _emit_followups) carry canonical_source.url —
        # they are digest-item-shaped, NOT cluster-shaped; there is no "head".
        # v3.42.13: the first version of this function read fu["head"]["url"],
        # which is the CLUSTER shape, so `closed` was always empty and the whole
        # close was a silent production no-op while its test passed against a
        # hand-built fixture using the imagined shape. dedup_followups(), five
        # lines up, had been reading the correct key all along. The regression
        # test now drives _emit_followups() itself so this shape can never
        # drift from the producer again (fixtures prove shape, production
        # proves contract).
        url = str((fu.get("canonical_source") or {}).get("url") or "")
        if url:
            closed.add(canonical_url(url))
    if not closed:
        return rows
    out: list[dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        if str(row.get("canonical_url") or "") in closed:
            row["status"] = "reported"
            row["issue_date"] = today
        out.append(row)
    return out


def resolve_issue_budget(
    ranked: list[Cluster],
    raw_followups: list[dict[str, Any]],
    items_per_issue: int,
    max_followups: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Resolve the follow-up / fresh-item budget for one issue (Bug-1 / D2 fix).

    A developing story can recur in this week's fresh harvest. It must appear
    EXACTLY ONCE — promoted to a fresh "new" item when it makes the publish cut,
    otherwise kept as a "continuing story" follow-up — and must NEVER be silently
    dropped. The 2026-06-30 audit's dedup excluded follow-ups against *all* of
    ``ranked`` while only ``ranked[:keep]`` was actually published, so a recurring
    story sitting in ``ranked[keep:]`` was removed from the follow-ups yet never
    published and never promoted: it vanished from the digest entirely.

    The fix is a fixpoint, because the two quantities are mutually dependent:
    the number of fresh slots (``keep``) depends on how many follow-ups survive,
    and follow-up survival depends on which fresh items are actually published.
    Dropping a follow-up that duplicates a PUBLISHED fresh item frees a slot,
    which can only ADD fresh items, which can only drop MORE duplicate follow-ups
    — a monotone iteration that converges in <= ``len(raw_followups)`` steps.

    Follow-ups are counted against ``items_per_issue`` so the issue can never
    overflow the per-issue cap (D2 overflow fix); ``finalize_issue`` appends
    them after the fresh items (2026-08-02).

    Returns ``(followups, keep)`` where ``keep`` is the number of leading
    ``ranked`` clusters to publish as fresh items; the caller publishes
    ``ranked[:keep]`` and records exactly that set into ``covered`` (D1).
    """
    cap = max(0, items_per_issue)
    # Follow-ups are continuing stories; cap them so they alone cannot overflow
    # the issue. Anything trimmed here stays "developing" in covered and is
    # eligible again next week — deferred, not lost.
    #
    # 2026-08-12 root cure. Until now the only ceiling was `items_per_issue`
    # itself, so continuing stories got FIRST CLAIM on the entire issue budget
    # and were never ranked against a single fresh item (`_emit_followups`
    # hardcodes significance 0.5 and an empty summary). Measured on the
    # 2026-08-12 loamwright issue: 3 stale entries took 3 of 7 slots, carrying
    # no new reporting, and — because a published follow-up was never marked
    # reported — the SAME three would have taken 3 slots again on 08-19 and
    # 08-26. At `items_per_issue` follow-ups an issue could contain zero fresh
    # news while still reporting success, which also opens the `keep == 0` hole
    # that lets `finalize_issue` hand `theme_of_week` to a follow-up despite
    # both SKILL layers promising it cannot.
    fu_cap = (
        DEFAULT_MAX_FOLLOWUPS_PER_ISSUE
        if max_followups is None
        else max(0, int(max_followups))
    )
    # Always leave at least one slot for fresh reporting: a "news digest" whose
    # every item is a recycled stub is not a news digest.
    fu_cap = min(fu_cap, max(0, cap - 1))
    followups = list(raw_followups)[:fu_cap]
    while True:
        keep = max(0, cap - len(followups))
        published_urls = {canonical_url(c["head"]["url"]) for c in ranked[:keep]}
        deduped = dedup_followups(followups, published_urls)
        if len(deduped) == len(followups):
            break
        followups = deduped
    keep = max(0, cap - len(followups))
    return followups, keep


def _append_issue(slug: str, issue: dict[str, Any]) -> None:
    """Upsert an issue stub into ``projects/{slug}/weekly/issues.json`` under a lock.

    Idempotent by ``task_id`` (H7): re-running the same task (e.g. a mid-pipeline
    crash + retry) updates the existing row in place instead of appending a
    duplicate. Written atomically (Rule 7).
    """
    path = PLUGIN_ROOT / "projects" / slug / "weekly" / "issues.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path):
        existing: list[dict[str, Any]] = []
        if path.exists():
            try:
                data: Any = json.loads(path.read_text(encoding="utf-8"))
                existing = data if isinstance(data, list) else []
            except Exception:
                existing = []
        tid = str(issue.get("task_id") or "")
        for i, e in enumerate(existing):
            if tid and str(e.get("task_id") or "") == tid:
                existing[i] = {**e, **issue}
                break
        else:
            existing.append(issue)
        atomic_write_text(path, json.dumps(existing, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Tier-A connector runner
# ---------------------------------------------------------------------------

def _record_into(
    items: list[NewsItem],
    run: list[dict[str, Any]],
    name: str,
    got: list[NewsItem],
    *,
    errored: bool = False,
    skipped: bool = False,
) -> None:
    """Append a connector's items + a run-record with a TRUTHFUL status (D4).

    status is one of: "error" (connector raised), "skipped" (intentionally not
    run), "ok" (returned items), "degraded" (ran but returned zero). "error" and
    "degraded" are kept distinct so a crash is never mistaken for an empty result.
    """
    items.extend(got)
    if errored:
        status = "error"
    elif skipped:
        status = "skipped"
    else:
        status = "ok" if got else "degraded"
    run.append({"name": name, "hits": len(got), "status": status})


def _run_connector(
    name: str, fn: Callable[[], list[NewsItem]]
) -> tuple[list[NewsItem], bool]:
    """Run a connector callable, LOGGING any exception (never swallow — D4).

    Returns ``(items, errored)``. A raising connector is logged to stderr and
    reported as errored so the runner continues with the other connectors
    instead of crashing (Tier-A parity) or silently degrading.
    """
    try:
        return fn(), False
    except Exception as e:  # noqa: BLE001 — log + continue, do not swallow
        print(
            f"⚠ digest connector '{name}' failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return [], True


def _run_tier_a(
    cfg: dict[str, Any], lookback_days: int
) -> tuple[list[NewsItem], list[dict[str, Any]]]:
    conns: dict[str, Any] = cfg.get("connectors", {})
    items: list[NewsItem] = []
    run: list[dict[str, Any]] = []

    def _record(name: str, got: list[NewsItem], *, errored: bool = False, skipped: bool = False) -> None:
        _record_into(items, run, name, got, errored=errored, skipped=skipped)

    # Import the first-party connector modules defensively: a single bad import
    # (e.g. a syntax/import error introduced in one fetch module) must NOT crash
    # the whole runner and take down every other connector. This extends D4's
    # per-connector-CALL continue-on-failure guarantee to the shared module
    # IMPORT, which the 2026-06-30 audit left unwrapped (D3 gap).
    try:
        from scripts.fetch import gdelt_query, hackernews_search, newsapi_query, rss_fetch
    except Exception as e:  # noqa: BLE001 — log + degrade, never crash the runner
        print(
            f"⚠ digest Tier-A connector modules failed to import: "
            f"{type(e).__name__}: {e}",
            file=sys.stderr,
        )
        for _cname in ("rss", "hackernews", "newsapi", "gdelt"):
            if _connector_on(conns, _cname):
                _record(_cname, [], errored=True)
        return items, run

    if _connector_on(conns, "rss"):
        got, err = _run_connector(
            "rss", lambda: rss_fetch.fetch(conns["rss"].get("feeds", []), lookback_days)
        )
        _record("rss", got, errored=err)
    if _connector_on(conns, "hackernews"):
        got, err = _run_connector(
            "hackernews",
            lambda: hackernews_search.fetch(conns["hackernews"].get("query", ""), lookback_days),
        )
        _record("hackernews", got, errored=err)
    if _connector_on(conns, "gdelt"):
        got, err = _run_connector(
            "gdelt", lambda: gdelt_query.fetch(conns["gdelt"].get("queries", []), lookback_days)
        )
        _record("gdelt", got, errored=err)
    if _connector_on(conns, "newsapi"):
        na: dict[str, Any] = conns["newsapi"]
        if not na.get("domains"):
            _record("newsapi", [], skipped=True)
        else:
            # ALL configured queries run (2026-07-01) — previously only queries[0]
            # was used and every other configured query was silently ignored.
            # Duplicate hits across queries collapse downstream in cluster_items
            # (URL-keyed dedup).
            queries: list[str] = [str(q) for q in (na.get("queries") or ["news"]) if str(q).strip()]
            all_got: list[NewsItem] = []
            any_err = False
            for q in queries:
                got, err = _run_connector(
                    "newsapi", lambda q=q: newsapi_query.fetch(q, na["domains"], lookback_days)
                )
                all_got.extend(got)
                any_err = any_err or err
            _record("newsapi", all_got, errored=any_err)

    # ------------------------------------------------------------------
    # Community connector (reddit / x via Tavily include_domains)
    # ------------------------------------------------------------------
    if _connector_on(conns, "community"):
        try:
            from scripts.fetch.community_search import search_community  # local import

            comm_cfg: dict[str, Any] = conns["community"]
            comm_query: str = str(comm_cfg.get("query") or "")
            if not comm_query:
                _record("community", [], skipped=True)
            else:
                comm_max: int = int(comm_cfg.get("max_results") or 8)
                comm_now: str = datetime.now(timezone.utc).isoformat()
                _sources_val = comm_cfg.get("sources")
                sources_raw: list[Any] = _sources_val if isinstance(_sources_val, list) else ["reddit"]
                comm_items: list[NewsItem] = []
                for src_raw in sources_raw:
                    src_str = str(src_raw)
                    if src_str == "reddit":
                        resp = search_community(
                            comm_query, source="reddit", max_results=comm_max, task_id=None
                        )
                    elif src_str == "x":
                        resp = search_community(
                            comm_query, source="x", max_results=comm_max, task_id=None
                        )
                    else:
                        continue
                    for post in resp.posts:
                        if not post.url or not post.title:
                            continue
                        comm_items.append(
                            make_item(
                                headline=post.title,
                                url=post.url,
                                source_name=post.source,
                                published_at=post.published_date or comm_now,
                                summary_raw=(post.content or "")[:500],
                                connector="community",
                                raw_score=float(post.score) if post.score else None,
                            )
                        )
                _record("community", comm_items)
        except Exception as e:  # noqa: BLE001 — log + continue, do not swallow (D4)
            print(
                f"⚠ digest connector 'community' failed: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            _record("community", [], errored=True)

    # ------------------------------------------------------------------
    # Tavily news connector (topic="news")
    # ------------------------------------------------------------------
    if _connector_on(conns, "tavily_news"):
        try:
            from scripts.fetch import tavily_search as _ts  # local import

            tn_cfg: dict[str, Any] = conns["tavily_news"]
            tn_query: str = str(tn_cfg.get("query") or "")
            if not tn_query:
                _record("tavily_news", [], skipped=True)
            else:
                tn_max: int = int(tn_cfg.get("max_results") or 10)
                tn_time_range: str = "week" if lookback_days <= 7 else "month"
                tn_now: str = datetime.now(timezone.utc).isoformat()
                tn_resp = _ts.search(
                    tn_query,
                    topic="news",
                    depth="basic",
                    max_results=tn_max,
                    time_range=tn_time_range,
                    use_cache=True,
                )
                tn_items: list[NewsItem] = []
                for r in tn_resp.results:
                    if not r.url or not r.title:
                        continue
                    tn_items.append(
                        make_item(
                            headline=r.title,
                            url=r.url,
                            source_name=domain_of(r.url) or r.title[:50],
                            published_at=r.published_date or tn_now,
                            summary_raw=(r.content or "")[:500],
                            connector="tavily_news",
                            raw_score=r.score,
                        )
                    )
                _record("tavily_news", tn_items)
        except Exception as e:  # noqa: BLE001 — log + continue, do not swallow (D4)
            print(
                f"⚠ digest connector 'tavily_news' failed: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            _record("tavily_news", [], errored=True)

    return items, run


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--lookback-days", type=int, default=None)
    ap.add_argument("--window-weeks", type=int, default=None)
    ap.add_argument("--extra-items", default=None, help="Path to Tier-B NewsItem JSON file")
    ap.add_argument("--force", action="store_true",
                    help="Run even if an issue already exists for the current ISO week.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    slug: str = args.project

    bc_path = PLUGIN_ROOT / "projects" / slug / "business-context.json"
    bc: dict[str, Any] = json.loads(bc_path.read_text(encoding="utf-8"))
    cfg: dict[str, Any] = bc.get("weekly_digest", {})
    if not cfg.get("enabled"):
        print(json.dumps({"error": "weekly_digest not enabled for project", "project": slug}))
        sys.exit(2)

    lookback: int = (
        args.lookback_days
        if args.lookback_days is not None
        else int(cfg.get("lookback_days") or 7)
    )
    window: int = (
        args.window_weeks
        if args.window_weeks is not None
        else int(cfg.get("follow_up_window_weeks") or 4)
    )
    industry: str = str(bc.get("industry") or "industry")
    series_kw: str = str(cfg.get("series_keyword") or f"{industry} news this week")
    now_iso: str = datetime.now(timezone.utc).isoformat()
    today: str = now_iso[:10]

    # --- Week-level idempotency guard (2026-07-01) ---
    # Task ids are DATE-stamped, so a second run in the same ISO week used to
    # silently produce a second draft + issues row + hub row. Refuse unless --force.
    issues_path = PLUGIN_ROOT / "projects" / slug / "weekly" / "issues.json"
    if issues_path.exists() and not args.force:
        try:
            existing_issues: list[dict[str, Any]] = json.loads(
                issues_path.read_text(encoding="utf-8")
            )
        except Exception:
            existing_issues = []
        dup = find_issue_in_week(existing_issues, today)
        if dup is not None:
            print(json.dumps({
                "error": "issue already exists for this ISO week",
                "week": week_key(today),
                "existing_task_id": dup.get("task_id"),
                "existing_issue_date": dup.get("issue_date") or dup.get("date"),
                "hint": "pass --force to intentionally publish a second issue this week",
            }, ensure_ascii=False))
            sys.exit(3)

    # --- Tier-A fetch + Tier-B merge ---
    tier_a_items, connectors_run = _run_tier_a(cfg, lookback)
    extra_items = _load_extra_items(args.extra_items)
    all_items: list[NewsItem] = tier_a_items + extra_items

    # --- Cluster, cross-week filter, competitor filter, rank ---
    clusters = cluster_items(all_items)
    covered: list[dict[str, Any]] = _load_covered(slug)

    # Auto-mark recurring stories "developing" (2026-07-01) — the entry edge the
    # follow-up state machine never had. Persist race-safely, then use the updated
    # ledger for cross_week_filter + follow-up selection below.
    covered, promoted = resolve_recurrences(
        covered, clusters, window_weeks=window, today=today
    )
    if promoted:
        try:
            _update_covered(
                slug,
                lambda existing: resolve_recurrences(
                    existing, clusters, window_weeks=window, today=today
                )[0],
            )
        except Exception:
            pass  # non-fatal; in-memory ledger still drives this run
        print(f"↺ {len(promoted)} recurring stor{'y' if len(promoted)==1 else 'ies'} "
              f"auto-marked developing", file=sys.stderr)

    clusters = cross_week_filter(clusters, covered)
    kept, rejected = competitor_filter(
        clusters, bc.get("citation_source_policy", {}).get("do_not_cite_domains", [])
    )
    kept = aggregator_filter(kept)
    # News EVENTS only (2026-08-02): the Tier-B researcher prompt's rule now
    # has a Tier-A executor. Drops are surfaced in the JSON result, not silent.
    kept, evergreen_dropped = evergreen_filter(kept)
    if evergreen_dropped:
        print(
            f"⤫ evergreen filter dropped {len(evergreen_dropped)}: "
            + "; ".join(evergreen_dropped[:5]),
            file=sys.stderr,
        )

    # Build authority_domains: project-derived from config (RSS feeds + NewsAPI domains + explicit override)
    authority_domains = _authority_domains_from_config(cfg)

    ranked = rank_clusters(
        kept,
        now_iso=now_iso,
        project_terms=_digest_relevance_terms(bc),
        authority_domains=authority_domains,
    )

    # --- Build digest (new items) then prepend follow-ups ---
    items_per_issue: int = int(cfg.get("items_per_issue") or 7)
    doc: dict[str, Any] = build_digest(
        ranked,
        project_slug=slug,
        series_keyword=series_kw,
        lookback_days=lookback,
        now_iso=now_iso,
        rejected=rejected,
        connectors_run=connectors_run,
        items_per_issue=items_per_issue,
    )
    # Follow-ups vs fresh items: resolve the per-issue budget to a fixpoint so a
    # recurring developing story is shown exactly once — promoted to a fresh item
    # when it makes the cut, else kept as a follow-up — and NEVER silently dropped
    # (Bug 1). The dedup excludes against what is ACTUALLY published (ranked[:keep]),
    # not all of `ranked`. Follow-ups are counted against items_per_issue (D2 cap).
    followups, keep = resolve_issue_budget(
        ranked,
        _emit_followups(covered, window, now_iso),
        items_per_issue,
        max_followups=(
            None
            if cfg.get("max_followups_per_issue") is None
            else int(cfg["max_followups_per_issue"])
        ),
    )
    # Fresh items lead, follow-ups trail, theme = top FRESH story (2026-08-02
    # root cure — pre-cure prepend+items[0] made a stale follow-up the theme/H1
    # whenever one survived; shipped 3 consecutive issues).
    doc["items"], _theme = finalize_issue(doc["items"][:keep], followups)
    if _theme:
        doc["theme_of_week"] = _theme

    # The clusters ACTUALLY published as new this issue (after follow-up truncation).
    # Recording covered from THIS set — not ranked[:items_per_issue] — is the D1 fix.
    published_new: list[Cluster] = ranked[:keep]

    # --- Write news-digest.json ---
    out_path = PLUGIN_ROOT / "memory" / "workspace" / args.task_id / "news-digest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- Update covered.json: race-safe locked RMW (D3); record only what was
    #     published (D1); promote re-reported developing stories (D2). ---
    retention_weeks: int = int(cfg.get("covered_retention_weeks") or 12)
    try:
        _update_covered(
            slug,
            lambda existing: expire_and_prune_covered(
                close_published_followups(
                    build_covered_update(existing, published_new, today=today),
                    followups,
                    today=today,
                ),
                window_weeks=window,
                retention_weeks=retention_weeks,
                today=today,
            ),
        )
    except Exception:
        pass  # non-fatal: digest was written; state update fails gracefully

    # --- Append issue stub ---
    try:
        _append_issue(
            slug,
            {
                "date": today,
                "task_id": args.task_id,
                "item_count": len(doc["items"]),
            },
        )
    except Exception:
        pass  # non-fatal

    print(
        json.dumps(
            {
                "ok": True,
                "items": len(doc["items"]),
                "follow_ups": len(followups),
                "evergreen_dropped": evergreen_dropped,
                "connectors_run": connectors_run,
                "out": str(out_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
