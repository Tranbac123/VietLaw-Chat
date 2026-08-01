"""Pure deterministic conflict resolution for structured semantic fact operations."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TypeVar

from ..contracts.internal import StrictModel
from ..contracts.legal_facts import (
    FACT_OPERATION_CONFIDENCE_FLOOR,
    AssertionSupersession,
    BoundFactOperation,
    ChangeType,
    Claimant,
    Epistemic,
    FactApplyResult,
    FactAssertion,
    FactConflictResolution,
    FactEpistemicNote,
    FactOpKind,
    FactSlot,
    FactStatus,
    FactValue,
    VerificationStatus,
    claimed_status_for_operation,
)


ModelT = TypeVar("ModelT", bound=StrictModel)


def _clone(model: ModelT) -> ModelT:
    """Clone one structured contract before it crosses a projection boundary."""

    return model.model_copy(deep=True)


def _guidance_status(status: FactStatus) -> FactStatus | None:
    return status if status in {FactStatus.PRESENT, FactStatus.ABSENT} else None


def _unchanged_change_type(slot: FactSlot[FactValue]) -> ChangeType:
    return slot.last_change_type or ChangeType.INITIAL


def _resolution(
    *,
    slot_name: str,
    current: FactSlot[FactValue],
    incoming_status: FactStatus | None,
    incoming_claimant: Claimant,
    decision: str,
    resulting_status: FactStatus,
    change_type: ChangeType,
    requires_clarification: bool,
    reason_code: str,
    supersessions: Sequence[AssertionSupersession] = (),
) -> FactConflictResolution:
    return FactConflictResolution(
        slot=slot_name,
        prior_status=current.status,
        incoming_status=incoming_status,
        prior_claimant=current.claimant,
        incoming_claimant=incoming_claimant,
        decision=decision,
        resulting_status=resulting_status,
        change_type=change_type,
        requires_clarification=requires_clarification,
        guidance_status=_guidance_status(resulting_status),
        reason_code=reason_code,
        supersessions=list(supersessions),
    )


def _assertion(
    operation: BoundFactOperation,
    *,
    assertion_id: str,
    observed_at: datetime,
    registry_version: str,
    status: FactStatus,
    change_type: ChangeType,
    reason_code: str,
) -> FactAssertion:
    unbound = operation.unbound
    value = unbound.value if status is FactStatus.PRESENT else None
    return FactAssertion(
        assertion_id=assertion_id,
        episode_id=operation.episode_id,
        slot=operation.slot,
        status_claimed=status,
        value=_clone(value) if value is not None else None,
        claimant=unbound.claimant,
        verification=VerificationStatus.UNVERIFIED,
        epistemic=unbound.epistemic,
        change_type=change_type,
        observed_at=observed_at,
        effective_from=_clone(unbound.effective_from) if unbound.effective_from is not None else None,
        effective_to=_clone(unbound.effective_to) if unbound.effective_to is not None else None,
        anchor=_clone(unbound.anchor),
        message_id=unbound.anchor.message_id,
        request_id=operation.request_id,
        op_index=unbound.op_index,
        extractor_version=unbound.extractor_version,
        resolver_version=operation.resolver_version,
        registry_version=registry_version,
        reason_code=reason_code,
    )


def _epistemic_note(
    operation: BoundFactOperation,
    *,
    note_id: str,
    observed_at: datetime,
    registry_version: str,
) -> FactEpistemicNote:
    unbound = operation.unbound
    if unbound.epistemic not in {Epistemic.USER_UNKNOWN, Epistemic.USER_UNSURE}:
        raise ValueError("epistemic operation lacks a reportable epistemic state")
    return FactEpistemicNote(
        note_id=note_id,
        episode_id=operation.episode_id,
        slot=operation.slot,
        epistemic=unbound.epistemic,
        claimant=unbound.claimant,
        observed_at=observed_at,
        anchor=_clone(unbound.anchor),
        message_id=unbound.anchor.message_id,
        request_id=operation.request_id,
        op_index=unbound.op_index,
        extractor_version=unbound.extractor_version,
        resolver_version=operation.resolver_version,
        registry_version=registry_version,
    )


def _is_duplicate(
    operation: BoundFactOperation,
    assertions: Sequence[FactAssertion],
    notes: Sequence[FactEpistemicNote],
) -> bool:
    identity = (
        operation.request_id,
        operation.episode_id,
        operation.slot,
        operation.unbound.op_index,
    )
    assertion_identities = {
        (item.request_id, item.episode_id, item.slot, item.op_index) for item in assertions
    }
    note_identities = {(item.request_id, item.episode_id, item.slot, item.op_index) for item in notes}
    return identity in assertion_identities or identity in note_identities


def _last_live_user_assertion(
    current: FactSlot[FactValue], assertions: Sequence[FactAssertion]
) -> FactAssertion | None:
    active_ids = set(current.assertion_ids)
    for assertion in reversed(assertions):
        if (
            assertion.assertion_id in active_ids
            and assertion.claimant is Claimant.USER
            and assertion.superseded_by is None
        ):
            return assertion
    return None


def _live_external_assertions(
    current: FactSlot[FactValue], assertions: Sequence[FactAssertion]
) -> list[FactAssertion]:
    active_ids = set(current.counter_claims)
    return [
        assertion
        for assertion in assertions
        if assertion.claimant is not Claimant.USER
        and assertion.superseded_by is None
        and (not active_ids or assertion.assertion_id in active_ids)
    ]


def _verification_for_user_claim(
    status: FactStatus,
    external_assertions: Sequence[FactAssertion],
) -> VerificationStatus:
    if not external_assertions:
        return VerificationStatus.UNVERIFIED
    if all(assertion.status_claimed is status for assertion in external_assertions):
        return VerificationStatus.CORROBORATED
    return VerificationStatus.CONTESTED


def _supersessions(
    current: FactSlot[FactValue],
    assertions: Sequence[FactAssertion],
    *,
    superseded_by: str,
    reason: str,
    all_live: bool,
) -> list[AssertionSupersession]:
    active_ids = set(current.assertion_ids)
    candidates = [
        assertion
        for assertion in assertions
        if assertion.assertion_id in active_ids
        and assertion.claimant is Claimant.USER
        and assertion.superseded_by is None
    ]
    if not all_live:
        last = _last_live_user_assertion(current, assertions)
        candidates = [] if last is None else [last]
    return [
        AssertionSupersession(
            assertion_id=assertion.assertion_id,
            superseded_by=superseded_by,
            reason=reason,
        )
        for assertion in candidates
    ]


def _no_change_result(
    current: FactSlot[FactValue],
    operation: BoundFactOperation,
    *,
    incoming_status: FactStatus | None,
    decision: str,
    reason_code: str,
) -> FactApplyResult:
    projected = current.model_copy(deep=True)
    return FactApplyResult(
        projected_slot=projected,
        resolution=_resolution(
            slot_name=operation.slot,
            current=current,
            incoming_status=incoming_status,
            incoming_claimant=operation.unbound.claimant,
            decision=decision,
            resulting_status=current.status,
            change_type=_unchanged_change_type(current),
            requires_clarification=current.pending_clarification,
            reason_code=reason_code,
        ),
    )


def resolve_fact_operation(
    current_slot: FactSlot[FactValue],
    incoming_bound_operation: BoundFactOperation,
    existing_assertions: Sequence[FactAssertion],
    assertion_id: str,
    observed_at: datetime,
    registry_version: str,
    existing_epistemic_notes: Sequence[FactEpistemicNote] = (),
) -> FactApplyResult:
    """Project one structured operation without mutating inputs or accessing I/O."""

    current = current_slot.model_copy(deep=True)
    operation = incoming_bound_operation
    unbound = operation.unbound
    incoming_status = claimed_status_for_operation(unbound)

    if _is_duplicate(operation, existing_assertions, existing_epistemic_notes):
        return _no_change_result(
            current,
            operation,
            incoming_status=incoming_status,
            decision="no_op",
            reason_code="fact.op.duplicate.v1",
        )

    if assertion_id in current.assertion_ids or any(
        assertion.assertion_id == assertion_id for assertion in existing_assertions
    ):
        return _no_change_result(
            current,
            operation,
            incoming_status=incoming_status,
            decision="reject",
            reason_code="fact.assertion_id.duplicate.v1",
        )

    if unbound.confidence < FACT_OPERATION_CONFIDENCE_FLOOR:
        return _no_change_result(
            current,
            operation,
            incoming_status=incoming_status,
            decision="reject",
            reason_code="fact.op.low_confidence.v1",
        )

    if unbound.op is FactOpKind.REPORT_UNKNOWN and unbound.claimant is not Claimant.USER:
        note = _epistemic_note(
            operation,
            note_id=assertion_id,
            observed_at=observed_at,
            registry_version=registry_version,
        )
        return FactApplyResult(
            projected_slot=current.model_copy(deep=True),
            resolution=_resolution(
                slot_name=operation.slot,
                current=current,
                incoming_status=None,
                incoming_claimant=unbound.claimant,
                decision="apply",
                resulting_status=current.status,
                change_type=ChangeType.EPISTEMIC_NOTE,
                requires_clarification=current.pending_clarification,
                reason_code="fact.external_epistemic_note.v1",
            ),
            epistemic_note_to_append=note,
        )

    if unbound.op is FactOpKind.REPORT_UNKNOWN:
        projected = current.model_copy(deep=True)
        projected.epistemic = unbound.epistemic
        projected.last_change_type = ChangeType.EPISTEMIC_NOTE
        if projected.status in {FactStatus.PRESENT, FactStatus.ABSENT}:
            projected.reconfirmation_needed = True
            projected.pending_clarification = True
        note = _epistemic_note(
            operation,
            note_id=assertion_id,
            observed_at=observed_at,
            registry_version=registry_version,
        )
        return FactApplyResult(
            projected_slot=projected,
            resolution=_resolution(
                slot_name=operation.slot,
                current=current,
                incoming_status=None,
                incoming_claimant=unbound.claimant,
                decision="apply",
                resulting_status=projected.status,
                change_type=ChangeType.EPISTEMIC_NOTE,
                requires_clarification=projected.pending_clarification,
                reason_code="fact.epistemic_note.v1",
            ),
            epistemic_note_to_append=note,
        )

    if incoming_status is None:
        return _no_change_result(
            current,
            operation,
            incoming_status=None,
            decision="reject",
            reason_code="fact.op.missing_claimed_status.v1",
        )

    if unbound.claimant is not Claimant.USER:
        assertion = _assertion(
            operation,
            assertion_id=assertion_id,
            observed_at=observed_at,
            registry_version=registry_version,
            status=incoming_status,
            change_type=ChangeType.INITIAL,
            reason_code="fact.external_claim.v1",
        )
        projected = current.model_copy(deep=True)
        projected.counter_claims = [*projected.counter_claims, assertion_id]
        if current.status in {FactStatus.PRESENT, FactStatus.ABSENT} and current.claimant is Claimant.USER:
            external_claims = [*_live_external_assertions(current, existing_assertions), assertion]
            projected.verification = _verification_for_user_claim(current.status, external_claims)
            reason_code = (
                "fact.external_claim.corroborates.v1"
                if projected.verification is VerificationStatus.CORROBORATED
                else "fact.external_claim.contests.v1"
            )
            decision = "contest"
        else:
            reason_code = "fact.external_claim.no_user_snapshot.v1"
            decision = "apply"
        return FactApplyResult(
            projected_slot=projected,
            resolution=_resolution(
                slot_name=operation.slot,
                current=current,
                incoming_status=incoming_status,
                incoming_claimant=unbound.claimant,
                decision=decision,
                resulting_status=projected.status,
                change_type=ChangeType.INITIAL,
                requires_clarification=projected.pending_clarification,
                reason_code=reason_code,
            ),
            assertion_to_append=assertion,
        )

    is_correction = unbound.op is FactOpKind.CORRECT or "correction" in unbound.change_markers
    is_transition = unbound.op is FactOpKind.TRANSITION or "temporal" in unbound.change_markers

    if current.status is FactStatus.DISPUTED and not (
        unbound.op is FactOpKind.RESOLVE_DISPUTE or is_correction
    ):
        return _no_change_result(
            current,
            operation,
            incoming_status=incoming_status,
            decision="clarify",
            reason_code="fact.dispute.requires_explicit_resolution.v1",
        )

    if unbound.op is FactOpKind.RESOLVE_DISPUTE:
        if current.status is not FactStatus.DISPUTED:
            return _no_change_result(
                current,
                operation,
                incoming_status=incoming_status,
                decision="reject",
                reason_code="fact.dispute.not_open.v1",
            )
        assertion = _assertion(
            operation,
            assertion_id=assertion_id,
            observed_at=observed_at,
            registry_version=registry_version,
            status=incoming_status,
            change_type=ChangeType.DISPUTE_RESOLVED,
            reason_code="fact.dispute.resolved.v1",
        )
        supersessions = _supersessions(
            current,
            existing_assertions,
            superseded_by=assertion_id,
            reason="dispute_resolved",
            all_live=True,
        )
        projected = current.model_copy(
            update={
                "status": incoming_status,
                "value": _clone(unbound.value) if incoming_status is FactStatus.PRESENT and unbound.value else None,
                "claimant": Claimant.USER,
                "epistemic": unbound.epistemic,
                "effective_from": _clone(unbound.effective_from) if unbound.effective_from else None,
                "last_change_type": ChangeType.DISPUTE_RESOLVED,
                "pending_clarification": False,
                "reconfirmation_needed": False,
                "assertion_ids": [*current.assertion_ids, assertion_id],
            },
            deep=True,
        )
        return FactApplyResult(
            projected_slot=projected,
            resolution=_resolution(
                slot_name=operation.slot,
                current=current,
                incoming_status=incoming_status,
                incoming_claimant=unbound.claimant,
                decision="supersede",
                resulting_status=incoming_status,
                change_type=ChangeType.DISPUTE_RESOLVED,
                requires_clarification=False,
                reason_code="fact.dispute.resolved.v1",
                supersessions=supersessions,
            ),
            assertion_to_append=assertion,
        )

    if current.status is FactStatus.UNSET:
        assertion = _assertion(
            operation,
            assertion_id=assertion_id,
            observed_at=observed_at,
            registry_version=registry_version,
            status=incoming_status,
            change_type=ChangeType.INITIAL,
            reason_code="fact.initial.v1",
        )
        projected = current.model_copy(
            update={
                "status": incoming_status,
                "value": _clone(unbound.value) if incoming_status is FactStatus.PRESENT and unbound.value else None,
                "claimant": Claimant.USER,
                "verification": _verification_for_user_claim(
                    incoming_status,
                    _live_external_assertions(current, existing_assertions),
                ),
                "epistemic": unbound.epistemic,
                "effective_from": _clone(unbound.effective_from) if unbound.effective_from else None,
                "last_change_type": ChangeType.INITIAL,
                "pending_clarification": False,
                "reconfirmation_needed": False,
                "assertion_ids": [*current.assertion_ids, assertion_id],
            },
            deep=True,
        )
        return FactApplyResult(
            projected_slot=projected,
            resolution=_resolution(
                slot_name=operation.slot,
                current=current,
                incoming_status=incoming_status,
                incoming_claimant=unbound.claimant,
                decision="apply",
                resulting_status=incoming_status,
                change_type=ChangeType.INITIAL,
                requires_clarification=False,
                reason_code="fact.initial.v1",
            ),
            assertion_to_append=assertion,
        )

    same_value = unbound.value is None or current.value == unbound.value
    if current.status is incoming_status and same_value:
        return _no_change_result(
            current,
            operation,
            incoming_status=incoming_status,
            decision="no_op",
            reason_code="fact.op.idempotent_reaffirmation.v1",
        )

    if is_transition and unbound.effective_from is None:
        return _no_change_result(
            current,
            operation,
            incoming_status=incoming_status,
            decision="reject",
            reason_code="fact.transition.effective_time_required.v1",
        )

    if is_correction or is_transition:
        change_type = ChangeType.CORRECTION if is_correction else ChangeType.STATE_TRANSITION
        supersession_reason = "correction" if is_correction else "state_transition"
        if is_correction and current.status is FactStatus.DISPUTED:
            reason_code = "fact.dispute.corrected.v1"
        else:
            reason_code = "fact.correction.v1" if is_correction else "fact.state_transition.v1"
        assertion = _assertion(
            operation,
            assertion_id=assertion_id,
            observed_at=observed_at,
            registry_version=registry_version,
            status=incoming_status,
            change_type=change_type,
            reason_code=reason_code,
        )
        supersessions = _supersessions(
            current,
            existing_assertions,
            superseded_by=assertion_id,
            reason=supersession_reason,
            all_live=current.status is FactStatus.DISPUTED,
        )
        projected = current.model_copy(
            update={
                "status": incoming_status,
                "value": _clone(unbound.value) if incoming_status is FactStatus.PRESENT and unbound.value else None,
                "claimant": Claimant.USER,
                "epistemic": unbound.epistemic,
                "effective_from": _clone(unbound.effective_from) if unbound.effective_from else None,
                "last_change_type": change_type,
                "pending_clarification": False,
                "reconfirmation_needed": False,
                "assertion_ids": [*current.assertion_ids, assertion_id],
            },
            deep=True,
        )
        return FactApplyResult(
            projected_slot=projected,
            resolution=_resolution(
                slot_name=operation.slot,
                current=current,
                incoming_status=incoming_status,
                incoming_claimant=unbound.claimant,
                decision="supersede",
                resulting_status=incoming_status,
                change_type=change_type,
                requires_clarification=False,
                reason_code=reason_code,
                supersessions=supersessions,
            ),
            assertion_to_append=assertion,
        )

    assertion = _assertion(
        operation,
        assertion_id=assertion_id,
        observed_at=observed_at,
        registry_version=registry_version,
        status=incoming_status,
        change_type=ChangeType.CONTRADICTION,
        reason_code="fact.contradiction.disputed.v1",
    )
    projected = current.model_copy(
        update={
            "status": FactStatus.DISPUTED,
            "value": None,
            "claimant": Claimant.USER,
            "last_change_type": ChangeType.CONTRADICTION,
            "pending_clarification": True,
            "reconfirmation_needed": False,
            "assertion_ids": [*current.assertion_ids, assertion_id],
        },
        deep=True,
    )
    return FactApplyResult(
        projected_slot=projected,
        resolution=_resolution(
            slot_name=operation.slot,
            current=current,
            incoming_status=incoming_status,
            incoming_claimant=unbound.claimant,
            decision="dispute",
            resulting_status=FactStatus.DISPUTED,
            change_type=ChangeType.CONTRADICTION,
            requires_clarification=True,
            reason_code="fact.contradiction.disputed.v1",
        ),
        assertion_to_append=assertion,
    )
