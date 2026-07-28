from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from ..services.demo_llm_generation import DemoOrchestrator

from ..constants import CONTRACT_VERSION
from ..errors import ChatNotFoundError, InvalidRequestError
from ..schemas.api import AnalyzeRequest, AnalyzeResponse
from ..schemas.chat import ChatMessage
from ..schemas.content import AnalyzeContent
from ..services.input_normalizer import InputNormalizer
from ..stores.sqlite_chat_store import utc_now
from .agent_state import AgentState, RequestState
from .protocols import (
    ChatStore,
    CitationGuard,
    ContentGenerator,
    ContextBuilder,
    DecisionPolicy,
    DomainClassifier,
    LanguageDetector,
    ResponseBuilder,
    Retriever,
    RiskClassifier,
    SafetyGuard,
    TitleService,
    UnsafeDetector,
)


class AgentRuntime:
    def __init__(
        self,
        chat_store: ChatStore,
        context_builder: ContextBuilder,
        normalizer: InputNormalizer,
        language_detector: LanguageDetector,
        unsafe_detector: UnsafeDetector,
        domain_classifier: DomainClassifier,
        risk_classifier: RiskClassifier,
        decision_policy: DecisionPolicy,
        retriever: Retriever,
        content_generator: ContentGenerator,
        citation_guard: CitationGuard,
        safety_guard: SafetyGuard,
        response_builder: ResponseBuilder,
        title_service: TitleService,
        demo_orchestrator: "DemoOrchestrator | None" = None,
        fast_demo_orchestrator=None,
    ) -> None:
        self.chat_store = chat_store
        self.context_builder = context_builder
        self.normalizer = normalizer
        self.language_detector = language_detector
        self.unsafe_detector = unsafe_detector
        self.domain_classifier = domain_classifier
        self.risk_classifier = risk_classifier
        self.decision_policy = decision_policy
        self.retriever = retriever
        self.content_generator = content_generator
        self.citation_guard = citation_guard
        self.safety_guard = safety_guard
        self.response_builder = response_builder
        self.title_service = title_service
        self.demo_orchestrator = demo_orchestrator
        self.fast_demo_orchestrator = fast_demo_orchestrator

    @contextmanager
    def _phase(self, state: AgentState, name: str):
        started = perf_counter()
        try:
            yield
        except Exception:
            state.trace.errors.append(name)
            raise
        else:
            state.trace.completed_phases.append(name)
        finally:
            state.trace.elapsed_ms[name] = round((perf_counter() - started) * 1000, 3)

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        state = AgentState(
            request=RequestState(
                request_id=f"req_{uuid4().hex}",
                contract_version=CONTRACT_VERSION,
                session_id=request.session_id,
                requested_chat_id=request.chat_id,
                question=request.question,
                user_type=request.user_type,
                language=request.language,
                client_request_id=request.client_request_id,
            )
        )
        state.persistence.user_message_id = f"msg_user_{uuid4().hex}"
        state.persistence.assistant_message_id = f"msg_asst_{uuid4().hex}"

        with self._phase(state, "validate_request"):
            state.request.question = state.request.question.strip()
            # Whitespace-only stays invalid; every other non-empty message is a
            # real turn and must reach routing. A short message the assistant
            # cannot act on is answered, not rejected as malformed data.
            if not state.request.question:
                raise InvalidRequestError("Bạn nhập nội dung tin nhắn giúp tôi nhé.")

        with self._phase(state, "resolve_or_create_chat"):
            if state.request.requested_chat_id:
                chat = self.chat_store.get_chat_for_session(
                    state.request.requested_chat_id,
                    state.request.session_id,
                )
                if chat is None:
                    raise ChatNotFoundError()
                state.chat.chat_id = chat.chat_id
            else:
                chat = self.chat_store.create_chat(
                    state.request.session_id,
                    self.title_service.make(state.request.question),
                )
                state.chat.chat_id = chat.chat_id
                state.chat.is_new_chat = True

        with self._phase(state, "store_user_message"):
            self.chat_store.add_message(
                ChatMessage(
                    message_id=state.persistence.user_message_id,
                    chat_id=state.chat.chat_id,
                    role="user",
                    content_type="text",
                    content_text=state.request.question,
                    content_json=None,
                    created_at=utc_now(),
                )
            )
            state.persistence.user_message_stored = True

        with self._phase(state, "build_same_chat_context"):
            self.context_builder.build(state)

        with self._phase(state, "normalize_input"):
            normalized, accentless = self.normalizer.normalize(state.request.question)
            state.classification.normalized_question = normalized
            state.classification.accent_insensitive_question = accentless

        with self._phase(state, "detect_language"):
            state.classification.detected_language = self.language_detector.detect(
                state.classification.normalized_question,
                state.classification.accent_insensitive_question,
                state.request.language,
            )

        with self._phase(state, "detect_unsafe_intent"):
            if state.classification.detected_language == "vi":
                detection = self.unsafe_detector.detect(state.classification.accent_insensitive_question)
                state.classification.unsafe_intent_detected = detection.unsafe
                state.classification.high_risk_detected = detection.high_risk
                state.classification.unsafe_category = detection.category
                state.classification.detected_topic = detection.detected_topic
                state.classification.safety_flags = detection.safety_flags
                if detection.expected_decision:
                    state.classification.decision = detection.expected_decision

        # FAST DEMO V2 hook (48-hour video path). Active only when a fast-demo
        # orchestrator was wired (VIETLAW_FAST_DEMO_V2_ENABLED). It runs ahead of
        # the V1 demo slice and the baseline, owns its own deterministic safety
        # route, and -- like the V1 hook -- any failure is contained and defers
        # to the pipeline below rather than surfacing a 500.
        if self.fast_demo_orchestrator is not None:
            fast_response = None
            try:
                with self._phase(state, "fast_demo_v2"):
                    fast_response = await self.fast_demo_orchestrator.handle(state)
            except Exception:  # noqa: BLE001 - contain; never leak a raw error
                state.trace.warnings.append("fast_demo_v2_deferred")
                fast_response = None
            if fast_response is not None:
                state.final_response = fast_response
                with self._phase(state, "validate_final_response"):
                    state.final_response = AnalyzeResponse.model_validate(
                        state.final_response.model_dump(mode="json")
                    )
                with self._phase(state, "store_assistant_message"):
                    content = AnalyzeContent.model_validate(
                        state.final_response.model_dump(
                            mode="json",
                            include={
                                "response_kind", "domain", "risk_level", "decision", "summary",
                                "clarifying_questions", "checklist", "next_steps", "sources",
                                "safety_notice", "confidence", "metadata",
                                "analysis", "draft", "known_facts", "uncertainty_notice",
                            },
                        )
                    )
                    self.chat_store.add_message(
                        ChatMessage(
                            message_id=state.persistence.assistant_message_id,
                            chat_id=state.chat.chat_id,
                            role="assistant",
                            content_type="structured",
                            content_text=None,
                            content_json=content,
                            created_at=utc_now(),
                        )
                    )
                    state.persistence.assistant_message_stored = True
                with self._phase(state, "return_response"):
                    return state.final_response

        # DEMO VERTICAL SLICE V1 hook. Only active when a demo orchestrator was wired
        # (feature flag on); otherwise this block is skipped entirely and the baseline
        # runtime below is unchanged. Safety turns are never handled here -- the
        # orchestrator returns None for them, deferring to the baseline pipeline.
        if self.demo_orchestrator is not None:
            demo_response = None
            try:
                with self._phase(state, "demo_vertical_slice"):
                    demo_response = await self.demo_orchestrator.handle(state)
            except Exception:  # noqa: BLE001 - contain demo failure; defer to baseline, no 500, no raw leak
                state.trace.warnings.append("demo_vertical_slice_deferred")
                demo_response = None
            if demo_response is not None:
                state.final_response = demo_response
                with self._phase(state, "validate_final_response"):
                    state.final_response = AnalyzeResponse.model_validate(
                        state.final_response.model_dump(mode="json")
                    )
                with self._phase(state, "store_assistant_message"):
                    content = AnalyzeContent.model_validate(
                        state.final_response.model_dump(
                            mode="json",
                            include={
                                "response_kind", "domain", "risk_level", "decision", "summary",
                                "clarifying_questions", "checklist", "next_steps", "sources",
                                "safety_notice", "confidence", "metadata",
                            },
                        )
                    )
                    self.chat_store.add_message(
                        ChatMessage(
                            message_id=state.persistence.assistant_message_id,
                            chat_id=state.chat.chat_id,
                            role="assistant",
                            content_type="structured",
                            content_text=None,
                            content_json=content,
                            created_at=utc_now(),
                        )
                    )
                    state.persistence.assistant_message_stored = True
                with self._phase(state, "return_response"):
                    return state.final_response

        with self._phase(state, "classify_domain"):
            domain, topic = self.domain_classifier.classify(state)
            state.classification.domain = domain
            state.classification.detected_topic = topic or state.classification.detected_topic

        with self._phase(state, "classify_risk"):
            state.classification.risk_level = self.risk_classifier.classify(state)

        with self._phase(state, "choose_decision"):
            state.classification.decision = self.decision_policy.choose(state)

        with self._phase(state, "retrieve_sources"):
            retrieval = self.retriever.retrieve(state)
            state.retrieval.combined_query = retrieval.combined_query
            state.retrieval.retrieved_sources = retrieval.sources
            state.retrieval.retrieved_source_objects = retrieval.source_objects
            state.retrieval.retrieved_source_ids = [source.id for source in retrieval.source_objects]
            state.retrieval.retrieval_count = len(retrieval.source_objects)
            state.retrieval.retrieval_strategy = retrieval.strategy
            state.retrieval.rag_loaded = True

        with self._phase(state, "generate_content"):
            state.generation.generated_content = await self.content_generator.generate(state)
            state.generation.used_source_ids = state.generation.generated_content.used_source_ids
            state.generation.used_llm = self.content_generator.used_llm
            state.generation.model_name = self.content_generator.model_name

        with self._phase(state, "apply_citation_guard"):
            citation_result = self.citation_guard.apply(state)
            state.guard.final_content = citation_result.content
            state.guard.citation_removed_source_ids = citation_result.removed_source_ids
            state.guard.citation_content_cautioned = citation_result.content_cautioned
            state.guard.confidence_answer_adjustment = citation_result.confidence_adjustment
            state.guard.guard_triggered = state.guard.guard_triggered or citation_result.guard_triggered

        with self._phase(state, "apply_safety_guard"):
            result = self.safety_guard.apply(state)
            state.guard.final_content = result.content
            state.guard.final_domain = result.domain
            state.guard.final_risk_level = result.risk_level
            state.guard.final_decision = result.decision
            state.guard.final_safety_flags = result.safety_flags
            state.guard.guard_triggered = result.guard_triggered

        with self._phase(state, "build_final_response"):
            state.final_response = self.response_builder.build(state)

        with self._phase(state, "validate_final_response"):
            state.final_response = AnalyzeResponse.model_validate(state.final_response.model_dump(mode="json"))

        with self._phase(state, "store_assistant_message"):
            response = state.final_response
            content = AnalyzeContent.model_validate(
                response.model_dump(
                    mode="json",
                    include={
                        "domain", "risk_level", "decision", "summary", "clarifying_questions",
                        "checklist", "next_steps", "sources", "safety_notice", "confidence", "metadata",
                    },
                )
            )
            self.chat_store.add_message(
                ChatMessage(
                    message_id=state.persistence.assistant_message_id,
                    chat_id=state.chat.chat_id,
                    role="assistant",
                    content_type="structured",
                    content_text=None,
                    content_json=content,
                    created_at=utc_now(),
                )
            )
            state.persistence.assistant_message_stored = True

        with self._phase(state, "return_response"):
            return state.final_response

        raise RuntimeError("unreachable")
