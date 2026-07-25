from __future__ import annotations

import unicodedata

import pytest

from backend_lite.app.contracts.demo_llm import DemoScenario
from backend_lite.app.contracts.legal_facts import FactOpKind, MoneyAmount, UnboundFactOperation, validate_text_anchor
from backend_lite.app.services.demo_deposit_extractor import (
    SUPPORTED_SLOTS,
    classify_demo_scenario,
    create_validated_text_anchor,
    extract_scenario_facts,
    normalize_for_eligibility,
)


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _classify(text: str) -> DemoScenario:
    return classify_demo_scenario(_nfc(text))


def _extract(text: str):
    nfc = _nfc(text)
    scenario = classify_demo_scenario(nfc)
    result = extract_scenario_facts(nfc, scenario, "m")
    for op in result.operations:
        assert validate_text_anchor(op.anchor, nfc) is op.anchor
    return result


def _slot_ops(result) -> dict[str, UnboundFactOperation]:
    return {op.slot_hint: op for op in result.operations}


# --- normalization (§4) -----------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected_substr",
    [
        ("mã-tấu", "ma tau"),
        ("trả_thù", "tra thu"),
        ("công-an", "cong an"),
        ("triệu_tập", "trieu tap"),
        ("example[.]com", "example com"),
        ("Đ i ề u", "d i e u"),
    ],
)
def test_normalization(raw: str, expected_substr: str):
    assert expected_substr in normalize_for_eligibility(raw)


# --- scenario classification (§6) -------------------------------------------

def test_fact_update_scenario():
    assert _classify("Tôi đã đặt cọc 20 triệu. Tôi không có giấy đặt cọc nhưng có sao kê chuyển khoản.") is DemoScenario.DEPOSIT_FACT_UPDATE


def test_legal_guidance_scenario():
    assert _classify(
        "Tôi đã đặt cọc 20 triệu, không có giấy đặt cọc, có sao kê chuyển khoản, "
        "chưa được bàn giao nhà và chủ nhà chưa trả lại tiền cọc. Tôi nên làm gì?"
    ) is DemoScenario.DEPOSIT_LEGAL_GUIDANCE


def test_draft_scenario():
    assert _classify("Tôi đã đặt cọc 20 triệu nhưng chủ nhà chưa trả lại tiền cọc. Viết giúp tôi tin nhắn yêu cầu hoàn trả tiền cọc.") is DemoScenario.DEPOSIT_DRAFT_REQUEST


@pytest.mark.parametrize(
    "text",
    [
        "Tôi đọc bài có chữ đặt cọc nhưng đang hỏi khoản vay.",
        "Người khác đã đặt cọc, còn tôi hỏi khoản vay.",
        "Tôi chưa đặt cọc, tôi chỉ hỏi hợp đồng thuê nhà.",
        "Deposit nghĩa là gì?",
        "Tôi dự định đặt cọc 20 triệu.",
        "Tôi sẽ đặt cọc 20 triệu.",
        "Tôi phải đặt cọc 20 triệu.",
        "Vợ tôi đã đặt cọc 20 triệu.",
        "Luật sư nói tôi đã đặt cọc.",
        "Tôi đoán là mình đã ký giấy đặt cọc.",
        "Tôi thuê nhà, tôi nên làm gì?",
        "Chủ nhà cho tôi vay 20 triệu, tôi nên làm gì?",
    ],
)
def test_false_context_is_unsupported(text: str):
    assert _classify(text) is DemoScenario.UNSUPPORTED


@pytest.mark.parametrize(
    "text",
    [
        "Tôi dự định đặt cọc 20 triệu.",
        "Tôi sẽ đặt cọc 20 triệu.",
        "Vợ tôi đã đặt cọc 20 triệu.",
        "Tôi đoán là mình đã ký giấy đặt cọc.",
        "Người khác đã đặt cọc 20 triệu.",
    ],
)
def test_unsupported_yields_no_operations(text: str):
    nfc = _nfc(text)
    scenario = classify_demo_scenario(nfc)
    assert extract_scenario_facts(nfc, scenario, "m").operations == []


# --- V4: complete-message allowlist (owner decision) ------------------------
# A valid paid-deposit prefix followed by ANY unrelated residual clause must be
# UNSUPPORTED. Prefix-only / search-based classification is prohibited.

