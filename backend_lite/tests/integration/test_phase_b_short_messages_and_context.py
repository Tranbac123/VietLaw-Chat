"""PHASE B: short-message acceptance and bounded recent-conversation context.

Covers required Phase B cases 1-30. The provider is always a deterministic
stub, so this module makes zero live provider calls.

Two independent defects are covered here:

* short social messages ("ok", "hi", "ừ") were rejected as invalid data before
  routing ever saw them -- a length floor, not a routing problem;
* a vague follow-up ("tôi nên làm gì?") after an intervening greeting fell back
  to a scope refusal, because "is there an active matter?" consulted only the
  extracted fact slots and ignored the conversation the user had just had.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend_lite.app.config import Settings
from backend_lite.app.main import create_app
from backend_lite.app.services.conversation_context import (
    RECENT_CONTEXT_MESSAGE_LIMIT,
    TOPIC_HANDOVER_REFUSED,
    detect_recent_matter,
)
from backend_lite.app.services.demo_llm_client import FakeLLMClient
from backend_lite.app.services.fast_demo_orchestrator import (
    FastDemoConfig,
    FastDemoOrchestrator,
)
from backend_lite.app.services.fast_demo_routing import FastDemoRoute, classify_route
from backend_lite.app.services.fast_demo_source_pack import FastDemoSourcePack
from backend_lite.app.stores.fast_demo_state_store import FastDemoStateStore

REPO_ROOT = Path(__file__).resolve().parents[3]

# Phrases that would prove the assistant lost the thread.
_AMNESIA_MARKERS = (
    "tôi tập trung hỗ trợ các tình huống",
    "chưa có thông tin",
    "không có thông tin",
    "bạn mô tả giúp tôi sự việc của mình",
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        backend_mode="lite",
        chat_db_path=tmp_path / "chat.sqlite3",
        legal_snippets_path=REPO_ROOT / "data" / "legal_snippets.json",
        unsafe_patterns_path=REPO_ROOT / "data" / "unsafe_patterns.json",
        cors_origins="http://127.0.0.1:5173",
    )


def _config(**overrides) -> FastDemoConfig:
    base = {
        "enabled": True,
        "model": "claude-test-model",
        "api_key": "test-key",
        "timeout_s": 30.0,
        "max_output_tokens": 2048,
        "temperature": 0.0,
    }
    base.update(overrides)
    return FastDemoConfig(**base)


def plan(**overrides) -> str:
    payload = {
        "response_kind": "legal",
        "response_mode": "acknowledge",
        "summary": "Đã ghi nhận thông tin của bạn.",
        "analysis": None,
        "clarifying_questions": [],
        "checklist": [],
        "next_steps": [],
        "draft": None,
        "known_facts_summary": [],
        "uncertainty_notice": None,
        "fact_updates": [],
        "selected_source_ids": [],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def build(tmp_path: Path, responses: list[str], **config_overrides):
    app = create_app(_settings(tmp_path))
    container = app.state.container
    fake = FakeLLMClient(responses=list(responses))
    store = FastDemoStateStore(_settings(tmp_path).chat_db_path)
    store.ensure_schema()
    container.runtime.fast_demo_orchestrator = FastDemoOrchestrator(
        store=store,
        source_pack=FastDemoSourcePack.from_snippets(container.snippet_store.active_snippets()),
        llm_client=fake,
        config=_config(**config_overrides),
    )
    return app, fake, store


def post(client: TestClient, question: str, *, chat_id=None, session="s1"):
    payload = {"session_id": session, "question": question}
    if chat_id:
        payload["chat_id"] = chat_id
    return client.post("/api/analyze", json=payload)


def ask(client: TestClient, question: str, *, chat_id=None, session="s1"):
    response = post(client, question, chat_id=chat_id, session=session)
    assert response.status_code == 200, response.text
    return response.json()


def _blob(body: dict) -> str:
    """All user-visible prose of a response, lowercased."""

    parts = [
        body.get("summary") or "",
        body.get("analysis") or "",
        *(body.get("clarifying_questions") or []),
        *(body.get("checklist") or []),
        *(body.get("next_steps") or []),
        *(body.get("known_facts") or []),
    ]
    return " ".join(parts).lower()


# ---------------------------------------------------------------------------
# 1-6: request validation for short messages
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["ok", "hello", "hi", "ừ", "okay", "cảm ơn", "thanks", "được"])
def test_short_messages_are_accepted(tmp_path: Path, text: str) -> None:
    """1, 2, 6: no short valid message returns an invalid-data error."""

    app, fake, _ = build(tmp_path, [])
    with TestClient(app) as client:
        response = post(client, text)
    assert response.status_code == 200, response.text
    assert fake.calls == 0


def test_surrounding_whitespace_is_normalized(tmp_path: Path) -> None:
    """3: '  ok  ' is trimmed and accepted, and stored without the padding."""

    app, _, _ = build(tmp_path, [])
    with TestClient(app) as client:
        response = post(client, "  ok  ")
        assert response.status_code == 200, response.text
        chat_id = response.json()["chat_id"]
        messages = client.get(f"/api/chats/{chat_id}", params={"session_id": "s1"}).json()["messages"]
    assert [m["content_text"] for m in messages if m["role"] == "user"] == ["ok"]


@pytest.mark.parametrize("text", ["", " ", "   ", "\n\t  "])
def test_whitespace_only_is_still_rejected(tmp_path: Path, text: str) -> None:
    """4: emptiness remains invalid."""

    app, _, _ = build(tmp_path, [])
    with TestClient(app) as client:
        response = post(client, text)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_maximum_length_validation_is_unchanged(tmp_path: Path) -> None:
    """5: the 3000-character ceiling still refuses oversized input."""

    app, _, _ = build(tmp_path, [])
    with TestClient(app) as client:
        assert post(client, "a" * 3000).status_code == 200
        over = post(client, "a" * 3001)
    assert over.status_code == 400
    assert over.json()["error"]["code"] == "invalid_request"


# ---------------------------------------------------------------------------
# 7-12: social routing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["hello", "hi", "hey", "Hello!", "HI", "good morning"])
def test_english_greeting_returns_direct_greeting(tmp_path: Path, text: str) -> None:
    """7: English greeting returns a direct safe greeting."""

    app, fake, _ = build(tmp_path, [])
    with TestClient(app) as client:
        body = ask(client, text)
    assert body["metadata"]["fast_demo_route"] == "social"
    assert body["summary"].startswith("Xin chào")
    assert fake.calls == 0


@pytest.mark.parametrize("text", ["xin chào", "chào", "chào bạn", "Xin chào!", "xin chao"])
def test_vietnamese_greeting_remains_supported(tmp_path: Path, text: str) -> None:
    """8: no Vietnamese greeting regressed."""

    app, _, _ = build(tmp_path, [])
    with TestClient(app) as client:
        body = ask(client, text)
    assert body["metadata"]["fast_demo_route"] == "social"
    assert body["summary"].startswith("Xin chào")


@pytest.mark.parametrize(
    "text",
    ["ok", "okay", "được", "đồng ý", "vâng", "ừ", "cảm ơn", "thanks", "thank you", "oke", "dạ"],
)
def test_acknowledgment_returns_concise_response(tmp_path: Path, text: str) -> None:
    """9: acknowledgments get a short reply, not the scope blurb."""

    app, _, _ = build(tmp_path, [])
    with TestClient(app) as client:
        body = ask(client, text)
    assert body["metadata"]["fast_demo_route"] == "social"
    assert body["summary"].startswith("Vâng.")
    assert len(body["summary"]) < 220
    assert body["clarifying_questions"] == []
    assert body["next_steps"] == []


@pytest.mark.parametrize("text", ["xin chào", "hello", "ok", "cảm ơn", "bạn là ai"])
def test_social_turns_spend_no_provider_call(tmp_path: Path, text: str) -> None:
    """10: deterministic social response uses zero provider calls."""

    app, fake, _ = build(tmp_path, [])
    with TestClient(app) as client:
        ask(client, text)
    assert fake.calls == 0


def test_social_turn_mutates_no_rental_state(tmp_path: Path) -> None:
    """11 and 12: a greeting/acknowledgment changes neither facts nor version."""

    app, _, store = build(tmp_path, [plan(summary="Ghi nhận.")])
    with TestClient(app) as client:
        first = ask(client, "tôi đặt cọc 20 triệu cho chủ nhà")
        chat_id = first["chat_id"]
        before = store.load(chat_id)
        for text in ("xin chào", "ok", "cảm ơn", "chào bạn"):
            ask(client, text, chat_id=chat_id)
        after = store.load(chat_id)

    assert after.state_version == before.state_version
    assert after.state.model_dump() == before.state.model_dump()


# ---------------------------------------------------------------------------
# 13-19: the owner's exact conversation
# ---------------------------------------------------------------------------

OWNER_SEQUENCE = (
    "xin chào",
    "tôi muốn thuê nhà, tôi cần lưu ý những gì?",
    "tôi đặt cọc mà chủ nhà không cho vào ở thì phải làm sao?",
    "chào bạn",
    "tôi nên làm gì?",
)


def _run_owner_sequence(client: TestClient) -> list[dict]:
    bodies: list[dict] = []
    chat_id = None
    for text in OWNER_SEQUENCE:
        body = ask(client, text, chat_id=chat_id)
        chat_id = body["chat_id"]
        bodies.append(body)
    return bodies


def test_owner_sequence_final_turn_uses_recent_context(tmp_path: Path) -> None:
    """13-18: the rental issue survives an intervening greeting."""

    app, _, _ = build(tmp_path, [plan() for _ in OWNER_SEQUENCE], enabled=False)
    with TestClient(app) as client:
        bodies = _run_owner_sequence(client)

    issue_turn, greeting_turn, final = bodies[2], bodies[3], bodies[4]

    # 13: the issue turn is handled as a legal conversation.
    assert issue_turn["metadata"]["fast_demo_route"] == "legal_conversation"
    # 14: the intervening greeting is still answered as a greeting...
    assert greeting_turn["metadata"]["fast_demo_route"] == "social"
    # ...and 15/16: the vague follow-up continues the legal matter.
    assert final["metadata"]["fast_demo_route"] == "legal_conversation"
    assert final["metadata"]["recent_matter_active"] is True
    assert final["metadata"]["recent_matter_topic"] == TOPIC_HANDOVER_REFUSED
    assert final["metadata"]["used_current_chat_history"] is True

    # 16: the answer addresses the landlord-refusal situation.
    assert "bàn giao" in final["summary"].lower()
    assert final["next_steps"], "a contextual follow-up must offer next steps"

    # 17: it never claims to have no prior information.
    blob = _blob(final)
    for marker in _AMNESIA_MARKERS:
        assert marker not in blob, f"amnesia marker present: {marker!r}"

    # 18: it does not ask the user to restate the already-known issue.
    assert "mô tả lại" not in blob
    assert "nhắc lại" not in blob


def test_owner_sequence_invents_no_unsupplied_facts(tmp_path: Path) -> None:
    """19: no deposit amount, evidence, written agreement or landlord reason."""

    app, _, _ = build(tmp_path, [plan() for _ in OWNER_SEQUENCE], enabled=False)
    with TestClient(app) as client:
        final = _run_owner_sequence(client)[4]

    # Nothing was ever extracted, so nothing may be asserted as known. This is
    # the authoritative surface: `known_facts` is the only place the backend
    # states what it believes about the user's situation.
    assert final["known_facts"] == []

    # No amount may appear anywhere -- a figure is never advice, only a claim.
    blob = _blob(final)
    assert "triệu" not in blob
    assert not any(ch.isdigit() for ch in blob), "a numeric quantity was invented"

    # The summary must not assert possession of evidence or an agreement.
    # (Advising the user to *keep* records is legitimate and lives in
    # next_steps; claiming they already have them is not.)
    summary = (final["summary"] or "").lower()
    for claimed in ("bạn có sao kê", "bạn đã có", "có chứng từ", "có giấy đặt cọc", "chủ nhà nói"):
        assert claimed not in summary, f"invented fact asserted: {claimed!r}"


# ---------------------------------------------------------------------------
# 20-22: empty context
# ---------------------------------------------------------------------------

def test_vague_followup_in_empty_chat_asks_for_context(tmp_path: Path) -> None:
    """20-22: clarification, not an invented rental scenario."""

    app, fake, _ = build(tmp_path, [])
    with TestClient(app) as client:
        body = ask(client, "tôi nên làm gì?")

    assert body["metadata"]["fast_demo_route"] == "scope"
    assert body["metadata"]["recent_matter_active"] is False
    assert fake.calls == 0
    blob = _blob(body)
    # It asks the user to describe the situation...
    assert "mô tả" in blob
    # ...and invents no specifics.
    for invented in ("20 triệu", "sao kê", "chưa bàn giao", "chủ nhà chưa hoàn"):
        assert invented not in blob


# ---------------------------------------------------------------------------
# 23-27: authority and isolation
# ---------------------------------------------------------------------------

CORRECTION_FIRST = plan(
    summary="Đã ghi nhận 20 triệu.",
    fact_updates=[
        {"operation": "set", "slot": "deposit_amount", "value": 20000000,
         "evidence_quote": "20 triệu"},
    ],
)
CORRECTION_SECOND = plan(
    summary="Đã cập nhật thành 15 triệu.",
    fact_updates=[
        {"operation": "set", "slot": "deposit_amount", "value": 15000000,
         "evidence_quote": "15 triệu"},
    ],
)


def test_current_message_correction_overrides_history(tmp_path: Path) -> None:
    """23 and 24: a correction wins, and history never restores the old value."""

    app, _, store = build(tmp_path, [CORRECTION_FIRST, CORRECTION_SECOND, plan()])
    with TestClient(app) as client:
        first = ask(client, "tôi đã đặt cọc 20 triệu cho chủ nhà")
        chat_id = first["chat_id"]
        ask(client, "không phải, tiền cọc là 15 triệu", chat_id=chat_id)
        # A later contextual turn must not resurrect 20 triệu.
        final = ask(client, "tôi nên làm gì?", chat_id=chat_id)
        state = store.load(chat_id).state

    assert state.facts.deposit_amount.value == 15000000
    assert "20.000.000" not in " ".join(final.get("known_facts") or [])


def test_assistant_prose_cannot_create_user_facts(tmp_path: Path) -> None:
    """25: the assistant's own words are never authoritative context."""

    # The model asserts a deposit in prose while supplying no fact_updates.
    chatty = plan(summary="Bạn đã đặt cọc 50 triệu và chủ nhà chưa hoàn trả tiền cọc.")
    app, _, store = build(tmp_path, [chatty, plan()])
    with TestClient(app) as client:
        first = ask(client, "tôi muốn hỏi về tiền cọc thuê nhà")
        chat_id = first["chat_id"]
        state = store.load(chat_id).state
        assert state.facts.deposit_amount is None

        follow = ask(client, "tôi nên làm gì?", chat_id=chat_id)

    assert store.load(chat_id).state.facts.deposit_amount is None
    assert "50" not in " ".join(follow.get("known_facts") or [])


