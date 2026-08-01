"""PHASE B1: exactly-once persistence, a strict context cap, and answer-token
precedence over social acknowledgment.

Every assertion here is about *observable counts* -- chat rows, message rows,
fact state, state_version and provider attempts -- because the defect under
correction was invisible in the API payload and only showed up in the persisted
transcript. The provider is always ``FakeLLMClient``; this module makes zero
live provider calls.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend_lite.app.config import Settings
from backend_lite.app.main import create_app
from backend_lite.app.services.conversation_context import (
    RECENT_CONTEXT_CHAR_BUDGET,
    RECENT_CONTEXT_MESSAGE_LIMIT,
    build_recent_context,
    detect_recent_matter,
    has_pending_clarification,
)
from backend_lite.app.services.demo_llm_client import FakeLLMClient
from backend_lite.app.services.fast_demo_orchestrator import (
    FastDemoConfig,
    FastDemoOrchestrator,
)
from backend_lite.app.services.fast_demo_routing import FastDemoRoute, classify_route
from backend_lite.app.services.fast_demo_source_pack import FastDemoSourcePack
from backend_lite.app.stores.fast_demo_request_receipts import (
    FastDemoRequestReceiptStore,
)
from backend_lite.app.stores.fast_demo_state_store import FastDemoStateStore

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------

def _settings(tmp_path: Path) -> Settings:
    return Settings(
        backend_mode="lite",
        chat_db_path=tmp_path / "chat.sqlite3",
        legal_snippets_path=REPO_ROOT / "data" / "legal_snippets.json",
        unsafe_patterns_path=REPO_ROOT / "data" / "unsafe_patterns.json",
        cors_origins="http://127.0.0.1:5173",
    )


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


DEPOSIT_PLAN = plan(
    summary="Đã ghi nhận 20 triệu.",
    fact_updates=[
        {"operation": "set", "slot": "deposit_amount", "value": 20000000,
         "evidence_quote": "20 triệu"},
    ],
)


def build(tmp_path: Path, responses: list[str]):
    settings = _settings(tmp_path)
    app = create_app(settings)
    container = app.state.container
    fake = FakeLLMClient(responses=list(responses))
    state_store = FastDemoStateStore(settings.chat_db_path)
    state_store.ensure_schema()
    container.runtime.fast_demo_orchestrator = FastDemoOrchestrator(
        store=state_store,
        source_pack=FastDemoSourcePack.from_snippets(container.snippet_store.active_snippets()),
        llm_client=fake,
        config=FastDemoConfig(
            enabled=True, model="claude-test-model", api_key="test-key",
            timeout_s=30.0, max_output_tokens=2048, temperature=0.0,
        ),
    )
    return app, fake, state_store, settings.chat_db_path


def db_counts(db_path: Path) -> tuple[int, int, int]:
    """(chats, user messages, assistant messages) actually persisted."""

    connection = sqlite3.connect(db_path)

    def count(sql: str) -> int:
        # The base tables are created lazily on first use, so "absent" and
        # "empty" are the same observation for these assertions.
        try:
            return connection.execute(sql).fetchone()[0]
        except sqlite3.OperationalError:
            return 0

    try:
        return (
            count("SELECT COUNT(*) FROM chats"),
            count("SELECT COUNT(*) FROM messages WHERE role = 'user'"),
            count("SELECT COUNT(*) FROM messages WHERE role = 'assistant'"),
        )
    finally:
        connection.close()


def deposit_of(state_store: FastDemoStateStore, chat_id: str):
    loaded = state_store.load(chat_id)
    amount = loaded.state.facts.deposit_amount
    return loaded.state_version, (amount.value if amount else None)


# ---------------------------------------------------------------------------
# Existing-chat completed replay
# ---------------------------------------------------------------------------

def test_existing_chat_replay_is_persistence_idempotent(tmp_path: Path) -> None:
    app, fake, state_store, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN, DEPOSIT_PLAN])
    with TestClient(app) as client:
        seed = client.post(
            "/api/analyze",
            json={"session_id": "s1", "question": "tôi thuê nhà và đã đặt cọc cho chủ nhà"},
        ).json()
        chat_id = seed["chat_id"]

        payload = {
            "session_id": "s1",
            "chat_id": chat_id,
            "question": "tôi đã đặt cọc 20 triệu, chủ nhà chưa trả lại tiền cọc",
            "client_request_id": "crid-existing",
        }
        first = client.post("/api/analyze", json=payload).json()
        before = db_counts(db)
        calls_before = fake.calls
        version_before, deposit_before = deposit_of(state_store, chat_id)

        second = client.post("/api/analyze", json=payload).json()
        after = db_counts(db)
        version_after, deposit_after = deposit_of(state_store, chat_id)

    # Same response and the same stable identities.
    assert second["chat_id"] == first["chat_id"]
    assert second["user_message_id"] == first["user_message_id"]
    assert second["assistant_message_id"] == first["assistant_message_id"]
    assert second["summary"] == first["summary"]

    # Zero deltas everywhere that matters.
    assert after[0] - before[0] == 0, "chat delta"
    assert after[1] - before[1] == 0, "user-message delta"
    assert after[2] - before[2] == 0, "assistant-message delta"
    assert version_after - version_before == 0, "state-version delta"
    assert deposit_after == deposit_before
    assert fake.calls - calls_before == 0, "replay must not call the provider"


# ---------------------------------------------------------------------------
# New-chat lost-response replay
# ---------------------------------------------------------------------------

def test_new_chat_lost_response_replay_resolves_to_original_chat(tmp_path: Path) -> None:
    """The client never learned the chat id, so the retry omits it again."""

    app, fake, state_store, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    payload = {
        "session_id": "s1",
        "question": "tôi đã đặt cọc 20 triệu cho chủ nhà",
        "client_request_id": "crid-newchat",
    }
    with TestClient(app) as client:
        first = client.post("/api/analyze", json=payload).json()   # response "lost"
        second = client.post("/api/analyze", json=payload).json()  # retry, still no chat_id
        chats, users, assistants = db_counts(db)

    assert second["chat_id"] == first["chat_id"], "retry must resolve to the original chat"
    assert second["user_message_id"] == first["user_message_id"]
    assert second["assistant_message_id"] == first["assistant_message_id"]

    assert chats == 1, "exactly one chat for one logical turn"
    assert users == 1, "exactly one user message"
    assert assistants == 1, "exactly one assistant message"
    assert fake.calls == 1, "exactly one provider attempt"

    version, deposit = deposit_of(state_store, first["chat_id"])
    assert version == 1, "the fact application happened exactly once"
    assert deposit == 20000000


# ---------------------------------------------------------------------------
# Fingerprint conflict
# ---------------------------------------------------------------------------

def test_reused_key_with_different_question_is_a_controlled_conflict(tmp_path: Path) -> None:
    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    with TestClient(app) as client:
        first = client.post(
            "/api/analyze",
            json={"session_id": "s1", "question": "tôi đã đặt cọc 20 triệu cho chủ nhà",
                  "client_request_id": "crid-conflict"},
        )
        assert first.status_code == 200
        before = db_counts(db)
        calls_before = fake.calls

        clash = client.post(
            "/api/analyze",
            json={"session_id": "s1", "question": "chủ nhà giữ giấy tờ nhà của tôi",
                  "client_request_id": "crid-conflict"},
        )
        after = db_counts(db)

    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "idempotency_conflict"
    assert fake.calls - calls_before == 0, "a conflict must not call the provider"
    assert after == before, "a conflict must not write anything"


def test_retry_may_name_the_chat_the_first_attempt_created(tmp_path: Path) -> None:
    """Learning the chat id from the response is not a conflict."""

    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    payload = {
        "session_id": "s1",
        "question": "tôi đã đặt cọc 20 triệu cho chủ nhà",
        "client_request_id": "crid-learned",
    }
    with TestClient(app) as client:
        first = client.post("/api/analyze", json=payload).json()
        before = db_counts(db)
        second = client.post(
            "/api/analyze", json={**payload, "chat_id": first["chat_id"]}
        )
        after = db_counts(db)

    assert second.status_code == 200
    assert second.json()["chat_id"] == first["chat_id"]
    assert after == before
    assert fake.calls == 1


# ---------------------------------------------------------------------------
# Cross-owner isolation
# ---------------------------------------------------------------------------

def test_same_request_id_across_owners_never_replays(tmp_path: Path) -> None:
    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    with TestClient(app) as client:
        a = client.post(
            "/api/analyze",
            json={"session_id": "owner-a", "question": "tôi đã đặt cọc 20 triệu cho chủ nhà",
                  "client_request_id": "shared-key"},
        ).json()
        b = client.post(
            "/api/analyze",
            json={"session_id": "owner-b", "question": "tôi đã đặt cọc 20 triệu cho chủ nhà",
                  "client_request_id": "shared-key"},
        ).json()
        chats, users, assistants = db_counts(db)

    assert a["chat_id"] != b["chat_id"], "owner B must not land in owner A's chat"
    assert a["assistant_message_id"] != b["assistant_message_id"]
    assert b["metadata"].get("fast_demo_replay") is not True
    assert (chats, users, assistants) == (2, 2, 2)
    assert fake.calls == 2, "two distinct owners are two real turns"


# ---------------------------------------------------------------------------
# Concurrent duplicate
# ---------------------------------------------------------------------------

def test_concurrent_duplicate_reserves_once(tmp_path: Path) -> None:
    """The second claimant of a live reservation is refused, not executed."""

    store = FastDemoRequestReceiptStore(tmp_path / "receipts.sqlite3")
    store.ensure_schema()

    first = store.reserve(
        session_id="s1", client_request_id="crid-race", request_fingerprint="f" * 64,
        user_message_id="msg_user_1", assistant_message_id="msg_asst_1",
    )
    second = store.reserve(
        session_id="s1", client_request_id="crid-race", request_fingerprint="f" * 64,
        user_message_id="msg_user_2", assistant_message_id="msg_asst_2",
    )

    assert first.reserved is True
    assert second.reserved is False, "only one caller may own the logical request"
    # The loser sees the winner's reserved identities, never its own.
    assert second.receipt.user_message_id == "msg_user_1"
    assert second.receipt.assistant_message_id == "msg_asst_1"


def test_pending_reservation_blocks_a_second_turn(tmp_path: Path) -> None:
    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN])
    receipts = app.state.container.runtime.request_receipts
    assert receipts is not None
    # Simulate an attempt that claimed the request and never finished.
    receipts.reserve(
        session_id="s1", client_request_id="crid-pending", request_fingerprint="x" * 64,
        user_message_id="msg_user_x", assistant_message_id="msg_asst_x",
    )
    before = db_counts(db)
    with TestClient(app) as client:
        response = client.post(
            "/api/analyze",
            json={"session_id": "s1", "question": "tôi đã đặt cọc 20 triệu cho chủ nhà",
                  "client_request_id": "crid-pending"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] in {"request_in_progress", "idempotency_conflict"}
    assert fake.calls == 0, "a pending claim must not spend a provider call"
    assert db_counts(db) == before, "a pending claim must not write anything"


def test_requests_without_a_client_request_id_keep_legacy_behaviour(tmp_path: Path) -> None:
    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    payload = {"session_id": "s1", "question": "tôi đã đặt cọc 20 triệu cho chủ nhà"}
    with TestClient(app) as client:
        a = client.post("/api/analyze", json=payload).json()
        b = client.post("/api/analyze", json=payload).json()
        chats, users, assistants = db_counts(db)

    # No key means no receipt: two separate turns, exactly as before.
    assert a["chat_id"] != b["chat_id"]
    assert (chats, users, assistants) == (2, 2, 2)
    assert fake.calls == 2


def test_receipt_schema_creation_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "receipts.sqlite3"
    for _ in range(3):
        FastDemoRequestReceiptStore(path).ensure_schema()
    store = FastDemoRequestReceiptStore(path)
    store.ensure_schema()
    assert store.find(session_id="s1", client_request_id="absent") is None


# ---------------------------------------------------------------------------
# Strict context cap
# ---------------------------------------------------------------------------

class _Msg:
    def __init__(self, role: str, text: str, content_json=None) -> None:
        self.role = role
        self.content_text = text
        self.content_json = content_json


def test_eight_short_messages_are_all_kept() -> None:
    history = [_Msg("user", f"tin nhắn {i}") for i in range(RECENT_CONTEXT_MESSAGE_LIMIT)]
    context = build_recent_context(history)
    assert context.messages_considered == RECENT_CONTEXT_MESSAGE_LIMIT
    assert len(context.messages) == RECENT_CONTEXT_MESSAGE_LIMIT
    assert context.truncated is False
    assert len(context.text) <= RECENT_CONTEXT_CHAR_BUDGET


def test_more_than_eight_messages_keeps_only_the_newest_eight() -> None:
    history = [_Msg("user", f"tin nhắn {i}") for i in range(20)]
    context = build_recent_context(history)
    assert context.messages_considered == RECENT_CONTEXT_MESSAGE_LIMIT
    assert "tin nhắn 19" in context.text
    assert "tin nhắn 11" not in context.text


def test_single_message_longer_than_the_budget_is_head_truncated() -> None:
    history = [_Msg("user", "x" * 9000)]
    context = build_recent_context(history)
    assert len(context.text) == RECENT_CONTEXT_CHAR_BUDGET
    assert context.truncated is True


def test_several_messages_crossing_the_budget_stay_within_it() -> None:
    history = [_Msg("user", "y" * 1500) for _ in range(6)]
    context = build_recent_context(history)
    assert len(context.text) <= RECENT_CONTEXT_CHAR_BUDGET


def test_exact_boundary_is_not_exceeded() -> None:
    history = [_Msg("user", "z" * RECENT_CONTEXT_CHAR_BUDGET)]
    context = build_recent_context(history)
    assert len(context.text) == RECENT_CONTEXT_CHAR_BUDGET
    assert context.truncated is False

    # One character more must still not exceed the cap.
    over = build_recent_context([_Msg("user", "z" * (RECENT_CONTEXT_CHAR_BUDGET + 1))])
    assert len(over.text) == RECENT_CONTEXT_CHAR_BUDGET


@pytest.mark.parametrize("size", [1, 999, 4000, 4001, 12000])
def test_context_never_exceeds_the_cap(size: int) -> None:
    history = [_Msg("user", "w" * size) for _ in range(RECENT_CONTEXT_MESSAGE_LIMIT)]
    assert len(build_recent_context(history).text) <= RECENT_CONTEXT_CHAR_BUDGET


def test_cue_beyond_the_cap_is_not_detected() -> None:
    """The exact case the independent review used as counter-evidence."""

    oversized = "x" * 4050 + " tôi đặt cọc mà chủ nhà không cho vào ở"
    assert len(oversized) > RECENT_CONTEXT_CHAR_BUDGET
    assert detect_recent_matter([_Msg("user", oversized)]).active is False

    # The same cue inside the budget is still detected.
    within = "x" * 100 + " tôi đặt cọc mà chủ nhà không cho vào ở"
    assert detect_recent_matter([_Msg("user", within)]).active is True


def test_context_reads_only_user_turns_and_stays_chronological() -> None:
    history = [
        _Msg("user", "câu một"),
        _Msg("assistant", "trả lời trợ lý"),
        _Msg("user", "câu hai"),
    ]
    context = build_recent_context(history)
    assert context.messages == ("câu một", "câu hai")
    assert "trả lời trợ lý" not in context.text


# ---------------------------------------------------------------------------
# Acknowledgment precedence
# ---------------------------------------------------------------------------

def _assistant_with_question(question: str) -> _Msg:
    class _Content:
        clarifying_questions = [question]

    return _Msg("assistant", None, content_json=_Content())


def test_pending_clarification_is_read_from_the_structured_field() -> None:
    history = [_assistant_with_question("Bạn đã được chủ nhà bàn giao nhà chưa?")]
    assert has_pending_clarification(history) is True

    # A user turn newer than the question means it was already answered.
    answered = [*history, _Msg("user", "chưa")]
    assert has_pending_clarification(answered) is False

    # An assistant turn with no structured question pending.
    class _NoQuestions:
        clarifying_questions: list[str] = []

    assert has_pending_clarification([_Msg("assistant", None, _NoQuestions())]) is False
    assert has_pending_clarification([]) is False


@pytest.mark.parametrize("answer", ["chưa", "Chưa.", "chưa có", "vẫn chưa"])
def test_chua_answers_a_pending_handover_question(answer: str) -> None:
    assert classify_route(
        answer, has_active_matter=False, pending_clarification=True
    ) is FastDemoRoute.LEGAL_CONVERSATION


@pytest.mark.parametrize("answer", ["không", "Không.", "không có"])
def test_khong_answers_a_pending_refund_question(answer: str) -> None:
    assert classify_route(
        answer, has_active_matter=False, pending_clarification=True
    ) is FastDemoRoute.LEGAL_CONVERSATION


@pytest.mark.parametrize("answer", ["có", "Có.", "có rồi", "rồi", "đúng rồi"])
def test_co_answers_a_pending_yes_no_question(answer: str) -> None:
    assert classify_route(
        answer, has_active_matter=False, pending_clarification=True
    ) is FastDemoRoute.LEGAL_CONVERSATION


@pytest.mark.parametrize("answer", ["được", "vâng", "dạ"])
def test_ambiguous_token_prefers_legal_when_a_matter_is_active(answer: str) -> None:
    assert classify_route(
        answer, has_active_matter=True
    ) is FastDemoRoute.LEGAL_CONVERSATION
    # With no context at all it stays a harmless acknowledgment.
    assert classify_route(
        answer, has_active_matter=False
    ) is FastDemoRoute.ACKNOWLEDGMENT


@pytest.mark.parametrize("text", ["cảm ơn", "cảm ơn bạn", "thanks", "thank you"])
def test_pure_gratitude_stays_social_even_with_a_pending_question(text: str) -> None:
    """Gratitude is never an answer to a yes/no question."""

    assert classify_route(
        text, has_active_matter=True, pending_clarification=True
    ) is FastDemoRoute.ACKNOWLEDGMENT


def test_ok_stays_an_acknowledgment() -> None:
    """`ok` is not a yes/no answer, so it is never promoted to a legal turn."""

    for pending in (False, True):
        for active in (False, True):
            assert classify_route(
                "ok", has_active_matter=active, pending_clarification=pending
            ) is FastDemoRoute.ACKNOWLEDGMENT


def test_empty_chat_ok_is_social() -> None:
    assert classify_route("ok", has_active_matter=False) is FastDemoRoute.ACKNOWLEDGMENT


def test_legal_sentence_containing_duoc_is_not_an_acknowledgment() -> None:
    for text in (
        "tôi có được lấy lại tiền cọc không?",
        "chủ nhà chưa cho tôi được vào ở",
        "tôi được chủ nhà trả cọc chưa?",
    ):
        assert classify_route(
            text, has_active_matter=True, pending_clarification=True
        ) is FastDemoRoute.LEGAL_CONVERSATION


def test_k_is_never_an_acknowledgment() -> None:
    """`k` abbreviates 'không' in Vietnamese chat; reading it as agreement would
    invert a refusal."""

    for pending in (False, True):
        for active in (False, True):
            assert classify_route(
                "k", has_active_matter=active, pending_clarification=pending
            ) is not FastDemoRoute.ACKNOWLEDGMENT


def test_safety_still_outranks_every_answer_token() -> None:
    assert classify_route(
        "tôi sẽ mang dao đến dọa chủ nhà",
        has_active_matter=True,
        pending_clarification=True,
    ) is FastDemoRoute.UNSAFE


def test_pending_clarification_answer_end_to_end(tmp_path: Path) -> None:
    """A `chưa` reply to a persisted clarifying question reaches legal processing."""

    asking = plan(
        response_mode="clarify",
        summary="Tôi cần làm rõ thêm.",
        clarifying_questions=["Bạn đã được chủ nhà bàn giao nhà chưa?"],
    )
    answered = plan(summary="Đã ghi nhận việc chưa bàn giao.")
    app, fake, _, _ = build(tmp_path, [asking, answered])
    with TestClient(app) as client:
        first = client.post(
            "/api/analyze",
            json={"session_id": "s1", "question": "tôi đã đặt cọc tiền thuê nhà cho chủ nhà"},
        ).json()
        assert first["clarifying_questions"], "the fixture must leave a question pending"

        reply = client.post(
            "/api/analyze",
            json={"session_id": "s1", "chat_id": first["chat_id"], "question": "Chưa."},
        ).json()

    assert reply["metadata"]["fast_demo_route"] == "legal_conversation"
    assert fake.calls == 2, "the answer is a real legal turn, not small talk"
