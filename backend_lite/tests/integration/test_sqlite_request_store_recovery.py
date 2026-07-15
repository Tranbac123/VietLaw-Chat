from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend_lite.app.adapters.sqlite_store import (
    DurableRowError,
    MAX_ATTEMPTS,
    PROCESSING_TIMEOUT_SECONDS,
    RequestStateError,
    SQLiteRequestChatStore,
    StoreBusyError,
)
from backend_lite.app.contracts.internal import (
    BeginRequest,
    BeginRequestAttemptsExhausted,
    BoundedContextQuery,
    CompleteRequest,
    FailRequest,
    RequestStatus,
)
from backend_lite.tests.integration.test_sqlite_request_store import (
    FixedClock,
    _begin,
    _complete,
    _connect,
    _corrupt_request,
    _error_payload,
    _ready,
)
from backend_lite.tests.integration.test_sqlite_request_store_concurrency import (
    _assert_write_lock_available,
    _capture,
    _data_snapshot,
    _forced_serialized_pair,
    _race,
    _release_lock,
    _start_lock_holder,
)


_START = datetime(2026, 7, 15, 1, tzinfo=timezone.utc)
_TIMEOUT = timedelta(seconds=PROCESSING_TIMEOUT_SECONDS)


def _store(
    path: Path,
    at: datetime,
    *,
    busy_timeout_ms: int = 3000,
    processing_timeout_seconds: int = PROCESSING_TIMEOUT_SECONDS,
    max_attempts: int = MAX_ATTEMPTS,
) -> SQLiteRequestChatStore:
    return SQLiteRequestChatStore(
        path,
        FixedClock(at),
        busy_timeout_ms=busy_timeout_ms,
        processing_timeout_seconds=processing_timeout_seconds,
        max_attempts=max_attempts,
    )


def _seed(path: Path, suffix: str = "recovery") -> tuple[BeginRequest, datetime]:
    store = _ready(path, FixedClock(_START))
    command = _begin(suffix, digest=(suffix[0].encode().hex()[0] * 64))
    result = store.begin_request(command)
    assert result.kind == "accepted"
    return command, _START + _TIMEOUT


