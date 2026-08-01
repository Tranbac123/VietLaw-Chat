"""FAST DEMO V2 fact-update validation.

Every ``fact_updates`` entry from the model is a *proposal*. Nothing reaches
state until it survives all of:

  1. slot allowlisted, operation allowlisted;
  2. ``evidence_quote`` maps to the CURRENT user message by exact normalized
     substring match (NFKC -> casefold -> whitespace collapse). No fuzzy match,
     no semantic match;
  3. exactly one match, or several matches that cannot disagree;
  4. the value is valid for the slot -- numeric amounts are re-parsed from the
     verified original span, never taken on the model's word;
  5. polarity is unambiguous for tri-state slots.

Rejecting one proposal never rejects the whole response: the turn continues
with the remaining valid updates and the unchanged state.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from ..contracts.fast_demo import (
    ALLOWED_EVIDENCE_TYPES,
    ALLOWED_SLOTS,
    ALLOWED_USER_GOALS,
    RECEIVING_PARTY_NONPERFORMANCE_SLOT,
    DepositAmount,
    FactUpdateProposal,
    FastDemoState,
    TRI_STATE_SLOTS,
)

_WS = re.compile(r"\s+")


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Return (normalized_text, index_map) where index_map[i] is the offset in
    the ORIGINAL string that normalized character i came from.

    Keeping the map is what lets us persist original_start/original_end that
    point into the user's own message rather than into model-written text.
    """

    out_chars: list[str] = []
    out_map: list[int] = []
    pending_space = False
    started = False

    for original_index, char in enumerate(text):
        folded = unicodedata.normalize("NFKC", char).casefold()
        if not folded:
            continue
        if folded.isspace() or _WS.fullmatch(folded):
            if started:
                pending_space = True
            continue
        if pending_space:
            out_chars.append(" ")
            out_map.append(original_index)
            pending_space = False
        for sub in folded:
            out_chars.append(sub)
            out_map.append(original_index)
        started = True

    return "".join(out_chars), out_map


@dataclass
class VerifiedSpan:
    original_start: int
    original_end: int
    original_quote: str


def locate_quote(quote: str, message: str) -> tuple[list[VerifiedSpan], str]:
    """Find every exact normalized occurrence of ``quote`` inside ``message``.

    Returns (spans, normalized_quote). Empty spans means the quote could not be
    verified and the proposal must be rejected.
    """

    norm_quote, _ = normalize_with_map(quote)
    if not norm_quote.strip():
        return [], norm_quote
    norm_message, index_map = normalize_with_map(message)
    if not norm_message:
        return [], norm_quote

    spans: list[VerifiedSpan] = []
    start = norm_message.find(norm_quote)
    while start != -1:
        end = start + len(norm_quote)
        original_start = index_map[start]
        # index_map[end - 1] is the original index of the last matched char;
        # +1 makes the slice end-exclusive over the original string.
        original_end = index_map[end - 1] + 1
        spans.append(
            VerifiedSpan(
                original_start=original_start,
                original_end=original_end,
                original_quote=message[original_start:original_end],
            )
        )
        start = norm_message.find(norm_quote, start + 1)
    return spans, norm_quote


# ---------------------------------------------------------------------------
# Vietnamese amount parsing, bounded to the formats the golden flow needs.
# ---------------------------------------------------------------------------

_AMOUNT_RE = re.compile(
    r"(\d[\d.,\s]*)\s*(trieu|tr|nghin|ngan|k|dong|d)\b",
    re.IGNORECASE,
)


# Accent stripping collapses two different words onto the token `chang`:
#   "chẳng" ("not at all")        -> real negation
#   "chăng" ("perhaps/is it so?") -> interrogative particle, NOT negation
# So a normalized `chang` may not be trusted as a negator on its own. Worse,
# simply dropping it would expose the positive cue inside the question:
# "Phải chăng đã ký hợp đồng?" would resolve `present` off "đã ký".
#
# Provenance is therefore decided on the ORIGINAL, still-accented evidence,
# before `_strip_accents` runs. Only "chẳng" is trusted as a negator; "chăng"
# and a bare unaccented "chang" (whose origin is unrecoverable) both block
# inference entirely, in either direction.
#
# This is a bounded disambiguation of one normalization collision, not a
# general Vietnamese question classifier.
_AMBIGUOUS_CHANG_RE = re.compile(r"\b(?:chăng|chang)\b")


def _has_ambiguous_chang(text: str) -> bool:
    """True when ``text`` carries a `chang` whose meaning cannot be trusted.

    Matches the interrogative "chang" and the accent-stripped "chang", but not
    the negation "chang", which stays available as a negator.
    """

    return _AMBIGUOUS_CHANG_RE.search(unicodedata.normalize("NFC", text).casefold()) is not None


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.replace("đ", "d")


def parse_amount_from_text(text: str) -> int | None:
    """Parse the first bounded Vietnamese amount in ``text``, or None."""

    normalized = _strip_accents(text)
    match = _AMOUNT_RE.search(normalized)
    if match is None:
        return None
    number = _to_number(match.group(1))
    if number is None:
        return None
    unit = match.group(2).lower()
    if unit in {"trieu", "tr"}:
        return int(round(number * 1_000_000))
    if unit in {"nghin", "ngan", "k"}:
        return int(round(number * 1_000))
    return int(round(number))


def _to_number(raw: str) -> float | None:
    token = raw.strip().replace(" ", "")
    if not token:
        return None
    if "," in token and "." in token:
        token = token.replace(".", "").replace(",", ".")
    elif "," in token:
        # "20,5" -> decimal comma; "20,000" -> thousands separator
        parts = token.split(",")
        token = token.replace(",", "") if len(parts[-1]) == 3 else token.replace(",", ".")
    elif "." in token:
        parts = token.split(".")
        token = token.replace(".", "") if all(len(p) == 3 for p in parts[1:]) else token
    try:
        return float(token)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Polarity, bounded. Not a general Vietnamese negation grammar.
# ---------------------------------------------------------------------------

