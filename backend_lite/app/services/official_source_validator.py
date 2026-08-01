"""Deterministic evidence-sufficiency gate (task §6.4).

Pure functions only -- no network code, no LLM call. This is what makes the
gate deterministic and independently testable: given a list of candidates
already retrieved by `OfficialLegalSearchService`, decide SUFFICIENT /
INSUFFICIENT / CONFLICTING / UNAVAILABLE with no side effects.

Model confidence (`retrieval_confidence`) can only ever narrow acceptance
(raise the bar), never substitute for the structural checks below -- that is
the literal requirement "Model confidence alone must not pass this gate."
"""

from __future__ import annotations

from .official_legal_domain_allowlist import is_trusted_legal_search_host

#: Below this, a candidate's relevance is not trusted even if every
#: structural field is present. Bounded and conservative on purpose: a
#: borderline match must not silently become "sufficient".
MIN_RETRIEVAL_CONFIDENCE = 0.6


def _candidate_is_structurally_complete(candidate) -> bool:
    """Task §6.4 checks 1-3: official domain validated, document identity
    resolved, relevant provision text retrieved."""

    if not is_trusted_legal_search_host(candidate.official_url):
        return False
    if not candidate.document_name and not candidate.document_number:
        return False
    if not candidate.relevant_excerpt or not candidate.relevant_excerpt.strip():
        return False
    return True


def _effective_dates_conflict(candidates) -> bool:
    """A crude but safe check: if two structurally-complete candidates name
    the SAME document but different non-empty effective dates, that is a
    conflict the gate must not silently resolve by picking one."""

    seen: dict[str, str] = {}
    for candidate in candidates:
        if not candidate.effective_date:
            continue
        key = candidate.document_number or candidate.document_name or ""
        if not key:
            continue
        if key in seen and seen[key] != candidate.effective_date:
            return True
        seen[key] = candidate.effective_date
    return False


def _documents_conflict(candidates) -> bool:
    """Two structurally-complete candidates citing genuinely different
    documents for what the caller believes is the same question is exactly
    the "two conflicting official sources" required test case -- the gate
    must surface this as CONFLICTING rather than silently preferring the
    first result."""

    document_keys = {
        (candidate.document_number or candidate.document_name or "").strip()
        for candidate in candidates
        if (candidate.document_number or candidate.document_name)
    }
    document_keys.discard("")
    return len(document_keys) > 1


def evaluate_evidence_sufficiency(
    candidates: list,
    *,
    min_confidence: float = MIN_RETRIEVAL_CONFIDENCE,
):
    """Return the deterministic `EvidenceOutcome` for this candidate set.

    Import is local to avoid a hard import-time dependency for callers that
    only need the pure evaluation function (keeps this module importable
    without pulling in the full contracts package at module load time in
    contexts where that matters, e.g. lightweight tests).
    """

    from ..contracts.legal_trust import EvidenceOutcome

    if not candidates:
        return EvidenceOutcome.UNAVAILABLE

    structurally_complete = [c for c in candidates if _candidate_is_structurally_complete(c)]
    if not structurally_complete:
        return EvidenceOutcome.UNAVAILABLE

    if _documents_conflict(structurally_complete):
        return EvidenceOutcome.CONFLICTING
    if _effective_dates_conflict(structurally_complete):
        return EvidenceOutcome.CONFLICTING

    confident = [c for c in structurally_complete if c.retrieval_confidence >= min_confidence]
    if not confident:
        return EvidenceOutcome.INSUFFICIENT

    return EvidenceOutcome.SUFFICIENT


def select_primary_candidate(candidates: list):
    """Given a SUFFICIENT candidate set, return the one candidate an answer
    may be grounded on -- the single highest-confidence structurally-complete
    entry. Callers must only invoke this after confirming
    `evaluate_evidence_sufficiency(...) is EvidenceOutcome.SUFFICIENT`."""

    complete = [c for c in candidates if _candidate_is_structurally_complete(c)]
    if not complete:
        return None
    return max(complete, key=lambda c: c.retrieval_confidence)


__all__ = [
    "MIN_RETRIEVAL_CONFIDENCE",
    "evaluate_evidence_sufficiency",
    "select_primary_candidate",
]
