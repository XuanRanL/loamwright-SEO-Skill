"""
scripts/_core/setup_wizard.py — Credential & brand-info collection at /init time.

CRITICAL UX: When the user runs /init <url>, this wizard runs FIRST.
It identifies every piece of info we'll need across the full lifecycle
(research → write → image → publish → monitor) and either:
  - confirms it's present (env var or file)
  - prompts the user for it
  - validates it works (test API call)
  - saves it to the correct location

This prevents the "I scanned your site but can't publish because you didn't
configure WordPress" failure mode.

Lifecycle of info collected:

  ── REQUIRED (Tier 1 — for any use) ────────────────────
    anthropic.key                — Claude API
    contact_email                — Crossref polite pool User-Agent

  ── HIGHLY RECOMMENDED (Tier 2 — research + image) ──
    tavily.key                   — research backbone (1000 free/mo)
    openai.key                   — official OpenAI (image-gen FALLBACK; primary is the configurable relay)
    openclawroot.key             — primary image relay (OpenAI-compatible; see config.yaml image.providers)
    gemini.key                   — second-opinion judge (free tier OK)

  ── REQUIRED FOR /PUBLISH (Tier 3 — WordPress) ──────
    wordpress/{slug}.json        — { url, username, app_password }
    Optional MU-plugin install   — for Yoast meta REST endpoint

  ── BRAND CONTEXT (Tier 4 — image generation, voice) ──
    projects/{slug}/brand/brand-config.json:
      brand_name
      industry / sub_industry
      primary_color (hex, for image Art Direction)
      secondary_color (hex)
      logo_url (optional)
      target_locale  (en-US / en-UK / etc)
      voice_pair    (warm × general etc, can derive from /init Stage 5)
      ymyl_flag     (health / finance / legal?)
      banned_competitors  (don't mention by name)
      target_ai_engines  (chatgpt / perplexity / claude / gemini priority)

  ── OPTIONAL (Tier 5 — power features) ────────────────
    bing-indexnow.json            — IndexNow instant indexing
    youtube.key                   — embed addon

Usage (programmatic from skill):
    from scripts._core.setup_wizard import SetupWizard, ProviderStatus

    wiz = SetupWizard(site_slug="example-com", site_url="https://example.com")

    status = wiz.detect_existing()  # → which keys are present / missing
    # For each missing, the skill asks the user, then:
    wiz.save_credential("openai", "sk-proj-...")
    wiz.save_wordpress("https://example.com", "admin", "abcd 1234 efgh ...")
    wiz.save_brand_config({...})

    val = wiz.validate_all()  # → per-provider {ok, error, latency_ms}

Usage (interactive CLI mode):
    python -m scripts._core.setup_wizard --site-slug example-com --site-url https://example.com
    python -m scripts._core.setup_wizard --status   # show current state
    python -m scripts._core.setup_wizard --validate # live-test all configured
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from scripts._core import credential_hub
from scripts._core.credential_hub import CRED_DIR, WP_DIR, XS_HOME


# ─── Data types ─────────────────────────────────────────

class Tier(str, Enum):
    REQUIRED = "tier_1_required"
    RECOMMENDED = "tier_2_recommended"
    PUBLISH = "tier_3_publish"
    BRAND = "tier_4_brand"
    OPTIONAL = "tier_5_optional"


@dataclass
class ProviderStatus:
    name: str
    tier: Tier
    purpose: str                  # one-line "why we need this"
    found: bool
    source: str                    # "env" / "file" / "none"
    valid: bool | None = None      # None = not tested; True/False after validate
    error: str | None = None
    latency_ms: int | None = None


@dataclass
class WizardStatus:
    site_slug: str
    site_url: str
    providers: list[ProviderStatus] = field(default_factory=list)
    brand_config_present: bool = False
    wp_credentials_present: bool = False
    wp_mu_plugin_status: str = "unknown"
    overall_ready_for: dict = field(default_factory=dict)
    # e.g. {"init": True, "article": True, "publish": False, "ai_visibility": True}


@dataclass
class BrandConfig:
    brand_name: str = ""
    industry: str = ""
    sub_industry: str = ""
    primary_color: str = "#000000"
    secondary_color: str = "#FFFFFF"
    accent_color: str = ""
    logo_url: str = ""
    target_locale: str = "en-US"
    voice_pair: str = "professional × general"
    voice_modifiers: list[str] = field(default_factory=list)
    ymyl_flag: bool = False
    banned_competitors: list[str] = field(default_factory=list)
    target_ai_engines: list[str] = field(default_factory=lambda: ["chatgpt", "google-aio"])
    publish_default_status: str = "draft"
    default_categories: list[str] = field(default_factory=list)
    default_tags: list[str] = field(default_factory=list)
    contact_email: str = ""


# ─── Provider catalog ─────────────────────────────────

_PROVIDER_CATALOG: list[tuple[str, Tier, str]] = [
    # name, tier, purpose
    ("anthropic",       Tier.REQUIRED,    "Claude API — main LLM for writing, orchestration"),
    ("tavily",          Tier.RECOMMENDED, "Web search for keyword research + fact-check (1000 free/mo)"),
    ("vertex-gemini",   Tier.RECOMMENDED, "Vertex AI (Gemini 3 Pro Image) — PRIMARY image gen, true 4K ~10x cheaper than OpenAI (AQ. key via x-goog-api-key)"),
    ("openai",          Tier.RECOMMENDED, "official OpenAI — image-gen 4K fallback (~$1.67/img) when vertex-gemini is unavailable"),
    ("gemini",          Tier.RECOMMENDED, "Gemini second-opinion judge for quality gates (free tier)"),
    ("youtube",         Tier.OPTIONAL,    "YouTube Data API — for /article --embed-youtube only"),
    ("bing-indexnow",   Tier.OPTIONAL,    "Bing IndexNow — instant indexing on publish"),
]


# ─── Detection ────────────────────────────────────────

class SetupWizard:
    """Credential + brand setup helper."""

    def __init__(self, site_slug: str, site_url: str = ""):
        self.site_slug = site_slug
        self.site_url = site_url

    def detect_existing(self) -> WizardStatus:
        """Pure detection — no network calls, no prompts."""
        status = WizardStatus(site_slug=self.site_slug, site_url=self.site_url)

        # Provider keys
        for name, tier, purpose in _PROVIDER_CATALOG:
            ps = self._detect_one_provider(name, tier, purpose)
            status.providers.append(ps)

        # WordPress credentials
        wp_file = WP_DIR / f"{self.site_slug}.json"
        status.wp_credentials_present = wp_file.exists() and wp_file.stat().st_size > 0

        # Brand config
        brand_file = self._brand_config_path()
        status.brand_config_present = brand_file.exists()

        # Compute "ready for what"
        all_provider_found = {p.name: p.found for p in status.providers}
        status.overall_ready_for = {
            "init":          all_provider_found.get("anthropic", False),
            "article":       all_provider_found.get("anthropic", False)
                             and all_provider_found.get("tavily", False),
            "image_gen":     all_provider_found.get("openai", False),
            "publish_wp":    status.wp_credentials_present,
            "ai_visibility": (all_provider_found.get("anthropic", False)
                              and all_provider_found.get("gemini", False)),
            "indexnow":      all_provider_found.get("bing-indexnow", False),
        }
        return status

    def _detect_one_provider(self, name: str, tier: Tier, purpose: str) -> ProviderStatus:
        """Check env var + file for a single provider."""
        try:
            credential_hub.get_credential(name)
            # Was found; figure out where
            env_var = credential_hub._PROVIDERS.get(name, ("", ""))[0]
            file_name = credential_hub._PROVIDERS.get(name, ("", ""))[1]
            if os.environ.get(env_var):
                src = "env"
            elif (CRED_DIR / file_name).exists():
                src = "file"
            else:
                src = "unknown"
            return ProviderStatus(name=name, tier=tier, purpose=purpose, found=True, source=src)
        except credential_hub.CredentialNotFoundError:
            return ProviderStatus(name=name, tier=tier, purpose=purpose, found=False, source="none")
        except Exception as e:
            return ProviderStatus(name=name, tier=tier, purpose=purpose, found=False, source="error", error=str(e))

    # ─── Saving ──────────────────────────────────────

    def save_credential(self, provider: str, value: str) -> Path:
        """Save a single-string credential to credentials/{provider}.key (chmod 0600).

        Returns the file path.
        Raises ValueError if provider not in catalog.
        """
        if provider not in credential_hub._PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}")
        value = value.strip()
        if not value:
            raise ValueError("Empty credential value")
        CRED_DIR.mkdir(parents=True, exist_ok=True)
        file_name = credential_hub._PROVIDERS[provider][1]
        file_path = CRED_DIR / file_name
        file_path.write_text(value, encoding="utf-8")
        try:
            file_path.chmod(0o600)
        except (OSError, NotImplementedError):
            pass  # Windows doesn't honor chmod; ACL handled separately
        return file_path

    def save_wordpress(
        self,
        url: str,
        username: str,
        app_password: str,
    ) -> Path:
        """Save WordPress credentials. Strips spaces from app_password (WP shows it spaced)."""
        url = url.strip().rstrip("/")
        if not url.startswith("https://"):
            raise ValueError(
                "WordPress URL must start with https:// (Application Passwords requirement)"
            )
        app_password = "".join(app_password.split())  # WP shows it as 'aaaa bbbb cccc dddd'; strip
        if not username.strip():
            raise ValueError("Username cannot be empty")
        if len(app_password) < 20:
            raise ValueError("App password looks too short; expected 24 chars (no spaces)")

        WP_DIR.mkdir(parents=True, exist_ok=True)
        path = WP_DIR / f"{self.site_slug}.json"
        path.write_text(json.dumps({
            "url": url,
            "username": username.strip(),
            "app_password": app_password,
        }, indent=2), encoding="utf-8")
        try:
            path.chmod(0o600)
        except (OSError, NotImplementedError):
            pass
        return path

    def save_brand_config(self, config: BrandConfig | dict) -> Path:
        """Save brand-config.json to projects/{slug}/."""
        if isinstance(config, BrandConfig):
            data = asdict(config)
        else:
            data = config
        # Emit a canonical nested `colors` block (the schema 5/6 projects + every reader
        # use — charts, article CSS) DERIVED from the flat *_color keys, so /init output
        # matches the nested-reading consumers. Flat keys are kept for backward compat.
        # (2026-06-29 — fixes the flat/nested writer-vs-reader split that greyed charts.)
        if isinstance(data, dict) and "colors" not in data:
            colors = {
                nested: data[flat]
                for nested, flat in (("primary", "primary_color"),
                                     ("secondary", "secondary_color"),
                                     ("accent", "accent_color"))
                if data.get(flat)
            }
            if data.get("surface_mode"):
                colors["surface_mode"] = data["surface_mode"]
            if colors:
                data = {**data, "colors": colors}
        path = self._brand_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def save_indexnow(self, key: str, key_location: str, host: str) -> Path:
        """Save Bing IndexNow config."""
        path = CRED_DIR / "bing-indexnow.json"
        path.write_text(json.dumps({
            "key": key.strip(),
            "key_location": key_location.strip(),
            "host": host.strip(),
        }, indent=2), encoding="utf-8")
        try:
            path.chmod(0o600)
        except (OSError, NotImplementedError):
            pass
        return path

    def save_contact_email(self, email: str) -> None:
        """Persist contact email to ~/.xuanran-seo/config.yaml (for Crossref polite pool)."""
        import yaml
        cfg = XS_HOME / "config.yaml"
        data = {}
        if cfg.exists():
            try:
                data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
        data["contact_email"] = email.strip()
        cfg.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def _brand_config_path(self) -> Path:
        from scripts._core.file_bus import PLUGIN_ROOT
        path = PLUGIN_ROOT / "projects" / self.site_slug / "brand" / "brand-config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    # ─── Live validation ─────────────────────────────

    def validate_all(self) -> dict[str, dict]:
        """Run live API tests for every configured provider.

        Returns: {provider_name: {ok: bool, latency_ms: int, error?: str}}
        """
        results: dict[str, dict] = {}
        for name, _, _ in _PROVIDER_CATALOG:
            try:
                credential_hub.get_credential(name)
            except credential_hub.CredentialNotFoundError:
                results[name] = {"ok": False, "error": "not_configured", "skipped": True}
                continue

            t0 = time.time()
            try:
                self._test_provider(name)
                results[name] = {"ok": True, "latency_ms": int((time.time() - t0) * 1000)}
            except Exception as e:
                results[name] = {
                    "ok": False,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "error": str(e)[:200],
                }

        # WordPress
        if (WP_DIR / f"{self.site_slug}.json").exists():
            t0 = time.time()
            try:
                from scripts.wordpress.wp_client import WPClient
                wp = WPClient(self.site_slug)
                with wp:
                    h = wp.health_check()
                results["wordpress"] = {
                    "ok": h["wp_rest"],
                    "yoast_mu": h["yoast_mu_plugin"],
                    "latency_ms": int((time.time() - t0) * 1000),
                    "info": h["info"],
                }
            except Exception as e:
                results["wordpress"] = {
                    "ok": False,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "error": str(e)[:200],
                }

        return results

    def _test_provider(self, name: str) -> None:
        """Tiny ping test per provider. Raises on failure."""
        if name == "anthropic":
            import anthropic
            c = anthropic.Anthropic()
            c.models.list()
        elif name == "openai":
            import openai
            c = openai.OpenAI()
            c.models.list()
        elif name == "tavily":
            from tavily import TavilyClient
            TavilyClient().search("test", max_results=1)
        elif name == "gemini":
            from google import genai
            c = genai.Client()
            # Cheaper validation: list models
            list(c.models.list())
        elif name == "youtube":
            from googleapiclient.discovery import build
            key = credential_hub.get_credential("youtube")
            yt = build("youtube", "v3", developerKey=key)
            yt.videos().list(part="snippet", id="dQw4w9WgXcQ").execute()  # smoke test
        elif name == "bing-indexnow":
            # Just confirm config parses
            credential_hub.get_bing_indexnow()
        else:
            raise ValueError(f"No test for provider {name}")


# ─── Interactive CLI (the standalone wizard) ─────────────

def _prompt(question: str, *, default: str | None = None, secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    fn = getpass.getpass if secret else input
    try:
        val = fn(f"  {question}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
    return val or (default or "")


def _prompt_yn(question: str, *, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    val = _prompt(question + suffix, default="y" if default else "n").lower()
    if not val:
        return default
    return val.startswith("y")


def interactive_wizard(site_slug: str, site_url: str) -> int:
    print(f"\n╔═══ Xuanran SEO Setup Wizard ═══╗")
    print(f"  Project: {site_slug}")
    print(f"  Site URL: {site_url}")
    print(f"╚════════════════════════════════╝\n")

    wiz = SetupWizard(site_slug, site_url)
    status = wiz.detect_existing()

    # Print current state
    print("Current state:")
    for p in status.providers:
        icon = "✓" if p.found else "✗"
        print(f"  {icon} [{p.tier.value}] {p.name:18s} {p.purpose}")
        if p.found:
            print(f"      (source: {p.source})")
    print(f"  {'✓' if status.wp_credentials_present else '✗'} wordpress credentials for {site_slug}")
    print(f"  {'✓' if status.brand_config_present else '✗'} brand-config.json for {site_slug}")
    print()

    # Tier 1 — REQUIRED
    if not any(p.name == "anthropic" and p.found for p in status.providers):
        print("─── TIER 1 REQUIRED: Anthropic API ───")
        print("  Get key at: https://console.anthropic.com/")
        key = _prompt("Anthropic API key", secret=True)
        if key:
            wiz.save_credential("anthropic", key)
            print(f"  ✓ Saved to {CRED_DIR / 'anthropic.key'}\n")
        else:
            print("  ✗ Skipped — plugin will NOT work without this\n")

    # Contact email (for Crossref)
    cfg_file = XS_HOME / "config.yaml"
    has_email = False
    if cfg_file.exists():
        try:
            import yaml
            d = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
            has_email = bool(d.get("contact_email"))
        except Exception:
            pass
    if not has_email:
        print("─── TIER 1 REQUIRED: Contact email ───")
        print("  Used in Crossref User-Agent for polite-pool DOI lookups")
        email = _prompt("Your email", default="contact@example.com")
        if email and "@" in email:
            wiz.save_contact_email(email)
            print(f"  ✓ Saved\n")

    # Tier 2 — RECOMMENDED
    for provider_name in ["tavily", "openai", "gemini"]:
        if any(p.name == provider_name and p.found for p in status.providers):
            continue
        print(f"─── TIER 2 RECOMMENDED: {provider_name.title()} ───")
        for p in status.providers:
            if p.name == provider_name:
                print(f"  {p.purpose}")
                break
        urls = {
            "tavily": "https://tavily.com/",
            "openai": "https://platform.openai.com/api-keys",
            "gemini": "https://aistudio.google.com/apikey",
        }
        print(f"  Get key at: {urls.get(provider_name)}")
        if _prompt_yn(f"Configure {provider_name} now?"):
            key = _prompt(f"{provider_name} API key", secret=True)
            if key:
                wiz.save_credential(provider_name, key)
                print(f"  ✓ Saved\n")
        else:
            print(f"  Skipped (you can run this wizard again later)\n")

    # Tier 3 — WordPress
    if not status.wp_credentials_present:
        print("─── TIER 3 (for /publish): WordPress credentials ───")
        print("  Create Application Password in WordPress:")
        print("    1. WP Admin → Users → Profile → scroll to 'Application Passwords'")
        print("    2. Type a name like 'xuanran-seo', click 'Add New'")
        print("    3. Copy the 24-char password (shown ONCE)\n")
        if _prompt_yn("Configure WordPress now?", default=True):
            wp_url = _prompt("WordPress site URL", default=site_url if site_url.startswith("https") else "")
            wp_user = _prompt("WordPress username")
            wp_pwd = _prompt("App Password (24 chars, spaces OK)", secret=True)
            try:
                wiz.save_wordpress(wp_url, wp_user, wp_pwd)
                print(f"  ✓ Saved")
                # Quick verification
                try:
                    from scripts.wordpress.wp_client import WPClient
                    with WPClient(site_slug) as wp:
                        h = wp.health_check()
                    print(f"  WP REST:    {'✓' if h['wp_rest'] else '✗'}")
                    print(f"  Yoast MU:   {'✓' if h['yoast_mu_plugin'] else '✗ (install MU-plugin for Yoast meta)'}")
                except Exception as e:
                    print(f"  ⚠ Health check failed: {e}")
                print()
            except ValueError as e:
                print(f"  ✗ Failed: {e}\n")

    # Tier 4 — Brand config
    if not status.brand_config_present:
        print("─── TIER 4 (for content/images): Brand config ───")
        print("  You can configure this manually later in projects/{slug}/brand/brand-config.json,")
        print("  but providing it now improves image generation + voice consistency.")
        if _prompt_yn("Configure brand basics now?", default=True):
            brand = BrandConfig(
                brand_name=_prompt("Brand name", default=site_slug),
                industry=_prompt("Industry (e.g. fishing, saas, fashion)", default="general"),
                target_locale=_prompt("Target locale (en-US/en-UK/en-AU/...)", default="en-US"),
                primary_color=_prompt("Primary brand color (hex, e.g. #FF8C00)", default="#000000"),
                secondary_color=_prompt("Secondary color (hex)", default="#FFFFFF"),
                logo_url=_prompt("Logo URL (optional, for visual reference)"),
            )
            brand.ymyl_flag = _prompt_yn("Is this YMYL content (health/finance/legal)?", default=False)
            engines_str = _prompt(
                "AI engines to prioritize (comma-separated: chatgpt,perplexity,claude,gemini,google-aio)",
                default="chatgpt,google-aio",
            )
            brand.target_ai_engines = [e.strip() for e in engines_str.split(",") if e.strip()]
            wiz.save_brand_config(brand)
            print(f"  ✓ Saved to projects/{site_slug}/brand-config.json\n")

    # Tier 5 — Optional
    print("─── TIER 5 OPTIONAL ───")
    if not any(p.name == "bing-indexnow" and p.found for p in status.providers):
        if _prompt_yn("Configure Bing IndexNow for instant indexing?", default=False):
            print("  See: https://www.bing.com/indexnow/getstarted")
            in_key = _prompt("IndexNow key (32-char hex; generate at indexnow.org if you don't have one)")
            if in_key:
                in_host = _prompt("Your domain (e.g. example.com)")
                in_loc = _prompt("Key file URL", default=f"https://{in_host}/{in_key}.txt")
                wiz.save_indexnow(in_key, in_loc, in_host)
                print(f"  ✓ Saved\n")

    if not any(p.name == "youtube" and p.found for p in status.providers):
        if _prompt_yn("Configure YouTube Data API (for /article --embed-youtube)?", default=False):
            key = _prompt("YouTube API key", secret=True)
            if key:
                wiz.save_credential("youtube", key)

    # Final summary
    print("\n╔═══ Setup Complete ═══╗")
    final = wiz.detect_existing()
    for cap, ready in final.overall_ready_for.items():
        icon = "✓" if ready else "✗"
        print(f"  {icon} {cap}")
    print("╚═══════════════════════╝\n")
    print(f"You can re-run anytime:  python -m scripts._core.setup_wizard --site-slug {site_slug} --status")
    return 0


# ─── CLI ──────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Setup wizard for credentials + brand config")
    ap.add_argument("--site-slug", required=True, help="Project slug (e.g. example-com)")
    ap.add_argument("--site-url", default="", help="Site URL (https://example.com)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--status", action="store_true", help="Show current setup status (no prompts)")
    g.add_argument("--validate", action="store_true", help="Live-test all configured providers")
    g.add_argument("--interactive", action="store_true", help="Run interactive wizard (default)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    wiz = SetupWizard(args.site_slug, args.site_url)

    if args.status:
        status = wiz.detect_existing()
        if args.json:
            print(json.dumps({
                "site_slug": status.site_slug,
                "site_url": status.site_url,
                "providers": [asdict(p) for p in status.providers],
                "wp_credentials_present": status.wp_credentials_present,
                "brand_config_present": status.brand_config_present,
                "ready_for": status.overall_ready_for,
            }, indent=2, ensure_ascii=False))
        else:
            print(f"Site: {status.site_slug} ({status.site_url})")
            for p in status.providers:
                icon = "✓" if p.found else "✗"
                print(f"  {icon} {p.name:18s} {p.purpose}")
                if p.found:
                    print(f"      source: {p.source}")
            print(f"  {'✓' if status.wp_credentials_present else '✗'} WordPress credentials")
            print(f"  {'✓' if status.brand_config_present else '✗'} Brand config")
            print()
            for cap, ready in status.overall_ready_for.items():
                print(f"  ready for {cap:15s}: {'yes' if ready else 'NO'}")
        return 0

    if args.validate:
        results = wiz.validate_all()
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            for name, r in results.items():
                ok = r.get("ok")
                icon = "✓" if ok else "✗"
                ms = r.get("latency_ms", "")
                ms_str = f"({ms}ms)" if ms else ""
                if r.get("skipped"):
                    print(f"  ⊘ {name:18s} not configured")
                elif ok:
                    print(f"  {icon} {name:18s} OK {ms_str}")
                else:
                    print(f"  {icon} {name:18s} FAILED {ms_str}")
                    print(f"      {r.get('error', '')[:120]}")
        return 0

    # Default: interactive
    return interactive_wizard(args.site_slug, args.site_url)


if __name__ == "__main__":
    sys.exit(main())
