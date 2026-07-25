from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Callable

import pytest

from backend_lite.app.adapters.sqlite_store import (
    RequestStateError,
    SQLiteRequestChatStore,
    StoreBusyError,
    StoreDatabaseError,
)
from backend_lite.app.contracts.internal import (
    BeginRequest,
    BoundedContextQuery,
    FailRequest,
    RequestStatus,
    StoredResponse,
)
from backend_lite.tests.integration.test_sqlite_request_store import (
    FixedClock,
    _begin,
    _complete,
    _connect,
    _error_payload,
    _payload,
    _ready,
    _stamps,
)

_RACE_TIMEOUT_SECONDS = 10
_STORE_BUSY_TIMEOUT_MS = 3000


def _store(
    path: Path,
    *,
    busy_timeout_ms: int = _STORE_BUSY_TIMEOUT_MS,
    clock: FixedClock | None = None,
) -> SQLiteRequestChatStore:
    return SQLiteRequestChatStore(
        path,
        clock or FixedClock(),
        busy_timeout_ms=busy_timeout_ms,
    )


def _capture(operation: Callable[[], object]) -> object:
    try:
        return operation()
    except Exception as exc:  # assertions inspect the typed loser below
        return exc


def _race(left: Callable[[], object], right: Callable[[], object]) -> tuple[object, object]:
    barrier = threading.Barrier(3, timeout=5)
    missing = object()
    results: list[object] = [missing, missing]

    def invoke(index: int, operation: Callable[[], object]) -> None:
        try:
            barrier.wait()
            results[index] = _capture(operation)
        except BaseException as exc:
            results[index] = exc

    threads = [
        threading.Thread(
            target=invoke,
            args=(index, operation),
            name=f"sqlite-race-{index}",
        )
        for index, operation in enumerate((left, right))
    ]
    for thread in threads:
        thread.start()
    barrier_failure: BaseException | None = None
    try:
        barrier.wait()
    except threading.BrokenBarrierError as exc:
        barrier_failure = exc
    deadline = monotonic() + _RACE_TIMEOUT_SECONDS
    for thread in threads:
        thread.join(timeout=max(0, deadline - monotonic()))
    alive = [thread.name for thread in threads if thread.is_alive()]
    assert not alive, f"race workers remained alive after timeout: {alive}"
    if barrier_failure is not None:
        raise AssertionError("race workers did not reach the start barrier") from barrier_failure
    assert all(result is not missing for result in results)
    return results[0], results[1]


def _rows(path: Path, table: str) -> list[dict[str, object]]:
    with _connect(path) as connection:
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]


def _data_snapshot(path: Path) -> dict[str, list[dict[str, object]]]:
    return {table: _rows(path, table) for table in ("chats", "analysis_requests", "messages")}


def _assert_one_whole_winner(path: Path, winner: BeginRequest) -> None:
    snapshot = _data_snapshot(path)
    assert [len(snapshot[name]) for name in ("chats", "analysis_requests", "messages")] == [1, 1, 1]
    request = snapshot["analysis_requests"][0]
    chat = snapshot["chats"][0]
    user = snapshot["messages"][0]
    stamps = winner.version_stamps
    assert request["request_id"] == winner.request_id
    assert request["request_fingerprint"] == winner.request_fingerprint
    assert request["chat_id"] == winner.chat_id_candidate
    assert request["user_message_id"] == winner.user_message_id_candidate
    assert request["status"] == RequestStatus.PROCESSING.value
    assert request["attempt_count"] == 1
    assert (
        request["contract_version"],
        request["corpus_version"],
        request["policy_version"],
        request["prompt_version"],
        request["retriever_version"],
        request["generator_mode"],
        request["generator_version"],
    ) == (
        stamps.contract_version,
        stamps.corpus_version,
        stamps.policy_version,
        stamps.prompt_version,
        stamps.retriever_version,
        stamps.generator_mode,
        stamps.generator_version,
    )
    assert (chat["chat_id"], chat["session_id"], chat["title"]) == (
        winner.chat_id_candidate,
        winner.session_id,
        winner.new_chat_title,
    )
    assert (user["message_id"], user["chat_id"], user["role"], user["content_text"]) == (
        winner.user_message_id_candidate,
        winner.chat_id_candidate,
        "user",
        winner.question,
    )


