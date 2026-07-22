"""Decision policy.

Risk and decision are separate axes. Unsafe intent routes to refuse/escalate;
high_risk domain escalates; unknown is unsupported; otherwise the matched group's
expected_decision applies, defaulting to asking for missing facts.
"""
from app.triage.legal_triage import DomainResult
from app.triage.risk_classifier import RiskResult
from app.schemas import Decision, Domain
from app.triage.unsafe_intent_detector import UnsafeResult


def decide(dom: DomainResult, risk: RiskResult, unsafe: UnsafeResult) -> Decision:
    if unsafe.detected:
        return Decision(unsafe.decision_hint)

    if dom.domain == Domain.high_risk:
        return Decision.recommend_professional_help

    if dom.domain == Domain.unknown:
        # Legal-but-vague → clarify; genuinely non-legal → out of scope.
        return (Decision.ask_clarifying_questions if dom.legal_signal
                else Decision.unsupported)

    if dom.matched_group and dom.matched_group.expected_decision:
        return Decision(dom.matched_group.expected_decision)

    return Decision.ask_clarifying_questions
