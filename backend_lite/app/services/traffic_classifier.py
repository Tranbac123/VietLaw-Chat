"""VietLaw Public Beta V0: bounded deterministic traffic-fact classifier.

Same design discipline as `fast_demo_fact_validation.py` and
`fast_demo_routing.py`: a bounded Vietnamese cue allowlist, not a general
NLP parser. A fact is extracted only when the CURRENT message states it
explicitly; nothing is inferred from vague wording (task §5.1: "Do not
force facts from vague wording").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..contracts.traffic import (
    ClarificationAnswer,
    ClarificationAnswerKind,
    LicenseStatus,
    ModificationType,
    TrafficAttribution,
    TrafficFacts,
    VehicleType,
)

_SEPARATORS = re.compile(r"[-_/\\()\[\]{}.·,;:!?\"'“”‘’…]+")


def _normalize(text: str) -> str:
    nfc = unicodedata.normalize("NFC", text)
    decomposed = unicodedata.normalize("NFD", nfc.lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    stripped = stripped.replace("đ", "d")
    spaced = _SEPARATORS.sub(" ", stripped)
    return re.sub(r"\s+", " ", spaced).strip()


# ---------------------------------------------------------------------------
# Topic detection. Each topic requires an explicit action/violation cue --
# never a bare vehicle-type word alone, and never a question ABOUT the topic
# ("phạt vượt đèn đỏ bao nhiêu?" still counts -- that IS a violation-topic
# question -- but "vượt đèn đỏ là gì?" does not carry an action cue distinct
# from a definition query; the bounded phrase set below only matches
# violation/penalty-shaped wording, not bare topic nouns).
# ---------------------------------------------------------------------------

_TOPIC_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "red_light",
        (
            "vuot den do", "khong chap hanh den tin hieu", "vuot den giao thong",
            # A bare "vượt đèn ..." (no explicit "đỏ") is required by the
            # accident-branch negative probe ("Tôi vượt đèn và gây tai
            # nạn.") to still reach the selector (so the accident exclusion
            # is actually exercised, not just an unmatched-topic fallthrough).
            "vuot den",
        ),
    ),
    (
        "no_helmet",
        (
            "khong doi mu bao hiem", "khong deo mu bao hiem", "quen mu bao hiem",
            # Traffic Safe Subset V1: a required positive probe ("Tôi đội mũ
            # nhưng không cài quai.") never says "không đội mũ" at all --
            # the strap-not-fastened phrasing is its own violation cue.
            "khong cai quai",
        ),
    ),
    (
        "alcohol",
        (
            "nong do con", "uong ruou bia lai xe", "co con lai xe", "thoi nong do con",
            # A bare breath-test measurement ("0.2 mg/l khí thở") is one of
            # the task's required disabled-topic probes and never says "nồng
            # độ cồn" explicitly -- "/" is stripped to a space by
            # `_normalize`, so "mg/l" becomes "mg l".
            "mg l", "khi tho",
        ),
    ),
    ("speeding", ("qua toc do", "vuot toc do", "chay qua toc do", "lai xe nhanh qua quy dinh")),
    (
        "driver_license",
        (
            "khong co bang lai", "quen bang lai", "quen mang bang lai", "chua co bang lai",
            "bang lai het han", "bi tuoc bang lai", "khong co giay phep lai xe",
            "quen giay phep lai xe", "quen mang giay phep lai xe",
            "chua tung co bang lai", "chua tung co giay phep lai xe",
        ),
    ),
    (
        "phone_use",
        (
            "dung dien thoai khi lai xe", "dung dien thoai khi di xe", "dung dien thoai khi chay xe",
            "nghe dien thoai khi chay xe", "nghe dien thoai khi lai xe", "nghe dien thoai khi di xe",
            "su dung dien thoai khi dieu khien xe", "su dung dien thoai khi di xe",
            "dung dien thoai khi dang lai xe", "dung dien thoai khi dang di xe",
            "dung dien thoai khi dang chay xe", "nghe dien thoai khi dang chay xe",
            "nghe dien thoai khi dang lai xe", "nghe dien thoai khi dang di xe",
            # Traffic Safe Subset V1: "tay cầm điện thoại" (hand-held phone)
            # phrasing, needed for Rule D's required positive probe ("Tôi
            # dùng tay cầm điện thoại khi đang chạy xe máy.") -- the cues
            # above all require "dùng điện thoại" to be immediately
            # adjacent to the vehicle verb, which "tay cầm" interrupts.
            "tay cam dien thoai", "cam dien thoai bang tay", "cam tay dien thoai",
        ),
    ),
    ("passenger_limit", ("cho qua so nguoi", "cho ba nguoi", "cho qua tai nguoi", "cho may nguoi")),
    (
        "vehicle_modification",
        ("thay doi ket cau xe", "do xe", "thay lop nho", "thay doi kich thuoc xe", "cai tao xe"),
    ),
)

#: Correction Round 2 (M-02-R) added the bare "mo to" alias so a standalone
#: clarification reply of just "Mô tô." (no "xe" prefix) still resolves --
#: the topic-cue list otherwise only matched "xe mô tô" as a substring of a
#: longer sentence.
_VEHICLE_CUES = {
    "motorcycle": ("xe may", "xe gan may", "xe mo to", "mo to"),
    "car": ("o to", "xe hoi", "xe con"),
}

#: Correction Round 2 (M-02-R) added short-answer aliases ("quen mang bang",
#: "khong mang theo", "bang het han", ... -- without the "lái"/"giấy phép"
#: qualifier) so a standalone clarification reply resolves even when it
#: doesn't repeat the full topic-detection phrasing. Deliberately still
#: requires "bằng"/"giấy phép" (or, for "forgot", the specific "không mang
#: theo") rather than a bare "hết hạn"/"bị thu hồi" -- those alone are far
#: too generic ("hết hạn thuê nhà", "thu hồi đất" are NOT license answers).
_LICENSE_STATUS_CUES: tuple[tuple[LicenseStatus, tuple[str, ...]], ...] = (
    (
        "forgot",
        (
            "quen bang lai", "quen giay phep lai xe", "quen mang bang lai", "quen mang giay phep",
            "quen mang bang", "quen giay phep", "khong mang theo",
        ),
    ),
    (
        "never_licensed",
        (
            "chua co bang lai", "chua tung co bang lai", "chua co giay phep lai xe",
            "chua tung co giay phep lai xe", "chua co bang", "chua tung co bang",
            "chua co giay phep", "chua tung co giay phep",
        ),
    ),
    ("expired", ("bang lai het han", "giay phep lai xe het han", "bang het han", "giay phep het han")),
    (
        "revoked",
        ("bi tuoc bang lai", "bi tuoc giay phep lai xe", "dang bi tuoc", "bang bi thu hoi", "bi tuoc bang", "bi tuoc giay phep"),
    ),
)

#: Correction Round 2 (M-02-R) added short-answer aliases for each
#: modification type ("đổi pô", "thay khung", "đổi đèn", "thay biển số", ...)
#: -- the topic-cue list otherwise only matched longer, differently-ordered
#: phrasings, so a standalone clarification reply like "Thay khung." failed
#: to resolve even though it unambiguously answers the pending field.
_MODIFICATION_CUES: tuple[tuple[ModificationType, tuple[str, ...]], ...] = (
    ("tire", ("thay lop", "doi lop", "lop nho", "lop khac kich thuoc")),
    ("exhaust", ("ong xa", "po do", "doi po", "thay po")),
    ("frame", ("khung xe", "sat xi", "thay khung", "doi khung")),
    ("lighting", ("den xe", "den led do", "doi den", "thay den")),
    ("license_plate", ("bien so", "thay bien so", "doi bien so")),
)

_SPEED_EXCESS_RE = re.compile(r"qua\s+toc\s+do\s+(\d{1,3})|vuot\s+(\d{1,3})\s*km")
_PASSENGER_COUNT_RE = re.compile(r"cho\s+(\d{1,2})\s*nguoi|(\d{1,2})\s*nguoi\s+tren\s+xe")

# ---------------------------------------------------------------------------
# Traffic Safe Subset V1 (legal-accuracy correction): bounded fact detectors
# for the four re-enabled rules. Each returns "unknown" by default -- never
# inferred from silence (task §4).
# ---------------------------------------------------------------------------

#: A message-level mention of a yellow (or flashing-yellow) signal always
#: wins over the mere presence of the red-light topic cue: the topic cue is
#: itself the phrase "vượt đèn đỏ" ("ran the red light"), but a user may use
#: that colloquially while going on to clarify the light was actually
#: turning yellow ("...nhưng đèn lúc đó đang chuyển vàng").
_FLASHING_YELLOW_CUES: tuple[str, ...] = ("den vang nhap nhay", "tin hieu vang nhap nhay")
_YELLOW_CUES: tuple[str, ...] = ("den vang", "tin hieu vang", "chuyen vang", "dang vang")
_RED_CUES: tuple[str, ...] = ("den do", "tin hieu do")


def _detect_signal_type(normalized: str, *, topic_matched_red_light: bool) -> str:
    if any(cue in normalized for cue in _FLASHING_YELLOW_CUES):
        return "flashing_yellow"
    if any(cue in normalized for cue in _YELLOW_CUES):
        return "yellow"
    if any(cue in normalized for cue in _RED_CUES) or topic_matched_red_light:
        return "red"
    return "unknown"


#: Both this and `_ACCIDENT_CAUSED_CUES` below are consulted through
#: `_any_cue_unnegated`, not a bare substring check -- a negated mention
#: ("Tôi đi xe máy vượt đèn đỏ, KHÔNG gây tai nạn.", a required positive
#: probe) must resolve to `"unknown"` (safe to proceed), never `"yes"`.
#: `_is_negated_at` is already defined below in this module for the topic
#: negation guard; declared here via forward reference at call time since
#: Python resolves module-level names at call, not definition, time.
_TRAFFIC_CONTROLLER_OVERRIDE_CUES: tuple[str, ...] = (
    "theo hieu lenh cua canh sat", "theo hieu lenh cua nguoi dieu khien giao thong",
    "canh sat giao thong ra hieu", "csgt ra hieu", "theo chi dan cua canh sat",
    "theo hieu lenh csgt",
)


def _any_cue_unnegated(normalized: str, cues: tuple[str, ...]) -> bool:
    for cue in cues:
        start = 0
        while True:
            idx = normalized.find(cue, start)
            if idx == -1:
                break
            if not _is_negated_at(normalized, idx):
                return True
            start = idx + len(cue)
    return False


def _detect_traffic_controller_override(normalized: str) -> str:
    if _any_cue_unnegated(normalized, _TRAFFIC_CONTROLLER_OVERRIDE_CUES):
        return "yes"
    return "unknown"


_ACCIDENT_CAUSED_CUES: tuple[str, ...] = ("gay tai nan", "gay ra tai nan", "va cham gay thuong tich")


def _detect_accident_caused(normalized: str) -> str:
    if _any_cue_unnegated(normalized, _ACCIDENT_CAUSED_CUES):
        return "yes"
    return "unknown"


#: An explicit third-party helmet subject (someone other than the speaker).
#: Checked BEFORE the driver-default so "Người ngồi sau không đội mũ." is
#: never mistaken for the speaker's own helmet status.
_HELMET_PASSENGER_CUES: tuple[str, ...] = (
    "nguoi ngoi sau", "hanh khach", "nguoi duoc cho", "cho nguoi khac khong doi mu",
)
_HELMET_DRIVER_CUES: tuple[str, ...] = (
    "toi lai", "toi dieu khien", "nguoi lai xe", "nguoi dieu khien xe",
)
#: A bare self-referential helmet mention with no passenger cue -- the
#: speaker is describing their OWN helmet-wearing while riding, the default
#: subject for a first-person traffic report (task §9's required positive
#: probe "Tôi đội mũ nhưng không cài quai." has no explicit "lái" verb at
#: all, yet must resolve as the driver's own helmet status).
_HELMET_SELF_MENTION_CUES: tuple[str, ...] = ("toi khong doi mu", "toi doi mu", "toi khong cai quai")


def _detect_helmet_subject(normalized: str) -> str:
    if any(cue in normalized for cue in _HELMET_PASSENGER_CUES):
        return "passenger"
    if any(cue in normalized for cue in _HELMET_DRIVER_CUES):
        return "driver"
    if any(cue in normalized for cue in _HELMET_SELF_MENTION_CUES):
        return "driver"
    return "unknown"


#: Checked in this order: "not cài quai" is more specific than a bare "not
#: đội mũ" and must win when both could match (they don't overlap in
#: practice, but order still documents intent). "wearing_correctly" requires
#: an EXPLICIT "đúng quy cách"/"đúng cách" qualifier -- a bare "đội mũ" alone
#: must never be read as confirming correct wear (that would silently turn
#: an unrelated mention into an exclusion).
_HELMET_STATUS_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("improperly_fastened", ("khong cai quai",)),
    ("not_wearing", ("khong doi mu", "khong deo mu")),
    ("wearing_correctly", ("doi mu dung quy cach", "doi mu bao hiem dung cach", "co doi mu dung quy cach")),
)


def _detect_helmet_status(normalized: str) -> str:
    for status, cues in _HELMET_STATUS_CUES:
        if any(cue in normalized for cue in cues):
            return status
    return "unknown"


_PHONE_HANDHELD_YES_CUES: tuple[str, ...] = (
    "dung tay cam", "cam dien thoai bang tay", "cam tay dien thoai", "tay cam dien thoai",
)
_PHONE_HANDHELD_NO_CUES: tuple[str, ...] = (
    "ranh tay", "tai nghe", "gia do", "gan tren xe", "gan tren gia", "khong cam tay",
)


def _detect_phone_handheld(normalized: str) -> str:
    if any(cue in normalized for cue in _PHONE_HANDHELD_NO_CUES):
        return "no"
    if any(cue in normalized for cue in _PHONE_HANDHELD_YES_CUES):
        return "yes"
    return "unknown"


_VEHICLE_STOPPED_CUES: tuple[str, ...] = ("da dung xe", "xe da dung", "khi xe da dung", "dung xe roi", "xe dang dung")
_VEHICLE_IN_OPERATION_CUES: tuple[str, ...] = (
    "dang chay xe", "dang lai xe", "dang dieu khien xe", "khi dang di xe", "khi dang chay xe",
    "dang di xe", "dang chay", "dang lai",
)


def _detect_vehicle_in_operation(normalized: str) -> str:
    if any(cue in normalized for cue in _VEHICLE_STOPPED_CUES):
        return "no"
    if any(cue in normalized for cue in _VEHICLE_IN_OPERATION_CUES):
        return "yes"
    return "unknown"

#: Negation preceding a topic action cue ("tôi KHÔNG vượt đèn đỏ", "tôi CHƯA
#: TỪNG lái xe khi CÓ nồng độ cồn") -- scoped to the topic action cues only:
#: license-status cues like "chưa có bằng lái" deliberately use "chưa" as
#: part of their own positive meaning and must not be affected by this
#: guard.
_NEGATION_WORDS = ("khong", "chua", "chang")
#: Clause-boundary words: negation scanning stops here rather than reading
#: into an earlier, unrelated clause of the same message (normalization
#: strips sentence-ending punctuation to spaces, so a period alone cannot
#: serve as the boundary -- see `_normalize`). A bounded heuristic, not a
#: full negation/clause grammar (same discipline as
#: `fast_demo_fact_validation.py`'s left-context window), but scanning the
#: whole clause rather than a fixed word count is what correctly catches
#: "chưa từng lái xe khi có nồng độ cồn" (6 words between negator and cue)
#: without also reaching across "Hôm qua trời mưa to. Tôi vượt đèn đỏ..."
#: style unrelated leading sentences.
_CLAUSE_BOUNDARY_WORDS = frozenset({"nhung", "va", "nen", "roi", "con", "hoac", "sau do"})


def _is_negated_at(normalized: str, cue_start: int) -> bool:
    left_words = normalized[:cue_start].split()
    scoped: list[str] = []
    for word in reversed(left_words):
        if word in _CLAUSE_BOUNDARY_WORDS:
            break
        scoped.append(word)
    return any(word in _NEGATION_WORDS for word in scoped)


# ---------------------------------------------------------------------------
# Attribution (Correction Round 1, M-01): who the detected event is ABOUT.
# Only `"self"` may cause a fact to be persisted into per-chat state or a
# curated answer phrased as the user's own confirmed event. Checked in
# priority order -- a message can only carry one attribution, and a
# third-party/hypothetical/educational marker always wins over an
# incidental "tôi" elsewhere in the same message (e.g. "tôi" inside "bạn
# TÔI" is not a first-person subject).
# ---------------------------------------------------------------------------

#: Bounded set of common Vietnamese third-party subject phrases. Deliberately
#: narrow (not a full pronoun/kinship grammar): covers the required probes
#: and their obvious siblings, never a bare "họ"/"anh ấy" alone (too easily
#: a false positive elsewhere).
_THIRD_PARTY_SUBJECT_CUES: tuple[str, ...] = (
    "ban toi", "ban cua toi", "anh toi", "anh trai toi", "chi toi", "chi gai toi",
    "em toi", "em trai toi", "em gai toi", "bo toi", "me toi", "con toi",
    "vo toi", "chong toi", "dong nghiep toi", "hang xom toi", "nguoi than toi",
    "mot nguoi ban", "nguoi khac", "ho vua", "anh ay vua", "co ay vua",
)

#: Conditional/hypothetical framing markers. Presence alone is treated as
#: hypothetical regardless of subject -- a user who explicitly frames their
#: own question conditionally ("nếu tôi...") is still asking about a
#: hypothetical consequence, not reporting a confirmed current event.
_HYPOTHETICAL_MARKERS: tuple[str, ...] = ("neu", "gia su", "vi du", "truong hop")

#: Educational/research framing: the user is reading/studying ABOUT the
#: topic, not reporting their own event.
_EDUCATIONAL_CUES: tuple[str, ...] = (
    "dang doc", "bai viet", "nghien cuu ve", "tai lieu ve", "hoc ve", "tim hieu ve",
)

#: A first-person subject marker. Checked LAST (lowest priority): every
#: third-party cue above also contains the substring "toi", so it must never
#: be checked first.
_SELF_SUBJECT_RE = re.compile(r"\btoi\b")


def _detect_attribution(normalized: str, *, action_negated: bool) -> TrafficAttribution:
    if action_negated:
        return "negated"
    if any(cue in normalized for cue in _THIRD_PARTY_SUBJECT_CUES):
        return "third_party"
    if any(cue in normalized for cue in _HYPOTHETICAL_MARKERS):
        return "hypothetical"
    if any(cue in normalized for cue in _EDUCATIONAL_CUES):
        return "educational"
    if _SELF_SUBJECT_RE.search(normalized):
        return "self"
    return "unknown"


#: Explicit "I don't know" -- treated as a genuine (if unresolved) attempt to
#: answer a pending clarification, never as an unrelated turn, for fields
#: with no bounded structural extraction (e.g. `alcohol_level`).
_DONT_KNOW_CUES: tuple[str, ...] = (
    "khong biet", "chua biet", "khong ro", "chua ro", "khong nho", "khong chac",
)

# ---------------------------------------------------------------------------
# Correction Round 2 (M-02-R): field-specific clarification-answer parsing.
#
# Root cause of the prior defect: `is_valid_clarification_answer` accepted
# ANY digit as an answer for `speed_excess_kmh`/`alcohol_level`/
# `passenger_count`. An unrelated message that merely happens to contain a
# number ("Hôm nay 30 độ C.", "Tôi nhận lương tháng 7...") was therefore
# treated as a genuine clarification attempt, which -- because it carries no
# first-person traffic attribution -- returned a generic answer WITHOUT ever
# clearing the pending state, leaving `traffic_topic_id`/
# `traffic_pending_field` on disk to contaminate a later, completely
# unrelated turn.
#
# The fix is a real parser per numeric field: a bare digit is never enough
# on its own -- it must be adjacent to the field's own unit/context word
# ("km"/"km/h"/"cây" for speed, "mg/l"/"mg/100ml"/"mg%" for alcohol,
# "người" for passengers). A message with a digit but no such context is
# UNRELATED, exactly like a message with no digit at all.
# ---------------------------------------------------------------------------

#: Speed-excess reply: a number immediately followed by a speed unit. The
#: leading "vượt"/"quá"/"khoảng" verb is optional -- a bare "10 km/h." must
#: still resolve, since it is answering a question the system itself just
#: asked ("bạn vượt bao nhiêu km/h?"), not making a free-standing claim.
_SPEED_ANSWER_RE = re.compile(r"\b(\d{1,3})\s*(?:km\s*h|km|cay\s*so|cay)\b")

#: Alcohol-level reply: a number with an alcohol-specific unit (mg/l,
#: mg/100ml, mg%). Deliberately NOT run against the accent-stripped,
#: separator-collapsing `_normalize()` output -- that collapses "0,2"/"0.2"
#: into two separate digit tokens ("0 2"), destroying the decimal value.
#: Applied to `message.lower()` instead, which is enough (the unit itself is
#: plain ASCII) and keeps the decimal point/comma intact.
_ALCOHOL_ANSWER_RE = re.compile(
    r"(\d+[.,]?\d*)\s*mg\s*/?\s*(?:100\s*)?m?l|(\d+[.,]?\d*)\s*mg\s*%"
)

#: Passenger-count reply: a number, or a small Vietnamese number WORD,
#: immediately followed by "người". Word-form ("ba người") is required by
#: the task; digit-form ("3 người"/"chở 3 người"/"tổng cộng 4 người") is the
#: common case.
_PASSENGER_ANSWER_DIGIT_RE = re.compile(r"\b(\d{1,2})\s*nguoi\b")
_VN_SMALL_NUMBER_WORDS: dict[str, int] = {
    "mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5,
    "sau": 6, "bay": 7, "tam": 8, "chin": 9, "muoi": 10,
}
_PASSENGER_ANSWER_WORD_RE = re.compile(
    r"\b(" + "|".join(_VN_SMALL_NUMBER_WORDS) + r")\s+nguoi\b"
)


def _parse_speed_excess_answer(normalized: str) -> int | None:
    match = _SPEED_ANSWER_RE.search(normalized)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _parse_alcohol_level_answer(raw_message: str) -> str | None:
    match = _ALCOHOL_ANSWER_RE.search(raw_message.lower())
    if not match:
        return None
    return match.group(0).strip()


def _parse_passenger_count_answer(normalized: str) -> int | None:
    match = _PASSENGER_ANSWER_DIGIT_RE.search(normalized)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    match = _PASSENGER_ANSWER_WORD_RE.search(normalized)
    if match:
        return _VN_SMALL_NUMBER_WORDS.get(match.group(1))
    return None


def _parse_vehicle_type_answer(normalized: str) -> str | None:
    value = _detect_vehicle_type(normalized)
    return None if value == "unknown" else value


def _parse_license_status_answer(normalized: str) -> str | None:
    value = _detect_license_status(normalized)
    return None if value == "unknown" else value


def _parse_modification_type_answer(normalized: str) -> str | None:
    value = _detect_modification_type(normalized)
    return None if value == "unknown" else value


#: Traffic Safe Subset V1: clarification-answer parsers for the five new
#: fields, each accepting a bounded bare-word short reply in addition to the
#: full-sentence cues `classify()` already detects with (e.g. a standalone
#: "Đỏ." answering "đèn tín hiệu đang màu gì?").
def _parse_signal_type_answer(normalized: str) -> str | None:
    stripped = normalized.strip()
    if any(cue in normalized for cue in _FLASHING_YELLOW_CUES):
        return "flashing_yellow"
    if any(cue in normalized for cue in _YELLOW_CUES) or stripped == "vang":
        return "yellow"
    if any(cue in normalized for cue in _RED_CUES) or stripped == "do":
        return "red"
    return None


def _parse_helmet_subject_answer(normalized: str) -> str | None:
    stripped = normalized.strip()
    if any(cue in normalized for cue in _HELMET_PASSENGER_CUES) or stripped in ("nguoi ngoi sau", "hanh khach"):
        return "passenger"
    if any(cue in normalized for cue in _HELMET_DRIVER_CUES) or stripped in ("toi", "nguoi lai", "tai xe", "nguoi lai xe"):
        return "driver"
    return None


def _parse_helmet_status_answer(normalized: str) -> str | None:
    value = _detect_helmet_status(normalized)
    return None if value == "unknown" else value


def _parse_phone_handheld_answer(normalized: str) -> str | None:
    value = _detect_phone_handheld(normalized)
    return None if value == "unknown" else value


def _parse_vehicle_in_operation_answer(normalized: str) -> str | None:
    value = _detect_vehicle_in_operation(normalized)
    return None if value == "unknown" else value


def parse_clarification_answer(pending_field: str, message: str) -> ClarificationAnswer:
    """Correction Round 2 (M-02-R): interpret `message` in the context of
    the SPECIFIC pending traffic clarification field the system itself just
    asked about -- a typed replacement for the boolean
    `is_valid_clarification_answer` (kept below as a thin wrapper for
    existing callers that only need the yes/no signal).

    A clarification answer is deliberately NOT run through the general
    first-person attribution detector (`_detect_attribution`): the
    conversational context (a pending question about a specific field) IS
    the attribution -- "Xe máy." or "10 km/h." answers the system's own
    question regardless of whether it names a subject.
    """

    if not message or not message.strip():
        return ClarificationAnswer(kind=ClarificationAnswerKind.UNRELATED, field=pending_field)

    normalized = _normalize(message)
    if any(cue in normalized for cue in _DONT_KNOW_CUES):
        return ClarificationAnswer(kind=ClarificationAnswerKind.UNKNOWN_VALUE, field=pending_field)

    parsed_value: str | int | None
    if pending_field == "vehicle_type":
        parsed_value = _parse_vehicle_type_answer(normalized)
    elif pending_field == "license_status":
        parsed_value = _parse_license_status_answer(normalized)
    elif pending_field == "modification_type":
        parsed_value = _parse_modification_type_answer(normalized)
    elif pending_field == "speed_excess_kmh":
        parsed_value = _parse_speed_excess_answer(normalized)
    elif pending_field == "passenger_count":
        parsed_value = _parse_passenger_count_answer(normalized)
    elif pending_field == "alcohol_level":
        parsed_value = _parse_alcohol_level_answer(message)
    elif pending_field == "signal_type":
        parsed_value = _parse_signal_type_answer(normalized)
    elif pending_field == "helmet_subject":
        parsed_value = _parse_helmet_subject_answer(normalized)
    elif pending_field == "helmet_status":
        parsed_value = _parse_helmet_status_answer(normalized)
    elif pending_field == "phone_handheld":
        parsed_value = _parse_phone_handheld_answer(normalized)
    elif pending_field == "vehicle_in_operation":
        parsed_value = _parse_vehicle_in_operation_answer(normalized)
    else:
        parsed_value = None

    if parsed_value is None:
        return ClarificationAnswer(kind=ClarificationAnswerKind.UNRELATED, field=pending_field)
    return ClarificationAnswer(
        kind=ClarificationAnswerKind.RESOLVED, field=pending_field, parsed_value=parsed_value
    )


def is_valid_clarification_answer(pending_field: str, message: str) -> bool:
    """Correction Round 1 (M-02) boolean signal, now a thin wrapper over the
    typed `parse_clarification_answer` (Correction Round 2, M-02-R). `True`
    for both `RESOLVED` and `UNKNOWN_VALUE` -- both are genuine answer
    attempts that must continue the pending topic; only `UNRELATED` means
    "release the pending clarification"."""

    return parse_clarification_answer(pending_field, message).kind != ClarificationAnswerKind.UNRELATED


@dataclass
class TrafficDetection:
    topic_id: str | None
    facts: TrafficFacts = field(default_factory=TrafficFacts)
    #: Correction Round 1 (M-01). See `contracts/traffic.py::TrafficAttribution`.
    attribution: TrafficAttribution = "unknown"


def _find_topic_and_negation(message: str) -> tuple[str | None, bool]:
    """Narrow by design: the first matching NON-negated topic wins, and only
    one topic is ever reported per message -- a message naming two different
    violations is out of scope for this bounded classifier and correctly
    falls through to a single clarifying question or the official-search/
    general-guidance path rather than guessing which one the user meant.

    Also reports whether a negated occurrence was seen at all (even if no
    positive topic was ultimately found), so `classify()` can distinguish
    "no violation ever mentioned" from "a violation was mentioned and
    explicitly negated" for attribution purposes (task M-01: `NEGATED_EVENT`).
    """

    normalized = _normalize(message)
    any_negated = False
    for topic, cues in _TOPIC_CUES:
        for cue in cues:
            for match in re.finditer(re.escape(cue), normalized):
                if _is_negated_at(normalized, match.start()):
                    any_negated = True
                else:
                    return topic, False

    # `passenger_limit`'s own cues are all fixed word-count phrases ("chở BA
    # người") or generic-overload phrasing -- a digit count ("chở 3 người",
    # one of the task's required disabled-topic probes) needs the same
    # numeric pattern `_PASSENGER_COUNT_RE` already uses to EXTRACT the
    # count, reused here just to DETECT the topic.
    passenger_match = _PASSENGER_COUNT_RE.search(normalized)
    if passenger_match:
        if _is_negated_at(normalized, passenger_match.start()):
            any_negated = True
        else:
            return "passenger_limit", False

    return None, any_negated


def detect_topic(message: str) -> str | None:
    """Return the bare topic slug (e.g. `"red_light"`) or `None`."""

    topic, _ = _find_topic_and_negation(message)
    return topic


def _detect_vehicle_type(normalized: str) -> VehicleType:
    for vehicle, cues in _VEHICLE_CUES.items():
        if any(cue in normalized for cue in cues):
            return vehicle  # type: ignore[return-value]
    return "unknown"


def _detect_license_status(normalized: str) -> LicenseStatus:
    for status, cues in _LICENSE_STATUS_CUES:
        if any(cue in normalized for cue in cues):
            return status
    return "unknown"


def _detect_modification_type(normalized: str) -> ModificationType:
    for kind, cues in _MODIFICATION_CUES:
        if any(cue in normalized for cue in cues):
            return kind
    return "unknown"


def classify(message: str) -> TrafficDetection:
    """Bounded extraction. Returns `topic_id=None` (via the public topic-id
    mapping in the caller) when no topic cue matched at all -- callers must
    treat that as "not a traffic message", never as "traffic with unknown
    violation_type".

    `attribution` (task M-01) tells the caller whether `facts` may be
    persisted as the user's own event: only `"self"` may. Every other value
    still allows a general/impersonal answer, but the caller must not merge
    `facts` into per-chat state or claim the user committed the violation.
    """

    normalized = _normalize(message)
    topic, any_negated = _find_topic_and_negation(message)
    attribution = _detect_attribution(normalized, action_negated=(topic is None and any_negated))

    # Traffic Safe Subset V1 fact detectors are scoped to their own topic --
    # e.g. "Tôi lái ô tô vượt đèn đỏ." must not incidentally set
    # `helmet_subject="driver"` (the `_HELMET_DRIVER_CUES` "tôi lái" cue would
    # otherwise fire on any first-person driving mention). An out-of-topic
    # fact stays `"unknown"`, which is always safe to proceed on for a
    # NON-blocking excluded fact and always blocking (askable) for a
    # required one -- never a false exclusion or a false match.
    if topic == "red_light":
        signal_type = _detect_signal_type(normalized, topic_matched_red_light=True)
        traffic_controller_override = _detect_traffic_controller_override(normalized)
        accident_caused = _detect_accident_caused(normalized)
    else:
        signal_type = "unknown"
        traffic_controller_override = "unknown"
        accident_caused = "unknown"

    if topic == "no_helmet":
        helmet_subject = _detect_helmet_subject(normalized)
        helmet_status = _detect_helmet_status(normalized)
    else:
        helmet_subject = "unknown"
        helmet_status = "unknown"

    if topic == "phone_use":
        phone_handheld = _detect_phone_handheld(normalized)
        vehicle_in_operation = _detect_vehicle_in_operation(normalized)
    else:
        phone_handheld = "unknown"
        vehicle_in_operation = "unknown"

    facts = TrafficFacts(
        vehicle_type=_detect_vehicle_type(normalized),
        violation_type=topic or "unknown",  # type: ignore[arg-type]
        license_status=_detect_license_status(normalized),
        modification_type=_detect_modification_type(normalized),
        signal_type=signal_type,
        traffic_controller_override=traffic_controller_override,
        accident_caused=accident_caused,
        helmet_subject=helmet_subject,
        helmet_status=helmet_status,
        phone_handheld=phone_handheld,
        vehicle_in_operation=vehicle_in_operation,
    )

    speed_match = _SPEED_EXCESS_RE.search(normalized)
    if speed_match:
        raw = speed_match.group(1) or speed_match.group(2)
        try:
            facts.speed_excess_kmh = int(raw)
        except (TypeError, ValueError):
            pass

    passenger_match = _PASSENGER_COUNT_RE.search(normalized)
    if passenger_match:
        raw = passenger_match.group(1) or passenger_match.group(2)
        try:
            facts.passenger_count = int(raw)
        except (TypeError, ValueError):
            pass

    return TrafficDetection(
        topic_id=(f"traffic_{topic}" if topic else None), facts=facts, attribution=attribution
    )


__all__ = [
    "TrafficDetection",
    "classify",
    "detect_topic",
    "is_valid_clarification_answer",
    "parse_clarification_answer",
]