_NEGATIVE_RE = re.compile(
    # Negators only: khong, chua, chang (<- "chang"). "chan" is NOT one -- it is
    # the stripped form of "chan" ("bored"), so "toi chan ky giay to" ("I am fed
    # up with signing paperwork") would read as "did not sign".
    r"\b(?:khong|chua|chang)\s+(?:co|ky|nhan|tra|hoan|duoc|giao|lam|gui|phan\s+hoi|noi)\b"
    r"|\b(?:khong|chua)\s+(?:duoc\s+)?(?:ban\s+giao|tra\s+lai|hoan\s+tra|hoan\s+lai)\b"
    r"|\bchua\b(?=[^.]{0,20}\b(?:tra|hoan|nhan|ky|giao|co)\b)"
    r"|\bkhong\s+co\b|\bchua\s+co\b"
)

_POSITIVE_RE = re.compile(
    r"\b(?:co|da|van\s+con|dang\s+giu|giu)\s+"
    r"(?:sao\s*ke|bien\s*nhan|hop\s*dong|giay|chung\s*tu|tin\s*nhan|bang\s*chung|anh|video)"
    r"|\bda\s+(?:ky|nhan|chuyen|tra|hoan|ban\s+giao|gui)\b"
    r"|\bco\s+(?:sao\s*ke|bien\s*nhan|hop\s*dong|giay)\b"
)


# `landlord_response_status` answers exactly one question: did the landlord
# respond at all? The generic polarity regexes above are slot-agnostic -- they
# list `noi` among the negatable verbs, so "khong noi ro ly do" ("did not give
# a clear reason") reads as a generic negation and would flip this slot to
# "absent". A missing reason is not a missing response, so this slot resolves
# from its own explicit cue sets instead of generic polarity.
#
# These are allowlists, not a Vietnamese negation grammar: evidence that does
# not state a response status either way is rejected, leaving the slot
# untouched. An allowlist is deliberately used in preference to a denylist of
# ambiguous phrases -- "chu nha chua phan hoi, cung khong noi ro ly do" carries
# a genuine no-response cue and must still be accepted.
#
# Every cue below must describe COMMUNICATION status and nothing else. Cues
# about receiving money or property are specifically excluded: "chua nhan lai
# tien coc" and "chu nha nhan tien coc" say nothing about whether the landlord
# replied, so a bare `nhan`/`nhan lai` must never appear here.
_COMMUNICATION_NOUNS = r"(?:phan\s+hoi|tra\s+loi|hoi\s+am|hoi\s+dap)"

_NO_RESPONSE_RE = re.compile(
    # "chua/khong/chang (he) (co) phan hoi|tra loi|hoi am|hoi dap".
    # `chang` is admissible here only because `_has_ambiguous_chang` has already
    # rejected the interrogative and unaccented forms upstream, so a `chang`
    # reaching this pattern provably came from the negation "chẳng".
    rf"\b(?:chua|khong|chang)\s+(?:he\s+)?(?:co\s+)?{_COMMUNICATION_NOUNS}\b"
    rf"|\b(?:chua|khong|chang)\s+nhan\s+duoc\s+{_COMMUNICATION_NOUNS}\b"
    r"|\bkhong\s+lien\s+lac\s+duoc\b|\b(?:chua|khong)\s+lien\s+lac\s+lai\b"
    r"|\bim\s+lang\b|\bmat\s+lien\s+lac\b"
)

# Speech verbs only, and only with `chu nha` immediately before them, so a
# negated form ("chu nha khong noi ro ly do") cannot match by adjacency.
_RESPONDED_RE = re.compile(
    rf"\b(?:da|co)\s+{_COMMUNICATION_NOUNS}\b"
    rf"|\b(?:da|co)\s+nhan\s+duoc\s+{_COMMUNICATION_NOUNS}\b"
    r"|\bchu\s+nha\s+(?:noi|bao|hua|tra\s+loi|phan\s+hoi|hoi\s+am|giai\s+thich|khang\s+dinh)\b"
)

# A positive cue sitting inside a negation is not a response. "chua co phan
# hoi" contains the literal "co phan hoi"; without this guard it would resolve
# `present` -- the exact inverse of what the user said.
# Accent-stripped negators only: khong <- khong, chua <- chua, chang <- chang.
# `chan` is NOT a negator -- it is the stripped form of "chan" ("bored"), which
# occurs in ordinary text ("chan qua, da phan hoi") and would silently suppress
# a genuine response cue inside the left-context window.
_NEGATOR_RE = re.compile(r"\b(?:khong|chua|chang)\b")
_NEGATION_LOOKBEHIND = 16


def _has_unnegated_response_cue(normalized: str) -> bool:
    """True only for a response cue that is not preceded by a negator."""

    for match in _RESPONDED_RE.finditer(normalized):
        prefix = normalized[max(0, match.start() - _NEGATION_LOOKBEHIND): match.start()]
        if not _NEGATOR_RE.search(prefix):
            return True
    return False


# MODE_2D correction round 2 (M-01): `receiving_party_nonperformance_status`
# answers a narrow legal question -- has the receiving party's refusal or
# matured failure to perform the secured obligation been established for
# THIS case, right now -- distinct from and stricter than the generic "is
# the property handed over" / "is the deposit returned" tri-state facts.
#
# Round 1 resolved this from `span.original_quote`, the MODEL-selected
# evidence substring. That is unsafe: the model can select a shorter
# embedded substring ("chủ nhà từ chối giao nhà") from a hypothetical,
# negated, or quoted full message ("Nếu chủ nhà từ chối giao nhà thì tôi
# phải làm gì?"), stripping exactly the framing that should have blocked
# `confirmed`. The model may still PROPOSE this slot via `fact_updates`, but
# the value below is always derived from the COMPLETE current user message
# -- never from the model's selected quote, which is not authoritative input
# for this slot.
#
# Bounded allowlist matching (like `landlord_response_status` above), not a
# general Vietnamese sentiment/refusal classifier: unmatched or ambiguous
# evidence never resolves to `confirmed`.
_ACTOR_RE = r"(?:chu\s+nha|ben\s+cho\s+thue|ben\s+nhan\s+coc)"

