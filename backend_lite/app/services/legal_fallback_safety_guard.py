"""VietLaw Public Beta V0: an additional, narrow safety gate for the
legal-fallback vertical only (task §9).

The runtime hook in `agent_runtime.py` already gates this vertical on the
baseline `unsafe_patterns.json`-driven detector (`state.classification.
unsafe_intent_detected`) and on FAST DEMO V2's own narrower `is_unsafe()`.
Neither of those two existing, frozen safety layers covers bribery/
corruption of officials or unauthorized government-system access -- before
this task that gap was harmless (an unmatched message just fell through to
the inert canned "out of scope" text), but this vertical now answers
"scope" turns with real curated/official legal content, which would let a
bribery-shaped request be unintentionally "rescued" with a genuinely helpful
answer instead of refused (task §9: "explicitly test... bribing officials...
unauthorized government-system access").

Deliberately narrow and additive: this module gates ONLY this vertical
(returning `True` makes `LegalFallbackOrchestrator.handle()` defer, exactly
like any other narrow miss), and never modifies the frozen baseline
`unsafe_patterns.json` data, `fast_demo_routing.py`, or their classification
output.
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


#: Bribery / corruption of an official. Narrow verb+object combination, not a
#: bare keyword: "tôi cần giữ tiền" alone must not match.
_BRIBERY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:dua\s*tien|hoi\s*lo|lo\s*lot|chi\s*tien|dut\s*lot|chay\s*an)\b"
        r"[^.]{0,40}\b(?:canh\s*sat|cong\s*an|can\s*bo|quan\s*chuc|nguoi\s*co\s*tham\s*quyen|"
        r"thanh\s*tra|toa\s*an|tham\s*phan)\b"
    ),
    re.compile(
        r"\b(?:canh\s*sat|cong\s*an|can\s*bo|quan\s*chuc|thanh\s*tra)\b[^.]{0,40}"
        r"\b(?:nhan\s*tien|de\s*bo\s*qua|de\s*khong\s*lap\s*bien\s*ban)\b"
    ),
)

#: Unauthorized access to a government/official system.
_UNAUTHORIZED_ACCESS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:hack|xam\s*nhap|truy\s*cap\s*trai\s*phep|pha\s*mat\s*khau|danh\s*cap\s*tai\s*khoan)\b"
        r"[^.]{0,40}\b(?:he\s*thong|co\s*so\s*du\s*lieu|website|cong\s*thong\s*tin)\b[^.]{0,40}"
        r"\b(?:nha\s*nuoc|chinh\s*phu|cong\s*an|co\s*quan)\b"
    ),
)

_ALL_PATTERNS = _BRIBERY_PATTERNS + _UNAUTHORIZED_ACCESS_PATTERNS


def is_unsafe_for_legal_fallback(message: str) -> bool:
    """Narrow, additive unsafe check scoped to this vertical only. Never
    authoritative for the rest of the runtime -- it only ever causes THIS
    vertical to defer, exactly like any other narrow miss."""

    normalized = _normalize(message)
    if not normalized:
        return False
    return any(pattern.search(normalized) is not None for pattern in _ALL_PATTERNS)


__all__ = ["is_unsafe_for_legal_fallback"]
