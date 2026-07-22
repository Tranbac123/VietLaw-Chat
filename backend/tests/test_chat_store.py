"""ChatStore tests."""
import pytest

from app.stores.chat_store import ChatStore
from app.errors import ChatNotFound, InvalidRequest


@pytest.fixture
def store(tmp_path):
    return ChatStore(str(tmp_path / "chat.sqlite3"))


def test_create_chat_links_session_and_returns_nonnull_id(store):
    chat = store.create_chat(session_id="s1")
    assert chat.chat_id
    assert chat.session_id == "s1"


def test_create_chat_rejects_empty_session_id(store):
    # Orphan chats forbidden.
    with pytest.raises(InvalidRequest):
        store.create_chat(session_id="")


def test_get_chat_unknown_raises_not_found(store):
    with pytest.raises(ChatNotFound):
        store.get_chat("chat_missing")


def test_session_boundary_mismatch_raises_not_found(store):
    chat = store.create_chat(session_id="owner")
    with pytest.raises(ChatNotFound):
        store.validate_session_boundary(chat, "someone_else")


def test_session_boundary_allows_matching_or_absent_session(store):
    chat = store.create_chat(session_id="owner")
    store.validate_session_boundary(chat, "owner")   # no raise
    store.validate_session_boundary(chat, None)       # no raise (optional when chat_id given)


def test_store_and_load_user_and_assistant_messages(store):
    chat = store.create_chat(session_id="s1")
    uid = store.store_user_message(chat.chat_id, "Tôi bị giữ cọc")
    store.store_assistant_message(
        chat.chat_id, "msg_asst_1", {"domain": "civil_dispute", "summary": "x"}
    )
    detail = store.get_chat_detail(chat.chat_id)
    assert [m.message_id for m in detail.messages] == [uid, "msg_asst_1"]
    assert detail.messages[0].content_type.value == "text"
    assert detail.messages[0].content_text == "Tôi bị giữ cọc"
    assert detail.messages[1].content_type.value == "structured"
    assert detail.messages[1].content_json["domain"] == "civil_dispute"


def test_messages_sorted_by_created_at_then_message_id(store):
    chat = store.create_chat(session_id="s1")
    # Same timestamp → tie-break ascending by message_id.
    store.store_user_message(chat.chat_id, "b", message_id="msg_b", created_at="2026-07-11T00:00:00.000000+00:00")
    store.store_user_message(chat.chat_id, "a", message_id="msg_a", created_at="2026-07-11T00:00:00.000000+00:00")
    store.store_user_message(chat.chat_id, "later", message_id="msg_z", created_at="2026-07-11T00:00:01.000000+00:00")
    detail = store.get_chat_detail(chat.chat_id)
    assert [m.message_id for m in detail.messages] == ["msg_a", "msg_b", "msg_z"]


def test_get_recent_messages_returns_last_n_ascending(store):
    chat = store.create_chat(session_id="s1")
    for i in range(5):
        store.store_user_message(
            chat.chat_id, f"m{i}", message_id=f"msg_{i}",
            created_at=f"2026-07-11T00:00:0{i}.000000+00:00",
        )
    recent = store.get_recent_messages(chat.chat_id, limit=3)
    assert [m.message_id for m in recent] == ["msg_2", "msg_3", "msg_4"]


def test_list_chats_scoped_to_session_and_excludes_deleted(store):
    a = store.create_chat(session_id="s1")
    store.create_chat(session_id="s1")
    store.create_chat(session_id="other")
    store.soft_delete(a.chat_id)
    items = store.list_chats("s1")
    ids = {c.chat_id for c in items}
    assert a.chat_id not in ids
    assert len(items) == 1


def test_get_chat_after_soft_delete_raises_not_found(store):
    chat = store.create_chat(session_id="s1")
    store.soft_delete(chat.chat_id)
    with pytest.raises(ChatNotFound):
        store.get_chat(chat.chat_id)
