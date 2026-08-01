"""VietLaw Public Beta V0: official legal-search service (task §13.3).

Every test here uses a deterministic fake -- `FakeOfficialLegalSearchService`
for orchestration-level outcomes, and `HttpOfficialLegalSearchService` wired
to an `httpx.MockTransport` for the low-level fetch/redirect/size/timeout
safety plumbing. Zero live network calls anywhere in this file.
"""

from __future__ import annotations

import httpx
import pytest

from backend_lite.app.contracts.legal_trust import EvidenceOutcome
from backend_lite.app.contracts.official_search import (
    LegalSearchQuery,
    OfficialLegalSearchCandidate,
)
from backend_lite.app.services.official_legal_search import (
    FakeOfficialLegalSearchService,
    HttpOfficialLegalSearchService,
)

_TRUSTED_URL = "https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=1"


def _candidate(**overrides) -> OfficialLegalSearchCandidate:
    base = dict(
        title="Nghị định mẫu",
        official_url=_TRUSTED_URL,
        official_domain="vbpl.vn",
        document_name="Nghị định mẫu",
        document_number="1/2025/ND-CP",
        effective_date="2025-01-01",
        retrieved_at="2026-07-31T00:00:00Z",
        relevant_excerpt="Nội dung điều khoản liên quan.",
        retrieval_confidence=0.8,
    )
    base.update(overrides)
    return OfficialLegalSearchCandidate(**base)


def _query() -> LegalSearchQuery:
    return LegalSearchQuery(query_text="test query")


# -- FakeOfficialLegalSearchService: orchestration-level outcomes -----------

@pytest.mark.asyncio
async def test_fake_service_returns_sufficient_for_a_well_formed_candidate() -> None:
    fake = FakeOfficialLegalSearchService(candidates=[_candidate()])
    result = await fake.search(_query())
    assert result.outcome is EvidenceOutcome.SUFFICIENT
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_fake_service_zero_results_is_unavailable() -> None:
    fake = FakeOfficialLegalSearchService(candidates=[])
    result = await fake.search(_query())
    assert result.outcome is EvidenceOutcome.UNAVAILABLE
    assert result.candidates == []


@pytest.mark.asyncio
async def test_fake_service_can_force_a_specific_outcome() -> None:
    fake = FakeOfficialLegalSearchService(outcome=EvidenceOutcome.CONFLICTING, reason_code="two_sources")
    result = await fake.search(_query())
    assert result.outcome is EvidenceOutcome.CONFLICTING
    assert result.reason_code == "two_sources"


@pytest.mark.asyncio
async def test_fake_service_raises_timeout_when_configured() -> None:
    fake = FakeOfficialLegalSearchService(raise_timeout=True)
    with pytest.raises(TimeoutError):
        await fake.search(_query())


@pytest.mark.asyncio
async def test_fake_service_raises_generic_error_when_configured() -> None:
    fake = FakeOfficialLegalSearchService(raise_error=True)
    with pytest.raises(RuntimeError):
        await fake.search(_query())


@pytest.mark.asyncio
async def test_fake_service_two_conflicting_documents_is_conflicting() -> None:
    first = _candidate(document_number="1/2025/ND-CP")
    second = _candidate(document_number="2/2025/ND-CP")
    fake = FakeOfficialLegalSearchService(candidates=[first, second])
    result = await fake.search(_query())
    assert result.outcome is EvidenceOutcome.CONFLICTING


@pytest.mark.asyncio
async def test_fake_service_snippet_only_candidate_is_unavailable() -> None:
    snippet_only = _candidate(document_name=None, document_number=None)
    fake = FakeOfficialLegalSearchService(candidates=[snippet_only])
    result = await fake.search(_query())
    assert result.outcome is EvidenceOutcome.UNAVAILABLE


# -- HttpOfficialLegalSearchService: fetch/redirect/size/timeout safety -----

