"""Distinguish what a CRAWLER sees from what a HUMAN sees, over time.

Why this exists
---------------
On 2026-08-06 the audit-client.example audit shipped two "critical" findings that were
wrong, and both came from the same mistake: a single headless screenshot was
treated as the page's FINAL state.

  claimed: "the six headline statistics show 0 to everyone"
  reality: they animate 0 -> 37/6/3/2000/2300/150, just slowly (>6s)

  claimed: "the advantages and testimonial blocks render as blank white voids"
  reality: they render completely; the capture caught the pre-animation frame

The cause was isolated empirically, and the first two hypotheses were WRONG:
`prefers-reduced-motion` made no difference, and neither did scroll-into-view.
The measured behaviour is that the animation is slow and unreliable rather than
deterministically broken:

    headless, 10s wait, 6 runs : 5 runs never started (all zeros), 1 completed
    headed,   10s wait, 3 runs : 3 animated, 1 still mid-flight at 10s

So the durable signal is NOT "headless is broken" — it is that a SINGLE capture,
in ANY browser, can land before an animation starts or finishes. Sampling over
time is what catches that; the real-browser pass is the tie-breaker when the two
disagree. This tool makes the three states separately visible:

  static   — no JS at all. This is what a text-extracting crawler or an AI
             engine's fetcher sees, and it is a legitimate finding on its own.
  headless — JS, but headless Chromium.
  headed   — JS in a real browser. The human-visitor ground truth.

A claim only earns "critical" when the headed column agrees.

Usage
-----
    python -m scripts.audit.render_probe https://example.com/ \\
        --selector "[data-to-value]" --selector ".hero h1" --json

    # CI/audit gate: non-zero exit if headless and headed disagree, i.e. any
    # finding derived from the headless pass would be unsafe to report.
    python -m scripts.audit.render_probe https://example.com/ \\
        --selector "[data-to-value]" --check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from scripts._core.ssrf_guard import SSRFError, validate_url

# When to sample the rendered DOM, in seconds after domcontentloaded. The last
# sample must be late enough that a slow animation has settled — audit-client.example's
# counters were still climbing at 6s.
DEFAULT_SAMPLES_S: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0, 8.0)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


@dataclass
class SelectorResult:
    selector: str
    static: list[str] = field(default_factory=list)
    #: Set when the static pass could not be read. When present, `static` is
    #: meaningless and must not be used as evidence of anything.
    static_unavailable: Optional[str] = None
    headless_samples: dict[str, list[str]] = field(default_factory=dict)
    headed_samples: dict[str, list[str]] = field(default_factory=dict)

    @property
    def headless_settled(self) -> list[str]:
        return list(self.headless_samples.values())[-1] if self.headless_samples else []

    @property
    def headed_settled(self) -> list[str]:
        return list(self.headed_samples.values())[-1] if self.headed_samples else []

    @property
    def animates(self) -> bool:
        """True if the rendered values changed across samples (either mode)."""
        for samples in (self.headless_samples, self.headed_samples):
            seen = {tuple(v) for v in samples.values()}
            if len(seen) > 1:
                return True
        return False

    @property
    def headless_differs_from_headed(self) -> Optional[bool]:
        """The trap. True means a headless-only finding here would be wrong.

        None when the headed pass produced no samples: NOT MEASURED, which is a
        different state from "they agree". Returning False here (as this did
        until 2026-08-12) let ``--check --no-headed`` exit 0 unconditionally —
        a check that can never fail is not a check (Rule 12/14).
        """
        if not self.headed_samples:
            return None
        return self.headless_settled != self.headed_settled

    @property
    def static_differs_from_rendered(self) -> Optional[bool]:
        """True means the content is JS-dependent — a real crawler-visibility
        finding, and a DIFFERENT finding from the human-visitor one.

        None when the static pass could not be read: unknown, not False.
        """
        if self.static_unavailable is not None:
            return None
        rendered = self.headed_settled or self.headless_settled
        return self.static != rendered

    def to_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "static": self.static,
            "static_unavailable": self.static_unavailable,
            "headless_samples": self.headless_samples,
            "headed_samples": self.headed_samples,
            "headless_settled": self.headless_settled,
            "headed_settled": self.headed_settled,
            "animates": self.animates,
            "headless_differs_from_headed": self.headless_differs_from_headed,
            "static_differs_from_rendered": self.static_differs_from_rendered,
        }


class StaticFetchUnavailable(RuntimeError):
    """The static pass could not be read at all (403/429/WAF/network).

    Deliberately its own type: "I could not read the page" and "the page has no
    such content" are different findings, and collapsing them is how a transport
    failure gets reported as a content verdict.
    """


# A bot-challenge interstitial is a transport failure wearing a 200/403.
_WAF_MARKERS = ("checking your browser", "just a moment", "jschallenge", "cf-browser-verification")


def _static_text(url: str, selectors: list[str], timeout: float) -> dict[str, list[str]]:
    """Extract selector text from raw HTML with no JS.

    Deliberately regex-based and crude: this approximates a text-extracting
    crawler, which is the audience the static column represents.
    """
    try:
        r = httpx.get(
            url, headers={"User-Agent": _UA}, timeout=timeout, follow_redirects=True
        )
    except httpx.HTTPError as exc:
        raise StaticFetchUnavailable(f"{type(exc).__name__}: {exc}") from exc
    if r.status_code >= 400:
        raise StaticFetchUnavailable(f"HTTP {r.status_code}")
    html = r.text
    low = html[:4000].lower()
    if any(m in low for m in _WAF_MARKERS):
        raise StaticFetchUnavailable(
            f"bot-challenge interstitial ({len(html)} bytes) — not the real page"
        )
    out: dict[str, list[str]] = {}
    for sel in selectors:
        attr = re.match(r"^\[([a-zA-Z0-9_-]+)\]$", sel.strip())
        if attr:
            # [data-to-value] -> text content of every element carrying it
            pat = rf"<([a-z0-9]+)[^>]*\b{re.escape(attr.group(1))}\s*=[^>]*>(.*?)</\1>"
            vals = [
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
                for m in re.finditer(pat, html, re.S | re.I)
            ]
        else:
            cls = re.match(r"^\.([\w-]+)$", sel.strip())
            if cls:
                pat = rf'<([a-z0-9]+)[^>]*class="[^"]*\b{re.escape(cls.group(1))}\b[^"]*"[^>]*>(.*?)</\1>'
                vals = [
                    re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
                    for m in re.finditer(pat, html, re.S | re.I)
                ]
            else:
                vals = []
        out[sel] = vals
    return out


def _render(
    url: str,
    selectors: list[str],
    samples_s: tuple[float, ...],
    headless: bool,
    viewport: tuple[int, int],
    scroll: bool,
) -> dict[str, dict[str, list[str]]]:
    from patchright.sync_api import sync_playwright

    per_selector: dict[str, dict[str, list[str]]] = {s: {} for s in selectors}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            user_agent=_UA,
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded")
        if scroll and selectors:
            try:
                page.locator(selectors[0]).first.scroll_into_view_if_needed(timeout=5000)
            except Exception:
                pass
        waited = 0.0
        for t in samples_s:
            page.wait_for_timeout(int(max(0.0, t - waited) * 1000))
            waited = t
            for sel in selectors:
                try:
                    vals = page.eval_on_selector_all(
                        sel, "els=>els.map(e=>(e.textContent||'').trim())"
                    )
                except Exception:
                    vals = []
                per_selector[sel][f"{t}s"] = vals
        browser.close()
    return per_selector


def probe(
    url: str,
    selectors: list[str],
    samples_s: tuple[float, ...] = DEFAULT_SAMPLES_S,
    verify_headed: bool = True,
    viewport: tuple[int, int] = (1440, 900),
    scroll: bool = True,
    timeout: float = 40.0,
) -> list[SelectorResult]:
    validate_url(url, allow_http=True)  # raises on refusal

    static_err: Optional[str] = None
    try:
        statics = _static_text(url, selectors, timeout)
    except StaticFetchUnavailable as exc:
        # Not fatal, and NOT a content verdict. The render passes still work,
        # and the static column is reported as unavailable rather than empty.
        static_err = str(exc)
        statics = {s: [] for s in selectors}

    headless = _render(url, selectors, samples_s, True, viewport, scroll)
    headed = (
        _render(url, selectors, samples_s, False, viewport, scroll)
        if verify_headed
        else {s: {} for s in selectors}
    )

    return [
        SelectorResult(
            selector=sel,
            static=statics.get(sel, []),
            static_unavailable=static_err,
            headless_samples=headless.get(sel, {}),
            headed_samples=headed.get(sel, {}),
        )
        for sel in selectors
    ]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="render_probe",
        description=(
            "Compare static HTML, headless render and real-browser render over time. "
            "Use before rating any 'does not render / shows zero / is blank' finding."
        ),
    )
    p.add_argument("url")
    p.add_argument(
        "--selector", "-s", action="append", default=[],
        help="CSS selector to sample. Repeatable. Required.",
    )
    p.add_argument(
        "--no-headed", action="store_true",
        help="Skip the real-browser pass (faster, but findings stay UNVERIFIED).",
    )
    p.add_argument("--viewport", default="1440x900")
    p.add_argument("--no-scroll", action="store_true")
    p.add_argument("--timeout", type=float, default=40.0)
    p.add_argument(
        "--check", action="store_true",
        help=(
            "Gate mode. Exit 1 if headless disagrees with the real browser on "
            "any selector (a headless-derived finding would be unsafe); exit 3 "
            "if the comparison could not be measured (no headed samples); "
            "refused up front (exit 2) when combined with --no-headed, because "
            "without the headed pass there is no ground truth to check against."
        ),
    )
    p.add_argument("--json", "-j", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.selector:
        print("error: at least one --selector is required", file=sys.stderr)
        return 2
    try:
        w, h = (int(x) for x in args.viewport.lower().split("x"))
    except ValueError:
        print("error: --viewport must look like 1440x900", file=sys.stderr)
        return 2
    if args.check and args.no_headed:
        # Refuse BEFORE probing: with no headed pass there is no ground truth,
        # so "agrees" is unmeasurable — and unmeasured must never exit 0
        # (Rule 12: a coverage gap is not a verdict).
        print(
            "error: --check needs the headed (real-browser) pass as ground "
            "truth; with --no-headed the comparison is UNMEASURABLE, not "
            "'agreed'. Drop --no-headed (or drop --check).",
            file=sys.stderr,
        )
        return 2

    try:
        results = probe(
            args.url,
            args.selector,
            verify_headed=not args.no_headed,
            viewport=(w, h),
            scroll=not args.no_scroll,
            timeout=args.timeout,
        )
    except SSRFError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    unsafe = [r for r in results if r.headless_differs_from_headed]
    unmeasured = [r for r in results if r.headless_differs_from_headed is None]

    if args.json:
        print(json.dumps(
            {
                "url": args.url,
                "results": [r.to_dict() for r in results],
                "headless_unsafe_selectors": [r.selector for r in unsafe],
                "unmeasured_selectors": [r.selector for r in unmeasured],
            },
            indent=2, ensure_ascii=False,
        ))
    else:
        for r in results:
            print(f"\n{r.selector}")
            if r.static_unavailable:
                print(f"  static (no JS) : UNAVAILABLE — {r.static_unavailable}")
                print("                   (transport failure, NOT evidence of absence)")
            else:
                print(f"  static (no JS) : {r.static}")
            for t, v in r.headless_samples.items():
                print(f"  headless @{t:<5}: {v}")
            for t, v in r.headed_samples.items():
                print(f"  headed   @{t:<5}: {v}")
            if r.headless_differs_from_headed is None:
                print("  ? headed pass not sampled — headless findings stay "
                      "UNVERIFIED (unmeasured is not agreement).")
            elif r.headless_differs_from_headed:
                print("  ⚠ headless disagrees with the real browser — do NOT report "
                      "a rendering defect from the headless pass.")
            if r.static_differs_from_rendered:
                print("  → content is JS-dependent: real finding for crawlers/AI, "
                      "but rate it as such, not as a human-visitor defect.")
        if unsafe:
            print(f"\nUNSAFE: {len(unsafe)} selector(s) differ between headless and "
                  f"real browser: {[r.selector for r in unsafe]}")

    if args.check:
        if unsafe:
            return 1
        if unmeasured:
            # The headed pass ran but yielded no samples for these selectors:
            # the comparison is UNMEASURABLE — a verdict distinct from both
            # "agrees" (0) and "differs" (1), never folded into a pass.
            print(
                f"UNMEASURED: {len(unmeasured)} selector(s) have no headed "
                f"samples — cannot verify agreement: "
                f"{[r.selector for r in unmeasured]}",
                file=sys.stderr,
            )
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
