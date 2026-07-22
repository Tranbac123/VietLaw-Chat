from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend_lite.app.adapters.migrator import SQLiteMigrator
from backend_lite.app.adapters.sqlite_store import (
    DurableRowError,
    RequestOwnershipError,
    RequestStateError,
    SQLiteRequestChatStore,
    StoreSchemaError,
)
from backend_lite.app.contracts.internal import (
    BeginRequest,
    BoundedContextQuery,
    CompleteRequest,
    FailRequest,
    RequestStatus,
    VersionStamps,
)
from backend_lite.app.stores.sqlite_chat_store import SQLiteChatStore


class FixedClock:
    def __init__(self, *values: datetime) -> None:
        self._values = list(values) or [datetime(2026, 7, 14, tzinfo=timezone.utc)]

    def now_utc(self) -> datetime:
        return self._values.pop(0) if len(self._values) > 1 else self._values[0]

    def monotonic(self) -> float:
        return 0.0


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _ready(path: Path, clock: FixedClock | None = None) -> SQLiteRequestChatStore:
    SQLiteChatStore(path).bootstrap_base_schema()
    SQLiteMigrator(path, now_factory=lambda: "2026-07-14T00:00:00+00:00").migrate()
    return SQLiteRequestChatStore(path, clock or FixedClock())


def _stamps() -> VersionStamps:
    return VersionStamps(
        corpus_version="corpus-test-v1",
        policy_version="policy-test-v1",
        retriever_version="lexical-test-v1",
        generator_version="renderer-test-v1",
    )


def _begin(
    suffix: str,
    *,
    session_id: str = "session-a",
    requested_chat_id: str | None = None,
    digest: str | None = "a" * 64,
    fingerprint: str = "1" * 64,
) -> BeginRequest:
    return BeginRequest(
        session_id=session_id,
        request_id=f"req-{suffix}",
        request_fingerprint=fingerprint,
        question=f"Câu hỏi {suffix}",
        requested_chat_id=requested_chat_id,
        new_chat_title=f"Title {suffix}" if requested_chat_id is None else None,
        idempotency_key_digest=digest,
        idempotency_key_digest_version="idempotency-key-digest-v1" if digest is not None else None,
        chat_id_candidate=f"chat-{suffix}" if requested_chat_id is None else None,
        user_message_id_candidate=f"msg-user-{suffix}",
        version_stamps=_stamps(),
    )


def _payload(
    command: BeginRequest,
    assistant_id: str,
    *,
    clarifications: list[str] | None = None,
    confirmed_topic: str | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {"stable": True}
    if confirmed_topic is not None:
        metadata["confirmed_topic"] = confirmed_topic
    return {
        "contract_version": "v1",
        "request_id": command.request_id,
        "chat_id": command.requested_chat_id or command.chat_id_candidate,
        "user_message_id": command.user_message_id_candidate,
        "assistant_message_id": assistant_id,
        "domain": "civil_dispute",
        "risk_level": "low",
        "decision": "ask_clarifying_questions",
        "summary": "Nội dung có cấu trúc.",
        "clarifying_questions": clarifications or ["Bạn có giấy tờ liên quan không?"],
        "checklist": ["Tài liệu"],
        "next_steps": ["Xác nhận thông tin"],
        "sources": [],
        "safety_notice": "Thông tin tham khảo.",
        "confidence": {"domain": 0.5, "risk": 0.5, "answer": 0.5},
        "metadata": metadata,
    }


def _complete(command: BeginRequest, assistant_id: str, **payload_kwargs: object) -> CompleteRequest:
    return CompleteRequest(
        session_id=command.session_id,
        request_id=command.request_id,
        request_fingerprint=command.request_fingerprint,
        attempt_count=1,
        chat_id=command.requested_chat_id or command.chat_id_candidate or "",
        user_message_id=command.user_message_id_candidate or "",
        assistant_message_id=assistant_id,
        response_payload=_payload(command, assistant_id, **payload_kwargs),
    )


def _error_payload(request_id: str) -> dict[str, object]:
    return {
        "contract_version": "v1",
        "request_id": request_id,
        "error": {"code": "internal_error", "message": "Lỗi an toàn."},
        "safety_notice": "Thông tin tham khảo.",
    }


def _counts(path: Path) -> tuple[int, int, int]:
    with _connect(path) as connection:
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("chats", "analysis_requests", "messages")
        )


