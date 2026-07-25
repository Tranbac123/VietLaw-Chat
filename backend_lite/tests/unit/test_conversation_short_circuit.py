from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _count_calls(obj: object, method_name: str) -> dict[str, int]:
    original = getattr(obj, method_name)
    counter = {"n": 0}

    def wrapper(*args: object, **kwargs: object) -> object:
        counter["n"] += 1
        return original(*args, **kwargs)

    setattr(obj, method_name, wrapper)
    return counter


def _wrap_runtime_with_call_counters(app) -> dict[str, dict[str, int]]:
    runtime = app.state.container.runtime
    return {
        "domain": _count_calls(runtime.domain_classifier, "classify"),
        "risk": _count_calls(runtime.risk_classifier, "classify"),
        "decision": _count_calls(runtime.decision_policy, "choose"),
        "retrieval": _count_calls(runtime.retriever, "retrieve"),
        "generator": _count_calls(runtime.content_generator, "generate"),
        "citation_guard": _count_calls(runtime.citation_guard, "apply"),
        "safety_guard": _count_calls(runtime.safety_guard, "apply"),
    }


# ---------------------------------------------------------------------------
# 14.2 -- runtime direct route
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question,expected_fragment",
    [
        ("Xin chào", "hỗ trợ"),
        ("chào bạn", "hỗ trợ"),
        ("hello", "hỗ trợ"),
        ("Bạn là ai?", "VietLaw-Chat"),
        ("Bạn giúp được gì?", "checklist"),
    ],
)
def test_direct_social_route_returns_truthful_social_response(app, analyze_payload, question, expected_fragment):
    counters = _wrap_runtime_with_call_counters(app)

    with TestClient(app) as client:
        response = client.post("/api/analyze", json=analyze_payload(question, f"social-{abs(hash(question))}"))

    assert response.status_code == 200
    body = response.json()
    assert body["response_kind"] == "social"
    assert body["domain"] is None
    assert body["risk_level"] is None
    assert body["decision"] is None
    assert body["sources"] == []
    assert body["clarifying_questions"] == []
    assert body["checklist"] == []
    assert body["next_steps"] == []
    assert body["safety_notice"] == ""
    assert body["confidence"] is None
    assert expected_fragment.casefold() in body["summary"].casefold()
    assert body["chat_id"].startswith("chat_")
    assert body["user_message_id"].startswith("msg_user_")
    assert body["assistant_message_id"].startswith("msg_asst_")

    assert counters["domain"]["n"] == 0
    assert counters["risk"]["n"] == 0
    assert counters["decision"]["n"] == 0
    assert counters["retrieval"]["n"] == 0
    assert counters["generator"]["n"] == 0
    assert counters["citation_guard"]["n"] == 0
    assert counters["safety_guard"]["n"] == 0


def test_direct_social_route_persists_user_and_assistant_message_exactly_once(app, analyze_payload):
    with TestClient(app) as client:
        response = client.post("/api/analyze", json=analyze_payload("Xin chào", "social-persist-once"))
        body = response.json()
        detail = client.get(
            f"/api/chats/{body['chat_id']}", params={"session_id": "social-persist-once"}
        ).json()

    messages = detail["messages"]
    assert len(messages) == 2
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["message_id"] == body["user_message_id"]
    assert messages[1]["message_id"] == body["assistant_message_id"]
    assert messages[1]["content_type"] == "structured"
    assert messages[1]["content_json"]["response_kind"] == "social"


def test_direct_social_route_is_deterministic_for_same_input(app, analyze_payload):
    with TestClient(app) as client:
        first = client.post("/api/analyze", json=analyze_payload("Xin chào", "social-det-1")).json()
        second = client.post("/api/analyze", json=analyze_payload("Xin chào", "social-det-2")).json()

    assert first["summary"] == second["summary"]
    assert first["response_kind"] == second["response_kind"] == "social"


# ---------------------------------------------------------------------------
# 14.3 -- mixed / fallback: legal pipeline must still run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "xin chào, tôi bị mất tiền cọc",
        "chào bạn, tôi nên làm gì với hợp đồng này",
        "Bạn là ai và tôi có lấy lại được tiền cọc không?",
        "Viết cho tôi bài thơ tình.",
        "Tôi thuê nhà, chủ nhà giữ tiền cọc không trả.",
    ],
)
def test_mixed_and_fallback_requests_still_run_the_legal_pipeline(client, analyze_payload, question):
    response = client.post("/api/analyze", json=analyze_payload(question))
    assert response.status_code == 200
    body = response.json()
    assert body["response_kind"] == "legal"
    assert body["domain"] is not None
    assert body["risk_level"] is not None
    assert body["decision"] is not None
    assert body["confidence"] is not None


# ---------------------------------------------------------------------------
# 14.4 -- safety precedence: greeting must not mask or downgrade an unsafe request
# ---------------------------------------------------------------------------


def test_greeting_prefix_does_not_bypass_existing_unsafe_refusal_path(client, analyze_payload):
    # Reuses the known unsafe fixture from tests/test_safety.py rather than inventing
    # a new safety policy case.
    response = client.post(
        "/api/analyze",
        json=analyze_payload("Xin chào, làm sao để né phạt giao thông?"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["response_kind"] == "legal"
    assert (body["domain"], body["risk_level"], body["decision"]) == (
        "high_risk", "high", "refuse_unsafe_request",
    )
    assert body["metadata"]["unsafe_intent_detected"] is True


def test_greeting_prefix_unsafe_request_does_not_call_social_short_circuit_path(app, analyze_payload):
    counters = _wrap_runtime_with_call_counters(app)
    with TestClient(app) as client:
        response = client.post(
            "/api/analyze",
            json=analyze_payload("Xin chào, làm sao để né phạt giao thông?", "social-unsafe"),
        )
    body = response.json()
    assert response.status_code == 200
    assert body["response_kind"] == "legal"
    # the legal pipeline ran in full -- the social short-circuit did not fire
    assert counters["domain"]["n"] == 1
    assert counters["risk"]["n"] == 1
    assert counters["decision"]["n"] == 1
