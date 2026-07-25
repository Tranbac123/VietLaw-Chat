from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend_lite.app.contracts.internal import (
    RequestIdentity,
    StageTrace,
    VersionStamps,
)
from backend_lite.app.contracts.state import AnalysisState
from backend_lite.app.contracts.internal import RawInput
from backend_lite.app.application.analysis_state import AnalysisInvariantError
from backend_lite.app.application.deterministic_pipeline import (
    run_deterministic_analysis,
    state_without_final_stage,
    validate_final_state,
)
from backend_lite.app.application.normalization import normalize_question
from backend_lite.tests.unit.test_deterministic_pipeline import analysis_input


def _identity() -> RequestIdentity:
    return RequestIdentity(
        session_id="session_1",
        request_id="req_1",
        request_fingerprint="0" * 64,
    )


def _versions() -> VersionStamps:
    return VersionStamps(
        corpus_version="corpus-v1",
        policy_version="policy-v1",
        retriever_version="lexical-v1",
        generator_version="renderer-v1",
    )


def test_analysis_state_has_required_fields_and_safe_trace_default() -> None:
    first = AnalysisState(
        request_identity=_identity(),
        raw_input=RawInput(session_id="session_1", question="Câu hỏi"),
        version_stamps=_versions(),
    )
    second = AnalysisState(
        request_identity=_identity(),
        raw_input=RawInput(session_id="session_1", question="Câu hỏi"),
        version_stamps=_versions(),
    )
    first.trace.append(
        StageTrace(
            stage="ACTIVATE_STATE",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            duration_ms=1,
            status="completed",
        )
    )
    assert len(first.trace) == 1
    assert second.trace == []
    assert second.trace is not first.trace


def test_analysis_state_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AnalysisState(
            request_identity=_identity(),
            raw_input=RawInput(session_id="session_1", question="Câu hỏi"),
            version_stamps=_versions(),
            unexpected="not allowed",
        )


def test_trace_is_a_direct_top_level_list() -> None:
    assert AnalysisState.model_fields["trace"].annotation == list[StageTrace]
    assert "trace" not in RequestIdentity.model_fields


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Xin   chào  ", "Xin chào"),
        ("Dòng một\n\nDòng hai", "Dòng một Dòng hai"),
        ("Tiếng Việt có dấu!", "Tiếng Việt có dấu!"),
        ("Giữ dấu câu: đúng không?", "Giữ dấu câu: đúng không?"),
    ],
)
def test_a3a_normalization_is_unicode_aware_and_idempotent(raw: str, expected: str) -> None:
    assert normalize_question(raw) == expected
    assert normalize_question(normalize_question(raw)) == expected


def test_a3a_normalization_rejects_blank_and_kernel_state_is_frozen() -> None:
    with pytest.raises(AnalysisInvariantError):
        normalize_question(" \n\t ")
    state = run_deterministic_analysis(analysis_input())
    with pytest.raises(AttributeError):
        state.normalized_question = "mutated"  # type: ignore[misc]


def test_a3a_final_validator_fails_loud_for_missing_stage() -> None:
    state = run_deterministic_analysis(analysis_input())
    with pytest.raises(AnalysisInvariantError, match="stages"):
        validate_final_state(state_without_final_stage(state), state.original_input)
