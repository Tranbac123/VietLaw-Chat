import json
from pathlib import Path

from backend_lite.app.services.deposit_case_facts import QUESTION_PRIORITY

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_ARTICLE_328_URL = "https://vbpl.vn/van-ban/chi-tiet/bo-luat-dan-su-so-91-2015-qh13--95942"

INITIAL_QUESTION = (
    "Tôi đặt cọc 20 triệu để thuê nhà, có giấy viết tay, nhưng chủ nhà không giao "
    "nhà và không trả cọc. Tôi nên làm gì?"
)
SIGNATURE_QUESTION = dict(QUESTION_PRIORITY)["signature"]
PAYMENT_PROOF_QUESTION = dict(QUESTION_PRIORITY)["payment_proof"]


def test_initial_response_does_not_ask_amount_or_written_agreement(client, analyze_payload):
    body = client.post("/api/analyze", json=analyze_payload(INITIAL_QUESTION)).json()
    joined_questions = " ".join(body["clarifying_questions"])
    assert "số tiền cọc" not in joined_questions.lower()
    assert "hợp đồng thuê nhà bằng văn bản" not in joined_questions.lower()
    assert len(body["clarifying_questions"]) <= 2


def test_initial_response_acknowledges_known_facts(client, analyze_payload):
    body = client.post("/api/analyze", json=analyze_payload(INITIAL_QUESTION)).json()
    summary = body["summary"]
    assert "20 triệu" in summary
    assert "giấy" in summary.lower()
    assert "bàn giao" in summary.lower()
    assert "hoàn lại" in summary.lower()
    assert body["next_steps"]
    assert "civil_deposit_001" in {source["id"] for source in body["sources"]}
    assert "chắc chắn" not in summary.lower()
    assert "hình sự" not in summary.lower()


def test_action_request_followup_gives_actions_and_does_not_repeat_questions(client, analyze_payload):
    first = client.post("/api/analyze", json=analyze_payload(INITIAL_QUESTION, session_id="s_action")).json()
    followup = client.post(
        "/api/analyze",
        json=analyze_payload("tôi nên làm gì?", session_id="s_action", chat_id=first["chat_id"]),
    ).json()
    assert followup["chat_id"] == first["chat_id"]
    assert followup["next_steps"]
    assert followup["checklist"] == []
    assert followup["response_kind"] == "legal"
    assert followup["metadata"]["used_current_chat_history"] is True
    assert followup["summary"] != first["summary"]
    assert set(followup["clarifying_questions"]) != set(first["clarifying_questions"])
    assert set(followup["clarifying_questions"]) & set(first["clarifying_questions"]) == set()


def test_risk_concern_followup_addresses_risk_without_repeating_questions(client, analyze_payload):
    first = client.post("/api/analyze", json=analyze_payload(INITIAL_QUESTION, session_id="s_risk")).json()
    client.post(
        "/api/analyze",
        json=analyze_payload("tôi nên làm gì?", session_id="s_risk", chat_id=first["chat_id"]),
    )
    risk = client.post(
        "/api/analyze",
        json=analyze_payload("tôi có sợ bị quỵt không?", session_id="s_risk", chat_id=first["chat_id"]),
    ).json()
    summary = risk["summary"].lower()
    assert "rủi ro" in summary
    assert "không thể kết luận" in summary
    assert "phụ thuộc" in summary
    assert risk["clarifying_questions"] == []
    assert risk["checklist"] == []
    assert risk["response_kind"] == "legal"


def test_fact_update_followup_removes_payment_and_signature_questions(client, analyze_payload):
    first = client.post("/api/analyze", json=analyze_payload(INITIAL_QUESTION, session_id="s_update")).json()
    assert SIGNATURE_QUESTION in first["clarifying_questions"]
    assert PAYMENT_PROOF_QUESTION in first["clarifying_questions"]

    updated = client.post(
        "/api/analyze",
        json=analyze_payload(
            "Tôi chuyển khoản và giấy có chữ ký.", session_id="s_update", chat_id=first["chat_id"]
        ),
    ).json()
    assert "cập nhật" in updated["summary"].lower()
    assert SIGNATURE_QUESTION not in updated["clarifying_questions"]
    assert PAYMENT_PROOF_QUESTION not in updated["clarifying_questions"]


def test_different_chats_do_not_share_deposit_facts(client, analyze_payload):
    chat_a = client.post(
        "/api/analyze", json=analyze_payload(INITIAL_QUESTION, session_id="s_isolation")
    ).json()
    chat_b = client.post(
        "/api/analyze",
        json=analyze_payload(
            "Chủ nhà giữ tiền cọc của tôi và không chịu trả lại.", session_id="s_isolation"
        ),
    ).json()
    assert chat_b["chat_id"] != chat_a["chat_id"]

    followup_b = client.post(
        "/api/analyze",
        json=analyze_payload("tôi nên làm gì?", session_id="s_isolation", chat_id=chat_b["chat_id"]),
    ).json()
    assert "20 triệu" not in followup_b["summary"]


def test_reload_preserves_bounded_case_context_for_next_turn(client, analyze_payload):
    first = client.post(
        "/api/analyze", json=analyze_payload(INITIAL_QUESTION, session_id="s_reload")
    ).json()

    detail = client.get(
        f"/api/chats/{first['chat_id']}", params={"session_id": "s_reload"}
    ).json()
    assert "20 triệu" in detail["messages"][-1]["content_json"]["summary"]

    followup = client.post(
        "/api/analyze",
        json=analyze_payload("tôi nên làm gì?", session_id="s_reload", chat_id=first["chat_id"]),
    ).json()
    assert followup["chat_id"] == first["chat_id"]
    joined_questions = " ".join(followup["clarifying_questions"]).lower()
    assert "số tiền cọc" not in joined_questions
    assert "hợp đồng thuê nhà bằng văn bản" not in joined_questions


def test_article_328_source_url_is_canonical(client, analyze_payload):
    raw = json.loads((REPO_ROOT / "data" / "legal_snippets.json").read_text(encoding="utf-8"))
    record = next(item for item in raw if item["id"] == "civil_deposit_001")
    assert record["source_url"] == CANONICAL_ARTICLE_328_URL

    body = client.post("/api/analyze", json=analyze_payload(INITIAL_QUESTION)).json()
    deposit_source = next(source for source in body["sources"] if source["id"] == "civil_deposit_001")
    assert deposit_source["url"] == CANONICAL_ARTICLE_328_URL
