from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..schemas.chat import ChatListItem, ChatMessage
from ..schemas.content import AnalyzeContent
from .chat_store import ChatRecord


class BaseSchemaError(RuntimeError):
    """Raised when the legacy chat schema is partial or incompatible."""


_BASE_OBJECTS = {
    "chats": ("table", "chats"),
    "messages": ("table", "messages"),
    "idx_chats_session_updated": ("index", "chats"),
    "idx_messages_chat_created": ("index", "messages"),
}

_BASE_DDL = (
    """
    CREATE TABLE chats (
        chat_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        deleted_at TEXT NULL
    )
    """,
    """
    CREATE TABLE messages (
        message_id TEXT PRIMARY KEY,
        chat_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
        content_type TEXT NOT NULL CHECK(content_type IN ('text', 'structured')),
        content_text TEXT NULL,
        content_json TEXT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(chat_id) REFERENCES chats(chat_id)
    )
    """,
    "CREATE INDEX idx_chats_session_updated ON chats(session_id, updated_at)",
    "CREATE INDEX idx_messages_chat_created ON messages(chat_id, created_at, message_id)",
)

_CHAT_COLUMNS = (
    ("chat_id", "TEXT", False, None, 1),
    ("session_id", "TEXT", True, None, 0),
    ("title", "TEXT", True, None, 0),
    ("created_at", "TEXT", True, None, 0),
    ("updated_at", "TEXT", True, None, 0),
    ("deleted_at", "TEXT", False, None, 0),
)

_MESSAGE_COLUMNS = (
    ("message_id", "TEXT", False, None, 1),
    ("chat_id", "TEXT", True, None, 0),
    ("role", "TEXT", True, None, 0),
    ("content_type", "TEXT", True, None, 0),
    ("content_text", "TEXT", False, None, 0),
    ("content_json", "TEXT", False, None, 0),
    ("created_at", "TEXT", True, None, 0),
)


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _normalize_schema_sql(sql: str | None) -> str:
    if sql is None:
        return ""
    normalized: list[str] = []
    index = 0
    while index < len(sql):
        character = sql[index]
        if character == "'":
            literal = [character]
            index += 1
            while index < len(sql):
                literal.append(sql[index])
                if sql[index] == "'":
                    if index + 1 < len(sql) and sql[index + 1] == "'":
                        literal.append(sql[index + 1])
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            normalized.extend(literal)
            continue
        if character in {'"', "`", "["}:
            terminator = "]" if character == "[" else character
            index += 1
            identifier: list[str] = []
            while index < len(sql) and sql[index] != terminator:
                identifier.append(sql[index])
                index += 1
            index += 1
            normalized.append("".join(identifier).casefold())
            continue
        if character.isspace():
            index += 1
            continue
        normalized.append(character.casefold())
        index += 1
    return "".join(normalized)


def _base_objects(connection: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    expected = {name.casefold() for name in _BASE_OBJECTS}
    objects: dict[str, sqlite3.Row] = {}
    for row in connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE type IN ('table', 'index')"
    ):
        folded_name = str(row["name"]).casefold()
        if folded_name not in expected:
            continue
        if folded_name in objects:
            raise BaseSchemaError(f"ambiguous case-insensitive base object: {row['name']}")
        objects[folded_name] = row
    return objects


def _table_columns(connection: sqlite3.Connection, table: str) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            str(row["name"]).casefold(),
            str(row["type"]).upper(),
            bool(row["notnull"]),
            row["dflt_value"],
            int(row["pk"]),
        )
        for row in connection.execute(f"PRAGMA table_info({_quote_identifier(table)})")
    )


def _verify_named_index(
    connection: sqlite3.Connection,
    *,
    table: str,
    name: str,
    columns: tuple[str, ...],
    unique: bool,
    partial: bool = False,
) -> None:
    indexes = {
        str(row["name"]).casefold(): row
        for row in connection.execute(f"PRAGMA index_list({_quote_identifier(table)})")
    }
    row = indexes.get(name.casefold())
    if row is None:
        raise BaseSchemaError(f"missing required index: {name}")
    if row["origin"] != "c" or bool(row["unique"]) is not unique or bool(row["partial"]) is not partial:
        raise BaseSchemaError(f"incompatible index flags: {name}")
    actual_name = str(row["name"])
    actual_columns = tuple(
        str(item["name"]).casefold()
        for item in connection.execute(f"PRAGMA index_info({_quote_identifier(actual_name)})")
    )
    if actual_columns != columns:
        raise BaseSchemaError(
            f"incompatible index columns for {name}: expected {columns!r}, got {actual_columns!r}"
        )


