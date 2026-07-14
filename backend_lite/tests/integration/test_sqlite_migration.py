from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import backend_lite.app.adapters.migrator as migrator_module
import backend_lite.app.stores.sqlite_chat_store as chat_store_module
from backend_lite.app.adapters.migrator import (
    MIGRATION_VERSION,
    MigrationError,
    SQLiteMigrator,
    verify_analysis_requests,
    verify_schema_migrations,
)
from backend_lite.app.stores.sqlite_chat_store import BaseSchemaError, SQLiteChatStore, verify_base_schema


def _connect(path: Path, *, foreign_keys: bool = True) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    if foreign_keys:
        connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _bootstrap(path: Path) -> SQLiteChatStore:
    store = SQLiteChatStore(path)
    store.bootstrap_base_schema()
    return store


def _migrate(path: Path) -> SQLiteMigrator:
    migrator = SQLiteMigrator(path, now_factory=lambda: "2026-07-13T00:00:00+00:00")
    migrator.migrate()
    return migrator


def _objects(path: Path) -> dict[str, str]:
    with _connect(path) as connection:
        return {
            row["name"]: row["type"]
            for row in connection.execute(
                "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_autoindex_%'"
            )
        }


def _migration_resource() -> str:
    return (
        Path(migrator_module.__file__).with_name("migrations") / "001_analysis_requests.sql"
    ).read_text(encoding="utf-8")


def _case_and_whitespace_variant(sql: str) -> str:
    """Change keyword/identifier case and whitespace, preserving SQL literals."""

    output: list[str] = []
    index = 0
    while index < len(sql):
        character = sql[index]
        if character == "'":
            output.append(character)
            index += 1
            while index < len(sql):
                output.append(sql[index])
                if sql[index] == "'":
                    if index + 1 < len(sql) and sql[index + 1] == "'":
                        output.append(sql[index + 1])
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            continue
        if character.isspace():
            if output and output[-1] != "\n  ":
                output.append("\n  ")
            index += 1
            continue
        output.append(character.upper())
        index += 1
    variant = "".join(output)
    replacements = {
        "UX_ANALYSIS_REQUESTS_ASSISTANT_MESSAGE": "Ux_AnAlYsIs_ReQuEsTs_AsSiStAnT_MeSsAgE",
        "UX_ANALYSIS_REQUESTS_SESSION_IDEMPOTENCY": "Ux_AnAlYsIs_ReQuEsTs_SeSsIoN_IdEmPoTeNcY",
        "IX_ANALYSIS_REQUESTS_STATUS_UPDATED": "Ix_AnAlYsIs_ReQuEsTs_StAtUs_UpDaTeD",
        "IX_ANALYSIS_REQUESTS_CHAT_CREATED": "Ix_AnAlYsIs_ReQuEsTs_ChAt_CrEaTeD",
        "ANALYSIS_REQUESTS": "AnAlYsIs_ReQuEsTs",
        "ANALYSIS_REQUEST_PK": "AnAlYsIs_ReQuEsT_Pk",
        "SESSION_ID": "SeSsIoN_Id",
        "REQUEST_ID": "ReQuEsT_Id",
        "ASSISTANT_MESSAGE_ID": "AsSiStAnT_MeSsAgE_Id",
    }
    for original, replacement in replacements.items():
        variant = variant.replace(original, replacement)
    return variant


def _install_recorded_request_schema(path: Path, request_sql: str) -> None:
    with _connect(path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.executescript(request_sql)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (MIGRATION_VERSION, "2026-07-13T00:00:00+00:00"),
        )


