"""Pure, deterministic detection of conversational-only turns.

Detects greeting / identity / capability turns so the (not-yet-wired) caller
can short-circuit before the legal pipeline. This module has no authority
beyond proposing a candidate: it must never be treated as a router or a
response generator.

Guarantees:
  - pure function, no I/O, no network, no DB, no LLM;
  - no state mutation;
  - does not choose a route, a legal domain, or a safety verdict;
  - does not call `InputNormalizer` or any other normalization service --
    the caller is responsible for passing already-normalized text (see
    Phase A report section 15: normalize_vi() from TOMTIT is DO_NOT_COPY,
    and `application/normalization.py` / `services/input_normalizer.py`
    remain the sole normalization authorities);
  - full-message/high-precision matching only: a social cue mixed with
    residual actionable content (e.g. a legal task) must NOT be classified
    as social-only. TOMTIT-Agent's source greeting cue is already anchored
    this way; its identity/capability cues are plain substring `.search()`
    patterns and were narrowed to full-message anchors here so mixed turns
    like "Bạn là ai và tôi có lấy lại được tiền cọc không?" are correctly
    rejected (see Phase A report section 7, discrepancy 3, and section 22,
    test case 14).
"""

from __future__ import annotations

import re

from ..contracts.conversation_intent import ConversationIntent

# COPY_WITH_ADAPTER from TOMTIT-Agent @ c2295c26a3449d42a411ce319a4fe54f5e3b76e4,
# agent_core/planning/intent_parser.py:31-36 (_GREETING_WORDS). Already
# full-message anchored in source; ported near-verbatim.
_GREETING = re.compile(
    r"^(?:hi|hello|hey|xin\s+chào|chào|alo|ê\s*lô|lô|ê(?:\s+ê)?|helo|ê\s*lo|hê\s*lo)"
    r"(?:\s+(?:bạn|mọi\s+người|anh|chị|em|buổi\s+(?:sáng|trưa|chiều|tối)))?"
    r"\s*[!?.]*\s*$",
    re.IGNORECASE,
)

# COPY_WITH_ADAPTER from TOMTIT-Agent @ c2295c26a3449d42a411ce319a4fe54f5e3b76e4,
# agent_core/planning/intent_parser.py:44-52 (_IDENTITY_CUE). Source cue is a
# substring `.search()` over the whole message; adapted to full-message
# anchors (narrower core phrasings only) to keep mixed identity+task turns
# out of the direct-response route.
_IDENTITY = re.compile(
    r"^(?:bạn|mày)\s+(?:là\s+ai|là\s+g[ìi]|tên\s+(?:là\s+)?g[ìi]|tên\s+g[ìi])\s*\??\s*$"
    r"|^tên\s+(?:bạn|mày)\s+(?:là\s+)?g[ìi]\s*\??\s*$"
    r"|^(?:who|what)\s+are\s+you\s*\??\s*$",
    re.IGNORECASE,
)

# COPY_WITH_ADAPTER from TOMTIT-Agent @ c2295c26a3449d42a411ce319a4fe54f5e3b76e4,
# agent_core/planning/intent_parser.py:57-68 (_CAPABILITY_CUE). Same
# substring-to-full-message-anchor adaptation as _IDENTITY above.
_CAPABILITY = re.compile(
    r"^(?:bạn|mày)\s+(?:"
    r"giúp\s+được(?:\s+(?:những\s+)?g[ìi](?:\s+cho\s+tôi)?)?"
    r"|(?:làm|hỗ\s+trợ)\s+được\s+(?:những\s+)?g[ìi](?:\s+cho\s+tôi)?"
    r"|làm\s+g[ìi]\s+được"
    r"|có\s+thể\s+(?:"
    r"(?:làm|giúp)\s+(?:được\s+)?(?:những\s+)?g[ìi](?:\s+cho\s+tôi)?"
    r"|hỗ\s+trợ(?:\s+tôi)?\s+(?:được\s+)?(?:những\s+)?g[ìi](?:\s+cho\s+tôi)?"
    r")"
    r")\s*[!?.]*\s*$"
    r"|^what\s+can\s+you\s+do\s*\??\s*$"
    r"|^help\s*\??\s*$",
    re.IGNORECASE,
)

_PATTERNS: tuple[tuple[re.Pattern[str], ConversationIntent], ...] = (
    (_GREETING, ConversationIntent.GREETING),
    (_IDENTITY, ConversationIntent.IDENTITY_QUERY),
    (_CAPABILITY, ConversationIntent.CAPABILITY_QUERY),
)


def detect_social_intent(normalized_text: str) -> ConversationIntent | None:
    """Classify a single conversational-only turn, or return None.

    `normalized_text` must already be normalized by the caller (whitespace
    collapsed, accents preserved). Leading/trailing whitespace is trimmed
    locally with `str.strip()` -- this is not a normalization call, just
    defensive handling for callers that pass raw text.
    """
    candidate = normalized_text.strip()
    if not candidate:
        return None
    for pattern, intent in _PATTERNS:
        if pattern.match(candidate):
            return intent
    return None


__all__ = ["detect_social_intent"]
