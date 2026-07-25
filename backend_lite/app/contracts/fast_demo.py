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

from pydantic import BaseModel, ConfigDict, Field

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


class DraftRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    body: str = ""


class FastDemoState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = STATE_SCHEMA_VERSION
    issue_type: str = ISSUE_TYPE_RENTAL_DEPOSIT
    facts: FastDemoFacts = Field(default_factory=FastDemoFacts)
    user_goal: str | None = None
    last_draft: DraftRecord | None = None
    last_response_mode: str | None = None
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