def _row(path: Path, request_id: str) -> dict[str, object]:
    with _connect(path) as connection:
        return dict(
            connection.execute(
                "SELECT * FROM analysis_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
        )


def _completion(command: BeginRequest, attempt: int, assistant_id: str) -> CompleteRequest:
    return _complete(command, assistant_id).model_copy(update={"attempt_count": attempt})


def _failure(command: BeginRequest, attempt: int, status: RequestStatus) -> FailRequest:
    values: dict[str, object] = {
        "session_id": command.session_id,
        "request_id": command.request_id,
        "request_fingerprint": command.request_fingerprint,
        "attempt_count": attempt,
        "status": status,
        "error_class": "retryable_dependency"
        if status is RequestStatus.FAILED_RETRYABLE
        else "final_deterministic",
        "last_error_code": "retrieval_error"
        if status is RequestStatus.FAILED_RETRYABLE
        else "internal_error",
    }
    if status is RequestStatus.FAILED_FINAL:
        values["response_payload"] = _error_payload(command.request_id)
    return FailRequest.model_validate(values)


def _advance_to_attempt(
    path: Path, command: BeginRequest, deadline: datetime, target: int
) -> datetime:
    for expected in range(2, target + 1):
        result = _store(path, deadline).begin_request(command)
        assert result.kind == "retry"
        assert result.identity.attempt_count == expected
        deadline += _TIMEOUT
    return deadline


@pytest.mark.parametrize(
    ("name", "value", "error"),
    [
        ("processing_timeout_seconds", True, TypeError),
        ("processing_timeout_seconds", 1.5, TypeError),
        ("processing_timeout_seconds", 0, ValueError),
        ("processing_timeout_seconds", -1, ValueError),
        ("max_attempts", False, TypeError),
        ("max_attempts", "3", TypeError),
        ("max_attempts", 0, ValueError),
        ("max_attempts", -1, ValueError),
    ],
)
def test_recovery_configuration_rejects_invalid_values(
    tmp_path: Path, name: str, value: object, error: type[Exception]
) -> None:
    with pytest.raises(error):
        SQLiteRequestChatStore(tmp_path / "unused.sqlite3", FixedClock(), **{name: value})


def test_default_and_explicit_fixed_recovery_policy_are_accepted_without_db_access(
    tmp_path: Path,
) -> None:
    missing_default = tmp_path / "missing-default.sqlite3"
    missing_explicit = tmp_path / "missing-explicit.sqlite3"
    default = SQLiteRequestChatStore(missing_default, FixedClock())
    explicit = SQLiteRequestChatStore(
        missing_explicit,
        FixedClock(),
        processing_timeout_seconds=PROCESSING_TIMEOUT_SECONDS,
        max_attempts=MAX_ATTEMPTS,
    )
    assert default._processing_timeout == _TIMEOUT  # noqa: SLF001 - fixed-policy control
    assert default._max_attempts == MAX_ATTEMPTS  # noqa: SLF001 - fixed-policy control
    assert explicit._processing_timeout == _TIMEOUT  # noqa: SLF001 - fixed-policy control
    assert explicit._max_attempts == MAX_ATTEMPTS  # noqa: SLF001 - fixed-policy control
    assert not missing_default.exists() and not missing_explicit.exists()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("processing_timeout_seconds", 60),
        ("processing_timeout_seconds", 119),
        ("processing_timeout_seconds", 121),
        ("max_attempts", 1),
        ("max_attempts", 2),
        ("max_attempts", 4),
    ],
)
def test_incompatible_recovery_policy_is_rejected_before_opening_or_creating_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, value: int
) -> None:
    path = tmp_path / f"incompatible-{name}-{value}.sqlite3"

    def unexpected_connect(*_args: object, **_kwargs: object) -> sqlite3.Connection:
        raise AssertionError("incompatible policy attempted SQLite access")

    monkeypatch.setattr(
        "backend_lite.app.adapters.sqlite_store.sqlite3.connect", unexpected_connect
    )
    with pytest.raises(ValueError, match="fixed"):
        SQLiteRequestChatStore(path, FixedClock(), **{name: value})
    assert not path.exists()


