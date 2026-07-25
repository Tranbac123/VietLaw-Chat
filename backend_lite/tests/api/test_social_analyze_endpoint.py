from __future__ import annotations

INITIAL_DEPOSIT_QUESTION = (
    "Tôi đặt cọc 20 triệu để thuê nhà, có giấy viết tay, nhưng chủ nhà không giao "
    "nhà và không trả cọc. Tôi nên làm gì?"
)


# ---------------------------------------------------------------------------
# 14.5 -- persistence
# ---------------------------------------------------------------------------


def test_social_response_appears_in_chat_detail_with_correct_message_count(client, analyze_payload):
    body = client.post("/api/analyze", json=analyze_payload("Xin chào", "social-detail")).json()
    detail = client.get(f"/api/chats/{body['chat_id']}", params={"session_id": "social-detail"}).json()

    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][0]["content_text"] == "Xin chào"
    assert detail["messages"][1]["role"] == "assistant"
    assert detail["messages"][1]["content_json"]["response_kind"] == "social"
    assert detail["messages"][1]["content_json"]["domain"] is None


def test_reload_does_not_lose_or_duplicate_the_social_response(client, analyze_payload):
    body = client.post("/api/analyze", json=analyze_payload("Bạn là ai?", "social-reload")).json()

    first_reload = client.get(f"/api/chats/{body['chat_id']}", params={"session_id": "social-reload"}).json()
    second_reload = client.get(f"/api/chats/{body['chat_id']}", params={"session_id": "social-reload"}).json()

    assert len(first_reload["messages"]) == 2
    assert len(second_reload["messages"]) == 2
    assert first_reload["messages"] == second_reload["messages"]
    assert second_reload["messages"][1]["content_json"]["summary"] == body["summary"]


def test_follow_up_legal_question_in_same_chat_still_runs_legal_pipeline_after_a_social_turn(
    client, analyze_payload
):
    greeting = client.post(
        "/api/analyze", json=analyze_payload("Xin chào", "social-then-legal")
    ).json()
    assert greeting["response_kind"] == "social"

    followup = client.post(
        "/api/analyze",
        json=analyze_payload(
            "Tôi thuê nhà, chủ nhà giữ tiền cọc không trả.",
            session_id="social-then-legal",
            chat_id=greeting["chat_id"],
        ),
    ).json()

    assert followup["chat_id"] == greeting["chat_id"]
    assert followup["response_kind"] == "legal"
    assert followup["domain"] is not None
    assert followup["decision"] is not None

    detail = client.get(
        f"/api/chats/{greeting['chat_id']}", params={"session_id": "social-then-legal"}
    ).json()
    assert len(detail["messages"]) == 4
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]


def test_social_turn_does_not_erase_deposit_case_facts_context(client, analyze_payload):
    first = client.post(
        "/api/analyze", json=analyze_payload(INITIAL_DEPOSIT_QUESTION, session_id="s_social_mid_deposit")
    ).json()
    assert first["response_kind"] == "legal"
    first_clarifying = set(first["clarifying_questions"])

    greeting = client.post(
        "/api/analyze",
        json=analyze_payload("Xin chào", session_id="s_social_mid_deposit", chat_id=first["chat_id"]),
    ).json()
    assert greeting["chat_id"] == first["chat_id"]
    assert greeting["response_kind"] == "social"

    followup = client.post(
        "/api/analyze",
        json=analyze_payload("tôi nên làm gì?", session_id="s_social_mid_deposit", chat_id=first["chat_id"]),
    ).json()

    assert followup["chat_id"] == first["chat_id"]
    assert followup["response_kind"] == "legal"
    assert followup["next_steps"]
    # the deposit facts already established by the initial turn must still be in
    # effect: the follow-up must not re-ask the same clarifying questions.
    assert set(followup["clarifying_questions"]) & first_clarifying == set()