def _lifecycle_snapshot(path: Path, request_id: str) -> tuple[dict[str, object], int, str]:
    with _connect(path) as connection:
        request = dict(
            connection.execute(
                "SELECT * FROM analysis_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
        )
        message_count = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        chat_updated_at = connection.execute(
            "SELECT updated_at FROM chats WHERE chat_id = ?", (request["chat_id"],)
        ).fetchone()[0]
    return request, message_count, chat_updated_at


def _corrupt_request(path: Path, request_id: str, **fields: object) -> None:
    assignments = ", ".join(f"{name} = ?" for name in fields)
    with _connect(path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            f"UPDATE analysis_requests SET {assignments} WHERE request_id = ?",  # noqa: S608 - names are test constants
            (*fields.values(), request_id),
        )


def _durable_state(path: Path, state: str) -> tuple[SQLiteRequestChatStore, BeginRequest]:
    store = _ready(path)
    command = _begin(f"corrupt-{state}", digest={"processing": "a", "complete": "b", "retry": "c", "final": "d"}[state] * 64)
    store.begin_request(command)
    if state == "complete":
        store.complete_request(_complete(command, f"msg-asst-{state}"))
    elif state == "retry":
        store.fail_request(
            FailRequest(
                session_id=command.session_id,
                request_id=command.request_id,
                request_fingerprint=command.request_fingerprint,
                attempt_count=1,
                status=RequestStatus.FAILED_RETRYABLE,
                error_class="retryable_dependency",
                last_error_code="retrieval_error",
            )
        )
    elif state == "final":
        store.fail_request(
            FailRequest(
                session_id=command.session_id,
                request_id=command.request_id,
                request_fingerprint=command.request_fingerprint,
                attempt_count=1,
                status=RequestStatus.FAILED_FINAL,
                error_class="final_deterministic",
                last_error_code="internal_error",
                response_payload=_error_payload(command.request_id),
            )
        )
    return store, command


def test_constructor_does_not_create_or_migrate_and_missing_schema_fails(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    store = SQLiteRequestChatStore(path, FixedClock())
    assert not path.exists()
    with pytest.raises(StoreSchemaError):
        store.begin_request(_begin("missing"))
    assert not path.exists()


def test_base_without_explicit_a2a_migration_fails_without_repair(tmp_path: Path) -> None:
    path = tmp_path / "base-only.sqlite3"
    SQLiteChatStore(path).bootstrap_base_schema()
    store = SQLiteRequestChatStore(path, FixedClock())
    with pytest.raises(StoreSchemaError):
        store.begin_request(_begin("base-only"))
    with _connect(path) as connection:
        objects = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master")}
    assert "schema_migrations" not in objects
    assert "analysis_requests" not in objects


def test_explicit_bootstrap_migration_new_request_is_atomic_and_adopts_candidates(tmp_path: Path) -> None:
    base = datetime(2026, 7, 14, 1, tzinfo=timezone.utc)
    path = tmp_path / "new.sqlite3"
    store = _ready(path, FixedClock(base))
    command = _begin("new")

    result = store.begin_request(command)

    assert result.kind == "accepted"
    assert result.status is RequestStatus.PROCESSING
    assert result.identity.chat_id == "chat-new"
    assert result.identity.user_message_id == "msg-user-new"
    assert _counts(path) == (1, 1, 1)
    with _connect(path) as connection:
        chat = connection.execute("SELECT * FROM chats").fetchone()
        message = connection.execute("SELECT * FROM messages").fetchone()
        request = connection.execute("SELECT * FROM analysis_requests").fetchone()
    assert chat["title"] == "Title new"
    assert chat["created_at"] == message["created_at"] == chat["updated_at"]
    assert request["status"] == "PROCESSING"
    assert request["idempotency_key_digest"] == "a" * 64
    assert "idempotency" not in message["content_text"].casefold()


def test_existing_chat_and_legacy_no_carrier_create_distinct_requests_with_strict_timestamps(tmp_path: Path) -> None:
    base = datetime(2026, 7, 14, 1, tzinfo=timezone.utc)
    path = tmp_path / "legacy.sqlite3"
    store = _ready(path, FixedClock(base, base, base - timedelta(days=1)))
    first = _begin("first")
    accepted = store.begin_request(first)
    existing_chat = accepted.identity.chat_id
    assert existing_chat is not None

    legacy_one = _begin("legacy-one", requested_chat_id=existing_chat, digest=None)
    legacy_two = _begin("legacy-two", requested_chat_id=existing_chat, digest=None)
    store.begin_request(legacy_one)
    store.begin_request(legacy_two)

    assert _counts(path) == (1, 3, 3)
    with _connect(path) as connection:
        timestamps = [row[0] for row in connection.execute("SELECT created_at FROM messages ORDER BY created_at")]
        request_versions = connection.execute(
            "SELECT corpus_version, policy_version, prompt_version, generator_mode FROM analysis_requests"
        ).fetchall()
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == 3
    assert {tuple(row) for row in request_versions} == {
        ("corpus-test-v1", "policy-test-v1", "none", "deterministic")
    }


@pytest.mark.parametrize("kind", ["missing", "deleted", "other-session"])
def test_ownership_failures_are_indistinguishable_and_write_nothing(tmp_path: Path, kind: str) -> None:
    path = tmp_path / f"ownership-{kind}.sqlite3"
    store = _ready(path)
    if kind != "missing":
        seed = _begin("seed", session_id="owner")
        store.begin_request(seed)
        chat_id = seed.chat_id_candidate or ""
        if kind == "deleted":
            with _connect(path) as connection:
                connection.execute("UPDATE chats SET deleted_at = updated_at WHERE chat_id = ?", (chat_id,))
        session = "attacker" if kind == "other-session" else "owner"
    else:
        chat_id = "does-not-exist"
        session = "attacker"
    before = _counts(path)
    with pytest.raises(RequestOwnershipError, match="chat_not_found"):
        store.begin_request(_begin(f"{kind}-request", session_id=session, requested_chat_id=chat_id))
    assert _counts(path) == before


def test_sequential_duplicate_matrix_replays_or_mutates_only_retry(tmp_path: Path) -> None:
    path = tmp_path / "duplicates.sqlite3"
    store = _ready(path)

    complete_command = _begin("complete", digest="b" * 64)
    store.begin_request(complete_command)
    completed = store.complete_request(_complete(complete_command, "msg-asst-complete"))
    before_complete = _counts(path)
    replay = store.begin_request(complete_command)
    assert replay.kind == "duplicate"
    assert replay.stored_response is not None
    assert replay.stored_response.response_payload == completed.response_payload
    assert _counts(path) == before_complete

    changed = complete_command.model_copy(update={"request_fingerprint": "2" * 64})
    reuse = store.begin_request(changed)
    assert reuse.kind == "duplicate"
    assert reuse.stored_response is not None
    assert reuse.stored_response.error_code == "IDEMPOTENCY_KEY_REUSED"
    assert _counts(path) == before_complete

    processing = _begin("processing", digest="c" * 64)
    store.begin_request(processing)
    in_progress = store.begin_request(processing)
    assert in_progress.kind == "in_progress"
    assert in_progress.should_execute is False

    retryable = _begin("retry", digest="d" * 64)
    store.begin_request(retryable)
    store.fail_request(
        FailRequest(
            session_id=retryable.session_id,
            request_id=retryable.request_id,
            request_fingerprint=retryable.request_fingerprint,
            attempt_count=1,
            status=RequestStatus.FAILED_RETRYABLE,
            error_class="retryable_dependency",
            last_error_code="retrieval_error",
        )
    )
    before_retry = _counts(path)
    retried = store.begin_request(retryable)
    assert retried.kind == "retry"
    assert retried.identity.attempt_count == 2
    assert retried.user_message_created is False
    assert _counts(path) == before_retry

    final = _begin("final", digest="e" * 64)
    store.begin_request(final)
    store.fail_request(
        FailRequest(
            session_id=final.session_id,
            request_id=final.request_id,
            request_fingerprint=final.request_fingerprint,
            attempt_count=1,
            status=RequestStatus.FAILED_FINAL,
            error_class="final_deterministic",
            last_error_code="internal_error",
            response_payload=_error_payload(final.request_id),
        )
    )
    final_replay = store.begin_request(final)
    assert final_replay.kind == "duplicate"
    assert final_replay.stored_response is not None
    assert final_replay.stored_response.response_payload == _error_payload(final.request_id)


@pytest.mark.parametrize("checkpoint", ["after_request_insert_before_user", "after_user_before_commit"])
def test_tx_a_failure_injection_rolls_back_request_chat_and_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, checkpoint: str
) -> None:
    path = tmp_path / f"txa-{checkpoint}.sqlite3"
    store = _ready(path)
    monkeypatch.setattr(
        store,
        "_checkpoint",
        lambda name: (_ for _ in ()).throw(RuntimeError("injected")) if name == checkpoint else None,
    )
    with pytest.raises(RuntimeError, match="injected"):
        store.begin_request(_begin("txa", digest="f" * 64))
    assert _counts(path) == (0, 0, 0)


@pytest.mark.parametrize("checkpoint", ["after_assistant_insert_before_complete", "after_response_update_before_commit"])
def test_tx_b_failure_injection_rolls_back_assistant_payload_and_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, checkpoint: str
) -> None:
    path = tmp_path / f"txb-{checkpoint}.sqlite3"
    store = _ready(path)
    command = _begin("txb", digest="9" * 64)
    store.begin_request(command)
    monkeypatch.setattr(
        store,
        "_checkpoint",
        lambda name: (_ for _ in ()).throw(RuntimeError("injected")) if name == checkpoint else None,
    )
    with pytest.raises(RuntimeError, match="injected"):
        store.complete_request(_complete(command, "msg-asst-txb"))
    with _connect(path) as connection:
        request = connection.execute("SELECT status, response_payload, assistant_message_id FROM analysis_requests").fetchone()
        messages = connection.execute("SELECT role FROM messages ORDER BY message_id").fetchall()
    assert tuple(request) == ("PROCESSING", None, None)
    assert [row["role"] for row in messages] == ["user"]


