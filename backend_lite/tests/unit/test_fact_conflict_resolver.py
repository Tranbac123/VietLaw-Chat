from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend_lite.app.application.fact_conflict_resolver import resolve_fact_operation
from backend_lite.app.contracts.legal_facts import (
    COUNTERPARTY_CLAIM_POLICY,
    DISPUTED_FACT_POLICY,
    BoundFactOperation,
    ChangeType,
    Claimant,
    CounterpartyClaimPolicy,
    DateValue,
    DisputedFactPolicy,
    Epistemic,
    ExistenceValue,
    FactAssertion,
    FactOpKind,
    FactSlot,
    FactStatus,
    FactValue,
    PaymentEvidenceValue,
    MoneyAmount,
    TextAnchor,
    UnboundFactOperation,
    VerificationStatus,
)


NOW = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)


def make_bound(
    op: FactOpKind,
    *,
    claimed_status: FactStatus | None = None,
    claimant: Claimant = Claimant.USER,
    request_id: str = "request-new",
    op_index: int = 0,
    confidence: float = 0.9,
    effective_from: DateValue | None = None,
    epistemic: Epistemic = Epistemic.NONE,
    slot: str = "written_agreement_exists",
    issue_type_hint: str | None = "rental_deposit",
    bound_issue_type: str = "rental_deposit",
    value: ExistenceValue | None | object = ...,
) -> BoundFactOperation:
    inferred_status = claimed_status
    if op in {FactOpKind.AFFIRM, FactOpKind.SET_VALUE}:
        inferred_status = FactStatus.PRESENT
    elif op is FactOpKind.NEGATE:
        inferred_status = FactStatus.ABSENT
    if value is ...:
        value = ExistenceValue() if inferred_status is FactStatus.PRESENT else None
    if op is FactOpKind.REPORT_UNKNOWN and epistemic is Epistemic.NONE:
        epistemic = Epistemic.USER_UNKNOWN
    unbound = UnboundFactOperation(
        op=op,
        slot_hint=slot,
        issue_type_hint=issue_type_hint,
        claimed_status=claimed_status,
        value=value,
        claimant=claimant,
        epistemic=epistemic,
        effective_from=effective_from,
        anchor=TextAnchor(message_id=f"message-{request_id}", start=0, end=2, quote="có"),
        extractor_version="extractor-v1",
        confidence=confidence,
        op_index=op_index,
    )
    return BoundFactOperation(
        unbound=unbound,
        episode_id="episode-1",
        bound_issue_type=bound_issue_type,
        slot=slot,
        resolver_version="resolver-v1",
        request_id=request_id,
    )


def make_assertion(
    assertion_id: str,
    status: FactStatus,
    *,
    request_id: str = "request-old",
    op_index: int = 0,
    claimant: Claimant = Claimant.USER,
) -> FactAssertion:
    return FactAssertion(
        assertion_id=assertion_id,
        episode_id="episode-1",
        slot="written_agreement_exists",
        status_claimed=status,
        value=ExistenceValue() if status is FactStatus.PRESENT else None,
        claimant=claimant,
        verification=VerificationStatus.UNVERIFIED,
        change_type=ChangeType.INITIAL,
        observed_at=NOW,
        anchor=TextAnchor(message_id=f"message-{request_id}", start=0, end=2, quote="có"),
        message_id=f"message-{request_id}",
        request_id=request_id,
        op_index=op_index,
        extractor_version="extractor-v1",
        resolver_version="resolver-v1",
        registry_version="registry-v1",
        reason_code="fact.initial.v1",
    )


def make_slot(status: FactStatus, assertion_ids: list[str] | None = None) -> FactSlot[FactValue]:
    return FactSlot[FactValue](
        status=status,
        value=ExistenceValue() if status is FactStatus.PRESENT else None,
        claimant=None if status is FactStatus.UNSET else Claimant.USER,
        verification=VerificationStatus.UNVERIFIED,
        last_change_type=None if status is FactStatus.UNSET else ChangeType.INITIAL,
        pending_clarification=status is FactStatus.DISPUTED,
        assertion_ids=assertion_ids or [],
    )


