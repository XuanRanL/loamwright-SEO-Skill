"""Business type detection from homepage HTML.

Analyzes homepage HTML to classify a website's business type by scoring
signal patterns (URL paths, text keywords, schema.org types, platform markers).

Usage:
    python -m scripts.audit.business_type_detector homepage.html --json
    curl -s https://example.com | python -m scripts.audit.business_type_detector --url https://example.com
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from bs4 import BeautifulSoup, Tag
except ImportError as exc:
    raise SystemExit(
        "beautifulsoup4 is required: pip install beautifulsoup4 lxml"
    ) from exc


# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------

BUSINESS_TYPES = (
    "saas",
    "ecommerce",
    "local_brick_mortar",
    "local_sab",
    "local_hybrid",
    "publisher",
    "agency",
    "other",
)

CONFIDENCE_THRESHOLD = 3  # minimum signals to claim a type


@dataclass
class DetectionResult:
    """Output payload for the detector."""

    primary_type: str
    confidence: float
    secondary_type: str | None
    signals: dict[str, list[str]]
    platform: str | None
    conditional_agents: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_type": self.primary_type,
            "confidence": self.confidence,
            "secondary_type": self.secondary_type,
            "signals": self.signals,
            "platform": self.platform,
            "conditional_agents": self.conditional_agents,
        }


@dataclass
class _ScoreBoard:
    """Accumulates signal hits per business type."""

    scores: dict[str, list[str]] = field(default_factory=lambda: {t: [] for t in BUSINESS_TYPES})

    def add(self, btype: str, signal: str) -> None:
        self.scores[btype].append(signal)

    def count(self, btype: str) -> int:
        return len(self.scores[btype])


# ---------------------------------------------------------------------------
# Signal definitions
# ---------------------------------------------------------------------------

# URL path fragments (checked against href attributes of internal links)
_URL_SIGNALS: dict[str, list[tuple[str, str]]] = {
    "saas": [
        ("/pricing", "pricing_page_link"),
        ("/features", "features_page_link"),
        ("/integrations", "integrations_page_link"),
        ("/docs", "docs_page_link"),
        ("/documentation", "documentation_page_link"),
        ("/api", "api_page_link"),
        ("/changelog", "changelog_page_link"),
        ("/signup", "signup_page_link"),
        ("/sign-up", "signup_page_link"),
        ("/register", "register_page_link"),
        ("/demo", "demo_page_link"),
    ],
    "ecommerce": [
        ("/products", "products_page_link"),
        ("/collections", "collections_page_link"),
        ("/cart", "cart_link"),
        ("/shop", "shop_page_link"),
        ("/store", "store_page_link"),
        ("/checkout", "checkout_page_link"),
        ("/account", "account_page_link"),
        ("/wishlist", "wishlist_page_link"),
    ],
    "local_brick_mortar": [
        ("/contact", "contact_page_link"),
        ("/directions", "directions_page_link"),
        ("/locations", "locations_page_link"),
        ("/hours", "hours_page_link"),
        ("/about-us", "about_us_page_link"),
    ],
    "local_sab": [
        ("/service-area", "service_area_page_link"),
        ("/areas-served", "areas_served_page_link"),
        ("/service-areas", "service_areas_page_link"),
        ("/coverage", "coverage_page_link"),
    ],
    "publisher": [
        ("/blog", "blog_page_link"),
        ("/articles", "articles_page_link"),
        ("/topics", "topics_page_link"),
        ("/category", "category_page_link"),
        ("/categories", "categories_page_link"),
        ("/author", "author_page_link"),
        ("/authors", "authors_page_link"),
        ("/archive", "archive_page_link"),
        ("/news", "news_page_link"),
        ("/editorial", "editorial_page_link"),
    ],
    "agency": [
        ("/case-studies", "case_studies_page_link"),
        ("/case-study", "case_study_page_link"),
        ("/portfolio", "portfolio_page_link"),
        ("/our-work", "our_work_page_link"),
        ("/work", "work_page_link"),
        ("/clients", "clients_page_link"),
        ("/industries", "industries_page_link"),
        ("/services", "services_page_link"),
        ("/team", "team_page_link"),
        ("/about", "about_page_link"),
    ],
}

# Text content patterns (case-insensitive regex, checked against visible text)
_TEXT_SIGNALS: dict[str, list[tuple[str, str]]] = {
    "saas": [
        (r"\bfree\s+trial\b", "free_trial_text"),
        (r"\bsign\s+up\b", "sign_up_text"),
        (r"\bstart\s+free\b", "start_free_text"),
        (r"\bsaas\b", "saas_mention"),
        (r"\bper\s+month\b", "per_month_pricing"),
        (r"\b/mo\b", "monthly_pricing_shorthand"),
        (r"\bper\s+user\b", "per_user_pricing"),
        (r"\bapi\s+key\b", "api_key_text"),
        (r"\bcloud[\s-]based\b", "cloud_based_text"),
        (r"\bget\s+started\b", "get_started_text"),
        (r"\bonboarding\b", "onboarding_text"),
    ],
    "ecommerce": [
        (r"\badd\s+to\s+cart\b", "add_to_cart_text"),
        (r"\bbuy\s+now\b", "buy_now_text"),
        (r"\bshop\s+now\b", "shop_now_text"),
        (r"\bfree\s+shipping\b", "free_shipping_text"),
        (r"\$\d+\.\d{2}\b", "price_dollar_format"),
        (r"\bshopping\s+cart\b", "shopping_cart_text"),
        (r"\bproduct\s+reviews?\b", "product_reviews_text"),
        (r"\bin\s+stock\b", "in_stock_text"),
        (r"\bout\s+of\s+stock\b", "out_of_stock_text"),
        (r"\bsku\b", "sku_mention"),
    ],
    "local_brick_mortar": [
        (r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "phone_number"),
        (r"\b\d{5}(?:-\d{4})?\b", "zip_code"),
        (r"\bopening\s+hours\b", "opening_hours_text"),
        (r"\bbusiness\s+hours\b", "business_hours_text"),
        (r"\bvisit\s+us\b", "visit_us_text"),
        (r"\bour\s+location\b", "our_location_text"),
        (r"\bwalk[\s-]?ins?\s+welcome\b", "walk_ins_welcome"),
        (r"\bparking\s+available\b", "parking_available"),
        (r"\bserving\s+\w+", "serving_city_text"),
        (r"\bcome\s+see\s+us\b", "come_see_us_text"),
    ],
    "local_sab": [
        (r"\bwe\s+serve\b", "we_serve_text"),
        (r"\bservice\s+area\b", "service_area_text"),
        (r"\bmile\s+radius\b", "mile_radius_text"),
        (r"\bserving\s+the\s+greater\b", "serving_greater_area"),
        (r"\bcoverage\s+area\b", "coverage_area_text"),
        (r"\bareas?\s+we\s+serve\b", "areas_we_serve_text"),
        (r"\bno\s+storefront\b", "no_storefront_text"),
        (r"\bmobile\s+service\b", "mobile_service_text"),
        (r"\bwe\s+come\s+to\s+you\b", "we_come_to_you_text"),
    ],
    "publisher": [
        (r"\beditorial\b", "editorial_text"),
        (r"\bpublished\s+on\b", "published_on_text"),
        (r"\bby\s+[A-Z][a-z]+\s+[A-Z][a-z]+", "byline_pattern"),
        (r"\bread\s+more\b", "read_more_text"),
        (r"\bmin\s+read\b", "min_read_text"),
        (r"\bsubscribe\b", "subscribe_text"),
        (r"\bnewsletter\b", "newsletter_text"),
        (r"\blatest\s+articles?\b", "latest_articles_text"),
        (r"\brecent\s+posts?\b", "recent_posts_text"),
    ],
    "agency": [
        (r"\bcase\s+stud(?:y|ies)\b", "case_study_text"),
        (r"\bour\s+clients?\b", "our_clients_text"),
        (r"\bindustries\s+we\s+serve\b", "industries_we_serve_text"),
        (r"\bfull[\s-]service\b", "full_service_text"),
        (r"\bcustom\s+solutions?\b", "custom_solutions_text"),
        (r"\btailored\b", "tailored_text"),
        (r"\bstrategic\s+partner\b", "strategic_partner_text"),
        (r"\bresults[\s-]driven\b", "results_driven_text"),
        (r"\bROI\b", "roi_mention"),
        (r"\bclient\s+testimonials?\b", "client_testimonials_text"),
    ],
}

# Schema.org type patterns (checked against JSON-LD and microdata)
_SCHEMA_SIGNALS: dict[str, list[tuple[str, str]]] = {
    "saas": [
        ("SoftwareApplication", "software_application_schema"),
        ("WebApplication", "web_application_schema"),
        ("APIReference", "api_reference_schema"),
    ],
    "ecommerce": [
        ("Product", "product_schema_found"),
        ("Offer", "offer_schema_found"),
        ("ItemList", "item_list_schema"),
        ("AggregateOffer", "aggregate_offer_schema"),
        ("ShoppingCenter", "shopping_center_schema"),
    ],
    "local_brick_mortar": [
        ("LocalBusiness", "local_business_schema"),
        ("Restaurant", "restaurant_schema"),
        ("Store", "store_schema"),
        ("PostalAddress", "postal_address_schema"),
        ("GeoCoordinates", "geo_coordinates_schema"),
        ("OpeningHoursSpecification", "opening_hours_schema"),
    ],
    "local_sab": [
        ("Service", "service_schema"),
        ("ServiceArea", "service_area_schema"),
        ("HomeAndConstructionBusiness", "home_construction_schema"),
        ("ProfessionalService", "professional_service_schema"),
    ],
    "publisher": [
        ("Article", "article_schema"),
        ("NewsArticle", "news_article_schema"),
        ("BlogPosting", "blog_posting_schema"),
        ("MediaObject", "media_object_schema"),
        ("Person", "person_schema"),
    ],
    "agency": [
        ("ProfessionalService", "professional_service_schema"),
        ("Organization", "organization_schema"),
    ],
}

# Platform markers (checked in HTML source)
_PLATFORM_MARKERS: list[tuple[str, str, str | None]] = [
    # (pattern, platform_name, associated_type_or_None)
    (r"cdn\.shopify\.com", "shopify", "ecommerce"),
    (r"myshopify\.com", "shopify", "ecommerce"),
    (r"Shopify\.theme", "shopify", "ecommerce"),
    (r"woocommerce", "woocommerce", "ecommerce"),
    (r"wc-block", "woocommerce", "ecommerce"),
    (r"wp-content", "wordpress", None),
    (r"wp-includes", "wordpress", None),
    (r"squarespace", "squarespace", None),
    (r"webflow\.com", "webflow", None),
    (r"wix\.com", "wix", None),
    (r"bigcommerce", "bigcommerce", "ecommerce"),
    (r"magento", "magento", "ecommerce"),
    (r"prestashop", "prestashop", "ecommerce"),
    (r"ghost\.io", "ghost", "publisher"),
    (r"substack\.com", "substack", "publisher"),
    (r"medium\.com", "medium", "publisher"),
    (r"hubspot", "hubspot", "saas"),
    (r"intercom", "intercom", "saas"),
    (r"stripe", "stripe", "saas"),
]


# ---------------------------------------------------------------------------
# Detection engine
# ---------------------------------------------------------------------------


def _extract_internal_links(soup: BeautifulSoup, base_url: str | None) -> list[str]:
    """Extract href paths from internal anchor tags."""
    hrefs: list[str] = []
    for a_tag in soup.find_all("a", href=True):
        href: str = a_tag["href"]
        # Relative paths are always internal
        if href.startswith("/"):
            hrefs.append(href.lower())
        elif base_url and href.startswith(base_url):
            # Strip the base URL to get the path
            path = href[len(base_url):]
            if not path.startswith("/"):
                path = "/" + path
            hrefs.append(path.lower())
        elif href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        elif not href.startswith("http"):
            # Relative without leading slash
            hrefs.append("/" + href.lower())
    return hrefs


def _check_url_signals(hrefs: list[str], board: _ScoreBoard) -> None:
    """Score URL path signals."""
    for btype, patterns in _URL_SIGNALS.items():
        for path_fragment, signal_name in patterns:
            for href in hrefs:
                if path_fragment in href:
                    board.add(btype, signal_name)
                    break  # one hit per signal is enough


def _check_text_signals(text: str, board: _ScoreBoard) -> None:
    """Score text content signals via regex."""
    for btype, patterns in _TEXT_SIGNALS.items():
        for regex, signal_name in patterns:
            if re.search(regex, text, re.IGNORECASE):
                board.add(btype, signal_name)


def _check_schema_signals(soup: BeautifulSoup, board: _ScoreBoard) -> None:
    """Score schema.org type signals from JSON-LD and microdata."""
    # JSON-LD
    jsonld_text = ""
    for script in soup.find_all("script", type="application/ld+json"):
        content = script.string or ""
        jsonld_text += content

    # Microdata (itemtype attributes)
    microdata_types: list[str] = []
    for elem in soup.find_all(attrs={"itemtype": True}):
        itemtype = elem.get("itemtype", "")
        if isinstance(itemtype, str):
            microdata_types.append(itemtype)

    combined = jsonld_text + " ".join(microdata_types)

    for btype, patterns in _SCHEMA_SIGNALS.items():
        for schema_type, signal_name in patterns:
            if schema_type in combined:
                board.add(btype, signal_name)


def _check_platform_markers(html_source: str, board: _ScoreBoard) -> str | None:
    """Detect platform markers and score associated business types."""
    detected_platform: str | None = None
    for regex, platform_name, associated_type in _PLATFORM_MARKERS:
        if re.search(regex, html_source, re.IGNORECASE):
            if detected_platform is None:
                detected_platform = platform_name
            if associated_type:
                board.add(associated_type, f"{platform_name}_marker")
    return detected_platform


def _check_special_signals(soup: BeautifulSoup, html_source: str, board: _ScoreBoard) -> None:
    """Check for special signals that don't fit neatly into other categories."""
    # Google Maps embed → local
    iframes = soup.find_all("iframe")
    for iframe in iframes:
        src = iframe.get("src", "")
        if isinstance(src, str) and "google.com/maps" in src:
            board.add("local_brick_mortar", "google_maps_embed")
            break

    # RSS feed link → publisher
    rss_link = soup.find("link", type="application/rss+xml")
    if rss_link:
        board.add("publisher", "rss_feed_link")
    atom_link = soup.find("link", type="application/atom+xml")
    if atom_link:
        board.add("publisher", "atom_feed_link")

    # Pricing table patterns → saas
    pricing_tables = soup.find_all(class_=re.compile(r"pricing|plan", re.IGNORECASE))
    if pricing_tables:
        board.add("saas", "pricing_table_elements")

    # Article date patterns → publisher
    time_elements = soup.find_all("time")
    if len(time_elements) >= 3:
        board.add("publisher", "article_dates")

    # Address tag → local
    address_tags = soup.find_all("address")
    if address_tags:
        board.add("local_brick_mortar", "address_html_element")

    # Client logo grid patterns → agency
    logo_sections = soup.find_all(
        class_=re.compile(r"client|partner|logo|trust", re.IGNORECASE)
    )
    if logo_sections:
        board.add("agency", "client_logo_section")

    # Meta generator tag
    meta_gen = soup.find("meta", attrs={"name": "generator"})
    if meta_gen and isinstance(meta_gen, Tag):
        gen_content = str(meta_gen.get("content", "")).lower()
        if "wordpress" in gen_content:
            # WordPress alone doesn't signal a type but is platform info
            pass
        if "ghost" in gen_content:
            board.add("publisher", "ghost_generator_meta")


