"""VietLaw Public Beta V0: official legal web-search contract.

Pure data shapes -- no network code lives here (see
`services/official_legal_search.py`). Kept separate from
`contracts/fast_demo.py` intentionally: this vertical's evidence model is not
a rental-deposit fact and must not be able to influence
`resolve_deposit_applicable_clause` or any other MODE_2D path.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .legal_trust import EvidenceOutcome


class LegalSearchQuery(BaseModel):
    """A bounded, redacted search query. Never carries conversation history,
    names, addresses, ID numbers, phone numbers, account numbers, or
    uploaded-document content -- see
    `services/legal_fallback_orchestrator.py::build_search_query` for the
    redaction step that constructs this."""

    model_config = ConfigDict(extra="forbid")

    query_text: str = Field(min_length=1, max_length=400)
    legal_topic_hint: str | None = None


class OfficialLegalSearchCandidate(BaseModel):
    """One retrieved-and-inspected candidate result (task §6.3). A search
    snippet alone is never enough to construct one of these -- the service
    must have fetched and parsed the actual official page content first."""

    model_config = ConfigDict(extra="forbid")

    title: str
    official_url: str
    official_domain: str
    document_name: str | None = None
    document_number: str | None = None
    article_number: str | None = None
    clause_number: str | None = None
    published_date: str | None = None
    effective_date: str | None = None
    retrieved_at: str
    relevant_excerpt: str = Field(max_length=2000)
    #: 0.0-1.0. Advisory only -- it can raise the bar the evidence gate
    #: applies, but by itself it can never pass the gate (task §6.4:
    #: "Model confidence alone must not pass this gate").
    retrieval_confidence: float = Field(ge=0.0, le=1.0)


class OfficialLegalSearchResult(BaseModel):
    """What `OfficialLegalSearchService.search()` returns. `outcome` is
    always present; `candidates` may be empty (zero results, or every
    candidate was rejected before construction)."""

    model_config = ConfigDict(extra="forbid")

    outcome: EvidenceOutcome
    candidates: list[OfficialLegalSearchCandidate] = Field(default_factory=list)
    #: Bounded, credential-free failure/insufficiency reason code, for
    #: observability -- never raw exception text or page content.
    reason_code: str | None = None


__all__ = [
    "LegalSearchQuery",
    "OfficialLegalSearchCandidate",
    "OfficialLegalSearchResult",
]