def resolve(
    slot: FactSlot[FactValue],
    operation: BoundFactOperation,
    assertions: list[FactAssertion] | None = None,
    assertion_id: str = "assertion-new",
):
    return resolve_fact_operation(
        slot,
        operation,
        assertions or [],
        assertion_id,
        NOW,
        "registry-v1",
    )


@pytest.mark.parametrize(
    ("operation", "expected"),
    [(FactOpKind.AFFIRM, FactStatus.PRESENT), (FactOpKind.NEGATE, FactStatus.ABSENT)],
)
def test_rows_1_and_2_unset_initial_claim(operation: FactOpKind, expected: FactStatus) -> None:
    result = resolve(make_slot(FactStatus.UNSET), make_bound(operation))
    assert result.projected_slot.status is expected
    assert result.resolution.change_type is ChangeType.INITIAL
    assert result.resolution.decision == "apply"
    assert result.resolution.requires_clarification is False
    assert result.assertion_to_append is not None


@pytest.mark.parametrize(
    ("status", "operation"),
    [(FactStatus.PRESENT, FactOpKind.AFFIRM), (FactStatus.ABSENT, FactOpKind.NEGATE)],
)
def test_rows_3_and_4_same_claim_is_idempotent(status: FactStatus, operation: FactOpKind) -> None:
    prior = make_assertion("assertion-old", status)
    result = resolve(make_slot(status, [prior.assertion_id]), make_bound(operation), [prior])
    assert result.projected_slot.status is status
    assert result.resolution.decision == "no_op"
    assert result.resolution.reason_code == "fact.op.idempotent_reaffirmation.v1"
    assert result.assertion_to_append is None


@pytest.mark.parametrize(
    ("prior_status", "target_status"),
    [(FactStatus.PRESENT, FactStatus.ABSENT), (FactStatus.ABSENT, FactStatus.PRESENT)],
)
def test_rows_5_and_6_explicit_correction_is_symmetric(
    prior_status: FactStatus, target_status: FactStatus
) -> None:
    prior = make_assertion("assertion-old", prior_status)
    operation = make_bound(FactOpKind.CORRECT, claimed_status=target_status)
    result = resolve(make_slot(prior_status, [prior.assertion_id]), operation, [prior])
    assert result.projected_slot.status is target_status
    assert result.resolution.change_type is ChangeType.CORRECTION
    assert result.resolution.decision == "supersede"
    assert result.resolution.requires_clarification is False
    assert result.resolution.supersessions[0].assertion_id == "assertion-old"
    assert result.resolution.supersessions[0].reason == "correction"


@pytest.mark.parametrize(
    ("prior_status", "operation", "target_status"),
    [
        (FactStatus.PRESENT, FactOpKind.NEGATE, FactStatus.ABSENT),
        (FactStatus.ABSENT, FactOpKind.AFFIRM, FactStatus.PRESENT),
    ],
)
def test_rows_7_and_8_bare_contradiction_is_symmetric_disputed(
    prior_status: FactStatus, operation: FactOpKind, target_status: FactStatus
) -> None:
    prior = make_assertion("assertion-old", prior_status)
    result = resolve(make_slot(prior_status, [prior.assertion_id]), make_bound(operation), [prior])
    assert result.resolution.incoming_status is target_status
    assert result.projected_slot.status is FactStatus.DISPUTED
    assert result.projected_slot.value is None
    assert result.projected_slot.pending_clarification is True
    assert result.resolution.requires_clarification is True
    assert result.resolution.guidance_status is None
    assert result.resolution.decision == "dispute"
    assert result.resolution.supersessions == []
    assert result.projected_slot.assertion_ids == ["assertion-old", "assertion-new"]


