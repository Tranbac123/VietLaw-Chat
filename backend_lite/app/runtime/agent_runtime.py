from __future__ import annotations

from contextlib import contextmanager
import re
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from ..services.demo_llm_generation import DemoOrchestrator

from ..application.conversation_router import route as route_conversation
from ..application.response_templates import render_social_response
from ..application.social_intent_detector import detect_social_intent
from ..constants import CONTRACT_VERSION
from ..contracts.conversation_route import ConversationRoute
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


_REFERENTIAL_ISSUE_PHRASES = (
    "van de nay",
    "vu nay",
    "truong hop tren",
    "thoa thuan do",
    "van de do",
    "viec do",
    "nhu tren",
)
_ELLIPTICAL_FOLLOW_UP_PHRASES = (
    "nen lam gi",
    "phai lam sao",
    "can chuan bi gi",
    "dang gap van de gi",
    "co rui ro khong",
)
_SUBJECT_TOKENS = {"toi", "cong ty", "chu nha", "nguoi khac", "ben ban", "canh sat", "cong an"}
_PROBLEM_TOKENS = {"bi", "khong", "no", "phat", "giu", "mat", "tranh chap"}
_LEGAL_OBJECT_TOKENS = {
    "tien", "nha", "luong", "hop dong", "bien ban", "mu bao hiem", "den do", "tai san", "khoan vay",
}


def _has_phrase(text: str, phrases: set[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _issue_signature(accentless_text: str, detected_topic: str | None = None) -> str | None:
    """Return a small, bounded issue signature, never a response or legal conclusion."""
    if "khong doi mu bao hiem" in accentless_text or "vuot den do" in accentless_text:
        return "traffic_violation"
    if "cong ty" in accentless_text and any(
        phrase in accentless_text for phrase in ("no luong", "khong tra luong", "cham luong")
    ):
        return "employment_wage"
    if re.search(r"\bcho\b.{0,40}\bvay\b", accentless_text) or any(
        phrase in accentless_text for phrase in ("vay tien", "khoan vay", "khong tra no")
    ):
        return "loan_dispute"
    if any(
        phrase in accentless_text
        for phrase in ("tien coc", "dat coc", "khoan coc", "thue nha", "chu nha")
    ):
        return "rental_deposit"
    if "lap bien ban" in accentless_text and any(
        phrase in accentless_text for phrase in ("giao thong", "den do", "loi vi pham")
    ):
        return "traffic_violation"
    if detected_topic and detected_topic not in {
        "unsupported_language", "unsupported_non_legal", "vague_legal",
    }:
        return detected_topic

    word_count = len(re.findall(r"[a-z0-9]+", accentless_text))
    if (
        word_count >= 5
        and _has_phrase(accentless_text, _SUBJECT_TOKENS)
        and _has_phrase(accentless_text, _PROBLEM_TOKENS)
        and _has_phrase(accentless_text, _LEGAL_OBJECT_TOKENS)
    ):
        return "standalone_legal_problem"
    return None


def _is_referential_follow_up(accentless_text: str) -> bool:
    stripped = accentless_text.strip(" !?.,")
    if any(phrase in stripped for phrase in _REFERENTIAL_ISSUE_PHRASES):
        return True
    if any(phrase in stripped for phrase in _ELLIPTICAL_FOLLOW_UP_PHRASES):
        return True
    return stripped.startswith("con ") or (" van " in f" {stripped} " and "thi sao" in stripped)


def _assistant_topic_after(messages: list[ChatMessage], user_index: int) -> str | None:
    for message in messages[user_index + 1:]:
        if message.role == "user":
            return None
        if message.role != "assistant" or message.content_json is None:
            continue
        if message.content_json.response_kind == "social":
            return None
        topic = message.content_json.metadata.get("detected_topic")
        return topic if isinstance(topic, str) else None
    return None


def _latest_issue_boundary(
    messages: list[ChatMessage], normalizer: InputNormalizer
) -> tuple[int, str] | None:
    latest: tuple[int, str] | None = None
    for index, message in enumerate(messages):
        if message.role != "user" or not message.content_text:
            continue
        normalized, accentless = normalizer.normalize(message.content_text)
        if detect_social_intent(normalized) is not None or _is_referential_follow_up(accentless):
            continue
        signature = _issue_signature(accentless, _assistant_topic_after(messages, index))
        if signature is not None:
            latest = (index, signature)
    return latest


def _context_terms(messages: list[ChatMessage], normalizer: InputNormalizer) -> list[str]:
    terms: list[str] = []
    for message in messages:
        if message.content_text:
            _, accentless = normalizer.normalize(message.content_text)
            terms.append(accentless)
        elif message.content_json:
            text = " ".join(
                [message.content_json.summary, *message.content_json.checklist, *message.content_json.next_steps]
            )
            _, accentless = normalizer.normalize(text)
            terms.append(accentless)
    return terms


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

    def _isolate_or_select_active_issue(self, state: AgentState) -> None:
        history = state.chat.history_messages
        boundary = _latest_issue_boundary(history, self.normalizer)
        current_signature = None
        if not _is_referential_follow_up(state.classification.accent_insensitive_question):
            current_signature = _issue_signature(state.classification.accent_insensitive_question)

        if current_signature is not None and (
            boundary is None or current_signature != boundary[1]
        ):
            selected: list[ChatMessage] = []
        elif boundary is not None:
            selected = history[boundary[0]:]
        else:
            selected = history

        state.chat.history_messages = selected
        state.chat.history_message_count = len(selected)
        state.chat.used_current_chat_history = bool(selected)
        state.chat.context_topic_terms = _context_terms(selected, self.normalizer)

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
            )
        )
        state.persistence.user_message_id = f"msg_user_{uuid4().hex}"
        state.persistence.assistant_message_id = f"msg_asst_{uuid4().hex}"

        with self._phase(state, "validate_request"):
            state.request.question = state.request.question.strip()
            if len(state.request.question) < 3:
                raise InvalidRequestError("Câu hỏi phải có ít nhất 3 ký tự.")

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

        with self._phase(state, "classify_conversation_intent"):
            conversational_intent = None
            if state.classification.detected_language == "vi" and not state.classification.unsafe_intent_detected:
                conversational_intent = detect_social_intent(state.classification.normalized_question)
            route_result = route_conversation(conversational_intent)

        if route_result.route is ConversationRoute.DIRECT_RESPONSE:
            with self._phase(state, "build_social_response"):
                assert route_result.template_id is not None  # router invariant for DIRECT_RESPONSE
                social_text = render_social_response(route_result.template_id)
                state.final_response = self.response_builder.build_social(state, route_result, social_text)

            with self._phase(state, "validate_final_response"):
                state.final_response = AnalyzeResponse.model_validate(state.final_response.model_dump(mode="json"))

            with self._phase(state, "store_assistant_message"):
                response = state.final_response
                content = AnalyzeContent.model_validate(
                    response.model_dump(
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

        with self._phase(state, "resolve_active_issue_context"):
            if not state.classification.unsafe_intent_detected:
                self._isolate_or_select_active_issue(state)

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
                        "response_kind", "domain", "risk_level", "decision", "summary", "clarifying_questions",
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
