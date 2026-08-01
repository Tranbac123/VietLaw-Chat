"""Exact-host allowlist for the Public Beta V0 official legal-search fallback.

Deliberately separate from `official_source_hosts.py` (the frozen MODE_2D
Civil-Code-only allowlist, three hosts, not modified by this task). This
module governs which official Vietnamese government / legal-publication
hosts the NEW official-search vertical may ever cite, and is intentionally
broader in scope but no less strict in validation.

Every rule from the Civil-Code validator is reused: HTTPS only, exact
hostname (never a suffix/wildcard match), no embedded credentials, no
explicit port. Two additional checks exist here because this validator also
gates live HTTP fetches (the Civil-Code one only gates static curated
strings): a redirect target must itself be re-validated against the same
allowlist, and a private/loopback/link-local address must never be treated
as trusted regardless of hostname spelling.
"""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit

#: Exact hostnames only. Configurable via environment for ops flexibility
#: (task §6.2: "Store this allowlist in backend configuration"), but the
#: default set below is the only one ever active unless an operator
#: explicitly overrides it -- and the override is itself validated (any
#: entry that is not a bare, lowercase, dot-containing hostname is dropped).
DEFAULT_OFFICIAL_LEGAL_SEARCH_HOSTS = frozenset(
    {
        # Cong bao (Official Gazette) and the Government e-portal.
        "congbao.chinhphu.vn",
        "vanban.chinhphu.vn",
        "chinhphu.vn",
        # Vietnam Legal Normative Document Database (Bo Tu phap).
        "vbpl.vn",
        "moj.gov.vn",
        # National Assembly's own legal-document portal.
        "quochoi.vn",
    }
)


def _env_override_hosts() -> frozenset[str] | None:
    raw = (os.environ.get("VIETLAW_OFFICIAL_LEGAL_SEARCH_HOSTS") or "").strip()
    if not raw:
        return None
    hosts = {
        entry.strip().lower()
        for entry in raw.split(",")
        if entry.strip() and "." in entry.strip() and "/" not in entry.strip()
    }
    return frozenset(hosts) if hosts else None


def official_legal_search_hosts() -> frozenset[str]:
    return _env_override_hosts() or DEFAULT_OFFICIAL_LEGAL_SEARCH_HOSTS


def _is_private_or_local_host(hostname: str) -> bool:
    """True for localhost, loopback, private, and link-local addresses.

    A hostname that is not a literal IP address (the overwhelmingly common
    case for a real government domain) always returns False here -- DNS
    resolution is deliberately out of scope for this pure, offline-testable
    check; the caller is responsible for re-validating the ADDRESS actually
    connected to at fetch time, not just the URL's hostname text.
    """

    if hostname in {"localhost", "localhost.localdomain"}:
        return True
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved


def is_trusted_legal_search_host(url: str | None) -> bool:
    """True only for an HTTPS URL whose hostname exactly matches an allowed
    official legal-search host, is not a private/loopback/link-local
    address, and carries no embedded credentials or explicit port.

    Mirrors `official_source_hosts.is_trusted_official_host`'s exact
    validation shape (see that module's docstring for why exact-hostname
    comparison, not suffix matching, is required).
    """

    if not isinstance(url, str) or not url.strip():
        return False

    parsed = urlsplit(url.strip())

    if parsed.scheme != "https":
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if not parsed.hostname:
        return False

    try:
        port = parsed.port
    except ValueError:
        return False
    if port is not None:
        return False

    hostname = parsed.hostname.lower()
    if _is_private_or_local_host(hostname):
        return False

    return hostname in official_legal_search_hosts()


def validate_redirect_chain(urls: list[str]) -> bool:
    """True only when EVERY URL in a redirect chain (initial request plus
    every hop) is itself a trusted host. One untrusted hop anywhere in the
    chain fails the whole chain closed -- task §6.2: "no redirects to
    non-allowlisted domains"."""

    if not urls:
        return False
    return all(is_trusted_legal_search_host(url) for url in urls)


__all__ = [
    "DEFAULT_OFFICIAL_LEGAL_SEARCH_HOSTS",
    "is_trusted_legal_search_host",
    "official_legal_search_hosts",
    "validate_redirect_chain",
]
