"""Two-axis conservative containment derived from canonical safety findings.

The suspicion layer is monotonic and non-authoritative.  It may only prevent
``CLEAR`` by producing ``SAFETY_UNCERTAIN``.  Exact harm rules remain the sole
authority for proven direct harm, and approved risk rules remain the sole
authority for high risk.
"""

from __future__ import annotations

from .analysis_state import (
    AnalysisInvariantError,
    CONTAINMENT_REASON_CODE_ORDER,
    CONTAINMENT_SIGNAL_ID_ORDER,
    RiskDisposition,
    SafetyAssessment,
    SafetyContainmentResult,
    SafetyDisposition,
)
from .safety_intent import ClauseSafetyFinding, SafetySignals, analyze_safety_intent
from .safety_registry import HARM_RULES, RISK_RULES

_HARM_RULE_IDS = tuple(rule.rule_id for rule in HARM_RULES)
_RISK_RULE_IDS = tuple(rule.rule_id for rule in RISK_RULES)

# These are registry atom names, not phrases.  Broad helper atoms such as
# ``help``, ``alter``, and ``provide_information`` cannot create suspicion by
# themselves; they require another safety-semantic atom below.
_STRONG_PARTIAL_ACTIONS = frozenset(
    {
        "evade",
        "forge",
        "delete",
        "destroy",
        "disable",
        "hide",
        "threaten",
        "coerce",
        "detain",
        "obstruct",
        "distort",
    }
)
_HARM_RELEVANT_OBJECTS = frozenset(
    {
        "police_authority",
        "required_appearance",
        "document",
        "evidence",
        "camera_data",
        "message",
        "investigation",
        "information",
        "person",
        "debtor",
        "property",
    }
)
_PARTIAL_OBJECTS = frozenset(
    {
        "evidence",
        "camera_data",
        "message",
        "person",
        "debtor",
        "property",
    }
)
_HARM_RELEVANT_OBJECTIVES = frozenset(
    {
        "appear_authentic",
        "pass_inspection",
        "false_content",
        "unusable",
        "prevent_recording",
        "prevent_discovery",
        "leave_no_trace",
        "avoid_detection",
        "force_payment",
        "frighten_person",
        "delay_investigation",
        "avoid_appearance",
        "wanted_person",
    }
)
_INTENT_KINDS = frozenset({"direct", "method", "application", "concealment"})


def _canonical_ids(values: set[str]) -> tuple[str, ...]:
    unknown = values.difference(CONTAINMENT_SIGNAL_ID_ORDER)
    if unknown:
        raise AnalysisInvariantError("canonical safety finding emitted an unknown signal")
    return tuple(value for value in CONTAINMENT_SIGNAL_ID_ORDER if value in values)


def _finding_signal_ids(finding: ClauseSafetyFinding) -> set[str]:
    return {
        *(atom.rule_id for atom in finding.concept_atoms),
        *(cue.stable_rule_id for cue in finding.direct_application_cues),
        *(cue.stable_rule_id for cue in finding.safe_context_cues),
        *(cue.stable_rule_id for cue in finding.concealment_cues),
        *(match.stable_rule_id for match in finding.harm_concepts),
    }


def _partial_unresolved_ids(finding: ClauseSafetyFinding) -> set[str]:
    """Return only concept-level unresolved provenance for one clause."""

    if finding.intent_outcome == "AMBIGUOUS":
        return {
            *(match.stable_rule_id for match in finding.harm_concepts),
            *(atom.rule_id for atom in finding.concept_atoms),
            *(cue.stable_rule_id for cue in finding.direct_application_cues),
            *(cue.stable_rule_id for cue in finding.safe_context_cues),
        }
    if finding.intent_outcome in {
        "LAWFUL_COMPLIANCE",
        "VICTIM_OR_REPORTING",
        "PREVENTION_OR_PROTECTION",
        "DESCRIPTIVE_OR_QUOTED",
    }:
        return set()
    if finding.harm_concepts:
        # Proven direct and resolved safe/descriptive relations are authoritative.
        return set()

    actions = tuple(
        atom for atom in finding.concept_atoms if atom.kind == "action"
    )
    objects = tuple(
        atom
        for atom in finding.concept_atoms
        if atom.kind == "object" and atom.name in _HARM_RELEVANT_OBJECTS
    )
    objectives = tuple(
        atom
        for atom in finding.concept_atoms
        if atom.kind == "objective" and atom.name in _HARM_RELEVANT_OBJECTIVES
    )
    strong_actions = tuple(
        atom for atom in actions if atom.name in _STRONG_PARTIAL_ACTIONS
    )
    intent_cues = tuple(
        cue
        for cue in finding.direct_application_cues + finding.concealment_cues
        if cue.cue_type in _INTENT_KINDS
        or cue.cue_type in {"direct_assistance", "method_request", "application"}
    )
    has_safety_composition_candidate = bool(
        strong_actions
        or objectives
        or intent_cues and any(atom.name in _PARTIAL_OBJECTS for atom in objects)
        or actions and objects and objectives
    )
    if not has_safety_composition_candidate:
        return set()
    return {
        *(atom.rule_id for atom in strong_actions + objects + objectives),
        *(cue.stable_rule_id for cue in intent_cues),
    }


