"""Response builder. The ONLY place a final response is assembled.

Attaches all backend-owned fields (ids, sources, safety_notice, confidence, metadata),
maps used_source_ids → full Source objects from the retrieved set, and validates via
Pydantic. It never retrieves, classifies, calls the LLM, or makes safety decisions.
"""
from typing import Optional

from app.config import SAFETY_NOTICE, Settings
from app.services.context_builder import Context
from app.rag.rag_retriever import RetrievalResult, RetrievedSource
from app.schemas import (
    AnalyzeResponse, Confidence, Decision, Domain, GuardsApplied, LLMContent,
    Metadata, RiskLevel, Source,
)


def _to_source(s: RetrievedSource) -> Source:
    return Source(
        id=s.id, title=s.title, source_name=s.source_name, url=s.source_url,
        snippet=s.text, source_type=s.source_type, last_checked=s.last_checked,
    )


def _answer_confidence(has_sources: bool, domain: Domain, fallback: bool) -> float:
    if fallback:
        return 0.25
    conf = 0.7 if has_sources else 0.4
    if domain == Domain.high_risk:
        conf = min(conf, 0.5)
    return conf


def build(*, request_id: str, chat_id: str, user_message_id: str, assistant_message_id: str,
          domain: Domain, risk_level: RiskLevel, decision: Decision, content: LLMContent,
          retrieved: RetrievalResult, settings: Settings, context: Optional[Context],
          used_llm: bool, unsafe_detected: bool, detected_topic: Optional[str],
          safety_flags: Optional[list[str]] = None, parse_error: bool = False,
          citation_note: Optional[str] = None, safety_note: Optional[str] = None,
          fallback_used: bool = False, domain_conf: float = 0.6,
          risk_conf: float = 0.7) -> AnalyzeResponse:
    by_id = {s.id: s for s in retrieved.sources}

    # Map used_source_ids → sources. If nothing was explicitly cited, surface the
    # retrieved set (still from RAG, never fabricated) so the panel isn't empty —
    # including safety/high-risk sources on a refusal/escalation.
    # Only `unsupported` shows no sources.
    if content.used_source_ids:
        used = [by_id[i] for i in content.used_source_ids if i in by_id]
    elif decision == Decision.unsupported:
        used = []
    else:
        used = list(retrieved.sources)
    sources = [_to_source(s) for s in used]

    ctx = context or Context()
    metadata = Metadata(
        retrieval_count=retrieved.retrieval_count,
        has_sources=bool(sources),
        retrieval_strategy=retrieved.retrieval_strategy if retrieved.sources else "none",
        used_llm=used_llm,
        model_name=settings.ai_model_name,
        used_current_chat_history=ctx.used_history,
        history_message_count=ctx.history_message_count,
        unsafe_intent_detected=unsafe_detected,
        high_risk_detected=domain == Domain.high_risk or unsafe_detected,
        detected_topic=detected_topic,
        safety_flags=safety_flags or [],
        guards_applied=GuardsApplied(citation_guard=True, safety_guard=True,
                                     fallback_used=fallback_used),
        llm_parse_error=True if parse_error else None,
        citation_guard_notes=citation_note,
        safety_guard_notes=safety_note,
    )

    return AnalyzeResponse(
        request_id=request_id, chat_id=chat_id, user_message_id=user_message_id,
        assistant_message_id=assistant_message_id, domain=domain, risk_level=risk_level,
        decision=decision, summary=content.summary,
        clarifying_questions=content.clarifying_questions, checklist=content.checklist,
        next_steps=content.next_steps, sources=sources, safety_notice=SAFETY_NOTICE,
        confidence=Confidence(
            domain=domain_conf, risk=risk_conf,
            answer=_answer_confidence(bool(sources), domain, parse_error or fallback_used),
        ),
        metadata=metadata,
    )