def _create_complete_base_with_messages_sql(path: Path, messages_sql: str) -> None:
    with _connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE chats (
                chat_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT NULL
            )
            """
        )
        connection.execute(messages_sql)
        connection.execute("CREATE INDEX idx_chats_session_updated ON chats(session_id, updated_at)")
        connection.execute(
            "CREATE INDEX idx_messages_chat_created ON messages(chat_id, created_at, message_id)"
        )


def test_constructor_has_no_schema_side_effect(tmp_path: Path) -> None:
    path = tmp_path / "constructor.sqlite3"
    SQLiteChatStore(path)
    assert not path.exists()


def test_empty_db_bootstraps_exact_base_objects(tmp_path: Path) -> None:
    path = tmp_path / "empty.sqlite3"
    _bootstrap(path)
    with _connect(path) as connection:
        verify_base_schema(connection)
        objects = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_autoindex_%'"
            )
        }
    assert objects == {
        "chats",
        "messages",
        "idx_chats_session_updated",
        "idx_messages_chat_created",
    }


def test_exact_complete_base_is_accepted_without_data_change(tmp_path: Path) -> None:
    path = tmp_path / "complete.sqlite3"
    store = _bootstrap(path)
    with _connect(path) as connection:
        connection.execute(
            "INSERT INTO chats VALUES (?, ?, ?, ?, ?, NULL)",
            ("chat_keep", "session_keep", "Keep", "t1", "t1"),
        )
        before_sql = {
            row["name"]: row["sql"]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_autoindex_%'"
            )
        }
    store.bootstrap_base_schema()
    with _connect(path) as connection:
        after_sql = {
            row["name"]: row["sql"]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_autoindex_%'"
            )
        }
        assert connection.execute("SELECT title FROM chats WHERE chat_id = 'chat_keep'").fetchone()[0] == "Keep"
    assert after_sql == before_sql


def test_capitalization_equivalent_base_schema_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "base-case-variant.sqlite3"
    with _connect(path) as connection:
        connection.executescript(
            """
            CrEaTe TaBlE ChAtS (
                ChAt_Id TeXt PrImArY KeY,
                SeSsIoN_Id TeXt NoT NuLl,
                TiTlE TeXt NoT NuLl,
                CrEaTeD_At TeXt NoT NuLl,
                UpDaTeD_At TeXt NoT NuLl,
                DeLeTeD_At TeXt NuLl
            );
            CrEaTe TaBlE MeSsAgEs (
                MeSsAgE_Id TeXt PrImArY KeY,
                ChAt_Id TeXt NoT NuLl,
                RoLe TeXt NoT NuLl ChEcK(RoLe In ('user', 'assistant')),
                CoNtEnT_TyPe TeXt NoT NuLl ChEcK(CoNtEnT_TyPe In ('text', 'structured')),
                CoNtEnT_TeXt TeXt NuLl,
                CoNtEnT_JsOn TeXt NuLl,
                CrEaTeD_At TeXt NoT NuLl,
                FoReIgN KeY(ChAt_Id) ReFeReNcEs ChAtS(ChAt_Id)
            );
            CrEaTe InDeX IdX_ChAtS_SeSsIoN_UpDaTeD On ChAtS(SeSsIoN_Id, UpDaTeD_At);
            CrEaTe InDeX IdX_MeSsAgEs_ChAt_CrEaTeD On MeSsAgEs(ChAt_Id, CrEaTeD_At, MeSsAgE_Id);
            """
        )
    SQLiteChatStore(path).bootstrap_base_schema()
    with _connect(path) as connection:
        verify_base_schema(connection)


def test_partial_base_fails_loud_without_filling_missing_objects(tmp_path: Path) -> None:
    path = tmp_path / "partial.sqlite3"
    with _connect(path) as connection:
        connection.execute("CREATE TABLE chats (chat_id TEXT PRIMARY KEY)")
    with pytest.raises(BaseSchemaError, match="partial"):
        SQLiteChatStore(path).bootstrap_base_schema()
    assert _objects(path) == {"chats": "table"}


def test_incompatible_base_column_fails_loud(tmp_path: Path) -> None:
    path = tmp_path / "wrong-column.sqlite3"
    with _connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE chats (
                chat_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, title INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE messages (
                message_id TEXT PRIMARY KEY, chat_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content_type TEXT NOT NULL CHECK(content_type IN ('text', 'structured')),
                content_text TEXT NULL, content_json TEXT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY(chat_id) REFERENCES chats(chat_id)
            )
            """
        )
        connection.execute("CREATE INDEX idx_chats_session_updated ON chats(session_id, updated_at)")
        connection.execute(
            "CREATE INDEX idx_messages_chat_created ON messages(chat_id, created_at, message_id)"
        )
    with pytest.raises(BaseSchemaError, match="chats columns"):
        SQLiteChatStore(path).bootstrap_base_schema()


def test_missing_base_index_fails_loud(tmp_path: Path) -> None:
    path = tmp_path / "missing-index.sqlite3"
    _bootstrap(path)
    with _connect(path) as connection:
        connection.execute("DROP INDEX idx_messages_chat_created")
    with pytest.raises(BaseSchemaError, match="partial"):
        SQLiteChatStore(path).bootstrap_base_schema()
    assert "idx_messages_chat_created" not in _objects(path)


