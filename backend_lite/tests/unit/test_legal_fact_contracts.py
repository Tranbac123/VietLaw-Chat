from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, get_args
import unicodedata

import pytest
from pydantic import TypeAdapter, ValidationError

from backend_lite.app.contracts.legal_facts import (
    CASE_EVIDENCE_KINDS,
    LEGAL_AUTHORITY_KINDS,
    BoundFactOperation,
    CaseEvidenceItem,
    ChangeType,
    Claimant,
    DateRange,
    DateValue,
    DocumentRef,
    EpisodeFacts,
    Epistemic,
    EvidenceSourceKind,
    ExistenceValue,
    FactApplyResult,
    FactAssertion,
    FactConflictResolution,
    FactOpKind,
    FactSlot,
    FactStatus,
    FactValue,
    LegalAuthorityReference,
    MoneyAmount,
    PartyRef,
    PaymentEvidenceValue,
    PersonalLoanFacts,
    RentalDepositFacts,
    TextAnchor,
    TextNormalization,
    UnboundFactOperation,
    VerificationStatus,
    validate_signature_dependency,
    validate_text_anchor,
    project_episode_fact_slot,
)


ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)


def anchor(quote: str = "có giấy", start: int = 0) -> TextAnchor:
    return TextAnchor(message_id="message-1", start=start, end=start + len(quote), quote=quote)


def unbound(**updates: object) -> UnboundFactOperation:
    values: dict[str, object] = {
        "op": FactOpKind.AFFIRM,
        "slot_hint": "written_agreement_exists",
        "issue_type_hint": "rental_deposit",
        "value": ExistenceValue(),
        "anchor": anchor(),
        "extractor_version": "extractor-v1",
        "confidence": 0.9,
        "op_index": 0,
    }
    values.update(updates)
    return UnboundFactOperation(**values)


def assertion(**updates: object) -> FactAssertion:
    values: dict[str, object] = {
        "assertion_id": "assertion-1",
        "episode_id": "episode-1",
        "slot": "written_agreement_exists",
        "status_claimed": FactStatus.PRESENT,
        "value": ExistenceValue(),
        "claimant": Claimant.USER,
        "verification": VerificationStatus.UNVERIFIED,
        "change_type": ChangeType.INITIAL,
        "observed_at": NOW,
        "anchor": anchor(),
        "message_id": "message-1",
        "request_id": "request-1",
        "op_index": 0,
        "extractor_version": "extractor-v1",
        "resolver_version": "resolver-v1",
        "registry_version": "registry-v1",
        "reason_code": "fact.initial.v1",
    }
    values.update(updates)
    return FactAssertion(**values)


def test_fact_status_has_exact_states_and_unknown_is_epistemic() -> None:
    assert {item.name for item in FactStatus} == {"UNSET", "PRESENT", "ABSENT", "DISPUTED"}
    assert "UNKNOWN" not in FactStatus.__members__
    assert Epistemic.USER_UNKNOWN.value == "user_unknown"


def test_strict_models_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        MoneyAmount(amount_vnd=20_000_000, as_written="20 triệu", extra_field=True)


@pytest.mark.parametrize("invalid", [20.0, "20", True])
def test_money_amount_requires_strict_integer_vnd(invalid: object) -> None:
    with pytest.raises(ValidationError):
        MoneyAmount(amount_vnd=invalid, as_written="20")


def test_money_amount_is_non_negative_bounded_and_retains_written_form() -> None:
    amount = MoneyAmount(amount_vnd=20_000_000, precision="approx", as_written="khoảng 20 triệu")
    assert amount.amount_vnd == 20_000_000
    assert amount.precision == "approx"
    with pytest.raises(ValidationError):
        MoneyAmount(amount_vnd=-1, as_written="âm một đồng")
    with pytest.raises(ValidationError):
        MoneyAmount(amount_vnd=10**13 + 1, as_written="quá lớn")


def test_dates_keep_written_form_and_do_not_invent_iso() -> None:
    relative = DateValue(granularity="unspecified", iso=None, as_written="hôm qua")
    assert relative.iso is None
    with pytest.raises(ValidationError):
        DateValue(granularity="unspecified", iso="2026-07-21", as_written="hôm qua")
    assert DateRange(start=relative).start == relative


def test_fact_value_union_is_discriminated_and_rejects_bad_shapes() -> None:
    adapter = TypeAdapter(FactValue)
    parsed = adapter.validate_python(
        {"kind": "payment_evidence", "method": "bank_transfer", "has_document": True}
    )
    assert isinstance(parsed, PaymentEvidenceValue)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "money", "role": "landlord"})
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "made_up"})


