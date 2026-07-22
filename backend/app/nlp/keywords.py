"""Topical domain keyword tables, accent-folded.

Used for (a) topical inference when the domain is forced to high_risk, and
(b) domain fallback when no pattern group in unsafe_patterns.json matches.
Single-syllable ambiguous tokens are avoided — folding "nợ"→"no" would false-match
"nói"/"khong", so multi-word phrases are used instead.
"""
from typing import Optional

from app.nlp.input_normalizer import strip_accents

_RAW = {
    "civil_dispute": [
        "tiền cọc", "đặt cọc", "chủ nhà", "thuê nhà", "hợp đồng", "vay tiền",
        "no tien", "không trả", "mua hàng", "shop không giao", "tranh chấp",
        "bồi thường", "chứng từ", "biên nhận",
        "chủ trọ", "phòng trọ", "tiền nhà", "chậm trả", "trả tiền nhà",
        "cho vay", "quỵt nợ", "quỵt tiền", "bùng nợ",
        "đặt hàng", "hoàn tiền", "mua online",
    ],
    "traffic": [
        "giao thông", "biên bản", "giấy phạt", "phạt xe", "bằng lái",
        "đăng ký xe", "vi phạm giao thông", "cảnh sát giao thông", "tai nạn giao thông",
        "csgt", "vượt đèn đỏ", "đèn đỏ", "phạt nguội", "quá tốc độ", "nồng độ cồn",
    ],
    "household_business": [
        "hộ kinh doanh", "bán đồ ăn online", "mở quán", "bán hàng online",
        "đăng ký kinh doanh", "giấy phép", "an toàn thực phẩm", "shop nhỏ",
        "kinh doanh tại nhà", "kinh doanh nhỏ",
        "mở tiệm", "mở shop", "buôn bán", "kinh doanh online",
        "bán đồ ăn", "vệ sinh thực phẩm", "bán online", "livestream",
    ],
    "administrative": [
        "thủ tục", "hồ sơ", "nộp hồ sơ", "cần giấy tờ gì", "cơ quan nào",
    ],
}

# Topical inference order: check these before falling back (traffic first so
# "né phạt giao thông" resolves to traffic).
_TOPIC_ORDER = ["traffic", "civil_dispute", "household_business", "administrative"]

DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    dom: tuple(strip_accents(k.lower()) for k in kws) for dom, kws in _RAW.items()
}


def match_domain(ai_text: str) -> Optional[str]:
    """First topical domain whose keywords appear in accent-insensitive text."""
    for dom in _TOPIC_ORDER:
        if any(k in ai_text for k in DOMAIN_KEYWORDS[dom]):
            return dom
    return None


# Generic legal-signal cues: a question that mentions law/dispute but names no
# domain is legal-but-vague (→ ask to clarify), not out of scope (→ unsupported).
_LEGAL_SIGNAL = tuple(
    strip_accents(k) for k in ("phap ly", "phap luat", "luat", "kien", "tranh chap", "quy dinh")
)


def has_legal_signal(ai_text: str) -> bool:
    return any(k in ai_text for k in _LEGAL_SIGNAL)
