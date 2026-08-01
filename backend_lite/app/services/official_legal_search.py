"""VietLaw Public Beta V0: official legal web-search service.

Models the interface on `demo_llm_client.py`'s `LLMClientProtocol` shape --
this is the second "external call" pattern this codebase has ever had (see
the architecture report, §5), so it is deliberately conservative: bounded
timeout, no retry loop, no logging of raw page/user content, and an
allowlist check before *and after* following any redirect.

Three implementations:

  * `OfficialLegalSearchService` -- the `Protocol` every caller depends on.
  * `FakeOfficialLegalSearchService` -- deterministic test double. Every test
    in this repository for this vertical uses this; zero live network calls.
  * `HttpOfficialLegalSearchService` -- a structurally-real `httpx`-based
    implementation, gated off by default
    (`VIETLAW_OFFICIAL_LEGAL_SEARCH_ENABLED`) and NOT wired to any specific
    search-provider API in this task: no search-provider contract or
    credentials were specified, and inventing one would mean guessing an
    integration the task's own "do not fabricate" principle rules out. It
    fetches and validates an already-known-candidate URL against the
    allowlist (i.e. it is the "fetch and inspect the official page" half of
    the pipeline); the "which URLs to consider" half (an actual search
    query issued to a real search API) is intentionally left as a single
    injectable callable (`page_finder`) so a future task can wire a real
    provider without touching this module's safety logic again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Protocol

import httpx

from ..contracts.legal_trust import EvidenceOutcome
from ..contracts.official_search import (
    LegalSearchQuery,
    OfficialLegalSearchCandidate,
    OfficialLegalSearchResult,
)
from .official_legal_domain_allowlist import (
    is_trusted_legal_search_host,
    validate_redirect_chain,
)
from .official_source_validator import evaluate_evidence_sufficiency

#: Hard ceiling shared by every implementation -- task §11.
MAX_FETCH_BYTES = 500_000
MAX_REDIRECTS = 3
DEFAULT_TIMEOUT_S = 8.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class OfficialLegalSearchService(Protocol):
    async def search(self, query: LegalSearchQuery) -> OfficialLegalSearchResult: ...


class FakeOfficialLegalSearchService:
    """Deterministic test double. Queue exactly the candidates (or the bare
    outcome, for UNAVAILABLE/zero-result cases) each test needs; never
    touches the network."""

    def __init__(
        self,
        *,
        candidates: list[OfficialLegalSearchCandidate] | None = None,
        outcome: EvidenceOutcome | None = None,
        reason_code: str | None = None,
        raise_timeout: bool = False,
        raise_error: bool = False,
    ) -> None:
        self._candidates = candidates or []
        self._forced_outcome = outcome
        self._reason_code = reason_code
        self._raise_timeout = raise_timeout
        self._raise_error = raise_error
        self.calls: list[LegalSearchQuery] = []

    async def search(self, query: LegalSearchQuery) -> OfficialLegalSearchResult:
        self.calls.append(query)
        if self._raise_timeout:
            raise TimeoutError("fake official legal search timeout")
        if self._raise_error:
            raise RuntimeError("fake official legal search failure")
        outcome = self._forced_outcome or evaluate_evidence_sufficiency(self._candidates)
        return OfficialLegalSearchResult(
            outcome=outcome,
            candidates=self._candidates,
            reason_code=self._reason_code,
        )


PageFinder = Callable[[LegalSearchQuery], Awaitable[list[str]]]


@dataclass
class HttpOfficialLegalSearchService:
    """Structurally-complete, allowlist-gated, bounded-timeout HTTP fetcher.

    `page_finder(query) -> list[str]` must return candidate URLs to inspect
    (e.g. from a real search API) -- this class does not itself decide which
    URLs exist, only whether an offered URL may be trusted, fetched, and
    turned into an `OfficialLegalSearchCandidate`. Not wired to a concrete
    `page_finder` anywhere in this task; see the module docstring.
    """

    page_finder: PageFinder
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_fetch_bytes: int = MAX_FETCH_BYTES
    max_redirects: int = MAX_REDIRECTS
    #: Injectable `httpx` transport. `None` (default) uses a real network
    #: connection; tests pass an `httpx.MockTransport` so the fetch/redirect/
    #: size/timeout safety logic can be exercised with zero live network
    #: calls (task §13.3).
    transport: httpx.AsyncBaseTransport | None = None
    _client: httpx.AsyncClient | None = field(default=None, repr=False)

    async def search(self, query: LegalSearchQuery) -> OfficialLegalSearchResult:
        try:
            candidate_urls = await self.page_finder(query)
        except TimeoutError:
            return OfficialLegalSearchResult(
                outcome=EvidenceOutcome.UNAVAILABLE, reason_code="search_timeout"
            )
        except Exception:  # noqa: BLE001 - contain; never leak a raw error/page content
            return OfficialLegalSearchResult(
                outcome=EvidenceOutcome.UNAVAILABLE, reason_code="search_failed"
            )

        candidates: list[OfficialLegalSearchCandidate] = []
        for url in candidate_urls[:5]:
            candidate = await self._fetch_and_validate(url)
            if candidate is not None:
                candidates.append(candidate)

        outcome = evaluate_evidence_sufficiency(candidates)
        return OfficialLegalSearchResult(outcome=outcome, candidates=candidates)

    async def _fetch_and_validate(self, url: str) -> OfficialLegalSearchCandidate | None:
        """Fetch one candidate URL, or return None (never raise) if it is
        untrusted, unreachable, unparseable, or oversized.

        A search SNIPPET alone is never sufficient (task §6.3): this method
        always performs the fetch, and any failure to do so drops the
        candidate rather than falling back to snippet-only text.
        """

        if not is_trusted_legal_search_host(url):
            return None
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_s,
                follow_redirects=True,
                max_redirects=self.max_redirects,
                transport=self.transport,
            ) as client:
                response = await client.get(url)
        except (httpx.TimeoutException, httpx.HTTPError):
            return None
        except Exception:  # noqa: BLE001 - contain; never leak raw content
            return None

        redirect_chain = [str(r.request.url) for r in response.history] + [str(response.url)]
        if not validate_redirect_chain(redirect_chain):
            return None
        if len(response.content) > self.max_fetch_bytes:
            return None
        if response.status_code != 200:
            return None

        excerpt = _extract_excerpt(response.text)
        if not excerpt:
            return None

        parsed_host = str(response.url).split("/")[2] if "//" in str(response.url) else ""
        return OfficialLegalSearchCandidate(
            title=_extract_title(response.text) or url,
            official_url=str(response.url),
            official_domain=parsed_host,
            retrieved_at=_utc_now_iso(),
            relevant_excerpt=excerpt,
            retrieval_confidence=0.5,
        )


def _extract_title(html: str) -> str:
    lower = html.lower()
    start = lower.find("<title>")
    end = lower.find("</title>")
    if start == -1 or end == -1 or end <= start:
        return ""
    return html[start + len("<title>"): end].strip()[:200]


def _extract_excerpt(html: str) -> str:
    """Bounded, deliberately unsophisticated text extraction: strip tags,
    collapse whitespace, cap length. A production integration would use a
    real HTML-to-text pipeline; this is enough to keep the candidate's
    `relevant_excerpt` non-empty and bounded without adding an HTML-parsing
    dependency to this task."""

    import re

    text = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:2000]


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "MAX_FETCH_BYTES",
    "MAX_REDIRECTS",
    "FakeOfficialLegalSearchService",
    "HttpOfficialLegalSearchService",
    "OfficialLegalSearchService",
]