def test_typed_slots_reject_cross_slot_values_and_boolean_escape_hatches() -> None:
    with pytest.raises(ValidationError):
        RentalDepositFacts(
            deposit_amount=FactSlot[PartyRef](
                status=FactStatus.PRESENT,
                claimant=Claimant.USER,
                value=PartyRef(role="landlord"),
            )
        )
    with pytest.raises(ValidationError):
        FactSlot[ExistenceValue](status=FactStatus.PRESENT, claimant=Claimant.USER, value=True)
    with pytest.raises(ValidationError):
        FactSlot[ExistenceValue](
            status=FactStatus.PRESENT,
            claimant=Claimant.USER,
            value={"kind": "existence", "unexpected": True},
        )


def test_bound_operation_validates_slot_value_shape() -> None:
    invalid = unbound(
        slot_hint="deposit_amount",
        value=PartyRef(role="landlord", identified=True),
    )
    with pytest.raises(ValidationError):
        BoundFactOperation(
            unbound=invalid,
            episode_id="episode-1",
            bound_issue_type="rental_deposit",
            slot="deposit_amount",
            resolver_version="resolver-v1",
            request_id="request-1",
        )


@pytest.mark.parametrize("invalid_status", [FactStatus.UNSET, FactStatus.DISPUTED])
def test_fact_assertion_only_allows_present_or_absent(invalid_status: FactStatus) -> None:
    with pytest.raises(ValidationError):
        assertion(status_claimed=invalid_status, value=None)


def test_verified_is_rejected_in_mvp_assertion_path() -> None:
    with pytest.raises(ValidationError):
        assertion(verification=VerificationStatus.VERIFIED)


def test_verified_is_rejected_in_slot_and_case_evidence_paths() -> None:
    with pytest.raises(ValidationError):
        FactSlot[ExistenceValue](verification=VerificationStatus.VERIFIED)
    with pytest.raises(ValidationError):
        CaseEvidenceItem(
            evidence_id="evidence-verified",
            episode_id="episode-1",
            kind="receipt",
            claimant=Claimant.USER,
            exists_status=FactStatus.PRESENT,
            anchor=anchor(),
            verification=VerificationStatus.VERIFIED,
            created_at=NOW,
        )


def test_assertion_rejects_value_shape_for_its_slot() -> None:
    with pytest.raises(ValidationError):
        assertion(slot="deposit_amount", value=PartyRef(role="landlord"))
    with pytest.raises(ValidationError):
        assertion(slot="landlord_identified", value=MoneyAmount(amount_vnd=1, as_written="1 đồng"))


def test_text_anchor_is_validated_against_nfc_original() -> None:
    text = "Tôi có giấy"
    item = TextAnchor(message_id="message-1", start=4, end=11, quote="có giấy")
    assert validate_text_anchor(item, text) is item
    with pytest.raises(ValueError):
        validate_text_anchor(item.model_copy(update={"quote": "co giay"}), text)
    with pytest.raises(ValueError):
        validate_text_anchor(item.model_copy(update={"end": 99}), text)


def test_text_normalization_validates_map_length_bounds_and_monotonicity() -> None:
    text = "tôi có giấy"
    valid = TextNormalization(
        nfc_original=text,
        normalized_text=text,
        comparison_text="toi co giay",
        index_map=list(range(len(text))),
        normalizer_version="normalizer-v1",
    )
    assert valid.index_map[7] == 7
    invalid_maps = ([0], [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 99], [0, 1, 2, 3, 4, 5, 7, 6, 8, 9, 10])
    for invalid_map in invalid_maps:
        with pytest.raises(ValidationError):
            TextNormalization(
                nfc_original=text,
                normalized_text=text,
                comparison_text="toi co giay",
                index_map=invalid_map,
                normalizer_version="normalizer-v1",
            )


def test_nfd_input_can_be_represented_only_after_nfc_ingress() -> None:
    nfd = unicodedata.normalize("NFD", "tôi có giấy")
    with pytest.raises(ValidationError):
        TextNormalization(
            nfc_original=nfd,
            normalized_text=nfd,
            comparison_text="toi co giay",
            index_map=list(range(11)),
            normalizer_version="normalizer-v1",
        )
    nfc = unicodedata.normalize("NFC", nfd)
    normalized = TextNormalization(
        nfc_original=nfc,
        normalized_text=nfc,
        comparison_text="toi co giay",
        index_map=list(range(11)),
        normalizer_version="normalizer-v1",
    )
    validate_text_anchor(TextAnchor(message_id="m", start=7, end=11, quote="giấy"), normalized.nfc_original)


