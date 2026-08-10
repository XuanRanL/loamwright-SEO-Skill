#!/usr/bin/env python3
"""PageSpeed Insights v5 + CrUX API combined checker.

Ported from claude-seo (requests → httpx, google_auth → credential_hub).

Usage:
    python -m scripts.audit.pagespeed_check https://example.com
    python -m scripts.audit.pagespeed_check https://example.com --strategy mobile --json
    python -m scripts.audit.pagespeed_check https://example.com --crux-only
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from scripts._core.ssrf_guard import validate_url, SSRFError

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CRUX_ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"

CWV_THRESHOLDS: dict[str, dict[str, Any]] = {
    "largest_contentful_paint": {"good": 2500, "poor": 4000, "unit": "ms", "label": "LCP"},
    "interaction_to_next_paint": {"good": 200, "poor": 500, "unit": "ms", "label": "INP"},
    "cumulative_layout_shift": {"good": 0.1, "poor": 0.25, "unit": "", "label": "CLS"},
    "first_contentful_paint": {"good": 1800, "poor": 3000, "unit": "ms", "label": "FCP"},
    "experimental_time_to_first_byte": {"good": 800, "poor": 1800, "unit": "ms", "label": "TTFB"},
}

PSI_METRIC_MAP = {
    "LARGEST_CONTENTFUL_PAINT_MS": "largest_contentful_paint",
    "INTERACTION_TO_NEXT_PAINT": "interaction_to_next_paint",
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": "cumulative_layout_shift",
    "FIRST_CONTENTFUL_PAINT_MS": "first_contentful_paint",
    "EXPERIMENTAL_TIME_TO_FIRST_BYTE": "experimental_time_to_first_byte",
}


def _get_api_key(override: Optional[str] = None) -> Optional[str]:
    if override:
        return override
    try:
        from scripts._core.credential_hub import get_credential
        return get_credential("google_psi_api_key") or get_credential("google_api_key")
    except (ImportError, Exception):
        return None


def rate_metric(metric_name: str, value: float) -> str:
    thresholds = CWV_THRESHOLDS.get(metric_name)
    if not thresholds:
        return "unknown"
    if value <= thresholds["good"]:
        return "good"
    elif value <= thresholds["poor"]:
        return "needs-improvement"
    return "poor"


def run_pagespeed(
    url: str,
    strategy: str = "mobile",
    api_key: Optional[str] = None,
    categories: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Run PageSpeed Insights v5 analysis."""
    result: dict[str, Any] = {
        "url": url,
        "strategy": strategy,
        "lighthouse_scores": {},
        "lab_metrics": {},
        "field_metrics": {},
        "opportunities": [],
        "diagnostics": [],
        "failed_audits": [],
        "passed_audits_count": 0,
        "seo_audits": [],
        "accessibility_audits": [],
        "audit_details": {},
        "analysis_timestamp": None,
        "error": None,
    }

    try:
        validate_url(url, allow_http=True)
    except SSRFError as e:
        result["error"] = f"SSRF blocked: {e}"
        return result

    if categories is None:
        categories = ["PERFORMANCE", "ACCESSIBILITY", "BEST_PRACTICES", "SEO"]

    params: dict[str, Any] = {"url": url, "strategy": strategy.upper()}
    for cat in categories:
        params.setdefault("category", [])
        if isinstance(params["category"], list):
            params["category"].append(cat)
    if api_key:
        params["key"] = api_key

    try:
        resp = httpx.get(PSI_ENDPOINT, params=params, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        result["error"] = "PageSpeed Insights request timed out (120s)."
        return result
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            result["error"] = "PSI rate limit exceeded (240 QPM / 25K QPD). Wait and retry."
        elif e.response.status_code == 400:
            result["error"] = f"Invalid URL or parameters: {e.response.text[:200]}"
        else:
            result["error"] = f"PSI API error {e.response.status_code}"
        return result
    except httpx.HTTPError as e:
        result["error"] = f"Request failed: {e}"
        return result

    result["analysis_timestamp"] = data.get("analysisUTCTimestamp")

    lr = data.get("lighthouseResult", {})
    for cat_key, cat_data in lr.get("categories", {}).items():
        result["lighthouse_scores"][cat_key] = round(cat_data.get("score", 0) * 100)

    audits = lr.get("audits", {})
    for audit_id in ["first-contentful-paint", "largest-contentful-paint",
                     "total-blocking-time", "cumulative-layout-shift",
                     "speed-index", "interactive"]:
        audit = audits.get(audit_id, {})
        if audit.get("numericValue") is not None:
            result["lab_metrics"][audit_id] = {
                "value": audit["numericValue"],
                "display": audit.get("displayValue", ""),
                "score": audit.get("score"),
            }

    for exp_key in ["loadingExperience", "originLoadingExperience"]:
        exp = data.get(exp_key, {})
        metrics = exp.get("metrics", {})
        if metrics:
            field_source = "url" if exp_key == "loadingExperience" else "origin"
            for psi_name, crux_name in PSI_METRIC_MAP.items():
                metric_data = metrics.get(psi_name, {})
                if metric_data:
                    p75 = metric_data.get("percentile")
                    category = metric_data.get("category", "NONE")
                    if p75 is not None:
                        p75_val = p75 / 100 if crux_name == "cumulative_layout_shift" and p75 > 1 else p75
                        result["field_metrics"][f"{field_source}_{crux_name}"] = {
                            "p75": p75_val,
                            "rating": category.lower().replace("_", "-"),
                            "source": f"PSI {field_source}-level",
                        }

    for audit_id, audit in audits.items():
        if audit.get("details", {}).get("type") == "opportunity":
            savings = audit.get("details", {}).get("overallSavingsMs")
            if savings and savings > 0:
                result["opportunities"].append({
                    "id": audit_id,
                    "title": audit.get("title", audit_id),
                    "savings_ms": savings,
                    "description": audit.get("description", ""),
                })
    result["opportunities"].sort(key=lambda x: x["savings_ms"], reverse=True)

    diagnostic_ids = [
        "dom-size", "render-blocking-resources", "uses-long-cache-ttl",
        "total-byte-weight", "mainthread-work-breakdown", "bootup-time",
        "font-display", "third-party-summary", "largest-contentful-paint-element",
        "layout-shifts", "long-tasks", "duplicated-javascript",
        "legacy-javascript", "unused-javascript", "unused-css-rules",
    ]
    for diag_id in diagnostic_ids:
        audit = audits.get(diag_id, {})
        if audit:
            result["diagnostics"].append({
                "id": diag_id,
                "title": audit.get("title", diag_id),
                "display": audit.get("displayValue", ""),
                "score": audit.get("score"),
                "description": audit.get("description", ""),
            })

    opportunity_ids = {o["id"] for o in result["opportunities"]}
    passed_count = 0
    for audit_id, audit in audits.items():
        score = audit.get("score")
        if score is None:
            continue
        if score >= 0.9:
            passed_count += 1
            continue
        if audit_id in opportunity_ids:
            continue
        result["failed_audits"].append({
            "id": audit_id, "title": audit.get("title", audit_id),
            "score": score, "display": audit.get("displayValue", ""),
        })
    result["passed_audits_count"] = passed_count
    result["failed_audits"].sort(key=lambda x: x.get("score", 1))

    seo_cat = lr.get("categories", {}).get("seo", {})
    for ref in seo_cat.get("auditRefs", []):
        audit = audits.get(ref.get("id"), {})
        if audit and audit.get("score") is not None:
            result["seo_audits"].append({
                "id": ref["id"], "title": audit.get("title", ref["id"]),
                "score": audit["score"], "pass": audit["score"] >= 0.9,
            })

    a11y_cat = lr.get("categories", {}).get("accessibility", {})
    for ref in a11y_cat.get("auditRefs", []):
        audit = audits.get(ref.get("id"), {})
        if audit and audit.get("score") is not None and audit["score"] < 0.9:
            result["accessibility_audits"].append({
                "id": ref["id"], "title": audit.get("title", ref["id"]),
                "score": audit["score"], "display": audit.get("displayValue", ""),
            })

    for audit_id, audit in audits.items():
        details = audit.get("details", {})
        items = details.get("items", [])
        headings = details.get("headings", [])
        if items and headings:
            heading_keys = [h.get("key", "") for h in headings if h.get("key")]
            extracted = []
            for item in items[:5]:
                row = {}
                for key in heading_keys:
                    val = item.get(key)
                    if isinstance(val, dict):
                        row[key] = val.get("url") or val.get("text") or str(val)[:200]
                    elif val is not None:
                        row[key] = val
                if row:
                    extracted.append(row)
            if extracted:
                result["audit_details"][audit_id] = {
                    "title": audit.get("title", audit_id),
                    "headings": heading_keys,
                    "items": extracted,
                    "total_items": len(items),
                }

    return result


def query_crux(
    url_or_origin: str,
    api_key: str,
    form_factor: Optional[str] = None,
) -> dict[str, Any]:
    """Query CrUX API for field data (28-day rolling average)."""
    result: dict[str, Any] = {
        "target": url_or_origin,
        "metrics": {},
        "collection_period": None,
        "form_factor": form_factor or "ALL",
        "error": None,
    }

    try:
        validate_url(url_or_origin, allow_http=True)
    except SSRFError as e:
        result["error"] = f"SSRF blocked: {e}"
        return result

    parsed = urlparse(url_or_origin)
    is_origin = parsed.path in ("", "/") and not parsed.query

    body: dict[str, Any] = {}
    if is_origin:
        body["origin"] = f"{parsed.scheme}://{parsed.netloc}"
    else:
        body["url"] = url_or_origin
    if form_factor:
        body["formFactor"] = form_factor.upper()

    try:
        resp = httpx.post(f"{CRUX_ENDPOINT}?key={api_key}", json=body, timeout=30)
        if resp.status_code == 404:
            target_type = "origin" if is_origin else "URL"
            result["error"] = f"No CrUX data for this {target_type}. Insufficient Chrome traffic."
            return result
        if resp.status_code == 429:
            result["error"] = "CrUX API rate limit exceeded (150 QPM). Wait and retry."
            return result
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        result["error"] = f"CrUX API request failed: {e}"
        return result

    record = data.get("record", {})
    cp = record.get("collectionPeriod", {})
    if cp:
        first = cp.get("firstDate", {})
        last = cp.get("lastDate", {})
        result["collection_period"] = {
            "first": f"{first.get('year')}-{first.get('month', 0):02d}-{first.get('day', 0):02d}",
            "last": f"{last.get('year')}-{last.get('month', 0):02d}-{last.get('day', 0):02d}",
        }

    for metric_name, metric_data in record.get("metrics", {}).items():
        p75s = metric_data.get("percentiles", {})
        p75 = p75s.get("p75")
        if p75 is None:
            continue

        if metric_name == "cumulative_layout_shift":
            try:
                p75_val = float(str(p75))
            except (ValueError, TypeError):
                p75_val = 0.0
        else:
            try:
                p75_val = int(p75)
            except (ValueError, TypeError):
                try:
                    p75_val = float(p75)
                except (ValueError, TypeError):
                    continue

        rating = rate_metric(metric_name, p75_val)
        thresholds = CWV_THRESHOLDS.get(metric_name, {})
        result["metrics"][metric_name] = {
            "p75": p75_val,
            "rating": rating,
            "label": thresholds.get("label", metric_name),
            "unit": thresholds.get("unit", ""),
            "good_threshold": thresholds.get("good"),
            "poor_threshold": thresholds.get("poor"),
        }

        histogram = metric_data.get("histogram", [])
        if histogram:
            densities = [b.get("density", 0) for b in histogram]
            if len(densities) >= 3:
                result["metrics"][metric_name]["distribution"] = {
                    "good": round(densities[0] * 100, 1),
                    "needs_improvement": round(densities[1] * 100, 1),
                    "poor": round(densities[2] * 100, 1),
                }

    return result


def combined_check(
    url: str,
    api_key: Optional[str] = None,
    strategy: str = "both",
) -> dict[str, Any]:
    """Run combined PSI + CrUX check."""
    result: dict[str, Any] = {"url": url, "psi": {}, "crux": None, "error": None}
    strategies = ["mobile", "desktop"] if strategy == "both" else [strategy]

    for strat in strategies:
        psi_result = run_pagespeed(url, strategy=strat, api_key=api_key)
        result["psi"][strat] = psi_result
        if psi_result.get("error"):
            result["error"] = psi_result["error"]

    if api_key:
        crux_result = query_crux(url, api_key)
        result["crux"] = crux_result
        if crux_result.get("error") and "insufficient" in crux_result.get("error", "").lower():
            parsed = urlparse(url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            origin_result = query_crux(origin, api_key)
            if not origin_result.get("error"):
                result["crux"] = origin_result
                result["crux"]["note"] = "URL-level data unavailable; showing origin-level data"

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="PageSpeed Insights v5 + CrUX checker")
    parser.add_argument("url", help="URL to analyze")
    parser.add_argument("--strategy", "-s", choices=["mobile", "desktop", "both"], default="both")
    parser.add_argument("--api-key", help="Google API key override")
    parser.add_argument("--crux-only", action="store_true", help="CrUX field data only")
    parser.add_argument("--psi-only", action="store_true", help="PSI Lighthouse only")
    parser.add_argument("--form-factor", choices=["PHONE", "DESKTOP", "TABLET"])
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    api_key = _get_api_key(args.api_key)

    if args.crux_only:
        if not api_key:
            print("Error: CrUX requires an API key (--api-key or credential_hub)", file=sys.stderr)
            sys.exit(1)
        result = query_crux(args.url, api_key, form_factor=args.form_factor)
    elif args.psi_only:
        result = run_pagespeed(args.url, strategy=args.strategy if args.strategy != "both" else "mobile", api_key=api_key)
    else:
        result = combined_check(args.url, api_key=api_key, strategy=args.strategy)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if "error" in result and result["error"]:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)

        if "psi" in result:
            for strat, psi in result["psi"].items():
                print(f"\n=== {strat.upper()} ===")
                scores = psi.get("lighthouse_scores", {})
                for name, score in scores.items():
                    print(f"  {name}: {score}/100")
                opps = psi.get("opportunities", [])
                if opps:
                    print(f"  Opportunities ({len(opps)}):")
                    for o in opps[:5]:
                        print(f"    - {o['title']}: save {o['savings_ms']}ms")
        if result.get("crux") and not result["crux"].get("error"):
            crux = result["crux"]
            print(f"\n=== CrUX Field Data ({crux['form_factor']}) ===")
            for name, m in crux.get("metrics", {}).items():
                unit = m.get("unit", "")
                print(f"  {m['label']}: {m['p75']}{unit} [{m['rating']}]")


if __name__ == "__main__":
    main()
