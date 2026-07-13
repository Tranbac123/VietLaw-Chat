"""Input normalization.

Produces three forms and never mutates meaning:
- original: kept verbatim for storage + prompt.
- normalized: lowercased, punctuation stripped, whitespace collapsed (rule matching).
- accent_insensitive: normalized with Vietnamese diacritics removed (no-diacritics matching).
"""
import re
import unicodedata
from dataclasses import dataclass

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class NormalizedText:
    original: str
    normalized: str
    accent_insensitive: str


def _collapse(text: str) -> str:
    return _SPACES.sub(" ", _PUNCT.sub(" ", text)).strip()


def strip_accents(text: str) -> str:
    # NFD splits base letter + combining tone mark; drop the marks. đ/Đ are distinct
    # base letters (no combining form) so handle them manually.
    decomposed = unicodedata.normalize("NFD", text)
    no_marks = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return no_marks.replace("đ", "d").replace("Đ", "D")


def normalize(text: str) -> NormalizedText:
    normalized = _collapse(text.lower())
    return NormalizedText(
        original=text,
        normalized=normalized,
        accent_insensitive=strip_accents(normalized),
    )
