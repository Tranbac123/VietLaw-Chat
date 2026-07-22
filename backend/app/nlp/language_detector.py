"""MVP language gate.

Vietnamese (with or without diacritics) is supported; clearly non-Vietnamese is
`unsupported`. Detection is keyword/token-based, NOT statistical: a statistical
detector would misflag no-diacritics Vietnamese and short legal phrases. When
uncertain, treat as Vietnamese (false-rejecting VN hurts demo trust more).
"""
from app.nlp.input_normalizer import NormalizedText
from app.nlp.keywords import DOMAIN_KEYWORDS
from app.nlp.patterns import PatternBank

# Distinctive Vietnamese tokens, accent-folded, curated to avoid English collisions
# (no "the"/"can"/"an"/"a"/"in"/"do"). Exact-token match, so no substring false hits.
_VN_TOKENS = frozenset({
    "toi", "khong", "nha", "tien", "giay", "thue", "phat", "xe", "dat", "kinh",
    "doanh", "hop", "dong", "cong", "luat", "cua", "duoc", "muon", "nao", "que",
    "minh", "nguoi", "viec", "sao", "cho", "gi", "bai", "tho", "vay", "chua",
    "roi", "cai", "nay", "la", "co", "bi", "giu", "tra", "coc",
})


def _cue_phrases(bank: PatternBank) -> list[str]:
    phrases: list[str] = []
    for kws in DOMAIN_KEYWORDS.values():
        phrases.extend(kws)
    for groups in (bank.unsafe, bank.high_risk, bank.medium, bank.low, bank.unsupported):
        for g in groups:
            phrases.extend(g.folded_patterns)
    return phrases


def is_vietnamese(norm: NormalizedText, language: str | None, bank: PatternBank) -> bool:
    if language and language.lower() != "vi":
        return False

    ai = norm.accent_insensitive
    if any(p in ai for p in _cue_phrases(bank)):
        return True

    tokens = set(ai.split())
    return bool(tokens & _VN_TOKENS)
