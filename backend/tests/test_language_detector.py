"""Language gate."""
from pathlib import Path

import pytest

from app.input_normalizer import normalize
from app.language_detector import is_vietnamese
from app.patterns import PatternBank

_DATA = Path(__file__).resolve().parents[2] / "data" / "unsafe_patterns.json"


@pytest.fixture(scope="module")
def bank():
    return PatternBank.load(str(_DATA))


def _vn(text, bank, language="vi"):
    return is_vietnamese(normalize(text), language, bank)


def test_vietnamese_with_diacritics(bank):
    assert _vn("Tôi thuê nhà, chủ nhà giữ tiền cọc.", bank)


def test_vietnamese_without_diacritics(bank):
    assert _vn("toi thue nha chu nha giu tien coc khong tra", bank)


def test_unsafe_without_diacritics_is_vietnamese(bank):
    assert _vn("lam sao de ne phat giao thong", bank)


def test_non_legal_vietnamese_still_vietnamese(bank):
    assert _vn("Viết cho tôi bài thơ tình.", bank)


def test_english_is_not_vietnamese(bank):
    assert not _vn("What documents do I need to sell food online in Vietnam?", bank)


def test_explicit_non_vi_language_is_unsupported(bank):
    # Even Vietnamese text must be unsupported if language is declared non-vi.
    assert not _vn("Tôi thuê nhà giữ tiền cọc", bank, language="en")


def test_missing_language_defaults_to_vietnamese(bank):
    assert _vn("Tôi thuê nhà giữ tiền cọc", bank, language=None)
