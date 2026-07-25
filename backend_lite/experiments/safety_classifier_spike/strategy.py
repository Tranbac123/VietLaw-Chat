"""Option A/B/C experiment strategies with backend-owned decision authority."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from backend_lite.app.application.safety_intent import (
    ClauseSafetyFinding,
    SafetySignals,
    analyze_safety_intent,
)

from .contract import (
    HARM_FAMILIES,
    RATIONALE_CODES,
    RISK_INDICATORS,
    SCHEMA_VERSION,
    ClassifierRequest,
    ProviderResponse,
    SafetyClassificationCandidate,
    SafetyClassifierProvider,
    SupportingSpan,
)
from .providers import ClassifierProviderError
from .validator import (
    ClassifierValidationError,
    normalize_current_question,
    validate_candidate,
)

BackendSafetyDecision = Literal[
    "REFUSE_UNSAFE_REQUEST",
    "RECOMMEND_PROFESSIONAL_HELP",
    "ASK_SAFETY_CLARIFICATION",
    "CONTINUE_DOMAIN_AND_EVIDENCE",
]
StrategyName = Literal["DETERMINISTIC", "MODEL", "HYBRID"]

_MIN_ACTIONABLE_CONFIDENCE = 0.70


@dataclass(frozen=True, slots=True)
class StrategyOutcome:
    strategy: StrategyName
    decision: BackendSafetyDecision
    candidate: SafetyClassificationCandidate | None
    classifier_called: bool
    classifier_valid: bool
    fallback_code: str | None
    latency_ms: float
    estimated_cost_usd: float | None


def backend_decision(candidate: SafetyClassificationCandidate) -> BackendSafetyDecision:
    """Convert signals to an internal action; the provider cannot set this value."""

    if candidate.intent_mode == "DIRECT_HARM_ASSISTANCE":
        return "REFUSE_UNSAFE_REQUEST"
    if candidate.risk_indicators:
        return "RECOMMEND_PROFESSIONAL_HELP"
    if candidate.abstain or candidate.intent_mode == "AMBIGUOUS":
        return "ASK_SAFETY_CLARIFICATION"
    return "CONTINUE_DOMAIN_AND_EVIDENCE"


def _rationale_for_intent(intent: str) -> tuple[str, ...]:
    mapping = {
        "DIRECT_HARM_ASSISTANCE": ("DIRECT_REQUEST",),
        "LAWFUL_COMPLIANCE": ("LAWFUL_POLICE_CONTACT",),
        "VICTIM_OR_REPORTING": ("VICTIM_REPORT",),
        "PREVENTION_OR_PROTECTION": ("PREVENTION_TARGET",),
        "DESCRIPTIVE_OR_QUOTED": ("DESCRIPTIVE_QUOTE",),
        "AMBIGUOUS": ("AMBIGUOUS_TARGET",),
        "NEUTRAL": ("INSUFFICIENT_SIGNAL",),
    }
    return mapping[intent]


def _finding_for_family(
    signals: SafetySignals,
    family: str,
) -> ClauseSafetyFinding | None:
    return next(
        (
            finding
            for finding in signals.findings
            if any(
                f"HARM_{match.family}" == family
                for match in finding.harm_concepts
            )
        ),
        None,
    )


def _deterministic_spans(signals: SafetySignals) -> tuple[SupportingSpan, ...]:
    spans: list[SupportingSpan] = []
    families = tuple(
        family
        for family in HARM_FAMILIES
        if any(
            f"HARM_{match.family}" == family
            for finding in signals.findings
            for match in finding.harm_concepts
        )
    )
    for family in families:
        finding = _finding_for_family(signals, family)
        if finding is None:
            continue
        action = next(
            (atom for atom in finding.concept_atoms if atom.kind == "action"),
            None,
        )
        target = next(
            (
                atom
                for atom in finding.concept_atoms
                if atom.kind in {"object", "objective"}
            ),
            None,
        )
        if action is not None:
            start, end = action.matched_span
            spans.append(
                SupportingSpan(start, end, finding.clause.normalized_text[
                    start - finding.clause.start_offset : end - finding.clause.start_offset
                ], "ACTION", family)  # type: ignore[arg-type]
            )
        if target is not None:
            start, end = target.matched_span
            spans.append(
                SupportingSpan(start, end, finding.clause.normalized_text[
                    start - finding.clause.start_offset : end - finding.clause.start_offset
                ], "TARGET", family)  # type: ignore[arg-type]
            )
        if finding.intent_outcome == "DIRECT_HARM_ASSISTANCE" and finding.direct_application_cues:
            cue = finding.direct_application_cues[0]
            start, end = cue.matched_span
            spans.append(
                SupportingSpan(start, end, finding.clause.normalized_text[
                    start - finding.clause.start_offset : end - finding.clause.start_offset
                ], "USER_APPLICATION", family)  # type: ignore[arg-type]
            )
    return tuple(
        sorted(
            spans,
            key=lambda span: (
                span.start,
                span.end,
                span.role,
                span.harm_family or "",
            ),
        )
    )


def deterministic_candidate(normalized_question: str) -> SafetyClassificationCandidate:
    """Adapt the existing deterministic authority without reimplementing it."""

    question = normalize_current_question(normalized_question)
    signals = analyze_safety_intent(question)
    families = tuple(
        family
        for family in HARM_FAMILIES
        if any(
            f"HARM_{match.family}" == family
            for finding in signals.findings
            for match in finding.harm_concepts
        )
    )
    relevant = next(
        (
            finding
            for finding in signals.findings
            if finding.intent_outcome == signals.intent_mode
        ),
        next((finding for finding in signals.findings if finding.harm_concepts), None),
    )
    actor = relevant.actor_orientation if relevant is not None else "UNKNOWN"
    confidence = (
        0.96
        if signals.intent_mode == "DIRECT_HARM_ASSISTANCE"
        else 0.92
        if signals.high_risk_rule_ids
        else 0.82
        if signals.intent_mode
        in {
            "LAWFUL_COMPLIANCE",
            "VICTIM_OR_REPORTING",
            "PREVENTION_OR_PROTECTION",
            "DESCRIPTIVE_OR_QUOTED",
        }
        else 0.40
        if signals.intent_mode == "AMBIGUOUS"
        else 0.60
    )
    return SafetyClassificationCandidate(
        SCHEMA_VERSION,
        signals.intent_mode,
        families,  # type: ignore[arg-type]
        actor,
        f"intent={signals.intent_mode}; harms={','.join(families) or 'NONE'}",
        tuple(
            risk
            for risk in RISK_INDICATORS
            if risk in signals.high_risk_reason_codes
        ),  # type: ignore[arg-type]
        _deterministic_spans(signals),
        confidence,
        signals.intent_mode == "AMBIGUOUS",
        tuple(
            code
            for code in RATIONALE_CODES
            if code in _rationale_for_intent(signals.intent_mode)
        ),  # type: ignore[arg-type]
    )


def run_deterministic_strategy(question: str) -> StrategyOutcome:
    candidate = deterministic_candidate(question)
    return StrategyOutcome(
        "DETERMINISTIC",
        backend_decision(candidate),
        candidate,
        False,
        True,
        None,
        0.0,
        0.0,
    )


def _safe_model_fallback(
    strategy: StrategyName,
    *,
    code: str,
    latency_ms: float = 0.0,
    cost: float | None = None,
) -> StrategyOutcome:
    return StrategyOutcome(
        strategy,
        "ASK_SAFETY_CLARIFICATION",
        None,
        True,
        False,
        code,
        latency_ms,
        cost,
    )


def _provider_candidate(
    provider: SafetyClassifierProvider,
    question: str,
) -> tuple[SafetyClassificationCandidate, ProviderResponse] | StrategyOutcome:
    normalized = normalize_current_question(question)
    try:
        response = provider.classify(ClassifierRequest(normalized))
    except ClassifierProviderError as exc:
        return _safe_model_fallback("MODEL", code=exc.code)
    except Exception:
        return _safe_model_fallback("MODEL", code="CLASSIFIER_PROVIDER_ERROR")
    if (
        isinstance(response.latency_ms, bool)
        or not isinstance(response.latency_ms, (int, float))
        or not isfinite(float(response.latency_ms))
        or response.latency_ms < 0
    ):
        return _safe_model_fallback("MODEL", code="CLASSIFIER_PROVIDER_METADATA_INVALID")
    try:
        candidate = validate_candidate(response.payload, normalized)
    except ClassifierValidationError:
        return _safe_model_fallback(
            "MODEL",
            code="CLASSIFIER_INVALID",
            latency_ms=float(response.latency_ms),
            cost=response.estimated_cost_usd,
        )
    return candidate, response


def run_model_strategy(
    question: str,
    provider: SafetyClassifierProvider,
) -> StrategyOutcome:
    result = _provider_candidate(provider, question)
    if isinstance(result, StrategyOutcome):
        return result
    candidate, response = result
    if candidate.confidence < _MIN_ACTIONABLE_CONFIDENCE:
        decision: BackendSafetyDecision = (
            "RECOMMEND_PROFESSIONAL_HELP"
            if candidate.risk_indicators
            else "ASK_SAFETY_CLARIFICATION"
        )
        return StrategyOutcome(
            "MODEL",
            decision,
            candidate,
            True,
            True,
            "CLASSIFIER_LOW_CONFIDENCE",
            float(response.latency_ms),
            response.estimated_cost_usd,
        )
    return StrategyOutcome(
        "MODEL",
        backend_decision(candidate),
        candidate,
        True,
        True,
        None,
        float(response.latency_ms),
        response.estimated_cost_usd,
    )


def deterministic_is_uncertain(question: str) -> bool:
    signals = analyze_safety_intent(normalize_current_question(question))
    if signals.intent_mode in {"AMBIGUOUS", "NEUTRAL"}:
        return True
    if len(signals.clauses) > 1:
        return True
    for finding in signals.findings:
        if (
            any(link.link_type != "same_clause" for link in finding.bounded_links)
            or finding.safe_context_cues
        ):
            return True
        if finding.intent_outcome == "DIRECT_HARM_ASSISTANCE" and (
            finding.actor_orientation != "USER"
            or any(mark in finding.clause.normalized_text for mark in ('"', "'", "‘", "’", "“", "”"))
        ):
            return True
    return False


def run_hybrid_strategy(
    question: str,
    provider: SafetyClassifierProvider,
) -> StrategyOutcome:
    deterministic = run_deterministic_strategy(question)
    if not deterministic_is_uncertain(question):
        return StrategyOutcome(
            "HYBRID",
            deterministic.decision,
            deterministic.candidate,
            False,
            True,
            None,
            0.0,
            0.0,
        )
    model = run_model_strategy(question, provider)
    if not model.classifier_valid or model.candidate is None:
        return StrategyOutcome(
            "HYBRID",
            model.decision,
            None,
            True,
            False,
            model.fallback_code,
            model.latency_ms,
            model.estimated_cost_usd,
        )
    deterministic_candidate_value = deterministic.candidate
    assert deterministic_candidate_value is not None
    deterministic_direct = (
        deterministic_candidate_value.intent_mode == "DIRECT_HARM_ASSISTANCE"
    )
    model_direct = model.candidate.intent_mode == "DIRECT_HARM_ASSISTANCE"
    deterministic_explicit_safe = deterministic_candidate_value.intent_mode in {
        "LAWFUL_COMPLIANCE",
        "VICTIM_OR_REPORTING",
        "PREVENTION_OR_PROTECTION",
        "DESCRIPTIVE_OR_QUOTED",
    }
    if deterministic_direct and not model_direct or deterministic_explicit_safe and model_direct:
        return StrategyOutcome(
            "HYBRID",
            "ASK_SAFETY_CLARIFICATION",
            model.candidate,
            True,
            True,
            "CLASSIFIER_DETERMINISTIC_CONFLICT",
            model.latency_ms,
            model.estimated_cost_usd,
        )
    return StrategyOutcome(
        "HYBRID",
        model.decision,
        model.candidate,
        True,
        True,
        model.fallback_code,
        model.latency_ms,
        model.estimated_cost_usd,
    )


__all__ = [
    "BackendSafetyDecision",
    "StrategyOutcome",
    "backend_decision",
    "deterministic_candidate",
    "deterministic_is_uncertain",
    "run_deterministic_strategy",
    "run_hybrid_strategy",
    "run_model_strategy",
]
