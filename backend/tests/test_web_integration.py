"""HTTP integration tests for the web layer.

Boots the real FastAPI app over the real pipeline (real RAG + safety data,
temp SQLite), but injects a fake LLM transport so tests never hit the network.
Covers health, analyze, the chat lifecycle, session-ownership 404s, and error
mapping.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm.llm_client import LLMClient
from app.main import create_app
from app.runtime.analyze import AiCore

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data"

# Valid LLMContent JSON — used_source_ids empty so it always passes the citation guard.
_FAKE_LLM_JSON = json.dumps(
    {
        "summary": "Đây là định hướng ban đầu cho vụ việc của bạn.",
        "clarifying_questions": ["Bạn có giấy tờ liên quan không?"],
        "checklist": ["Giấy tờ liên quan"],
        "next_steps": ["Tham khảo cơ quan chức năng."],
        "used_source_ids": [],
    },
    ensure_ascii=False,
)


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        legal_snippets_path=str(DATA / "legal_snippets.json"),
        unsafe_patterns_path=str(DATA / "unsafe_patterns.json"),
        chat_db_path=str(tmp_path / "test_chat.sqlite3"),
        frontend_origin="http://localhost:5173",
    )
    fake_llm = LLMClient(settings, transport=lambda _prompt: _FAKE_LLM_JSON)
    core = AiCore(settings, llm=fake_llm)
    app = create_app(settings=settings, core=core)
    return TestClient(app)


# ------------------------------------------------------------------ health

def test_health_ok(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "vietlaw-chat-backend"
    assert body["contract_version"] == "v1"
    assert body["rag_loaded"] and body["safety_loaded"] and body["chat_store_ready"]


# ------------------------------------------------------------------ analyze

def test_analyze_new_chat_returns_full_envelope(client: TestClient) -> None:
    r = client.post(
        "/api/analyze",
        json={"question": "Tôi bị nợ tiền không trả, phải làm gì?", "session_id": "s1"},
    )
    assert r.status_code == 200
    body = r.json()
    for field in (
        "contract_version", "request_id", "chat_id", "user_message_id",
        "assistant_message_id", "domain", "risk_level", "decision", "summary",
        "sources", "safety_notice", "confidence", "metadata",
    ):
        assert field in body
    assert body["contract_version"] == "v1"
    assert body["chat_id"]
    assert body["safety_notice"]


def test_analyze_short_question_is_invalid_request(client: TestClient) -> None:
    r = client.post("/api/analyze", json={"question": "a", "session_id": "s1"})
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "invalid_request"
    assert body["safety_notice"]


def test_analyze_follow_up_reuses_chat(client: TestClient) -> None:
    first = client.post(
        "/api/analyze", json={"question": "Tranh chấp tiền cọc thuê nhà.", "session_id": "s1"}
    ).json()
    chat_id = first["chat_id"]
    second = client.post(
        "/api/analyze",
        json={"question": "Tôi chưa có hợp đồng.", "session_id": "s1", "chat_id": chat_id},
    ).json()
    assert second["chat_id"] == chat_id


# ------------------------------------------------------------------ chats

def test_chat_create_list_detail_delete_lifecycle(client: TestClient) -> None:
    created = client.post("/api/chats", json={"session_id": "s1", "title": "Vụ việc A"})
    assert created.status_code == 200
    chat_id = created.json()["chat_id"]
    assert created.json()["title"] == "Vụ việc A"

    listed = client.get("/api/chats", params={"session_id": "s1"})
    assert listed.status_code == 200
    assert any(c["chat_id"] == chat_id for c in listed.json()["chats"])

    detail = client.get(f"/api/chats/{chat_id}", params={"session_id": "s1"})
    assert detail.status_code == 200
    assert detail.json()["chat_id"] == chat_id

    deleted = client.delete(f"/api/chats/{chat_id}", params={"session_id": "s1"})
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    # gone after delete
    assert client.get(f"/api/chats/{chat_id}", params={"session_id": "s1"}).status_code == 404


def test_analyze_persists_user_and_assistant_messages(client: TestClient) -> None:
    resp = client.post(
        "/api/analyze", json={"question": "Tôi bị nợ tiền không trả.", "session_id": "s1"}
    ).json()
    detail = client.get(f"/api/chats/{resp['chat_id']}", params={"session_id": "s1"}).json()
    roles = [(m["role"], m["content_type"]) for m in detail["messages"]]
    assert ("user", "text") in roles
    assert ("assistant", "structured") in roles


def test_wrong_session_is_not_found(client: TestClient) -> None:
    chat_id = client.post("/api/chats", json={"session_id": "owner"}).json()["chat_id"]
    r = client.get(f"/api/chats/{chat_id}", params={"session_id": "intruder"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "chat_not_found"


def test_missing_chat_is_not_found(client: TestClient) -> None:
    r = client.get("/api/chats/chat_does_not_exist", params={"session_id": "s1"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "chat_not_found"


def test_list_chats_requires_session_id(client: TestClient) -> None:
    r = client.get("/api/chats")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_request"
