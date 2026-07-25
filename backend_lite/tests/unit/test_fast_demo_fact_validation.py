"""FAST DEMO V2 fact-update validation.

Covers required cases 10, 14-19 of the 48-hour contract: tri-state semantics,
evidence-span verification, ambiguity rejection, and numeric parsing from the
verified span rather than from whatever number the model asserted.
"""

from __future__ import annotations

from backend_lite.app.contracts.fast_demo import (
    DepositAmount,
    FactUpdateProposal,
    FastDemoState,
)
from backend_lite.app.services.fast_demo_fact_validation import (
    apply_fact_updates,
    locate_quote,
    normalize_with_map,
    parse_amount_from_text,
)


def prop(**kwargs) -> FactUpdateProposal:
    return FactUpdateProposal(**kwargs)


# -- 16: normalized evidence-quote validation -------------------------------

def test_normalized_quote_matches_across_case_and_whitespace() -> None:
    message = "Tôi   đã ĐẶT cọc 20 triệu."
    spans, _ = locate_quote("tôi đã đặt cọc 20 triệu", message)
    assert len(spans) == 1
    # The persisted span points into the ORIGINAL message, not the model text.
    assert message[spans[0].original_start:spans[0].original_end] == spans[0].original_quote
    assert "ĐẶT" in spans[0].original_quote


def test_quote_absent_from_message_is_not_located() -> None:
    spans, _ = locate_quote("chủ nhà đã trả tiền", "Tôi đã đặt cọc 20 triệu.")
    assert spans == []


def test_index_map_round_trips() -> None:
    message = "Tôi  không   có giấy đặt cọc"
    normalized, index_map = normalize_with_map(message)
    assert len(normalized) == len(index_map)
    assert normalized == "tôi không có giấy đặt cọc"


# -- 18: numeric value parsed from the verified span ------------------------

def test_amount_parsing_bounded_formats() -> None:
    assert parse_amount_from_text("20 triệu") == 20_000_000
    assert parse_amount_from_text("15 triệu") == 15_000_000
    assert parse_amount_from_text("20tr") == 20_000_000
    assert parse_amount_from_text("500 nghìn") == 500_000
    assert parse_amount_from_text("không có số") is None


def test_amount_taken_from_span_not_from_model_value() -> None:
    state = FastDemoState()
    outcome = apply_fact_updates(
        state,
        [prop(operation="set", slot="deposit_amount", value=99_000_000, evidence_quote="20 triệu")],
        "Tôi đã đặt cọc 20 triệu.",
    )
    assert outcome.state.facts.deposit_amount is not None
    # The model claimed 99,000,000; only the verified span is trusted.
    assert outcome.state.facts.deposit_amount.value == 20_000_000


def test_amount_with_unverifiable_quote_is_rejected() -> None:
    state = FastDemoState()
    outcome = apply_fact_updates(
        state,
        [prop(operation="set", slot="deposit_amount", value=20_000_000, evidence_quote="30 triệu")],
        "Tôi đã đặt cọc 20 triệu.",
    )
    assert outcome.state.facts.deposit_amount is None
    assert any("evidence_not_found" in reason for reason in outcome.rejected)


# -- 17: conflicting matches reject the update ------------------------------

def test_conflicting_amount_matches_reject_update() -> None:
    # "triệu" appears twice with different preceding numbers; a single quote
    # that matches both cannot yield one unambiguous value.
    state = FastDemoState()
    outcome = apply_fact_updates(
        state,
        [prop(operation="set", slot="deposit_amount", value=20_000_000, evidence_quote="triệu")],
        "Tôi đặt cọc 20 triệu rồi trả thêm 5 triệu.",
    )
    assert outcome.state.facts.deposit_amount is None
    assert outcome.rejected


# -- 14/19: tri-state and polarity ------------------------------------------

def test_explicit_negative_sets_absent() -> None:
    state = FastDemoState()
    outcome = apply_fact_updates(
        state,
        [prop(
            operation="negate",
            slot="written_deposit_agreement_status",
            evidence_quote="không có giấy đặt cọc",
        )],
        "Tôi không có giấy đặt cọc.",
    )
    assert outcome.state.facts.written_deposit_agreement_status == "absent"


