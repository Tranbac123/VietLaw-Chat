def test_explicit_create_list_get_delete_chat(client):
    created = client.post("/api/chats", json={"session_id": "session_crud", "title": "Chat thử"})
    assert created.status_code == 200
    chat_id = created.json()["chat_id"]

    listed = client.get("/api/chats", params={"session_id": "session_crud"}).json()
    assert [chat["chat_id"] for chat in listed["chats"]] == [chat_id]

    detail = client.get(f"/api/chats/{chat_id}", params={"session_id": "session_crud"}).json()
    assert detail["messages"] == []
    assert detail["session_id"] == "session_crud"

    deleted = client.delete(f"/api/chats/{chat_id}", params={"session_id": "session_crud"})
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/api/chats/{chat_id}", params={"session_id": "session_crud"}).status_code == 404


def test_list_chats_scoped_by_session(client, analyze_payload):
    first = client.post("/api/analyze", json=analyze_payload("Tôi hỏi về tiền cọc.", "session_a")).json()
    second = client.post("/api/analyze", json=analyze_payload("Tôi hỏi về biên bản giao thông.", "session_b")).json()
    a_ids = {item["chat_id"] for item in client.get("/api/chats", params={"session_id": "session_a"}).json()["chats"]}
    assert first["chat_id"] in a_ids
    assert second["chat_id"] not in a_ids


def test_get_chat_returns_full_message_shape(client, analyze_payload):
    analyzed = client.post(
        "/api/analyze",
        json=analyze_payload("Tôi thuê nhà, chủ nhà giữ tiền cọc không trả."),
    ).json()
    messages = client.get(
        f"/api/chats/{analyzed['chat_id']}", params={"session_id": "session_test"}
    ).json()["messages"]
    assert len(messages) == 2
    required = {"message_id", "chat_id", "role", "content_type", "content_text", "content_json", "created_at"}
    assert all(set(message) == required for message in messages)
    assert messages[0]["content_type"] == "text"
    assert messages[1]["content_type"] == "structured"
    assert messages[1]["content_json"] is not None
    assert set(messages[1]["content_json"]) == {
        "response_kind", "domain", "risk_level", "decision", "summary", "clarifying_questions", "checklist",
        "next_steps", "sources", "safety_notice", "confidence", "metadata",
    }


def test_user_and_assistant_messages_are_persisted_with_backend_ids(client, analyze_payload):
    body = client.post("/api/analyze", json=analyze_payload("Tôi hỏi về giấy phạt giao thông.")).json()
    messages = client.get(
        f"/api/chats/{body['chat_id']}", params={"session_id": "session_test"}
    ).json()["messages"]
    assert messages[0]["message_id"] == body["user_message_id"]
    assert messages[0]["content_text"] == "Tôi hỏi về giấy phạt giao thông."
    assert messages[1]["message_id"] == body["assistant_message_id"]
