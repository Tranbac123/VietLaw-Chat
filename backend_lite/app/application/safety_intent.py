"""Pure bounded clause resolution built on the compositional safety grammar."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from .analysis_state import SafetyIntentMode
from .safety_grammar import (
    ActorOrientation,
    ClauseGrammar,
    ComposedHarm,
    ConceptAtom,
    OperatorSignal,
    analyze_clause_grammar,
    fold_text,
)
from .safety_registry import HARM_RULES, RISK_RULES, SAFE_CONTEXT_RULES, HarmFamily

ClauseIntent = Literal[
    "DIRECT_HARM_ASSISTANCE",
    "LAWFUL_COMPLIANCE",
    "VICTIM_OR_REPORTING",
    "PREVENTION_OR_PROTECTION",
    "DESCRIPTIVE_OR_QUOTED",
    "AMBIGUOUS",
    "NEUTRAL",
]


@dataclass(frozen=True, slots=True)
class Clause:
    clause_id: int
    normalized_text: str
    start_offset: int
    end_offset: int
    separator: str = ""


@dataclass(frozen=True, slots=True)
class HarmConceptMatch:
    family: HarmFamily
    stable_rule_id: str
    reason_code: str
    matched_span: tuple[int, int]
    canonical_concept: str


@dataclass(frozen=True, slots=True)
class IntentCue:
    cue_type: str
    stable_rule_id: str
    matched_span: tuple[int, int]


@dataclass(frozen=True, slots=True)
class ContextCue:
    cue_type: str
    stable_rule_id: str
    matched_span: tuple[int, int]
    target_family: HarmFamily | None = None


@dataclass(frozen=True, slots=True)
class BoundedLink:
    source_clause_id: int
    target_clause_id: int
    link_type: Literal[
        "same_clause",
        "immediate_anaphora",
        "immediate_safe_target",
    ]
    target_family: HarmFamily


@dataclass(frozen=True, slots=True)
class ClauseSafetyFinding:
    clause: Clause
    actor_orientation: ActorOrientation
    concept_atoms: tuple[ConceptAtom, ...]
    harm_concepts: tuple[HarmConceptMatch, ...]
    action_targets: tuple[HarmFamily, ...]
    direct_application_cues: tuple[IntentCue, ...]
    safe_context_cues: tuple[ContextCue, ...]
    concealment_cues: tuple[IntentCue, ...]
    bounded_links: tuple[BoundedLink, ...]
    ordered_reason_codes: tuple[str, ...]
    ordered_rule_ids: tuple[str, ...]
    intent_outcome: ClauseIntent


@dataclass(frozen=True, slots=True)
class SafetySignals:
    clauses: tuple[Clause, ...]
    findings: tuple[ClauseSafetyFinding, ...]
    direct_harm_matches: tuple[HarmConceptMatch, ...]
    high_risk_rule_ids: tuple[str, ...]
    high_risk_reason_codes: tuple[str, ...]
    safe_context_rule_ids: tuple[str, ...]
    intent_mode: SafetyIntentMode


_CLAUSE_SEPARATOR = re.compile(
    r"[.!?;:\n]+|\b(?:nhưng|còn\s+bây\s+giờ|trước\s+tiên|sau\s+đó|tuy\s+nhiên)\b",
    re.IGNORECASE,
)
_SAFE_CONTEXT_NAMES = (
    ("safety.context.safe_negation.v1", "safe_negation"),
    ("safety.context.victim_reporting.v1", "victim_reporting"),
    ("safety.context.prevention_protection.v1", "prevention"),
    ("safety.context.lawful_compliance.v1", "lawful_compliance"),
    ("safety.context.descriptive_quoted.v1", "descriptive"),
)
if tuple(rule_id for rule_id, _ in _SAFE_CONTEXT_NAMES) != SAFE_CONTEXT_RULES:
    raise RuntimeError("safe-context registry order is inconsistent")


def segment_clauses(normalized_question: str) -> tuple[Clause, ...]:
    """Split only at bounded punctuation and selected conjunction boundaries."""

    clauses: list[Clause] = []
    cursor = 0
    for boundary in _CLAUSE_SEPARATOR.finditer(normalized_question):
        _append_clause(
            clauses,
            normalized_question,
            cursor,
            boundary.start(),
            boundary.group(0),
        )
        cursor = boundary.end()
    _append_clause(clauses, normalized_question, cursor, len(normalized_question), "")
    if not clauses:
        stripped = normalized_question.strip()
        return (Clause(0, stripped, 0, len(normalized_question)),)
    return tuple(clauses)


def _append_clause(
    clauses: list[Clause],
    text: str,
    start: int,
    end: int,
    separator: str,
) -> None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start < end:
        clauses.append(Clause(len(clauses), text[start:end], start, end, separator))


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result)


def _as_harm_matches(
    grammar_harms: tuple[ComposedHarm, ...],
) -> tuple[HarmConceptMatch, ...]:
    return tuple(
        HarmConceptMatch(
            harm.family,
            harm.stable_rule_id,
            harm.reason_code,
            harm.matched_span,
            harm.canonical_concept,
        )
        for harm in grammar_harms
    )


def _intent_cues(operators: tuple[OperatorSignal, ...]) -> tuple[IntentCue, ...]:
    return tuple(
        IntentCue(operator.name, operator.rule_id, operator.matched_span)
        for operator in operators
    )


def _first_operator(
    operators: tuple[OperatorSignal, ...],
    kinds: tuple[str, ...],
) -> OperatorSignal | None:
    return next((operator for operator in operators if operator.kind in kinds), None)


def _context_cues(
    grammar: ClauseGrammar,
    matches: tuple[HarmConceptMatch, ...],
    *,
    safe_prevention: bool | None = None,
    victim_reporting: bool | None = None,
) -> tuple[ContextCue, ...]:
    target = matches[0].family if len(matches) == 1 else None
    enabled = (
        ("safe_negation", grammar.safe_negation, ("safe_negation",)),
        (
            "victim_reporting",
            grammar.victim_reporting
            if victim_reporting is None
            else victim_reporting,
            ("reporting",),
        ),
        (
            "prevention",
            grammar.safe_prevention
            if safe_prevention is None
            else safe_prevention,
            ("prevention", "preservation", "detection"),
        ),
        ("lawful_compliance", grammar.lawful_compliance, ("compliance",)),
        ("descriptive", grammar.descriptive, ("description",)),
    )
    result: list[ContextCue] = []
    for rule_id, registry_name in _SAFE_CONTEXT_NAMES:
        item = next(item for item in enabled if item[0] == registry_name)
        if not item[1]:
            continue
        operator = _first_operator(grammar.operators, item[2])
        span = (
            operator.matched_span
            if operator
            else grammar.harm_concepts[0].matched_span
            if grammar.harm_concepts
            else grammar.atoms[0].matched_span
            if grammar.atoms
            else (0, 0)
        )
        result.append(ContextCue(registry_name, rule_id, span, target))
    return tuple(result)


def _stable_matches(
    matches: tuple[HarmConceptMatch, ...],
) -> tuple[HarmConceptMatch, ...]:
    result: list[HarmConceptMatch] = []
    for rule in HARM_RULES:
        for match in matches:
            if match.stable_rule_id == rule.rule_id and not any(
                existing.stable_rule_id == match.stable_rule_id for existing in result
            ):
                result.append(match)
    return tuple(result)


def _append_risk(
    risks: list[tuple[str, str]],
    rule_id: str,
    reason: str,
) -> None:
    if not any(existing_id == rule_id for existing_id, _ in risks):
        risks.append((rule_id, reason))


def _explicit_question_risks(folded_question: str) -> tuple[tuple[str, str], ...]:
    risks: list[tuple[str, str]] = []
    if any(
        phrase in folded_question
        for phrase in ("tai nan nghiem trong", "tai nan chet", "tu vong")
    ):
        _append_risk(
            risks,
            "risk.serious_accident.v1",
            "RISK_SERIOUS_OR_FATAL_ACCIDENT",
        )
    if any(phrase in folded_question for phrase in ("khoi to", "truy cuu hinh su")):
        _append_risk(
            risks,
            "risk.criminal_exposure.v1",
            "RISK_CRIMINAL_EXPOSURE",
        )
    return tuple(risks)


def analyze_safety_intent(normalized_question: str) -> SafetySignals:
    """Resolve the current question without constructing policy state."""

    clauses = segment_clauses(normalized_question)
    findings: list[ClauseSafetyFinding] = []
    direct_matches: list[HarmConceptMatch] = []
    prior_matches: tuple[HarmConceptMatch, ...] = ()
    effective_context = {name: False for _, name in _SAFE_CONTEXT_NAMES}
    risks = list(_explicit_question_risks(fold_text(normalized_question)))
    exposure_needs_criminal_risk = False

    for clause in clauses:
        grammar = analyze_clause_grammar(clause.normalized_text, clause.start_offset)
        matches = _as_harm_matches(grammar.harm_concepts)
        direct_cues = list(
            _intent_cues(grammar.direct_operators + grammar.application_operators)
        )
        concealment_cues = _intent_cues(grammar.concealment_operators)
        links: list[BoundedLink] = []
        clause_direct: list[HarmConceptMatch] = []
        if grammar.direct_harm:
            clause_direct.extend(matches)
            links.extend(
                BoundedLink(
                    clause.clause_id,
                    clause.clause_id,
                    "same_clause",
                    match.family,
                )
                for match in matches
            )
        if not matches and prior_matches and grammar.application_operators:
            clause_direct.extend(prior_matches)
            links.extend(
                BoundedLink(
                    clause.clause_id - 1,
                    clause.clause_id,
                    "immediate_anaphora",
                    match.family,
                )
                for match in prior_matches
            )
            direct_cues.extend(
                IntentCue(
                    "anaphoric_application",
                    "safety.intent.immediate_anaphora.v1",
                    operator.matched_span,
                )
                for operator in grammar.application_operators
            )

        linked_prevention = bool(
            not matches
            and prior_matches
            and any(
                operator.kind in {"prevention", "preservation", "detection"}
                for operator in grammar.context_operators
            )
        )
        linked_reporting = bool(
            not matches
            and prior_matches
            and any(
                operator.kind == "reporting"
                for operator in grammar.context_operators
            )
        )
        if linked_prevention or linked_reporting:
            links.extend(
                BoundedLink(
                    clause.clause_id - 1,
                    clause.clause_id,
                    "immediate_safe_target",
                    match.family,
                )
                for match in prior_matches
            )

        if clause_direct:
            outcome: ClauseIntent = "DIRECT_HARM_ASSISTANCE"
            direct_matches.extend(clause_direct)
        elif grammar.safe_prevention or linked_prevention:
            outcome = "PREVENTION_OR_PROTECTION"
        elif grammar.victim_reporting or linked_reporting:
            outcome = "VICTIM_OR_REPORTING"
        elif grammar.lawful_compliance:
            outcome = "LAWFUL_COMPLIANCE"
        elif grammar.descriptive:
            outcome = "DESCRIPTIVE_OR_QUOTED"
        elif matches:
            outcome = "AMBIGUOUS"
        else:
            outcome = "NEUTRAL"

        context_cues = _context_cues(
            grammar,
            matches or prior_matches if linked_prevention or linked_reporting else matches,
            safe_prevention=grammar.safe_prevention or linked_prevention,
            victim_reporting=grammar.victim_reporting or linked_reporting,
        )
        for cue in context_cues:
            registry_name = next(
                name for rule_id, name in _SAFE_CONTEXT_NAMES if rule_id == cue.stable_rule_id
            )
            effective_context[registry_name] = True

        evasion_with_notice = any(
            match.family == "EVASION" for match in matches
        ) and any(
            atom.kind == "object"
            and atom.name == "official_notice"
            and atom.lexeme == "giay trieu tap"
            for atom in grammar.atoms
        )
        if grammar.personal_police_contact or evasion_with_notice:
            _append_risk(risks, "risk.police_contact.v1", "RISK_POLICE_CONTACT")
        if grammar.actor_orientation == "VICTIM_USER" and matches:
            if any(match.family == "COERCION_OR_THREAT" for match in matches):
                property_risk = "bi cuong ep" in grammar.folded_text or any(
                    match.stable_rule_id == "safety.property_coercion.v1"
                    for match in matches
                )
                _append_risk(
                    risks,
                    "risk.property_seizure.v1"
                    if property_risk
                    else "risk.threat_received.v1",
                    "RISK_PROPERTY_SEIZURE_OR_COERCION"
                    if property_risk
                    else "RISK_VIOLENCE_OR_THREAT_RECEIVED",
                )
        targeted_matches = matches or prior_matches if linked_prevention or linked_reporting else matches
        if targeted_matches and not clause_direct and (
            grammar.victim_reporting
            or linked_reporting
            or (grammar.safe_prevention or linked_prevention)
            and grammar.actor_orientation == "THIRD_PARTY"
        ):
            exposure_needs_criminal_risk = True

        findings.append(
            ClauseSafetyFinding(
                clause,
                grammar.actor_orientation,
                grammar.atoms,
                matches,
                tuple(match.family for match in targeted_matches),
                tuple(direct_cues),
                context_cues,
                concealment_cues,
                tuple(links),
                _ordered_unique(tuple(match.reason_code for match in matches)),
                tuple(match.stable_rule_id for match in matches),
                outcome,
            )
        )
        prior_matches = matches

    stable_direct = _stable_matches(tuple(direct_matches))
    if exposure_needs_criminal_risk and not stable_direct and not risks:
        _append_risk(
            risks,
            "risk.criminal_exposure.v1",
            "RISK_CRIMINAL_EXPOSURE",
        )
    risks = [
        next(item for item in risks if item[0] == rule_id)
        for rule_id in tuple(rule.rule_id for rule in RISK_RULES)
        if any(existing_id == rule_id for existing_id, _ in risks)
    ]

    if stable_direct:
        intent_mode: SafetyIntentMode = "DIRECT_HARM_ASSISTANCE"
        safe_context_ids: tuple[str, ...] = ()
    else:
        unresolved_harm = any(
            finding.intent_outcome == "AMBIGUOUS" for finding in findings
        )
        if risks:
            if effective_context["prevention"]:
                intent_mode = "PREVENTION_OR_PROTECTION"
            elif effective_context["victim_reporting"]:
                intent_mode = "VICTIM_OR_REPORTING"
            else:
                intent_mode = "LAWFUL_COMPLIANCE"
                effective_context["lawful_compliance"] = True
        elif unresolved_harm:
            intent_mode = "AMBIGUOUS"
        elif effective_context["prevention"]:
            intent_mode = "PREVENTION_OR_PROTECTION"
        elif effective_context["victim_reporting"]:
            intent_mode = "VICTIM_OR_REPORTING"
        elif effective_context["lawful_compliance"]:
            intent_mode = "LAWFUL_COMPLIANCE"
        elif effective_context["descriptive"]:
            intent_mode = "DESCRIPTIVE_OR_QUOTED"
        else:
            intent_mode = "NEUTRAL"
        safe_context_ids = (
            ()
            if intent_mode == "AMBIGUOUS"
            else tuple(
                rule_id
                for rule_id, name in _SAFE_CONTEXT_NAMES
                if effective_context[name]
            )
        )

    return SafetySignals(
        clauses,
        tuple(findings),
        stable_direct,
        tuple(rule_id for rule_id, _ in risks),
        tuple(reason for _, reason in risks),
        safe_context_ids,
        intent_mode,
    )


__all__ = [
    "BoundedLink",
    "Clause",
    "ClauseSafetyFinding",
    "ContextCue",
    "HarmConceptMatch",
    "IntentCue",
    "SafetySignals",
    "analyze_safety_intent",
    "fold_text",
    "segment_clauses",
]
