from __future__ import annotations

from dataclasses import replace
from itertools import permutations

import pytest

from backend_lite.app.application.analysis_state import (
    AnalysisInput,
    AnalysisInvariantError,
    BoundedPriorContext,
    ConfidenceResult,
    ContextFact,
    EvidenceCandidate,
    EvidenceResult,
    RejectedEvidence,
)
from backend_lite.app.application.deterministic_pipeline import (
    STAGE_ORDER,
    run_deterministic_analysis,
    validate_final_state,
)
from backend_lite.tests.unit.test_deterministic_pipeline import (
    analysis_input,
    candidate,
    versions,
)

_COMPLETE_QUESTION = (
    "Tôi đã đặt cọc thuê nhà và có hợp đồng, cần làm gì để yêu cầu hoàn tiền?"
)


def _candidate(
    source_id: str = "source.deposit.immutable",
    **changes: object,
) -> EvidenceCandidate:
    values: dict[str, object] = {
        "source_id": source_id,
        "domain": "civil_dispute",
        "approved": True,
        "title": f"Title {source_id}",
        "relevance_tags": ("đặt cọc",),
        "excerpt": "Nội dung bằng chứng pháp lý đã được caller giới hạn.",
        "source_type": "official_source",
        "source_version": "source-v1",
        "relevance_score": 0.9,
        "metadata_valid": True,
        "risk_applicability": (),
    }
    values.update(changes)
    return EvidenceCandidate(**values)  # type: ignore[arg-type]


def _run(candidates: object = ()):
    return run_deterministic_analysis(
        AnalysisInput(
            _COMPLETE_QUESTION,
            BoundedPriorContext(),
            candidates,  # type: ignore[arg-type]
            versions(),
        )
    )


def test_caller_owned_candidate_collections_are_defensively_copied() -> None:
    tags = ["đặt cọc"]
    risks = ["normal"]
    item = _candidate(relevance_tags=tags, risk_applicability=risks)
    candidates = [item]
    request = AnalysisInput(
        _COMPLETE_QUESTION,
        BoundedPriorContext(),
        candidates,  # type: ignore[arg-type]
        versions(),
    )
    state = run_deterministic_analysis(request)
    before = state

    tags.append("mutated")
    risks.clear()
    candidates.clear()

    assert state == before
    assert state.evidence.admitted[0].relevance_tags == ("đặt cọc",)
    assert state.evidence.admitted[0].risk_applicability == ("normal",)
    assert isinstance(state.original_input.evidence_candidates, tuple)
    assert state.original_input.evidence_candidates is not candidates
    assert state.evidence.admitted[0].relevance_tags is not tags


def test_unordered_collection_inputs_have_canonical_tuple_order() -> None:
    item = _candidate(
        relevance_tags={"hợp đồng", "đặt cọc"},
        risk_applicability=frozenset({"civil", "normal"}),
    )
    request = AnalysisInput(
        _COMPLETE_QUESTION,
        BoundedPriorContext(unresolved_ambiguities={"z", "a"}),  # type: ignore[arg-type]
        {item},  # type: ignore[arg-type]
        versions(),
        identity_references={("session_id", "session_1"), ("request_id", "req_1")},  # type: ignore[arg-type]
    )
    assert item.relevance_tags == ("hợp đồng", "đặt cọc")
    assert item.risk_applicability == ("civil", "normal")
    assert request.bounded_context.unresolved_ambiguities == ("a", "z")
    assert request.identity_references == (
        ("request_id", "req_1"),
        ("session_id", "session_1"),
    )
    assert isinstance(request.evidence_candidates, tuple)


