from __future__ import annotations

from ..constants import CONTRACT_VERSION, SAFETY_NOTICE
from ..contracts.conversation_route import RouteResult
from ..runtime.agent_state import AgentState
from ..schemas.api import AnalyzeResponse
from ..schemas.content import Confidence


class LiteResponseBuilder:
    def build_social(self, state: AgentState, route_result: RouteResult, text: str) -> AnalyzeResponse:
        """Build a truthful `response_kind='social'` response for a direct
        conversational short-circuit (greeting/identity/capability). Unlike
        `build()` below, this method never reads `state.guard`/`state.retrieval`/
        `state.generation` -- those are legal-pipeline fields that are never
        populated for a social turn (see Gate C report section 8: the runtime
        returns before any of those phases run).
        """
        return AnalyzeResponse(
            response_kind="social",
            contract_version=CONTRACT_VERSION,
            request_id=state.request.request_id,
            chat_id=state.chat.chat_id,
            user_message_id=state.persistence.user_message_id,
            assistant_message_id=state.persistence.assistant_message_id,
            domain=None,
            risk_level=None,
            decision=None,
            summary=text,
            clarifying_questions=[],
            checklist=[],
            next_steps=[],
            sources=[],
            safety_notice="",
            confidence=None,
            metadata={
                "conversational_intent": route_result.intent.value,
                "conversation_route": route_result.route.value,
                "reason_code": route_result.reason_code,
            },
        )

    def build(self, state: AgentState) -> AnalyzeResponse:
        content = state.guard.final_content
        if content is None:
            raise ValueError("final content is missing")
        source_by_id = {source.id: source for source in state.retrieval.retrieved_source_objects}
        sources = [source_by_id[source_id] for source_id in content.used_source_ids if source_id in source_by_id]
        base_answer_confidence = 0.78 if sources else 0.48
        answer_adjustment = state.guard.confidence_answer_adjustment or 0.0
        confidence = Confidence(
            domain=0.92 if state.classification.detected_topic else 0.55,
            risk=0.95 if state.guard.final_risk_level == "high" else 0.8,
            answer=max(0.0, min(1.0, base_answer_confidence + answer_adjustment)),
        )
        metadata = {
            "retrieval_count": len(sources),
            "has_sources": bool(sources),
            "retrieval_strategy": state.retrieval.retrieval_strategy,
            "used_llm": state.generation.used_llm,
            "model_name": state.generation.model_name,
            "used_current_chat_history": state.chat.used_current_chat_history,
            "history_message_count": state.chat.history_message_count,
            "unsafe_intent_detected": state.classification.unsafe_intent_detected,
            "high_risk_detected": state.classification.high_risk_detected,
            "detected_topic": state.classification.detected_topic,
            "safety_flags": state.guard.final_safety_flags,
            "guards_applied": {
                "citation_guard": state.guard.citation_guard_applied,
                "safety_guard": state.guard.safety_guard_applied,
                "fallback_used": False,
            },
            "llm_parse_error": False,
            "runtime_trace": list(state.trace.completed_phases),
            "guard_warnings": list(state.trace.warnings),
            "citation_removed_source_ids": list(state.guard.citation_removed_source_ids),
            "citation_content_cautioned": state.guard.citation_content_cautioned,
            "asked_question_ids": list(content.asked_question_ids),
        }
        return AnalyzeResponse(
            contract_version=CONTRACT_VERSION,
            request_id=state.request.request_id,
            chat_id=state.chat.chat_id,
            user_message_id=state.persistence.user_message_id,
            assistant_message_id=state.persistence.assistant_message_id,
            domain=state.guard.final_domain,
            risk_level=state.guard.final_risk_level,
            decision=state.guard.final_decision,
            summary=content.summary,
            clarifying_questions=content.clarifying_questions,
            checklist=content.checklist,
            next_steps=content.next_steps,
            sources=sources,
            safety_notice=SAFETY_NOTICE,
            confidence=confidence,
            metadata=metadata,
        )
