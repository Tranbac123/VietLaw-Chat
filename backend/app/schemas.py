"""Pydantic models.

Split by ownership:
- LLMContent = the 5 whitelisted fields the LLM produces.
- AnalyzeResponse = the full backend-owned response the Response Builder assembles.
"""
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------- enums

class Domain(str, Enum):
    civil_dispute = "civil_dispute"
    traffic = "traffic"
    household_business = "household_business"
    administrative = "administrative"
    high_risk = "high_risk"
    unknown = "unknown"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Decision(str, Enum):
    answer_with_guidance = "answer_with_guidance"
    ask_clarifying_questions = "ask_clarifying_questions"
    recommend_professional_help = "recommend_professional_help"
    refuse_unsafe_request = "refuse_unsafe_request"
    unsupported = "unsupported"


class UserType(str, Enum):
    citizen = "citizen"
    household_business = "household_business"
    sme = "sme"
    unknown = "unknown"


class SourceType(str, Enum):
    official_source = "official_source"
    procedure = "procedure"
    legal_snippet = "legal_snippet"
    curated_note = "curated_note"
    safety_policy = "safety_policy"
    demo_only = "demo_only"


class Role(str, Enum):
    user = "user"
    assistant = "assistant"


class ContentType(str, Enum):
    text = "text"
    structured = "structured"


# ---------------------------------------------------------------- request

class AnalyzeRequest(BaseModel):
    question: str = Field(min_length=3, max_length=3000)
    user_type: UserType = UserType.unknown
    chat_id: Optional[str] = None
    session_id: Optional[str] = Field(default=None, max_length=128)
    language: str = "vi"

    @field_validator("question", mode="before")
    @classmethod
    def _strip_question(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


# ---------------------------------------------------------------- response parts

class Source(BaseModel):
    id: str
    title: str
    source_name: str
    url: Optional[str] = None
    snippet: str
    source_type: SourceType
    last_checked: str


class Confidence(BaseModel):
    domain: float = Field(ge=0.0, le=1.0)
    risk: float = Field(ge=0.0, le=1.0)
    answer: float = Field(ge=0.0, le=1.0)


class GuardsApplied(BaseModel):
    citation_guard: bool = True
    safety_guard: bool = True
    fallback_used: bool = False


class Metadata(BaseModel):
    retrieval_count: int
    has_sources: bool
    retrieval_strategy: str
    used_llm: bool
    model_name: str
    used_current_chat_history: bool
    history_message_count: int
    unsafe_intent_detected: bool
    high_risk_detected: bool
    detected_topic: Optional[str] = None
    safety_flags: list[str] = Field(default_factory=list)
    guards_applied: GuardsApplied
    # optional debug extras
    llm_parse_error: Optional[bool] = None
    retrieval_error_recovered: Optional[bool] = None
    citation_guard_notes: Optional[str] = None
    safety_guard_notes: Optional[str] = None


class LLMContent(BaseModel):
    """The only fields the LLM may produce (whitelist)."""
    summary: str
    clarifying_questions: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    used_source_ids: list[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    contract_version: Literal["v1"] = "v1"
    request_id: str
    chat_id: str
    user_message_id: str
    assistant_message_id: str
    domain: Domain
    risk_level: RiskLevel
    decision: Decision
    summary: str
    clarifying_questions: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    safety_notice: str
    confidence: Confidence
    metadata: Metadata


# ---------------------------------------------------------------- error

class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    contract_version: Literal["v1"] = "v1"
    request_id: str
    error: ErrorDetail
    safety_notice: str


# ---------------------------------------------------------------- chat store / chat endpoints

class ChatRecord(BaseModel):
    chat_id: str
    session_id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
    deleted_at: Optional[str] = None


class MessageOut(BaseModel):
    message_id: str
    role: Role
    content_type: ContentType
    content_text: Optional[str] = None
    content_json: Optional[dict] = None
    created_at: str


class ChatDetail(BaseModel):
    contract_version: Literal["v1"] = "v1"
    chat_id: str
    session_id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
    messages: list[MessageOut] = Field(default_factory=list)


class ChatListItem(BaseModel):
    chat_id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
    last_message_preview: Optional[str] = None
    domain: Optional[Domain] = None
    risk_level: Optional[RiskLevel] = None
    message_count: int


class ChatListResponse(BaseModel):
    contract_version: Literal["v1"] = "v1"
    session_id: str
    chats: list[ChatListItem] = Field(default_factory=list)
