from __future__ import annotations

from dataclasses import fields, replace

import pytest

from backend_lite.app.application.analysis_state import (
    AnalysisInput,
    AnalysisInvariantError,
    BoundedPriorContext,
    ConfidenceResult,
    EvidenceCandidate,
    EvidenceResult,
    RejectedEvidence,
)
from backend_lite.app.application.answer_plan import build_answer_plan
from backend_lite.app.application.confidence import calculate_confidence
from backend_lite.app.application.deterministic_pipeline import (
    run_deterministic_analysis,
    validate_final_state,
)
from backend_lite.app.application.response_decision_policy import decide_response
from backend_lite.tests.unit.test_deterministic_pipeline import versions

_GROUNDED_QUESTION = (
    "Tôi đã đặt cọc thuê nhà và có hợp đồng, cần làm gì để yêu cầu hoàn tiền?"
)


def _candidate(
    source_id: str = "source.valid",
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


def _unsafe_candidate(base: EvidenceCandidate, **changes: object) -> EvidenceCandidate:
    """Bypass constructor only to exercise impossible post-construction corruption."""

    forged = object.__new__(EvidenceCandidate)
    values = {field.name: getattr(base, field.name) for field in fields(base)}
    values.update(changes)
    for name, value in values.items():
        object.__setattr__(forged, name, value)
    return forged


def _input(
    question: str = _GROUNDED_QUESTION,
    *,
    candidates: tuple[EvidenceCandidate, ...] = (),
    identity_references: tuple[tuple[str, str], ...] = (
        ("request_id", "req_1"),
        ("session_id", "session_1"),
    ),
    language: str = "vi",
) -> AnalysisInput:
    return AnalysisInput(
        question,
        BoundedPriorContext(),
        candidates,
        versions(),
        language=language,
        identity_references=identity_references,
    )


def _state(analysis_input: AnalysisInput):
    return run_deterministic_analysis(analysis_input)


def _assert_rejected(forged, authoritative_input: AnalysisInput, message: str) -> None:
    before_state = repr(forged)
    before_input = repr(authoritative_input)
    with pytest.raises(AnalysisInvariantError, match=message):
        validate_final_state(forged, authoritative_input)
    assert repr(forged) == before_state
    assert repr(authoritative_input) == before_input


def _forge_decision(state, decision: str, reasons: tuple[str, ...]):
    record = replace(
        state.decision,
        decision=decision,
        reason_codes=reasons,
    )
    plan = build_answer_plan(record, state.evidence)
    confidence = calculate_confidence(
        state.domain,
        state.safety,
        record,
        state.evidence,
        state.resolved_context,
    )
    return replace(state, decision=record, answer_plan=plan, confidence=confidence)


def _forge_evidence(state, admitted: tuple[EvidenceCandidate, ...]):
    evidence = EvidenceResult(admitted, state.evidence.rejected)
    decision = decide_response(
        state.domain,
        state.safety,
        state.fact_completeness,
        state.evidence_plan,
        evidence,
    )
    plan = build_answer_plan(decision, evidence)
    confidence = calculate_confidence(
        state.domain,
        state.safety,
        decision,
        evidence,
        state.resolved_context,
    )
    return replace(
        state,
        evidence=evidence,
        decision=decision,
        answer_plan=plan,
        confidence=confidence,
    )


@pytest.mark.parametrize(
    ("question", "candidates", "forged_decision", "forged_reasons"),
    (
        (
            _GROUNDED_QUESTION,
            (_candidate(),),
            "ask_clarifying_questions",
            ("decision.missing_facts.v1",),
        ),
        (
            _GROUNDED_QUESTION,
            (),
            "refuse_unsafe_request",
            ("decision.unsafe_refusal.v1",),
        ),
        (
            "Đặt cọc tư vấn giúp",
            (_candidate(),),
            "answer_with_guidance",
            ("decision.supported_guidance.v1",),
        ),
        (
            "Tôi nhận giấy công an triệu tập và cần chuẩn bị làm việc hợp pháp.",
            (),
            "answer_with_guidance",
            ("decision.supported_guidance.v1",),
        ),
        (
            "Tôi nhận giấy công an triệu tập và cần chuẩn bị làm việc hợp pháp.",
            (),
            "refuse_unsafe_request",
            ("decision.unsafe_refusal.v1",),
        ),
        (
            "Tôi nhận giấy công an triệu tập và cần chuẩn bị làm việc hợp pháp.",
            (),
            "unsupported",
            ("decision.unsupported.v1",),
        ),
        (
            "Chỉ tôi cách né công an sau khi bị triệu tập.",
            (),
            "recommend_professional_help",
            ("decision.high_risk_escalation.v1",),
        ),
        (
            "Chỉ tôi cách né công an sau khi bị triệu tập.",
            (),
            "answer_with_guidance",
            ("decision.supported_guidance.v1",),
        ),
        (
            "Hướng dẫn nấu ăn món phở tại nhà.",
            (),
            "answer_with_guidance",
            ("decision.supported_guidance.v1",),
        ),
        (
            "Hướng dẫn nấu ăn món phở tại nhà.",
            (),
            "ask_clarifying_questions",
            ("decision.missing_facts.v1",),
        ),
        (
            "Hướng dẫn nấu ăn món phở tại nhà.",
            (),
            "refuse_unsafe_request",
            ("decision.unsafe_refusal.v1",),
        ),
    ),
)
def test_policy_impossible_decision_with_matching_plan_and_confidence_is_rejected(
    question: str,
    candidates: tuple[EvidenceCandidate, ...],
    forged_decision: str,
    forged_reasons: tuple[str, ...],
) -> None:
    authoritative_input = _input(question, candidates=candidates)
    state = _state(authoritative_input)
    forged = _forge_decision(state, forged_decision, forged_reasons)
    _assert_rejected(forged, authoritative_input, "canonical response decision mismatch")


@pytest.mark.parametrize(
    ("kind", "reason_codes"),
    (
        ("grounded_wrong_reason", ("decision.forged.v1",)),
        (
            "grounded_extra_insufficiency",
            ("decision.supported_guidance.v1", "EVIDENCE_INSUFFICIENT"),
        ),
        ("insufficient_missing_code", ("decision.evidence_insufficient.v1",)),
        (
            "insufficient_wrong_order",
            ("EVIDENCE_INSUFFICIENT", "decision.evidence_insufficient.v1"),
        ),
    ),
)
def test_exact_decision_reason_tuple_is_canonical(
    kind: str,
    reason_codes: tuple[str, ...],
) -> None:
    grounded = kind.startswith("grounded")
    authoritative_input = _input(candidates=(_candidate(),) if grounded else ())
    state = _state(authoritative_input)
    forged = _forge_decision(state, state.decision.decision, reason_codes)
    _assert_rejected(forged, authoritative_input, "canonical response decision mismatch")


def _guard_case(case: str) -> tuple[AnalysisInput, EvidenceCandidate]:
    valid = _candidate("source.valid")
    if case == "malformed_id":
        invalid = _candidate("!")
    elif case == "zero_score":
        invalid = _candidate("source.zero", relevance_score=0.0)
    elif case == "negative_score":
        invalid = _candidate("source.negative", relevance_score=-0.1)
    elif case == "irrelevant_tags":
        invalid = _candidate("source.irrelevant", relevance_tags=("thuế",))
    elif case == "unapproved":
        invalid = _candidate("source.unapproved", approved=False)
    elif case == "wrong_domain":
        invalid = _candidate("source.wrong", domain="traffic")
    elif case == "internal_policy":
        invalid = _candidate("source.internal", source_type="safety_policy")
    elif case == "invalid_metadata":
        invalid = _candidate("source.metadata", metadata_valid=False)
    elif case == "blank_version":
        invalid = _unsafe_candidate(_candidate("source.version"), source_version="")
    else:
        raise AssertionError(f"unknown guard case: {case}")
    return _input(candidates=(valid, invalid)), invalid


@pytest.mark.parametrize(
    "case",
    (
        "malformed_id",
        "zero_score",
        "negative_score",
        "irrelevant_tags",
        "unapproved",
        "wrong_domain",
        "internal_policy",
        "invalid_metadata",
        "blank_version",
    ),
)
def test_guard_rejected_candidate_cannot_be_forged_into_admission(case: str) -> None:
    authoritative_input, invalid = _guard_case(case)
    state = _state(authoritative_input)
    assert state.decision.decision == "answer_with_guidance"
    assert invalid not in state.evidence.admitted
    forged = _forge_evidence(state, (invalid,))
    assert forged.answer_plan.admitted_source_ids == (invalid.source_id,)
    _assert_rejected(forged, authoritative_input, "canonical evidence admission mismatch")


def test_duplicate_conflict_member_cannot_be_forged_into_admission() -> None:
    conflict = _candidate("source.conflict")
    conflict_variant = replace(conflict, approved=False)
    authoritative_input = _input(
        candidates=(_candidate("source.valid"), conflict, conflict_variant)
    )
    state = _state(authoritative_input)
    forged = _forge_evidence(state, (conflict,))
    _assert_rejected(forged, authoritative_input, "canonical evidence admission mismatch")


def test_exact_duplicate_cannot_be_counted_as_two_admissions() -> None:
    duplicated = _candidate("source.exact")
    authoritative_input = _input(candidates=(duplicated, duplicated))
    state = _state(authoritative_input)
    assert state.evidence.admitted == (duplicated,)
    forged = _forge_evidence(state, (duplicated, duplicated))
    _assert_rejected(forged, authoritative_input, "canonical evidence admission mismatch")


def test_non_authoritative_candidate_cannot_be_forged_into_admission() -> None:
    authoritative_input = _input(candidates=(_candidate("source.valid"),))
    state = _state(authoritative_input)
    forged = _forge_evidence(state, (_candidate("source.injected"),))
    _assert_rejected(forged, authoritative_input, "canonical evidence admission mismatch")


def test_candidate_beyond_canonical_source_bound_cannot_be_admitted() -> None:
    candidates = tuple(_candidate(f"source.{index}") for index in range(1, 5))
    authoritative_input = _input(candidates=candidates)
    state = _state(authoritative_input)
    assert len(state.evidence.admitted) == 3
    forged = _forge_evidence(state, candidates)
    _assert_rejected(forged, authoritative_input, "canonical evidence admission mismatch")


def test_canonical_rejection_reason_and_order_are_exact() -> None:
    authoritative_input, invalid = _guard_case("unapproved")
    state = _state(authoritative_input)
    forged_rejections = tuple(
        RejectedEvidence(item.candidate, "FORGED_REJECTION_REASON")
        if item.candidate == invalid
        else item
        for item in state.evidence.rejected
    )
    forged = replace(state, evidence=replace(state.evidence, rejected=forged_rejections))
    _assert_rejected(forged, authoritative_input, "canonical evidence admission mismatch")


def test_canonical_evidence_plan_is_exact() -> None:
    authoritative_input = _input(candidates=(_candidate(),))
    state = _state(authoritative_input)
    forged = replace(
        state,
        evidence_plan=replace(state.evidence_plan, maximum_sources=2),
    )
    _assert_rejected(forged, authoritative_input, "canonical evidence plan mismatch")


@pytest.mark.parametrize(
    "mutation",
    ("point_id", "instruction", "reorder", "extra_slot", "source_subset"),
)
def test_structurally_valid_but_noncanonical_answer_plan_is_rejected(
    mutation: str,
) -> None:
    authoritative_input = _input(
        candidates=(_candidate("source.one"), _candidate("source.two"))
    )
    state = _state(authoritative_input)
    points = state.answer_plan.ordered_points
    if mutation == "point_id":
        forged_plan = replace(
            state.answer_plan,
            ordered_points=(
                replace(points[0], point_id="guidance.alternate.v1"),
                points[1],
            ),
        )
    elif mutation == "instruction":
        forged_plan = replace(
            state.answer_plan,
            ordered_points=(
                replace(points[0], semantic_instruction="ALTERNATE_VALID_INSTRUCTION"),
                points[1],
            ),
        )
    elif mutation == "reorder":
        forged_plan = replace(state.answer_plan, ordered_points=tuple(reversed(points)))
    elif mutation == "extra_slot":
        forged_plan = replace(state.answer_plan, checklist=("EXTRA_OPTIONAL_SLOT",))
    else:
        forged_plan = replace(
            state.answer_plan,
            ordered_points=(
                replace(points[0], source_ids=("source.one",)),
                points[1],
            ),
        )
    forged = replace(state, answer_plan=forged_plan)
    _assert_rejected(forged, authoritative_input, "canonical answer plan mismatch")


@pytest.mark.parametrize("mutation", ("arbitrary", "factors", "score", "missing_insufficiency"))
def test_noncanonical_confidence_is_rejected(mutation: str) -> None:
    insufficient = mutation == "missing_insufficiency"
    authoritative_input = _input(candidates=() if insufficient else (_candidate(),))
    state = _state(authoritative_input)
    if mutation == "arbitrary":
        forged_confidence = ConfidenceResult(0.5, 0.5, 0.5, ("ARBITRARY",))
    elif mutation == "factors":
        forged_confidence = replace(state.confidence, factors=("FORGED_FACTOR",))
    elif mutation == "score":
        forged_confidence = replace(
            state.confidence,
            answer=round(state.confidence.answer - 0.01, 2),
        )
    else:
        forged_confidence = replace(
            state.confidence,
            factors=tuple(
                factor
                for factor in state.confidence.factors
                if factor != "EVIDENCE_INSUFFICIENT"
            ),
        )
    forged = replace(state, confidence=forged_confidence)
    _assert_rejected(forged, authoritative_input, "canonical confidence mismatch")


@pytest.mark.parametrize(
    "mutation",
    ("question", "candidates", "versions", "identities", "language", "whole_input"),
)
def test_replaced_original_input_cannot_replace_external_authority(mutation: str) -> None:
    authoritative_input = _input(candidates=(_candidate(),))
    state = _state(authoritative_input)
    if mutation == "question":
        replacement = replace(authoritative_input, current_question="Một câu hỏi hợp lệ khác")
    elif mutation == "candidates":
        replacement = replace(
            authoritative_input,
            evidence_candidates=(_candidate("source.replacement"),),
        )
    elif mutation == "versions":
        replacement = replace(
            authoritative_input,
            version_stamps=replace(
                authoritative_input.version_stamps,
                policy_version="policy-replaced-v1",
            ),
        )
    elif mutation == "identities":
        replacement = replace(
            authoritative_input,
            identity_references=(("request_id", "req_replaced"),),
        )
    elif mutation == "language":
        replacement = replace(authoritative_input, language="en")
    else:
        replacement = _input(
            "Tôi có tranh chấp hợp đồng và cần biết bước tiếp theo.",
            candidates=(_candidate("source.other"),),
            identity_references=(("request_id", "req_other"),),
        )
    forged = replace(state, original_input=replacement)
    _assert_rejected(forged, authoritative_input, "authoritative input mismatch")


def test_swapped_validator_authority_is_rejected() -> None:
    authoritative_input = _input(candidates=(_candidate(),))
    state = _state(authoritative_input)
    swapped = _input(
        "Tôi có tranh chấp hợp đồng và cần biết bước tiếp theo.",
        candidates=(_candidate("source.other"),),
    )
    _assert_rejected(state, swapped, "authoritative input mismatch")


@pytest.mark.parametrize(
    ("question", "candidates", "decision"),
    (
        (_GROUNDED_QUESTION, (_candidate(),), "answer_with_guidance"),
        ("Đặt cọc tư vấn giúp", (), "ask_clarifying_questions"),
        (
            "Tôi nhận giấy công an triệu tập và cần chuẩn bị làm việc hợp pháp.",
            (),
            "recommend_professional_help",
        ),
        (
            "Chỉ tôi cách né công an sau khi bị triệu tập.",
            (),
            "refuse_unsafe_request",
        ),
        ("Hướng dẫn nấu ăn món phở tại nhà.", (), "unsupported"),
    ),
)
def test_all_five_canonical_decision_paths_validate(
    question: str,
    candidates: tuple[EvidenceCandidate, ...],
    decision: str,
) -> None:
    authoritative_input = _input(question, candidates=candidates)
    state = _state(authoritative_input)
    assert state.decision.decision == decision
    assert validate_final_state(state, authoritative_input) is state