def test_context_never_crosses_chats(tmp_path: Path) -> None:
    """26: chat A's matter is invisible to chat B."""

    app, _, _ = build(tmp_path, [plan(), plan()], enabled=False)
    with TestClient(app) as client:
        a = ask(client, "tôi đặt cọc mà chủ nhà không cho vào ở thì phải làm sao?")
        assert a["metadata"]["recent_matter_active"] is True

        # A brand-new chat in the same session.
        b = ask(client, "tôi nên làm gì?")

    assert b["chat_id"] != a["chat_id"]
    assert b["metadata"]["fast_demo_route"] == "scope"
    assert b["metadata"]["recent_matter_active"] is False


def test_bounded_window_excludes_older_messages() -> None:
    """27: a matter outside the declared limit is not considered."""

    class _Msg:
        def __init__(self, role: str, text: str) -> None:
            self.role = role
            self.content_text = text
            self.content_json = None

    matter = _Msg("user", "tôi đặt cọc mà chủ nhà không cho vào ở")
    filler = [_Msg("user", "vâng") for _ in range(RECENT_CONTEXT_MESSAGE_LIMIT)]

    # Inside the window: detected.
    assert detect_recent_matter([matter, *filler[:-1]]).active is True
    # Pushed out of the window by newer traffic: not detected.
    assert detect_recent_matter([matter, *filler]).active is False