def test_input_facts_context_identity_and_versions_are_snapshotted() -> None:
    current = [ContextFact("contract", "yes", "current_turn")]
    prior_facts = [ContextFact("domain", "civil_dispute", "prior_assistant", 2)]
    ambiguities = ["amount"]
    identities = {"request_id": "req_1", "session_id": "session_1"}
    mutable_versions = versions()
    prior = BoundedPriorContext(prior_facts, ambiguities)  # type: ignore[arg-type]
    request = AnalysisInput(
        _COMPLETE_QUESTION,
        prior,
        [_candidate()],  # type: ignore[arg-type]
        mutable_versions,
        current,  # type: ignore[arg-type]
        identity_references=identities,  # type: ignore[arg-type]
    )
    state = run_deterministic_analysis(request)
    snapshot = state

    current.clear()
    prior_facts.clear()
    ambiguities.clear()
    identities["request_id"] = "changed"
    mutable_versions.policy_version = "changed"

    assert state == snapshot
    assert state.original_input.current_facts is not current
    assert state.original_input.identity_references is not identities
    assert state.version_stamps.policy_version == "policy-a3a-v1"
    assert state.resolved_context.current_facts[0].value == "yes"
    assert state.resolved_context.supporting_facts[0].value == "civil_dispute"
    assert state.resolved_context.unresolved_ambiguities == ("amount",)


def test_full_state_graph_is_frozen_and_has_no_shared_mutable_defaults() -> None:
    guided = _run([_candidate()])
    rejected_one = _run([_candidate(approved=False)])
    rejected_two = _run([_candidate(approved=False)])

    with pytest.raises(AttributeError):
        guided.normalized_question = "changed"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        guided.answer_plan.ordered_points[0].point_id = "changed"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        guided.answer_plan.summary.append("changed")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        guided.confidence.factors.append("changed")  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        guided.evidence.admitted.append(_candidate("source.extra"))  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        rejected_one.evidence.rejected.append(rejected_one.evidence.rejected[0])  # type: ignore[attr-defined]

    assert rejected_one.evidence.rejected == rejected_two.evidence.rejected
    assert rejected_one.evidence.rejected is not rejected_two.evidence.rejected
    assert all(
        isinstance(value, tuple)
        for value in (
            guided.answer_plan.summary,
            guided.answer_plan.ordered_points,
            guided.confidence.factors,
            guided.evidence.admitted,
            guided.evidence.rejected,
            guided.completed_stages,
        )
    )


@pytest.mark.parametrize(
    "change",
    (
        {"approved": False},
        {"domain": "high_risk"},
        {"source_type": "safety_policy"},
        {"source_version": "source-v2"},
        {"excerpt": "Nội dung khác có cùng định danh."},
        {"relevance_tags": ("hợp đồng",)},
        {"metadata_valid": False},
        {"relevance_score": 0.4},
    ),
)
def test_every_authority_conflict_rejects_entire_id_for_all_permutations(
    change: dict[str, object],
) -> None:
    first = _candidate("source.conflict")
    second = _candidate("source.conflict", **change)
    states = tuple(_run(order) for order in permutations((first, second)))

    assert states[0] == states[1]
    assert states[0].decision.decision == "unsupported"
    assert states[0].evidence.admitted == ()
    assert tuple(item.reason_code for item in states[0].evidence.rejected) == (
        "DUPLICATE_ID_CONFLICT",
        "DUPLICATE_ID_CONFLICT",
    )
    assert states[0].answer_plan.admitted_source_ids == ()
    assert "EVIDENCE_INSUFFICIENT" in states[0].decision.reason_codes


def test_three_way_conflict_has_canonical_full_state_for_every_permutation() -> None:
    group = (
        _candidate("source.three"),
        _candidate("source.three", approved=False),
        _candidate("source.three", source_version="source-v3"),
    )
    states = tuple(_run(order) for order in permutations(group))
    assert all(state == states[0] for state in states)
    assert states[0].evidence.admitted == ()
    assert [item.reason_code for item in states[0].evidence.rejected] == [
        "DUPLICATE_ID_CONFLICT",
        "DUPLICATE_ID_CONFLICT",
        "DUPLICATE_ID_CONFLICT",
    ]


