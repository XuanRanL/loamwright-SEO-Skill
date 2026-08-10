"""scripts/fetch/ai_search_probe.py — Active probe of AI search engines.

For each (engine, query) pair, ask the AI: "tell me about {brand}".
Parse response for:
  - Brand mentioned? (yes/no)
  - Brand presented accurately? (vs ground truth from brand-config)
  - Own domain URL cited? (yes/no — if yes, AI recognizes brand)
  - Competitors mentioned?
  - Factual errors (hallucinations about our brand)

Used by:
  - /init Stage 7 (GEO Baseline)
  - /ai-visibility command
  - subskills/monitor/ai-visibility-tracker

Engines supported:
  - ChatGPT (via OpenAI API gpt-4o or gpt-5)
  - Perplexity (via Perplexity API)
  - Claude (via Anthropic API)
  - Gemini (via google-genai)
  - Google AIO (no direct API; use Tavily/SerpAPI fallback)

Output `ai_resolution_status` per engine:
  - recognized: brand mentioned + accurate facts + own URL cited
  - partial: brand mentioned but some facts wrong OR own URL not cited
  - unrecognized: brand not mentioned at all
  - confused: brand mentioned but mixed with another brand's info (HIGH RISK)

Cost note: each probe is 1 LLM call per engine; budget ~$0.05 per query per engine.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from scripts._core import credential_hub, cost_ledger


ResolutionStatus = Literal["recognized", "partial", "unrecognized", "confused", "probe_failed"]


@dataclass
class EngineProbeResult:
    engine: str
    query: str
    response_text: str
    mentions_brand: bool = False
    our_domain_cited: bool = False
    cites_in_response: list[str] = field(default_factory=list)
    competitors_mentioned: list[str] = field(default_factory=list)
    factual_errors: list[str] = field(default_factory=list)
    resolution_status: ResolutionStatus = "unrecognized"
    response_time_seconds: float = 0
    cost_usd: float = 0
    error: str | None = None


@dataclass
class ProbeReport:
    brand: str
    domain: str
    engines: dict[str, list[EngineProbeResult]] = field(default_factory=dict)
    overall_resolution: dict[str, ResolutionStatus] = field(default_factory=dict)


def _probe_chatgpt(query: str) -> EngineProbeResult:
    """Probe ChatGPT/OpenAI."""
    import time
    try:
        import openai
    except ImportError as e:
        return EngineProbeResult("chatgpt", query, "", error=str(e))

    try:
        api_key = credential_hub.get_credential("openai")
    except credential_hub.CredentialNotFoundError:
        return EngineProbeResult("chatgpt", query, "", error="no openai key")

    client = openai.OpenAI(api_key=api_key)
    t0 = time.time()
    try:
        r = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful research assistant. Answer with facts and cite sources where possible."},
                {"role": "user", "content": query},
            ],
            max_tokens=600,
        )
        text = r.choices[0].message.content or ""
        elapsed = time.time() - t0
        return EngineProbeResult(
            engine="chatgpt", query=query,
            response_text=text, response_time_seconds=round(elapsed, 2),
            cost_usd=0.01,  # estimate; ~$2.50/M for gpt-4o input + 10/M output
        )
    except Exception as e:
        return EngineProbeResult("chatgpt", query, "",
                                  error=f"openai error: {e}",
                                  resolution_status="probe_failed")


def _probe_claude(query: str) -> EngineProbeResult:
    """Probe Claude via Anthropic API."""
    import time
    try:
        import anthropic
    except ImportError as e:
        return EngineProbeResult("claude", query, "", error=str(e))

    try:
        api_key = credential_hub.get_credential("anthropic")
    except credential_hub.CredentialNotFoundError:
        return EngineProbeResult("claude", query, "", error="no anthropic key")

    client = anthropic.Anthropic(api_key=api_key)
    t0 = time.time()
    try:
        r = client.messages.create(
            model="claude-haiku-4-5",   # cheaper for probes
            max_tokens=600,
            system="You are a research assistant. Answer with facts and cite known sources.",
            messages=[{"role": "user", "content": query}],
        )
        text = r.content[0].text if r.content else ""
        elapsed = time.time() - t0
        # cost ~$1/M input + $5/M output for haiku
        cost = (r.usage.input_tokens / 1_000_000) * 1.0 + (r.usage.output_tokens / 1_000_000) * 5.0
        return EngineProbeResult(
            engine="claude", query=query, response_text=text,
            response_time_seconds=round(elapsed, 2), cost_usd=round(cost, 4),
        )
    except Exception as e:
        return EngineProbeResult("claude", query, "",
                                  error=f"anthropic error: {e}",
                                  resolution_status="probe_failed")


def _probe_gemini(query: str) -> EngineProbeResult:
    """Probe Gemini."""
    import time
    try:
        from google import genai
    except ImportError as e:
        return EngineProbeResult("gemini", query, "", error=str(e))

    try:
        api_key = credential_hub.get_credential("gemini")
    except credential_hub.CredentialNotFoundError:
        return EngineProbeResult("gemini", query, "", error="no gemini key")

    client = genai.Client(api_key=api_key)
    t0 = time.time()
    try:
        r = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=query,
        )
        elapsed = time.time() - t0
        return EngineProbeResult(
            engine="gemini", query=query,
            response_text=r.text or "",
            response_time_seconds=round(elapsed, 2),
            cost_usd=0.005,
        )
    except Exception as e:
        return EngineProbeResult("gemini", query, "",
                                  error=f"gemini error: {e}",
                                  resolution_status="probe_failed")


def _analyze_response(
    result: EngineProbeResult,
    *,
    brand: str,
    domain: str,
    known_competitors: list[str] | None = None,
    known_facts: dict | None = None,
) -> EngineProbeResult:
    """Analyze response text to detect brand mention, citations, errors."""
    text_lower = result.response_text.lower()
    brand_lower = brand.lower()
    domain_lower = domain.lower().replace("https://", "").replace("http://", "").rstrip("/")

    result.mentions_brand = brand_lower in text_lower
    result.our_domain_cited = domain_lower in text_lower

    # Extract URLs from response
    import re
    urls = re.findall(r"https?://[^\s<>\")']+", result.response_text)
    result.cites_in_response = [u for u in urls if domain_lower in u][:20]

    # Competitors mentioned
    if known_competitors:
        for comp in known_competitors:
            if comp.lower() in text_lower:
                result.competitors_mentioned.append(comp)

    # Factual error detection (heuristic; compare known_facts)
    if known_facts:
        for fact_key, expected in known_facts.items():
            # E.g., fact_key="founded_year", expected=2015
            if isinstance(expected, int) and isinstance(fact_key, str):
                # Find any year near brand mention
                if brand_lower in text_lower:
                    years = re.findall(r"\b(19|20)\d{2}\b", result.response_text)
                    if years and str(expected) not in [str(y) for y in years]:
                        result.factual_errors.append(
                            f"{fact_key}: expected {expected}, but response mentions {years[:3]}"
                        )

    # Determine resolution status
    if result.error:
        result.resolution_status = "probe_failed"
    elif not result.mentions_brand:
        result.resolution_status = "unrecognized"
    elif result.factual_errors:
        if known_competitors and any(c.lower() in text_lower for c in known_competitors):
            # Mixed with competitor info → confused
            result.resolution_status = "confused"
        else:
            result.resolution_status = "partial"
    elif result.our_domain_cited:
        result.resolution_status = "recognized"
    else:
        result.resolution_status = "partial"

    return result


def probe(
    brand: str,
    domain: str,
    *,
    engines: list[str] | None = None,
    queries: list[str] | None = None,
    known_competitors: list[str] | None = None,
    known_facts: dict | None = None,
    task_id: str | None = None,
) -> ProbeReport:
    """Probe AI engines about a brand. Returns ProbeReport.

    Default queries: 5 standard SEO/GEO discovery queries.
    """
    if not engines:
        engines = ["chatgpt", "claude", "gemini"]
    if not queries:
        queries = [
            f"tell me about {brand}",
            f"what does {brand} sell or offer",
            f"is {brand} reputable",
            f"what are alternatives to {brand}",
            f"who founded {brand} and when",
        ]

    report = ProbeReport(brand=brand, domain=domain)

    for engine in engines:
        report.engines[engine] = []
        for query in queries:
            if engine == "chatgpt":
                result = _probe_chatgpt(query)
            elif engine == "claude":
                result = _probe_claude(query)
            elif engine == "gemini":
                result = _probe_gemini(query)
            else:
                continue

            result = _analyze_response(
                result, brand=brand, domain=domain,
                known_competitors=known_competitors,
                known_facts=known_facts,
            )
            report.engines[engine].append(result)

            # Log cost
            if not result.error:
                cost_ledger.log(
                    None, model=engine, endpoint=f"ai_search_probe.{engine}",
                    task_id=task_id,
                    extra={"query": query[:80], "status": result.resolution_status},
                ) if result.cost_usd > 0 else None

        # Overall status for engine = worst across queries (more conservative)
        statuses = [r.resolution_status for r in report.engines[engine]]
        if "confused" in statuses:
            overall = "confused"
        elif all(s == "unrecognized" for s in statuses):
            overall = "unrecognized"
        elif "partial" in statuses or "unrecognized" in statuses:
            overall = "partial"
        elif all(s == "recognized" for s in statuses):
            overall = "recognized"
        elif all(s == "probe_failed" for s in statuses):
            overall = "probe_failed"
        else:
            overall = "partial"
        report.overall_resolution[engine] = overall

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe AI engines for brand visibility")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--engines", help="Comma-separated: chatgpt,claude,gemini",
                    default="chatgpt,claude,gemini")
    ap.add_argument("--queries", help="Comma-separated custom queries (else use defaults)")
    ap.add_argument("--competitors", help="Comma-separated known competitors")
    ap.add_argument("--facts-json", type=Path, help="JSON file with {fact_key: expected_value}")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--task-id")
    args = ap.parse_args()

    engines = [e.strip() for e in args.engines.split(",")]
    queries = [q.strip() for q in args.queries.split(",")] if args.queries else None
    competitors = [c.strip() for c in args.competitors.split(",")] if args.competitors else None
    facts = json.loads(args.facts_json.read_text(encoding="utf-8")) if args.facts_json and args.facts_json.exists() else None

    report = probe(
        args.brand, args.domain,
        engines=engines, queries=queries,
        known_competitors=competitors, known_facts=facts,
        task_id=args.task_id,
    )

    out = {
        "brand": report.brand,
        "domain": report.domain,
        "overall_resolution": report.overall_resolution,
        "engines": {
            engine: [asdict(r) for r in results]
            for engine, results in report.engines.items()
        },
    }
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"Brand: {report.brand}  Domain: {report.domain}")
        print(f"\nOverall resolution:")
        for engine, status in report.overall_resolution.items():
            icon = {"recognized": "✓", "partial": "⚠", "unrecognized": "✗",
                    "confused": "🔴", "probe_failed": "❓"}.get(status, "?")
            print(f"  {icon} {engine}: {status}")
        for engine, results in report.engines.items():
            print(f"\n--- {engine} ({len(results)} queries) ---")
            for r in results:
                if r.error:
                    print(f"  ✗ {r.query}: {r.error}")
                else:
                    print(f"  {r.resolution_status}: {r.query}")
                    if r.factual_errors:
                        for e in r.factual_errors[:3]:
                            print(f"     ⚠ {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
