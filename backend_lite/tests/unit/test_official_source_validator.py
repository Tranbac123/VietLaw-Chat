"""VietLaw Public Beta V0: evidence-sufficiency gate (task §6.4).

Pure-function tests, no network. Model confidence alone must never pass the
gate -- only a structurally-complete, allowlisted, non-conflicting candidate
set with confidence at or above the threshold can produce SUFFICIENT.
"""

from __future__ import annotations

from backend_lite.app.contracts.legal_trust import EvidenceOutcome
from backend_lite.app.contracts.official_search import OfficialLegalSearchCandidate
from backend_lite.app.services.official_source_validator import (
    evaluate_evidence_sufficiency,
    select_primary_candidate,
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


def test_zero_candidates_is_unavailable() -> None:
    assert evaluate_evidence_sufficiency([]) is EvidenceOutcome.UNAVAILABLE


def test_snippet_only_candidate_without_document_identity_is_unavailable() -> None:
    candidate = _candidate(document_name=None, document_number=None)
    assert evaluate_evidence_sufficiency([candidate]) is EvidenceOutcome.UNAVAILABLE


def test_empty_excerpt_candidate_is_unavailable() -> None:
    candidate = _candidate(relevant_excerpt="")
    assert evaluate_evidence_sufficiency([candidate]) is EvidenceOutcome.UNAVAILABLE


def test_non_allowlisted_host_candidate_is_unavailable() -> None:
    candidate = _candidate(official_url="https://not-a-real-legal-site.com/doc")
    assert evaluate_evidence_sufficiency([candidate]) is EvidenceOutcome.UNAVAILABLE


def test_low_confidence_structurally_complete_candidate_is_insufficient() -> None:
    candidate = _candidate(retrieval_confidence=0.1)
    assert evaluate_evidence_sufficiency([candidate]) is EvidenceOutcome.INSUFFICIENT


def test_model_confidence_alone_cannot_pass_the_gate() -> None:
    # Maximum confidence, but no document identity resolved -- confidence
    # alone must never substitute for the structural checks.
    candidate = _candidate(document_name=None, document_number=None, retrieval_confidence=1.0)
    assert evaluate_evidence_sufficiency([candidate]) is EvidenceOutcome.UNAVAILABLE


def test_two_candidates_citing_different_documents_is_conflicting() -> None:
    first = _candidate(document_number="1/2025/ND-CP")
    second = _candidate(document_number="2/2025/ND-CP")
    assert evaluate_evidence_sufficiency([first, second]) is EvidenceOutcome.CONFLICTING


def test_same_document_with_conflicting_effective_dates_is_conflicting() -> None:
    first = _candidate(effective_date="2025-01-01")
    second = _candidate(effective_date="2025-06-01")
    assert evaluate_evidence_sufficiency([first, second]) is EvidenceOutcome.CONFLICTING


def test_well_formed_candidate_is_sufficient() -> None:
    assert evaluate_evidence_sufficiency([_candidate()]) is EvidenceOutcome.SUFFICIENT


def test_select_primary_candidate_picks_the_highest_confidence_complete_one() -> None:
    weak = _candidate(retrieval_confidence=0.65)
    strong = _candidate(retrieval_confidence=0.9)
    incomplete = _candidate(document_name=None, document_number=None, retrieval_confidence=0.99)
    primary = select_primary_candidate([weak, strong, incomplete])
    assert primary is strong


def test_select_primary_candidate_returns_none_when_all_incomplete() -> None:
    incomplete = _candidate(document_name=None, document_number=None)
    assert select_primary_candidate([incomplete]) is None
