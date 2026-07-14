"""Strict internal DTOs used by the planned Gate A pipeline.

These models are deliberately separate from the frozen HTTP schemas.  They
describe the future application boundary without changing the currently
served runtime or public API.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, TypeAlias

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from ..schemas.content import Confidence, Decision, Domain, RiskLevel, SourceObject

RedactedValue: TypeAlias = str | int | float | bool | None | list[str]
PointStrength: TypeAlias = Literal["informational", "cautious", "strong"]
StageStatus: TypeAlias = Literal["started", "completed", "failed"]
UserType: TypeAlias = Literal["citizen", "household_business", "foreign_visitor", "unknown"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RequestStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    COMPLETE = "COMPLETE"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"


class IdKind(str, Enum):
    REQUEST = "request"
    CHAT = "chat"
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"


_ALLOWED_TRANSITIONS: dict[RequestStatus, frozenset[RequestStatus]] = {
    RequestStatus.RECEIVED: frozenset({RequestStatus.PROCESSING}),
    RequestStatus.PROCESSING: frozenset(
        {RequestStatus.COMPLETE, RequestStatus.FAILED_RETRYABLE, RequestStatus.FAILED_FINAL}
    ),
    RequestStatus.FAILED_RETRYABLE: frozenset({RequestStatus.PROCESSING}),
    RequestStatus.COMPLETE: frozenset(),
    RequestStatus.FAILED_FINAL: frozenset(),
}


def _status(value: RequestStatus | str) -> RequestStatus:
    try:
        return value if isinstance(value, RequestStatus) else RequestStatus(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unknown request status: {value!r}") from exc


def is_valid_transition(current: RequestStatus | str, target: RequestStatus | str) -> bool:
    """Return whether the durable state machine permits ``current -> target``."""

    return _status(target) in _ALLOWED_TRANSITIONS[_status(current)]


def validate_transition(current: RequestStatus | str, target: RequestStatus | str) -> RequestStatus:
    """Validate a state transition and fail loudly for an invalid edge."""

    current_status = _status(current)
    target_status = _status(target)
    if not is_valid_transition(current_status, target_status):
        raise ValueError(f"invalid request status transition: {current_status.value} -> {target_status.value}")
    return target_status


class VersionStamps(StrictModel):
    contract_version: str = "v1"
    corpus_version: str
    policy_version: str
    prompt_version: Literal["none"] = "none"
    retriever_version: str
    generator_mode: Literal["deterministic"] = "deterministic"
    generator_version: str


class RequestIdentity(StrictModel):
    session_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    fingerprint_version: Literal["fingerprint-v1"] = "fingerprint-v1"
    contract_version: str = "v1"
    requested_chat_id: str | None = Field(default=None, min_length=1, max_length=128)
    chat_id: str | None = Field(default=None, min_length=1, max_length=128)
    user_message_id: str | None = Field(default=None, min_length=1, max_length=128)
    assistant_candidate_id: str | None = Field(default=None, min_length=1, max_length=128)
    assistant_message_id: str | None = Field(default=None, min_length=1, max_length=128)
    idempotency_key_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    idempotency_key_digest_version: Literal["idempotency-key-digest-v1"] | None = None
    attempt_count: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_carrier_pair(self) -> "RequestIdentity":
        if (self.idempotency_key_digest is None) != (self.idempotency_key_digest_version is None):
            raise ValueError("idempotency digest and digest version must be supplied together")
        return self


class RawInput(StrictModel):
    session_id: str = Field(min_length=1, max_length=128)
    chat_id: str | None = Field(default=None, min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=3000)
    user_type: UserType = "unknown"
    language: str = Field(default="vi", min_length=2, max_length=16)
    contract_version: str = "v1"


class NormalizedInput(StrictModel):
    question: str = Field(min_length=1, max_length=3000)
    normalized_question: str = Field(min_length=1, max_length=3000)
    accentless_question: str = Field(min_length=1, max_length=3000)
    detected_language: str = Field(min_length=2, max_length=32)


class MinimalConversationContext(StrictModel):
    current_question: str = ""
    last_assistant_clarification: list[str] = Field(default_factory=list, max_length=5)
    last_assistant_message_id: str | None = None
    last_confirmed_topic: str | None = Field(default=None, max_length=64)
    last_confirmed_domain: Domain | None = None
    last_confirmed_message_id: str | None = None
    used_current_chat_history: bool = False

    @field_validator("last_assistant_clarification")
    @classmethod
    def validate_clarification_bounds(cls, values: list[str]) -> list[str]:
        if any(len(item) > 300 for item in values):
            raise ValueError("clarification items must be at most 300 characters")
        if any(not item.strip() for item in values):
            raise ValueError("clarification items must be non-empty")
        return values


class SafetyResult(StrictModel):
    harmful_intent: bool = False
    legal_high_risk: bool = Field(default=False, validation_alias=AliasChoices("legal_high_risk", "high_risk"))
    category: str | None = None
    policy_ids: list[str] = Field(default_factory=list)
    matched_pattern_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    current_turn_safe: bool = True


class RouteCandidate(StrictModel):
    domain: Domain
    topic: str | None = None
    score: float = Field(ge=0)
    reason_codes: list[str] = Field(default_factory=list)


class RoutingResult(StrictModel):
    candidates: list[RouteCandidate] = Field(default_factory=list)
    selected_domain: Domain = "unknown"
    selected_topic: str | None = None
    routing_version: str


class RetrievalQuery(StrictModel):
    question: str = Field(min_length=1, max_length=3000)
    normalized_question: str = Field(min_length=1, max_length=3000)
    domain: Domain = "unknown"
    topic: str | None = None
    top_k: int = Field(default=5, ge=1, le=50)
    threshold: float = Field(default=0, ge=0)


class RetrievalHit(StrictModel):
    source_id: str = Field(min_length=1)
    score: float = Field(ge=0)
    rank: int = Field(ge=1)
    lexical_score: float = Field(default=0, ge=0)
    metadata_boost: float = Field(default=0, ge=0)
    matched_terms: list[str] = Field(default_factory=list)


class RetrievalResult(StrictModel):
    hits: list[RetrievalHit] = Field(default_factory=list)
    query: RetrievalQuery
    strategy: Literal["lexical"] = "lexical"
    retriever_version: str
    available: bool = True
    no_source: bool = False


class EvidenceBundle(StrictModel):
    sources: list[SourceObject] = Field(default_factory=list)
    selected_source_ids: list[str] = Field(default_factory=list)
    point_source_ids: dict[str, list[str]] = Field(default_factory=dict)
    adequate: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    evidence_version: str

    @model_validator(mode="after")
    def validate_source_containment(self) -> "EvidenceBundle":
        source_ids = {source.id for source in self.sources}
        if len(self.selected_source_ids) != len(set(self.selected_source_ids)):
            raise ValueError("selected source IDs must be unique")
        if not set(self.selected_source_ids).issubset(source_ids):
            raise ValueError("selected source IDs must belong to the evidence bundle")
        if any(not set(ids).issubset(set(self.selected_source_ids)) for ids in self.point_source_ids.values()):
            raise ValueError("point source IDs must belong to selected evidence")
        return self


class DecisionResult(StrictModel):
    domain: Domain
    risk_level: RiskLevel
    decision: Decision
    confidence: Confidence
    reason_codes: list[str] = Field(default_factory=list)
    evidence_sufficient: bool = False


class GuidancePoint(StrictModel):
    point_id: str = Field(min_length=1)
    canonical_text: str = Field(min_length=1)
    supporting_source_ids: list[str] = Field(default_factory=list)
    strength: PointStrength


class RenderedPoint(StrictModel):
    point_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class AnswerPlan(StrictModel):
    points: list[GuidancePoint] = Field(default_factory=list)
    required_point_ids: list[str] = Field(default_factory=list)
    slot_order: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_point_order(self) -> "AnswerPlan":
        point_ids = [point.point_id for point in self.points]
        if len(point_ids) != len(set(point_ids)):
            raise ValueError("answer plan point IDs must be unique")
        if len(self.required_point_ids) != len(set(self.required_point_ids)):
            raise ValueError("required point IDs must be unique")
        if not set(self.required_point_ids).issubset(point_ids):
            raise ValueError("required point IDs must belong to the answer plan")
        if len(self.slot_order) != len(set(self.slot_order)):
            raise ValueError("slot order must not contain duplicate slots")
        return self


class AnswerDraft(StrictModel):
    rendered_points: list[RenderedPoint] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rendered_ids(self) -> "AnswerDraft":
        ids = [point.point_id for point in self.rendered_points]
        if len(ids) != len(set(ids)):
            raise ValueError("rendered point IDs must be unique")
        return self


class GuardResults(StrictModel):
    schema_valid: bool = True
    evidence_valid: bool = True
    output_safety_valid: bool = True
    confidence_adjustment: float = Field(default=0, ge=-1, le=0)
    warnings: list[str] = Field(default_factory=list)
    failure_code: str | None = None
    replacements: list[str] = Field(default_factory=list)


class StageTrace(StrictModel):
    stage: str = Field(min_length=1)
    started_at: datetime
    finished_at: datetime
    duration_ms: float = Field(ge=0)
    status: StageStatus
    input_summary_redacted: dict[str, RedactedValue] = Field(default_factory=dict)
    output_summary_redacted: dict[str, RedactedValue] = Field(default_factory=dict)
    error_code: str | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("trace timestamps must be timezone-aware")
        return value


class BoundedContextQuery(StrictModel):
    session_id: str = Field(min_length=1, max_length=128)
    chat_id: str = Field(min_length=1, max_length=128)
    current_user_message_id: str = Field(min_length=1, max_length=128)
    current_question: str = Field(min_length=1, max_length=3000)


class BeginRequest(StrictModel):
    session_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    fingerprint_version: Literal["fingerprint-v1"] = "fingerprint-v1"
    contract_version: str = "v1"
    question: str = Field(min_length=1, max_length=3000)
    user_type: UserType = "unknown"
    language: str = Field(default="vi", min_length=2, max_length=16)
    requested_chat_id: str | None = Field(default=None, min_length=1, max_length=128)
    new_chat_title: str | None = Field(default=None, max_length=160)
    idempotency_key_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    idempotency_key_digest_version: Literal["idempotency-key-digest-v1"] | None = None
    chat_id_candidate: str | None = Field(default=None, min_length=1, max_length=128)
    user_message_id_candidate: str | None = Field(default=None, min_length=1, max_length=128)
    # The request row has non-null durable version columns.  The application
    # service captures these before Tx A; a storage adapter must not invent
    # artifact versions on its behalf.
    version_stamps: VersionStamps

    @model_validator(mode="after")
    def validate_carrier_pair(self) -> "BeginRequest":
        if (self.idempotency_key_digest is None) != (self.idempotency_key_digest_version is None):
            raise ValueError("idempotency digest and digest version must be supplied together")
        return self


class StoredResponse(StrictModel):
    request_id: str = Field(min_length=1, max_length=128)
    status: RequestStatus
    response_payload: dict[str, JsonValue] | None = None
    assistant_message_id: str | None = None
    error_code: str | None = None


class BeginRequestResult(StrictModel):
    kind: Literal["accepted", "duplicate", "in_progress", "retry"]
    status: RequestStatus
    identity: RequestIdentity
    should_execute: bool
    user_message_created: bool = False
    stored_response: StoredResponse | None = None


class BeginRequestAccepted(BeginRequestResult):
    kind: Literal["accepted"] = "accepted"


class BeginRequestDuplicate(BeginRequestResult):
    kind: Literal["duplicate"] = "duplicate"


class BeginRequestInProgress(BeginRequestResult):
    kind: Literal["in_progress"] = "in_progress"


class BeginRequestRetry(BeginRequestResult):
    kind: Literal["retry"] = "retry"


class CompleteRequest(StrictModel):
    session_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_count: int = Field(ge=1)
    chat_id: str = Field(min_length=1, max_length=128)
    user_message_id: str = Field(min_length=1, max_length=128)
    assistant_message_id: str = Field(min_length=1, max_length=128)
    response_payload: dict[str, JsonValue]


class FailRequest(StrictModel):
    session_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_count: int = Field(ge=1)
    status: Literal[RequestStatus.FAILED_RETRYABLE, RequestStatus.FAILED_FINAL]
    error_class: str = Field(min_length=1)
    last_error_code: str = Field(min_length=1)
    error_details_redacted: dict[str, JsonValue] = Field(default_factory=dict)
    response_payload: dict[str, JsonValue] | None = None


__all__ = [
    "AnswerDraft",
    "AnswerPlan",
    "BeginRequest",
    "BeginRequestAccepted",
    "BeginRequestDuplicate",
    "BeginRequestInProgress",
    "BeginRequestResult",
    "BeginRequestRetry",
    "BoundedContextQuery",
    "CompleteRequest",
    "DecisionResult",
    "EvidenceBundle",
    "FailRequest",
    "GuidancePoint",
    "GuardResults",
    "IdKind",
    "JsonValue",
    "MinimalConversationContext",
    "NormalizedInput",
    "RawInput",
    "RenderedPoint",
    "RequestIdentity",
    "RequestStatus",
    "RetrievalHit",
    "RetrievalQuery",
    "RetrievalResult",
    "RouteCandidate",
    "RoutingResult",
    "SafetyResult",
    "StageTrace",
    "StoredResponse",
    "VersionStamps",
    "is_valid_transition",
    "validate_transition",
]