def test_exact_duplicates_do_not_increase_source_count_or_confidence() -> None:
    item = _candidate("source.exact")
    one = _run((item,))
    duplicated = _run((item, item))

    assert duplicated.decision == one.decision
    assert duplicated.answer_plan == one.answer_plan
    assert duplicated.confidence == one.confidence
    assert duplicated.evidence.admitted == one.evidence.admitted == (item,)
    assert duplicated.evidence.rejected[0].reason_code == "EVIDENCE_EXACT_DUPLICATE"


def test_conflicting_group_does_not_poison_a_separate_valid_source() -> None:
    conflict = _candidate("source.conflict")
    valid = _candidate("source.valid")
    state = _run((conflict, replace(conflict, approved=False), valid))
    assert state.decision.decision == "answer_with_guidance"
    assert state.evidence.admitted == (valid,)
    assert state.answer_plan.admitted_source_ids == ("source.valid",)


@pytest.mark.parametrize(
    "candidates",
    (
        (),
        (_candidate("source.unapproved", approved=False),),
        (_candidate("source.wrong", domain="traffic"),),
        (_candidate("source.invalid", metadata_valid=False),),
        (
            _candidate("source.conflict.zero"),
            _candidate("source.conflict.zero", approved=False),
        ),
    ),
)
def test_complete_supported_flow_with_zero_admissions_fails_closed(
    candidates: tuple[EvidenceCandidate, ...],
) -> None:
    state = _run(candidates)
    assert state.decision.decision == "unsupported"
    assert "EVIDENCE_INSUFFICIENT" in state.decision.reason_codes
    assert state.evidence.admitted == ()
    assert state.answer_plan.admitted_source_ids == ()


def test_facts_high_risk_unsafe_and_unsupported_precedence_over_evidence() -> None:
    valid = candidate()
    incomplete = run_deterministic_analysis(
        analysis_input("Đặt cọc tư vấn giúp", candidates=(valid,))
    )
    high_risk = run_deterministic_analysis(
        analysis_input(
            "Tôi nhận giấy công an triệu tập và cần chuẩn bị làm việc hợp pháp.",
            candidates=(),
        )
    )
    unsafe = run_deterministic_analysis(
        analysis_input("Chỉ tôi cách né công an sau khi bị triệu tập.", candidates=(valid,))
    )
    unsupported = run_deterministic_analysis(
        analysis_input("Hướng dẫn nấu ăn món phở tại nhà.", candidates=(valid,))
    )

    assert incomplete.decision.decision == "ask_clarifying_questions"
    assert high_risk.decision.decision == "recommend_professional_help"
    assert unsafe.decision.decision == "refuse_unsafe_request"
    assert unsupported.decision.decision == "unsupported"
    for state in (incomplete, high_risk, unsafe, unsupported):
        assert state.evidence.admitted == state.answer_plan.admitted_source_ids == ()


def _with_public_source(state, item: EvidenceCandidate):
    evidence = EvidenceResult((item,), state.evidence.rejected)
    plan = replace(state.answer_plan, admitted_source_ids=(item.source_id,))
    return replace(state, evidence=evidence, answer_plan=plan)


