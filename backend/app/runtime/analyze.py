"""analyze() orchestrator. The callable the HTTP layer mounts.

Wires the full pipeline: validate → chat → store user → context → normalize →
language gate → unsafe → domain/risk/decision → RAG → (LLM only on guidance paths)
→ parse → citation guard → safety guard → response build → store assistant.
Raises typed errors (InvalidRequest/ChatNotFound/LlmError/...) for the HTTP layer
to map; never returns the error schema itself.
"""
import uuid
from typing import Optional

from app.guards import citation_guard, safety_guard
from app.llm import content_templates as ct
from app.triage import decision_policy, legal_triage, risk_classifier
from app.stores.chat_store import ChatStore
from app.config import Settings
from app.services.context_builder import build_context
from app.errors import InvalidRequest
from app.nlp.input_normalizer import normalize
from app.nlp.language_detector import is_vietnamese
from app.llm.llm_client import LLMClient
from app.llm.output_parser import parse_content_or_fallback
from app.nlp.patterns import PatternBank
from app.llm.prompt_builder import build_prompt
from app.rag.rag_retriever import RetrievalResult, Retriever, load_snippets
from app.services.response_builder import build as build_response
from app.schemas import AnalyzeRequest, AnalyzeResponse, Decision, Domain, RiskLevel
from app.triage.unsafe_intent_detector import detect

_GUIDANCE = {Decision.answer_with_guidance, Decision.ask_clarifying_questions}
_EMPTY_RETRIEVAL = RetrievalResult(retrieval_strategy="none")