# Round 6 (M-01B): CONSERVATIVE POSITIVE EVENT GRAMMAR replaces round 5's
# free-form actor inference.
#
# Round 5 tried to recognize arbitrary Vietnamese actors generically and
# bind the nearest one to each action. Independent verification broke that
# three ways: subjects whose shape the generic detector never matched
# (`đại diện công ty`, `cán bộ quản lý`) were invisible and so borrowed an
# earlier landlord; larger nouns merely CONTAINING a trusted phrase
# (`hiệp hội chủ nhà`, `câu lạc bộ chủ nhà`) were read as the trusted
# subject itself; and `Theo người quen, chủ nhà ...` still confirmed.
#
# Identifying arbitrary actors is the wrong problem to solve. Round 6 stops
# attempting it. Instead a positive event must match one of a small number
# of explicit affirmative TEMPLATES, each anchored so that a trusted
# subject stands at the very START of its own assertion segment. This
# inverts the failure mode: an unrecognized subject is not "an actor we
# failed to classify" but simply text that does not match any template, and
# the message fails closed with no enumeration of untrusted parties at all.
#
# Only these three exact phrases are ever trusted as a subject.
_TRUSTED_SUBJECT_RE = r"(?:chu\s+nha|ben\s+cho\s+thue|ben\s+nhan\s+coc)"

# Bounded object sets. A bare verb with no object never forms an event.
_REFUSAL_OBJECT_RE = (
    r"(?:cho\s+thue|giao\s+nha|ban\s+giao|giao\s+ket|thuc\s+hien|tra\s+nha|tra\s+coc"
    r"|hoan\s+coc|tiep\s+tuc)"
)
_AGREEMENT_OBJECT_RE = r"(?:hop\s+dong|giao\s+dich|thoa\s+thuan)"
_PERFORMANCE_ACTION_RE = (
    r"(?:giao\s+nha|ban\s+giao|giao\s+ket|giao|tra\s+lai\s+coc|tra\s+coc|tra\s+lai|tra"
    r"|hoan\s+tra|hoan|thuc\s+hien)"
)

# Bounded adverbial fillers admitted between subject and verb. Anything not
# listed here breaks adjacency and the template fails -- which is what makes
# "Bên cho thuê căn nhà này hủy thỏa thuận." and "Chủ nhà đồng ý, ... hủy
# thỏa thuận." fail closed without naming the intervening material.
_SUBJECT_VERB_FILLER_RE = r"(?:\s+(?:da|vua|cung|lai|nay|hien|van|roi))*"

# The affirmative structures. Each is anchored with `^` against an assertion
# segment, so the trusted subject must BE the segment's subject rather than
# appear anywhere inside it.
_POSITIVE_EVENT_RES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        # <trusted> (đã|vừa|nhất quyết|kiên quyết)? từ chối <refusal object>
        rf"^{_TRUSTED_SUBJECT_RE}(?:\s+(?:da|vua|cung|nhat\s+quyet|kien\s+quyet))?"
        rf"\s+tu\s+choi\s+(?:tiep\s+tuc\s+)?{_REFUSAL_OBJECT_RE}\b",
        # <trusted> (đã|vừa)? hủy <agreement object>
        rf"^{_TRUSTED_SUBJECT_RE}{_SUBJECT_VERB_FILLER_RE}\s+huy\s+{_AGREEMENT_OBJECT_RE}\b",
        # <trusted> thông báo (rằng)? sẽ (không)? hủy <agreement object>
        rf"^{_TRUSTED_SUBJECT_RE}\s+thong\s+bao(?:\s+rang)?\s+se\s+huy\s+{_AGREEMENT_OBJECT_RE}\b",
        # <trusted> thông báo (rằng)? sẽ không (tiếp tục)? <performance action>
        rf"^{_TRUSTED_SUBJECT_RE}\s+thong\s+bao(?:\s+rang)?\s+se\s+khong"
        rf"(?:\s+tiep\s+tuc)?\s+{_PERFORMANCE_ACTION_RE}\b",
        # <trusted> nói (rằng)? chắc chắn sẽ không (tiếp tục)? <performance action>
        rf"^{_TRUSTED_SUBJECT_RE}\s+noi(?:\s+rang)?\s+chac\s+chan\s+se\s+khong"
        rf"(?:\s+tiep\s+tuc)?\s+{_PERFORMANCE_ACTION_RE}\b",
        # <trusted> (nhất quyết|kiên quyết)? không chịu <performance action>
        rf"^{_TRUSTED_SUBJECT_RE}(?:\s+(?:nhat\s+quyet|kien\s+quyet))?"
        rf"\s+khong\s+chiu(?:\s+tiep\s+tuc)?\s+{_PERFORMANCE_ACTION_RE}\b",
        # <trusted> không cho thuê nữa
        rf"^{_TRUSTED_SUBJECT_RE}\s+khong\s+cho\s+thue\s+nua\b",
    )
)

# Matured (past-deadline) nonperformance has its own narrow template rather
# than any generic binding: the trusted subject must head the segment and be
# the subject of the still-unmet action, and a deadline cue must exist in the
# message. Round 5's generic binding let "Hiệp hội chủ nhà đã quá hạn nhưng
# vẫn chưa giao nhà." confirm.
_MATURED_EVENT_RE = re.compile(
    rf"^{_TRUSTED_SUBJECT_RE}{_SUBJECT_VERB_FILLER_RE}\s+chua\s+{_PERFORMANCE_ACTION_RE}\b"
)

# Assertion-segment boundaries. A trusted subject only ever counts when it
# starts a segment, so every comma, sentence terminator and adversative
# conjunction opens a fresh opportunity -- and closes the previous one.
_ASSERTION_SEGMENT_BOUNDARY_RE = re.compile(
    r"[.!?;\n,]+|\bnhung\b|\btuy\s+nhien\b|\bcon\b|\bsau\s+do\b"
)

