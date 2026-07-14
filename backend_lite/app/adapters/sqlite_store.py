"""Single-process SQLite implementation of the Gate A request lifecycle.

This adapter deliberately has no startup/bootstrap side effect.  Its caller
must first bootstrap the legacy base schema and apply the reviewed migration.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from ..application.ports import Clock
from ..contracts.internal import (
    BeginRequest,
    BeginRequestAccepted,
    BeginRequestDuplicate,
    BeginRequestInProgress,
    BeginRequestResult,
    BeginRequestRetry,
    BoundedContextQuery,
    CompleteRequest,
    FailRequest,
    MinimalConversationContext,
    RequestIdentity,
    RequestStatus,
    StoredResponse,
    VersionStamps,
)
from ..schemas.content import AnalyzeContent
from ..stores.sqlite_chat_store import BaseSchemaError, verify_base_schema
from .migrator import (
    MIGRATION_VERSION,
    MigrationError,
    verify_analysis_requests,
    verify_schema_migrations,
)


class SQLiteRequestStoreError(RuntimeError):
    """Base failure for the internal request-lifecycle adapter."""


class StoreSchemaError(SQLiteRequestStoreError):
    """The explicit A2a bootstrap/migration precondition was not met."""


class RequestOwnershipError(SQLiteRequestStoreError):
    """A supplied chat is missing, deleted, or belongs to another session."""


class RequestStateError(SQLiteRequestStoreError):
    """A lifecycle command does not own the expected durable request state."""


class DurableRowError(SQLiteRequestStoreError):
    """A manually corrupted durable row cannot be mapped to internal DTOs."""


_ERROR_CLASSES = {"client", "retryable_dependency", "final_deterministic", "internal"}
_ERROR_CODE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_FORBIDDEN_ERROR_DETAIL_KEYS = {
    "carrier",
    "exception",
    "idempotency_key",
    "question",
    "raw_exception",
    "stack",
    "traceback",
}
_CONTENT_KEYS = (
    "domain",
    "risk_level",
    "decision",
    "summary",
    "clarifying_questions",
    "checklist",
    "next_steps",
    "sources",
    "safety_notice",
    "confidence",
    "metadata",
)


def _canonical_json(value: object) -> str:
    """Serialize JSON-only data in the one durable representation."""

    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("payload is not JSON serializable") from exc


def _decode_canonical_object(raw: object, field: str) -> dict[str, object]:
    if not isinstance(raw, str):
        raise DurableRowError(f"durable {field} must be text")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DurableRowError(f"durable {field} is malformed JSON") from exc
    if not isinstance(value, dict) or _canonical_json(value) != raw:
        raise DurableRowError(f"durable {field} is not canonical JSON object")
    return value


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware UTC timestamp")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise DurableRowError(f"durable {field} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DurableRowError(f"durable {field} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DurableRowError(f"durable {field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _safe_error_details(details: dict[str, object]) -> dict[str, object]:
    folded_keys = {key.casefold() for key in details}
    if folded_keys & _FORBIDDEN_ERROR_DETAIL_KEYS:
        raise ValueError("error details contain forbidden raw diagnostic fields")
    canonical = _canonical_json(details)
    decoded = json.loads(canonical)
    if not isinstance(decoded, dict):  # defensive; ``details`` is typed as a dict
        raise ValueError("error details must be an object")
    return decoded


def _validate_error_code(value: str) -> str:
    if not _ERROR_CODE.fullmatch(value):
        raise ValueError("error code must be a short safe token")
    return value


def _validated_version_stamps(stamps: VersionStamps) -> VersionStamps:
    values = (
        stamps.contract_version,
        stamps.corpus_version,
        stamps.policy_version,
        stamps.prompt_version,
        stamps.retriever_version,
        stamps.generator_mode,
        stamps.generator_version,
    )
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("version stamps must be non-empty strings")
    return stamps


@dataclass(frozen=True)
class _DurableRequest:
    identity: RequestIdentity
    status: RequestStatus
    response_payload: dict[str, object] | None
    error_code: str | None
    created_at: str
    updated_at: str
    completed_at: str | None
    failed_at: str | None


class SQLiteRequestChatStore:
    """Implement ``ChatStore`` with short sequential SQLite transactions only."""

    def __init__(self, db_path: Path, clock: Clock) -> None:
        self.db_path = Path(db_path)
        self._clock = clock

    def _checkpoint(self, _name: str) -> None:
        """Private test seam; production code has no externally exposed hook."""

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise StoreSchemaError("A2a base schema and migration must be applied explicitly before store use")
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            connection.close()
            raise StoreSchemaError("failed to enable SQLite foreign keys")
        return connection

    def _verify_ready_schema(self, connection: sqlite3.Connection) -> None:
        try:
            verify_base_schema(connection)
            verify_schema_migrations(connection)
            verify_analysis_requests(connection)
            versions = [row["version"] for row in connection.execute("SELECT version FROM schema_migrations")]
        except (BaseSchemaError, MigrationError, sqlite3.DatabaseError) as exc:
            raise StoreSchemaError("A2a base schema and migration must be exact before store use") from exc
        if versions != [MIGRATION_VERSION]:
            raise StoreSchemaError("A2a migration version is missing, unknown, or duplicated")

    def _begin(self) -> sqlite3.Connection:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._verify_ready_schema(connection)
            return connection
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            connection.close()
            raise

    def _owned_chat(self, connection: sqlite3.Connection, chat_id: str, session_id: str) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT chat_id, session_id, title, created_at, updated_at, deleted_at
            FROM chats WHERE chat_id = ? AND session_id = ? AND deleted_at IS NULL
            """,
            (chat_id, session_id),
        ).fetchone()
        if row is None:
            raise RequestOwnershipError("chat_not_found")
        return row

    def _next_chat_timestamp(self, connection: sqlite3.Connection, chat: sqlite3.Row) -> str:
        values: list[datetime] = [
            _parse_timestamp(chat["created_at"], "chat.created_at"),
            _parse_timestamp(chat["updated_at"], "chat.updated_at"),
        ]
        latest_message = connection.execute(
            "SELECT MAX(created_at) AS created_at FROM messages WHERE chat_id = ?", (chat["chat_id"],)
        ).fetchone()["created_at"]
        if latest_message is not None:
            values.append(_parse_timestamp(latest_message, "message.created_at"))
        high_water = max(values)
        now = _parse_timestamp(_utc_timestamp(self._clock.now_utc()), "clock.now_utc")
        return _utc_timestamp(max(now, high_water + timedelta(microseconds=1)))

    def _new_chat_timestamp(self) -> str:
        return _utc_timestamp(self._clock.now_utc())

    def _validate_request_lifecycle(
        self,
        *,
        status: RequestStatus,
        identity: RequestIdentity,
        response_payload: dict[str, object] | None,
        completed_at: object,
        failed_at: object,
        error_class: object,
        last_error_code: object,
        error_details: dict[str, object] | None,
    ) -> None:
        """Reject any durable row that is inconsistent with its lifecycle state.

        This is intentionally the single read-side mirror of the lifecycle
        CHECKs.  It runs while mapping a durable request, before a duplicate
        can replay, a retry can transition, or a caller can mutate the row.
        """

        no_terminal_or_failure_fields = (
            identity.assistant_message_id is None
            and response_payload is None
            and completed_at is None
            and failed_at is None
            and error_class is None
            and last_error_code is None
            and error_details is None
        )
        if status is RequestStatus.RECEIVED:
            raise DurableRowError("committed RECEIVED durable request is invalid")
        if status is RequestStatus.PROCESSING:
            if not no_terminal_or_failure_fields:
                raise DurableRowError("PROCESSING durable request retains terminal or failure fields")
            return

        if status is RequestStatus.COMPLETE:
            if identity.assistant_message_id is None or response_payload is None or completed_at is None:
                raise DurableRowError("complete durable request is incomplete")
            if failed_at is not None or error_class is not None or last_error_code is not None or error_details is not None:
                raise DurableRowError("complete durable request retains failure fields")
            self._validate_success_payload(
                response_payload,
                request_id=identity.request_id,
                chat_id=identity.chat_id,
                user_message_id=identity.user_message_id,
                assistant_message_id=identity.assistant_message_id,
            )
            return

        if status not in {RequestStatus.FAILED_RETRYABLE, RequestStatus.FAILED_FINAL}:
            raise DurableRowError(f"durable request has unsupported lifecycle status: {status.value}")
        if identity.assistant_message_id is not None or completed_at is not None:
            raise DurableRowError(f"{status.value} durable request retains assistant or completion fields")
        if failed_at is None or error_class not in _ERROR_CLASSES or not isinstance(last_error_code, str):
            raise DurableRowError(f"{status.value} durable request has incomplete failure fields")
        try:
            _validate_error_code(last_error_code)
        except ValueError as exc:
            raise DurableRowError("failed durable request has an unsafe error code") from exc
        if error_details is not None:
            forbidden = {key.casefold() for key in error_details} & _FORBIDDEN_ERROR_DETAIL_KEYS
            if forbidden:
                raise DurableRowError("failed durable request has forbidden raw diagnostic fields")

        if status is RequestStatus.FAILED_RETRYABLE:
            if response_payload is not None:
                raise DurableRowError("retryable durable request retains a terminal response payload")
            return

        if response_payload is None:
            raise DurableRowError("final failure durable request is incomplete")
        self._validate_final_error_payload(response_payload, identity.request_id)
        error = response_payload["error"]
        if not isinstance(error, dict) or error.get("code") != last_error_code:
            raise DurableRowError("final error payload code does not match durable error code")

    def _map_request(self, row: sqlite3.Row) -> _DurableRequest:
        try:
            status = RequestStatus(row["status"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DurableRowError("durable request has an unknown status") from exc
        attempt_count = row["attempt_count"]
        if isinstance(attempt_count, bool) or not isinstance(attempt_count, int) or attempt_count < 1:
            raise DurableRowError("durable request has an invalid attempt count")
        try:
            identity = RequestIdentity(
                session_id=row["session_id"],
                request_id=row["request_id"],
                request_fingerprint=row["request_fingerprint"],
                fingerprint_version=row["fingerprint_version"],
                contract_version=row["contract_version"],
                requested_chat_id=row["requested_chat_id"],
                chat_id=row["chat_id"],
                user_message_id=row["user_message_id"],
                assistant_message_id=row["assistant_message_id"],
                idempotency_key_digest=row["idempotency_key_digest"],
                idempotency_key_digest_version=row["idempotency_key_version"],
                attempt_count=attempt_count,
            )
            _validated_version_stamps(VersionStamps(
                contract_version=row["contract_version"],
                corpus_version=row["corpus_version"],
                policy_version=row["policy_version"],
                prompt_version=row["prompt_version"],
                retriever_version=row["retriever_version"],
                generator_mode=row["generator_mode"],
                generator_version=row["generator_version"],
            ))
            _parse_timestamp(row["created_at"], "request.created_at")
            _parse_timestamp(row["processing_started_at"], "request.processing_started_at")
            _parse_timestamp(row["updated_at"], "request.updated_at")
            if row["completed_at"] is not None:
                _parse_timestamp(row["completed_at"], "request.completed_at")
            if row["failed_at"] is not None:
                _parse_timestamp(row["failed_at"], "request.failed_at")
        except (ValidationError, ValueError, TypeError) as exc:
            raise DurableRowError("durable request identity or version stamps are invalid") from exc

        payload = None
        if row["response_payload"] is not None:
            payload = _decode_canonical_object(row["response_payload"], "response_payload")
        error_details = (
            _decode_canonical_object(row["error_details_json"], "error_details_json")
            if row["error_details_json"] is not None
            else None
        )
        self._validate_request_lifecycle(
            status=status,
            identity=identity,
            response_payload=payload,
            completed_at=row["completed_at"],
            failed_at=row["failed_at"],
            error_class=row["error_class"],
            last_error_code=row["last_error_code"],
            error_details=error_details,
        )

        return _DurableRequest(
            identity=identity,
            status=status,
            response_payload=payload,
            error_code=row["last_error_code"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            failed_at=row["failed_at"],
        )

    @staticmethod
    def _validate_success_payload(
        payload: dict[str, object],
        *,
        request_id: str,
        chat_id: str | None,
        user_message_id: str | None,
        assistant_message_id: str | None,
    ) -> AnalyzeContent:
        expected = {
            "request_id": request_id,
            "chat_id": chat_id,
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise DurableRowError("success response payload IDs do not match durable request")
        if payload.get("contract_version") != "v1" or set(payload) != {
            "contract_version", *expected, *_CONTENT_KEYS
        }:
            raise DurableRowError("success response payload does not match the stored contract shape")
        try:
            content = AnalyzeContent.model_validate({key: payload[key] for key in _CONTENT_KEYS})
        except (KeyError, ValidationError, TypeError) as exc:
            raise DurableRowError("success response payload is not a valid structured response") from exc
        return content

    @staticmethod
    def _validate_final_error_payload(payload: dict[str, object], request_id: str) -> None:
        if set(payload) - {"contract_version", "request_id", "error", "safety_notice"}:
            raise DurableRowError("final error response contains unknown fields")
        if payload.get("contract_version") != "v1" or payload.get("request_id") != request_id:
            raise DurableRowError("final error response does not match durable request")
        error = payload.get("error")
        if not isinstance(error, dict) or not isinstance(error.get("code"), str) or not isinstance(error.get("message"), str):
            raise DurableRowError("final error response is malformed")
        if set(error) - {"code", "message", "details"}:
            raise DurableRowError("final error response contains unknown error fields")
        _validate_error_code(error["code"])
        if not isinstance(payload.get("safety_notice"), str):
            raise DurableRowError("final error response is missing safety notice")

    def _stored_response(self, durable: _DurableRequest, *, error_code: str | None = None) -> StoredResponse:
        return StoredResponse(
            request_id=durable.identity.request_id,
            status=durable.status,
            response_payload=durable.response_payload,
            assistant_message_id=durable.identity.assistant_message_id,
            error_code=error_code if error_code is not None else durable.error_code,
        )

    def _load_request(self, connection: sqlite3.Connection, session_id: str, request_id: str) -> _DurableRequest:
        row = connection.execute(
            "SELECT * FROM analysis_requests WHERE session_id = ? AND request_id = ?", (session_id, request_id)
        ).fetchone()
        if row is None:
            raise RequestStateError("request_not_found")
        durable = self._map_request(row)
        try:
            self._owned_chat(connection, durable.identity.chat_id or "", session_id)
        except RequestOwnershipError as exc:
            raise DurableRowError("durable request links to an unowned or deleted chat") from exc
        self._validate_request_message_links(connection, durable)
        return durable

    @staticmethod
    def _validate_request_message_links(connection: sqlite3.Connection, durable: _DurableRequest) -> None:
        identity = durable.identity
        if identity.requested_chat_id is not None and identity.requested_chat_id != identity.chat_id:
            raise DurableRowError("durable request has inconsistent requested and resolved chat IDs")
        user = connection.execute(
            "SELECT chat_id, role, content_type FROM messages WHERE message_id = ?",
            (identity.user_message_id,),
        ).fetchone()
        if (
            user is None
            or user["chat_id"] != identity.chat_id
            or user["role"] != "user"
            or user["content_type"] != "text"
        ):
            raise DurableRowError("durable request user message link is invalid")
        if identity.assistant_message_id is not None:
            assistant = connection.execute(
                "SELECT chat_id, role, content_type FROM messages WHERE message_id = ?",
                (identity.assistant_message_id,),
            ).fetchone()
            if (
                assistant is None
                or assistant["chat_id"] != identity.chat_id
                or assistant["role"] != "assistant"
                or assistant["content_type"] != "structured"
            ):
                raise DurableRowError("durable request assistant message link is invalid")

    def _result_for_duplicate(self, durable: _DurableRequest, fingerprint: str) -> BeginRequestResult:
        if durable.identity.request_fingerprint != fingerprint:
            return BeginRequestDuplicate(
                status=durable.status,
                identity=durable.identity,
                should_execute=False,
                stored_response=self._stored_response(durable, error_code="IDEMPOTENCY_KEY_REUSED"),
            )
        if durable.status is RequestStatus.COMPLETE or durable.status is RequestStatus.FAILED_FINAL:
            return BeginRequestDuplicate(
                status=durable.status,
                identity=durable.identity,
                should_execute=False,
                stored_response=self._stored_response(durable),
            )
        if durable.status is RequestStatus.PROCESSING:
            return BeginRequestInProgress(
                status=RequestStatus.PROCESSING,
                identity=durable.identity,
                should_execute=False,
            )
        raise DurableRowError("durable request has no valid duplicate outcome")

    def begin_request(self, command: BeginRequest) -> BeginRequestResult:
        connection = self._begin()
        try:
            chat: sqlite3.Row | None = None
            if command.requested_chat_id is not None:
                chat = self._owned_chat(connection, command.requested_chat_id, command.session_id)

            if command.idempotency_key_digest is not None:
                row = connection.execute(
                    "SELECT * FROM analysis_requests WHERE session_id = ? AND idempotency_key_digest = ?",
                    (command.session_id, command.idempotency_key_digest),
                ).fetchone()
                if row is not None:
                    durable = self._map_request(row)
                    self._owned_chat(connection, durable.identity.chat_id or "", command.session_id)
                    self._validate_request_message_links(connection, durable)
                    if durable.status is RequestStatus.FAILED_RETRYABLE and (
                        durable.identity.request_fingerprint == command.request_fingerprint
                    ):
                        retry_time = _utc_timestamp(self._clock.now_utc())
                        connection.execute(
                            """
                            UPDATE analysis_requests
                            SET status = ?, attempt_count = ?, error_class = NULL,
                                last_error_code = NULL, error_details_json = NULL,
                                response_payload = NULL, failed_at = NULL,
                                processing_started_at = ?, processing_deadline_at = NULL, updated_at = ?
                            WHERE session_id = ? AND request_id = ? AND status = ? AND attempt_count = ?
                            """,
                            (
                                RequestStatus.PROCESSING.value,
                                durable.identity.attempt_count + 1,
                                retry_time,
                                retry_time,
                                command.session_id,
                                durable.identity.request_id,
                                RequestStatus.FAILED_RETRYABLE.value,
                                durable.identity.attempt_count,
                            ),
                        )
                        refreshed = self._load_request(connection, command.session_id, durable.identity.request_id)
                        connection.commit()
                        return BeginRequestRetry(
                            status=refreshed.status,
                            identity=refreshed.identity,
                            should_execute=True,
                            user_message_created=False,
                        )
                    result = self._result_for_duplicate(durable, command.request_fingerprint)
                    connection.commit()
                    return result

            if chat is None:
                if command.chat_id_candidate is None or command.new_chat_title is None:
                    raise ValueError("new chat requests require candidate chat ID and title")
                timestamp = self._new_chat_timestamp()
                connection.execute(
                    """
                    INSERT INTO chats(chat_id, session_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (command.chat_id_candidate, command.session_id, command.new_chat_title, timestamp, timestamp),
                )
                chat_id = command.chat_id_candidate
            else:
                timestamp = self._next_chat_timestamp(connection, chat)
                chat_id = str(chat["chat_id"])

            if command.user_message_id_candidate is None:
                raise ValueError("new requests require a candidate user message ID")
            stamps = _validated_version_stamps(command.version_stamps)
            connection.execute(
                """
                INSERT INTO analysis_requests(
                    session_id, request_id, idempotency_key_version, idempotency_key_digest,
                    fingerprint_version, request_fingerprint, status, attempt_count,
                    requested_chat_id, chat_id, user_type, language, user_message_id,
                    contract_version, corpus_version, policy_version, prompt_version,
                    retriever_version, generator_mode, generator_version,
                    created_at, processing_started_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command.session_id,
                    command.request_id,
                    command.idempotency_key_digest_version,
                    command.idempotency_key_digest,
                    command.fingerprint_version,
                    command.request_fingerprint,
                    RequestStatus.RECEIVED.value,
                    command.requested_chat_id,
                    chat_id,
                    command.user_type,
                    command.language,
                    command.user_message_id_candidate,
                    stamps.contract_version,
                    stamps.corpus_version,
                    stamps.policy_version,
                    stamps.prompt_version,
                    stamps.retriever_version,
                    stamps.generator_mode,
                    stamps.generator_version,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            self._checkpoint("after_request_insert_before_user")
            connection.execute(
                """
                INSERT INTO messages(message_id, chat_id, role, content_type, content_text, content_json, created_at)
                VALUES (?, ?, 'user', 'text', ?, NULL, ?)
                """,
                (command.user_message_id_candidate, chat_id, command.question, timestamp),
            )
            connection.execute("UPDATE chats SET updated_at = ? WHERE chat_id = ?", (timestamp, chat_id))
            self._checkpoint("after_user_before_commit")
            transitioned = connection.execute(
                """
                UPDATE analysis_requests
                SET status = ?, processing_started_at = ?, updated_at = ?
                WHERE session_id = ? AND request_id = ? AND status = ?
                """,
                (
                    RequestStatus.PROCESSING.value,
                    timestamp,
                    timestamp,
                    command.session_id,
                    command.request_id,
                    RequestStatus.RECEIVED.value,
                ),
            )
            if transitioned.rowcount != 1:
                raise RequestStateError("new request could not enter processing")
            durable = self._load_request(connection, command.session_id, command.request_id)
            connection.commit()
            return BeginRequestAccepted(
                status=durable.status,
                identity=durable.identity,
                should_execute=True,
                user_message_created=True,
            )
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def complete_request(self, command: CompleteRequest) -> StoredResponse:
        content = self._validate_success_payload(
            command.response_payload,
            request_id=command.request_id,
            chat_id=command.chat_id,
            user_message_id=command.user_message_id,
            assistant_message_id=command.assistant_message_id,
        )
        payload_json = _canonical_json(command.response_payload)
        content_json = _canonical_json(content.model_dump(mode="json"))
        connection = self._begin()
        try:
            durable = self._load_request(connection, command.session_id, command.request_id)
            identity = durable.identity
            matches = (
                identity.request_fingerprint == command.request_fingerprint
                and identity.attempt_count == command.attempt_count
                and identity.chat_id == command.chat_id
                and identity.user_message_id == command.user_message_id
            )
            if durable.status is RequestStatus.COMPLETE:
                if (
                    not matches
                    or identity.assistant_message_id != command.assistant_message_id
                    or durable.response_payload != command.response_payload
                ):
                    raise RequestStateError("completed request does not match completion command")
                connection.commit()
                return self._stored_response(durable)
            if durable.status is not RequestStatus.PROCESSING or not matches:
                raise RequestStateError("completion does not own the expected processing attempt")
            existing = connection.execute(
                "SELECT 1 FROM messages WHERE message_id = ?", (command.assistant_message_id,)
            ).fetchone()
            if existing is not None:
                raise RequestStateError("assistant candidate ID is already in use")
            chat = self._owned_chat(connection, command.chat_id, command.session_id)
            timestamp = self._next_chat_timestamp(connection, chat)
            connection.execute(
                """
                INSERT INTO messages(message_id, chat_id, role, content_type, content_text, content_json, created_at)
                VALUES (?, ?, 'assistant', 'structured', NULL, ?, ?)
                """,
                (command.assistant_message_id, command.chat_id, content_json, timestamp),
            )
            self._checkpoint("after_assistant_insert_before_complete")
            connection.execute(
                """
                UPDATE analysis_requests
                SET response_payload = ?, assistant_message_id = ?, status = ?,
                    completed_at = ?, updated_at = ?
                WHERE session_id = ? AND request_id = ? AND status = ? AND attempt_count = ?
                """,
                (
                    payload_json,
                    command.assistant_message_id,
                    RequestStatus.COMPLETE.value,
                    timestamp,
                    timestamp,
                    command.session_id,
                    command.request_id,
                    RequestStatus.PROCESSING.value,
                    command.attempt_count,
                ),
            )
            self._checkpoint("after_response_update_before_commit")
            connection.execute("UPDATE chats SET updated_at = ? WHERE chat_id = ?", (timestamp, command.chat_id))
            completed = self._load_request(connection, command.session_id, command.request_id)
            connection.commit()
            return self._stored_response(completed)
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def fail_request(self, command: FailRequest) -> None:
        if command.error_class not in _ERROR_CLASSES:
            raise ValueError("error class is not approved for durable storage")
        _validate_error_code(command.last_error_code)
        details = _safe_error_details(command.error_details_redacted)
        if command.status is RequestStatus.FAILED_RETRYABLE:
            if command.response_payload is not None:
                raise ValueError("retryable failures must not store a terminal response payload")
            payload_json = None
        else:
            if command.response_payload is None:
                raise ValueError("final failures require a public error payload")
            self._validate_final_error_payload(command.response_payload, command.request_id)
            error = command.response_payload["error"]
            if not isinstance(error, dict) or error.get("code") != command.last_error_code:
                raise ValueError("final error payload code must match last error code")
            payload_json = _canonical_json(command.response_payload)
        connection = self._begin()
        try:
            durable = self._load_request(connection, command.session_id, command.request_id)
            identity = durable.identity
            if (
                durable.status is not RequestStatus.PROCESSING
                or identity.request_fingerprint != command.request_fingerprint
                or identity.attempt_count != command.attempt_count
                or identity.assistant_message_id is not None
            ):
                raise RequestStateError("failure does not own the expected processing attempt")
            timestamp = _utc_timestamp(self._clock.now_utc())
            updated = connection.execute(
                """
                UPDATE analysis_requests
                SET status = ?, error_class = ?, last_error_code = ?, error_details_json = ?,
                    response_payload = ?, failed_at = ?, updated_at = ?
                WHERE session_id = ? AND request_id = ? AND status = ? AND attempt_count = ?
                """,
                (
                    command.status.value,
                    command.error_class,
                    command.last_error_code,
                    _canonical_json(details),
                    payload_json,
                    timestamp,
                    timestamp,
                    command.session_id,
                    command.request_id,
                    RequestStatus.PROCESSING.value,
                    command.attempt_count,
                ),
            )
            if updated.rowcount != 1:
                raise RequestStateError("failure lost ownership of processing attempt")
            self._checkpoint("during_failure_update_before_commit")
            self._load_request(connection, command.session_id, command.request_id)
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def load_bounded_context(self, query: BoundedContextQuery) -> MinimalConversationContext:
        connection = self._connect()
        try:
            self._verify_ready_schema(connection)
            self._owned_chat(connection, query.chat_id, query.session_id)
            current = connection.execute(
                """
                SELECT message_id, chat_id, role, created_at FROM messages
                WHERE message_id = ? AND chat_id = ? AND role = 'user'
                """,
                (query.current_user_message_id, query.chat_id),
            ).fetchone()
            if current is None:
                raise RequestStateError("current durable user message is missing")
            durable_current_row = connection.execute(
                """
                SELECT * FROM analysis_requests
                WHERE session_id = ? AND chat_id = ? AND user_message_id = ?
                """,
                (query.session_id, query.chat_id, query.current_user_message_id),
            ).fetchone()
            if durable_current_row is None:
                raise RequestStateError("current user message is not a durable request cutoff")
            durable_current = self._map_request(durable_current_row)
            self._validate_request_message_links(connection, durable_current)
            _parse_timestamp(current["created_at"], "current_user_message.created_at")
            assistants = connection.execute(
                """
                SELECT message_id, content_json FROM messages
                WHERE chat_id = ? AND role = 'assistant'
                  AND (created_at < ? OR (created_at = ? AND message_id < ?))
                ORDER BY created_at DESC, message_id DESC
                """,
                (query.chat_id, current["created_at"], current["created_at"], current["message_id"]),
            ).fetchall()
            clarifications: list[str] = []
            clarification_id: str | None = None
            topic: str | None = None
            domain: str | None = None
            topic_id: str | None = None
            for row in assistants:
                parsed = _decode_canonical_object(row["content_json"], "assistant content_json")
                try:
                    content = AnalyzeContent.model_validate(parsed)
                except ValidationError as exc:
                    raise DurableRowError("assistant content_json is not a valid structured response") from exc
                if not clarifications and content.clarifying_questions:
                    clarifications = [item[:300] for item in content.clarifying_questions[:5] if item.strip()]
                    clarification_id = row["message_id"]
                if topic is None:
                    candidate = content.metadata.get("confirmed_topic")
                    if isinstance(candidate, str) and candidate.strip() and len(candidate) <= 64:
                        topic = candidate
                        domain = content.domain
                        topic_id = row["message_id"]
                if clarifications and topic is not None:
                    break
            return MinimalConversationContext(
                current_question=query.current_question,
                last_assistant_clarification=clarifications,
                last_assistant_message_id=clarification_id,
                last_confirmed_topic=topic,
                last_confirmed_domain=domain,
                last_confirmed_message_id=topic_id,
                used_current_chat_history=bool(clarifications or topic),
            )
        finally:
            connection.close()


__all__ = [
    "DurableRowError",
    "RequestOwnershipError",
    "RequestStateError",
    "SQLiteRequestChatStore",
    "SQLiteRequestStoreError",
    "StoreSchemaError",
]
