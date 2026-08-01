from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..schemas.chat import ChatMessage
from ..schemas.content import Decision, Domain, GeneratedContent, RiskLevel, SourceObject


@dataclass
class RequestState:
    request_id: str
    contract_version: str
    session_id: str
    requested_chat_id: str | None
    question: str
    user_type: str
    language: str
    # FAST DEMO V2 client-supplied idempotency key (stable across transport
    # retries of one user submission). Defaulted so every existing construction
    # site keeps working.
    client_request_id: str | None = None


@dataclass
class ChatState:
    chat_id: str = ""
    is_new_chat: bool = False
    history_messages: list[ChatMessage] = field(default_factory=list)
    history_message_count: int = 0
    context_topic_terms: list[str] = field(default_factory=list)
    used_current_chat_history: bool = False


@dataclass
class ClassificationState:
    normalized_question: str = ""
    accent_insensitive_question: str = ""
    detected_language: str = "vi"
    domain: Domain = "unknown"
    risk_level: RiskLevel = "low"
    decision: Decision = "ask_clarifying_questions"
    unsafe_intent_detected: bool = False
    high_risk_detected: bool = False
    detected_topic: str | None = None
    safety_flags: list[str] = field(default_factory=list)
    unsafe_category: str | None = None


@dataclass
class RetrievalState:
    combined_query: str = ""
    retrieved_sources: list[Any] = field(default_factory=list)
    retrieved_source_objects: list[SourceObject] = field(default_factory=list)
    retrieved_source_ids: list[str] = field(default_factory=list)
    retrieval_count: int = 0
    retrieval_strategy: str = ""
    rag_loaded: bool = False


@dataclass
class GenerationState:
    generated_content: GeneratedContent | None = None
    used_source_ids: list[str] = field(default_factory=list)
    used_llm: bool = False
    model_name: str = ""


@dataclass
class GuardState:
    citation_guard_applied: bool = False
    safety_guard_applied: bool = False
    guard_triggered: bool = False
    final_domain: Domain = "unknown"
    final_risk_level: RiskLevel = "low"
    final_decision: Decision = "ask_clarifying_questions"
    final_content: GeneratedContent | None = None
    final_safety_flags: list[str] = field(default_factory=list)
    citation_removed_source_ids: list[str] = field(default_factory=list)
    citation_content_cautioned: bool = False
    confidence_answer_adjustment: float | None = None


@dataclass
class PersistenceState:
    user_message_id: str = ""
    assistant_message_id: str = ""
    user_message_stored: bool = False
    assistant_message_stored: bool = False


@dataclass
class TraceState:
    completed_phases: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed_ms: dict[str, float] = field(default_factory=dict)


@dataclass
class AgentState:
    request: RequestState
    chat: ChatState = field(default_factory=ChatState)
    classification: ClassificationState = field(default_factory=ClassificationState)
    retrieval: RetrievalState = field(default_factory=RetrievalState)
    generation: GenerationState = field(default_factory=GenerationState)
    guard: GuardState = field(default_factory=GuardState)
    persistence: PersistenceState = field(default_factory=PersistenceState)
    trace: TraceState = field(default_factory=TraceState)
    final_response: Any | None = None
