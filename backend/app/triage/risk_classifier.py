"""Risk classification.

Pattern-driven (golden-aligned): the matched group's expected_risk is authoritative.
Unsafe intent and high_risk domain always force high. Additive scoring is not
used as primary because it disagrees with the frozen data on traffic fines (data
says medium, scoring would say low); data + golden win.
"""
from dataclasses import dataclass

from app.nlp.input_normalizer import NormalizedText
from app.triage.legal_triage import DomainResult
from app.nlp.patterns import PatternBank
from app.schemas import Domain, RiskLevel
from app.triage.unsafe_intent_detector import UnsafeResult

_FALLBACK_RISK = {
    Domain.civil_dispute: RiskLevel.medium,
    Domain.traffic: RiskLevel.medium,
    Domain.household_business: RiskLevel.low,
    Domain.administrative: RiskLevel.low,
    Domain.unknown: RiskLevel.low,
}


@dataclass
class RiskResult:
    risk: RiskLevel
    confidence: float = 0.7


def classify(norm: NormalizedText, dom: DomainResult, unsafe: UnsafeResult,
             bank: PatternBank) -> RiskResult:
    if unsafe.detected or dom.domain == Domain.high_risk:
        return RiskResult(RiskLevel.high, confidence=0.9)

    if dom.matched_group and dom.matched_group.expected_risk:
        return RiskResult(RiskLevel(dom.matched_group.expected_risk), confidence=0.8)

    # Vague-but-legal unknown gets medium (something legal is at stake, facts missing).
    if dom.domain == Domain.unknown and dom.legal_signal:
        return RiskResult(RiskLevel.medium, confidence=0.4)

    return RiskResult(_FALLBACK_RISK.get(dom.domain, RiskLevel.low), confidence=0.6)
