"""FAST DEMO V2 fact-intake behaviour and contextual fallback classes.

The live defect was that every legal turn produced one generic fallback that
ignored what the user actually said. These tests pin the intent classifier and
the four bounded fallback classes it selects.
"""

from __future__ import annotations

import pytest

from backend_lite.app.contracts.fast_demo import DepositAmount, FastDemoState
from backend_lite.app.services.fast_demo_orchestrator import (
    _acknowledgement_sentence,
    _fallback_content,
)
from backend_lite.app.services.fast_demo_routing import LegalIntent, classify_legal_intent

_INTERNAL_TERMS = [
    "demo", "provider", "fallback", "route", "schema", "json",
    "structured output", "response mode", "phản hồi dự phòng", "state",
]


def _state_with_facts() -> FastDemoState:
    state = FastDemoState()
    state.facts.deposit_amount = DepositAmount(value=20_000_000)
    state.facts.payment_evidence_status = "present"
    state.facts.payment_evidence_types = ["bank_transfer"]
    return state


# -- 1: intent classification ----------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "Tôi đã đặt cọc thuê nhà 20 triệu và có sao kê chuyển khoản.",
        "Tôi đã đặt cọc 20 triệu cho chủ nhà.",
        "Tôi có sao kê chuyển khoản và giấy đặt cọc.",
    ],
)
def test_fact_only_message_is_intake(text: str) -> None:
    assert classify_legal_intent(text) is LegalIntent.FACT_INTAKE


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("tôi đẽ đặt cọc nhưng chủ không cho vào ở, tôi nên làm gì tiếp theo?", LegalIntent.NEXT_STEPS),
        ("Tôi nên làm gì tiếp?", LegalIntent.NEXT_STEPS),
        ("Vậy tôi cần chuẩn bị những bằng chứng gì?", LegalIntent.EVIDENCE),
        ("Viết giúp tôi tin nhắn yêu cầu hoàn trả.", LegalIntent.DRAFT),
        ("Cập nhật lại tin nhắn giúp tôi.", LegalIntent.DRAFT),
    ],
)
def test_intent_classification(text: str, expected: LegalIntent) -> None:
    assert classify_legal_intent(text) is expected


# -- 2-7: the intake fallback ----------------------------------------------

def test_intake_fallback_acknowledges_amount_and_evidence() -> None:
    summary, questions, steps = _fallback_content(
        LegalIntent.FACT_INTAKE, _state_with_facts(), []
    )
    assert "20.000.000" in summary
    assert "sao kê" in summary.lower() or "chuyển khoản" in summary.lower()
    # It asks what the user wants rather than assuming.
    assert questions
    assert any("hỗ trợ" in q or "phản hồi" in q for q in questions)


def test_intake_fallback_does_not_assume_a_refund_dispute() -> None:
    summary, questions, steps = _fallback_content(
        LegalIntent.FACT_INTAKE, _state_with_facts(), []
    )
    blob = " ".join([summary, *questions, *steps]).lower()
    # It must not assert the landlord refused, nor instruct a refund demand.
    assert "chủ nhà đã từ chối" not in blob
    assert "gửi yêu cầu hoàn trả" not in blob
    assert "yêu cầu hoàn cọc bằng văn bản" not in blob
    # And it proposes no next steps at all on an intake turn.
    assert steps == []


def test_intake_fallback_has_no_internal_language() -> None:
    summary, questions, steps = _fallback_content(
        LegalIntent.FACT_INTAKE, _state_with_facts(), []
    )
    blob = " ".join([summary, *questions, *steps]).lower()
    leaked = [t for t in _INTERNAL_TERMS if t in blob]
    assert leaked == [], leaked


def test_intake_fallback_uses_accepted_state_not_the_raw_message() -> None:
    # With no accepted facts it must not invent an amount.
    summary, _, _ = _fallback_content(LegalIntent.FACT_INTAKE, FastDemoState(), [])
    assert "20.000.000" not in summary


# -- 9-12: the no-handover fallback ----------------------------------------

def test_no_handover_fallback_differs_from_intake() -> None:
    intake, _, _ = _fallback_content(LegalIntent.FACT_INTAKE, _state_with_facts(), [])
    steps_summary, _, steps = _fallback_content(
        LegalIntent.NEXT_STEPS, _state_with_facts(), []
    )
    assert steps_summary != intake
    assert steps  # intake has none, this one does


def test_no_handover_fallback_gives_context_specific_steps() -> None:
    _, _, steps = _fallback_content(LegalIntent.NEXT_STEPS, _state_with_facts(), [])
    blob = " ".join(steps).lower()
    assert "giữ lại" in blob or "sao kê" in blob      # preserve evidence
    assert "văn bản" in blob                            # written request
    assert "bàn giao" in blob                           # handover
    assert "thỏa thuận" in blob                         # check the agreement


def test_no_handover_fallback_asks_about_agreement_or_movein_date() -> None:
    _, questions, _ = _fallback_content(LegalIntent.NEXT_STEPS, _state_with_facts(), [])
    blob = " ".join(questions).lower()
    assert "văn bản" in blob or "giấy đặt cọc" in blob
    assert "bàn giao" in blob or "nhận nhà" in blob


def test_no_handover_fallback_makes_no_guaranteed_legal_claim() -> None:
    summary, questions, steps = _fallback_content(
        LegalIntent.NEXT_STEPS, _state_with_facts(), []
    )
    blob = " ".join([summary, *questions, *steps]).lower()
    for claim in [
        "chắc chắn vi phạm",
        "chắc chắn thắng",
        "chắc chắn được",
        "phạt cọc gấp đôi",
        "bồi thường gấp đôi",
        "toà án có thẩm quyền",
        "trong vòng 30 ngày",
    ]:
        assert claim not in blob, claim


# -- draft + general classes ------------------------------------------------

def test_draft_fallback_retains_facts_and_invites_retry() -> None:
    summary, _, _ = _fallback_content(LegalIntent.DRAFT, _state_with_facts(), [])
    assert "20.000.000" in summary
    assert "nhắn lại" in summary.lower()
    assert "phản hồi dự phòng" not in summary.lower()


@pytest.mark.parametrize(
    "intent",
    [LegalIntent.FACT_INTAKE, LegalIntent.NEXT_STEPS, LegalIntent.EVIDENCE,
     LegalIntent.DRAFT, LegalIntent.GENERAL],
)
def test_no_fallback_class_leaks_internal_language(intent: LegalIntent) -> None:
    summary, questions, steps = _fallback_content(intent, _state_with_facts(), [])
    blob = " ".join([summary, *questions, *steps]).lower()
    leaked = [t for t in _INTERNAL_TERMS if t in blob]
    assert leaked == [], f"{intent}: {leaked}"


# -- 13/14: accepted state is authoritative in the acknowledgement ----------

def test_acknowledgement_uses_corrected_amount() -> None:
    state = _state_with_facts()
    state.facts.deposit_amount = DepositAmount(value=15_000_000)
    sentence = _acknowledgement_sentence(state)
    assert "15.000.000" in sentence
    assert "20.000.000" not in sentence


def test_acknowledgement_retains_transfer_evidence() -> None:
    assert "chứng từ" in _acknowledgement_sentence(_state_with_facts()).lower()


def test_acknowledgement_is_empty_without_accepted_facts() -> None:
    assert _acknowledgement_sentence(FastDemoState()) == ""
