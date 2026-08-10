"""
scripts/openai/real_photo_sourcer.py — source a REAL product photo of a real brand.

For project-echo (age-restricted product brands are the SUBJECT, not competitors), article product images
must be real photographs of the real brand. This module finds the best real-product
still-life from web image search (Tavily + Brave, independent quotas) and optionally a
product page (Firecrawl), then the editor re-scenes it while preserving the real pack.

This file separates PURE, unit-tested logic (query building, result-shape normalization,
candidate scoring/selection) from thin network wrappers (validated by live --smoke runs).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ─── Candidate model + pure logic (unit-tested) ────────────────────────────────


@dataclass(frozen=True)
class Candidate:
    """One image-search hit, normalized across providers."""
    url: str
    description: str
    width: int | None
    height: int | None
    source: str  # "tavily" | "brave" | "firecrawl"


def build_search_queries(
    brand: str,
    purpose: str = "",
    *,
    product_noun: str = "product",
    search_terms: tuple[str, ...] = (),
) -> list[str]:
    """Build a few query variants biased toward a real product still-life.

    Domain-neutral by default. A project supplies ``product_noun`` (e.g. "age-restricted product pack")
    and/or explicit ``search_terms`` templates (each may contain "{brand}") so this stays
    free of any one vertical's wording.
    """
    b = brand.strip()
    if search_terms:
        qs = [t.format(brand=b) if "{brand}" in t else f"{b} {t}" for t in search_terms]
    else:
        noun = product_noun.strip() or "product"
        qs = [
            f"{b} {noun} product photo",
            f"{b} {noun} official product packaging",
            f"buy {b} {noun}",
        ]
    if purpose.strip():
        qs.append(f"{b} {purpose.strip()}")
    seen: set[str] = set()
    out: list[str] = []
    for q in qs:
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out


def candidate_from_tavily(item: Any) -> Candidate:
    """Normalize a Tavily image result (a URL string, or {url, description})."""
    if isinstance(item, str):
        return Candidate(url=item, description="", width=None, height=None, source="tavily")
    if not isinstance(item, dict):
        return Candidate(url="", description="", width=None, height=None, source="tavily")
    return Candidate(
        url=str(item.get("url", "") or ""),
        description=str(item.get("description") or ""),
        width=item.get("width"),
        height=item.get("height"),
        source="tavily",
    )


def candidate_from_brave(item: dict[str, Any]) -> Candidate:
    """Normalize a Brave image result — the IMAGE url lives in properties.url."""
    props = item.get("properties") or {}
    if not isinstance(props, dict):
        props = {}
    url = props.get("url") or item.get("url") or ""
    desc = item.get("title") or props.get("description") or ""
    return Candidate(
        url=str(url),
        description=str(desc),
        width=props.get("width") or item.get("width"),
        height=props.get("height") or item.get("height"),
        source="brave",
    )


# Terms that signal a lifestyle/person shot we do NOT want (we want a clean product
# still-life). Domain-NEUTRAL: any vertical-specific negatives (e.g. project-echo "off-theme")
# come from the project's negative_terms config, not from this skill-level list.
_LIFESTYLE_TERMS = (
    "woman", "man", "model", "portrait", "lifestyle", "person", "people",
    "face", "hand", "girl", "boy",
)
_PRODUCT_TERMS = ("pack", "box", "carton", "product", "packaging", "packet", "still life")


def score_candidate(
    candidate: Candidate,
    brand: str,
    *,
    negative_terms: tuple[str, ...] = (),
) -> float:
    """Score a candidate: prefer real product still-life of the brand, larger, no people.

    ``negative_terms`` adds project-supplied penalties (e.g. project-echo "off-theme terms")
    on top of the domain-neutral lifestyle/person negatives.
    """
    desc = (candidate.description or "").lower()
    b = brand.strip().lower()
    score = 0.0
    if b and b in desc:
        score += 2.0
    for t in _PRODUCT_TERMS:
        if t in desc:
            score += 1.0
    for t in (*_LIFESTYLE_TERMS, *negative_terms):
        if t in desc:
            score -= 3.0
    smaller_edge = min(candidate.width or 0, candidate.height or 0)
    if smaller_edge >= 1000:
        score += 3.0
    elif smaller_edge >= 600:
        score += 2.0
    elif smaller_edge >= 400:
        score += 1.0
    elif 0 < smaller_edge < 200:
        score -= 1.0
    return score


def pick_best(
    candidates: list[Candidate],
    brand: str,
    *,
    negative_terms: tuple[str, ...] = (),
) -> Candidate | None:
    """Return the highest-scoring candidate, or None if there are none."""
    if not candidates:
        return None
    return max(candidates, key=lambda c: score_candidate(c, brand, negative_terms=negative_terms))


# ─── Network wrappers (thin; validated by live --smoke runs) ───────────────────

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


def tavily_image_search(query: str, max_results: int = 8, max_key_tries: int = 12) -> list[Candidate]:
    """Tavily image search, rotating pool keys past 432 (quota-exhausted)."""
    import httpx
    from scripts._core import credential_hub
    try:
        tries = min(credential_hub.tavily_pool_size() or 1, max_key_tries)
    except Exception:
        tries = 1
    with httpx.Client(timeout=45) as client:
        for _ in range(max(tries, 1)):
            try:
                key = credential_hub.get_tavily_key()
                r = client.post("https://api.tavily.com/search", json={
                    "api_key": key, "query": query, "include_images": True,
                    "include_image_descriptions": True, "max_results": max_results})
            except Exception:
                continue
            if r.status_code == 200:
                return [candidate_from_tavily(it) for it in r.json().get("images", [])]
            # non-200 (e.g. 432 quota) → rotate to the next key
    return []


def brave_image_search(query: str, count: int = 8) -> list[Candidate]:
    """Brave image search (independent quota from Tavily)."""
    import httpx
    from scripts._core import credential_hub
    try:
        key = credential_hub.get_credential("brave-search")
    except Exception:
        return []
    try:
        with httpx.Client(timeout=45) as client:
            r = client.get("https://api.search.brave.com/res/v1/images/search",
                           params={"q": query, "count": count, "safesearch": "off"},
                           headers={"X-Subscription-Token": key, "Accept": "application/json"})
        if r.status_code == 200:
            return [candidate_from_brave(it) for it in r.json().get("results", [])]
    except Exception:
        pass
    return []


def firecrawl_page_images(url: str) -> list[str]:
    """Scrape a product page via Firecrawl and return its image URLs (canonical high-res)."""
    import re
    import httpx
    from scripts._core import credential_hub
    try:
        key = credential_hub.get_credential("firecrawl")
    except Exception:
        return []
    try:
        with httpx.Client(timeout=90) as client:
            r = client.post("https://api.firecrawl.dev/v1/scrape",
                            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                            json={"url": url, "formats": ["markdown"]})
        j = r.json()
        if r.status_code == 200 and j.get("success"):
            md = (j.get("data", {}) or {}).get("markdown", "") or ""
            urls = re.findall(r'!\[[^\]]*\]\((https?://[^)\s]+)\)', md)
            return [u for u in urls
                    if any(u.lower().split("?")[0].endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp"))]
    except Exception:
        pass
    return []


def download_image(url: str, min_bytes: int = 25_000, min_edge: int = 380) -> bytes | None:
    """Download + validate a real image (content-type, byte size, min edge)."""
    import io
    import httpx
    from PIL import Image
    try:
        with httpx.Client(timeout=40, follow_redirects=True, headers=_UA) as client:
            r = client.get(url)
        if r.status_code != 200 or "image" not in r.headers.get("content-type", ""):
            return None
        data = r.content
        if len(data) < min_bytes:
            return None
        im = Image.open(io.BytesIO(data))
        if min(im.size) < min_edge:
            return None
        return data
    except Exception:
        return None


def source_real_photo(
    brand: str,
    purpose: str = "",
    providers: tuple[str, ...] = ("tavily", "brave"),
    max_candidates: int = 24,
    *,
    product_noun: str = "product",
    search_terms: tuple[str, ...] = (),
    negative_terms: tuple[str, ...] = (),
) -> tuple[Candidate, bytes] | None:
    """Find + download the best real product photo for ``brand``. Returns (candidate, bytes)."""
    candidates: list[Candidate] = []
    for q in build_search_queries(brand, purpose, product_noun=product_noun, search_terms=search_terms):
        if "brave" in providers:
            candidates += brave_image_search(q)
        if "tavily" in providers:
            candidates += tavily_image_search(q)
        if len(candidates) >= max_candidates:
            break
    ranked = sorted(
        candidates, key=lambda c: score_candidate(c, brand, negative_terms=negative_terms), reverse=True
    )
    for cand in ranked:
        if not cand.url:
            continue
        data = download_image(cand.url)
        if data is not None:
            return (cand, data)
    return None
