"""Pre-decision evidence requirements and fail-closed admission."""

from __future__ import annotations

import re
from collections import defaultdict

from .analysis_state import (
    DomainAssessment,
    EvidenceCandidate,
    EvidencePlan,
    EvidenceResult,
    FactCompleteness,
    RejectedEvidence,
    SafetyContainmentResult,
    SafetyDisposition,
    SafetyAssessment,
)
from .safety_containment import validate_containment_against_safety

_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")


def create_evidence_plan(
    domain: DomainAssessment,
    safety: SafetyAssessment,
    facts: FactCompleteness,
    containment: SafetyContainmentResult | None = None,
) -> EvidencePlan:
    if containment is not None:
        validate_containment_against_safety(containment, safety)
    resolved_domain = "high_risk" if safety.unsafe_request or safety.high_risk else domain.domain
    if containment is not None and containment.safety_disposition in {
        SafetyDisposition.PROVEN_DIRECT_HARM,
        SafetyDisposition.SAFETY_UNCERTAIN,
    }:
        rationale = (
            "evidence.plan.unsafe.v1"
            if containment.safety_disposition is SafetyDisposition.PROVEN_DIRECT_HARM
            else "evidence.plan.safety_uncertain.v1"
        )
        return EvidencePlan((), (), False, False, resolved_domain, 0, (rationale,))
    if safety.unsafe_request:
        return EvidencePlan((), (), False, False, resolved_domain, 0, ("evidence.plan.unsafe.v1",))
    if domain.status == "unsupported":
        return EvidencePlan((), (), False, False, domain.domain, 0, ("evidence.plan.unsupported.v1",))
    if safety.high_risk:
        return EvidencePlan((), ("approved_legal_evidence",), True, False, resolved_domain, 3, ("evidence.plan.high_risk_optional.v1",))
    if not facts.complete:
        return EvidencePlan((), (), False, False, domain.domain, 0, ("evidence.plan.incomplete_facts.v1",))
    return EvidencePlan(("approved_legal_evidence",), (), True, True, domain.domain, 3, ("evidence.plan.normal_required.v1",))


def _candidate_rejection(
    candidate: EvidenceCandidate, plan: EvidencePlan, normalized_question: str
) -> str | None:
    folded = normalized_question.casefold()
    if not plan.sources_allowed:
        return "EVIDENCE_PLAN_DISALLOWS_SOURCES"
    if not candidate.approved:
        return "EVIDENCE_NOT_APPROVED"
    if candidate.domain != plan.compatible_domain:
        return "EVIDENCE_WRONG_DOMAIN"
    if candidate.source_type == "safety_policy":
        return "EVIDENCE_INTERNAL_POLICY_NOT_LEGAL_SOURCE"
    if (
        not candidate.metadata_valid
        or not _SOURCE_ID.fullmatch(candidate.source_id)
        or not candidate.source_version.strip()
    ):
        return "EVIDENCE_INVALID_METADATA"
    if candidate.relevance_score <= 0 or not any(
        tag.casefold() in folded for tag in candidate.relevance_tags
    ):
        return "EVIDENCE_NOT_RELEVANT"
    return None


def admit_evidence(
    candidates: tuple[EvidenceCandidate, ...],
    plan: EvidencePlan,
    normalized_question: str,
) -> EvidenceResult:
    groups: dict[str, list[EvidenceCandidate]] = defaultdict(list)
    for candidate in candidates:
        groups[candidate.source_id].append(candidate)
    admitted: list[EvidenceCandidate] = []
    rejected: list[RejectedEvidence] = []
    for source_id in sorted(groups):
        group = sorted(groups[source_id], key=EvidenceCandidate.authority_signature)
        signatures = {candidate.authority_signature() for candidate in group}
        if len(signatures) > 1:
            rejected.extend(
                RejectedEvidence(candidate, "DUPLICATE_ID_CONFLICT") for candidate in group
            )
            continue
        canonical = group[0]
        reason = _candidate_rejection(canonical, plan, normalized_question)
        if reason is None and len(admitted) < plan.maximum_sources:
            admitted.append(canonical)
        else:
            rejected.append(
                RejectedEvidence(
                    canonical,
                    reason or "EVIDENCE_BOUNDED_LIMIT",
                )
            )
        rejected.extend(
            RejectedEvidence(candidate, "EVIDENCE_EXACT_DUPLICATE") for candidate in group[1:]
        )
    return EvidenceResult(tuple(admitted), tuple(rejected))


__all__ = ["admit_evidence", "create_evidence_plan"]
