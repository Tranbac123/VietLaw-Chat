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
    r"\b(?:khong|chua|chang|chan)\s+(?:co|ky|nhan|tra|hoan|duoc|giao|lam|gui|phan\s+hoi|noi)\b"
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
    # "chua/khong (he) (co) phan hoi|tra loi|hoi am|hoi dap"
    rf"\b(?:chua|khong)\s+(?:he\s+)?(?:co\s+)?{_COMMUNICATION_NOUNS}\b"
    rf"|\b(?:chua|khong)\s+nhan\s+duoc\s+{_COMMUNICATION_NOUNS}\b"
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
_NEGATOR_RE = re.compile(r"\b(?:khong|chua|chang|chan)\b")
_NEGATION_LOOKBEHIND = 16


def _has_unnegated_response_cue(normalized: str) -> bool:
    """True only for a response cue that is not preceded by a negator."""

    for match in _RESPONDED_RE.finditer(normalized):
        prefix = normalized[max(0, match.start() - _NEGATION_LOOKBEHIND): match.start()]
        if not _NEGATOR_RE.search(prefix):
            return True
    return False


def infer_response_status(span_text: str) -> str | None:
    """Resolve `landlord_response_status` from explicit cues only.

    Returns 'absent' or 'present' only when the verified span itself states
    whether the landlord responded. Anything else -- including evidence that
    only says the *reason* was unclear -- returns None so the slot is left
    unchanged rather than inferred from an unrelated absence.
    """

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
            window = normalized_message[max(0, position - 24): position + len(normalized_target)]
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
    if slot in TRI_STATE_SLOTS:
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
    if slot in TRI_STATE_SLOTS:
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
    "locate_quote",
    "normalize_with_map",
    "parse_amount_from_text",
]
