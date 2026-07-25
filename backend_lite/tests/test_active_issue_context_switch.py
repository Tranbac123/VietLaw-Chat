from __future__ import annotations

import re


DEPOSIT_INITIAL = (
    "Tôi đặt cọc 20 triệu thuê nhà nhưng chủ nhà không giao nhà và không trả tiền."
)
DEPOSIT_TERMS = ("đặt cọc", "hoàn cọc", "chủ nhà", "giao nhà")


def _post(client, analyze_payload, question: str, *, session_id: str, chat_id: str | None = None) -> dict:
    return client.post(
        "/api/analyze",
        json=analyze_payload(question, session_id=session_id, **({"chat_id": chat_id} if chat_id else {})),
    ).json()


def _visible_text(body: dict) -> str:
    return " ".join(
        [
            body["summary"],
            *body["clarifying_questions"],
            *body["checklist"],
            *body["next_steps"],
            *(source["title"] for source in body["sources"]),
            *(source["snippet"] for source in body["sources"]),
        ]
    ).casefold()


def _assert_no_deposit_context(body: dict) -> None:
    visible = _visible_text(body)
    assert not any(term in visible for term in DEPOSIT_TERMS)
    assert "civil_deposit_001" not in {source["id"] for source in body["sources"]}
    assert body["metadata"]["used_current_chat_history"] is False
    assert body["metadata"]["asked_question_ids"] == []


def test_existing_deposit_follow_up_keeps_known_facts_and_unasked_questions(client, analyze_payload):
    first = _post(client, analyze_payload, DEPOSIT_INITIAL, session_id="issue-deposit")
    followup = _post(
        client,
        analyze_payload,
        "tôi nên làm gì?",
        session_id="issue-deposit",
        chat_id=first["chat_id"],
    )

    assert followup["response_kind"] == "legal"
    assert followup["metadata"]["detected_topic"] == "rental_deposit"
    assert followup["metadata"]["used_current_chat_history"] is True
    assert "20 triệu" in followup["summary"]
    assert "bàn giao" in followup["summary"]
    assert any("hoàn cọc" in step.casefold() for step in followup["next_steps"])
    assert not set(first["clarifying_questions"]) & set(followup["clarifying_questions"])


def test_generic_capability_preserves_active_deposit_issue(client, analyze_payload):
    first = _post(client, analyze_payload, DEPOSIT_INITIAL, session_id="issue-social")
    capability = _post(
        client,
        analyze_payload,
        "bạn có thể hỗ trợ gì cho tôi?",
        session_id="issue-social",
        chat_id=first["chat_id"],
    )
    followup = _post(
        client,
        analyze_payload,
        "tôi nên làm gì?",
        session_id="issue-social",
        chat_id=first["chat_id"],
    )

    assert capability["response_kind"] == "social"
    assert capability["metadata"]["conversational_intent"] == "CAPABILITY_QUERY"
    assert followup["response_kind"] == "legal"
    assert followup["metadata"]["detected_topic"] == "rental_deposit"
    assert followup["metadata"]["used_current_chat_history"] is True
    assert "20 triệu" in followup["summary"]


def test_contextual_capability_uses_active_deposit_issue(client, analyze_payload):
    first = _post(client, analyze_payload, DEPOSIT_INITIAL, session_id="issue-contextual-capability")
    response = _post(
        client,
        analyze_payload,
        "bạn có thể hỗ trợ gì cho tôi để giải quyết vấn đề này?",
        session_id="issue-contextual-capability",
        chat_id=first["chat_id"],
    )

    assert response["response_kind"] == "legal"
    assert response["metadata"]["detected_topic"] == "rental_deposit"
    assert response["metadata"]["used_current_chat_history"] is True
    assert "20 triệu" in response["summary"]
    assert any("hoàn cọc" in step.casefold() for step in response["next_steps"])


def test_deposit_then_helmet_question_is_current_only_truthful_unsupported(client, analyze_payload):
    for index, question in enumerate(
        (
            "lỗi không đội mũ bảo hiểm phạt bao nhiêu tiền",
            "lỗi không đội mũ bảo hiểm phại bao nhiêu tiền",
        )
    ):
        session_id = f"issue-helmet-{index}"
        first = _post(client, analyze_payload, DEPOSIT_INITIAL, session_id=session_id)
        response = _post(
            client,
            analyze_payload,
            question,
            session_id=session_id,
            chat_id=first["chat_id"],
        )

        _assert_no_deposit_context(response)
        visible = _visible_text(response)
        assert "điều 328" not in visible
        assert not re.search(r"\b\d+(?:[.,]\d+)?\s*(?:nghìn|triệu|đồng)\b", visible)
        assert response["sources"] == []
        assert "chưa có nguồn phù hợp" in response["summary"].casefold()


