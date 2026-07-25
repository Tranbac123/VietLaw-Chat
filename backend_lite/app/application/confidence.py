"""Transparent deterministic diagnostic confidence, never legal correctness."""

from __future__ import annotations

from .analysis_state import ConfidenceResult, DecisionRecord, DomainAssessment, EvidenceResult, ResolvedContext, SafetyAssessment


def calculate_confidence(
    domain: DomainAssessment,
    safety: SafetyAssessment,
    decision: DecisionRecord,
    evidence: EvidenceResult,
    context: ResolvedContext,
) -> ConfidenceResult:
    factors = [f"DOMAIN_{domain.status.upper()}", f"DECISION_{decision.decision.upper()}"]
    domain_value = {"supported": 0.86, "ambiguous": 0.46, "unsupported": 0.2}[domain.status]
    risk_value = 0.9 if safety.unsafe_request or safety.high_risk else 0.7
    answer_value = {
        "answer_with_guidance": 0.84,
        "ask_clarifying_questions": 0.55,
        "recommend_professional_help": 0.66,
        "refuse_unsafe_request": 0.82,
        "unsupported": 0.3,
    }[decision.decision]
    if "EVIDENCE_INSUFFICIENT" in decision.reason_codes:
        factors.append("EVIDENCE_INSUFFICIENT")
    if context.unresolved_ambiguities:
        domain_value -= 0.1
        answer_value -= 0.1
        factors.append("UNRESOLVED_AMBIGUITY")
    if context.conflicts:
        domain_value -= 0.15
        answer_value -= 0.15
        factors.append("CONTEXT_CONFLICT")
    bounded = lambda value: round(max(0.0, min(0.99, value)), 2)  # noqa: E731 - local bound
    return ConfidenceResult(bounded(domain_value), bounded(risk_value), bounded(answer_value), tuple(factors))


__all__ = ["calculate_confidence"]