def _http_service(handler, *, page_finder=None, **overrides) -> HttpOfficialLegalSearchService:
    async def default_page_finder(query: LegalSearchQuery) -> list[str]:
        return [_TRUSTED_URL]

    return HttpOfficialLegalSearchService(
        page_finder=page_finder or default_page_finder,
        transport=httpx.MockTransport(handler),
        **overrides,
    )


@pytest.mark.asyncio
async def test_http_service_accepts_an_allowlisted_source() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html="<title>Nghi dinh mau</title><body>noi dung dieu khoan</body>")

    service = _http_service(handler)
    result = await service.search(_query())
    assert len(result.candidates) == 1
    assert result.candidates[0].official_domain == "vbpl.vn"


@pytest.mark.asyncio
async def test_http_service_rejects_a_non_allowlisted_source() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html="<title>Fake</title><body>fake content</body>")

    async def page_finder(query: LegalSearchQuery) -> list[str]:
        return ["https://not-a-real-legal-site.com/doc"]

    service = _http_service(handler, page_finder=page_finder)
    result = await service.search(_query())
    assert result.candidates == []
    assert result.outcome is EvidenceOutcome.UNAVAILABLE


@pytest.mark.asyncio
async def test_http_service_rejects_a_redirect_outside_the_allowlist() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == _TRUSTED_URL:
            return httpx.Response(302, headers={"location": "https://evil.com/steal"})
        return httpx.Response(200, html="<title>Evil</title><body>evil</body>")

    service = _http_service(handler)
    result = await service.search(_query())
    assert result.candidates == []


@pytest.mark.asyncio
async def test_http_service_rejects_a_private_network_url_before_ever_fetching() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, html="<title>x</title><body>x</body>")

    async def page_finder(query: LegalSearchQuery) -> list[str]:
        return ["https://127.0.0.1/internal-admin"]

    service = _http_service(handler, page_finder=page_finder)
    result = await service.search(_query())
    assert result.candidates == []
    assert calls == []  # never even attempted the fetch


@pytest.mark.asyncio
async def test_http_service_rejects_oversized_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html="<title>Big</title><body>" + ("a" * 10) + "</body>")

    service = _http_service(handler, max_fetch_bytes=5)
    result = await service.search(_query())
    assert result.candidates == []


@pytest.mark.asyncio
async def test_http_service_drops_a_page_with_no_extractable_excerpt() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html="")

    service = _http_service(handler)
    result = await service.search(_query())
    assert result.candidates == []
    assert result.outcome is EvidenceOutcome.UNAVAILABLE


@pytest.mark.asyncio
async def test_http_service_page_finder_timeout_is_unavailable_not_a_raised_error() -> None:
    async def raising_page_finder(query: LegalSearchQuery) -> list[str]:
        raise TimeoutError("provider timed out")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html="<title>x</title><body>x</body>")

    service = _http_service(handler, page_finder=raising_page_finder)
    result = await service.search(_query())
    assert result.outcome is EvidenceOutcome.UNAVAILABLE
    assert result.reason_code == "search_timeout"


@pytest.mark.asyncio
async def test_http_service_page_finder_failure_is_unavailable_not_a_raised_error() -> None:
    async def raising_page_finder(query: LegalSearchQuery) -> list[str]:
        raise RuntimeError("provider exploded")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html="<title>x</title><body>x</body>")

    service = _http_service(handler, page_finder=raising_page_finder)
    result = await service.search(_query())
    assert result.outcome is EvidenceOutcome.UNAVAILABLE
    assert result.reason_code == "search_failed"


@pytest.mark.asyncio
async def test_http_service_zero_results_from_page_finder_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, html="<title>x</title><body>x</body>")

    async def empty_page_finder(query: LegalSearchQuery) -> list[str]:
        return []

    service = _http_service(handler, page_finder=empty_page_finder)
    result = await service.search(_query())
    assert result.candidates == []
    assert result.outcome is EvidenceOutcome.UNAVAILABLE


@pytest.mark.asyncio
async def test_http_service_non_200_status_is_dropped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, html="<title>Not found</title>")

    service = _http_service(handler)
    result = await service.search(_query())
    assert result.candidates == []
