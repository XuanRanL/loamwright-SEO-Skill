"""Two-tier community-insight verification (signal vs claim) + 4-dimension claim check.

SIGNAL  -> used freely (real language, pain points, questions, opinions).
CLAIM   -> quarantined; scored on (1) authoritative corroboration, (2) consensus,
           (3) author credibility, (4) engagement. Verdict drives writer usage.

IRON RULE: a community URL is never the citation. A verified claim cites the
authoritative corroborating source; the community URL is provenance only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Literal, Optional

# A claim asserts a checkable fact: numbers, units, causal/experimental language.
_CLAIM_PATTERNS = [
    r"\d",  # any number / measurement
    r"\b(tested|measured|experiment|result|data|study|proven|increases?|decreases?|"
    r"reduces?|causes?|improves?|percent)\b",
    r"%",
]
_CLAIM_RE = re.compile("|".join(_CLAIM_PATTERNS), re.IGNORECASE)

Verdict = Literal["verified", "unverified", "contradicted"]
Guidance = Literal[
    "state_as_fact_with_auth_cite", "attributed_hedge_no_cite", "drop"
]


@dataclass
class AuthoritativeHit:
    title: str
    url: str
    apa: str


@dataclass
class ClaimVerdict:
    text: str
    source_url: str
    source: str
    verdict: Verdict
    dimensions: dict[str, object]
    authoritative_source: Optional[AuthoritativeHit]
    writer_guidance: Guidance


def classify(text: str) -> Literal["signal", "claim"]:
    """A question is a signal even if it contains a number; otherwise factual/
    numeric/causal/experimental language marks a CLAIM."""
    if text.strip().endswith("?"):
        return "signal"
    return "claim" if _CLAIM_RE.search(text) else "signal"


def verify_claim(
    text: str,
    source_url: str,
    source: str,
    *,
    consensus: int = 1,
    engagement: str = "low",
    author_credibility: str = "low",
    authoritative_lookup: Callable[[str], Optional[AuthoritativeHit]],
) -> ClaimVerdict:
    """Score a CLAIM on 4 dimensions and assign a verdict + writer guidance.

    Dimension 1 (authoritative corroboration) is the gate for stating a claim as
    fact. Dimensions 2-4 (consensus / author credibility / engagement) are recorded
    for transparency and tie-breaking but never upgrade an uncorroborated claim to
    fact — anonymous community agreement is not proof.
    """
    hit = authoritative_lookup(text)
    dimensions = {
        "authoritative": hit is not None,
        "consensus": consensus,
        "author_credibility": author_credibility,
        "engagement": engagement,
    }
    if hit is not None:
        verdict: Verdict = "verified"
        guidance: Guidance = "state_as_fact_with_auth_cite"
    else:
        verdict = "unverified"
        guidance = "attributed_hedge_no_cite"
    return ClaimVerdict(
        text=text,
        source_url=source_url,
        source=source,
        verdict=verdict,
        dimensions=dimensions,
        authoritative_source=hit,
        writer_guidance=guidance,
    )


def default_authoritative_lookup(
    task_id: str | None = None,
) -> Callable[[str], Optional[AuthoritativeHit]]:
    """Real lookup: Tavily search excluding community (and, when a project is
    active, competitor) domains; the first high-confidence hit corroborates the
    claim. Returns a closure so the runner can inject a mock in tests."""
    from scripts._core import competitor_domains
    from scripts.fetch import tavily_search
    from scripts.fetch.community_search import SOURCE_DOMAINS

    community = [d for ds in SOURCE_DOMAINS.values() for d in ds]
    # Rule 8: never let a competitor domain become the corroborating source.
    policy = (
        competitor_domains.load_policy_for_task(task_id)
        if task_id
        else competitor_domains.load_policy()
    )
    exclude = community + sorted(policy.domains)

    def _lookup(claim: str) -> Optional[AuthoritativeHit]:
        # Tavily hard-caps queries at 400 chars (HTTP 400 BadRequestError above
        # that). Community claims are FULL post bodies (runner passes
        # `post.content`), which routinely exceed 400 — the 2026-07-01 batches
        # crashed every community pass containing one long claim post. Truncate
        # at a word boundary: the leading sentences carry the searchable core.
        query = claim if len(claim) <= 400 else claim[:397].rsplit(" ", 1)[0]
        resp = tavily_search.search(
            query,
            max_results=3,
            depth="advanced",
            exclude_domains=exclude,
            task_id=task_id,
        )
        for r in resp.results:
            # Belt-and-braces: skip community + competitor hits even if the
            # provider ignored exclude_domains.
            if r.score >= 0.5 and not policy.is_blocked(r.url) and not any(
                d in r.url for d in community
            ):
                return AuthoritativeHit(
                    title=r.title, url=r.url, apa=f"{r.title}. {r.url}"
                )
        return None

    return _lookup
