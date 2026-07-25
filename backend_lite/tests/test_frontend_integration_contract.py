from pathlib import Path

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]


def analyze_content_from_response(body: dict) -> dict:
    keys = {
        "response_kind", "domain", "risk_level", "decision", "summary", "clarifying_questions", "checklist",
        "next_steps", "sources", "safety_notice", "confidence", "metadata",
    }
    return {key: body[key] for key in keys}


def test_optimistic_analyze_content_equals_reloaded_content(client, analyze_payload):
    body = client.post(
        "/api/analyze",
        json=analyze_payload("Tôi muốn bán đồ ăn online ở quê thì cần giấy tờ gì?", user_type="household_business"),
    ).json()
    reloaded = client.get(
        f"/api/chats/{body['chat_id']}", params={"session_id": "session_test"}
    ).json()["messages"][-1]["content_json"]
    assert reloaded == analyze_content_from_response(body)


def test_cors_preflight_for_frontend_origin(client):
    response = client.options(
        "/api/analyze",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_cors_preflight_rejects_disallowed_origin(client):
    response = client.options(
        "/api/analyze",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_unsupported_is_success_not_error_banner_condition(client, analyze_payload):
    response = client.post("/api/analyze", json=analyze_payload("Viết cho tôi bài thơ tình."))
    assert response.status_code == 200
    assert response.json()["decision"] == "unsupported"


def test_invalid_generated_response_is_not_stored_as_assistant(app, analyze_payload, monkeypatch):
    class InvalidResponse:
        def model_dump(self, *args, **kwargs):
            return {"contract_version": "v1"}

    monkeypatch.setattr(app.state.container.runtime.response_builder, "build", lambda _state: InvalidResponse())
    with TestClient(app, raise_server_exceptions=False) as safe_client:
        response = safe_client.post(
            "/api/analyze",
            json=analyze_payload("Tôi hỏi về tiền cọc.", "invalid_generation"),
        )
    assert response.status_code == 500
    chats = app.state.container.chat_store.list_chats("invalid_generation")
    assert len(chats) == 1
    messages = app.state.container.chat_store.list_messages(chats[0].chat_id)
    assert [message.role for message in messages] == ["user"]


def test_adaptive_structured_answer_presentation_contract() -> None:
    source = (REPO_ROOT / "frontend/src/components/StructuredAnswer.tsx").read_text(encoding="utf-8")

    assert 'if (visibleItems.length === 0) return null' in source
    assert '<h2>Tóm tắt ban đầu</h2>' not in source
    assert 'title="Bạn nên chuẩn bị"' in source
    assert 'title="Bạn có thể làm ngay"' in source
    assert source.index('title="Bạn có thể làm ngay"') < source.index('<ClarifyingQuestions')
    assert 'Để tôi đánh giá chính xác hơn, bạn có thể cho biết thêm:' in source
    assert '<SafetyNotice' not in source
    assert "content.response_kind === 'social'" in source


def test_source_and_badge_presentation_policy_is_public_safe() -> None:
    source = (REPO_ROOT / "frontend/src/components/StructuredAnswer.tsx").read_text(encoding="utf-8")

    assert "source.source_type !== 'curated_note'" in source
    assert "source.source_type !== 'safety_policy'" in source
    assert "source.source_type !== 'demo_only'" in source
    assert "source.source_type !== 'official_source'" not in source
    assert "isFollowUp ? [] : content.sources.filter" in source
    assert "content.domain !== 'high_risk'" in source


def test_new_chat_notice_and_assistant_header_contract() -> None:
    app_source = (REPO_ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    bubble_source = (REPO_ROOT / "frontend/src/components/MessageBubble.tsx").read_text(encoding="utf-8")
    css_source = (REPO_ROOT / "frontend/src/styles/globals.css").read_text(encoding="utf-8")

    assert "VietLaw-Chat cung cấp định hướng ban đầu và không thay thế tư vấn pháp lý chuyên nghiệp." in app_source
    assert "messages.some((message) => message.role === 'assistant')" in app_source
    assert "'Trợ lý'" not in bubble_source
    assert "<time" not in bubble_source
    assert "title={isUser ? undefined : formatDate(message.created_at)}" in bubble_source
    assert ".composer-legal-reference { display: none; }" in css_source

