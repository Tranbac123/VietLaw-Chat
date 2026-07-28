"""Bounded same-chat conversational working memory. Zero provider calls.

Why this exists
---------------
Route selection used to ask a single question -- "does the persisted structured
state already hold a rental fact?" -- and treated a ``no`` as "this chat has no
legal matter". That is wrong whenever the user has *described* a situation whose
facts were never extracted into a slot (the model was unavailable, or the turn
carried no verifiable span). The chat then answered a legitimate follow-up such
as "tôi nên làm gì?" with a scope refusal asking the user to restate a problem
they had already explained two turns earlier.

This module supplies the missing signal from messages that are *already
persisted* for the chat, so no new store, vector index or long-term-memory
service is introduced.

Authority
---------
This is **supporting context only**. It answers "is there an unresolved rental
matter in this chat, and roughly what is it about?" and nothing else. It never
returns a fact value, never writes state, and never feeds
``apply_fact_updates``. Only *user* turns are inspected: an assistant's own
prose must never become the evidence that a user fact exists (see the Phase B
contract, "assistant prose cannot create authoritative rental facts").

Bound
-----
At most ``RECENT_CONTEXT_MESSAGE_LIMIT`` messages, newest first, and at most
``RECENT_CONTEXT_CHAR_BUDGET`` characters of user text. The message bound
matches ``Settings.context_message_limit`` (8), i.e. roughly the last four
exchanges, which covers the demo's longest scripted sequence (greeting, intake,
issue, greeting, follow-up = 5 turns) with room to spare while keeping an old,
abandoned topic from being resurrected many turns later.
"""

from __future__ import annotations

from dataclasses import dataclass

from .fast_demo_routing import normalize_for_cue

#: Newest-first message cap. Mirrors ``Settings.context_message_limit``.
RECENT_CONTEXT_MESSAGE_LIMIT = 8
#: Secondary cap so a few very long turns cannot blow the scan budget.
RECENT_CONTEXT_CHAR_BUDGET = 4000

#: Human-readable description of the bound, surfaced in response metadata.
CONTEXT_WINDOW_POLICY = (
    f"last {RECENT_CONTEXT_MESSAGE_LIMIT} same-chat messages, user turns only, "
    f"max {RECENT_CONTEXT_CHAR_BUDGET} chars"
)

# A rental-deposit matter is "present in this chat" when a user turn mentioned
# it. Kept deliberately close to the router's deposit vocabulary so routing and
# context activation cannot drift apart.
_MATTER_CUES: tuple[str, ...] = (
    "dat coc", "tien coc", "tien dat coc", "coc thue nha", "bo coc", "hoan coc",
    "hoan tra coc", "mat coc", "chu nha", "thue nha", "thue phong", "tra phong",
    "hop dong thue", "giay dat coc", "ban giao nha", "nhan nha",
)

# Refinements. These pick which unresolved issue is most recent; they never
# assert a fact value into state.
_HANDOVER_CUES: tuple[str, ...] = (
    "khong cho vao o", "chua cho vao o", "khong cho nhan nha", "chua ban giao",
    "khong ban giao", "chua duoc ban giao", "chua nhan duoc nha", "chua nhan nha",
    "khong giao nha", "chua vao o duoc", "khong vao o duoc",
)
_UNRETURNED_CUES: tuple[str, ...] = (
    "khong tra lai coc", "chua tra lai coc", "khong tra coc", "chua tra coc",
    "khong hoan coc", "chua hoan coc", "khong hoan tra", "chua hoan tra",
    "khong tra lai tien coc", "chua tra lai tien coc", "khong tra lai tien",
    "giu tien coc", "quyt coc",
)

#: Unresolved-issue topics, most specific first.
TOPIC_HANDOVER_REFUSED = "handover_refused"
TOPIC_DEPOSIT_UNRETURNED = "deposit_unreturned"
TOPIC_DEPOSIT_GENERAL = "deposit_general"


@dataclass(frozen=True)
class RecentMatter:
    """What the bounded window says about this chat's unresolved legal matter."""

    active: bool
    topic: str | None
    considered_messages: int

    @property
    def handover_refused(self) -> bool:
        return self.topic == TOPIC_HANDOVER_REFUSED


NO_MATTER = RecentMatter(active=False, topic=None, considered_messages=0)


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)


def detect_recent_matter(
    history_messages: list, *, current_message: str | None = None
) -> RecentMatter:
    """Scan the bounded window for an unresolved rental matter.

    ``history_messages`` is the same-chat window the context builder already
    assembled; callers must never pass messages from another chat. Returns
    :data:`NO_MATTER` for an empty or unrelated chat, which is what keeps a
    vague follow-up in a fresh chat on the clarification path instead of
    inventing a rental scenario.

    ``current_message`` is inspected first and outranks history when choosing
    the topic, per the authority rule that the current turn wins. It does not
    count towards ``considered_messages``, which reports only how much *history*
    was actually read.
    """

    budget = RECENT_CONTEXT_CHAR_BUDGET
    considered = 0
    topic: str | None = None
    active = False

    if current_message:
        normalized = normalize_for_cue(current_message)
        if _contains_any(normalized, _MATTER_CUES):
            active = True
            if _contains_any(normalized, _HANDOVER_CUES):
                topic = TOPIC_HANDOVER_REFUSED
            elif _contains_any(normalized, _UNRETURNED_CUES):
                topic = TOPIC_DEPOSIT_UNRETURNED

    if not history_messages:
        if not active:
            return NO_MATTER
        return RecentMatter(
            active=True, topic=topic or TOPIC_DEPOSIT_GENERAL, considered_messages=0
        )

    # Newest first: the most recent statement of the issue wins.
    for message in reversed(history_messages[-RECENT_CONTEXT_MESSAGE_LIMIT:]):
        if budget <= 0:
            break
        if getattr(message, "role", None) != "user":
            continue
        text = getattr(message, "content_text", None)
        if not text:
            continue
        budget -= len(text)
        considered += 1
        normalized = normalize_for_cue(text)
        if not _contains_any(normalized, _MATTER_CUES):
            continue
        active = True
        if topic is None:
            if _contains_any(normalized, _HANDOVER_CUES):
                topic = TOPIC_HANDOVER_REFUSED
            elif _contains_any(normalized, _UNRETURNED_CUES):
                topic = TOPIC_DEPOSIT_UNRETURNED

    if not active:
        return RecentMatter(active=False, topic=None, considered_messages=considered)
    return RecentMatter(
        active=True,
        topic=topic or TOPIC_DEPOSIT_GENERAL,
        considered_messages=considered,
    )


__all__ = [
    "CONTEXT_WINDOW_POLICY",
    "NO_MATTER",
    "RECENT_CONTEXT_CHAR_BUDGET",
    "RECENT_CONTEXT_MESSAGE_LIMIT",
    "RecentMatter",
    "TOPIC_DEPOSIT_GENERAL",
    "TOPIC_DEPOSIT_UNRETURNED",
    "TOPIC_HANDOVER_REFUSED",
    "detect_recent_matter",
]