# A bounded appositive that merely restates the trusted subject
# ("Chủ nhà, là bên nhận cọc, từ chối ..." / "Chủ nhà — bên nhận cọc — hủy
# ...") is transparent: it is elided before segmentation so it neither
# breaks the segment nor introduces a competing subject. Only appositives
# that are THEMSELVES trusted subjects are elided.
_TRUSTED_APPOSITIVE_RE = re.compile(
    rf",\s*(?:la\s+)?{_TRUSTED_SUBJECT_RE}\s*,"
    rf"|\s*[-–—]\s*(?:la\s+)?{_TRUSTED_SUBJECT_RE}\s*[-–—]\s*"
)

# Attribution: the MARKER makes the statement non-authoritative, so no
# reporting subject is ever enumerated. `theo` is attributive by default;
# only a bounded set of document/agreement objects is exempt, because
# "Theo thỏa thuận đã quá hạn, bên cho thuê vẫn chưa bàn giao nhà." is a
# first-person assertion about the user's own agreement, not a report.
_ATTRIBUTION_DOCUMENT_OBJECT_RE = (
    r"(?:thoa\s+thuan|hop\s+dong|quy\s+dinh|luat|dieu\s+khoan|dieu\s+\d+|khoan\s+\d+"
    r"|lich|ke\s+hoach|bien\s+ban|giay\s+dat\s+coc|cam\s+ket)"
)
_NONPERFORMANCE_ATTRIBUTION_RE = re.compile(
    rf"\btheo\s+(?!{_ATTRIBUTION_DOCUMENT_OBJECT_RE}\b)"
)

_NONPERFORMANCE_ACTOR_NEGATION_RE = re.compile(
    rf"\bkhong\s+phai\s+(?:la\s+)?{_ACTOR_RE}\b"
)

# Bare (no object required): used only to detect the TOPIC and negation,
# since a negated "không từ chối." carries no object at all.
_NONPERFORMANCE_BARE_ACTION_RE = re.compile(
    r"\btu\s+choi\b|\bhuy\b|\bkhong\s+thuc\s+hien\b|\bkhong\s+cho\s+thue\s+nua\b"
)

_NONPERFORMANCE_NEGATOR_RE = re.compile(r"\b(?:khong|chua)\b")
_NONPERFORMANCE_NEGATION_LOOKBEHIND = 20

# "Quá hạn" (deadline passed) alone says nothing about continuing
# nonperformance; it must co-occur with a still-unmet cue AND the correct
# actor in the same message to read as matured nonperformance.
_NONPERFORMANCE_PAST_DEADLINE_RE = re.compile(r"\bqua\s+han\b")
_NONPERFORMANCE_STILL_UNMET_RE = re.compile(
    r"\b(?:chua|khong)\s+(?:giao|tra|hoan|ban\s+giao)\b"
)

# Explicit not-yet-due/temporary-delay evidence must be able to CLEAR a
# previously accepted "confirmed" value (the state-correction requirement),
# so it is its own contrary signal ("not_confirmed"), not merely the absence
# of a confirmed cue.
_NONPERFORMANCE_NOT_YET_DUE_RE = re.compile(
    r"\bchua\s+(?:den|toi)\s+(?:han|ngay|luc)\b"
    r"|\bmoi\s+(?:den|toi)\s+(?:han|ngay|luc)\b"
    r"|\bmoi\s+(?:giao|ban\s+giao|tra|hoan)\b"
    r"|\bxin\s+(?:cham|lui|hoan)\b"
)

_NONPERFORMANCE_HYPOTHETICAL_RE = re.compile(
    r"\bneu\b.{0,40}\bthi\b"
    r"|\bgia\s+su\b"
    r"|\btruong\s+hop\b.{0,40}\bthi\b"
    r"|\bneu\s+nhu\b"
)

_NONPERFORMANCE_UNVERIFIED_RE = re.compile(
    r"\bchua\s+xac\s+minh\b"
    r"|\bchua\s+kiem\s+chung\b"
    r"|\bnghe\s+noi\b"
    r"|\bnghe\s+dau\b"
    r"|\bco\s+nguoi\s+bao\b"
    r"|\bnguoi\s+ta\s+noi\b"
    r"|\btin\s+nhan\s+ghi\b"
)

_NONPERFORMANCE_GENERIC_LEGAL_RE = re.compile(
    r"\bluat\s+quy\s+dinh\b"
    r"|\bphap\s+luat\s+quy\s+dinh\b"
    r"|\bquy\s+dinh\s+tai\b"
    r"|\bdieu\s+\d+\b"
    r"|\bkhoan\s+\d+\b"
)

# Round 3 (M-01, independent reverification): no longer requires "đã" after
# the recency marker. "Chủ nhà từng hủy giao dịch nhưng sau đó hai bên tiếp
# tục hợp đồng." has no "đã" at all and was a confirmed round-2 false
# positive. Broadening this regex is safe in only one direction -- it can
# only ever downgrade a message toward "not_confirmed"/"unknown", never
# toward "confirmed" -- so requiring less here cannot introduce a new false
# positive, only fix false negatives (acceptable) into correct rejections.
_NONPERFORMANCE_PAST_MARKER_RE = r"\btruoc\s+day\b|\btung\b|\bhom\s+qua\b"
_NONPERFORMANCE_RECENCY_MARKER_RE = (
    r"\bhien\s*(?:nay)?\b|\bbay\s+gio\b|\bgio\b|\bsau\s+do\b|\bhom\s+nay\b"
)
_NONPERFORMANCE_HISTORICAL_SUPERSEDED_RE = re.compile(
    rf"(?:{_NONPERFORMANCE_PAST_MARKER_RE}).{{0,100}}(?:{_NONPERFORMANCE_RECENCY_MARKER_RE})"
)

_NONPERFORMANCE_CONTRADICTION_RE = re.compile(
    r"\bchua\s+biet\b|\bkhong\s+chac\b|\bkhong\s+ro\b|\bhay\s+khong\b"
)

