"""Unsafe intent detection.

Matches raw unsafe patterns against the accent-insensitive question. HARD RULE:
no negation exemption on input — a "không" near an unsafe
phrase must not suppress detection. Runs per-turn, independent of chat history.
"""
from dataclasses import dataclass, field

from app.nlp.keywords import match_domain
from app.nlp.patterns import PatternBank


@dataclass
class UnsafeResult:
    detected: bool = False
    categories: list[str] = field(default_factory=list)
    safety_flags: list[str] = field(default_factory=list)
    decision_hint: str = "refuse_unsafe_request"
    safe_hint: str = ""
    detected_topic: str | None = None


def detect(ai_text: str, bank: PatternBank) -> UnsafeResult:
    matched = [g for g in bank.unsafe if g.match(ai_text)]
    if not matched:
        return UnsafeResult()

    categories = [g.category for g in matched]
    topic = match_domain(ai_text)

    # Any refuse-worthy category dominates; police-tactical-only stays as escalation.
    decisions = {g.expected_decision for g in matched}
    decision_hint = (
        "refuse_unsafe_request"
        if "refuse_unsafe_request" in decisions
        else "recommend_professional_help"
    )

    flags = list(dict.fromkeys(categories))  # dedup, keep order
    if topic:
        flags.append(f"{topic_short(topic)}_evasion")

    return UnsafeResult(
        detected=True,
        categories=categories,
        safety_flags=flags,
        decision_hint=decision_hint,
        safe_hint=matched[0].safe_response_hint or "",
        detected_topic=topic_short(topic) if topic else None,
    )


def topic_short(domain: str | None) -> str | None:
    # metadata.detected_topic uses the short topic name (e.g. "traffic").
    return {"civil_dispute": "civil", "household_business": "household"}.get(domain, domain)
