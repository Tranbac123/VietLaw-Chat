"""Deeply immutable value objects for the pure Gate A3a kernel."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Iterable, Literal, Mapping

from ..contracts.internal import Decision, Domain, RiskLevel, VersionStamps
from .safety_registry import (
    CONCEPT_ATOM_RULE_IDS,
    INTENT_OPERATOR_IDS,
    MATCHED_RULE_IDS,
    OPERATOR_RULE_IDS,
    SAFETY_REASON_CODES,
    SAFE_CONTEXT_RULES,
    harm_rule_for_id,
    risk_rule_for_id,
)

DomainStatus = Literal["supported", "ambiguous", "unsupported"]
ContextProvenance = Literal["current_turn", "prior_assistant"]
SafetyIntentMode = Literal[
    "DIRECT_HARM_ASSISTANCE",
    "LAWFUL_COMPLIANCE",
    "VICTIM_OR_REPORTING",
    "PREVENTION_OR_PROTECTION",
    "DESCRIPTIVE_OR_QUOTED",
    "AMBIGUOUS",
    "NEUTRAL",
]
_RISK_LEVELS = ("low", "medium", "high")


class SafetyDisposition(str, Enum):
    PROVEN_DIRECT_HARM = "proven_direct_harm"
    SAFETY_UNCERTAIN = "safety_uncertain"
    CLEAR = "clear"


class RiskDisposition(str, Enum):
    HIGH_RISK = "high_risk"
    NORMAL = "normal"


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


# Registry order is the sole canonical provenance order.  Safe-context IDs also
# occur in the operator registry, so deduplication is explicit and stable.
CONTAINMENT_SIGNAL_ID_ORDER = _ordered_unique(
    MATCHED_RULE_IDS
    + SAFE_CONTEXT_RULES
    + CONCEPT_ATOM_RULE_IDS
    + OPERATOR_RULE_IDS
    + INTENT_OPERATOR_IDS
)
CONTAINMENT_REASON_CODE_ORDER = (
    "CONTAINMENT_PROVEN_DIRECT_HARM",
    "CONTAINMENT_SAFETY_UNCERTAIN",
    "CONTAINMENT_CLEAR",
    "CONTAINMENT_UNRESOLVED_SIGNAL",
    "CONTAINMENT_HIGH_RISK",
    "CONTAINMENT_NORMAL_RISK",
)


class AnalysisInvariantError(ValueError):
    """A required kernel stage or authority invariant is invalid."""


def _strings(values: Iterable[str], field: str, *, canonical_set: bool = False) -> tuple[str, ...]:
    if isinstance(values, str):
        raise AnalysisInvariantError(f"{field} must be a collection of strings")
    result = tuple(sorted(values)) if isinstance(values, (set, frozenset)) else tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise AnalysisInvariantError(f"{field} contains an invalid string")
    return tuple(sorted(set(result))) if canonical_set else result


def _typed_tuple(values: Iterable[object], expected: type, field: str) -> tuple[object, ...]:
    if isinstance(values, (str, bytes)):
        raise AnalysisInvariantError(f"{field} must be a typed collection")
    result = (
        tuple(sorted(values, key=repr))
        if isinstance(values, (set, frozenset))
        else tuple(values)
    )
    if any(not isinstance(value, expected) for value in result):
        raise AnalysisInvariantError(f"{field} contains an invalid value")
    return result


@dataclass(frozen=True, slots=True)
class VersionSnapshot:
    contract_version: str
    corpus_version: str
    policy_version: str
    prompt_version: str
    retriever_version: str
    generator_mode: str
    generator_version: str

    @classmethod
    def capture(cls, value: VersionSnapshot | VersionStamps) -> VersionSnapshot:
        if isinstance(value, cls):
            return value
        if not isinstance(value, VersionStamps):
            raise AnalysisInvariantError("version stamps have an invalid type")
        return cls(**value.model_dump())


@dataclass(frozen=True, slots=True)
class ContextFact:
    key: str
    value: str
    provenance: ContextProvenance
    recency: int = 0

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.value.strip() or isinstance(self.recency, bool):
            raise AnalysisInvariantError("context fact is invalid")


@dataclass(frozen=True, slots=True)
class BoundedPriorContext:
    facts: tuple[ContextFact, ...] = ()
    unresolved_ambiguities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        facts = _typed_tuple(self.facts, ContextFact, "prior facts")
        object.__setattr__(
            self,
            "facts",
            tuple(
                sorted(
                    facts,
                    key=lambda fact: (-fact.recency, fact.key, fact.value, fact.provenance),
                )
            ),
        )
        object.__setattr__(self, "unresolved_ambiguities", _strings(self.unresolved_ambiguities, "ambiguities", canonical_set=True))


@dataclass(frozen=True, slots=True)
class ResolvedContext:
    current_facts: tuple[ContextFact, ...]
    supporting_facts: tuple[ContextFact, ...]
    unresolved_ambiguities: tuple[str, ...]
    conflicts: tuple[str, ...]

    def __post_init__(self) -> None:
        current_facts = _typed_tuple(self.current_facts, ContextFact, "current facts")
        object.__setattr__(
            self,
            "current_facts",
            tuple(
                sorted(
                    current_facts,
                    key=lambda fact: (fact.key, fact.value, fact.provenance, fact.recency),
                )
            ),
        )
        object.__setattr__(self, "supporting_facts", _typed_tuple(self.supporting_facts, ContextFact, "supporting facts"))
        object.__setattr__(self, "unresolved_ambiguities", _strings(self.unresolved_ambiguities, "ambiguities", canonical_set=True))
        object.__setattr__(self, "conflicts", _strings(self.conflicts, "conflicts", canonical_set=True))


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    source_id: str
    domain: Domain
    approved: bool
    title: str
    relevance_tags: tuple[str, ...]
    excerpt: str
    source_type: str
    source_version: str
    relevance_score: float
    metadata_valid: bool = True
    risk_applicability: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "relevance_tags", _strings(self.relevance_tags, "relevance tags", canonical_set=True))
        object.__setattr__(self, "risk_applicability", _strings(self.risk_applicability, "risk applicability", canonical_set=True))
        if not all(isinstance(value, str) and value.strip() for value in (self.source_id, self.title, self.excerpt, self.source_type, self.source_version)):
            raise AnalysisInvariantError("evidence candidate text metadata is invalid")
        if not isinstance(self.approved, bool) or not isinstance(self.metadata_valid, bool):
            raise AnalysisInvariantError("evidence candidate flags are invalid")
        if isinstance(self.relevance_score, bool) or not isinstance(self.relevance_score, (int, float)) or not isfinite(float(self.relevance_score)):
            raise AnalysisInvariantError("evidence relevance score is invalid")

    def authority_signature(self) -> tuple[object, ...]:
        return (
            self.source_id,
            self.approved,
            self.domain,
            self.source_type,
            self.title,
            self.excerpt,
            self.relevance_tags,
            self.metadata_valid,
            self.source_version,
            float(self.relevance_score),
            self.risk_applicability,
        )


@dataclass(frozen=True, slots=True)
class AnalysisInput:
    current_question: str
    bounded_context: BoundedPriorContext
    evidence_candidates: tuple[EvidenceCandidate, ...]
    version_stamps: VersionSnapshot
    current_facts: tuple[ContextFact, ...] = ()
    language: str = "vi"
    identity_references: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.current_question, str) or not isinstance(self.bounded_context, BoundedPriorContext):
            raise AnalysisInvariantError("analysis input is invalid")
        candidates = _typed_tuple(
            self.evidence_candidates,
            EvidenceCandidate,
            "evidence candidates",
        )
        object.__setattr__(
            self,
            "evidence_candidates",
            tuple(sorted(candidates, key=EvidenceCandidate.authority_signature)),
        )
        object.__setattr__(self, "current_facts", _typed_tuple(self.current_facts, ContextFact, "current facts"))
        object.__setattr__(self, "version_stamps", VersionSnapshot.capture(self.version_stamps))
        references = self.identity_references
        if isinstance(references, Mapping):
            references = tuple(sorted(references.items()))
        else:
            references = tuple(references)
        if any(not isinstance(item, tuple) or len(item) != 2 or not all(isinstance(part, str) and part for part in item) for item in references):
            raise AnalysisInvariantError("identity references are invalid")
        object.__setattr__(self, "identity_references", tuple(sorted(references)))


@dataclass(frozen=True, slots=True)
class DomainAssessment:
    domain: Domain
    status: DomainStatus
    facts_sufficient: bool
    matched_rule_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "matched_rule_ids", _strings(self.matched_rule_ids, "domain rules"))


@dataclass(frozen=True, slots=True)
class FactCompleteness:
    complete: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_codes", _strings(self.reason_codes, "fact completeness reasons"))


@dataclass(frozen=True, slots=True)
class SafetyAssessment:
    risk_level: RiskLevel
    reason_codes: tuple[str, ...]
    unsafe_request: bool
    high_risk: bool
    matched_rule_ids: tuple[str, ...]
    explanation_codes: tuple[str, ...]
    intent_mode: SafetyIntentMode = "NEUTRAL"
    safe_context_rule_ids: tuple[str, ...] = ()
    needs_intent_clarification: bool = False

    def __post_init__(self) -> None:
        for field, values in (
            ("safety reasons", self.reason_codes),
            ("safety rules", self.matched_rule_ids),
            ("safety explanations", self.explanation_codes),
            ("safe-context rules", self.safe_context_rule_ids),
        ):
            if not isinstance(values, tuple):
                raise AnalysisInvariantError(f"{field} must be an immutable tuple")
        reason_codes = _strings(self.reason_codes, "safety reasons")
        matched_rule_ids = _strings(self.matched_rule_ids, "safety rules")
        explanation_codes = _strings(self.explanation_codes, "safety explanations")
        safe_context_rule_ids = _strings(
            self.safe_context_rule_ids,
            "safe-context rules",
        )
        object.__setattr__(self, "reason_codes", reason_codes)
        object.__setattr__(self, "matched_rule_ids", matched_rule_ids)
        object.__setattr__(self, "explanation_codes", explanation_codes)
        object.__setattr__(self, "safe_context_rule_ids", safe_context_rule_ids)
        if self.risk_level not in _RISK_LEVELS:
            raise AnalysisInvariantError("safety risk level is invalid")
        if self.intent_mode not in {
            "DIRECT_HARM_ASSISTANCE",
            "LAWFUL_COMPLIANCE",
            "VICTIM_OR_REPORTING",
            "PREVENTION_OR_PROTECTION",
            "DESCRIPTIVE_OR_QUOTED",
            "AMBIGUOUS",
            "NEUTRAL",
        }:
            raise AnalysisInvariantError("safety intent mode is invalid")
        if not all(
            isinstance(value, bool)
            for value in (self.unsafe_request, self.high_risk, self.needs_intent_clarification)
        ):
            raise AnalysisInvariantError("safety flags are invalid")
        for field, values in (
            ("safety reasons", reason_codes),
            ("safety rules", matched_rule_ids),
            ("safety explanations", explanation_codes),
            ("safe-context rules", safe_context_rule_ids),
        ):
            if len(values) != len(set(values)):
                raise AnalysisInvariantError(f"{field} must be canonical and unique")
        if any(reason not in SAFETY_REASON_CODES for reason in reason_codes):
            raise AnalysisInvariantError("safety reason code is invalid")
        if explanation_codes != reason_codes:
            raise AnalysisInvariantError("safety explanations must equal reasons")
        if any(rule_id not in MATCHED_RULE_IDS for rule_id in matched_rule_ids):
            raise AnalysisInvariantError("safety rule ID is invalid")
        if any(rule_id not in SAFE_CONTEXT_RULES for rule_id in safe_context_rule_ids):
            raise AnalysisInvariantError("safe-context rule ID is invalid")
        canonical_matched = tuple(
            rule_id for rule_id in MATCHED_RULE_IDS if rule_id in matched_rule_ids
        )
        canonical_safe = tuple(
            rule_id for rule_id in SAFE_CONTEXT_RULES if rule_id in safe_context_rule_ids
        )
        if matched_rule_ids != canonical_matched or safe_context_rule_ids != canonical_safe:
            raise AnalysisInvariantError("safety rule IDs are not in canonical order")
        expected_reasons: list[str] = []
        for rule_id in matched_rule_ids:
            harm_rule = harm_rule_for_id(rule_id)
            risk_rule = risk_rule_for_id(rule_id)
            reason = (
                harm_rule.reason_code
                if harm_rule is not None
                else risk_rule.reason_code
                if risk_rule is not None
                else ""
            )
            if reason not in expected_reasons:
                expected_reasons.append(reason)
        if reason_codes != tuple(expected_reasons):
            raise AnalysisInvariantError("safety reasons do not match registered rules")
        harm_reasons = tuple(
            reason for reason in reason_codes if reason.startswith("HARM_")
        )
        risk_reasons = tuple(
            reason for reason in reason_codes if reason.startswith("RISK_")
        )
        if self.unsafe_request:
            if (
                self.intent_mode != "DIRECT_HARM_ASSISTANCE"
                or not harm_reasons
                or risk_reasons
                or not matched_rule_ids
                or self.risk_level != "high"
                or self.needs_intent_clarification
                or safe_context_rule_ids
            ):
                raise AnalysisInvariantError("unsafe safety fields are incompatible")
        elif self.intent_mode == "DIRECT_HARM_ASSISTANCE":
            raise AnalysisInvariantError("direct harm intent must be unsafe")
        if self.intent_mode == "AMBIGUOUS":
            if (
                self.unsafe_request
                or self.high_risk
                or self.risk_level != "medium"
                or reason_codes
                or matched_rule_ids
                or not self.needs_intent_clarification
            ):
                raise AnalysisInvariantError("ambiguous safety fields are incompatible")
        elif self.needs_intent_clarification:
            raise AnalysisInvariantError("clarification flag requires ambiguous intent")
        if self.high_risk and not self.unsafe_request:
            if (
                self.risk_level != "high"
                or not risk_reasons
                or harm_reasons
                or not matched_rule_ids
            ):
                raise AnalysisInvariantError("high-risk safety fields are incompatible")
        if not self.unsafe_request and not self.high_risk and self.intent_mode != "AMBIGUOUS":
            if self.risk_level != "low" or reason_codes or matched_rule_ids:
                raise AnalysisInvariantError("low-risk safety fields are incompatible")


@dataclass(frozen=True, slots=True)
class SafetyContainmentResult:
    safety_disposition: SafetyDisposition
    risk_disposition: RiskDisposition
    signal_ids: tuple[str, ...]
    unresolved_signal_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.safety_disposition, SafetyDisposition):
            raise AnalysisInvariantError("containment safety disposition is invalid")
        if not isinstance(self.risk_disposition, RiskDisposition):
            raise AnalysisInvariantError("containment risk disposition is invalid")
        for field, values in (
            ("containment signals", self.signal_ids),
            ("containment unresolved signals", self.unresolved_signal_ids),
            ("containment reasons", self.reason_codes),
        ):
            if not isinstance(values, tuple):
                raise AnalysisInvariantError(f"{field} must be an immutable tuple")
            _strings(values, field)
            if len(values) != len(set(values)):
                raise AnalysisInvariantError(f"{field} must be canonical and unique")
        if any(value not in CONTAINMENT_SIGNAL_ID_ORDER for value in self.signal_ids):
            raise AnalysisInvariantError("containment signal ID is invalid")
        if any(
            value not in CONTAINMENT_SIGNAL_ID_ORDER
            for value in self.unresolved_signal_ids
        ):
            raise AnalysisInvariantError("containment unresolved signal ID is invalid")
        if any(value not in CONTAINMENT_REASON_CODE_ORDER for value in self.reason_codes):
            raise AnalysisInvariantError("containment reason code is invalid")
        canonical_signals = tuple(
            value for value in CONTAINMENT_SIGNAL_ID_ORDER if value in self.signal_ids
        )
        canonical_unresolved = tuple(
            value
            for value in CONTAINMENT_SIGNAL_ID_ORDER
            if value in self.unresolved_signal_ids
        )
        canonical_reasons = tuple(
            value for value in CONTAINMENT_REASON_CODE_ORDER if value in self.reason_codes
        )
        if (
            self.signal_ids != canonical_signals
            or self.unresolved_signal_ids != canonical_unresolved
            or self.reason_codes != canonical_reasons
        ):
            raise AnalysisInvariantError("containment fields are not in canonical order")
        if not set(self.unresolved_signal_ids).issubset(self.signal_ids):
            raise AnalysisInvariantError("unresolved containment signal is not observed")
        expected_safety_reason = {
            SafetyDisposition.PROVEN_DIRECT_HARM: "CONTAINMENT_PROVEN_DIRECT_HARM",
            SafetyDisposition.SAFETY_UNCERTAIN: "CONTAINMENT_SAFETY_UNCERTAIN",
            SafetyDisposition.CLEAR: "CONTAINMENT_CLEAR",
        }[self.safety_disposition]
        expected_risk_reason = {
            RiskDisposition.HIGH_RISK: "CONTAINMENT_HIGH_RISK",
            RiskDisposition.NORMAL: "CONTAINMENT_NORMAL_RISK",
        }[self.risk_disposition]
        expected_reason_set = {expected_safety_reason, expected_risk_reason}
        if self.unresolved_signal_ids:
            expected_reason_set.add("CONTAINMENT_UNRESOLVED_SIGNAL")
        expected_reasons = tuple(
            value
            for value in CONTAINMENT_REASON_CODE_ORDER
            if value in expected_reason_set
        )
        if self.reason_codes != expected_reasons:
            raise AnalysisInvariantError("containment reasons are incompatible")
        if (
            self.safety_disposition is SafetyDisposition.SAFETY_UNCERTAIN
            and not self.unresolved_signal_ids
        ):
            raise AnalysisInvariantError("safety uncertainty requires an unresolved signal")
        if (
            self.safety_disposition is SafetyDisposition.CLEAR
            and self.unresolved_signal_ids
        ):
            raise AnalysisInvariantError("clear containment has unresolved signals")


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    domain: Domain
    risk_level: RiskLevel
    decision: Decision
    reason_codes: tuple[str, ...]
    facts_sufficient: bool
    evidence_available: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_codes", _strings(self.reason_codes, "decision reasons"))


@dataclass(frozen=True, slots=True)
class EvidencePlan:
    required_categories: tuple[str, ...]
    optional_categories: tuple[str, ...]
    sources_allowed: bool
    evidence_required: bool
    compatible_domain: Domain
    maximum_sources: int
    rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_categories", _strings(self.required_categories, "required evidence categories"))
        object.__setattr__(self, "optional_categories", _strings(self.optional_categories, "optional evidence categories"))
        object.__setattr__(self, "rationale_codes", _strings(self.rationale_codes, "evidence rationale"))
        if isinstance(self.maximum_sources, bool) or self.maximum_sources < 0:
            raise AnalysisInvariantError("maximum sources is invalid")


@dataclass(frozen=True, slots=True)
class RejectedEvidence:
    candidate: EvidenceCandidate
    reason_code: str


@dataclass(frozen=True, slots=True)
class EvidenceResult:
    admitted: tuple[EvidenceCandidate, ...]
    rejected: tuple[RejectedEvidence, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "admitted", _typed_tuple(self.admitted, EvidenceCandidate, "admitted evidence"))
        object.__setattr__(self, "rejected", _typed_tuple(self.rejected, RejectedEvidence, "rejected evidence"))


@dataclass(frozen=True, slots=True)
class PlanPoint:
    point_id: str
    slot: str
    semantic_instruction: str
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_ids", _strings(self.source_ids, "point source IDs"))


@dataclass(frozen=True, slots=True)
class StructuredAnswerPlan:
    summary: tuple[str, ...]
    clarifying_questions: tuple[str, ...]
    checklist: tuple[str, ...]
    next_steps: tuple[str, ...]
    safe_alternative: tuple[str, ...]
    escalation_notice: tuple[str, ...]
    admitted_source_ids: tuple[str, ...]
    ordered_points: tuple[PlanPoint, ...]

    def __post_init__(self) -> None:
        for field in ("summary", "clarifying_questions", "checklist", "next_steps", "safe_alternative", "escalation_notice", "admitted_source_ids"):
            object.__setattr__(self, field, _strings(getattr(self, field), field))
        object.__setattr__(self, "ordered_points", _typed_tuple(self.ordered_points, PlanPoint, "answer plan points"))


@dataclass(frozen=True, slots=True)
class ConfidenceResult:
    domain: float
    risk: float
    answer: float
    factors: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "factors", _strings(self.factors, "confidence factors"))


@dataclass(frozen=True, slots=True)
class AnalysisState:
    original_input: AnalysisInput
    raw_current_question: str
    normalized_question: str
    resolved_context: ResolvedContext
    domain: DomainAssessment
    fact_completeness: FactCompleteness
    safety: SafetyAssessment
    safety_containment: SafetyContainmentResult
    evidence_plan: EvidencePlan
    evidence: EvidenceResult
    decision: DecisionRecord
    answer_plan: StructuredAnswerPlan
    confidence: ConfidenceResult
    completed_stages: tuple[str, ...]
    version_stamps: VersionSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.original_input, AnalysisInput):
            raise AnalysisInvariantError("original input is not canonical")
        object.__setattr__(self, "completed_stages", _strings(self.completed_stages, "stage markers"))
        object.__setattr__(self, "version_stamps", VersionSnapshot.capture(self.version_stamps))


__all__ = [
    "AnalysisInput", "AnalysisInvariantError", "AnalysisState", "BoundedPriorContext",
    "ConfidenceResult", "ContextFact", "DecisionRecord", "DomainAssessment",
    "EvidenceCandidate", "EvidencePlan", "EvidenceResult", "FactCompleteness",
    "PlanPoint", "RejectedEvidence", "ResolvedContext", "SafetyAssessment",
    "RiskDisposition", "SafetyContainmentResult", "SafetyDisposition",
    "SafetyIntentMode",
    "StructuredAnswerPlan", "VersionSnapshot",
]