def _resolve_local_hybrid(board: _ScoreBoard) -> None:
    """Promote to local_hybrid if both brick_mortar and SAB signals present."""
    bm_count = board.count("local_brick_mortar")
    sab_count = board.count("local_sab")
    if bm_count >= 2 and sab_count >= 2:
        # Merge signals into local_hybrid
        for signal in board.scores["local_brick_mortar"]:
            board.add("local_hybrid", signal)
        for signal in board.scores["local_sab"]:
            board.add("local_hybrid", signal)


def _determine_conditional_agents(
    primary: str,
    secondary: str | None,
    all_signals: dict[str, list[str]],
) -> list[str]:
    """Map detected types to conditional audit agents."""
    agents: list[str] = []

    # Local types → audit-local
    local_types = {"local_brick_mortar", "local_sab", "local_hybrid"}
    if primary in local_types or (secondary and secondary in local_types):
        agents.append("audit-local")
        # If dataforseo could be available, also spawn audit-maps
        agents.append("audit-maps")

    # Ecommerce → audit-ecommerce
    if primary == "ecommerce" or secondary == "ecommerce":
        agents.append("audit-ecommerce")

    # Publisher OR has /blog signals → audit-cluster
    has_blog_signal = any(
        "blog" in s for s in all_signals.get("publisher", [])
    )
    if primary == "publisher" or secondary == "publisher" or has_blog_signal:
        agents.append("audit-cluster")

    # Always include audit-backlinks (Common Crawl is free)
    agents.append("audit-backlinks")

    return agents


