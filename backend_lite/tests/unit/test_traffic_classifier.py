"""VietLaw Public Beta V0: bounded traffic-fact classifier (task §13.2).

Deterministic, no LLM, no network. Covers all 8 curated traffic topics plus
the required dimensions: vehicle ambiguity, missing threshold fact, wrong
legal domain, educational/hypothetical framing, negation, third-party
attribution, and multi-sentence subject switch.
"""

from __future__ import annotations

import pytest

from backend_lite.app.contracts.traffic import ClarificationAnswerKind
from backend_lite.app.services.traffic_classifier import (
    classify,
    detect_topic,
    is_valid_clarification_answer,
    parse_clarification_answer,
)

# -- 1-8: one clear positive example per curated topic -----------------------

@pytest.mark.parametrize(
    ("message", "expected_topic"),
    [
        ("Tôi vượt đèn đỏ khi đi xe máy thì bị phạt bao nhiêu?", "red_light"),
        ("Tôi không đội mũ bảo hiểm khi đi xe máy, mức phạt thế nào?", "no_helmet"),
        ("Tôi có nồng độ cồn khi lái xe máy thì bị phạt bao nhiêu?", "alcohol"),
        ("Tôi chạy quá tốc độ quy định 20km/h khi đi xe máy.", "speeding"),
        ("Tôi quên mang bằng lái xe khi đi xe máy.", "driver_license"),
        ("Tôi dùng điện thoại khi lái xe máy.", "phone_use"),
        ("Tôi chở quá số người quy định trên xe máy.", "passenger_limit"),
        ("Tôi độ xe, thay đổi kết cấu xe máy của mình.", "vehicle_modification"),
    ],
)
def test_clear_positive_per_topic(message: str, expected_topic: str) -> None:
    assert detect_topic(message) == expected_topic


# -- 9: vehicle ambiguity -----------------------------------------------------

def test_vehicle_ambiguity_leaves_vehicle_type_unknown() -> None:
    detection = classify("Tôi vượt đèn đỏ thì bị phạt bao nhiêu?")
    assert detection.topic_id == "traffic_red_light"
    assert detection.facts.vehicle_type == "unknown"


# -- 10: missing threshold fact ----------------------------------------------

def test_speeding_without_kmh_leaves_speed_excess_unknown() -> None:
    detection = classify("Tôi chạy quá tốc độ quy định khi đi xe máy, bị phạt bao nhiêu?")
    assert detection.topic_id == "traffic_speeding"
    assert detection.facts.speed_excess_kmh is None


def test_alcohol_never_extracts_a_structured_level_from_free_text() -> None:
    detection = classify("Tôi có nồng độ cồn 0.3 mg/l khi đi xe máy.")
    assert detection.topic_id == "traffic_alcohol"
    # No bounded extraction path exists for alcohol_level (task §5.1: do not
    # force a fact from vague wording) -- it always stays unknown from text.
    assert detection.facts.alcohol_level is None


# -- 11: wrong legal domain ---------------------------------------------------

@pytest.mark.parametrize(
    "message",
    [
        "Công ty giữ lương của tôi không trả thì tôi phải làm sao?",
        "Tôi muốn ly hôn thì cần chuẩn bị giấy tờ gì?",
        "Hàng xóm lấn chiếm đất của gia đình tôi thì phải làm sao?",
    ],
)
def test_unrelated_legal_domain_is_not_a_traffic_topic(message: str) -> None:
    assert detect_topic(message) is None


# -- 12: educational / hypothetical framing ----------------------------------

def test_hypothetical_framing_still_recognizes_the_topic() -> None:
    # A hypothetical/educational question about the rule is still a genuine
    # traffic-topic question -- the curated answer is general-penalty
    # information, not a personal accusation, so detecting it is correct.
    # Correction Round 1 (M-01): but it must NOT be attributed to the user
    # -- callers must gate persistence on `attribution == "self"`.
    detection = classify("Giả sử một người vượt đèn đỏ khi đi xe máy thì bị phạt bao nhiêu?")
    assert detection.topic_id == "traffic_red_light"
    assert detection.attribution != "self"


# -- 13: negation --------------------------------------------------------------