def test_row_9_temporal_transition_uses_supplied_effective_time() -> None:
    prior = make_assertion("assertion-old", FactStatus.ABSENT)
    effective = DateValue(granularity="unspecified", iso=None, as_written="hôm nay")
    operation = make_bound(
        FactOpKind.TRANSITION,
        claimed_status=FactStatus.PRESENT,
        effective_from=effective,
    )
    result = resolve(make_slot(FactStatus.ABSENT, [prior.assertion_id]), operation, [prior])
    assert result.projected_slot.status is FactStatus.PRESENT
    assert result.projected_slot.effective_from == effective
    assert result.resolution.change_type is ChangeType.STATE_TRANSITION
    assert result.resolution.supersessions[0].reason == "state_transition"
    assert result.resolution.requires_clarification is False


def test_temporal_transition_without_effective_time_is_rejected() -> None:
    prior = make_assertion("assertion-old", FactStatus.ABSENT)
    operation = make_bound(FactOpKind.TRANSITION, claimed_status=FactStatus.PRESENT)
    result = resolve(make_slot(FactStatus.ABSENT, [prior.assertion_id]), operation, [prior])
    assert result.projected_slot.status is FactStatus.ABSENT
    assert result.resolution.decision == "reject"
    assert result.resolution.reason_code == "fact.transition.effective_time_required.v1"
    assert result.assertion_to_append is None


def test_row_10_opposing_counterparty_claim_does_not_overwrite_user_snapshot() -> None:
    prior = make_assertion("assertion-user", FactStatus.PRESENT)
    operation = make_bound(FactOpKind.NEGATE, claimant=Claimant.COUNTERPARTY)
    result = resolve(make_slot(FactStatus.PRESENT, [prior.assertion_id]), operation, [prior])
    assert result.projected_slot.status is FactStatus.PRESENT
    assert result.projected_slot.claimant is Claimant.USER
    assert result.projected_slot.verification is VerificationStatus.CONTESTED
    assert result.projected_slot.counter_claims == ["assertion-new"]
    assert result.resolution.decision == "contest"
    assert result.resolution.requires_clarification is False
    assert result.assertion_to_append is not None
    assert result.assertion_to_append.claimant is Claimant.COUNTERPARTY


def test_agreeing_counterparty_claim_corroborates_without_overwrite() -> None:
    prior = make_assertion("assertion-user", FactStatus.PRESENT)
    operation = make_bound(FactOpKind.AFFIRM, claimant=Claimant.COUNTERPARTY)
    result = resolve(make_slot(FactStatus.PRESENT, [prior.assertion_id]), operation, [prior])
    assert result.projected_slot.status is FactStatus.PRESENT
    assert result.projected_slot.claimant is Claimant.USER
    assert result.projected_slot.verification is VerificationStatus.CORROBORATED
    assert result.projected_slot.counter_claims == ["assertion-new"]


def test_counterparty_only_claim_keeps_user_snapshot_unset() -> None:
    operation = make_bound(FactOpKind.NEGATE, claimant=Claimant.COUNTERPARTY)
    result = resolve(make_slot(FactStatus.UNSET), operation)
    assert result.projected_slot.status is FactStatus.UNSET
    assert result.projected_slot.claimant is None
    assert result.projected_slot.verification is VerificationStatus.UNVERIFIED
    assert result.projected_slot.counter_claims == ["assertion-new"]
    assert result.resolution.requires_clarification is False


def test_row_11_report_unknown_preserves_present_and_adds_epistemic_note() -> None:
    prior = make_assertion("assertion-old", FactStatus.PRESENT)
    operation = make_bound(FactOpKind.REPORT_UNKNOWN, epistemic=Epistemic.USER_UNKNOWN)
    result = resolve(make_slot(FactStatus.PRESENT, [prior.assertion_id]), operation, [prior])
    assert result.projected_slot.status is FactStatus.PRESENT
    assert result.projected_slot.epistemic is Epistemic.USER_UNKNOWN
    assert result.projected_slot.reconfirmation_needed is True
    assert result.projected_slot.pending_clarification is True
    assert result.epistemic_note_to_append is not None
    assert result.assertion_to_append is None
    assert result.resolution.change_type is ChangeType.EPISTEMIC_NOTE


