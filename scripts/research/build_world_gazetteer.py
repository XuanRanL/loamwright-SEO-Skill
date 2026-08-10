"""scripts/research/build_world_gazetteer.py — One-shot builder for the WORLD gazetteer.

PURPOSE
─────────
v3.40.0 (2026-07-16): local-mode detection must trigger for ALL world cities,
provinces/states, and countries — not only the bundled US subset (the 2026-05-22
research artifact memory/research/location_intent_detection_2026.json designed the
international layer, but v5.0 only shipped us_states.json + us_cities_top500.json).

This script downloads the GeoNames dumps and emits three bundled JSON data files
consumed by scripts/research/_detect_local_intent.py:

    scripts/research/data/world_countries.json   (~250 rows)
    scripts/research/data/world_admin1.json      (~3,800 rows — states/provinces worldwide)
    scripts/research/data/world_cities.json      (~26,000 rows — cities with population ≥15k)

DATA LICENSE — GeoNames is CC-BY 4.0. Attribution is embedded in each emitted
file's `_source` header and MUST be preserved.

The emitted files are committed to git (the detector must work offline). Re-run
this builder only to refresh the data; it is NOT invoked at pipeline runtime.

CLI
───
    python -m scripts.research.build_world_gazetteer            # full build
    python -m scripts.research.build_world_gazetteer --min-population 15000
    python -m scripts.research.build_world_gazetteer --skip-download   # reuse cached dumps

EXIT: 0 = files written; 1 = download/parse failure.
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

import httpx

_GEONAMES_BASE = "https://download.geonames.org/export/dump"
_CACHE_DIR = Path.home() / ".xuanran-seo" / "data" / "geonames"
_OUT_DIR = Path(__file__).resolve().parent / "data"

_ATTRIBUTION = "GeoNames (geonames.org), CC-BY 4.0 — attribution required"

# ─── Curated collision + alias tables ────────────────────────────
#
# Names in _ENGLISH_WORD_COLLISIONS are genuinely-common English words (or
# high-frequency non-place tokens like brand/food words). A single-token
# country/admin1/city match on one of these requires a SECONDARY geo cue in
# the same keyword before the detector will accept it ("bone china tea set"
# must NOT anchor to China; "tea shop nice france" MAY anchor to Nice).
# Curated (not derived from a 370k wordlist) so big cities like Hamilton,
# Ontario, London are never accidentally gated.
_ENGLISH_WORD_COLLISIONS = {
    # countries
    "china", "turkey", "jordan", "chad", "georgia", "niger", "guinea", "mali",
    # admin1 / cities that are common English words or high-risk brand tokens.
    # NOT included on purpose: windsor / hamburg / moscow — genuine article
    # targets (project-echo published a regional city) that are not everyday English words.
    "nice", "bath", "reading", "split", "sale", "most", "deal", "march",
    "mobile", "orange", "buffalo", "male", "price", "best", "surprise",
    "normal", "industry", "hurricane", "eden", "hope", "liberty",
    "independence", "enterprise", "battle", "hell", "boring", "why",
    "young", "banks", "golden", "central", "union", "commerce", "victoria",
    "phoenix", "crystal", "diamond", "energy", "friend", "garland", "harmony",
    "jasper", "media", "midway", "ideal", "star", "sun", "rice",
    "cream", "cool", "green", "salem", "florida", "asbestos", "petroleum",
    "vulcan", "cork", "derby", "ash", "over", "street",
    "well", "sandy", "chester", "gap", "advance", "alert", "may", "june",
    "august", "florence", "clinton", "monterey", "manor", "villa",
}

# Function words / everyday tokens that must NEVER stand alone as a place
# match at ANY population ("To", Burkina Faso and "Yoga", Tokyo are real
# GeoNames populated places). Merged into the collision set.
_STOPWORD_COLLISIONS = {
    "a", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is",
    "it", "my", "no", "of", "on", "or", "so", "to", "up", "us", "we",
    "and", "are", "but", "can", "for", "get", "has", "how", "new", "not",
    "now", "off", "one", "our", "out", "per", "set", "the", "top", "two",
    "use", "was", "who", "why", "you", "yoga", "best", "buy", "from",
    "have", "into", "less", "like", "long", "made", "many", "more",
    "much", "near", "onto", "some", "than", "that", "this", "very",
    "what", "when", "where", "with", "your", "guide", "price", "cheap",
    "review", "versus",
}
_ENGLISH_WORD_COLLISIONS |= _STOPWORD_COLLISIONS
# NOTE: no population whitelist — curated words are ALWAYS gated (Salé, Morocco
# has 900k+ people and must still not match "for sale"). US majors like Phoenix
# arrive unflagged via us_cities_top500.json, so they are unaffected.

# Country-name aliases → ISO2 (matched as whole normalized spans)
_COUNTRY_ALIASES: dict[str, str] = {
    "uk": "GB", "u k": "GB", "great britain": "GB", "britain": "GB",
    "usa": "US", "united states of america": "US",
    "uae": "AE", "holland": "NL", "south korea": "KR", "north korea": "KP",
    "czech republic": "CZ", "czechia": "CZ", "ivory coast": "CI",
    "burma": "MM", "macedonia": "MK",
}

# Historic / colloquial city aliases → GeoNames asciiname to alias onto
_CITY_ALIASES: dict[str, tuple[str, str]] = {
    # alias → (asciiname, country_code)
    "saigon": ("Ho Chi Minh City", "VN"),
    "bombay": ("Mumbai", "IN"),
    "calcutta": ("Kolkata", "IN"),
    "madras": ("Chennai", "IN"),
    "peking": ("Beijing", "CN"),
    "canton": ("Guangzhou", "CN"),
}

# ISO 3166-2 canonical codes for CA provinces / AU states (GeoNames uses
# numeric admin1 codes for these; ISO codes are what SEO briefs + schema want).
_CA_PROVINCE_ISO = {
    "Alberta": "AB", "British Columbia": "BC", "Manitoba": "MB",
    "New Brunswick": "NB", "Newfoundland and Labrador": "NL",
    "Nova Scotia": "NS", "Northwest Territories": "NT", "Nunavut": "NU",
    "Ontario": "ON", "Prince Edward Island": "PE", "Quebec": "QC",
    "Saskatchewan": "SK", "Yukon": "YT",
}
_AU_STATE_ISO = {
    "New South Wales": "NSW", "Victoria": "VIC", "Queensland": "QLD",
    "Western Australia": "WA", "South Australia": "SA", "Tasmania": "TAS",
    "Australian Capital Territory": "ACT", "Northern Territory": "NT",
}


def _download(name: str, *, skip_download: bool) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = _CACHE_DIR / name
    if dest.exists() and (skip_download or dest.stat().st_size > 0):
        if skip_download:
            return dest
    url = f"{_GEONAMES_BASE}/{name}"
    print(f"  downloading {url} ...", file=sys.stderr)
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        dest.write_bytes(r.content)
    return dest


def _iso_admin1_canonical(country: str, name: str, geonames_code: str) -> str:
    if country == "CA":
        return _CA_PROVINCE_ISO.get(name, name)
    if country == "AU":
        return _AU_STATE_ISO.get(name, name)
    if country == "US":
        return geonames_code  # already the 2-letter state abbrev
    # GB uses ENG/SCT/WLS/NIR; other countries get the readable name
    if country == "GB" and geonames_code in ("ENG", "SCT", "WLS", "NIR"):
        return geonames_code
    return name


def _is_collision(name: str) -> bool:
    if " " in name:
        return False  # multi-word names are unambiguous enough
    return name.lower() in _ENGLISH_WORD_COLLISIONS


def build_countries(country_info: Path) -> dict:
    rows: dict[str, dict] = {}
    for line in country_info.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        iso2, name, population = parts[0], parts[4], parts[7]
        if not iso2 or not name:
            continue
        rows[iso2] = {
            "name": name,
            "population": int(population) if population.isdigit() else 0,
            "aliases": [],
            "word_collision": _is_collision(name),
        }
    for alias, iso2 in _COUNTRY_ALIASES.items():
        if iso2 in rows:
            rows[iso2]["aliases"].append(alias)
    return {
        "_schema": "v1.0 — world countries. iso2 → {name, population, aliases, word_collision}",
        "_source": f"{_ATTRIBUTION} — countryInfo.txt",
        "countries": rows,
    }


def build_admin1(
    admin1_file: Path, countries: dict, admin1_city_pop: dict[tuple[str, str], int],
) -> dict:
    """admin1_city_pop: (country, canonical_code) → sum of member-city populations.

    That sum is the admin1's SIZE PROXY — it lets the detector rank a province
    against a same-name city (Ontario province ≈ 10M+ city-pop beats Ontario,
    CA city 175k; Bermuda's Hamilton parish ≈ 1k loses to Hamilton, ON 569k).
    """
    rows: list[list] = []
    for line in admin1_file.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        code, _name, asciiname = parts[0], parts[1], parts[2]
        if "." not in code:
            continue
        country, gcode = code.split(".", 1)
        if country == "US":
            continue  # US states live in us_states.json (backward compat)
        if not asciiname or asciiname.isdigit():
            continue
        canonical = _iso_admin1_canonical(country, asciiname, gcode)
        country_pop = countries["countries"].get(country, {}).get("population", 0)
        rows.append([
            asciiname,
            country,
            canonical,
            admin1_city_pop.get((country, canonical), 0),
            country_pop,
            _is_collision(asciiname),
        ])
    return {
        "_schema": "v1.0 — world admin1 (states/provinces), US excluded. Rows: "
                   "[name, country_iso2, canonical_code, member_city_population_sum, "
                   "country_population, word_collision]",
        "_source": f"{_ATTRIBUTION} — admin1CodesASCII.txt",
        "admin1": rows,
    }


def build_cities(cities_zip: Path, min_population: int) -> dict:
    txt_name = cities_zip.stem + ".txt"
    with zipfile.ZipFile(cities_zip) as zf:
        raw = zf.read(txt_name).decode("utf-8")
    rows: list[list] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 15:
            continue
        asciiname = parts[2]
        feature_class = parts[6]
        country = parts[8]
        admin1 = parts[10]
        population = int(parts[14]) if parts[14].isdigit() else 0
        if feature_class != "P" or not asciiname or population < min_population:
            continue
        aliases = []
        for alias, (target, cc) in _CITY_ALIASES.items():
            if asciiname == target and country == cc:
                aliases.append(alias)
        rows.append([
            asciiname,
            country,
            admin1,
            population,
            _is_collision(asciiname),
            aliases,
        ])
    rows.sort(key=lambda r: -r[3])
    return {
        "_schema": "v1.0 — world cities (population ≥ min). Rows: "
                   "[asciiname, country_iso2, geonames_admin1_code, population, word_collision, aliases]",
        "_source": f"{_ATTRIBUTION} — cities15000.zip",
        "cities": rows,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Build world gazetteer JSONs from GeoNames dumps")
    p.add_argument("--min-population", type=int, default=15000)
    p.add_argument("--skip-download", action="store_true", help="reuse cached dumps")
    p.add_argument("--out-dir", default=str(_OUT_DIR))
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        country_info = _download("countryInfo.txt", skip_download=args.skip_download)
        admin1_file = _download("admin1CodesASCII.txt", skip_download=args.skip_download)
        cities_zip = _download("cities15000.zip", skip_download=args.skip_download)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: GeoNames download failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    countries = build_countries(country_info)
    cities = build_cities(cities_zip, args.min_population)

    # Resolve each city's admin1 code → canonical (ISO for CA/AU, readable name otherwise)
    code_map: dict[tuple[str, str], str] = {}
    for line in admin1_file.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 4 or "." not in parts[0]:
            continue
        country, gcode = parts[0].split(".", 1)
        code_map[(country, gcode)] = _iso_admin1_canonical(country, parts[2], gcode)
    for row in cities["cities"]:
        row[2] = code_map.get((row[1], row[2]), row[2] or "")

    # Aggregate member-city population per admin1 → the province size proxy
    admin1_city_pop: dict[tuple[str, str], int] = {}
    for name, country, admin1_code, pop, _coll, _aliases in cities["cities"]:
        key = (country, admin1_code)
        admin1_city_pop[key] = admin1_city_pop.get(key, 0) + pop

    admin1 = build_admin1(admin1_file, countries, admin1_city_pop)

    (out_dir / "world_countries.json").write_text(
        json.dumps(countries, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "world_admin1.json").write_text(
        json.dumps(admin1, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "world_cities.json").write_text(
        json.dumps(cities, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"world_countries.json: {len(countries['countries'])} countries")
    print(f"world_admin1.json:    {len(admin1['admin1'])} admin1 rows")
    print(f"world_cities.json:    {len(cities['cities'])} cities (pop ≥ {args.min_population})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
