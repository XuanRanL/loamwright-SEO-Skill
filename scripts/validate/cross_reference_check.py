"""scripts/validate/cross_reference_check.py — Independent corroboration check.

Second-pass verification: for each critical numeric claim, check whether ≥1 INDEPENDENT
source corroborates it. "Independent" = different domain + different publisher.

Reduces single-source risk + adds trust through redundancy.

Used by `agents/fact-checker.md` Phase 3 (after primary citation verified).

Process:
  1. Extract critical claims from citations.json (numeric + has citation)
  2. For each, do an INDEPENDENT Tavily search excluding the primary source domain
  3. Look for the same/similar claim in different source
  4. Tag corroboration status

CLI:
    python -m scripts.validate.cross_reference_check \
        --citations workspace/{task}/citations.json \
        --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scripts._core import credential_hub, cost_ledger


@dataclass
class CrossRefResult:
    claim_id: str
    primary_source_url: str
    primary_source_domain: str
    primary_value: str
    corroborated: bool = False
    corroborating_urls: list[str] = field(default_factory=list)
    corroborating_domains: list[str] = field(default_factory=list)
    search_query_used: str = ""
    status: str = ""        # corroborated | single_source | conflicting | search_failed
    cost_usd: str = "0.0000"


@dataclass
class CrossRefReport:
    citations_input: str
    total_claims_with_value: int = 0
    corroborated_claims: int = 0
    single_source_claims: int = 0
    conflicting_claims: int = 0
    search_failed: int = 0
    total_cost_usd: str = "0.0000"
    results: list[CrossRefResult] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    overall_pass: bool = True


def _extract_domain(url: str) -> str:
    """Get bare domain from URL."""
    from urllib.parse import urlparse
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc.replace("www.", "")
    except Exception:
        return ""


def _value_to_search_term(value: str) -> str:
    """Convert numeric value (e.g., "73%") to searchable phrase."""
    if "%" in value:
        return value
    if value.startswith("$"):
        return value
    return value


def _claim_to_search_query(claim_text: str, value: str) -> str:
    """Build search query to find corroborating source."""
    cleaned = re.sub(r"\([^)]*\)", "", claim_text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words = cleaned.split()
    keywords = [w for w in words[:25] if len(w) > 3 and w[0].isalpha()]
    query_parts = keywords[:10]
    if value not in " ".join(query_parts):
        query_parts.append(value)
    return " ".join(query_parts)


def cross_check_claim(
    claim_id: str,
    claim_text: str,
    value: str,
    primary_source_url: str,
    *,
    tavily_excluded_domain: str | None = None,
    timeout: float = 30.0,
) -> CrossRefResult:
    """Search for independent corroboration of one claim."""
    result = CrossRefResult(
        claim_id=claim_id,
        primary_source_url=primary_source_url,
        primary_source_domain=_extract_domain(primary_source_url),
        primary_value=value,
    )

    if tavily_excluded_domain is None:
        tavily_excluded_domain = result.primary_source_domain

    query = _claim_to_search_query(claim_text, value)
    result.search_query_used = query

    try:
        import httpx

        from scripts._core.tavily_retry import with_retry

        def _do_search(api_key: str) -> dict[str, Any]:
            params: dict[str, object] = {
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": 8,
                "include_answer": False,
            }
            if tavily_excluded_domain:
                params["exclude_domains"] = [tavily_excluded_domain]
            r = httpx.post(
                "https://api.tavily.com/search",
                json=params,
                timeout=timeout,
            )
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]

        # Route every Tavily call through with_retry so a per-minute 429 / timeout
        # rotates to the next pool key instead of failing the whole corroboration.
        # The balance-aware pool's resilience must cover EVERY call site, not just
        # the fetch/ scripts — a raw one-key httpx.post here silently degraded
        # fact-checking under the parallel-session bursts the pool exists to serve
        # (Rule 7). get_key resolves+rotates the pool; CredentialNotFoundError
        # surfaces as the search_failed path below.
        data = with_retry(
            _do_search,
            get_key=credential_hub.get_tavily_key,
            label="cross_ref",
        )

        try:
            est_cost = cost_ledger.estimate("tavily", tavily_calls_advanced=1)
            result.cost_usd = str(est_cost.estimated_usd)
            cost_ledger.log(
                est_cost, model="tavily", endpoint="search/cross-reference",
                task_id=claim_id,
            )
        except Exception:
            pass

        corroborating_urls: list[str] = []
        corroborating_domains: list[str] = []

        for item in data.get("results", []) or []:
            url = item.get("url", "")
            content = item.get("content", "")
            domain = _extract_domain(url)

            if not domain or domain == tavily_excluded_domain:
                continue

            value_search = _value_to_search_term(value)
            if value_search.lower() in content.lower():
                corroborating_urls.append(url)
                corroborating_domains.append(domain)
                if len(corroborating_urls) >= 3:
                    break

        result.corroborating_urls = corroborating_urls
        result.corroborating_domains = list(set(corroborating_domains))
        result.corroborated = len(corroborating_urls) >= 1

        if result.corroborated:
            result.status = "corroborated"
        else:
            result.status = "single_source"

    except Exception:
        # with_retry has already exhausted rotation across the pool by here, or a
        # non-transient error occurred — either way this claim is uncorroborated.
        result.status = "search_failed"

    return result


def cross_reference_citations(
    citations_path: Path,
    *,
    skip_already_corroborated: bool = True,
    max_claims_to_check: int = 20,
) -> CrossRefReport:
    """Run cross-reference check on all citations in a citations.json file."""
    if not citations_path.exists():
        raise FileNotFoundError(citations_path)

    data = json.loads(citations_path.read_text(encoding="utf-8"))
    references = data.get("references", []) or []

    report = CrossRefReport(citations_input=str(citations_path))
    total_cost = 0.0

    claims_to_check = []
    for i, ref in enumerate(references[:max_claims_to_check]):
        url = ref.get("url", "")
        if not url:
            continue
        claim_text = ref.get("apa", "") or ref.get("claim", "")
        value_match = re.search(r"\b(\d+\.?\d*%|\d+x|\$\d+(?:,\d{3})*(?:\.\d+)?)\b", claim_text)
        if not value_match:
            continue
        claims_to_check.append({
            "id": ref.get("id", f"ref-{i}"),
            "claim_text": claim_text,
            "value": value_match.group(1),
            "url": url,
        })

    report.total_claims_with_value = len(claims_to_check)

    for claim in claims_to_check:
        result = cross_check_claim(
            claim["id"], claim["claim_text"], claim["value"], claim["url"],
        )
        report.results.append(result)
        try:
            total_cost += float(result.cost_usd)
        except (ValueError, TypeError):
            pass

        if result.status == "corroborated":
            report.corroborated_claims += 1
        elif result.status == "single_source":
            report.single_source_claims += 1
        elif result.status == "conflicting":
            report.conflicting_claims += 1
        else:
            report.search_failed += 1

        time.sleep(0.5)

    report.total_cost_usd = f"{total_cost:.4f}"

    if report.total_claims_with_value > 0:
        corroboration_rate = report.corroborated_claims / report.total_claims_with_value
        if corroboration_rate < 0.5:
            report.recommendations.append(
                f"⚠ Only {corroboration_rate:.0%} of claims have independent corroboration. "
                f"Single-source risk is high. Consider adding ≥1 alternate source per critical claim."
            )
            report.overall_pass = False
        elif corroboration_rate < 0.75:
            report.recommendations.append(
                f"~ {corroboration_rate:.0%} corroboration rate is acceptable but improvable."
            )

    if report.single_source_claims > 0:
        single_source_ids = [r.claim_id for r in report.results if r.status == "single_source"][:5]
        report.recommendations.append(
            f"Single-source claims to corroborate: {', '.join(single_source_ids)}"
        )

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Independent source corroboration check")
    ap.add_argument("--citations", type=Path, required=True,
                    help="Path to citations.json")
    ap.add_argument("--max-claims", type=int, default=20,
                    help="Max claims to check (cost control)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        report = cross_reference_citations(args.citations, max_claims_to_check=args.max_claims)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    else:
        icon = "✓" if report.overall_pass else "⚠"
        print(f"{icon} Cross-reference check")
        print(f"  Citations analyzed: {report.total_claims_with_value}")
        print(f"  Corroborated:       {report.corroborated_claims}")
        print(f"  Single source:      {report.single_source_claims}")
        print(f"  Conflicting:        {report.conflicting_claims}")
        print(f"  Search failed:      {report.search_failed}")
        print(f"  Cost:               ${report.total_cost_usd}")
        if report.recommendations:
            print()
            for r in report.recommendations:
                print(f"  • {r}")
    return 0 if report.overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
