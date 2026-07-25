from backend_lite.app.application.analysis_state import DecisionRecord, DomainAssessment, EvidenceResult, ResolvedContext, SafetyAssessment
from backend_lite.app.application.confidence import calculate_confidence


def test_confidence_is_deterministic_bounded_and_explained() -> None:
    inputs = (DomainAssessment("civil_dispute", "supported", True, ()), SafetyAssessment("low", (), False, False, (), ()), DecisionRecord("civil_dispute", "low", "answer_with_guidance", (), True, True), EvidenceResult((), ()), ResolvedContext((), (), (), ()))
    first = calculate_confidence(*inputs)
    assert first == calculate_confidence(*inputs)
    assert all(0 <= value < 1 for value in (first.domain, first.risk, first.answer)) and first.factors


def test_ambiguity_and_conflict_reduce_diagnostic_confidence() -> None:
    domain = DomainAssessment("unknown", "ambiguous", False, ())
    safety = SafetyAssessment(
        "medium",
        (),
        False,
        False,
        (),
        (),
        "AMBIGUOUS",
        (),
        True,
    )
    decision = DecisionRecord("unknown", "medium", "ask_clarifying_questions", (), False, False)
    clean = calculate_confidence(domain, safety, decision, EvidenceResult((), ()), ResolvedContext((), (), (), ()))
    conflicted = calculate_confidence(domain, safety, decision, EvidenceResult((), ()), ResolvedContext((), (), ("missing_fact",), ("domain",)))
    assert conflicted.domain < clean.domain and conflicted.answer < clean.answer
