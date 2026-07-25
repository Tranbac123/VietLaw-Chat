from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
# Additive discriminator for the analyze response contract (Gate C). "legal" is the
# default so every pre-existing construction site (which never set this field) keeps
# its current behavior unchanged. See TOMTIT_VIETLAW_INTENT_PORT_GATE_C_REPORT.md
# section 5 for the full contract design.
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
    asked_question_ids: list[str] = Field(default_factory=list)


def validate_response_kind_invariants(
    *,
    response_kind: ResponseKind,
    domain: Domain | None,
    risk_level: RiskLevel | None,
    decision: Decision | None,
    confidence: Confidence | None,
    sources: list[SourceObject],
    clarifying_questions: list[str],
    checklist: list[str],
    next_steps: list[str],
) -> None:
    """Shared invariant check for both `AnalyzeResponse` (schemas/api.py) and its
    persisted `AnalyzeContent` projection below -- kept here rather than duplicated
    so the two response-kind contracts cannot silently drift apart.

    legal:  domain, risk_level, decision, and confidence must all be present.
    social: domain, risk_level, decision, and confidence must all be null;
            sources, clarifying_questions, checklist, and next_steps must all
            be empty.
    """
    if response_kind == "legal":
        if domain is None or risk_level is None or decision is None or confidence is None:
            raise ValueError(
                "response_kind='legal' requires non-null domain, risk_level, decision, and confidence"
            )
        return
    if domain is not None or risk_level is not None or decision is not None:
        raise ValueError("response_kind='social' must not carry a legal domain, risk_level, or decision")
    if confidence is not None:
        raise ValueError("response_kind='social' must not carry confidence")
    if sources:
        raise ValueError("response_kind='social' must not carry sources")
    if clarifying_questions or checklist or next_steps:
        raise ValueError(
            "response_kind='social' must not carry legal clarifying_questions, checklist, or next_steps"
        )


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