def detect_business_type(
    html: str,
    base_url: str | None = None,
) -> DetectionResult:
    """Analyze HTML and classify the website's business type.

    Args:
        html: Raw HTML content of the homepage.
        base_url: Optional base URL for resolving relative links.

    Returns:
        DetectionResult with primary type, confidence, and signals.
    """
    soup = BeautifulSoup(html, "lxml" if _has_lxml() else "html.parser")
    board = _ScoreBoard()

    # Extract data
    hrefs = _extract_internal_links(soup, base_url)
    visible_text = soup.get_text(separator=" ", strip=True)

    # Run all signal checks
    _check_url_signals(hrefs, board)
    _check_text_signals(visible_text, board)
    _check_schema_signals(soup, board)
    _check_platform_markers(html, board)
    _check_special_signals(soup, html, board)

    # Resolve local hybrid case
    _resolve_local_hybrid(board)

    # Determine platform
    platform = _check_platform_markers(html, _ScoreBoard())  # re-run for clean extraction

    # Rank types by signal count
    ranked = sorted(
        [(t, board.count(t)) for t in BUSINESS_TYPES if t != "other"],
        key=lambda x: x[1],
        reverse=True,
    )

    # Primary type
    if ranked and ranked[0][1] >= CONFIDENCE_THRESHOLD:
        primary_type = ranked[0][0]
        primary_count = ranked[0][1]
    else:
        primary_type = "other"
        primary_count = 0

    # Secondary type
    secondary_type: str | None = None
    if len(ranked) >= 2 and ranked[1][1] >= CONFIDENCE_THRESHOLD:
        secondary_type = ranked[1][0]

    # Confidence: normalized score (signals found / max possible for that type)
    max_possible = _max_signals_for_type(primary_type)
    if max_possible > 0 and primary_count > 0:
        confidence = round(min(primary_count / max_possible, 1.0), 2)
    else:
        confidence = 0.0

    # Build filtered signals dict (only types that scored)
    all_signals: dict[str, list[str]] = {}
    for btype, signals in board.scores.items():
        if signals:
            # Deduplicate while preserving order
            seen: set[str] = set()
            unique: list[str] = []
            for s in signals:
                if s not in seen:
                    seen.add(s)
                    unique.append(s)
            all_signals[btype] = unique

    # Conditional agents
    conditional_agents = _determine_conditional_agents(primary_type, secondary_type, all_signals)

    return DetectionResult(
        primary_type=primary_type,
        confidence=confidence,
        secondary_type=secondary_type,
        signals=all_signals,
        platform=platform,
        conditional_agents=conditional_agents,
    )