def test_wrong_base_index_columns_fail_loud(tmp_path: Path) -> None:
    path = tmp_path / "wrong-index.sqlite3"
    _bootstrap(path)
    with _connect(path) as connection:
        connection.execute("DROP INDEX idx_messages_chat_created")
        connection.execute("CREATE INDEX idx_messages_chat_created ON messages(created_at, chat_id)")
    with pytest.raises(BaseSchemaError, match="index columns"):
        SQLiteChatStore(path).bootstrap_base_schema()


def test_missing_messages_check_and_fk_fail_loud(tmp_path: Path) -> None:
    path = tmp_path / "wrong-messages.sqlite3"
    _create_complete_base_with_messages_sql(
        path,
        """
        CREATE TABLE messages (
            message_id TEXT PRIMARY KEY, chat_id TEXT NOT NULL,
            role TEXT NOT NULL, content_type TEXT NOT NULL,
            content_text TEXT NULL, content_json TEXT NULL, created_at TEXT NOT NULL
        )
        """,
    )
    with pytest.raises(BaseSchemaError, match="constraint|foreign keys"):
        SQLiteChatStore(path).bootstrap_base_schema()


def test_bootstrap_verification_failure_rolls_back_all_additions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rollback-base.sqlite3"
    real_verify = chat_store_module.verify_base_schema

    def fail_after_verification(connection: sqlite3.Connection) -> None:
        real_verify(connection)
        raise BaseSchemaError("injected verification failure")

    monkeypatch.setattr(chat_store_module, "verify_base_schema", fail_after_verification)
    with pytest.raises(BaseSchemaError, match="injected"):
        SQLiteChatStore(path).bootstrap_base_schema()
    assert _objects(path) == {}


def test_migration_fails_if_base_schema_does_not_exist(tmp_path: Path) -> None:
    path = tmp_path / "no-base.sqlite3"
    with pytest.raises(MigrationError, match="base schema verification failed"):
        _migrate(path)
    assert _objects(path) == {}


def test_migration_fails_before_001_for_partial_base(tmp_path: Path) -> None:
    path = tmp_path / "partial-before-001.sqlite3"
    with _connect(path) as connection:
        connection.execute("CREATE TABLE chats (chat_id TEXT PRIMARY KEY)")
    with pytest.raises(MigrationError, match="base schema verification failed"):
        _migrate(path)
    assert "schema_migrations" not in _objects(path)
    assert "analysis_requests" not in _objects(path)


def test_migration_fails_before_001_for_incompatible_base(tmp_path: Path) -> None:
    path = tmp_path / "incompatible-before-001.sqlite3"
    _bootstrap(path)
    with _connect(path) as connection:
        connection.execute("DROP INDEX idx_chats_session_updated")
        connection.execute("CREATE INDEX idx_chats_session_updated ON chats(updated_at, session_id)")
    with pytest.raises(MigrationError, match="base schema verification failed"):
        _migrate(path)
    assert "schema_migrations" not in _objects(path)
    assert "analysis_requests" not in _objects(path)


def test_first_run_creates_registry_request_table_and_version(tmp_path: Path) -> None:
    path = tmp_path / "first-run.sqlite3"
    _bootstrap(path)
    _migrate(path)
    with _connect(path) as connection:
        verify_base_schema(connection)
        verify_schema_migrations(connection)
        verify_analysis_requests(connection)
        versions = connection.execute(
            "SELECT version, applied_at FROM schema_migrations"
        ).fetchall()
    assert [tuple(row) for row in versions] == [(MIGRATION_VERSION, "2026-07-13T00:00:00+00:00")]


def test_analysis_requests_has_all_expected_named_indexes_and_foreign_keys(tmp_path: Path) -> None:
    path = tmp_path / "shape.sqlite3"
    _bootstrap(path)
    _migrate(path)
    with _connect(path) as connection:
        indexes = {
            row["name"]: (bool(row["unique"]), bool(row["partial"]))
            for row in connection.execute("PRAGMA index_list(analysis_requests)")
            if row["origin"] == "c"
        }
        foreign_keys = {
            (row["from"], row["table"], row["to"])
            for row in connection.execute("PRAGMA foreign_key_list(analysis_requests)")
        }
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'analysis_requests'"
        ).fetchone()[0]
    assert indexes == {
        "ux_analysis_requests_assistant_message": (True, True),
        "ux_analysis_requests_session_idempotency": (True, True),
        "ix_analysis_requests_status_updated": (False, False),
        "ix_analysis_requests_chat_created": (False, False),
    }
    assert foreign_keys == {
        ("chat_id", "chats", "chat_id"),
        ("user_message_id", "messages", "message_id"),
        ("assistant_message_id", "messages", "message_id"),
    }
    assert table_sql.upper().count("DEFERRABLE INITIALLY DEFERRED") == 2