def test_unbound_operation_has_no_episode_or_infrastructure_references() -> None:
    fields = set(UnboundFactOperation.model_fields)
    assert "episode_id" not in fields
    assert not fields.intersection({"store", "runtime", "connection", "repository"})


def test_bound_operation_adds_episode_only_after_binding() -> None:
    bound = BoundFactOperation(
        unbound=unbound(),
        episode_id="episode-1",
        bound_issue_type="rental_deposit",
        slot="written_agreement_exists",
        resolver_version="resolver-v1",
        request_id="request-1",
    )
    assert bound.episode_id == "episode-1"


def test_positive_direction_payload_names_are_exact() -> None:
    rental = set(RentalDepositFacts.model_fields) - {"issue_type", "schema_version"}
    loan = set(PersonalLoanFacts.model_fields) - {"issue_type", "schema_version"}
    assert rental == {
        "deposit_amount",
        "written_agreement_exists",
        "signatures_exist",
        "payment_evidence_exists",
        "payment_sent",
        "payment_receipt_acknowledged",
        "property_handed_over",
        "deposit_returned",
        "refund_terms_documented",
        "landlord_identified",
        "deposit_paid_on",
        "handover_due_on",
    }
    assert loan == {
        "principal_amount",
        "loan_agreement_exists",
        "signatures_exist",
        "payment_evidence_exists",
        "disbursement_sent",
        "disbursement_acknowledged",
        "loan_repaid",
        "amount_repaid",
        "repayment_promised",
        "borrower_identified",
        "loan_made_on",
        "repayment_due_on",
    }
    forbidden = {"refund_refused", "property_not_delivered", "loan_unpaid"}
    assert not rental.intersection(forbidden)
    assert not loan.intersection(forbidden)


def test_episode_facts_union_is_discriminated() -> None:
    parsed = TypeAdapter(EpisodeFacts).validate_python({"issue_type": "rental_deposit"})
    assert isinstance(parsed, RentalDepositFacts)
    with pytest.raises(ValidationError):
        TypeAdapter(EpisodeFacts).validate_python({"issue_type": "sale"})


@pytest.mark.parametrize("payload_type, agreement_field", [(RentalDepositFacts, "written_agreement_exists"), (PersonalLoanFacts, "loan_agreement_exists")])
def test_signature_dependency_rejects_present_signature_when_agreement_absent(
    payload_type: type[RentalDepositFacts] | type[PersonalLoanFacts], agreement_field: str
) -> None:
    values = {
        agreement_field: FactSlot[ExistenceValue](status=FactStatus.ABSENT, claimant=Claimant.USER),
        "signatures_exist": FactSlot[ExistenceValue](
            status=FactStatus.PRESENT,
            claimant=Claimant.USER,
            value=ExistenceValue(),
        ),
    }
    with pytest.raises(ValidationError):
        payload_type(**values)


@pytest.mark.parametrize("facts", [RentalDepositFacts(), PersonalLoanFacts()])
def test_signature_dependency_helper_does_not_mutate_agreement(facts: RentalDepositFacts | PersonalLoanFacts) -> None:
    agreement_name = "written_agreement_exists" if isinstance(facts, RentalDepositFacts) else "loan_agreement_exists"
    absent = FactSlot[ExistenceValue](status=FactStatus.ABSENT, claimant=Claimant.USER)
    facts = facts.model_copy(update={agreement_name: absent}, deep=True)
    before = facts.model_dump_json()
    with pytest.raises(ValueError):
        validate_signature_dependency(facts, "signatures_exist", FactStatus.PRESENT)
    assert facts.model_dump_json() == before


@pytest.mark.parametrize(
    ("payload_type", "agreement_field"),
    [(RentalDepositFacts, "written_agreement_exists"), (PersonalLoanFacts, "loan_agreement_exists")],
)
def test_full_payload_dependency_projection_rejects_both_directions_without_mutation(
    payload_type: type[RentalDepositFacts] | type[PersonalLoanFacts], agreement_field: str
) -> None:
    present = FactSlot[ExistenceValue](
        status=FactStatus.PRESENT,
        claimant=Claimant.USER,
        value=ExistenceValue(),
    )
    absent = FactSlot[ExistenceValue](status=FactStatus.ABSENT, claimant=Claimant.USER)
    unset = FactSlot[ExistenceValue]()
    facts = payload_type(**{agreement_field: present, "signatures_exist": present, "payment_evidence_exists": unset})
    before = facts.model_dump_json()
    agreement_projection = project_episode_fact_slot(facts, agreement_field, absent)
    assert agreement_projection.accepted is False
    assert agreement_projection.requires_clarification is True
    assert agreement_projection.reason_code == "fact.dependency.signature_agreement_conflict.v1"
    assert agreement_projection.projected_facts.model_dump_json() == before

    absent_agreement = payload_type(**{agreement_field: absent, "signatures_exist": unset, "payment_evidence_exists": unset})
    signature_projection = project_episode_fact_slot(absent_agreement, "signatures_exist", present)
    assert signature_projection.accepted is False
    assert signature_projection.projected_facts.model_dump_json() == absent_agreement.model_dump_json()
    assert facts.model_dump_json() == before


