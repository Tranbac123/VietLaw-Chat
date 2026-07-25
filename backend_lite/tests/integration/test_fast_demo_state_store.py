"""FAST DEMO V2 state store: isolated schema, CAS, and bounded dedup records.

Covers required cases 24-27 (partly) and 13 of the 48-hour contract at the
store level; the orchestrator-level behavior is covered in
``test_fast_demo_conversation.py``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend_lite.app.contracts.fast_demo import (
    DepositAmount,
    FastDemoState,
    RecentRequestRecord,
)
from backend_lite.app.stores.fast_demo_state_store import (
    TABLE_NAME,
    FastDemoStateStore,
)
from backend_lite.app.stores.sqlite_chat_store import SQLiteChatStore, verify_base_schema


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "chat.sqlite3"


def test_ensure_schema_is_idempotent(db_path: Path) -> None:
    store = FastDemoStateStore(db_path)
    store.ensure_schema()
    store._schema_ready = False  # force a second real pass
    store.ensure_schema()

    connection = sqlite3.connect(db_path)
    try:
        names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        connection.close()
    assert TABLE_NAME in names


def test_fast_demo_table_does_not_break_base_chat_schema(db_path: Path) -> None:
    """The base verifier name-filters sqlite_master, so an extra table is fine."""

    chat_store = SQLiteChatStore(db_path)
    chat_store.bootstrap_base_schema()
    FastDemoStateStore(db_path).ensure_schema()

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        verify_base_schema(connection)  # must not raise
    finally:
        connection.close()
    assert chat_store.ready is True


def test_schema_is_not_registered_in_production_migration_registry(db_path: Path) -> None:
    FastDemoStateStore(db_path).ensure_schema()
    connection = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        connection.close()
    assert "schema_migrations" not in tables


def test_load_creates_default_row(db_path: Path) -> None:
    store = FastDemoStateStore(db_path)
    loaded = store.load("chat_1")
    assert loaded.state_version == 0
    assert loaded.state.issue_type == "rental_deposit"
    assert loaded.state.facts.deposit_amount is None
    assert loaded.recent_requests == []


def test_commit_increments_version_and_persists(db_path: Path) -> None:
    store = FastDemoStateStore(db_path)
    loaded = store.load("chat_1")

    state = loaded.state.model_copy(deep=True)
    state.facts.deposit_amount = DepositAmount(value=20_000_000)
    ok = store.commit_state(
        chat_id="chat_1",
        expected_version=loaded.state_version,
        state=state,
        recent_requests=[
            RecentRequestRecord(client_request_id="a", response_json={"x": 1}, applied_state_version=1)
        ],
    )
    assert ok is True

    reloaded = store.load("chat_1")
    assert reloaded.state_version == 1
    assert reloaded.state.facts.deposit_amount is not None
    assert reloaded.state.facts.deposit_amount.value == 20_000_000
    assert reloaded.find_recent("a") is not None


def test_compare_and_swap_rejects_stale_writer(db_path: Path) -> None:
    """The core concurrency property: a writer holding version N cannot commit
    once another turn has already moved the row to N+1."""

    store = FastDemoStateStore(db_path)
    loaded = store.load("chat_1")
    stale_version = loaded.state_version

    winner = loaded.state.model_copy(deep=True)
    winner.facts.deposit_amount = DepositAmount(value=15_000_000)
    assert store.commit_state(
        chat_id="chat_1", expected_version=stale_version, state=winner, recent_requests=[]
    ) is True

    loser = loaded.state.model_copy(deep=True)
    loser.facts.deposit_amount = DepositAmount(value=99_000_000)
    assert store.commit_state(
        chat_id="chat_1", expected_version=stale_version, state=loser, recent_requests=[]
    ) is False

    # The winner's value survives; the stale value is never applied.
    assert store.load("chat_1").state.facts.deposit_amount.value == 15_000_000


def test_recent_requests_are_bounded_to_eight(db_path: Path) -> None:
    store = FastDemoStateStore(db_path)
    loaded = store.load("chat_1")
    records = [
        RecentRequestRecord(
            client_request_id=f"req_{index}", response_json={"i": index}, applied_state_version=1
        )
        for index in range(12)
    ]
    store.commit_state(
        chat_id="chat_1",
        expected_version=loaded.state_version,
        state=loaded.state,
        recent_requests=records,
    )
    reloaded = store.load("chat_1")
    assert len(reloaded.recent_requests) == 8
    assert reloaded.find_recent("req_11") is not None
    assert reloaded.find_recent("req_0") is None


def test_cross_chat_isolation(db_path: Path) -> None:
    store = FastDemoStateStore(db_path)
    first = store.load("chat_a")
    state = first.state.model_copy(deep=True)
    state.facts.deposit_amount = DepositAmount(value=20_000_000)
    store.commit_state(
        chat_id="chat_a", expected_version=first.state_version, state=state, recent_requests=[]
    )

    other = store.load("chat_b")
    assert other.state.facts.deposit_amount is None
    assert other.state_version == 0


def test_corrupt_state_json_degrades_to_default(db_path: Path) -> None:
    store = FastDemoStateStore(db_path)
    store.load("chat_1")
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            f"UPDATE {TABLE_NAME} SET state_json = ? WHERE chat_id = ?", ("{not json", "chat_1")
        )
        connection.commit()
    finally:
        connection.close()

    loaded = store.load("chat_1")
    assert isinstance(loaded.state, FastDemoState)
    assert loaded.state.facts.deposit_amount is None