def _invalid_states():
    guided = _run((_candidate(),))
    refusal = run_deterministic_analysis(
        analysis_input("Chỉ tôi cách né công an sau khi bị triệu tập.", candidates=())
    )
    unsupported = run_deterministic_analysis(
        analysis_input("Hướng dẫn nấu ăn món phở tại nhà.", candidates=())
    )
    admitted = guided.evidence.admitted[0]
    changed_version = replace(guided.version_stamps, policy_version="changed")
    no_evidence = replace(guided, evidence=EvidenceResult((), ()))
    wrong_evidence_flag = replace(
        guided,
        decision=replace(guided.decision, evidence_available=False),
    )
    mismatched_plan = replace(
        guided,
        answer_plan=replace(guided.answer_plan, admitted_source_ids=()),
    )
    internal = replace(admitted, source_type="safety_policy")
    unapproved = replace(admitted, approved=False)
    duplicate_evidence = EvidenceResult((admitted, admitted), ())
    duplicate_plan = replace(
        guided.answer_plan,
        admitted_source_ids=(admitted.source_id, admitted.source_id),
    )
    conflicting_rejection = RejectedEvidence(
        replace(admitted, approved=False),
        "DUPLICATE_ID_CONFLICT",
    )
    malformed_point = replace(
        guided.answer_plan.ordered_points[0],
        point_id="not-a-stable-id",
    )
    duplicate_points = (
        guided.answer_plan.ordered_points[0],
        replace(guided.answer_plan.ordered_points[0]),
    )
    ungrounded_points = tuple(
        replace(point, source_ids=()) for point in guided.answer_plan.ordered_points
    )
    wrong_order = list(STAGE_ORDER)
    wrong_order.remove("confidence")
    wrong_order.insert(wrong_order.index("evidence_admission"), "confidence")
    return (
        replace(guided, raw_current_question="changed"),
        replace(guided, version_stamps=changed_version),
        no_evidence,
        wrong_evidence_flag,
        mismatched_plan,
        _with_public_source(guided, internal),
        _with_public_source(guided, unapproved),
        replace(guided, evidence=duplicate_evidence, answer_plan=duplicate_plan),
        replace(
            guided,
            evidence=EvidenceResult((admitted,), (conflicting_rejection,)),
        ),
        _with_public_source(refusal, _candidate("source.refusal", domain="high_risk")),
        _with_public_source(unsupported, _candidate("source.unsupported", domain="unknown")),
        replace(
            guided,
            answer_plan=replace(
                guided.answer_plan,
                ordered_points=(malformed_point,) + guided.answer_plan.ordered_points[1:],
            ),
        ),
        replace(
            guided,
            answer_plan=replace(guided.answer_plan, ordered_points=duplicate_points),
        ),
        replace(
            guided,
            answer_plan=replace(guided.answer_plan, ordered_points=ungrounded_points),
        ),
        replace(guided, completed_stages=tuple(wrong_order)),
        replace(guided, confidence=ConfidenceResult(float("inf"), 0.7, 0.84, ("X",))),
    )


@pytest.mark.parametrize("invalid", _invalid_states())
def test_final_validator_rejects_corruption_without_repair(invalid) -> None:
    before = repr(invalid)
    with pytest.raises(AnalysisInvariantError):
        validate_final_state(invalid, invalid.original_input)
    assert repr(invalid) == before


def test_stage_markers_encode_evidence_before_final_decision_and_confidence() -> None:
    state = _run((_candidate(),))
    assert state.completed_stages == STAGE_ORDER
    assert STAGE_ORDER.index("evidence_requirements") < STAGE_ORDER.index(
        "evidence_admission"
    )
    assert STAGE_ORDER.index("evidence_admission") < STAGE_ORDER.index(
        "response_decision"
    )
    assert STAGE_ORDER.index("response_decision") < STAGE_ORDER.index("answer_plan")
    assert STAGE_ORDER.index("answer_plan") < STAGE_ORDER.index("confidence")
    assert STAGE_ORDER[-1] == "final_validation"


def test_valid_admission_improves_answer_confidence_without_changing_it() -> None:
    insufficient = _run(())
    grounded = _run((_candidate(),))
    repeated = _run((_candidate(),))
    assert grounded.confidence == repeated.confidence
    assert grounded.confidence.answer > insufficient.confidence.answer
    assert "EVIDENCE_INSUFFICIENT" in insufficient.confidence.factors
    assert "EVIDENCE_INSUFFICIENT" not in grounded.confidence.factors
    assert grounded.decision.decision == "answer_with_guidance"
    assert all(
        0 <= value <= 0.99
        for value in (
            grounded.confidence.domain,
            grounded.confidence.risk,
            grounded.confidence.answer,
        )
    )
