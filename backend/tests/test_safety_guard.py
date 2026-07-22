"""Safety guard. Escalate-only."""
from pathlib import Path

import pytest

from app.nlp.patterns import PatternBank
from app.guards.safety_guard import apply
from app.schemas import Decision, Domain, LLMContent, RiskLevel

_DATA = Path(__file__).resolve().parents[2] / "data" / "unsafe_patterns.json"


@pytest.fixture(scope="module")
def bank():
    return PatternBank.load(str(_DATA))


def _c(summary, next_steps=None):
    return LLMContent(summary=summary, clarifying_questions=[], checklist=[],
                      next_steps=next_steps or [], used_source_ids=[])


def test_clean_content_not_triggered(bank):
    r = apply(_c("Bạn nên chuẩn bị hợp đồng và chứng từ."), Domain.civil_dispute,
              RiskLevel.medium, Decision.ask_clarifying_questions, bank)
    assert r.guard_triggered is False
    assert r.decision == Decision.ask_clarifying_questions
    assert r.risk_level == RiskLevel.medium


def test_refusal_context_is_safe(bank):
    # negated/refusal phrasing must NOT trigger the guard.
    r = apply(_c("Tôi không thể hướng dẫn cách né phạt giao thông."),
              Domain.traffic, RiskLevel.medium, Decision.ask_clarifying_questions, bank)
    assert r.guard_triggered is False


def test_tactical_output_escalates_to_refusal(bank):
    r = apply(_c("Bạn cứ né phạt bằng cách nói không thấy biển báo."),
              Domain.traffic, RiskLevel.medium, Decision.ask_clarifying_questions, bank)
    assert r.guard_triggered is True
    assert r.decision == Decision.refuse_unsafe_request
    assert r.risk_level == RiskLevel.high
    assert r.domain == Domain.high_risk


def test_guarantee_language_is_scrubbed(bank):
    r = apply(_c("Bạn chắc chắn thắng kiện này."), Domain.civil_dispute,
              RiskLevel.medium, Decision.ask_clarifying_questions, bank)
    assert r.guard_triggered is True
    assert "chắc chắn thắng" not in r.content.summary.lower()


def test_never_downgrades_risk_or_decision(bank):
    # Clean content but caller already at high/refuse — guard must not lower it.
    r = apply(_c("Bạn nên liên hệ luật sư."), Domain.high_risk,
              RiskLevel.high, Decision.refuse_unsafe_request, bank)
    assert r.risk_level == RiskLevel.high
    assert r.decision == Decision.refuse_unsafe_request
    assert r.domain == Domain.high_risk
