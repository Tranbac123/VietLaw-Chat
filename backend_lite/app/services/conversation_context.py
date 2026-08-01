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
    f"hard cap {RECENT_CONTEXT_CHAR_BUDGET} chars (head-truncated at the boundary)"
)


@dataclass(frozen=True)
class RecentContext:
    """The bounded supporting context actually passed onward.

    ``text`` is guaranteed to satisfy ``len(text) <= RECENT_CONTEXT_CHAR_BUDGET``.
    Nothing downstream may read history other than through this value.
    """

    text: str
    #: The accepted (possibly head-truncated) user turns, oldest first. Cue
    #: detection walks these rather than ``text`` so a match can never span a
    #: message boundary that the joiner happens to create.
    messages: tuple[str, ...]
    messages_considered: int
    truncated: bool


EMPTY_CONTEXT = RecentContext(text="", messages=(), messages_considered=0, truncated=False)

#: Separator between accepted messages in the assembled context string. Counted
#: against the budget so the final string can never exceed it.
_JOINER = "\n"


def build_recent_context(history_messages: list) -> RecentContext:
    """Assemble the bounded same-chat context under a strict character cap.

    Deterministic rule:

    1. take at most the last ``RECENT_CONTEXT_MESSAGE_LIMIT`` messages;
    2. walk them newest-first, keeping only ``role == "user"`` turns;
    3. include a whole message while the remaining budget allows it;
    4. at the boundary, include only the message's leading
       ``remaining`` characters -- a *head* truncation, so the cap is observable
       from the front of the text and a cue sitting past the budget genuinely
       falls outside it;
    5. stop once the budget is exhausted;
    6. reverse the accepted messages so the caller consumes them chronologically.

    The joiner is charged to the budget too, so the returned string satisfies
    ``len(text) <= RECENT_CONTEXT_CHAR_BUDGET`` exactly, not approximately.
    """

    if not history_messages:
        return EMPTY_CONTEXT

    remaining = RECENT_CONTEXT_CHAR_BUDGET
    accepted: list[str] = []
    considered = 0
    truncated = False

    for message in reversed(history_messages[-RECENT_CONTEXT_MESSAGE_LIMIT:]):
        if remaining <= 0:
            break
        if getattr(message, "role", None) != "user":
            continue
        text = getattr(message, "content_text", None)
        if not text:
            continue
        considered += 1
        # Every message after the first costs a joiner as well.
        cost = len(text) + (len(_JOINER) if accepted else 0)
        if cost <= remaining:
            accepted.append(text)
            remaining -= cost
            continue
        allowance = remaining - (len(_JOINER) if accepted else 0)
        if allowance > 0:
            accepted.append(text[:allowance])
            truncated = True
        remaining = 0
        break

    accepted.reverse()
    return RecentContext(
        text=_JOINER.join(accepted),
        messages=tuple(accepted),
        messages_considered=considered,
        truncated=truncated,
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

    # Detection reads ONLY the capped context string. Scanning the raw messages
    # here is what made the declared cap advisory: a cue sitting past the budget
    # inside one oversized message was still found.
    context = build_recent_context(history_messages)
    considered = context.messages_considered
    # Newest first among the accepted turns: the most recent statement wins.
    for text in reversed(context.messages):
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


def has_pending_clarification(history_messages: list) -> bool:
    """Message-level view of whether a clarifying question was just asked.

    **Superseded for routing.** The orchestrator now reads
    ``FastDemoState.pending_clarification``, because this history heuristic
    treats *any* newer user turn as an answer -- so a greeting or a thank-you
    silently closed the question. Retained as the message-level accessor (and
    for callers that only have a transcript), not as the routing authority.

    Read from the persisted ``content_json.clarifying_questions`` field -- a
    field the backend itself produced -- never by parsing assistant prose. The
    signal says only *that* a question is outstanding; it never supplies the
    value of any user fact, which remains the exclusive job of the verified
    current-message fact-update contract.

    Only the latest assistant turn counts: once the user has replied to it with
    real content, a later bare token is no longer answering it.
    """

    for message in reversed(history_messages or []):
        role = getattr(message, "role", None)
        if role == "user":
            # A user turn newer than the question means it was already answered.
            return False
        if role != "assistant":
            continue
        content = getattr(message, "content_json", None)
        if content is None:
            return False
        questions = getattr(content, "clarifying_questions", None)
        if questions is None and isinstance(content, dict):
            questions = content.get("clarifying_questions")
        return bool(questions)
    return False


__all__ = [
    "CONTEXT_WINDOW_POLICY",
    "EMPTY_CONTEXT",
    "RecentContext",
    "build_recent_context",
    "has_pending_clarification",
    "NO_MATTER",
    "RECENT_CONTEXT_CHAR_BUDGET",
    "RECENT_CONTEXT_MESSAGE_LIMIT",
    "RecentMatter",
    "TOPIC_DEPOSIT_GENERAL",
    "TOPIC_DEPOSIT_UNRETURNED",
    "TOPIC_HANDOVER_REFUSED",
    "detect_recent_matter",
]
