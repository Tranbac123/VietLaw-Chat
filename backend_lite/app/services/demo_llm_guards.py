"""DEMO structured-plan validation.

Because the model now returns ONLY an enum :class:`DemoResponsePlan` (no
user-visible free text), release safety is STRUCTURAL: enum-only output +
`extra="forbid"` + backend-owned rendering + trusted captured facts + backend
Source metadata. The old free-text guards (source-prose / certainty /
fact-reversal scanners) are therefore no longer part of the active flow and have
been removed; there is no model prose left to scan.

This module only parses the model plan and supplies a deterministic default plan
when the model output is invalid.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from ..contracts.demo_llm import (
    ActionCode,
    DemoResponsePlan,
    GenerationMode,
    GuardOutcome,
    PlanKind,
    SummaryCode,
    Tone,
)


def parse_demo_plan(raw: str) -> tuple[DemoResponsePlan | None, GuardOutcome]:
    """Strictly parse provider text into the enum plan, or return an error."""

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, GuardOutcome(ok=False, reason_code="demo.plan.invalid_json.v1")
    if not isinstance(data, dict):
        return None, GuardOutcome(ok=False, reason_code="demo.plan.invalid_json.v1", detail="non-object")
    try:
        plan = DemoResponsePlan.model_validate(data)
    except ValidationError:
        # Any arbitrary string field, extra field, or unknown enum lands here.
        return None, GuardOutcome(ok=False, reason_code="demo.plan.schema_invalid.v1")
    return plan, GuardOutcome(ok=True, reason_code="demo.plan.ok.v1")


def default_plan(mode: GenerationMode) -> DemoResponsePlan:
    """Deterministic safe default used when the model plan is invalid/unavailable."""

    if mode == "document_drafting":
        return DemoResponsePlan(
            plan_kind=PlanKind.DRAFT_REQUEST,
            summary_code=SummaryCode.DEPOSIT_NOT_RETURNED,
            action_codes=[],
            tone=Tone.POLITE_FIRM,
        )
    return DemoResponsePlan(
        plan_kind=PlanKind.LEGAL_GUIDANCE,
        summary_code=SummaryCode.DEPOSIT_NOT_RETURNED,
        action_codes=[ActionCode.SEND_WRITTEN_REFUND_REQUEST, ActionCode.PRESERVE_PAYMENT_EVIDENCE],
        tone=Tone.NEUTRAL,
    )


__all__ = ["default_plan", "parse_demo_plan"]
