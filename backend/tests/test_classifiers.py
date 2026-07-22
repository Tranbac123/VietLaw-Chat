"""Deterministic classifiers."""
from pathlib import Path

import pytest

from app.triage import decision_policy, legal_triage, risk_classifier
from app.nlp.patterns import PatternBank
from app.nlp.input_normalizer import normalize
from app.schemas import Decision, Domain, RiskLevel
from app.triage.unsafe_intent_detector import detect

_DATA = Path(__file__).resolve().parents[2] / "data" / "unsafe_patterns.json"


@pytest.fixture(scope="module")
def bank():
    return PatternBank.load(str(_DATA))


def _pipe(text, bank):
    """Run the deterministic chain on raw text, return (domain, risk, decision, unsafe)."""
    n = normalize(text)
    unsafe = detect(n.accent_insensitive, bank)
    dom = legal_triage.classify(n, unsafe, bank)
    risk = risk_classifier.classify(n, dom, unsafe, bank)
    dec = decision_policy.decide(dom, risk, unsafe)
    return dom, risk, dec, unsafe


# ---- domain ----

@pytest.mark.parametrize("text,domain", [
    ("Tôi thuê nhà, chủ nhà giữ tiền cọc không trả.", Domain.civil_dispute),
    ("Tôi bị phạt giao thông nhưng không hiểu lỗi.", Domain.traffic),
    ("Tôi bị CSGT phạt lỗi vượt đèn đỏ.", Domain.traffic),
    ("Tôi bị phạt nguội quá tốc độ.", Domain.traffic),
    ("Tôi cho vay nhưng bị quỵt nợ.", Domain.civil_dispute),
    ("Tôi mua online nhưng shop không hoàn tiền.", Domain.civil_dispute),
    ("Tôi muốn bán đồ ăn online ở quê cần giấy tờ gì?", Domain.household_business),
    ("Tôi mở tiệm tạp hóa nhỏ.", Domain.household_business),
    ("Tôi livestream bán hàng có phải đăng ký không?", Domain.household_business),
    ("Tôi bị công an mời làm việc.", Domain.high_risk),
    ("Làm sao để né phạt giao thông?", Domain.high_risk),
    ("Viết cho tôi bài thơ tình.", Domain.unknown),
])
def test_domain(text, domain, bank):
    dom, _, _, _ = _pipe(text, bank)
    assert dom.domain == domain


# ---- risk ----

@pytest.mark.parametrize("text,risk", [
    ("Tôi muốn mở hộ kinh doanh nhỏ.", RiskLevel.low),
    ("Chủ nhà giữ tiền cọc không trả.", RiskLevel.medium),
    ("Tôi bị phạt giao thông nhưng không hiểu lỗi.", RiskLevel.medium),
    ("Tôi bị công an mời làm việc.", RiskLevel.high),
    ("Làm sao để làm giả giấy tờ?", RiskLevel.high),
    ("Làm sao để né phạt giao thông?", RiskLevel.high),
])
def test_risk(text, risk, bank):
    _, r, _, _ = _pipe(text, bank)
    assert r.risk == risk


def test_basic_business_stays_low_despite_missing_details(bank):
    _, r, _, _ = _pipe("Tôi muốn mở hộ kinh doanh nhỏ thì cần chuẩn bị gì?", bank)
    assert r.risk == RiskLevel.low


def test_large_money_signal_raises_risk(bank):
    _, r, _, _ = _pipe("Tôi cho vay vài trăm triệu không đòi được.", bank)
    assert r.risk == RiskLevel.high


# ---- decision ----

@pytest.mark.parametrize("text,decision", [
    ("Tôi bị phạt giao thông nhưng không hiểu lỗi.", Decision.ask_clarifying_questions),
    ("Tôi muốn mở hộ kinh doanh nhỏ.", Decision.answer_with_guidance),
    ("Tôi bị công an mời làm việc.", Decision.recommend_professional_help),
    ("Làm sao để giấu chứng cứ?", Decision.refuse_unsafe_request),
    ("Viết cho tôi bài thơ tình.", Decision.unsupported),
])
def test_decision(text, decision, bank):
    _, _, d, _ = _pipe(text, bank)
    assert d == decision


# ---- no-diacritics ----

@pytest.mark.parametrize("text,domain,decision", [
    ("toi thue nha chu nha giu tien coc khong tra", Domain.civil_dispute, Decision.ask_clarifying_questions),
    ("toi muon ban do an online o que can giay to gi", Domain.household_business, Decision.answer_with_guidance),
    ("lam sao de ne phat giao thong", Domain.high_risk, Decision.refuse_unsafe_request),
])
def test_no_diacritics(text, domain, decision, bank):
    dom, _, d, _ = _pipe(text, bank)
    assert dom.domain == domain
    assert d == decision


# ---- unsafe detection + flags ----

def test_ne_phat_flags_and_topic(bank):
    dom, r, d, unsafe = _pipe("Làm sao để né phạt giao thông?", bank)
    assert unsafe.detected
    assert d == Decision.refuse_unsafe_request
    assert dom.detected_topic == "traffic"
    assert "legal_evasion" in unsafe.safety_flags
    assert "traffic_evasion" in unsafe.safety_flags


def test_negation_does_not_exempt_input(bank):
    # "không" near unsafe phrase must NOT exempt input detection.
    _, _, d, unsafe = _pipe("Có cách nào không? né phạt giao thông giúp tôi.", bank)
    assert unsafe.detected
    assert d == Decision.refuse_unsafe_request


def test_rental_lockout_is_civil_dispute(bank):
    dom, r, d, _ = _pipe("Chủ trọ khóa cửa phòng vì tôi chậm trả tiền nhà.", bank)
    assert dom.domain == Domain.civil_dispute
    assert r.risk == RiskLevel.medium
    assert d == Decision.ask_clarifying_questions


def test_vague_legal_question_asks_instead_of_unsupported(bank):
    # A legal-but-underspecified question should clarify, not be marked out of scope.
    dom, r, d, _ = _pipe("Tôi có một vấn đề pháp lý rất lạ nhưng chưa mô tả rõ.", bank)
    assert dom.domain == Domain.unknown
    assert r.risk == RiskLevel.medium
    assert d == Decision.ask_clarifying_questions


def test_non_legal_stays_unsupported(bank):
    _, _, d, _ = _pipe("Viết cho tôi bài thơ tình.", bank)
    assert d == Decision.unsupported


def test_business_evasion_is_high_risk(bank):
    dom, r, d, _ = _pipe("Tôi muốn lách giấy phép để bán hàng.", bank)
    assert dom.domain == Domain.high_risk
    assert r.risk == RiskLevel.high
    assert d == Decision.refuse_unsafe_request
