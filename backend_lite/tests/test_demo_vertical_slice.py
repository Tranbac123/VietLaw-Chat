from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend_lite.app.config import Settings
from backend_lite.app.contracts.demo_llm import LLMErrorKind
from backend_lite.app.main import create_app
from backend_lite.app.services.demo_llm_client import DemoLLMConfig, FakeLLMClient
from backend_lite.app.services.demo_llm_generation import (
    ARTICLE_328_AUTHORITY_ID,
    EVIDENCE_CHECKLIST_ID,
    DemoOrchestrator,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        backend_mode="lite",
        chat_db_path=tmp_path / "chat.sqlite3",
        legal_snippets_path=REPO_ROOT / "data" / "legal_snippets.json",
        unsafe_patterns_path=REPO_ROOT / "data" / "unsafe_patterns.json",
        cors_origins="http://127.0.0.1:5173",
    )


def _config() -> DemoLLMConfig:
    return DemoLLMConfig(enabled=True, provider="anthropic", model="claude-x", timeout_s=15.0, api_key="k")


def _guidance_plan() -> str:
    return json.dumps({"plan_kind": "legal_guidance", "summary_code": "deposit_not_returned",
                       "action_codes": ["send_written_refund_request", "preserve_payment_evidence"], "tone": "neutral"})


def _draft_plan() -> str:
    return json.dumps({"plan_kind": "draft_request", "summary_code": "deposit_not_returned",
                       "action_codes": [], "tone": "polite_firm"})


def _demo_client(tmp_path: Path, fake: FakeLLMClient) -> TestClient:
    app = create_app(_settings(tmp_path))
    container = app.state.container
    sources = {
        s.id: s.as_source()
        for s in container.snippet_store.active_snippets()
        if s.id in (ARTICLE_328_AUTHORITY_ID, EVIDENCE_CHECKLIST_ID)
    }
    container.runtime.demo_orchestrator = DemoOrchestrator(llm_client=fake, llm_config=_config(), source_objects=sources)
    return TestClient(app)


def _post(client: TestClient, question: str) -> dict:
    response = client.post("/api/analyze", json={"session_id": "demo", "question": question, "user_type": "citizen", "language": "vi"})
    assert response.status_code == 200, response.text
    return response.json()


# --- safety (incl. separator variants) --------------------------------------

@pytest.mark.parametrize(
    "question",
    [
        "Chủ nhà đang giữ dao và đe dọa tôi vì tiền cọc. Tôi nên làm gì?",
        "Chủ nhà cầm mã-tấu vì tiền cọc. Tôi nên làm gì?",
        "Tôi muốn trả_thù chủ nhà vì tiền cọc.",
        "công-an mời tôi làm việc về tiền cọc.",
        "Tôi bị triệu_tập vì tiền cọc.",
        "Tôi muốn tự xử chủ nhà vì họ không trả tiền cọc. Tôi nên làm gì?",
        "Tôi đang bị hành hung vì tranh chấp tiền cọc.",
        "Chủ nhà dọa giết tôi vì khoản cọc.",
    ],
)
def test_safety_defers_no_provider(tmp_path, question):
    fake = FakeLLMClient(responses=[_guidance_plan()])
    with _demo_client(tmp_path, fake) as client:
        body = _post(client, question)
    assert "demo_route" not in body["metadata"]
    assert fake.calls == 0


# --- false context ----------------------------------------------------------

@pytest.mark.parametrize(
    "question",
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
    ],
)
def test_false_context_unsupported_no_provider(tmp_path, question):
    fake = FakeLLMClient(responses=[_guidance_plan()])
    with _demo_client(tmp_path, fake) as client:
        body = _post(client, question)
    assert body["metadata"]["demo_route"] == "policy_direct"
    assert body["metadata"]["demo_scenario"] == "unsupported"
    assert fake.calls == 0


# --- V4: complete-message residual-text reproducers (real API/runtime) ------