def test_row_12_report_unknown_from_unset_never_becomes_absent_or_present() -> None:
    operation = make_bound(FactOpKind.REPORT_UNKNOWN, epistemic=Epistemic.USER_UNKNOWN)
    result = resolve(make_slot(FactStatus.UNSET), operation)
    assert result.projected_slot.status is FactStatus.UNSET
    assert result.projected_slot.epistemic is Epistemic.USER_UNKNOWN
    assert result.projected_slot.reconfirmation_needed is False
    assert result.epistemic_note_to_append is not None


def test_row_13_explicit_dispute_resolution_supersedes_conflicting_assertions() -> None:
    first = make_assertion("assertion-present", FactStatus.PRESENT, request_id="request-a")
    second = make_assertion("assertion-absent", FactStatus.ABSENT, request_id="request-b")
    slot = make_slot(FactStatus.DISPUTED, [first.assertion_id, second.assertion_id])
    operation = make_bound(FactOpKind.RESOLVE_DISPUTE, claimed_status=FactStatus.PRESENT)
    result = resolve(slot, operation, [first, second])
    assert result.projected_slot.status is FactStatus.PRESENT
    assert result.projected_slot.pending_clarification is False
    assert result.resolution.change_type is ChangeType.DISPUTE_RESOLVED
    assert result.resolution.requires_clarification is False
    assert {item.assertion_id for item in result.resolution.supersessions} == {
        "assertion-present",
        "assertion-absent",
    }


def test_row_14_duplicate_operation_identity_is_no_op() -> None:
    duplicate = make_assertion(
        "assertion-existing",
        FactStatus.PRESENT,
        request_id="request-duplicate",
        op_index=4,
    )
    slot = make_slot(FactStatus.PRESENT, [duplicate.assertion_id])
    operation = make_bound(FactOpKind.AFFIRM, request_id="request-duplicate", op_index=4)
    result = resolve(slot, operation, [duplicate])
    assert result.projected_slot == slot
    assert result.resolution.decision == "no_op"
    assert result.resolution.reason_code == "fact.op.duplicate.v1"
    assert result.assertion_to_append is None


def test_contradiction_symmetry_has_mirrored_statuses_and_identical_policy_shape() -> None:
    shapes = []
    for prior_status, operation in (
        (FactStatus.PRESENT, FactOpKind.NEGATE),
        (FactStatus.ABSENT, FactOpKind.AFFIRM),
    ):
        prior = make_assertion(f"prior-{prior_status.value}", prior_status)
        result = resolve(make_slot(prior_status, [prior.assertion_id]), make_bound(operation), [prior])
        shapes.append(
            (
                result.projected_slot.status,
                result.resolution.decision,
                result.resolution.change_type,
                result.resolution.requires_clarification,
                result.resolution.guidance_status,
                result.resolution.reason_code,
            )
        )
    assert shapes[0] == shapes[1]


def test_same_turn_opposites_without_structure_become_disputed() -> None:
    first_operation = make_bound(FactOpKind.AFFIRM, request_id="request-turn", op_index=0)
    first = resolve(make_slot(FactStatus.UNSET), first_operation, assertion_id="assertion-first")
    assert first.assertion_to_append is not None
    second_operation = make_bound(FactOpKind.NEGATE, request_id="request-turn", op_index=1)
    second = resolve(
        first.projected_slot,
        second_operation,
        [first.assertion_to_append],
        assertion_id="assertion-second",
    )
    assert second.projected_slot.status is FactStatus.DISPUTED
    assert second.resolution.requires_clarification is True