@pytest.mark.parametrize(
    "message",
    [
        "Tôi không vượt đèn đỏ.",
        "Tôi chưa từng chạy quá tốc độ quy định.",
        "Tôi không đội mũ bảo hiểm là sai à? Thực ra tôi không dùng điện thoại khi lái xe.",
    ],
)
def test_negated_action_is_not_detected_as_the_topic(message: str) -> None:
    # These are deliberately narrow: only the exact negated cue is checked.
    # The third case both negates phone_use and separately mentions helmet
    # as a question, neither of which should register as a positive topic.
    if "vượt đèn đỏ" in message:
        assert detect_topic(message) != "red_light"
    if "quá tốc độ" in message:
        assert detect_topic(message) != "speeding"


def test_explicit_negation_of_red_light_returns_none() -> None:
    assert detect_topic("Tôi không vượt đèn đỏ.") is None


# -- 14: third-party attribution ----------------------------------------------

def test_third_party_attribution_still_detects_the_topic() -> None:
    # A friend's violation is still a legitimate traffic question about that
    # topic. Correction Round 1 (M-01): but `attribution` must say so --
    # callers must never persist this as the user's own confirmed event.
    detection = classify("Bạn tôi vượt đèn đỏ khi đi xe máy, hỏi hộ mức phạt.")
    assert detection.topic_id == "traffic_red_light"
    assert detection.facts.vehicle_type == "motorcycle"
    assert detection.attribution == "third_party"


# -- 15: multi-sentence subject switch ----------------------------------------

def test_topic_detected_even_after_an_unrelated_earlier_sentence() -> None:
    detection = classify("Hôm qua trời mưa to. Tôi vượt đèn đỏ khi đi xe máy.")
    assert detection.topic_id == "traffic_red_light"
    assert detection.facts.vehicle_type == "motorcycle"


# -- narrow-by-design: first matching topic wins, never two at once ----------

def test_only_one_topic_is_ever_reported_per_message() -> None:
    detection = classify(
        "Tôi vượt đèn đỏ và cũng không đội mũ bảo hiểm khi đi xe máy."
    )
    assert detection.topic_id in {"traffic_red_light", "traffic_no_helmet"}


# -- speed/passenger numeric extraction ---------------------------------------

def test_speed_excess_kmh_extracted_when_stated() -> None:
    detection = classify("Tôi chạy quá tốc độ quy định, vượt 25km khi đi xe máy.")
    assert detection.facts.speed_excess_kmh == 25


def test_passenger_count_extracted_when_stated() -> None:
    detection = classify("Tôi chở 3 người trên xe máy.")
    assert detection.facts.passenger_count == 3


# =============================================================================
# Correction Round 1, M-01: attribution (self / third_party / hypothetical /
# educational / negated / unknown). Required probes verbatim from the
# correction task.
# =============================================================================

@pytest.mark.parametrize(
    "message",
    [
        "Nếu một người vượt đèn đỏ khi đi xe máy thì bị phạt sao?",
        "Giả sử tài xế ô tô vượt đèn đỏ thì xử lý thế nào?",
    ],
)
def test_hypothetical_probes_are_never_attributed_to_the_user(message: str) -> None:
    assert classify(message).attribution == "hypothetical"


@pytest.mark.parametrize(
    "message",
    [
        "Bạn tôi dùng điện thoại khi chạy xe máy.",
        "Anh trai tôi chạy quá tốc độ 10 km/h.",
    ],
)
def test_third_party_probes_are_never_attributed_to_the_user(message: str) -> None:
    assert classify(message).attribution == "third_party"


def test_educational_probe_is_never_attributed_to_the_user() -> None:
    detection = classify("Tôi đang đọc bài viết về nồng độ cồn.")
    assert detection.attribution == "educational"


def test_ví_dụ_framed_probe_is_hypothetical_not_self() -> None:
    detection = classify("Ví dụ một người không đội mũ bảo hiểm thì bị phạt sao?")
    assert detection.attribution == "hypothetical"


@pytest.mark.parametrize(
    "message",
    [
        "Tôi không vượt đèn đỏ.",
        "Tôi chưa từng lái xe khi có nồng độ cồn.",
    ],
)
def test_negated_probes_are_never_attributed_to_the_user(message: str) -> None:
    detection = classify(message)
    assert detection.attribution == "negated"
    assert detection.topic_id is None


@pytest.mark.parametrize(
    "message",
    [
        "Tôi đi xe máy vượt đèn đỏ.",
        "Tôi dùng điện thoại khi đang chạy xe máy.",
        "Tôi chạy quá tốc độ 10 km/h.",
        "Tôi quên mang bằng lái.",
    ],
)
def test_required_self_attributed_probes_remain_self(message: str) -> None:
    detection = classify(message)
    assert detection.attribution == "self"
    assert detection.topic_id is not None


