from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from ..services.demo_llm_generation import DemoOrchestrator

from dataclasses import dataclass, field
from typing import Callable

from ..application.fingerprint import fingerprint_request
from ..constants import CONTRACT_VERSION
from ..errors import (
    ChatNotFoundError,
    IdempotencyConflictError,
    IdempotencyUnavailableError,
    InvalidRequestError,
    RequestInProgressError,
)
from ..schemas.api import AnalyzeRequest, AnalyzeResponse
from ..stores.fast_demo_request_receipts import RequestReceiptStoreError
from ..stores.sqlite_chat_store import ChatStartNotCommittedError
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


# Outcome of the atomic chat/first-user-message write. The release rule reads
# these and nothing else:
#
#   NOT_ATTEMPTED       nothing ran            -> release permitted
#   PROVEN_NOT_COMMITTED transaction rolled back -> release permitted
#   COMMITTED           rows are durable        -> never release
#   OUTCOME_UNKNOWN     commit/rollback ambiguous -> never release
#
# A failed row read-back can never upgrade uncertainty into a release.
CHAT_START_NOT_ATTEMPTED = "not_attempted"
CHAT_START_PROVEN_NOT_COMMITTED = "proven_not_committed"
CHAT_START_COMMITTED = "committed"
CHAT_START_OUTCOME_UNKNOWN = "outcome_unknown"

_RELEASE_PERMITTED_OUTCOMES = frozenset(
    {CHAT_START_NOT_ATTEMPTED, CHAT_START_PROVEN_NOT_COMMITTED}
)


