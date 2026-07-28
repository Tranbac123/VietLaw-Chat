"""PHASE B3: post-reservation receipt failures fail closed, the atomic-write
outcome is explicit, and a pending clarification resolves only on acceptance.

The defects closed here were all "safe-looking" failures: a swallowed receipt
error, a raise mistaken for a rollback, and a bare token mistaken for an
answer. Every assertion is therefore on observable rows, provider counters and
persisted state. The provider is always ``FakeLLMClient``: zero live calls.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend_lite.app.config import Settings
from backend_lite.app.contracts.fast_demo import (
    PENDING_QUESTION_EXPECTED_SLOT,
    PendingClarification,
)
from backend_lite.app.main import create_app
from backend_lite.app.services.demo_llm_client import FakeLLMClient
from backend_lite.app.services.fast_demo_orchestrator import (
    FastDemoConfig,
    FastDemoOrchestrator,
)
from backend_lite.app.services.fast_demo_source_pack import FastDemoSourcePack
from backend_lite.app.stores.fast_demo_request_receipts import (
    STATUS_PENDING,
    FastDemoRequestReceiptStore,
    RequestReceiptStoreError,
)
from backend_lite.app.stores.fast_demo_state_store import FastDemoStateStore
from backend_lite.app.stores.sqlite_chat_store import (
    ChatStartNotCommittedError,
    ChatStartOutcomeUnknownError,
    SQLiteChatStore,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

ASSISTANT_ID = "msg_asst_" + "0" * 32


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
# Answers "Chưa." citing a span that IS present in the current message.
ANSWER_VERIFIABLE = plan(
    summary="Đã ghi nhận việc chưa bàn giao.",
    fact_updates=[
        {"operation": "negate", "slot": "property_handover_status", "value": None,
         "evidence_quote": "Chưa"},
    ],
)
# Same answer, but citing a span that is NOT in "Chưa." -> must be rejected.
ANSWER_UNVERIFIABLE = plan(
    summary="Đã ghi nhận.",
    fact_updates=[
        {"operation": "negate", "slot": "property_handover_status", "value": None,
         "evidence_quote": "chưa bàn giao nhà cho tôi"},
    ],
)
# A proposal for a slot that does not answer the pending question.
ANSWER_WRONG_SLOT = plan(
    summary="Đã ghi nhận.",
    fact_updates=[
        {"operation": "negate", "slot": "payment_evidence_status", "value": None,
         "evidence_quote": "Chưa"},
    ],
)

KEYED = {
    "session_id": "s1",
    "question": "tôi đã đặt cọc 20 triệu cho chủ nhà",
    "client_request_id": "crid-b3",
}
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


def pending_of(state_store: FastDemoStateStore, chat_id: str):
    return state_store.load(chat_id).state.pending_clarification


# ---------------------------------------------------------------------------
# 1. bind_chat() failure fails closed
# ---------------------------------------------------------------------------

def test_bind_chat_failure_fails_closed(tmp_path: Path) -> None:
    app, fake, state_store, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    receipts = app.state.container.runtime.request_receipts

    with TestClient(app) as client:
        with patch.object(
            type(receipts), "bind_chat", side_effect=RequestReceiptStoreError("injected")
        ):
            response = client.post("/api/analyze", json=KEYED)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "idempotency_unavailable"
    assert "sqlite" not in response.text.lower()
    assert "Traceback" not in response.text

    # Zero side effects: no legacy execution took place.
    assert fake.calls == 0
    assert db_counts(db) == (0, 0, 0)


def test_bind_chat_failure_leaves_retry_controlled(tmp_path: Path) -> None:
    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    receipts = app.state.container.runtime.request_receipts

    with TestClient(app) as client:
        with patch.object(
            type(receipts), "bind_chat", side_effect=RequestReceiptStoreError("injected")
        ):
            client.post("/api/analyze", json=KEYED)
        # Nothing was written, so the reservation was released and an explicit
        # retry behaves like a first attempt -- exactly once, no duplicates.
        retry = client.post("/api/analyze", json=KEYED)

    assert retry.status_code in {200, 409}
    if retry.status_code == 200:
        assert db_counts(db) == (1, 1, 1)
        assert fake.calls == 1
    else:
        assert db_counts(db) == (0, 0, 0)
        assert fake.calls == 0


# ---------------------------------------------------------------------------
# 2. Receipt setup filesystem errors are normalized
# ---------------------------------------------------------------------------

def test_permission_error_during_setup_is_normalized(tmp_path: Path) -> None:
    store = FastDemoRequestReceiptStore(tmp_path / "nested" / "receipts.sqlite3")
    with patch.object(Path, "mkdir", side_effect=PermissionError("denied")):
        with pytest.raises(RequestReceiptStoreError):
            store.ensure_schema()


def test_permission_error_yields_controlled_503(tmp_path: Path) -> None:
    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN])
    receipts = app.state.container.runtime.request_receipts
    receipts._schema_ready = False  # force a re-bootstrap on the next call

    with TestClient(app) as client:
        with patch.object(Path, "mkdir", side_effect=PermissionError("denied")):
            response = client.post("/api/analyze", json=KEYED)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "idempotency_unavailable"
    # The filesystem path and the OS error never reach the caller.
    assert "denied" not in response.text
    assert fake.calls == 0
    assert db_counts(db) == (0, 0, 0)


def test_unkeyed_request_unaffected_by_receipt_setup_failure(tmp_path: Path) -> None:
    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN])
    app.state.container.runtime.request_receipts = None
    with TestClient(app) as client:
        response = client.post(
            "/api/analyze", json={"session_id": "s1", "question": KEYED["question"]}
        )

    assert response.status_code == 200
    assert db_counts(db) == (1, 1, 1)


# ---------------------------------------------------------------------------
# 3. Explicit atomic-write outcome
# ---------------------------------------------------------------------------

def test_store_reports_proven_rollback_on_pre_commit_failure(tmp_path: Path) -> None:
    store = SQLiteChatStore(tmp_path / "chat.sqlite3")
    from backend_lite.app.schemas.chat import ChatMessage
    from backend_lite.app.stores.sqlite_chat_store import utc_now

    message = ChatMessage(
        message_id="msg_user_x", chat_id="chat_x", role="user", content_type="text",
        content_text="xin chào", content_json=None, created_at=utc_now(),
    )
    real_connect = SQLiteChatStore._connect

    class _FailInsert:
        def __init__(self, connection) -> None:
            self._connection = connection

        def execute(self, sql, *args, **kwargs):
            if sql.strip().upper().startswith("INSERT INTO MESSAGES"):
                raise sqlite3.OperationalError("injected")
            return self._connection.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._connection, name)

    with patch.object(SQLiteChatStore, "_connect", lambda self: _FailInsert(real_connect(self))):
        with pytest.raises(ChatStartNotCommittedError):
            store.create_chat_with_first_user_message(
                chat_id="chat_x", session_id="s1", title="t", message=message,
            )
    assert store.chat_exists("chat_x") is False
    assert store.message_exists("msg_user_x") is False


def test_store_reports_unknown_when_commit_fails(tmp_path: Path) -> None:
    """A failing commit() may still have applied the transaction."""

    store = SQLiteChatStore(tmp_path / "chat.sqlite3")
    from backend_lite.app.schemas.chat import ChatMessage
    from backend_lite.app.stores.sqlite_chat_store import utc_now

    message = ChatMessage(
        message_id="msg_user_y", chat_id="chat_y", role="user", content_type="text",
        content_text="xin chào", content_json=None, created_at=utc_now(),
    )
    real_connect = SQLiteChatStore._connect

    class _AmbiguousCommit:
        def __init__(self, connection) -> None:
            self._connection = connection

        def commit(self):
            self._connection.commit()          # rows DO become durable
            raise sqlite3.OperationalError("commit reported an error")

        def __getattr__(self, name):
            return getattr(self._connection, name)

    with patch.object(
        SQLiteChatStore, "_connect", lambda self: _AmbiguousCommit(real_connect(self))
    ):
        with pytest.raises(ChatStartOutcomeUnknownError):
            store.create_chat_with_first_user_message(
                chat_id="chat_y", session_id="s1", title="t", message=message,
            )
    # The rows are in fact present -- which is exactly why release is forbidden.
    assert store.chat_exists("chat_y") is True


def test_ambiguous_commit_keeps_receipt_and_blocks_duplicates(tmp_path: Path) -> None:
    """Rows commit, commit() errors, read-back unavailable, then the client
    retries: no duplicate chat, no duplicate user row, no provider call."""

    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    receipts = app.state.container.runtime.request_receipts
    real = SQLiteChatStore.create_chat_with_first_user_message
    fired = {"n": 0}

    def ambiguous(self, **kwargs):
        fired["n"] += 1
        if fired["n"] == 1:
            real(self, **kwargs)  # durable
            raise ChatStartOutcomeUnknownError("commit outcome is unknown")
        return real(self, **kwargs)

    def unavailable(self, *args, **kwargs):
        raise sqlite3.OperationalError("read-back unavailable")

    with TestClient(app) as client:
        with patch.object(SQLiteChatStore, "create_chat_with_first_user_message", ambiguous), \
             patch.object(SQLiteChatStore, "chat_exists", unavailable), \
             patch.object(SQLiteChatStore, "message_exists", unavailable):
            with pytest.raises(ChatStartOutcomeUnknownError):
                client.post("/api/analyze", json=KEYED)
        after_failure = db_counts(db)
        retry = client.post("/api/analyze", json=KEYED)
        after_retry = db_counts(db)

    assert after_failure == (1, 1, 0)
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "request_in_progress"
    assert after_retry == (1, 1, 0), "no duplicate chat or user row"
    assert fake.calls == 0, "the provider was never reached"

    receipt = receipts.find(session_id="s1", client_request_id="crid-b3")
    assert receipt is not None and receipt.status == STATUS_PENDING


def test_proven_rollback_allows_a_clean_retry(tmp_path: Path) -> None:
    app, fake, state_store, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    fired = {"n": 0}
    real = SQLiteChatStore.create_chat_with_first_user_message

    def rollback_once(self, **kwargs):
        fired["n"] += 1
        if fired["n"] == 1:
            raise ChatStartNotCommittedError("rolled back before commit")
        return real(self, **kwargs)

    with TestClient(app) as client:
        with patch.object(SQLiteChatStore, "create_chat_with_first_user_message", rollback_once):
            with pytest.raises(ChatStartNotCommittedError):
                client.post("/api/analyze", json=KEYED)
            assert db_counts(db) == (0, 0, 0)
            retry = client.post("/api/analyze", json=KEYED)

    assert retry.status_code == 200
    assert db_counts(db) == (1, 1, 1)
    assert fake.calls == 1
    chat_id = retry.json()["chat_id"]
    assert state_store.load(chat_id).state_version == 1


def test_failed_readback_never_authorises_release(tmp_path: Path) -> None:
    """Read-back may strengthen a refusal; it can never turn UNKNOWN into a
    release."""

    app, fake, _, db = build(tmp_path, [DEPOSIT_PLAN, DEPOSIT_PLAN])
    real = SQLiteChatStore.create_chat_with_first_user_message
    fired = {"n": 0}

    def unknown_once(self, **kwargs):
        fired["n"] += 1
        if fired["n"] == 1:
            real(self, **kwargs)
            raise ChatStartOutcomeUnknownError("unknown")
        return real(self, **kwargs)

    def unavailable(self, *args, **kwargs):
        raise sqlite3.OperationalError("unavailable")

    with TestClient(app) as client:
        with patch.object(SQLiteChatStore, "create_chat_with_first_user_message", unknown_once), \
             patch.object(SQLiteChatStore, "chat_exists", unavailable), \
             patch.object(SQLiteChatStore, "message_exists", unavailable):
            with pytest.raises(ChatStartOutcomeUnknownError):
                client.post("/api/analyze", json=KEYED)
            retry = client.post("/api/analyze", json=KEYED)

    assert retry.status_code == 409
    assert db_counts(db)[0] == 1, "still exactly one chat"


# ---------------------------------------------------------------------------
# 4. Pending acceptance contract
# ---------------------------------------------------------------------------

def _seed_pending(client: TestClient) -> str:
    first = client.post(
        "/api/analyze", json={"session_id": "s1", "question": SEED_QUESTION}
    ).json()
    return first["chat_id"]


@pytest.mark.parametrize(
    ("answer_plan", "label"),
    [(ANSWER_UNVERIFIABLE, "unverifiable evidence"), (ANSWER_WRONG_SLOT, "wrong slot")],
)
def test_rejected_fact_update_preserves_pending(
    tmp_path: Path, answer_plan: str, label: str,
) -> None:
    app, _, state_store, _ = build(tmp_path, [ASK_HANDOVER, answer_plan])
    with TestClient(app) as client:
        chat_id = _seed_pending(client)
        assert pending_of(state_store, chat_id).question_id == "property_handover_status"

        replied = client.post(
            "/api/analyze",
            json={"session_id": "s1", "chat_id": chat_id, "question": "Chưa."},
        ).json()

    state = state_store.load(chat_id).state
    assert "property_handover_status" not in (replied["metadata"].get("applied_slots") or [])
    assert state.facts.property_handover_status == "unknown"
    record = state.pending_clarification
    assert record is not None and record.question_id == "property_handover_status", label
    assert record.status == "pending"


def test_accepted_fact_update_resolves_pending_in_the_same_commit(tmp_path: Path) -> None:
    app, _, state_store, _ = build(tmp_path, [ASK_HANDOVER, ANSWER_VERIFIABLE])
    with TestClient(app) as client:
        chat_id = _seed_pending(client)
        version_before = state_store.load(chat_id).state_version

        replied = client.post(
            "/api/analyze",
            json={"session_id": "s1", "chat_id": chat_id, "question": "Chưa."},
        ).json()

    loaded = state_store.load(chat_id)
    assert "property_handover_status" in replied["metadata"]["applied_slots"]
    assert loaded.state.facts.property_handover_status == "absent"
    assert loaded.state.pending_clarification is None
    # Both the fact and the pending transition landed in one CAS step.
    assert loaded.state_version == version_before + 1


def test_general_pending_is_never_auto_resolved_by_a_bare_token(tmp_path: Path) -> None:
    ask_general = plan(
        response_mode="clarify",
        summary="Tôi cần thêm thông tin.",
        clarifying_questions=["Bạn muốn tôi hỗ trợ phần nào trước?"],
    )
    app, _, state_store, _ = build(tmp_path, [ask_general, plan(summary="Ghi nhận.")])
    with TestClient(app) as client:
        chat_id = _seed_pending(client)
        record = pending_of(state_store, chat_id)
        assert record is not None and record.question_id == "general"
        assert record.expected_slot is None

        client.post(
            "/api/analyze",
            json={"session_id": "s1", "chat_id": chat_id, "question": "Có."},
        )

    still = pending_of(state_store, chat_id)
    assert still is not None and still.question_id == "general"


def test_expected_slot_map_covers_every_slot_backed_question() -> None:
    for question_id, slot in PENDING_QUESTION_EXPECTED_SLOT.items():
        assert PendingClarification(
            question_id=question_id,
            created_by_assistant_message_id=ASSISTANT_ID,
            created_at_state_version=0,
        ).expected_slot == slot
    assert PendingClarification(
        question_id="general",
        created_by_assistant_message_id=ASSISTANT_ID,
        created_at_state_version=0,
    ).expected_slot is None


# ---------------------------------------------------------------------------
# 5. Pending field validation
# ---------------------------------------------------------------------------

def test_pending_rejects_empty_assistant_message_id() -> None:
    with pytest.raises(ValueError):
        PendingClarification(
            question_id="general", created_by_assistant_message_id="",
            created_at_state_version=0,
        )


def test_pending_rejects_overlong_assistant_message_id() -> None:
    with pytest.raises(ValueError):
        PendingClarification(
            question_id="general",
            created_by_assistant_message_id="msg_asst_" + "a" * 500,
            created_at_state_version=0,
        )


def test_pending_rejects_foreign_assistant_message_id_shape() -> None:
    with pytest.raises(ValueError):
        PendingClarification(
            question_id="general", created_by_assistant_message_id="not-a-message-id",
            created_at_state_version=0,
        )


def test_pending_rejects_negative_state_version() -> None:
    with pytest.raises(ValueError):
        PendingClarification(
            question_id="general", created_by_assistant_message_id=ASSISTANT_ID,
            created_at_state_version=-1,
        )


def test_pending_keeps_existing_bounds() -> None:
    with pytest.raises(ValueError):
        PendingClarification(
            question_id="invented", created_by_assistant_message_id=ASSISTANT_ID,
            created_at_state_version=0,
        )
    with pytest.raises(ValueError):
        PendingClarification(
            question_id="general", question_text="x" * 301,
            created_by_assistant_message_id=ASSISTANT_ID, created_at_state_version=0,
        )
    ok = PendingClarification(
        question_id="general", created_by_assistant_message_id=ASSISTANT_ID,
        created_at_state_version=0,
    )
    assert ok.status == "pending"


# ---------------------------------------------------------------------------
# 6. New-matter policy: Option B (declared unsupported)
# ---------------------------------------------------------------------------

def test_distinct_matter_without_a_new_question_preserves_pending(tmp_path: Path) -> None:
    """Documents the single-issue limitation rather than claiming a fix.

    A distinct legal turn that asks no replacement question leaves the earlier
    question outstanding. There is no deterministic new-matter signal in this
    demo, and guessing one would be worse than preserving the question.
    """

    app, _, state_store, _ = build(
        tmp_path, [ASK_HANDOVER, plan(summary="Ghi nhận vấn đề khác.")]
    )
    with TestClient(app) as client:
        chat_id = _seed_pending(client)
        assert pending_of(state_store, chat_id).question_id == "property_handover_status"

        client.post(
            "/api/analyze",
            json={"session_id": "s1", "chat_id": chat_id,
                  "question": "tôi muốn hỏi về hợp đồng thuê nhà của tôi"},
        )

    record = pending_of(state_store, chat_id)
    assert record is not None
    assert record.question_id == "property_handover_status"


def test_a_replacement_question_still_replaces_pending(tmp_path: Path) -> None:
    ask_refund = plan(
        response_mode="clarify",
        summary="Tôi cần làm rõ thêm.",
        clarifying_questions=["Chủ nhà có đồng ý hoàn trả tiền cọc không?"],
    )
    app, _, state_store, _ = build(tmp_path, [ASK_HANDOVER, ask_refund])
    with TestClient(app) as client:
        chat_id = _seed_pending(client)
        client.post(
            "/api/analyze",
            json={"session_id": "s1", "chat_id": chat_id,
                  "question": "chủ nhà vẫn chưa trả lại tiền cọc cho tôi"},
        )

    assert pending_of(state_store, chat_id).question_id == "deposit_returned_status"