def test_second_run_is_noop_but_verifies_shape(tmp_path: Path) -> None:
    path = tmp_path / "twice.sqlite3"
    _bootstrap(path)
    _migrate(path)
    before = _objects(path)
    _migrate(path)
    with _connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1
        verify_analysis_requests(connection)
    assert _objects(path) == before


def test_recorded_version_with_missing_request_table_fails_without_recreate(tmp_path: Path) -> None:
    path = tmp_path / "version-without-request-table.sqlite3"
    _bootstrap(path)
    _migrate(path)
    with _connect(path) as connection:
        connection.execute("DROP TABLE analysis_requests")
    with pytest.raises(MigrationError, match="recorded migration.*incomplete"):
        _migrate(path)
    objects = _objects(path)
    assert "analysis_requests" not in objects
    with _connect(path) as connection:
        assert connection.execute("SELECT version FROM schema_migrations").fetchone()[0] == MIGRATION_VERSION


def test_exact_request_schema_without_version_fails_without_reconstructing_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "orphan-exact-request-schema.sqlite3"
    _bootstrap(path)
    _migrate(path)
    with _connect(path) as connection:
        connection.execute(
            "INSERT INTO chats VALUES (?, ?, ?, ?, ?, NULL)",
            ("chat_orphan", "session_orphan", "Orphan", "t1", "t1"),
        )
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, NULL, ?)",
            ("msg_orphan", "chat_orphan", "user", "text", "preserve me", "t1"),
        )
        connection.execute("DELETE FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,))
    before_objects = _objects(path)
    migrator = SQLiteMigrator(path)
    monkeypatch.setattr(
        migrator,
        "_load_migration_sql",
        lambda: pytest.fail("orphan schema must fail before loading migration resource"),
    )

    with pytest.raises(MigrationError, match="history is incomplete or inconsistent"):
        migrator.migrate()

    assert _objects(path) == before_objects
    with _connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 0
        assert connection.execute("SELECT title FROM chats WHERE chat_id = 'chat_orphan'").fetchone()[0] == "Orphan"
        assert connection.execute(
            "SELECT content_text FROM messages WHERE message_id = 'msg_orphan'"
        ).fetchone()[0] == "preserve me"


def test_capitalization_and_whitespace_equivalent_recorded_schema_is_accepted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "case-equivalent.sqlite3"
    _bootstrap(path)
    request_sql = _case_and_whitespace_variant(_migration_resource())
    with _connect(path) as connection:
        connection.execute(
            "CrEaTe TaBlE ScHeMa_MiGrAtIoNs (VeRsIoN TeXt PrImArY KeY, ApPlIeD_At TeXt NoT NuLl)"
        )
        connection.executescript(request_sql)
        connection.execute(
            "INSERT INTO ScHeMa_MiGrAtIoNs(VeRsIoN, ApPlIeD_At) VALUES (?, ?)",
            (MIGRATION_VERSION, "2026-07-13T00:00:00+00:00"),
        )

    _migrate(path)

    with _connect(path) as connection:
        verify_schema_migrations(connection)
        verify_analysis_requests(connection)
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'index')"
            )
        }
        assert connection.execute("SELECT COUNT(*) FROM ScHeMa_MiGrAtIoNs").fetchone()[0] == 1
    assert "AnAlYsIs_ReQuEsTs" in names
    assert "Ux_AnAlYsIs_ReQuEsTs_AsSiStAnT_MeSsAgE" in names


def test_existing_chats_and_messages_are_preserved_without_backfill(tmp_path: Path) -> None:
    path = tmp_path / "preserve.sqlite3"
    _bootstrap(path)
    with _connect(path) as connection:
        connection.execute(
            "INSERT INTO chats VALUES (?, ?, ?, ?, ?, NULL)",
            ("chat_legacy", "session_legacy", "Legacy", "t1", "t2"),
        )
        connection.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, NULL, ?)",
            ("msg_legacy", "chat_legacy", "user", "text", "legacy content", "t2"),
        )
    _migrate(path)
    _migrate(path)
    with _connect(path) as connection:
        chat = connection.execute("SELECT * FROM chats").fetchone()
        message = connection.execute("SELECT * FROM messages").fetchone()
        request_count = connection.execute("SELECT COUNT(*) FROM analysis_requests").fetchone()[0]
    assert dict(chat)["title"] == "Legacy"
    assert dict(message)["content_text"] == "legacy content"
    assert request_count == 0


