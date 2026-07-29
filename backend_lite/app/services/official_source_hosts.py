"""Exact-host allowlist for the Civil Code official-source migration.

This is deliberately narrow: it validates only the three hosts verified for
Bộ luật Dân sự 91/2015/QH13 (`congbao.chinhphu.vn`, `vanban.chinhphu.vn`,
`vbpl.vn`). It is not a general trust policy for every source the app
displays -- other legal snippets (traffic, business) cite other verified
government hosts outside this set, and this module does not gate them.
"""

from __future__ import annotations

from urllib.parse import urlsplit

#: Exact hostnames only. No wildcard suffix ("*.gov.vn", "*.chinhphu.vn") is
#: accepted: a broad suffix match would also accept an attacker-registered
#: domain crafted to end with the same characters.
OFFICIAL_SOURCE_HOSTS = frozenset(
    {
        "congbao.chinhphu.vn",
        "vanban.chinhphu.vn",
        "vbpl.vn",
    }
)


def is_trusted_official_host(url: str | None) -> bool:
    """True only for an HTTPS URL whose hostname exactly matches an allowed host.

    Exact string equality (not `endswith`/suffix matching) is what rejects
    `congbao.chinhphu.vn.evil.example` -- a suffix check would treat that as
    ending in an allowed name. Comparing the full hostname to the parsed
    `hostname` (not the raw `netloc`) is what rejects an embedded-credentials
    form like `https://user@congbao.chinhphu.vn/x`, since `netloc` would
    otherwise still visually contain the allowed host text.
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
        # A non-numeric (":evil") or out-of-range (":65536") port. `.port`
        # raises rather than returning None, so this must be caught explicitly.
        return False
    if port is not None:
        # None of the three verified URLs carry an explicit port -- not even
        # the default ":443" -- so any explicit port is treated as a mismatch
        # from the verified form rather than silently accepted.
        return False

    return parsed.hostname.lower() in OFFICIAL_SOURCE_HOSTS


__all__ = ["OFFICIAL_SOURCE_HOSTS", "is_trusted_official_host"]