def _unresolved_signal_ids(signals: SafetySignals) -> tuple[str, ...]:
    unresolved: set[str] = set()
    for finding in signals.findings:
        unresolved.update(_partial_unresolved_ids(finding))

    # A descriptive/quoted harm followed later by an unlinked application cue
    # is neither a proven application nor a resolved mention.  Immediate links
    # remain owned by the exact clause resolver.
    descriptive_harm_seen = False
    for finding in signals.findings:
        if finding.intent_outcome == "DESCRIPTIVE_OR_QUOTED" and finding.harm_concepts:
            descriptive_harm_seen = True
            continue
        unlinked_application = tuple(
            cue
            for cue in finding.direct_application_cues
            if cue.cue_type in {"application", "anaphoric_application"}
            and not finding.bounded_links
        )
        if descriptive_harm_seen and unlinked_application:
            unresolved.update(cue.stable_rule_id for cue in unlinked_application)

    return _canonical_ids(unresolved)


def _all_signal_ids(signals: SafetySignals, safety: SafetyAssessment) -> tuple[str, ...]:
    observed = set(safety.matched_rule_ids + safety.safe_context_rule_ids)
    observed.update(signals.high_risk_rule_ids)
    for finding in signals.findings:
        observed.update(_finding_signal_ids(finding))
    return _canonical_ids(observed)


def _reason_codes(
    safety_disposition: SafetyDisposition,
    risk_disposition: RiskDisposition,
    unresolved_signal_ids: tuple[str, ...],
) -> tuple[str, ...]:
    wanted = {
        {
            SafetyDisposition.PROVEN_DIRECT_HARM: "CONTAINMENT_PROVEN_DIRECT_HARM",
            SafetyDisposition.SAFETY_UNCERTAIN: "CONTAINMENT_SAFETY_UNCERTAIN",
            SafetyDisposition.CLEAR: "CONTAINMENT_CLEAR",
        }[safety_disposition],
        {
            RiskDisposition.HIGH_RISK: "CONTAINMENT_HIGH_RISK",
            RiskDisposition.NORMAL: "CONTAINMENT_NORMAL_RISK",
        }[risk_disposition],
    }
    if unresolved_signal_ids:
        wanted.add("CONTAINMENT_UNRESOLVED_SIGNAL")
    return tuple(code for code in CONTAINMENT_REASON_CODE_ORDER if code in wanted)


def validate_containment_against_safety(
    containment: SafetyContainmentResult,
    safety: SafetyAssessment,
) -> None:
    """Fail loudly when the two-axis state contradicts canonical policy state."""

    harm_ids = tuple(rule_id for rule_id in containment.signal_ids if rule_id in _HARM_RULE_IDS)
    risk_ids = tuple(rule_id for rule_id in containment.signal_ids if rule_id in _RISK_RULE_IDS)
    if containment.safety_disposition is SafetyDisposition.PROVEN_DIRECT_HARM:
        if not safety.unsafe_request or not harm_ids:
            raise AnalysisInvariantError("proven direct containment lacks exact harm authority")
    elif safety.unsafe_request:
        raise AnalysisInvariantError("exact direct harm was downgraded by containment")
    if containment.safety_disposition is SafetyDisposition.SAFETY_UNCERTAIN:
        if safety.unsafe_request:
            raise AnalysisInvariantError("suspicion cannot replace exact direct harm")
    elif (
        containment.safety_disposition is SafetyDisposition.CLEAR
        and containment.unresolved_signal_ids
    ):
        raise AnalysisInvariantError("clear containment retains unresolved safety")
    if containment.risk_disposition is RiskDisposition.HIGH_RISK:
        if not safety.high_risk or not risk_ids:
            raise AnalysisInvariantError("high-risk containment lacks approved risk authority")
    elif safety.high_risk:
        raise AnalysisInvariantError("approved high risk was cleared by containment")


def derive_safety_containment(
    normalized_question: str,
    safety: SafetyAssessment,
) -> SafetyContainmentResult:
    """Recompute the canonical two-axis state from safety-owner findings."""

    signals = analyze_safety_intent(normalized_question)
    direct_ids = tuple(match.stable_rule_id for match in signals.direct_harm_matches)
    if safety.unsafe_request != bool(direct_ids):
        raise AnalysisInvariantError("safety assessment and exact harm findings disagree")
    if safety.high_risk != bool(signals.high_risk_rule_ids):
        raise AnalysisInvariantError("safety assessment and approved risk findings disagree")

    unresolved = _unresolved_signal_ids(signals)
    if direct_ids:
        safety_disposition = SafetyDisposition.PROVEN_DIRECT_HARM
    elif unresolved:
        safety_disposition = SafetyDisposition.SAFETY_UNCERTAIN
    else:
        safety_disposition = SafetyDisposition.CLEAR
    risk_disposition = (
        RiskDisposition.HIGH_RISK if signals.high_risk_rule_ids else RiskDisposition.NORMAL
    )
    result = SafetyContainmentResult(
        safety_disposition,
        risk_disposition,
        _all_signal_ids(signals, safety),
        unresolved,
        _reason_codes(safety_disposition, risk_disposition, unresolved),
    )
    validate_containment_against_safety(result, safety)
    return result


__all__ = ["derive_safety_containment", "validate_containment_against_safety"]
