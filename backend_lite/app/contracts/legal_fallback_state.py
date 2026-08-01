"""VietLaw Public Beta V0: per-chat state for the legal-fallback vertical.

Task §8 requires three things NOT be conflated in one untyped memory field:
user-reported fact, retrieved legal proposition, and model-generated
explanation. This module keeps them as three distinct typed fields on one
state object, mirroring `contracts/fast_demo.py::FastDemoState`'s shape
without extending or importing it (that model is frozen and deposit-shaped).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .legal_trust import EvidenceOutcome
from .traffic import TrafficFacts


class RetrievedEvidenceRecord(BaseModel):
    """A RETRIEVED LEGAL PROPOSITION -- never a user-reported fact, and never
    stored as if the model's explanation of it were itself authoritative.
    Kept only for continuity/observability across turns in the same chat;
    it is re-derived (never assumed still valid) on every new official-
    search attempt."""

    model_config = ConfigDict(extra="forbid")

    query_text: str
    outcome: EvidenceOutcome
    retrieved_at: str
    document_number: str | None = None
    document_name: str | None = None


class LegalFallbackState(BaseModel):
    """Per-chat state for the legal-fallback vertical. `extra="forbid"` so an
    unrecognized field fails loudly rather than silently vanishing.

    `traffic_facts`/`traffic_topic_id` are USER-REPORTED facts, status-typed
    the same conservative way as `TrafficFacts` itself (a slot is only ever
    `"unknown"` or an explicit value the user's own message established --
    see task §8's `unknown/reported/confirmed/not_confirmed/resolved`
    vocabulary: this bounded demo needs only the reported/unknown
    distinction `TrafficFacts` already gives per-slot, since no downstream
    legal-clause selection depends on a stronger status here the way MODE_2D
    depends on `receiving_party_nonperformance_status`).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    traffic_facts: TrafficFacts = Field(default_factory=TrafficFacts)
    traffic_topic_id: str | None = None
    #: Correction Round 1 (M-02): which single required-fact slot the last
    #: clarification question asked about (e.g. `"vehicle_type"`,
    #: `"speed_excess_kmh"`). `None` whenever no clarification is pending.
    #: A later turn may only continue `traffic_topic_id` when it is a
    #: plausible answer to THIS field (see
    #: `traffic_classifier.is_valid_clarification_answer`); otherwise the
    #: pending state is released rather than trapping an unrelated turn.
    traffic_pending_field: str | None = None
    last_retrieved_evidence: RetrievedEvidenceRecord | None = None


__all__ = ["LegalFallbackState", "RetrievedEvidenceRecord"]
