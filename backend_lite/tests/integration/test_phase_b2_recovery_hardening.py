"""PHASE B2: keyed requests fail closed, new-chat start is atomic, and a
pending clarification survives social interruption.

Fault injection is deterministic and the provider is always ``FakeLLMClient``;
this module makes zero live provider calls. Assertions are on observable row
counts, provider counters and persisted state -- the three defects under
correction were all invisible in the response payload.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend_lite.app.config import Settings
from backend_lite.app.contracts.fast_demo import PendingClarification
from backend_lite.app.main import create_app
from backend_lite.app.services.demo_llm_client import FakeLLMClient
from backend_lite.app.services.fast_demo_orchestrator import (
    FastDemoConfig,
    FastDemoOrchestrator,
)
from backend_lite.app.services.fast_demo_source_pack import FastDemoSourcePack
from backend_lite.app.stores.fast_demo_request_receipts import (
    FastDemoRequestReceiptStore,
    RequestReceiptStoreError,
)
from backend_lite.app.stores.fast_demo_state_store import FastDemoStateStore
from backend_lite.app.stores.sqlite_chat_store import (
    ChatStartNotCommittedError,
    SQLiteChatStore,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


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
ASK_HANDOVER = plan(
    response_mode="clarify",
    summary="Tôi cần làm rõ thêm.",
    clarifying_questions=["Bạn đã được chủ nhà bàn giao nhà chưa?"],
)
ASK_REFUND = plan(
    response_mode="clarify",
    summary="Tôi cần làm rõ thêm.",
    clarifying_questions=["Chủ nhà có đồng ý hoàn trả tiền cọc không?"],
)
def answer_accepting(slot: str, evidence: str) -> str:
    """An answering turn whose proposed update is verifiable in the message.

    Phase B3 made acceptance the condition for closing a pending question, so a
    fixture that answers must actually apply the expected slot -- a bare token
    with no accepted update deliberately no longer resolves anything.
    """

    return plan(
        summary="Đã ghi nhận câu trả lời của bạn.",
        fact_updates=[
            {"operation": "negate", "slot": slot, "value": None,
             "evidence_quote": evidence},
        ],
    )


ANSWER_HANDOVER = answer_accepting("property_handover_status", "Chưa")
ANSWER_REFUND = answer_accepting("deposit_returned_status", "Không")

KEYED_QUESTION = "tôi đã đặt cọc 20 triệu cho chủ nhà"
SEED_QUESTION = "tôi đã đặt cọc tiền thuê nhà cho chủ nhà"


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
    connection = sqlite3.connect(db_path)

    def count(sql: str) -> int:
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


def pending_id(state_store: FastDemoStateStore, chat_id: str) -> str | None:
    record = state_store.load(chat_id).state.pending_clarification
    return None if record is None else record.question_id


# ---------------------------------------------------------------------------
# Keyed requests fail closed
# ---------------------------------------------------------------------------

KEYED = {
    "session_id": "s1",
    "question": KEYED_QUESTION,
    "client_request_id": "crid-keyed",
}


def test_keyed_request_fails_closed_when_receipt_store_is_absent(tmp_path: Path) -> None:
    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    app.state.container.runtime.request_receipts = None
    with TestClient(app) as client:
        first = client.post("/api/analyze", json=KEYED)
        second = client.post("/api/analyze", json=KEYED)

    for response in (first, second):
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "idempotency_unavailable"
        # No raw SQLite / stack detail leaks to the user.
        assert "sqlite" not in response.text.lower()
        assert "Traceback" not in response.text

    assert fake.calls == 0
    assert db_counts(db) == (0, 0, 0)


def test_keyed_request_fails_closed_when_reservation_raises(tmp_path: Path) -> None:
    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    receipts = app.state.container.runtime.request_receipts
    with patch.object(
        type(receipts), "reserve", side_effect=RequestReceiptStoreError("injected")
    ):
        with TestClient(app) as client:
            response = client.post("/api/analyze", json=KEYED)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "idempotency_unavailable"
    assert fake.calls == 0
    assert db_counts(db) == (0, 0, 0)


def test_keyed_request_fails_closed_when_schema_bootstrap_fails(tmp_path: Path) -> None:
    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN])
    receipts = app.state.container.runtime.request_receipts
    with patch.object(
        type(receipts), "ensure_schema", side_effect=RequestReceiptStoreError("injected")
    ):
        with TestClient(app) as client:
            response = client.post("/api/analyze", json=KEYED)

    assert response.status_code == 503
    assert fake.calls == 0
    assert db_counts(db) == (0, 0, 0)


def test_receipt_store_is_none_when_bootstrap_fails_at_startup(tmp_path: Path) -> None:
    """A store that cannot create its table must not block startup -- but the
    keyed path must then refuse rather than run unprotected."""

    from backend_lite.app import dependencies

    with patch.object(
        FastDemoRequestReceiptStore, "ensure_schema",
        side_effect=RequestReceiptStoreError("injected"),
    ):
        store = dependencies._build_request_receipts(_settings(tmp_path))
    assert store is None


def test_unkeyed_request_keeps_legacy_behaviour_without_receipts(tmp_path: Path) -> None:
    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    app.state.container.runtime.request_receipts = None
    payload = {"session_id": "s1", "question": KEYED_QUESTION}
    with TestClient(app) as client:
        first = client.post("/api/analyze", json=payload)
        second = client.post("/api/analyze", json=payload)

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["chat_id"] != second.json()["chat_id"]
    assert db_counts(db) == (2, 2, 2)
    assert fake.calls == 2


# ---------------------------------------------------------------------------
# Atomic new-chat start
# ---------------------------------------------------------------------------

class _FailingMessageInsertConnection:
    """Passes everything through except the first user-message INSERT."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def execute(self, sql, *args, **kwargs):
        if sql.strip().upper().startswith("INSERT INTO MESSAGES"):
            raise sqlite3.OperationalError("injected message insert failure")
        return self._connection.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._connection, name)