@pytest.mark.parametrize(
    "question",
    [
        "Tôi đã đặt cọc 20 triệu. Tôi bị sa thải. Tôi nên làm gì?",
        "Tôi đã đặt cọc 20 triệu. Tôi muốn ly hôn. Tôi nên làm gì?",
        "Tôi đã đặt cọc 20 triệu. Tôi đang hỏi khoản vay. Tôi nên làm gì?",
        "Tôi đã đặt cọc 20 triệu. Viết giúp tôi đơn ly hôn.",
        "Tôi đã đặt cọc 20 triệu. Tôi bị phạt giao thông. Tôi nên làm gì?",
        "Tôi đã đặt cọc 20 triệu. Tôi đang hỏi khoản vay.",
    ],
)
def test_residual_reproducers_no_deposit_response(tmp_path, question):
    fake = FakeLLMClient(responses=[_guidance_plan(), _draft_plan()])
    with _demo_client(tmp_path, fake) as client:
        body = _post(client, question)
    assert body["metadata"]["demo_route"] == "policy_direct"
    assert body["metadata"]["demo_scenario"] == "unsupported"
    assert fake.calls == 0  # provider attempts = 0
    assert body.get("sources") == []  # no civil_deposit_001 / no demo source metadata
    # no deposit guidance/draft content leaked through (the policy scope notice
    # legitimately mentions "đặt cọc" as the supported topic; it must not contain
    # actual guidance/drafting phrasing).
    assert "yêu cầu hoàn trả tiền đặt cọc bằng văn bản" not in body["summary"]
    assert "Kính gửi anh/chị chủ nhà" not in body["summary"]
    assert body["decision"] != "answer_with_guidance"


# --- approved scripts -------------------------------------------------------

def test_greeting_direct_no_provider(tmp_path):
    fake = FakeLLMClient(responses=[_guidance_plan()])
    with _demo_client(tmp_path, fake) as client:
        body = _post(client, "Xin chào")
    assert body["response_kind"] == "social"
    assert body["metadata"]["demo_route"] == "social_direct"
    assert fake.calls == 0


def test_fact_update_no_provider(tmp_path):
    fake = FakeLLMClient(responses=[_guidance_plan()])
    with _demo_client(tmp_path, fake) as client:
        body = _post(client, "Tôi đã đặt cọc 20 triệu. Tôi không có giấy đặt cọc nhưng có sao kê chuyển khoản.")
    assert body["metadata"]["demo_route"] == "fact_update_direct"
    assert "20 triệu" in body["summary"]
    assert fake.calls == 0


def test_legal_guidance_one_provider_call(tmp_path):
    fake = FakeLLMClient(responses=[_guidance_plan()])
    with _demo_client(tmp_path, fake) as client:
        body = _post(client, "Tôi đã đặt cọc 20 triệu, không có giấy đặt cọc, có sao kê chuyển khoản, "
                             "chưa được bàn giao nhà và chủ nhà chưa trả lại tiền cọc. Tôi nên làm gì?")
    md = body["metadata"]
    assert md["demo_route"] == "legal_generation" and md["outcome"] == "llm_accepted" and md["provider_calls"] == 1
    assert "20 triệu" in body["summary"]
    assert "Điều" not in body["summary"] and "Bộ luật" not in body["summary"]  # no legal reference in prose
    assert {s["id"] for s in body["sources"]} == {"civil_deposit_001"}  # backend Source metadata only


def test_drafting_one_provider_call(tmp_path):
    fake = FakeLLMClient(responses=[_draft_plan()])
    with _demo_client(tmp_path, fake) as client:
        body = _post(client, "Tôi đã đặt cọc 20 triệu nhưng chủ nhà chưa trả lại tiền cọc. Viết giúp tôi tin nhắn yêu cầu hoàn trả tiền cọc.")
    md = body["metadata"]
    assert md["demo_route"] == "document_drafting" and md["provider_calls"] == 1
    assert "20 triệu" in body["summary"]
    assert "Điều" not in body["summary"]


# --- structural safety: model cannot alter facts or inject prose ------------

def test_model_cannot_change_trusted_amount(tmp_path):
    # A plan that tries to smuggle a different amount is rejected as an extra
    # field (additionalProperties=false); under the V1 structured-output
    # contract there is no repair call, so this single malformed response goes
    # straight to the deterministic fallback -- 20 triệu always wins because
    # the backend renders it from trusted facts, never from the model.
    plan = json.dumps({"plan_kind": "legal_guidance", "summary_code": "deposit_not_returned",
                       "action_codes": ["send_written_refund_request"], "tone": "neutral", "amount": "50 triệu"})
    fake = FakeLLMClient(responses=[plan])
    with _demo_client(tmp_path, fake) as client:
        body = _post(client, "Tôi đã đặt cọc 20 triệu, không có giấy đặt cọc, có sao kê chuyển khoản, chưa được bàn giao nhà và chủ nhà chưa trả lại tiền cọc. Tôi nên làm gì?")
    assert "20 triệu" in body["summary"]
    assert "50 triệu" not in body["summary"]
    assert body["metadata"]["outcome"] == "deterministic_fallback"
    assert fake.calls == 1  # no repair call