# Round 3, widened in round 4 (M-01A): the user is reading, researching,
# quoting or describing material -- an example, an article, a document --
# rather than asserting a fact about their own case. "Tài liệu mô tả chủ nhà
# từ chối bàn giao." must not confirm even though the embedded clause
# matches the positive pattern. These markers are conservative FRAMING
# GUARDS: they are never sufficient to establish anything on their own, they
# only push a message away from `confirmed` toward `unknown` (fail-closed).
_NONPERFORMANCE_EXAMPLE_CONTEXT_RE = re.compile(
    r"\bvi\s+du\b"
    r"|\bbai\s+viet\b"
    r"|\btai\s+lieu\b"
    r"|\bmo\s+ta\b"
    r"|\bdang\s+doc\b"
    r"|\bdang\s+nghien\s+cuu\b"
    r"|\bdang\s+tim\s+hieu\b"
    r"|\btinh\s+huong\s+gia\s+dinh\b"
)

# Round 3, widened in round 4 (M-01A): a question asked BY someone else, or
# quoted/reported rather than asserted -- distinct from the user's own
# hypothetical framing ("nếu... thì"). Round 3 covered only three attributed
# askers and only the "có ... không"/"hay không" question forms, so
# `Bạn tôi hỏi: "Chủ nhà sẽ không giao nhà đúng không?"` slipped through on
# both counts.
_NONPERFORMANCE_ATTRIBUTED_ASKER_RE = (
    r"(?:luat\s+su|nguoi\s+tu\s+van|nguoi\s+khac|ban\s+toi|ban\s+be|nguoi\s+quen|ai\s+do)"
)
# Interrogative tails. Also reused per clause, so a bare unattributed
# question ("Chủ nhà có từ chối giao nhà không?") cannot confirm either.
_NONPERFORMANCE_QUESTION_FORM_RE = (
    r"(?:\bco\b.{0,40}\bkhong\b|\bhay\s+khong\b|\bdung\s+khong\b|\bphai\s+khong\b)"
)
_NONPERFORMANCE_REPORTED_QUESTION_RE = re.compile(
    rf"\b(?:hoi|dat\s+cau\s+hoi|muon\s+biet)\b.{{0,60}}{_NONPERFORMANCE_QUESTION_FORM_RE}"
    rf"|\b{_NONPERFORMANCE_ATTRIBUTED_ASKER_RE}\s+hoi\b"
    r"|\bcau\s+hoi\s+la\b"
)

_NONPERFORMANCE_LOCAL_QUESTION_RE = re.compile(_NONPERFORMANCE_QUESTION_FORM_RE)

# Round 4 (M-01B): clause boundaries. Sentence terminators, PLUS the bounded
# comma+conjunction forms after which a new grammatical subject reliably
# starts. Round 3 split on sentence terminators only, so
# "Chủ nhà đồng ý, nhưng bên môi giới hủy thỏa thuận." kept the landlord and
# the broker's action in one segment and the landlord authorized it.
#
# Deliberately NOT a general comma split: an arbitrary comma routinely sits
# inside a single actor/action phrase ("Chủ nhà, theo tin nhắn tôi nhận
# được, nói sẽ không giao nhà"), and splitting there would destroy the
# attribution rather than protect it. Only these five conjunctions qualify.
_NONPERFORMANCE_CLAUSE_BOUNDARY_RE = re.compile(
    r"[.!?;\n]+"
    r"|,\s*(?=(?:nhung|tuy\s+nhien|sau\s+do|hien|bay\s+gio)\b)"
)


def _nonperformance_split_clauses(normalized: str) -> list[tuple[str, bool]]:
    """Bounded clause segmentation (round 4, M-01B stage 2).

    Returns (clause_text, is_question) pairs. `is_question` records that the
    clause was terminated by `?`, which the split itself would otherwise
    discard -- a quoted or direct question must not license a positive
    reading of the words inside it.
    """

    clauses: list[tuple[str, bool]] = []
    start = 0
    for boundary in _NONPERFORMANCE_CLAUSE_BOUNDARY_RE.finditer(normalized):
        text = normalized[start: boundary.start()].strip()
        if text:
            clauses.append((text, "?" in boundary.group(0)))
        start = boundary.end()
    tail = normalized[start:].strip()
    if tail:
        clauses.append((tail, False))
    return clauses


def _nonperformance_assertion_segments(normalized: str) -> list[str]:
    """Split into assertion segments for the positive event grammar.

    A trusted subject only ever counts when it heads a segment, so every
    comma, sentence terminator and adversative conjunction both closes the
    previous opportunity and opens a fresh one. That single property is what
    makes the grammar safe against subjects nobody enumerated:
    "Chủ nhà đồng ý, <anything at all> hủy thỏa thuận." puts the unknown
    material at the head of its own segment, where it simply is not a
    trusted subject -- no classification of it is needed or attempted.

    A bounded appositive that merely restates the trusted subject
    ("Chủ nhà, là bên nhận cọc, ...") is elided first so it neither breaks
    the segment nor looks like a competing subject.
    """

    collapsed = _TRUSTED_APPOSITIVE_RE.sub(" ", normalized)
    return [
        segment
        for segment in (
            part.strip() for part in _ASSERTION_SEGMENT_BOUNDARY_RE.split(collapsed)
        )
        if segment
    ]


def _nonperformance_positive_event(normalized: str) -> bool:
    """True when some assertion segment matches an explicit affirmative
    template headed by a trusted receiving-party subject (round 6).

    Every template is `^`-anchored against its segment, so a trusted phrase
    appearing anywhere other than the subject position -- inside a larger
    noun (`hiệp hội chủ nhà`), after a reporting subject (`Người quen nói
    chủ nhà ...`), or after an intervening subject (`Chủ nhà đồng ý, đại
    diện công ty ...`) -- cannot form an event.
    """

    matured_available = _NONPERFORMANCE_PAST_DEADLINE_RE.search(normalized) is not None
    for segment in _nonperformance_assertion_segments(normalized):
        if any(pattern.match(segment) for pattern in _POSITIVE_EVENT_RES):
            return True
        # Matured nonperformance additionally requires a deadline cue
        # somewhere in the message; "Chủ nhà chưa giao nhà." alone is a bare
        # current state, not a matured breach.
        if matured_available and _MATURED_EVENT_RE.match(segment):
            return True
    return False


