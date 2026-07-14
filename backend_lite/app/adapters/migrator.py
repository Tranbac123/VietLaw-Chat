"""Atomic, versioned SQLite schema migration for Gate A2a."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path

from ..stores.sqlite_chat_store import BaseSchemaError, verify_base_schema

MIGRATION_VERSION = "001_analysis_requests"
_MIGRATION_RESOURCE = Path(__file__).with_name("migrations") / f"{MIGRATION_VERSION}.sql"
_REQUEST_OBJECTS = {
    "analysis_requests": ("table", "analysis_requests"),
    "ux_analysis_requests_assistant_message": ("index", "analysis_requests"),
    "ux_analysis_requests_session_idempotency": ("index", "analysis_requests"),
    "ix_analysis_requests_status_updated": ("index", "analysis_requests"),
    "ix_analysis_requests_chat_created": ("index", "analysis_requests"),
}

_REGISTRY_COLUMNS = (
    ("version", "TEXT", False, None, 1),
    ("applied_at", "TEXT", True, None, 0),
)

_REQUEST_COLUMNS = (
    ("analysis_request_pk", "INTEGER", False, None, 1),
    ("session_id", "TEXT", True, None, 0),
    ("request_id", "TEXT", True, None, 0),
    ("idempotency_key_version", "TEXT", False, None, 0),
    ("idempotency_key_digest", "TEXT", False, None, 0),
    ("fingerprint_version", "TEXT", True, None, 0),
    ("request_fingerprint", "TEXT", True, None, 0),
    ("status", "TEXT", True, None, 0),
    ("attempt_count", "INTEGER", True, "1", 0),
    ("requested_chat_id", "TEXT", False, None, 0),
    ("chat_id", "TEXT", True, None, 0),
    ("user_type", "TEXT", True, None, 0),
    ("language", "TEXT", True, None, 0),
    ("user_message_id", "TEXT", True, None, 0),
    ("assistant_message_id", "TEXT", False, None, 0),
    ("response_payload", "TEXT", False, None, 0),
    ("error_class", "TEXT", False, None, 0),
    ("last_error_code", "TEXT", False, None, 0),
    ("error_details_json", "TEXT", False, None, 0),
    ("contract_version", "TEXT", True, None, 0),
    ("corpus_version", "TEXT", True, None, 0),
    ("policy_version", "TEXT", True, None, 0),
    ("prompt_version", "TEXT", True, None, 0),
    ("retriever_version", "TEXT", True, None, 0),
    ("generator_mode", "TEXT", True, None, 0),
    ("generator_version", "TEXT", True, None, 0),
    ("created_at", "TEXT", True, None, 0),
    ("processing_started_at", "TEXT", True, None, 0),
    ("processing_deadline_at", "TEXT", False, None, 0),
    ("updated_at", "TEXT", True, None, 0),
    ("completed_at", "TEXT", False, None, 0),
    ("failed_at", "TEXT", False, None, 0),
)

_REQUEST_SQL_FRAGMENTS = (
    "CHECK (idempotency_key_digest IS NULL OR (length(idempotency_key_digest) = 64 "
    "AND idempotency_key_digest NOT GLOB '*[^0-9a-f]*'))",
    "CHECK (length(request_fingerprint) = 64 "
    "AND request_fingerprint NOT GLOB '*[^0-9a-f]*')",
    "CHECK (status IN ('RECEIVED', 'PROCESSING', 'COMPLETE', 'FAILED_RETRYABLE', 'FAILED_FINAL'))",
    "CHECK (attempt_count >= 1)",
    "CHECK (error_class IS NULL OR error_class IN "
    "('client', 'retryable_dependency', 'final_deterministic', 'internal'))",
    "CHECK ((idempotency_key_version IS NULL) = (idempotency_key_digest IS NULL))",
    "FOREIGN KEY (user_message_id) REFERENCES messages(message_id) DEFERRABLE INITIALLY DEFERRED",
    "FOREIGN KEY (assistant_message_id) REFERENCES messages(message_id) DEFERRABLE INITIALLY DEFERRED",
    "CHECK ((status = 'COMPLETE') = (assistant_message_id IS NOT NULL))",
    "CHECK ((status IN ('COMPLETE', 'FAILED_FINAL')) = (response_payload IS NOT NULL))",
    "CHECK ((status = 'COMPLETE') = (completed_at IS NOT NULL))",
    "CHECK ((status IN ('FAILED_RETRYABLE', 'FAILED_FINAL')) = (failed_at IS NOT NULL))",
    "CHECK ((status IN ('FAILED_RETRYABLE', 'FAILED_FINAL')) = (error_class IS NOT NULL))",
    "CHECK ((status IN ('FAILED_RETRYABLE', 'FAILED_FINAL')) = (last_error_code IS NOT NULL))",
)


class MigrationError(RuntimeError):
    """Raised when migration ownership, ordering, or shape is invalid."""


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _normalize_schema_sql(sql: str | None) -> str:
    """Normalize formatting/identifier case while preserving string literals."""

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


def _schema_objects(
    connection: sqlite3.Connection, expected_names: set[str]
) -> dict[str, sqlite3.Row]:
    expected = {name.casefold() for name in expected_names}
    objects: dict[str, sqlite3.Row] = {}
    for row in connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE type IN ('table', 'index')"
    ):
        folded_name = str(row["name"]).casefold()
        if folded_name not in expected:
            continue
        if folded_name in objects:
            raise MigrationError(f"ambiguous case-insensitive schema object: {row['name']}")
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


def _index_columns(connection: sqlite3.Connection, name: str) -> tuple[str, ...]:
    return tuple(
        str(row["name"]).casefold()
        for row in connection.execute(f"PRAGMA index_info({_quote_identifier(name)})")
    )


def _verify_named_index(
    connection: sqlite3.Connection,
    indexes: dict[str, sqlite3.Row],
    *,
    name: str,
    columns: tuple[str, ...],
    unique: bool,
    partial: bool,
    where_clause: str | None = None,
) -> None:
    row = indexes.get(name.casefold())
    if row is None:
        raise MigrationError(f"missing required analysis_requests index: {name}")
    if row["origin"] != "c" or bool(row["unique"]) is not unique or bool(row["partial"]) is not partial:
        raise MigrationError(f"incompatible index flags: {name}")
    actual_name = str(row["name"])
    actual_columns = _index_columns(connection, actual_name)
    if actual_columns != columns:
        raise MigrationError(
            f"incompatible index columns for {name}: expected {columns!r}, got {actual_columns!r}"
        )
    if where_clause is not None:
        sql_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?", (actual_name,)
        ).fetchone()
        normalized_sql = _normalize_schema_sql(sql_row["sql"] if sql_row is not None else None)
        _, marker, actual_predicate = normalized_sql.rpartition("where")
        expected_predicate = _normalize_schema_sql(where_clause).removeprefix("where")
        if not marker or actual_predicate != expected_predicate:
            raise MigrationError(f"incompatible partial predicate: {name}")


def verify_schema_migrations(connection: sqlite3.Connection) -> None:
    objects = _schema_objects(connection, {"schema_migrations"})
    row = objects.get("schema_migrations")
    if (
        row is None
        or str(row["type"]).casefold() != "table"
        or str(row["tbl_name"]).casefold() != "schema_migrations"
    ):
        raise MigrationError("schema_migrations is missing or has the wrong object type")
    table_name = str(row["name"])
    if _table_columns(connection, table_name) != _REGISTRY_COLUMNS:
        raise MigrationError("incompatible schema_migrations columns")
    registry_sql = _normalize_schema_sql(row["sql"])
    if (
        "versiontextprimarykey" not in registry_sql
        or "applied_attextnotnull" not in registry_sql
        or any(token in registry_sql for token in ("check(", "unique(", "foreignkey("))
    ):
        raise MigrationError("incompatible schema_migrations constraints")

    indexes = list(connection.execute(f"PRAGMA index_list({_quote_identifier(table_name)})"))
    if len(indexes) != 1:
        raise MigrationError("incompatible schema_migrations indexes")
    index = indexes[0]
    if (
        index["origin"] != "pk"
        or not bool(index["unique"])
        or bool(index["partial"])
        or _index_columns(connection, index["name"]) != ("version",)
    ):
        raise MigrationError("incompatible schema_migrations primary key")


def verify_analysis_requests(connection: sqlite3.Connection) -> None:
    objects = _schema_objects(connection, set(_REQUEST_OBJECTS))
    if set(objects) != set(_REQUEST_OBJECTS):
        missing = sorted(set(_REQUEST_OBJECTS) - set(objects))
        raise MigrationError(f"analysis request schema is incomplete; missing objects: {missing}")
    for name, (expected_type, expected_table) in _REQUEST_OBJECTS.items():
        row = objects[name]
        if (
            str(row["type"]).casefold() != expected_type.casefold()
            or str(row["tbl_name"]).casefold() != expected_table.casefold()
        ):
            raise MigrationError(f"incompatible analysis request object: {name}")

    table_name = str(objects["analysis_requests"]["name"])
    if _table_columns(connection, table_name) != _REQUEST_COLUMNS:
        raise MigrationError("incompatible analysis_requests columns")

    table_sql = _normalize_schema_sql(objects["analysis_requests"]["sql"])
    for fragment in _REQUEST_SQL_FRAGMENTS:
        if _normalize_schema_sql(fragment) not in table_sql:
            raise MigrationError(f"analysis_requests is missing required constraint: {fragment}")
    if table_sql.count("check(") != 12:
        raise MigrationError("analysis_requests has unexpected check constraints")

    foreign_keys = {
        (
            str(row["table"]).casefold(),
            str(row["from"]).casefold(),
            str(row["to"]).casefold(),
            row["on_update"],
            row["on_delete"],
            row["match"],
        )
        for row in connection.execute(f"PRAGMA foreign_key_list({_quote_identifier(table_name)})")
    }
    expected_foreign_keys = {
        ("chats", "chat_id", "chat_id", "NO ACTION", "NO ACTION", "NONE"),
        ("messages", "user_message_id", "message_id", "NO ACTION", "NO ACTION", "NONE"),
        ("messages", "assistant_message_id", "message_id", "NO ACTION", "NO ACTION", "NONE"),
    }
    if foreign_keys != expected_foreign_keys:
        raise MigrationError("incompatible analysis_requests foreign keys")

    index_rows = list(connection.execute(f"PRAGMA index_list({_quote_identifier(table_name)})"))
    indexes = {str(row["name"]).casefold(): row for row in index_rows}
    named_indexes = {
        str(row["name"]).casefold() for row in index_rows if row["origin"] == "c"
    }
    expected_named_indexes = set(_REQUEST_OBJECTS) - {"analysis_requests"}
    if named_indexes != expected_named_indexes:
        raise MigrationError("incompatible named analysis_requests indexes")

    unique_constraints = {
        _index_columns(connection, row["name"])
        for row in index_rows
        if row["origin"] == "u" and bool(row["unique"]) and not bool(row["partial"])
    }
    if unique_constraints != {("session_id", "request_id"), ("user_message_id",)}:
        raise MigrationError("incompatible analysis_requests unique constraints")
    if len(index_rows) != 6:
        raise MigrationError("unexpected analysis_requests indexes")
    if any(row["origin"] not in {"c", "u"} for row in index_rows):
        raise MigrationError("unexpected analysis_requests index origin")

    _verify_named_index(
        connection,
        indexes,
        name="ux_analysis_requests_assistant_message",
        columns=("assistant_message_id",),
        unique=True,
        partial=True,
        where_clause="WHERE assistant_message_id IS NOT NULL",
    )
    _verify_named_index(
        connection,
        indexes,
        name="ux_analysis_requests_session_idempotency",
        columns=("session_id", "idempotency_key_digest"),
        unique=True,
        partial=True,
        where_clause="WHERE idempotency_key_digest IS NOT NULL",
    )
    _verify_named_index(
        connection,
        indexes,
        name="ix_analysis_requests_status_updated",
        columns=("status", "updated_at"),
        unique=False,
        partial=False,
    )
    _verify_named_index(
        connection,
        indexes,
        name="ix_analysis_requests_chat_created",
        columns=("chat_id", "created_at", "analysis_request_pk"),
        unique=False,
        partial=False,
    )


def _iter_statements(sql: str) -> Iterator[str]:
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                yield statement
            buffer = ""
    if buffer.strip():
        raise MigrationError("migration resource ends with an incomplete SQL statement")


def _validate_resource(sql: str) -> None:
    for forbidden in (r"\bBEGIN\b", r"\bCOMMIT\b", r"\bPRAGMA\b", r"\bINSERT\b"):
        if re.search(forbidden, sql, flags=re.IGNORECASE):
            raise MigrationError(f"migration resource contains forbidden SQL: {forbidden}")
    if re.search(r"\bschema_migrations\b", sql, flags=re.IGNORECASE):
        raise MigrationError("migration resource must not own schema_migrations")
    if re.search(r"CURRENT_TIMESTAMP|datetime\s*\(", sql, flags=re.IGNORECASE):
        raise MigrationError("migration resource must not contain dynamic timestamps")


class SQLiteMigrator:
    """Own the registry and apply the reviewed request migration in one transaction."""

    def __init__(
        self,
        db_path: Path,
        *,
        connection_factory: Callable[[], sqlite3.Connection] | None = None,
        now_factory: Callable[[], str] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self._connection_factory = connection_factory
        self._now_factory = now_factory or (lambda: datetime.now(timezone.utc).isoformat())

    def _connect(self) -> sqlite3.Connection:
        connection = (
            self._connection_factory()
            if self._connection_factory is not None
            else sqlite3.connect(self.db_path, timeout=10)
        )
        connection.row_factory = sqlite3.Row
        if connection.in_transaction:
            connection.close()
            raise MigrationError("migrator cannot enter a nested transaction")
        connection.execute("PRAGMA foreign_keys = ON")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            connection.close()
            raise MigrationError("failed to enable SQLite foreign keys")
        return connection

    def _load_migration_sql(self) -> str:
        return _MIGRATION_RESOURCE.read_text(encoding="utf-8")

    def migrate(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                verify_base_schema(connection)
            except BaseSchemaError as exc:
                raise MigrationError(f"base schema verification failed: {exc}") from exc

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            verify_schema_migrations(connection)

            applied_versions = {
                row["version"] for row in connection.execute("SELECT version FROM schema_migrations")
            }
            request_objects = set(_schema_objects(connection, set(_REQUEST_OBJECTS)))
            expected_request_objects = set(_REQUEST_OBJECTS)

            unknown_versions = applied_versions - {MIGRATION_VERSION}
            if unknown_versions:
                raise MigrationError(f"unknown future migration versions: {sorted(unknown_versions)}")

            if MIGRATION_VERSION in applied_versions:
                if request_objects != expected_request_objects:
                    raise MigrationError(
                        "recorded migration has incomplete or partial analysis request objects"
                    )
                verify_analysis_requests(connection)
                connection.commit()
                return

            if request_objects:
                raise MigrationError(
                    "migration history is incomplete or inconsistent: analysis request objects exist "
                    "without recorded version"
                )

            sql = self._load_migration_sql()
            _validate_resource(sql)
            for statement in _iter_statements(sql):
                connection.execute(statement)
            verify_analysis_requests(connection)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (MIGRATION_VERSION, self._now_factory()),
            )
            verify_schema_migrations(connection)
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()


__all__ = [
    "MIGRATION_VERSION",
    "MigrationError",
    "SQLiteMigrator",
    "verify_analysis_requests",
    "verify_schema_migrations",
]