class AiCore:
    def __init__(self, settings: Settings, *, store: Optional[ChatStore] = None,
                 bank: Optional[PatternBank] = None, retriever: Optional[Retriever] = None,
                 llm=None):
        self.settings = settings
        self.store = store or ChatStore(settings.chat_db_path)
        self.bank = bank or PatternBank.load(settings.unsafe_patterns_path)
        self.retriever = retriever or Retriever(load_snippets(settings.legal_snippets_path))
        self.llm = llm or LLMClient(settings)

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        request_id = "req_" + uuid.uuid4().hex[:12]

        # --- chat resolution ---
        if request.chat_id is None:
            if not request.session_id:
                raise InvalidRequest("session_id is required when chat_id is omitted")
            chat = self.store.create_chat(session_id=request.session_id)
        else:
            chat = self.store.get_chat(request.chat_id)
            self.store.validate_session_boundary(chat, request.session_id)

        user_message_id = self.store.store_user_message(chat.chat_id, request.question)
        assistant_message_id = "msg_asst_" + uuid.uuid4().hex[:12]

        context = build_context(self.store, chat.chat_id, request.question,
                                window=self.settings.history_window)
        norm = normalize(request.question)

        # --- language gate ---
        if not is_vietnamese(norm, request.language, self.bank):
            response = self._finalize(
                request_id, chat.chat_id, user_message_id, assistant_message_id,
                Domain.unknown, RiskLevel.low, Decision.unsupported,
                ct.unsupported_content(self.bank, reason="language"),
                _EMPTY_RETRIEVAL, context, used_llm=False, unsafe_detected=False,
                detected_topic=None, safety_flags=[],
            )
            return self._store_and_return(chat.chat_id, response)

        # --- deterministic classification ---
        unsafe = detect(norm.accent_insensitive, self.bank)
        dom = legal_triage.classify(norm, unsafe, self.bank)
        # Follow-up understanding: if this turn alone is unclassifiable but the
        # chat already has a domain, inherit it. Never overrides per-turn unsafe.
        if not unsafe.detected and dom.domain == Domain.unknown:
            prior = self._prior_domain(context)
            if prior and prior != Domain.unknown:
                dom = legal_triage.DomainResult(prior, confidence=0.6)
        risk = risk_classifier.classify(norm, dom, unsafe, self.bank)
        decision = decision_policy.decide(dom, risk, unsafe)

        # --- RAG ---
        retrieved = self.retriever.retrieve(
            norm, domain=dom.domain, decision=decision,
            detected_topic=dom.detected_topic, context_terms=context.context_terms)

        # Empty retrieval must not yield ungrounded substantive guidance (spec:
        # no strong legal claims when sources are empty). Degrade to asking for
        # the specifics that would let RAG ground a follow-up turn. This is the
        # backstop for any domain — notably administrative, whose generic
        # procedural match can select a topic with no matching snippet.
        if decision == Decision.answer_with_guidance and not retrieved.has_sources:
            decision = Decision.ask_clarifying_questions

        parse_error = False
        citation_note = None
        safety_note = None
        safety_flags = list(unsafe.safety_flags)
        used_llm = False

        if decision in _GUIDANCE:
            # LLM authors content only on benign guidance paths.
            prompt = build_prompt(request.question, context.context_summary, dom.domain,
                                  risk.risk, decision, retrieved.sources,
                                  retrieved.allowed_source_ids)
            raw = self.llm.generate(prompt)  # raises LlmError → 503
            used_llm = True
            content, parse_error = parse_content_or_fallback(
                raw, retrieved.allowed_source_ids, dom.domain, self.bank)
            content, citation_note = citation_guard.apply(content, retrieved.allowed_source_ids)

            guard = safety_guard.apply(content, dom.domain, risk.risk, decision, self.bank)
            content = guard.content
            domain_final, risk_final, decision_final = guard.domain, guard.risk_level, guard.decision
            if guard.guard_triggered:
                safety_flags += guard.safety_flags
                safety_note = "safety_guard escalated generated content"
            sources_for_build = retrieved
        else:
            # Templated, pre-vetted content (refuse / escalate / unsupported non-legal).
            content = self._templated_content(decision, dom.domain, unsafe)
            domain_final, risk_final, decision_final = dom.domain, risk.risk, decision
            # Refuse/escalate may surface safety/high-risk sources; unsupported shows none.
            sources_for_build = _EMPTY_RETRIEVAL if decision == Decision.unsupported else retrieved

        response = self._finalize(
            request_id, chat.chat_id, user_message_id, assistant_message_id,
            domain_final, risk_final, decision_final, content, sources_for_build, context,
            used_llm=used_llm, unsafe_detected=unsafe.detected,
            detected_topic=dom.detected_topic, safety_flags=safety_flags,
            parse_error=parse_error, citation_note=citation_note, safety_note=safety_note,
            domain_conf=dom.confidence, risk_conf=risk.confidence,
        )
        return self._store_and_return(chat.chat_id, response)

    # ------------------------------------------------------------ helpers

    def _prior_domain(self, context) -> Optional[Domain]:
        for m in reversed(context.recent_messages):
            if m.role.value == "assistant" and m.content_json:
                try:
                    return Domain(m.content_json.get("domain"))
                except ValueError:
                    return None
        return None

    def _templated_content(self, decision, domain, unsafe):
        if decision == Decision.refuse_unsafe_request:
            return ct.refusal_content(unsafe, self.bank)
        if decision == Decision.recommend_professional_help:
            return ct.escalation_content(domain, self.bank)
        return ct.unsupported_content(self.bank, reason="non_legal")

    def _finalize(self, request_id, chat_id, user_message_id, assistant_message_id,
                  domain, risk_level, decision, content, retrieved, context, *,
                  used_llm, unsafe_detected, detected_topic, safety_flags,
                  parse_error=False, citation_note=None, safety_note=None,
                  domain_conf=0.6, risk_conf=0.7) -> AnalyzeResponse:
        return build_response(
            request_id=request_id, chat_id=chat_id, user_message_id=user_message_id,
            assistant_message_id=assistant_message_id, domain=domain, risk_level=risk_level,
            decision=decision, content=content, retrieved=retrieved, settings=self.settings,
            context=context, used_llm=used_llm, unsafe_detected=unsafe_detected,
            detected_topic=detected_topic, safety_flags=safety_flags, parse_error=parse_error,
            citation_note=citation_note, safety_note=safety_note, fallback_used=parse_error,
            domain_conf=domain_conf, risk_conf=risk_conf,
        )

    def _store_and_return(self, chat_id: str, response: AnalyzeResponse) -> AnalyzeResponse:
        # Store only the final, validated assistant response.
        content_json = {
            "domain": response.domain.value,
            "risk_level": response.risk_level.value,
            "decision": response.decision.value,
            "summary": response.summary,
            "clarifying_questions": response.clarifying_questions,
            "checklist": response.checklist,
            "next_steps": response.next_steps,
            "sources": [s.model_dump() for s in response.sources],
            "safety_notice": response.safety_notice,
        }
        self.store.store_assistant_message(chat_id, response.assistant_message_id, content_json)
        return response
