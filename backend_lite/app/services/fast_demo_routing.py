"""FAST DEMO V2 deterministic first-level routing. Zero provider calls.

Five first-level routes only: social, capability, unsafe, scope_or_unsupported,
legal_conversation. Everything finer (fact update, clarification answer,
correction, follow-up, draft, redraft) is a *response mode* decided inside the
single legal-turn model call -- not a route.

Cue matching runs on an accent-stripped, punctuation-flattened form, so
"Xin chào", "xin chào?", "xin chao?" and "  XIN CHÀO !!  " are one token
sequence. This is the fix for the live-test failures where accentless
Vietnamese fell through to a scope refusal.

Full-message anchoring is retained on purpose: a greeting mixed with actionable
legal content ("Xin chào, tôi đã đặt cọc 20 triệu") is NOT social.
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum

_SEPARATORS = re.compile(r"[-_/\\()\[\]{}.·,;:!?\"'“”‘’…]+")


class FastDemoRoute(str, Enum):
    SOCIAL = "social"
    CAPABILITY = "capability"
    ACKNOWLEDGMENT = "acknowledgment"
    LEGAL_CONVERSATION = "legal_conversation"
    UNSAFE = "unsafe"
    SCOPE_OR_UNSUPPORTED = "scope_or_unsupported"


def normalize_for_cue(text: str) -> str:
    """NFC -> lower -> strip Vietnamese diacritics -> separators to space -> collapse."""

    nfc = unicodedata.normalize("NFC", text)
    decomposed = unicodedata.normalize("NFD", nfc.lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    stripped = stripped.replace("đ", "d").replace("Đ", "d")
    spaced = _SEPARATORS.sub(" ", stripped)
    return re.sub(r"\s+", " ", spaced).strip()


# Trailing courtesy particles absorbed by the anchors below.
_TAIL = r"(?:\s+(?:nhe|nha|a|ah|vay|the|voi|với))?"

_SOCIAL_RE = re.compile(
    r"^(?:"
    r"xin\s+chao|chao|hi|hello|hey|helo|alo|e\s*lo|lo|good\s+morning|good\s+evening"
    r")"
    r"(?:\s+(?:ban|anh|chi|em|moi\s+nguoi|shop|ad))?"
    r"(?:\s+buoi\s+(?:sang|trua|chieu|toi))?"
    + _TAIL + r"$"
)

# Optional object/qualifier between the verb and the interrogative, e.g.
# "giúp TÔI VIỆC gì", "giúp ĐƯỢC NHỮNG gì cho tôi". Kept as one shared fragment so
# every capability phrasing accepts the same set rather than each listing its own.
_CAP_OBJ = r"(?:\s+(?:toi|minh|duoc|nhung|viec|gi\s+viec))*"
_CAP_TAIL_OBJ = r"(?:\s+(?:cho\s+toi|cho\s+minh|khong|a|the\s+nao))?"
_CAP_ACTOR = r"(?:ban|may|bot|ai|em|cau)"
_CAP_VERB = r"(?:lam|giup|ho\s+tro|tro\s+giup|assist)"

_CAPABILITY_RE = re.compile(
    r"^(?:"
    # "bạn làm được gì" / "bạn giúp tôi được gì" / "bạn giúp tôi việc gì" /
    # "bạn hỗ trợ được những gì cho tôi" — object may sit before OR after the verb.
    rf"{_CAP_ACTOR}\s+{_CAP_VERB}{_CAP_OBJ}\s+gi{_CAP_TAIL_OBJ}"
    # "bạn làm gì được"
    rf"|{_CAP_ACTOR}\s+{_CAP_VERB}\s+gi\s+duoc"
    # "bạn có thể giúp tôi việc gì" / "bạn có thể làm gì" / "bạn có thể hỗ trợ gì"
    rf"|{_CAP_ACTOR}\s+co\s+the\s+{_CAP_VERB}{_CAP_OBJ}\s+gi{_CAP_TAIL_OBJ}"
    # "tôi có thể hỏi bạn gì" / "tôi hỏi bạn được gì" / "mình có thể nhờ bạn việc gì"
    rf"|(?:toi|minh)\s+(?:co\s+the\s+)?(?:hoi|nho|yeu\s+cau)\s+{_CAP_ACTOR}{_CAP_OBJ}\s+gi{_CAP_TAIL_OBJ}"
    # identity, folded into capability for the demo
    rf"|{_CAP_ACTOR}\s+la\s+ai"
    rf"|{_CAP_ACTOR}\s+ten\s+(?:la\s+)?gi"
    rf"|ten\s+{_CAP_ACTOR}\s+(?:la\s+)?gi"
    r"|who\s+are\s+you|what\s+are\s+you|what\s+can\s+you\s+do|help"
    r")"
    + _TAIL + r"$"
)

# Bare acknowledgments: "ok", "vâng", "cảm ơn". These carry no new instruction,
# so they get a short reply rather than the scope blurb that used to answer them
# — telling someone who just said "cảm ơn" that we only handle deposit matters
# reads as though the assistant forgot the conversation it is in.
#
# Full-message anchored for the same reason as the greeting: "ok vậy tôi nên làm
# gì?" carries a real question and must stay on the legal path.
_ACKNOWLEDGMENT_RE = re.compile(
    r"^(?:"
    # "k" is deliberately absent: in Vietnamese chat it abbreviates "không" (no),
    # not "ok", so treating it as agreement would misread a refusal.
    r"ok|oke|okey|okay|okie|dc|duoc|duoc roi|ro|ro roi|hieu roi|da hieu"
    r"|vang|da|u|um|uh|hm|hmm|yes|yep|yeah|sure|fine|got it|noted"
    r"|dong y|nhat tri|chuan|dung roi|the nhe|vay nhe"
    r"|cam on|cam on ban|cam on nhe|thanks|thank you|thank u|tks|thx|ty"
    r")"
    + _TAIL + r"$"
)

# Short tokens that are *answers* when a structured clarification is pending, or
# when a legal matter is already active. "Chưa." replying to "Bạn đã được bàn
# giao nhà chưa?" carries real meaning; consuming it as small talk throws the
# user's answer away. These never establish a fact themselves -- they only route
# the turn into legal processing, where the existing verified current-message
# fact-update contract decides what (if anything) is recorded.
#
# `cảm ơn`/`thanks` and `ok` are deliberately NOT here: gratitude and a bare
# "ok" are not answers to a yes/no question, so they stay social.
_ANSWER_TOKEN_RE = re.compile(
    r"^(?:"
    r"chua|chua co|chua a|chua ah|van chua|chua he"
    r"|khong|khong co|khong a|khong ah|khong phai|chua phai"
    r"|co|co a|co ah|co roi|roi|da roi|dung|dung roi|dung vay|phai"
    r"|duoc|duoc roi|vang|da|u|um|uh"
    r")"
    + _TAIL + r"$"
)

# Bounded harmful-intent cues. Deliberately NARROW: a lawful request that merely
# mentions công an / chứng cứ / đe dọa / luật sư is not unsafe. Only the
# combination of a harmful verb with its object refuses.
_UNSAFE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        # destroying / concealing / falsifying evidence
        r"\b(?:xoa|huy|tieu\s*huy|phi\s*tang|giau|che\s*giau|thu\s*tieu)\b[^.]{0,40}\b(?:chung\s*cu|bang\s*chung|tin\s*nhan|sao\s*ke|hop\s*dong|giay\s*to|du\s*lieu)\b",
        # forgery
        r"\b(?:lam\s*gia|gia\s*mao|nguy\s*tao|che\s*bien\s*gia)\b[^.]{0,40}\b(?:giay|hop\s*dong|chu\s*ky|con\s*dau|tai\s*lieu|bang\s*chung|sao\s*ke)\b",
        # knowingly false statements / evasion
        r"\b(?:khai\s*gian|khai\s*man|noi\s*doi|khai\s*sai|lam\s*chung\s*gian)\b",
        r"\b(?:tron|lach|ne)\b[^.]{0,30}\b(?:luat|thue|trach\s*nhiem|nghia\s*vu|xu\s*ly|phat)\b",
        # threats / violence / coercion / illegal retaliation
        r"\b(?:de\s*doa|doa|uy\s*hiep|khung\s*bo|ep\s*buoc|cuong\s*ep|tong\s*tien)\b[^.]{0,40}\b(?:chu\s*nha|no|ho|nguoi|doi\s*phuong|gia\s*dinh)\b",
        r"\b(?:danh|hanh\s*hung|chem|giet|dot|pha\s*hoai|tat)\b[^.]{0,30}\b(?:chu\s*nha|no|ho|nguoi|doi\s*phuong)\b",
        r"\b(?:thue\s*(?:giang\s*ho|xa\s*hoi\s*den)|tu\s*xu|xu\s*dep|tra\s*thu)\b",
        # obstruction
        r"\b(?:can\s*tro|choi\s*bo|cho\s*chay)\b[^.]{0,30}\b(?:dieu\s*tra|co\s*quan|cong\s*an|toa)\b",
    )
)

# Rental-deposit topic cues (accent-stripped).
_DEPOSIT_CUES: tuple[str, ...] = (
    "dat coc", "tien coc", "tien dat coc", "coc thue nha", "bo coc", "hoan coc",
    "hoan tra coc", "mat coc", "chu nha", "thue nha", "thue phong", "tra phong",
    "hop dong thue", "giay dat coc", "sao ke", "ban giao nha", "nhan nha",
)

# Cues indicating an in-scope conversational follow-up even when the deposit
# noun is absent ("tôi nên làm gì tiếp?").
_FOLLOWUP_CUES: tuple[str, ...] = (
    "lam gi tiep", "lam gi bay gio", "tiep theo", "buoc tiep", "nen lam gi",
    "can chuan bi", "chuan bi gi", "bang chung gi", "chung cu gi", "giay to gi",
    "can gi", "the nao", "ra sao", "con gi", "viet lai", "cap nhat lai",
    "sua lai", "viet manh hon", "gui lai", "soan lai", "noi nham", "nham",
    "khong phai", "thuc ra la", "dinh chinh", "sua thanh", "doi thanh",
    "toi muon", "giup toi", "tin nhan",
)

# Out-of-scope legal domains that must NOT contaminate the deposit matter.
_OUT_OF_SCOPE_CUES: tuple[str, ...] = (
    "vay tien", "khoan vay", "no xau", "tin dung", "vi pham giao thong",
    "phat nguoi", "bang lai", "giay phep kinh doanh", "ho kinh doanh",
    "thue thu nhap", "ly hon", "thua ke", "bao hiem", "sa thai", "hop dong lao dong",
    "mua hang online", "don hang",
)


# Explicit contrast markers: "X, không phải Y" / "chứ không phải Y".
_CONTRAST_CUES: tuple[str, ...] = (
    "khong phai", "chu khong phai", "chu khong", "chang phai",
)


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)


def is_unsafe(text: str) -> bool:
    """Narrow harmful-intent check. Overblocking on bare keywords is a bug, not
    a safety win: 'Tôi cần giữ chứng cứ như thế nào?' must not refuse."""

    normalized = normalize_for_cue(text)
    return any(pattern.search(normalized) is not None for pattern in _UNSAFE_PATTERNS)


def classify_route(
    text: str,
    *,
    has_active_matter: bool,
    pending_clarification: bool = False,
) -> FastDemoRoute:
    """Deterministic first-level route. No provider call, no state mutation.

    Precedence, highest first:

      1. safety;
      2. explicit legal/current-turn intent (deposit cues, below);
      3. a short answer to a pending structured legal clarification;
      4. capability / greeting;
      5. pure acknowledgment;
      6. remaining legal / scope handling.

    ``pending_clarification`` must come from a structured persisted assistant
    field, never from parsing assistant prose.
    """

    normalized = normalize_for_cue(text)
    if not normalized:
        return FastDemoRoute.SCOPE_OR_UNSUPPORTED

    # Safety first, before any social short-circuit.
    if is_unsafe(text):
        return FastDemoRoute.UNSAFE

    # A short token that answers an outstanding question, or that lands in a
    # chat with a live matter, is treated as legal content rather than small
    # talk. Ranked above the greeting/acknowledgment anchors so "Chưa." cannot
    # be consumed as a pleasantry -- but still below safety.
    if (pending_clarification or has_active_matter) and _ANSWER_TOKEN_RE.match(normalized):
        return FastDemoRoute.LEGAL_CONVERSATION

    # Full-message anchors: a greeting carrying actionable content is not social.
    if _SOCIAL_RE.match(normalized):
        return FastDemoRoute.SOCIAL
    if _CAPABILITY_RE.match(normalized):
        return FastDemoRoute.CAPABILITY
    # Bare acknowledgment. Checked before the topic cues so a standalone "được"
    # is a reply, not a deposit keyword hit, but after the anchors above so an
    # acknowledgment carrying a real question stays on its proper route.
    if _ACKNOWLEDGMENT_RE.match(normalized):
        return FastDemoRoute.ACKNOWLEDGMENT

    out_of_scope = _contains_any(normalized, _OUT_OF_SCOPE_CUES)

    # An explicit topic change ("tôi hỏi khoản vay, KHÔNG PHẢI tiền cọc") must
    # win over the deposit noun it contrasts against -- otherwise the mere
    # mention of "tiền cọc" would drag an unrelated question into the matter.
    if out_of_scope and _contains_any(normalized, _CONTRAST_CUES):
        return FastDemoRoute.SCOPE_OR_UNSUPPORTED

    if _contains_any(normalized, _DEPOSIT_CUES):
        return FastDemoRoute.LEGAL_CONVERSATION

    # An out-of-scope domain cue also wins over a generic follow-up cue, so an
    # unrelated question can never be absorbed into the deposit matter.
    if out_of_scope:
        return FastDemoRoute.SCOPE_OR_UNSUPPORTED

    if has_active_matter and _contains_any(normalized, _FOLLOWUP_CUES):
        return FastDemoRoute.LEGAL_CONVERSATION

    return FastDemoRoute.SCOPE_OR_UNSUPPORTED


# User-facing copy. Deliberately free of implementation vocabulary — no "bản demo",
# "phản hồi dự phòng", provider/route/scope/schema/state. The assistant speaks as an
# assistant, never about its own plumbing.

class LegalIntent(str, Enum):
    """Bounded intent within an already-classified legal turn.

    Used only to choose which contextual fallback to render when the provider
    fails. It never gates a provider call and never writes state.
    """

    FACT_INTAKE = "fact_intake"
    NEXT_STEPS = "next_steps"
    DRAFT = "draft"
    EVIDENCE = "evidence"
    GENERAL = "general"


_DRAFT_CUES = (
    "viet giup", "viet ho", "soan giup", "soan ho", "soan tin nhan", "viet tin nhan",
    "cap nhat lai tin nhan", "viet lai", "soan lai", "gui lai tin nhan", "viet manh hon",
)
_EVIDENCE_CUES = (
    "bang chung", "chung cu", "giay to gi", "chuan bi gi", "can chuan bi", "ho so",
)
_NEXT_STEP_CUES = (
    "lam gi tiep", "lam gi bay gio", "tiep theo", "buoc tiep", "nen lam gi", "phai lam gi",
    "xu ly the nao", "giai quyet the nao", "lam sao", "the nao bay gio",
)
# A turn that only reports facts: it states what happened but asks nothing.
_QUESTION_CUES = (
    "?", "lam gi", "the nao", "ra sao", "co nen", "co the", "gi khong", "khong a",
    "bao lau", "o dau", "ai", "tai sao", "vi sao",
)


def classify_legal_intent(text: str) -> LegalIntent:
    """Classify intent inside a legal turn. Deterministic, no provider call."""

    normalized = normalize_for_cue(text)
    raw = text.strip()

    if _contains_any(normalized, _DRAFT_CUES):
        return LegalIntent.DRAFT
    if _contains_any(normalized, _EVIDENCE_CUES):
        return LegalIntent.EVIDENCE
    if _contains_any(normalized, _NEXT_STEP_CUES):
        return LegalIntent.NEXT_STEPS

    # No question mark and no interrogative cue => the user is supplying facts,
    # not yet asking for anything. This is the intake case.
    asks_something = raw.endswith("?") or _contains_any(normalized, _QUESTION_CUES)
    if not asks_something:
        return LegalIntent.FACT_INTAKE
    return LegalIntent.GENERAL


GREETING_TEXT = (
    "Xin chào! Tôi có thể giúp bạn xử lý tình huống tiền cọc thuê nhà: phân tích sự việc, "
    "xác định thông tin còn thiếu, chuẩn bị chứng cứ, gợi ý bước tiếp theo và soạn tin nhắn "
    "yêu cầu hoàn cọc. Bạn kể giúp tôi tình huống của bạn nhé."
)

CAPABILITY_TEXT = (
    "Tôi có thể giúp bạn phân tích tình huống tiền cọc thuê nhà, xác định thông tin còn "
    "thiếu, chuẩn bị chứng cứ, đề xuất bước tiếp theo và soạn tin nhắn yêu cầu hoàn trả.\n\n"
    "Bạn chỉ cần cho tôi biết số tiền đã đặt cọc, giấy tờ hoặc chứng từ đang có, và chủ nhà "
    "đã phản hồi thế nào."
)

# Acknowledgments get two variants so the reply matches the conversation the
# user is actually in. Neither asks the user to restate anything, and neither
# claims a fact: they only offer to continue.
ACKNOWLEDGMENT_TEXT_WITH_MATTER = (
    "Vâng. Tôi vẫn giữ những thông tin bạn đã cung cấp về tình huống tiền cọc của bạn. "
    "Bạn muốn tôi hỗ trợ tiếp phần nào — chuẩn bị chứng cứ, gợi ý bước tiếp theo, hay "
    "soạn tin nhắn gửi chủ nhà?"
)

ACKNOWLEDGMENT_TEXT = (
    "Vâng. Khi nào bạn cần hỗ trợ về tình huống tiền cọc thuê nhà, bạn cứ mô tả giúp tôi "
    "sự việc nhé."
)

SCOPE_TEXT = (
    "Tôi tập trung hỗ trợ các tình huống liên quan đến tiền cọc thuê nhà. Bạn mô tả giúp tôi "
    "sự việc của mình — số tiền đã đặt cọc, giấy tờ hoặc chứng từ đang có, và chủ nhà đã phản "
    "hồi thế nào — để tôi hỗ trợ cụ thể hơn nhé."
)

UNSAFE_TEXT = (
    "Rất tiếc, tôi không thể hỗ trợ yêu cầu này. Tôi có thể giúp bạn xử lý tranh chấp "
    "tiền cọc bằng cách hợp pháp: giữ lại chứng cứ, gửi yêu cầu hoàn trả bằng văn bản, "
    "và cân nhắc nhờ luật sư hoặc cơ quan có thẩm quyền hỗ trợ."
)


__all__ = [
    "ACKNOWLEDGMENT_TEXT",
    "ACKNOWLEDGMENT_TEXT_WITH_MATTER",
    "CAPABILITY_TEXT",
    "FastDemoRoute",
    "GREETING_TEXT",
    "SCOPE_TEXT",
    "UNSAFE_TEXT",
    "classify_route",
    "is_unsafe",
    "normalize_for_cue",
]
