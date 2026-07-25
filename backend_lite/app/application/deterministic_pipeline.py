"""Pure state-first Gate A3a pipeline with evidence before final decision."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from .analysis_state import (
    AnalysisInput,
    AnalysisInvariantError,
    AnalysisState,
    ConfidenceResult,
    DecisionRecord,
    DomainAssessment,
    EvidencePlan,
    EvidenceResult,
    FactCompleteness,
    ResolvedContext,
    RiskDisposition,
    SafetyAssessment,
    SafetyContainmentResult,
    SafetyDisposition,
    StructuredAnswerPlan,
    VersionSnapshot,
)
from .answer_plan import build_answer_plan, validate_point_id
from .confidence import calculate_confidence
from .context_resolution import resolve_context
from .domain_policy import classify_domain
from .evidence_policy import admit_evidence, create_evidence_plan
from .normalization import normalize_question
from .response_decision_policy import decide_response
from .safety_policy import assess_safety
from .safety_containment import (
    derive_safety_containment,
    validate_containment_against_safety,
)

# Twelve transforming/decision markers followed by the final validation marker.
STAGE_ORDER = (
    "validate_input",
    "normalize",
    "resolve_context",
    "classify_domain",
    "safety",
    "safety_containment",
    "fact_completeness",
    "evidence_requirements",
    "evidence_admission",
    "response_decision",
    "answer_plan",
    "confidence",
    "final_validation",
)


@dataclass(frozen=True, slots=True)
class _CanonicalAnalysis:
    normalized_question: str
    resolved_context: ResolvedContext
    domain: DomainAssessment
    fact_completeness: FactCompleteness
    safety: SafetyAssessment
    safety_containment: SafetyContainmentResult
    evidence_plan: EvidencePlan
    evidence: EvidenceResult
    decision: DecisionRecord
    answer_plan: StructuredAnswerPlan
    confidence: ConfidenceResult


def _validate_analysis_input(analysis_input: AnalysisInput) -> None:
    if not isinstance(analysis_input, AnalysisInput):
        raise AnalysisInvariantError("analysis input is not canonical")
    if analysis_input.language != "vi" or not analysis_input.version_stamps.policy_version:
        raise AnalysisInvariantError("analysis input language or versions are invalid")


def _derive_canonical_analysis(analysis_input: AnalysisInput) -> _CanonicalAnalysis:
    """Derive normal output without final validation or I/O."""

    _validate_analysis_input(analysis_input)
    normalized = normalize_question(analysis_input.current_question)
    context = resolve_context(analysis_input.current_facts, analysis_input.bounded_context)
    domain = classify_domain(normalized, context)
    safety = assess_safety(normalized, domain, evidence_available=False)
    containment = derive_safety_containment(normalized, safety)
    facts_complete = domain.facts_sufficient and not context.unresolved_ambiguities
    facts = FactCompleteness(
        facts_complete,
        () if facts_complete else ("FACTS_INCOMPLETE",),
    )
    evidence_plan = create_evidence_plan(domain, safety, facts, containment)
    evidence = admit_evidence(
        analysis_input.evidence_candidates,
        evidence_plan,
        normalized,
    )
    decision = decide_response(
        domain,
        safety,
        facts,
        evidence_plan,
        evidence,
        containment,
    )
    answer_plan = build_answer_plan(decision, evidence, containment)
    confidence = calculate_confidence(domain, safety, decision, evidence, context)
    return _CanonicalAnalysis(
        normalized,
        context,
        domain,
        facts,
        safety,
        containment,
        evidence_plan,
        evidence,
        decision,
        answer_plan,
        confidence,
    )


def validate_final_state(
    state: AnalysisState,
    authoritative_input: AnalysisInput,
) -> AnalysisState:
    _validate_analysis_input(authoritative_input)
    if not isinstance(state.original_input, AnalysisInput):
        raise AnalysisInvariantError("original input is missing")
    if state.original_input != authoritative_input:
        raise AnalysisInvariantError("authoritative input mismatch")
    if state.raw_current_question != authoritative_input.current_question:
        raise AnalysisInvariantError("raw question changed after input validation")
    if state.version_stamps != authoritative_input.version_stamps or not isinstance(
        state.version_stamps, VersionSnapshot
    ):
        raise AnalysisInvariantError("version stamps changed after input validation")
    if state.completed_stages != STAGE_ORDER:
        raise AnalysisInvariantError("analysis stages are missing or out of order")
    if state.completed_stages.index("response_decision") < state.completed_stages.index(
        "evidence_admission"
    ):
        raise AnalysisInvariantError("final decision precedes evidence admission")
    if not state.normalized_question.strip():
        raise AnalysisInvariantError("normalized question is blank")
    expected = _derive_canonical_analysis(authoritative_input)
    if (
        state.normalized_question != expected.normalized_question
        or state.resolved_context != expected.resolved_context
        or state.domain != expected.domain
        or state.fact_completeness != expected.fact_completeness
        or state.safety != expected.safety
    ):
        raise AnalysisInvariantError("canonical upstream analysis mismatch")
    if state.safety_containment != expected.safety_containment:
        raise AnalysisInvariantError("canonical safety containment mismatch")
    validate_containment_against_safety(state.safety_containment, state.safety)
    if state.evidence_plan != expected.evidence_plan:
        raise AnalysisInvariantError("canonical evidence plan mismatch")
    if state.evidence != expected.evidence:
        raise AnalysisInvariantError("canonical evidence admission mismatch")
    if state.decision != expected.decision:
        raise AnalysisInvariantError("canonical response decision mismatch")
    if state.answer_plan != expected.answer_plan:
        raise AnalysisInvariantError("canonical answer plan mismatch")
    if state.confidence != expected.confidence:
        raise AnalysisInvariantError("canonical confidence mismatch")
    if state.safety.unsafe_request and state.decision.decision != "refuse_unsafe_request":
        raise AnalysisInvariantError("unsafe request decision is incompatible")
    if (
        state.safety_containment.safety_disposition
        is SafetyDisposition.SAFETY_UNCERTAIN
        and state.decision.decision != "ask_clarifying_questions"
    ):
        raise AnalysisInvariantError("safety uncertainty decision is incompatible")
    if (
        state.safety_containment.safety_disposition
        is not SafetyDisposition.CLEAR
        and state.decision.decision == "answer_with_guidance"
    ):
        raise AnalysisInvariantError("contained safety state cannot receive guidance")
    if (
        state.safety.high_risk
        and not state.safety.unsafe_request
        and state.safety_containment.safety_disposition is SafetyDisposition.CLEAR
        and state.decision.decision != "recommend_professional_help"
    ):
        raise AnalysisInvariantError("high-risk decision is incompatible")
    admitted_ids = tuple(candidate.source_id for candidate in state.evidence.admitted)
    expected_domain = (
        "high_risk"
        if state.safety.unsafe_request or state.safety.high_risk
        else state.domain.domain
    )
    if (
        state.decision.domain != expected_domain
        or state.decision.risk_level != state.safety.risk_level
        or state.decision.facts_sufficient != state.fact_completeness.complete
        or state.decision.evidence_available != bool(admitted_ids)
    ):
        raise AnalysisInvariantError("final decision authority fields are inconsistent")
    if (
        len(admitted_ids) > state.evidence_plan.maximum_sources
        or (admitted_ids and not state.evidence_plan.sources_allowed)
        or (state.evidence_plan.evidence_required and not state.evidence_plan.sources_allowed)
    ):
        raise AnalysisInvariantError("evidence result is incompatible with its plan")
    if (
        state.safety_containment.safety_disposition
        is not SafetyDisposition.CLEAR
        and (
            admitted_ids
            or state.evidence_plan.sources_allowed
            or state.answer_plan.admitted_source_ids
        )
    ):
        raise AnalysisInvariantError("contained safety state exposes evidence")
    if len(set(admitted_ids)) != len(admitted_ids):
        raise AnalysisInvariantError("admitted evidence IDs are duplicated")
    conflicting_ids = {
        item.candidate.source_id
        for item in state.evidence.rejected
        if item.reason_code == "DUPLICATE_ID_CONFLICT"
    }
    if conflicting_ids & set(admitted_ids):
        raise AnalysisInvariantError("conflicting evidence ID was admitted")
    if state.answer_plan.admitted_source_ids != admitted_ids:
        raise AnalysisInvariantError("answer plan source IDs differ from admitted evidence")
    point_ids = tuple(point.point_id for point in state.answer_plan.ordered_points)
    if len(set(point_ids)) != len(point_ids):
        raise AnalysisInvariantError("answer plan point IDs are duplicated")
    for point in state.answer_plan.ordered_points:
        validate_point_id(point.point_id)
        if not set(point.source_ids).issubset(admitted_ids):
            raise AnalysisInvariantError("answer plan point cites rejected evidence")
    decision = state.decision.decision
    if decision == "answer_with_guidance":
        if not state.evidence_plan.evidence_required or not admitted_ids:
            raise AnalysisInvariantError("guidance lacks required admitted evidence")
        if not state.answer_plan.summary or not state.answer_plan.next_steps:
            raise AnalysisInvariantError("guidance plan shape is incomplete")
        if not any(point.source_ids for point in state.answer_plan.ordered_points):
            raise AnalysisInvariantError("guidance plan lacks an admitted source reference")
    if decision == "ask_clarifying_questions" and not state.answer_plan.clarifying_questions:
        raise AnalysisInvariantError("clarification plan shape is incomplete")
    if (
        state.safety_containment.safety_disposition
        is SafetyDisposition.SAFETY_UNCERTAIN
        and (
            state.answer_plan.summary != ("STATE_SAFE_INTENT_BOUNDARY",)
            or state.answer_plan.clarifying_questions
            != ("ASK_REPORT_PREVENT_PROTECT_OR_PERFORM",)
        )
    ):
        raise AnalysisInvariantError("safety clarification plan shape is incompatible")
    if (
        state.safety_containment.safety_disposition
        is SafetyDisposition.SAFETY_UNCERTAIN
        and state.safety_containment.risk_disposition is RiskDisposition.HIGH_RISK
        and (
            not state.answer_plan.next_steps
            or not state.answer_plan.escalation_notice
        )
    ):
        raise AnalysisInvariantError("high-risk safety clarification lacks escalation")
    if decision == "recommend_professional_help" and (
        not state.answer_plan.next_steps or not state.answer_plan.escalation_notice
    ):
        raise AnalysisInvariantError("escalation plan shape is incomplete")
    if decision in {"refuse_unsafe_request", "unsupported"} and (
        admitted_ids or state.answer_plan.admitted_source_ids
    ):
        raise AnalysisInvariantError("source-free decision contains public sources")
    if decision == "refuse_unsafe_request" and not state.answer_plan.safe_alternative:
        raise AnalysisInvariantError("refusal plan shape is incomplete")
    if decision == "unsupported" and not state.answer_plan.summary:
        raise AnalysisInvariantError("unsupported plan shape is incomplete")
    if (
        decision == "unsupported"
        and state.domain.status == "supported"
        and state.fact_completeness.complete
        and "EVIDENCE_INSUFFICIENT" not in state.decision.reason_codes
    ):
        raise AnalysisInvariantError("grounded flow lacks evidence-insufficiency reason")
    confidence_values = (
        state.confidence.domain,
        state.confidence.risk,
        state.confidence.answer,
    )
    if not state.confidence.factors or any(
        not isfinite(value) or value < 0 or value >= 1 for value in confidence_values
    ):
        raise AnalysisInvariantError("confidence is unbounded or unexplained")
    canonical_fields = (
        state.original_input.evidence_candidates,
        state.original_input.current_facts,
        state.original_input.identity_references,
        state.evidence.admitted,
        state.evidence.rejected,
        state.answer_plan.ordered_points,
        state.safety_containment.signal_ids,
        state.safety_containment.unresolved_signal_ids,
        state.safety_containment.reason_codes,
        state.confidence.factors,
        state.completed_stages,
    )
    if any(not isinstance(value, tuple) for value in canonical_fields):
        raise AnalysisInvariantError("state contains a mutable collection")
    return state


def run_deterministic_analysis(analysis_input: AnalysisInput) -> AnalysisState:
    canonical = _derive_canonical_analysis(analysis_input)
    state = AnalysisState(
        original_input=analysis_input,
        raw_current_question=analysis_input.current_question,
        normalized_question=canonical.normalized_question,
        resolved_context=canonical.resolved_context,
        domain=canonical.domain,
        fact_completeness=canonical.fact_completeness,
        safety=canonical.safety,
        safety_containment=canonical.safety_containment,
        evidence_plan=canonical.evidence_plan,
        evidence=canonical.evidence,
        decision=canonical.decision,
        answer_plan=canonical.answer_plan,
        confidence=canonical.confidence,
        completed_stages=STAGE_ORDER,
        version_stamps=analysis_input.version_stamps,
    )
    return validate_final_state(state, analysis_input)


def state_without_final_stage(state: AnalysisState) -> AnalysisState:
    return replace(state, completed_stages=state.completed_stages[:-1])


__all__ = ["STAGE_ORDER", "run_deterministic_analysis", "validate_final_state"]