def test_low_confidence_operation_is_dropped_by_explicit_policy() -> None:
    operation = make_bound(FactOpKind.AFFIRM, confidence=0.49)
    result = resolve(make_slot(FactStatus.UNSET), operation)
    assert result.projected_slot.status is FactStatus.UNSET
    assert result.resolution.decision == "reject"
    assert result.resolution.reason_code == "fact.op.low_confidence.v1"
    assert result.assertion_to_append is None


@pytest.mark.parametrize("operation", [FactOpKind.NEGATE, FactOpKind.REPORT_UNKNOWN])
def test_negate_and_report_unknown_never_create_present_from_unset(operation: FactOpKind) -> None:
    result = resolve(make_slot(FactStatus.UNSET), make_bound(operation))
    assert result.projected_slot.status is not FactStatus.PRESENT


def test_resolver_does_not_mutate_inputs() -> None:
    prior = make_assertion("assertion-old", FactStatus.PRESENT)
    slot = make_slot(FactStatus.PRESENT, [prior.assertion_id])
    operation = make_bound(FactOpKind.NEGATE)
    slot_before = slot.model_dump_json()
    operation_before = operation.model_dump_json()
    assertion_before = prior.model_dump_json()
    resolve(slot, operation, [prior])
    assert slot.model_dump_json() == slot_before
    assert operation.model_dump_json() == operation_before
    assert prior.model_dump_json() == assertion_before


def test_reason_codes_are_deterministic() -> None:
    operation = make_bound(FactOpKind.AFFIRM, confidence=0.1)
    first = resolve(make_slot(FactStatus.UNSET), operation, assertion_id="one")
    second = resolve(make_slot(FactStatus.UNSET), operation, assertion_id="two")
    assert first.resolution.reason_code == second.resolution.reason_code == "fact.op.low_confidence.v1"


def test_owner_approved_policy_constants_are_inspectable() -> None:
    assert DISPUTED_FACT_POLICY is DisputedFactPolicy.EXCLUDE_FROM_GUIDANCE_AND_CLARIFY
    assert DISPUTED_FACT_POLICY.value == "EXCLUDE_FROM_GUIDANCE_AND_CLARIFY"
    assert COUNTERPARTY_CLAIM_POLICY is CounterpartyClaimPolicy.DO_NOT_OVERWRITE_USER_SNAPSHOT
    assert COUNTERPARTY_CLAIM_POLICY.value == "DO_NOT_OVERWRITE_USER_SNAPSHOT"


def test_nested_values_and_provenance_are_deeply_separated() -> None:
    evidence = PaymentEvidenceValue(
        method="bank_transfer",
        has_document=True,
        evidence_ref_ids=["ev-1"],
    )
    effective = DateValue(granularity="unspecified", iso=None, as_written="hôm nay")
    operation = make_bound(
        FactOpKind.AFFIRM,
        slot="payment_evidence_exists",
        value=evidence,
        effective_from=None,
    )
    operation = operation.model_copy(
        update={
            "unbound": operation.unbound.model_copy(
                update={"effective_from": effective}, deep=True
            )
        },
        deep=True,
    )
    input_slot = FactSlot[FactValue](
        status=FactStatus.UNSET,
        assertion_ids=["prior"],
        counter_claims=["counter-prior"],
    )
    result = resolve(input_slot, operation, assertion_id="assertion-new")
    emitted = result.assertion_to_append
    assert emitted is not None
    projected_value = result.projected_slot.value
    assert projected_value is not None
    assert operation.unbound.value is not projected_value
    assert operation.unbound.value is not emitted.value
    assert projected_value is not emitted.value
    assert operation.unbound.anchor is not emitted.anchor
    assert operation.unbound.effective_from is not result.projected_slot.effective_from
    assert operation.unbound.effective_from is not emitted.effective_from
    assert result.projected_slot.assertion_ids is not input_slot.assertion_ids
    assert result.projected_slot.counter_claims is not input_slot.counter_claims

    before_operation = operation.unbound.value.model_dump_json()
    before_emitted = emitted.value.model_dump_json()
    before_projected = projected_value.model_dump_json()
    operation.unbound.value.evidence_ref_ids.append("operation-only")
    assert emitted.value.model_dump_json() == before_emitted
    assert projected_value.model_dump_json() == before_projected
    emitted.value.evidence_ref_ids.append("assertion-only")
    assert operation.unbound.value.model_dump_json() != before_operation
    assert projected_value.model_dump_json() == before_projected
    projected_value.evidence_ref_ids.append("projection-only")
    assert emitted.value.model_dump_json() != before_emitted
    assert "projection-only" not in emitted.value.evidence_ref_ids
    assert input_slot.assertion_ids == ["prior"]
    assert input_slot.counter_claims == ["counter-prior"]


