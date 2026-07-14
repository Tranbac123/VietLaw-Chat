"""SQLite chat store.

Owns chat/message persistence and same-chat context loading. Orphan chats are
forbidden: every chat is linked to a non-empty session_id. Message ordering is
ascending by created_at, tie-broken by message_id.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.errors import ChatNotFound, InvalidRequest
from app.schemas import (
    ChatDetail,
    ChatListItem,
    ChatRecord,
    MessageOut,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content_text TEXT,
    content_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, created_at, message_id);
CREATE INDEX IF NOT EXISTS idx_chats_session ON chats(session_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class ChatStore:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------- chats

    def create_chat(self, session_id: str, title: Optional[str] = None) -> ChatRecord:
        if not session_id:
            raise InvalidRequest("session_id is required to create a chat")
        chat_id = "chat_" + uuid.uuid4().hex[:12]
        ts = _now()
        self._conn.execute(
            "INSERT INTO chats (chat_id, session_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (chat_id, session_id, title, ts, ts),
        )
        self._conn.commit()
        return ChatRecord(chat_id=chat_id, session_id=session_id, title=title,
                          created_at=ts, updated_at=ts)

    def get_chat(self, chat_id: str) -> ChatRecord:
        row = self._conn.execute(
            "SELECT * FROM chats WHERE chat_id = ? AND deleted_at IS NULL", (chat_id,)
        ).fetchone()
        if row is None:
            raise ChatNotFound(f"chat {chat_id} not found")
        return ChatRecord(**dict(row))

    def validate_session_boundary(self, chat: ChatRecord, session_id: Optional[str]) -> None:
        # session_id is optional when chat_id is provided; if given it must match.
        if session_id is not None and chat.session_id != session_id:
            raise ChatNotFound(f"chat {chat.chat_id} not found")

    def soft_delete(self, chat_id: str) -> bool:
        cur = self._conn.execute(
            "UPDATE chats SET deleted_at = ? WHERE chat_id = ? AND deleted_at IS NULL",
            (_now(), chat_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------- messages

    def store_user_message(
        self, chat_id: str, content_text: str,
        message_id: Optional[str] = None, created_at: Optional[str] = None,
    ) -> str:
        mid = message_id or ("msg_user_" + uuid.uuid4().hex[:12])
        self._insert_message(chat_id, mid, "user", "text",
                             content_text=content_text, content_json=None,
                             created_at=created_at)
        return mid

    def store_assistant_message(
        self, chat_id: str, message_id: str, content_json: dict,
        created_at: Optional[str] = None,
    ) -> str:
        self._insert_message(chat_id, message_id, "assistant", "structured",
                             content_text=None, content_json=content_json,
                             created_at=created_at)
        return message_id

    def _insert_message(self, chat_id, message_id, role, content_type,
                        content_text, content_json, created_at) -> None:
        ts = created_at or _now()
        self._conn.execute(
            "INSERT INTO messages "
            "(message_id, chat_id, role, content_type, content_text, content_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (message_id, chat_id, role, content_type, content_text,
             json.dumps(content_json, ensure_ascii=False) if content_json is not None else None,
             ts),
        )
        self._conn.execute("UPDATE chats SET updated_at = ? WHERE chat_id = ?", (ts, chat_id))
        self._conn.commit()

    def get_recent_messages(self, chat_id: str, limit: int) -> list[MessageOut]:
        # Last `limit` messages, returned ascending for context building.
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE chat_id = ? "
            "ORDER BY created_at DESC, message_id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        return [self._row_to_message(r) for r in reversed(rows)]

    def get_chat_detail(self, chat_id: str) -> ChatDetail:
        chat = self.get_chat(chat_id)
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC, message_id ASC",
            (chat_id,),
        ).fetchall()
        return ChatDetail(
            chat_id=chat.chat_id, session_id=chat.session_id, title=chat.title,
            created_at=chat.created_at, updated_at=chat.updated_at,
            messages=[self._row_to_message(r) for r in rows],
        )

    def list_chats(self, session_id: str) -> list[ChatListItem]:
        rows = self._conn.execute(
            "SELECT * FROM chats WHERE session_id = ? AND deleted_at IS NULL "
            "ORDER BY updated_at DESC",
            (session_id,),
        ).fetchall()
        return [self._chat_summary(dict(r)) for r in rows]

    # ------------------------------------------------------------- helpers

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> MessageOut:
        cj = row["content_json"]
        return MessageOut(
            message_id=row["message_id"], role=row["role"],
            content_type=row["content_type"], content_text=row["content_text"],
            content_json=json.loads(cj) if cj else None, created_at=row["created_at"],
        )

    def _chat_summary(self, chat: dict) -> ChatListItem:
        msgs = self._conn.execute(
            "SELECT role, content_type, content_text, content_json FROM messages "
            "WHERE chat_id = ? ORDER BY created_at ASC, message_id ASC",
            (chat["chat_id"],),
        ).fetchall()
        preview, domain, risk = None, None, None
        if msgs:
            last = msgs[-1]
            preview = last["content_text"]
            for m in reversed(msgs):
                if m["role"] == "assistant" and m["content_json"]:
                    data = json.loads(m["content_json"])
                    domain = data.get("domain")
                    risk = data.get("risk_level")
                    if preview is None:
                        preview = data.get("summary")
                    break
        return ChatListItem(
            chat_id=chat["chat_id"], title=chat["title"],
            created_at=chat["created_at"], updated_at=chat["updated_at"],
            last_message_preview=preview, domain=domain, risk_level=risk,
            message_count=len(msgs),
        )