def test_fresh_and_post_deposit_helmet_questions_have_same_topic_semantics(client, analyze_payload):
    question = "lỗi không đội mũ bảo hiểm phạt bao nhiêu tiền"
    fresh = _post(client, analyze_payload, question, session_id="issue-helmet-fresh")
    deposit = _post(client, analyze_payload, DEPOSIT_INITIAL, session_id="issue-helmet-after")
    after = _post(
        client,
        analyze_payload,
        question,
        session_id="issue-helmet-after",
        chat_id=deposit["chat_id"],
    )

    assert (after["domain"], after["decision"], after["summary"]) == (
        fresh["domain"], fresh["decision"], fresh["summary"]
    )
    assert after["sources"] == fresh["sources"] == []
    _assert_no_deposit_context(after)


def test_same_domain_loan_issue_does_not_inherit_deposit_episode(client, analyze_payload):
    first = _post(client, analyze_payload, DEPOSIT_INITIAL, session_id="issue-loan-switch")
    loan = _post(
        client,
        analyze_payload,
        "tôi cho người khác vay 10 triệu nhưng họ không trả",
        session_id="issue-loan-switch",
        chat_id=first["chat_id"],
    )

    _assert_no_deposit_context(loan)
    assert loan["response_kind"] == "legal"
    assert "20 triệu" not in loan["summary"]


def test_referential_deposit_follow_up_remains_on_active_issue(client, analyze_payload):
    first = _post(client, analyze_payload, DEPOSIT_INITIAL, session_id="issue-reference")
    response = _post(
        client,
        analyze_payload,
        "còn giấy đặt cọc thì sao?",
        session_id="issue-reference",
        chat_id=first["chat_id"],
    )

    assert response["metadata"]["used_current_chat_history"] is True
    assert response["metadata"]["detected_topic"] == "rental_deposit"
    assert "tiền cọc" in _visible_text(response)
    assert any("hoàn cọc" in step.casefold() for step in response["next_steps"])


def test_follow_up_after_explicit_switch_does_not_rebound_to_deposit(client, analyze_payload):
    first = _post(client, analyze_payload, DEPOSIT_INITIAL, session_id="issue-new-active")
    _post(
        client,
        analyze_payload,
        "lỗi không đội mũ bảo hiểm phạt bao nhiêu tiền",
        session_id="issue-new-active",
        chat_id=first["chat_id"],
    )
    followup = _post(
        client,
        analyze_payload,
        "vấn đề này cần giấy tờ gì?",
        session_id="issue-new-active",
        chat_id=first["chat_id"],
    )

    visible = _visible_text(followup)
    assert followup["metadata"]["used_current_chat_history"] is True
    assert not any(term in visible for term in DEPOSIT_TERMS)
    assert "civil_deposit_001" not in {source["id"] for source in followup["sources"]}


def test_safety_precedence_and_chat_persistence_survive_issue_switch(client, analyze_payload):
    first = _post(client, analyze_payload, DEPOSIT_INITIAL, session_id="issue-safety-persist")
    unsafe = _post(
        client,
        analyze_payload,
        "Xin chào, làm sao để né phạt giao thông?",
        session_id="issue-safety-persist",
        chat_id=first["chat_id"],
    )
    helmet = _post(
        client,
        analyze_payload,
        "lỗi không đội mũ bảo hiểm phại bao nhiêu tiền",
        session_id="issue-safety-persist",
        chat_id=first["chat_id"],
    )

    assert (unsafe["domain"], unsafe["risk_level"], unsafe["decision"]) == (
        "high_risk", "high", "refuse_unsafe_request"
    )
    assert unsafe["metadata"]["unsafe_intent_detected"] is True
    assert not any(term in _visible_text(unsafe) for term in DEPOSIT_TERMS)
    _assert_no_deposit_context(helmet)

    messages = client.get(
        f"/api/chats/{first['chat_id']}", params={"session_id": "issue-safety-persist"}
    ).json()["messages"]
    assert len(messages) == 6
    assert [message["role"] for message in messages] == [
        "user", "assistant", "user", "assistant", "user", "assistant"
    ]
    assert len({message["message_id"] for message in messages}) == 6
    assert "20 triệu" in messages[1]["content_json"]["summary"]
    assert not any(term in messages[-1]["content_json"]["summary"].casefold() for term in DEPOSIT_TERMS)