@pytest.mark.parametrize("claimant", [Claimant.COUNTERPARTY, Claimant.AUTHORITY])
@pytest.mark.parametrize(
    "status",
    [FactStatus.UNSET, FactStatus.PRESENT, FactStatus.ABSENT, FactStatus.DISPUTED],
)
def test_non_user_epistemic_reports_are_retained_without_mutating_user_snapshot(
    claimant: Claimant, status: FactStatus
) -> None:
    current = make_slot(status, ["existing"] if status is not FactStatus.UNSET else [])
    current_before = current.model_dump_json()
    operation = make_bound(
        FactOpKind.REPORT_UNKNOWN,
        claimant=claimant,
        epistemic=Epistemic.USER_UNKNOWN,
    )
    result = resolve(current, operation)

    # Invariants that must hold for every USER slot state: no exception was
    # raised (pytest would already have failed above if one had been), the
    # projected slot is a distinct deep copy, status/value/USER epistemic are
    # unchanged, the external claimant is retained (never relabelled as the
    # USER), and the input slot itself was never mutated.
    assert result.projected_slot is not current
    assert result.projected_slot.model_dump_json() == current_before
    assert result.projected_slot.status is status
    assert result.projected_slot.value == current.value
    assert result.projected_slot.claimant == current.claimant
    assert result.projected_slot.epistemic is current.epistemic
    assert result.resolution.resulting_status is status
    assert result.assertion_to_append is None
    assert result.epistemic_note_to_append is not None
    assert result.epistemic_note_to_append.claimant is claimant
    assert result.epistemic_note_to_append.claimant is not Claimant.USER
    assert result.epistemic_note_to_append.epistemic is Epistemic.USER_UNKNOWN
    assert result.resolution.reason_code == "fact.external_epistemic_note.v1"
    assert current.model_dump_json() == current_before

    if status is FactStatus.DISPUTED:
        # An already-disputed USER slot already requires clarification by
        # construction (`FactSlot.validate_state`); external uncertainty must
        # carry that existing requirement forward, never clear it, and the
        # resolution must stay valid-by-construction against
        # `FactConflictResolution.disputed_guidance_is_excluded`.
        assert current.pending_clarification is True
        assert result.projected_slot.pending_clarification is True
        assert result.resolution.requires_clarification is True
        assert result.resolution.guidance_status is None
    else:
        # External uncertainty must never manufacture a new clarification
        # requirement on its own for a non-disputed USER slot.
        assert result.resolution.requires_clarification is False


