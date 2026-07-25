"""Conversational-turn intent taxonomy for the pure social short-circuit kernel.

First-wave only. Deliberately excludes legal domain, legal risk, legal
Decision, safety verdicts, tool intents, and memory intents -- those remain
owned by their existing modules. See:

  docs/plans (Phase A): TOMTIT_TO_VIETLAW_INTENT_PORT_PLAN_V1.md, section 19.
"""

from __future__ import annotations

from enum import Enum


class ConversationIntent(str, Enum):
    """A candidate conversational intent for the current turn's raw text.

    PORT_PATTERN_ONLY from TOMTIT-Agent @ c2295c26a3449d42a411ce319a4fe54f5e3b76e4,
    agent_core/planning/intents.py:8-31 (IntentName) -- only the conversational
    subset is kept; tool/memory/planning members were not ported.
    """

    GREETING = "GREETING"
    IDENTITY_QUERY = "IDENTITY_QUERY"
    CAPABILITY_QUERY = "CAPABILITY_QUERY"
    UNKNOWN = "UNKNOWN"


__all__ = ["ConversationIntent"]