def _max_signals_for_type(btype: str) -> int:
    """Return the theoretical maximum signals detectable for a type."""
    total = 0
    if btype in _URL_SIGNALS:
        total += len(_URL_SIGNALS[btype])
    if btype in _TEXT_SIGNALS:
        total += len(_TEXT_SIGNALS[btype])
    if btype in _SCHEMA_SIGNALS:
        total += len(_SCHEMA_SIGNALS[btype])
    # Platform markers contribute at most 1-2 per type
    for _, _, associated in _PLATFORM_MARKERS:
        if associated == btype:
            total += 1
    # Special signals (estimate 2-3 per type)
    total += 2
    return max(total, 1)


def _has_lxml() -> bool:
    """Check if lxml parser is available."""
    try:
        import lxml  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="business_type_detector",
        description="Detect business type from homepage HTML.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=None,
        help="Path to HTML file (reads stdin if omitted).",
    )
    parser.add_argument(
        "--url", "-u",
        type=str,
        default=None,
        help="Base URL of the site (for resolving relative links).",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=True,
        help="Output as JSON (default).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Show all signal matches in output.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Read HTML input
    if args.file is not None:
        file_path: Path = args.file
        if not file_path.exists():
            print(f"Error: file not found: {file_path}", file=sys.stderr)
            return 1
        html = file_path.read_text(encoding="utf-8", errors="replace")
    else:
        if sys.stdin.isatty():
            print("Error: no file argument and stdin is a TTY. Pipe HTML or pass a file path.", file=sys.stderr)
            return 1
        html = sys.stdin.read()

    # Normalize base URL
    base_url = args.url.rstrip("/") if args.url else None

    # Run detection
    result = detect_business_type(html, base_url=base_url)

    # Format output
    output = result.to_dict()
    if not args.verbose:
        # In non-verbose mode, only show signals for primary and secondary
        filtered_signals: dict[str, list[str]] = {}
        if result.primary_type in output["signals"]:
            filtered_signals[result.primary_type] = output["signals"][result.primary_type]
        if result.secondary_type and result.secondary_type in output["signals"]:
            filtered_signals[result.secondary_type] = output["signals"][result.secondary_type]
        output["signals"] = filtered_signals

    json_str = json.dumps(output, indent=2, ensure_ascii=False)
    print(json_str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