def _assert_command_isolated(path: Path, command: BeginRequest) -> None:
    with _connect(path) as connection:
        request = connection.execute(
            "SELECT * FROM analysis_requests WHERE session_id = ? AND request_id = ?",
            (command.session_id, command.request_id),
        ).fetchone()
        assert request is not None
        chat = connection.execute(
            "SELECT * FROM chats WHERE chat_id = ? AND session_id = ?",
            (command.chat_id_candidate, command.session_id),
        ).fetchone()
        user = connection.execute(
            "SELECT * FROM messages WHERE message_id = ?",
            (command.user_message_id_candidate,),
        ).fetchone()
    assert chat is not None and user is not None
    assert (request["chat_id"], request["user_message_id"], request["request_fingerprint"]) == (
        command.chat_id_candidate,
        command.user_message_id_candidate,
        command.request_fingerprint,
    )
    assert (chat["title"], user["chat_id"], user["content_text"]) == (
        command.new_chat_title,
        command.chat_id_candidate,
        command.question,
    )
    assert (request["corpus_version"], request["policy_version"], request["generator_version"]) == (
        command.version_stamps.corpus_version,
        command.version_stamps.policy_version,
        command.version_stamps.generator_version,
    )


def _accepted_winner(
    results: tuple[object, object], left: BeginRequest, right: BeginRequest
) -> BeginRequest:
    accepted = [result for result in results if getattr(result, "kind", None) == "accepted"]
    assert len(accepted) == 1
    request_id = accepted[0].identity.request_id  # type: ignore[union-attr]
    return left if left.request_id == request_id else right


def _retryable_failure(command: BeginRequest) -> FailRequest:
    return FailRequest(
        session_id=command.session_id,
        request_id=command.request_id,
        request_fingerprint=command.request_fingerprint,
        attempt_count=1,
        status=RequestStatus.FAILED_RETRYABLE,
        error_class="retryable_dependency",
        last_error_code="retrieval_error",
        error_details_redacted={"operation": "retrieval"},
    )


def _final_failure(command: BeginRequest) -> FailRequest:
    return FailRequest(
        session_id=command.session_id,
        request_id=command.request_id,
        request_fingerprint=command.request_fingerprint,
        attempt_count=1,
        status=RequestStatus.FAILED_FINAL,
        error_class="final_deterministic",
        last_error_code="internal_error",
        response_payload=_error_payload(command.request_id),
    )


def _assert_write_lock_available(path: Path) -> None:
    connection = sqlite3.connect(path, timeout=0)
    try:
        connection.execute("BEGIN IMMEDIATE")
        assert connection.in_transaction
        connection.rollback()
    finally:
        connection.close()


