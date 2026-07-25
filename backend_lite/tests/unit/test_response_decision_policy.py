import pytest

from backend_lite.app.application.analysis_state import (
    DomainAssessment,
    EvidencePlan,
    EvidenceResult,
    FactCompleteness,
    SafetyAssessment,
)
from backend_lite.app.application.response_decision_policy import decide_response


@pytest.mark.parametrize(("domain", "safety", "evidence", "expected"), [
    (DomainAssessment("high_risk", "supported", True, ()), SafetyAssessment("high", ("HARM_EVASION",), True, True, ("safety.evasion.v1",), ("HARM_EVASION",), "DIRECT_HARM_ASSISTANCE"), False, "refuse_unsafe_request"),
    (DomainAssessment("high_risk", "supported", True, ()), SafetyAssessment("high", ("RISK_POLICE_CONTACT",), False, True, ("risk.police_contact.v1",), ("RISK_POLICE_CONTACT",), "LAWFUL_COMPLIANCE"), False, "recommend_professional_help"),
    (DomainAssessment("civil_dispute", "supported", False, ()), SafetyAssessment("low", (), False, False, (), ()), False, "ask_clarifying_questions"),
    (DomainAssessment("civil_dispute", "supported", True, ()), SafetyAssessment("low", (), False, False, (), ()), True, "answer_with_guidance"),
    (DomainAssessment("unknown", "unsupported", False, ()), SafetyAssessment("low", (), False, False, (), ()), False, "unsupported"),
])
def test_complete_decision_table_has_one_explicit_outcome(domain: DomainAssessment, safety: SafetyAssessment, evidence: bool, expected: str) -> None:
    facts = FactCompleteness(domain.facts_sufficient, () if domain.facts_sufficient else ("FACTS_INCOMPLETE",))
    plan = EvidencePlan(
        ("approved_legal_evidence",) if domain.facts_sufficient else (),
        (),
        domain.status != "unsupported" and domain.facts_sufficient,
        domain.status != "unsupported" and domain.facts_sufficient,
        "high_risk" if safety.high_risk else domain.domain,
        3 if domain.status != "unsupported" and domain.facts_sufficient else 0,
        ("test.evidence.plan.v1",),
    )
    admitted = ()
    if evidence:
        from backend_lite.tests.unit.test_deterministic_pipeline import candidate

        admitted = (candidate(domain=plan.compatible_domain),)
    result = decide_response(domain, safety, facts, plan, EvidenceResult(admitted, ()))
    assert result.decision == expected and result.reason_codes


def test_supported_complete_flow_without_admitted_evidence_is_unsupported() -> None:
    domain = DomainAssessment("civil_dispute", "supported", True, ())
    safety = SafetyAssessment("low", (), False, False, (), ())
    facts = FactCompleteness(True, ())
    plan = EvidencePlan(("approved_legal_evidence",), (), True, True, "civil_dispute", 3, ("test.evidence.plan.v1",))
    result = decide_response(domain, safety, facts, plan, EvidenceResult((), ()))
    assert result.decision == "unsupported"
    assert "EVIDENCE_INSUFFICIENT" in result.reason_codes
