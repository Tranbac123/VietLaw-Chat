"""FAST DEMO V2 state store: one JSON state row per chat, with compare-and-swap.

Deliberately isolated from the production migration registry
(``adapters/migrator.py``) and from the chats/messages base schema. It creates
exactly one table via ``CREATE TABLE IF NOT EXISTS`` and is only ever invoked
when ``VIETLAW_FAST_DEMO_V2_ENABLED`` is true.

Safety properties:
  * no SQLite transaction is ever held across a provider call -- the store
    exposes short ``load``/``commit`` calls, and the orchestrator does the
    network work strictly between them;
  * ``commit_state`` is a compare-and-swap on ``state_version``; a losing writer
    updates zero rows and is told so, rather than clobbering a newer state;
  * ``recent_requests_json`` is the single source of truth for fast-demo request
    deduplication -- there is no second dedup table and no duplicated
    idempotency entry inside ``state_json``.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..contracts.fast_demo import (
    ISSUE_TYPE_RENTAL_DEPOSIT,
    MAX_RECENT_REQUESTS,
    FastDemoState,
    RecentRequestRecord,
)

TABLE_NAME = "demo_conversation_states"

_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    chat_id TEXT PRIMARY KEY,
    issue_type TEXT NOT NULL,
    state_json TEXT NOT NULL,
    recent_requests_json TEXT NOT NULL DEFAULT '[]',
    state_version INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
)
"""

_REQUIRED_COLUMNS = {
    "chat_id",
    "issue_type",
    "state_json",
    "recent_requests_json",
    "state_version",
    "updated_at",
}


class FastDemoStoreError(RuntimeError):
    """Raised only inside the store; the orchestrator converts it into a
    controlled fallback so no raw SQLite error can reach the UI."""


@dataclass
class LoadedFastDemoState:
    chat_id: str
    state: FastDemoState
    state_version: int
    recent_requests: list[RecentRequestRecord]

    def find_recent(self, client_request_id: str) -> RecentRequestRecord | None:
        if not client_request_id:
            return None
        for record in self.recent_requests:
            if record.client_request_id == client_request_id:
                return record
        return None


class FastDemoStateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._schema_ready = False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def ensure_schema(self) -> None:
        """Create the fast-demo table if absent and verify its columns.

        Idempotent. Never touches chats/messages, never registers a migration
        version, and never runs unless the caller has already checked the flag.
        """

        if self._schema_ready:
            return
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            connection = self._connect()
            try:
                connection.execute(_CREATE_TABLE)
                connection.commit()
                columns = {
                    str(row["name"])
                    for row in connection.execute(f"PRAGMA table_info({TABLE_NAME})")
                }
                missing = _REQUIRED_COLUMNS - columns
                if missing:
                    raise FastDemoStoreError(
                        f"fast-demo table missing columns: {sorted(missing)}"
                    )
            finally:
                connection.close()
        except FastDemoStoreError:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced as a controlled fallback
            raise FastDemoStoreError(f"fast-demo schema init failed: {type(exc).__name__}") from exc
        self._schema_ready = True

    def load(self, chat_id: str) -> LoadedFastDemoState:
        """Ensure a default row exists, then read it. Short transaction only."""

        self.ensure_schema()
        try:
            connection = self._connect()
            try:
                default_state = FastDemoState()
                connection.execute(
                    f"INSERT OR IGNORE INTO {TABLE_NAME}"
                    " (chat_id, issue_type, state_json, recent_requests_json, state_version, updated_at)"
                    " VALUES (?, ?, ?, '[]', 0, ?)",
                    (
                        chat_id,
                        ISSUE_TYPE_RENTAL_DEPOSIT,
                        default_state.model_dump_json(),
                        _utc_now(),
                    ),
                )
                connection.commit()
                row = connection.execute(
                    f"SELECT state_json, recent_requests_json, state_version FROM {TABLE_NAME}"
                    " WHERE chat_id = ?",
                    (chat_id,),
                ).fetchone()
            finally:
                connection.close()
        except Exception as exc:  # noqa: BLE001
            raise FastDemoStoreError(f"fast-demo load failed: {type(exc).__name__}") from exc

        if row is None:
            raise FastDemoStoreError("fast-demo state row missing after insert")
        return LoadedFastDemoState(
            chat_id=chat_id,
            state=_parse_state(row["state_json"]),
            state_version=int(row["state_version"]),
            recent_requests=_parse_recent(row["recent_requests_json"]),
        )

    def commit_state(
        self,
        *,
        chat_id: str,
        expected_version: int,
        state: FastDemoState,
        recent_requests: list[RecentRequestRecord],
    ) -> bool:
        """Compare-and-swap. Returns False when another turn committed first.

        A False return means the caller's model output was computed against a
        now-stale state and must be discarded -- never merged, never retried
        with a second provider call.
        """

        self.ensure_schema()
        bounded = recent_requests[-MAX_RECENT_REQUESTS:]
        payload = json.dumps(
            [record.model_dump(mode="json") for record in bounded], ensure_ascii=False
        )
        try:
            connection = self._connect()
            try:
                cursor = connection.execute(
                    f"UPDATE {TABLE_NAME} SET state_json = ?, recent_requests_json = ?,"
                    " state_version = state_version + 1, updated_at = ?"
                    " WHERE chat_id = ? AND state_version = ?",
                    (
                        state.model_dump_json(),
                        payload,
                        _utc_now(),
                        chat_id,
                        expected_version,
                    ),
                )
                connection.commit()
                return cursor.rowcount == 1
            finally:
                connection.close()
        except Exception as exc:  # noqa: BLE001
            raise FastDemoStoreError(f"fast-demo commit failed: {type(exc).__name__}") from exc


def _parse_state(raw: object) -> FastDemoState:
    try:
        return FastDemoState.model_validate_json(str(raw))
    except Exception:  # noqa: BLE001 - a corrupt row must not break the turn
        return FastDemoState()


def _parse_recent(raw: object) -> list[RecentRequestRecord]:
    try:
        items = json.loads(str(raw))
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(items, list):
        return []
    records: list[RecentRequestRecord] = []
    for item in items:
        try:
            records.append(RecentRequestRecord.model_validate(item))
        except Exception:  # noqa: BLE001 - skip unreadable entries, keep the rest
            continue
    return records[-MAX_RECENT_REQUESTS:]


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "FastDemoStateStore",
    "FastDemoStoreError",
    "LoadedFastDemoState",
    "TABLE_NAME",
]
