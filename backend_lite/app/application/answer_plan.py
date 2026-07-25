"""Deterministic semantic AnswerPlan construction with stable point IDs."""

from __future__ import annotations

import re

from .analysis_state import (
    AnalysisInvariantError,
    DecisionRecord,
    EvidenceResult,
    PlanPoint,
    RiskDisposition,
    SafetyContainmentResult,
    SafetyDisposition,
    StructuredAnswerPlan,
)

_POINT_ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*$")


def validate_point_id(point_id: str) -> None:
    if not _POINT_ID.fullmatch(point_id):
        raise AnalysisInvariantError("answer plan has malformed stable point ID")


def build_answer_plan(
    decision: DecisionRecord,
    evidence: EvidenceResult,
    containment: SafetyContainmentResult | None = None,
) -> StructuredAnswerPlan:
    source_ids = tuple(candidate.source_id for candidate in evidence.admitted)
    safety_uncertain = bool(
        containment is not None
        and containment.safety_disposition is SafetyDisposition.SAFETY_UNCERTAIN
    )
    if containment is not None and containment.safety_disposition is not SafetyDisposition.CLEAR and source_ids:
        raise AnalysisInvariantError("contained answer plan cannot expose sources")
    if safety_uncertain:
        if decision.decision != "ask_clarifying_questions":
            raise AnalysisInvariantError("safety uncertainty requires clarification")
        slots = (
            (
                "summary",
                "safety.clarification.summary.v1",
                "STATE_SAFE_INTENT_BOUNDARY",
            ),
            (
                "clarifying_questions",
                "safety.clarification.intent.v1",
                "ASK_REPORT_PREVENT_PROTECT_OR_PERFORM",
            ),
        )
        if containment.risk_disposition is RiskDisposition.HIGH_RISK:
            slots += (
                (
                    "next_steps",
                    "safety.clarification.professional_help.v1",
                    "RECOMMEND_QUALIFIED_HELP_WHILE_CLARIFYING",
                ),
            )
    elif decision.decision == "answer_with_guidance":
        slots = (("summary", "guidance.summary.v1", "SUMMARIZE_SUPPORTED_ROUTE"), ("next_steps", "guidance.next_steps.v1", "PROVIDE_BOUNDED_NEXT_STEP"))
    elif decision.decision == "ask_clarifying_questions":
        slots = (("summary", "clarification.summary.v1", "STATE_FACT_GAP"), ("clarifying_questions", "clarification.critical_facts.v1", "REQUEST_CRITICAL_FACTS"))
    elif decision.decision == "recommend_professional_help":
        slots = (("summary", "escalation.summary.v1", "STATE_HIGH_RISK_BOUNDARY"), ("next_steps", "escalation.professional_help.v1", "RECOMMEND_QUALIFIED_HELP"))
    elif decision.decision == "refuse_unsafe_request":
        slots = (("summary", "safety.refusal.v1", "REFUSE_UNSAFE_ASSISTANCE"), ("safe_alternative", "safety.safe_alternative.v1", "OFFER_LAWFUL_ALTERNATIVE"))
    else:
        slots = (("summary", "unsupported.boundary.v1", "STATE_UNSUPPORTED_BOUNDARY"),)
    points = tuple(
        PlanPoint(point_id, slot, instruction, source_ids if slot in {"summary", "next_steps"} else ())
        for slot, point_id, instruction in slots
    )
    for point in points:
        validate_point_id(point.point_id)
    values = {name: tuple(point.semantic_instruction for point in points if point.slot == name) for name in ("summary", "clarifying_questions", "checklist", "next_steps", "safe_alternative", "escalation_notice")}
    if decision.decision == "recommend_professional_help":
        values["escalation_notice"] = ("ESCALATION_NOTICE_REQUIRED",)
    elif safety_uncertain and containment is not None and containment.risk_disposition is RiskDisposition.HIGH_RISK:
        values["escalation_notice"] = ("SAFE_ESCALATION_NOTICE_REQUIRED",)
    return StructuredAnswerPlan(
        **values,
        admitted_source_ids=source_ids,
        ordered_points=points,
    )


__all__ = ["build_answer_plan", "validate_point_id"]
