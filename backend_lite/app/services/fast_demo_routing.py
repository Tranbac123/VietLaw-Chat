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

_CAPABILITY_RE = re.compile(
    r"^(?:"
    # "bạn làm được gì", "bạn giúp được gì", "bạn hỗ trợ được gì"
    r"(?:ban|may|bot|ai)\s+(?:lam|giup|ho\s+tro)\s+duoc\s+(?:nhung\s+)?gi(?:\s+cho\s+toi)?"
    # "bạn làm gì được"
    r"|(?:ban|may|bot|ai)\s+lam\s+gi\s+duoc"
    # "bạn có thể làm/giúp/hỗ trợ gì"
    r"|(?:ban|may|bot|ai)\s+co\s+the\s+(?:lam|giup|ho\s+tro)\s+(?:duoc\s+)?(?:nhung\s+)?gi(?:\s+cho\s+toi)?"
    # identity, folded into capability for the demo
    r"|(?:ban|may)\s+la\s+ai"
    r"|(?:ban|may)\s+ten\s+(?:la\s+)?gi"
    r"|ten\s+(?:ban|may)\s+(?:la\s+)?gi"
    r"|who\s+are\s+you|what\s+are\s+you|what\s+can\s+you\s+do|help"
    # "bạn giúp được gì cho tôi", "bạn hỗ trợ gì"
    r"|(?:ban|may|bot|ai)\s+(?:giup|ho\s+tro)\s+(?:duoc\s+)?gi"
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


def classify_route(text: str, *, has_active_matter: bool) -> FastDemoRoute:
    """Deterministic first-level route. No provider call, no state mutation."""

    normalized = normalize_for_cue(text)
    if not normalized:
        return FastDemoRoute.SCOPE_OR_UNSUPPORTED

    # Safety first, before any social short-circuit.
    if is_unsafe(text):
        return FastDemoRoute.UNSAFE

    # Full-message anchors: a greeting carrying actionable content is not social.
    if _SOCIAL_RE.match(normalized):
        return FastDemoRoute.SOCIAL
    if _CAPABILITY_RE.match(normalized):
        return FastDemoRoute.CAPABILITY

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


GREETING_TEXT = (
    "Xin chào! Tôi có thể giúp bạn phân tích tình huống tiền cọc thuê nhà, "
    "xác định thông tin còn thiếu, chuẩn bị chứng cứ, đề xuất bước tiếp theo "
    "và soạn tin nhắn yêu cầu hoàn cọc."
)

CAPABILITY_TEXT = (
    "Tôi có thể giúp bạn phân tích tranh chấp tiền cọc thuê nhà, xác định thông tin "
    "còn thiếu, chuẩn bị danh sách chứng cứ, đề xuất bước xử lý và soạn tin nhắn "
    "yêu cầu hoàn trả. Bản demo hiện tập trung vào tình huống tiền cọc thuê nhà."
)

SCOPE_TEXT = (
    "Bản demo này hiện chỉ hỗ trợ tình huống tiền cọc thuê nhà. Bạn mô tả giúp tôi "
    "tình huống đặt cọc của mình (số tiền, giấy tờ hiện có, chủ nhà đã phản hồi thế nào) "
    "để tôi hỗ trợ cụ thể hơn nhé."
)

UNSAFE_TEXT = (
    "Rất tiếc, tôi không thể hỗ trợ yêu cầu này. Tôi có thể giúp bạn xử lý tranh chấp "
    "tiền cọc bằng cách hợp pháp: giữ lại chứng cứ, gửi yêu cầu hoàn trả bằng văn bản, "
    "và cân nhắc nhờ luật sư hoặc cơ quan có thẩm quyền hỗ trợ."
)


__all__ = [
    "CAPABILITY_TEXT",
    "FastDemoRoute",
    "GREETING_TEXT",
    "SCOPE_TEXT",
    "UNSAFE_TEXT",
    "classify_route",
    "is_unsafe",
    "normalize_for_cue",
]