def _start_lock_holder(
    path: Path, mutation: Callable[[sqlite3.Connection], None] | None = None
) -> tuple[threading.Event, threading.Event, threading.Thread, list[BaseException]]:
    acquired = threading.Event()
    release = threading.Event()
    failures: list[BaseException] = []

    def hold() -> None:
        connection = _connect(path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            if mutation is not None:
                mutation(connection)
            assert connection.in_transaction
            acquired.set()
            if not release.wait(timeout=10):
                raise AssertionError("lock holder release timed out")
            assert connection.in_transaction
            connection.rollback()
        except BaseException as exc:
            failures.append(exc)
            acquired.set()
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    thread = threading.Thread(target=hold, name="sqlite-lock-holder")
    thread.start()
    if not acquired.wait(timeout=5) or failures:
        release.set()
        thread.join(timeout=5)
        assert not thread.is_alive(), "failed lock holder setup left a live thread"
        assert not failures, failures
        raise AssertionError("lock holder did not acquire BEGIN IMMEDIATE")
    return acquired, release, thread, failures


def _release_lock(
    release: threading.Event, thread: threading.Thread, failures: list[BaseException]
) -> None:
    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive(), "lock holder did not stop"
    assert not failures


def _forced_serialized_pair(
    *,
    winner_store: SQLiteRequestChatStore,
    winner_checkpoint: str,
    winner_call: Callable[[], object],
    loser_store: SQLiteRequestChatStore,
    loser_call: Callable[[], object],
) -> tuple[object, object]:
    winner_paused = threading.Event()
    release_winner = threading.Event()
    loser_before_begin = threading.Event()
    allow_loser_begin = threading.Event()
    loser_after_begin = threading.Event()
    results: list[object] = []

    def winner_hook(name: str) -> None:
        if name != winner_checkpoint:
            return
        winner_paused.set()
        if not release_winner.wait(timeout=5):
            raise AssertionError("winner checkpoint release timed out")

    def loser_hook(name: str) -> None:
        if name == "before_begin_immediate":
            loser_before_begin.set()
            if not allow_loser_begin.wait(timeout=5):
                raise AssertionError("loser begin release timed out")
        elif name == "after_begin_immediate":
            loser_after_begin.set()

    winner_store._checkpoint = winner_hook  # type: ignore[method-assign]  # noqa: SLF001
    loser_store._checkpoint = loser_hook  # type: ignore[method-assign]  # noqa: SLF001
    winner = threading.Thread(
        target=lambda: results.append(_capture(winner_call)),
        name="forced-winner",
    )
    loser = threading.Thread(
        target=lambda: results.append(_capture(loser_call)),
        name="forced-loser",
    )
    winner.start()
    try:
        assert winner_paused.wait(timeout=5), "winner did not reach in-transaction checkpoint"
        loser.start()
        assert loser_before_begin.wait(timeout=5), "loser did not reach BEGIN IMMEDIATE"
        allow_loser_begin.set()
        assert not loser_after_begin.wait(timeout=0.1), "loser acquired lock before winner commit"
    finally:
        allow_loser_begin.set()
        release_winner.set()
        winner.join(timeout=5)
        if loser.ident is not None:
            loser.join(timeout=5)
    assert not winner.is_alive() and not loser.is_alive(), "forced race left a live worker"
    assert loser_after_begin.is_set(), "loser did not acquire lock after winner commit"
    assert len(results) == 2
    return results[0], results[1]


def test_connection_policy_is_explicit_and_per_connection(tmp_path: Path) -> None:
    path = tmp_path / "connection-policy.sqlite3"
    _ready(path)
    first = _store(path, busy_timeout_ms=137)
    second = _store(path, busy_timeout_ms=241)
    first_connection = first._connect()  # noqa: SLF001 - direct connection-policy control
    second_connection = second._connect()  # noqa: SLF001 - direct connection-policy control
    try:
        assert first_connection is not second_connection
        assert first_connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert second_connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert first_connection.execute("PRAGMA busy_timeout").fetchone()[0] == 137
        assert second_connection.execute("PRAGMA busy_timeout").fetchone()[0] == 241
    finally:
        first_connection.close()
        second_connection.close()


@pytest.mark.parametrize("value", [True, False, 1.5, "100", None])
def test_busy_timeout_rejects_bool_and_non_integer(tmp_path: Path, value: object) -> None:
    path = tmp_path / "invalid-busy-timeout.sqlite3"
    _ready(path)
    with pytest.raises(TypeError, match="busy_timeout_ms"):
        SQLiteRequestChatStore(path, FixedClock(), busy_timeout_ms=value)  # type: ignore[arg-type]


def test_busy_timeout_rejects_negative_and_zero_is_immediate_typed_busy(tmp_path: Path) -> None:
    path = tmp_path / "zero-busy-timeout.sqlite3"
    _ready(path)
    with pytest.raises(ValueError, match="non-negative"):
        SQLiteRequestChatStore(path, FixedClock(), busy_timeout_ms=-1)
    before = _data_snapshot(path)
    _, release, thread, failures = _start_lock_holder(path)
    store = _store(path, busy_timeout_ms=0)
    try:
        connection = store._connect()  # noqa: SLF001 - exact internal PRAGMA control
        try:
            assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 0
        finally:
            connection.close()
        with pytest.raises(StoreBusyError):
            store.begin_request(_begin("zero-timeout", digest="9" * 64))
        assert _data_snapshot(path) == before
    finally:
        _release_lock(release, thread, failures)


def test_concurrent_begin_same_carrier_same_fingerprint_same_candidates(tmp_path: Path) -> None:
    path = tmp_path / "begin-same-candidates.sqlite3"
    _ready(path)
    command = _begin("same-candidates")
    left_store, right_store = _store(path), _store(path)

    results = _race(
        lambda: left_store.begin_request(command),
        lambda: right_store.begin_request(command),
    )

    assert sorted(getattr(result, "kind", None) for result in results) == ["accepted", "in_progress"]
    accepted = next(result for result in results if result.kind == "accepted")  # type: ignore[union-attr]
    loser = next(result for result in results if result.kind == "in_progress")  # type: ignore[union-attr]
    assert loser.identity == accepted.identity  # type: ignore[union-attr]
    _assert_one_whole_winner(path, command)
    _assert_write_lock_available(path)


def test_forced_overlap_begin_loser_waits_for_committed_winner(tmp_path: Path) -> None:
    path = tmp_path / "forced-begin-overlap.sqlite3"
    _ready(path)
    command = _begin("forced-begin", digest="a" * 64)
    winner_store, loser_store = _store(path), _store(path)

    results = _forced_serialized_pair(
        winner_store=winner_store,
        winner_checkpoint="after_user_before_commit",
        winner_call=lambda: winner_store.begin_request(command),
        loser_store=loser_store,
        loser_call=lambda: loser_store.begin_request(command),
    )

    assert sorted(getattr(result, "kind", None) for result in results) == ["accepted", "in_progress"]
    accepted = next(result for result in results if result.kind == "accepted")  # type: ignore[union-attr]
    loser = next(result for result in results if result.kind == "in_progress")  # type: ignore[union-attr]
    assert loser.identity == accepted.identity  # type: ignore[union-attr]
    _assert_one_whole_winner(path, command)


def test_concurrent_begin_same_carrier_same_fingerprint_different_candidates(tmp_path: Path) -> None:
    path = tmp_path / "begin-different-candidates.sqlite3"
    _ready(path)
    left = _begin("candidate-left", digest="b" * 64)
    right = _begin("candidate-right", digest="b" * 64).model_copy(
        update={
            "question": left.question,
            "request_fingerprint": left.request_fingerprint,
            "version_stamps": _stamps().model_copy(
                update={"corpus_version": "loser-or-winner-distinct-version"}
            ),
        }
    )

    results = _race(
        lambda: _store(path).begin_request(left),
        lambda: _store(path).begin_request(right),
    )

    assert sorted(getattr(result, "kind", None) for result in results) == ["accepted", "in_progress"]
    winner = _accepted_winner(results, left, right)
    loser_result = next(result for result in results if result.kind == "in_progress")  # type: ignore[union-attr]
    assert loser_result.identity.request_id == winner.request_id  # type: ignore[union-attr]
    assert loser_result.identity.chat_id == winner.chat_id_candidate  # type: ignore[union-attr]
    assert loser_result.identity.user_message_id == winner.user_message_id_candidate  # type: ignore[union-attr]
    _assert_one_whole_winner(path, winner)


def test_concurrent_begin_same_carrier_different_fingerprint_has_one_reused_loser(
    tmp_path: Path,
) -> None:
    path = tmp_path / "begin-different-fingerprint.sqlite3"
    _ready(path)
    left = _begin("fingerprint-left", digest="c" * 64, fingerprint="1" * 64)
    right = _begin("fingerprint-right", digest="c" * 64, fingerprint="2" * 64)

    results = _race(
        lambda: _store(path).begin_request(left),
        lambda: _store(path).begin_request(right),
    )

    assert sorted(getattr(result, "kind", None) for result in results) == ["accepted", "duplicate"]
    duplicate = next(result for result in results if result.kind == "duplicate")  # type: ignore[union-attr]
    assert duplicate.stored_response.error_code == "IDEMPOTENCY_KEY_REUSED"  # type: ignore[union-attr]
    winner = _accepted_winner(results, left, right)
    assert duplicate.identity.request_id == winner.request_id  # type: ignore[union-attr]
    _assert_one_whole_winner(path, winner)


def test_same_digest_in_different_sessions_does_not_conflict(tmp_path: Path) -> None:
    path = tmp_path / "cross-session.sqlite3"
    _ready(path)
    digest = "d" * 64
    left = _begin("session-left", session_id="session-left", digest=digest)
    right = _begin("session-right", session_id="session-right", digest=digest)

    results = _race(
        lambda: _store(path).begin_request(left),
        lambda: _store(path).begin_request(right),
    )

    assert [getattr(result, "kind", None) for result in results].count("accepted") == 2
    snapshot = _data_snapshot(path)
    assert [len(snapshot[name]) for name in ("chats", "analysis_requests", "messages")] == [2, 2, 2]
    assert {row["session_id"] for row in snapshot["analysis_requests"]} == {
        "session-left",
        "session-right",
    }
    assert {row["attempt_count"] for row in snapshot["analysis_requests"]} == {1}
    accepted_by_session = {result.identity.session_id: result for result in results}  # type: ignore[union-attr]
    assert accepted_by_session["session-left"].identity.request_id == left.request_id
    assert accepted_by_session["session-right"].identity.request_id == right.request_id
    _assert_command_isolated(path, left)
    _assert_command_isolated(path, right)


def test_concurrent_retry_increments_once_and_never_creates_user(tmp_path: Path) -> None:
    path = tmp_path / "retry-race.sqlite3"
    started_at = datetime(2026, 7, 14, 0, tzinfo=timezone.utc)
    failed_at = datetime(2026, 7, 14, 0, 1, tzinfo=timezone.utc)
    retry_left_at = datetime(2026, 7, 14, 0, 2, tzinfo=timezone.utc)
    retry_right_at = datetime(2026, 7, 14, 0, 3, tzinfo=timezone.utc)
    seed = _ready(path, FixedClock(started_at, failed_at))
    command = _begin("retry-race", digest="e" * 64)
    accepted = seed.begin_request(command)
    seed.fail_request(_retryable_failure(command))
    original_ids = (
        accepted.identity.request_id,
        accepted.identity.chat_id,
        accepted.identity.user_message_id,
    )

    results = _race(
        lambda: _store(path, clock=FixedClock(retry_left_at)).begin_request(command),
        lambda: _store(path, clock=FixedClock(retry_right_at)).begin_request(command),
    )

    assert sorted(getattr(result, "kind", None) for result in results) == ["in_progress", "retry"]
    row = _rows(path, "analysis_requests")[0]
    messages = _rows(path, "messages")
    assert (row["request_id"], row["chat_id"], row["user_message_id"]) == original_ids
    assert row["status"] == RequestStatus.PROCESSING.value
    assert row["attempt_count"] == 2
    assert row["assistant_message_id"] is None
    assert row["response_payload"] is None
    assert row["failed_at"] is None
    assert row["error_class"] is None
    assert row["last_error_code"] is None
    assert row["error_details_json"] is None
    assert row["processing_started_at"] == row["updated_at"]
    assert row["processing_started_at"] in {
        retry_left_at.isoformat(timespec="microseconds"),
        retry_right_at.isoformat(timespec="microseconds"),
    }
    assert row["processing_started_at"] != started_at.isoformat(timespec="microseconds")
    assert [message["role"] for message in messages] == ["user"]


def test_forced_overlap_retry_loser_sees_new_attempt_only(tmp_path: Path) -> None:
    path = tmp_path / "forced-retry-overlap.sqlite3"
    seed = _ready(path)
    command = _begin("forced-retry", digest="e" * 64)
    seed.begin_request(command)
    seed.fail_request(_retryable_failure(command))
    winner_store, loser_store = _store(path), _store(path)

    results = _forced_serialized_pair(
        winner_store=winner_store,
        winner_checkpoint="after_retry_update_before_commit",
        winner_call=lambda: winner_store.begin_request(command),
        loser_store=loser_store,
        loser_call=lambda: loser_store.begin_request(command),
    )

    assert sorted(getattr(result, "kind", None) for result in results) == ["in_progress", "retry"]
    row = _rows(path, "analysis_requests")[0]
    assert (row["status"], row["attempt_count"], len(_rows(path, "messages"))) == (
        RequestStatus.PROCESSING.value,
        2,
        1,
    )


def test_concurrent_identical_completion_replays_one_stored_response(tmp_path: Path) -> None:
    path = tmp_path / "completion-same.sqlite3"
    started_at = datetime(2026, 7, 14, 1, tzinfo=timezone.utc)
    completed_left_at = datetime(2026, 7, 14, 1, 1, tzinfo=timezone.utc)
    completed_right_at = datetime(2026, 7, 14, 1, 2, tzinfo=timezone.utc)
    seed = _ready(path, FixedClock(started_at))
    command = _begin("completion-same", digest="f" * 64)
    seed.begin_request(command)
    completion = _complete(command, "msg-asst-completion-same")

    results = _race(
        lambda: _store(path, clock=FixedClock(completed_left_at)).complete_request(completion),
        lambda: _store(path, clock=FixedClock(completed_right_at)).complete_request(completion),
    )

    assert all(isinstance(result, StoredResponse) for result in results)
    assert results[0] == results[1]
    request = _rows(path, "analysis_requests")[0]
    messages = _rows(path, "messages")
    assert request["status"] == RequestStatus.COMPLETE.value
    assert request["assistant_message_id"] == "msg-asst-completion-same"
    assert json.loads(request["response_payload"]) == completion.response_payload
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assistant = next(message for message in messages if message["role"] == "assistant")
    chat = _rows(path, "chats")[0]
    assert request["completed_at"] == request["updated_at"] == assistant["created_at"] == chat["updated_at"]
    assert assistant["created_at"] in {
        completed_left_at.isoformat(timespec="microseconds"),
        completed_right_at.isoformat(timespec="microseconds"),
    }
    content = {
        key: value
        for key, value in completion.response_payload.items()
        if key not in {"contract_version", "request_id", "chat_id", "user_message_id", "assistant_message_id"}
    }
    # AnalyzeContent's additive `response_kind` field (Gate C) is not in the durable
    # store's own _CONTENT_KEYS extraction, so it always falls back to its "legal"
    # default when persisted here -- this adapter has no social-turn concept.
    content["response_kind"] = "legal"
    assert json.loads(assistant["content_json"]) == content


def test_forced_overlap_completion_loser_replays_after_commit(tmp_path: Path) -> None:
    path = tmp_path / "forced-completion-overlap.sqlite3"
    seed = _ready(path)
    command = _begin("forced-completion", digest="f" * 64)
    seed.begin_request(command)
    completion = _complete(command, "msg-asst-forced-completion")
    winner_store, loser_store = _store(path), _store(path)

    results = _forced_serialized_pair(
        winner_store=winner_store,
        winner_checkpoint="after_response_update_before_commit",
        winner_call=lambda: winner_store.complete_request(completion),
        loser_store=loser_store,
        loser_call=lambda: loser_store.complete_request(completion),
    )

    assert all(isinstance(result, StoredResponse) for result in results)
    assert results[0] == results[1]
    assert len([row for row in _rows(path, "messages") if row["role"] == "assistant"]) == 1


@pytest.mark.parametrize("variant", ["different-assistant", "different-payload"])
def test_conflicting_concurrent_completion_never_overwrites_winner(
    tmp_path: Path, variant: str
) -> None:
    path = tmp_path / f"completion-conflict-{variant}.sqlite3"
    seed = _ready(path)
    command = _begin(f"completion-conflict-{variant}", digest="0" * 64)
    seed.begin_request(command)
    left = _complete(command, "msg-asst-left")
    if variant == "different-assistant":
        right = _complete(command, "msg-asst-right")
    else:
        changed_payload = dict(left.response_payload)
        changed_payload["summary"] = "Nội dung khác nhưng vẫn hợp lệ."
        right = left.model_copy(update={"response_payload": changed_payload})

    results = _race(
        lambda: _store(path).complete_request(left),
        lambda: _store(path).complete_request(right),
    )

    assert sum(isinstance(result, StoredResponse) for result in results) == 1
    assert sum(isinstance(result, RequestStateError) for result in results) == 1
    stored = next(result for result in results if isinstance(result, StoredResponse))
    request = _rows(path, "analysis_requests")[0]
    messages = _rows(path, "messages")
    assert request["status"] == RequestStatus.COMPLETE.value
    assert request["assistant_message_id"] == stored.assistant_message_id
    assert json.loads(request["response_payload"]) == stored.response_payload
    assistants = [message for message in messages if message["role"] == "assistant"]
    assert len(assistants) == 1
    assert assistants[0]["message_id"] == stored.assistant_message_id
    assert request["completed_at"] == request["updated_at"] == assistants[0]["created_at"]
    assert _rows(path, "chats")[0]["updated_at"] == assistants[0]["created_at"]
    stored_content = {
        key: value
        for key, value in (stored.response_payload or {}).items()
        if key not in {"contract_version", "request_id", "chat_id", "user_message_id", "assistant_message_id"}
    }
    # AnalyzeContent's additive `response_kind` field (Gate C) is not in the durable
    # store's own _CONTENT_KEYS extraction, so it always falls back to its "legal"
    # default when persisted here -- this adapter has no social-turn concept.
    stored_content["response_kind"] = "legal"
    assert json.loads(assistants[0]["content_json"]) == stored_content


@pytest.mark.parametrize("failure_kind", ["retryable", "final"])
def test_concurrent_complete_versus_fail_has_one_coherent_terminal_winner(
    tmp_path: Path, failure_kind: str
) -> None:
    path = tmp_path / f"complete-versus-{failure_kind}.sqlite3"
    seed = _ready(path)
    command = _begin(f"complete-versus-{failure_kind}", digest="1" * 64)
    seed.begin_request(command)
    completion = _complete(command, f"msg-asst-{failure_kind}")
    failure = _retryable_failure(command) if failure_kind == "retryable" else _final_failure(command)

    results = _race(
        lambda: _store(path).complete_request(completion),
        lambda: _store(path).fail_request(failure),
    )

    assert sum(isinstance(result, RequestStateError) for result in results) == 1
    row = _rows(path, "analysis_requests")[0]
    assistants = [message for message in _rows(path, "messages") if message["role"] == "assistant"]
    if row["status"] == RequestStatus.COMPLETE.value:
        assert len(assistants) == 1
        assert row["assistant_message_id"] == assistants[0]["message_id"]
        assert row["response_payload"] is not None
        assert row["completed_at"] is not None
        assert row["failed_at"] is None
        assert row["error_class"] is None
        assert row["last_error_code"] is None
        assert row["error_details_json"] is None
    else:
        assert row["status"] == failure.status.value
        assert assistants == []
        assert row["assistant_message_id"] is None
        assert row["completed_at"] is None
        assert row["failed_at"] is not None
        assert row["error_class"] == failure.error_class
        assert row["last_error_code"] == failure.last_error_code
        assert (row["response_payload"] is not None) is (failure_kind == "final")
        if failure_kind == "final":
            assert json.loads(row["response_payload"]) == failure.response_payload
        else:
            assert row["response_payload"] is None


@pytest.mark.parametrize("operation", ["begin", "complete", "fail"])
def test_explicit_busy_timeout_is_typed_zero_mutation_and_manually_retryable(
    tmp_path: Path, operation: str
) -> None:
    path = tmp_path / f"busy-{operation}.sqlite3"
    seed = _ready(path)
    command = _begin(f"busy-{operation}", digest="2" * 64)
    if operation != "begin":
        seed.begin_request(command)
    completion = _complete(command, "msg-asst-busy")
    failure = _retryable_failure(command)

    def call(store: SQLiteRequestChatStore) -> object:
        if operation == "begin":
            return store.begin_request(command)
        if operation == "complete":
            return store.complete_request(completion)
        return store.fail_request(failure)
    before = _data_snapshot(path)
    _, release, thread, failures = _start_lock_holder(path)
    busy_store = _store(path, busy_timeout_ms=60)
    started = monotonic()
    try:
        with pytest.raises(StoreBusyError, match="lock timed out") as caught:
            call(busy_store)
        elapsed = monotonic() - started
        assert caught.value.__cause__ is None
        assert caught.value.__suppress_context__ is True
        assert elapsed < 2
        assert _data_snapshot(path) == before
    finally:
        _release_lock(release, thread, failures)

    call(busy_store)
    _assert_write_lock_available(path)


@pytest.mark.parametrize(
    ("operation", "checkpoint"),
    [
        ("begin", "after_user_before_commit"),
        ("complete", "after_response_update_before_commit"),
        ("fail", "during_failure_update_before_commit"),
    ],
)
def test_commit_time_busy_rolls_back_active_transaction_without_partial_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str, checkpoint: str
) -> None:
    path = tmp_path / f"commit-busy-{operation}.sqlite3"
    seed = _ready(path)
    command = _begin(f"commit-busy-{operation}", digest="8" * 64)
    if operation != "begin":
        seed.begin_request(command)
    completion = _complete(command, "msg-asst-commit-busy")
    failure = _retryable_failure(command)

    def call(store: SQLiteRequestChatStore) -> object:
        if operation == "begin":
            return store.begin_request(command)
        if operation == "complete":
            return store.complete_request(completion)
        return store.fail_request(failure)

    before = _data_snapshot(path)
    mutation_ready = threading.Event()
    continue_to_commit = threading.Event()
    store = _store(path, busy_timeout_ms=60)

    def pause_at_checkpoint(name: str) -> None:
        if name != checkpoint:
            return
        mutation_ready.set()
        if not continue_to_commit.wait(timeout=5):
            raise AssertionError("writer checkpoint release timed out")

    monkeypatch.setattr(store, "_checkpoint", pause_at_checkpoint)
    result: list[object] = []
    writer = threading.Thread(
        target=lambda: result.append(_capture(lambda: call(store))),
        name=f"commit-busy-writer-{operation}",
    )
    writer.start()
    assert mutation_ready.wait(timeout=5), "writer did not reach post-mutation checkpoint"

    reader = _connect(path)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM analysis_requests").fetchall()
        assert reader.in_transaction
        continue_to_commit.set()
        writer.join(timeout=3)
        assert not writer.is_alive(), "writer did not finish after bounded commit busy timeout"
        assert len(result) == 1 and isinstance(result[0], StoreBusyError)
        assert result[0].__suppress_context__ is True  # type: ignore[union-attr]
        assert reader.in_transaction
    finally:
        continue_to_commit.set()
        reader.rollback()
        reader.close()
        writer.join(timeout=3)
    assert not writer.is_alive()
    assert _data_snapshot(path) == before

    call(store)
    _assert_write_lock_available(path)


