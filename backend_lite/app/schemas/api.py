from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from .content import (
    Confidence,
    Decision,
    Domain,
    DraftBlock,
    ResponseKind,
    RiskLevel,
    SourceObject,
    validate_response_kind_invariants,
)

UserType = Literal["citizen", "household_business", "foreign_visitor", "unknown"]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    chat_id: str | None = Field(default=None, min_length=1, max_length=128)
    # Any non-empty message is a legitimate turn: "ok", "hi" and "ừ" are things
    # people actually send. A 3-character floor rejected them as malformed data
    # before routing could ever see them. Emptiness is still refused, but by the
    # runtime's post-trim check, so "" and "   " fail identically with one
    # user-facing message rather than two different ones.
    question: str = Field(min_length=1, max_length=3000)
    user_type: UserType = "unknown"
    language: str = Field(default="vi", min_length=2, max_length=16)
    # FAST DEMO V2 idempotency key: generated once per user submission by the
    # client and reused for transport retries of that same submission, so a
    # retry can neither spend a second provider call nor re-apply fact updates.
    # Optional so the flag-off path and legacy clients keep working unchanged.
    client_request_id: str | None = Field(default=None, min_length=1, max_length=128)


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_kind: ResponseKind = "legal"
    contract_version: Literal["v1"]
    request_id: str
    chat_id: str
    user_message_id: str
    assistant_message_id: str
    domain: Domain | None
    risk_level: RiskLevel | None
    decision: Decision | None
    summary: str
    clarifying_questions: list[str]
    checklist: list[str]
    next_steps: list[str]
    sources: list[SourceObject]
    safety_notice: str
    confidence: Confidence | None
    metadata: dict[str, Any]
    # FAST DEMO V2 optional presentation blocks (additive; defaulted so every
    # existing construction site remains valid).
    analysis: str | None = None
    draft: DraftBlock | None = None
    known_facts: list[str] = Field(default_factory=list)
    uncertainty_notice: str | None = None

    @model_validator(mode="after")
    def _check_response_kind_invariants(self) -> "AnalyzeResponse":
        validate_response_kind_invariants(
            response_kind_is_set="response_kind" in self.model_fields_set,
            response_kind=self.response_kind,
            domain=self.domain,
            risk_level=self.risk_level,
            decision=self.decision,
            confidence=self.confidence,
            sources=self.sources,
            clarifying_questions=self.clarifying_questions,
            checklist=self.checklist,
            next_steps=self.next_steps,
        )
        return self

    @model_serializer(mode="wrap")
    def _serialize_response_kind_when_set(self, handler):
        data = handler(self)
        # Optional/additive fields are emitted only when the constructor set
        # them explicitly, so the baseline wire contract stays byte-identical
        # and only FAST DEMO V2 responses carry the extra blocks.
        for field in ("response_kind", "analysis", "draft", "known_facts", "uncertainty_notice"):
            if field not in self.model_fields_set:
                data.pop(field, None)
        return data


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ApiErrorResponse(BaseModel):
    contract_version: Literal["v1"] = "v1"
    request_id: str
    error: ErrorBody
    safety_notice: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    contract_version: Literal["v1"] = "v1"
    rag_loaded: bool
    safety_loaded: bool
    chat_store_ready: bool