def test_fault_inside_atomic_start_rolls_back_both_rows(tmp_path: Path) -> None:
    """No orphan chat: the chat and its first user message land together."""

    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    real_connect = SQLiteChatStore._connect
    armed = {"on": True}

    def connect(self):
        connection = real_connect(self)
        return _FailingMessageInsertConnection(connection) if armed["on"] else connection

    with TestClient(app) as client:
        with patch.object(SQLiteChatStore, "_connect", connect):
            # The store classifies this as a proven rollback, which is the only
            # outcome that authorises releasing the reservation.
            with pytest.raises(ChatStartNotCommittedError):
                client.post("/api/analyze", json=KEYED)
        armed["on"] = False
        after_failure = db_counts(db)

        retry = client.post("/api/analyze", json=KEYED)
        after_retry = db_counts(db)

    assert after_failure == (0, 0, 0), "rollback must leave neither chat nor message"
    assert fake.calls == 0 or fake.calls == 1

    # A later explicit retry completes the logical turn exactly once.
    assert retry.status_code == 200
    assert after_retry == (1, 1, 1)
    assert fake.calls == 1


def test_fault_before_the_chat_transaction_leaves_nothing(tmp_path: Path) -> None:
    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])

    def boom(self, **kwargs):
        # Nothing was opened, let alone written: a proven non-commit.
        raise ChatStartNotCommittedError("injected before chat creation")

    with TestClient(app) as client:
        with patch.object(SQLiteChatStore, "create_chat_with_first_user_message", boom):
            with pytest.raises(ChatStartNotCommittedError):
                client.post("/api/analyze", json=KEYED)
        after_failure = db_counts(db)
        retry = client.post("/api/analyze", json=KEYED)
        after_retry = db_counts(db)

    assert after_failure == (0, 0, 0)
    assert fake.calls == 0 or fake.calls == 1
    assert retry.status_code == 200
    assert after_retry == (1, 1, 1)
    assert fake.calls == 1


