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
# "capability" and "scope" are FAST DEMO V2 additions. Like "social" they are
# non-legal kinds: they carry no domain/risk/decision/confidence/sources, so a
# greeting, a capability answer or a scope refusal can never render legal
# badges or an empty source panel.
ResponseKind: TypeAlias = Literal["legal", "social", "capability", "scope"]

NON_LEGAL_RESPONSE_KINDS: frozenset[str] = frozenset({"social", "capability", "scope"})


class SourceObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    source_name: str
    url: str | None = None
    snippet: str
    source_type: SourceType
    last_checked: str
    # MODE_2D: article-level legal citation metadata. Optional and additive --
    # None/empty for every source without curated article-level data (which is
    # every source outside the bounded Civil Code scope), so this is a wire
    # contract extension, not a breaking change. Populated only from curated
    # snippet data and backend-computed clause resolution, never from
    # model-generated prose (see fast_demo_source_pack.py).
    document_title: str | None = None
    document_number: str | None = None
    article_number: str | None = None
    article_title: str | None = None
    clause_numbers: list[int] = Field(default_factory=list)
    applicable_clause: int | None = None
    relevance_note: str | None = None
    # Public Beta V0: when this source was retrieved live (official-source
    # search). Optional and additive; absent for curated static content,
    # which already carries `last_checked` for that purpose.
    retrieved_at: str | None = None
    # Legal Correction Round 1 (Traffic Safe Subset V1, MEDIUM-01): a curated
    # traffic rule's legal support is a LIST of independently traceable
    # provisions (contracts/traffic.py::TrafficLegalCitation), each rendered
    # as its own SourceObject rather than folded into one card's prose.
    # Optional and additive -- None for every source outside that model
    # (MODE_2D citations, official-source-search results, and general
    # curated notes never set these). `clause_number` is the exact source
    # string (e.g. "1-4" for a multi-khoản signal-interpretation citation) --
    # deliberately separate from `applicable_clause`/`clause_numbers` above,
    # which are integer-only and cannot represent a khoản range without loss.
    clause_number: str | None = None
    point_number: str | None = None
    citation_role: str | None = None


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
    if response_kind in NON_LEGAL_RESPONSE_KINDS:
        if domain is not None:
            raise ValueError(f"response_kind='{response_kind}' requires domain=None")
        if risk_level is not None:
            raise ValueError(f"response_kind='{response_kind}' requires risk_level=None")
        if decision is not None:
            raise ValueError(f"response_kind='{response_kind}' requires decision=None")
        if confidence is not None:
            raise ValueError(f"response_kind='{response_kind}' requires confidence=None")
        if sources:
            raise ValueError(f"response_kind='{response_kind}' requires sources=[]")
        if clarifying_questions:
            raise ValueError(f"response_kind='{response_kind}' requires clarifying_questions=[]")
        if checklist:
            raise ValueError(f"response_kind='{response_kind}' requires checklist=[]")
        if next_steps:
            raise ValueError(f"response_kind='{response_kind}' requires next_steps=[]")
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


class DraftBlock(BaseModel):
    """FAST DEMO V2 copyable draft message."""

    model_config = ConfigDict(extra="forbid")

    title: str
    body: str


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
    # FAST DEMO V2 optional presentation blocks. Additive and defaulted so every
    # existing construction site and every persisted legacy row stays valid.
    analysis: str | None = None
    draft: DraftBlock | None = None
    known_facts: list[str] = Field(default_factory=list)
    uncertainty_notice: str | None = None
    # Public Beta V0 trust-level contract (additive; see contracts/legal_trust.py).
    trust_level: str | None = None
    trust_label: str | None = None
    trust_explanation: str | None = None
    source_checked_at: str | None = None

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
        # Optional/additive fields are emitted only when explicitly set, so
        # legacy persisted content and baseline responses keep their exact
        # historical key set.
        for field in (
            "response_kind", "analysis", "draft", "known_facts", "uncertainty_notice",
            "trust_level", "trust_label", "trust_explanation", "source_checked_at",
        ):
            if field not in self.model_fields_set:
                data.pop(field, None)
        return data