def test_explicit_positive_sets_present() -> None:
    state = FastDemoState()
    outcome = apply_fact_updates(
        state,
        [prop(
            operation="affirm",
            slot="payment_evidence_status",
            evidence_quote="có sao kê chuyển khoản",
        )],
        "Tôi có sao kê chuyển khoản.",
    )
    assert outcome.state.facts.payment_evidence_status == "present"


def test_landlord_has_not_returned_deposit_is_absent() -> None:
    state = FastDemoState()
    outcome = apply_fact_updates(
        state,
        [prop(
            operation="negate",
            slot="deposit_returned_status",
            evidence_quote="chưa trả tiền cọc",
        )],
        "Chủ nhà chưa trả tiền cọc.",
    )
    assert outcome.state.facts.deposit_returned_status == "absent"


def test_mere_mention_does_not_change_unknown() -> None:
    # "Giấy đặt cọc thì sao?" mentions the slot without asserting anything.
    state = FastDemoState()
    outcome = apply_fact_updates(
        state,
        [prop(
            operation="set",
            slot="written_deposit_agreement_status",
            evidence_quote="Giấy đặt cọc thì sao",
        )],
        "Giấy đặt cọc thì sao?",
    )
    assert outcome.state.facts.written_deposit_agreement_status == "unknown"
    assert outcome.rejected


def test_unknown_is_distinct_from_absent() -> None:
    state = FastDemoState()
    assert state.facts.rental_contract_status == "unknown"
    outcome = apply_fact_updates(
        state,
        [prop(
            operation="negate",
            slot="rental_contract_status",
            evidence_quote="không có hợp đồng",
        )],
        "Tôi không có hợp đồng thuê nhà.",
    )
    assert outcome.state.facts.rental_contract_status == "absent"


# -- 10: correction 20M -> 15M with bounded previous values -----------------

def test_correction_moves_old_amount_to_previous_values() -> None:
    state = FastDemoState()
    state.facts.deposit_amount = DepositAmount(value=20_000_000)
    outcome = apply_fact_updates(
        state,
        [prop(operation="correct", slot="deposit_amount", value=15_000_000, evidence_quote="15 triệu")],
        "Tôi nói nhầm, số tiền là 15 triệu.",
    )
    assert outcome.state.facts.deposit_amount is not None
    assert outcome.state.facts.deposit_amount.value == 15_000_000
    assert outcome.state.previous_values["deposit_amount"] == [
        {"value": 20_000_000, "currency": "VND"}
    ]
    # The input state object is never mutated in place.
    assert state.facts.deposit_amount.value == 20_000_000


# -- slot allowlist ---------------------------------------------------------

def test_unknown_slot_is_rejected() -> None:
    state = FastDemoState()
    outcome = apply_fact_updates(
        state,
        [prop(operation="set", slot="salary_amount", value=1, evidence_quote="20 triệu")],
        "Tôi đã đặt cọc 20 triệu.",
    )
    assert outcome.applied == []
    assert any("slot_not_allowed" in reason for reason in outcome.rejected)


def test_one_invalid_update_does_not_reject_the_valid_one() -> None:
    state = FastDemoState()
    outcome = apply_fact_updates(
        state,
        [
            prop(operation="set", slot="salary_amount", value=1, evidence_quote="20 triệu"),
            prop(operation="set", slot="deposit_amount", value=20_000_000, evidence_quote="20 triệu"),
        ],
        "Tôi đã đặt cọc 20 triệu.",
    )
    assert outcome.state.facts.deposit_amount is not None
    assert outcome.state.facts.deposit_amount.value == 20_000_000
    assert len(outcome.rejected) == 1


def test_payment_evidence_types_allowlisted() -> None:
    state = FastDemoState()
    outcome = apply_fact_updates(
        state,
        [
            prop(
                operation="set",
                slot="payment_evidence_types",
                value=["bank_transfer", "crypto_wallet"],
                evidence_quote="sao kê chuyển khoản",
            )
        ],
        "Tôi có sao kê chuyển khoản.",
    )
    assert outcome.state.facts.payment_evidence_types == ["bank_transfer"]