_RESIDUAL_REPRODUCERS: tuple[str, ...] = (
    "Tôi đã đặt cọc 20 triệu. Tôi bị sa thải. Tôi nên làm gì?",
    "Tôi đã đặt cọc 20 triệu. Tôi muốn ly hôn. Tôi nên làm gì?",
    "Tôi đã đặt cọc 20 triệu. Tôi đang hỏi khoản vay. Tôi nên làm gì?",
    "Tôi đã đặt cọc 20 triệu. Viết giúp tôi đơn ly hôn.",
    "Tôi đã đặt cọc 20 triệu. Tôi bị phạt giao thông. Tôi nên làm gì?",
    "Tôi đã đặt cọc 20 triệu. Tôi đang hỏi khoản vay.",
)


@pytest.mark.parametrize("text", _RESIDUAL_REPRODUCERS)
def test_residual_reproducers_are_unsupported(text: str):
    assert _classify(text) is DemoScenario.UNSUPPORTED


@pytest.mark.parametrize("text", _RESIDUAL_REPRODUCERS)
def test_residual_reproducers_emit_zero_operations(text: str):
    result = _extract(text)
    assert result.operations == []


def _punctuation_variants(base: str) -> list[str]:
    # base uses ". " as the clause separator between the paid prefix and residual.
    return [
        base.replace(". ", ".\n"),
        base.replace(". ", "; "),
        base.replace(". ", ": "),
        base.replace(". ", ", "),
        base.replace(". ", " - "),
        base.replace(" ", "   "),
        base.upper(),
    ]


@pytest.mark.parametrize(
    "text",
    _punctuation_variants("Tôi đã đặt cọc 20 triệu. Tôi bị sa thải. Tôi nên làm gì?"),
)
def test_residual_punctuation_and_case_variants_unsupported(text: str):
    assert _classify(text) is DemoScenario.UNSUPPORTED


def test_residual_unaccented_variant_unsupported():
    assert _classify("Toi da dat coc 20 trieu. Toi bi sa thai. Toi nen lam gi?") is DemoScenario.UNSUPPORTED


@pytest.mark.parametrize(
    "text",
    [
        "Tôi đã đặt cọc 20 triệu nhé.",  # extra word at end
        "Chào bạn, tôi đã đặt cọc 20 triệu.",  # extra clause at beginning
        (
            "Tôi đã đặt cọc 20 triệu, không có giấy đặt cọc, có sao kê chuyển khoản, "
            "tôi bị sa thải, chưa được bàn giao nhà và chủ nhà chưa trả lại tiền cọc. "
            "Tôi nên làm gì?"
        ),  # extra clause in the middle of the guidance template
    ],
)
def test_near_miss_scripts_are_rejected(text: str):
    assert _classify(text) is DemoScenario.UNSUPPORTED


def test_approved_scripts_remain_accepted_after_v4():
    assert _classify("Tôi đã đặt cọc 20 triệu.") is DemoScenario.DEPOSIT_FACT_UPDATE
    assert _classify(
        "Tôi đã đặt cọc 20 triệu. Tôi không có giấy đặt cọc nhưng có sao kê chuyển khoản."
    ) is DemoScenario.DEPOSIT_FACT_UPDATE
    assert _classify("Tôi đã đưa 20 triệu tiền cọc.") is DemoScenario.DEPOSIT_FACT_UPDATE
    assert _classify(
        "Tôi đã đưa 10 triệu tiền cọc, còn hợp đồng ghi 20 triệu."
    ) is DemoScenario.DEPOSIT_FACT_UPDATE
    assert _classify(
        "Tôi đã đặt cọc 20 triệu, không có giấy đặt cọc, có sao kê chuyển khoản, "
        "chưa được bàn giao nhà và chủ nhà chưa trả lại tiền cọc. Tôi nên làm gì?"
    ) is DemoScenario.DEPOSIT_LEGAL_GUIDANCE
    assert _classify(
        "Tôi đã đặt cọc 20 triệu nhưng chủ nhà chưa trả lại tiền cọc. "
        "Viết giúp tôi tin nhắn yêu cầu hoàn trả tiền cọc."
    ) is DemoScenario.DEPOSIT_DRAFT_REQUEST


