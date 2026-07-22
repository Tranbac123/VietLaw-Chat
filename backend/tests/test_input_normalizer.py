"""Input normalizer."""
from app.nlp.input_normalizer import normalize


def test_preserves_original():
    n = normalize("  Tôi thuê nhà, giữ tiền cọc?  ")
    assert n.original == "  Tôi thuê nhà, giữ tiền cọc?  "


def test_normalized_lowercases_dedups_and_strips_punctuation():
    n = normalize("Tôi  thuê nhà, giữ  tiền cọc?")
    assert n.normalized == "tôi thuê nhà giữ tiền cọc"


def test_accent_insensitive_folds_tones_and_d():
    n = normalize("Tôi thuê nhà, giữ tiền cọc 2 tháng?")
    assert n.accent_insensitive == "toi thue nha giu tien coc 2 thang"


def test_dstroke_folds_to_d():
    n = normalize("Đặt cọc")
    assert n.accent_insensitive == "dat coc"


def test_no_diacritic_input_unchanged_by_folding():
    n = normalize("toi thue nha chu nha giu tien coc khong tra")
    assert n.accent_insensitive == "toi thue nha chu nha giu tien coc khong tra"
