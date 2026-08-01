"""Pure typed contracts for semantic legal facts.

Phase A1 intentionally contains no extraction, episode selection, persistence,
runtime, or presentation behavior.  Every value carried by a fact is a bounded,
discriminated model; there is no untyped persistence escape hatch.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Generic, Literal, TypeAlias, TypeVar
import unicodedata

from pydantic import Field, field_validator, model_validator

from .internal import StrictModel


class FactStatus(str, Enum):
    UNSET = "unset"
    PRESENT = "present"
    ABSENT = "absent"
    DISPUTED = "disputed"


class Epistemic(str, Enum):
    NONE = "none"
    USER_UNKNOWN = "user_unknown"
    USER_UNSURE = "user_unsure"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    DOCUMENT_CLAIMED = "document_claimed"
    CORROBORATED = "corroborated"
    CONTESTED = "contested"
    VERIFIED = "verified"


class Claimant(str, Enum):
    USER = "user"
    COUNTERPARTY = "counterparty"
    AUTHORITY = "authority"
    UNKNOWN = "unknown"


class ChangeType(str, Enum):
    INITIAL = "initial"
    REAFFIRMATION = "reaffirmation"
    CORRECTION = "correction"
    STATE_TRANSITION = "state_transition"
    CONTRADICTION = "contradiction"
    EPISTEMIC_NOTE = "epistemic_note"
    DISPUTE_RESOLVED = "dispute_resolved"


class FactOpKind(str, Enum):
    AFFIRM = "affirm"
    NEGATE = "negate"
    SET_VALUE = "set_value"
    CORRECT = "correct"
    TRANSITION = "transition"
    REPORT_UNKNOWN = "report_unknown"
    RESOLVE_DISPUTE = "resolve_dispute"


class EvidenceSourceKind(str, Enum):
    DEPOSIT_AGREEMENT = "deposit_agreement"
    LOAN_AGREEMENT = "loan_agreement"
    RECEIPT = "receipt"
    TRANSFER_RECORD = "transfer_record"
    MESSAGE = "message"
    UPLOADED_DOCUMENT = "uploaded_document"
    PARTY_STATEMENT = "party_statement"
    STATUTE = "statute"
    DECREE = "decree"
    OFFICIAL_DOCUMENT = "official_document"
    CORPUS_ENTRY = "corpus_entry"


class DisputedFactPolicy(str, Enum):
    EXCLUDE_FROM_GUIDANCE_AND_CLARIFY = "EXCLUDE_FROM_GUIDANCE_AND_CLARIFY"


class CounterpartyClaimPolicy(str, Enum):
    DO_NOT_OVERWRITE_USER_SNAPSHOT = "DO_NOT_OVERWRITE_USER_SNAPSHOT"


class LowConfidenceOperationPolicy(str, Enum):
    DROP = "DROP"


DISPUTED_FACT_POLICY = DisputedFactPolicy.EXCLUDE_FROM_GUIDANCE_AND_CLARIFY
COUNTERPARTY_CLAIM_POLICY = CounterpartyClaimPolicy.DO_NOT_OVERWRITE_USER_SNAPSHOT
LOW_CONFIDENCE_OPERATION_POLICY = LowConfidenceOperationPolicy.DROP
FACT_OPERATION_CONFIDENCE_FLOOR = 0.5


class MoneyAmount(StrictModel):
    kind: Literal["money"] = "money"
    amount_vnd: int = Field(strict=True, ge=0, le=10**13)
    precision: Literal["exact", "approx"] = "exact"
    as_written: str = Field(min_length=1, max_length=64)


class DateValue(StrictModel):
    kind: Literal["date"] = "date"
    granularity: Literal["day", "month", "year", "unspecified"]
    iso: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$")
    as_written: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unspecified_dates_have_no_iso(self) -> "DateValue":
        if self.granularity == "unspecified" and self.iso is not None:
            raise ValueError("unspecified temporal expressions must not invent an ISO date")
        return self


class DateRange(StrictModel):
    kind: Literal["date_range"] = "date_range"
    start: DateValue | None = None
    end: DateValue | None = None

    @model_validator(mode="after")
    def has_at_least_one_endpoint(self) -> "DateRange":
        if self.start is None and self.end is None:
            raise ValueError("date range must have at least one endpoint")
        return self


class PaymentEvidenceValue(StrictModel):
    kind: Literal["payment_evidence"] = "payment_evidence"
    method: Literal["bank_transfer", "cash", "e_wallet", "other"]
    amount: MoneyAmount | None = None
    has_document: bool = False
    evidence_ref_ids: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("evidence_ref_ids")
    @classmethod
    def evidence_refs_are_bounded(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 64 for value in values):
            raise ValueError("evidence reference IDs must contain 1 to 64 characters")
        if len(values) != len(set(values)):
            raise ValueError("evidence reference IDs must be unique")
        return values


class PartyRef(StrictModel):
    kind: Literal["party"] = "party"
    role: Literal[
        "landlord",
        "tenant",
        "lender",
        "borrower",
        "seller",
        "buyer",
        "authority",
        "other",
    ]
    display_name: str | None = Field(default=None, max_length=80)
    identified: bool = False


class DocumentRef(StrictModel):
    kind: Literal["document"] = "document"
    evidence_id: str = Field(min_length=1, max_length=64)


class ExistenceValue(StrictModel):
    """Value-free predicate marker; polarity is carried by FactStatus."""

    kind: Literal["existence"] = "existence"


FactValue: TypeAlias = Annotated[
    MoneyAmount
    | DateValue
    | DateRange
    | PaymentEvidenceValue
    | PartyRef
    | DocumentRef
    | ExistenceValue,
    Field(discriminator="kind"),
]


class TextAnchor(StrictModel):
    message_id: str = Field(min_length=1, max_length=128)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=300)
    text_form: Literal["nfc_original"] = "nfc_original"

    @model_validator(mode="after")
    def end_exceeds_start(self) -> "TextAnchor":
        if self.end <= self.start:
            raise ValueError("anchor end must exceed start")
        return self


class TextNormalization(StrictModel):
    nfc_original: str
    normalized_text: str
    comparison_text: str
    index_map: list[int]
    normalizer_version: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_index_map(self) -> "TextNormalization":
        if self.nfc_original != unicodedata.normalize("NFC", self.nfc_original):
            raise ValueError("nfc_original must be NFC-normalized")
        if len(self.index_map) != len(self.comparison_text):
            raise ValueError("index_map length must equal comparison_text length")
        if any(index < 0 or index >= len(self.nfc_original) for index in self.index_map):
            raise ValueError("every mapped index must be within nfc_original bounds")
        if any(left > right for left, right in zip(self.index_map, self.index_map[1:])):
            raise ValueError("index_map must be monotonic non-decreasing")
        return self


def validate_text_anchor(anchor: TextAnchor, nfc_original: str) -> TextAnchor:
    """Validate an anchor against the sole permitted span coordinate system."""

    if nfc_original != unicodedata.normalize("NFC", nfc_original):
        raise ValueError("anchor source text must be NFC-normalized")
    if anchor.end > len(nfc_original):
        raise ValueError("anchor exceeds nfc_original bounds")
    if anchor.quote != nfc_original[anchor.start : anchor.end]:
        raise ValueError("anchor quote does not match the nfc_original slice")
    return anchor


ClaimedFactStatus: TypeAlias = Literal[FactStatus.PRESENT, FactStatus.ABSENT]
ChangeMarker: TypeAlias = Literal["correction", "temporal", "contrast", "negation", "hedge"]
IssueType: TypeAlias = Literal["rental_deposit", "personal_loan"]


class UnboundFactOperation(StrictModel):
    op: FactOpKind
    slot_hint: str = Field(min_length=1, max_length=64)
    issue_type_hint: IssueType | None = None
    claimed_status: ClaimedFactStatus | None = None
    value: FactValue | None = None
    claimant: Claimant = Claimant.USER
    epistemic: Epistemic = Epistemic.NONE
    change_markers: list[ChangeMarker] = Field(default_factory=list, max_length=5)
    effective_from: DateValue | None = None
    effective_to: DateValue | None = None
    anchor: TextAnchor
    extractor_version: str = Field(min_length=1, max_length=32)
    confidence: float = Field(ge=0.0, le=1.0)
    op_index: int = Field(ge=0)

    @model_validator(mode="after")
    def operation_shape_is_coherent(self) -> "UnboundFactOperation":
        inferred = {
            FactOpKind.AFFIRM: FactStatus.PRESENT,
            FactOpKind.NEGATE: FactStatus.ABSENT,
            FactOpKind.SET_VALUE: FactStatus.PRESENT,
        }.get(self.op)
        if inferred is not None and self.claimed_status not in (None, inferred):
            raise ValueError(f"{self.op.value} cannot claim {self.claimed_status}")
        if self.op in {FactOpKind.CORRECT, FactOpKind.TRANSITION, FactOpKind.RESOLVE_DISPUTE}:
            if self.claimed_status is None:
                raise ValueError(f"{self.op.value} requires claimed_status")
        if self.op is FactOpKind.REPORT_UNKNOWN:
            if self.claimed_status is not None or self.value is not None:
                raise ValueError("report_unknown is epistemic-only")
            if self.epistemic not in {Epistemic.USER_UNKNOWN, Epistemic.USER_UNSURE}:
                raise ValueError("report_unknown requires a user epistemic state")
        if self.op is FactOpKind.NEGATE and self.value is not None:
            raise ValueError("negation cannot carry a positive value")
        if self.effective_from is not None and self.op is not FactOpKind.TRANSITION:
            raise ValueError("effective_from is only valid on a transition operation")
        return self


_RENTAL_SLOT_TYPES: dict[str, type[StrictModel]] = {
    "deposit_amount": MoneyAmount,
    "written_agreement_exists": ExistenceValue,
    "signatures_exist": ExistenceValue,
    "payment_evidence_exists": PaymentEvidenceValue,
    "payment_sent": ExistenceValue,
    "payment_receipt_acknowledged": ExistenceValue,
    "property_handed_over": ExistenceValue,
    "deposit_returned": ExistenceValue,
    "refund_terms_documented": ExistenceValue,
    "landlord_identified": PartyRef,
    "deposit_paid_on": DateValue,
    "handover_due_on": DateValue,
}

_LOAN_SLOT_TYPES: dict[str, type[StrictModel]] = {
    "principal_amount": MoneyAmount,
    "loan_agreement_exists": ExistenceValue,
    "signatures_exist": ExistenceValue,
    "payment_evidence_exists": PaymentEvidenceValue,
    "disbursement_sent": ExistenceValue,
    "disbursement_acknowledged": ExistenceValue,
    "loan_repaid": ExistenceValue,
    "amount_repaid": MoneyAmount,
    "repayment_promised": ExistenceValue,
    "borrower_identified": PartyRef,
    "loan_made_on": DateValue,
    "repayment_due_on": DateValue,
}

SLOT_VALUE_TYPES: dict[IssueType, dict[str, type[StrictModel]]] = {
    "rental_deposit": _RENTAL_SLOT_TYPES,
    "personal_loan": _LOAN_SLOT_TYPES,
}


def _validate_slot_value(
    slot: str,
    status: FactStatus,
    value: FactValue | None,
    issue_type: IssueType | None = None,
) -> None:
    registries = [SLOT_VALUE_TYPES[issue_type]] if issue_type is not None else list(SLOT_VALUE_TYPES.values())
    expected_types = {registry[slot] for registry in registries if slot in registry}
    if not expected_types:
        raise ValueError(f"unknown semantic fact slot: {slot}")
    if status in {FactStatus.ABSENT, FactStatus.UNSET, FactStatus.DISPUTED} and value is not None:
        raise ValueError(f"{status.value} slot must not carry a value")
    if value is not None and not isinstance(value, tuple(expected_types)):
        expected_names = ", ".join(sorted(expected.__name__ for expected in expected_types))
        raise ValueError(f"slot {slot} requires one of: {expected_names}")
    if status is FactStatus.PRESENT and MoneyAmount in expected_types and value is None:
        raise ValueError(f"amount slot {slot} requires MoneyAmount when PRESENT")
    if status is FactStatus.PRESENT and PartyRef in expected_types and value is None:
        raise ValueError(f"party slot {slot} requires PartyRef when PRESENT")
    if status is FactStatus.PRESENT and DateValue in expected_types and value is None:
        raise ValueError(f"date slot {slot} requires DateValue when PRESENT")


class BoundFactOperation(StrictModel):
    unbound: UnboundFactOperation
    episode_id: str = Field(min_length=1, max_length=64)
    bound_issue_type: IssueType
    slot: str = Field(min_length=1, max_length=64)
    resolver_version: str = Field(min_length=1, max_length=32)
    request_id: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_binding(self) -> "BoundFactOperation":
        if self.slot != self.unbound.slot_hint:
            raise ValueError("bound slot must match the validated slot hint")
        if self.unbound.issue_type_hint is not None and self.unbound.issue_type_hint != self.bound_issue_type:
            raise ValueError("bound issue type conflicts with the operation issue-type hint")
        issue_type = self.bound_issue_type
        if self.slot not in SLOT_VALUE_TYPES[issue_type]:
            raise ValueError("bound slot does not belong to the selected issue type")
        status = claimed_status_for_operation(self.unbound)
        if status is not None:
            _validate_slot_value(self.slot, status, self.unbound.value, issue_type)
        return self


def claimed_status_for_operation(operation: UnboundFactOperation) -> FactStatus | None:
    if operation.op in {FactOpKind.AFFIRM, FactOpKind.SET_VALUE}:
        return FactStatus.PRESENT
    if operation.op is FactOpKind.NEGATE:
        return FactStatus.ABSENT
    return operation.claimed_status


class FactAssertion(StrictModel):
    assertion_id: str = Field(min_length=1, max_length=64)
    episode_id: str = Field(min_length=1, max_length=64)
    slot: str = Field(min_length=1, max_length=64)
    status_claimed: ClaimedFactStatus
    value: FactValue | None = None
    claimant: Claimant
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    epistemic: Epistemic = Epistemic.NONE
    change_type: ChangeType
    observed_at: datetime
    effective_from: DateValue | None = None
    effective_to: DateValue | None = None
    anchor: TextAnchor
    message_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    op_index: int = Field(ge=0)
    superseded_by: str | None = Field(default=None, min_length=1, max_length=64)
    supersession_reason: str | None = Field(default=None, min_length=1, max_length=64)
    extractor_version: str = Field(min_length=1, max_length=32)
    resolver_version: str = Field(min_length=1, max_length=32)
    registry_version: str = Field(min_length=1, max_length=32)
    schema_version: Literal[1] = 1
    reason_code: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def assertion_is_persistable(self) -> "FactAssertion":
        if self.verification is VerificationStatus.VERIFIED:
            raise ValueError("VERIFIED is unreachable through the MVP deterministic assertion path")
        if self.message_id != self.anchor.message_id:
            raise ValueError("message_id must equal anchor.message_id")
        if (self.superseded_by is None) != (self.supersession_reason is None):
            raise ValueError("supersession target and reason must be supplied together")
        _validate_slot_value(self.slot, self.status_claimed, self.value)
        return self


class FactEpistemicNote(StrictModel):
    note_id: str = Field(min_length=1, max_length=64)
    episode_id: str = Field(min_length=1, max_length=64)
    slot: str = Field(min_length=1, max_length=64)
    epistemic: Literal[Epistemic.USER_UNKNOWN, Epistemic.USER_UNSURE]
    claimant: Claimant
    observed_at: datetime
    anchor: TextAnchor
    message_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    op_index: int = Field(ge=0)
    extractor_version: str = Field(min_length=1, max_length=32)
    resolver_version: str = Field(min_length=1, max_length=32)
    registry_version: str = Field(min_length=1, max_length=32)
    schema_version: Literal[1] = 1
    reason_code: Literal["fact.epistemic_note.v1"] = "fact.epistemic_note.v1"

    @model_validator(mode="after")
    def note_message_matches_anchor(self) -> "FactEpistemicNote":
        if self.message_id != self.anchor.message_id:
            raise ValueError("message_id must equal anchor.message_id")
        return self


ValueT = TypeVar("ValueT", bound=StrictModel)


class FactSlot(StrictModel, Generic[ValueT]):
    status: FactStatus = FactStatus.UNSET
    value: ValueT | None = None
    claimant: Claimant | None = None
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    epistemic: Epistemic = Epistemic.NONE
    effective_from: DateValue | None = None
    last_change_type: ChangeType | None = None
    pending_clarification: bool = False
    reconfirmation_needed: bool = False
    assertion_ids: list[str] = Field(default_factory=list, max_length=40)
    counter_claims: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_state(self) -> "FactSlot[ValueT]":
        if self.verification is VerificationStatus.VERIFIED:
            raise ValueError("VERIFIED is reserved and unreachable in MVP fact snapshots")
        if self.status in {FactStatus.UNSET, FactStatus.ABSENT, FactStatus.DISPUTED} and self.value is not None:
            raise ValueError(f"{self.status.value} slot must not carry a value")
        if self.status is FactStatus.UNSET and self.claimant is not None:
            raise ValueError("UNSET slot must not manufacture a snapshot claimant")
        if self.status is FactStatus.DISPUTED and not self.pending_clarification:
            raise ValueError("DISPUTED slot must request clarification")
        if self.status is not FactStatus.DISPUTED and self.pending_clarification and not self.reconfirmation_needed:
            raise ValueError("non-DISPUTED clarification must be an explicit re-confirmation")
        if len(self.assertion_ids) != len(set(self.assertion_ids)):
            raise ValueError("assertion IDs must be unique")
        if len(self.counter_claims) != len(set(self.counter_claims)):
            raise ValueError("counter-claim IDs must be unique")
        return self


class RentalDepositFacts(StrictModel):
    issue_type: Literal["rental_deposit"] = "rental_deposit"
    schema_version: Literal[1] = 1
    deposit_amount: FactSlot[MoneyAmount] = Field(default_factory=FactSlot[MoneyAmount])
    written_agreement_exists: FactSlot[ExistenceValue] = Field(default_factory=FactSlot[ExistenceValue])
    signatures_exist: FactSlot[ExistenceValue] = Field(default_factory=FactSlot[ExistenceValue])
    payment_evidence_exists: FactSlot[PaymentEvidenceValue] = Field(
        default_factory=FactSlot[PaymentEvidenceValue]
    )
    payment_sent: FactSlot[ExistenceValue] = Field(default_factory=FactSlot[ExistenceValue])
    payment_receipt_acknowledged: FactSlot[ExistenceValue] = Field(default_factory=FactSlot[ExistenceValue])
    property_handed_over: FactSlot[ExistenceValue] = Field(default_factory=FactSlot[ExistenceValue])
    deposit_returned: FactSlot[ExistenceValue] = Field(default_factory=FactSlot[ExistenceValue])
    refund_terms_documented: FactSlot[ExistenceValue] = Field(default_factory=FactSlot[ExistenceValue])
    landlord_identified: FactSlot[PartyRef] = Field(default_factory=FactSlot[PartyRef])
    deposit_paid_on: FactSlot[DateValue] = Field(default_factory=FactSlot[DateValue])
    handover_due_on: FactSlot[DateValue] = Field(default_factory=FactSlot[DateValue])

    @model_validator(mode="after")
    def signatures_require_possible_agreement(self) -> "RentalDepositFacts":
        if (
            self.signatures_exist.status is FactStatus.PRESENT
            and self.written_agreement_exists.status is FactStatus.ABSENT
        ):
            raise ValueError("signatures cannot be PRESENT when written agreement is ABSENT")
        return self


class PersonalLoanFacts(StrictModel):
    issue_type: Literal["personal_loan"] = "personal_loan"
    schema_version: Literal[1] = 1
    principal_amount: FactSlot[MoneyAmount] = Field(default_factory=FactSlot[MoneyAmount])
    loan_agreement_exists: FactSlot[ExistenceValue] = Field(default_factory=FactSlot[ExistenceValue])
    signatures_exist: FactSlot[ExistenceValue] = Field(default_factory=FactSlot[ExistenceValue])
    payment_evidence_exists: FactSlot[PaymentEvidenceValue] = Field(
        default_factory=FactSlot[PaymentEvidenceValue]
    )
    disbursement_sent: FactSlot[ExistenceValue] = Field(default_factory=FactSlot[ExistenceValue])
    disbursement_acknowledged: FactSlot[ExistenceValue] = Field(default_factory=FactSlot[ExistenceValue])
    loan_repaid: FactSlot[ExistenceValue] = Field(default_factory=FactSlot[ExistenceValue])
    amount_repaid: FactSlot[MoneyAmount] = Field(default_factory=FactSlot[MoneyAmount])
    repayment_promised: FactSlot[ExistenceValue] = Field(default_factory=FactSlot[ExistenceValue])
    borrower_identified: FactSlot[PartyRef] = Field(default_factory=FactSlot[PartyRef])
    loan_made_on: FactSlot[DateValue] = Field(default_factory=FactSlot[DateValue])
    repayment_due_on: FactSlot[DateValue] = Field(default_factory=FactSlot[DateValue])

    @model_validator(mode="after")
    def signatures_require_possible_agreement(self) -> "PersonalLoanFacts":
        if self.signatures_exist.status is FactStatus.PRESENT and self.loan_agreement_exists.status is FactStatus.ABSENT:
            raise ValueError("signatures cannot be PRESENT when loan agreement is ABSENT")
        return self


EpisodeFacts: TypeAlias = Annotated[
    RentalDepositFacts | PersonalLoanFacts,
    Field(discriminator="issue_type"),
]


def validate_signature_dependency(
    facts: RentalDepositFacts | PersonalLoanFacts,
    slot: str,
    incoming_status: FactStatus,
) -> None:
    """Fail closed when an affirmative signature would contradict no agreement."""

    if slot != "signatures_exist" or incoming_status is not FactStatus.PRESENT:
        return
    agreement = (
        facts.written_agreement_exists
        if isinstance(facts, RentalDepositFacts)
        else facts.loan_agreement_exists
    )
    if agreement.status is FactStatus.ABSENT:
        raise ValueError("signature affirmation requires clarification while agreement is ABSENT")


class DependencyProjectionResult(StrictModel):
    accepted: bool
    projected_facts: EpisodeFacts
    requires_clarification: bool
    conflict_slots: list[str] = Field(default_factory=list, max_length=4)
    reason_code: str = Field(min_length=1, max_length=64)


def project_episode_fact_slot(
    current_facts: RentalDepositFacts | PersonalLoanFacts,
    slot: str,
    projected_slot: FactSlot[FactValue],
) -> DependencyProjectionResult:
    """Purely project and revalidate one slot against a concrete episode payload."""

    original = current_facts.model_copy(deep=True)
    if slot not in type(current_facts).model_fields:
        return DependencyProjectionResult(
            accepted=False,
            projected_facts=original,
            requires_clarification=True,
            conflict_slots=[slot],
            reason_code="fact.dependency.unknown_slot.v1",
        )

    payload = current_facts.model_dump(mode="python")
    payload[slot] = projected_slot.model_dump(mode="python")
    agreement_field = (
        "written_agreement_exists"
        if isinstance(current_facts, RentalDepositFacts)
        else "loan_agreement_exists"
    )
    signature_slot = payload["signatures_exist"]
    agreement_slot = payload[agreement_field]
    if (
        agreement_slot["status"] == FactStatus.ABSENT.value
        and signature_slot["status"] == FactStatus.PRESENT.value
    ):
        return DependencyProjectionResult(
            accepted=False,
            projected_facts=original,
            requires_clarification=True,
            conflict_slots=[agreement_field, "signatures_exist"],
            reason_code="fact.dependency.signature_agreement_conflict.v1",
        )
    try:
        projected = type(current_facts).model_validate(payload)
    except Exception:
        return DependencyProjectionResult(
            accepted=False,
            projected_facts=original,
            requires_clarification=True,
            conflict_slots=[slot],
            reason_code="fact.dependency.payload_revalidation_failed.v1",
        )
    return DependencyProjectionResult(
        accepted=True,
        projected_facts=projected,
        requires_clarification=False,
        reason_code="fact.dependency.projection_valid.v1",
    )


CASE_EVIDENCE_KINDS = frozenset(
    {
        EvidenceSourceKind.DEPOSIT_AGREEMENT,
        EvidenceSourceKind.LOAN_AGREEMENT,
        EvidenceSourceKind.RECEIPT,
        EvidenceSourceKind.TRANSFER_RECORD,
        EvidenceSourceKind.MESSAGE,
        EvidenceSourceKind.UPLOADED_DOCUMENT,
        EvidenceSourceKind.PARTY_STATEMENT,
    }
)
LEGAL_AUTHORITY_KINDS = frozenset(
    {
        EvidenceSourceKind.STATUTE,
        EvidenceSourceKind.DECREE,
        EvidenceSourceKind.OFFICIAL_DOCUMENT,
        EvidenceSourceKind.CORPUS_ENTRY,
    }
)
assert CASE_EVIDENCE_KINDS.isdisjoint(LEGAL_AUTHORITY_KINDS)


class CaseEvidenceItem(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=64)
    episode_id: str = Field(min_length=1, max_length=64)
    kind: EvidenceSourceKind
    claimant: Claimant
    exists_status: Literal[FactStatus.UNSET, FactStatus.PRESENT, FactStatus.ABSENT]
    anchor: TextAnchor
    supports_slots: list[str] = Field(default_factory=list, max_length=10)
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    created_at: datetime

    @field_validator("kind")
    @classmethod
    def kind_is_case_evidence(cls, value: EvidenceSourceKind) -> EvidenceSourceKind:
        if value not in CASE_EVIDENCE_KINDS:
            raise ValueError("case evidence cannot use a legal-authority kind")
        return value

    @field_validator("verification")
    @classmethod
    def verified_is_reserved(cls, value: VerificationStatus) -> VerificationStatus:
        if value is VerificationStatus.VERIFIED:
            raise ValueError("VERIFIED is reserved and unreachable in MVP evidence")
        return value

    @field_validator("supports_slots")
    @classmethod
    def supports_known_slots(cls, values: list[str]) -> list[str]:
        all_slots = set(_RENTAL_SLOT_TYPES) | set(_LOAN_SLOT_TYPES)
        if any(value not in all_slots for value in values):
            raise ValueError("case evidence may support only registered fact slots")
        if len(values) != len(set(values)):
            raise ValueError("supported slots must be unique")
        return values


class LegalAuthorityReference(StrictModel):
    source_id: str = Field(min_length=1, max_length=64)
    kind: EvidenceSourceKind
    corpus_version: str = Field(min_length=1, max_length=64)
    retrieved_for_request_id: str = Field(min_length=1, max_length=128)

    @field_validator("kind")
    @classmethod
    def kind_is_legal_authority(cls, value: EvidenceSourceKind) -> EvidenceSourceKind:
        if value not in LEGAL_AUTHORITY_KINDS:
            raise ValueError("legal authority cannot use a case-evidence kind")
        return value


ResolutionDecision: TypeAlias = Literal[
    "apply", "supersede", "dispute", "contest", "no_op", "reject", "clarify"
]


class AssertionSupersession(StrictModel):
    assertion_id: str = Field(min_length=1, max_length=64)
    superseded_by: str = Field(min_length=1, max_length=64)
    reason: Literal["correction", "state_transition", "dispute_resolved"]


class FactConflictResolution(StrictModel):
    slot: str = Field(min_length=1, max_length=64)
    prior_status: FactStatus
    incoming_status: FactStatus | None
    prior_claimant: Claimant | None
    incoming_claimant: Claimant
    decision: ResolutionDecision
    resulting_status: FactStatus
    change_type: ChangeType
    requires_clarification: bool
    guidance_status: ClaimedFactStatus | None = None
    reason_code: str = Field(min_length=1, max_length=64)
    supersessions: list[AssertionSupersession] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def disputed_guidance_is_excluded(self) -> "FactConflictResolution":
        if self.resulting_status is FactStatus.DISPUTED:
            if not self.requires_clarification or self.guidance_status is not None:
                raise ValueError("DISPUTED facts must be excluded from guidance and clarified")
        if self.guidance_status is not None and self.guidance_status is not self.resulting_status:
            raise ValueError("guidance status must match the usable resulting status")
        return self


class FactApplyResult(StrictModel):
    projected_slot: FactSlot[FactValue]
    resolution: FactConflictResolution
    assertion_to_append: FactAssertion | None = None
    epistemic_note_to_append: FactEpistemicNote | None = None

    @model_validator(mode="after")
    def current_state_is_mvp_safe(self) -> "FactApplyResult":
        if self.projected_slot.verification is VerificationStatus.VERIFIED:
            raise ValueError("VERIFIED is reserved and unreachable in MVP projections")
        return self
