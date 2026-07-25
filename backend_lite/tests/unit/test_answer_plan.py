import pytest

from backend_lite.app.application.analysis_state import AnalysisInvariantError, DecisionRecord, EvidenceResult
from backend_lite.app.application.answer_plan import build_answer_plan, validate_point_id


@pytest.mark.parametrize(("decision", "required_field"), [("answer_with_guidance", "next_steps"), ("ask_clarifying_questions", "clarifying_questions"), ("recommend_professional_help", "escalation_notice"), ("refuse_unsafe_request", "safe_alternative"), ("unsupported", "summary")])
def test_answer_plan_has_required_shape_for_every_decision(decision: str, required_field: str) -> None:
    record = DecisionRecord("civil_dispute", "low", decision, (), True, False)  # type: ignore[arg-type]
    plan = build_answer_plan(record, EvidenceResult((), ()))
    assert plan.summary and getattr(plan, required_field)
    assert all(point.point_id.endswith(".v1") for point in plan.ordered_points)


def test_malformed_stable_point_id_fails_loud() -> None:
    with pytest.raises(AnalysisInvariantError):
        validate_point_id("Random UUID Or Wording")
