"""VietLaw Public Beta V0: official legal-search domain allowlist (task §6.2)."""

from __future__ import annotations

import pytest

from backend_lite.app.services.official_legal_domain_allowlist import (
    is_trusted_legal_search_host,
    validate_redirect_chain,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=1",
        "https://moj.gov.vn/some/path",
        "https://vanban.chinhphu.vn/?pageid=27160",
        "https://congbao.chinhphu.vn/",
        "https://chinhphu.vn/",
        "https://quochoi.vn/",
    ],
)
def test_allowlisted_https_host_is_trusted(url: str) -> None:
    assert is_trusted_legal_search_host(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "http://vbpl.vn/path",  # not HTTPS
        "https://not-a-real-legal-site.com/vbpl.vn",  # not an allowlisted host
        "https://evil.com/?redirect=vbpl.vn",
        "https://vbpl.vn.evil.com/",  # suffix-spoofing must not pass
        "https://user:pass@vbpl.vn/",  # embedded credentials
        "https://vbpl.vn:8443/",  # explicit port
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        None,
        "",
    ],
)
def test_non_allowlisted_or_unsafe_url_is_rejected(url) -> None:
    assert is_trusted_legal_search_host(url) is False


@pytest.mark.parametrize(
    "hostname_url",
    [
        "https://localhost/",
        "https://127.0.0.1/",
        "https://10.0.0.5/",
        "https://192.168.1.1/",
        "https://169.254.0.1/",
    ],
)
def test_private_or_local_network_url_is_rejected(hostname_url: str) -> None:
    assert is_trusted_legal_search_host(hostname_url) is False


def test_redirect_chain_fully_within_allowlist_is_valid() -> None:
    assert validate_redirect_chain(["https://vbpl.vn/a", "https://vbpl.vn/b"]) is True


def test_redirect_chain_with_one_untrusted_hop_is_rejected() -> None:
    assert validate_redirect_chain(["https://vbpl.vn/a", "https://evil.com/b"]) is False


def test_empty_redirect_chain_is_rejected() -> None:
    assert validate_redirect_chain([]) is False
