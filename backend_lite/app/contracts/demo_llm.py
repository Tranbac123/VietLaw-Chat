"""Strict contracts for the SCRIPTED DEMO VERTICAL SLICE V1 (rental_deposit only).

Scope: this is a SCRIPTED vertical slice, NOT a general legal chatbot, NOT full
Phase A2, NOT persistence, NOT multi-episode. Only four scenario families are
supported (greeting, deposit fact-update, deposit legal-guidance, deposit
drafting). The LLM returns ONLY a structured enum plan (:class:`DemoResponsePlan`)
— never user-visible free text. The backend deterministically renders all prose
from plan codes plus trusted captured facts. Nothing here lets the model produce
prose, amounts, sources, articles, URLs, or facts.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictDemoModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Scenario classification + routing
# ---------------------------------------------------------------------------

class DemoScenario(str, Enum):
    GREETING_DIRECT = "greeting_direct"
    DEPOSIT_FACT_UPDATE = "deposit_fact_update"
    DEPOSIT_LEGAL_GUIDANCE = "deposit_legal_guidance"
    DEPOSIT_DRAFT_REQUEST = "deposit_draft_request"
    UNSUPPORTED = "unsupported"


class DemoRoute(str, Enum):
    SOCIAL_DIRECT = "social_direct"
    CAPABILITY_DIRECT = "capability_direct"
    SOURCE_LOOKUP_DIRECT = "source_lookup_direct"
    FACT_UPDATE_DIRECT = "fact_update_direct"
    LEGAL_GENERATION = "legal_generation"
    DOCUMENT_DRAFTING = "document_drafting"
    POLICY_DIRECT = "policy_direct"


LLM_ROUTES: frozenset[DemoRoute] = frozenset({DemoRoute.LEGAL_GENERATION, DemoRoute.DOCUMENT_DRAFTING})


class DemoGenerationRoute(StrictDemoModel):
    route: DemoRoute
    llm_required: bool
    reason_code: str = Field(min_length=1, max_length=64)
    scenario: DemoScenario


# ---------------------------------------------------------------------------
# LLM request (bounded context only)
# ---------------------------------------------------------------------------

DemoIssueType = Literal["rental_deposit"]
GenerationMode = Literal["legal_generation", "document_drafting"]
ReportedVerification = Literal["unverified", "document_claimed"]


class TrustedFactView(StrictDemoModel):
    slot: str = Field(min_length=1, max_length=64)
    status: Literal["present", "absent"]
    claimant: Literal["user"] = "user"
    verification: ReportedVerification = "unverified"
    value_summary: str | None = Field(default=None, max_length=120)


class ApprovedAuthority(StrictDemoModel):
    source_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    source_name: str = Field(min_length=1, max_length=200)
    snippet: str = Field(min_length=1, max_length=1200)


class LLMPlanRequest(StrictDemoModel):
    """What the provider is allowed to see. No raw history, no unrelated issues."""

    request_id: str = Field(min_length=1, max_length=128)
    generation_mode: GenerationMode
    issue_type: DemoIssueType = "rental_deposit"
    trusted_facts: list[TrustedFactView] = Field(default_factory=list, max_length=16)
    schema_version: Literal["demo_plan_request.v1"] = "demo_plan_request.v1"
    prompt_version: str = Field(min_length=1, max_length=32)


# ---------------------------------------------------------------------------
# LLM STRUCTURED PLAN (enum-only; the ONLY thing the model may return)
# ---------------------------------------------------------------------------

class PlanKind(str, Enum):
    LEGAL_GUIDANCE = "legal_guidance"
    DRAFT_REQUEST = "draft_request"


class SummaryCode(str, Enum):
    DEPOSIT_NOT_RETURNED = "deposit_not_returned"
    DEPOSIT_NO_WRITTEN_AGREEMENT = "deposit_no_written_agreement"
    DEPOSIT_HANDOVER_NOT_COMPLETED = "deposit_handover_not_completed"


class ActionCode(str, Enum):
    PRESERVE_PAYMENT_EVIDENCE = "preserve_payment_evidence"
    SEND_WRITTEN_REFUND_REQUEST = "send_written_refund_request"
    REQUEST_WRITTEN_RESPONSE = "request_written_response"
    SEEK_PROFESSIONAL_HELP = "seek_professional_help"


class Tone(str, Enum):
    NEUTRAL = "neutral"
    POLITE_FIRM = "polite_firm"


class DemoResponsePlan(StrictDemoModel):
    """The complete model output surface. Enums only — no free text, no amounts,
    no sources, no facts. Invalid plans are replaced by a deterministic default."""

    plan_kind: PlanKind
    summary_code: SummaryCode
    action_codes: list[ActionCode] = Field(default_factory=list, max_length=4)
    tone: Tone


# ---------------------------------------------------------------------------
# Anthropic native Structured Outputs wire schema for DemoResponsePlan.
#
# Hand-authored (not derived from Pydantic's `model_json_schema()`, which emits
# `$ref`/`$defs` for enum members) so the wire payload is a single flat, fully
# self-contained JSON Schema object -- exactly `output_config.format.schema`.
# Enum value lists are built FROM the Enum classes above, so this constant
# cannot silently drift from `DemoResponsePlan`'s actual accepted values; see
# `test_demo_llm_generation.py::test_structured_output_schema_matches_enums`.
#
# All four fields are marked required at the WIRE level (the model must always
# emit `action_codes`, even as `[]`), independent of the local Pydantic model's
# `default_factory=list` on that field, which exists only to keep local/test
# construction lenient. `additionalProperties: false` and per-field `enum`
# lists are the two constraints that a prompt-only JSON contract could never
# enforce natively.
#
# `action_codes` deliberately carries NO `maxItems` at the wire level (Codex
# V1 finding H-1: Anthropic's Structured Outputs JSON Schema subset does not
# support `maxItems`; an unsupported keyword risks the whole schema being
# rejected or silently ignored by the provider). The four-item cap is enforced
# ONLY locally, by `DemoResponsePlan.action_codes`'s `max_length=4` Pydantic
# constraint below -- this is a deliberate two-layer contract: the wire schema
# constrains type/enum/required/additionalProperties (what the provider can
# structurally emit), local validation constrains cardinality (how many the
# backend will accept) before any oversized plan can be rendered, and any
# malformed/invalid plan (including an oversized `action_codes`) falls back
# deterministically after exactly one provider call -- the provider can never
# directly control rendered prose regardless of which layer rejects it. See
# `test_demo_llm_generation.py::test_structured_output_schema_matches_enums`.
# ---------------------------------------------------------------------------

DEMO_RESPONSE_PLAN_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "plan_kind": {
            "type": "string",
            "enum": [member.value for member in PlanKind],
        },
        "summary_code": {
            "type": "string",
            "enum": [member.value for member in SummaryCode],
        },
        "action_codes": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [member.value for member in ActionCode],
            },
        },
        "tone": {
            "type": "string",
            "enum": [member.value for member in Tone],
        },
    },
    "required": ["plan_kind", "summary_code", "action_codes", "tone"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Guard + orchestration result contracts
# ---------------------------------------------------------------------------

class GuardOutcome(StrictDemoModel):
    ok: bool
    reason_code: str = Field(min_length=1, max_length=64)
    detail: str = Field(default="", max_length=200)


class LLMErrorKind(str, Enum):
    DISABLED = "disabled"
    MISSING_API_KEY = "missing_api_key"
    MISSING_MODEL = "missing_model"
    TIMEOUT = "timeout"
    NETWORK = "network"
    INVALID_JSON = "invalid_json"
    SCHEMA_INVALID = "schema_invalid"
    PROVIDER_ERROR = "provider_error"
    # Native-structured-output-specific diagnostic kinds (V1 structured-output contract).
    REFUSAL = "refusal"
    MAX_TOKENS = "max_tokens"


class GenerationOutcomeKind(str, Enum):
    LLM_ACCEPTED = "llm_accepted"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class DemoGenerationResult(StrictDemoModel):
    """Internal orchestration result before mapping to the public API shape."""

    outcome: GenerationOutcomeKind
    summary: str
    next_steps: list[str] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list)
    used_source_ids: list[str] = Field(default_factory=list)
    reason_code: str = Field(min_length=1, max_length=64)
    llm_error_kind: LLMErrorKind | None = None
    provider_calls: int = Field(default=0, ge=0)
    plan_kind: PlanKind | None = None


__all__ = [
    "ActionCode",
    "ApprovedAuthority",
    "DEMO_RESPONSE_PLAN_JSON_SCHEMA",
    "DemoGenerationResult",
    "DemoGenerationRoute",
    "DemoIssueType",
    "DemoResponsePlan",
    "DemoRoute",
    "DemoScenario",
    "GenerationMode",
    "GenerationOutcomeKind",
    "GuardOutcome",
    "LLMErrorKind",
    "LLMPlanRequest",
    "LLM_ROUTES",
    "PlanKind",
    "StrictDemoModel",
    "SummaryCode",
    "Tone",
    "TrustedFactView",
]
