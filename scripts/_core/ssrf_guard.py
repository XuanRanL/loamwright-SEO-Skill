"""
scripts/_core/ssrf_guard.py — SSRF protection for all URL fetches.

Every URL that the plugin's scripts pass to an HTTP client MUST be
validated through validate_url() first. This is the centralized policy
that blocks:

  - localhost / 127.0.0.0/8 / 0.0.0.0
  - Private IP ranges (RFC 1918):  10/8, 172.16/12, 192.168/16
  - Link-local (RFC 3927):  169.254/16  (includes cloud metadata 169.254.169.254)
  - Carrier-grade NAT (RFC 6598):  100.64/10
  - Multicast / reserved
  - IPv6 equivalents (::1, fc00::/7, fe80::/10)
  - Hostnames that DNS-resolve to any of the above

By default only http:// and https:// schemes are allowed. Trusted hosts
can be allowed via the allowlist parameter.

Usage:
    from scripts._core.ssrf_guard import validate_url, SSRFError

    try:
        clean = validate_url("https://example.com/page")
        # clean is a ValidatedURL named tuple with .url / .host / .scheme
    except SSRFError as e:
        log.warning(f"SSRF blocked: {e}")

Used by:
    scripts/fetch/fetch_page.py
    scripts/fetch/tavily_search.py
    scripts/fetch/crossref_lookup.py
    scripts/validate/link_resolver.py
    scripts/publish/indexnow_submit.py
    agents/researcher.md
    agents/linker.md
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import sys
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlparse, urlunparse, ParseResult


# ─── Blocklist definitions ──────────────────────────────────────────

# IPv4 private + special ranges
_BLOCKED_V4_NETWORKS: Final[list[ipaddress.IPv4Network]] = [
    ipaddress.IPv4Network("0.0.0.0/8"),       # "this network"
    ipaddress.IPv4Network("10.0.0.0/8"),      # private
    ipaddress.IPv4Network("100.64.0.0/10"),   # carrier-grade NAT
    ipaddress.IPv4Network("127.0.0.0/8"),     # loopback
    ipaddress.IPv4Network("169.254.0.0/16"),  # link-local (incl. metadata 169.254.169.254)
    ipaddress.IPv4Network("172.16.0.0/12"),   # private
    ipaddress.IPv4Network("192.0.0.0/24"),    # protocol assignments
    ipaddress.IPv4Network("192.0.2.0/24"),    # TEST-NET-1
    ipaddress.IPv4Network("192.168.0.0/16"),  # private
    ipaddress.IPv4Network("198.18.0.0/15"),   # benchmark
    ipaddress.IPv4Network("198.51.100.0/24"), # TEST-NET-2
    ipaddress.IPv4Network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.IPv4Network("224.0.0.0/4"),     # multicast
    ipaddress.IPv4Network("240.0.0.0/4"),     # reserved
    ipaddress.IPv4Network("255.255.255.255/32"),  # broadcast
]

_BLOCKED_V6_NETWORKS: Final[list[ipaddress.IPv6Network]] = [
    ipaddress.IPv6Network("::/128"),          # unspecified
    ipaddress.IPv6Network("::1/128"),         # loopback
    ipaddress.IPv6Network("::ffff:0:0/96"),   # IPv4-mapped
    ipaddress.IPv6Network("64:ff9b::/96"),    # IPv4/IPv6 translation
    ipaddress.IPv6Network("100::/64"),        # discard prefix
    ipaddress.IPv6Network("2001:db8::/32"),   # documentation
    ipaddress.IPv6Network("fc00::/7"),        # unique local
    ipaddress.IPv6Network("fe80::/10"),       # link-local
    ipaddress.IPv6Network("ff00::/8"),        # multicast
]

# Hostname blocklist (case-insensitive, exact match)
_BLOCKED_HOSTS: Final[set[str]] = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "metadata.google.internal",  # GCP metadata
    "169.254.169.254",           # AWS / GCP / Azure metadata
    "metadata.azure.com",        # Azure metadata
}

# Allowed URL schemes
_ALLOWED_SCHEMES: Final[set[str]] = {"http", "https"}


# ─── Exception ──────────────────────────────────────────────────────

class SSRFError(ValueError):
    """Raised when a URL fails SSRF policy checks."""


# ─── Result type ────────────────────────────────────────────────────

@dataclass(frozen=True)
class ValidatedURL:
    """A URL that has passed SSRF validation."""
    url: str
    host: str
    scheme: str
    port: int
    resolved_ip: str | None  # may be None if DNS skipped
    is_https: bool


# ─── Core API ───────────────────────────────────────────────────────

def validate_url(
    url: str,
    *,
    allow_http: bool = False,
    allow_hosts: list[str] | None = None,
    resolve_dns: bool = True,
    timeout_seconds: float = 3.0,
) -> ValidatedURL:
    """Validate URL against SSRF policy.

    Args:
        url: Input URL.
        allow_http: If False (default), only https:// allowed.
        allow_hosts: Explicit allowlist that bypasses private IP block
            (e.g. ["my-wordpress.local"] when running against test WP site).
        resolve_dns: If True, resolve hostname and check IP. Set False only
            for offline test fixtures.
        timeout_seconds: DNS resolution timeout.

    Returns:
        ValidatedURL with resolved IP.

    Raises:
        SSRFError: URL is malformed, scheme not allowed, hostname or IP blocked.
    """
    if not url or not isinstance(url, str):
        raise SSRFError(f"URL must be non-empty string, got {type(url).__name__}")

    if len(url) > 2048:
        raise SSRFError(f"URL too long ({len(url)} chars, max 2048)")

    try:
        parsed = urlparse(url.strip())
    except Exception as e:
        raise SSRFError(f"Cannot parse URL: {e}") from e

    # Scheme
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise SSRFError(f"Scheme {scheme!r} not allowed. Use http or https.")
    if scheme == "http" and not allow_http:
        raise SSRFError(f"http:// not allowed. Use https://. URL: {url}")

    # Host
    host = parsed.hostname
    if not host:
        raise SSRFError(f"URL missing host: {url}")
    host = host.lower()

    # Allowlist override
    if allow_hosts and host in {h.lower() for h in allow_hosts}:
        return ValidatedURL(
            url=url, host=host, scheme=scheme,
            port=parsed.port or (443 if scheme == "https" else 80),
            resolved_ip=None,
            is_https=(scheme == "https"),
        )

    # Hostname blocklist
    if host in _BLOCKED_HOSTS:
        raise SSRFError(f"Host {host!r} is in blocklist.")

    # If host is already an IP literal, check directly
    resolved_ip: str | None = None
    if _looks_like_ip(host):
        if _ip_in_blocked_ranges(host):
            raise SSRFError(f"IP {host!r} is in private/restricted range.")
        resolved_ip = host
    elif resolve_dns:
        # DNS resolution + IP check
        try:
            # getaddrinfo returns AF_INET / AF_INET6 records; check all
            results = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise SSRFError(f"DNS resolution failed for {host!r}: {e}") from e
        except OSError as e:
            raise SSRFError(f"Network error resolving {host!r}: {e}") from e

        ips = {r[4][0] for r in results}
        for ip in ips:
            if _ip_in_blocked_ranges(ip):
                raise SSRFError(
                    f"Host {host!r} resolves to blocked IP {ip!r}"
                )
        resolved_ip = next(iter(ips), None)

    # Port check (block common admin ports unless explicitly allowed)
    port = parsed.port or (443 if scheme == "https" else 80)
    if port in {22, 23, 25, 110, 143, 445, 3306, 5432, 6379, 11211, 27017}:
        raise SSRFError(f"Port {port} blocked (DB/admin service)")

    return ValidatedURL(
        url=url, host=host, scheme=scheme,
        port=port, resolved_ip=resolved_ip,
        is_https=(scheme == "https"),
    )


# ─── Helpers ─────────────────────────────────────────────────────

def _looks_like_ip(s: str) -> bool:
    """Return True if string is a valid IPv4 or IPv6 literal."""
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def _ip_in_blocked_ranges(ip_str: str) -> bool:
    """Check whether IP is in any blocked range."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False  # not an IP

    if isinstance(addr, ipaddress.IPv4Address):
        return any(addr in net for net in _BLOCKED_V4_NETWORKS)
    if isinstance(addr, ipaddress.IPv6Address):
        return any(addr in net for net in _BLOCKED_V6_NETWORKS)
    return False


# ─── CLI ────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="SSRF URL validator")
    ap.add_argument("urls", nargs="+", help="URLs to validate")
    ap.add_argument("--allow-http", action="store_true")
    ap.add_argument("--allow-host", action="append", default=[], help="Allow specific hosts")
    ap.add_argument("--no-dns", action="store_true", help="Skip DNS resolution")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    results = []
    overall_ok = True
    for url in args.urls:
        try:
            v = validate_url(
                url,
                allow_http=args.allow_http,
                allow_hosts=args.allow_host,
                resolve_dns=not args.no_dns,
            )
            results.append({
                "url": url, "valid": True,
                "host": v.host, "scheme": v.scheme,
                "port": v.port, "resolved_ip": v.resolved_ip,
            })
        except SSRFError as e:
            results.append({"url": url, "valid": False, "error": str(e)})
            overall_ok = False

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            icon = "✓" if r["valid"] else "✗"
            if r["valid"]:
                print(f"  {icon} {r['url']}  → {r['host']} ({r['resolved_ip']}) :{r['port']}")
            else:
                print(f"  {icon} {r['url']}")
                print(f"      {r['error']}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
