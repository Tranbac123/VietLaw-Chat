"""Deterministic fail-closed validation for untrusted model output."""

from __future__ import annotations

import json
from math import isfinite
import unicodedata
from typing import Any

from .contract import (
    ACTOR_ORIENTATIONS,
    HARM_FAMILIES,
    INTENT_MODES,
    RATIONALE_CODES,
    RISK_INDICATORS,
    SCHEMA_VERSION,
    SPAN_ROLES,
    SafetyClassificationCandidate,
    SupportingSpan,
)

_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "intent_mode",
        "harm_families",
        "actor_orientation",
        "action_target_summary",
        "risk_indicators",
        "supporting_spans",
        "confidence",
        "abstain",
        "rationale_codes",
    }
)
_SPAN_FIELDS = frozenset({"start", "end", "text", "role", "harm_family"})
_FAMILY_SPAN_ROLES = frozenset({"ACTION", "TARGET", "USER_APPLICATION"})


class ClassifierValidationError(ValueError):
    """A redacted, stable classifier validation failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def normalize_current_question(value: str) -> str:
    if not isinstance(value, str):
        raise ClassifierValidationError("CLASSIFIER_INPUT_INVALID")
    normalized = unicodedata.normalize("NFC", " ".join(value.split()))
    if not normalized or len(normalized) > 4_000:
        raise ClassifierValidationError("CLASSIFIER_INPUT_INVALID")
    return normalized


def _reject_constant(_: str) -> None:
    raise ClassifierValidationError("CLASSIFIER_NUMBER_INVALID")


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClassifierValidationError("CLASSIFIER_DUPLICATE_FIELD")
        result[key] = value
    return result


def _parse(payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if not isinstance(payload, (str, bytes)) or not payload:
        raise ClassifierValidationError("CLASSIFIER_EMPTY_RESPONSE")
    try:
        value = json.loads(
            payload,
            parse_constant=_reject_constant,
            object_pairs_hook=_object_no_duplicates,
        )
    except ClassifierValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClassifierValidationError("CLASSIFIER_MALFORMED_JSON") from exc
    if not isinstance(value, dict):
        raise ClassifierValidationError("CLASSIFIER_SCHEMA_INVALID")
    return value


def _exact_fields(value: dict[str, Any], expected: frozenset[str]) -> None:
    if frozenset(value) != expected:
        raise ClassifierValidationError("CLASSIFIER_SCHEMA_FIELDS_INVALID")


def _closed_string(value: Any, allowed: tuple[str, ...], code: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ClassifierValidationError(code)
    return value


def _closed_array(
    value: Any,
    allowed: tuple[str, ...],
    *,
    maximum: int,
    code: str,
) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ClassifierValidationError(code)
    if any(not isinstance(item, str) or item not in allowed for item in value):
        raise ClassifierValidationError(code)
    if len(value) != len(set(value)):
        raise ClassifierValidationError(code)
    return tuple(item for item in allowed if item in value)


def _spans(value: Any, question: str) -> tuple[SupportingSpan, ...]:
    if not isinstance(value, list) or len(value) > 16:
        raise ClassifierValidationError("CLASSIFIER_SPANS_INVALID")
    spans: list[SupportingSpan] = []
    signatures: set[tuple[object, ...]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ClassifierValidationError("CLASSIFIER_SPAN_INVALID")
        _exact_fields(raw, _SPAN_FIELDS)
        start, end, text = raw["start"], raw["end"], raw["text"]
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or not 0 <= start < end <= len(question)
            or not isinstance(text, str)
            or question[start:end] != text
            or not text.strip()
        ):
            raise ClassifierValidationError("CLASSIFIER_SPAN_NOT_IN_QUESTION")
        role = _closed_string(
            raw["role"], SPAN_ROLES, "CLASSIFIER_SPAN_ROLE_INVALID"
        )
        family_raw = raw["harm_family"]
        family = None
        if family_raw is not None:
            family = _closed_string(
                family_raw,
                HARM_FAMILIES,
                "CLASSIFIER_HARM_FAMILY_INVALID",
            )
        if (role in _FAMILY_SPAN_ROLES) != (family is not None):
            raise ClassifierValidationError("CLASSIFIER_SPAN_FAMILY_INVALID")
        signature = (start, end, text, role, family)
        if signature in signatures:
            raise ClassifierValidationError("CLASSIFIER_SPANS_INVALID")
        signatures.add(signature)
        spans.append(SupportingSpan(start, end, text, role, family))  # type: ignore[arg-type]
    return tuple(
        sorted(
            spans,
            key=lambda span: (
                span.start,
                span.end,
                SPAN_ROLES.index(span.role),
                HARM_FAMILIES.index(span.harm_family)
                if span.harm_family is not None
                else len(HARM_FAMILIES),
            ),
        )
    )


def validate_candidate(
    payload: str | bytes | dict[str, Any],
    current_question: str,
) -> SafetyClassificationCandidate:
    """Return a canonical signal object or one redacted validation error."""

    question = normalize_current_question(current_question)
    raw = _parse(payload)
    _exact_fields(raw, _ROOT_FIELDS)
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ClassifierValidationError("CLASSIFIER_SCHEMA_VERSION_INVALID")
    intent = _closed_string(
        raw["intent_mode"], INTENT_MODES, "CLASSIFIER_INTENT_INVALID"
    )
    harms = _closed_array(
        raw["harm_families"],
        HARM_FAMILIES,
        maximum=len(HARM_FAMILIES),
        code="CLASSIFIER_HARM_FAMILY_INVALID",
    )
    actor = _closed_string(
        raw["actor_orientation"],
        ACTOR_ORIENTATIONS,
        "CLASSIFIER_ACTOR_INVALID",
    )
    summary = raw["action_target_summary"]
    if (
        not isinstance(summary, str)
        or not 1 <= len(summary.strip()) <= 160
        or any(ord(character) < 32 for character in summary)
    ):
        raise ClassifierValidationError("CLASSIFIER_SUMMARY_INVALID")
    risks = _closed_array(
        raw["risk_indicators"],
        RISK_INDICATORS,
        maximum=len(RISK_INDICATORS),
        code="CLASSIFIER_RISK_INVALID",
    )
    spans = _spans(raw["supporting_spans"], question)
    confidence = raw["confidence"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not isfinite(float(confidence))
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise ClassifierValidationError("CLASSIFIER_CONFIDENCE_INVALID")
    abstain = raw["abstain"]
    if not isinstance(abstain, bool):
        raise ClassifierValidationError("CLASSIFIER_ABSTAIN_INVALID")
    rationale = _closed_array(
        raw["rationale_codes"],
        RATIONALE_CODES,
        maximum=len(RATIONALE_CODES),
        code="CLASSIFIER_RATIONALE_INVALID",
    )

    span_families = {span.harm_family for span in spans if span.harm_family}
    if span_families - set(harms):
        raise ClassifierValidationError("CLASSIFIER_SPAN_FAMILY_INVALID")
    for family in harms:
        family_roles = {
            span.role for span in spans if span.harm_family == family
        }
        if not {"ACTION", "TARGET"}.issubset(family_roles):
            raise ClassifierValidationError("CLASSIFIER_HARM_SUPPORT_INVALID")
    if intent == "DIRECT_HARM_ASSISTANCE":
        if (
            not harms
            or actor != "USER"
            or abstain
            or not any(span.role == "USER_APPLICATION" for span in spans)
        ):
            raise ClassifierValidationError("CLASSIFIER_DIRECT_LINK_INVALID")
    if intent == "VICTIM_OR_REPORTING" and (
        actor not in {"THIRD_PARTY", "VICTIM_USER"}
        or any(span.role == "USER_APPLICATION" for span in spans)
    ):
        raise ClassifierValidationError("CLASSIFIER_VICTIM_ACTOR_INVALID")
    if abstain and (
        intent not in {"AMBIGUOUS", "NEUTRAL"} or float(confidence) > 0.5
    ):
        raise ClassifierValidationError("CLASSIFIER_ABSTAIN_CONFLICT")
    if intent == "AMBIGUOUS" and (not abstain or risks):
        raise ClassifierValidationError("CLASSIFIER_AMBIGUITY_CONFLICT")
    if intent == "NEUTRAL" and (harms or risks):
        raise ClassifierValidationError("CLASSIFIER_NEUTRAL_CONFLICT")

    return SafetyClassificationCandidate(
        SCHEMA_VERSION,
        intent,  # type: ignore[arg-type]
        harms,  # type: ignore[arg-type]
        actor,  # type: ignore[arg-type]
        summary.strip(),
        risks,  # type: ignore[arg-type]
        spans,
        float(confidence),
        abstain,
        rationale,  # type: ignore[arg-type]
    )


__all__ = [
    "ClassifierValidationError",
    "normalize_current_question",
    "validate_candidate",
]