def test_completion_guards_and_exact_repeated_completion(tmp_path: Path) -> None:
    path = tmp_path / "completion.sqlite3"
    store = _ready(path)
    command = _begin("completion", digest="0" * 64)
    store.begin_request(command)
    completion = _complete(command, "msg-asst-completion")
    stored = store.complete_request(completion)
    assert store.complete_request(completion) == stored
    assert _counts(path) == (1, 1, 2)
    for changed in (
        completion.model_copy(update={"request_fingerprint": "3" * 64}),
        completion.model_copy(update={"attempt_count": 2}),
        completion.model_copy(update={"chat_id": "wrong"}),
        completion.model_copy(update={"user_message_id": "wrong"}),
        completion.model_copy(update={"assistant_message_id": "wrong"}),
    ):
        with pytest.raises((RequestStateError, DurableRowError)):
            store.complete_request(changed)

    second = _begin("completion-second", requested_chat_id="chat-completion", digest="a" * 64)
    store.begin_request(second)
    with pytest.raises(RequestStateError, match="already in use"):
        store.complete_request(_complete(second, "msg-asst-completion"))
    assert _counts(path) == (1, 2, 3)


def test_failure_shape_stale_attempt_and_injected_failure_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "failure.sqlite3"
    store = _ready(path)
    command = _begin("failure", digest="4" * 64)
    store.begin_request(command)
    retryable = FailRequest(
        session_id=command.session_id,
        request_id=command.request_id,
        request_fingerprint=command.request_fingerprint,
        attempt_count=1,
        status=RequestStatus.FAILED_RETRYABLE,
        error_class="retryable_dependency",
        last_error_code="retrieval_error",
        error_details_redacted={"operation": "retrieval"},
    )
    monkeypatch.setattr(
        store,
        "_checkpoint",
        lambda name: (_ for _ in ()).throw(RuntimeError("injected"))
        if name == "during_failure_update_before_commit"
        else None,
    )
    with pytest.raises(RuntimeError, match="injected"):
        store.fail_request(retryable)
    with _connect(path) as connection:
        assert connection.execute("SELECT status FROM analysis_requests").fetchone()[0] == "PROCESSING"
    monkeypatch.setattr(store, "_checkpoint", lambda _name: None)
    store.fail_request(retryable)
    retried = store.begin_request(command)
    assert retried.identity.attempt_count == 2
    with pytest.raises(RequestStateError):
        store.fail_request(retryable)
    with _connect(path) as connection:
        row = connection.execute("SELECT status, attempt_count, response_payload, assistant_message_id FROM analysis_requests").fetchone()
        details = connection.execute("SELECT error_details_json FROM analysis_requests").fetchone()[0]
    assert tuple(row) == ("PROCESSING", 2, None, None)
    assert details is None
    with pytest.raises(ValueError, match="forbidden"):
        store.fail_request(retryable.model_copy(update={"error_details_redacted": {"traceback": "secret"}}))