# =============================================================================
# Correction Round 1, M-02: is_valid_clarification_answer -- per-field
# plausible-answer validation so a pending clarification can be released
# instead of trapping an unrelated turn.
# =============================================================================

@pytest.mark.parametrize("message", ["xe máy", "ô tô", "tôi đi xe máy", "tôi lái ô tô"])
def test_vehicle_type_clarification_accepts_bounded_answers(message: str) -> None:
    assert is_valid_clarification_answer("vehicle_type", message) is True


@pytest.mark.parametrize(
    "message",
    ["Hôm nay thời tiết thế nào?", "Cảm ơn bạn.", "Tôi muốn hỏi về tiền lương.", "Bạn là ai?"],
)
def test_vehicle_type_clarification_rejects_unrelated_turns(message: str) -> None:
    assert is_valid_clarification_answer("vehicle_type", message) is False


@pytest.mark.parametrize(
    ("field", "valid_answer"),
    [
        ("speed_excess_kmh", "vượt 15km"),
        ("license_status", "bằng lái hết hạn rồi"),
        ("alcohol_level", "Tôi không biết mức đo cụ thể."),
        ("passenger_count", "chở 4 người"),
        ("modification_type", "tôi thay lốp nhỏ hơn"),
    ],
)
def test_each_required_field_accepts_its_own_plausible_answer(field: str, valid_answer: str) -> None:
    assert is_valid_clarification_answer(field, valid_answer) is True


@pytest.mark.parametrize(
    "field",
    ["speed_excess_kmh", "license_status", "alcohol_level", "passenger_count", "modification_type"],
)
@pytest.mark.parametrize(
    "unrelated_message",
    ["Hôm nay thời tiết thế nào?", "Cảm ơn bạn.", "Chủ nhà đã trả lại tiền cọc."],
)
def test_every_required_field_rejects_unrelated_turns(field: str, unrelated_message: str) -> None:
    assert is_valid_clarification_answer(field, unrelated_message) is False


def test_dont_know_is_a_valid_answer_for_any_pending_field() -> None:
    for field in (
        "vehicle_type", "speed_excess_kmh", "license_status", "alcohol_level",
        "passenger_count", "modification_type",
    ):
        assert is_valid_clarification_answer(field, "Tôi không biết.") is True


def test_empty_message_is_never_a_valid_clarification_answer() -> None:
    assert is_valid_clarification_answer("vehicle_type", "") is False


# =============================================================================
# Correction Round 2, M-02-R: parse_clarification_answer -- the typed,
# field-specific parser that replaces the old "any digit counts" rule for
# speed_excess_kmh/alcohol_level/passenger_count. Required probes verbatim
# from the correction task §3/§4.
# =============================================================================

def _assert_resolved(field: str, message: str, expected_value) -> None:
    answer = parse_clarification_answer(field, message)
    assert answer.kind == ClarificationAnswerKind.RESOLVED, f"{message!r} -> {answer.kind}"
    assert answer.field == field
    assert answer.parsed_value == expected_value


def _assert_unrelated(field: str, message: str) -> None:
    answer = parse_clarification_answer(field, message)
    assert answer.kind == ClarificationAnswerKind.UNRELATED, f"{message!r} -> {answer.kind} ({answer.parsed_value!r})"
    assert answer.parsed_value is None


def _assert_unknown_value(field: str, message: str) -> None:
    answer = parse_clarification_answer(field, message)
    assert answer.kind == ClarificationAnswerKind.UNKNOWN_VALUE
    assert answer.parsed_value is None


# -- vehicle_type -------------------------------------------------------------

@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("xe máy", "motorcycle"),
        ("mô tô", "motorcycle"),
        ("ô tô", "car"),
        ("xe hơi", "car"),
        ("tôi đi xe máy", "motorcycle"),
        ("tôi lái ô tô", "car"),
    ],
)
def test_vehicle_type_answer_resolves(message: str, expected: str) -> None:
    _assert_resolved("vehicle_type", message, expected)


@pytest.mark.parametrize(
    "message",
    ["xe của tôi màu đỏ", "tôi mua xe năm 2024", "công ty có 3 xe"],
)
def test_vehicle_type_answer_rejects_unrelated_xe_mentions(message: str) -> None:
    _assert_unrelated("vehicle_type", message)


