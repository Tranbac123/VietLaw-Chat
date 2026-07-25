"""SCRIPTED DEMO orchestration: safety defer -> scenario classify -> route ->
bounded extraction -> LLM enum plan -> BACKEND deterministic rendering.

The LLM returns only an enum :class:`DemoResponsePlan`; the backend owns every
visible string. FactSlot state is projected by the accepted A1 resolver; the
amount and every fact come from trusted captured facts, never the model; the
approved Article 328 source appears only as a backend Source object. Entered only
when the demo flag wires a :class:`DemoOrchestrator`; otherwise baseline is
unchanged.

Conformance to :class:`DemoResponsePlan` is enforced by Anthropic native
Structured Outputs (``ANTHROPIC_OUTPUT_MODE=native_structured_outputs``), not
by a prompt-only JSON contract. There is exactly one provider call per turn --
no JSON-repair retry -- with every failure mode (invalid JSON, schema
mismatch, refusal, truncation, network/provider error) classified into the
same deterministic fallback.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from ..constants import CONTRACT_VERSION, SAFETY_NOTICE
from ..contracts.demo_llm import (
    ActionCode,
    DemoGenerationResult,
    DemoResponsePlan,
    DemoRoute,
    DemoScenario,
    GenerationMode,
    GenerationOutcomeKind,
    LLMErrorKind,
    LLMPlanRequest,
    PlanKind,
    TrustedFactView,
)
from ..contracts.legal_facts import (
    BoundFactOperation,
    Claimant,
    FactSlot,
    FactStatus,
    FactValue,
    MoneyAmount,
    PaymentEvidenceValue,
    UnboundFactOperation,
)
from ..application.fact_conflict_resolver import resolve_fact_operation
from ..schemas.api import AnalyzeResponse
from ..schemas.content import Confidence, SourceObject
from .demo_deposit_extractor import classify_demo_scenario, extract_scenario_facts
from .demo_generation_router import route_demo, should_defer_demo_for_risk
from .demo_llm_client import DemoLLMConfig, LLMClientError, LLMClientProtocol
from .demo_llm_guards import default_plan, parse_demo_plan

PROMPT_VERSION = "demo_plan_prompt.v1"
RESOLVER_VERSION = "demo.resolver.v1"
REGISTRY_VERSION = "demo.registry.v1"
DEMO_EPISODE_ID = "demo-rental-deposit"

ARTICLE_328_AUTHORITY_ID = "civil_deposit_001"
EVIDENCE_CHECKLIST_ID = "civil_rental_001"

_ACTION_TEXT = {
    ActionCode.PRESERVE_PAYMENT_EVIDENCE: "Giữ lại toàn bộ chứng từ thanh toán và các trao đổi liên quan.",
    ActionCode.SEND_WRITTEN_REFUND_REQUEST: "Gửi yêu cầu hoàn trả tiền đặt cọc bằng văn bản (tin nhắn/email).",
    ActionCode.REQUEST_WRITTEN_RESPONSE: "Đề nghị chủ nhà phản hồi bằng văn bản trong thời gian hợp lý.",
    ActionCode.SEEK_PROFESSIONAL_HELP: "Nếu không đạt kết quả, tham khảo luật sư hoặc cơ quan chức năng.",
}
_DEFAULT_ACTIONS = [ActionCode.SEND_WRITTEN_REFUND_REQUEST, ActionCode.PRESERVE_PAYMENT_EVIDENCE, ActionCode.SEEK_PROFESSIONAL_HELP]
_MAX_ACTIONS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# A1 fact application (per-slot, in-memory only; no persistence)
# ---------------------------------------------------------------------------

@dataclass
class AppliedFacts:
    slots: dict[str, FactSlot[FactValue]]


def apply_operations(ops: list[UnboundFactOperation], request_id: str) -> AppliedFacts:
    slots: dict[str, FactSlot[FactValue]] = {}
    assertions_by_slot: dict[str, list] = {}
    for i, unbound in enumerate(ops):
        slot = unbound.slot_hint
        bound = BoundFactOperation(
            unbound=unbound, episode_id=DEMO_EPISODE_ID, bound_issue_type="rental_deposit",
            slot=slot, resolver_version=RESOLVER_VERSION, request_id=request_id,
        )
        current = slots.get(slot, FactSlot[FactValue]())
        result = resolve_fact_operation(
            current, bound, assertions_by_slot.get(slot, []),
            assertion_id=f"demo-a-{i}", observed_at=_now(), registry_version=REGISTRY_VERSION,
        )
        slots[slot] = result.projected_slot
        if result.assertion_to_append is not None:
            assertions_by_slot.setdefault(slot, []).append(result.assertion_to_append)
    return AppliedFacts(slots=slots)


def _amount(applied: AppliedFacts) -> MoneyAmount | None:
    slot = applied.slots.get("deposit_amount")
    return slot.value if slot is not None and isinstance(slot.value, MoneyAmount) else None


def build_trusted_views(applied: AppliedFacts) -> list[TrustedFactView]:
    trusted: list[TrustedFactView] = []
    for slot, fs in applied.slots.items():
        if fs.status not in (FactStatus.PRESENT, FactStatus.ABSENT) or fs.claimant is not Claimant.USER:
            continue
        verification = "document_claimed" if slot == "payment_evidence_exists" and fs.status is FactStatus.PRESENT else "unverified"
        value_summary = fs.value.as_written if isinstance(fs.value, MoneyAmount) else None
        trusted.append(TrustedFactView(
            slot=slot, status="present" if fs.status is FactStatus.PRESENT else "absent",
            verification=verification, value_summary=value_summary,
        ))
    return trusted


# ---------------------------------------------------------------------------
# LLM enum-plan request -- exactly one call per turn.
#
# Conformance is enforced by Anthropic native Structured Outputs
# (``output_config.format.type = "json_schema"`` in demo_llm_client.py), not by
# prompt text or a second "please fix your JSON" repair call. There is no
# repair path: any failure -- invalid JSON, schema mismatch, refusal,
# truncation, network/provider error -- goes straight to the deterministic
# fallback with a diagnostic reason code. See owner decision
# ``PROMPT_ONLY_JSON_CONTRACT=no``.
# ---------------------------------------------------------------------------

def _system_prompt() -> str:
    return (
        "Bạn hỗ trợ tình huống đặt cọc thuê nhà. Trả về một kế hoạch phản hồi gồm các mã "
        "enum: plan_kind, summary_code, action_codes (danh sách), tone. TUYỆT ĐỐI KHÔNG viết "
        "bất kỳ văn bản tự do, số tiền, tên điều luật, nguồn hay URL nào. Toàn bộ nội dung "
        "hiển thị sẽ do hệ thống tạo."
    )


def _user_prompt(request: LLMPlanRequest) -> str:
    body = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
    return f"Dữ liệu:\n{body}"


@dataclass
class _PlanOutcome:
    plan: DemoResponsePlan
    outcome: GenerationOutcomeKind
    attempts: int
    error_kind: LLMErrorKind | None
    reason_code: str


async def request_plan(request: LLMPlanRequest, client: LLMClientProtocol, config: DemoLLMConfig) -> _PlanOutcome:
    mode: GenerationMode = request.generation_mode
    readiness = config.readiness_error()
    if readiness is not None:
        return _PlanOutcome(default_plan(mode), GenerationOutcomeKind.DETERMINISTIC_FALLBACK, 0, readiness, f"demo.fallback.{readiness.value}")

    try:
        raw = await client.complete(
            system=_system_prompt(), user=_user_prompt(request), max_tokens=config.max_tokens, timeout_s=config.timeout_s
        )
    except LLMClientError as exc:
        return _PlanOutcome(default_plan(mode), GenerationOutcomeKind.DETERMINISTIC_FALLBACK, 1, exc.kind, f"demo.fallback.{exc.kind.value}")
    except Exception:  # noqa: BLE001 - contained; CancelledError is BaseException and propagates
        return _PlanOutcome(default_plan(mode), GenerationOutcomeKind.DETERMINISTIC_FALLBACK, 1, LLMErrorKind.PROVIDER_ERROR, "demo.fallback.provider_error")

    plan, outcome = parse_demo_plan(raw)
    if plan is None:
        # Diagnostic-only distinction; neither case triggers a second network call.
        error_kind = LLMErrorKind.INVALID_JSON if outcome.reason_code == "demo.plan.invalid_json.v1" else LLMErrorKind.SCHEMA_INVALID
        return _PlanOutcome(default_plan(mode), GenerationOutcomeKind.DETERMINISTIC_FALLBACK, 1, error_kind, f"demo.fallback.{error_kind.value}")
    return _PlanOutcome(plan, GenerationOutcomeKind.LLM_ACCEPTED, 1, None, "demo.plan.accepted.v1")


# ---------------------------------------------------------------------------
# BACKEND deterministic rendering (all visible prose is backend-owned)
# ---------------------------------------------------------------------------

def _fact_present(applied: AppliedFacts, slot: str, status: FactStatus) -> bool:
    fs = applied.slots.get(slot)
    return fs is not None and fs.status is status and fs.claimant is Claimant.USER


def render_guidance_summary(applied: AppliedFacts) -> str:
    parts: list[str] = ["Theo thông tin bạn cung cấp"]
    amount = _amount(applied)
    if amount is not None:
        parts.append(f", bạn đã đặt cọc {amount.as_written}")
    clauses: list[str] = []
    if _fact_present(applied, "written_agreement_exists", FactStatus.ABSENT):
        clauses.append("chưa có giấy đặt cọc")
    if _fact_present(applied, "payment_evidence_exists", FactStatus.PRESENT):
        clauses.append("có chứng từ thanh toán")
    if _fact_present(applied, "property_handed_over", FactStatus.ABSENT):
        clauses.append("chưa được bàn giao nhà")
    if _fact_present(applied, "deposit_returned", FactStatus.ABSENT):
        clauses.append("chủ nhà chưa hoàn trả tiền cọc")
    if clauses:
        parts.append(", " + ", ".join(clauses))
    parts.append(
        ". Trước mắt bạn nên yêu cầu hoàn cọc bằng văn bản và giữ lại toàn bộ chứng từ. "
        "Nguồn pháp luật liên quan được hiển thị trong phần Nguồn bên dưới."
    )
    return "".join(parts)


def render_actions(plan: DemoResponsePlan) -> list[str]:
    codes = plan.action_codes or _DEFAULT_ACTIONS
    seen: list[str] = []
    for code in codes:
        text = _ACTION_TEXT.get(code)
        if text and text not in seen:
            seen.append(text)
        if len(seen) >= _MAX_ACTIONS:
            break
    return seen or [_ACTION_TEXT[_DEFAULT_ACTIONS[0]]]


def render_draft(applied: AppliedFacts) -> str:
    amount = _amount(applied)
    money = f" {amount.as_written}" if amount is not None else ""
    return (
        f"Kính gửi anh/chị chủ nhà, tôi đã đặt cọc{money} khi thuê nhà. Tôi đề nghị anh/chị hoàn "
        "trả lại khoản tiền đặt cọc này cho tôi và phản hồi giúp tôi bằng văn bản trong thời gian "
        "sớm nhất. Tôi xin cảm ơn."
    )


# ---------------------------------------------------------------------------
# Turn orchestrator
# ---------------------------------------------------------------------------

class DemoOrchestrator:
    def __init__(self, *, llm_client: LLMClientProtocol, llm_config: DemoLLMConfig, source_objects: dict[str, SourceObject]) -> None:
        self._client = llm_client
        self._config = llm_config
        self._sources = source_objects

    def _source_objects_for(self, ids: list[str]) -> list[SourceObject]:
        seen: list[SourceObject] = []
        for source_id in ids:
            obj = self._sources.get(source_id)
            if obj is not None and obj not in seen:
                seen.append(obj)
        return seen

    async def handle(self, state) -> AnalyzeResponse | None:
        c = state.classification
        # Safety ordering: baseline flags + bounded demo-safety defer, BEFORE any
        # scenario classification / extraction / provider construction.
        if c.unsafe_intent_detected or c.high_risk_detected:
            return None
        if should_defer_demo_for_risk(state.request.question):
            return None

        nfc = unicodedata.normalize("NFC", state.request.question)
        message_id = state.persistence.user_message_id
        scenario = classify_demo_scenario(nfc)
        route = route_demo(c.normalized_question, c.accent_insensitive_question, scenario)

        if route.route in (DemoRoute.SOCIAL_DIRECT, DemoRoute.CAPABILITY_DIRECT):
            return self._social_response(state, route)
        if route.route is DemoRoute.SOURCE_LOOKUP_DIRECT:
            return self._source_lookup_response(state, route)
        if route.route is DemoRoute.POLICY_DIRECT:
            return self._policy_response(state, route)

        extraction = extract_scenario_facts(nfc, scenario, message_id)
        applied = apply_operations(extraction.operations, state.request.request_id)

        if route.route is DemoRoute.FACT_UPDATE_DIRECT:
            return self._fact_update_response(state, route, applied)

        mode: GenerationMode = "document_drafting" if route.route is DemoRoute.DOCUMENT_DRAFTING else "legal_generation"
        request = LLMPlanRequest(
            request_id=state.request.request_id, generation_mode=mode,
            trusted_facts=build_trusted_views(applied), prompt_version=PROMPT_VERSION,
        )
        plan_outcome = await request_plan(request, self._client, self._config)
        if mode == "document_drafting":
            summary = render_draft(applied)
            next_steps: list[str] = []
            sources = self._source_objects_for([])
        else:
            summary = render_guidance_summary(applied)
            next_steps = render_actions(plan_outcome.plan)
            sources = self._source_objects_for([ARTICLE_328_AUTHORITY_ID])
        result = DemoGenerationResult(
            outcome=plan_outcome.outcome, summary=summary, next_steps=next_steps,
            used_source_ids=[s.id for s in sources], reason_code=plan_outcome.reason_code,
            llm_error_kind=plan_outcome.error_kind, provider_calls=plan_outcome.attempts,
            plan_kind=plan_outcome.plan.plan_kind,
        )
        return self._legal_envelope(
            state, route, summary=summary, next_steps=next_steps, clarifying=[], sources=sources,
            decision="answer_with_guidance", risk="medium", answer_conf=0.78 if plan_outcome.outcome is GenerationOutcomeKind.LLM_ACCEPTED else 0.5,
            extra={"outcome": result.outcome.value, "provider_calls": result.provider_calls,
                   "llm_error_kind": result.llm_error_kind.value if result.llm_error_kind else None,
                   "plan_kind": result.plan_kind.value if result.plan_kind else None,
                   "generation_reason": result.reason_code},
        )

    # -- response builders ---------------------------------------------------

    def _base_metadata(self, route, extra: dict) -> dict:
        metadata = {
            "demo_vertical_slice": True, "demo_route": route.route.value, "demo_scenario": route.scenario.value,
            "demo_route_reason": route.reason_code, "llm_required": route.llm_required,
            "used_current_chat_history": False, "detected_topic": "rental_deposit", "asked_question_ids": [],
        }
        metadata.update(extra)
        return metadata

    def _social_response(self, state, route) -> AnalyzeResponse:
        if route.route is DemoRoute.CAPABILITY_DIRECT:
            text = (
                "Trong bản demo này, tôi hỗ trợ tình huống đặt cọc thuê nhà: ghi nhận thông tin bạn cung cấp, "
                "gợi ý hướng xử lý và soạn tin nhắn yêu cầu hoàn cọc. Nguồn pháp luật được hiển thị trong phần "
                "Nguồn bên dưới khi có."
            )
        else:
            text = "Chào bạn, tôi có thể hỗ trợ bạn về vấn đề đặt cọc thuê nhà. Bạn cứ mô tả tình huống của mình nhé."
        return self._social_envelope(state, route, text)

    def _policy_response(self, state, route) -> AnalyzeResponse:
        text = (
            "Bản demo này chỉ hỗ trợ tình huống đặt cọc thuê nhà (khi bạn đã thực sự đặt cọc). "
            "Bạn vui lòng mô tả đúng tình huống đặt cọc để tôi hỗ trợ nhé."
        )
        return self._social_envelope(state, route, text)

    def _social_envelope(self, state, route, text: str) -> AnalyzeResponse:
        return AnalyzeResponse(
            response_kind="social", contract_version=CONTRACT_VERSION, request_id=state.request.request_id,
            chat_id=state.chat.chat_id, user_message_id=state.persistence.user_message_id,
            assistant_message_id=state.persistence.assistant_message_id, domain=None, risk_level=None, decision=None,
            summary=text, clarifying_questions=[], checklist=[], next_steps=[], sources=[], safety_notice="",
            confidence=None, metadata=self._base_metadata(route, {}),
        )

    def _source_lookup_response(self, state, route) -> AnalyzeResponse:
        sources = self._source_objects_for([ARTICLE_328_AUTHORITY_ID, EVIDENCE_CHECKLIST_ID])
        summary = "Với tình huống đặt cọc thuê nhà, nguồn pháp luật liên quan được hiển thị trong phần Nguồn bên dưới."
        return self._legal_envelope(state, route, summary=summary, next_steps=[], clarifying=[], sources=sources,
                                    decision="answer_with_guidance", risk="low", answer_conf=0.7, extra={"outcome": "source_lookup"})

    def _fact_update_response(self, state, route, applied: AppliedFacts) -> AnalyzeResponse:
        fragments = self._ack_fragments(applied)
        summary = ("Đã ghi nhận: " + "; ".join(fragments) + ".") if fragments else (
            "Tôi chưa ghi nhận được thông tin đặt cọc cụ thể. Bạn có thể nêu rõ số tiền đã đặt cọc không?"
        )
        return self._legal_envelope(
            state, route, summary=summary, next_steps=[], clarifying=[] if fragments else ["Số tiền bạn đã đặt cọc là bao nhiêu?"],
            sources=[], decision="answer_with_guidance" if fragments else "ask_clarifying_questions",
            risk="medium", answer_conf=0.6 if fragments else 0.45,
            extra={"outcome": "fact_acknowledged", "recorded_slots": sorted(applied.slots)},
        )

    def _ack_fragments(self, applied: AppliedFacts) -> list[str]:
        fragments: list[str] = []
        amount = _amount(applied)
        if amount is not None:
            fragments.append(f"đã đặt cọc {amount.as_written}")
        if _fact_present(applied, "written_agreement_exists", FactStatus.ABSENT):
            fragments.append("chưa có giấy đặt cọc")
        if _fact_present(applied, "payment_evidence_exists", FactStatus.PRESENT):
            fragments.append("có chứng từ thanh toán")
        if _fact_present(applied, "property_handed_over", FactStatus.ABSENT):
            fragments.append("chưa được bàn giao nhà")
        if _fact_present(applied, "deposit_returned", FactStatus.ABSENT):
            fragments.append("chủ nhà chưa hoàn trả tiền cọc")
        return fragments

    def _legal_envelope(self, state, route, *, summary, next_steps, clarifying, sources, decision, risk, answer_conf, extra) -> AnalyzeResponse:
        confidence = Confidence(domain=0.9, risk=0.8 if risk == "medium" else 0.7, answer=answer_conf)
        return AnalyzeResponse(
            response_kind="legal", contract_version=CONTRACT_VERSION, request_id=state.request.request_id,
            chat_id=state.chat.chat_id, user_message_id=state.persistence.user_message_id,
            assistant_message_id=state.persistence.assistant_message_id, domain="civil_dispute", risk_level=risk,
            decision=decision, summary=summary, clarifying_questions=clarifying, checklist=[], next_steps=next_steps,
            sources=sources, safety_notice=SAFETY_NOTICE, confidence=confidence, metadata=self._base_metadata(route, extra),
        )


__all__ = [
    "ARTICLE_328_AUTHORITY_ID",
    "EVIDENCE_CHECKLIST_ID",
    "AppliedFacts",
    "DemoOrchestrator",
    "apply_operations",
    "build_trusted_views",
    "render_draft",
    "render_guidance_summary",
    "request_plan",
]