def _nonperformance_classify_clauses(normalized: str) -> tuple[bool, bool]:
    """Return (positive, negated_present).

    Positive evidence now comes solely from the conservative event grammar
    (round 6). Negation detection stays clause-scoped and unchanged, since
    it only ever feeds the CONTRARY side and can never create a `confirmed`.
    """

    positive = False
    negated = False
    for clause, is_question in _nonperformance_split_clauses(normalized):
        for match in _NONPERFORMANCE_BARE_ACTION_RE.finditer(clause):
            prefix = clause[
                max(0, match.start() - _NONPERFORMANCE_NEGATION_LOOKBEHIND): match.start()
            ]
            if _NONPERFORMANCE_NEGATOR_RE.search(prefix):
                negated = True

        if positive:
            continue
        # Local non-factual framing blocks a positive reading of this clause
        # independently of the message-wide gates.
        local_blocked = (
            is_question
            or _NONPERFORMANCE_LOCAL_QUESTION_RE.search(clause) is not None
            or _NONPERFORMANCE_EXAMPLE_CONTEXT_RE.search(clause) is not None
            or '"' in clause
        )
        if not local_blocked and _nonperformance_positive_event(clause):
            positive = True

    return positive, negated


def infer_receiving_party_nonperformance_from_message(message: str) -> str | None:
    """Resolve `receiving_party_nonperformance_status` from the FULL current
    user message -- never from a model-selected evidence quote, which may
    omit the negation, hypothetical framing, or quotation qualifying the
    same words elsewhere in the message (MODE_2D correction round 2, M-01).

    Four distinct outcomes:
      - "confirmed": an explicit, current, correctly-attributed refusal,
        cancellation, stated future non-performance, or matured
        (past-deadline) nonperformance by the receiving party.
      - "not_confirmed": explicit CURRENT evidence against a refusal --
        negation, not-yet-due/temporary-delay evidence, an explicit
        correction of actor attribution, or a historical refusal
        superseded by a later resolution in the same message.
      - "unknown": the message discusses the topic but the evidence is
        hypothetical, unverified/hearsay, generic legal discussion, a
        generic example/educational discussion, a question attributed to
        someone else, internally contradictory, or otherwise inconclusive --
        explicitly persisted so a stale "confirmed" cannot silently survive.
      - None: the message does not discuss receiving-party refusal or
        nonperformance at all -- no_update, the previous value is preserved
        untouched.
    """

    if _has_ambiguous_chang(message):
        return "unknown"

    normalized = _strip_accents(message)

    actor_negated = _NONPERFORMANCE_ACTOR_NEGATION_RE.search(normalized) is not None
    hypothetical = _NONPERFORMANCE_HYPOTHETICAL_RE.search(normalized) is not None
    unverified = _NONPERFORMANCE_UNVERIFIED_RE.search(normalized) is not None
    generic_legal = _NONPERFORMANCE_GENERIC_LEGAL_RE.search(normalized) is not None
    contradictory_marker = _NONPERFORMANCE_CONTRADICTION_RE.search(normalized) is not None
    example_context = _NONPERFORMANCE_EXAMPLE_CONTEXT_RE.search(normalized) is not None
    reported_question = _NONPERFORMANCE_REPORTED_QUESTION_RE.search(normalized) is not None
    historical_superseded = _NONPERFORMANCE_HISTORICAL_SUPERSEDED_RE.search(normalized) is not None
    not_yet_due = _NONPERFORMANCE_NOT_YET_DUE_RE.search(normalized) is not None
    still_unmet = _NONPERFORMANCE_STILL_UNMET_RE.search(normalized) is not None
    bare_action_present = _NONPERFORMANCE_BARE_ACTION_RE.search(normalized) is not None
    # Round 6 (M-01B): positive evidence comes solely from the conservative
    # event grammar -- an explicit affirmative template headed by a trusted
    # receiving-party subject at the start of its own assertion segment.
    positive, action_negated = _nonperformance_classify_clauses(normalized)
    # Round 6 (M-01B): an attribution MARKER makes the whole statement
    # non-authoritative, whatever the reporting subject is, so no reporting
    # subject is ever enumerated ("Theo người quen, chủ nhà đã hủy...").
    attributed = _NONPERFORMANCE_ATTRIBUTION_RE.search(normalized) is not None

    topic_present = any(
        [
            actor_negated,
            not_yet_due,
            still_unmet,
            positive,
            action_negated,
            bare_action_present,
        ]
    )
    if not topic_present:
        return None

    if (
        hypothetical
        or unverified
        or generic_legal
        or contradictory_marker
        or example_context
        or reported_question
        or attributed
    ):
        return "unknown"

    contrary = not_yet_due or action_negated or actor_negated or historical_superseded

    if contrary and positive:
        # Both readings present in the same message -- genuinely ambiguous,
        # but a stale "confirmed" must not silently survive.
        return "unknown"
    if contrary:
        return "not_confirmed"
    if positive:
        return "confirmed"
    # Topic discussed (e.g. a bare "chưa giao nhà" with no timing or
    # refusal evidence) but nothing conclusive either way.
    return "unknown"


def infer_response_status(span_text: str) -> str | None:
    """Resolve `landlord_response_status` from explicit cues only.

    Returns 'absent' or 'present' only when the verified span itself states
    whether the landlord responded. Anything else -- including evidence that
    only says the *reason* was unclear -- returns None so the slot is left
    unchanged rather than inferred from an unrelated absence.
    """

    # Same provenance check as generic polarity, on the original span: an
    # interrogative "chăng" (or an unaccented "chang") settles nothing about
    # whether the landlord made contact, in either direction.
    if _has_ambiguous_chang(span_text):
        return None

    normalized = _strip_accents(span_text)
    says_no_response = _NO_RESPONSE_RE.search(normalized) is not None
    says_responded = _has_unnegated_response_cue(normalized)
    if says_no_response and says_responded:
        # Both readings present in one span -> genuinely ambiguous.
        return None
    if says_no_response:
        return "absent"
    if says_responded:
        return "present"
    return None


