"""scripts/research/_detect_local_intent.py — Local-intent detector (GLOBAL, v3.40.0).

PURPOSE
─────────
Given a keyword like "1000W LED grow light Oklahoma" or "chinese age-restricted products
toronto" or "tea wholesale guangdong", determine if the keyword contains a
geographic anchor and, if so, classify the granularity
(country | state | city | region | metro | zip | near_me).

This is the gate that routes seo-blog from generic-flow to local-mode. The
output is written into state.json::brief.local_mode + brief.location_anchor
(see schemas/state.schema.json).

SCOPE — WORLDWIDE (v3.40.0, 2026-07-16)
────────────────────────────────────────
v5.0 shipped only the US gazetteer (us_states.json + us_cities_top500.json),
so "toronto"/"sydney"/"guangdong" never triggered local mode and — worse —
"ontario" anchored to Ontario, California and "british columbia" substring-
matched Columbia, SC. The international layer designed in
memory/research/location_intent_detection_2026.json is now implemented:

    world_countries.json  — 252 countries + curated aliases (UK, USA, UAE …)
    world_admin1.json     — ~3.8k states/provinces worldwide (Ontario, Guangdong,
                            Queensland, England …; US states stay in us_states.json)
    world_cities.json     — ~34k cities with population ≥15k (GeoNames, CC-BY)

Rebuild data via:  python -m scripts.research.build_world_gazetteer

DESIGN — 4-tier cascade (per memory/research/location_intent_detection_2026.json)
─────────────────────────────────────────────────────────────────────────────────
Tier 1: regex (sub-millisecond)
    - US ZIP, UK postcode, Canadian postal, "near me" family
Tier 2: gazetteer n-gram exact match (~ms; hash lookup, NOT per-name regex)
    - US colloquial regions (PNW, DMV, …) → countries → US states +
      world admin1 → cities (US top500 + world) → trailing state/province codes
    - Longest span wins across kinds ("british columbia" admin1 beats "columbia" city)
    - A city consistent with an in-keyword state/admin1/country cue wins over
      the bare state/admin1 anchor ("london ontario" → London, ON, CA)
Tier 3: spaCy NER (optional; gap-filler; resolves through the SAME global gazetteer)
Tier 4: geopy/Nominatim (disabled by default)

COLLISION HANDLING
──────────────────
- 12 US state abbreviations are English words (OR, IN, ME, …): 2-letter code
  must be ALL-CAPS at end of keyword (unchanged from v5.0).
- CA province / AU state codes (ON, QC, BC, NSW, QLD, …) follow the same
  ALL-CAPS + end-of-string discipline. WA keeps its US-state precedence.
- World names that are common English words (nice, bath, china, turkey, …)
  carry a word_collision flag from the builder and only match when the keyword
  contains a SECOND, unflagged geo cue ("tea shop nice france" ✓;
  "bone china tea set" ✗). Curated list — big cities (population ≥400k, e.g.
  Phoenix) are never gated.

AMBIGUITY (unchanged contract)
──────────────────────────────
service_area_states → in-keyword cue → project target-market countries →
population ≥2x auto-pick → ambiguous=true with disambiguation_options.
Cross-COUNTRY duplicates (Vancouver BC/WA, London GB/ON) resolve the same way.

CLI
───
    python -m scripts.research._detect_local_intent "1000W LED Oklahoma"
    python -m scripts.research._detect_local_intent --keyword "matcha vancouver" --json
    python -m scripts.research._detect_local_intent --keyword "tea shop ontario" \
        --countries CA --json

EXIT
────
    0 = detection succeeded (output to stdout; check JSON `local_mode`)
    2 = bad arguments
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


_DATA_DIR = Path(__file__).resolve().parent / "data"

_MAX_NGRAM = 5  # longest place-name span we attempt to match (tokens)

# Known non-place phrases (brands, franchises, personas) whose tokens must NOT
# seed a gazetteer match. Curated per the v5.0 xfail class (Indiana Jones,
# Manchester United, New York Times, …). Normalized form.
_NON_PLACE_PHRASES = [
    "manchester united", "manchester city fc", "new york times",
    "washington post", "boston dynamics", "indiana jones", "maine coon",
    "brooklyn 99", "kansas city chiefs", "chicago bulls", "boston terrier",
    "yorkshire terrier", "victoria s secret", "victoria secret",
    "paris hilton", "birmingham small arms", "york peppermint",
]


# ─── Tier 1: regex patterns ──────────────────────────────────────

_US_ZIP_RE = re.compile(r"\b(\d{5})(-\d{4})?\b")
_UK_POSTCODE_RE = re.compile(
    r"\b([A-Z]{1,2}\d[A-Z\d]?)\s?(\d[A-Z]{2})\b",
    re.IGNORECASE,
)
_CA_POSTAL_RE = re.compile(
    r"\b([A-Z]\d[A-Z])\s?(\d[A-Z]\d)\b",
    re.IGNORECASE,
)
_NEAR_ME_RE = re.compile(
    r"\b(near\s+me|around\s+me|in\s+my\s+area|closest|nearby|near\s+by)\b",
    re.IGNORECASE,
)


# ─── Data load (lazy) ────────────────────────────────────────────

_STATES_CACHE: dict[str, Any] | None = None
_INDEX_CACHE: dict[str, Any] | None = None

# Trailing province/state codes for CA + AU (ALL-CAPS + end-of-string only).
# US codes are handled via us_states.json. WA is deliberately absent here —
# it keeps its US-state meaning (documented collision).
_CA_PROVINCE_CODES = {
    "ON": "Ontario", "QC": "Quebec", "BC": "British Columbia", "AB": "Alberta",
    "MB": "Manitoba", "SK": "Saskatchewan", "NS": "Nova Scotia",
    "NB": "New Brunswick", "NL": "Newfoundland and Labrador",
    "PE": "Prince Edward Island", "YT": "Yukon", "NT": "Northwest Territories",
    "NU": "Nunavut",
}
_AU_STATE_CODES = {
    "NSW": "New South Wales", "VIC": "Victoria", "QLD": "Queensland",
    "SA": "South Australia", "TAS": "Tasmania",
    "ACT": "Australian Capital Territory",
}


def _load_states() -> dict:
    global _STATES_CACHE
    if _STATES_CACHE is None:
        _STATES_CACHE = json.loads((_DATA_DIR / "us_states.json").read_text(encoding="utf-8"))
    return _STATES_CACHE


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _build_indexes() -> dict[str, Any]:
    """Build hash indexes over all gazetteer layers. Cached module-global.

    Index value shapes (all keyed by normalized name):
        countries: list[{kind:'country', country, canonical, name, population, collision}]
        admin1:    list[{kind:'admin1', country, canonical, name, country_population, collision}]
        us_states: list[{kind:'us_state', canonical(abbrev), name, fips, population}]
        cities:    list[{kind:'city', name, country, admin1, population, collision}]
    """
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE

    countries_idx: dict[str, list[dict]] = {}
    admin1_idx: dict[str, list[dict]] = {}
    us_state_idx: dict[str, list[dict]] = {}
    city_idx: dict[str, list[dict]] = {}

    def _add(idx: dict[str, list[dict]], key: str, entry: dict) -> None:
        idx.setdefault(key, []).append(entry)

    # world countries
    wc = json.loads((_DATA_DIR / "world_countries.json").read_text(encoding="utf-8"))
    for iso2, info in wc["countries"].items():
        entry = {
            "kind": "country", "country": iso2, "canonical": iso2,
            "name": info["name"], "population": info.get("population", 0),
            "collision": info.get("word_collision", False),
        }
        _add(countries_idx, _normalize(info["name"]), entry)
        for alias in info.get("aliases", []):
            _add(countries_idx, _normalize(alias), entry)

    # world admin1 (US excluded at build time)
    wa = json.loads((_DATA_DIR / "world_admin1.json").read_text(encoding="utf-8"))
    for name, country, canonical, member_pop, country_pop, collision in wa["admin1"]:
        _add(admin1_idx, _normalize(name), {
            "kind": "admin1", "country": country, "canonical": canonical,
            "name": name, "population": member_pop,
            "country_population": country_pop, "collision": collision,
        })

    # US states (full names; abbreviations handled separately)
    states = _load_states()["states"]
    for abbrev, info in states.items():
        _add(us_state_idx, _normalize(info["name"]), {
            "kind": "us_state", "canonical": abbrev, "name": info["name"],
            "fips": info["fips"], "population": info["population"],
        })

    # cities: US top500 first (has curated aliases), then world (dedupe)
    seen: set[tuple[str, str, str]] = set()
    us500 = json.loads((_DATA_DIR / "us_cities_top500.json").read_text(encoding="utf-8"))
    for name, state, pop, aliases in us500["cities"]:
        entry = {
            "kind": "city", "name": name, "country": "US", "admin1": state,
            "population": pop, "collision": False,
        }
        seen.add((_normalize(name), "US", state))
        _add(city_idx, _normalize(name), entry)
        for alias in aliases:
            _add(city_idx, _normalize(alias), entry)

    wcity = json.loads((_DATA_DIR / "world_cities.json").read_text(encoding="utf-8"))
    for name, country, admin1, pop, collision, aliases in wcity["cities"]:
        key = (_normalize(name), country, admin1)
        if key in seen:
            continue
        seen.add(key)
        entry = {
            "kind": "city", "name": name, "country": country, "admin1": admin1,
            "population": pop, "collision": bool(collision),
        }
        _add(city_idx, _normalize(name), entry)
        for alias in aliases:
            _add(city_idx, _normalize(alias), entry)

    _INDEX_CACHE = {
        "countries": countries_idx,
        "admin1": admin1_idx,
        "us_states": us_state_idx,
        "cities": city_idx,
        "country_names": {iso2: info["name"] for iso2, info in wc["countries"].items()},
    }
    return _INDEX_CACHE


def _country_name(iso2: str) -> str:
    return _build_indexes()["country_names"].get(iso2, iso2)


# ─── Result type ─────────────────────────────────────────────────

@dataclass
class LocationAnchor:
    type: str
    canonical: str
    name_full: str
    fips: str | None = None
    geonameid: int | None = None
    country: str = "US"
    containing_state: str | None = None
    population: int | None = None
    ambiguous: bool = False
    disambiguation_options: list = field(default_factory=list)
    detection_tier: int = 0
    confidence: float = 0.0


@dataclass
class DetectionResult:
    local_mode: bool
    location_anchor: LocationAnchor | None
    keyword: str
    tier_used: int | None = None
    notes: list[str] = field(default_factory=list)


# ─── Tier 1: regex ───────────────────────────────────────────────

def _tier1_regex(keyword: str) -> LocationAnchor | None:
    # ZIP code (5 or 5+4)
    if m := _US_ZIP_RE.search(keyword):
        zip5 = m.group(1)
        return LocationAnchor(
            type="zip", canonical=zip5, name_full=f"ZIP {zip5}",
            country="US", detection_tier=1, confidence=0.95,
        )
    # UK postcode
    if m := _UK_POSTCODE_RE.search(keyword):
        pc = f"{m.group(1)} {m.group(2)}".upper()
        return LocationAnchor(
            type="zip", canonical=pc, name_full=f"UK postcode {pc}",
            country="GB", detection_tier=1, confidence=0.95,
        )
    # Canadian postal
    if m := _CA_POSTAL_RE.search(keyword):
        pc = f"{m.group(1)} {m.group(2)}".upper()
        return LocationAnchor(
            type="zip", canonical=pc, name_full=f"Canadian postal {pc}",
            country="CA", detection_tier=1, confidence=0.95,
        )
    # "near me"
    if _NEAR_ME_RE.search(keyword):
        return LocationAnchor(
            type="near_me", canonical="near_me", name_full="near user (no specific location)",
            country="US", detection_tier=1, confidence=1.0,
        )
    return None


# ─── Tier 2: gazetteer (n-gram hash lookup) ──────────────────────

def _tokenize(keyword: str) -> list[str]:
    """Tokenize keyword into words. Preserves multi-word city names via joining."""
    return re.findall(r"[A-Za-z][A-Za-z\.\-']*", keyword)


def _check_state_abbrev(token: str, prev_token: str | None, is_last: bool) -> str | None:
    """Return state abbrev if token matches an actual state code AND passes collision filter."""
    if not token.isupper() or len(token) != 2:
        return None
    states = _load_states()["states"]
    if token not in states:
        return None
    # Always accept if it's actually uppercase AND it's at end of string OR follows a city-like word
    if states[token]["english_word_collision"]:
        # Stricter: must be at end of keyword (most common pattern: "X in OK", "Y Oklahoma OR")
        if not is_last:
            return None
    return token


def _check_regions(keyword: str, keyword_lc: str) -> dict | None:
    """Match colloquial regions like PNW, DMV, Bay Area."""
    regions = _load_states()["regions"]
    for region_id, info in regions.items():
        # Check the region key itself + the full name
        for variant in [region_id, info["name"]]:
            v_lc = variant.lower()
            if re.search(rf"\b{re.escape(v_lc)}\b", keyword_lc):
                return {
                    "region_id": region_id,
                    "name": info["name"],
                    "states": info["states"],
                }
    return None


@dataclass
class _Span:
    start: int
    length: int
    entry: dict

    @property
    def end(self) -> int:
        return self.start + self.length

    def contains(self, other: "_Span") -> bool:
        return (self.start <= other.start and other.end <= self.end
                and self.length > other.length)


def _masked_token_indexes(tokens_norm: list[str]) -> set[int]:
    """Token indexes covered by a known non-place phrase (brand/franchise)."""
    masked: set[int] = set()
    joined = tokens_norm
    for phrase in _NON_PLACE_PHRASES:
        p_tokens = phrase.split()
        n = len(p_tokens)
        for start in range(0, len(joined) - n + 1):
            if joined[start:start + n] == p_tokens:
                masked.update(range(start, start + n))
    return masked


def _collect_spans(tokens_norm: list[str]) -> list[_Span]:
    """All gazetteer matches over the normalized token list (longest n-grams too)."""
    idx = _build_indexes()
    masked = _masked_token_indexes(tokens_norm)
    spans: list[_Span] = []
    n_tokens = len(tokens_norm)
    for n in range(min(_MAX_NGRAM, n_tokens), 0, -1):
        for start in range(0, n_tokens - n + 1):
            if masked and any(i in masked for i in range(start, start + n)):
                continue
            gram = " ".join(tokens_norm[start:start + n])
            for kind in ("countries", "admin1", "us_states", "cities"):
                for entry in idx[kind].get(gram, []):
                    spans.append(_Span(start=start, length=n, entry=entry))
    return spans


def _drop_contained(spans: list[_Span]) -> list[_Span]:
    """Longest-span rule: a match strictly inside a longer match is dropped
    ('columbia' city inside 'british columbia' admin1)."""
    kept: list[_Span] = []
    for s in spans:
        if any(o.contains(s) for o in spans):
            continue
        kept.append(s)
    return kept


def _entry_country(entry: dict) -> str:
    return "US" if entry["kind"] == "us_state" else entry["country"]


def _synthetic_code_cues(tokens: list[str]) -> list[dict]:
    """ALL-CAPS state/province code cues, with the abbrev-collision discipline."""
    cues: list[dict] = []
    if len(tokens) < 2:
        return cues
    idx = _build_indexes()
    us_states_data = _load_states()["states"]

    def _prev_is_city(i: int) -> bool:
        return i > 0 and _normalize(tokens[i - 1]) in idx["cities"]

    for i, tok in enumerate(tokens):
        if not tok.isupper():
            continue
        is_last = i == len(tokens) - 1
        if len(tok) == 2 and tok in us_states_data:
            if us_states_data[tok]["english_word_collision"] and not (is_last or _prev_is_city(i)):
                continue
            cues.append({"kind": "us_state", "country": "US", "canonical": tok})
        elif tok in _CA_PROVINCE_CODES and (is_last or _prev_is_city(i)):
            cues.append({"kind": "admin1", "country": "CA", "canonical": tok})
        elif tok in _AU_STATE_CODES and (is_last or _prev_is_city(i)):
            cues.append({"kind": "admin1", "country": "AU", "canonical": tok})
    return cues


# Single-token world-city matches below this population are treated like
# word-collisions (they need a country-consistent cue). GeoNames ≥15k contains
# real-but-obscure names ("To", Burkina Faso 16k) that would otherwise hijack
# ordinary keywords. Every project-echo/metro-class target (mid-size cities
# 256k, Vaughan 323k …) clears this floor comfortably.
_MIN_UNCUED_WORLD_CITY_POP = 50_000


def _needs_cue(entry: dict) -> bool:
    if entry.get("collision"):
        return True
    return (
        entry["kind"] == "city"
        and entry["country"] != "US"
        and " " not in entry["name"]
        and entry.get("population", 0) < _MIN_UNCUED_WORLD_CITY_POP
    )


def _gate_collisions(
    spans: list[_Span], notes: list[str], *, cue_countries: set[str] | None = None,
) -> list[_Span]:
    """Word-collision names (and tiny single-token world cities) need a
    COUNTRY-CONSISTENT second geo cue.

    "tea shop nice france" → France unlocks Nice (FR); but "solar panels for
    sale in Texas" must NOT unlock Salé, Morocco (Texas is a US cue). A trailing
    ALL-CAPS province code ("victoria BC") contributes its country as a cue.
    """
    cue_countries = set(cue_countries or set())
    unflagged_countries = {
        _entry_country(s.entry) for s in spans if not _needs_cue(s.entry)
    }
    allowed = unflagged_countries | cue_countries
    result: list[_Span] = []
    for s in spans:
        if not _needs_cue(s.entry):
            result.append(s)
            continue
        if _entry_country(s.entry) in allowed:
            result.append(s)
        else:
            notes.append(
                f"'{s.entry['name']}' skipped: needs a country-consistent "
                f"secondary geo signal (English-word collision or <50k population)"
            )
    return result


def _city_anchor(c: dict, *, ambiguous: bool = False, options: list | None = None,
                 confidence: float = 0.9) -> LocationAnchor:
    if c["country"] == "US":
        name_full = f"{c['name']}, {c['admin1']}"
    elif c["admin1"]:
        name_full = f"{c['name']}, {c['admin1']}, {_country_name(c['country'])}"
    else:
        name_full = f"{c['name']}, {_country_name(c['country'])}"
    return LocationAnchor(
        type="city", canonical=c["name"], name_full=name_full,
        containing_state=c["admin1"] or None, country=c["country"],
        population=c["population"], ambiguous=ambiguous,
        disambiguation_options=options or [], detection_tier=2,
        confidence=confidence,
    )


def _admin1_anchor(a: dict, *, ambiguous: bool = False, options: list | None = None,
                   confidence: float = 0.95) -> LocationAnchor:
    return LocationAnchor(
        type="state", canonical=a["canonical"],
        name_full=f"{a['name']}, {_country_name(a['country'])}",
        country=a["country"], population=a.get("population") or None,
        ambiguous=ambiguous,
        disambiguation_options=options or [], detection_tier=2, confidence=confidence,
    )


def _us_state_anchor(s: dict, *, confidence: float = 0.95) -> LocationAnchor:
    return LocationAnchor(
        type="state", canonical=s["canonical"], name_full=s["name"],
        fips=s["fips"], population=s["population"], country="US",
        detection_tier=2, confidence=confidence,
    )


def _country_anchor(c: dict, *, confidence: float = 0.9) -> LocationAnchor:
    return LocationAnchor(
        type="country", canonical=c["canonical"], name_full=c["name"],
        country=c["country"], detection_tier=2, confidence=confidence,
    )


def _city_option(c: dict) -> dict:
    return {
        "name": c["name"], "state": c["admin1"], "country": c["country"],
        "population": c["population"],
        "canonical": f"{c['name']}, {c['admin1']}, US" if c["country"] == "US"
        else f"{c['name']}, {c['admin1']}, {_country_name(c['country'])}",
    }


def _admin1_option(a: dict) -> dict:
    return {
        "name": a["name"], "state": a["canonical"], "country": a["country"],
        "population": a.get("population") or None,
        "canonical": f"{a['name']} ({_country_name(a['country'])} province/state)",
    }


def _resolve_cities(
    cities: list[dict],
    cue_admin1: list[dict],       # us_state + admin1 candidates present in keyword
    cue_countries: list[dict],    # country candidates present in keyword
    project_service_area_states: list[str] | None,
    project_countries: list[str] | None,
) -> LocationAnchor:
    candidates = list(cities)

    # Step A: in-keyword cue — city consistent with a state/admin1/country mention wins
    if len(candidates) > 1 or cue_admin1 or cue_countries:
        cue_regions = {(a["country"] if a["kind"] == "admin1" else "US",
                        a["canonical"]) for a in cue_admin1}
        cue_ccs = {c["country"] for c in cue_countries} | {a["country"] if a["kind"] == "admin1" else "US"
                                                           for a in cue_admin1}
        by_region = [c for c in candidates if (c["country"], c["admin1"]) in cue_regions]
        if by_region:
            candidates = by_region
        else:
            by_cc = [c for c in candidates if c["country"] in cue_ccs]
            if by_cc:
                candidates = by_cc

    # Step B: project service-area states (US legacy contract)
    if project_service_area_states and len(candidates) > 1:
        filtered = [c for c in candidates
                    if c["country"] == "US" and c["admin1"] in project_service_area_states]
        if filtered:
            candidates = filtered

    # Step C: project target-market countries
    if project_countries and len(candidates) > 1:
        filtered = [c for c in candidates if c["country"] in project_countries]
        if filtered:
            candidates = filtered

    # Step D: population — ≥2x gap auto-picks, else ambiguous
    candidates.sort(key=lambda c: c["population"], reverse=True)
    top = candidates[0]
    if len(candidates) > 1:
        second = candidates[1]
        if top["population"] >= 2 * max(second["population"], 1):
            return _city_anchor(top, confidence=0.7)
        return _city_anchor(
            top, ambiguous=True,
            options=[_city_option(c) for c in candidates[:3]],
            confidence=0.5,
        )
    return _city_anchor(top, confidence=0.9)


def _tier2_gazetteer(
    keyword: str,
    project_service_area_states: list[str] | None = None,
    project_countries: list[str] | None = None,
    notes: list[str] | None = None,
) -> LocationAnchor | None:
    notes = notes if notes is not None else []
    keyword_lc = keyword.lower()
    tokens = _tokenize(keyword)

    # 1. Colloquial US regions first (PNW, DMV, Bay Area, …) — distinctive
    if region := _check_regions(keyword, keyword_lc):
        return LocationAnchor(
            type="region",
            canonical=region["region_id"],
            name_full=region["name"],
            detection_tier=2,
            confidence=0.9,
        )

    # 2. ALL-CAPS state/province codes act as synthetic cues ("victoria BC",
    #    "toronto ON", "Springfield IL real estate", "sydney NSW") — they unlock
    #    collision-gated names and feed city disambiguation. Discipline mirrors
    #    _check_state_abbrev: English-word-colliding codes (and all CA/AU codes)
    #    only count at end-of-keyword OR right after a known city token. The
    #    bare-code fallback at step 6 still covers keywords with no other match.
    synthetic_cues = _synthetic_code_cues(tokens)

    # 3. n-gram span collection over countries / admin1 / US states / cities
    tokens_norm = _normalize(keyword).split()
    spans = _collect_spans(tokens_norm)
    spans = _drop_contained(spans)
    spans = _gate_collisions(
        spans, notes, cue_countries={c["country"] for c in synthetic_cues})

    city_spans = [s for s in spans if s.entry["kind"] == "city"]
    us_state_spans = [s for s in spans if s.entry["kind"] == "us_state"]
    admin1_spans = [s for s in spans if s.entry["kind"] == "admin1"]
    country_spans = [s for s in spans if s.entry["kind"] == "country"]

    if city_spans:
        # "Twin" spans: the same token range reads as BOTH a city and a
        # state/admin1 ("ontario" = CA province + Ontario, CA city;
        # "new york" = US state + NYC).
        state_like_spans = us_state_spans + admin1_spans
        twin_keys = {(s.start, s.length) for s in state_like_spans}
        pure_city_spans = [s for s in city_spans if (s.start, s.length) not in twin_keys]

        if pure_city_spans:
            # Distinct city present — every state/admin1/country mention (twins
            # included) is a cue for resolving it ("london ontario" → London, ON, CA)
            cue_admin1 = [s.entry for s in state_like_spans] + synthetic_cues
            cue_countries = [s.entry for s in country_spans]
            return _resolve_cities(
                [s.entry for s in pure_city_spans], cue_admin1, cue_countries,
                project_service_area_states, project_countries)

        # ALL city readings are twins of a state/admin1 reading.
        city_twin_keys = {(s.start, s.length) for s in city_spans}
        us_twins = [s for s in us_state_spans if (s.start, s.length) in city_twin_keys]
        if us_twins:
            # Preserve v5.0 behavior: a full US state name wins over its
            # same-name city ("washington…" → state WA, "new york…" → state NY)
            return _us_state_anchor(us_twins[0].entry)

        a1_twins = sorted(
            (s.entry for s in admin1_spans if (s.start, s.length) in city_twin_keys),
            key=lambda e: e.get("population", 0), reverse=True,
        )
        if a1_twins:
            # World province vs same-name city ("ontario" = CA province vs
            # Ontario, CA city; "hamilton" = Bermuda parish vs Hamilton, ON).
            twin_cities = sorted(
                (c.entry for c in city_spans),
                key=lambda c: c["population"], reverse=True,
            )
            # In-keyword country cue ("manchester uk" / "manchester jamaica")
            # decides the reading directly.
            cue_ccs = {s.entry["country"] for s in country_spans} | {
                c["country"] for c in synthetic_cues}
            if cue_ccs:
                cued_cities = [c for c in twin_cities if c["country"] in cue_ccs]
                cued_admin1 = [a for a in a1_twins if a["country"] in cue_ccs]
                if cued_cities and not cued_admin1:
                    return _resolve_cities(
                        cued_cities, synthetic_cues, [s.entry for s in country_spans],
                        project_service_area_states, project_countries)
                if cued_admin1 and not cued_cities:
                    return _admin1_anchor(cued_admin1[0])
            # Containment: the top city sits INSIDE the same-name admin1
            # ("tokyo" city in Tokyo prefecture, "quebec" city in Quebec,
            # "dubai" city in Dubai emirate) — not a real ambiguity; the more
            # specific city reading serves both intents.
            if (twin_cities and a1_twins
                    and twin_cities[0]["country"] == a1_twins[0]["country"]
                    and twin_cities[0]["admin1"] == a1_twins[0]["canonical"]):
                return _city_anchor(twin_cities[0], confidence=0.75)
            # Project target markets decide when they can.
            proj = set(project_countries or [])
            if proj:
                a_fav = [a for a in a1_twins if a["country"] in proj]
                city_fav = [c for c in twin_cities if c["country"] in proj]
                if a_fav and not city_fav:
                    return _admin1_anchor(a_fav[0], confidence=0.7)
                if city_fav and not a_fav:
                    return _resolve_cities(
                        city_fav, [], [], project_service_area_states, project_countries)
                if a_fav and city_fav:
                    a1_twins, twin_cities = a_fav, city_fav
            # Size decides: the admin1's member-city population sum vs the
            # biggest same-name city. ≥2x gap auto-picks; else flag ambiguous.
            a_top = a1_twins[0]
            c_top = twin_cities[0]
            a_pop = a_top.get("population", 0)
            c_pop = c_top["population"]
            if a_pop >= 2 * max(c_pop, 1):
                return _admin1_anchor(
                    a_top, ambiguous=True,
                    options=[_admin1_option(a_top)] + [_city_option(c) for c in twin_cities[:2]],
                    confidence=0.6,
                ) if not (proj and a_top["country"] in proj) else _admin1_anchor(a_top, confidence=0.7)
            if c_pop >= 2 * max(a_pop, 1):
                return _resolve_cities(
                    twin_cities, synthetic_cues, [s.entry for s in country_spans],
                    project_service_area_states, project_countries)
            winner_is_admin1 = a_pop >= c_pop
            options = [_admin1_option(a) for a in a1_twins[:1]] + \
                      [_city_option(c) for c in twin_cities[:2]]
            if winner_is_admin1:
                return _admin1_anchor(a_top, ambiguous=True, options=options, confidence=0.55)
            return _city_anchor(c_top, ambiguous=True, options=options, confidence=0.55)

        # Unreachable in practice (twins imply state-like spans), but stay safe:
        return _resolve_cities(
            [s.entry for s in city_spans], synthetic_cues,
            [s.entry for s in country_spans],
            project_service_area_states, project_countries)

    # 3. US state full names (no city present)
    if us_state_spans:
        return _us_state_anchor(us_state_spans[0].entry)

    # 4. World admin1 full names (Ontario, Guangdong, Queensland, England, …)
    if admin1_spans:
        entries = [s.entry for s in admin1_spans]
        if len(entries) > 1:
            proj = set(project_countries or [])
            in_proj = [e for e in entries if e["country"] in proj]
            if in_proj:
                entries = in_proj
        entries.sort(
            key=lambda e: (e.get("population", 0), e.get("country_population", 0)),
            reverse=True,
        )
        top = entries[0]
        if len(entries) > 1:
            second = entries[1]
            if top.get("population", 0) < 2 * max(second.get("population", 0), 1):
                return _admin1_anchor(
                    top, ambiguous=True,
                    options=[_admin1_option(e) for e in entries[:3]],
                    confidence=0.6,
                )
        return _admin1_anchor(top)

    # 5. Country names / aliases ("chinese age-restricted products canada", "tea shop uk")
    if country_spans:
        return _country_anchor(country_spans[0].entry)

    # 6. Trailing state/province codes (last resort — high false-positive risk)
    if len(tokens) >= 2:
        states = _load_states()["states"]
        for i, tok in enumerate(tokens):
            prev = tokens[i - 1] if i > 0 else None
            is_last = (i == len(tokens) - 1)
            if state_ab := _check_state_abbrev(tok, prev, is_last):
                info = states[state_ab]
                return LocationAnchor(
                    type="state",
                    canonical=state_ab,
                    name_full=info["name"],
                    fips=info["fips"],
                    population=info["population"],
                    detection_tier=2,
                    confidence=0.7 if not info["english_word_collision"] else 0.55,
                )
        last = tokens[-1]
        if last.isupper():
            if last in _CA_PROVINCE_CODES:
                return LocationAnchor(
                    type="state", canonical=last,
                    name_full=f"{_CA_PROVINCE_CODES[last]}, CA",
                    country="CA", detection_tier=2, confidence=0.7,
                )
            if last in _AU_STATE_CODES:
                return LocationAnchor(
                    type="state", canonical=last,
                    name_full=f"{_AU_STATE_CODES[last]}, AU",
                    country="AU", detection_tier=2, confidence=0.7,
                )

    return None


# ─── Tier 3: spaCy NER (optional gap-filler) ─────────────────────

def _tier3_spacy(
    keyword: str,
    project_service_area_states: list[str] | None = None,
    project_countries: list[str] | None = None,
) -> LocationAnchor | None:
    """Run spaCy NER on the keyword. Degrades gracefully if spaCy unavailable."""
    try:
        import spacy  # noqa: F401
    except ImportError:
        return None
    try:
        # Try the small English model first (faster)
        try:
            nlp = spacy.load("en_core_web_sm")
        except Exception:
            return None
        doc = nlp(keyword)
        # Collect GPE (Geo-Political Entity) tags
        gpes = [ent.text for ent in doc.ents if ent.label_ in ("GPE", "LOC")]
        if not gpes:
            return None
        # Try to resolve the first GPE via Tier 2 (global gazetteer)
        for gpe in gpes:
            sub_result = _tier2_gazetteer(
                gpe,
                project_service_area_states=project_service_area_states,
                project_countries=project_countries,
            )
            if sub_result:
                sub_result.detection_tier = 3
                sub_result.confidence = min(sub_result.confidence, 0.7)
                return sub_result
        return None
    except Exception:
        return None


# ─── Main detection ──────────────────────────────────────────────

def detect_local_intent(
    keyword: str,
    *,
    project_service_area_states: list[str] | None = None,
    project_countries: list[str] | None = None,
    allow_spacy: bool = True,
    allow_geopy: bool = False,
) -> DetectionResult:
    """Main entry point.

    Args:
        keyword: The user's raw search keyword.
        project_service_area_states: If provided, disambiguates same-name US cities.
        project_countries: ISO2 country codes of the project's target markets;
            biases cross-country disambiguation (never gates detection).
        allow_spacy: Try Tier 3 spaCy NER if Tier 1+2 miss.
        allow_geopy: Try Tier 4 geopy/Nominatim (disabled by default; slow).

    Returns:
        DetectionResult with local_mode + location_anchor + tier_used.
    """
    notes: list[str] = []

    # Tier 1
    anchor = _tier1_regex(keyword)
    if anchor:
        return DetectionResult(
            local_mode=True, location_anchor=anchor, keyword=keyword, tier_used=1,
        )

    # Tier 2
    anchor = _tier2_gazetteer(
        keyword,
        project_service_area_states=project_service_area_states,
        project_countries=project_countries,
        notes=notes,
    )
    if anchor:
        return DetectionResult(
            local_mode=True, location_anchor=anchor, keyword=keyword, tier_used=2,
            notes=notes,
        )

    # Tier 3
    if allow_spacy:
        anchor = _tier3_spacy(
            keyword,
            project_service_area_states=project_service_area_states,
            project_countries=project_countries,
        )
        if anchor:
            return DetectionResult(
                local_mode=True, location_anchor=anchor, keyword=keyword, tier_used=3,
                notes=notes,
            )

    # Tier 4 (off by default)
    # ... geopy/Nominatim, deliberately omitted ...

    notes.append("no location detected in keyword across tiers 1-3")
    return DetectionResult(
        local_mode=False, location_anchor=None, keyword=keyword, tier_used=None,
        notes=notes,
    )


# ─── CLI ─────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="Detect local-intent in a keyword")
    p.add_argument("keyword", nargs="?", help="Keyword to analyze")
    p.add_argument("--keyword", dest="keyword_flag", help="Alternative flag form")
    p.add_argument(
        "--service-area-states",
        help="Comma-separated state abbrevs that bias ambiguity resolution (e.g. 'CA,CO,OK')",
    )
    p.add_argument(
        "--countries",
        help="Comma-separated ISO2 target-market countries that bias cross-country "
             "disambiguation (e.g. 'CA,GB')",
    )
    p.add_argument("--no-spacy", action="store_true", help="Disable Tier 3 spaCy NER")
    p.add_argument("--allow-geopy", action="store_true", help="Enable Tier 4 geopy/Nominatim")
    p.add_argument("--json", action="store_true", help="Emit JSON")
    args = p.parse_args()

    kw = args.keyword or args.keyword_flag
    if not kw:
        print("ERROR: keyword required (positional or --keyword)", file=sys.stderr)
        return 2

    states_filter = (
        [s.strip().upper() for s in args.service_area_states.split(",")]
        if args.service_area_states
        else None
    )
    countries_filter = (
        [s.strip().upper() for s in args.countries.split(",")]
        if args.countries
        else None
    )

    result = detect_local_intent(
        kw,
        project_service_area_states=states_filter,
        project_countries=countries_filter,
        allow_spacy=not args.no_spacy,
        allow_geopy=args.allow_geopy,
    )

    # Convert dataclass → dict for JSON
    out = {
        "keyword": result.keyword,
        "local_mode": result.local_mode,
        "tier_used": result.tier_used,
        "location_anchor": asdict(result.location_anchor) if result.location_anchor else None,
        "notes": result.notes,
    }

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"keyword:     {kw!r}")
        print(f"local_mode:  {result.local_mode}")
        print(f"tier_used:   {result.tier_used}")
        if result.location_anchor:
            la = result.location_anchor
            print(f"location:    {la.name_full} ({la.canonical}, type={la.type}, conf={la.confidence:.2f})")
            if la.ambiguous:
                print(f"  AMBIGUOUS — options: {la.disambiguation_options}")
        for n in result.notes:
            print(f"  note: {n}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
