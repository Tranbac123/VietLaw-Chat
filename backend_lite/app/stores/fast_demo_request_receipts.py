"""Session-scoped request receipts: exactly-once persistence for one logical turn.

Why this table exists
---------------------
The fast-demo state store already deduplicates by ``client_request_id``, but its
records live *inside a chat's* state row, so the identity is effectively
``(chat_id, client_request_id)``. That identity has two gaps:

* it is only consulted **after** ``AgentRuntime`` has already created/resolved a
  chat and inserted the user message, so a replay still writes rows;
* it is unreachable when the first request had no ``chat_id`` -- a retry that
  still omits ``chat_id`` lands on a brand-new chat, finds no record, and
  re-executes the whole turn (second chat, second provider call, second fact
  application).

The second gap cannot be represented by the existing per-chat schema at all: to
resolve a lost new-chat response you must look the request up *before* a chat
exists. This table is therefore the smallest addition that can express the
required identity, and it is additive only -- the chats/messages base schema and
the fast-demo state schema are untouched.

Identity
--------
``(session_id, client_request_id)``. ``session_id`` is the trusted ownership
identity the application already uses to scope chats (``get_chat_for_session``),
so two owners cannot collide on or replay each other's requests. It is never
taken from public message text.

A ``request_fingerprint`` over the canonical request guards against the same
owner reusing a key for a different question: that is reported as a conflict
rather than silently replaying an unrelated answer.

Transaction boundary
--------------------
Every method opens a short connection and commits before returning. No
transaction is ever held across a provider call: the runtime reserves (TX-A),
releases the connection, calls the provider, then finalizes (TX-B).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TABLE_NAME = "demo_request_receipts"

STATUS_PENDING = "PENDING"
STATUS_COMPLETE = "COMPLETE"

_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    session_id TEXT NOT NULL,
    client_request_id TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'COMPLETE')),
    -- NULL until the turn resolves its chat. The claim is taken *before* any
    -- chat row is written, so a concurrent duplicate cannot leak an extra chat.
    chat_id TEXT NULL,
    user_message_id TEXT NOT NULL,
    assistant_message_id TEXT NOT NULL,
    response_json TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (session_id, client_request_id),
    CHECK (status <> 'COMPLETE' OR (chat_id IS NOT NULL AND response_json IS NOT NULL))
)
"""

_REQUIRED_COLUMNS = {
    "session_id",
    "client_request_id",
    "request_fingerprint",
    "status",
    "chat_id",
    "user_message_id",
    "assistant_message_id",
    "response_json",
    "created_at",
    "updated_at",
}


class RequestReceiptStoreError(RuntimeError):
    """Raised only inside the store. Callers convert it into a controlled
    outcome so no raw SQLite error can reach the UI."""


@dataclass(frozen=True)
class RequestReceipt:
    session_id: str
    client_request_id: str
    request_fingerprint: str
    status: str
    chat_id: str | None
    user_message_id: str
    assistant_message_id: str
    response: dict[str, Any] | None

    @property
    def is_complete(self) -> bool:
        return self.status == STATUS_COMPLETE and self.response is not None