def test_valid_prefix_plus_invalid_residual_is_not_a_fact_update():
    """Direct proof required by V4 §8: a valid paid prefix followed by an
    unrelated residual clause must NOT be treated as DEPOSIT_FACT_UPDATE."""

    text = "Tôi đã đặt cọc 20 triệu. Tôi bị sa thải. Tôi nên làm gì?"
    scenario = _classify(text)
    assert scenario is DemoScenario.UNSUPPORTED
    assert scenario is not DemoScenario.DEPOSIT_FACT_UPDATE
    result = _extract(text)
    assert result.operations == []  # the valid "20 triệu" prefix is NOT partially extracted


def test_paid_amount_10m_not_replaced_by_trailing_contract_20m():
    amount = _slot_ops(_extract("Tôi đã đưa 10 triệu tiền cọc, còn hợp đồng ghi 20 triệu."))["deposit_amount"]
    assert amount.value.amount_vnd == 10_000_000


# --- bounded extraction (§8) ------------------------------------------------

def test_paid_amount_captured():
    amount = _slot_ops(_extract("Tôi đã đặt cọc 20 triệu."))["deposit_amount"]
    assert amount.op is FactOpKind.SET_VALUE
    assert isinstance(amount.value, MoneyAmount)
    assert amount.value.amount_vnd == 20_000_000


def test_paid_amount_dua_form():
    amount = _slot_ops(_extract("Tôi đã đưa 10 triệu tiền cọc, còn hợp đồng ghi 20 triệu."))["deposit_amount"]
    assert amount.value.amount_vnd == 10_000_000  # actual paid, not the contract figure


def test_fact_clauses_captured():
    by_slot = _slot_ops(_extract(
        "Tôi đã đặt cọc 20 triệu, không có giấy đặt cọc, có sao kê chuyển khoản, "
        "chưa được bàn giao nhà và chủ nhà chưa trả lại tiền cọc. Tôi nên làm gì?"
    ))
    assert by_slot["written_agreement_exists"].op is FactOpKind.NEGATE
    assert by_slot["payment_evidence_exists"].op is FactOpKind.AFFIRM
    assert by_slot["property_handed_over"].op is FactOpKind.NEGATE
    assert by_slot["deposit_returned"].op is FactOpKind.NEGATE


def test_only_supported_slots_and_no_episode_id():
    result = _extract("Tôi đã đặt cọc 20 triệu, không có giấy đặt cọc.")
    assert "episode_id" not in UnboundFactOperation.model_fields
    for op in result.operations:
        assert op.slot_hint in SUPPORTED_SLOTS
        assert op.issue_type_hint == "rental_deposit"


def test_extract_only_after_scenario_approval():
    nfc = _nfc("Deposit nghĩa là gì?")
    assert extract_scenario_facts(nfc, DemoScenario.UNSUPPORTED, "m").operations == []


@pytest.mark.parametrize(
    "text",
    ["Tôi   đã   đặt   cọc   20   triệu.", "Tôi đã đặt cọc 20 triệu!!!", "TÔI ĐÃ ĐẶT CỌC 20 TRIỆU."],
)
def test_span_correctness(text: str):
    nfc = _nfc(text)
    scenario = classify_demo_scenario(nfc)
    result = extract_scenario_facts(nfc, scenario, "m")
    assert result.operations
    for op in result.operations:
        assert op.anchor.quote == nfc[op.anchor.start : op.anchor.end]


def test_nfd_input_normalized_preserves_anchor():
    nfd = unicodedata.normalize("NFD", "Tôi đã đặt cọc 20 triệu.")
    nfc = unicodedata.normalize("NFC", nfd)
    scenario = classify_demo_scenario(nfc)
    result = extract_scenario_facts(nfc, scenario, "m")
    assert result.operations
    for op in result.operations:
        validate_text_anchor(op.anchor, nfc)


def test_extractor_rejects_non_nfc():
    nfd = unicodedata.normalize("NFD", "Tôi đã đặt cọc 20 triệu.")
    with pytest.raises(ValueError):
        extract_scenario_facts(nfd, DemoScenario.DEPOSIT_FACT_UPDATE, "m")


def test_factory_rejects_mismatched_quote():
    nfc = _nfc("Tôi đã đặt cọc")
    with pytest.raises(ValueError):
        create_validated_text_anchor(nfc, 0, len(nfc) + 5, "m")
