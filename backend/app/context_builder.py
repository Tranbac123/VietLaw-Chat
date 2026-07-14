"""Same-chat context builder.

MVP strategy: load recent messages from THIS chat only; the prior user turns supply
`context_terms` so a follow-up ("Vậy tôi cần giấy tờ gì?") still retrieves the right
sources. Cross-chat memory is never used. Known/missing-fact extraction is left out
of MVP — context_terms is what RAG actually needs for follow-up continuity.
"""
from dataclasses import dataclass, field

from app.chat_store import ChatStore


@dataclass
class Context:
    recent_messages: list = field(default_factory=list)
    context_terms: str = ""
    context_summary: str = ""
    history_message_count: int = 0
    used_history: bool = False


def build_context(store: ChatStore, chat_id: str, latest_question: str,
                  window: int = 10) -> Context:
    recent = store.get_recent_messages(chat_id, window)
    # The latest user message was already stored; exclude it as "history".
    prior = recent[:-1] if recent else []
    if not prior:
        return Context(recent_messages=recent)

    prior_user_text = [m.content_text for m in prior
                       if m.role.value == "user" and m.content_text]
    context_terms = " ".join(prior_user_text)
    summary = " | ".join(prior_user_text[-3:])
    return Context(
        recent_messages=recent,
        context_terms=context_terms,
        context_summary=summary,
        history_message_count=len(prior),
        used_history=True,
    )
