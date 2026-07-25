from backend_lite.app.application.analysis_state import (
    DomainAssessment,
    FactCompleteness,
    SafetyAssessment,
)
from backend_lite.app.application.evidence_policy import admit_evidence, create_evidence_plan
from backend_lite.tests.unit.test_deterministic_pipeline import candidate


def _plan(*, domain: str = "civil_dispute", supported: bool = True, complete: bool = True, unsafe: bool = False):
    assessment = DomainAssessment(domain, "supported" if supported else "unsupported", complete, ())  # type: ignore[arg-type]
    safety = (
        SafetyAssessment(
            "high",
            ("HARM_EVASION",),
            True,
            False,
            ("safety.evasion.v1",),
            ("HARM_EVASION",),
            "DIRECT_HARM_ASSISTANCE",
        )
        if unsafe
        else SafetyAssessment("low", (), False, False, (), ())
    )
    return create_evidence_plan(assessment, safety, FactCompleteness(complete, () if complete else ("FACTS_INCOMPLETE",)))


def test_guard_admits_only_approved_relevant_matching_domain() -> None:
    approved = candidate()
    unapproved = candidate("source.unapproved", approved=False)
    wrong = candidate("source.wrong", domain="traffic")
    internal = candidate("source.policy", source_type="safety_policy")
    result = admit_evidence((wrong, approved, internal, unapproved), _plan(), "Tôi đã đặt cọc thuê nhà")
    assert result.admitted == (approved,)
    assert {item.reason_code for item in result.rejected} == {"EVIDENCE_NOT_APPROVED", "EVIDENCE_WRONG_DOMAIN", "EVIDENCE_INTERNAL_POLICY_NOT_LEGAL_SOURCE"}


def test_conflicting_duplicate_ids_fail_closed_and_are_order_independent() -> None:
    first, duplicate = candidate("source.duplicate", score=0.9), candidate("source.duplicate", score=0.8)
    left = admit_evidence((duplicate, first), _plan(), "đặt cọc")
    right = admit_evidence((first, duplicate), _plan(), "đặt cọc")
    assert left == right and left.admitted == ()
    assert {item.reason_code for item in left.rejected} == {"DUPLICATE_ID_CONFLICT"}


def test_exact_duplicate_is_collapsed_without_conflict() -> None:
    first = candidate("source.duplicate")
    result = admit_evidence((first, first), _plan(), "đặt cọc")
    assert result.admitted == (first,)
    assert result.rejected[0].reason_code == "EVIDENCE_EXACT_DUPLICATE"


def test_refusal_and_unsupported_never_admit_sources() -> None:
    plans = (
        _plan(domain="high_risk", unsafe=True),
        _plan(domain="unknown", supported=False, complete=False),
    )
    for plan in plans:
        result = admit_evidence((candidate(domain=plan.compatible_domain),), plan, "đặt cọc")
        assert result.admitted == ()
        assert result.rejected[0].reason_code == "EVIDENCE_PLAN_DISALLOWS_SOURCES"