def test_bounded_context_is_scoped_by_current_user_cutoff_and_never_returns_raw_history(tmp_path: Path) -> None:
    path = tmp_path / "context.sqlite3"
    store = _ready(path)
    first = _begin("context-first", digest="5" * 64)
    first_result = store.begin_request(first)
    assert first_result.identity.chat_id is not None
    store.complete_request(
        _complete(
            first,
            "msg-asst-context-first",
            clarifications=["Q" * 350, "Câu hỏi thứ hai"],
            confirmed_topic="rental_deposit",
        )
    )
    second = _begin(
        "context-second",
        requested_chat_id=first_result.identity.chat_id,
        digest="6" * 64,
    )
    second_result = store.begin_request(second)
    context = store.load_bounded_context(
        BoundedContextQuery(
            session_id=second.session_id,
            chat_id=second_result.identity.chat_id or "",
            current_user_message_id=second_result.identity.user_message_id or "",
            current_question=second.question,
        )
    )
    assert context.current_question == second.question
    assert context.last_assistant_message_id == "msg-asst-context-first"
    assert context.last_confirmed_topic == "rental_deposit"
    assert context.last_confirmed_domain == "civil_dispute"
    assert len(context.last_assistant_clarification) == 2
    assert len(context.last_assistant_clarification[0]) == 300
    assert "Nội dung có cấu trúc" not in context.model_dump_json()
    assert first.question not in context.model_dump_json()

    store.complete_request(_complete(second, "msg-asst-context-second", confirmed_topic="later"))
    again = store.load_bounded_context(
        BoundedContextQuery(
            session_id=second.session_id,
            chat_id=second_result.identity.chat_id or "",
            current_user_message_id=second_result.identity.user_message_id or "",
            current_question=second.question,
        )
    )
    assert again.last_confirmed_message_id == "msg-asst-context-first"
    with pytest.raises(RequestOwnershipError, match="chat_not_found"):
        store.load_bounded_context(
            BoundedContextQuery(
                session_id="other-session",
                chat_id=second_result.identity.chat_id or "",
                current_user_message_id=second_result.identity.user_message_id or "",
                current_question=second.question,
            )
        )


