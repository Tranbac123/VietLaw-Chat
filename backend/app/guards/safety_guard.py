"""Safety guard. Final layer before build.

Escalate-only: may raise risk/decision/domain to stricter values, never lower.
Scans generated content for forbidden phrases in *enabling* context (negated/refusal
phrasing is exempt — that exemption applies here on OUTPUT, never on input detection).
On a violation the content is replaced with a safe template so nothing tactical or
guarantee-like can reach the user.
"""
from dataclasses import dataclass, field

from app.llm import content_templates as ct
from app.nlp.input_normalizer import strip_accents
from app.nlp.patterns import PatternBank
from app.schemas import Decision, Domain, LLMContent, RiskLevel

# Illegal/tactical forbidden phrases → refuse. Everything else forbidden → over-claim.
_TACTICAL = frozenset(strip_accents(p) for p in (
    "giấu chứng cứ", "xóa chứng cứ", "làm giả giấy tờ", "né phạt", "lách luật",
    "đối phó công an", "mẹo né phạt", "cách né phạt", "cách giấu chứng cứ",
    "hãy xóa chứng cứ", "cách xóa chứng cứ", "cách làm giả giấy tờ", "mẹo lách luật",
    "cách lách luật", "mẹo lách giấy phép", "cách đối phó công an", "khai gian", "nói dối",
))

_RISK_ORDER = {RiskLevel.low: 0, RiskLevel.medium: 1, RiskLevel.high: 2}


@dataclass
class SafetyGuardResult:
    content: LLMContent
    domain: Domain
    risk_level: RiskLevel
    decision: Decision
    safety_flags: list[str] = field(default_factory=list)
    guard_triggered: bool = False


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _RISK_ORDER[a] >= _RISK_ORDER[b] else b


def _is_negated(text_ai: str, idx: int, rules: dict) -> bool:
    strong_w = rules.get("strong_negation_window_chars", 40)
    weak_w = rules.get("weak_negation_window_chars", 12)
    strong = [strip_accents(c) for c in rules.get("strong_negation_cues", [])]
    weak = [strip_accents(c) for c in rules.get("weak_negation_cues", [])]
    before_strong = text_ai[max(0, idx - strong_w):idx]
    before_weak = text_ai[max(0, idx - weak_w):idx]
    return any(c in before_strong for c in strong) or any(c in before_weak for c in weak)


def _scan(content: LLMContent, bank: PatternBank) -> tuple[bool, bool]:
    text_ai = strip_accents(" ".join(
        [content.summary, *content.clarifying_questions, *content.checklist, *content.next_steps]
    ).lower())
    tactical = overclaim = False
    for raw_phrase in bank.forbidden_output_phrases:
        phrase = strip_accents(raw_phrase.lower())
        start = 0
        while True:
            idx = text_ai.find(phrase, start)
            if idx == -1:
                break
            if not _is_negated(text_ai, idx, bank.matching_rules):
                if phrase in _TACTICAL:
                    tactical = True
                else:
                    overclaim = True
            start = idx + len(phrase)
    return tactical, overclaim


def apply(content: LLMContent, domain: Domain, risk_level: RiskLevel,
          decision: Decision, bank: PatternBank) -> SafetyGuardResult:
    tactical, overclaim = _scan(content, bank)

    if tactical:
        return SafetyGuardResult(
            content=ct.refusal_content(None, bank),
            domain=Domain.high_risk,
            risk_level=RiskLevel.high,
            decision=Decision.refuse_unsafe_request,
            safety_flags=["unsafe_output"],
            guard_triggered=True,
        )

    if overclaim:
        return SafetyGuardResult(
            content=ct.escalation_content(domain if domain != Domain.unknown else Domain.high_risk, bank),
            domain=domain if domain == Domain.high_risk else domain,
            risk_level=_max_risk(risk_level, RiskLevel.medium),
            decision=(decision if decision in (Decision.refuse_unsafe_request,
                                               Decision.recommend_professional_help)
                      else Decision.recommend_professional_help),
            safety_flags=["overclaim_scrubbed"],
            guard_triggered=True,
        )

    return SafetyGuardResult(
        content=content, domain=domain, risk_level=risk_level,
        decision=decision, safety_flags=[], guard_triggered=False,
    )