def test_001_resource_contains_request_ddl_only() -> None:
    resource = (
        Path(migrator_module.__file__).with_name("migrations") / "001_analysis_requests.sql"
    ).read_text(encoding="utf-8")
    upper = resource.upper()
    assert "ANALYSIS_REQUESTS" in upper
    assert "SCHEMA_MIGRATIONS" not in upper
    assert "BEGIN" not in upper
    assert "COMMIT" not in upper
    assert "PRAGMA" not in upper
    assert "INSERT INTO" not in upper
    assert "CURRENT_TIMESTAMP" not in upper


def test_failed_migration_rolls_back_registry_request_ddl_and_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "atomic-failure.sqlite3"
    _bootstrap(path)
    migrator = SQLiteMigrator(path)
    valid_resource = migrator._load_migration_sql()  # noqa: SLF001 - failure injection
    monkeypatch.setattr(
        migrator,
        "_load_migration_sql",
        lambda: f"{valid_resource}\nCREATE TABLE invalid_sql(;",
    )
    with pytest.raises(sqlite3.OperationalError):
        migrator.migrate()
    objects = _objects(path)
    assert "schema_migrations" not in objects
    assert "analysis_requests" not in objects
    assert not any(name.startswith(("ux_analysis_requests", "ix_analysis_requests")) for name in objects)


def test_failure_after_version_insert_rolls_back_entire_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "after-version-insert.sqlite3"
    _bootstrap(path)
    real_verify_registry = migrator_module.verify_schema_migrations
    call_count = 0

    def fail_after_insert(connection: sqlite3.Connection) -> None:
        nonlocal call_count
        call_count += 1
        real_verify_registry(connection)
        if call_count == 2:
            assert connection.execute(
                "SELECT version FROM schema_migrations"
            ).fetchone()[0] == MIGRATION_VERSION
            raise MigrationError("injected post-version failure")

    monkeypatch.setattr(migrator_module, "verify_schema_migrations", fail_after_insert)
    with pytest.raises(MigrationError, match="post-version"):
        _migrate(path)
    assert "schema_migrations" not in _objects(path)
    assert "analysis_requests" not in _objects(path)


def test_partial_unversioned_request_schema_is_not_repaired(tmp_path: Path) -> None:
    path = tmp_path / "partial-request.sqlite3"
    _bootstrap(path)
    with _connect(path) as connection:
        connection.execute("CREATE TABLE analysis_requests (analysis_request_pk INTEGER PRIMARY KEY)")
    with pytest.raises(MigrationError, match="incomplete"):
        _migrate(path)
    objects = _objects(path)
    assert objects["analysis_requests"] == "table"
    assert "schema_migrations" not in objects


def test_recorded_migration_does_not_hide_corrupted_request_schema(tmp_path: Path) -> None:
    path = tmp_path / "corrupt-request.sqlite3"
    _bootstrap(path)
    _migrate(path)
    with _connect(path) as connection:
        connection.execute("DROP INDEX ix_analysis_requests_status_updated")
    with pytest.raises(MigrationError, match="incomplete"):
        _migrate(path)
    assert "ix_analysis_requests_status_updated" not in _objects(path)
    with _connect(path) as connection:
        assert connection.execute("SELECT version FROM schema_migrations").fetchone()[0] == MIGRATION_VERSION


def test_wrong_request_index_order_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "wrong-request-index-order.sqlite3"
    _bootstrap(path)
    _migrate(path)
    with _connect(path) as connection:
        connection.execute("DROP INDEX ix_analysis_requests_chat_created")
        connection.execute(
            "CREATE INDEX ix_analysis_requests_chat_created "
            "ON analysis_requests(created_at, chat_id, analysis_request_pk)"
        )
    with pytest.raises(MigrationError, match="index columns"):
        _migrate(path)


def test_wrong_partial_index_predicate_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "wrong-partial-predicate.sqlite3"
    _bootstrap(path)
    _migrate(path)
    with _connect(path) as connection:
        connection.execute("DROP INDEX ux_analysis_requests_assistant_message")
        connection.execute(
            "CREATE UNIQUE INDEX ux_analysis_requests_assistant_message "
            "ON analysis_requests(assistant_message_id) WHERE assistant_message_id IS NULL"
        )
    with pytest.raises(MigrationError, match="partial predicate"):
        _migrate(path)