@dataclass(frozen=True)
class ReserveOutcome:
    """Result of TX-A.

    ``receipt`` is the row that now owns this logical request.
    ``reserved`` is True only for the caller that actually created it; a caller
    that finds an existing row must not start a second provider attempt.
    """

    receipt: RequestReceipt
    reserved: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FastDemoRequestReceiptStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._schema_ready = False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def ensure_schema(self) -> None:
        """Idempotent: safe to call on every startup and on an existing file."""

        if self._schema_ready:
            return
        try:
            with self._connect() as connection:
                connection.execute(_CREATE_TABLE)
                columns = {
                    row["name"] for row in connection.execute(f"PRAGMA table_info({TABLE_NAME})")
                }
        except sqlite3.Error as exc:  # noqa: BLE001 - contained
            raise RequestReceiptStoreError(f"receipt schema unavailable: {exc}") from exc
        missing = _REQUIRED_COLUMNS - columns
        if missing:
            raise RequestReceiptStoreError(f"receipt table missing columns: {sorted(missing)}")
        self._schema_ready = True

    def _row_to_receipt(self, row: sqlite3.Row) -> RequestReceipt:
        payload = None
        if row["response_json"]:
            try:
                decoded = json.loads(row["response_json"])
                if isinstance(decoded, dict):
                    payload = decoded
            except (TypeError, ValueError):
                # An unreadable payload must not be replayed as if it were valid.
                payload = None
        return RequestReceipt(
            session_id=row["session_id"],
            client_request_id=row["client_request_id"],
            request_fingerprint=row["request_fingerprint"],
            status=row["status"],
            chat_id=row["chat_id"],
            user_message_id=row["user_message_id"],
            assistant_message_id=row["assistant_message_id"],
            response=payload,
        )

    def find(self, *, session_id: str, client_request_id: str) -> RequestReceipt | None:
        self.ensure_schema()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"SELECT * FROM {TABLE_NAME} WHERE session_id = ? AND client_request_id = ?",
                    (session_id, client_request_id),
                ).fetchone()
        except sqlite3.Error as exc:  # noqa: BLE001 - contained
            raise RequestReceiptStoreError(f"receipt lookup failed: {exc}") from exc
        return self._row_to_receipt(row) if row is not None else None

    def reserve(
        self,
        *,
        session_id: str,
        client_request_id: str,
        request_fingerprint: str,
        user_message_id: str,
        assistant_message_id: str,
    ) -> ReserveOutcome:
        """TX-A. Claim this logical request, or report the existing claim.

        The insert is ``ON CONFLICT DO NOTHING`` against the primary key, so
        exactly one concurrent caller can win. The loser reads back the winning
        row and is told ``reserved=False``, which is what keeps a simultaneous
        duplicate from spending a second provider attempt.
        """

        self.ensure_schema()
        now = _utc_now()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    f"""
                    INSERT INTO {TABLE_NAME} (
                        session_id, client_request_id, request_fingerprint, status,
                        chat_id, user_message_id, assistant_message_id, response_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, NULL, ?, ?, NULL, ?, ?)
                    ON CONFLICT (session_id, client_request_id) DO NOTHING
                    """,
                    (
                        session_id, client_request_id, request_fingerprint, STATUS_PENDING,
                        user_message_id, assistant_message_id, now, now,
                    ),
                )
                # DO NOTHING leaves rowcount at 0 for the caller that lost the
                # race, which is the authoritative "someone else owns this" flag.
                reserved = cursor.rowcount == 1
                row = connection.execute(
                    f"SELECT * FROM {TABLE_NAME} WHERE session_id = ? AND client_request_id = ?",
                    (session_id, client_request_id),
                ).fetchone()
        except sqlite3.Error as exc:  # noqa: BLE001 - contained
            raise RequestReceiptStoreError(f"receipt reserve failed: {exc}") from exc
        if row is None:  # pragma: no cover - the insert above guarantees a row
            raise RequestReceiptStoreError("receipt row vanished after reserve")
        return ReserveOutcome(receipt=self._row_to_receipt(row), reserved=reserved)

    def bind_chat(self, *, session_id: str, client_request_id: str, chat_id: str) -> None:
        """Attach the resolved chat to a still-pending claim.

        This is what makes a lost new-chat response recoverable: the retry finds
        the completed receipt and its chat rather than creating a second chat.
        Guarded by ``status = 'PENDING'`` so a completed receipt's chat can never
        be repointed.
        """

        self.ensure_schema()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    f"""
                    UPDATE {TABLE_NAME}
                       SET chat_id = ?, updated_at = ?
                     WHERE session_id = ? AND client_request_id = ? AND status = ?
                    """,
                    (chat_id, _utc_now(), session_id, client_request_id, STATUS_PENDING),
                )
        except sqlite3.Error as exc:  # noqa: BLE001 - contained
            raise RequestReceiptStoreError(f"receipt chat binding failed: {exc}") from exc

    def complete(
        self,
        *,
        session_id: str,
        client_request_id: str,
        response: dict[str, Any],
    ) -> None:
        """TX-B. Record the finished turn's response snapshot exactly once.

        Guarded by ``status = 'PENDING'`` so a late finalizer cannot overwrite an
        already-completed receipt with a different payload.
        """

        self.ensure_schema()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    f"""
                    UPDATE {TABLE_NAME}
                       SET status = ?, response_json = ?, updated_at = ?
                     WHERE session_id = ? AND client_request_id = ? AND status = ?
                    """,
                    (
                        STATUS_COMPLETE,
                        json.dumps(response, ensure_ascii=False),
                        _utc_now(),
                        session_id,
                        client_request_id,
                        STATUS_PENDING,
                    ),
                )
        except sqlite3.Error as exc:  # noqa: BLE001 - contained
            raise RequestReceiptStoreError(f"receipt completion failed: {exc}") from exc

    def release(self, *, session_id: str, client_request_id: str) -> None:
        """Drop a still-PENDING reservation whose turn failed before completing.

        A failed attempt must not leave a permanent pending claim that blocks the
        user's own retry, and because the reservation is removed rather than
        completed, no response is ever replayed for a turn that did not finish.
        """

        self.ensure_schema()
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    f"DELETE FROM {TABLE_NAME} WHERE session_id = ? AND client_request_id = ? AND status = ?",
                    (session_id, client_request_id, STATUS_PENDING),
                )
        except sqlite3.Error as exc:  # noqa: BLE001 - contained
            raise RequestReceiptStoreError(f"receipt release failed: {exc}") from exc


__all__ = [
    "FastDemoRequestReceiptStore",
    "RequestReceipt",
    "RequestReceiptStoreError",
    "ReserveOutcome",
    "STATUS_COMPLETE",
    "STATUS_PENDING",
    "TABLE_NAME",
]
