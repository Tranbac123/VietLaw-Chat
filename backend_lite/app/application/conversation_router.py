"""Pure mapping from a conversational-intent candidate to a route.

PORT_PATTERN_ONLY from TOMTIT-Agent @ c2295c26a3449d42a411ce319a4fe54f5e3b76e4,
agent_core/conversation/router.py:105-186 (ConversationRouter.route). The
source signature is `route(state: AgentState)` and reads `state.goal`,
re-parses it, and calls a response composer inline. That shape was not
ported: this router does not classify raw text (the caller must run
`social_intent_detector.detect_social_intent` first), does not read any
target runtime state, and does not generate response text -- it only maps
an already-classified `ConversationIntent` to a `RouteResult`.
"""

from __future__ import annotations

from ..contracts.conversation_intent import ConversationIntent
from ..contracts.conversation_route import ConversationRoute, RouteResult

_ROUTE_TABLE: dict[ConversationIntent, tuple[ConversationRoute, str | None, str]] = {
    ConversationIntent.GREETING: (
        ConversationRoute.DIRECT_RESPONSE,
        "greeting",
        "conversation.route.greeting.v1",
    ),
    ConversationIntent.IDENTITY_QUERY: (
        ConversationRoute.DIRECT_RESPONSE,
        "identity",
        "conversation.route.identity.v1",
    ),
    ConversationIntent.CAPABILITY_QUERY: (
        ConversationRoute.DIRECT_RESPONSE,
        "capability",
        "conversation.route.capability.v1",
    ),
    ConversationIntent.UNKNOWN: (
        ConversationRoute.RUNTIME_FALLBACK,
        None,
        "conversation.route.unknown.v1",
    ),
}


def route(intent: ConversationIntent | None) -> RouteResult:
    """Map a conversational-intent candidate to a route.

    `None` (the detector found no social-only candidate) is treated
    identically to `ConversationIntent.UNKNOWN`: RUNTIME_FALLBACK, so the
    existing legal pipeline runs unchanged.
    """
    resolved_intent = intent if intent is not None else ConversationIntent.UNKNOWN
    try:
        target_route, template_id, reason_code = _ROUTE_TABLE[resolved_intent]
    except KeyError as exc:  # fail loudly: an unmapped enum member is a bug, not a fallback
        raise ValueError(f"no route mapping for conversation intent {resolved_intent!r}") from exc
    return RouteResult(
        intent=resolved_intent,
        route=target_route,
        reason_code=reason_code,
        template_id=template_id,
    )


__all__ = ["route"]