def test_non_busy_operational_error_is_not_misclassified_as_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "non-busy.sqlite3"
    _ready(path)
    store = _store(path)

    class BrokenConnection:
        in_transaction = False
        closed = False

        def execute(self, _sql: str) -> None:
            raise sqlite3.OperationalError("near BROKEN: syntax error")

        def close(self) -> None:
            self.closed = True

    broken = BrokenConnection()
    monkeypatch.setattr(store, "_connect", lambda: broken)
    with pytest.raises(StoreDatabaseError) as caught:
        store.begin_request(_begin("non-busy", digest="3" * 64))
    assert not isinstance(caught.value, StoreBusyError)
    assert broken.closed


def test_bounded_context_reads_committed_snapshot_under_begin_immediate_writer(
    tmp_path: Path,
) -> None:
    path = tmp_path / "context-under-writer.sqlite3"
    seed = _ready(path)
    first = _begin("context-writer-first", digest="4" * 64)
    first_result = seed.begin_request(first)
    seed.complete_request(
        _complete(first, "msg-asst-context-writer", confirmed_topic="committed-topic")
    )
    second = _begin(
        "context-writer-second",
        requested_chat_id=first_result.identity.chat_id,
        digest="5" * 64,
    )
    second_result = seed.begin_request(second)
    before = _data_snapshot(path)

    uncommitted_content = {
        key: value
        for key, value in _payload(first, "msg-asst-context-writer", confirmed_topic="uncommitted-topic").items()
        if key not in {"contract_version", "request_id", "chat_id", "user_message_id", "assistant_message_id"}
    }

    def mutate(connection: sqlite3.Connection) -> None:
        connection.execute(
            "UPDATE messages SET content_json = ? WHERE message_id = ?",
            (
                json.dumps(uncommitted_content, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                "msg-asst-context-writer",
            ),
        )

    _, release, thread, failures = _start_lock_holder(path, mutate)
    try:
        context = _store(path, busy_timeout_ms=200).load_bounded_context(
            BoundedContextQuery(
                session_id=second.session_id,
                chat_id=second_result.identity.chat_id or "",
                current_user_message_id=second_result.identity.user_message_id or "",
                current_question=second.question,
            )
        )
        assert context.last_confirmed_topic == "committed-topic"
        assert _data_snapshot(path) == before
    finally:
        _release_lock(release, thread, failures)
    assert _data_snapshot(path) == before


def test_duplicate_reuse_replay_mismatch_and_injected_failure_release_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cleanup-paths.sqlite3"
    store = _ready(path)
    processing = _begin("cleanup-processing", digest="6" * 64)
    store.begin_request(processing)
    assert store.begin_request(processing).kind == "in_progress"
    changed = processing.model_copy(update={"request_fingerprint": "9" * 64})
    assert store.begin_request(changed).stored_response.error_code == "IDEMPOTENCY_KEY_REUSED"
    _assert_write_lock_available(path)

    store.fail_request(_retryable_failure(processing))
    assert store.begin_request(processing).kind == "retry"
    completion = _complete(processing, "msg-asst-cleanup").model_copy(update={"attempt_count": 2})
    store.complete_request(completion)
    assert store.begin_request(processing).kind == "duplicate"
    assert store.complete_request(completion).status is RequestStatus.COMPLETE
    with pytest.raises(RequestStateError):
        store.complete_request(
            _complete(processing, "different").model_copy(update={"attempt_count": 2})
        )
    _assert_write_lock_available(path)

    collision = _begin(
        "cleanup-collision",
        requested_chat_id=processing.chat_id_candidate,
        digest="a" * 64,
    )
    store.begin_request(collision)
    with pytest.raises(RequestStateError, match="already in use"):
        store.complete_request(_complete(collision, "msg-asst-cleanup"))
    _assert_write_lock_available(path)

    injected = _begin("cleanup-injected", digest="7" * 64)
    monkeypatch.setattr(
        store,
        "_checkpoint",
        lambda name: (_ for _ in ()).throw(RuntimeError("injected"))
        if name == "after_user_before_commit"
        else None,
    )
    with pytest.raises(RuntimeError, match="injected"):
        store.begin_request(injected)
    _assert_write_lock_available(path)


def test_bounded_stress_begin_retry_and_completion_races(tmp_path: Path) -> None:
    for iteration in range(20):
        begin_path = tmp_path / f"stress-begin-{iteration}.sqlite3"
        _ready(begin_path)
        begin = _begin(f"stress-begin-{iteration}", digest=f"{iteration:064x}")
        begin_results = _race(
            lambda path=begin_path, command=begin: _store(path).begin_request(command),
            lambda path=begin_path, command=begin: _store(path).begin_request(command),
        )
        assert sorted(getattr(result, "kind", None) for result in begin_results) == [
            "accepted",
            "in_progress",
        ]
        assert [len(_rows(begin_path, table)) for table in ("analysis_requests", "messages")] == [1, 1]

        retry_path = tmp_path / f"stress-retry-{iteration}.sqlite3"
        retry_seed = _ready(retry_path)
        retry = _begin(f"stress-retry-{iteration}", digest=f"{iteration + 100:064x}")
        retry_seed.begin_request(retry)
        retry_seed.fail_request(_retryable_failure(retry))
        retry_results = _race(
            lambda path=retry_path, command=retry: _store(path).begin_request(command),
            lambda path=retry_path, command=retry: _store(path).begin_request(command),
        )
        assert sorted(getattr(result, "kind", None) for result in retry_results) == [
            "in_progress",
            "retry",
        ]
        retry_row = _rows(retry_path, "analysis_requests")[0]
        assert (retry_row["status"], retry_row["attempt_count"], len(_rows(retry_path, "messages"))) == (
            RequestStatus.PROCESSING.value,
            2,
            1,
        )

        complete_path = tmp_path / f"stress-complete-{iteration}.sqlite3"
        complete_seed = _ready(complete_path)
        complete = _begin(f"stress-complete-{iteration}", digest=f"{iteration + 200:064x}")
        complete_seed.begin_request(complete)
        completion = _complete(complete, f"msg-asst-stress-{iteration}")
        complete_results = _race(
            lambda path=complete_path, command=completion: _store(path).complete_request(command),
            lambda path=complete_path, command=completion: _store(path).complete_request(command),
        )
        assert all(isinstance(result, StoredResponse) for result in complete_results)
        complete_row = _rows(complete_path, "analysis_requests")[0]
        assert (complete_row["status"], len(_rows(complete_path, "messages"))) == (
            RequestStatus.COMPLETE.value,
            2,
        )
