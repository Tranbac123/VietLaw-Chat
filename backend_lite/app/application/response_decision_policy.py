"""Sole final response-decision authority, after EvidenceGuard."""

from __future__ import annotations

from .analysis_state import (
    AnalysisInvariantError,
    DecisionRecord,
    DomainAssessment,
    EvidencePlan,
    EvidenceResult,
    FactCompleteness,
    RiskDisposition,
    SafetyAssessment,
    SafetyContainmentResult,
    SafetyDisposition,
)
from .safety_containment import validate_containment_against_safety


def decide_response(
    domain: DomainAssessment,
    safety: SafetyAssessment,
    facts: FactCompleteness,
    evidence_plan: EvidencePlan,
    evidence: EvidenceResult,
    containment: SafetyContainmentResult | None = None,
) -> DecisionRecord:
    if containment is not None:
        validate_containment_against_safety(containment, safety)
    admitted = bool(evidence.admitted)
    if (
        containment is not None
        and containment.safety_disposition is not SafetyDisposition.CLEAR
        and (admitted or evidence_plan.sources_allowed)
    ):
        raise AnalysisInvariantError("contained safety state received evidence authority")
    reasons: tuple[str, ...]
    if (
        containment is not None
        and containment.safety_disposition is SafetyDisposition.PROVEN_DIRECT_HARM
    ) or (containment is None and safety.unsafe_request):
        decision, reasons = "refuse_unsafe_request", ("decision.unsafe_refusal.v1",)
    elif (
        containment is not None
        and containment.safety_disposition is SafetyDisposition.SAFETY_UNCERTAIN
    ):
        decision, reasons = "ask_clarifying_questions", (
            "decision.safety_containment_clarification.v1",
        )
    elif (
        containment is not None
        and containment.risk_disposition is RiskDisposition.HIGH_RISK
    ) or (containment is None and safety.high_risk):
        decision, reasons = "recommend_professional_help", ("decision.high_risk_escalation.v1",)
    elif domain.status == "unsupported":
        decision, reasons = "unsupported", ("decision.unsupported.v1",)
    elif safety.needs_intent_clarification:
        decision, reasons = "ask_clarifying_questions", (
            "decision.safety_intent_clarification.v1",
        )
    elif not facts.complete:
        decision, reasons = "ask_clarifying_questions", ("decision.missing_facts.v1",)
    elif evidence_plan.evidence_required and not admitted:
        decision, reasons = "unsupported", (
            "decision.evidence_insufficient.v1",
            "EVIDENCE_INSUFFICIENT",
        )
    elif evidence_plan.evidence_required and admitted:
        decision, reasons = "answer_with_guidance", ("decision.supported_guidance.v1",)
    else:
        raise ValueError("analysis constraints have no final response decision")
    resolved_domain = (
        "high_risk"
        if safety.unsafe_request or safety.high_risk
        else domain.domain
    )
    return DecisionRecord(
        resolved_domain,
        safety.risk_level,
        decision,  # type: ignore[arg-type]
        reasons,
        facts.complete,
        admitted,
    )


__all__ = ["decide_response"]
