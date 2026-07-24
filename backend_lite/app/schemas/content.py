from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

Domain: TypeAlias = Literal[
    "civil_dispute",
    "traffic",
    "household_business",
    "administrative",
    "high_risk",
    "unknown",
]
RiskLevel: TypeAlias = Literal["low", "medium", "high"]
Decision: TypeAlias = Literal[
    "answer_with_guidance",
    "ask_clarifying_questions",
    "recommend_professional_help",
    "refuse_unsafe_request",
    "unsupported",
]
SourceType: TypeAlias = Literal[
    "official_source",
    "procedure",
    "legal_snippet",
    "curated_note",
    "demo_only",
    "safety_policy",
]
ResponseKind: TypeAlias = Literal["legal", "social"]


class SourceObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    source_name: str
    url: str | None = None
    snippet: str
    source_type: SourceType
    last_checked: str


class Confidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: float = Field(ge=0, le=1)
    risk: float = Field(ge=0, le=1)
    answer: float = Field(ge=0, le=1)


class GeneratedContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    clarifying_questions: list[str]
    checklist: list[str]
    next_steps: list[str]
    used_source_ids: list[str]


def validate_response_kind_invariants(
    *,
    response_kind_is_set: bool,
    response_kind: "ResponseKind",
    domain: Domain | None,
    risk_level: RiskLevel | None,
    decision: Decision | None,
    confidence: "Confidence | None",
    sources: list["SourceObject"],
    clarifying_questions: list[str],
    checklist: list[str],
    next_steps: list[str],
) -> None:
    """Shared response_kind/field semantic contract for AnalyzeResponse and
    AnalyzeContent -- kept here once so the two models cannot silently drift.

    Legacy (response_kind never explicitly set): no new invariant is enforced,
    preserving pre-demo baseline construction exactly.

    social: domain, risk_level, decision, and confidence must all be None, and
    sources/clarifying_questions/checklist/next_steps must all be empty.

    legal: domain, risk_level, decision, and confidence must all be non-None.
    Collections may be empty or non-empty.
    """

    if not response_kind_is_set:
        return
    if response_kind == "social":
        if domain is not None:
            raise ValueError("response_kind='social' requires domain=None")
        if risk_level is not None:
            raise ValueError("response_kind='social' requires risk_level=None")
        if decision is not None:
            raise ValueError("response_kind='social' requires decision=None")
        if confidence is not None:
            raise ValueError("response_kind='social' requires confidence=None")
        if sources:
            raise ValueError("response_kind='social' requires sources=[]")
        if clarifying_questions:
            raise ValueError("response_kind='social' requires clarifying_questions=[]")
        if checklist:
            raise ValueError("response_kind='social' requires checklist=[]")
        if next_steps:
            raise ValueError("response_kind='social' requires next_steps=[]")
        return
    # response_kind == "legal"
    if domain is None:
        raise ValueError("response_kind='legal' requires domain to be set")
    if risk_level is None:
        raise ValueError("response_kind='legal' requires risk_level to be set")
    if decision is None:
        raise ValueError("response_kind='legal' requires decision to be set")
    if confidence is None:
        raise ValueError("response_kind='legal' requires confidence to be set")


class AnalyzeContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_kind: ResponseKind = "legal"
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
    def _check_response_kind_invariants(self) -> "AnalyzeContent":
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
        if "response_kind" not in self.model_fields_set:
            data.pop("response_kind", None)
        return data
