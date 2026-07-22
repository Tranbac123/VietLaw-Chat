"""Chat persistence endpoints. Session ownership is validated before any chat
or message field is returned; missing, deleted, and wrong-session chats all
surface as 404 chat_not_found (ChatStore raises it) without revealing the owner.
"""
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_core
from app.runtime.analyze import AiCore
from app.schemas import (
    ChatCreateRequest,
    ChatCreateResponse,
    ChatDetail,
    ChatListResponse,
    DeleteChatResponse,
)

router = APIRouter(prefix="/api/chats", tags=["chats"])


@router.post("", response_model=ChatCreateResponse)
def create_chat(payload: ChatCreateRequest, core: AiCore = Depends(get_core)) -> ChatCreateResponse:
    chat = core.store.create_chat(payload.session_id, payload.title)
    return ChatCreateResponse(
        chat_id=chat.chat_id,
        session_id=chat.session_id,
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
    )


@router.get("", response_model=ChatListResponse)
def list_chats(
    session_id: str = Query(min_length=1, max_length=128),
    core: AiCore = Depends(get_core),
) -> ChatListResponse:
    return ChatListResponse(session_id=session_id, chats=core.store.list_chats(session_id))


@router.get("/{chat_id}", response_model=ChatDetail)
def get_chat(
    chat_id: str,
    session_id: str = Query(min_length=1, max_length=128),
    core: AiCore = Depends(get_core),
) -> ChatDetail:
    chat = core.store.get_chat(chat_id)  # ChatNotFound -> 404 (missing/deleted)
    core.store.validate_session_boundary(chat, session_id)  # wrong session -> 404
    return core.store.get_chat_detail(chat_id)


@router.delete("/{chat_id}", response_model=DeleteChatResponse)
def delete_chat(
    chat_id: str,
    session_id: str = Query(min_length=1, max_length=128),
    core: AiCore = Depends(get_core),
) -> DeleteChatResponse:
    chat = core.store.get_chat(chat_id)  # ChatNotFound -> 404 (missing/deleted)
    core.store.validate_session_boundary(chat, session_id)  # wrong session -> 404
    core.store.soft_delete(chat_id)
    return DeleteChatResponse(chat_id=chat_id, deleted=True)