def infer_polarity(span_text: str, message: str) -> str | None:
    """Return 'absent', 'present', or None when polarity is not clear enough.

    Looks at a bounded window around the verified span rather than the whole
    message, so a negation elsewhere in a long turn cannot flip an unrelated
    fact.
    """

    # Decided on the original text, before accents are lost. Blocks BOTH
    # directions: an interrogative "chăng" must not yield `absent` via the
    # negation pattern, nor `present` via a positive cue left inside it.
    if _has_ambiguous_chang(span_text):
        return None

    normalized_span = _strip_accents(span_text)
    if _NEGATIVE_RE.search(normalized_span):
        return "absent"
    if _POSITIVE_RE.search(normalized_span):
        return "present"

    # Bounded left-context window: negation in Vietnamese precedes its object.
    normalized_message = _strip_accents(message)
    normalized_target = normalized_span.strip()
    if normalized_target:
        position = normalized_message.find(normalized_target)
        if position != -1:
            start = max(0, position - 24)
            end = position + len(normalized_target)
            # `_strip_accents` maps characters 1:1, so the same offsets address
            # the original text; fall back to the whole message if that ever
            # stops holding, which errs toward blocking rather than inferring.
            original_window = (
                message[start:end] if len(normalized_message) == len(message) else message
            )
            if _has_ambiguous_chang(original_window):
                return None
            window = normalized_message[start:end]
            if _NEGATIVE_RE.search(window):
                return "absent"
            if _POSITIVE_RE.search(window):
                return "present"
    return None


# Reserved machine tokens a model may emit to mean "no value here". They are
# internal placeholders, never something a user or landlord actually said, so
# they must not be persisted as a free-text fact. Deliberately ASCII
# machine-token shapes only: this is not a Vietnamese natural-language denylist,
# and a real reason such as "nhà chưa sửa xong" is unaffected.
RESERVED_SENTINEL_VALUES: frozenset[str] = frozenset(
    {
        "not_stated",
        "not_specified",
        "not_provided",
        "not_given",
        "not_available",
        "not_applicable",
        "unspecified",
        "unknown",
        "undefined",
        "unavailable",
        "none",
        "null",
        "nil",
        "n_a",
        "na",
        "empty",
        "no_reason",
        "no_reason_given",
        "no_value",
        "todo",
        "tbd",
        "placeholder",
    }
)


def is_reserved_sentinel(value: str) -> bool:
    """True when ``value`` is an internal placeholder rather than real content.

    Exact match after a bounded normalization (case-fold, collapse spaces and
    hyphens to underscores, drop surrounding punctuation) so ``"NOT STATED"``,
    ``"not-stated"`` and ``"not_stated."`` are all caught. No fuzzy matching and
    no substring matching -- a genuine reason that merely contains one of these
    words is never rejected.
    """

    token = unicodedata.normalize("NFKC", value).strip().strip(".,;:!?\"'()[]{}").casefold()
    token = re.sub(r"[\s\-/]+", "_", token)
    token = re.sub(r"_+", "_", token).strip("_")
    return token in RESERVED_SENTINEL_VALUES


_CORRECTION_CUES = (
    "noi nham", "nham", "khong phai", "thuc ra", "dinh chinh", "sua lai",
    "sua thanh", "doi thanh", "cho minh sua", "toi nham", "phai la",
)


def has_correction_cue(message: str) -> bool:
    normalized = _strip_accents(message)
    return any(cue in normalized for cue in _CORRECTION_CUES)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class AppliedUpdate:
    slot: str
    operation: str
    value: Any
    original_start: int
    original_end: int
    original_quote: str


@dataclass
class ValidationOutcome:
    state: FastDemoState
    applied: list[AppliedUpdate] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def apply_fact_updates(
    state: FastDemoState,
    proposals: list[FactUpdateProposal],
    current_message: str,
) -> ValidationOutcome:
    """Validate proposals against the current message and return a NEW state.

    The input state is never mutated; the caller commits the returned copy via
    compare-and-swap.
    """

    working = state.model_copy(deep=True)
    outcome = ValidationOutcome(state=working)

    for proposal in proposals:
        slot = (proposal.slot or "").strip()
        if slot not in ALLOWED_SLOTS:
            outcome.rejected.append(f"{slot or '<empty>'}:slot_not_allowed")
            continue
        if proposal.operation not in {"set", "affirm", "negate", "correct", "retract"}:
            outcome.rejected.append(f"{slot}:operation_not_allowed")
            continue

        if proposal.operation == "retract":
            if _retract(working, slot):
                outcome.applied.append(
                    AppliedUpdate(slot, "retract", None, -1, -1, "")
                )
            else:
                outcome.rejected.append(f"{slot}:retract_unsupported")
            continue

        if slot == RECEIVING_PARTY_NONPERFORMANCE_SLOT:
            # MODE_2D correction round 2 (M-01): the model may PROPOSE this
            # slot, but its `evidence_quote` is never the authoritative
            # input -- a model-selected substring can omit the negation,
            # hypothetical framing, or quotation qualifying the same words
            # elsewhere in the message. The value is always derived from the
            # full current message. `None` means "does not discuss this at
            # all" (no_update, previous value preserved); every other
            # outcome, including the explicit string "unknown", is written,
            # so a stale "confirmed" cannot silently survive ambiguous or
            # contrary evidence.
            result = infer_receiving_party_nonperformance_from_message(current_message)
            if result is None:
                outcome.rejected.append(f"{slot}:no_update")
                continue
            if not _write(working, slot, result, proposal.operation):
                outcome.rejected.append(f"{slot}:write_rejected")
                continue
            outcome.applied.append(
                AppliedUpdate(
                    slot=slot,
                    operation=proposal.operation,
                    value=result,
                    original_start=-1,
                    original_end=-1,
                    # Diagnostic/audit only -- never re-derived from this.
                    original_quote=(proposal.evidence_quote or "")[:200],
                )
            )
            continue

        spans, _ = locate_quote(proposal.evidence_quote, current_message)
        if not spans:
            outcome.rejected.append(f"{slot}:evidence_not_found")
            continue

        resolved = _resolve_value(slot, proposal, spans, current_message)
        if resolved is None:
            outcome.rejected.append(f"{slot}:value_invalid_or_ambiguous")
            continue
        value, span = resolved

        if not _write(working, slot, value, proposal.operation):
            outcome.rejected.append(f"{slot}:write_rejected")
            continue
        outcome.applied.append(
            AppliedUpdate(
                slot=slot,
                operation=proposal.operation,
                value=value,
                original_start=span.original_start,
                original_end=span.original_end,
                original_quote=span.original_quote,
            )
        )

    return outcome


