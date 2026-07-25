"""Conversation routing outcome for the pure social short-circuit kernel.

Answers a narrower question than `schemas.content.Decision`: not "what kind
of legal answer is this" but "does this turn need the legal pipeline at
all". First-wave only; CLARIFICATION and LLM_RESPONSE are not ported --
there is no first-wave caller for either. See:

  docs/plans (Phase A): TOMTIT_TO_VIETLAW_INTENT_PORT_PLAN_V1.md, sections 14, 19.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .conversation_intent import ConversationIntent


class ConversationRoute(str, Enum):
    """PORT_PATTERN_ONLY from TOMTIT-Agent @ c2295c26a3449d42a411ce319a4fe54f5e3b76e4,
    agent_core/conversation/models.py:14-18 (ConversationRoute) -- only the
    DIRECT_RESPONSE/RUNTIME_FALLBACK subset is kept."""

    DIRECT_RESPONSE = "DIRECT_RESPONSE"
    RUNTIME_FALLBACK = "RUNTIME_FALLBACK"


@dataclass(frozen=True)
class RouteResult:
    """Outcome of routing a conversational-intent candidate.

    Deliberately carries no response text, legal Decision, domain, risk, or
    sources -- the router only selects a route and, for direct responses, a
    template identifier. Response text generation stays with the templates
    module (see response_templates.py) so routing and response-authorship
    remain separate authorities.
    """

    intent: ConversationIntent
    route: ConversationRoute
    reason_code: str
    template_id: str | None = None


__all__ = ["ConversationRoute", "RouteResult"]