@pytest.mark.parametrize("claimant", [Claimant.COUNTERPARTY, Claimant.AUTHORITY])
@pytest.mark.parametrize("status", [FactStatus.PRESENT, FactStatus.ABSENT])
def test_non_user_epistemic_report_preserves_pre_existing_reconfirmation_clarification(
    claimant: Claimant, status: FactStatus
) -> None:
    """A non-USER REPORT_UNKNOWN must preserve, not clear, a clarification
    requirement that already exists for another reason (an earlier USER-owned
    REPORT_UNKNOWN sets `reconfirmation_needed`/`pending_clarification` on a
    PRESENT/ABSENT slot; see the resolver's USER REPORT_UNKNOWN branch)."""
    current = make_slot(status, ["existing"])
    current.reconfirmation_needed = True
    current.pending_clarification = True
    current_before = current.model_dump_json()
    operation = make_bound(
        FactOpKind.REPORT_UNKNOWN,
        claimant=claimant,
        epistemic=Epistemic.USER_UNKNOWN,
    )
    result = resolve(current, operation)
    assert result.projected_slot.model_dump_json() == current_before
    assert result.projected_slot.pending_clarification is True
    assert result.resolution.requires_clarification is True
    assert result.resolution.resulting_status is status


@pytest.mark.parametrize("claimant", [Claimant.COUNTERPARTY, Claimant.AUTHORITY])
def test_regression_non_user_report_unknown_against_disputed_no_longer_raises(
    claimant: Claimant,
) -> None:
    """Reproduces the exact HIGH-2 defect from
    VIETLAW_SEMANTIC_FACT_PHASE_A1_REVERIFICATION_V1.md: a non-USER
    REPORT_UNKNOWN against an already-DISPUTED USER slot previously raised an
    uncaught pydantic ValidationError ('DISPUTED facts must be excluded from
    guidance and clarified'), because `requires_clarification` was hard-coded
    to `False` while `resulting_status` stayed `DISPUTED`. Both COUNTERPARTY
    and AUTHORITY must behave identically."""
    current = make_slot(FactStatus.DISPUTED, ["assertion-a", "assertion-b"])
    operation = make_bound(
        FactOpKind.REPORT_UNKNOWN,
        claimant=claimant,
        epistemic=Epistemic.USER_UNKNOWN,
    )
    result = resolve(current, operation)
    assert result.resolution.resulting_status is FactStatus.DISPUTED
    assert result.resolution.requires_clarification is True
    assert result.resolution.guidance_status is None
    assert result.projected_slot.status is FactStatus.DISPUTED
    assert result.projected_slot.pending_clarification is True
    assert result.epistemic_note_to_append is not None
    assert result.epistemic_note_to_append.claimant is claimant


@pytest.mark.parametrize("status", [FactStatus.PRESENT, FactStatus.ABSENT])
def test_counterparty_first_and_user_first_have_same_contested_semantics(status: FactStatus) -> None:
    external_operation = make_bound(
        FactOpKind.NEGATE if status is FactStatus.PRESENT else FactOpKind.AFFIRM,
        claimant=Claimant.COUNTERPARTY,
        request_id="counter-request",
    )
    user_operation = make_bound(
        FactOpKind.AFFIRM if status is FactStatus.PRESENT else FactOpKind.NEGATE,
        request_id="user-request",
    )
    external = resolve(make_slot(FactStatus.UNSET), external_operation, assertion_id="counter-1")
    assert external.assertion_to_append is not None
    first_external = resolve(
        external.projected_slot,
        user_operation,
        [external.assertion_to_append],
        assertion_id="user-1",
    )
    user = resolve(make_slot(FactStatus.UNSET), user_operation, assertion_id="user-2")
    assert user.assertion_to_append is not None
    first_user = resolve(
        user.projected_slot,
        external_operation.model_copy(
            update={
                "request_id": "counter-request-2",
                "unbound": external_operation.unbound.model_copy(update={"op_index": 1}),
            },
            deep=True,
        ),
        [user.assertion_to_append],
        assertion_id="counter-2",
    )
    assert first_external.projected_slot.status is first_user.projected_slot.status is status
    assert first_external.projected_slot.claimant is first_user.projected_slot.claimant is Claimant.USER
    assert first_external.projected_slot.verification is first_user.projected_slot.verification is VerificationStatus.CONTESTED
    assert first_external.resolution.requires_clarification is first_user.resolution.requires_clarification is False


