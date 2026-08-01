"""VietLaw Public Beta V0: the legal-fallback orchestrator.

Sibling to `fast_demo_orchestrator.FastDemoOrchestrator`, not a branch
inside it (see the architecture report §2/§5). `handle(...)` is only ever
called by `agent_runtime.py` when FAST DEMO V2 already classified the turn
`scope_or_unsupported` (deposit-shaped, social, capability, identity,
memory, acknowledgment, and unsafe messages never reach here) -- see that
module's own docstring for the exact structural signal used.

Decision order (task §3):

    IS_LEGAL_OR_RIGHTS_RELATED?
        no  -> return None (defer to the original scope_or_unsupported reply)
        yes -> CURATED_TRAFFIC_MATCH?
                 yes -> CURATED_VERIFIED (or ask one clarification)
                 no  -> OFFICIAL_SOURCE_SEARCH_AVAILABLE (flag on) and evidence
                        SUFFICIENT?
                          yes -> OFFICIAL_SOURCE_SEARCH
                          no  -> GENERAL_GUIDANCE

No LLM call is made anywhere in this module. OFFICIAL_SOURCE_SEARCH answers
are built entirely from the retrieved candidate's own TYPED fields (never
from free-form generation over its `relevant_excerpt` text) -- the strongest
available guarantee against an unsupported citation, and it also means
prompt-injection text embedded in a fetched page can never reach a system
prompt (there is no prompt): see `services/official_legal_search.py` and
the final report's "Prompt injection review" section.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from ..constants import CONTRACT_VERSION, SAFETY_NOTICE
from ..contracts.legal_fallback_state import LegalFallbackState, RetrievedEvidenceRecord
from ..contracts.legal_trust import EVIDENCE_OUTCOME_TRUST_LEVEL, EvidenceOutcome, TrustLevel, trust_explanation, trust_label
from ..contracts.official_search import LegalSearchQuery
from ..contracts.traffic import ClarificationAnswer, ClarificationAnswerKind, RuleSelectionOutcome, TrafficFacts
from ..schemas.api import AnalyzeResponse
from ..schemas.content import Confidence, SourceObject
from ..stores.legal_fallback_state_store import LegalFallbackStateStore, LegalFallbackStoreError
from .general_legal_guidance import build_general_guidance
from .legal_fallback_safety_guard import is_unsafe_for_legal_fallback
from .legal_intent_classifier import is_legal_or_rights_related
from .official_legal_search import OfficialLegalSearchService
from .official_source_validator import evaluate_evidence_sufficiency, select_primary_candidate
from .traffic_classifier import TrafficDetection
from .traffic_classifier import classify as classify_traffic
from .traffic_classifier import parse_clarification_answer
from .traffic_source_pack import TrafficRuleRecord, TrafficSourcePack

_logger = logging.getLogger(__name__)

#: Fallback question for the one required fact every safe-subset rule shares
#: (task §5.1). Used only when `select_rule` reports `vehicle_type` missing
#: -- at that point no single candidate rule has been chosen yet (a topic
#: may have both a motorcycle and a car rule), so there is no one rule to
#: pull a topic-flavored question from.
_VEHICLE_TYPE_QUESTION = "Bạn điều khiển xe máy hay ô tô?"

_TOPIC_ISSUE_LABELS = {
    "traffic_red_light": "vượt đèn đỏ",
    "traffic_no_helmet": "không đội mũ bảo hiểm",
    "traffic_alcohol": "nồng độ cồn khi lái xe",
    "traffic_speeding": "chạy quá tốc độ quy định",
    "traffic_driver_license": "giấy phép lái xe",
    "traffic_phone_use": "sử dụng điện thoại khi lái xe",
    "traffic_passenger_limit": "chở quá số người quy định",
    "traffic_vehicle_modification": "thay đổi kết cấu xe",
}


def build_search_query(message: str, topic_hint: str | None = None) -> LegalSearchQuery | None:
    """Layered query-privacy minimization (task §6.5, Correction Round 1
    M-04). Uses only the current message text (already validated non-empty/
    bounded by `AnalyzeRequest`) and an optional topic hint -- never
    conversation history or uploaded-document content, neither of which this
    orchestrator ever receives in the first place (it is handed only
    `state.request.question` and already-typed facts, never the raw chat
    history object).

    Strategy, in order:

      1. If the message matches a known bounded legal-issue category (a
         handful of common Vietnamese phrasings -- labor/wage, dismissal,
         land dispute, etc.), build the query from a FIXED topic-level
         template. This never touches the raw narrative at all, so no name,
         address, or contact value the user wrote can ever reach it.
      2. Otherwise, minimize the raw narrative: strip contact-shaped digit
         runs, email addresses, street-number+name address patterns, and
         "tôi là <Name>"-style self-introductions (a bounded heuristic, not
         Vietnamese NER -- see `_NAME_INTRO_RE`).
      3. If minimization leaves nothing usable (empty/whitespace-only), fail
         closed: return `None`. Callers MUST treat `None` as "do not call
         search" and defer to `GENERAL_GUIDANCE` -- never fall back to
         sending the raw, unminimized message.
    """

    normalized = _normalize_for_category(message)
    for cue, structured_query in _ISSUE_CATEGORY_QUERIES:
        if cue in normalized:
            return LegalSearchQuery(query_text=structured_query, legal_topic_hint=topic_hint)

    minimized = _minimize_narrative(message).strip()
    # Fail closed on punctuation-only leftovers too (e.g. a bare "Tôi là
    # Nguyễn Văn A." minimizes to a lone "."), not just a literally empty
    # string -- neither is a usable search query.
    if not minimized or not re.search(r"\w", minimized):
        return None
    return LegalSearchQuery(query_text=minimized[:400], legal_topic_hint=topic_hint)


def _normalize_for_category(text: str) -> str:
    nfc = unicodedata.normalize("NFC", text)
    decomposed = unicodedata.normalize("NFD", nfc.lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.replace("đ", "d")


#: Bounded set of common Vietnamese legal-issue phrasings, each mapped to a
#: FIXED topic-level query template (task §6.5: "prefer constructing the
#: legal search query from structured legal topic... category and
#: normalized legal keywords"). Deliberately small and hand-curated, not a
#: general classifier -- when nothing here matches, `build_search_query`
#: falls through to narrative minimization instead.
_ISSUE_CATEGORY_QUERIES: tuple[tuple[str, str], ...] = (
    (
        "khong tra luong",
        "quy định pháp luật Việt Nam về người sử dụng lao động không trả lương "
        "sau khi người lao động nghỉ việc",
    ),
    ("giu luong", "quy định pháp luật Việt Nam về người sử dụng lao động giữ lương của người lao động"),
    ("sa thai", "quy định pháp luật Việt Nam về sa thải người lao động"),
    ("hop dong lao dong", "quy định pháp luật Việt Nam về hợp đồng lao động"),
    ("lan chiem dat", "quy định pháp luật Việt Nam về lấn chiếm đất đai"),
    ("lan chiem nha", "quy định pháp luật Việt Nam về lấn chiếm nhà ở"),
    ("tranh chap dat", "quy định pháp luật Việt Nam về tranh chấp đất đai"),
    ("boi thuong", "quy định pháp luật Việt Nam về bồi thường thiệt hại"),
    ("khieu nai", "quy định pháp luật Việt Nam về thủ tục khiếu nại hành chính"),
    ("khoi kien", "quy định pháp luật Việt Nam về thủ tục khởi kiện dân sự"),
)


#: Contact-value-shaped digit runs -- phone numbers, CCCD/CMND, bank
#: accounts. Bounded and conservative: over-redacting is safe, under-
#: redacting is not.
_SENSITIVE_PATTERNS_REDACTED = (
    (r"\b0\d{9,10}\b", "[so_dien_thoai]"),
    (r"\b\d{9}\b", "[giay_to_tuy_than]"),
    (r"\b\d{12}\b", "[giay_to_tuy_than]"),
    (r"\b\d{8,16}\b", "[so_tai_khoan]"),
)

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

#: A Vietnamese proper-noun-shaped word: starts with an uppercase letter
#: (including Đ, extremely common in given/family names and place names --
#: "Đạo", "Đông", "Đức" -- but never matched by a plain A-Z range).
#: Deliberately NOT full Unicode-aware capitalization (`re` has no
#: `\p{Lu}`), so a name written with an initial Ư/Ơ/Ê capital is missed --
#: bounded heuristic, not Vietnamese NER, exactly as instructed.
_CAP_WORD = r"[A-ZĐ][a-zà-ỹđ]*"

#: A street-number + capitalized-street-name address pattern ("12 Nguyễn
#: Huệ", "45 Lê Lợi", "số 20 Trần Hưng Đạo").
_ADDRESS_RE = re.compile(rf"\b(?:s[ốo]\s+)?\d{{1,4}}\s+{_CAP_WORD}(?:\s+{_CAP_WORD}){{0,3}}")

#: A self-introduction naming the speaker ("Tôi là Nguyễn Văn A", "tên tôi
#: là ...", "tôi tên là ..."). The whole clause is dropped, not just the
#: name -- there is no legal-search value in keeping "tôi là" once the name
#: is gone.
_NAME_INTRO_RE = re.compile(
    rf"\b[Tt]ôi\s+(?:tên\s+)?là\s+{_CAP_WORD}(?:\s+{_CAP_WORD}){{0,3}}"
)


def _minimize_narrative(text: str) -> str:
    minimized = _NAME_INTRO_RE.sub("", text)
    minimized = _ADDRESS_RE.sub("", minimized)
    minimized = _EMAIL_RE.sub("[email]", minimized)
    for pattern, replacement in _SENSITIVE_PATTERNS_REDACTED:
        minimized = re.sub(pattern, replacement, minimized)
    return re.sub(r"\s+", " ", minimized).strip()


class LegalFallbackOrchestrator:
    def __init__(
        self,
        *,
        store: LegalFallbackStateStore,
        traffic_pack: TrafficSourcePack,
        search_service: OfficialLegalSearchService | None,
        official_search_enabled: bool,
    ) -> None:
        self._store = store
        self._traffic_pack = traffic_pack
        self._search_service = search_service
        self._official_search_enabled = official_search_enabled

    async def handle(self, state) -> AnalyzeResponse | None:
        """Own the turn, or return None to defer to the original
        scope_or_unsupported reply -- never raises."""

        try:
            return await self._handle(state)
        except Exception:  # noqa: BLE001 - contain; never surface a 500 or leak
            return None

    async def _handle(self, state) -> AnalyzeResponse | None:
        message = state.request.question
        chat_id = state.chat.chat_id

        # Additional narrow safety gate scoped to this vertical only (task
        # §9) -- see `legal_fallback_safety_guard.py`'s module docstring for
        # why this exists in addition to the runtime-level checks.
        if is_unsafe_for_legal_fallback(message):
            return None

        try:
            loaded = self._store.load(chat_id)
        except LegalFallbackStoreError:
            loaded = None

        current_state = loaded.state if loaded is not None else LegalFallbackState()
        expected_version = loaded.state_version if loaded is not None else None

        detection = classify_traffic(message)
        pending_topic_id = current_state.traffic_topic_id
        pending_field = current_state.traffic_pending_field

        # Correction Round 2 (M-02-R): a fresh topic mention in THIS message
        # always takes priority over a stale pending clarification -- exactly
        # one dispatch, never both. Only when there is no fresh topic AND a
        # clarification is genuinely pending does the message get routed
        # through the TYPED, field-specific parser (`parse_clarification_
        # answer`), whose result decides everything from here: it is never
        # re-run through the generic attribution/topic classifier for this
        # decision (a clarification answer's attribution comes from the
        # pending QUESTION, not from the reply needing its own subject).
        if detection.topic_id is None and pending_topic_id is not None and pending_field is not None:
            answer = parse_clarification_answer(pending_field, message)
            if answer.kind != ClarificationAnswerKind.UNRELATED:
                return await self._handle_pending_clarification_answer(
                    state, message, answer, pending_topic_id, current_state, loaded, expected_version
                )

            # UNRELATED: durably release the stale pending state, THEN route
            # this exact message as a fresh turn -- exactly once, never a
            # second traffic/search pass and never using the stale topic.
            current_state = current_state.model_copy(
                update={"traffic_topic_id": None, "traffic_pending_field": None}
            )
            self._commit_best_effort(
                chat_id=chat_id, loaded=loaded, expected_version=expected_version, state=current_state
            )
            try:
                loaded = self._store.load(chat_id)
            except LegalFallbackStoreError:
                loaded = None
            expected_version = loaded.state_version if loaded is not None else None
            current_state = loaded.state if loaded is not None else current_state

        return await self._handle_fresh_turn(state, message, detection, current_state, loaded, expected_version)

    async def _handle_fresh_turn(
        self, state, message: str, detection: TrafficDetection, current_state: LegalFallbackState, loaded, expected_version: int | None
    ) -> AnalyzeResponse | None:
        """The ordinary (non-pending-clarification) turn: safety already
        cleared, no stale clarification in play (either none was pending, or
        it was just durably released by `_handle`). Exactly the Correction
        Round 1 routing order: curated traffic (self-attribution-gated) ->
        official search / general guidance -> defer."""

        topic_id = detection.topic_id
        if topic_id is None and not is_legal_or_rights_related(message, traffic_topic_detected=False):
            return None

        response: AnalyzeResponse | None = None
        candidate_state = current_state
        if topic_id is not None:
            # Correction Round 1 (M-01): only a `"self"`-attributed event may
            # persist facts or leave a personal pending clarification --
            # third-party/hypothetical/educational/negated/unknown-attributed
            # mentions may still receive a general answer, but never mutate
            # per-chat state (`_handle_traffic` branches on this).
            response, candidate_state = self._handle_traffic(
                state, topic_id, detection.facts, current_state, attribution=detection.attribution
            )

        # Either no traffic topic matched at all, or a topic matched but the
        # curated pack has no verified entry for this exact (topic,
        # vehicle_type) combination (`_handle_traffic` returns `None` for
        # that case) -- both fall through to the next routing tier (task §3:
        # curated match? no -> official-source search? insufficient ->
        # general guidance), never straight back to the canned scope reply.
        if response is None:
            if self._official_search_enabled and self._search_service is not None:
                response, candidate_state = await self._handle_official_search(
                    state, message, current_state
                )
            else:
                response, candidate_state = self._handle_general_guidance(
                    state, message, current_state
                )

        if response is None:
            return None

        self._commit_best_effort(
            chat_id=state.chat.chat_id, loaded=loaded, expected_version=expected_version, state=candidate_state
        )
        return response

    async def _handle_pending_clarification_answer(
        self,
        state,
        message: str,
        answer: ClarificationAnswer,
        topic_id: str,
        current_state: LegalFallbackState,
        loaded,
        expected_version: int | None,
    ) -> AnalyzeResponse | None:
        """Correction Round 2 (M-02-R): `answer.kind` is either `RESOLVED` or
        `UNKNOWN_VALUE` (the caller already handled `UNRELATED`). Neither
        case requires first-person attribution -- the pending question
        itself supplies the context (task §6's documented exception to
        M-01's normal self-attribution gate)."""

        if answer.kind == ClarificationAnswerKind.RESOLVED:
            # Merge ONLY the one resolved field -- never inferred/guessed
            # values for any other slot.
            single_field_facts = TrafficFacts(**{answer.field: answer.parsed_value})
            merged_facts = _merge_traffic_facts(current_state.traffic_facts, single_field_facts)
            force_answer_now = False
        else:  # UNKNOWN_VALUE
            merged_facts = current_state.traffic_facts
            # The user just said they don't know/recall -- never ask the
            # same (or any further) question again for this topic; proceed
            # with the safest available answer.
            force_answer_now = True

        response, updates = self._resolve_traffic_topic(
            state, topic_id, merged_facts, previously_pending_field=answer.field, force_answer_now=force_answer_now
        )
        candidate_state = current_state.model_copy(update=updates)

        if response is None:
            # No curated rule for this exact (topic, vehicle) combination --
            # fall through to the next routing tier exactly once, never back
            # into the pending-clarification path again.
            if self._official_search_enabled and self._search_service is not None:
                response, candidate_state = await self._handle_official_search(
                    state, message, candidate_state
                )
            else:
                response, candidate_state = self._handle_general_guidance(
                    state, message, candidate_state
                )

        if response is None:
            return None

        self._commit_best_effort(
            chat_id=state.chat.chat_id, loaded=loaded, expected_version=expected_version, state=candidate_state
        )
        return response

    def _commit_best_effort(
        self, *, chat_id: str, loaded, expected_version: int | None, state: LegalFallbackState
    ) -> None:
        if loaded is not None and expected_version is not None:
            try:
                self._store.commit_state(chat_id=chat_id, expected_version=expected_version, state=state)
            except LegalFallbackStoreError:
                pass  # informational-only vertical: a lost CAS still returns this turn's answer

    # -- traffic --------------------------------------------------------

    def _handle_traffic(
        self,
        state,
        topic_id: str,
        detected_facts: TrafficFacts,
        current: LegalFallbackState,
        *,
        attribution: str,
    ) -> tuple[AnalyzeResponse | None, LegalFallbackState]:
        # Correction Round 1 (M-01): only a `"self"`-attributed event may
        # persist facts, ask a personal follow-up clarification, or mutate
        # per-chat state at all. Every other attribution
        # (third_party/hypothetical/educational/negated/unknown) still gets
        # a shot at a general, impersonal answer -- but only when every
        # required fact is ALREADY determinable from this one message; no
        # personal clarification is ever asked about someone else's (or a
        # hypothetical) event, and `current` is returned unmodified.
        if attribution != "self":
            return self._handle_traffic_impersonal(state, topic_id, detected_facts, current)

        merged_facts = _merge_traffic_facts(current.traffic_facts, detected_facts)
        # The field the last turn's clarification (if any, for THIS topic)
        # was about -- passed through only as a defensive loop-breaker (see
        # `_resolve_traffic_topic`), not to gate asking about a *different*
        # missing field.
        previously_pending_field = (
            current.traffic_pending_field if current.traffic_topic_id == topic_id else None
        )
        response, updates = self._resolve_traffic_topic(
            state, topic_id, merged_facts, previously_pending_field=previously_pending_field, force_answer_now=False
        )
        return response, current.model_copy(update=updates)

    def _resolve_traffic_topic(
        self,
        state,
        topic_id: str,
        merged_facts: TrafficFacts,
        *,
        previously_pending_field: str | None,
        force_answer_now: bool,
    ) -> tuple[AnalyzeResponse | None, dict]:
        """Traffic Safe Subset V1: the shared core that both a fresh
        self-attributed traffic turn AND a resolved/unknown pending-
        clarification continuation (`_handle_pending_clarification_answer`)
        use to decide, from fully-merged facts, whether to ask the single
        next clarification or build the final curated answer -- via
        `TrafficSourcePack.select_rule` (task §6), never a bare
        `(topic_id, vehicle_type)` lookup.

        Returns the response plus a `LegalFallbackState` update dict
        (`traffic_facts` always included; `traffic_topic_id`/
        `traffic_pending_field` set only while a NEW clarification is being
        asked, cleared in every other outcome -- match, no-safe-rule,
        ambiguous, or forced-answer-now).

        `force_answer_now=True` (only ever passed after an explicit
        `UNKNOWN_VALUE` answer) means: never ask another question for this
        topic -- proceed with whatever is known (falling through to the next
        tier if no rule can be selected), rather than looping the same
        question the user just said they can't answer.
        """

        selection = self._traffic_pack.select_rule(topic_id, merged_facts)
        cleared_update = {"traffic_facts": merged_facts, "traffic_topic_id": None, "traffic_pending_field": None}

        if selection.outcome == RuleSelectionOutcome.MATCH:
            # Task §7: CURATED_VERIFIED only ever reachable via this exact
            # branch -- `select_rule` guarantees an ENABLED rule, every
            # required fact resolved, and no excluding fact present.
            response = _build_curated_traffic_response(state, topic_id, merged_facts.vehicle_type, selection.rule)
            return response, cleared_update

        if selection.outcome == RuleSelectionOutcome.AMBIGUOUS:
            # Task §6/§7: never a guessed curated answer -- general guidance,
            # plus an internal warning since a de-duplicated pack (enforced
            # at `TrafficSourcePack.from_file` load time) should make this
            # unreachable in normal operation.
            _logger.warning("traffic rule selection ambiguous for topic_id=%s", topic_id)
            return None, cleared_update

        if selection.outcome == RuleSelectionOutcome.NO_SAFE_RULE:
            # No enabled rule for this (topic, vehicle_type) at all, or an
            # explicit excluding fact (e.g. `signal_type="yellow"`,
            # `helmet_subject="passenger"`) is present -- fail closed to the
            # next tier rather than guessing or narrowing the caveat away.
            return None, cleared_update

        # MISSING_FACT: ask about exactly the one field `select_rule` says is
        # still blocking, unless forced to answer now, the field is unknown
        # (shouldn't happen), or it is the SAME field the immediately prior
        # turn already tried (and failed) to resolve -- a defensive loop
        # breaker; every required field in the safe subset has a bounded
        # parser, so a resolved answer always clears its own field, but this
        # keeps a hypothetical unparseable field from being re-asked forever.
        field = selection.missing_field
        if force_answer_now or field is None or field == previously_pending_field:
            return None, cleared_update

        if field == "vehicle_type":
            question = _VEHICLE_TYPE_QUESTION
        else:
            question = selection.rule.clarification_questions.get(field) if selection.rule else None
        if not question:
            return None, cleared_update

        response = self._clarification_response(state, topic_id=topic_id, question=question)
        return response, {
            "traffic_facts": merged_facts, "traffic_topic_id": topic_id, "traffic_pending_field": field,
        }

    def _handle_traffic_impersonal(
        self, state, topic_id: str, detected_facts: TrafficFacts, current: LegalFallbackState
    ) -> tuple[AnalyzeResponse | None, LegalFallbackState]:
        """A third-party/hypothetical/educational/negated/unknown-attributed
        mention (task M-01). `detected_facts` is used only transiently, for
        THIS turn's rule lookup -- it is never merged into per-chat state,
        and no personal clarification is ever asked. `current` is always
        returned exactly as received (never a blank state, which would wipe
        out any unrelated legitimate state already on this chat): this path
        touches nothing, it only READS `detected_facts` to decide whether an
        impersonal answer is possible. Falls through (`None`) to the next
        routing tier for every outcome except an exact `MATCH`, rather than
        presuming an answer or interrogating the user about someone else's
        situation."""

        selection = self._traffic_pack.select_rule(topic_id, detected_facts)
        if selection.outcome != RuleSelectionOutcome.MATCH:
            return None, current

        response = _build_curated_traffic_response(state, topic_id, detected_facts.vehicle_type, selection.rule)
        return response, current

    def _clarification_response(self, state, *, topic_id: str, question: str) -> AnalyzeResponse:
        # Legal Correction Round 1 (MEDIUM-02): a clarification is a QUESTION,
        # not a legal conclusion -- it has no sources and resolves no legal
        # proposition, so it must never carry `trust_level=curated_verified`
        # (or any other trust level, which would equally misrepresent an
        # unresolved turn as an established fact). `CURATED_VERIFIED` is
        # reachable ONLY from `_build_curated_traffic_response`, itself only
        # reachable from `select_rule`'s `MATCH` outcome.
        return AnalyzeResponse(
            response_kind="legal",
            contract_version=CONTRACT_VERSION,
            request_id=state.request.request_id,
            chat_id=state.chat.chat_id,
            user_message_id=state.persistence.user_message_id,
            assistant_message_id=state.persistence.assistant_message_id,
            domain="traffic",
            risk_level="medium",
            decision="ask_clarifying_questions",
            summary=(
                f"Tôi cần thêm một thông tin để trả lời chính xác hơn về "
                f"{_TOPIC_ISSUE_LABELS.get(topic_id, 'tình huống giao thông này')}."
            ),
            clarifying_questions=[question],
            checklist=[],
            next_steps=[],
            sources=[],
            safety_notice=SAFETY_NOTICE,
            confidence=Confidence(domain=0.7, risk=0.5, answer=0.4),
            trust_level=None,
            trust_label=None,
            trust_explanation=None,
            metadata={
                "legal_fallback": True,
                "legal_fallback_route": "curated_traffic_clarification",
                "traffic_topic_id": topic_id,
            },
        )

    # -- official search --------------------------------------------------

    async def _handle_official_search(
        self, state, message: str, current: LegalFallbackState
    ) -> tuple[AnalyzeResponse | None, LegalFallbackState]:
        query = build_search_query(message)
        if query is None:
            # M-04 fail-closed: minimization left nothing safe/usable to
            # search with -- never fall back to sending the raw message.
            return self._handle_general_guidance(state, message, current)
        try:
            result = await self._search_service.search(query)
        except Exception:  # noqa: BLE001 - a provider timeout/failure degrades
            # to general guidance (task §11: "a search outage must not break
            # curated deposit or traffic answers"), never a raw 500 and never
            # a bounce back to the unrelated canned scope reply.
            return self._handle_general_guidance(state, message, current)
        outcome = result.outcome

        evidence_record = RetrievedEvidenceRecord(
            query_text=query.query_text,
            outcome=outcome,
            retrieved_at=_now_iso(),
        )
        candidate_state = current.model_copy(update={"last_retrieved_evidence": evidence_record})

        if outcome is not EvidenceOutcome.SUFFICIENT:
            return self._handle_general_guidance(state, message, candidate_state)

        primary = select_primary_candidate(result.candidates)
        if primary is None:
            return self._handle_general_guidance(state, message, candidate_state)

        source = SourceObject(
            id=f"official_search_{abs(hash(primary.official_url))}",
            title=primary.title,
            source_name=primary.document_name or primary.title,
            url=primary.official_url,
            snippet=primary.relevant_excerpt,
            source_type="official_source",
            last_checked=primary.retrieved_at[:10],
            document_title=primary.document_name,
            document_number=primary.document_number,
            article_number=primary.article_number,
            clause_numbers=[],
            applicable_clause=None,
            relevance_note=primary.relevant_excerpt,
            retrieved_at=primary.retrieved_at,
        )
        summary_parts = [f"Theo {primary.title}"]
        if primary.document_number:
            summary_parts.append(f"({primary.document_number})")
        summary = " ".join(summary_parts) + f": {primary.relevant_excerpt}"

        response = AnalyzeResponse(
            response_kind="legal",
            contract_version=CONTRACT_VERSION,
            request_id=state.request.request_id,
            chat_id=state.chat.chat_id,
            user_message_id=state.persistence.user_message_id,
            assistant_message_id=state.persistence.assistant_message_id,
            domain="unknown",
            risk_level="medium",
            decision="answer_with_guidance",
            summary=summary,
            clarifying_questions=[],
            checklist=[],
            next_steps=["Bạn nên đối chiếu lại với văn bản gốc trước khi sử dụng cho mục đích quan trọng."],
            sources=[source],
            safety_notice=SAFETY_NOTICE,
            confidence=Confidence(domain=0.6, risk=0.5, answer=primary.retrieval_confidence),
            trust_level=TrustLevel.OFFICIAL_SOURCE_SEARCH.value,
            trust_label=trust_label(TrustLevel.OFFICIAL_SOURCE_SEARCH),
            trust_explanation=trust_explanation(TrustLevel.OFFICIAL_SOURCE_SEARCH),
            source_checked_at=primary.retrieved_at,
            metadata={"legal_fallback": True, "legal_fallback_route": "official_source_search"},
        )
        return response, candidate_state

    # -- general guidance ---------------------------------------------------

    def _handle_general_guidance(
        self, state, message: str, current: LegalFallbackState
    ) -> tuple[AnalyzeResponse, LegalFallbackState]:
        content = build_general_guidance(issue_summary="", clarifying_questions=[])
        response = AnalyzeResponse(
            response_kind="legal",
            contract_version=CONTRACT_VERSION,
            request_id=state.request.request_id,
            chat_id=state.chat.chat_id,
            user_message_id=state.persistence.user_message_id,
            assistant_message_id=state.persistence.assistant_message_id,
            domain="unknown",
            risk_level="medium",
            decision="answer_with_guidance",
            summary=content.summary,
            clarifying_questions=[],
            checklist=content.checklist,
            next_steps=content.next_steps,
            sources=[],
            safety_notice=SAFETY_NOTICE,
            confidence=Confidence(domain=0.3, risk=0.5, answer=0.3),
            uncertainty_notice=content.uncertainty_notice,
            trust_level=TrustLevel.GENERAL_GUIDANCE.value,
            trust_label=trust_label(TrustLevel.GENERAL_GUIDANCE),
            trust_explanation=trust_explanation(TrustLevel.GENERAL_GUIDANCE),
            metadata={"legal_fallback": True, "legal_fallback_route": "general_guidance"},
        )
        return response, current


#: Legal Correction Round 1 (task §6): the Vietnamese heading shown for each
#: citation role in the frontend's source panel. Kept here (not only in the
#: frontend) so the backend's own `title`/summary text and the frontend's
#: rendering can never disagree about what each role means.
_CITATION_ROLE_LABELS: dict[str, str] = {
    "primary_penalty": "Căn cứ mức phạt",
    "licence_point_deduction": "Căn cứ trừ điểm GPLX",
    "signal_interpretation": "Quy tắc tín hiệu giao thông",
}


def _format_citation_locator(
    *, article_number: str, clause_number: str, point_number: str | None
) -> str:
    parts = [f"Điều {article_number}", f"khoản {clause_number}"]
    if point_number:
        parts.append(f"điểm {point_number}")
    return " ".join(parts)


def _format_traffic_citation(rule: TrafficRuleRecord) -> str:
    """Full "<document> (<number>), Điều X khoản Y điểm Z" locator string
    for the rule's PRIMARY_PENALTY citation -- used only in the summary's
    lead-in sentence; every citation (including the secondary ones) gets its
    own full `SourceObject` via `_build_curated_traffic_response`, never
    folded into this one string."""

    primary = next(
        (c for c in rule.legal_citations if c.citation_role == "primary_penalty"), None
    )
    if primary is None:
        # Structurally unreachable for an ENABLED rule (load-time validation
        # requires exactly one primary_penalty citation) -- defensive only.
        base = f"{rule.legal_document_name} ({rule.legal_document_number})"
        locator_parts = []
        if rule.article_number:
            locator_parts.append(f"Điều {rule.article_number}")
        if rule.clause_number:
            locator_parts.append(f"khoản {rule.clause_number}")
        if rule.point_number:
            locator_parts.append(f"điểm {rule.point_number}")
        locator = " ".join(locator_parts)
        return f"{base}, {locator}" if locator else base

    locator = _format_citation_locator(
        article_number=primary.article_number,
        clause_number=primary.clause_number,
        point_number=primary.point_number,
    )
    return f"{primary.document_name} ({primary.document_number}), {locator}"


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _build_citation_sources(rule: TrafficRuleRecord) -> list[SourceObject]:
    """Legal Correction Round 1 (MEDIUM-01): one independently traceable
    `SourceObject` per entry in `rule.legal_citations` -- the licence-point
    deduction and (for red-light rules) the Luật 36/2024/QH15 signal-
    priority basis each get their own card with their own official URL,
    never folded into the primary-penalty citation's prose."""

    sources: list[SourceObject] = []
    for citation in rule.legal_citations:
        clause_int = _safe_int(citation.clause_number)
        locator = _format_citation_locator(
            article_number=citation.article_number,
            clause_number=citation.clause_number,
            point_number=citation.point_number,
        )
        sources.append(
            SourceObject(
                id=f"{rule.rule_id}__{citation.citation_role}",
                title=_CITATION_ROLE_LABELS.get(citation.citation_role, citation.document_name),
                source_name=citation.document_name,
                url=citation.official_url,
                snippet=citation.relevance_note,
                source_type="official_source",
                last_checked=rule.last_verified_at,
                document_title=citation.document_name,
                document_number=citation.document_number,
                article_number=citation.article_number,
                clause_numbers=[clause_int] if clause_int is not None else [],
                applicable_clause=clause_int,
                relevance_note=f"{locator} — {citation.relevance_note}",
                clause_number=citation.clause_number,
                point_number=citation.point_number,
                citation_role=citation.citation_role,
            )
        )
    return sources


def _build_curated_traffic_response(
    state, topic_id: str, vehicle_type: str, rule: TrafficRuleRecord
) -> AnalyzeResponse:
    """Shared by the self-attributed and impersonal (M-01) traffic paths --
    the rendered text is already general/law-stating ("Người điều khiển...
    bị phạt..."), never phrased as an accusation ("bạn đã vi phạm"), so it
    is equally valid for a confirmed self-report or an impersonal/
    hypothetical/third-party question about the same rule.

    Traffic Safe Subset V1: prefers `rule.answer_template` (the final,
    conditionally-worded answer, e.g. "Nếu... không thuộc trường hợp...")
    over the older `source_excerpt` prose -- every enabled rule in the safe
    subset carries one (enforced structurally: only ever reached via
    `select_rule`'s `MATCH` outcome, task §7).

    Legal Correction Round 1 (MEDIUM-01): `sources` is built entirely from
    `rule.legal_citations` (one card per independently traceable legal
    basis), never a single citation folded around `source_excerpt` prose."""

    citation = _format_traffic_citation(rule)
    answer_text = rule.answer_template or rule.source_excerpt
    sources = _build_citation_sources(rule)
    summary = f"Theo {citation}: {answer_text}"
    return AnalyzeResponse(
        response_kind="legal",
        contract_version=CONTRACT_VERSION,
        request_id=state.request.request_id,
        chat_id=state.chat.chat_id,
        user_message_id=state.persistence.user_message_id,
        assistant_message_id=state.persistence.assistant_message_id,
        domain="traffic",
        risk_level="medium",
        decision="answer_with_guidance",
        summary=summary,
        clarifying_questions=[],
        checklist=[],
        next_steps=[
            "Đây là khung phạt tham khảo; mức phạt cụ thể còn phụ thuộc tình tiết thực tế "
            "và quyết định của người có thẩm quyền xử lý.",
        ],
        sources=sources,
        safety_notice=SAFETY_NOTICE,
        confidence=Confidence(domain=0.85, risk=0.6, answer=0.75),
        trust_level=TrustLevel.CURATED_VERIFIED.value,
        trust_label=trust_label(TrustLevel.CURATED_VERIFIED),
        trust_explanation=trust_explanation(TrustLevel.CURATED_VERIFIED),
        source_checked_at=rule.last_verified_at,
        metadata={
            "legal_fallback": True,
            "legal_fallback_route": "curated_traffic",
            "traffic_topic_id": topic_id,
            "traffic_rule_id": rule.rule_id,
            "vehicle_type": vehicle_type,
        },
    )


def _merge_traffic_facts(current: TrafficFacts, detected: TrafficFacts) -> TrafficFacts:
    """Newly-detected explicit values win; `"unknown"`/`None` in the new
    detection never overwrites an already-accepted stronger value from an
    earlier turn (task §8: "Do not overwrite stronger evidence with weaker
    later text")."""

    updates: dict = {}
    for slot in TrafficFacts.model_fields:
        new_value = getattr(detected, slot)
        if new_value not in (None, "unknown"):
            updates[slot] = new_value
    return current.model_copy(update=updates)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = ["LegalFallbackOrchestrator", "build_search_query"]