@pytest.mark.parametrize(
    ("original", "corrupted"),
    [
        ("attempt_count >= 1", "attempt_count >= 0"),
        ("'RECEIVED', 'PROCESSING'", "'received', 'PROCESSING'"),
    ],
)
def test_altered_request_check_is_rejected(
    tmp_path: Path, original: str, corrupted: str
) -> None:
    path = tmp_path / f"altered-check-{len(corrupted)}.sqlite3"
    _bootstrap(path)
    request_sql = _migration_resource().replace(original, corrupted, 1)
    assert request_sql != _migration_resource()
    _install_recorded_request_schema(path, request_sql)
    with pytest.raises(MigrationError, match="constraint"):
        _migrate(path)


def test_missing_deferred_message_foreign_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "missing-deferred-fk.sqlite3"
    _bootstrap(path)
    request_sql = _migration_resource().replace("DEFERRABLE INITIALLY DEFERRED", "", 1)
    _install_recorded_request_schema(path, request_sql)
    with pytest.raises(MigrationError, match="constraint"):
        _migrate(path)


def test_extra_request_column_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "extra-request-column.sqlite3"
    _bootstrap(path)
    request_sql = _migration_resource().replace(
        "failed_at TEXT NULL,",
        "failed_at TEXT NULL,\n    unexpected_column TEXT NULL,",
        1,
    )
    _install_recorded_request_schema(path, request_sql)
    with pytest.raises(MigrationError, match="analysis_requests columns"):
        _migrate(path)


def test_corrupted_schema_migrations_fails_loud_without_repair(tmp_path: Path) -> None:
    path = tmp_path / "corrupt-registry.sqlite3"
    _bootstrap(path)
    _migrate(path)
    with _connect(path) as connection:
        connection.execute("ALTER TABLE schema_migrations ADD COLUMN unexpected TEXT")
    with pytest.raises(MigrationError, match="schema_migrations columns"):
        _migrate(path)
    with _connect(path) as connection:
        assert [row["name"] for row in connection.execute("PRAGMA table_info(schema_migrations)")] == [
            "version",
            "applied_at",
            "unexpected",
        ]


def test_unknown_future_version_fails_without_changing_data(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    _bootstrap(path)
    _migrate(path)
    with _connect(path) as connection:
        connection.execute(
            "INSERT INTO chats VALUES (?, ?, ?, ?, ?, NULL)",
            ("chat_future", "session_future", "Future", "t1", "t1"),
        )
        connection.execute(
            "INSERT INTO schema_migrations VALUES (?, ?)",
            ("999_future", "2026-07-14T00:00:00+00:00"),
        )
    with pytest.raises(MigrationError, match="unknown future"):
        _migrate(path)
    with _connect(path) as connection:
        assert connection.execute("SELECT title FROM chats WHERE chat_id = 'chat_future'").fetchone()[0] == "Future"
        assert {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations")
        } == {MIGRATION_VERSION, "999_future"}


def test_migrator_rejects_nested_transaction(tmp_path: Path) -> None:
    path = tmp_path / "nested.sqlite3"
    _bootstrap(path)

    def connection_factory() -> sqlite3.Connection:
        connection = sqlite3.connect(path)
        connection.execute("BEGIN")
        return connection

    with pytest.raises(MigrationError, match="nested transaction"):
        SQLiteMigrator(path, connection_factory=connection_factory).migrate()


def test_foreign_keys_are_enabled_before_single_begin_immediate(tmp_path: Path) -> None:
    path = tmp_path / "trace.sqlite3"
    _bootstrap(path)
    statements: list[str] = []

    def connection_factory() -> sqlite3.Connection:
        connection = sqlite3.connect(path)
        connection.set_trace_callback(statements.append)
        return connection

    SQLiteMigrator(
        path,
        connection_factory=connection_factory,
        now_factory=lambda: "2026-07-13T00:00:00+00:00",
    ).migrate()
    normalized = [statement.strip().upper() for statement in statements]
    begin_positions = [index for index, statement in enumerate(normalized) if statement.startswith("BEGIN")]
    pragma_position = next(
        index for index, statement in enumerate(normalized) if statement.startswith("PRAGMA FOREIGN_KEYS = ON")
    )
    assert len(begin_positions) == 1
    assert normalized[begin_positions[0]] == "BEGIN IMMEDIATE"
    assert pragma_position < begin_positions[0]
