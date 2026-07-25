from backend_lite.app.services.deposit_case_facts import (
    DepositCaseFacts,
    classify_follow_up_intent,
    extract_facts,
    extract_facts_from_text,
    select_clarifying_questions,
)
from backend_lite.app.services.input_normalizer import InputNormalizer

NORMALIZER = InputNormalizer()


def test_initial_message_extracts_amount_agreement_delivery_and_refund_facts():
    text = (
        "Tôi đặt cọc 20 triệu để thuê nhà, có giấy viết tay, nhưng chủ nhà không giao "
        "nhà và không trả cọc. Tôi nên làm gì?"
    )
    facts = extract_facts_from_text(text, NORMALIZER)
    assert facts.deposit_amount_millions == 20.0
    assert facts.has_written_agreement is True
    assert facts.property_not_delivered is True
    assert facts.refund_refused is True
    assert facts.has_signature is False
    assert facts.has_payment_proof is False


def test_short_amount_form_and_deposit_paper_phrase_are_supported():
    facts = extract_facts_from_text("cọc 20tr, có giấy đặt cọc", NORMALIZER)
    assert facts.deposit_amount_millions == 20.0
    assert facts.has_written_agreement is True


def test_signature_and_payment_proof_phrases_are_supported():
    facts = extract_facts_from_text("có chữ ký và có biên nhận", NORMALIZER)
    assert facts.has_signature is True
    assert facts.has_payment_proof is True


def test_bank_transfer_implies_payment_proof_and_cash_does_not():
    bank = extract_facts_from_text("tôi chuyển khoản tiền cọc", NORMALIZER)
    assert bank.payment_method == "bank_transfer"
    assert bank.has_payment_proof is True

    cash = extract_facts_from_text("tôi đưa tiền mặt", NORMALIZER)
    assert cash.payment_method == "cash"
    assert cash.has_payment_proof is False


def test_extract_facts_merges_across_bounded_message_list():
    facts = extract_facts(
        ["đặt cọc 20 triệu, có giấy viết tay", "chủ nhà không giao nhà và không trả cọc"],
        NORMALIZER,
    )
    assert facts.deposit_amount_millions == 20.0
    assert facts.has_written_agreement is True
    assert facts.property_not_delivered is True
    assert facts.refund_refused is True


def test_select_clarifying_questions_never_asks_amount_or_written_agreement():
    facts = DepositCaseFacts()
    selected_ids = {question_id for question_id, _ in select_clarifying_questions(facts, set())}
    assert selected_ids == {"signature", "payment_proof"}
    assert "deposit_amount" not in selected_ids
    assert "written_agreement" not in selected_ids


def test_select_clarifying_questions_skips_known_and_already_asked():
    facts = DepositCaseFacts(has_signature=True)
    selected_ids = {question_id for question_id, _ in select_clarifying_questions(facts, {"payment_proof"})}
    assert selected_ids == {"refund_terms", "timeline"}
    assert "signature" not in selected_ids
    assert "payment_proof" not in selected_ids


def test_select_clarifying_questions_caps_at_two():
    facts = DepositCaseFacts()
    selected = select_clarifying_questions(facts, set())
    assert len(selected) <= 2


def test_classify_follow_up_intent_action_risk_fact_update_and_general():
    empty = DepositCaseFacts()
    assert classify_follow_up_intent("tôi nên làm gì?", empty, NORMALIZER) == "action_request"
    assert classify_follow_up_intent("bây giờ phải làm sao?", empty, NORMALIZER) == "action_request"
    assert classify_follow_up_intent("tôi có sợ bị quỵt không?", empty, NORMALIZER) == "risk_concern"
    fact_bearing = extract_facts_from_text("tôi chuyển khoản và giấy có chữ ký", NORMALIZER)
    assert classify_follow_up_intent("tôi chuyển khoản và giấy có chữ ký", fact_bearing, NORMALIZER) == "fact_update"
    assert classify_follow_up_intent("còn gì nữa không?", empty, NORMALIZER) == "general_follow_up"