@pytest.mark.parametrize(
    ("payload_type", "agreement_field"),
    [(RentalDepositFacts, "written_agreement_exists"), (PersonalLoanFacts, "loan_agreement_exists")],
)
def test_full_payload_dependency_projection_accepts_valid_present_absent_states(
    payload_type: type[RentalDepositFacts] | type[PersonalLoanFacts], agreement_field: str
) -> None:
    present = FactSlot[ExistenceValue](
        status=FactStatus.PRESENT,
        claimant=Claimant.USER,
        value=ExistenceValue(),
    )
    absent = FactSlot[ExistenceValue](status=FactStatus.ABSENT, claimant=Claimant.USER)
    facts = payload_type(**{agreement_field: present, "signatures_exist": absent})
    result = project_episode_fact_slot(facts, agreement_field, present)
    assert result.accepted is True
    assert result.requires_clarification is False
    assert result.reason_code == "fact.dependency.projection_valid.v1"
    assert result.projected_facts.model_dump_json() == facts.model_dump_json()


def test_case_evidence_and_legal_authority_kind_sets_are_disjoint() -> None:
    assert CASE_EVIDENCE_KINDS.isdisjoint(LEGAL_AUTHORITY_KINDS)
    case = CaseEvidenceItem(
        evidence_id="evidence-1",
        episode_id="episode-1",
        kind=EvidenceSourceKind.RECEIPT,
        claimant=Claimant.USER,
        exists_status=FactStatus.PRESENT,
        anchor=anchor(),
        supports_slots=["payment_evidence_exists"],
        created_at=NOW,
    )
    authority = LegalAuthorityReference(
        source_id="source-1",
        kind=EvidenceSourceKind.STATUTE,
        corpus_version="corpus-v1",
        retrieved_for_request_id="request-1",
    )
    assert case.kind in CASE_EVIDENCE_KINDS
    assert authority.kind in LEGAL_AUTHORITY_KINDS
    assert "supports_slots" not in LegalAuthorityReference.model_fields


def test_case_evidence_and_authority_cannot_be_mixed() -> None:
    with pytest.raises(ValidationError):
        CaseEvidenceItem(
            evidence_id="evidence-1",
            episode_id="episode-1",
            kind=EvidenceSourceKind.DECREE,
            claimant=Claimant.USER,
            exists_status=FactStatus.PRESENT,
            anchor=anchor(),
            created_at=NOW,
        )
    with pytest.raises(ValidationError):
        LegalAuthorityReference(
            source_id="source-1",
            kind=EvidenceSourceKind.RECEIPT,
            corpus_version="corpus-v1",
            retrieved_for_request_id="request-1",
        )
    with pytest.raises(ValidationError):
        LegalAuthorityReference(
            source_id="source-1",
            kind=EvidenceSourceKind.STATUTE,
            corpus_version="corpus-v1",
            retrieved_for_request_id="request-1",
            supports_slots=["deposit_amount"],
        )


def test_persisted_contract_annotations_do_not_use_unrestricted_any() -> None:
    models = (
        FactAssertion,
        FactSlot,
        RentalDepositFacts,
        PersonalLoanFacts,
        CaseEvidenceItem,
        LegalAuthorityReference,
        FactConflictResolution,
        FactApplyResult,
    )

    def contains_any(annotation: object) -> bool:
        return annotation is Any or any(contains_any(argument) for argument in get_args(annotation))

    for model in models:
        for field in model.model_fields.values():
            assert not contains_any(field.annotation), f"{model.__name__}.{field} contains Any"


def test_phase_a1_modules_have_no_forbidden_imports() -> None:
    forbidden = (
        "backend_lite.app.runtime",
        "backend_lite.app.stores",
        "backend_lite.app.adapters",
        "backend_lite.app.services",
        "frontend",
    )
    targets = (
        ROOT / "backend_lite/app/contracts/legal_facts.py",
        ROOT / "backend_lite/app/application/fact_conflict_resolver.py",
    )
    found: list[str] = []
    for target in targets:
        tree = ast.parse(target.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.extend(alias.name for alias in node.names if alias.name.startswith(forbidden))
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(forbidden):
                    found.append(node.module)
    assert found == []
