"""Regression coverage for ``chẳng`` negation versus ``chăng/chang`` ambiguity.

These tests deliberately exercise the public inference and fact-update paths.
They ensure original Vietnamese provenance is checked before accent-stripped
patterns can interpret the ambiguous spelling as the ``chang`` negator.
"""

from __future__ import annotations

import unicodedata

import pytest

from backend_lite.app.contracts.fast_demo import FactUpdateProposal, FastDemoState
from backend_lite.app.services.fast_demo_fact_validation import (
    _NEGATIVE_RE,
    _NEGATOR_RE,
    apply_fact_updates,
    infer_polarity,
    infer_response_status,
    is_reserved_sentinel,
)


def _outcome(message: str, slot: str, quote: str):
    return apply_fact_updates(
        FastDemoState(),
        [FactUpdateProposal(operation="set", slot=slot, evidence_quote=quote)],
        message,
    )


@pytest.mark.parametrize(
    ("message", "slot", "expected"),
    [
        ("Tôi chẳng ký giấy đặt cọc.", "written_deposit_agreement_status", "absent"),
        ("Tôi chẳng có sao kê.", "payment_evidence_status", "absent"),
        ("Tôi không có sao kê.", "payment_evidence_status", "absent"),
        ("Tôi có sao kê chuyển khoản.", "payment_evidence_status", "present"),
    ],
)
def test_legitimate_negators_keep_generic_fact_semantics(message: str, slot: str, expected: str) -> None:
    outcome = _outcome(message, slot, message.rstrip("."))
    assert getattr(outcome.state.facts, slot) == expected


@pytest.mark.parametrize(
    ("message", "slot", "expected"),
    [
        ("Tôi chưa ký giấy đặt cọc.", "written_deposit_agreement_status", "absent"),
        ("Tôi đã ký giấy đặt cọc.", "written_deposit_agreement_status", "present"),
    ],
)
def test_existing_generic_polarity_is_unchanged(message: str, slot: str, expected: str) -> None:
    outcome = _outcome(message, slot, message.rstrip("."))
    assert getattr(outcome.state.facts, slot) == expected


@pytest.mark.parametrize(
    "message",
    [
        "Liệu chăng có sao kê chuyển khoản?",
        "Phải chăng đã ký hợp đồng?",
        "lieu chang co sao ke",
        "phai chang da ky hop dong",
        "Tôi chán ký giấy tờ.",
    ],
)
def test_ambiguous_or_unrelated_chang_text_never_updates_generic_fact(message: str) -> None:
    outcome = _outcome(message, "payment_evidence_status", message.rstrip(".?"))
    assert outcome.state.facts.payment_evidence_status == "unknown"
    assert outcome.rejected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("chủ nhà chẳng phản hồi", "absent"),
        ("chủ nhà chẳng có phản hồi", "absent"),
        ("chủ nhà không phản hồi", "absent"),
        ("chủ nhà đã phản hồi", "present"),
        ("Liệu chăng có phản hồi?", None),
        ("Liệu chăng chủ nhà có phản hồi?", None),
        ("chang co phan hoi", None),
    ],
)
def test_response_status_preserves_chang_provenance_boundary(text: str, expected: str | None) -> None:
    assert infer_response_status(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "chủ nhà không nói rõ lý do",
        "chủ nhà chưa nói rõ lý do",
        "không nêu lý do",
        "lý do không rõ",
        "tôi chưa nhận lại tiền cọc",
        "chủ nhà nhận tiền cọc",
        "chủ nhà nhận nhà",
        "chưa được hoàn cọc",
        "chủ nhà đã phản hồi nhưng chưa hồi âm",
    ],
)
def test_response_status_ambiguous_reason_money_and_conflicts_do_not_update(text: str) -> None:
    assert infer_response_status(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("chưa có phản hồi", "absent"),
        ("không có phản hồi", "absent"),
        ("không trả lời", "absent"),
        ("chưa hồi âm", "absent"),
        ("chủ nhà im lặng", "absent"),
        ("chủ nhà có phản hồi", "present"),
        ("chủ nhà nói sẽ trả cọc", "present"),
        ("chủ nhà có phản hồi nhưng không nêu lý do", "present"),
    ],
)
def test_response_status_semantic_matrix_remains_unchanged(text: str, expected: str) -> None:
    assert infer_response_status(text) == expected


@pytest.mark.parametrize("word", ["chăng", "Chăng", "CHĂNG"])
def test_accented_chang_variants_block_before_generic_or_response_patterns(word: str) -> None:
    assert infer_polarity(f"{word} có sao kê", f"{word} có sao kê") is None
    assert infer_response_status(f"{word} có phản hồi") is None


@pytest.mark.parametrize("word", ["chẳng", "Chẳng", "CHẲNG"])
def test_accented_chang_negator_variants_remain_negators(word: str) -> None:
    assert infer_polarity(f"{word} có sao kê", f"{word} có sao kê") == "absent"
    assert infer_response_status(f"{word} có phản hồi") == "absent"


def test_nfd_is_conservative_and_never_creates_a_false_fact() -> None:
    assert infer_polarity(unicodedata.normalize("NFD", "chẳng có sao kê"), unicodedata.normalize("NFD", "chẳng có sao kê")) == "absent"
    ambiguous = unicodedata.normalize("NFD", "chăng có sao kê")
    assert infer_polarity(ambiguous, ambiguous) is None
    assert infer_response_status(unicodedata.normalize("NFD", "chăng có phản hồi")) is None


def test_generic_window_checks_original_provenance_before_normalized_patterns() -> None:
    assert infer_polarity("sao kê", "Phải chăng đã có sao kê?") is None
    assert infer_polarity("sao kê", "không có sao kê") == "absent"
    assert infer_polarity("sao kê", "có sao kê chuyển khoản") == "present"


def test_remote_ambiguous_chang_does_not_cancel_independent_local_fact() -> None:
    message = "Chăng là chuyện khác. Tôi có sao kê chuyển khoản."
    assert infer_polarity("sao kê", message) == "present"


@pytest.mark.parametrize("verb", ["ký", "có", "nhận", "trả", "hoàn", "được", "giao", "làm", "gửi", "phản hồi", "nói"])
def test_chan_is_not_a_negator_or_a_negative_pattern(verb: str) -> None:
    normalized = f"chan {verb}"
    assert _NEGATOR_RE.search(normalized) is None
    assert _NEGATIVE_RE.search(normalized) is None


@pytest.mark.parametrize("value", ["not_stated", "NOT STATED", "not-stated", "n/a"])
def test_reserved_sentinels_remain_protected(value: str) -> None:
    assert is_reserved_sentinel(value)


@pytest.mark.parametrize("value", ["chủ nhà không nói rõ lý do", "none of the deposit was returned"])
def test_real_refusal_reasons_are_not_sentinels(value: str) -> None:
    assert not is_reserved_sentinel(value)


@pytest.mark.parametrize("operation", ["affirm", "negate"])
def test_model_operation_cannot_override_ambiguous_response_evidence(operation: str) -> None:
    message = "Chủ nhà không nói rõ lý do."
    outcome = apply_fact_updates(
        FastDemoState(),
        [FactUpdateProposal(operation=operation, slot="landlord_response_status", evidence_quote="không nói rõ lý do")],
        message,
    )
    assert outcome.state.facts.landlord_response_status == "unknown"
    assert outcome.rejected
