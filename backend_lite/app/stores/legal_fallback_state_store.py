"""VietLaw Public Beta V0: state store for the legal-fallback vertical.

Same shape as `fast_demo_state_store.py::FastDemoStateStore` (one dedicated
table via `CREATE TABLE IF NOT EXISTS`, compare-and-swap on `state_version`,
short load/commit transactions with no SQLite transaction ever held across
a network call) -- a NEW, separate table, so a bug in this vertical's state
handling can never corrupt or contend with the MODE_2D deposit table.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..contracts.legal_fallback_state import LegalFallbackState

TABLE_NAME = "legal_fallback_states"

_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    chat_id TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    state_version INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
)
"""

_REQUIRED_COLUMNS = {"chat_id", "state_json", "state_version", "updated_at"}


class LegalFallbackStoreError(RuntimeError):
    """Raised only inside the store; the orchestrator converts it into a
    safe defer (return None), never a raw error."""


@dataclass
class LoadedLegalFallbackState:
    chat_id: str
    state: LegalFallbackState
    state_version: int


class LegalFallbackStateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._schema_ready = False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def ensure_schema(self) -> None:
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
                    raise LegalFallbackStoreError(f"table missing columns: {sorted(missing)}")
            finally:
                connection.close()
        except LegalFallbackStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise LegalFallbackStoreError(f"schema init failed: {type(exc).__name__}") from exc
        self._schema_ready = True

    def load(self, chat_id: str) -> LoadedLegalFallbackState:
        self.ensure_schema()
        try:
            connection = self._connect()
            try:
                default_state = LegalFallbackState()
                connection.execute(
                    f"INSERT OR IGNORE INTO {TABLE_NAME}"
                    " (chat_id, state_json, state_version, updated_at)"
                    " VALUES (?, ?, 0, ?)",
                    (chat_id, default_state.model_dump_json(), _utc_now()),
                )
                connection.commit()
                row = connection.execute(
                    f"SELECT state_json, state_version FROM {TABLE_NAME} WHERE chat_id = ?",
                    (chat_id,),
                ).fetchone()
            finally:
                connection.close()
        except Exception as exc:  # noqa: BLE001
            raise LegalFallbackStoreError(f"load failed: {type(exc).__name__}") from exc

        if row is None:
            raise LegalFallbackStoreError("state row missing after insert")
        return LoadedLegalFallbackState(
            chat_id=chat_id,
            state=_parse_state(row["state_json"]),
            state_version=int(row["state_version"]),
        )

    def commit_state(
        self, *, chat_id: str, expected_version: int, state: LegalFallbackState
    ) -> bool:
        """Compare-and-swap. False means a concurrent turn already committed;
        the caller must discard its candidate rather than merge or retry."""

        self.ensure_schema()
        try:
            connection = self._connect()
            try:
                cursor = connection.execute(
                    f"UPDATE {TABLE_NAME} SET state_json = ?, state_version = state_version + 1,"
                    " updated_at = ? WHERE chat_id = ? AND state_version = ?",
                    (state.model_dump_json(), _utc_now(), chat_id, expected_version),
                )
                connection.commit()
                return cursor.rowcount == 1
            finally:
                connection.close()
        except Exception as exc:  # noqa: BLE001
            raise LegalFallbackStoreError(f"commit failed: {type(exc).__name__}") from exc


def _parse_state(raw: object) -> LegalFallbackState:
    try:
        return LegalFallbackState.model_validate_json(str(raw))
    except Exception:  # noqa: BLE001 - a corrupt row must not break the turn
        return LegalFallbackState()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "LegalFallbackStateStore",
    "LegalFallbackStoreError",
    "LoadedLegalFallbackState",
    "TABLE_NAME",
]
