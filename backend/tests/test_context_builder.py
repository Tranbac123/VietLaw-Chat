"""Context builder. Same-chat only, follow-up support."""
import pytest

from app.chat_store import ChatStore
from app.context_builder import build_context


@pytest.fixture
def store(tmp_path):
    return ChatStore(str(tmp_path / "c.sqlite3"))


def test_first_turn_has_no_history(store):
    chat = store.create_chat(session_id="s1")
    store.store_user_message(chat.chat_id, "Tôi thuê nhà giữ tiền cọc không trả")
    ctx = build_context(store, chat.chat_id, "Tôi thuê nhà giữ tiền cọc không trả")
    assert ctx.used_history is False
    assert ctx.history_message_count == 0
    assert ctx.context_terms == ""


def test_followup_carries_prior_question_terms(store):
    chat = store.create_chat(session_id="s1")
    store.store_user_message(chat.chat_id, "Tôi thuê nhà, chủ nhà giữ tiền cọc không trả")
    store.store_assistant_message(chat.chat_id, "msg_a1",
                                  {"domain": "civil_dispute", "summary": "..."})
    store.store_user_message(chat.chat_id, "Vậy tôi cần chuẩn bị giấy tờ gì?")
    ctx = build_context(store, chat.chat_id, "Vậy tôi cần chuẩn bị giấy tờ gì?")
    assert ctx.used_history is True
    assert ctx.history_message_count >= 2
    assert "cọc" in ctx.context_terms or "thuê" in ctx.context_terms