def test_assistant_history_alone_does_not_activate_context() -> None:
    """25 (unit): only user turns can establish that a matter exists."""

    class _Msg:
        def __init__(self, role: str, text: str) -> None:
            self.role = role
            self.content_text = text
            self.content_json = None

    assistant_only = [_Msg("assistant", "Bạn đã đặt cọc và chủ nhà chưa hoàn trả tiền cọc.")]
    assert detect_recent_matter(assistant_only).active is False


# ---------------------------------------------------------------------------
# 28-30: regression guards
# ---------------------------------------------------------------------------

def test_acknowledgment_with_real_question_stays_on_legal_route() -> None:
    """28: full-message anchoring — "ok" plus a question is not an ack."""

    assert classify_route("ok", has_active_matter=True) is FastDemoRoute.ACKNOWLEDGMENT
    assert (
        classify_route("ok vậy tôi nên làm gì?", has_active_matter=True)
        is FastDemoRoute.LEGAL_CONVERSATION
    )
    assert (
        classify_route("cảm ơn, tôi đã đặt cọc 20 triệu", has_active_matter=False)
        is FastDemoRoute.LEGAL_CONVERSATION
    )


def test_idempotent_replay_still_returns_stored_response(tmp_path: Path) -> None:
    """29: replay behaviour is unchanged and spends no extra call."""

    app, fake, _ = build(tmp_path, [plan(summary="Ghi nhận một lần.")])
    with TestClient(app) as client:
        payload = {
            "session_id": "s1",
            "question": "tôi đã đặt cọc 20 triệu cho chủ nhà",
            "client_request_id": "crid-1",
        }
        first = client.post("/api/analyze", json=payload).json()
        payload["chat_id"] = first["chat_id"]
        second = client.post("/api/analyze", json=payload).json()

    assert fake.calls == 1
    assert second["summary"] == first["summary"]
    assert second["metadata"]["fast_demo_replay"] is True


def test_context_routing_adds_no_extra_provider_call(tmp_path: Path) -> None:
    """30: continuing a matter still costs at most one call per turn."""

    app, fake, _ = build(tmp_path, [plan(), plan(), plan()])
    with TestClient(app) as client:
        first = ask(client, "tôi đặt cọc mà chủ nhà không cho vào ở thì phải làm sao?")
        chat_id = first["chat_id"]
        assert fake.calls == 1
        ask(client, "chào bạn", chat_id=chat_id)
        assert fake.calls == 1, "a greeting must not spend a call"
        ask(client, "tôi nên làm gì?", chat_id=chat_id)
        assert fake.calls == 2, "the contextual follow-up costs exactly one call"