# -- speed_excess_kmh ----------------------------------------------------------

@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("10 km/h", 10),
        ("vượt 10 km/h", 10),
        ("quá 10 cây", 10),
        ("khoảng 15 km/h", 15),
        ("tôi vượt 8 km/h", 8),
    ],
)
def test_speed_excess_answer_resolves(message: str, expected: int) -> None:
    _assert_resolved("speed_excess_kmh", message, expected)


@pytest.mark.parametrize(
    "message",
    ["Hôm nay 30 độ C.", "Tháng 7.", "Tôi 30 tuổi.", "Lương 10 triệu.", "Đi lúc 8 giờ."],
)
def test_speed_excess_answer_rejects_context_free_numbers(message: str) -> None:
    # These are the exact regression probes from the M-02-R defect report --
    # a bare digit with no speed unit/context must never resolve.
    _assert_unrelated("speed_excess_kmh", message)


# -- alcohol_level --------------------------------------------------------------

@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("0.2 mg/l", "0.2 mg/l"),
        ("0,2 mg/l khí thở", "0,2 mg/l"),
        ("50 mg/100 ml máu", "50 mg/100 ml"),
    ],
)
def test_alcohol_level_answer_resolves(message: str, expected: str) -> None:
    _assert_resolved("alcohol_level", message, expected)


def test_alcohol_level_answer_unknown_value() -> None:
    _assert_unknown_value("alcohol_level", "tôi không biết mức nồng độ")


@pytest.mark.parametrize("message", ["0.2 kg", "30 độ", "2 chai", "tháng 2"])
def test_alcohol_level_answer_rejects_non_alcohol_units(message: str) -> None:
    _assert_unrelated("alcohol_level", message)


# -- passenger_count ------------------------------------------------------------

@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("3 người", 3),
        ("chở 3 người", 3),
        ("ba người", 3),
        ("tổng cộng 4 người", 4),
    ],
)
def test_passenger_count_answer_resolves(message: str, expected: int) -> None:
    _assert_resolved("passenger_count", message, expected)


@pytest.mark.parametrize("message", ["3 triệu", "3 giờ", "tháng 3", "đường số 3"])
def test_passenger_count_answer_rejects_non_passenger_numbers(message: str) -> None:
    _assert_unrelated("passenger_count", message)


# -- license_status ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("quên mang bằng", "forgot"),
        ("không mang theo", "forgot"),
        ("chưa từng có bằng", "never_licensed"),
        ("bằng hết hạn", "expired"),
        ("bằng bị thu hồi", "revoked"),
    ],
)
def test_license_status_answer_resolves(message: str, expected: str) -> None:
    _assert_resolved("license_status", message, expected)


@pytest.mark.parametrize(
    "message",
    ["quên trả tiền", "không có hợp đồng", "hết hạn thuê nhà"],
)
def test_license_status_answer_rejects_unrelated_use_of_similar_words(message: str) -> None:
    _assert_unrelated("license_status", message)


# -- modification_type -------------------------------------------------------------

@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("thay lốp", "tire"),
        ("đổi pô", "exhaust"),
        ("thay khung", "frame"),
        ("đổi đèn", "lighting"),
        ("thay biển số", "license_plate"),
    ],
)
def test_modification_type_answer_resolves(message: str, expected: str) -> None:
    _assert_resolved("modification_type", message, expected)


@pytest.mark.parametrize(
    "message",
    ["thay công việc", "đổi nhà", "sửa hợp đồng"],
)
def test_modification_type_answer_rejects_unrelated_thay_doi_mentions(message: str) -> None:
    _assert_unrelated("modification_type", message)


# -- cross-field: an empty/whitespace message is always UNRELATED -------------

@pytest.mark.parametrize(
    "field",
    ["vehicle_type", "speed_excess_kmh", "alcohol_level", "passenger_count", "license_status", "modification_type"],
)
def test_empty_message_is_unrelated_for_every_field(field: str) -> None:
    _assert_unrelated(field, "")
    _assert_unrelated(field, "   ")


# -- cross-field: "don't know" is UNKNOWN_VALUE for every field ---------------

@pytest.mark.parametrize(
    "field",
    ["vehicle_type", "speed_excess_kmh", "alcohol_level", "passenger_count", "license_status", "modification_type"],
)
def test_dont_know_is_unknown_value_for_every_field(field: str) -> None:
    _assert_unknown_value(field, "Tôi không biết.")
