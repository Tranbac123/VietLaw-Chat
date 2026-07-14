from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend_lite.app.contracts.internal import (
    AnswerDraft,
    AnswerPlan,
    GuidancePoint,
    RequestStatus,
    StageTrace,
    VersionStamps,
    is_valid_transition,
    validate_transition,
)


def test_status_transition_matrix_is_exact() -> None:
    assert is_valid_transition(RequestStatus.RECEIVED, RequestStatus.PROCESSING)
    assert is_valid_transition(RequestStatus.PROCESSING, RequestStatus.COMPLETE)
    assert is_valid_transition(RequestStatus.PROCESSING, RequestStatus.FAILED_RETRYABLE)
    assert is_valid_transition(RequestStatus.PROCESSING, RequestStatus.FAILED_FINAL)
    assert is_valid_transition(RequestStatus.FAILED_RETRYABLE, RequestStatus.PROCESSING)
    assert not is_valid_transition(RequestStatus.COMPLETE, RequestStatus.PROCESSING)
    with pytest.raises(ValueError, match="invalid request status transition"):
        validate_transition(RequestStatus.COMPLETE, RequestStatus.PROCESSING)


def test_strict_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        GuidancePoint(point_id="p1", canonical_text="text", strength="informational", extra=True)
    with pytest.raises(ValidationError):
        AnswerDraft(rendered_points=[], domain="traffic")


def test_plan_keeps_stable_ids_required_ids_and_order() -> None:
    plan = AnswerPlan(
        points=[
            GuidancePoint(point_id="p1", canonical_text="One", strength="informational"),
            GuidancePoint(point_id="p2", canonical_text="Two", strength="strong", supporting_source_ids=["s1"]),
        ],
        required_point_ids=["p2"],
        slot_order=["p1", "p2"],
    )
    assert [point.point_id for point in plan.points] == ["p1", "p2"]
    with pytest.raises(ValidationError):
        AnswerPlan(
            points=[GuidancePoint(point_id="p1", canonical_text="One", strength="informational")],
            required_point_ids=["missing"],
        )


def test_stage_trace_is_redacted_and_timezone_aware() -> None:
    trace = StageTrace(
        stage="SAFETY",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        duration_ms=1000,
        status="completed",
        input_summary_redacted={"matched": 1},
        output_summary_redacted={"safe": True},
    )
    assert trace.error_code is None
    with pytest.raises(ValidationError):
        StageTrace(
            stage="SAFETY",
            started_at=datetime(2026, 1, 1),
            finished_at=datetime(2026, 1, 1, 0, 0, 1),
            duration_ms=1,
            status="completed",
        )


def test_gate_a_version_defaults_are_deterministic() -> None:
    stamps = VersionStamps(
        corpus_version="corpus-v1",
        policy_version="policy-v1",
        retriever_version="lexical-v1",
        generator_version="renderer-v1",
    )
    assert stamps.prompt_version == "none"
    assert stamps.generator_mode == "deterministic"
