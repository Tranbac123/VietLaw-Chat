"""Request-scoped in-memory state for the planned Gate A pipeline."""

from __future__ import annotations

from pydantic import Field

from .internal import (
    AnswerDraft,
    AnswerPlan,
    DecisionResult,
    EvidenceBundle,
    GuardResults,
    MinimalConversationContext,
    NormalizedInput,
    RawInput,
    RequestIdentity,
    RetrievalResult,
    RouteCandidate,
    SafetyResult,
    StageTrace,
    StoredResponse,
    StrictModel,
    VersionStamps,
)


class AnalysisState(StrictModel):
    request_identity: RequestIdentity
    raw_input: RawInput
    normalized_input: NormalizedInput | None = None
    conversation_context: MinimalConversationContext | None = None
    safety_result: SafetyResult | None = None
    route_candidates: list[RouteCandidate] = Field(default_factory=list)
    retrieval_results: RetrievalResult | None = None
    evidence_bundle: EvidenceBundle | None = None
    decision: DecisionResult | None = None
    answer_plan: AnswerPlan | None = None
    generated_draft: AnswerDraft | None = None
    guard_results: GuardResults | None = None
    final_response: StoredResponse | None = None
    version_stamps: VersionStamps
    trace: list[StageTrace] = Field(default_factory=list)


__all__ = ["AnalysisState"]