def verify_base_schema(connection: sqlite3.Connection) -> None:
    """Fail loudly unless the supported chats/messages schema is exact."""

    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise BaseSchemaError("foreign keys must be enabled before base-schema verification")

    objects = _base_objects(connection)
    if set(objects) != set(_BASE_OBJECTS):
        missing = sorted(set(_BASE_OBJECTS) - set(objects))
        raise BaseSchemaError(f"base schema is incomplete; missing objects: {missing}")
    for name, (expected_type, expected_table) in _BASE_OBJECTS.items():
        row = objects[name]
        if (
            str(row["type"]).casefold() != expected_type.casefold()
            or str(row["tbl_name"]).casefold() != expected_table.casefold()
        ):
            raise BaseSchemaError(f"incompatible base object: {name}")

    chats_table = str(objects["chats"]["name"])
    messages_table = str(objects["messages"]["name"])
    if _table_columns(connection, chats_table) != _CHAT_COLUMNS:
        raise BaseSchemaError("incompatible chats columns")
    if _table_columns(connection, messages_table) != _MESSAGE_COLUMNS:
        raise BaseSchemaError("incompatible messages columns")

    message_sql = _normalize_schema_sql(objects["messages"]["sql"])
    for required_check in (
        "check(rolein('user','assistant'))",
        "check(content_typein('text','structured'))",
    ):
        if required_check not in message_sql:
            raise BaseSchemaError(f"messages is missing required constraint: {required_check}")
    if message_sql.count("check(") != 2:
        raise BaseSchemaError("messages has unexpected check constraints")

    foreign_keys = {
        (
            str(row["table"]).casefold(),
            str(row["from"]).casefold(),
            str(row["to"]).casefold(),
            row["on_update"],
            row["on_delete"],
            row["match"],
        )
        for row in connection.execute(
            f"PRAGMA foreign_key_list({_quote_identifier(messages_table)})"
        )
    }
    expected_foreign_keys = {("chats", "chat_id", "chat_id", "NO ACTION", "NO ACTION", "NONE")}
    if foreign_keys != expected_foreign_keys:
        raise BaseSchemaError("incompatible messages foreign keys")

    explicit_chat_indexes = {
        str(row["name"]).casefold()
        for row in connection.execute(f"PRAGMA index_list({_quote_identifier(chats_table)})")
        if row["origin"] == "c"
    }
    explicit_message_indexes = {
        str(row["name"]).casefold()
        for row in connection.execute(f"PRAGMA index_list({_quote_identifier(messages_table)})")
        if row["origin"] == "c"
    }
    if explicit_chat_indexes != {"idx_chats_session_updated"}:
        raise BaseSchemaError("incompatible explicit chats indexes")
    if explicit_message_indexes != {"idx_messages_chat_created"}:
        raise BaseSchemaError("incompatible explicit messages indexes")

    for table, primary_column in ((chats_table, "chat_id"), (messages_table, "message_id")):
        automatic_indexes = [
            row
            for row in connection.execute(f"PRAGMA index_list({_quote_identifier(table)})")
            if row["origin"] != "c"
        ]
        if (
            len(automatic_indexes) != 1
            or automatic_indexes[0]["origin"] != "pk"
            or not bool(automatic_indexes[0]["unique"])
            or bool(automatic_indexes[0]["partial"])
            or tuple(
                str(row["name"]).casefold()
                for row in connection.execute(
                    f"PRAGMA index_info({_quote_identifier(str(automatic_indexes[0]['name']))})"
                )
            )
            != (primary_column,)
        ):
            raise BaseSchemaError(f"incompatible {table} primary-key index")

    _verify_named_index(
        connection,
        table=chats_table,
        name="idx_chats_session_updated",
        columns=("session_id", "updated_at"),
        unique=False,
    )
    _verify_named_index(
        connection,
        table=messages_table,
        name="idx_messages_chat_created",
        columns=("chat_id", "created_at", "message_id"),
        unique=False,
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteChatStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._ready = False
        self.error: str | None = None

    @property
    def ready(self) -> bool:
        """Preserve legacy health behavior without mutating during construction."""

        if not self._ready:
            try:
                self.bootstrap_base_schema()
            except Exception:  # noqa: BLE001 - readiness details are exposed through ``error``
                return False
        return self._ready

    def _open_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _connect(self) -> sqlite3.Connection:
        """Legacy connection helper; construction itself remains side-effect free."""

        self._ensure_base_schema()
        return self._open_connection()

    def bootstrap_base_schema(self) -> None:
        """Atomically create an absent base schema or verify the exact existing one."""

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._open_connection()
        try:
            if connection.in_transaction:
                raise BaseSchemaError("base bootstrap cannot run inside an existing transaction")
            connection.execute("BEGIN IMMEDIATE")
            existing = _base_objects(connection)
            if not existing:
                for statement in _BASE_DDL:
                    connection.execute(statement)
            elif set(existing) != set(_BASE_OBJECTS):
                present = sorted(str(row["name"]) for row in existing.values())
                raise BaseSchemaError(f"base schema is partial; present objects: {present}")
            verify_base_schema(connection)
            connection.commit()
            self._ready = True
            self.error = None
        except Exception as exc:  # noqa: BLE001 - readiness is surfaced by health
            if connection.in_transaction:
                connection.rollback()
            self._ready = False
            self.error = str(exc)
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Compatibility alias for the explicit base-schema bootstrap."""

        self.bootstrap_base_schema()

    def _ensure_base_schema(self) -> None:
        if not self._ready:
            self.bootstrap_base_schema()

    def create_chat(self, session_id: str, title: str = "Chat mới") -> ChatRecord:
        self._ensure_base_schema()
        chat_id = f"chat_{uuid4().hex}"
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO chats(chat_id, session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, session_id, title or "Chat mới", now, now),
            )
        return ChatRecord(chat_id, session_id, title or "Chat mới", now, now)

    def get_chat(self, chat_id: str) -> ChatRecord | None:
        self._ensure_base_schema()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chats WHERE chat_id = ? AND deleted_at IS NULL",
                (chat_id,),
            ).fetchone()
        return ChatRecord(**dict(row)) if row else None

    def get_chat_for_session(self, chat_id: str, session_id: str) -> ChatRecord | None:
        self._ensure_base_schema()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM chats
                WHERE chat_id = ? AND session_id = ? AND deleted_at IS NULL
                """,
                (chat_id, session_id),
            ).fetchone()
        return ChatRecord(**dict(row)) if row else None

    def add_message(self, message: ChatMessage) -> None:
        self._ensure_base_schema()
        content_json = (
            json.dumps(message.content_json.model_dump(mode="json"), ensure_ascii=False)
            if message.content_json is not None
            else None
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO messages(message_id, chat_id, role, content_type, content_text, content_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.chat_id,
                    message.role,
                    message.content_type,
                    message.content_text,
                    content_json,
                    message.created_at,
                ),
            )
            connection.execute(
                "UPDATE chats SET updated_at = ? WHERE chat_id = ?",
                (message.created_at, message.chat_id),
            )

    def list_messages(self, chat_id: str, limit: int | None = None) -> list[ChatMessage]:
        self._ensure_base_schema()
        with self._connect() as connection:
            if limit is None:
                rows = connection.execute(
                    "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC, message_id ASC",
                    (chat_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM (
                        SELECT * FROM messages WHERE chat_id = ?
                        ORDER BY created_at DESC, message_id DESC LIMIT ?
                    ) ORDER BY created_at ASC, message_id ASC
                    """,
                    (chat_id, limit),
                ).fetchall()
        messages: list[ChatMessage] = []
        for row in rows:
            raw = dict(row)
            parsed = json.loads(raw["content_json"]) if raw["content_json"] else None
            messages.append(
                ChatMessage(
                    message_id=raw["message_id"],
                    chat_id=raw["chat_id"],
                    role=raw["role"],
                    content_type=raw["content_type"],
                    content_text=raw["content_text"],
                    content_json=AnalyzeContent.model_validate(parsed) if parsed is not None else None,
                    created_at=raw["created_at"],
                )
            )
        return messages

    def list_chats(self, session_id: str) -> list[ChatListItem]:
        self._ensure_base_schema()
        with self._connect() as connection:
            chats = connection.execute(
                "SELECT * FROM chats WHERE session_id = ? AND deleted_at IS NULL ORDER BY updated_at DESC, chat_id DESC",
                (session_id,),
            ).fetchall()
        result: list[ChatListItem] = []
        for chat_row in chats:
            chat = dict(chat_row)
            messages = self.list_messages(chat["chat_id"])
            preview = ""
            domain = None
            risk_level = None
            if messages:
                latest = messages[-1]
                preview = latest.content_text or (latest.content_json.summary if latest.content_json else "")
                for message in reversed(messages):
                    if message.content_json is not None:
                        domain = message.content_json.domain
                        risk_level = message.content_json.risk_level
                        break
            result.append(
                ChatListItem(
                    chat_id=chat["chat_id"],
                    title=chat["title"],
                    created_at=chat["created_at"],
                    updated_at=chat["updated_at"],
                    last_message_preview=preview[:240],
                    domain=domain,
                    risk_level=risk_level,
                    message_count=len(messages),
                )
            )
        return result

    def soft_delete(self, chat_id: str) -> bool:
        self._ensure_base_schema()
        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE chats SET deleted_at = ?, updated_at = ? WHERE chat_id = ? AND deleted_at IS NULL",
                (now, now, chat_id),
            )
        return cursor.rowcount > 0

    def soft_delete_chat_for_session(self, chat_id: str, session_id: str) -> bool:
        self._ensure_base_schema()
        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE chats SET deleted_at = ?, updated_at = ?
                WHERE chat_id = ? AND session_id = ? AND deleted_at IS NULL
                """,
                (now, now, chat_id, session_id),
            )
        return cursor.rowcount > 0