@dataclass
class _TurnBinding:
    """Identities reserved for one logical turn, plus the hooks the receipt
    layer uses to observe it. Kept out of ``AgentState`` so the exactly-once
    concern does not leak into the analysis contract."""

    user_message_id: str
    assistant_message_id: str
    #: Pre-minted identity for a new chat. Reserved before the row exists so the
    #: receipt can be bound first and recovered after a crash.
    reserved_chat_id: str = ""
    #: The chat this turn actually resolved to, once known.
    chat_id: str | None = None
    #: Explicit outcome of the chat/first-user-message write. Never inferred
    #: from "the call raised": only PROVEN_NOT_COMMITTED authorises a release.
    chat_start_outcome: str = CHAT_START_NOT_ATTEMPTED
    on_chat_bound: Callable[[str], None] | None = None
    state: AgentState | None = field(default=None, repr=False)


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
        legal_fallback_orchestrator=None,
        request_receipts=None,
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
        # Public Beta V0: optional sibling hook, only ever consulted when
        # `fast_demo_orchestrator` itself declined the turn as out of its
        # scope (see the branch in `_analyze_turn` below). When absent
        # (default), `_analyze_turn`'s behavior for every route is
        # byte-identical to before this vertical existed.
        self.legal_fallback_orchestrator = legal_fallback_orchestrator
        # Optional: when absent, analyze() keeps its exact legacy behaviour.
        self.request_receipts = request_receipts

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
        """Exactly-once entry point.

        When a ``client_request_id`` is supplied and a receipt store is wired,
        one logical turn is claimed *before* any chat or message row is written,
        so a replay can never add a second user/assistant pair, a second chat, a
        second provider call or a second fact application. Without either of
        those the behaviour is exactly the legacy path.
        """

        binding = _TurnBinding(
            user_message_id=f"msg_user_{uuid4().hex}",
            assistant_message_id=f"msg_asst_{uuid4().hex}",
            reserved_chat_id=f"chat_{uuid4().hex}",
        )
        client_request_id = (request.client_request_id or "").strip()
        if not client_request_id:
            # Unkeyed: the caller never asked for exactly-once, so the legacy
            # path is still the correct behaviour.
            return await self._analyze_turn(request, binding)
        if self.request_receipts is None:
            # Keyed requests fail closed. Running them on the legacy path would
            # honour the key's promise in name only.
            raise IdempotencyUnavailableError()

        session_id = request.session_id
        fingerprint = self._request_fingerprint(request, request.chat_id)

        try:
            outcome = self.request_receipts.reserve(
                session_id=session_id,
                client_request_id=client_request_id,
                request_fingerprint=fingerprint,
                user_message_id=binding.user_message_id,
                assistant_message_id=binding.assistant_message_id,
            )
        except RequestReceiptStoreError as exc:
            # Reservation is the gate that makes the key mean anything. If it
            # cannot be taken, nothing runs: no chat, no message, no provider
            # call, no fact write. The raw SQLite error never reaches the user.
            raise IdempotencyUnavailableError() from exc

        if not outcome.reserved:
            existing = outcome.receipt
            # A reused key with a different request must never replay an
            # unrelated answer, and must not run: zero writes, zero provider.
            if not self._fingerprint_compatible(request, existing):
                raise IdempotencyConflictError()
            if existing.is_complete:
                return self._replayed_response(existing.response)
            # Still pending: another attempt owns this turn. Starting a second
            # provider call could duplicate its effects, so refuse in a
            # controlled way and leave the receipt for explicit review.
            raise RequestInProgressError()

        binding.on_chat_bound = lambda chat_id: self._bind_receipt_chat(
            session_id, client_request_id, chat_id
        )
        try:
            response = await self._analyze_turn(request, binding)
        except Exception:
            # Release only after *proving* the turn left nothing behind. The
            # previous test -- "the user message was not stored" -- was not a
            # valid boundary: the chat row could already exist, and releasing
            # then let a retry build a second chat beside the orphan.
            if self._turn_left_no_trace(binding):
                self._release_receipt(session_id, client_request_id)
            raise

        try:
            self.request_receipts.complete(
                session_id=session_id,
                client_request_id=client_request_id,
                response=response.model_dump(mode="json"),
            )
        except RequestReceiptStoreError:
            # The turn itself succeeded and is already persisted; failing to
            # record the snapshot must not turn that into an error for the user.
            pass
        return response

    @staticmethod
    def _replayed_response(payload: dict) -> AnalyzeResponse:
        """Return the stored turn verbatim, flagged as a replay.

        Every content field and every stable id -- chat, user message, assistant
        message -- is the original. The only difference is the additive
        ``fast_demo_replay`` marker, which is the repository's existing
        convention for "this answer was not recomputed".
        """

        data = dict(payload)
        metadata = dict(data.get("metadata") or {})
        metadata["fast_demo_replay"] = True
        data["metadata"] = metadata
        return AnalyzeResponse.model_validate(data)

    @staticmethod
    def _request_fingerprint(request: AnalyzeRequest, chat_id: str | None) -> str:
        return fingerprint_request(
            {
                "chat_id": chat_id,
                "contract_version": CONTRACT_VERSION,
                "language": request.language,
                "question": request.question,
                "session_id": request.session_id,
                "user_type": request.user_type,
            }
        )

    def _fingerprint_compatible(self, request: AnalyzeRequest, receipt) -> bool:
        """Is this request the same logical turn as the stored receipt?

        The fingerprint covers the requested chat identity, but a retry is
        allowed to name the chat the first attempt created: the client learns
        ``chat_id`` from the response it is retrying, so an existing-chat replay
        legitimately arrives with a ``chat_id`` the original request did not
        carry. Both spellings are accepted, but only while they refer to the
        chat this receipt is already bound to -- pointing the same key at a
        *different* chat stays a conflict.
        """

        requested = request.chat_id
        candidates: set[str | None] = {requested}
        if requested is None or requested == receipt.chat_id:
            candidates.add(None)
            if receipt.chat_id is not None:
                candidates.add(receipt.chat_id)
        return any(
            self._request_fingerprint(request, candidate) == receipt.request_fingerprint
            for candidate in candidates
        )

    def _bind_receipt_chat(self, session_id: str, client_request_id: str, chat_id: str) -> None:
        """Bind the reservation to its chat, or refuse the turn.

        This runs before any chat, message, provider or fact side effect. If it
        cannot be recorded, a lost response could never be resolved back to this
        chat -- so continuing would hand the caller an unenforceable key.
        Swallowing the failure here previously let the whole turn execute.
        """

        if self.request_receipts is None:
            raise IdempotencyUnavailableError()
        try:
            self.request_receipts.bind_chat(
                session_id=session_id, client_request_id=client_request_id, chat_id=chat_id
            )
        except RequestReceiptStoreError as exc:
            raise IdempotencyUnavailableError() from exc

    def _turn_left_no_trace(self, binding: "_TurnBinding") -> bool:
        """May this turn's reservation be dropped?

        Release requires *positive proof* that nothing was persisted. The
        authority is the classified outcome the store reported; "the call
        raised" is never proof, because a failing ``commit()`` may still have
        applied the transaction.

        The row read-back is only allowed to *strengthen* the refusal. An
        unavailable read-back leaves the decision exactly where the outcome put
        it -- it can never turn uncertainty into a release, which is what let a
        retry duplicate a chat and a user message.
        """

        if binding.chat_start_outcome not in _RELEASE_PERMITTED_OUTCOMES:
            return False
        state = binding.state
        if state is not None and state.persistence.user_message_stored:
            return False
        try:
            for chat_id in {binding.reserved_chat_id, binding.chat_id}:
                if chat_id and self.chat_store.chat_exists(chat_id):
                    return False
            if self.chat_store.message_exists(binding.user_message_id):
                return False
        except Exception:  # noqa: BLE001 - may refuse, never authorise
            pass
        return True

    def _release_receipt(self, session_id: str, client_request_id: str) -> None:
        if self.request_receipts is None:
            return
        try:
            self.request_receipts.release(
                session_id=session_id, client_request_id=client_request_id
            )
        except RequestReceiptStoreError:
            pass

    async def _analyze_turn(
        self, request: AnalyzeRequest, binding: "_TurnBinding"
    ) -> AnalyzeResponse:
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
        # Reserved by the caller so the persisted rows carry exactly the ids the
        # request receipt already recorded; a replay therefore returns the same
        # user_message_id / assistant_message_id it returned the first time.
        binding.state = state
        state.persistence.user_message_id = binding.user_message_id
        state.persistence.assistant_message_id = binding.assistant_message_id

        with self._phase(state, "validate_request"):
            state.request.question = state.request.question.strip()
            # Whitespace-only stays invalid; every other non-empty message is a
            # real turn and must reach routing. A short message the assistant
            # cannot act on is answered, not rejected as malformed data.
            if not state.request.question:
                raise InvalidRequestError("Bạn nhập nội dung tin nhắn giúp tôi nhé.")

        first_user_message = ChatMessage(
            message_id=state.persistence.user_message_id,
            chat_id="",  # replaced once the chat identity is known
            role="user",
            content_type="text",
            content_text=state.request.question,
            content_json=None,
            created_at=utc_now(),
        )

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
                # Reserve the identity here rather than letting the store mint
                # it, so the receipt can be bound *before* the row exists.
                state.chat.chat_id = binding.reserved_chat_id
                state.chat.is_new_chat = True
            # Bind the receipt to the resolved chat before any write and before
            # any provider work, so a retry that still cannot supply a chat_id
            # resolves to this chat rather than creating another one.
            if binding.on_chat_bound is not None:
                binding.on_chat_bound(state.chat.chat_id)
            binding.chat_id = state.chat.chat_id

        with self._phase(state, "store_user_message"):
            first_user_message = first_user_message.model_copy(
                update={"chat_id": state.chat.chat_id}
            )
            try:
                if state.chat.is_new_chat:
                    # One transaction: a failure can no longer leave a chat with
                    # no messages for a retry to trip over.
                    self.chat_store.create_chat_with_first_user_message(
                        chat_id=state.chat.chat_id,
                        session_id=state.request.session_id,
                        title=self.title_service.make(state.request.question),
                        message=first_user_message,
                    )
                else:
                    self.chat_store.add_message(first_user_message)
            except ChatStartNotCommittedError:
                binding.chat_start_outcome = CHAT_START_PROVEN_NOT_COMMITTED
                raise
            except Exception:
                # Includes ChatStartOutcomeUnknownError and any unclassified
                # failure of the existing-chat insert. Unknown is the safe
                # default: never release a reservation we cannot account for.
                binding.chat_start_outcome = CHAT_START_OUTCOME_UNKNOWN
                raise
            binding.chat_start_outcome = CHAT_START_COMMITTED
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

            # Public Beta V0 (legal-fallback vertical): only ever consulted
            # when FAST DEMO V2 itself just declined the turn as out of its
            # scope -- never for a deposit-shaped answer, and structurally
            # never for the unsafe route, which sets metadata["unsafe"]=True
            # under the same "scope" response_kind. See
            # `services/legal_fallback_orchestrator.py`'s module docstring.
            #
            # `fast_demo_routing.is_unsafe()` uses its own deliberately
            # narrow keyword set, distinct from the baseline
            # `unsafe_patterns.json`-driven detector run above (task §9:
            # "the official-source fallback must not execute for unsafe
            # requests before safety handling") -- a phrase the baseline
            # detector already flagged (`unsafe_intent_detected`) must gate
            # this hook too, even on a turn FAST DEMO V2's own narrower
            # check did not itself label unsafe. Never rescue what the
            # baseline safety layer already refused.
            if (
                fast_response is not None
                and self.legal_fallback_orchestrator is not None
                and fast_response.metadata.get("fast_demo_route") == "scope"
                and not fast_response.metadata.get("unsafe")
                and not state.classification.unsafe_intent_detected
            ):
                fallback_response = None
                try:
                    with self._phase(state, "legal_fallback"):
                        fallback_response = await self.legal_fallback_orchestrator.handle(state)
                except Exception:  # noqa: BLE001 - contain; never leak a raw error
                    state.trace.warnings.append("legal_fallback_deferred")
                    fallback_response = None
                if fallback_response is not None:
                    fast_response = fallback_response

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
                                "trust_level", "trust_label", "trust_explanation", "source_checked_at",
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
