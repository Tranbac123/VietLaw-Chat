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
