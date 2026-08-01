"""VietLaw Public Beta V0: the `IS_LEGAL_OR_RIGHTS_RELATED?` gate.

Only reached for messages `fast_demo_routing.classify_route` already
classified `scope_or_unsupported` (deposit-shaped, social, capability,
identity, memory, acknowledgment, and unsafe messages never reach here --
see `services/legal_fallback_orchestrator.py`). This module decides whether
that residual message is a genuine unclassified LEGAL question (which
deserves a chance at curated-traffic / official-search / general-guidance)
or genuinely unrelated chit-chat (which must fall through to the existing
canned scope response unchanged -- task §3: "Non-legal questions must not
trigger legal web search").

Deliberately a BOUNDED COMBINATION of signals (task §3), never one broad
keyword list and never a model classification acting alone:

  1. a small set of legal-intent phrases (rights/obligation/dispute/
     penalty/document/procedure question forms);
  2. traffic-specific structured extraction (`traffic_classifier.py`)
     reporting *any* topic hit, even a low-confidence one -- a positive
     traffic signal is always legal-intent by definition;
  3. (extension point only) an LLM classification MAY be added later as one
     additional signal, but per task §3 ("Any model classification must not
     itself authorize a legal conclusion") it could only ever be OR'd in
     alongside signals 1-2, never substitute for both being absent. No such
     call exists in this task.
"""

from __future__ import annotations

import re
import unicodedata

_SEPARATORS = re.compile(r"[-_/\\()\[\]{}.·,;:!?\"'“”‘’…]+")


def _normalize(text: str) -> str:
    nfc = unicodedata.normalize("NFC", text)
    decomposed = unicodedata.normalize("NFD", nfc.lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    stripped = stripped.replace("đ", "d")
    spaced = _SEPARATORS.sub(" ", stripped)
    return re.sub(r"\s+", " ", spaced).strip()


#: Bounded legal-intent phrase set. Rights/obligation/dispute/penalty/
#: document/procedure question forms -- a general question ABOUT law or
#: one's own legal situation, not a request for entertainment, weather,
#: coding help, etc.
_LEGAL_INTENT_PHRASES: tuple[str, ...] = (
    "bi phat", "muc phat", "xu phat", "vi pham", "phap luat", "luat quy dinh",
    "quyen loi", "nghia vu", "khieu nai", "khoi kien", "toa an", "hop dong lao dong",
    "giu luong", "sa thai", "boi thuong", "tranh chap", "quyen cua toi", "co duoc phep",
    "co vi pham khong", "bi xu ly the nao", "phap ly", "luat su",
    "quy dinh phap luat", "theo quy dinh", "co quan chuc nang", "giay to phap ly",
    "lan chiem dat", "lan chiem nha",
)

#: A tight set of clearly NON-legal conversational intents that must never
#: be promoted even if a legal-sounding word appears incidentally nearby
#: (e.g. "luật chơi" = "the rules of the game"). Deliberately narrow.
_NON_LEGAL_OVERRIDE_PHRASES: tuple[str, ...] = (
    "thoi tiet", "cong thuc nau an", "luat choi", "ket qua bong da", "gia vang hom nay",
)


def is_legal_or_rights_related(message: str, *, traffic_topic_detected: bool) -> bool:
    """Deterministic bounded gate. `traffic_topic_detected` must come from
    `traffic_classifier.classify(message)` reporting a non-`"unknown"`
    `violation_type` -- callers must not pass a bare keyword match instead.
    """

    normalized = _normalize(message)
    if not normalized:
        return False
    if any(phrase in normalized for phrase in _NON_LEGAL_OVERRIDE_PHRASES):
        return False
    if traffic_topic_detected:
        return True
    return any(phrase in normalized for phrase in _LEGAL_INTENT_PHRASES)


__all__ = ["is_legal_or_rights_related"]
