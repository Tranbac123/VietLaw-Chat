"""Legal domain classification.

Priority: unsafe intent forces high_risk; then high_risk patterns; then
medium/low pattern groups; then keyword fallback; else unknown. Unsafe/serious
signals always beat the topical domain.
"""
from dataclasses import dataclass
from typing import Optional

from app.nlp.input_normalizer import NormalizedText
from app.nlp.keywords import has_legal_signal, match_domain
from app.nlp.patterns import PatternBank, PatternGroup
from app.schemas import Domain
from app.triage.unsafe_intent_detector import UnsafeResult, topic_short


@dataclass
class DomainResult:
    domain: Domain
    detected_topic: Optional[str] = None
    matched_group: Optional[PatternGroup] = None
    confidence: float = 0.6
    legal_signal: bool = False


def _first_match(groups, ai_text) -> Optional[PatternGroup]:
    for g in groups:
        if g.match(ai_text):
            return g
    return None


def classify(norm: NormalizedText, unsafe: UnsafeResult, bank: PatternBank) -> DomainResult:
    ai = norm.accent_insensitive

    if unsafe.detected:
        return DomainResult(Domain.high_risk, detected_topic=unsafe.detected_topic,
                            confidence=0.9)

    hi = _first_match(bank.high_risk, ai)
    if hi:
        topic = match_domain(ai)
        return DomainResult(Domain.high_risk, detected_topic=topic_short(topic),
                            matched_group=hi, confidence=0.9)

    grp = _first_match(bank.medium, ai) or _first_match(bank.low, ai)
    if grp:
        return DomainResult(Domain(grp.expected_domain), matched_group=grp, confidence=0.85)

    fallback = match_domain(ai)
    if fallback:
        return DomainResult(Domain(fallback), confidence=0.6)

    return DomainResult(Domain.unknown, confidence=0.3,
                        legal_signal=has_legal_signal(ai))