def test_incompatible_policy_cannot_recover_attempt_three_or_create_attempt_four(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mixed-max-policy.sqlite3"
    command, deadline = _seed(path, "mixedmax")
    deadline = _advance_to_attempt(path, command, deadline, MAX_ATTEMPTS)
    before = _data_snapshot(path)

    with pytest.raises(ValueError, match="max_attempts is fixed"):
        _store(path, deadline, max_attempts=4)

    assert _data_snapshot(path) == before
    exhausted = _store(path, deadline).begin_request(command)
    assert isinstance(exhausted, BeginRequestAttemptsExhausted)
    assert exhausted.kind == "attempts_exhausted"
    assert exhausted.identity.attempt_count == MAX_ATTEMPTS
    assert _data_snapshot(path) == before


def test_incompatible_timeout_cannot_open_or_recover_default_policy_row(tmp_path: Path) -> None:
    path = tmp_path / "mixed-timeout-policy.sqlite3"
    command, deadline = _seed(path, "mixedtimeout")
    before = _data_snapshot(path)

    with pytest.raises(ValueError, match="processing_timeout_seconds is fixed"):
        _store(path, deadline, processing_timeout_seconds=60)

    assert _data_snapshot(path) == before
    assert _store(path, deadline).begin_request(command).identity.attempt_count == 2


def test_new_request_has_exact_canonical_120_second_deadline(tmp_path: Path) -> None:
    path = tmp_path / "new-deadline.sqlite3"
    command, _ = _seed(path, "deadline")
    row = _row(path, command.request_id)
    assert row["processing_started_at"] == "2026-07-15T01:00:00.000000+00:00"
    assert row["processing_deadline_at"] == "2026-07-15T01:02:00.000000+00:00"
    assert row["updated_at"] == row["processing_started_at"]


def test_non_stale_duplicate_is_in_progress_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "non-stale.sqlite3"
    command, deadline = _seed(path, "nonstale")
    before = _data_snapshot(path)
    result = _store(path, deadline - timedelta(microseconds=1)).begin_request(command)
    assert result.kind == "in_progress"
    assert result.identity.attempt_count == 1
    assert _data_snapshot(path) == before


@pytest.mark.parametrize("offset", [timedelta(0), timedelta(microseconds=1)])
def test_exact_or_past_deadline_recovers_attempt_one_to_two(
    tmp_path: Path, offset: timedelta
) -> None:
    path = tmp_path / f"deadline-boundary-{offset.microseconds}.sqlite3"
    command, deadline = _seed(path, "boundary")
    result = _store(path, deadline + offset).begin_request(command)
    row = _row(path, command.request_id)
    assert result.kind == "retry" and result.identity.attempt_count == 2
    assert row["attempt_count"] == 2
    expected_start = deadline + offset
    assert row["processing_started_at"] == expected_start.isoformat(timespec="microseconds")
    assert row["processing_deadline_at"] == (expected_start + _TIMEOUT).isoformat(
        timespec="microseconds"
    )
    assert len(_data_snapshot(path)["messages"]) == 1


def test_stale_attempt_two_recovers_to_three_then_exhausts_without_attempt_four(
    tmp_path: Path,
) -> None:
    path = tmp_path / "attempt-three.sqlite3"
    command, deadline = _seed(path, "attempts")
    deadline = _advance_to_attempt(path, command, deadline, 3)
    before = _data_snapshot(path)
    result = _store(path, deadline).begin_request(command)
    assert isinstance(result, BeginRequestAttemptsExhausted)
    assert result.kind == "attempts_exhausted"
    assert result.identity.attempt_count == 3
    assert result.processing_deadline_at == deadline
    assert result.version_stamps == command.version_stamps
    assert _data_snapshot(path) == before


def test_failed_retryable_retries_once_and_attempt_three_exhausts_unchanged(
    tmp_path: Path,
) -> None:
    path = tmp_path / "failed-retryable.sqlite3"
    command, deadline = _seed(path, "failedretry")
    first = _store(path, _START + timedelta(seconds=1))
    first.fail_request(_failure(command, 1, RequestStatus.FAILED_RETRYABLE))
    result = _store(path, _START + timedelta(seconds=2)).begin_request(command)
    assert result.kind == "retry" and result.identity.attempt_count == 2
    row = _row(path, command.request_id)
    assert all(
        row[name] is None
        for name in ("failed_at", "error_class", "last_error_code", "error_details_json")
    )
    deadline = datetime.fromisoformat(str(row["processing_deadline_at"]))
    _store(path, deadline).begin_request(command)
    _store(path, deadline + _TIMEOUT + timedelta(seconds=1)).fail_request(
        _failure(command, 3, RequestStatus.FAILED_RETRYABLE)
    )
    before = _data_snapshot(path)
    exhausted = _store(path, deadline + _TIMEOUT + timedelta(seconds=2)).begin_request(command)
    assert exhausted.kind == "attempts_exhausted"
    assert exhausted.status is RequestStatus.FAILED_RETRYABLE
    assert _data_snapshot(path) == before


@pytest.mark.parametrize("starting_attempt", [1, 2])
def test_two_connection_stale_recovery_has_one_claimant(
    tmp_path: Path, starting_attempt: int
) -> None:
    path = tmp_path / f"recovery-race-{starting_attempt}.sqlite3"
    command, deadline = _seed(path, f"race{starting_attempt}")
    deadline = _advance_to_attempt(path, command, deadline, starting_attempt)
    winner = _store(path, deadline)
    loser = _store(path, deadline)
    results = _forced_serialized_pair(
        winner_store=winner,
        winner_checkpoint="after_recovery_update_before_commit",
        winner_call=lambda: winner.begin_request(command),
        loser_store=loser,
        loser_call=lambda: loser.begin_request(command),
    )
    assert sorted(getattr(result, "kind", type(result).__name__) for result in results) == [
        "in_progress",
        "retry",
    ]
    row = _row(path, command.request_id)
    assert row["attempt_count"] == starting_attempt + 1
    assert len(_data_snapshot(path)["messages"]) == 1
    _assert_write_lock_available(path)


def test_two_connection_attempt_three_is_exhausted_and_zero_mutation(tmp_path: Path) -> None:
    path = tmp_path / "exhausted-race.sqlite3"
    command, deadline = _seed(path, "exhaustedrace")
    deadline = _advance_to_attempt(path, command, deadline, 3)
    before = _data_snapshot(path)
    results = _race(
        lambda: _store(path, deadline).begin_request(command),
        lambda: _store(path, deadline).begin_request(command),
    )
    assert [getattr(result, "kind", None) for result in results] == [
        "attempts_exhausted",
        "attempts_exhausted",
    ]
    assert _data_snapshot(path) == before


def test_recovery_wins_before_old_completion(tmp_path: Path) -> None:
    path = tmp_path / "recovery-before-complete.sqlite3"
    command, deadline = _seed(path, "recoverfirst")
    recovery = _store(path, deadline)
    old_worker = _store(path, deadline)
    results = _forced_serialized_pair(
        winner_store=recovery,
        winner_checkpoint="after_recovery_update_before_commit",
        winner_call=lambda: recovery.begin_request(command),
        loser_store=old_worker,
        loser_call=lambda: old_worker.complete_request(
            _completion(command, 1, "msg-asst-old-rejected")
        ),
    )
    assert any(getattr(result, "kind", None) == "retry" for result in results)
    assert any(isinstance(result, RequestStateError) for result in results)
    row = _row(path, command.request_id)
    assert row["status"] == RequestStatus.PROCESSING.value and row["attempt_count"] == 2
    assert not [m for m in _data_snapshot(path)["messages"] if m["role"] == "assistant"]


def test_old_completion_wins_before_recovery(tmp_path: Path) -> None:
    path = tmp_path / "complete-before-recovery.sqlite3"
    command, deadline = _seed(path, "completefirst")
    completer = _store(path, deadline)
    recovery = _store(path, deadline)
    completion = _completion(command, 1, "msg-asst-complete-winner")
    results = _forced_serialized_pair(
        winner_store=completer,
        winner_checkpoint="after_response_update_before_commit",
        winner_call=lambda: completer.complete_request(completion),
        loser_store=recovery,
        loser_call=lambda: recovery.begin_request(command),
    )
    assert any(getattr(result, "kind", None) == "duplicate" for result in results)
    row = _row(path, command.request_id)
    assert row["status"] == RequestStatus.COMPLETE.value and row["attempt_count"] == 1
    assert len([m for m in _data_snapshot(path)["messages"] if m["role"] == "assistant"]) == 1


@pytest.mark.parametrize("status", [RequestStatus.FAILED_RETRYABLE, RequestStatus.FAILED_FINAL])
def test_recovery_wins_before_old_failure(tmp_path: Path, status: RequestStatus) -> None:
    path = tmp_path / f"recover-before-{status.value}.sqlite3"
    command, deadline = _seed(path, f"recover{status.value}")
    recovery = _store(path, deadline)
    failing = _store(path, deadline)
    results = _forced_serialized_pair(
        winner_store=recovery,
        winner_checkpoint="after_recovery_update_before_commit",
        winner_call=lambda: recovery.begin_request(command),
        loser_store=failing,
        loser_call=lambda: failing.fail_request(_failure(command, 1, status)),
    )
    assert any(getattr(result, "kind", None) == "retry" for result in results)
    assert any(isinstance(result, RequestStateError) for result in results)
    row = _row(path, command.request_id)
    assert (row["status"], row["attempt_count"], row["error_class"]) == (
        RequestStatus.PROCESSING.value,
        2,
        None,
    )


@pytest.mark.parametrize("status", [RequestStatus.FAILED_RETRYABLE, RequestStatus.FAILED_FINAL])
def test_failure_wins_before_recovery_and_next_outcome_is_coherent(
    tmp_path: Path, status: RequestStatus
) -> None:
    path = tmp_path / f"{status.value}-before-recover.sqlite3"
    command, deadline = _seed(path, f"failfirst{status.value}")
    failing = _store(path, deadline)
    recovery = _store(path, deadline)
    results = _forced_serialized_pair(
        winner_store=failing,
        winner_checkpoint="during_failure_update_before_commit",
        winner_call=lambda: failing.fail_request(_failure(command, 1, status)),
        loser_store=recovery,
        loser_call=lambda: recovery.begin_request(command),
    )
    expected = "retry" if status is RequestStatus.FAILED_RETRYABLE else "duplicate"
    assert any(getattr(result, "kind", None) == expected for result in results)
    row = _row(path, command.request_id)
    if status is RequestStatus.FAILED_RETRYABLE:
        assert (row["status"], row["attempt_count"], row["error_class"]) == (
            RequestStatus.PROCESSING.value,
            2,
            None,
        )
    else:
        assert (row["status"], row["attempt_count"]) == (RequestStatus.FAILED_FINAL.value, 1)


def test_crash_after_tx_a_commit_is_recoverable_after_reopen(tmp_path: Path) -> None:
    path = tmp_path / "crash-after-txa.sqlite3"
    command, deadline = _seed(path, "crashtxa")
    assert _store(path, deadline - timedelta(microseconds=1)).begin_request(command).kind == "in_progress"
    recovered = _store(path, deadline).begin_request(command)
    assert recovered.kind == "retry" and recovered.identity.attempt_count == 2


def test_exception_inside_recovery_rolls_back_then_reopen_can_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "crash-during-recovery.sqlite3"
    command, deadline = _seed(path, "crashrecovery")
    before = _data_snapshot(path)
    crashing = _store(path, deadline)

    def crash(name: str) -> None:
        if name == "after_recovery_update_before_commit":
            raise RuntimeError("simulated recovery crash")

    monkeypatch.setattr(crashing, "_checkpoint", crash)
    with pytest.raises(RuntimeError, match="simulated recovery crash"):
        crashing.begin_request(command)
    assert _data_snapshot(path) == before
    assert _store(path, deadline).begin_request(command).identity.attempt_count == 2
    _assert_write_lock_available(path)


def test_crash_after_recovery_commit_can_recover_next_deadline(tmp_path: Path) -> None:
    path = tmp_path / "crash-after-recovery.sqlite3"
    command, deadline = _seed(path, "crashafterrecovery")
    assert _store(path, deadline).begin_request(command).identity.attempt_count == 2
    next_deadline = deadline + _TIMEOUT
    assert _store(path, next_deadline - timedelta(microseconds=1)).begin_request(command).kind == "in_progress"
    assert _store(path, next_deadline).begin_request(command).identity.attempt_count == 3


def test_crash_during_tx_b_rolls_back_then_stale_attempt_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "crash-during-txb.sqlite3"
    command, deadline = _seed(path, "crashtxb")
    before = _data_snapshot(path)
    crashing = _store(path, deadline)

    def crash(name: str) -> None:
        if name == "after_response_update_before_commit":
            raise RuntimeError("simulated Tx B crash")

    monkeypatch.setattr(crashing, "_checkpoint", crash)
    with pytest.raises(RuntimeError, match="simulated Tx B crash"):
        crashing.complete_request(_completion(command, 1, "msg-asst-rolled-back"))
    assert _data_snapshot(path) == before
    assert _store(path, deadline).begin_request(command).identity.attempt_count == 2


def test_complete_replay_is_never_recovered_even_long_after_deadline(tmp_path: Path) -> None:
    path = tmp_path / "complete-no-recovery.sqlite3"
    command, deadline = _seed(path, "completereplay")
    completion = _completion(command, 1, "msg-asst-complete")
    stored = _store(path, deadline).complete_request(completion)
    before = _data_snapshot(path)
    duplicate = _store(path, deadline + timedelta(days=7)).begin_request(command)
    assert duplicate.kind == "duplicate" and duplicate.stored_response == stored
    assert _data_snapshot(path) == before


def test_busy_at_recovery_begin_is_typed_zero_mutation_and_manual_retry_works(
    tmp_path: Path,
) -> None:
    path = tmp_path / "recovery-busy-begin.sqlite3"
    command, deadline = _seed(path, "busybegin")
    before = _data_snapshot(path)
    _, release, thread, failures = _start_lock_holder(path)
    try:
        with pytest.raises(StoreBusyError):
            _store(path, deadline, busy_timeout_ms=20).begin_request(command)
        assert _data_snapshot(path) == before
    finally:
        _release_lock(release, thread, failures)
    assert _store(path, deadline).begin_request(command).identity.attempt_count == 2


def test_commit_time_busy_after_recovery_dml_rolls_back_and_releases_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "recovery-commit-busy.sqlite3"
    command, deadline = _seed(path, "busycommit")
    before = _data_snapshot(path)
    mutation_ready = threading.Event()
    continue_to_commit = threading.Event()
    store = _store(path, deadline, busy_timeout_ms=30)

    def pause(name: str) -> None:
        if name == "after_recovery_update_before_commit":
            mutation_ready.set()
            if not continue_to_commit.wait(timeout=5):
                raise AssertionError("recovery writer release timed out")

    monkeypatch.setattr(store, "_checkpoint", pause)
    result: list[object] = []
    writer = threading.Thread(
        target=lambda: result.append(_capture(lambda: store.begin_request(command))),
        name="recovery-commit-busy",
    )
    reader: sqlite3.Connection | None = None
    writer.start()
    try:
        assert mutation_ready.wait(timeout=5)
        reader = _connect(path)
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM analysis_requests").fetchall()
        continue_to_commit.set()
        writer.join(timeout=3)
        assert not writer.is_alive()
        assert len(result) == 1 and isinstance(result[0], StoreBusyError)
    finally:
        continue_to_commit.set()
        if reader is not None:
            reader.rollback()
            reader.close()
        writer.join(timeout=3)
    assert not writer.is_alive()
    assert _data_snapshot(path) == before
    assert _store(path, deadline).begin_request(command).identity.attempt_count == 2
    _assert_write_lock_available(path)


def test_backward_clock_is_clamped_without_timestamp_regression(tmp_path: Path) -> None:
    path = tmp_path / "backward-clock.sqlite3"
    command, deadline = _seed(path, "backward")
    _store(path, deadline).fail_request(_failure(command, 1, RequestStatus.FAILED_RETRYABLE))
    failed = _row(path, command.request_id)
    failed_at = datetime.fromisoformat(str(failed["failed_at"]))
    result = _store(path, _START - timedelta(days=1)).begin_request(command)
    row = _row(path, command.request_id)
    started = datetime.fromisoformat(str(row["processing_started_at"]))
    due = datetime.fromisoformat(str(row["processing_deadline_at"]))
    assert result.identity.attempt_count == 2
    assert started == failed_at + timedelta(microseconds=1)
    assert due - started == _TIMEOUT


@pytest.mark.parametrize(
    "fields",
    [
        {"processing_started_at": ""},
        {"processing_deadline_at": None},
        {"processing_deadline_at": "not-a-timestamp"},
        {"processing_deadline_at": "2026-07-15T00:59:00.000000+00:00"},
        {"processing_deadline_at": "2026-07-15T01:03:00.000000+00:00"},
        {"attempt_count": 4},
    ],
)
def test_corrupt_deadline_timestamp_or_attempt_fails_loud_without_repair(
    tmp_path: Path, fields: dict[str, object]
) -> None:
    path = tmp_path / f"corrupt-{next(iter(fields))}-{str(next(iter(fields.values())))[-4:]}.sqlite3"
    command, deadline = _seed(path, "corrupt")
    _corrupt_request(path, command.request_id, **fields)
    before = _data_snapshot(path)
    with pytest.raises(DurableRowError):
        _store(path, deadline).begin_request(command)
    assert _data_snapshot(path) == before


def test_stale_context_is_read_only_and_does_not_trigger_recovery(tmp_path: Path) -> None:
    path = tmp_path / "stale-context.sqlite3"
    command, deadline = _seed(path, "context")
    before = _data_snapshot(path)
    context = _store(path, deadline + timedelta(days=1)).load_bounded_context(
        BoundedContextQuery(
            session_id=command.session_id,
            chat_id=command.chat_id_candidate or "",
            current_user_message_id=command.user_message_id_candidate or "",
            current_question=command.question,
        )
    )
    assert context.current_question == command.question
    assert _data_snapshot(path) == before


def test_exhausted_result_can_be_followed_by_explicit_safe_final_failure(
    tmp_path: Path,
) -> None:
    path = tmp_path / "exhausted-final.sqlite3"
    command, deadline = _seed(path, "explicitfinal")
    deadline = _advance_to_attempt(path, command, deadline, 3)
    result = _store(path, deadline).begin_request(command)
    assert result.kind == "attempts_exhausted"
    _store(path, deadline + timedelta(seconds=1)).fail_request(
        _failure(command, 3, RequestStatus.FAILED_FINAL)
    )
    row = _row(path, command.request_id)
    assert (row["status"], row["attempt_count"]) == (RequestStatus.FAILED_FINAL.value, 3)


def test_stress_twenty_fresh_stale_recovery_races(tmp_path: Path) -> None:
    for iteration in range(20):
        path = tmp_path / f"stale-stress-{iteration}.sqlite3"
        command, deadline = _seed(path, f"stale{iteration}")
        results = _race(
            lambda: _store(path, deadline).begin_request(command),
            lambda: _store(path, deadline).begin_request(command),
        )
        assert sorted(getattr(result, "kind", type(result).__name__) for result in results) == [
            "in_progress",
            "retry",
        ]
        snapshot = _data_snapshot(path)
        assert snapshot["analysis_requests"][0]["attempt_count"] == 2
        assert len(snapshot["messages"]) == 1


def test_stress_twenty_recovery_versus_completion_races(tmp_path: Path) -> None:
    for iteration in range(20):
        path = tmp_path / f"terminal-stress-{iteration}.sqlite3"
        command, deadline = _seed(path, f"terminal{iteration}")
        completion = _completion(command, 1, f"msg-asst-stress-{iteration}")
        results = _race(
            lambda: _store(path, deadline).begin_request(command),
            lambda: _store(path, deadline).complete_request(completion),
        )
        row = _row(path, command.request_id)
        assistants = [m for m in _data_snapshot(path)["messages"] if m["role"] == "assistant"]
        if row["status"] == RequestStatus.COMPLETE.value:
            assert row["attempt_count"] == 1 and len(assistants) == 1
            assert any(getattr(result, "kind", None) == "duplicate" for result in results)
        else:
            assert (row["status"], row["attempt_count"], len(assistants)) == (
                RequestStatus.PROCESSING.value,
                2,
                0,
            )
            assert any(isinstance(result, RequestStateError) for result in results)
        assert not any(isinstance(result, (sqlite3.IntegrityError, sqlite3.OperationalError)) for result in results)
        _assert_write_lock_available(path)