def test_atomic_helper_commits_both_rows_together(tmp_path: Path) -> None:
    store = SQLiteChatStore(tmp_path / "chat.sqlite3")
    from backend_lite.app.schemas.chat import ChatMessage
    from backend_lite.app.stores.sqlite_chat_store import utc_now

    store.create_chat_with_first_user_message(
        chat_id="chat_fixed",
        session_id="s1",
        title="Tiêu đề",
        message=ChatMessage(
            message_id="msg_user_fixed", chat_id="chat_fixed", role="user",
            content_type="text", content_text="xin chào", content_json=None,
            created_at=utc_now(),
        ),
    )
    assert store.chat_exists("chat_fixed") is True
    assert store.message_exists("msg_user_fixed") is True
    assert store.chat_exists("chat_missing") is False
    assert store.message_exists("msg_missing") is False


def test_existing_chat_request_creates_no_new_chat(tmp_path: Path) -> None:
    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    with TestClient(app) as client:
        seed = client.post(
            "/api/analyze", json={"session_id": "s1", "question": SEED_QUESTION}
        ).json()
        before = db_counts(db)
        follow = client.post(
            "/api/analyze",
            json={"session_id": "s1", "chat_id": seed["chat_id"],
                  "question": KEYED_QUESTION, "client_request_id": "crid-follow"},
        ).json()
        after = db_counts(db)

    assert follow["chat_id"] == seed["chat_id"]
    assert after[0] - before[0] == 0, "an existing-chat request must not create a chat"


def test_completed_new_chat_replay_still_has_zero_deltas(tmp_path: Path) -> None:
    """Phase B1 guarantee retained under the new atomic start."""

    app, fake, state_store, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    with TestClient(app) as client:
        first = client.post("/api/analyze", json=KEYED).json()
        before = db_counts(db)
        calls_before = fake.calls
        version_before = state_store.load(first["chat_id"]).state_version

        second = client.post("/api/analyze", json=KEYED).json()
        after = db_counts(db)
        version_after = state_store.load(first["chat_id"]).state_version

    assert second["chat_id"] == first["chat_id"]
    assert second["user_message_id"] == first["user_message_id"]
    assert second["assistant_message_id"] == first["assistant_message_id"]
    assert after == before
    assert fake.calls - calls_before == 0
    assert version_after - version_before == 0


# ---------------------------------------------------------------------------
# Durable pending clarification
# ---------------------------------------------------------------------------

def test_pending_clarification_is_persisted_in_state(tmp_path: Path) -> None:
    app, _, state_store, _ = build(tmp_path, [ASK_HANDOVER])
    with TestClient(app) as client:
        first = client.post(
            "/api/analyze", json={"session_id": "s1", "question": SEED_QUESTION}
        ).json()

    record = state_store.load(first["chat_id"]).state.pending_clarification
    assert record is not None
    assert record.question_id == "property_handover_status"
    assert record.question_text == "Bạn đã được chủ nhà bàn giao nhà chưa?"
    assert record.created_by_assistant_message_id == first["assistant_message_id"]
    assert record.status == "pending"


def test_pending_question_id_must_be_allowlisted() -> None:
    with pytest.raises(ValueError):
        PendingClarification(question_id="something_invented")
    # Bounded text: arbitrary prose cannot be parked in state.
    with pytest.raises(ValueError):
        PendingClarification(question_id="general", question_text="x" * 5000)


