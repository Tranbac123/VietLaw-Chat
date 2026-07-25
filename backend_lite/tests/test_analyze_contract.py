from backend_lite.app.constants import SAFETY_NOTICE


REQUIRED_FIELDS = {
    "response_kind", "contract_version", "request_id", "chat_id", "user_message_id", "assistant_message_id",
    "domain", "risk_level", "decision", "summary", "clarifying_questions", "checklist",
    "next_steps", "sources", "safety_notice", "confidence", "metadata",
}


def test_new_analyze_creates_chat_and_full_contract(client, analyze_payload):
    response = client.post(
        "/api/analyze",
        json=analyze_payload("Tôi thuê nhà, chủ nhà giữ tiền cọc không trả."),
    )
    body = response.json()
    assert response.status_code == 200
    assert REQUIRED_FIELDS == set(body)
    assert body["chat_id"].startswith("chat_")
    assert body["user_message_id"].startswith("msg_user_")
    assert body["assistant_message_id"].startswith("msg_asst_")


def test_new_analyze_requires_session_id(client):
    response = client.post(
        "/api/analyze",
        json={"question": "Tôi cần hỏi về tiền cọc.", "language": "vi"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_invalid_requests_use_public_400_envelope(client):
    requests = [
        {"session_id": "s"},
        {"session_id": "s", "question": "   "},
        {"session_id": "s", "question": "Tôi hỏi pháp lý", "user_type": "invalid"},
        {"session_id": "s", "question": "Tôi hỏi pháp lý", "language": "x"},
    ]
    for payload in requests:
        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_request"

    invalid_json = client.post(
        "/api/analyze", content="{not-json", headers={"Content-Type": "application/json"}
    )
    assert invalid_json.status_code == 400
    assert invalid_json.json()["error"]["code"] == "invalid_request"
    assert "Traceback" not in invalid_json.text


def test_new_analyze_omits_chat_id_safely(client, analyze_payload):
    payload = analyze_payload("Tôi muốn mở hộ kinh doanh nhỏ.")
    assert "chat_id" not in payload
    response = client.post("/api/analyze", json=payload)
    assert response.status_code == 200
    assert response.json()["chat_id"]


def test_confidence_has_exact_contract_fields(client, analyze_payload):
    body = client.post("/api/analyze", json=analyze_payload("Tôi cần hỏi về tiền cọc.")).json()
    assert set(body["confidence"]) == {"domain", "risk", "answer"}


def test_exact_safety_notice(client, analyze_payload):
    body = client.post("/api/analyze", json=analyze_payload("Tôi cần hỏi về tiền cọc.")).json()
    assert body["safety_notice"] == SAFETY_NOTICE


def test_backend_lite_metadata(client, analyze_payload):
    body = client.post("/api/analyze", json=analyze_payload("Tôi cần hỏi về tiền cọc.")).json()
    metadata = body["metadata"]
    assert metadata["used_llm"] is False
    assert metadata["model_name"] == "backend_lite_template_v1"
    assert metadata["llm_parse_error"] is False
    assert metadata["guards_applied"] == {
        "citation_guard": True,
        "safety_guard": True,
        "fallback_used": False,
    }


def test_script_shaped_question_is_stored_and_returned_as_json_data(client, analyze_payload):
    question = "<script>alert(1)</script> Tôi thuê nhà bị giữ cọc"
    response = client.post("/api/analyze", json=analyze_payload(question, "script_session"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    detail = client.get(
        f"/api/chats/{body['chat_id']}", params={"session_id": "script_session"}
    ).json()
    assert detail["messages"][0]["content_text"] == question