def test_fresh_context_and_corrupt_durable_response_fail_loud(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.sqlite3"
    store = _ready(path)
    command = _begin("corrupt", digest="7" * 64)
    accepted = store.begin_request(command)
    fresh = store.load_bounded_context(
        BoundedContextQuery(
            session_id=command.session_id,
            chat_id=accepted.identity.chat_id or "",
            current_user_message_id=accepted.identity.user_message_id or "",
            current_question=command.question,
        )
    )
    assert fresh.last_assistant_clarification == []
    assert fresh.last_confirmed_topic is None
    store.complete_request(_complete(command, "msg-asst-corrupt"))
    with _connect(path) as connection:
        connection.execute("UPDATE analysis_requests SET response_payload = ?", ("{not-json",))
    with pytest.raises(DurableRowError, match="malformed JSON"):
        store.begin_request(command)
    with _connect(path) as connection:
        row = connection.execute("SELECT response_payload FROM analysis_requests").fetchone()[0]
    assert row == "{not-json"


def test_invalid_version_stamps_cannot_be_invented_by_store(tmp_path: Path) -> None:
    path = tmp_path / "versions.sqlite3"
    store = _ready(path)
    command = _begin("versions")
    with _connect(path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            """
            INSERT INTO chats VALUES ('chat-bad', 'session-a', 'Bad', '2026-07-14T00:00:00+00:00',
                                     '2026-07-14T00:00:00+00:00', NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO messages VALUES ('msg-user-bad', 'chat-bad', 'user', 'text', 'bad', NULL,
                                        '2026-07-14T00:00:00+00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO analysis_requests(
                session_id, request_id, idempotency_key_version, idempotency_key_digest,
                fingerprint_version, request_fingerprint, status, attempt_count,
                chat_id, user_type, language, user_message_id, contract_version, corpus_version,
                policy_version, prompt_version, retriever_version, generator_mode, generator_version,
                created_at, processing_started_at, updated_at
            ) VALUES ('session-a', 'req-bad', 'idempotency-key-digest-v1', ?, 'fingerprint-v1', ?, 'PROCESSING', 1,
                'chat-bad', 'unknown', 'vi', 'msg-user-bad', 'v1', 'corpus', 'policy', 'not-none',
                'retriever', 'deterministic', 'generator', '2026-07-14T00:00:00+00:00',
                '2026-07-14T00:00:00+00:00', '2026-07-14T00:00:00+00:00')
            """,
                ("a" * 64, "8" * 64),
        )
    with pytest.raises(DurableRowError, match="version stamps"):
        store.begin_request(command)


def test_failed_final_with_valid_message_link_fails_before_replay_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "failed-final-assistant.sqlite3"
    store, command = _durable_state(path, "final")
    payload = _payload(command, "unused")
    content = {
        key: value
        for key, value in payload.items()
        if key
        not in {"contract_version", "request_id", "chat_id", "user_message_id", "assistant_message_id"}
    }
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO messages(message_id, chat_id, role, content_type, content_text, content_json, created_at)
            VALUES ('msg-asst-valid-link', ?, 'assistant', 'structured', NULL, ?, ?)
            """,
            (
                command.chat_id_candidate,
                json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                "2026-07-14T02:00:00.000000+00:00",
            ),
        )
    _corrupt_request(path, command.request_id, assistant_message_id="msg-asst-valid-link")
    before = _lifecycle_snapshot(path, command.request_id)

    with pytest.raises(DurableRowError, match="assistant or completion"):
        store.begin_request(command)

    assert _lifecycle_snapshot(path, command.request_id) == before


def test_failed_retryable_without_failed_at_fails_before_retry_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "failed-retryable-no-time.sqlite3"
    store, command = _durable_state(path, "retry")
    _corrupt_request(path, command.request_id, failed_at=None)
    before = _lifecycle_snapshot(path, command.request_id)

    with pytest.raises(DurableRowError, match="incomplete failure fields"):
        store.begin_request(command)

    after = _lifecycle_snapshot(path, command.request_id)
    assert after == before
    assert after[0]["attempt_count"] == 1
    assert after[0]["status"] == "FAILED_RETRYABLE"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("assistant_message_id", lambda row: row["user_message_id"]),
        ("response_payload", lambda _row: '{"unexpected":true}'),
        ("completed_at", lambda _row: "2026-07-14T01:00:00.000000+00:00"),
        ("failed_at", lambda _row: "2026-07-14T01:00:00.000000+00:00"),
        ("error_class", lambda _row: "internal"),
        ("last_error_code", lambda _row: "internal_error"),
        ("error_details_json", lambda _row: "{}"),
    ],
)
def test_processing_lifecycle_corruption_fails_without_mutation(
    tmp_path: Path, field: str, value: object
) -> None:
    path = tmp_path / f"processing-{field}.sqlite3"
    store, command = _durable_state(path, "processing")
    request, _, _ = _lifecycle_snapshot(path, command.request_id)
    _corrupt_request(path, command.request_id, **{field: value(request)})  # type: ignore[operator]
    before = _lifecycle_snapshot(path, command.request_id)

    with pytest.raises(DurableRowError, match="PROCESSING"):
        store.begin_request(command)

    assert _lifecycle_snapshot(path, command.request_id) == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("assistant_message_id", lambda _row: None),
        ("response_payload", lambda _row: None),
        ("completed_at", lambda _row: None),
        ("failed_at", lambda _row: "2026-07-14T01:00:00.000000+00:00"),
        ("error_class", lambda _row: "internal"),
        ("last_error_code", lambda _row: "internal_error"),
        ("error_details_json", lambda _row: "{}"),
    ],
)
def test_complete_lifecycle_corruption_fails_without_mutation(
    tmp_path: Path, field: str, value: object
) -> None:
    path = tmp_path / f"complete-{field}.sqlite3"
    store, command = _durable_state(path, "complete")
    request, _, _ = _lifecycle_snapshot(path, command.request_id)
    _corrupt_request(path, command.request_id, **{field: value(request)})  # type: ignore[operator]
    before = _lifecycle_snapshot(path, command.request_id)

    with pytest.raises(DurableRowError):
        store.begin_request(command)

    assert _lifecycle_snapshot(path, command.request_id) == before


def test_complete_success_payload_identity_mismatch_fails_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "complete-payload-identity.sqlite3"
    store, command = _durable_state(path, "complete")
    request, _, _ = _lifecycle_snapshot(path, command.request_id)
    payload = json.loads(request["response_payload"])
    payload["chat_id"] = "wrong-chat"
    _corrupt_request(
        path,
        command.request_id,
        response_payload=json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )
    before = _lifecycle_snapshot(path, command.request_id)

    with pytest.raises(DurableRowError, match="IDs do not match"):
        store.begin_request(command)

    assert _lifecycle_snapshot(path, command.request_id) == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("assistant_message_id", lambda row: row["user_message_id"]),
        ("response_payload", lambda _row: '{"unexpected":true}'),
        ("completed_at", lambda _row: "2026-07-14T01:00:00.000000+00:00"),
        ("failed_at", lambda _row: None),
        ("error_class", lambda _row: None),
        ("last_error_code", lambda _row: None),
        ("error_details_json", lambda _row: "{not-json"),
        ("error_details_json", lambda _row: '{"traceback":"hidden"}'),
    ],
)
def test_failed_retryable_lifecycle_corruption_fails_without_mutation(
    tmp_path: Path, field: str, value: object
) -> None:
    path = tmp_path / f"retry-{field}.sqlite3"
    store, command = _durable_state(path, "retry")
    request, _, _ = _lifecycle_snapshot(path, command.request_id)
    _corrupt_request(path, command.request_id, **{field: value(request)})  # type: ignore[operator]
    before = _lifecycle_snapshot(path, command.request_id)

    with pytest.raises(DurableRowError):
        store.begin_request(command)

    assert _lifecycle_snapshot(path, command.request_id) == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("assistant_message_id", lambda row: row["user_message_id"]),
        ("response_payload", lambda _row: None),
        ("completed_at", lambda _row: "2026-07-14T01:00:00.000000+00:00"),
        ("failed_at", lambda _row: None),
        ("error_class", lambda _row: None),
        ("last_error_code", lambda _row: None),
        ("last_error_code", lambda _row: "retrieval_error"),
        ("response_payload", lambda _row: '{"unexpected":true}'),
        ("response_payload", lambda _row: '{ "unexpected":true}'),
    ],
)
def test_failed_final_lifecycle_corruption_fails_without_mutation(
    tmp_path: Path, field: str, value: object
) -> None:
    path = tmp_path / f"final-{field}.sqlite3"
    store, command = _durable_state(path, "final")
    request, _, _ = _lifecycle_snapshot(path, command.request_id)
    _corrupt_request(path, command.request_id, **{field: value(request)})  # type: ignore[operator]
    before = _lifecycle_snapshot(path, command.request_id)

    with pytest.raises(DurableRowError):
        store.begin_request(command)

    assert _lifecycle_snapshot(path, command.request_id) == before


def test_context_cutoff_maps_lifecycle_before_using_corrupt_request(tmp_path: Path) -> None:
    path = tmp_path / "context-lifecycle.sqlite3"
    store, command = _durable_state(path, "processing")
    accepted = store.begin_request(command)
    _corrupt_request(path, command.request_id, failed_at="2026-07-14T01:00:00.000000+00:00")
    before = _lifecycle_snapshot(path, command.request_id)

    with pytest.raises(DurableRowError, match="PROCESSING"):
        store.load_bounded_context(
            BoundedContextQuery(
                session_id=command.session_id,
                chat_id=accepted.identity.chat_id or "",
                current_user_message_id=accepted.identity.user_message_id or "",
                current_question=command.question,
            )
        )

    assert _lifecycle_snapshot(path, command.request_id) == before


def test_committed_received_fails_all_read_and_mutation_paths_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "committed-received.sqlite3"
    store, command = _durable_state(path, "processing")
    _corrupt_request(path, command.request_id, status=RequestStatus.RECEIVED.value)
    before = _lifecycle_snapshot(path, command.request_id)
    completion = _complete(command, "msg-asst-received")
    failure = FailRequest(
        session_id=command.session_id,
        request_id=command.request_id,
        request_fingerprint=command.request_fingerprint,
        attempt_count=1,
        status=RequestStatus.FAILED_RETRYABLE,
        error_class="retryable_dependency",
        last_error_code="retrieval_error",
    )
    context = BoundedContextQuery(
        session_id=command.session_id,
        chat_id=command.chat_id_candidate or "",
        current_user_message_id=command.user_message_id_candidate or "",
        current_question=command.question,
    )

    for operation in (
        lambda: store.begin_request(command),
        lambda: store.complete_request(completion),
        lambda: store.fail_request(failure),
        lambda: store.load_bounded_context(context),
    ):
        with pytest.raises(DurableRowError, match="committed RECEIVED"):
            operation()
        assert _lifecycle_snapshot(path, command.request_id) == before