@pytest.mark.parametrize(
    ("ask", "interruption", "expected_route", "answer", "question_id", "answer_plan"),
    [
        (ASK_HANDOVER, "Cảm ơn bạn.", "social", "Chưa.",
         "property_handover_status", ANSWER_HANDOVER),
        (ASK_REFUND, "Xin chào.", "social", "Không.",
         "deposit_returned_status", ANSWER_REFUND),
        (ASK_HANDOVER, "Bạn có thể làm gì?", "capability", "Chưa.",
         "property_handover_status", ANSWER_HANDOVER),
    ],
)
def test_interruption_preserves_pending_then_answer_resolves_it(
    tmp_path: Path, ask: str, interruption: str, expected_route: str,
    answer: str, question_id: str, answer_plan: str,
) -> None:
    app, _, state_store, _ = build(tmp_path, [ask, answer_plan, answer_plan])
    with TestClient(app) as client:
        first = client.post(
            "/api/analyze", json={"session_id": "s1", "question": SEED_QUESTION}
        ).json()
        chat_id = first["chat_id"]
        assert pending_id(state_store, chat_id) == question_id

        social = client.post(
            "/api/analyze",
            json={"session_id": "s1", "chat_id": chat_id, "question": interruption},
        ).json()
        assert social["metadata"]["fast_demo_route"] == expected_route
        # The interruption neither answers nor clears the question.
        assert pending_id(state_store, chat_id) == question_id

        replied = client.post(
            "/api/analyze",
            json={"session_id": "s1", "chat_id": chat_id, "question": answer},
        ).json()

    assert replied["metadata"]["fast_demo_route"] == "legal_conversation"
    assert pending_id(state_store, chat_id) is None, "an accepted answer resolves it"


def test_social_interruption_mutates_no_legal_state(tmp_path: Path) -> None:
    app, _, state_store, _ = build(tmp_path, [ASK_HANDOVER, ANSWER_HANDOVER])
    with TestClient(app) as client:
        first = client.post(
            "/api/analyze", json={"session_id": "s1", "question": SEED_QUESTION}
        ).json()
        chat_id = first["chat_id"]
        before = state_store.load(chat_id)
        for text in ("Cảm ơn bạn.", "Xin chào.", "ok"):
            client.post(
                "/api/analyze",
                json={"session_id": "s1", "chat_id": chat_id, "question": text},
            )
        after = state_store.load(chat_id)

    assert after.state_version == before.state_version
    assert after.state.model_dump() == before.state.model_dump()


def test_failed_legal_answer_does_not_close_pending(tmp_path: Path) -> None:
    # Only one canned response, so the answering turn falls back.
    app, _, state_store, _ = build(tmp_path, [ASK_HANDOVER])
    with TestClient(app) as client:
        first = client.post(
            "/api/analyze", json={"session_id": "s1", "question": SEED_QUESTION}
        ).json()
        chat_id = first["chat_id"]
        replied = client.post(
            "/api/analyze",
            json={"session_id": "s1", "chat_id": chat_id, "question": "Chưa."},
        ).json()

    assert replied["metadata"]["fast_demo_mode"] == "fallback"
    assert pending_id(state_store, chat_id) == "property_handover_status"


def test_a_new_question_replaces_the_previous_pending(tmp_path: Path) -> None:
    app, _, state_store, _ = build(tmp_path, [ASK_HANDOVER, ASK_REFUND])
    with TestClient(app) as client:
        first = client.post(
            "/api/analyze", json={"session_id": "s1", "question": SEED_QUESTION}
        ).json()
        chat_id = first["chat_id"]
        assert pending_id(state_store, chat_id) == "property_handover_status"
        client.post(
            "/api/analyze",
            json={"session_id": "s1", "chat_id": chat_id,
                  "question": "chủ nhà vẫn chưa trả lại tiền cọc cho tôi"},
        )

    assert pending_id(state_store, chat_id) == "deposit_returned_status"


def test_resolved_pending_does_not_hijack_later_turns(tmp_path: Path) -> None:
    app, _, state_store, _ = build(
        tmp_path, [ASK_HANDOVER, ANSWER_HANDOVER, ANSWER_HANDOVER]
    )
    with TestClient(app) as client:
        first = client.post(
            "/api/analyze", json={"session_id": "s1", "question": SEED_QUESTION}
        ).json()
        chat_id = first["chat_id"]
        client.post(
            "/api/analyze",
            json={"session_id": "s1", "chat_id": chat_id, "question": "Chưa."},
        )
        assert pending_id(state_store, chat_id) is None

        # With nothing pending, a bare "ok" is social again.
        later = client.post(
            "/api/analyze",
            json={"session_id": "s1", "chat_id": chat_id, "question": "ok"},
        ).json()

    assert later["metadata"]["fast_demo_route"] == "social"
