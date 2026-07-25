"""Sole deterministic safety-assessment authority for the A3a kernel."""

from __future__ import annotations

from .analysis_state import DomainAssessment, SafetyAssessment
from .safety_intent import analyze_safety_intent


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


def assess_safety(
    normalized_question: str,
    domain: DomainAssessment,
    *,
    evidence_available: bool,
) -> SafetyAssessment:
    """Classify only the normalized current turn through bounded clause rules."""

    del domain, evidence_available
    signals = analyze_safety_intent(normalized_question)
    direct = bool(signals.direct_harm_matches)
    high_risk = bool(signals.high_risk_rule_ids)
    if direct:
        matched_rule_ids = tuple(
            match.stable_rule_id for match in signals.direct_harm_matches
        )
        reasons = _ordered_unique(
            tuple(match.reason_code for match in signals.direct_harm_matches)
        )
    else:
        matched_rule_ids = signals.high_risk_rule_ids
        reasons = signals.high_risk_reason_codes
    risk_level = (
        "high"
        if direct or high_risk
        else "medium"
        if signals.intent_mode == "AMBIGUOUS"
        else "low"
    )
    return SafetyAssessment(
        risk_level,  # type: ignore[arg-type]
        reasons,
        direct,
        high_risk,
        matched_rule_ids,
        reasons,
        signals.intent_mode,
        signals.safe_context_rule_ids,
        signals.intent_mode == "AMBIGUOUS",
    )


__all__ = ["assess_safety"]