def _resolve_value(
    slot: str,
    proposal: FactUpdateProposal,
    spans: list[VerifiedSpan],
    message: str,
) -> tuple[Any, VerifiedSpan] | None:
    """Derive the accepted value from the verified span. Ambiguity -> None."""

    if slot == "deposit_amount":
        candidates: list[tuple[int, VerifiedSpan]] = []
        for span in spans:
            parsed = parse_amount_from_text(span.original_quote)
            if parsed is None:
                # Fall back to a bounded window around the span so a quote like
                # "số tiền là 15 triệu" still resolves when the digits sit just
                # outside the matched text.
                window = message[max(0, span.original_start - 12): span.original_end + 24]
                parsed = parse_amount_from_text(window)
            if parsed is not None:
                candidates.append((parsed, span))
        if not candidates:
            return None
        distinct = {value for value, _ in candidates}
        if len(distinct) != 1:
            # Multiple matches producing different values -> reject.
            return None
        return candidates[0]

    if slot == "landlord_response_status":
        # Scoped ahead of the generic tri-state path: this slot must never be
        # derived from generic negation, and must never fall back to the
        # model's stated operation. A model that asserts operation="negate"
        # while quoting "khong noi ro ly do" is exactly the inference being
        # prevented, so unexplicit evidence rejects and the slot stays as it is.
        statuses: list[tuple[str, VerifiedSpan]] = []
        for span in spans:
            status = infer_response_status(span.original_quote)
            if status is not None:
                statuses.append((status, span))
        if not statuses:
            return None
        if len({status for status, _ in statuses}) != 1:
            return None
        return statuses[0]

    if slot in TRI_STATE_SLOTS:
        polarities: list[tuple[str, VerifiedSpan]] = []
        for span in spans:
            polarity = infer_polarity(span.original_quote, message)
            if polarity is not None:
                polarities.append((polarity, span))
        if not polarities:
            # Fall back to the model's stated operation ONLY when it is
            # explicitly directional; a bare "set" with unclear polarity is
            # rejected so a mere mention never flips unknown.
            if proposal.operation == "affirm":
                return "present", spans[0]
            if proposal.operation == "negate":
                return "absent", spans[0]
            return None
        distinct = {polarity for polarity, _ in polarities}
        if len(distinct) != 1:
            return None
        return polarities[0]

    if slot == "payment_evidence_types":
        raw = proposal.value
        values = raw if isinstance(raw, list) else [raw]
        cleaned = [str(v).strip().lower() for v in values if isinstance(v, (str, int))]
        allowed = [v for v in cleaned if v in ALLOWED_EVIDENCE_TYPES]
        if not allowed:
            return None
        return allowed, spans[0]

    if slot == "user_goal":
        value = str(proposal.value or "").strip().lower()
        if value not in ALLOWED_USER_GOALS:
            return None
        return value, spans[0]

    if slot == "deposit_currency":
        value = str(proposal.value or "").strip().upper()
        # VND is a backend demo default; only accept it when the user said it.
        if value != "VND":
            return None
        return value, spans[0]

    if slot == "landlord_refusal_reason":
        value = str(proposal.value or "").strip()
        if not value or len(value) > 200:
            return None
        # This is the only free-text fact slot, so it is the only place a model
        # can pass an internal placeholder off as a real user fact. A sentinel
        # such as "not_stated" is not a reason the landlord gave -- accepting it
        # would persist a machine token as testimony. Reject it here so the slot
        # stays None (no reason recorded); "the landlord gave no reason" is
        # carried by landlord_response_status, which is tri-state.
        if is_reserved_sentinel(value):
            return None
        return value, spans[0]

    return None


def _write(state: FastDemoState, slot: str, value: Any, operation: str) -> bool:
    facts = state.facts
    if slot == "deposit_amount":
        previous = facts.deposit_amount
        if previous is not None and previous.value != value:
            state.previous_values.setdefault("deposit_amount", []).append(
                {"value": previous.value, "currency": previous.currency}
            )
            # Keep the correction history bounded; this is a demo, not a ledger.
            state.previous_values["deposit_amount"] = state.previous_values["deposit_amount"][-5:]
        facts.deposit_amount = DepositAmount(
            value=int(value), currency="VND", status="present", original_quote=""
        )
        return True
    if slot in TRI_STATE_SLOTS or slot == RECEIVING_PARTY_NONPERFORMANCE_SLOT:
        setattr(facts, slot, value)
        return True
    if slot == "payment_evidence_types":
        merged = list(dict.fromkeys([*facts.payment_evidence_types, *value]))
        facts.payment_evidence_types = merged[:5]
        return True
    if slot == "user_goal":
        state.user_goal = value
        return True
    if slot == "deposit_currency":
        facts.deposit_currency = value
        return True
    if slot == "landlord_refusal_reason":
        facts.landlord_refusal_reason = value
        return True
    return False


def _retract(state: FastDemoState, slot: str) -> bool:
    facts = state.facts
    if slot == "deposit_amount":
        facts.deposit_amount = None
        return True
    if slot in TRI_STATE_SLOTS or slot == RECEIVING_PARTY_NONPERFORMANCE_SLOT:
        setattr(facts, slot, "unknown")
        return True
    if slot == "payment_evidence_types":
        facts.payment_evidence_types = []
        return True
    if slot == "landlord_refusal_reason":
        facts.landlord_refusal_reason = None
        return True
    if slot == "user_goal":
        state.user_goal = None
        return True
    return False


__all__ = [
    "AppliedUpdate",
    "ValidationOutcome",
    "VerifiedSpan",
    "apply_fact_updates",
    "has_correction_cue",
    "infer_polarity",
    "infer_receiving_party_nonperformance_from_message",
    "locate_quote",
    "normalize_with_map",
    "parse_amount_from_text",
]
