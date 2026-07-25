from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .content import (
    Confidence,
    Decision,
    Domain,
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
    question: str = Field(min_length=3, max_length=3000)
    user_type: UserType = "unknown"
    language: str = Field(default="vi", min_length=2, max_length=16)


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Additive discriminator (Gate C). Default "legal" preserves every pre-existing
    # construction site (LiteResponseBuilder.build never sets this field) unchanged.
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

    @model_validator(mode="after")
    def _check_response_kind_invariants(self) -> "AnalyzeResponse":
        validate_response_kind_invariants(
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
