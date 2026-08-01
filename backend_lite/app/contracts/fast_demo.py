"""FAST DEMO V2 contracts: bounded state, model plan, and the wire JSON schema.

Scope note: this is the 48-hour *video* path, deliberately narrower than the
post-demo hardened architecture (no normalized episode/fact/event tables, no
separate interpretation call, no question graph). Everything here is designed
to be deleted in one piece once the hardened architecture lands.

Two invariants are load-bearing and enforced elsewhere but stated here because
the types encode them:

  * ``FastDemoState`` is the authority for previously accepted facts. Chat
    history is context only (see ``fast_demo_prompt``).
  * ``FastDemoPlan.fact_updates`` are *proposals*. The model never writes state;
    every proposal is re-validated against the current user message by
    ``fast_demo_fact_validation`` before it can touch ``FastDemoState``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

STATE_SCHEMA_VERSION = "fast_demo_state_v1"
ISSUE_TYPE_RENTAL_DEPOSIT = "rental_deposit"

# Bounded output limits. Also mirrored into the wire JSON schema below so the
# provider itself is constrained, not just the local validator.
MAX_SUMMARY = 1200
MAX_ANALYSIS = 1600
MAX_LIST_ITEMS = 6
MAX_LIST_ITEM = 400
MAX_DRAFT_BODY = 2000
MAX_FACT_UPDATES = 8
MAX_SOURCE_IDS = 3
MAX_RECENT_REQUESTS = 8

TriState = Literal["present", "absent", "unknown"]

# MODE_2D correction (M-01): a matured refusal/nonperformance conclusion is a
# distinct legal question from the generic tri-state "is the property handed
# over / is the deposit returned" facts -- neither of those, by itself,
# establishes that the receiving party refused or failed a due obligation.
# Kept as its own three-value type (not TriState's present/absent) so the
# field name and its values stay self-describing at every call site, rather
# than overloading "present"/"absent" to mean something slot-specific here.
NonperformanceStatus = Literal["unknown", "confirmed", "not_confirmed"]
RECEIVING_PARTY_NONPERFORMANCE_SLOT = "receiving_party_nonperformance_status"

ResponseMode = Literal[
    "acknowledge",
    "clarify",
    "guidance",
    "checklist",
    "next_steps",
    "draft",
    "correction",
    "redraft",
]

FactOperation = Literal["set", "affirm", "negate", "correct", "retract"]

# Narrow rental-deposit allowlist. A slot outside this set is rejected outright;
# the model can never invent a slot name.
TRI_STATE_SLOTS: frozenset[str] = frozenset(
    {
        "written_deposit_agreement_status",
        "payment_evidence_status",
        "rental_contract_status",
        "property_handover_status",
        "deposit_returned_status",
        "written_refund_request_status",
        "landlord_response_status",
    }
)

ALLOWED_SLOTS: frozenset[str] = TRI_STATE_SLOTS | {
    "deposit_amount",
    "deposit_currency",
    "payment_evidence_types",
    "landlord_refusal_reason",
    "user_goal",
    RECEIVING_PARTY_NONPERFORMANCE_SLOT,
}

ALLOWED_EVIDENCE_TYPES: frozenset[str] = frozenset(
    {"bank_transfer", "receipt", "message", "witness", "other"}
)

ALLOWED_USER_GOALS: frozenset[str] = frozenset(
    {"recover_deposit", "understand_rights", "prepare_evidence", "draft_message", "unknown"}
)


class DepositAmount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int = Field(ge=0)
    currency: str = "VND"
    status: TriState = "present"
    original_quote: str = ""


class FastDemoFacts(BaseModel):
    """Accepted facts only. ``unknown`` means 'no accepted answer', which is
    deliberately distinct from ``absent`` ('user confirmed it does not exist')."""

    model_config = ConfigDict(extra="forbid")

    deposit_amount: DepositAmount | None = None
    deposit_currency: str | None = None
    written_deposit_agreement_status: TriState = "unknown"
    payment_evidence_status: TriState = "unknown"
    payment_evidence_types: list[str] = Field(default_factory=list)
    rental_contract_status: TriState = "unknown"
    property_handover_status: TriState = "unknown"
    deposit_returned_status: TriState = "unknown"
    written_refund_request_status: TriState = "unknown"
    landlord_response_status: TriState = "unknown"
    landlord_refusal_reason: str | None = None
    # MODE_2D (M-01): whether the receiving party's refusal or matured
    # nonperformance is established -- resolved only from a bounded evidence
    # allowlist (see fast_demo_fact_validation.infer_receiving_party_
    # nonperformance), never from generic tri-state polarity or from the
    # model's bare operation flag.
    receiving_party_nonperformance_status: NonperformanceStatus = "unknown"


class DraftRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    body: str = ""


#: A pending question may only ever concern an allowlisted slot, or be generic.
#: The identity is never derived by parsing assistant prose.
PENDING_QUESTION_GENERAL = "general"
ALLOWED_PENDING_QUESTION_IDS: frozenset[str] = TRI_STATE_SLOTS | {
    "deposit_amount",
    "landlord_refusal_reason",
    "user_goal",
    PENDING_QUESTION_GENERAL,
}

#: Bounded so a pending record can never become a store of arbitrary prose.
MAX_PENDING_QUESTION_TEXT = 300
#: Assistant message ids are repository-generated (`msg_asst_<32 hex>`); the cap
#: is generous but finite so the field cannot become free text.
MAX_PENDING_MESSAGE_ID = 128

#: Which accepted fact slot answers which pending question. A slot-backed
#: question resolves ONLY when its expected slot was actually applied, so a
#: rejected update (unverifiable evidence, bad value, wrong slot, CAS conflict)
#: leaves the question outstanding instead of silently closing it.
#:
#: `general` is deliberately absent: there is no slot that proves a general
#: question was answered, so it is preserved rather than guessed.
PENDING_QUESTION_EXPECTED_SLOT: dict[str, str] = {
    "written_deposit_agreement_status": "written_deposit_agreement_status",
    "payment_evidence_status": "payment_evidence_status",
    "rental_contract_status": "rental_contract_status",
    "property_handover_status": "property_handover_status",
    "deposit_returned_status": "deposit_returned_status",
    "written_refund_request_status": "written_refund_request_status",
    "landlord_response_status": "landlord_response_status",
    "deposit_amount": "deposit_amount",
    "landlord_refusal_reason": "landlord_refusal_reason",
    "user_goal": "user_goal",
}


class PendingClarification(BaseModel):
    """One outstanding structured clarifying question.

    Persisted in the fast-demo state rather than re-derived from message
    history, because the history heuristic ("any newer user turn answered it")
    wrongly treated a greeting or a thank-you as an answer. Being state, it also
    transitions under the same compare-and-swap as the facts it relates to.

    It records only *that* a question is outstanding and which allowlisted slot
    it concerns. It never carries a fact value: facts change exclusively through
    the verified current-message fact-update contract.
    """

    model_config = ConfigDict(extra="forbid")

    question_id: str = PENDING_QUESTION_GENERAL
    question_text: str = Field(default="", max_length=MAX_PENDING_QUESTION_TEXT)
    #: Must name a real assistant turn: a pending record with no provenance
    #: could never be audited back to the question that created it.
    created_by_assistant_message_id: str = Field(
        min_length=1, max_length=MAX_PENDING_MESSAGE_ID
    )
    created_at_state_version: int = Field(ge=0)
    status: Literal["pending"] = "pending"

    @field_validator("question_id")
    @classmethod
    def _known_question_id(cls, value: str) -> str:
        if value not in ALLOWED_PENDING_QUESTION_IDS:
            raise ValueError(f"unknown pending question_id: {value}")
        return value

    @field_validator("created_by_assistant_message_id")
    @classmethod
    def _message_id_shape(cls, value: str) -> str:
        # Same shape the runtime mints. Keeps model- or user-supplied strings
        # from becoming state authority.
        if not value.startswith("msg_asst_"):
            raise ValueError("created_by_assistant_message_id must be an assistant message id")
        return value

    @property
    def expected_slot(self) -> str | None:
        """The fact slot whose acceptance proves this question was answered."""

        return PENDING_QUESTION_EXPECTED_SLOT.get(self.question_id)


class FastDemoState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = STATE_SCHEMA_VERSION
    issue_type: str = ISSUE_TYPE_RENTAL_DEPOSIT
    facts: FastDemoFacts = Field(default_factory=FastDemoFacts)
    user_goal: str | None = None
    last_draft: DraftRecord | None = None
    last_response_mode: str | None = None
    #: Outstanding structured clarification, or None. Survives social and
    #: capability turns because those routes commit no state at all.
    pending_clarification: PendingClarification | None = None
    # Bounded correction history. Deliberately not a normalized provenance
    # chain -- that is post-demo work.
    previous_values: dict[str, list[Any]] = Field(default_factory=dict)


class RecentRequestRecord(BaseModel):
    """One committed turn, used as the single source of truth for fast-demo
    request deduplication. Bounded content only: never prompts, provider
    payloads, credentials or tracebacks."""

    model_config = ConfigDict(extra="forbid")

    client_request_id: str
    response_json: dict[str, Any]
    applied_state_version: int


class FactUpdateProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: FactOperation
    slot: str
    value: Any = None
    evidence_quote: str = ""


class DraftProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=MAX_DRAFT_BODY)


class FastDemoPlan(BaseModel):
    """The single structured output of the one legal-turn provider call.

    Unlike the post-demo architecture, the model *is* allowed to write visible
    prose here (owner decision for the video). It is still never allowed to
    write state, choose source metadata, or emit a source ID outside the pack
    it was given.
    """

    model_config = ConfigDict(extra="forbid")

    response_kind: Literal["legal"] = "legal"
    response_mode: ResponseMode
    summary: str = Field(max_length=MAX_SUMMARY)
    analysis: str | None = Field(default=None, max_length=MAX_ANALYSIS)
    clarifying_questions: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    checklist: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    next_steps: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    draft: DraftProposal | None = None
    known_facts_summary: list[str] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    uncertainty_notice: str | None = Field(default=None, max_length=600)
    fact_updates: list[FactUpdateProposal] = Field(default_factory=list, max_length=MAX_FACT_UPDATES)
    selected_source_ids: list[str] = Field(default_factory=list, max_length=MAX_SOURCE_IDS)


def _str(max_length: int) -> dict:
    return {"type": "string", "maxLength": max_length}


def _list(max_items: int, item_max: int) -> dict:
    return {"type": "array", "maxItems": max_items, "items": _str(item_max)}


# Wire schema for Anthropic native Structured Outputs. Kept in lockstep with
# FastDemoPlan; local Pydantic validation still runs on the returned text.
FAST_DEMO_PLAN_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["response_kind", "response_mode", "summary"],
    "properties": {
        "response_kind": {"type": "string", "enum": ["legal"]},
        "response_mode": {
            "type": "string",
            "enum": [
                "acknowledge", "clarify", "guidance", "checklist",
                "next_steps", "draft", "correction", "redraft",
            ],
        },
        "summary": _str(MAX_SUMMARY),
        "analysis": {"type": ["string", "null"], "maxLength": MAX_ANALYSIS},
        "clarifying_questions": _list(MAX_LIST_ITEMS, MAX_LIST_ITEM),
        "checklist": _list(MAX_LIST_ITEMS, MAX_LIST_ITEM),
        "next_steps": _list(MAX_LIST_ITEMS, MAX_LIST_ITEM),
        "draft": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["title", "body"],
            "properties": {"title": _str(200), "body": _str(MAX_DRAFT_BODY)},
        },
        "known_facts_summary": _list(MAX_LIST_ITEMS, MAX_LIST_ITEM),
        "uncertainty_notice": {"type": ["string", "null"], "maxLength": 600},
        "fact_updates": {
            "type": "array",
            "maxItems": MAX_FACT_UPDATES,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["operation", "slot", "evidence_quote"],
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["set", "affirm", "negate", "correct", "retract"],
                    },
                    "slot": {"type": "string", "enum": sorted(ALLOWED_SLOTS)},
                    "value": {
                        "type": ["string", "number", "boolean", "array", "null"],
                        "items": {"type": "string"},
                    },
                    "evidence_quote": _str(400),
                },
            },
        },
        "selected_source_ids": {
            "type": "array",
            "maxItems": MAX_SOURCE_IDS,
            "items": _str(64),
        },
    },
}


__all__ = [
    "ALLOWED_EVIDENCE_TYPES",
    "ALLOWED_SLOTS",
    "ALLOWED_USER_GOALS",
    "DepositAmount",
    "DraftProposal",
    "DraftRecord",
    "FAST_DEMO_PLAN_JSON_SCHEMA",
    "FactOperation",
    "FactUpdateProposal",
    "FastDemoFacts",
    "FastDemoPlan",
    "FastDemoState",
    "ISSUE_TYPE_RENTAL_DEPOSIT",
    "MAX_RECENT_REQUESTS",
    "RecentRequestRecord",
    "ResponseMode",
    "STATE_SCHEMA_VERSION",
    "TRI_STATE_SLOTS",
    "TriState",
]