def test_agreeing_claims_are_corrobated_in_both_orders() -> None:
    external_operation = make_bound(
        FactOpKind.AFFIRM,
        claimant=Claimant.COUNTERPARTY,
        request_id="counter-request",
    )
    user_operation = make_bound(FactOpKind.AFFIRM, request_id="user-request")
    external = resolve(make_slot(FactStatus.UNSET), external_operation, assertion_id="counter-1")
    first_external = resolve(
        external.projected_slot,
        user_operation,
        [external.assertion_to_append] if external.assertion_to_append else [],
        assertion_id="user-1",
    )
    user = resolve(make_slot(FactStatus.UNSET), user_operation, assertion_id="user-2")
    first_user = resolve(
        user.projected_slot,
        external_operation.model_copy(
            update={
                "request_id": "counter-request-2",
                "unbound": external_operation.unbound.model_copy(update={"op_index": 1}),
            },
            deep=True,
        ),
        [user.assertion_to_append] if user.assertion_to_append else [],
        assertion_id="counter-2",
    )
    assert first_external.projected_slot.verification is first_user.projected_slot.verification is VerificationStatus.CORROBORATED


@pytest.mark.parametrize("target", [FactStatus.PRESENT, FactStatus.ABSENT])
def test_correction_resolves_disputed_symmetrically(target: FactStatus) -> None:
    first = make_assertion("assertion-present", FactStatus.PRESENT, request_id="request-a")
    second = make_assertion("assertion-absent", FactStatus.ABSENT, request_id="request-b")
    operation = make_bound(FactOpKind.CORRECT, claimed_status=target)
    result = resolve(
        make_slot(FactStatus.DISPUTED, [first.assertion_id, second.assertion_id]),
        operation,
        [first, second],
    )
    assert result.projected_slot.status is target
    assert result.projected_slot.pending_clarification is False
    assert result.resolution.change_type is ChangeType.CORRECTION
    assert result.resolution.reason_code == "fact.dispute.corrected.v1"
    assert {item.assertion_id for item in result.resolution.supersessions} == {
        first.assertion_id,
        second.assertion_id,
    }
    assert all(item.reason == "correction" for item in result.resolution.supersessions)


def test_required_bound_issue_type_rejects_bogus_and_cross_issue_slots() -> None:
    with pytest.raises(ValidationError):
        make_bound(
            FactOpKind.REPORT_UNKNOWN,
            issue_type_hint=None,
            slot="totally_bogus_slot",
        )
    with pytest.raises(ValidationError):
        BoundFactOperation(
            unbound=make_bound(FactOpKind.REPORT_UNKNOWN).unbound,
            episode_id="episode-1",
            slot="written_agreement_exists",
            resolver_version="resolver-v1",
            request_id="request-1",
        )
    with pytest.raises(ValidationError):
        make_bound(
            FactOpKind.REPORT_UNKNOWN,
            issue_type_hint="rental_deposit",
            bound_issue_type="personal_loan",
        )
    with pytest.raises(ValidationError):
        make_bound(
            FactOpKind.AFFIRM,
            slot="principal_amount",
            issue_type_hint=None,
            bound_issue_type="rental_deposit",
            value=MoneyAmount(amount_vnd=1, as_written="1"),
        )


def test_duplicate_assertion_id_is_structured_rejection() -> None:
    prior = make_assertion("assertion-old", FactStatus.PRESENT)
    result = resolve(
        make_slot(FactStatus.PRESENT, [prior.assertion_id]),
        make_bound(FactOpKind.NEGATE),
        [prior],
        assertion_id="assertion-old",
    )
    assert result.resolution.decision == "reject"
    assert result.resolution.reason_code == "fact.assertion_id.duplicate.v1"
    assert result.assertion_to_append is None
