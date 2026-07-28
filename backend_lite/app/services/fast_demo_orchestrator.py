"""FAST DEMO V2 orchestrator: the whole video path in one bounded flow.

Frozen processing order (see the 48-hour contract, section 12):

  1. ensure the state row exists (short transaction, no provider call inside);
  2. load state, version, recent requests, bounded same-chat history;
  3. duplicate check on client_request_id -> return stored response, 0 calls;
  4. retain loaded_state_version;
  5. deterministic route (social / capability / unsafe / scope / legal);
  6. legal only: select source pack, ONE provider call, validate, build candidate;
  7. short compare-and-swap transaction;
  8. success -> return committed response;
  9. CAS failure -> discard model output, never call again, controlled message.

Two properties are enforced structurally rather than by convention:
  * no SQLite transaction is ever open while the provider call runs -- the store
    exposes only short load/commit calls and the call happens between them;
  * ``_provider_calls`` is asserted <= 1 per ``handle`` execution.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..constants import CONTRACT_VERSION, SAFETY_NOTICE
from ..contracts.fast_demo import (
    MAX_PENDING_QUESTION_TEXT,
    PENDING_QUESTION_GENERAL,
    DraftRecord,
    FastDemoPlan,
    FastDemoState,
    PendingClarification,
    RecentRequestRecord,
)
from ..schemas.api import AnalyzeResponse
from ..schemas.content import Confidence, DraftBlock, SourceObject
from ..stores.fast_demo_state_store import (
    FastDemoStateStore,
    FastDemoStoreError,
    LoadedFastDemoState,
)
from .conversation_context import (
    CONTEXT_WINDOW_POLICY,
    NO_MATTER,
    RecentMatter,
    detect_recent_matter,
    has_pending_clarification,
)
from .demo_llm_client import LLMClientError, LLMClientProtocol
from .fast_demo_fact_validation import apply_fact_updates, is_reserved_sentinel
from .fast_demo_prompt import SYSTEM_PROMPT, build_user_prompt
from .fast_demo_routing import (
    ACKNOWLEDGMENT_TEXT,
    ACKNOWLEDGMENT_TEXT_WITH_MATTER,
    CAPABILITY_TEXT,
    GREETING_TEXT,
    SCOPE_TEXT,
    UNSAFE_TEXT,
    FastDemoRoute,
    LegalIntent,
    classify_legal_intent,
    classify_route,
    is_answer_token,
    normalize_for_cue,
)
from .fast_demo_source_pack import FastDemoSourcePack

_logger = logging.getLogger("vietlaw.fast_demo")

DISCLAIMER_NOTICE = SAFETY_NOTICE

_FALLBACK_SUMMARY = (
    "Hiện tôi chưa thể tạo phân tích chi tiết cho lượt này. Tôi vẫn giữ lại các thông tin "
    "bạn đã cung cấp để bạn không phải nhập lại."
)
_FALLBACK_STEPS = [
    "Giữ lại toàn bộ chứng từ chuyển khoản và tin nhắn trao đổi với chủ nhà.",
    "Gửi yêu cầu hoàn trả tiền cọc bằng văn bản (tin nhắn hoặc email) để có bằng chứng.",
]
_CONCURRENCY_SUMMARY = (
    "Cuộc trò chuyện vừa được cập nhật ở nơi khác nên tôi chưa áp dụng phản hồi này. "
    "Bạn gửi lại tin nhắn giúp tôi nhé."
)


class FastDemoConfig:
    """Pinned provider configuration for the video candidate."""

    def __init__(
        self,
        *,
        enabled: bool,
        model: str | None,
        api_key: str | None,
        timeout_s: float,
        max_output_tokens: int,
        temperature: float,
        use_structured_output: bool = True,
    ) -> None:
        self.enabled = enabled
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        # Native structured outputs are not supported on every Claude model. When
        # the pinned model lacks them, the request must omit output_config and rely
        # on the prompt's JSON-only instruction plus local Pydantic validation --
        # validation strength is unchanged, only where conformance is enforced.
        self.use_structured_output = use_structured_output

    @property
    def provider_ready(self) -> bool:
        return bool(self.enabled and self.model and self.api_key)


class FastDemoOrchestrator:
    def __init__(
        self,
        *,
        store: FastDemoStateStore,
        source_pack: FastDemoSourcePack,
        llm_client: LLMClientProtocol,
        config: FastDemoConfig,
    ) -> None:
        self._store = store
        self._pack = source_pack
        self._client = llm_client
        self._config = config
        self._last_failure: str | None = None

    # -- entry point ---------------------------------------------------------

    async def handle(self, state) -> AnalyzeResponse | None:
        """Own the turn, or return None to defer to the baseline pipeline."""

        provider_calls = 0
        self._last_failure = None
        chat_id = state.chat.chat_id
        message = state.request.question
        client_request_id = getattr(state.request, "client_request_id", None) or ""

        try:
            loaded = self._store.load(chat_id)
        except FastDemoStoreError:
            # Schema/load failure must never surface as a 500 or a raw SQLite
            # error; degrade to a safe deterministic response.
            return self._fallback_response(state, FastDemoState(), reason="store_unavailable")

        # Step 3: duplicate replay. Zero provider calls, zero mutation.
        replay = loaded.find_recent(client_request_id)
        if replay is not None:
            return self._replay_response(state, replay)

        loaded_state_version = loaded.state_version
        # An unresolved matter counts as active when the *state* holds a fact OR
        # when a recent user turn in this same chat described one. Without the
        # second signal a chat whose facts were never extracted (provider
        # unavailable, or no verifiable span) answered a legitimate follow-up
        # with a scope refusal, asking the user to restate what they had just
        # explained. The window is bounded and same-chat only.
        history = getattr(state.chat, "history_messages", []) or []
        recent = detect_recent_matter(history, current_message=message)
        has_active_matter = _has_active_matter(loaded.state) or recent.active
        # Durable structured state, not a history heuristic: a greeting or a
        # thank-you no longer counts as having answered the question.
        pending = loaded.state.pending_clarification
        pending_clarification = pending is not None
        route = classify_route(
            message,
            has_active_matter=has_active_matter,
            pending_clarification=pending_clarification,
        )

        if route is FastDemoRoute.SOCIAL:
            # A greeting mid-conversation is answered, but it neither clears the
            # active topic nor touches state: no commit runs on this path.
            return self._direct_response(state, "social", GREETING_TEXT, recent=recent)
        if route is FastDemoRoute.CAPABILITY:
            return self._direct_response(state, "capability", CAPABILITY_TEXT, recent=recent)
        if route is FastDemoRoute.ACKNOWLEDGMENT:
            text = ACKNOWLEDGMENT_TEXT_WITH_MATTER if has_active_matter else ACKNOWLEDGMENT_TEXT
            return self._direct_response(state, "social", text, recent=recent)
        if route is FastDemoRoute.UNSAFE:
            return self._direct_response(state, "scope", UNSAFE_TEXT, unsafe=True, recent=recent)
        if route is FastDemoRoute.SCOPE_OR_UNSUPPORTED:
            return self._direct_response(state, "scope", SCOPE_TEXT, recent=recent)

        # ---- legal_conversation: at most one provider call -------------------
        pack = self._pack.select(loaded.state, normalize_for_cue(message))
        plan: FastDemoPlan | None = None
        if self._config.provider_ready:
            provider_calls = 1
            plan = await self._request_plan(
                message=message,
                history=state.chat.history_messages,
                loaded=loaded,
                pack=pack,
            )
        assert provider_calls <= 1, "fast demo must never exceed one provider call"

        if plan is None:
            candidate_state = loaded.state.model_copy(deep=True)
            response = self._fallback_response(
                state,
                candidate_state,
                reason=self._last_failure or "provider_not_configured",
                intent=classify_legal_intent(message),
                recent=recent,
            )
        else:
            candidate_state, response = self._build_success(
                state, loaded, plan, pack, message, recent
            )
            # Pending transitions ride the same candidate state, so they commit
            # under the same CAS as the fact updates -- never as a second write.
            # If that CAS loses, neither the facts nor this transition is
            # authoritative, and the question stays open.
            candidate_state.pending_clarification = _next_pending_clarification(
                current=pending,
                plan_questions=response.clarifying_questions,
                answered=_pending_answer_accepted(
                    pending, list(response.metadata.get("applied_slots") or [])
                ),
                assistant_message_id=state.persistence.assistant_message_id,
                state_version=loaded.state_version + 1,
            )

        # Step 7: short CAS transaction. The provider call is already finished.
        committed = self._commit(
            loaded=loaded,
            expected_version=loaded_state_version,
            candidate_state=candidate_state,
            client_request_id=client_request_id,
            response=response,
        )
        if committed is None:
            # Step 9: stale output is discarded, never merged, never retried.
            return self._concurrency_response(state)
        return response

    # -- provider ------------------------------------------------------------

    async def _request_plan(
        self,
        *,
        message: str,
        history: list,
        loaded: LoadedFastDemoState,
        pack: list,
    ) -> FastDemoPlan | None:
        """Exactly one call. Any failure returns None -> deterministic fallback.

        There is no repair call and no second attempt of any kind.
        """

        from ..contracts.fast_demo import FAST_DEMO_PLAN_JSON_SCHEMA

        user_prompt = build_user_prompt(
            current_message=message,
            history=history,
            state=loaded.state,
            pack=pack,
        )
        try:
            raw = await self._client.complete(
                system=SYSTEM_PROMPT,
                user=user_prompt,
                max_tokens=self._config.max_output_tokens,
                timeout_s=self._config.timeout_s,
                json_schema=FAST_DEMO_PLAN_JSON_SCHEMA,
                temperature=self._config.temperature,
                use_structured_output=self._config.use_structured_output,
            )
        except LLMClientError as exc:
            # exc.detail is bounded and constructed by our own client (e.g.
            # "status 400"); it never carries credentials or user content.
            self._note_failure(f"provider_error:{exc.kind.value}", exc.detail)
            return None
        except Exception as exc:  # noqa: BLE001 - contained; CancelledError is BaseException
            self._note_failure(f"client_exception:{type(exc).__name__}", "")
            return None

        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            self._note_failure("provider_invalid_json", "")
            return None
        if not isinstance(payload, dict):
            self._note_failure("provider_invalid_json", "top-level not an object")
            return None
        try:
            return FastDemoPlan.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 - schema failure -> deterministic fallback
            # Only the failing field names are recorded — never field values,
            # which would echo user content back into the log.
            fields = ""
            errors = getattr(exc, "errors", None)
            if callable(errors):
                try:
                    fields = ",".join(
                        ".".join(str(p) for p in e.get("loc", ())) for e in errors()[:5]
                    )
                except Exception:  # noqa: BLE001
                    fields = ""
            self._note_failure("local_schema_validation_failure", fields[:120])
            return None

    def _note_failure(self, category: str, detail: str) -> None:
        """Record one bounded, credential-free reason for this turn's fallback.

        Logged server-side and surfaced in response metadata as a category only.
        Never contains the API key, headers, prompts, or user conversation text.
        """

        self._last_failure = category
        _logger.warning(
            "fast_demo provider turn failed: category=%s detail=%s", category, detail[:120]
        )

    # -- response construction ----------------------------------------------

    def _build_success(
        self,
        state,
        loaded: LoadedFastDemoState,
        plan: FastDemoPlan,
        pack: list,
        message: str,
        recent: RecentMatter = NO_MATTER,
    ) -> tuple[FastDemoState, AnalyzeResponse]:
        outcome = apply_fact_updates(loaded.state, plan.fact_updates, message)
        candidate = outcome.state
        candidate.last_response_mode = plan.response_mode

        draft_block: DraftBlock | None = None
        if plan.draft is not None and plan.draft.body.strip():
            draft_block = DraftBlock(
                title=plan.draft.title.strip() or "Tin nhắn gửi chủ nhà",
                body=plan.draft.body.strip(),
            )
            candidate.last_draft = DraftRecord(title=draft_block.title, body=draft_block.body)

        sources = self._pack.resolve_selected(pack, plan.selected_source_ids)

        response = AnalyzeResponse(
            response_kind="legal",
            contract_version=CONTRACT_VERSION,
            request_id=state.request.request_id,
            chat_id=state.chat.chat_id,
            user_message_id=state.persistence.user_message_id,
            assistant_message_id=state.persistence.assistant_message_id,
            domain="civil_dispute",
            risk_level="medium",
            decision=_decision_for(plan.response_mode),
            summary=plan.summary.strip(),
            clarifying_questions=_clean(plan.clarifying_questions),
            checklist=_clean(plan.checklist),
            next_steps=_clean(plan.next_steps),
            sources=sources,
            safety_notice=SAFETY_NOTICE,
            confidence=Confidence(domain=0.9, risk=0.75, answer=0.78),
            analysis=(plan.analysis or "").strip() or None,
            draft=draft_block,
            known_facts=_known_facts(candidate),
            uncertainty_notice=(plan.uncertainty_notice or "").strip() or None,
            metadata=_metadata(
                route="legal_conversation",
                mode=plan.response_mode,
                extra={"applied_slots": sorted({u.slot for u in outcome.applied})},
                recent=recent,
            ),
        )
        return candidate, response

    def _direct_response(
        self,
        state,
        kind: str,
        text: str,
        *,
        unsafe: bool = False,
        recent: RecentMatter = NO_MATTER,
    ) -> AnalyzeResponse:
        """social / capability / scope: zero provider calls and, structurally,
        no domain, risk, decision, confidence or sources."""

        return AnalyzeResponse(
            response_kind=kind,  # type: ignore[arg-type]
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
            metadata=_metadata(route=kind, mode=None, extra={"unsafe": unsafe}, recent=recent),
        )

    def _fallback_response(
        self,
        state,
        current: FastDemoState,
        *,
        reason: str,
        intent: LegalIntent = LegalIntent.GENERAL,
        recent: RecentMatter = NO_MATTER,
    ) -> AnalyzeResponse:
        """Contextual deterministic response for the user's actual turn.

        Bounded classes (intake / next-steps / evidence / draft / general) rather
        than one generic message. Every sentence is backend-authored and uses only
        facts already accepted into state -- nothing is invented, no legal
        conclusion is asserted, and no implementation vocabulary is exposed.
        """

        known = _known_facts(current)
        summary, questions, steps = _fallback_content(intent, current, known, recent)
        return AnalyzeResponse(
            response_kind="legal",
            contract_version=CONTRACT_VERSION,
            request_id=state.request.request_id,
            chat_id=state.chat.chat_id,
            user_message_id=state.persistence.user_message_id,
            assistant_message_id=state.persistence.assistant_message_id,
            domain="civil_dispute",
            risk_level="medium",
            decision="ask_clarifying_questions" if questions else "answer_with_guidance",
            summary=summary,
            clarifying_questions=questions,
            checklist=[],
            next_steps=steps,
            sources=[],
            safety_notice=SAFETY_NOTICE,
            confidence=Confidence(domain=0.6, risk=0.6, answer=0.4),
            analysis=None,
            draft=None,
            known_facts=known,
            uncertainty_notice=None,
            metadata=_metadata(
                route="legal_conversation",
                mode="fallback",
                extra={"reason": reason},
                recent=recent,
            ),
        )

    def _concurrency_response(self, state) -> AnalyzeResponse:
        return AnalyzeResponse(
            response_kind="scope",
            contract_version=CONTRACT_VERSION,
            request_id=state.request.request_id,
            chat_id=state.chat.chat_id,
            user_message_id=state.persistence.user_message_id,
            assistant_message_id=state.persistence.assistant_message_id,
            domain=None,
            risk_level=None,
            decision=None,
            summary=_CONCURRENCY_SUMMARY,
            clarifying_questions=[],
            checklist=[],
            next_steps=[],
            sources=[],
            safety_notice="",
            confidence=None,
            metadata=_metadata(route="scope", mode="concurrency_retry", extra={}),
        )

    def _replay_response(self, state, record: RecentRequestRecord) -> AnalyzeResponse:
        """Return the stored response verbatim, re-pointed at this HTTP turn's
        message IDs so the transcript stays consistent."""

        payload: dict[str, Any] = dict(record.response_json)
        payload["request_id"] = state.request.request_id
        payload["chat_id"] = state.chat.chat_id
        payload["user_message_id"] = state.persistence.user_message_id
        payload["assistant_message_id"] = state.persistence.assistant_message_id
        metadata = dict(payload.get("metadata") or {})
        metadata["fast_demo_replay"] = True
        payload["metadata"] = metadata
        try:
            return AnalyzeResponse.model_validate(payload)
        except Exception:  # noqa: BLE001 - unreadable stored row -> safe fallback
            return self._fallback_response(state, FastDemoState(), reason="replay_unreadable")

    # -- persistence ---------------------------------------------------------

    def _commit(
        self,
        *,
        loaded: LoadedFastDemoState,
        expected_version: int,
        candidate_state: FastDemoState,
        client_request_id: str,
        response: AnalyzeResponse,
    ) -> bool | None:
        """Compare-and-swap. None means a concurrent turn won."""

        record = RecentRequestRecord(
            client_request_id=client_request_id or response.request_id,
            response_json=response.model_dump(mode="json"),
            applied_state_version=expected_version + 1,
        )
        recent = [*loaded.recent_requests, record]
        try:
            ok = self._store.commit_state(
                chat_id=loaded.chat_id,
                expected_version=expected_version,
                state=candidate_state,
                recent_requests=recent,
            )
        except FastDemoStoreError:
            # A failed write must not fabricate a "committed" answer, but the
            # user still gets their response for this turn.
            return True
        return True if ok else None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Contextual fallback copy. Backend-authored, uses only accepted facts, asserts
# no legal conclusion, and never names an internal mechanism.
# ---------------------------------------------------------------------------

_INTAKE_QUESTIONS = [
    "Hiện chủ nhà đã phản hồi thế nào về khoản cọc này?",
    "Bạn muốn tôi hỗ trợ phân tích tình huống, chuẩn bị chứng cứ, đề xuất bước tiếp theo, "
    "hay soạn tin nhắn gửi chủ nhà?",
]
_NO_HANDOVER_QUESTIONS = [
    "Hai bên có giấy đặt cọc hoặc thỏa thuận bằng văn bản không?",
    "Hai bên đã thống nhất ngày nhận nhà hoặc bàn giao chưa?",
]
_NO_HANDOVER_STEPS = [
    "Giữ lại sao kê chuyển khoản, tin nhắn trao đổi và mọi thỏa thuận bằng văn bản.",
    "Nhắn cho chủ nhà bằng văn bản, đề nghị bàn giao như đã thỏa thuận hoặc nêu rõ lý do chưa "
    "bàn giao, và trao đổi về việc hoàn lại tiền cọc.",
    "Xem lại thỏa thuận để đối chiếu điều khoản bàn giao, hoàn cọc và trách nhiệm của mỗi bên.",
    "Nếu trao đổi không có kết quả, bạn có thể cân nhắc hòa giải hoặc hỏi ý kiến luật sư cho "
    "trường hợp cụ thể của mình.",
]
_EVIDENCE_STEPS = [
    "Sao kê hoặc biên nhận cho khoản tiền đã đặt cọc.",
    "Tin nhắn, email trao đổi với chủ nhà.",
    "Giấy đặt cọc hoặc hợp đồng thuê nếu có.",
    "Mốc thời gian sự việc và thông tin về việc nhận nhà.",
]
_GENERAL_STEPS = [
    "Giữ lại chứng từ chuyển khoản và các trao đổi với chủ nhà.",
    "Trao đổi với chủ nhà bằng văn bản để có căn cứ về sau.",
]


def _fallback_content(
    intent: LegalIntent,
    current: FastDemoState,
    known: list[str],
    recent: RecentMatter = NO_MATTER,
) -> tuple[str, list[str], list[str]]:
    """Return (summary, clarifying_questions, next_steps) for one fallback class."""

    acknowledged = _acknowledgement_sentence(current)

    if intent is LegalIntent.FACT_INTAKE:
        # Facts only: acknowledge and ask what help is wanted. Deliberately does
        # NOT assume a refund dispute or tell the user to demand repayment.
        summary = acknowledged or (
            "Tôi đã ghi nhận thông tin bạn cung cấp về khoản tiền cọc."
        )
        if current.facts.payment_evidence_status == "present":
            summary += " Sao kê chuyển khoản là chứng từ quan trọng để chứng minh việc bạn đã chuyển tiền."
        return summary, list(_INTAKE_QUESTIONS), []

    if intent is LegalIntent.NEXT_STEPS:
        # The handover sentence is an assertion about the user's situation, so it
        # may only be said when something actually established it: an accepted
        # fact, or the user's own recent description. Otherwise the answer still
        # continues from the conversation, but claims nothing.
        handover_known = (
            current.facts.property_handover_status == "absent" or recent.handover_refused
        )
        if handover_known:
            lead = (
                "Việc chủ nhà chưa bàn giao nhà như thỏa thuận là điều cần làm rõ sớm. "
                "Dưới đây là những bước bạn có thể làm ngay."
            )
        elif recent.active:
            lead = (
                "Dựa trên tình huống bạn đã mô tả ở trên, đây là những bước bạn có thể làm ngay."
            )
        else:
            lead = "Đây là những bước bạn có thể làm ngay."
        summary = (acknowledged + " " if acknowledged else "") + lead
        return summary, list(_NO_HANDOVER_QUESTIONS), list(_NO_HANDOVER_STEPS)

    if intent is LegalIntent.EVIDENCE:
        summary = (
            (acknowledged + " " if acknowledged else "")
            + "Đây là những giấy tờ bạn nên chuẩn bị cho tình huống này."
        )
        return summary, [], list(_EVIDENCE_STEPS)

    if intent is LegalIntent.DRAFT:
        summary = (
            "Hiện tôi chưa soạn xong tin nhắn cho bạn. "
            + (acknowledged + " " if acknowledged else "")
            + "Bạn nhắn lại giúp tôi để tôi soạn lại nhé."
        )
        return summary, [], []

    summary = (
        (acknowledged + " " if acknowledged else "")
        + "Bạn mô tả thêm tình huống hiện tại để tôi hỗ trợ cụ thể hơn nhé."
    )
    return summary, [], list(_GENERAL_STEPS)


def _acknowledgement_sentence(current: FastDemoState) -> str:
    """One sentence naming only facts already accepted into state."""

    parts: list[str] = []
    facts = current.facts
    if facts.deposit_amount is not None:
        parts.append(f"bạn đã đặt cọc {_format_vnd(facts.deposit_amount.value)}")
    if facts.payment_evidence_status == "present":
        parts.append("có chứng từ chuyển khoản")
    if facts.written_deposit_agreement_status == "absent":
        parts.append("chưa có giấy đặt cọc")
    if facts.deposit_returned_status == "absent":
        parts.append("chủ nhà chưa hoàn trả tiền cọc")
    if not parts:
        return ""
    return "Tôi đã ghi nhận " + ", ".join(parts) + "."


# --- pending-clarification lifecycle ---------------------------------------
#
# Deterministic rules, evaluated in order:
#
#   R1 replace  a legal turn that asks a new clarifying question replaces any
#               existing pending record;
#   R2 resolve  the pending question's expected fact slot was actually applied
#               to state -- not merely proposed, and not merely answered-looking;
#   R3 keep     anything else leaves it exactly as it was -- including a failed
#               legal turn and a rejected fact update, neither of which may look
#               like an answer.
#
# NEW MATTER: not supported in this single-issue demo. A distinct matter clears
# the pending question only if the model happens to ask a replacement one (R1);
# otherwise the old question is preserved. There is no deterministic new-matter
# signal here, and guessing one would be worse than keeping the question.
#
# Social, capability and acknowledgment routes never reach here: they return
# before `_commit`, so they cannot touch pending at all.

# Question-text cues -> allowlisted slot. Matching is on the backend's own
# generated question, and only ever selects an *identity*; it never reads a
# fact value out of prose.
_PENDING_QUESTION_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("property_handover_status", ("ban giao", "nhan nha", "vao o")),
    ("deposit_returned_status", ("hoan tra", "hoan coc", "tra lai tien coc", "tra coc")),
    ("written_deposit_agreement_status", ("giay dat coc", "van ban", "thoa thuan bang van ban")),
    ("payment_evidence_status", ("sao ke", "chung tu", "bien nhan", "chuyen khoan")),
    ("rental_contract_status", ("hop dong thue",)),
    ("written_refund_request_status", ("yeu cau hoan", "gui yeu cau")),
    ("landlord_response_status", ("phan hoi", "chu nha da noi")),
    ("deposit_amount", ("bao nhieu", "so tien")),
)


def _question_identity(question_text: str) -> str:
    normalized = normalize_for_cue(question_text)
    for question_id, cues in _PENDING_QUESTION_CUES:
        if any(cue in normalized for cue in cues):
            return question_id
    return PENDING_QUESTION_GENERAL


def _pending_answer_accepted(
    pending: PendingClarification | None, applied_slots: list[str]
) -> bool:
    """Was the outstanding question genuinely answered *and accepted*?

    Being a bare answer token is not enough, and neither is the provider
    returning parseable output or visible prose. The question closes only when
    the fact slot it asks about was actually applied to state -- so a proposal
    rejected for an unverifiable evidence quote, an invalid value, a disallowed
    operation, the wrong slot or a stale CAS leaves the question outstanding.

    A ``general`` question has no such slot and is therefore never auto-closed.
    """

    if pending is None:
        return False
    expected = pending.expected_slot
    if expected is None:
        return False
    return expected in set(applied_slots)


def _next_pending_clarification(
    *,
    current: PendingClarification | None,
    plan_questions: list[str],
    answered: bool,
    assistant_message_id: str,
    state_version: int,
) -> PendingClarification | None:
    # R1: a newly asked question always wins, and replaces an older one.
    for question in plan_questions:
        text = (question or "").strip()
        if not text:
            continue
        return PendingClarification(
            question_id=_question_identity(text),
            question_text=text[:MAX_PENDING_QUESTION_TEXT],
            created_by_assistant_message_id=assistant_message_id,
            created_at_state_version=state_version,
        )
    # R2: an accepted short answer closes the question it answered.
    if answered:
        return None
    # R3: unchanged.
    return current


def _has_active_matter(state: FastDemoState) -> bool:
    facts = state.facts
    return bool(
        facts.deposit_amount is not None
        or facts.written_deposit_agreement_status != "unknown"
        or facts.payment_evidence_status != "unknown"
        or facts.deposit_returned_status != "unknown"
        or state.user_goal
    )


def _decision_for(mode: str) -> str:
    if mode == "clarify":
        return "ask_clarifying_questions"
    return "answer_with_guidance"


def _clean(items: list[str]) -> list[str]:
    return [item.strip() for item in items if isinstance(item, str) and item.strip()][:6]


def _format_vnd(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " đồng"


_TRI_LABELS = {
    "written_deposit_agreement_status": ("Có giấy đặt cọc", "Không có giấy đặt cọc"),
    "payment_evidence_status": ("Có chứng từ thanh toán", "Không có chứng từ thanh toán"),
    "rental_contract_status": ("Có hợp đồng thuê nhà", "Không có hợp đồng thuê nhà"),
    "property_handover_status": ("Đã được bàn giao nhà", "Chưa được bàn giao nhà"),
    "deposit_returned_status": ("Đã được hoàn cọc", "Chưa được hoàn cọc"),
    "written_refund_request_status": ("Đã gửi yêu cầu hoàn cọc bằng văn bản", "Chưa gửi yêu cầu bằng văn bản"),
    "landlord_response_status": ("Chủ nhà đã phản hồi", "Chủ nhà chưa phản hồi"),
}


def _known_facts(state: FastDemoState) -> list[str]:
    """Backend-owned rendering of accepted facts only. ``unknown`` never shows."""

    lines: list[str] = []
    facts = state.facts
    if facts.deposit_amount is not None:
        lines.append(f"Số tiền đặt cọc: {_format_vnd(facts.deposit_amount.value)}")
    for slot, (present_label, absent_label) in _TRI_LABELS.items():
        value = getattr(facts, slot, "unknown")
        if value == "present":
            lines.append(present_label)
        elif value == "absent":
            lines.append(absent_label)
    if facts.payment_evidence_types:
        readable = {
            "bank_transfer": "sao kê chuyển khoản",
            "receipt": "biên nhận",
            "message": "tin nhắn",
            "witness": "người làm chứng",
            "other": "khác",
        }
        names = [readable.get(item, item) for item in facts.payment_evidence_types]
        lines.append("Chứng cứ thanh toán: " + ", ".join(names))
    # Defense in depth only -- acceptance already refuses sentinels, but a row
    # persisted before that guard existed must still never reach the user.
    if facts.landlord_refusal_reason and not is_reserved_sentinel(facts.landlord_refusal_reason):
        lines.append(f"Lý do chủ nhà đưa ra: {facts.landlord_refusal_reason}")
    return lines


def _metadata(
    *, route: str, mode: str | None, extra: dict, recent: RecentMatter = NO_MATTER
) -> dict:
    data = {
        "fast_demo": True,
        "fast_demo_route": route,
        "fast_demo_mode": mode,
        # Truthful now that routing consults the bounded window: this was hard-
        # coded False while history was genuinely unused.
        "used_current_chat_history": bool(recent.considered_messages),
        "recent_matter_active": recent.active,
        "recent_matter_topic": recent.topic,
        "context_window_policy": CONTEXT_WINDOW_POLICY,
    }
    data.update(extra)
    return data


__all__ = ["FastDemoConfig", "FastDemoOrchestrator"]
