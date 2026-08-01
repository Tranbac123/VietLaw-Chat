"""Regression coverage for the live FAST DEMO V2 schema-conformance defects."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend_lite.app.contracts.fast_demo import FastDemoPlan
from backend_lite.app.services.fast_demo_prompt import SYSTEM_PROMPT


def canonical_skeleton() -> dict:
    """Mechanically decode the canonical JSON object embedded in the prompt."""

    marker_offset = SYSTEM_PROMPT.index("KHUNG JSON CHUẨN")
    object_offset = SYSTEM_PROMPT.index("{", marker_offset)
    payload, _ = json.JSONDecoder().raw_decode(SYSTEM_PROMPT[object_offset:])
    return payload


def validation_error(payload: dict) -> ValidationError:
    with pytest.raises(ValidationError) as raised:
        FastDemoPlan.model_validate(payload)
    return raised.value


def assert_error(error: ValidationError, *, kind: str, location: tuple[object, ...]) -> None:
    matching = [item for item in error.errors() if tuple(item["loc"]) == location]
    assert matching, error.errors()
    assert matching[0]["type"] == kind


def test_analysis_note_is_rejected_as_an_extra_field() -> None:
    payload = canonical_skeleton()
    payload["analysis_note"] = "ghi chú không hợp lệ"

    error = validation_error(payload)

    assert_error(error, kind="extra_forbidden", location=("analysis_note",))


def test_checklist_string_is_rejected_as_the_wrong_type() -> None:
    payload = canonical_skeleton()
    payload["checklist"] = "một chuỗi thay vì mảng"

    error = validation_error(payload)

    assert_error(error, kind="list_type", location=("checklist",))


def test_checklist_object_element_is_rejected_as_the_wrong_type() -> None:
    payload = canonical_skeleton()
    payload["checklist"] = [{"text": "một mục"}]

    error = validation_error(payload)

    assert_error(error, kind="string_type", location=("checklist", 0))


def test_prompt_skeleton_has_the_exact_fast_demo_plan_keyset_and_validates() -> None:
    payload = canonical_skeleton()

    assert set(payload) == set(FastDemoPlan.model_fields)
    assert isinstance(payload["checklist"], list)
    assert payload["analysis"] is None or isinstance(payload["analysis"], str)
    assert "analysis_note" not in payload
    assert FastDemoPlan.model_validate(payload).model_dump() == payload


def test_prompt_explicitly_prohibits_the_two_live_failure_shapes() -> None:
    prompt = SYSTEM_PROMPT.lower()

    assert "analysis_note" in prompt
    assert 'trong trường "analysis"' in prompt
    assert '"checklist"' in prompt
    assert "luôn luôn là mảng" in prompt
    assert "không bao giờ là một chuỗi" in prompt
    assert "không thêm không bớt khóa" in prompt