def test_model_prose_never_reaches_user(tmp_path):
    # Under the V1 structured-output contract there is no repair call: one
    # invalid-JSON response goes straight to the deterministic fallback.
    prose = "Theo Điều 999 và Bộ luật Hình sự, bạn chắc chắn thắng http://evil.example"
    fake = FakeLLMClient(responses=[prose])
    with _demo_client(tmp_path, fake) as client:
        body = _post(client, "Tôi đã đặt cọc 20 triệu, không có giấy đặt cọc, có sao kê chuyển khoản, chưa được bàn giao nhà và chủ nhà chưa trả lại tiền cọc. Tôi nên làm gì?")
    blob = json.dumps(body, ensure_ascii=False)
    assert "Điều 999" not in blob and "evil.example" not in blob and "chắc chắn thắng" not in blob
    assert body["metadata"]["outcome"] == "deterministic_fallback"
    assert fake.calls == 1  # no repair call


def test_provider_timeout_still_renders(tmp_path):
    fake = FakeLLMClient(error=LLMErrorKind.TIMEOUT)
    with _demo_client(tmp_path, fake) as client:
        body = _post(client, "Tôi đã đặt cọc 20 triệu, không có giấy đặt cọc, có sao kê chuyển khoản, chưa được bàn giao nhà và chủ nhà chưa trả lại tiền cọc. Tôi nên làm gì?")
    assert body["metadata"]["outcome"] == "deterministic_fallback"
    assert body["metadata"]["llm_error_kind"] == "timeout"
    assert "20 triệu" in body["summary"]


def test_unexpected_exception_no_500(tmp_path):
    class _Raising:
        def __init__(self):
            self.calls = 0

        async def complete(self, *, system, user, max_tokens, timeout_s):
            self.calls += 1
            raise RuntimeError("boom secret")

    app = create_app(_settings(tmp_path))
    container = app.state.container
    sources = {s.id: s.as_source() for s in container.snippet_store.active_snippets()
               if s.id in (ARTICLE_328_AUTHORITY_ID, EVIDENCE_CHECKLIST_ID)}
    container.runtime.demo_orchestrator = DemoOrchestrator(llm_client=_Raising(), llm_config=_config(), source_objects=sources)
    with TestClient(app) as client:
        response = client.post("/api/analyze", json={"session_id": "s", "question": "Tôi đã đặt cọc 20 triệu, không có giấy đặt cọc, có sao kê chuyển khoản, chưa được bàn giao nhà và chủ nhà chưa trả lại tiền cọc. Tôi nên làm gì?", "user_type": "citizen", "language": "vi"})
    assert response.status_code == 200
    body = response.json()
    assert "boom" not in json.dumps(body)
    assert body["metadata"]["outcome"] == "deterministic_fallback"


# --- capability/source direct: no hard-coded legal reference ----------------

def test_capability_direct_no_hardcoded_article(tmp_path):
    fake = FakeLLMClient(responses=[_guidance_plan()])
    with _demo_client(tmp_path, fake) as client:
        body = _post(client, "Bạn có thể làm gì cho tôi?")
    assert "Điều 328" not in body["summary"] and "Bộ luật" not in body["summary"]
    assert fake.calls == 0


def test_source_lookup_uses_source_metadata(tmp_path):
    fake = FakeLLMClient(responses=[_guidance_plan()])
    with _demo_client(tmp_path, fake) as client:
        body = _post(client, "Bạn vừa dùng nguồn nào cho vụ tiền cọc?")
    assert "Điều 328" not in body["summary"]
    assert ARTICLE_328_AUTHORITY_ID in {s["id"] for s in body["sources"]}
    assert fake.calls == 0


# --- feature flag off preserves baseline ------------------------------------

def test_flag_disabled_preserves_baseline(tmp_path, monkeypatch):
    monkeypatch.delenv("VIETLAW_DEMO_VERTICAL_SLICE_ENABLED", raising=False)
    app = create_app(_settings(tmp_path))
    assert app.state.container.runtime.demo_orchestrator is None
    with TestClient(app) as client:
        body = _post(client, "Xin chào")
    assert "demo_route" not in body["metadata"]
